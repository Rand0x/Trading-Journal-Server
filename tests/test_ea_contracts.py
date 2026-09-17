"""EA source/payload contracts; these tests do not compile or run MQL."""
from pathlib import Path
import ast
import json
import re
import unittest

from server.models import MQLSyncPayload

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "server" / "static" / "downloads"


def function_body(source, name):
    definition = re.search(r"(?m)^(?:void|string|double|int) " + re.escape(name) + r"\([^;]*?\)\s*\{", source)
    if not definition:
        raise AssertionError("Missing EA function: " + name)
    start = source.index("{", definition.start())
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start + 1:end - 1]


def render_mql_format(body, values):
    """Execute the EA's actual JSON format and scalar arguments with Python shims."""
    match = re.search(r'return StringFormat\(\s*("(?:\\.|[^"\\])*")\s*,(.*?)\);', body, re.S)
    if not match:
        raise AssertionError("Missing JSON StringFormat return")
    fmt = ast.literal_eval(match.group(1))
    shims = dict(IntegerToString=str, TimeToString=lambda time, flags: time,
                 JsonEscape=lambda text: json.dumps(text)[1:-1],
                 TIME_DATE=1, TIME_SECONDS=2, **values)
    args = eval("(" + match.group(2) + ",)", {"__builtins__": {}}, shims)
    return json.loads(fmt % args)


def mql_scalar(body, variable, values):
    """Evaluate one real EA arithmetic expression, not a copied Python formula."""
    match = re.search(r"double " + variable + r" = ([^;]+);", body)
    if not match:
        raise AssertionError("Missing scalar expression: " + variable)
    return eval(match.group(1), {"__builtins__": {}}, dict(MathMin=min, **values))


class EATimerContracts(unittest.TestCase):
    def test_mt4_state_change_returns_before_cached_unsigned_subtraction(self):
        body = function_body((DOWNLOADS / "TradeJournalSync.mq4").read_text(), "OnTimer")
        branch = re.search(r"if\(change > 0\)\s*\{([^}]+)\}", body).group(1)
        self.assertRegex(branch, r"RequestSync\([^;]+;\s*(?://[^\n]*\n\s*)*return;",
                         "A synchronous upload advances g_lastSyncTick beyond cached now")
        # Execute the uint32 elapsed-time regression, including actual wraparound.
        now, finished = 10000, 10125
        self.assertGreaterEqual((now - finished) & 0xffffffff, 60000)
        self.assertEqual((0x20 - 0xfffffff0) & 0xffffffff, 48)


class MT5HistoryContracts(unittest.TestCase):
    def setUp(self):
        self.source = (DOWNLOADS / "TradeJournalSync.mq5").read_text()

    def test_open_snapshot_keeps_sub_centilot_volume(self):
        body = function_body(self.source, "SyncToServer").split("// Open positions")[1].split("// Pending orders")[0]
        self.assertIn('"lots":%.8f', body.replace('\\"', '"'))

    def test_actual_partial_payload_preserves_deal_identity_and_net_fees(self):
        partial = function_body(self.source, "BuildPartialCloseJson")
        history = function_body(self.source, "BuildPositionHistoryJson")
        totals = dict(closedVolume=0., exitValue=0., profit=0., commission=0., swap=0.)
        records = []
        for ticket, volume, price, gross, commission, swap, close in (
            (9007199254741001, .001, 1.12, 10, -.12, -.03, "2026.09.16 10:15:01"),
            (9007199254741002, .002, 1.13, -4, -.24, -.06, "2026.09.16 10:45:02"),
        ):
            values = dict(ticket=ticket, volume=volume, price=price, gross=gross,
                          commission=commission, swap=swap, closeTime=close)
            record = render_mql_format(partial, values)
            self.assertEqual(record["ticket"], str(ticket))
            self.assertEqual(record["volume"], volume)
            self.assertEqual(record["close_time"], close)
            self.assertAlmostEqual(record["net_profit"], gross + commission + swap)
            self.assertEqual(record["gross_profit"], gross)
            self.assertEqual(render_mql_format(partial, values), record)
            records.append(record)
            totals.update(closeVolume=volume, price=price, gross=gross,
                          partialCommission=commission, dealSwap=swap)
            for variable in ("closedVolume", "exitValue", "profit", "commission", "swap"):
                statement = re.search(variable + r" \+= [^;]+", history).group(0)
                exec(statement, {"__builtins__": {}}, totals)
        self.assertEqual(len({r["ticket"] for r in records}), 2)
        self.assertAlmostEqual(totals["closedVolume"], .003)
        self.assertAlmostEqual(totals["profit"], 6)
        self.assertAlmostEqual(totals["commission"], -.36)
        self.assertAlmostEqual(totals["swap"], -.09)
        for remaining in (.007, 0):
            values = dict(positionId=71, orderTicket=61, symbol="EURUSD", posType=0,
                          remainingVolume=remaining, entryValue=.011, entryVolume=.01,
                          openTime="2026.07.01 10:00:00", closeTimeJson="null" if remaining else '"2026.09.16 10:45:02"',
                          sl=1, tp=1.2, **totals,
                          comment='entry "note"', partials=json.dumps(records), candlesJson="[]")
            for name in ("volume", "openPrice", "closePrice"):
                values[name] = mql_scalar(history, name, values)
            parent = render_mql_format(history, values)
            payload = MQLSyncPayload(account_number="test", balance=100, equity=100,
                                     platform="MT5", closed_trades=[parent])
            trade = payload.closed_trades[0]
            self.assertEqual(trade.ticket, "71")
            self.assertEqual(trade.position_id, "71")
            self.assertAlmostEqual(trade.lots, .003 + remaining)
            self.assertEqual(trade.open_time, "2026-07-01 10:00:00")
            self.assertEqual(trade.close_time, None if remaining else "2026-09-16 10:45:02")
            self.assertAlmostEqual(trade.close_price, 1.12666667)
            self.assertAlmostEqual(sum(p.net_profit for p in trade.partial_closes), 5.55)

    def test_entry_fee_allocation_is_stable_as_later_exits_arrive(self):
        history = function_body(self.source, "BuildPositionHistoryJson")
        values = dict(exposure=1., entryCommissionPool=-2.)
        commissions = []
        for volume, fee in ((.4, -.4), (.6, -.6)):
            values.update(dealVolume=volume, fee=fee)
            for name in ("closeVolume", "entryFee", "exitFee", "partialCommission"):
                values[name] = mql_scalar(history, name, values)
            commissions.append(values["partialCommission"])
            # Run the EA's own state updates, preserving chronological fee pools.
            for variable in ("entryCommissionPool", "exposure"):
                statement = re.search(variable + r" -= [^;]+", history).group(0)
                exec(statement, {"__builtins__": {}}, values)
        self.assertAlmostEqual(commissions[0], -1.2)
        self.assertAlmostEqual(commissions[1], -1.8)
        self.assertAlmostEqual(sum(commissions), -3.)
        self.assertAlmostEqual(values["exposure"], 0)
        self.assertAlmostEqual(values["entryCommissionPool"], 0)
        # A reversal's reported volume includes an opening leg: only close exposure.
        values = dict(exposure=.4, entryCommissionPool=-.8, dealVolume=1., fee=-1.)
        for name in ("closeVolume", "entryFee", "exitFee", "partialCommission", "reverseVolume"):
            values[name] = mql_scalar(history, name, values)
        self.assertAlmostEqual(values["closeVolume"], .4)
        self.assertAlmostEqual(values["reverseVolume"], .6)
        self.assertAlmostEqual(values["partialCommission"], -1.2)

    def test_exit_deals_are_grouped_by_position_before_serialization(self):
        source = (DOWNLOADS / "TradeJournalSync.mq5").read_text()
        sync = function_body(source, "SyncToServer").split("// Open positions")[0]
        self.assertIn("HistorySelectByPosition(positionIds[i])", sync)
        self.assertIn("positionIds[j] == positionId", sync)
        self.assertIn("BuildPositionHistoryJson(positionIds[i]", sync)
        # Selecting full position history must not invalidate the discovery loop.
        self.assertLess(sync.index("positionIds[j] == positionId"),
                        sync.index("HistorySelectByPosition(positionIds[i])"))
        history = function_body(source, "BuildPositionHistoryJson")
        for contract in ("DEAL_ENTRY_OUT_BY", "DEAL_ENTRY_INOUT", "POSITION_IDENTIFIER",
                         "closedVolume + remainingVolume", "openTime == 0 || dealTime < openTime",
                         "BuildPartialCloseJson", "entryCommissionPool", "DEAL_FEE"):
            self.assertIn(contract, history)
        self.assertNotIn("closeTime - 3600", history)
        self.assertIn('"partial_closes":%s', history.replace('\\"', '"'))


if __name__ == "__main__":
    unittest.main()

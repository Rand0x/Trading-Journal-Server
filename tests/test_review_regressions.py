"""Regression tests for bugs found during the code review.

Each test documents one concrete failure scenario so the fix stays in place.
"""
import os
import tempfile
import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from server.analytics import (
    calculate_trade_metrics,
    get_calendar_heatmap,
    get_cost_of_mistakes,
)
from server.connectors.ctrader_api import CTraderConnector
from server.connectors.statement_parser import _parse_mt4_html, parse_and_import_statement
from server.database import get_connection, init_db
from server.main import app


class TestAnalyticsRegressions(unittest.TestCase):
    def test_max_drawdown_pct_is_tracked_independently_of_amount(self):
        # 10,000 -> 9,000 is a 10% drawdown. Later, 100,000 -> 98,500 is a
        # larger amount (1,500) but only 1.5%. The max % must stay 10%.
        trades = [
            {"net_profit": -1000.0, "status": "LOSS", "close_time": "2026-01-01 10:00:00"},
            {"net_profit": 91000.0, "status": "WIN", "close_time": "2026-01-02 10:00:00"},
            {"net_profit": -1500.0, "status": "LOSS", "close_time": "2026-01-03 10:00:00"},
        ]
        m = calculate_trade_metrics(trades, initial_balance=10000.0)
        self.assertEqual(m["max_drawdown_amount"], 1500.0)
        self.assertEqual(m["max_drawdown_pct"], 10.0)

    def test_calendar_ignores_open_floating_trades(self):
        trades = [
            {"net_profit": 100.0, "status": "WIN", "open_time": "2026-09-01 09:00:00", "close_time": "2026-09-01 10:00:00"},
            {"net_profit": -80.0, "status": "OPEN", "open_time": "2026-09-02 09:00:00", "close_time": None},
        ]
        heatmap = get_calendar_heatmap(trades)
        self.assertIn("2026-09-01", heatmap)
        self.assertNotIn("2026-09-02", heatmap)

    def test_cost_of_mistakes_ignores_unrealized_and_missed_trades(self):
        mistakes = {1: "FOMO Entry"}
        trades = [
            {"mistake_id": 1, "net_profit": -50.0, "status": "LOSS", "close_time": "2026-09-01 10:00:00"},
            {"mistake_id": 1, "net_profit": -500.0, "status": "OPEN", "close_time": None},
            {"mistake_id": 1, "net_profit": 0.0, "status": "PENDING", "close_time": None},
            {"mistake_id": 1, "net_profit": 0.0, "status": "CANCELLED", "close_time": None},
            {"mistake_id": 1, "net_profit": -300.0, "status": "LOSS", "is_missed": 1, "close_time": "2026-09-01 11:00:00"},
        ]
        result = get_cost_of_mistakes(trades, mistakes)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["count"], 1)
        self.assertEqual(result[0]["total_loss"], 50.0)


class TestStatementParserRegressions(unittest.TestCase):
    MT4_ROW = (
        '<tr><td>{ticket}</td><td>2026.08.20 10:15:00</td><td>buy</td><td>1.00</td>'
        '<td>eurusd</td><td>1.08200</td><td>1.08000</td><td>1.08600</td>'
        '<td>2026.08.20 12:00:00</td><td>1.08550</td><td>-7.00</td><td>-1.00</td>'
        '<td>-2.00</td><td>{profit}</td></tr>'
    )

    def test_mt4_net_profit_includes_commission_taxes_and_swap(self):
        html = "<b>Closed Transactions:</b><table>" + self.MT4_ROW.format(ticket="1", profit="350.00") + "</table>"
        trades = _parse_mt4_html(html)
        self.assertEqual(len(trades), 1)
        self.assertAlmostEqual(trades[0]["gross_profit"], 350.0)
        self.assertAlmostEqual(trades[0]["net_profit"], 340.0)
        self.assertAlmostEqual(trades[0]["commission"], -8.0)
        self.assertAlmostEqual(trades[0]["swap"], -2.0)

    def test_mt4_parses_space_thousand_separators(self):
        html = "<b>Closed Transactions:</b><table>" + self.MT4_ROW.format(ticket="2", profit="1 250.00") + "</table>"
        trades = _parse_mt4_html(html)
        self.assertEqual(len(trades), 1)
        self.assertAlmostEqual(trades[0]["gross_profit"], 1250.0)


class TestReviewApiRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        os.environ["DB_DIR"] = cls.temp_dir.name
        init_db()
        cls.client = TestClient(app)
        now_str = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO accounts (name, platform, account_number, api_key, created_at, updated_at)
                VALUES ('Review Acc', 'cTrader', 'rev-1', 'key_review_1', ?, ?);
                """,
                (now_str, now_str),
            )
            conn.commit()
            cls.account_id = cursor.lastrowid

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()
        os.environ.pop("DB_DIR", None)

    def _insert_trade(self, ticket, open_time, close_time, net_profit, status="WIN"):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trades (account_id, ticket, symbol, direction, volume, open_time, close_time,
                                    open_price, close_price, net_profit, status, created_at, updated_at)
                VALUES (?, ?, 'DATEFILTER', 'BUY', 1.0, ?, ?, 1.1, 1.2, ?, ?, ?, ?);
                """,
                (self.account_id, ticket, open_time, close_time, net_profit, status, open_time, open_time),
            )
            conn.commit()
            return cursor.lastrowid

    def test_date_to_includes_iso_timestamps_on_the_last_day(self):
        # cTrader (cBot and Open API) stores ISO timestamps with a "T" separator.
        self._insert_trade("iso-day", "2026-05-10T15:30:00.0000000Z", "2026-05-10T16:00:00.0000000Z", 42.0)
        self._insert_trade("iso-next-day", "2026-05-11T00:00:00.0000000Z", "2026-05-11T01:00:00.0000000Z", 7.0)
        params = {"account_id": self.account_id, "date_from": "2026-05-10", "date_to": "2026-05-10"}

        res = self.client.get("/api/trades", params={**params, "symbol": "DATEFILTER"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual([t["ticket"] for t in res.json()["trades"]], ["iso-day"])

        res = self.client.get("/api/dashboard", params={**params, "symbol": "DATEFILTER"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["metrics"]["net_profit"], 42.0)

        res = self.client.get("/api/analytics/symbol", params=params)
        self.assertEqual(res.status_code, 200)
        rows = {r["symbol"]: r for r in res.json()}
        self.assertEqual(rows["DATEFILTER"]["net_profit"], 42.0)

    def test_create_trade_with_duplicate_ticket_returns_conflict(self):
        body = {
            "account_id": self.account_id, "ticket": "dup-ticket", "symbol": "EURUSD",
            "direction": "BUY", "volume": 1.0, "open_time": "2026-09-01 10:00",
            "open_price": 1.1, "close_price": 1.2, "close_time": "2026-09-01 11:00", "net_profit": 10.0,
        }
        first = self.client.post("/api/trades", json=body)
        self.assertEqual(first.status_code, 200)
        self.assertIsNotNone(first.json())

        second = self.client.post("/api/trades", json=body)
        self.assertEqual(second.status_code, 409)

    def test_update_recomputes_r_from_initial_risk_without_stop_loss(self):
        body = {
            "account_id": self.account_id, "symbol": "EURUSD", "direction": "BUY", "volume": 1.0,
            "open_time": "2026-09-02 10:00", "open_price": 1.1, "close_price": 1.2,
            "close_time": "2026-09-02 11:00", "net_profit": 100.0, "initial_risk": 50.0,
        }
        created = self.client.post("/api/trades", json=body).json()
        self.assertEqual(created["r_multiple"], 2.0)

        updated = self.client.put(f"/api/trades/{created['id']}", json={"net_profit": 150.0}).json()
        self.assertEqual(updated["r_multiple"], 3.0)

    def _import(self, filename, content_bytes):
        return self.client.post(
            "/api/sync/import",
            files={"file": (filename, content_bytes)},
            data={"account_id": str(self.account_id)},
        )

    def test_reimport_reports_duplicates_and_distinct_files_do_not_collide(self):
        file_a = (
            "Date,Ticker,Type,Quantity,Entry Price,Exit Price,Net P&L,Notes\n"
            "2026-08-15 09:30,XAUUSD,Long,0.50,2480.00,2495.00,750.00,A1\n"
        )
        file_b = (
            "Date,Ticker,Type,Quantity,Entry Price,Exit Price,Net P&L,Notes\n"
            "2026-08-16 13:00,US30,Short,0.20,40500,40650,-300.00,B1\n"
        )
        first = self._import("a.csv", file_a.encode()).json()
        self.assertEqual((first["imported"], first["skipped"]), (1, 0))

        again = self._import("a.csv", file_a.encode()).json()
        self.assertEqual((again["imported"], again["skipped"]), (0, 1))

        other = self._import("b.csv", file_b.encode()).json()
        self.assertEqual((other["imported"], other["skipped"]), (1, 0))

    def test_import_strips_utf8_bom_from_csv_headers(self):
        bom_csv = (
            "Deal ID,Symbol,Opening Direction,Volume,Opening Time,Closing Time,Entry Price,Closing Price,Net USD\n"
            "bom-1,EURUSD,Buy,100000,2026-08-10 10:00:00,2026-08-10 11:30:00,1.08500,1.08800,290.00\n"
        ).encode("utf-8-sig")
        res = self._import("ctrader.csv", bom_csv)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["imported"], 1)
        with get_connection() as conn:
            row = conn.execute(
                "SELECT symbol, direction FROM trades WHERE account_id = ? AND ticket = 'bom-1';",
                (self.account_id,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual((row["symbol"], row["direction"]), ("EURUSD", "BUY"))

    def test_live_candles_keep_their_own_timeframe(self):
        from server.routers.sync import upload_candles
        bar = {"symbol": "LIVETF", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1}
        upload_candles({"candles": [
            {**bar, "timeframe": "H1", "time": 3600 * 500},
            {**bar, "timeframe": "D1", "time": 86400 * 20},
        ]})
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT timeframe, timestamp FROM market_candles WHERE symbol = 'LIVETF' ORDER BY timestamp;"
            ).fetchall()
        self.assertEqual([(r["timeframe"], r["timestamp"]) for r in rows], [("D1", 86400 * 20), ("H1", 3600 * 500)])

    def _mql(self, **lists):
        from server.connectors.mql_receiver import process_mql_payload
        from server.models import MQLSyncPayload
        payload = MQLSyncPayload(source="mql", account_number="rev-1", balance=10000.0, equity=10000.0,
                                 pending_orders=lists.get("pending", []), open_trades=lists.get("open", []),
                                 closed_trades=lists.get("closed", []))
        return process_mql_payload("key_review_1", payload)

    def _rows_for(self, symbol):
        with get_connection() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM trades WHERE account_id = ? AND symbol = ? ORDER BY id;", (self.account_id, symbol)
            ).fetchall()]

    def test_mt5_fill_links_pending_order_without_order_id(self):
        pending = {"ticket": "mt5-order-501", "order_id": "501", "symbol": "MTFILL", "type": 0, "lots": 1.0,
                   "open_time": "2026-09-01 09:00:00", "open_price": 1.1000, "status": "PENDING"}
        self._mql(pending=[pending])
        with get_connection() as conn:
            conn.execute("UPDATE trades SET notes = 'Entry plan', setup_id = 1 WHERE ticket = 'mt5-order-501';")
            conn.commit()
        # The MT5 EA reports the filled position by position id only.
        self._mql(open=[{"ticket": "501", "position_id": "501", "symbol": "MTFILL", "type": 0, "lots": 1.0,
                         "open_time": "2026-09-01 10:00:00", "open_price": 1.1002, "profit": 5.0}])
        rows = self._rows_for("MTFILL")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["ticket"], rows[0]["status"], rows[0]["order_id"]), ("501", "OPEN", "501"))
        self.assertEqual((rows[0]["notes"], rows[0]["setup_id"]), ("Entry plan", 1))

    def test_mt4_fill_and_close_between_syncs_uses_broker_entry(self):
        pending = {"ticket": "mt4-order-77", "order_id": "77", "symbol": "MT4FILL", "type": 0, "lots": 0.5,
                   "open_time": "2026-09-01 08:00:00", "open_price": 1.2000, "status": "PENDING"}
        self._mql(pending=[pending])
        self._mql(pending=[], closed=[{"ticket": "77", "symbol": "MT4FILL", "type": 0, "lots": 0.4,
                                       "open_time": "2026-09-01 09:30:00", "close_time": "2026-09-01 11:00:00",
                                       "open_price": 1.2001, "close_price": 1.2050, "profit": 20.0}])
        rows = self._rows_for("MT4FILL")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["status"], "WIN")
        self.assertEqual((row["open_time"], row["open_price"], row["volume"]), ("2026-09-01 09:30:00", 1.2001, 0.4))

    def test_search_by_date_finds_that_days_trades(self):
        self._insert_trade("search-day", "2026-04-02T08:00:00Z", "2026-04-03T09:00:00Z", 5.0)
        res = self.client.get("/api/trades", params={"account_id": self.account_id, "search": "2026-04-03"})
        self.assertIn("search-day", [t["ticket"] for t in res.json()["trades"]])

    def test_weekly_review_has_no_best_trade_in_a_losing_week(self):
        from server.analytics import get_weekly_review
        from datetime import date
        today = date.today().isoformat()
        review = get_weekly_review([
            {"net_profit": -10.0, "status": "LOSS", "close_time": f"{today} 10:00:00"},
            {"net_profit": -40.0, "status": "LOSS", "close_time": f"{today} 11:00:00"},
        ])
        self.assertIsNone(review["best_trade"])
        self.assertEqual(review["worst_trade"]["net_profit"], -40.0)

    def test_ctrader_sync_with_blank_secret_keeps_stored_credentials(self):
        with get_connection() as conn:
            conn.execute(
                "UPDATE accounts SET ctrader_client_secret = 'stored-secret', ctrader_access_token = 'stored-token' WHERE id = ?;",
                (self.account_id,),
            )
            conn.commit()
        self.client.post("/api/sync/ctrader", json={
            "account_id": self.account_id, "client_id": "cid", "client_secret": "",
            "access_token": "", "ctrader_account_id": "", "is_live": False,
        })
        with get_connection() as conn:
            row = conn.execute(
                "SELECT ctrader_client_secret, ctrader_access_token FROM accounts WHERE id = ?;", (self.account_id,)
            ).fetchone()
        self.assertEqual((row["ctrader_client_secret"], row["ctrader_access_token"]), ("stored-secret", "stored-token"))

    def test_ctrader_open_api_closing_deal_keeps_position_direction(self):
        # Closing a long position is a SELL deal (tradeSide 2) in cTrader.
        remote = {
            "balance": 10100.0, "equity": 10100.0, "money_digits": 2,
            "symbols": {"1": "EURUSD"},
            "deals": [{
                "dealId": 555001, "symbolId": 1, "tradeSide": 2, "filledVolume": 100000,
                "executionPrice": 1.0900, "executionTimestamp": 1767261600000,
                "closePositionDetail": {"entryPrice": 1.0800, "grossProfit": 10000, "swap": 0, "commission": 0},
            }],
            "orders": [],
        }
        connector = CTraderConnector("client", "secret", "token", "123")
        connector._persist_synced_data(self.account_id, remote)
        with get_connection() as conn:
            row = conn.execute(
                "SELECT direction, net_profit FROM trades WHERE account_id = ? AND ticket = '555001';",
                (self.account_id,),
            ).fetchone()
        self.assertEqual(row["direction"], "BUY")
        self.assertEqual(row["net_profit"], 100.0)


if __name__ == "__main__":
    unittest.main()

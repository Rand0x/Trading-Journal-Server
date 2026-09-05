"""Tests for connector behavior that can run without broker credentials."""

import asyncio
import unittest

from server.connectors.ctrader_api import CTraderConnector


class _FakeSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []

    async def send(self, message):
        self.sent.append(message)

    async def recv(self):
        return self.messages.pop(0)


class TestCTraderConnector(unittest.TestCase):
    def test_request_round_trip(self):
        socket = _FakeSocket([
            '{"payloadType": 2101, "payload": {"ok": true}}'
        ])
        connector = CTraderConnector("client", "secret", "token", "123")

        result = asyncio.run(connector._request(socket, 2100, {"clientId": "client"}, 2101))

        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(socket.sent), 1)
        self.assertIn('"payloadType": 2100', socket.sent[0])

    def test_request_surfaces_api_error(self):
        socket = _FakeSocket([
            '{"payloadType": 2142, "payload": {"errorCode": "AUTH_FAILED", "description": "invalid token"}}'
        ])
        connector = CTraderConnector("client", "secret", "token", "123")

        with self.assertRaisesRegex(ValueError, "AUTH_FAILED"):
            asyncio.run(connector._request(socket, 2100, {}, 2101))


import os
import tempfile
from server.database import init_db, get_connection
from server.connectors.mql_receiver import process_mql_payload
from server.models import MQLSyncPayload, MQLTradeItem, TradePartialCloseBase


class TestMQLReceiverPreservation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        os.environ["DB_DIR"] = cls.temp_dir.name
        init_db()

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO accounts (name, platform, account_number, server_name, api_key, created_at, updated_at)
                VALUES ('Sync Test Acc', 'MT5', 'sync-acc-100', 'Broker-Demo', 'key_sync_test_123', '2026-09-01T00:00:00Z', '2026-09-01T00:00:00Z');
            """)
            conn.commit()
            cls.account_id = cursor.lastrowid
            cls.api_key = "key_sync_test_123"

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()
        os.environ.pop("DB_DIR", None)

    def test_mql_close_preserves_notes_emotions_and_computes_r(self):
        # 1. Pre-insert a trade with notes, structured notes, emotions, signals, initial_risk
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trades (
                    account_id, ticket, symbol, direction, volume,
                    open_time, open_price, stop_loss, take_profit,
                    initial_risk, risk_mode, status,
                    notes, pre_trade_notes, post_trade_notes, key_learnings,
                    emotion_pre, emotion_during, signals,
                    created_at, updated_at
                ) VALUES (
                    ?, 'ticket-sync-1', 'EURUSD', 'BUY', 1.0,
                    '2026-09-03 10:00:00', 1.0800, 1.0750, 1.0950,
                    100.0, 'CURRENCY', 'OPEN',
                    'User original notes', 'Identified key support', 'Execution was prompt', 'Held to target',
                    'Disciplined', 'Calm', 'Support Bounce,OB',
                    '2026-09-03T10:00:00Z', '2026-09-03T10:00:00Z'
                );
            """, (self.account_id,))
            conn.commit()
            trade_id = cursor.lastrowid

        # 2. Receive closing payload from broker with profit 300.0 (3R)
        payload = MQLSyncPayload(
            source="mql",
            account_number="sync-acc-100",
            balance=10300.0,
            equity=10300.0,
            closed_trades=[
                MQLTradeItem(
                    ticket="ticket-sync-1",
                    symbol="EURUSD",
                    type=0,
                    lots=1.0,
                    open_time="2026-09-03 10:00:00",
                    close_time="2026-09-03 14:00:00",
                    open_price=1.0800,
                    close_price=1.0950,
                    stop_loss=1.0750,
                    take_profit=1.0950,
                    profit=300.0
                )
            ]
        )

        res = process_mql_payload(self.api_key, payload)
        self.assertEqual(res["updated_trades"], 1)

        # 3. Verify in DB
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE id = ?;", (trade_id,))
            t = dict(cursor.fetchone())

            self.assertEqual(t["status"], "WIN")
            self.assertEqual(t["net_profit"], 300.0)
            self.assertAlmostEqual(t["r_multiple"], 3.0, places=2)
            # Verify user metadata is intact
            self.assertEqual(t["pre_trade_notes"], "Identified key support")
            self.assertEqual(t["post_trade_notes"], "Execution was prompt")
            self.assertEqual(t["key_learnings"], "Held to target")
            self.assertEqual(t["emotion_pre"], "Disciplined")
            self.assertEqual(t["emotion_during"], "Calm")
            self.assertEqual(t["signals"], "Support Bounce,OB")

    def test_ctrader_grouped_dynamic_tps(self):
        # Test cTrader grouped partial closes (dynamic TPs: e.g. 3 partial scale-outs)
        payload = MQLSyncPayload(
            source="ctrader-cbot",
            account_number="sync-acc-100",
            balance=10500.0,
            equity=10500.0,
            closed_trades=[
                MQLTradeItem(
                    ticket="ct-grouped-1",
                    symbol="GBPJPY",
                    type=0,
                    lots=3.0,
                    open_time="2026-09-03 12:00:00",
                    open_price=190.00,
                    stop_loss=189.00,
                    partial_closes=[
                        TradePartialCloseBase(
                            ticket="ct-deal-1",
                            volume=1.0,
                            close_time="2026-09-03 13:00:00",
                            close_price=191.00,
                            net_profit=100.0
                        ),
                        TradePartialCloseBase(
                            ticket="ct-deal-2",
                            volume=1.0,
                            close_time="2026-09-03 14:00:00",
                            close_price=192.00,
                            net_profit=200.0
                        ),
                        TradePartialCloseBase(
                            ticket="ct-deal-3",
                            volume=1.0,
                            close_time="2026-09-03 15:00:00",
                            close_price=193.00,
                            net_profit=300.0
                        ),
                    ]
                )
            ]
        )

        res = process_mql_payload(self.api_key, payload)
        self.assertEqual(res["inserted_trades"], 1)

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE account_id = ? AND ticket = 'ct-grouped-1';", (self.account_id,))
            t = dict(cursor.fetchone())
            self.assertEqual(t["status"], "WIN")
            self.assertEqual(t["net_profit"], 600.0)
            self.assertIsNotNone(t["r_multiple"])
            self.assertGreater(t["r_multiple"], 0)

            cursor.execute("SELECT COUNT(*) FROM trade_partial_closes WHERE trade_id = ?;", (t["id"],))
            self.assertEqual(cursor.fetchone()[0], 3)

    def test_mt5_closed_trade_zero_sl_preserves_open_sl_and_calculates_r(self):
        # When MT5 EA syncs an open trade, it sends the real stop loss.
        # When the trade closes, MT5 EA Deal history typically sends stop_loss: 0.0.
        # The journal must NEVER overwrite the existing stop_loss with 0.0,
        # and must use the preserved SL to compute the correct R-multiple!
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trades (
                    account_id, ticket, symbol, direction, volume,
                    open_time, open_price, stop_loss, take_profit,
                    status, notes, created_at, updated_at
                ) VALUES (
                    ?, 'mt5-real-deal-99', 'EURUSD', 'BUY', 1.0,
                    '2026-09-04 10:00:00', 1.0800, 1.0750, 1.0950,
                    'OPEN', 'Important swing trade',
                    '2026-09-04T10:00:00Z', '2026-09-04T10:00:00Z'
                );
            """, (self.account_id,))
            conn.commit()
            trade_id = cursor.lastrowid

        # Broker EA sends closed deal with stop_loss: 0.0 (exact MT5 EA behavior)
        payload = MQLSyncPayload(
            source="mql",
            account_number="sync-acc-100",
            balance=10600.0,
            equity=10600.0,
            closed_trades=[
                MQLTradeItem(
                    ticket="mt5-real-deal-99",
                    symbol="EURUSD",
                    type=0,
                    lots=1.0,
                    open_time="2026-09-04 10:00:00",
                    close_time="2026-09-04 14:00:00",
                    open_price=1.0800,
                    close_price=1.0950,
                    stop_loss=0.0,  # 0.0 sent by MT5 EA
                    take_profit=0.0,
                    profit=300.0
                )
            ]
        )

        res = process_mql_payload(self.api_key, payload)
        self.assertEqual(res["updated_trades"], 1)

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE id = ?;", (trade_id,))
            t = dict(cursor.fetchone())

            # Stop loss must NOT have been erased to 0.0!
            self.assertEqual(t["stop_loss"], 1.0750)
            self.assertEqual(t["take_profit"], 1.0950)
            self.assertEqual(t["status"], "WIN")
            # R-Multiple must be exactly (1.0950 - 1.0800) / (1.0800 - 1.0750) = 0.0150 / 0.0050 = 3.0 R!
            self.assertIsNotNone(t["r_multiple"])
            self.assertAlmostEqual(t["r_multiple"], 3.0, places=2)
            self.assertEqual(t["notes"], "Important swing trade")

    def test_mt5_closed_trade_without_prior_sl_sets_r_none(self):
        # If a trade had no SL at all (stop_loss = 0.0), R-multiple should be None,
        # never computed as if 0.0 were the price SL!
        payload = MQLSyncPayload(
            source="mql",
            account_number="sync-acc-100",
            balance=10700.0,
            equity=10700.0,
            closed_trades=[
                MQLTradeItem(
                    ticket="mt5-no-sl-1",
                    symbol="EURUSD",
                    type=0,
                    lots=1.0,
                    open_time="2026-09-04 10:00:00",
                    close_time="2026-09-04 11:00:00",
                    open_price=1.0800,
                    close_price=1.0820,
                    stop_loss=0.0,
                    take_profit=0.0,
                    profit=200.0
                )
            ]
        )

        res = process_mql_payload(self.api_key, payload)
        self.assertEqual(res["inserted_trades"], 1)

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE account_id = ? AND ticket = 'mt5-no-sl-1';", (self.account_id,))
            t = dict(cursor.fetchone())
            self.assertIsNone(t["r_multiple"])


if __name__ == "__main__":
    unittest.main()

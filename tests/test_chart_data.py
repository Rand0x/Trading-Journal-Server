"""Unit tests for chart data provider, auto-timeframe selection, and aggregation."""

import os
import tempfile
import unittest
from datetime import datetime, timezone

from server.connectors.market_data import (
    _aggregate_candles,
    _select_auto_timeframe,
    get_chart_data_for_trade,
)
from server.database import get_connection, init_db


class TestChartData(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["DB_DIR"] = self.temp_dir.name
        init_db()

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO accounts (name, account_number, broker, platform, currency, current_balance, equity, created_at, updated_at)
                VALUES ('Test Account', '12345', 'Test Broker', 'MT5', 'USD', 10000.0, 10000.0, '2026-09-01 00:00:00', '2026-09-01 00:00:00');
                """
            )
            self.account_id = cursor.lastrowid
            conn.commit()

    def tearDown(self):
        self.temp_dir.cleanup()
        if "DB_DIR" in os.environ:
            del os.environ["DB_DIR"]

    def test_auto_timeframe_selection(self):
        # 1 hour trade -> M15
        self.assertEqual(_select_auto_timeframe(1000000, 1000000 + 3600), "M15")
        # 3 days trade -> M15
        self.assertEqual(_select_auto_timeframe(1000000, 1000000 + 3 * 86400), "M15")
        # 10 days trade -> H1
        self.assertEqual(_select_auto_timeframe(1000000, 1000000 + 10 * 86400), "H1")
        # 30 days trade -> H4
        self.assertEqual(_select_auto_timeframe(1000000, 1000000 + 30 * 86400), "H4")
        # 120 days trade -> D1
        self.assertEqual(_select_auto_timeframe(1000000, 1000000 + 120 * 86400), "D1")

    def test_candle_aggregation_m15_to_h1(self):
        base_ts = 1788510000 - (1788510000 % 3600)
        m15_bars = [
            {"time": base_ts,        "open": 1.1000, "high": 1.1050, "low": 1.0990, "close": 1.1020, "volume": 10.0},
            {"time": base_ts + 900,  "open": 1.1020, "high": 1.1080, "low": 1.1010, "close": 1.1070, "volume": 20.0},
            {"time": base_ts + 1800, "open": 1.1070, "high": 1.1075, "low": 1.1030, "close": 1.1040, "volume": 15.0},
            {"time": base_ts + 2700, "open": 1.1040, "high": 1.1060, "low": 1.1025, "close": 1.1050, "volume": 25.0},
        ]
        h1_bars = _aggregate_candles(m15_bars, "H1")
        self.assertEqual(len(h1_bars), 1)
        h1 = h1_bars[0]
        self.assertEqual(h1["time"], base_ts)
        self.assertEqual(h1["open"], 1.1000)
        self.assertEqual(h1["high"], 1.1080)
        self.assertEqual(h1["low"], 1.0990)
        self.assertEqual(h1["close"], 1.1050)
        self.assertEqual(h1["volume"], 70.0)

    def test_never_generate_fake_candles(self):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trades (
                    account_id, ticket, symbol, direction, volume,
                    open_time, close_time, open_price, close_price,
                    net_profit, status, created_at, updated_at
                ) VALUES (?, 't_no_candles', 'EURUSD', 'BUY', 1.0,
                          '2026-09-01 10:00:00', '2026-09-01 12:00:00', 1.0850, 1.0890,
                          400.0, 'WIN', '2026-09-01 12:00:00', '2026-09-01 12:00:00');
                """,
                (self.account_id,),
            )
            trade_id = cursor.lastrowid
            conn.commit()

        data = get_chart_data_for_trade(trade_id, timeframe="AUTO")
        self.assertEqual(len(data["candles"]), 0)
        self.assertFalse(data["data_available"])
        self.assertFalse(data["complete_coverage"])
        self.assertIn("No real", data["message"])
        self.assertEqual(len(data["markers"]), 0)

    def test_complete_and_partial_coverage(self):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trades (
                    account_id, ticket, symbol, direction, volume,
                    open_time, close_time, open_price, close_price,
                    net_profit, status, created_at, updated_at
                ) VALUES (?, 't_partial', 'GBPUSD', 'BUY', 1.0,
                          '2026-09-01 08:00:00', '2026-09-01 14:00:00', 1.3000, 1.3050,
                          500.0, 'WIN', '2026-09-01 14:00:00', '2026-09-01 14:00:00');
                """,
                (self.account_id,),
            )
            trade_id = cursor.lastrowid

            exit_ts = int(datetime.fromisoformat("2026-09-01 14:00:00").replace(tzinfo=timezone.utc).timestamp())
            for step in range(-2, 3):
                ts = exit_ts + (step * 900)
                cursor.execute(
                    """
                    INSERT INTO market_candles (symbol, timeframe, timestamp, open, high, low, close, volume)
                    VALUES ('GBPUSD', 'M15', ?, 1.3040, 1.3060, 1.3030, 1.3050, 100.0);
                    """,
                    (ts,),
                )
            conn.commit()

        data_partial = get_chart_data_for_trade(trade_id, timeframe="M15")
        self.assertTrue(data_partial["data_available"])
        self.assertFalse(data_partial["complete_coverage"])
        self.assertIn("Only part of the real broker data is available", data_partial["message"])

        entry_ts = int(datetime.fromisoformat("2026-09-01 08:00:00").replace(tzinfo=timezone.utc).timestamp())
        with get_connection() as conn:
            cursor = conn.cursor()
            for step in range(-8, 9):
                ts = entry_ts + (step * 900)
                cursor.execute(
                    """
                    INSERT INTO market_candles (symbol, timeframe, timestamp, open, high, low, close, volume)
                    VALUES ('GBPUSD', 'M15', ?, 1.2990, 1.3010, 1.2980, 1.3000, 100.0);
                    """,
                    (ts,),
                )
            conn.commit()

        data_complete = get_chart_data_for_trade(trade_id, timeframe="M15")
        self.assertTrue(data_complete["data_available"])
        self.assertTrue(data_complete["complete_coverage"])
        self.assertEqual(data_complete["message"], "")
        self.assertEqual(len(data_complete["markers"]), 2)


if __name__ == "__main__":
    unittest.main()

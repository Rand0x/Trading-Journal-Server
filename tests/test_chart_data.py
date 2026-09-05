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

    def test_pending_order_chart_coverage(self):
        # 1. Create a pending limit order
        now_dt = datetime.now(timezone.utc)
        now_ts = int(now_dt.timestamp())
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trades (
                    account_id, ticket, symbol, direction, volume,
                    open_time, open_price, stop_loss, take_profit,
                    status, order_type, created_at, updated_at
                ) VALUES (?, 't_pending_limit', 'USDJPY', 'BUY', 0.5,
                          ?, 150.250, 149.800, 151.000,
                          'PENDING', 'Buy Limit', ?, ?);
                """,
                (self.account_id, now_str, now_str, now_str),
            )
            pending_trade_id = cursor.lastrowid
            conn.commit()

        # Without candles, reports real candles missing
        data_no_candles = get_chart_data_for_trade(pending_trade_id, timeframe="AUTO")
        self.assertFalse(data_no_candles["data_available"])
        self.assertIn("No real", data_no_candles["message"])

        # Insert real broker candles for USDJPY (e.g. 50 bars leading up to now)
        with get_connection() as conn:
            cursor = conn.cursor()
            for step in range(50, 0, -1):
                ts = now_ts - (step * 900)
                cursor.execute(
                    """
                    INSERT INTO market_candles (symbol, timeframe, timestamp, open, high, low, close, volume)
                    VALUES ('USDJPY', 'M15', ?, 150.100, 150.400, 150.050, 150.300, 50.0);
                    """,
                    (ts,),
                )
            conn.commit()

        data_with_candles = get_chart_data_for_trade(pending_trade_id, timeframe="AUTO")
        self.assertTrue(data_with_candles["data_available"])
        self.assertTrue(data_with_candles["complete_coverage"])
        self.assertEqual(data_with_candles["message"], "")
        self.assertEqual(data_with_candles["timeframe"], "M15")
        self.assertGreaterEqual(len(data_with_candles["candles"]), 40)
        # Pending orders must have no execution markers (buy/sell arrows), only limit price lines
        self.assertEqual(len(data_with_candles["markers"]), 0)
        self.assertEqual(len(data_with_candles["price_lines"]), 3)
        limit_line = next(l for l in data_with_candles["price_lines"] if "LIMIT" in l["title"])
        self.assertEqual(limit_line["price"], 150.250)
        self.assertEqual(limit_line["color"], "#f59e0b")

    def test_load_2000_candles_capacity(self):
        now_ts = int(datetime.now(timezone.utc).timestamp())
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trades (
                    account_id, ticket, symbol, direction, volume,
                    open_time, open_price, status, created_at, updated_at
                ) VALUES (?, 't_2000_bars', 'BTCUSD', 'BUY', 0.5,
                          '2026-09-01 00:00:00', 60000.0, 'OPEN',
                          '2026-09-01 00:00:00', '2026-09-01 00:00:00');
                """,
                (self.account_id,),
            )
            trade_id = cursor.lastrowid

            # Insert 2000 bars
            rows = [
                ('BTCUSD', 'M15', now_ts - (i * 900), 60000.0 + i, 60010.0 + i, 59990.0 + i, 60005.0 + i, 10.0)
                for i in range(2000, 0, -1)
            ]
            cursor.executemany(
                """
                INSERT INTO market_candles (symbol, timeframe, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                rows,
            )
            conn.commit()

        data = get_chart_data_for_trade(trade_id, timeframe="M15", num_bars=2000)
        self.assertTrue(data["data_available"])
        self.assertEqual(len(data["candles"]), 2000)

    def test_cancelled_order_chart_markers_and_timeframes(self):
        now_dt = datetime.now(timezone.utc)
        now_ts = int(now_dt.timestamp())
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trades (
                    account_id, ticket, symbol, direction, volume,
                    open_time, open_price, stop_loss, take_profit,
                    status, order_type, created_at, updated_at
                ) VALUES (?, 't_cancelled_1', 'BTCUSD', 'SELL', 0.01,
                          ?, 82885.0, 85620.51, 80075.19,
                          'CANCELLED', 'Limit', ?, ?);
                """,
                (self.account_id, now_str, now_str, now_str),
            )
            trade_id = cursor.lastrowid

            # Insert M15 and M5 candles around now
            m15_rows = [
                ('BTCUSD', 'M15', now_ts - (i * 900), 82000.0, 82100.0, 81900.0, 82050.0, 50.0)
                for i in range(10, 0, -1)
            ]
            m5_rows = [
                ('BTCUSD', 'M5', now_ts - (i * 300), 82000.0, 82050.0, 81950.0, 82020.0, 20.0)
                for i in range(20, 0, -1)
            ]
            cursor.executemany(
                """
                INSERT INTO market_candles (symbol, timeframe, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                m15_rows + m5_rows,
            )
            conn.commit()

        # 1. Test M15 timeframe on cancelled trade
        data_m15 = get_chart_data_for_trade(trade_id, timeframe="M15")
        self.assertTrue(data_m15["data_available"])
        self.assertTrue(data_m15["complete_coverage"])
        # No BUY or SELL execution markers for cancelled order!
        self.assertEqual(data_m15["markers"], [])
        # Check price line has muted CANCELLED line and no active SL/TP
        self.assertEqual(len(data_m15["price_lines"]), 1)
        self.assertEqual(data_m15["price_lines"][0]["title"], "CANCELLED: 82885.0")
        self.assertEqual(data_m15["price_lines"][0]["color"], "#9ca3af")

        # 2. Test switching to M5 timeframe
        data_m5 = get_chart_data_for_trade(trade_id, timeframe="M5")
        self.assertTrue(data_m5["data_available"])
        self.assertTrue(data_m5["complete_coverage"])
        self.assertEqual(data_m5["timeframe"], "M5")
        self.assertEqual(data_m5["markers"], [])

        # 3. Test AUTO mode
        data_auto = get_chart_data_for_trade(trade_id, timeframe="AUTO")
        self.assertTrue(data_auto["data_available"])
        self.assertEqual(data_auto["markers"], [])


if __name__ == "__main__":
    unittest.main()


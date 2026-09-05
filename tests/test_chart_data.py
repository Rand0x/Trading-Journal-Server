"""Unit tests for chart data provider, auto-timeframe selection, and aggregation."""

import os
import tempfile
import unittest
from datetime import datetime, timezone

from server.connectors.market_data import (
    _aggregate_candles,
    _select_auto_timeframe,
    _parse_dt,
    get_chart_data_for_trade,
)
from server.routers.trades import _get_trade_with_partials
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
        # Check price lines have CANCELLED, SL, and TP
        self.assertEqual(len(data_m15["price_lines"]), 3)
        self.assertEqual(data_m15["price_lines"][0]["title"], "CANCELLED: 82885.0")
        self.assertEqual(data_m15["price_lines"][0]["color"], "#9ca3af")
        self.assertEqual(data_m15["price_lines"][1]["title"], "SL: 85620.51")
        self.assertEqual(data_m15["price_lines"][1]["color"], "#ef4444")
        self.assertEqual(data_m15["price_lines"][2]["title"], "TP: 80075.19")
        self.assertEqual(data_m15["price_lines"][2]["color"], "#10b981")

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

    def test_multiple_take_profits_displayed_on_chart(self):
        now_dt = datetime.now(timezone.utc)
        now_ts = int(now_dt.timestamp())
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        with get_connection() as conn:
            cursor = conn.cursor()
            # Order 1: primary trade with TP1 (80075.19)
            cursor.execute(
                """
                INSERT INTO trades (
                    account_id, ticket, symbol, direction, volume,
                    open_time, open_price, stop_loss, take_profit,
                    status, order_type, notes, created_at, updated_at
                ) VALUES (?, 't_multi_tp_1', 'BTCUSD', 'SELL', 0.01,
                          ?, 82885.0, 85620.51, 80075.19,
                          'CANCELLED', 'Limit', 'Planned TP2: 78500.00', ?, ?);
                """,
                (self.account_id, now_str, now_str, now_str),
            )
            trade_id_1 = cursor.lastrowid

            # Order 2: related order for same setup with TP3 (76000.00)
            cursor.execute(
                """
                INSERT INTO trades (
                    account_id, ticket, symbol, direction, volume,
                    open_time, open_price, stop_loss, take_profit,
                    status, order_type, created_at, updated_at
                ) VALUES (?, 't_multi_tp_2', 'BTCUSD', 'SELL', 0.01,
                          ?, 82885.0, 85620.51, 76000.00,
                          'CANCELLED', 'Limit', ?, ?);
                """,
                (self.account_id, now_str, now_str, now_str),
            )

            # Insert M15 candles
            m15_rows = [
                ('BTCUSD', 'M15', now_ts - (i * 900), 82000.0, 82100.0, 81900.0, 82050.0, 50.0)
                for i in range(5, 0, -1)
            ]
            cursor.executemany(
                """
                INSERT INTO market_candles (symbol, timeframe, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                m15_rows,
            )
            conn.commit()

        data = get_chart_data_for_trade(trade_id_1, timeframe="M15")
        # Should have CANCELLED, SL, TP1, TP2, TP3 lines
        titles = [pl["title"] for pl in data["price_lines"]]
        self.assertIn("CANCELLED: 82885.0", titles)
        self.assertIn("SL: 85620.51", titles)
        self.assertIn("TP1: 80075.19", titles)
        self.assertIn("TP2: 78500.0", titles)
        self.assertIn("TP3: 76000.0", titles)

    def test_parse_dt_with_metatrader_dot_dates(self):
        # MT4/MT5 format with dots: YYYY.MM.DD HH:MM:SS
        dt1 = _parse_dt("2026.09.05 13:27:57")
        self.assertEqual(dt1.year, 2026)
        self.assertEqual(dt1.month, 9)
        self.assertEqual(dt1.day, 5)
        self.assertEqual(dt1.hour, 13)
        self.assertEqual(dt1.minute, 27)
        self.assertEqual(dt1.second, 57)

        # Standard ISO format with dashes
        dt2 = _parse_dt("2026-09-05 13:27:57")
        self.assertEqual(dt2.year, 2026)
        self.assertEqual(dt2.month, 9)
        self.assertEqual(dt2.day, 5)

        # ISO with T
        dt3 = _parse_dt("2026-09-05T13:27:57Z")
        self.assertEqual(dt3.year, 2026)
        self.assertEqual(dt3.month, 9)

        # Dot format date only
        dt4 = _parse_dt("2026.09.05")
        self.assertEqual(dt4.year, 2026)
        self.assertEqual(dt4.month, 9)

    def test_chart_data_with_dot_date_trade(self):
        # Verify get_chart_data_for_trade handles MT5 dot dates without crashing
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trades (
                    account_id, ticket, symbol, direction, volume,
                    open_time, close_time, open_price, close_price,
                    net_profit, status, created_at, updated_at
                ) VALUES (?, 'mt5_dot_date_ticket', 'EURUSD', 'BUY', 0.5,
                          '2026.09.05 13:27:57', '2026.09.05 14:15:00', 1.0850, 1.0890,
                          20.0, 'WIN', '2026-09-05 14:15:00', '2026-09-05 14:15:00');
                """,
                (self.account_id,),
            )
            trade_id = cursor.lastrowid
            conn.commit()

        # Must not raise ValueError
        data = get_chart_data_for_trade(trade_id, timeframe="M15")
        self.assertIsNotNone(data)
        self.assertEqual(data["symbol"], "EURUSD")

    def test_open_trades_grouping_with_multiple_tps(self):
        # Verify sibling open trades with same entry and direction are grouped
        with get_connection() as conn:
            cursor = conn.cursor()
            # Order 1 (TP1)
            cursor.execute(
                """
                INSERT INTO trades (
                    account_id, ticket, symbol, direction, volume,
                    open_time, open_price, stop_loss, take_profit,
                    status, net_profit, created_at, updated_at
                ) VALUES (?, 'mt5_open_1', 'EURUSD', 'BUY', 0.5,
                          '2026-09-05 13:27:57', 1.08500, 1.08200, 1.08800,
                          'OPEN', 10.0, '2026-09-05 13:27:57', '2026-09-05 13:27:57');
                """,
                (self.account_id,),
            )
            trade_id_1 = cursor.lastrowid

            # Order 2 (TP2)
            cursor.execute(
                """
                INSERT INTO trades (
                    account_id, ticket, symbol, direction, volume,
                    open_time, open_price, stop_loss, take_profit,
                    status, net_profit, created_at, updated_at
                ) VALUES (?, 'mt5_open_2', 'EURUSD', 'BUY', 0.5,
                          '2026-09-05 13:27:57', 1.08500, 1.08200, 1.09200,
                          'OPEN', 10.0, '2026-09-05 13:27:57', '2026-09-05 13:27:57');
                """,
                (self.account_id,),
            )

            # Order 3 (TP3)
            cursor.execute(
                """
                INSERT INTO trades (
                    account_id, ticket, symbol, direction, volume,
                    open_time, open_price, stop_loss, take_profit,
                    status, net_profit, created_at, updated_at
                ) VALUES (?, 'mt5_open_3', 'EURUSD', 'BUY', 0.5,
                          '2026-09-05 13:27:57', 1.08500, 1.08200, 1.09600,
                          'OPEN', 10.0, '2026-09-05 13:27:57', '2026-09-05 13:27:57');
                """,
                (self.account_id,),
            )
            conn.commit()

            trade_info = _get_trade_with_partials(cursor, trade_id_1)

        self.assertTrue(trade_info["is_grouped"])
        self.assertEqual(trade_info["grouped_count"], 3)
        self.assertEqual(trade_info["grouped_total_volume"], 1.5)
        self.assertEqual(trade_info["grouped_net_profit"], 30.0)
        self.assertEqual(trade_info["multiple_tps"], [1.088, 1.092, 1.096])
        self.assertEqual(len(trade_info["sub_trades"]), 3)

    def test_tp_targets_does_not_extract_timestamps_or_bogus_numbers(self):
        # Verify JSON tp_targets with dates, volumes, tickets does NOT extract timestamps
        complex_tp_targets = (
            '[{"price": 80310.66, "lots": 0.18, "status": "OPEN", "close_time": "2026-09-05 13:27:57"}]'
        )
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trades (
                    account_id, ticket, symbol, direction, volume,
                    open_time, open_price, stop_loss, take_profit, tp_targets,
                    status, net_profit, created_at, updated_at
                ) VALUES (?, 'btc_tp_test', 'BTCUSD', 'SELL', 0.18,
                          '2026-09-05 13:27:57', 83363.85, 84500.00, 80310.66, ?,
                          'PENDING', 0.0, '2026-09-05 13:27:57', '2026-09-05 13:27:57');
                """,
                (self.account_id, complex_tp_targets),
            )
            trade_id = cursor.lastrowid
            conn.commit()

            trade_info = _get_trade_with_partials(cursor, trade_id)

        # Must only contain the real TP price 80310.66, NOT 2026, 27, 13, 0.18 etc.
        self.assertEqual(trade_info["multiple_tps"], [80310.66])

        chart_data = get_chart_data_for_trade(trade_id, timeframe="M15")
        tp_lines = [pl for pl in chart_data.get("price_lines", []) if pl.get("title", "").startswith("TP")]
        self.assertEqual(len(tp_lines), 1)
        self.assertEqual(tp_lines[0]["price"], 80310.66)
        # Ensure no bogus TP lines were added
        bogus_prices = [2026.0, 27.0, 13.0, 9.0, 5.0, 1.0, 0.18]
        for pl in chart_data.get("price_lines", []):
            self.assertNotIn(pl["price"], bogus_prices)


if __name__ == "__main__":
    unittest.main()



"""Currency-neutral analytics / weekly review for several accounts, and the daily Sharpe ratio."""
import math
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from server.analytics import (
    _annualized_daily_sharpe,
    attach_trade_returns,
    calculate_trade_metrics,
    get_cost_of_mistakes,
    get_performance_by_symbol,
    get_weekly_review,
)
from server.database import get_connection, init_db
from server.main import app

ACCOUNTS = [
    {"id": 1, "initial_balance": 10000.0},    # GBP
    {"id": 2, "initial_balance": 100000.0},   # USD
]


def _trade(account_id, symbol, close_time, pnl, **extra):
    return {
        "account_id": account_id, "symbol": symbol, "net_profit": pnl,
        "status": "WIN" if pnl > 0 else "LOSS", "open_time": close_time, "close_time": close_time, **extra,
    }


class TestDailySharpe(unittest.TestCase):
    def test_sharpe_uses_daily_results_and_counts_quiet_weekdays_as_zero(self):
        trades = [
            _trade(1, "EURUSD", "2026-09-07 10:00", 60.0),    # Mon (two trades, one day)
            _trade(1, "EURUSD", "2026-09-07 15:00", 40.0),
            _trade(1, "EURUSD", "2026-09-08 10:00", -50.0),   # Tue
            _trade(1, "EURUSD", "2026-09-10 10:00", 100.0),   # Thu, Wed had no trade
        ]
        # Daily series [100, -50, 0, 100]: mean 37.5, sample std 75.
        expected = round(37.5 / 75 * math.sqrt(252), 2)
        self.assertEqual(calculate_trade_metrics(trades, 10000.0)["sharpe_ratio"], expected)

    def test_weekends_without_trades_are_skipped(self):
        self.assertEqual(_annualized_daily_sharpe({"2026-09-11": 1.0, "2026-09-14": 1.0}), 0.0)  # Fri, Mon
        self.assertEqual(_annualized_daily_sharpe({"2026-09-11": 1.0}), 0.0)


class TestPercentBreakdowns(unittest.TestCase):
    def test_symbol_returns_are_shares_of_the_average_return(self):
        trades = [
            _trade(1, "EURUSD", "2026-09-01 10:00", 1000.0),    # GBP +10 %
            _trade(2, "EURUSD", "2026-09-02 10:00", 10000.0),   # USD +10 %
            _trade(2, "GBPUSD", "2026-09-03 10:00", 10000.0),   # USD +10 %
        ]
        self.assertEqual(attach_trade_returns(trades, ACCOUNTS), 2)
        rows = {r["symbol"]: r for r in get_performance_by_symbol(trades)}
        # Accounts return +10 % and +20 % -> average +15 % = EURUSD 10 + GBPUSD 5.
        self.assertEqual(rows["EURUSD"]["return_pct"], 10.0)
        self.assertEqual(rows["GBPUSD"]["return_pct"], 5.0)
        self.assertEqual(rows["EURUSD"]["avg_trade_pct"], 10.0)
        self.assertEqual(rows["EURUSD"]["profit_factor_pct"], 999.0)

    def test_mistake_costs_in_percent_of_each_account(self):
        trades = [
            _trade(1, "EURUSD", "2026-09-01 10:00", -500.0, mistake_id=7),    # GBP -5 %
            _trade(2, "EURUSD", "2026-09-02 10:00", -1000.0, mistake_id=7),   # USD -1 %
        ]
        attach_trade_returns(trades, ACCOUNTS)
        row = get_cost_of_mistakes(trades, {7: "FOMO"})[0]
        self.assertEqual((row["total_loss_pct"], row["worst_loss_pct"], row["avg_loss_pct"]), (3.0, 5.0, 3.0))

    def test_weekly_review_ranks_by_percent_of_own_account(self):
        monday = date.today() - timedelta(days=date.today().weekday())
        day = f"{monday.isoformat()} 10:00"
        trades = [
            _trade(1, "EURUSD", day, 500.0),     # GBP +5 %   (smaller amount, better trade)
            _trade(2, "XAUUSD", day, 2000.0),    # USD +2 %
        ]
        attach_trade_returns(trades, ACCOUNTS)
        review = get_weekly_review(trades, rank_by_pct=True)
        self.assertEqual(review["best_trade"]["symbol"], "EURUSD")
        self.assertEqual((review["return_pct"], review["return_accounts"]), (3.5, 2))
        self.assertEqual(get_weekly_review(trades)["best_trade"]["symbol"], "XAUUSD")


class TestAnalyticsOverviewFlag(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        os.environ["DB_DIR"] = cls.temp_dir.name
        init_db()
        cls.client = TestClient(app)
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            ids = []
            for name, currency, balance in (("Pound", "GBP", 10000.0), ("Dollar", "USD", 100000.0)):
                cursor = conn.execute(
                    "INSERT INTO accounts (name, platform, currency, initial_balance, api_key, created_at, updated_at)"
                    " VALUES (?, 'MT5', ?, ?, ?, ?, ?);",
                    (name, currency, balance, f"key_ov_{name}", now, now),
                )
                ids.append(cursor.lastrowid)
            for account_id, pnl in zip(ids, (1000.0, 20000.0)):
                conn.execute(
                    "INSERT INTO trades (account_id, ticket, symbol, direction, volume, open_time, close_time,"
                    " open_price, close_price, net_profit, status, created_at, updated_at)"
                    " VALUES (?, ?, 'EURUSD', 'BUY', 1, '2026-09-01 10:00', '2026-09-01 12:00', 1.1, 1.2, ?, 'WIN', ?, ?);",
                    (account_id, f"ov-{account_id}", pnl, now, now),
                )
            conn.commit()
        cls.account_ids = ids

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()
        os.environ.pop("DB_DIR", None)

    def test_all_accounts_analytics_report_equal_weighted_percent(self):
        data = self.client.get("/api/analytics/overview").json()
        self.assertTrue(data["is_overview"])
        self.assertEqual(data["by_symbol"][0]["return_pct"], 15.0)

    def test_single_account_is_not_an_overview(self):
        data = self.client.get("/api/analytics/overview", params={"account_id": self.account_ids[0]}).json()
        self.assertFalse(data["is_overview"])
        review = self.client.get("/api/analytics/weekly-review", params={"account_id": self.account_ids[0]}).json()
        self.assertFalse(review["is_overview"])
        self.assertTrue(self.client.get("/api/analytics/weekly-review").json()["is_overview"])


if __name__ == "__main__":
    unittest.main()

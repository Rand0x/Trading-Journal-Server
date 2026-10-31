"""Currency-neutral per-account return curves for the multi-account overview."""
import os
import tempfile
import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from server.analytics import get_account_return_curves
from server.database import get_connection, init_db
from server.main import app


def _trade(account_id, close_time, pnl, status=None):
    return {
        "account_id": account_id, "symbol": "EURUSD", "net_profit": pnl,
        "status": status or ("WIN" if pnl > 0 else "LOSS"),
        "open_time": close_time, "close_time": close_time,
    }


class TestAccountReturnCurves(unittest.TestCase):
    ACCOUNTS = [
        {"id": 1, "name": "GBP Account", "currency": "GBP", "initial_balance": 10000.0},
        {"id": 2, "name": "USD Account", "currency": "USD", "initial_balance": 100000.0},
    ]

    def test_each_account_is_measured_against_its_own_starting_balance(self):
        trades = [
            _trade(1, "2026-09-01 10:00", 400.0),
            _trade(2, "2026-09-02 10:00", 20000.0),
            _trade(1, "2026-09-03 10:00", 600.0),
        ]
        result = get_account_return_curves(trades, self.ACCOUNTS)
        by_name = {c["name"]: c for c in result["accounts"]}

        self.assertEqual(by_name["GBP Account"]["return_pct"], 10.0)
        self.assertEqual(by_name["GBP Account"]["currency"], "GBP")
        self.assertEqual(by_name["GBP Account"]["trades"], 2)
        self.assertEqual([p["pct"] for p in by_name["GBP Account"]["points"]], [0.0, 4.0, 10.0])
        self.assertEqual(by_name["USD Account"]["return_pct"], 20.0)
        self.assertEqual(by_name["USD Account"]["net_profit"], 20000.0)

    def test_average_weights_every_account_equally_over_time(self):
        trades = [
            _trade(1, "2026-09-01 10:00", 400.0),     # GBP +4 %
            _trade(2, "2026-09-02 10:00", 20000.0),   # USD +20 %
            _trade(1, "2026-09-03 10:00", 600.0),     # GBP +10 %
        ]
        result = get_account_return_curves(trades, self.ACCOUNTS)
        self.assertEqual(result["average_return_pct"], 15.0)
        self.assertEqual(
            [(p["time"], p["pct"]) for p in result["average"]],
            [("2026-09-01 10:00", 2.0), ("2026-09-02 10:00", 12.0), ("2026-09-03 10:00", 15.0)],
        )

    def test_accounts_without_closed_trades_or_balance_are_left_out(self):
        accounts = self.ACCOUNTS + [{"id": 3, "name": "Empty", "currency": "EUR", "initial_balance": 0.0}]
        trades = [
            _trade(1, "2026-09-01 10:00", 1000.0),
            {**_trade(2, "2026-09-02 10:00", 0.0), "status": "OPEN", "close_time": None},
            _trade(3, "2026-09-02 10:00", 50.0),
        ]
        result = get_account_return_curves(trades, accounts)
        self.assertEqual([c["name"] for c in result["accounts"]], ["GBP Account"])
        self.assertEqual(result["average_return_pct"], 10.0)


class TestDashboardAccountCurves(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        os.environ["DB_DIR"] = cls.temp_dir.name
        init_db()
        cls.client = TestClient(app)
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            cursor = conn.cursor()
            ids = []
            for name, currency, balance in (("Pound", "GBP", 10000.0), ("Dollar", "USD", 100000.0)):
                cursor.execute(
                    "INSERT INTO accounts (name, platform, currency, initial_balance, api_key, created_at, updated_at)"
                    " VALUES (?, 'MT5', ?, ?, ?, ?, ?);",
                    (name, currency, balance, f"key_curve_{name}", now, now),
                )
                ids.append(cursor.lastrowid)
            for account_id, pnl in zip(ids, (1000.0, 20000.0)):
                cursor.execute(
                    "INSERT INTO trades (account_id, ticket, symbol, direction, volume, open_time, close_time,"
                    " open_price, close_price, net_profit, status, created_at, updated_at)"
                    " VALUES (?, ?, 'EURUSD', 'BUY', 1, '2026-09-01 10:00', '2026-09-01 12:00', 1.1, 1.2, ?, 'WIN', ?, ?);",
                    (account_id, f"curve-{account_id}", pnl, now, now),
                )
            conn.commit()
        cls.account_ids = ids

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()
        os.environ.pop("DB_DIR", None)

    def test_all_accounts_overview_returns_one_percent_curve_per_account(self):
        data = self.client.get("/api/dashboard").json()
        curves = data["account_curves"]
        self.assertEqual(
            [(c["name"], c["currency"], c["return_pct"]) for c in curves["accounts"]],
            [("Pound", "GBP", 10.0), ("Dollar", "USD", 20.0)],
        )
        self.assertEqual(curves["average_return_pct"], 15.0)

    def test_single_account_view_keeps_the_currency_chart(self):
        data = self.client.get("/api/dashboard", params={"account_id": self.account_ids[0]}).json()
        self.assertIsNone(data["account_curves"])
        self.assertEqual(data["currency"], "GBP")


if __name__ == "__main__":
    unittest.main()

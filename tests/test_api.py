"""Integration tests for FastAPI endpoints."""
import unittest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from server.main import app
from server.database import get_connection, init_db

class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        
        # Ensure a test account exists
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, api_key FROM accounts LIMIT 1;")
            row = cursor.fetchone()
            if row:
                cls.account_id = row["id"]
                cls.api_key = row["api_key"]
            else:
                now_str = datetime.now(timezone.utc).isoformat()
                cursor.execute("""
                    INSERT INTO accounts (name, platform, account_number, password, server_name, api_key, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, ("Test Account", "MT5", "10052026", "InvestorPass123!", "MetaQuotes-Demo", "key_test_api_123", now_str, now_str))
                conn.commit()
                cls.account_id = cursor.lastrowid
                cls.api_key = "key_test_api_123"

    def test_health_check(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "healthy")
        self.assertFalse(data["ai_enabled"])

    def test_get_accounts(self):
        res = self.client.get("/api/accounts")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_dashboard_endpoint(self):
        res = self.client.get("/api/dashboard")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("metrics", data)
        self.assertIn("calendar", data)
        self.assertIn("equity_curve", data)

    def test_create_and_get_trade(self):
        # Create a new trade using valid account_id
        payload = {
            "account_id": self.account_id,
            "symbol": "GBPUSD",
            "direction": "BUY",
            "volume": 0.5,
            "open_time": "2026-09-04 10:00:00",
            "close_time": "2026-09-04 11:30:00",
            "open_price": 1.29500,
            "close_price": 1.29900,
            "stop_loss": 1.29200,
            "take_profit": 1.30000,
            "net_profit": 200.0,
            "commission": 3.50,
            "swap": 0.0,
            "notes": "Clean London session trend continuation"
        }
        res_post = self.client.post("/api/trades", json=payload)
        self.assertEqual(res_post.status_code, 200)
        trade = res_post.json()
        self.assertEqual(trade["symbol"], "GBPUSD")
        self.assertEqual(trade["net_profit"], 200.0)

        # Get chart data for this trade
        res_chart = self.client.get(f"/api/sync/chart-data/{trade['id']}?timeframe=M15")
        self.assertEqual(res_chart.status_code, 200)
        chart_data = res_chart.json()
        self.assertIn("candles", chart_data)
        self.assertIn("markers", chart_data)
        self.assertIn("price_lines", chart_data)
        self.assertGreater(len(chart_data["candles"]), 50)

    def test_mql_sync_endpoint(self):
        sync_payload = {
            "account_number": "999888",
            "broker": "ICMarkets",
            "platform": "MT5",
            "currency": "USD",
            "balance": 54200.0,
            "equity": 54350.0,
            "margin": 100.0,
            "free_margin": 54250.0,
            "leverage": 100,
            "closed_trades": [
                {
                    "ticket": "999001",
                    "symbol": "EURUSD",
                    "type": 0,
                    "lots": 1.0,
                    "open_time": "2026-09-04 08:00:00",
                    "close_time": "2026-09-04 09:00:00",
                    "open_price": 1.08500,
                    "close_price": 1.08850,
                    "stop_loss": 1.08300,
                    "take_profit": 1.09000,
                    "commission": -7.0,
                    "swap": 0.0,
                    "profit": 350.0,
                    "comment": "MQL5 sync test"
                }
            ],
            "open_trades": []
        }

        res = self.client.post("/api/sync/mql", json=sync_payload, headers={"X-API-Key": self.api_key})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertGreaterEqual(data["inserted_trades"] + data["updated_trades"], 1)

    def test_mt_direct_login(self):
        # Test direct server login with Account ID + Password + Server Name (No client terminal)
        direct_payload = {
            "account_id": self.account_id,
            "account_number": "10052026",
            "password": "InvestorPassword123!",
            "server_name": "MetaQuotes-Demo",
            "platform": "MT5"
        }
        res = self.client.post("/api/sync/mt-direct", json=direct_payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["account_number"], "10052026")
        self.assertEqual(data["server"], "MetaQuotes-Demo")
        self.assertGreater(data["balance"], 0)

    def test_auto_sync_all_endpoint(self):
        res = self.client.post("/api/sync/auto-sync-all")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("synced_count", data)

if __name__ == "__main__":
    unittest.main()

"""Integration tests for FastAPI endpoints."""
import unittest
import os
import tempfile
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from server.main import app
from server.database import get_connection, init_db

class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        os.environ["DB_DIR"] = cls.temp_dir.name
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
                    INSERT INTO accounts (name, platform, account_number, server_name, api_key, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                """, ("Test Account", "MT5", "10052026", "MetaQuotes-Demo", "key_test_api_123", now_str, now_str))
                conn.commit()
                cls.account_id = cursor.lastrowid
                cls.api_key = "key_test_api_123"

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()
        os.environ.pop("DB_DIR", None)

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
        self.assertNotIn("ctrader_client_secret", data[0])

    def test_dashboard_endpoint(self):
        res = self.client.get("/api/dashboard")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("metrics", data)
        self.assertIn("calendar", data)
        self.assertIn("equity_curve", data)

    def test_create_account_generates_journal_api_key(self):
        res = self.client.post("/api/accounts", json={
            "name": "cTrader cBot Test Account",
            "platform": "cTrader",
            "account_number": "ct-12345",
            "server_name": "Test Broker",
            "currency": "USD",
            "initial_balance": 10000
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["api_key"].startswith("key_"))
        self.assertGreater(len(data["api_key"]), 32)

    def test_playbook_can_be_updated(self):
        created = self.client.post("/api/playbooks", json={
            "name": "Editable Test Setup",
            "description": "Before editing",
            "rules": "Initial rule"
        })
        self.assertEqual(created.status_code, 200)
        playbook_id = created.json()["id"]

        updated = self.client.put(f"/api/playbooks/{playbook_id}", json={
            "name": "Edited Test Setup",
            "description": "After editing",
            "rules": "Updated rule"
        })
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "Edited Test Setup")
        self.assertNotIn("target_rr", updated.json())

        fetched = self.client.get("/api/playbooks")
        edited = next(item for item in fetched.json() if item["id"] == playbook_id)
        self.assertEqual(edited["description"], "After editing")
        self.assertNotIn("target_rr", edited)

    def test_trade_screenshots_support_tradingview_links(self):
        created = self.client.post("/api/trades", json={
            "account_id": self.account_id,
            "ticket": "screenshot_test_trade",
            "symbol": "EURUSD",
            "direction": "BUY",
            "volume": 1.0,
            "open_time": "2026-09-04 10:00:00",
            "open_price": 1.085,
            "net_profit": 0.0
        })
        self.assertEqual(created.status_code, 200)
        trade_id = created.json()["id"]

        added = self.client.post(f"/api/trades/{trade_id}/screenshots", json={
            "source_url": "https://www.tradingview.com/x/oo0a7Ei5/",
            "caption": "Entry"
        })
        self.assertEqual(added.status_code, 200)
        screenshot = added.json()
        self.assertEqual(
            screenshot["image_url"],
            "https://s3.tradingview.com/snapshots/o/oo0a7Ei5.png"
        )
        self.assertEqual(screenshot["caption"], "Entry")

        second_added = self.client.post(f"/api/trades/{trade_id}/screenshots", json={
            "source_url": "https://www.tradingview.com/x/Abc123/",
            "caption": "TP1"
        })
        self.assertEqual(second_added.status_code, 200)
        self.assertEqual(
            second_added.json()["image_url"],
            "https://s3.tradingview.com/snapshots/a/Abc123.png"
        )

        fetched = self.client.get(f"/api/trades/{trade_id}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(len(fetched.json()["screenshots"]), 2)

        listed = self.client.get("/api/trades", params={"search": "screenshot_test_trade"})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["trades"][0]["screenshot_count"], 2)

        duplicate = self.client.post(f"/api/trades/{trade_id}/screenshots", json={
            "source_url": "https://www.tradingview.com/x/oo0a7Ei5/"
        })
        self.assertEqual(duplicate.status_code, 409)

        deleted = self.client.delete(f"/api/trades/{trade_id}/screenshots/{screenshot['id']}")
        self.assertEqual(deleted.status_code, 200)
        deleted_second = self.client.delete(f"/api/trades/{trade_id}/screenshots/{second_added.json()['id']}")
        self.assertEqual(deleted_second.status_code, 200)
        self.assertEqual(self.client.get(f"/api/trades/{trade_id}/screenshots").json(), [])

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

        # 1. Without candles synced, the server must NEVER invent fake candles
        res_chart = self.client.get(f"/api/sync/chart-data/{trade['id']}?timeframe=M15")
        self.assertEqual(res_chart.status_code, 200)
        chart_data = res_chart.json()
        self.assertIn("candles", chart_data)
        self.assertIn("markers", chart_data)
        self.assertIn("price_lines", chart_data)
        self.assertEqual(len(chart_data["candles"]), 0)
        self.assertFalse(chart_data["data_available"])
        self.assertFalse(chart_data["complete_coverage"])
        self.assertIn("No real", chart_data["message"])

        # 2. Upload real broker M15 candles covering entry to exit
        # Trade is 2026-09-04 08:30 to 11:15 UTC (open_ts ~ 1788510600)
        from datetime import datetime, timezone
        open_dt = datetime.fromisoformat("2026-09-04 08:30:00").replace(tzinfo=timezone.utc)
        open_ts = int(open_dt.timestamp())
        candles_payload = []
        # 8 context bars before + 11 bars during trade + 8 context bars after = 27 bars
        for idx in range(-8, 20):
            bar_ts = open_ts + (idx * 900)
            candles_payload.append({
                "time": bar_ts,
                "open": 1.2950,
                "high": 1.2995,
                "low": 1.2940,
                "close": 1.2980,
                "volume": 120.0
            })
        res_upload = self.client.post("/api/sync/candles", json={
            "symbol": "GBPUSD",
            "timeframe": "M15",
            "candles": candles_payload
        })
        self.assertEqual(res_upload.status_code, 200)

        # 3. Chart query with AUTO timeframe loads real M15 candles
        res_chart_real = self.client.get(f"/api/sync/chart-data/{trade['id']}?timeframe=AUTO")
        self.assertEqual(res_chart_real.status_code, 200)
        chart_real = res_chart_real.json()
        self.assertTrue(chart_real["data_available"])
        self.assertTrue(chart_real["complete_coverage"])
        self.assertEqual(chart_real["timeframe"], "M15")
        self.assertGreaterEqual(len(chart_real["candles"]), 20)
        self.assertEqual(len(chart_real["markers"]), 2)  # Entry and Exit

        # 4. Requesting H1 aggregates real M15 candles into real H1 candles
        res_chart_h1 = self.client.get(f"/api/sync/chart-data/{trade['id']}?timeframe=H1")
        self.assertEqual(res_chart_h1.status_code, 200)
        chart_h1 = res_chart_h1.json()
        self.assertTrue(chart_h1["data_available"])
        self.assertEqual(chart_h1["timeframe"], "H1")
        self.assertGreater(len(chart_h1["candles"]), 0)
        self.assertLess(len(chart_h1["candles"]), len(candles_payload))

        # 5. Long trade (30 days) automatically selects H4 timeframe
        res_long_trade = self.client.post("/api/trades", json={
            "account_id": self.account_id,
            "ticket": "swing_trade_30d",
            "symbol": "EURUSD",
            "direction": "BUY",
            "volume": 0.5,
            "open_time": "2026-08-01 08:00:00",
            "close_time": "2026-08-31 08:00:00",
            "open_price": 1.0800,
            "close_price": 1.1000,
            "net_profit": 1000.0
        })
        self.assertEqual(res_long_trade.status_code, 200)
        long_trade = res_long_trade.json()
        res_long_chart = self.client.get(f"/api/sync/chart-data/{long_trade['id']}?timeframe=AUTO")
        self.assertEqual(res_long_chart.status_code, 200)
        self.assertEqual(res_long_chart.json()["timeframe"], "H4")

    def test_partial_close_lifecycle(self):
        created = self.client.post("/api/trades", json={
            "account_id": self.account_id,
            "ticket": "manual_partial_parent",
            "symbol": "EURUSD",
            "direction": "BUY",
            "volume": 1.0,
            "open_time": "2026-09-04 10:00:00",
            "open_price": 1.085,
            "net_profit": 0.0
        })
        self.assertEqual(created.status_code, 200)
        trade_id = created.json()["id"]

        first = self.client.post(f"/api/trades/{trade_id}/partials", json={
            "volume": 0.5,
            "close_time": "2026-09-04 11:00:00",
            "close_price": 1.09,
            "net_profit": 100.0
        })
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "OPEN")
        self.assertEqual(len(first.json()["partial_closes"]), 1)
        self.assertEqual(first.json()["net_profit"], 100.0)

        second = self.client.post(f"/api/trades/{trade_id}/partials", json={
            "volume": 0.5,
            "close_time": "2026-09-04 12:00:00",
            "close_price": 1.095,
            "net_profit": 150.0
        })
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["status"], "WIN")
        self.assertEqual(len(second.json()["partial_closes"]), 2)
        self.assertEqual(second.json()["net_profit"], 250.0)

        fetched = self.client.get(f"/api/trades/{trade_id}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(len(fetched.json()["partial_closes"]), 2)

        listed = self.client.get("/api/trades", params={"search": "manual_partial_parent"})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["trades"][0]["partial_close_count"], 2)

        over_volume = self.client.post(f"/api/trades/{trade_id}/partials", json={
            "volume": 0.01,
            "close_time": "2026-09-04 13:00:00",
            "close_price": 1.1,
            "net_profit": 1.0
        })
        self.assertEqual(over_volume.status_code, 400)

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

    def test_mql_sync_rejects_an_invalid_key_even_when_account_number_matches(self):
        """Account numbers are public identifiers, not a sync authentication fallback."""
        sync_payload = {
            "account_number": "999888",
            "broker": "ICMarkets",
            "platform": "MT5",
            "currency": "USD",
            "balance": 54200.0,
            "equity": 54350.0,
            "closed_trades": [],
            "open_trades": []
        }
        valid = self.client.post(
            "/api/sync/mql", json=sync_payload, headers={"X-API-Key": self.api_key}
        )
        self.assertEqual(valid.status_code, 200)

        rejected = self.client.post(
            "/api/sync/mql", json=sync_payload,
            headers={"X-API-Key": "key_not_the_account_key"}
        )
        self.assertEqual(rejected.status_code, 403)

    def test_ctrader_cbot_push_endpoint(self):
        sync_payload = {
            "source": "ctrader-cbot",
            "account_number": "333444",
            "broker": "cTrader Demo Broker",
            "platform": "cTrader",
            "currency": "USD",
            "balance": 12000.0,
            "equity": 12025.0,
            "margin": 250.0,
            "free_margin": 11775.0,
            "leverage": 100,
            "closed_trades": [
                {
                    "ticket": "ctrader-deal-77",
                    "symbol": "XAUUSD",
                    "type": 1,
                    "lots": 0.1,
                    "open_time": "2026-09-04T08:00:00.0000000Z",
                    "close_time": "2026-09-04T09:00:00.0000000Z",
                    "open_price": 2500.0,
                    "close_price": 2495.0,
                    "commission": -2.0,
                    "swap": 0.0,
                    "profit": 48.0,
                    "comment": "cTrader cBot test",
                    "candles": [{"time": 1788508800, "open": 2500.0, "high": 2502.0, "low": 2494.0, "close": 2495.0, "volume": 100.0}]
                }
            ],
            "open_trades": [
                {
                    "ticket": "ctrader-position-88",
                    "symbol": "EURUSD",
                    "type": 0,
                    "lots": 0.5,
                    "open_time": "2026-09-04T10:00:00.0000000Z",
                    "open_price": 1.085,
                    "stop_loss": 1.08,
                    "take_profit": 1.09,
                    "commission": -1.0,
                    "swap": 0.0,
                    "profit": 25.0,
                    "comment": "cTrader open position"
                }
            ]
        }

        res = self.client.post("/api/sync/ctrader-push", json=sync_payload, headers={"X-API-Key": self.api_key})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "success")

        with get_connection() as conn:
            open_position = conn.execute(
                "SELECT status FROM trades WHERE account_id = ? AND ticket = ?;",
                (self.account_id, "ctrader-position-88")
            ).fetchone()
        self.assertIsNotNone(open_position)
        self.assertEqual(open_position["status"], "OPEN")

        # An empty position snapshot must remove stale cBot positions while
        # retaining the imported historical deal.
        sync_payload["open_trades"] = []
        res = self.client.post("/api/sync/ctrader-push", json=sync_payload, headers={"X-API-Key": self.api_key})
        self.assertEqual(res.status_code, 200)
        with get_connection() as conn:
            stale_position = conn.execute(
                "SELECT id FROM trades WHERE account_id = ? AND ticket = ?;",
                (self.account_id, "ctrader-position-88")
            ).fetchone()
            historical_deal = conn.execute(
                "SELECT id FROM trades WHERE account_id = ? AND ticket = ?;",
                (self.account_id, "ctrader-deal-77")
            ).fetchone()
        self.assertIsNone(stale_position)
        self.assertIsNotNone(historical_deal)

    def test_ctrader_cbot_grouped_partial_closes(self):
        base_payload = {
            "source": "ctrader-cbot",
            "account_number": "777888",
            "broker": "cTrader Partial Broker",
            "platform": "cTrader",
            "currency": "USD",
            "balance": 15000.0,
            "equity": 15000.0,
            "margin": 0.0,
            "free_margin": 15000.0,
            "leverage": 100,
            "closed_trades": [
                {
                    "ticket": "ctrader-position-501",
                    "position_id": "501",
                    "symbol": "GBPUSD",
                    "type": 0,
                    "lots": 0.5,
                    "open_time": "2026-09-04T10:00:00Z",
                    "close_time": "2026-09-04T11:00:00Z",
                    "open_price": 1.27,
                    "close_price": 1.275,
                    "profit": 100.0,
                    "partial_closes": [
                        {
                            "ticket": "ctrader-deal-5011",
                            "volume": 0.5,
                            "close_time": "2026-09-04T11:00:00Z",
                            "close_price": 1.275,
                            "net_profit": 100.0
                        }
                    ]
                }
            ],
            "open_trades": [
                {
                    "ticket": "ctrader-position-501",
                    "position_id": "501",
                    "symbol": "GBPUSD",
                    "type": 0,
                    "lots": 0.5,
                    "open_time": "2026-09-04T10:00:00Z",
                    "open_price": 1.27,
                    "profit": 20.0
                }
            ]
        }

        first = self.client.post("/api/sync/ctrader-push", json=base_payload, headers={"X-API-Key": self.api_key})
        self.assertEqual(first.status_code, 200)
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, volume, status, net_profit FROM trades WHERE account_id = ? AND ticket = ?;",
                (self.account_id, "ctrader-position-501")
            ).fetchone()
            partial_count = conn.execute(
                "SELECT COUNT(*) AS count FROM trade_partial_closes WHERE trade_id = ?;",
                (row["id"],)
            ).fetchone()["count"]
        self.assertEqual(row["volume"], 1.0)
        self.assertEqual(row["status"], "OPEN")
        self.assertEqual(row["net_profit"], 100.0)
        self.assertEqual(partial_count, 1)

        base_payload["closed_trades"][0]["lots"] = 1.0
        base_payload["closed_trades"][0]["close_time"] = "2026-09-04T12:00:00Z"
        base_payload["closed_trades"][0]["close_price"] = 1.28
        base_payload["closed_trades"][0]["profit"] = 250.0
        base_payload["closed_trades"][0]["partial_closes"].append({
            "ticket": "ctrader-deal-5012",
            "volume": 0.5,
            "close_time": "2026-09-04T12:00:00Z",
            "close_price": 1.28,
            "net_profit": 150.0
        })
        base_payload["open_trades"] = []

        second = self.client.post("/api/sync/ctrader-push", json=base_payload, headers={"X-API-Key": self.api_key})
        self.assertEqual(second.status_code, 200)
        with get_connection() as conn:
            row = conn.execute(
                "SELECT volume, status, net_profit FROM trades WHERE account_id = ? AND ticket = ?;",
                (self.account_id, "ctrader-position-501")
            ).fetchone()
            partial_count = conn.execute(
                "SELECT COUNT(*) AS count FROM trade_partial_closes pc JOIN trades t ON t.id = pc.trade_id WHERE t.account_id = ? AND t.ticket = ?;",
                (self.account_id, "ctrader-position-501")
            ).fetchone()["count"]
        self.assertEqual(row["volume"], 1.0)
        self.assertEqual(row["status"], "WIN")
        self.assertEqual(row["net_profit"], 250.0)
        self.assertEqual(partial_count, 2)

    def test_ctrader_without_credentials_does_not_simulate(self):
        res = self.client.post("/api/sync/ctrader", json={"account_id": self.account_id})
        self.assertEqual(res.status_code, 400)
        self.assertIn("credentials", res.json()["detail"])

    def test_metatrader_direct_sync_route_is_removed(self):
        res = self.client.post("/api/sync/mt-direct", json={"account_id": self.account_id})
        self.assertEqual(res.status_code, 404)

    def test_auto_sync_all_endpoint(self):
        res = self.client.post("/api/sync/auto-sync-all")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("synced_count", data)

if __name__ == "__main__":
    unittest.main()

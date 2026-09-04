"""Unit tests for SQLite database initialization and queries."""
import os
import unittest
import tempfile
import sqlite3

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["DB_DIR"] = self.temp_dir.name
        from server.database import init_db, get_connection
        self.init_db = init_db
        self.get_connection = get_connection
        self.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_database_initialization(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Check journal mode is WAL
            cursor.execute("PRAGMA journal_mode;")
            mode = cursor.fetchone()[0]
            self.assertEqual(mode.lower(), "wal")

            # Check tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cursor.fetchall()]
            self.assertIn("accounts", tables)
            self.assertIn("trades", tables)
            self.assertIn("playbooks", tables)
            self.assertIn("mistakes", tables)
            self.assertIn("market_candles", tables)
            self.assertIn("equity_history", tables)

    def test_seed_playbooks_and_mistakes(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM playbooks;")
            pb_count = cursor.fetchone()[0]
            self.assertGreater(pb_count, 0)

            cursor.execute("SELECT COUNT(*) FROM mistakes;")
            mk_count = cursor.fetchone()[0]
            self.assertGreater(mk_count, 0)

if __name__ == "__main__":
    unittest.main()

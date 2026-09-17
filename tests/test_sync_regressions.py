"""Broker identity and partial-exit regression tests, isolated from real data."""
import os
import tempfile
import unittest
from unittest.mock import patch

from server.database import init_db, get_connection
from server.connectors.mql_receiver import process_mql_payload
from server.models import MQLSyncPayload


class TestSyncRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, DB_DIR=self.tmp.name)
        self.env.start()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.env.stop)
        init_db()
        with get_connection() as conn:
            self.account = conn.execute("INSERT INTO accounts (name, platform, created_at, updated_at, api_key) VALUES ('Regression', 'MT5', '2026-09-01', '2026-09-01', 'regression-test-key')").lastrowid
            conn.commit()

    def trade(self, ticket, **changes):
        result = dict(ticket=ticket, symbol='EURUSD', type=0, lots=1.0,
                      open_time='2026-09-01 10:00:00', open_price=1.1,
                      close_time='2026-09-01 11:00:00', close_price=1.11, profit=100)
        result.update(changes)
        return result

    def sync(self, **changes):
        payload = dict(account_number='test-only', balance=10000, equity=10000, source='mql', **changes)
        return process_mql_payload('regression-test-key', MQLSyncPayload(**payload))

    def rows(self):
        with get_connection() as conn:
            return [dict(r) for r in conn.execute('SELECT * FROM trades WHERE account_id = ? ORDER BY id', (self.account,))]

    def partial(self, ticket='deal-1', **changes):
        result = dict(ticket=ticket, volume=0.4, close_time='2026-09-01 11:00:00',
                      close_price=1.12, net_profit=38, gross_profit=40, commission=-2)
        result.update(changes)
        return result

    def test_mt5_grouped_exits_and_live_snapshot_are_idempotent(self):
        grouped = self.trade('201', partial_closes=[self.partial()], lots=1.0)
        for _ in range(2):
            self.sync(closed_trades=[grouped])
            row = self.rows()[0]
            self.assertEqual(row['status'], 'OPEN')
            self.assertIsNone(row['close_time'])
            self.assertEqual(row['net_profit'], 38)
            self.sync(open_trades=[self.trade('201', lots=0.6, profit=12)])
            row = self.rows()[0]
            self.assertEqual(row['volume'], 1.0)
            self.assertEqual(row['net_profit'], 50)
            self.assertEqual(row['gross_profit'], 52)
            self.assertIsNone(row['close_time'])
        with get_connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM trade_partial_closes').fetchone()[0], 1)
        grouped['partial_closes'].append(self.partial('deal-2', volume=0.6, net_profit=60, gross_profit=63, commission=-3))
        self.sync(closed_trades=[grouped])
        self.sync(closed_trades=[grouped])
        row = self.rows()[0]
        self.assertEqual(row['status'], 'WIN')
        self.assertEqual(row['net_profit'], 98)
        self.assertEqual(row['volume'], 1.0)
        self.assertIsNotNone(row['close_time'])

    def test_grouped_history_restores_original_volume_after_first_live_sync(self):
        self.sync(open_trades=[self.trade('201', lots=0.4)])
        self.sync(closed_trades=[self.trade('201', lots=1.0, partial_closes=[self.partial(volume=0.6)])])
        row = self.rows()[0]
        self.assertEqual(row['volume'], 1.0)
        self.assertEqual(row['status'], 'OPEN')
        self.assertIsNone(row['close_time'])

    def test_live_candles_add_realized_profit_without_accumulating_repeats(self):
        from server.routers.sync import upload_candles
        self.sync(closed_trades=[self.trade('301', partial_closes=[self.partial()])])
        for floating in (12, 12, -8, 0):
            result = upload_candles({'candles': [], 'open_trades': [
                {'ticket': '301', 'profit': floating, 'current_price': 1.115}
            ]}, x_api_key='regression-test-key')
            self.assertEqual(result['updated_open_trades'], 1)
            row = self.rows()[0]
            self.assertEqual(row['net_profit'], 38 + floating)
            self.assertEqual(row['gross_profit'], 40 + floating)
            self.assertEqual(row['volume'], 1.0)
            self.assertIsNone(row['close_time'])
        upload_candles({'open_trades': [{'ticket': '301', 'current_price': 1.116}]}, x_api_key='regression-test-key')
        self.assertEqual(self.rows()[0]['net_profit'], 38)

    def test_authoritative_deal_migration_preserves_screenshots(self):
        self.sync(closed_trades=[self.trade('deal-1', comment='My annotated exit')])
        legacy_id = self.rows()[0]['id']
        with get_connection() as conn:
            conn.execute("INSERT INTO trade_screenshots (trade_id, source_url, image_url, caption, created_at) VALUES (?, 'https://example.test/chart', 'https://example.test/image', 'exit', '2026-09-01')", (legacy_id,))
            conn.commit()
        self.sync(closed_trades=[self.trade('401', partial_closes=[self.partial()])])
        parent = self.rows()[0]
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(parent['notes'], 'My annotated exit')
        with get_connection() as conn:
            screenshots = conn.execute('SELECT trade_id, caption FROM trade_screenshots').fetchall()
            self.assertEqual([(r['trade_id'], r['caption']) for r in screenshots], [(parent['id'], 'exit')])

    def test_grouped_fill_reuses_authoritatively_linked_pending_annotations(self):
        self.sync(pending_orders=[self.trade('mt5-order-501', order_id='501', comment='Entry plan')])
        pending_id = self.rows()[0]['id']
        self.sync(closed_trades=[self.trade('601', order_id='501', partial_closes=[self.partial()])])
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], pending_id)
        self.assertEqual(rows[0]['ticket'], '601')
        self.assertEqual(rows[0]['notes'], 'Entry plan')
        self.assertEqual(rows[0]['status'], 'OPEN')

    def test_grouped_partial_fill_with_cancelled_remainder_uses_executed_volume(self):
        self.sync(pending_orders=[self.trade(
            'mt5-order-501', order_id='501', lots=1.0, comment='Entry plan')])
        pending_id = self.rows()[0]['id']
        # Only 0.4 lots filled; the unfilled 0.6 lots were cancelled.
        exit_deal = self.partial()
        grouped = self.trade('601', order_id='501', lots=0.4,
                             partial_closes=[exit_deal])
        for _ in range(2):
            self.sync(closed_trades=[grouped], pending_orders=[])
            rows = self.rows()
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row['id'], pending_id)
            self.assertEqual(row['ticket'], '601')
            self.assertEqual(row['notes'], 'Entry plan')
            self.assertEqual(row['volume'], 0.4)
            self.assertEqual(row['status'], 'WIN')
            self.assertEqual(row['close_time'], exit_deal['close_time'])
            self.assertEqual(row['net_profit'], exit_deal['net_profit'])
        with get_connection() as conn:
            self.assertEqual(conn.execute(
                'SELECT COUNT(*) FROM trade_partial_closes WHERE trade_id = ?',
                (pending_id,)).fetchone()[0], 1)

    def test_incomplete_ctrader_parent_survives_history_only_sync(self):
        payload = MQLSyncPayload(account_number='test-only', balance=10000, equity=10000,
                                 source='ctrader-cbot', closed_trades=[self.trade(
                                     'ctrader-position-701', partial_closes=[self.partial()])])
        process_mql_payload('regression-test-key', payload)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0]['status'], 'OPEN')

    def test_distinct_broker_tickets_survive_identical_market_fields(self):
        for field in ('open_trades', 'closed_trades'):
            with self.subTest(field=field):
                self.sync(**{field: [self.trade('101'), self.trade('102')]})
                self.assertEqual({r['ticket'] for r in self.rows()}, {'101', '102'})
                self.sync(**{field: [self.trade('101'), self.trade('102')]})
                self.assertEqual(len(self.rows()), 2)

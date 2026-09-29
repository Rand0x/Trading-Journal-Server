"""Broker identity and partial-exit regression tests, isolated from real data."""
import os
import tempfile
import unittest
from unittest.mock import patch

from server.database import init_db, get_connection
from server.connectors.mql_receiver import process_mql_payload
from server.models import MQLSyncPayload


def datetime_str(ts):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


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

    def open_leg(self, ticket, **changes):
        changes.setdefault('close_time', None)
        changes.setdefault('close_price', None)
        return self.trade(ticket, **changes)

    def annotate(self, trade_id, notes):
        with get_connection() as conn:
            conn.execute('UPDATE trades SET notes = ?, setup_id = 1 WHERE id = ?', (notes, trade_id))
            conn.execute("INSERT INTO trade_screenshots (trade_id, source_url, image_url, caption, created_at) VALUES (?, 'https://example.test/c', 'https://example.test/i', 'entry', '2026-09-01')", (trade_id,))
            conn.commit()

    def test_stale_open_row_merges_into_closed_record_with_other_ticket(self):
        self.sync(open_trades=[self.open_leg('4214955', type=1, profit=547)])
        ghost_id = self.rows()[0]['id']
        self.annotate(ghost_id, 'Planned short at resistance')
        # Position closed; history reports it under a different id and it left the snapshot.
        self.sync(closed_trades=[self.trade('4047511', type=1, profit=-1345)], open_trades=[])
        self.sync(closed_trades=[], open_trades=[])
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['ticket'], '4047511')
        self.assertEqual(rows[0]['status'], 'LOSS')
        self.assertEqual(rows[0]['net_profit'], -1345)
        self.assertEqual(rows[0]['notes'], 'Planned short at resistance')
        self.assertEqual(rows[0]['setup_id'], 1)
        with get_connection() as conn:
            shots = conn.execute('SELECT trade_id FROM trade_screenshots').fetchall()
        self.assertEqual([r['trade_id'] for r in shots], [rows[0]['id']])

    def test_stale_open_row_without_close_record_is_cancelled_not_deleted(self):
        self.sync(open_trades=[self.open_leg('4214950', profit=-9)])
        ghost_id = self.rows()[0]['id']
        self.annotate(ghost_id, 'Keep me')
        self.sync(open_trades=[])
        row = self.rows()[0]
        self.assertEqual(row['id'], ghost_id)
        self.assertEqual(row['status'], 'CANCELLED')
        self.assertEqual(row['notes'], 'Keep me')

    def test_identical_legs_still_open_are_not_touched_when_one_closes(self):
        legs = [self.open_leg(t, lots=0.53) for t in ('4040034', '4040035', '4040036')]
        self.sync(open_trades=legs)
        self.sync(closed_trades=[self.trade('4040036', lots=0.53)], open_trades=legs[:2])
        by_ticket = {r['ticket']: r['status'] for r in self.rows()}
        self.assertEqual(by_ticket, {'4040034': 'OPEN', '4040035': 'OPEN', '4040036': 'WIN'})

    def test_reconcile_skips_manual_trades_and_payloads_without_open_list(self):
        self.sync(open_trades=[self.open_leg('901')])
        with get_connection() as conn:
            conn.execute("INSERT INTO trades (account_id, ticket, symbol, direction, volume, open_time, open_price, status, created_at, updated_at) VALUES (?, 'manual_1', 'EURUSD', 'BUY', 1.0, '2026-09-01 10:00:00', 1.1, 'OPEN', '2026-09-01', '2026-09-01')", (self.account,))
            conn.commit()
        self.sync(closed_trades=[])  # history-only payload: no open snapshot
        self.assertEqual({r['ticket']: r['status'] for r in self.rows()}, {'901': 'OPEN', 'manual_1': 'OPEN'})
        self.sync(open_trades=[])
        self.assertEqual({r['ticket']: r['status'] for r in self.rows()}, {'901': 'CANCELLED', 'manual_1': 'OPEN'})

    def test_mt5_fill_matches_pending_order_by_position_id(self):
        self.sync(pending_orders=[self.open_leg('mt5-order-777', order_id='777', comment='Entry plan')])
        pending_id = self.rows()[0]['id']
        self.sync(open_trades=[self.open_leg('777', position_id='777')], pending_orders=[])
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], pending_id)
        self.assertEqual(rows[0]['status'], 'OPEN')
        self.assertEqual(rows[0]['notes'], 'Entry plan')

    def test_mt4_fill_keeps_order_ticket_and_annotations(self):
        self.sync(pending_orders=[self.open_leg('mt4-order-888', order_id='888', comment='MT4 plan')])
        pending_id = self.rows()[0]['id']
        self.sync(open_trades=[self.open_leg('888')], pending_orders=[])
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], pending_id)
        self.assertEqual(rows[0]['ticket'], '888')
        self.assertEqual(rows[0]['notes'], 'MT4 plan')

    def test_point_distance_risk_migration_runs_once_and_spares_manual_trades(self):
        with get_connection() as conn:
            for ticket, risk in (('4040034', 28.57), ('manual_2', 28.57)):
                conn.execute("""INSERT INTO trades (account_id, ticket, symbol, direction, volume, open_time, close_time,
                    open_price, close_price, stop_loss, net_profit, status, initial_risk, r_multiple, created_at, updated_at)
                    VALUES (?, ?, 'XAUUSD', 'BUY', 0.53, '2026-09-24 09:27:51', '2026-09-24 12:00:00',
                    4258.57, 4270.14, 4230.00, 613.21, 'WIN', ?, 21.46, '2026-09-24', '2026-09-24')""",
                    (self.account, ticket, risk))
            conn.execute('DELETE FROM app_migrations')
            conn.commit()
        init_db()
        risk = {r['ticket']: (r['initial_risk'], r['r_multiple']) for r in self.rows()}
        self.assertEqual(risk['4040034'], (None, 0.4))
        self.assertEqual(risk['manual_2'], (28.57, 21.46))
        with get_connection() as conn:
            conn.execute("UPDATE trades SET initial_risk = 28.57 WHERE ticket = '4040034'")
            conn.commit()
        init_db()
        self.assertEqual(self.rows()[0]['initial_risk'], 28.57)

    def test_detail_grouping_matches_trade_log_rule(self):
        from server.routers.trades import _get_trade_with_partials
        self.sync(closed_trades=[
            self.trade('a1', open_time='2026-09-01 10:00:00'),
            self.trade('a2', open_time='2026-09-01 11:30:00', profit=-40),
            self.trade('a3', open_time='2026-09-01 16:00:00'),  # > 2h after a2
            self.trade('a4', open_time='2026-09-01 10:05:00', open_price=1.1002),
        ])
        self.sync(open_trades=[self.open_leg('a5', open_time='2026-09-01 10:10:00')])
        ids = {r['ticket']: r['id'] for r in self.rows()}
        with get_connection() as conn:
            detail = _get_trade_with_partials(conn.cursor(), ids['a1'])
            lonely = _get_trade_with_partials(conn.cursor(), ids['a3'])
        self.assertTrue(detail['is_grouped'])
        self.assertEqual(sorted(leg['ticket'] for leg in detail['sub_trades']), ['a1', 'a2'])
        self.assertEqual(detail['grouped_net_profit'], 60)
        self.assertFalse(lonely['is_grouped'])

    def test_dashboard_flags_mixed_account_currencies(self):
        from server.routers.dashboard import get_dashboard_summary
        single = get_dashboard_summary(account_id=None, date_from=None, date_to=None, symbol=None)
        self.assertFalse(single['mixed_currencies'])
        with get_connection() as conn:
            conn.execute("INSERT INTO accounts (name, platform, currency, created_at, updated_at, api_key) VALUES ('GBP acct', 'cTrader', 'GBP', '2026-09-01', '2026-09-01', 'gbp-key')")
            conn.commit()
        mixed = get_dashboard_summary(account_id=None, date_from=None, date_to=None, symbol=None)
        self.assertTrue(mixed['mixed_currencies'])
        self.assertEqual(mixed['currencies'], ['GBP', 'USD'])
        scoped = get_dashboard_summary(account_id=self.account, date_from=None, date_to=None, symbol=None)
        self.assertFalse(scoped['mixed_currencies'])

    def test_trade_list_pages_never_split_a_group(self):
        from fastapi.testclient import TestClient
        from server.main import app
        legs = [self.trade(f'g{i}', open_time=f'2026-09-01 10:0{i}:00', lots=0.5) for i in range(3)]
        singles = [self.trade(f's{i}', open_time=f'2026-09-0{i + 2} 10:00:00', open_price=1.2 + i / 10) for i in range(2)]
        self.sync(closed_trades=legs + singles)
        client = TestClient(app)
        pages = [client.get('/api/trades', params={'account_id': self.account, 'limit': 2, 'offset': o, 'sort_by': 'open_time', 'sort_order': 'asc'}).json()
                 for o in (0, 2)]
        self.assertEqual(pages[0]['total'], 3)
        self.assertEqual(pages[0]['total_legs'], 5)
        self.assertEqual(sorted(t['ticket'] for t in pages[0]['trades']), ['g0', 'g1', 'g2', 's0'])
        self.assertEqual([t['ticket'] for t in pages[1]['trades']], ['s1'])

    def test_candle_retention_keeps_recent_bars_and_trade_windows(self):
        from server.connectors.market_data import prune_market_candles
        day = 86400
        now = 1790000000
        trade_open = now - 200 * day
        self.sync(closed_trades=[self.trade('c1', open_time=datetime_str(trade_open), close_time=datetime_str(trade_open + 3600))])
        bars = {
            'recent': now - 10 * day,                 # inside retention period
            'before_trade': trade_open - 5 * day,     # inside the M15 replay window
            'far_old': now - 400 * day,               # outside everything -> pruned
        }
        with get_connection() as conn:
            for tf in ('M1', 'M15'):
                for ts in bars.values():
                    conn.execute("INSERT INTO market_candles (symbol, timeframe, timestamp, open, high, low, close) VALUES ('EURUSD', ?, ?, 1, 1, 1, 1)", (tf, ts))
            conn.commit()
        self.assertEqual(prune_market_candles(now_ts=now), 1)
        with get_connection() as conn:
            left = {(r['timeframe'], r['timestamp']) for r in conn.execute('SELECT timeframe, timestamp FROM market_candles')}
        self.assertNotIn(('M1', bars['far_old']), left)
        self.assertIn(('M15', bars['far_old']), left)  # higher timeframes are never pruned
        self.assertIn(('M1', bars['recent']), left)
        self.assertIn(('M1', bars['before_trade']), left)


    def test_trade_list_filters_by_realization_day(self):
        from fastapi.testclient import TestClient
        from server.main import app
        self.sync(closed_trades=[
            self.trade('full', open_time='2026-09-24 18:30:00', close_time='2026-09-25 03:10:00', profit=-50),
            self.trade('other', open_time='2026-09-25 10:00:00', close_time='2026-09-26 10:00:00'),
            self.trade('scaled', open_time='2026-09-20 10:00:00', close_time='2026-09-27 10:00:00',
                       partial_closes=[self.partial('p1', close_time='2026-09-25 09:00:00', volume=0.5),
                                       self.partial('p2', close_time='2026-09-27 10:00:00', volume=0.5)]),
        ])
        client = TestClient(app)
        def tickets(day):
            res = client.get('/api/trades', params={'account_id': self.account, 'closed_on': day})
            self.assertEqual(res.status_code, 200)
            return sorted(t['ticket'] for t in res.json()['trades'])
        # Opened on the 24th but closed on the 25th; the scaled position realized a partial on the 25th.
        self.assertEqual(tickets('2026-09-25'), ['full', 'scaled'])
        self.assertEqual(tickets('2026-09-24'), [])
        self.assertEqual(client.get('/api/trades', params={'closed_on': '25.09.2026'}).status_code, 422)
        # A calendar week (range) includes every trade realized inside it.
        res = client.get('/api/trades', params={'account_id': self.account, 'closed_from': '2026-09-21', 'closed_to': '2026-09-27'})
        self.assertEqual(sorted(t['ticket'] for t in res.json()['trades']), ['full', 'other', 'scaled'])
        res = client.get('/api/trades', params={'account_id': self.account, 'closed_from': '2026-09-26', 'closed_to': '2026-09-26'})
        self.assertEqual([t['ticket'] for t in res.json()['trades']], ['other'])

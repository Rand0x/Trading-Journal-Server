"""Unit tests for mathematical and statistical analytics."""
import unittest
from server.analytics import (
    calculate_trade_metrics,
    get_calendar_heatmap,
    get_equity_curve,
    get_performance_by_day_of_week,
    get_performance_by_hour,
    get_performance_by_symbol
)

class TestAnalytics(unittest.TestCase):
    def setUp(self):
        self.trades = [
            {"id": 1, "symbol": "EURUSD", "net_profit": 200.0, "status": "WIN", "open_time": "2026-09-01 09:30:00", "close_time": "2026-09-01 10:30:00", "volume": 1.0},
            {"id": 2, "symbol": "EURUSD", "net_profit": -100.0, "status": "LOSS", "open_time": "2026-09-01 14:00:00", "close_time": "2026-09-01 14:45:00", "volume": 1.0},
            {"id": 3, "symbol": "XAUUSD", "net_profit": 350.0, "status": "WIN", "open_time": "2026-09-02 11:00:00", "close_time": "2026-09-02 13:00:00", "volume": 0.5},
            {"id": 4, "symbol": "GBPUSD", "net_profit": 150.0, "status": "WIN", "open_time": "2026-09-03 08:00:00", "close_time": "2026-09-03 09:15:00", "volume": 1.0},
        ]

    def test_metrics_calculation(self):
        m = calculate_trade_metrics(self.trades, initial_balance=10000.0)
        self.assertEqual(m["total_trades"], 4)
        self.assertEqual(m["winning_trades"], 3)
        self.assertEqual(m["losing_trades"], 1)
        self.assertEqual(m["win_rate"], 75.0)
        self.assertEqual(m["net_profit"], 600.0)
        self.assertEqual(m["gross_profit"], 700.0)
        self.assertEqual(m["gross_loss"], 100.0)
        self.assertEqual(m["profit_factor"], 7.0)
        self.assertEqual(m["avg_win"], 233.33)
        self.assertEqual(m["avg_loss"], 100.0)
        self.assertEqual(m["largest_win"], 350.0)
        self.assertEqual(m["largest_loss"], -100.0)

    def test_calendar_heatmap(self):
        heatmap = get_calendar_heatmap(self.trades)
        self.assertIn("2026-09-01", heatmap)
        self.assertEqual(heatmap["2026-09-01"]["net_profit"], 100.0)
        self.assertEqual(heatmap["2026-09-01"]["trades_count"], 2)
        self.assertIn("2026-09-02", heatmap)
        self.assertEqual(heatmap["2026-09-02"]["net_profit"], 350.0)

    def test_equity_curve(self):
        equity = get_equity_curve(self.trades, initial_balance=10000.0)
        self.assertEqual(len(equity), 5)  # 1 start point + 4 trade points
        self.assertEqual(equity[-1]["balance"], 10600.0)
        self.assertEqual(equity[-1]["cumulative_pnl"], 600.0)

    def test_open_trades_metrics(self):
        trades_with_open = self.trades + [
            {"id": 5, "symbol": "EURUSD", "net_profit": 55.0, "status": "OPEN", "open_time": "2026-09-03 10:00:00", "close_time": None, "volume": 1.0},
            {"id": 6, "symbol": "USDJPY", "net_profit": 0.0, "status": "PENDING", "open_time": "2026-09-03 11:00:00", "close_time": None, "volume": 1.0}
        ]
        m = calculate_trade_metrics(trades_with_open, initial_balance=10000.0)
        # Closed trade metrics remain untainted
        self.assertEqual(m["total_trades"], 4)
        self.assertEqual(m["net_profit"], 600.0)
        # Open trades captured properly
        self.assertEqual(m["open_trades_count"], 1)
        self.assertEqual(m["open_pnl"], 55.0)
        self.assertEqual(m["total_pnl"], 655.0)

        # Performance by symbol ignores open trades
        syms = get_performance_by_symbol(trades_with_open)
        eur = next(s for s in syms if s["symbol"] == "EURUSD")
        self.assertEqual(eur["trades"], 2)
        self.assertEqual(eur["net_profit"], 100.0)

    def test_dashboard_insights_breakdowns(self):
        from server.analytics import get_dashboard_insights
        trades = [dict(t) for t in self.trades]
        trades[0].update(direction="BUY", r_multiple=2.0, setup_id=1)
        trades[1].update(direction="SELL", r_multiple=-1.0, setup_id=1, mistake_id=3)
        trades[2].update(direction="BUY", r_multiple=3.5)
        trades[3].update(direction="SELL", r_multiple=1.5, setup_id=2)
        trades += [
            {"id": 5, "symbol": "EURUSD", "net_profit": 40.0, "status": "OPEN", "open_time": "2026-09-04 08:00:00", "direction": "BUY"},
            {"id": 6, "symbol": "EURUSD", "net_profit": 500.0, "status": "WIN", "is_missed": 1, "open_time": "2026-09-04 09:00:00",
             "close_time": "2026-09-04 10:00:00", "r_multiple": 5.0},
        ]
        metrics = calculate_trade_metrics(trades, initial_balance=10000.0)
        ins = get_dashboard_insights(trades, metrics)

        dist = {b["label"]: b["count"] for b in ins["r_distribution"]}
        # Buckets are [low, high): a full -1R stop-out counts as "-1R to 0R".
        self.assertEqual(dist["-1R to 0R"], 1)
        self.assertEqual(dist["-2R to -1R"], 0)
        self.assertEqual(dist["1R to 2R"], 1)
        self.assertEqual(dist["2R to 3R"], 1)
        self.assertEqual(dist["≥ 3R"], 1)                # missed trade (5R) is excluded

        self.assertEqual(ins["long_short"]["long"], {"trades": 2, "wins": 2, "win_rate": 100.0, "net_profit": 550.0, "avg_r": 2.75})
        self.assertEqual(ins["long_short"]["short"]["net_profit"], 50.0)

        self.assertEqual(ins["day_stats"]["trading_days"], 3)
        self.assertEqual(ins["day_stats"]["green_days"], 3)
        self.assertEqual(ins["day_stats"]["best_day"], {"date": "2026-09-02", "net_profit": 350.0})
        self.assertEqual(ins["holding"]["winners_min"], 85.0)   # (60 + 120 + 75) / 3
        self.assertEqual(ins["holding"]["losers_min"], 45.0)

        self.assertEqual(ins["monthly"], [{"month": "2026-09", "net_profit": 600.0, "trades": 4, "win_rate": 75.0, "total_r": 6.0}])
        self.assertEqual(ins["plan_rate"], 50.0)               # trades 1 and 4: setup and no mistake
        self.assertEqual([t["id"] for t in ins["open_positions"]], [5])
        self.assertEqual(ins["recent_trades"][0]["id"], 4)

        score = ins["journal_score"]
        self.assertEqual(len(score["components"]), 6)
        by_key = {c["key"]: c["score"] for c in score["components"]}
        self.assertEqual(by_key["win_rate"], 100.0)            # 75 % win rate, capped
        self.assertEqual(by_key["discipline"], 50.0)
        self.assertAlmostEqual(score["score"], sum(by_key.values()) / 6, places=1)

    def test_calendar_and_equity_use_realization_dates(self):
        trades = [
            # Scaled out: 0.5 lots closed on the 2nd, remainder closed on the 4th.
            {"id": 1, "symbol": "EURUSD", "status": "WIN", "net_profit": 300.0, "volume": 1.0, "r_multiple": 3.0,
             "open_time": "2026-09-01 10:00:00", "close_time": "2026-09-04 12:00:00",
             "partial_closes": [
                 {"volume": 0.5, "close_time": "2026-09-02 09:00:00", "net_profit": 100.0},
                 {"volume": 0.5, "close_time": "2026-09-04 12:00:00", "net_profit": 200.0},
             ]},
            # Still open with one realized partial on the 3rd; its floating P&L is ignored.
            {"id": 2, "symbol": "XAUUSD", "status": "OPEN", "net_profit": 999.0, "volume": 1.0,
             "open_time": "2026-09-02 08:00:00",
             "partial_closes": [{"volume": 0.4, "close_time": "2026-09-03 15:00:00", "net_profit": -40.0}]},
            # Open without partials: nothing realized yet.
            {"id": 3, "symbol": "GBPUSD", "status": "OPEN", "net_profit": 55.0, "open_time": "2026-09-03 09:00:00"},
            # Opened on the 4th, closed on the 5th: counts on the 5th.
            {"id": 4, "symbol": "US30", "status": "LOSS", "net_profit": -80.0, "r_multiple": -1.0,
             "open_time": "2026-09-04 22:00:00", "close_time": "2026-09-05 01:00:00"},
        ]
        cal = get_calendar_heatmap(trades, initial_balance=10000.0)
        self.assertEqual(sorted(cal), ["2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05"])
        self.assertEqual(cal["2026-09-02"]["net_profit"], 100.0)
        self.assertEqual(cal["2026-09-02"]["r_multiple"], 1.5)          # half the volume of a 3R trade
        self.assertEqual(cal["2026-09-03"]["net_profit"], -40.0)
        self.assertEqual(cal["2026-09-04"]["net_profit"], 200.0)
        self.assertEqual(cal["2026-09-05"]["net_profit"], -80.0)
        self.assertEqual((cal["2026-09-05"]["wins"], cal["2026-09-05"]["losses"]), (0, 1))

        equity = get_equity_curve(trades, initial_balance=10000.0)
        self.assertEqual(equity[0]["symbol"], "START")
        self.assertEqual([p["cumulative_pnl"] for p in equity[1:]], [100.0, 60.0, 260.0, 180.0])
        self.assertEqual(equity[-1]["balance"], 10180.0)

    def test_dashboard_insights_empty(self):
        from server.analytics import get_dashboard_insights
        ins = get_dashboard_insights([], calculate_trade_metrics([], 10000.0))
        self.assertEqual(ins["journal_score"]["score"], 0.0)
        self.assertEqual(ins["day_stats"]["best_day"], None)
        self.assertEqual(sum(b["count"] for b in ins["r_distribution"]), 0)

if __name__ == "__main__":
    unittest.main()

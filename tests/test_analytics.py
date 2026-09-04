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

    def test_performance_by_symbol(self):
        syms = get_performance_by_symbol(self.trades)
        self.assertEqual(len(syms), 3)
        eur = next(s for s in syms if s["symbol"] == "EURUSD")
        self.assertEqual(eur["trades"], 2)
        self.assertEqual(eur["win_rate"], 50.0)
        self.assertEqual(eur["net_profit"], 100.0)

if __name__ == "__main__":
    unittest.main()

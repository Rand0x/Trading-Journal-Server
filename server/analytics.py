"""
Pure Quantitative Trading Analytics Engine (No AI)
High performance, lightweight, zero-dependency statistical calculations
optimized for low-resource environments (Raspberry Pi 3 Model B).
"""

import math
from datetime import datetime
from typing import List, Dict, Any, Optional

def calculate_trade_metrics(trades: List[Dict[str, Any]], initial_balance: float = 10000.0) -> Dict[str, Any]:
    """
    Computes full TradeZella-style KPIs for a list of trades.
    Trades should be a list of dicts with at least:
    - net_profit (float)
    - status ('WIN', 'LOSS', 'BE', 'CLOSED', 'OPEN')
    - open_time / close_time (str)
    """
    closed_trades = [t for t in trades if t.get("status") in ("CLOSED", "WIN", "LOSS", "BE") or t.get("close_time")]
    total_closed = len(closed_trades)

    if total_closed == 0:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "breakeven_trades": 0,
            "win_rate": 0.0,
            "loss_rate": 0.0,
            "net_profit": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "profit_factor": 0.0,
            "avg_trade": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "win_loss_ratio": 0.0,
            "largest_win": 0.0,
            "largest_loss": 0.0,
            "expectancy": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_amount": 0.0,
            "max_drawdown_pct": 0.0,
            "current_streak": 0,
            "max_win_streak": 0,
            "max_loss_streak": 0,
            "kelly_criterion": 0.0,
        }

    wins = []
    losses = []
    breakevens = []

    for t in closed_trades:
        pnl = float(t.get("net_profit") or 0.0)
        if pnl > 0.001:
            wins.append(pnl)
        elif pnl < -0.001:
            losses.append(pnl)
        else:
            breakevens.append(pnl)

    win_count = len(wins)
    loss_count = len(losses)
    be_count = len(breakevens)

    win_rate = (win_count / total_closed) * 100.0 if total_closed > 0 else 0.0
    loss_rate = (loss_count / total_closed) * 100.0 if total_closed > 0 else 0.0

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    net_profit = gross_profit - gross_loss

    if gross_loss > 0:
        profit_factor = round(gross_profit / gross_loss, 2)
    elif gross_profit > 0:
        profit_factor = 999.0
    else:
        profit_factor = 0.0

    avg_trade = round(net_profit / total_closed, 2)
    avg_win = round(gross_profit / win_count, 2) if win_count > 0 else 0.0
    avg_loss = round(gross_loss / loss_count, 2) if loss_count > 0 else 0.0
    win_loss_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0

    largest_win = round(max(wins), 2) if wins else 0.0
    largest_loss = round(min(losses), 2) if losses else 0.0

    # Trade Expectancy: (Win Rate * Avg Win) - (Loss Rate * Avg Loss)
    p_win = win_rate / 100.0
    p_loss = loss_rate / 100.0
    expectancy = round((p_win * avg_win) - (p_loss * avg_loss), 2)

    # Kelly Criterion % = W - ((1 - W) / R)
    if win_loss_ratio > 0:
        kelly = (p_win - ((1.0 - p_win) / win_loss_ratio)) * 100.0
        kelly_criterion = round(max(0.0, kelly), 2)
    else:
        kelly_criterion = 0.0

    # Sharpe Ratio (Trade returns standard deviation)
    pnl_series = [float(t.get("net_profit") or 0.0) for t in closed_trades]
    mean_pnl = sum(pnl_series) / total_closed
    variance = sum((x - mean_pnl) ** 2 for x in pnl_series) / total_closed
    std_dev = math.sqrt(variance) if variance > 0 else 0.0
    sharpe_ratio = round((mean_pnl / std_dev) * math.sqrt(252), 2) if std_dev > 0 else 0.0

    # Drawdown & Streaks calculation
    # Sort trades chronologically by close_time or open_time
    sorted_trades = sorted(closed_trades, key=lambda x: x.get("close_time") or x.get("open_time") or "")
    
    running_balance = initial_balance
    peak_balance = initial_balance
    max_dd_amount = 0.0
    max_dd_pct = 0.0

    current_streak = 0
    max_win_streak = 0
    max_loss_streak = 0
    temp_win_streak = 0
    temp_loss_streak = 0

    for t in sorted_trades:
        pnl = float(t.get("net_profit") or 0.0)
        running_balance += pnl

        if running_balance > peak_balance:
            peak_balance = running_balance

        dd_amount = peak_balance - running_balance
        if dd_amount > max_dd_amount:
            max_dd_amount = dd_amount
            if peak_balance > 0:
                max_dd_pct = (dd_amount / peak_balance) * 100.0

        # Streak tracking
        if pnl > 0.001:
            temp_win_streak += 1
            temp_loss_streak = 0
            current_streak = temp_win_streak if current_streak >= 0 else 1
            if temp_win_streak > max_win_streak:
                max_win_streak = temp_win_streak
        elif pnl < -0.001:
            temp_loss_streak += 1
            temp_win_streak = 0
            current_streak = -temp_loss_streak if current_streak <= 0 else -1
            if temp_loss_streak > max_loss_streak:
                max_loss_streak = temp_loss_streak
        else:
            temp_win_streak = 0
            temp_loss_streak = 0

    return {
        "total_trades": total_closed,
        "winning_trades": win_count,
        "losing_trades": loss_count,
        "breakeven_trades": be_count,
        "win_rate": round(win_rate, 1),
        "loss_rate": round(loss_rate, 1),
        "net_profit": round(net_profit, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": profit_factor,
        "avg_trade": avg_trade,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "win_loss_ratio": win_loss_ratio,
        "largest_win": largest_win,
        "largest_loss": largest_loss,
        "expectancy": expectancy,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown_amount": round(max_dd_amount, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "current_streak": current_streak,
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "kelly_criterion": kelly_criterion,
    }

def get_calendar_heatmap(trades: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Groups closed trades by date (YYYY-MM-DD) for TradeZella-style calendar heatmap.
    Returns:
    {
       "2026-09-01": {"date": "2026-09-01", "pnl": 450.50, "trades_count": 3, "wins": 2, "losses": 1},
       ...
    }
    """
    days = {}
    for t in trades:
        close_time = t.get("close_time") or t.get("open_time")
        if not close_time:
            continue
        # Extract YYYY-MM-DD
        date_str = close_time[:10]
        pnl = float(t.get("net_profit") or 0.0)

        if date_str not in days:
            days[date_str] = {
                "date": date_str,
                "net_profit": 0.0,
                "trades_count": 0,
                "wins": 0,
                "losses": 0,
                "breakevens": 0,
            }

        days[date_str]["net_profit"] += pnl
        days[date_str]["trades_count"] += 1
        if pnl > 0.001:
            days[date_str]["wins"] += 1
        elif pnl < -0.001:
            days[date_str]["losses"] += 1
        else:
            days[date_str]["breakevens"] += 1

    # Round all values
    for d, data in days.items():
        data["net_profit"] = round(data["net_profit"], 2)

    return days

def get_equity_curve(trades: List[Dict[str, Any]], initial_balance: float = 10000.0) -> List[Dict[str, Any]]:
    """
    Builds cumulative equity curve points chronologically.
    Returns:
    [
       {"time": "2026-08-01 10:30", "balance": 10000.0, "net_pnl": 0.0, "trade_id": None},
       {"time": "2026-08-01 14:15", "balance": 10250.0, "net_pnl": 250.0, "trade_id": 1, "symbol": "EURUSD"}
    ]
    """
    closed = [t for t in trades if t.get("status") in ("CLOSED", "WIN", "LOSS", "BE") or t.get("close_time")]
    sorted_trades = sorted(closed, key=lambda x: x.get("close_time") or x.get("open_time") or "")

    points = []
    running_balance = initial_balance
    cumulative_pnl = 0.0

    # Start point
    if sorted_trades:
        first_time = sorted_trades[0].get("open_time") or sorted_trades[0].get("close_time") or ""
        points.append({
            "time": first_time[:16].replace("T", " "),
            "balance": round(running_balance, 2),
            "cumulative_pnl": 0.0,
            "trade_pnl": 0.0,
            "trade_id": None,
            "symbol": "START"
        })

    for t in sorted_trades:
        pnl = float(t.get("net_profit") or 0.0)
        running_balance += pnl
        cumulative_pnl += pnl
        c_time = t.get("close_time") or t.get("open_time") or ""

        points.append({
            "time": c_time[:16].replace("T", " "),
            "balance": round(running_balance, 2),
            "cumulative_pnl": round(cumulative_pnl, 2),
            "trade_pnl": round(pnl, 2),
            "trade_id": t.get("id"),
            "symbol": t.get("symbol", "")
        })

    return points

def get_performance_by_day_of_week(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Performance breakdown by Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday."""
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    buckets = {i: {"day": day_names[i], "day_num": i, "trades": 0, "wins": 0, "losses": 0, "net_profit": 0.0} for i in range(7)}

    for t in trades:
        t_time = t.get("open_time") or t.get("close_time")
        if not t_time:
            continue
        try:
            # Parse ISO or YYYY-MM-DD HH:MM:SS
            clean_time = t_time[:19].replace("T", " ")
            dt = datetime.fromisoformat(clean_time)
            w = dt.weekday()  # 0=Monday, 6=Sunday
            pnl = float(t.get("net_profit") or 0.0)

            buckets[w]["trades"] += 1
            buckets[w]["net_profit"] += pnl
            if pnl > 0.001:
                buckets[w]["wins"] += 1
            elif pnl < -0.001:
                buckets[w]["losses"] += 1
        except Exception:
            continue

    result = []
    for i in range(7):
        b = buckets[i]
        tr = b["trades"]
        wr = round((b["wins"] / tr) * 100.0, 1) if tr > 0 else 0.0
        result.append({
            "day": b["day"],
            "trades": tr,
            "wins": b["wins"],
            "losses": b["losses"],
            "win_rate": wr,
            "net_profit": round(b["net_profit"], 2)
        })

    return result

def get_performance_by_hour(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Performance breakdown by hour of day (00:00 - 23:00) to find best trading sessions."""
    hours = {h: {"hour": f"{h:02d}:00", "trades": 0, "wins": 0, "losses": 0, "net_profit": 0.0} for h in range(24)}

    for t in trades:
        t_time = t.get("open_time")
        if not t_time:
            continue
        try:
            clean_time = t_time[:19].replace("T", " ")
            dt = datetime.fromisoformat(clean_time)
            h = dt.hour
            pnl = float(t.get("net_profit") or 0.0)

            hours[h]["trades"] += 1
            hours[h]["net_profit"] += pnl
            if pnl > 0.001:
                hours[h]["wins"] += 1
            elif pnl < -0.001:
                hours[h]["losses"] += 1
        except Exception:
            continue

    result = []
    for h in range(24):
        b = hours[h]
        tr = b["trades"]
        wr = round((b["wins"] / tr) * 100.0, 1) if tr > 0 else 0.0
        result.append({
            "hour": b["hour"],
            "trades": tr,
            "win_rate": wr,
            "net_profit": round(b["net_profit"], 2)
        })

    return result

def get_performance_by_symbol(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Performance breakdown per symbol/ticker."""
    symbols = {}

    for t in trades:
        sym = (t.get("symbol") or "UNKNOWN").upper()
        pnl = float(t.get("net_profit") or 0.0)

        if sym not in symbols:
            symbols[sym] = {
                "symbol": sym,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "net_profit": 0.0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "volume": 0.0
            }

        symbols[sym]["trades"] += 1
        symbols[sym]["net_profit"] += pnl
        symbols[sym]["volume"] += float(t.get("volume") or 0.0)

        if pnl > 0.001:
            symbols[sym]["wins"] += 1
            symbols[sym]["gross_profit"] += pnl
        elif pnl < -0.001:
            symbols[sym]["losses"] += 1
            symbols[sym]["gross_loss"] += abs(pnl)

    result = []
    for sym, data in symbols.items():
        tr = data["trades"]
        wr = round((data["wins"] / tr) * 100.0, 1) if tr > 0 else 0.0
        pf = round(data["gross_profit"] / data["gross_loss"], 2) if data["gross_loss"] > 0 else (999.0 if data["gross_profit"] > 0 else 0.0)
        result.append({
            "symbol": sym,
            "trades": tr,
            "win_rate": wr,
            "net_profit": round(data["net_profit"], 2),
            "profit_factor": pf,
            "volume": round(data["volume"], 2),
            "avg_trade": round(data["net_profit"] / tr, 2) if tr > 0 else 0.0
        })

    # Sort by highest net profit
    result.sort(key=lambda x: x["net_profit"], reverse=True)
    return result

def get_performance_by_setup(trades: List[Dict[str, Any]], playbooks: Dict[int, str]) -> List[Dict[str, Any]]:
    """Performance breakdown per playbook setup."""
    stats = {}

    for t in trades:
        setup_id = t.get("setup_id")
        setup_name = playbooks.get(setup_id, "No Setup / Discretionary") if setup_id else "No Setup / Discretionary"
        pnl = float(t.get("net_profit") or 0.0)

        if setup_name not in stats:
            stats[setup_name] = {
                "setup_name": setup_name,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "net_profit": 0.0,
                "gross_profit": 0.0,
                "gross_loss": 0.0
            }

        stats[setup_name]["trades"] += 1
        stats[setup_name]["net_profit"] += pnl

        if pnl > 0.001:
            stats[setup_name]["wins"] += 1
            stats[setup_name]["gross_profit"] += pnl
        elif pnl < -0.001:
            stats[setup_name]["losses"] += 1
            stats[setup_name]["gross_loss"] += abs(pnl)

    result = []
    for name, data in stats.items():
        tr = data["trades"]
        wr = round((data["wins"] / tr) * 100.0, 1) if tr > 0 else 0.0
        pf = round(data["gross_profit"] / data["gross_loss"], 2) if data["gross_loss"] > 0 else (999.0 if data["gross_profit"] > 0 else 0.0)
        result.append({
            "setup_name": name,
            "trades": tr,
            "win_rate": wr,
            "net_profit": round(data["net_profit"], 2),
            "profit_factor": pf,
            "avg_trade": round(data["net_profit"] / tr, 2) if tr > 0 else 0.0
        })

    result.sort(key=lambda x: x["net_profit"], reverse=True)
    return result

def get_cost_of_mistakes(trades: List[Dict[str, Any]], mistakes_map: Dict[int, str]) -> List[Dict[str, Any]]:
    """Calculates exactly how much money each mistake has cost the trader."""
    stats = {}

    for t in trades:
        mistake_id = t.get("mistake_id")
        if not mistake_id:
            continue

        mistake_name = mistakes_map.get(mistake_id, f"Mistake #{mistake_id}")
        pnl = float(t.get("net_profit") or 0.0)

        if mistake_name not in stats:
            stats[mistake_name] = {
                "mistake_name": mistake_name,
                "count": 0,
                "total_loss": 0.0,
                "worst_loss": 0.0
            }

        stats[mistake_name]["count"] += 1
        if pnl < 0:
            stats[mistake_name]["total_loss"] += abs(pnl)
            if abs(pnl) > stats[mistake_name]["worst_loss"]:
                stats[mistake_name]["worst_loss"] = abs(pnl)

    result = []
    for name, data in stats.items():
        result.append({
            "mistake_name": name,
            "count": data["count"],
            "total_loss": round(data["total_loss"], 2),
            "worst_loss": round(data["worst_loss"], 2),
            "avg_loss": round(data["total_loss"] / data["count"], 2) if data["count"] > 0 else 0.0
        })

    result.sort(key=lambda x: x["total_loss"], reverse=True)
    return result

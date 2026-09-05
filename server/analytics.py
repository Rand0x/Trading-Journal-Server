"""
Pure Quantitative Trading Analytics Engine (No AI)
High performance, lightweight, zero-dependency statistical calculations
designed for efficient, dependency-free calculations.
"""

import math
import re
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

def _normalize_date_str(time_str: Optional[str]) -> str:
    if not time_str:
        return ""
    s = str(time_str).strip()
    if len(s) >= 10 and s[4] == "." and s[7] == ".":
        s = s[:4] + "-" + s[5:7] + "-" + s[8:]
    return s

def compute_r_multiple(
    direction: str,
    open_price: Optional[float],
    stop_loss: Optional[float],
    close_price: Optional[float] = None,
    net_profit: Optional[float] = None,
    initial_risk: Optional[float] = None,
    partial_closes: Optional[List[Dict[str, Any]]] = None,
    volume: Optional[float] = None
) -> Optional[float]:
    """
    Deterministically computes the R-Multiple of a trade.
    Priority 1: If net_profit is given and initial_risk is given (> 0):
                r_multiple = net_profit / initial_risk
    Priority 2: If open_price and stop_loss are provided and stop_loss != open_price:
                rew / risk_dist (or sum of partials)
    """
    if net_profit is not None and initial_risk is not None and initial_risk > 0:
        return round(net_profit / initial_risk, 2)

    if open_price is not None and open_price > 0 and stop_loss is not None and stop_loss > 0 and open_price != stop_loss:
        risk_dist = abs(open_price - stop_loss)
        if partial_closes:
            parent_vol = volume or sum(float(pc.get("volume", 0.0) or 0.0) for pc in partial_closes)
            if parent_vol > 0 and risk_dist > 0:
                total_r = 0.0
                for pc in partial_closes:
                    pc_vol = float(pc.get("volume", 0.0) or 0.0)
                    pc_price = float(pc.get("close_price", 0.0) or 0.0)
                    pc_rew = (pc_price - open_price) if direction.upper() in ("BUY", "LONG") else (open_price - pc_price)
                    total_r += (pc_rew / risk_dist) * (pc_vol / parent_vol)
                return round(total_r, 2)
        if close_price is not None and risk_dist > 0:
            rew = (close_price - open_price) if direction.upper() in ("BUY", "LONG") else (open_price - close_price)
            return round(rew / risk_dist, 2)
    return None

def calculate_trade_metrics(trades: List[Dict[str, Any]], initial_balance: float = 10000.0) -> Dict[str, Any]:
    """
    Computes full TradeZella-style KPIs for a list of trades.
    Trades should be a list of dicts with at least:
    - net_profit (float)
    - status ('WIN', 'LOSS', 'BE', 'CLOSED', 'OPEN')
    - open_time / close_time (str)
    Excludes missed trades (is_missed = 1) from all PnL and risk calculations.
    """
    valid_trades = [t for t in trades if not t.get("is_missed") and t.get("status") not in ("CANCELLED", "PENDING")]
    closed_trades = [t for t in valid_trades if t.get("status") in ("CLOSED", "WIN", "LOSS", "BE") or t.get("close_time")]
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
            "current_drawdown_amount": 0.0,
            "current_drawdown_pct": 0.0,
            "current_drawdown_r": 0.0,
            "max_drawdown_r": 0.0,
            "current_streak": 0,
            "current_streak_type": "NONE",
            "current_streak_count": 0,
            "max_win_streak": 0,
            "max_loss_streak": 0,
            "kelly_criterion": 0.0,
            "total_r": 0.0,
            "avg_r": 0.0,
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

    r_vals = [float(t["r_multiple"]) for t in closed_trades if t.get("r_multiple") is not None]
    total_r = round(sum(r_vals), 2)
    avg_r = round(sum(r_vals) / len(r_vals), 2) if r_vals else 0.0

    cum_r = 0.0
    peak_r = 0.0
    max_r_dd = 0.0

    current_streak = 0
    max_win_streak = 0
    max_loss_streak = 0
    temp_win_streak = 0
    temp_loss_streak = 0

    for t in sorted_trades:
        pnl = float(t.get("net_profit") or 0.0)
        running_balance += pnl
        if t.get("r_multiple") is not None:
            cum_r += float(t["r_multiple"])
        elif initial_balance > 0:
            # Fallback approximate R if not explicitly present: 1R = 1% of initial balance
            cum_r += pnl / (initial_balance * 0.01)

        if cum_r > peak_r:
            peak_r = cum_r
        r_dd = peak_r - cum_r
        if r_dd > max_r_dd:
            max_r_dd = r_dd

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

    # Current status from ATH
    cur_dd_amount = round(max(0.0, peak_balance - running_balance), 2)
    cur_dd_pct = round((cur_dd_amount / peak_balance) * 100.0, 2) if peak_balance > 0 else 0.0
    cur_dd_r = round(max(0.0, peak_r - cum_r), 2)

    # Current streak from the newest trade backwards
    cur_streak_type = "NONE"
    cur_streak_count = 0
    for t in reversed(sorted_trades):
        pnl = float(t.get("net_profit") or 0.0)
        if cur_streak_type == "NONE":
            if pnl > 0.001:
                cur_streak_type = "WIN"
                cur_streak_count = 1
            elif pnl < -0.001:
                cur_streak_type = "LOSS"
                cur_streak_count = 1
            else:
                break
        elif cur_streak_type == "WIN":
            if pnl > 0.001:
                cur_streak_count += 1
            else:
                break
        elif cur_streak_type == "LOSS":
            if pnl < -0.001:
                cur_streak_count += 1
            else:
                break

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
        "current_drawdown_amount": cur_dd_amount,
        "current_drawdown_pct": cur_dd_pct,
        "current_drawdown_r": cur_dd_r,
        "max_drawdown_r": round(max_r_dd, 2),
        "current_streak": current_streak,
        "current_streak_type": cur_streak_type,
        "current_streak_count": cur_streak_count,
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "kelly_criterion": kelly_criterion,
        "total_r": total_r,
        "avg_r": avg_r,
    }

def get_calendar_heatmap(trades: List[Dict[str, Any]], initial_balance: float = 10000.0) -> Dict[str, Dict[str, Any]]:
    """
    Groups closed trades by date (YYYY-MM-DD) for TradeZella-style calendar heatmap.
    Excludes missed trades (is_missed = 1).
    Returns:
    {
       "2026-09-01": {"date": "2026-09-01", "net_profit": 450.50, "r_multiple": 2.4, "pct_return": 4.51, "trades_count": 3, "wins": 2, "losses": 1},
       ...
    }
    """
    days = {}
    valid_trades = [t for t in trades if not t.get("is_missed") and t.get("status") not in ("CANCELLED", "PENDING")]
    for t in valid_trades:
        close_time = t.get("close_time") or t.get("open_time")
        if not close_time:
            continue
        # Extract YYYY-MM-DD
        date_str = _normalize_date_str(close_time)[:10]
        pnl = float(t.get("net_profit") or 0.0)
        r_mult = float(t["r_multiple"]) if t.get("r_multiple") is not None else None

        if date_str not in days:
            days[date_str] = {
                "date": date_str,
                "net_profit": 0.0,
                "r_multiple": 0.0,
                "pct_return": 0.0,
                "trades_count": 0,
                "wins": 0,
                "losses": 0,
                "breakevens": 0,
            }

        days[date_str]["net_profit"] += pnl
        if r_mult is not None:
            days[date_str]["r_multiple"] += r_mult
        elif initial_balance > 0:
            days[date_str]["r_multiple"] += pnl / (initial_balance * 0.01)

        days[date_str]["trades_count"] += 1
        if pnl > 0.001:
            days[date_str]["wins"] += 1
        elif pnl < -0.001:
            days[date_str]["losses"] += 1
        else:
            days[date_str]["breakevens"] += 1

    # Round all values and compute pct_return
    for d, data in days.items():
        data["net_profit"] = round(data["net_profit"], 2)
        data["r_multiple"] = round(data["r_multiple"], 2)
        if initial_balance > 0:
            data["pct_return"] = round((data["net_profit"] / initial_balance) * 100.0, 2)
        else:
            data["pct_return"] = 0.0

    return days

def get_equity_curve(trades: List[Dict[str, Any]], initial_balance: float = 10000.0) -> List[Dict[str, Any]]:
    """
    Builds cumulative equity curve points chronologically.
    Excludes missed trades (is_missed = 1).
    """
    valid_trades = [t for t in trades if not t.get("is_missed") and t.get("status") not in ("CANCELLED", "PENDING")]
    closed = [t for t in valid_trades if t.get("status") in ("CLOSED", "WIN", "LOSS", "BE") or t.get("close_time")]
    sorted_trades = sorted(closed, key=lambda x: x.get("close_time") or x.get("open_time") or "")

    points = []
    running_balance = initial_balance
    cumulative_pnl = 0.0
    cumulative_r = 0.0

    # Start point
    if sorted_trades:
        first_time = sorted_trades[0].get("open_time") or sorted_trades[0].get("close_time") or ""
        points.append({
            "time": first_time[:16].replace("T", " "),
            "balance": round(running_balance, 2),
            "cumulative_pnl": 0.0,
            "cumulative_r": 0.0,
            "trade_pnl": 0.0,
            "r_multiple": 0.0,
            "trade_id": None,
            "symbol": "START"
        })

    for t in sorted_trades:
        pnl = float(t.get("net_profit") or 0.0)
        running_balance += pnl
        cumulative_pnl += pnl
        r_val = float(t["r_multiple"]) if t.get("r_multiple") is not None else (pnl / (initial_balance * 0.01) if initial_balance > 0 else 0.0)
        cumulative_r += r_val
        c_time = t.get("close_time") or t.get("open_time") or ""

        points.append({
            "time": c_time[:16].replace("T", " "),
            "balance": round(running_balance, 2),
            "cumulative_pnl": round(cumulative_pnl, 2),
            "cumulative_r": round(cumulative_r, 2),
            "trade_pnl": round(pnl, 2),
            "r_multiple": round(r_val, 2),
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
            clean_time = _normalize_date_str(t_time)[:19].replace("T", " ")
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
            clean_time = _normalize_date_str(t_time)[:19].replace("T", " ")
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

def get_take_profit_analysis(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Evaluates Take-Profit scale-outs with support for an arbitrary number of TPs.
    Analyzes hit rate, percentage of wins, and average R contribution per TP level.
    """
    valid_trades = [t for t in trades if not t.get("is_missed") and t.get("status") not in ("CANCELLED", "PENDING")]
    closed_trades = [t for t in valid_trades if t.get("status") in ("CLOSED", "WIN", "LOSS", "BE") or t.get("close_time")]
    total_closed = len(closed_trades)
    win_trades = [t for t in closed_trades if float(t.get("net_profit") or 0.0) > 0.001 or t.get("status") == "WIN"]
    total_wins = len(win_trades)

    if total_closed == 0:
        return {
            "total_closed": 0,
            "total_wins": 0,
            "levels": [],
            "exit_distribution": {}
        }

    # Find maximum partial close count across all trades
    max_partials = 0
    for t in closed_trades:
        pcs = t.get("partial_closes") or []
        if len(pcs) > max_partials:
            max_partials = len(pcs)

    # Total levels to show (at least 3, or dynamic max_partials)
    total_levels = max(3, max_partials)

    levels_stats = []
    for lvl in range(1, total_levels + 1):
        reached_trades = []
        r_contributions = []

        for t in closed_trades:
            pcs = t.get("partial_closes") or []
            reached = False
            r_contrib = 0.0

            if len(pcs) >= lvl:
                pc = pcs[lvl - 1]
                parent_vol = float(t.get("volume") or 0.0) or sum(float(p.get("volume", 0.0) or 0.0) for p in pcs)
                pc_vol = float(pc.get("volume", 0.0) or 0.0)
                sl = float(t.get("stop_loss", 0.0) or 0.0)
                open_p = float(t.get("open_price", 0.0) or 0.0)
                direction = (t.get("direction") or "BUY").upper()
                pc_price = float(pc.get("close_price", 0.0) or 0.0)
                pc_net = float(pc.get("net_profit", 0.0) or 0.0)
                rew = (pc_price - open_p) if direction in ("BUY", "LONG") else (open_p - pc_price)

                # A partial exit represents a reached Take Profit if it realized a profit
                if rew > 0 or pc_net > 0.001 or (lvl == 1 and t.get("status") == "WIN"):
                    reached = True
                    if sl > 0 and open_p > 0 and sl != open_p and parent_vol > 0:
                        risk_dist = abs(open_p - sl)
                        r_contrib = (rew / risk_dist) * (pc_vol / parent_vol)
                    elif t.get("r_multiple") is not None and float(t.get("net_profit") or 0.0) != 0:
                        r_contrib = (pc_net / float(t.get("net_profit") or 1.0)) * float(t["r_multiple"])
                    elif t.get("r_multiple") is not None and len(pcs) > 0:
                        r_contrib = float(t["r_multiple"]) / len(pcs)

            elif lvl == 1 and not pcs and (t.get("status") == "WIN" or float(t.get("net_profit") or 0.0) > 0.001):
                reached = True
                r_contrib = float(t.get("r_multiple") or 0.0)

            if reached:
                reached_trades.append(t)
                r_contributions.append(r_contrib)

        pct_all = round((len(reached_trades) / total_closed) * 100.0, 1) if total_closed > 0 else 0.0
        pct_wins = round((len(reached_trades) / total_wins) * 100.0, 1) if total_wins > 0 else 0.0
        avg_r_contrib = round(sum(r_contributions) / len(r_contributions), 2) if r_contributions else 0.0

        levels_stats.append({
            "level": lvl,
            "name": f"TP{lvl}",
            "reached_count": len(reached_trades),
            "pct_of_all": pct_all,
            "pct_of_wins": pct_wins,
            "avg_r_contribution": avg_r_contrib
        })

    # Exit distribution
    exit_counts = {}
    for t in closed_trades:
        status = t.get("status") or "CLOSED"
        pcs = t.get("partial_closes") or []
        if pcs:
            last_pc = pcs[-1]
            last_net = float(last_pc.get("net_profit", 0.0) or 0.0)
            if last_net < -0.001 or status == "LOSS":
                exit_name = f"TP{len(pcs)-1} + SL" if len(pcs) > 1 else "Partial Exit + SL"
            elif abs(last_net) <= 0.001 or status == "BE":
                exit_name = f"TP{len(pcs)-1} + BE" if len(pcs) > 1 else "Partial Exit + BE"
            else:
                exit_name = f"TP{len(pcs)} (Partial Exit)"
        elif status == "LOSS":
            exit_name = "Stop Loss"
        elif status == "BE":
            exit_name = "Break-Even"
        elif status == "WIN":
            exit_name = "Take Profit (Full)"
        else:
            exit_name = "Manual Close"
        exit_counts[exit_name] = exit_counts.get(exit_name, 0) + 1

    return {
        "total_closed": total_closed,
        "total_wins": total_wins,
        "levels": levels_stats,
        "exit_distribution": exit_counts
    }

def get_signal_combinations(trades: List[Dict[str, Any]], min_samples: int = 2) -> Dict[str, Any]:
    """
    Evaluates confluence by analyzing pairwise signal combinations and their uplift vs solo edge.
    """
    valid_trades = [t for t in trades if not t.get("is_missed") and t.get("status") not in ("CANCELLED", "PENDING")]
    closed_trades = [t for t in valid_trades if t.get("status") in ("CLOSED", "WIN", "LOSS", "BE") or t.get("close_time")]

    def parse_signals(raw):
        if not raw:
            return []
        if isinstance(raw, list):
            return [str(s).strip() for s in raw if str(s).strip()]
        return [s.strip() for s in re.split(r"[,;|\n]", str(raw)) if s.strip()]

    trade_signals = [(t, parse_signals(t.get("signals") or t.get("tags"))) for t in closed_trades]

    all_signals = set()
    for _, sigs in trade_signals:
        all_signals.update(sigs)

    solo_stats = {}
    for sig in all_signals:
        matching = [t for t, sigs in trade_signals if sig in sigs]
        if not matching:
            continue
        wins = [t for t in matching if float(t.get("net_profit") or 0.0) > 0.001 or t.get("status") == "WIN"]
        r_vals = [float(t["r_multiple"]) for t in matching if t.get("r_multiple") is not None]
        avg_r = round(sum(r_vals) / len(r_vals), 2) if r_vals else 0.0
        wr = round((len(wins) / len(matching)) * 100.0, 1)
        solo_stats[sig] = {
            "signal": sig,
            "count": len(matching),
            "wins": len(wins),
            "win_rate": wr,
            "avg_r": avg_r
        }

    combos = []
    signals_list = sorted(list(all_signals))
    for i in range(len(signals_list)):
        for j in range(i + 1, len(signals_list)):
            sig1 = signals_list[i]
            sig2 = signals_list[j]
            matching = [t for t, sigs in trade_signals if sig1 in sigs and sig2 in sigs]
            if len(matching) < min_samples:
                continue
            wins = [t for t in matching if float(t.get("net_profit") or 0.0) > 0.001 or t.get("status") == "WIN"]
            r_vals = [float(t["r_multiple"]) for t in matching if t.get("r_multiple") is not None]
            avg_r = round(sum(r_vals) / len(r_vals), 2) if r_vals else 0.0
            wr = round((len(wins) / len(matching)) * 100.0, 1)

            best_solo_ev = max(solo_stats.get(sig1, {}).get("avg_r", 0.0), solo_stats.get(sig2, {}).get("avg_r", 0.0))
            uplift = round(avg_r - best_solo_ev, 2)

            net_profit_sum = round(sum(float(t.get("net_profit") or 0.0) for t in matching), 2)
            combos.append({
                "signal_a": sig1,
                "signal_b": sig2,
                "count": len(matching),
                "wins": len(wins),
                "win_rate": wr,
                "net_profit": net_profit_sum,
                "avg_r": avg_r,
                "uplift": uplift
            })

    combos.sort(key=lambda x: (x["avg_r"], x["uplift"]), reverse=True)
    solo_list = sorted(list(solo_stats.values()), key=lambda x: x["win_rate"], reverse=True)

    return {
        "solo": solo_list,
        "combinations": combos
    }

def get_psychology_performance(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Correlates psychological mindset (pre-trade and during-trade) with trade outcomes.
    """
    valid_trades = [t for t in trades if not t.get("is_missed") and t.get("status") not in ("CANCELLED", "PENDING")]
    closed_trades = [t for t in valid_trades if t.get("status") in ("CLOSED", "WIN", "LOSS", "BE") or t.get("close_time")]

    def parse_emotions(val):
        if not val:
            return []
        if isinstance(val, list):
            return [str(e).strip() for e in val if str(e).strip()]
        return [e.strip() for e in str(val).split(",") if e.strip()]

    def analyze_field(field_name):
        buckets = {}
        for t in closed_trades:
            emos = parse_emotions(t.get(field_name))
            if not emos and field_name == "emotion_pre" and t.get("emotions"):
                emos = [t.get("emotions").strip()]

            pnl = float(t.get("net_profit") or 0.0)
            is_win = pnl > 0.001 or t.get("status") == "WIN"
            r_val = float(t.get("r_multiple")) if t.get("r_multiple") is not None else 0.0

            for emo in emos:
                if emo not in buckets:
                    buckets[emo] = {"emotion": emo, "count": 0, "wins": 0, "losses": 0, "net_profit": 0.0, "r_sum": 0.0, "r_count": 0}
                b = buckets[emo]
                b["count"] += 1
                b["net_profit"] += pnl
                if is_win:
                    b["wins"] += 1
                else:
                    b["losses"] += 1
                if t.get("r_multiple") is not None:
                    b["r_sum"] += r_val
                    b["r_count"] += 1

        res = []
        for emo, b in buckets.items():
            wr = round((b["wins"] / b["count"]) * 100.0, 1) if b["count"] > 0 else 0.0
            avg_r = round(b["r_sum"] / b["r_count"], 2) if b["r_count"] > 0 else 0.0
            res.append({
                "emotion": emo,
                "count": b["count"],
                "wins": b["wins"],
                "losses": b["losses"],
                "win_rate": wr,
                "net_profit": round(b["net_profit"], 2),
                "total_r": round(b["r_sum"], 2),
                "avg_r": avg_r
            })
        res.sort(key=lambda x: x["win_rate"], reverse=True)
        return res

    return {
        "emotion_pre": analyze_field("emotion_pre"),
        "emotion_during": analyze_field("emotion_during")
    }

def get_weekly_review(trades: List[Dict[str, Any]], week_offset: int = 0) -> Dict[str, Any]:
    """
    Generates an automated weekly review with KPIs, best/worst trade, and emotional patterns.
    """
    today = date.today()
    monday_this_week = today - timedelta(days=today.weekday())
    target_monday = monday_this_week + timedelta(weeks=week_offset)
    target_sunday = target_monday + timedelta(days=6)

    start_iso = target_monday.strftime("%Y-%m-%d")
    end_iso = target_sunday.strftime("%Y-%m-%d")

    week_trades = []
    for t in trades:
        time_str = t.get("close_time") or t.get("open_time") or ""
        d_str = _normalize_date_str(time_str)[:10]
        if start_iso <= d_str <= end_iso:
            week_trades.append(t)

    missed_trades = [t for t in week_trades if t.get("is_missed")]
    active_week_trades = [t for t in week_trades if not t.get("is_missed") and t.get("status") not in ("CANCELLED", "PENDING")]
    closed_week_trades = [t for t in active_week_trades if t.get("status") in ("CLOSED", "WIN", "LOSS", "BE") or t.get("close_time")]

    wins = [t for t in closed_week_trades if float(t.get("net_profit") or 0.0) > 0.001 or t.get("status") == "WIN"]
    losses = [t for t in closed_week_trades if float(t.get("net_profit") or 0.0) < -0.001 or t.get("status") == "LOSS"]
    bes = [t for t in closed_week_trades if t not in wins and t not in losses]

    total_net = sum(float(t.get("net_profit") or 0.0) for t in closed_week_trades)
    r_vals = [float(t["r_multiple"]) for t in closed_week_trades if t.get("r_multiple") is not None]
    total_r = round(sum(r_vals), 2)

    win_rate = round((len(wins) / len(closed_week_trades)) * 100.0, 1) if closed_week_trades else 0.0

    best_trade = None
    worst_trade = None
    if closed_week_trades:
        sorted_by_perf = sorted(
            closed_week_trades,
            key=lambda x: float(x.get("net_profit") or 0.0)
        )
        worst_trade = sorted_by_perf[0]
        best_trade = sorted_by_perf[-1]

    sorted_chrono = sorted(closed_week_trades, key=lambda x: x.get("close_time") or x.get("open_time") or "")
    max_w = 0
    max_l = 0
    cur_w = 0
    cur_l = 0
    for t in sorted_chrono:
        pnl = float(t.get("net_profit") or 0.0)
        if pnl > 0.001:
            cur_w += 1
            cur_l = 0
            if cur_w > max_w:
                max_w = cur_w
        elif pnl < -0.001:
            cur_l += 1
            cur_w = 0
            if cur_l > max_l:
                max_l = cur_l
        else:
            cur_w = 0
            cur_l = 0

    loss_emos = {}
    for t in losses:
        raw = t.get("emotion_pre") or t.get("emotions")
        if raw:
            for emo in re.split(r"[,;|\n]", str(raw)):
                emo_clean = emo.strip()
                if emo_clean:
                    loss_emos[emo_clean] = loss_emos.get(emo_clean, 0) + 1
    top_loss_emo = max(loss_emos.items(), key=lambda x: x[1])[0] if loss_emos else None

    playbook_counts = {}
    for t in active_week_trades:
        pb = t.get("setup_name") or t.get("setup_id")
        if pb:
            playbook_counts[str(pb)] = playbook_counts.get(str(pb), 0) + 1
    top_playbook = max(playbook_counts.items(), key=lambda x: x[1])[0] if playbook_counts else None

    missing_r_count = sum(1 for t in closed_week_trades if t.get("r_multiple") is None)

    return {
        "start_date": start_iso,
        "end_date": end_iso,
        "week_label": f"{target_monday.strftime('%d.%m.')} – {target_sunday.strftime('%d.%m.%Y')}",
        "week_offset": week_offset,
        "trades_count": len(active_week_trades),
        "closed_count": len(closed_week_trades),
        "wins_count": len(wins),
        "losses_count": len(losses),
        "be_count": len(bes),
        "win_rate": win_rate,
        "net_profit": round(total_net, 2),
        "total_r": total_r,
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "max_win_streak": max_w,
        "max_loss_streak": max_l,
        "top_loss_emotion": top_loss_emo,
        "top_playbook": top_playbook,
        "missed_trades_count": len(missed_trades),
        "missed_trades": missed_trades,
        "missing_r_count": missing_r_count
    }

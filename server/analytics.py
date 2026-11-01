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

def _annualized_daily_sharpe(daily_values: Dict[str, float]) -> float:
    """
    Sharpe ratio (risk-free rate 0) from daily results, annualized with
    sqrt(252) trading days. Weekdays without a closed trade count as 0 so
    quiet days are not skipped; weekend days only count when traded.
    The ratio is scale-free, so daily amounts and daily % give the same value.
    """
    parsed = {}
    for key, value in daily_values.items():
        try:
            parsed[date.fromisoformat(str(key)[:10])] = float(value or 0.0)
        except ValueError:
            continue
    if not parsed:
        return 0.0
    series = []
    day = min(parsed)
    end = max(parsed)
    while day <= end:
        if day in parsed:
            series.append(parsed[day])
        elif day.weekday() < 5:
            series.append(0.0)
        day += timedelta(days=1)
    if len(series) < 2:
        return 0.0
    mean = sum(series) / len(series)
    variance = sum((x - mean) ** 2 for x in series) / (len(series) - 1)
    if variance <= 0:
        return 0.0
    return round(mean / math.sqrt(variance) * math.sqrt(252), 2)

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
                (initial_risk is always a currency amount; legacy price distances
                are cleared by a one-time migration in database.py)
    Priority 2: If open_price and stop_loss are provided and stop_loss != open_price:
                rew / risk_dist (or volume-weighted sum of partials)
    """
    if net_profit is not None and initial_risk is not None and initial_risk > 0:
        return round(net_profit / initial_risk, 2)

    if open_price is not None and open_price > 0 and stop_loss is not None and stop_loss > 0 and open_price != stop_loss:
        sl_dist = abs(open_price - stop_loss)
        if partial_closes:
            parent_vol = volume or sum(float(pc.get("volume", 0.0) or 0.0) for pc in partial_closes)
            if parent_vol > 0:
                total_r = 0.0
                for pc in partial_closes:
                    pc_vol = float(pc.get("volume", 0.0) or 0.0)
                    pc_price = float(pc.get("close_price", 0.0) or 0.0)
                    pc_rew = (pc_price - open_price) if direction.upper() in ("BUY", "LONG") else (open_price - pc_price)
                    total_r += (pc_rew / sl_dist) * (pc_vol / parent_vol)
                return round(total_r, 2)
        if close_price is not None:
            rew = (close_price - open_price) if direction.upper() in ("BUY", "LONG") else (open_price - close_price)
            return round(rew / sl_dist, 2)

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
    open_trades = [t for t in valid_trades if t.get("status") == "OPEN" and not t.get("close_time")]
    open_pnl = sum(float(t.get("net_profit") or 0.0) for t in open_trades)
    open_count = len(open_trades)
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
            "open_trades_count": open_count,
            "open_pnl": round(open_pnl, 2),
            "total_pnl": round(open_pnl, 2),
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

    # Sharpe Ratio from daily results (per-trade values annualized with
    # sqrt(252) treated every trade as a trading day and inflated the ratio).
    daily_pnl: Dict[str, float] = {}
    for t in closed_trades:
        day_key = _normalize_date_str(t.get("close_time") or t.get("open_time"))[:10]
        daily_pnl[day_key] = daily_pnl.get(day_key, 0.0) + float(t.get("net_profit") or 0.0)
    sharpe_ratio = _annualized_daily_sharpe(daily_pnl)

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
        # The deepest percentage drawdown can happen at a different point than
        # the largest absolute one (e.g. after the balance has grown), so
        # track both independently.
        if peak_balance > 0:
            dd_pct = (dd_amount / peak_balance) * 100.0
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

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
        "open_trades_count": open_count,
        "open_pnl": round(open_pnl, 2),
        "total_pnl": round(net_profit + open_pnl, 2),
    }

def get_realized_events(trades: List[Dict[str, Any]], initial_balance: float = 10000.0) -> List[Dict[str, Any]]:
    """
    Every realized P&L event, in chronological order.

    - A closing deal of a scaled-out position counts on its own close time.
    - A fully closed trade counts on its close time (minus what its partial
      closes already realized, e.g. entry commission).
    - Floating P&L of open positions is never included.
    Missed, pending and cancelled trades are excluded. Each event carries the
    R share of its trade (volume-weighted for partial closes).
    """
    events = []
    for t in trades:
        if t.get("is_missed") or t.get("status") in ("CANCELLED", "PENDING"):
            continue
        is_closed = t.get("status") in ("CLOSED", "WIN", "LOSS", "BE") or (
            t.get("status") != "OPEN" and t.get("close_time")
        )
        total_pnl = float(t.get("net_profit") or 0.0)
        total_r = float(t["r_multiple"]) if t.get("r_multiple") is not None else None
        partials = [pc for pc in (t.get("partial_closes") or []) if pc.get("close_time")]
        volume = float(t.get("volume") or 0.0) or sum(float(pc.get("volume") or 0.0) for pc in partials)

        def cash_r(pnl):
            # Without a known risk, 1 R is approximated as 1 % of the starting balance.
            return pnl / (initial_balance * 0.01) if initial_balance > 0 else 0.0

        base = {"trade_id": t.get("id"), "symbol": t.get("symbol", ""), "open_time": t.get("open_time")}
        realized = 0.0
        realized_r = 0.0
        for pc in partials:
            pnl = float(pc.get("net_profit") or 0.0)
            if total_r is None:
                r_val = cash_r(pnl)
            else:
                r_val = total_r * float(pc.get("volume") or 0.0) / volume if volume > 0 else 0.0
            events.append({**base, "time": _normalize_date_str(pc["close_time"]), "pnl": pnl, "r": r_val, "closes_trade": False})
            realized += pnl
            realized_r += r_val

        if is_closed:
            close_time = t.get("close_time") or t.get("open_time")
            if not close_time:
                continue
            remainder = total_pnl - realized
            if partials and abs(remainder) < 0.005 and (total_r is None or abs(total_r - realized_r) < 0.005):
                events[-1]["closes_trade"] = True
                continue
            r_rem = (total_r - realized_r) if total_r is not None else cash_r(remainder)
            events.append({**base, "time": _normalize_date_str(close_time), "pnl": remainder, "r": r_rem, "closes_trade": True})

    events.sort(key=lambda e: e["time"])
    return events


def get_calendar_heatmap(trades: List[Dict[str, Any]], initial_balance: float = 10000.0) -> Dict[str, Dict[str, Any]]:
    """
    Realized P&L per calendar day (YYYY-MM-DD) for the TradeZella-style heatmap.
    Uses get_realized_events(): partial exits count on the day they were
    realized, open positions contribute nothing until they close.
    A trade counts once per day it realized P&L; win/loss is judged on what it
    realized that day.
    Returns:
    {
       "2026-09-01": {"date": "2026-09-01", "net_profit": 450.50, "r_multiple": 2.4, "pct_return": 4.51, "trades_count": 3, "wins": 2, "losses": 1},
       ...
    }
    """
    days: Dict[str, Dict[str, Any]] = {}
    per_trade: Dict[str, Dict[Any, float]] = {}
    for e in get_realized_events(trades, initial_balance):
        date_str = e["time"][:10]
        day = days.setdefault(date_str, {
            "date": date_str, "net_profit": 0.0, "r_multiple": 0.0, "pct_return": 0.0,
            "trades_count": 0, "wins": 0, "losses": 0, "breakevens": 0,
        })
        day["net_profit"] += e["pnl"]
        day["r_multiple"] += e["r"]
        trade_key = e["trade_id"] if e["trade_id"] is not None else id(e)
        per_trade.setdefault(date_str, {})
        per_trade[date_str][trade_key] = per_trade[date_str].get(trade_key, 0.0) + e["pnl"]

    for date_str, data in days.items():
        results = per_trade.get(date_str, {}).values()
        data["trades_count"] = len(results)
        data["wins"] = sum(1 for v in results if v > 0.001)
        data["losses"] = sum(1 for v in results if v < -0.001)
        data["breakevens"] = data["trades_count"] - data["wins"] - data["losses"]
        data["net_profit"] = round(data["net_profit"], 2)
        data["r_multiple"] = round(data["r_multiple"], 2)
        data["pct_return"] = round((data["net_profit"] / initial_balance) * 100.0, 2) if initial_balance > 0 else 0.0

    return days


def get_equity_curve(trades: List[Dict[str, Any]], initial_balance: float = 10000.0) -> List[Dict[str, Any]]:
    """
    Cumulative realized equity, one point per realized event (see get_realized_events).
    Excludes missed trades (is_missed = 1) and floating P&L.
    """
    events = get_realized_events(trades, initial_balance)
    points = []
    running_balance = initial_balance
    cumulative_pnl = 0.0
    cumulative_r = 0.0

    if events:
        first_open = _normalize_date_str(events[0].get("open_time") or "")
        start = first_open if first_open and first_open < events[0]["time"] else events[0]["time"]
        points.append({
            "time": start[:16].replace("T", " "),
            "balance": round(running_balance, 2),
            "cumulative_pnl": 0.0,
            "cumulative_r": 0.0,
            "trade_pnl": 0.0,
            "r_multiple": 0.0,
            "trade_id": None,
            "symbol": "START"
        })

    for e in events:
        running_balance += e["pnl"]
        cumulative_pnl += e["pnl"]
        cumulative_r += e["r"]
        points.append({
            "time": e["time"][:16].replace("T", " "),
            "balance": round(running_balance, 2),
            "cumulative_pnl": round(cumulative_pnl, 2),
            "cumulative_r": round(cumulative_r, 2),
            "trade_pnl": round(e["pnl"], 2),
            "r_multiple": round(e["r"], 2),
            "trade_id": e["trade_id"],
            "symbol": e["symbol"],
            "partial": not e["closes_trade"],
        })

    return points

def get_account_return_curves(trades: List[Dict[str, Any]], accounts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Currency-neutral equity curves for the multi-account overview.

    Each account gets its own curve in percent of its own starting balance
    (10,000 GBP -> 11,000 GBP is +10 %), so accounts of different size and
    currency can be compared on one chart. The "average" curve weights every
    account equally: at each point in time it is the mean of the accounts'
    cumulative returns (an account counts as 0 % before its first trade).
    Accounts without closed trades in the selection, or without a starting
    balance, are left out of both.
    """
    curves = []
    for color_index, account in enumerate(accounts):
        initial_balance = float(account.get("initial_balance") or 0.0)
        if initial_balance <= 0:
            continue
        account_trades = [t for t in trades if t.get("account_id") == account.get("id")]
        points = get_equity_curve(account_trades, initial_balance)
        if not points:
            continue
        pct_points = [
            {
                "time": p["time"],
                "pct": round(p["cumulative_pnl"] / initial_balance * 100.0, 2),
                "cumulative_pnl": p["cumulative_pnl"],
                "trade_pnl": p["trade_pnl"],
                "trade_id": p["trade_id"],
                "symbol": p["symbol"],
            }
            for p in points
        ]
        curves.append({
            "account_id": account.get("id"),
            # Stable per-account colour slot, shared with the comparison table.
            "color_index": color_index,
            "name": account.get("name") or f"Account {account.get('id')}",
            "currency": (account.get("currency") or "USD").upper(),
            "initial_balance": initial_balance,
            "net_profit": pct_points[-1]["cumulative_pnl"],
            "return_pct": pct_points[-1]["pct"],
            "trades": len(pct_points) - 1,
            "points": pct_points,
        })

    average = []
    if curves:
        # Sort by time, then keep each curve's own order (never by value: a
        # START point and a losing trade can share the same timestamp).
        events = sorted(
            ((p["time"], index, seq, p["pct"])
             for index, curve in enumerate(curves)
             for seq, p in enumerate(curve["points"])),
            key=lambda e: (e[0], e[1], e[2]),
        )
        current = [0.0] * len(curves)
        for time_str, index, _, pct in events:
            current[index] = pct
            value = round(sum(current) / len(curves), 2)
            if average and average[-1]["time"] == time_str:
                average[-1]["pct"] = value
            else:
                average.append({"time": time_str, "pct": value})

    return {
        "accounts": curves,
        "average": average,
        "average_return_pct": average[-1]["pct"] if average else 0.0,
    }

def _is_closed_trade(t: Dict[str, Any]) -> bool:
    """Realized trade: not missed/pending/cancelled and closed (by status or close time)."""
    if t.get("is_missed") or t.get("status") in ("CANCELLED", "PENDING"):
        return False
    return t.get("status") in ("CLOSED", "WIN", "LOSS", "BE") or bool(t.get("close_time"))


def _trade_r(t: Dict[str, Any], initial_balance: float) -> float:
    """Explicit R-multiple, else the journal's fallback of 1R = 1 % of the account's start."""
    if t.get("r_multiple") is not None:
        return float(t["r_multiple"])
    if initial_balance > 0:
        return float(t.get("net_profit") or 0.0) / (initial_balance * 0.01)
    return 0.0


def attach_trade_returns(trades: List[Dict[str, Any]], accounts: List[Dict[str, Any]]) -> int:
    """
    Annotate trades for currency-neutral breakdowns of several accounts.

    trade_pct: the trade's P&L in % of its own account's starting balance
               (None when the account has no starting balance).
    return_contrib: trade_pct / N, N = accounts with closed trades. Summed
               over any group (symbol, weekday, setup, ...) it is that group's
               share of the equal-weighted average return, so all groups of a
               breakdown add up to the dashboard's average return.
    Returns N.
    """
    balances = {a.get("id"): float(a.get("initial_balance") or 0.0) for a in accounts}
    active = {
        t.get("account_id") for t in trades
        if _is_closed_trade(t) and balances.get(t.get("account_id"), 0.0) > 0
    }
    n = len(active)
    for t in trades:
        balance = balances.get(t.get("account_id"), 0.0)
        pct = float(t.get("net_profit") or 0.0) / balance * 100.0 if balance > 0 else None
        t["trade_pct"] = pct
        t["return_contrib"] = pct / n if (pct is not None and n) else 0.0
    return n


_MONEY_FIELDS = ("net_profit", "gross_profit", "commission", "swap")


def scale_trades_to_return_share(
    trades: List[Dict[str, Any]], accounts: List[Dict[str, Any]], active_accounts: int
) -> List[Dict[str, Any]]:
    """
    Copies of the trades with every amount expressed as its share of the
    equal-weighted average return in % (amount / start balance / N * 100).

    Feeding these into the money-based dashboard breakdowns (weekday, month,
    long/short, day statistics, symbols) gives currency-neutral results that
    add up to the overview's average return. Pass initial_balance=100/N to
    those functions so their 1R = 1 % fallback keeps the original R values.
    Trades of accounts without a starting balance are left out.
    """
    if active_accounts <= 0:
        return []
    balances = {a.get("id"): float(a.get("initial_balance") or 0.0) for a in accounts}
    scaled = []
    for t in trades:
        balance = balances.get(t.get("account_id"), 0.0)
        if balance <= 0:
            continue
        factor = 100.0 / (balance * active_accounts)
        copy = dict(t)
        for field in _MONEY_FIELDS:
            if copy.get(field) is not None:
                copy[field] = float(copy[field]) * factor
        copy["partial_closes"] = [
            {**pc, **{f: float(pc[f]) * factor for f in _MONEY_FIELDS if pc.get(f) is not None}}
            for pc in (t.get("partial_closes") or [])
        ]
        scaled.append(copy)
    return scaled


def _pct_profit_factor(gross_win_pct: float, gross_loss_pct: float) -> float:
    if gross_loss_pct > 0:
        return round(gross_win_pct / gross_loss_pct, 2)
    return 999.0 if gross_win_pct > 0 else 0.0


def _add_pct(stats: Dict[str, Any], t: Dict[str, Any]) -> None:
    """Accumulate currency-neutral figures for one trade into a breakdown bucket."""
    stats["return_pct"] = stats.get("return_pct", 0.0) + float(t.get("return_contrib") or 0.0)
    pct = t.get("trade_pct")
    if pct is None:
        return
    stats["pct_n"] = stats.get("pct_n", 0) + 1
    stats["pct_sum"] = stats.get("pct_sum", 0.0) + pct
    if pct > 0:
        stats["pct_win"] = stats.get("pct_win", 0.0) + pct
    elif pct < 0:
        stats["pct_loss"] = stats.get("pct_loss", 0.0) - pct


def _pct_fields(stats: Dict[str, Any]) -> Dict[str, float]:
    n = stats.get("pct_n", 0)
    return {
        "return_pct": round(stats.get("return_pct", 0.0), 2),
        "avg_trade_pct": round(stats.get("pct_sum", 0.0) / n, 2) if n else 0.0,
        "profit_factor_pct": _pct_profit_factor(stats.get("pct_win", 0.0), stats.get("pct_loss", 0.0)),
    }


def get_overview_summary(
    trades: List[Dict[str, Any]], accounts: List[Dict[str, Any]], curves: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Currency-neutral KPIs, calendar and per-account comparison for the
    multi-account overview. Amounts in different currencies are never added
    up: every trade is measured in percent of its own account's starting
    balance (or in R), and accounts are weighted equally like the average
    line of get_account_return_curves().
    """
    rows = []
    trade_pcts = []
    pooled_r = []
    open_floating = []
    open_trades_count = 0
    day_buckets: Dict[str, Dict[str, Any]] = {}
    active_ids = {c["account_id"] for c in curves.get("accounts", [])}

    for index, account in enumerate(accounts):
        initial_balance = float(account.get("initial_balance") or 0.0)
        account_trades = [t for t in trades if t.get("account_id") == account.get("id")]
        m = calculate_trade_metrics(account_trades, initial_balance if initial_balance > 0 else 10000.0)
        closed = [t for t in account_trades if _is_closed_trade(t)]
        has_balance = initial_balance > 0
        account_r = sum(_trade_r(t, initial_balance) for t in closed)

        rows.append({
            "account_id": account.get("id"),
            "name": account.get("name") or f"Account {account.get('id')}",
            "currency": (account.get("currency") or "USD").upper(),
            "platform": account.get("platform") or "",
            "color_index": index,
            "initial_balance": initial_balance,
            "net_profit": m["net_profit"],
            "return_pct": round(m["net_profit"] / initial_balance * 100.0, 2) if has_balance else None,
            "open_pnl": m["open_pnl"],
            "open_trades_count": m["open_trades_count"],
            "floating_pct": round(m["open_pnl"] / initial_balance * 100.0, 2) if has_balance else None,
            "max_drawdown_pct": m["max_drawdown_pct"],
            "total_trades": m["total_trades"],
            "win_rate": m["win_rate"],
            "profit_factor": m["profit_factor"],
            "total_r": round(account_r, 2),
        })

        if not has_balance:
            continue
        for t in closed:
            pnl = float(t.get("net_profit") or 0.0)
            trade_pcts.append(pnl / initial_balance * 100.0)
            pooled_r.append((t.get("close_time") or t.get("open_time") or "", _trade_r(t, initial_balance)))
        if m["open_trades_count"] > 0:
            open_floating.append(m["open_pnl"] / initial_balance * 100.0)
            open_trades_count += m["open_trades_count"]

        # Equal-weighted daily return: each active account's day return / N.
        if account.get("id") in active_ids:
            for day, data in get_calendar_heatmap(account_trades, initial_balance).items():
                bucket = day_buckets.setdefault(day, {
                    "date": day, "net_profit": None, "pct_return": 0.0, "r_multiple": 0.0,
                    "trades_count": 0, "wins": 0, "losses": 0, "breakevens": 0,
                })
                bucket["pct_return"] += data["pct_return"]
                bucket["r_multiple"] += data["r_multiple"]
                for key in ("trades_count", "wins", "losses", "breakevens"):
                    bucket[key] += data[key]

    active_count = len(active_ids)
    for bucket in day_buckets.values():
        # 4 decimals so the month sum in the UI matches the average return.
        bucket["pct_return"] = round(bucket["pct_return"] / active_count, 4) if active_count else 0.0
        bucket["r_multiple"] = round(bucket["r_multiple"], 2)

    wins = [p for p in trade_pcts if p > 0]
    losses = [p for p in trade_pcts if p < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss > 0:
        profit_factor = round(gross_win / gross_loss, 2)
    else:
        profit_factor = 999.0 if gross_win > 0 else 0.0
    avg_win = gross_win / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0

    # Sharpe from the equal-weighted daily returns (same series as the calendar).
    sharpe = _annualized_daily_sharpe({day: b["pct_return"] for day, b in day_buckets.items()})

    # Drawdown of the equal-weighted average curve, as % of its equity peak.
    peak_equity = 1.0
    equity = 1.0
    max_dd = 0.0
    for point in curves.get("average", []):
        equity = 1.0 + point["pct"] / 100.0
        peak_equity = max(peak_equity, equity)
        if peak_equity > 0:
            max_dd = max(max_dd, (peak_equity - equity) / peak_equity * 100.0)
    current_dd = (peak_equity - equity) / peak_equity * 100.0 if peak_equity > 0 else 0.0

    cum_r = 0.0
    peak_r = 0.0
    for _, r_val in sorted(pooled_r, key=lambda item: item[0]):
        cum_r += r_val
        peak_r = max(peak_r, cum_r)

    return {
        "active_accounts": active_count,
        "avg_return_pct": curves.get("average_return_pct", 0.0),
        "avg_floating_pct": round(sum(open_floating) / len(open_floating), 2) if open_floating else 0.0,
        "open_trades_count": open_trades_count,
        "open_accounts_count": len(open_floating),
        "profit_factor": profit_factor,
        "gross_win_pct": round(gross_win, 2),
        "gross_loss_pct": round(gross_loss, 2),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "win_loss_ratio": round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0,
        "expectancy_pct": round(sum(trade_pcts) / len(trade_pcts), 2) if trade_pcts else 0.0,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": round(max_dd, 2),
        "current_drawdown_pct": round(max(0.0, current_dd), 2),
        "total_r": round(cum_r, 2),
        "current_drawdown_r": round(max(0.0, peak_r - cum_r), 2),
        "calendar": day_buckets,
        "accounts": rows,
    }

def get_performance_by_day_of_week(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Performance breakdown by Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday."""
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    buckets = {i: {"day": day_names[i], "day_num": i, "trades": 0, "wins": 0, "losses": 0, "net_profit": 0.0} for i in range(7)}
    closed_trades = [t for t in trades if not t.get("is_missed") and (t.get("status") in ("CLOSED", "WIN", "LOSS", "BE") or (t.get("status") not in ("CANCELLED", "PENDING", "OPEN") and t.get("close_time")))]

    for t in closed_trades:
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
            _add_pct(buckets[w], t)
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
            "net_profit": round(b["net_profit"], 2),
            "return_pct": round(b.get("return_pct", 0.0), 2)
        })

    return result

def get_performance_by_hour(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Performance breakdown by hour of day (00:00 - 23:00) to find best trading sessions."""
    hours = {h: {"hour": f"{h:02d}:00", "trades": 0, "wins": 0, "losses": 0, "net_profit": 0.0} for h in range(24)}
    closed_trades = [t for t in trades if not t.get("is_missed") and (t.get("status") in ("CLOSED", "WIN", "LOSS", "BE") or (t.get("status") not in ("CANCELLED", "PENDING", "OPEN") and t.get("close_time")))]

    for t in closed_trades:
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
            _add_pct(hours[h], t)
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
            "net_profit": round(b["net_profit"], 2),
            "return_pct": round(b.get("return_pct", 0.0), 2)
        })

    return result

def get_performance_by_symbol(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Performance breakdown per symbol/ticker."""
    symbols = {}
    closed_trades = [t for t in trades if not t.get("is_missed") and (t.get("status") in ("CLOSED", "WIN", "LOSS", "BE") or (t.get("status") not in ("CANCELLED", "PENDING", "OPEN") and t.get("close_time")))]

    for t in closed_trades:
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
        _add_pct(symbols[sym], t)

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
            "avg_trade": round(data["net_profit"] / tr, 2) if tr > 0 else 0.0,
            **_pct_fields(data)
        })

    # Sort by highest net profit
    result.sort(key=lambda x: x["net_profit"], reverse=True)
    return result

def get_performance_by_setup(trades: List[Dict[str, Any]], playbooks: Dict[int, str]) -> List[Dict[str, Any]]:
    """Performance breakdown per playbook setup."""
    stats = {}
    closed_trades = [t for t in trades if not t.get("is_missed") and (t.get("status") in ("CLOSED", "WIN", "LOSS", "BE") or (t.get("status") not in ("CANCELLED", "PENDING", "OPEN") and t.get("close_time")))]

    for t in closed_trades:
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
        _add_pct(stats[setup_name], t)

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
            "avg_trade": round(data["net_profit"] / tr, 2) if tr > 0 else 0.0,
            **_pct_fields(data)
        })

    result.sort(key=lambda x: x["net_profit"], reverse=True)
    return result

def get_cost_of_mistakes(trades: List[Dict[str, Any]], mistakes_map: Dict[int, str]) -> List[Dict[str, Any]]:
    """Calculates exactly how much money each mistake has cost the trader."""
    stats = {}
    # Match /api/mistakes: only realized, non-missed trades have a cost.
    closed_trades = [
        t for t in trades
        if not t.get("is_missed")
        and t.get("status") not in ("CANCELLED", "PENDING")
        and (t.get("status") in ("CLOSED", "WIN", "LOSS", "BE") or t.get("close_time"))
    ]

    for t in closed_trades:
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
                "worst_loss": 0.0,
                # Currency-neutral: share of the average return / % of own account.
                "total_loss_pct": 0.0,
                "worst_loss_pct": 0.0,
                "loss_pct_sum": 0.0
            }

        stats[mistake_name]["count"] += 1
        if pnl < 0:
            stats[mistake_name]["total_loss"] += abs(pnl)
            if abs(pnl) > stats[mistake_name]["worst_loss"]:
                stats[mistake_name]["worst_loss"] = abs(pnl)
            stats[mistake_name]["total_loss_pct"] += abs(float(t.get("return_contrib") or 0.0))
            if t.get("trade_pct") is not None:
                loss_pct = abs(t["trade_pct"])
                stats[mistake_name]["loss_pct_sum"] += loss_pct
                stats[mistake_name]["worst_loss_pct"] = max(stats[mistake_name]["worst_loss_pct"], loss_pct)

    result = []
    for name, data in stats.items():
        result.append({
            "mistake_name": name,
            "count": data["count"],
            "total_loss": round(data["total_loss"], 2),
            "worst_loss": round(data["worst_loss"], 2),
            "avg_loss": round(data["total_loss"] / data["count"], 2) if data["count"] > 0 else 0.0,
            "total_loss_pct": round(data["total_loss_pct"], 2),
            "worst_loss_pct": round(data["worst_loss_pct"], 2),
            "avg_loss_pct": round(data["loss_pct_sum"] / data["count"], 2) if data["count"] > 0 else 0.0
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
                "return_pct": round(sum(float(t.get("return_contrib") or 0.0) for t in matching), 2),
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
                b["return_pct"] = b.get("return_pct", 0.0) + float(t.get("return_contrib") or 0.0)
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
                "return_pct": round(b.get("return_pct", 0.0), 2),
                "total_r": round(b["r_sum"], 2),
                "avg_r": avg_r
            })
        res.sort(key=lambda x: x["win_rate"], reverse=True)
        return res

    return {
        "emotion_pre": analyze_field("emotion_pre"),
        "emotion_during": analyze_field("emotion_during")
    }

def get_weekly_review(trades: List[Dict[str, Any]], week_offset: int = 0, rank_by_pct: bool = False) -> Dict[str, Any]:
    """
    Generates an automated weekly review with KPIs, best/worst trade, and emotional patterns.

    With trades annotated by attach_trade_returns() it also reports the
    week's equal-weighted return in %. rank_by_pct picks best/worst trade by
    % of their own account instead of by amount (needed across currencies).
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
    open_week_trades = [t for t in active_week_trades if t.get("status") == "OPEN" and not t.get("close_time")]
    open_net = sum(float(t.get("net_profit") or 0.0) for t in open_week_trades)
    open_trades_count = len(open_week_trades)

    wins = [t for t in closed_week_trades if float(t.get("net_profit") or 0.0) > 0.001 or t.get("status") == "WIN"]
    losses = [t for t in closed_week_trades if float(t.get("net_profit") or 0.0) < -0.001 or t.get("status") == "LOSS"]
    bes = [t for t in closed_week_trades if t not in wins and t not in losses]

    total_net = sum(float(t.get("net_profit") or 0.0) for t in closed_week_trades)
    r_vals = [float(t["r_multiple"]) for t in closed_week_trades if t.get("r_multiple") is not None]
    total_r = round(sum(r_vals), 2)

    # Equal-weighted week return across the accounts that closed trades.
    pct_closed = [t for t in closed_week_trades if t.get("trade_pct") is not None]
    week_accounts = {t.get("account_id") for t in pct_closed}
    week_return_pct = sum(t["trade_pct"] for t in pct_closed) / len(week_accounts) if week_accounts else 0.0
    open_by_account: Dict[Any, float] = {}
    for t in open_week_trades:
        if t.get("trade_pct") is not None:
            open_by_account[t.get("account_id")] = open_by_account.get(t.get("account_id"), 0.0) + t["trade_pct"]
    open_return_pct = sum(open_by_account.values()) / len(open_by_account) if open_by_account else 0.0

    def performance(trade: Dict[str, Any]) -> float:
        if rank_by_pct and trade.get("trade_pct") is not None:
            return float(trade["trade_pct"])
        return float(trade.get("net_profit") or 0.0)

    win_rate = round((len(wins) / len(closed_week_trades)) * 100.0, 1) if closed_week_trades else 0.0

    best_trade = None
    worst_trade = None
    if closed_week_trades:
        sorted_by_perf = sorted(closed_week_trades, key=performance)
        # Only a winner can be the best trade and only a loser the worst one;
        # otherwise a losing week shows its smallest loss as "Best Trade".
        if performance(sorted_by_perf[0]) < -0.001:
            worst_trade = sorted_by_perf[0]
        if performance(sorted_by_perf[-1]) > 0.001:
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
        "missing_r_count": missing_r_count,
        "open_trades_count": open_trades_count,
        "open_pnl": round(open_net, 2),
        "total_pnl": round(total_net + open_net, 2),
        "return_pct": round(week_return_pct, 2),
        "open_return_pct": round(open_return_pct, 2),
        "return_accounts": len(week_accounts),
    }


R_DISTRIBUTION_BUCKETS = [
    ("≤ -2R", None, -2.0), ("-2R to -1R", -2.0, -1.0), ("-1R to 0R", -1.0, 0.0),
    ("0R to 1R", 0.0, 1.0), ("1R to 2R", 1.0, 2.0), ("2R to 3R", 2.0, 3.0), ("≥ 3R", 3.0, None),
]


def _is_realized(t: Dict[str, Any]) -> bool:
    return not t.get("is_missed") and t.get("status") in ("CLOSED", "WIN", "LOSS", "BE")


def _parse_trade_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(_normalize_date_str(value)[:19].replace("T", " "))
    except ValueError:
        return None


def _journal_score(metrics: Dict[str, Any], green_day_rate: float, plan_rate: float) -> Dict[str, Any]:
    """Transparent 0-100 score: the mean of six clamped component scores."""
    def clamp(value: float) -> float:
        return max(0.0, min(100.0, value))

    pf = float(metrics.get("profit_factor") or 0.0)
    components = [
        {"key": "win_rate", "label": "Win rate", "hint": "60 % win rate = 100",
         "score": clamp(float(metrics.get("win_rate") or 0.0) / 60.0 * 100.0)},
        {"key": "profit_factor", "label": "Profit factor", "hint": "1.0 = 0, 2.5 or more = 100",
         "score": clamp((pf - 1.0) / 1.5 * 100.0)},
        {"key": "win_loss_ratio", "label": "Avg win / avg loss", "hint": "2 : 1 or more = 100",
         "score": clamp(float(metrics.get("win_loss_ratio") or 0.0) / 2.0 * 100.0)},
        {"key": "drawdown", "label": "Max drawdown", "hint": "0 % = 100, 20 % or more = 0",
         "score": clamp(100.0 - float(metrics.get("max_drawdown_pct") or 0.0) * 5.0)},
        {"key": "consistency", "label": "Green days", "hint": "70 % green days = 100",
         "score": clamp(green_day_rate / 70.0 * 100.0)},
        {"key": "discipline", "label": "Plan followed", "hint": "Trades with a setup and no tagged mistake",
         "score": clamp(plan_rate)},
    ]
    for c in components:
        c["score"] = round(c["score"], 1)
    total = round(sum(c["score"] for c in components) / len(components), 1) if metrics.get("total_trades") else 0.0
    return {"score": total, "components": components}


def get_dashboard_insights(trades: List[Dict[str, Any]], metrics: Dict[str, Any], recent_limit: int = 8,
                           initial_balance: float = 10000.0) -> Dict[str, Any]:
    """Deterministic breakdowns for the dashboard beyond the headline KPIs."""
    closed = [t for t in trades if _is_realized(t)]
    events = get_realized_events(trades, initial_balance)

    def pnl(t):
        return float(t.get("net_profit") or 0.0)

    # R-multiple distribution
    r_values = [float(t["r_multiple"]) for t in closed if t.get("r_multiple") is not None]
    r_distribution = [
        {"label": label, "positive": low is not None and low >= 0,
         "count": sum(1 for r in r_values if (low is None or r >= low) and (high is None or r < high))}
        for label, low, high in R_DISTRIBUTION_BUCKETS
    ]

    # Long vs short
    long_short = {}
    for key, sides in (("long", ("BUY", "LONG")), ("short", ("SELL", "SHORT"))):
        side_trades = [t for t in closed if (t.get("direction") or "").upper() in sides]
        wins = sum(1 for t in side_trades if pnl(t) > 0.001)
        side_r = [float(t["r_multiple"]) for t in side_trades if t.get("r_multiple") is not None]
        long_short[key] = {
            "trades": len(side_trades),
            "wins": wins,
            "win_rate": round(wins / len(side_trades) * 100.0, 1) if side_trades else 0.0,
            "net_profit": round(sum(pnl(t) for t in side_trades), 2),
            "avg_r": round(sum(side_r) / len(side_r), 2) if side_r else None,
        }

    # Holding time of winners vs losers (minutes)
    def avg_hold(selected):
        durations = []
        for t in selected:
            start, end = _parse_trade_dt(t.get("open_time")), _parse_trade_dt(t.get("close_time"))
            if start and end and end >= start:
                durations.append((end - start).total_seconds() / 60.0)
        return round(sum(durations) / len(durations), 1) if durations else None

    holding = {
        "winners_min": avg_hold([t for t in closed if pnl(t) > 0.001]),
        "losers_min": avg_hold([t for t in closed if pnl(t) < -0.001]),
        "all_min": avg_hold(closed),
    }

    # Day-level statistics on realized P&L (same basis as the calendar)
    days: Dict[str, float] = {}
    for e in events:
        days[e["time"][:10]] = days.get(e["time"][:10], 0.0) + e["pnl"]
    green = sum(1 for v in days.values() if v > 0.001)
    red = sum(1 for v in days.values() if v < -0.001)
    best_day = max(days.items(), key=lambda kv: kv[1]) if days else None
    worst_day = min(days.items(), key=lambda kv: kv[1]) if days else None
    day_stats = {
        "trading_days": len(days),
        "green_days": green,
        "red_days": red,
        "green_day_rate": round(green / len(days) * 100.0, 1) if days else 0.0,
        "avg_daily_pnl": round(sum(days.values()) / len(days), 2) if days else 0.0,
        "best_day": {"date": best_day[0], "net_profit": round(best_day[1], 2)} if best_day else None,
        "worst_day": {"date": worst_day[0], "net_profit": round(worst_day[1], 2)} if worst_day else None,
    }

    # Monthly results: realized P&L and R by realization date; trades and win
    # rate count the trades that were fully closed in that month.
    months: Dict[str, Dict[str, float]] = {}
    for e in events:
        m = months.setdefault(e["time"][:7], {"net_profit": 0.0, "trades": 0, "wins": 0, "r": 0.0})
        m["net_profit"] += e["pnl"]
        m["r"] += e["r"]
    for t in closed:
        key = _normalize_date_str(t.get("close_time") or t.get("open_time") or "")[:7]
        if not key:
            continue
        m = months.setdefault(key, {"net_profit": 0.0, "trades": 0, "wins": 0, "r": 0.0})
        m["trades"] += 1
        m["wins"] += 1 if pnl(t) > 0.001 else 0
    monthly = [
        {"month": key, "net_profit": round(m["net_profit"], 2), "trades": m["trades"],
         "win_rate": round(m["wins"] / m["trades"] * 100.0, 1) if m["trades"] else 0.0,
         "total_r": round(m["r"], 2)}
        for key, m in sorted(months.items())
    ]

    by_symbol = get_performance_by_symbol(trades)  # sorted by net profit, best first

    # Plan adherence: a setup was assigned and no mistake was tagged
    plan_followed = sum(1 for t in closed if t.get("setup_id") and not t.get("mistake_id"))
    plan_rate = plan_followed / len(closed) * 100.0 if closed else 0.0

    weekdays = get_performance_by_day_of_week(trades)
    recent = sorted(closed, key=lambda t: _normalize_date_str(t.get("close_time") or t.get("open_time") or ""), reverse=True)
    open_positions = [t for t in trades if t.get("status") == "OPEN" and not t.get("is_missed")]

    def trade_summary(t):
        return {
            "id": t.get("id"), "symbol": t.get("symbol"), "direction": t.get("direction"),
            "volume": t.get("volume"), "net_profit": round(pnl(t), 2),
            "r_multiple": t.get("r_multiple"), "status": t.get("status"),
            "open_time": t.get("open_time"), "close_time": t.get("close_time"),
            "setup_name": t.get("setup_name"), "account_currency": t.get("account_currency"),
        }

    return {
        "realized_pnl": round(sum(e["pnl"] for e in events), 2),
        "r_distribution": r_distribution,
        "long_short": long_short,
        "holding": holding,
        "day_stats": day_stats,
        "monthly": monthly,
        # Weekends only when traded, so FX-only journals keep a Mon-Fri chart.
        "by_weekday": [d for i, d in enumerate(weekdays) if i < 5 or d["trades"] > 0],
        "top_symbols": by_symbol[:5],
        "worst_symbols": [s for s in reversed(by_symbol) if s.get("net_profit", 0.0) < 0][:3],
        "plan_rate": round(plan_rate, 1),
        "journal_score": _journal_score(metrics, day_stats["green_day_rate"], plan_rate),
        "recent_trades": [trade_summary(t) for t in recent[:recent_limit]],
        "open_positions": [trade_summary(t) for t in open_positions],
    }

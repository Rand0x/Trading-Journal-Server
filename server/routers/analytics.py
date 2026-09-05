"""
Analytics Reports Router
Serves deep quantitative breakdowns: Day of week, Hour of day, Symbol, Setup, Mistakes,
Take-Profit scale-outs, Signal Combinations, Psychology, and Weekly Review.
"""

from typing import Optional
from fastapi import APIRouter, Query
from server.database import get_connection
from server.analytics import (
    get_performance_by_day_of_week,
    get_performance_by_hour,
    get_performance_by_symbol,
    get_performance_by_setup,
    get_cost_of_mistakes,
    calculate_trade_metrics,
    get_take_profit_analysis,
    get_signal_combinations,
    get_psychology_performance,
    get_weekly_review
)

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

def _fetch_filtered_trades(account_id: Optional[int], date_from: Optional[str], date_to: Optional[str]):
    with get_connection() as conn:
        cursor = conn.cursor()
        where_clauses = []
        params = []

        if account_id:
            where_clauses.append("t.account_id = ?")
            params.append(account_id)
        if date_from:
            where_clauses.append("t.open_time >= ?")
            params.append(date_from)
        if date_to:
            where_clauses.append("t.open_time <= ?")
            params.append(date_to + " 23:59:59")

        where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        cursor.execute(f"""
            SELECT t.*, p.name as setup_name, m.name as mistake_name
            FROM trades t
            LEFT JOIN playbooks p ON t.setup_id = p.id
            LEFT JOIN mistakes m ON t.mistake_id = m.id
            {where_str}
            ORDER BY t.open_time ASC;
        """, params)
        trades = [dict(r) for r in cursor.fetchall()]

        if trades:
            trade_ids = [t["id"] for t in trades]
            placeholders = ",".join("?" for _ in trade_ids)
            cursor.execute(f"""
                SELECT id, trade_id, ticket, volume, close_time, close_price,
                       commission, swap, gross_profit, net_profit
                FROM trade_partial_closes
                WHERE trade_id IN ({placeholders})
                ORDER BY close_time ASC, id ASC;
            """, trade_ids)
            partials_by_trade = {}
            for pc in cursor.fetchall():
                tid = pc["trade_id"]
                if tid not in partials_by_trade:
                    partials_by_trade[tid] = []
                partials_by_trade[tid].append(dict(pc))
            for t in trades:
                t["partial_closes"] = partials_by_trade.get(t["id"], [])
        else:
            for t in trades:
                t["partial_closes"] = []

        # Also get playbooks map
        cursor.execute("SELECT id, name FROM playbooks;")
        playbooks = {r["id"]: r["name"] for r in cursor.fetchall()}

        # Also get mistakes map
        cursor.execute("SELECT id, name FROM mistakes;")
        mistakes = {r["id"]: r["name"] for r in cursor.fetchall()}

        return trades, playbooks, mistakes

@router.get("/overview")
def get_analytics_overview(
    account_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None)
):
    trades, playbooks, mistakes = _fetch_filtered_trades(account_id, date_from, date_to)
    
    currency = "USD"
    with get_connection() as conn:
        cursor = conn.cursor()
        if account_id:
            cursor.execute("SELECT currency FROM accounts WHERE id = ?;", (account_id,))
            row = cursor.fetchone()
            if row and row["currency"]:
                currency = row["currency"]
        else:
            cursor.execute("SELECT COUNT(DISTINCT currency), MIN(currency) FROM accounts;")
            row = cursor.fetchone()
            if row and row[0] == 1 and row[1]:
                currency = row[1]

    return {
        "metrics": calculate_trade_metrics(trades),
        "currency": currency,
        "by_day_of_week": get_performance_by_day_of_week(trades),
        "by_hour": get_performance_by_hour(trades),
        "by_symbol": get_performance_by_symbol(trades),
        "by_setup": get_performance_by_setup(trades, playbooks),
        "by_mistake": get_cost_of_mistakes(trades, mistakes),
        "take_profit": get_take_profit_analysis(trades),
        "signal_combinations": get_signal_combinations(trades),
        "psychology": get_psychology_performance(trades)
    }

@router.get("/day-of-week")
def get_day_of_week_report(account_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None):
    trades, _, _ = _fetch_filtered_trades(account_id, date_from, date_to)
    return get_performance_by_day_of_week(trades)

@router.get("/hour-of-day")
def get_hour_of_day_report(account_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None):
    trades, _, _ = _fetch_filtered_trades(account_id, date_from, date_to)
    return get_performance_by_hour(trades)

@router.get("/symbol")
def get_symbol_report(account_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None):
    trades, _, _ = _fetch_filtered_trades(account_id, date_from, date_to)
    return get_performance_by_symbol(trades)

@router.get("/setup")
def get_setup_report(account_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None):
    trades, playbooks, _ = _fetch_filtered_trades(account_id, date_from, date_to)
    return get_performance_by_setup(trades, playbooks)

@router.get("/mistakes")
def get_mistakes_report(account_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None):
    trades, _, mistakes = _fetch_filtered_trades(account_id, date_from, date_to)
    return get_cost_of_mistakes(trades, mistakes)

@router.get("/take-profit")
def get_take_profit_report(account_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None):
    trades, _, _ = _fetch_filtered_trades(account_id, date_from, date_to)
    return get_take_profit_analysis(trades)

@router.get("/signal-combinations")
def get_signal_combinations_report(account_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, min_samples: int = 2):
    trades, _, _ = _fetch_filtered_trades(account_id, date_from, date_to)
    return get_signal_combinations(trades, min_samples=min_samples)

@router.get("/psychology")
def get_psychology_report(account_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None):
    trades, _, _ = _fetch_filtered_trades(account_id, date_from, date_to)
    return get_psychology_performance(trades)

@router.get("/weekly-review")
def get_weekly_review_report(
    account_id: Optional[int] = None,
    week_offset: int = Query(0, description="0 = current week, -1 = previous week, etc.")
):
    trades, _, _ = _fetch_filtered_trades(account_id, None, None)
    return get_weekly_review(trades, week_offset=week_offset)


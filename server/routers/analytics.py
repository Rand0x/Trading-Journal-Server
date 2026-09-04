"""
Analytics Reports Router
Serves deep quantitative breakdowns: Day of week, Hour of day, Symbol, Setup, and Mistakes.
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
    calculate_trade_metrics
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
        cursor.execute(f"SELECT * FROM trades t {where_str} ORDER BY t.open_time ASC;", params)
        trades = [dict(r) for r in cursor.fetchall()]

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
    
    return {
        "metrics": calculate_trade_metrics(trades),
        "by_day_of_week": get_performance_by_day_of_week(trades),
        "by_hour": get_performance_by_hour(trades),
        "by_symbol": get_performance_by_symbol(trades),
        "by_setup": get_performance_by_setup(trades, playbooks),
        "by_mistake": get_cost_of_mistakes(trades, mistakes)
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

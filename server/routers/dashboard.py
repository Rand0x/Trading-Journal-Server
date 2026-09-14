"""
Dashboard Router
Serves executive KPIs, TradeZella-style Calendar Heatmap, and Equity Curve.
"""

from typing import Optional
from fastapi import APIRouter, Query
from server.database import get_connection
from server.analytics import calculate_trade_metrics, get_calendar_heatmap, get_equity_curve

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("")
def get_dashboard_summary(
    account_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None)
):
    with get_connection() as conn:
        cursor = conn.cursor()
        
        where_clauses = []
        params = []

        if account_id:
            where_clauses.append("t.account_id = ?")
            params.append(account_id)
        if symbol:
            where_clauses.append("t.symbol = ?")
            params.append(symbol.upper())
        if date_from:
            where_clauses.append("t.open_time >= ?")
            params.append(date_from)
        if date_to:
            where_clauses.append("t.open_time <= ?")
            params.append(date_to + " 23:59:59")

        where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Fetch initial balance, current balance, equity and currency
        initial_balance = 10000.0
        current_balance = None
        equity = None
        currency = "USD"
        if account_id:
            cursor.execute("SELECT initial_balance, current_balance, equity, currency FROM accounts WHERE id = ?;", (account_id,))
            acc = cursor.fetchone()
            if acc:
                initial_balance = float(acc["initial_balance"])
                current_balance = float(acc["current_balance"]) if acc["current_balance"] is not None else initial_balance
                equity = float(acc["equity"]) if acc["equity"] is not None else initial_balance
                currency = acc["currency"] or "USD"
        else:
            cursor.execute("SELECT SUM(initial_balance), SUM(current_balance), SUM(equity), COUNT(DISTINCT currency), MIN(currency) FROM accounts;")
            row = cursor.fetchone()
            if row and row[0]:
                initial_balance = float(row[0])
            if row and row[1] is not None:
                current_balance = float(row[1])
            if row and row[2] is not None:
                equity = float(row[2])
            if row and row[3] == 1 and row[4]:
                currency = row[4]

        # Fetch trades
        cursor.execute(f"""
            SELECT t.*, a.name as account_name, a.currency as account_currency
            FROM trades t
            LEFT JOIN accounts a ON t.account_id = a.id
            {where_str}
            ORDER BY t.open_time ASC;
        """, params)
        trades = [dict(r) for r in cursor.fetchall()]

    metrics = calculate_trade_metrics(trades, initial_balance)
    calendar = get_calendar_heatmap(trades, initial_balance)
    equity_curve = get_equity_curve(trades, initial_balance)

    return {
        "metrics": metrics,
        "calendar": calendar,
        "equity_curve": equity_curve,
        "initial_balance": initial_balance,
        "current_balance": current_balance,
        "equity": equity,
        "currency": currency,
        "trades_count": len(trades),
        "open_trades_count": metrics.get("open_trades_count", 0),
        "open_pnl": metrics.get("open_pnl", 0.0),
        "total_pnl": metrics.get("total_pnl", metrics.get("net_profit", 0.0)),
    }

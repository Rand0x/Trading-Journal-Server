"""
Dashboard Router
Serves executive KPIs, TradeZella-style Calendar Heatmap, and Equity Curve.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from server.database import get_connection
from server.analytics import calculate_trade_metrics, get_calendar_heatmap, get_equity_curve, get_dashboard_insights
from server.routers.trades import _display_groups

RECENT_TRADES_LIMIT = 8


def _grouped_recent_trades(trades: List[Dict[str, Any]], limit: int = RECENT_TRADES_LIMIT) -> List[Dict[str, Any]]:
    """Latest closed positions, with sibling legs merged exactly like the trade log."""
    closed = [t for t in trades if not t.get("is_missed") and t.get("status") in ("CLOSED", "WIN", "LOSS", "BE")]
    closed.sort(key=lambda t: (t.get("close_time") or t.get("open_time") or "", t.get("id") or 0), reverse=True)
    result = []
    for legs in _display_groups(closed)[:limit]:
        primary = min(legs, key=lambda t: t.get("id") or 0)
        volume = sum(float(t.get("volume") or 0.0) for t in legs)
        net = sum(float(t.get("net_profit") or 0.0) for t in legs)
        r_legs = [(float(t["r_multiple"]), float(t.get("volume") or 0.0)) for t in legs if t.get("r_multiple") is not None]
        r_volume = sum(v for _, v in r_legs)
        # Volume-weighted R, the same figure the trade log shows for a grouped row
        r_multiple = round(sum(r * v for r, v in r_legs) / r_volume, 2) if r_volume > 0 else None
        result.append({
            "id": primary.get("id"),
            "symbol": primary.get("symbol"),
            "direction": primary.get("direction"),
            "volume": round(volume, 4),
            "net_profit": round(net, 2),
            "r_multiple": r_multiple,
            "status": "WIN" if net > 0.001 else ("LOSS" if net < -0.001 else "BE"),
            "open_time": min(t.get("open_time") or "" for t in legs),
            "close_time": max(t.get("close_time") or "" for t in legs),
            "setup_name": next((t.get("setup_name") for t in legs if t.get("setup_name")), None),
            "account_currency": primary.get("account_currency"),
            "legs": len(legs),
        })
    return result

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
        currencies = []
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
            cursor.execute("SELECT DISTINCT UPPER(COALESCE(NULLIF(currency, ''), 'USD')) FROM accounts ORDER BY 1;")
            currencies = [r[0] for r in cursor.fetchall()]

        # Fetch trades
        cursor.execute(f"""
            SELECT t.*, a.name as account_name, a.currency as account_currency, p.name as setup_name
            FROM trades t
            LEFT JOIN accounts a ON t.account_id = a.id
            LEFT JOIN playbooks p ON t.setup_id = p.id
            {where_str}
            ORDER BY t.open_time ASC;
        """, params)
        trades = [dict(r) for r in cursor.fetchall()]

        # Partial exits are realized on their own dates (calendar, equity curve).
        partials_by_trade: Dict[int, List[Dict[str, Any]]] = {}
        if trades:
            placeholders = ",".join("?" for _ in trades)
            cursor.execute(f"""
                SELECT trade_id, ticket, volume, close_time, close_price, net_profit
                FROM trade_partial_closes
                WHERE trade_id IN ({placeholders})
                ORDER BY close_time ASC, id ASC;
            """, [t["id"] for t in trades])
            for pc in cursor.fetchall():
                partials_by_trade.setdefault(pc["trade_id"], []).append(dict(pc))
        for t in trades:
            t["partial_closes"] = partials_by_trade.get(t["id"], [])

    metrics = calculate_trade_metrics(trades, initial_balance)
    calendar = get_calendar_heatmap(trades, initial_balance)
    equity_curve = get_equity_curve(trades, initial_balance)
    insights = get_dashboard_insights(trades, metrics, initial_balance=initial_balance)
    insights["recent_trades"] = _grouped_recent_trades(trades)

    return {
        "metrics": metrics,
        "calendar": calendar,
        "equity_curve": equity_curve,
        "insights": insights,
        "initial_balance": initial_balance,
        "current_balance": current_balance,
        "equity": equity,
        "currency": currency,
        # Amounts of accounts in different currencies are summed without FX conversion.
        "mixed_currencies": len(currencies) > 1,
        "currencies": currencies,
        "trades_count": len(trades),
        "open_trades_count": metrics.get("open_trades_count", 0),
        "open_pnl": metrics.get("open_pnl", 0.0),
        "total_pnl": metrics.get("total_pnl", metrics.get("net_profit", 0.0)),
    }

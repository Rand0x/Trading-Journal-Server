"""
Trades Router
Full trade log management, filtering, searching, editing, and CSV/JSON export.
"""

import io
import csv
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Response
from server.database import get_connection
from server.models import TradeCreate, TradeUpdate, TradeResponse

router = APIRouter(prefix="/api/trades", tags=["Trades"])

@router.get("")
def get_trades(
    account_id: Optional[int] = Query(None),
    symbol: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    setup_id: Optional[int] = Query(None),
    mistake_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: str = Query("open_time"),
    sort_order: str = Query("desc"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0)
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
        if direction:
            where_clauses.append("t.direction = ?")
            params.append(direction.upper())
        if status:
            where_clauses.append("t.status = ?")
            params.append(status.upper())
        if setup_id:
            where_clauses.append("t.setup_id = ?")
            params.append(setup_id)
        if mistake_id:
            where_clauses.append("t.mistake_id = ?")
            params.append(mistake_id)
        if date_from:
            where_clauses.append("t.open_time >= ?")
            params.append(date_from)
        if date_to:
            where_clauses.append("t.open_time <= ?")
            params.append(date_to + " 23:59:59")
        if search:
            where_clauses.append("(t.symbol LIKE ? OR t.notes LIKE ? OR t.tags LIKE ? OR t.ticket LIKE ?)")
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param, search_param])

        where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Validate sorting column
        allowed_sorts = {
            "open_time": "t.open_time",
            "close_time": "t.close_time",
            "net_profit": "t.net_profit",
            "volume": "t.volume",
            "symbol": "t.symbol",
            "id": "t.id"
        }
        order_col = allowed_sorts.get(sort_by, "t.open_time")
        order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"

        # Count total
        cursor.execute(f"SELECT COUNT(*) FROM trades t {where_str};", params)
        total_count = cursor.fetchone()[0]

        # Fetch records
        query = f"""
            SELECT t.*, a.name as account_name, p.name as setup_name, m.name as mistake_name
            FROM trades t
            LEFT JOIN accounts a ON t.account_id = a.id
            LEFT JOIN playbooks p ON t.setup_id = p.id
            LEFT JOIN mistakes m ON t.mistake_id = m.id
            {where_str}
            ORDER BY {order_col} {order_dir}
            LIMIT ? OFFSET ?;
        """
        cursor.execute(query, params + [limit, offset])
        trades = [dict(r) for r in cursor.fetchall()]

        return {
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "trades": trades
        }

@router.get("/{trade_id}")
def get_trade(trade_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.*, a.name as account_name, a.currency as account_currency,
                   p.name as setup_name, m.name as mistake_name
            FROM trades t
            LEFT JOIN accounts a ON t.account_id = a.id
            LEFT JOIN playbooks p ON t.setup_id = p.id
            LEFT JOIN mistakes m ON t.mistake_id = m.id
            WHERE t.id = ?;
        """, (trade_id,))
        trade = cursor.fetchone()
        if not trade:
            raise HTTPException(status_code=404, detail="Trade not found")
        return dict(trade)

@router.post("")
def create_trade(trade: TradeCreate):
    now_str = datetime.now(timezone.utc).isoformat()
    pnl = trade.net_profit or 0.0
    status = trade.status or ("WIN" if pnl > 0.001 else ("LOSS" if pnl < -0.001 else "BE"))
    
    with get_connection() as conn:
        cursor = conn.cursor()
        ticket = trade.ticket or f"manual_{int(datetime.now().timestamp())}"
        cursor.execute("""
            INSERT INTO trades (
                account_id, ticket, symbol, direction, volume,
                open_time, close_time, open_price, close_price,
                stop_loss, take_profit, commission, swap,
                gross_profit, net_profit, pnl_percent, status,
                setup_id, mistake_id, notes, emotions, rating,
                tags, timeframe, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            trade.account_id, ticket, trade.symbol.upper(), trade.direction.upper(),
            trade.volume, trade.open_time, trade.close_time or trade.open_time,
            trade.open_price, trade.close_price or trade.open_price,
            trade.stop_loss, trade.take_profit, trade.commission or 0.0, trade.swap or 0.0,
            trade.gross_profit or pnl, pnl, trade.pnl_percent or 0.0, status,
            trade.setup_id, trade.mistake_id, trade.notes or "",
            trade.emotions or "Disciplined", trade.rating or 5,
            trade.tags or "", trade.timeframe or "M15",
            now_str, now_str
        ))
        trade_id = cursor.lastrowid
        conn.commit()

        cursor.execute("SELECT * FROM trades WHERE id = ?;", (trade_id,))
        return dict(cursor.fetchone())

@router.put("/{trade_id}")
def update_trade(trade_id: int, trade: TradeUpdate):
    now_str = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE id = ?;", (trade_id,))
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Trade not found")

        updates = []
        values = []
        for field, val in trade.model_dump(exclude_unset=True).items():
            updates.append(f"{field} = ?")
            values.append(val)

        if updates:
            updates.append("updated_at = ?")
            values.append(now_str)
            values.append(trade_id)
            cursor.execute(f"UPDATE trades SET {', '.join(updates)} WHERE id = ?;", values)
            conn.commit()

        cursor.execute("""
            SELECT t.*, a.name as account_name, p.name as setup_name, m.name as mistake_name
            FROM trades t
            LEFT JOIN accounts a ON t.account_id = a.id
            LEFT JOIN playbooks p ON t.setup_id = p.id
            LEFT JOIN mistakes m ON t.mistake_id = m.id
            WHERE t.id = ?;
        """, (trade_id,))
        return dict(cursor.fetchone())

@router.delete("/{trade_id}")
def delete_trade(trade_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM trades WHERE id = ?;", (trade_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Trade not found")
        conn.commit()
    return {"message": "Trade deleted successfully"}

@router.get("/export/csv")
def export_csv(account_id: Optional[int] = None):
    """Exports all trades in standard TradeZella CSV format."""
    with get_connection() as conn:
        cursor = conn.cursor()
        where_clause = "WHERE t.account_id = ?" if account_id else ""
        params = [account_id] if account_id else []
        cursor.execute(f"""
            SELECT t.id, t.ticket, a.name as account_name, t.symbol, t.direction, t.volume,
                   t.open_time, t.close_time, t.open_price, t.close_price, t.stop_loss, t.take_profit,
                   t.commission, t.swap, t.net_profit, t.status, p.name as setup, m.name as mistake,
                   t.emotions, t.rating, t.notes
            FROM trades t
            LEFT JOIN accounts a ON t.account_id = a.id
            LEFT JOIN playbooks p ON t.setup_id = p.id
            LEFT JOIN mistakes m ON t.mistake_id = m.id
            {where_clause}
            ORDER BY t.open_time DESC;
        """, params)
        rows = cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Trade ID", "Ticket", "Account", "Symbol", "Direction", "Volume",
        "Open Time", "Close Time", "Open Price", "Close Price", "Stop Loss", "Take Profit",
        "Commission", "Swap", "Net P&L", "Status", "Setup / Playbook", "Mistake",
        "Emotion", "Rating", "Notes"
    ])
    for r in rows:
        writer.writerow(list(r))

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=trading_journal_export.csv"}
    )

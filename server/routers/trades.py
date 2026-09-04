"""
Trades Router
Full trade log management, filtering, searching, editing, and CSV/JSON export.
"""

import io
import csv
import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Response
from server.database import get_connection
from server.models import (
    TradeCreate, TradeUpdate, TradeResponse, TradePartialCloseCreate,
    TradeScreenshotCreate
)

router = APIRouter(prefix="/api/trades", tags=["Trades"])

def _get_trade_with_partials(cursor, trade_id: int):
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
        return None

    result = dict(trade)
    cursor.execute("""
        SELECT id, trade_id, ticket, volume, close_time, close_price,
               commission, swap, gross_profit, net_profit, created_at, updated_at
        FROM trade_partial_closes
        WHERE trade_id = ?
        ORDER BY close_time ASC, id ASC;
    """, (trade_id,))
    result["partial_closes"] = [dict(row) for row in cursor.fetchall()]
    cursor.execute("""
        SELECT id, trade_id, source_url, image_url, caption, created_at
        FROM trade_screenshots
        WHERE trade_id = ?
        ORDER BY created_at ASC, id ASC;
    """, (trade_id,))
    result["screenshots"] = [dict(row) for row in cursor.fetchall()]
    return result

def _tradingview_image_url(source_url: str) -> Optional[str]:
    match = re.match(
        r"^https?://(?:www\.)?tradingview\.com/x/([A-Za-z0-9]+)/?$",
        source_url.strip(),
        flags=re.IGNORECASE
    )
    if not match:
        return None
    pattern = match.group(1)
    return f"https://s3.tradingview.com/snapshots/{pattern[0].lower()}/{pattern}.png"

def _validate_http_url(value: str, field_name: str) -> str:
    value = value.strip()
    if not re.match(r"^https?://[^\s]+$", value, flags=re.IGNORECASE):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a valid http(s) URL")
    return value

def _partial_values(partial: TradePartialCloseCreate):
    commission = partial.commission if partial.commission is not None else 0.0
    swap = partial.swap if partial.swap is not None else 0.0
    net_profit = partial.net_profit if partial.net_profit is not None else 0.0
    gross_profit = partial.gross_profit if partial.gross_profit is not None else net_profit - commission - swap
    return commission, swap, gross_profit, net_profit

def _recalculate_trade_from_partials(cursor, trade_id: int):
    cursor.execute("SELECT volume FROM trades WHERE id = ?;", (trade_id,))
    parent = cursor.fetchone()
    if not parent:
        raise HTTPException(status_code=404, detail="Trade not found")

    cursor.execute("""
        SELECT volume, close_time, close_price, commission, swap, gross_profit, net_profit
        FROM trade_partial_closes
        WHERE trade_id = ?
        ORDER BY close_time ASC, id ASC;
    """, (trade_id,))
    partials = cursor.fetchall()
    total_volume = sum(float(row["volume"] or 0.0) for row in partials)
    original_volume = float(parent["volume"] or 0.0)
    if total_volume > original_volume + 1e-9:
        raise HTTPException(status_code=400, detail="Partial close volume cannot exceed the original trade volume")

    now_str = datetime.now(timezone.utc).isoformat()
    if not partials:
        cursor.execute("""
            UPDATE trades
            SET close_time = NULL, close_price = NULL,
                commission = 0.0, swap = 0.0, gross_profit = 0.0,
                net_profit = 0.0, status = 'OPEN', updated_at = ?
            WHERE id = ?;
        """, (now_str, trade_id))
        return

    total_commission = sum(float(row["commission"] or 0.0) for row in partials)
    total_swap = sum(float(row["swap"] or 0.0) for row in partials)
    total_gross = sum(float(row["gross_profit"] or 0.0) for row in partials)
    total_net = sum(float(row["net_profit"] or 0.0) for row in partials)
    weighted_close_price = sum(float(row["volume"]) * float(row["close_price"]) for row in partials) / total_volume
    last_close_time = partials[-1]["close_time"]
    is_complete = total_volume >= original_volume - 1e-9
    status = "WIN" if total_net > 0.001 else ("LOSS" if total_net < -0.001 else "BE")
    if not is_complete:
        status = "OPEN"

    cursor.execute("""
        UPDATE trades
        SET close_time = ?, close_price = ?, commission = ?, swap = ?,
            gross_profit = ?, net_profit = ?, status = ?, updated_at = ?
        WHERE id = ?;
    """, (
        last_close_time, weighted_close_price, total_commission, total_swap,
        total_gross, total_net, status, now_str, trade_id
    ))

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
            SELECT t.*, a.name as account_name, p.name as setup_name, m.name as mistake_name,
                   (SELECT COUNT(*) FROM trade_partial_closes pc WHERE pc.trade_id = t.id) AS partial_close_count,
                   (SELECT COUNT(*) FROM trade_screenshots ts WHERE ts.trade_id = t.id) AS screenshot_count
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
        trade = _get_trade_with_partials(cursor, trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail="Trade not found")
        return trade

@router.post("")
def create_trade(trade: TradeCreate):
    now_str = datetime.now(timezone.utc).isoformat()
    partial_closes = trade.partial_closes or []
    commission = trade.commission if trade.commission is not None else 0.0
    swap = trade.swap if trade.swap is not None else 0.0
    pnl = trade.net_profit if trade.net_profit is not None else 0.0
    gross_profit = trade.gross_profit if trade.gross_profit is not None else pnl

    if partial_closes:
        partial_volume = sum(partial.volume for partial in partial_closes)
        if partial_volume > trade.volume + 1e-9:
            raise HTTPException(status_code=400, detail="Partial close volume cannot exceed the original trade volume")
        commission = sum(_partial_values(partial)[0] for partial in partial_closes)
        swap = sum(_partial_values(partial)[1] for partial in partial_closes)
        gross_profit = sum(_partial_values(partial)[2] for partial in partial_closes)
        pnl = sum(_partial_values(partial)[3] for partial in partial_closes)
        close_time = max(partial.close_time for partial in partial_closes)
        close_price = sum(partial.volume * partial.close_price for partial in partial_closes) / partial_volume
        status = "WIN" if pnl > 0.001 else ("LOSS" if pnl < -0.001 else "BE")
        if partial_volume < trade.volume - 1e-9:
            status = "OPEN"
    else:
        close_time = trade.close_time
        close_price = trade.close_price
        status = trade.status
        if status is None:
            status = "OPEN" if close_time is None else ("WIN" if pnl > 0.001 else ("LOSS" if pnl < -0.001 else "BE"))
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM accounts WHERE id = ?;", (trade.account_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Account not found")

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
            trade.volume, trade.open_time, close_time,
            trade.open_price, close_price,
            trade.stop_loss, trade.take_profit,
            commission,
            swap,
            gross_profit,
            pnl, trade.pnl_percent if trade.pnl_percent is not None else 0.0, status,
            trade.setup_id, trade.mistake_id, trade.notes or "",
            trade.emotions or "Disciplined", trade.rating if trade.rating is not None else 5,
            trade.tags or "", trade.timeframe or "M15",
            now_str, now_str
        ))
        trade_id = cursor.lastrowid

        for index, partial in enumerate(partial_closes, start=1):
            partial_ticket = partial.ticket or f"manual_partial_{trade_id}_{index}"
            partial_commission, partial_swap, partial_gross, partial_net = _partial_values(partial)
            cursor.execute("""
                INSERT INTO trade_partial_closes (
                    trade_id, ticket, volume, close_time, close_price,
                    commission, swap, gross_profit, net_profit, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                trade_id, partial_ticket, partial.volume, partial.close_time,
                partial.close_price, partial_commission, partial_swap,
                partial_gross, partial_net, now_str, now_str
            ))

        conn.commit()

        return _get_trade_with_partials(cursor, trade_id)

@router.put("/{trade_id}")
def update_trade(trade_id: int, trade: TradeUpdate):
    now_str = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE id = ?;", (trade_id,))
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Trade not found")

        changes = trade.model_dump(exclude_unset=True)
        if "net_profit" in changes and "status" not in changes:
            pnl = changes["net_profit"] or 0.0
            changes["status"] = "WIN" if pnl > 0.001 else ("LOSS" if pnl < -0.001 else "BE")

        updates = []
        values = []
        for field, val in changes.items():
            updates.append(f"{field} = ?")
            values.append(val.upper() if field in ("symbol", "direction") and isinstance(val, str) else val)

        if updates:
            updates.append("updated_at = ?")
            values.append(now_str)
            values.append(trade_id)
            cursor.execute(f"UPDATE trades SET {', '.join(updates)} WHERE id = ?;", values)
        cursor.execute("SELECT COUNT(*) AS count FROM trade_partial_closes WHERE trade_id = ?;", (trade_id,))
        if cursor.fetchone()["count"] > 0:
            _recalculate_trade_from_partials(cursor, trade_id)
        conn.commit()

        return _get_trade_with_partials(cursor, trade_id)

@router.post("/{trade_id}/partials")
def add_partial_close(trade_id: int, partial: TradePartialCloseCreate):
    """Add one partial exit to a parent trade and refresh its aggregate values."""
    now_str = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT volume FROM trades WHERE id = ?;", (trade_id,))
        parent = cursor.fetchone()
        if not parent:
            raise HTTPException(status_code=404, detail="Trade not found")

        cursor.execute("SELECT COALESCE(SUM(volume), 0.0) AS volume FROM trade_partial_closes WHERE trade_id = ?;", (trade_id,))
        existing_volume = float(cursor.fetchone()["volume"] or 0.0)
        if existing_volume + partial.volume > float(parent["volume"]) + 1e-9:
            raise HTTPException(status_code=400, detail="Partial close volume cannot exceed the original trade volume")

        partial_ticket = partial.ticket or f"manual_partial_{trade_id}_{int(datetime.now().timestamp() * 1000)}"
        commission, swap, gross_profit, net_profit = _partial_values(partial)
        cursor.execute("""
            INSERT INTO trade_partial_closes (
                trade_id, ticket, volume, close_time, close_price,
                commission, swap, gross_profit, net_profit, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            trade_id, partial_ticket, partial.volume, partial.close_time,
            partial.close_price, commission, swap, gross_profit, net_profit,
            now_str, now_str
        ))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=409, detail="A partial close with this ticket already exists")

        _recalculate_trade_from_partials(cursor, trade_id)
        conn.commit()
        return _get_trade_with_partials(cursor, trade_id)

@router.delete("/{trade_id}/partials/{partial_id}")
def delete_partial_close(trade_id: int, partial_id: int):
    """Remove one partial exit and recalculate the parent trade."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM trade_partial_closes WHERE id = ? AND trade_id = ?;",
            (partial_id, trade_id)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Partial close not found")
        _recalculate_trade_from_partials(cursor, trade_id)
        conn.commit()
        return _get_trade_with_partials(cursor, trade_id)

@router.get("/{trade_id}/screenshots")
def get_trade_screenshots(trade_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM trades WHERE id = ?;", (trade_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Trade not found")
        cursor.execute("""
            SELECT id, trade_id, source_url, image_url, caption, created_at
            FROM trade_screenshots
            WHERE trade_id = ?
            ORDER BY created_at ASC, id ASC;
        """, (trade_id,))
        return [dict(row) for row in cursor.fetchall()]

@router.post("/{trade_id}/screenshots")
def add_trade_screenshot(trade_id: int, screenshot: TradeScreenshotCreate):
    source_url = _validate_http_url(screenshot.source_url, "source_url")
    image_url = screenshot.image_url.strip() if screenshot.image_url else _tradingview_image_url(source_url)
    if not image_url:
        raise HTTPException(
            status_code=400,
            detail="For a non-TradingView link, provide a direct image URL"
        )
    image_url = _validate_http_url(image_url, "image_url")
    now_str = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM trades WHERE id = ?;", (trade_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Trade not found")

        cursor.execute("""
            INSERT INTO trade_screenshots (trade_id, source_url, image_url, caption, created_at)
            VALUES (?, ?, ?, ?, ?);
        """, (trade_id, source_url, image_url, screenshot.caption or "", now_str))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=409, detail="This screenshot is already attached to the trade")
        conn.commit()
        cursor.execute("""
            SELECT id, trade_id, source_url, image_url, caption, created_at
            FROM trade_screenshots
            WHERE id = ?;
        """, (cursor.lastrowid,))
        return dict(cursor.fetchone())

@router.delete("/{trade_id}/screenshots/{screenshot_id}")
def delete_trade_screenshot(trade_id: int, screenshot_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM trade_screenshots WHERE id = ? AND trade_id = ?;",
            (screenshot_id, trade_id)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Screenshot not found")
        conn.commit()
    return {"message": "Screenshot deleted successfully"}

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

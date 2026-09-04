"""
MQL Receiver Connector for MetaTrader 4 and MetaTrader 5
Receives incoming JSON payloads from the TradeJournalSync Expert Advisor.
Updates account balance, equity, closed trades, and stores market candle bars.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import sqlite3
from server.database import get_connection
from server.models import MQLSyncPayload

logger = logging.getLogger(__name__)

def process_mql_payload(api_key: str, payload: MQLSyncPayload) -> Dict[str, Any]:
    """
    Validates API key and processes data sent by MT4/MT5 EA:
    1. Authenticate account by api_key
    2. Update current balance, equity, margin, free margin, leverage, broker, platform
    3. Record equity history snapshot
    4. Upsert closed trades
    5. Save market candle bars for chart replay
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. Lookup account by api_key
        cursor.execute("SELECT id, name, initial_balance FROM accounts WHERE api_key = ?;", (api_key,))
        account = cursor.fetchone()
        if not account:
            # Check if account matches account_number if api_key was empty
            cursor.execute("SELECT id, name, initial_balance FROM accounts WHERE account_number = ?;", (payload.account_number,))
            account = cursor.fetchone()
            if not account:
                raise ValueError("Invalid API Key or unknown account.")

        account_id = account["id"]
        now_str = datetime.now(timezone.utc).isoformat()

        # 2. Update account information
        cursor.execute("""
            UPDATE accounts
            SET current_balance = ?,
                equity = ?,
                margin = ?,
                free_margin = ?,
                leverage = ?,
                broker = COALESCE(NULLIF(?, ''), broker),
                platform = COALESCE(NULLIF(?, ''), platform),
                account_number = COALESCE(NULLIF(?, ''), account_number),
                currency = COALESCE(NULLIF(?, ''), currency),
                last_synced_at = ?,
                updated_at = ?
            WHERE id = ?;
        """, (
            payload.balance,
            payload.equity,
            payload.margin or 0.0,
            payload.free_margin or payload.balance,
            payload.leverage or 100,
            payload.broker or "",
            payload.platform or "MT5",
            payload.account_number or "",
            payload.currency or "USD",
            now_str,
            now_str,
            account_id
        ))

        # 3. Record equity history snapshot (throttled to max 1 per 5 mins or balance change)
        cursor.execute("""
            SELECT balance, equity FROM equity_history 
            WHERE account_id = ? 
            ORDER BY id DESC LIMIT 1;
        """, (account_id,))
        last_equity = cursor.fetchone()
        
        should_insert_equity = False
        if not last_equity:
            should_insert_equity = True
        elif abs(last_equity["balance"] - payload.balance) > 0.01 or abs(last_equity["equity"] - payload.equity) > 5.0:
            should_insert_equity = True

        if should_insert_equity:
            cursor.execute("""
                INSERT INTO equity_history (account_id, timestamp, balance, equity, margin)
                VALUES (?, ?, ?, ?, ?);
            """, (account_id, now_str, payload.balance, payload.equity, payload.margin or 0.0))

        # 4. Upsert closed trades
        inserted_trades = 0
        updated_trades = 0
        candles_saved = 0

        for trade in (payload.closed_trades or []):
            direction = "BUY" if trade.type == 0 else "SELL"
            pnl = trade.profit or 0.0
            gross_pnl = pnl - (trade.commission or 0.0) - (trade.swap or 0.0)
            status = "WIN" if pnl > 0.001 else ("LOSS" if pnl < -0.001 else "BE")

            # Check if trade already exists
            cursor.execute("SELECT id FROM trades WHERE account_id = ? AND ticket = ?;", (account_id, trade.ticket))
            existing = cursor.fetchone()

            if existing:
                cursor.execute("""
                    UPDATE trades
                    SET close_time = ?,
                        close_price = ?,
                        stop_loss = COALESCE(?, stop_loss),
                        take_profit = COALESCE(?, take_profit),
                        commission = ?,
                        swap = ?,
                        gross_profit = ?,
                        net_profit = ?,
                        status = ?,
                        updated_at = ?
                    WHERE id = ?;
                """, (
                    trade.close_time,
                    trade.close_price,
                    trade.stop_loss,
                    trade.take_profit,
                    trade.commission or 0.0,
                    trade.swap or 0.0,
                    gross_pnl,
                    pnl,
                    status,
                    now_str,
                    existing["id"]
                ))
                updated_trades += 1
            else:
                cursor.execute("""
                    INSERT INTO trades (
                        account_id, ticket, symbol, direction, volume,
                        open_time, close_time, open_price, close_price,
                        stop_loss, take_profit, commission, swap,
                        gross_profit, net_profit, status,
                        notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    account_id,
                    trade.ticket,
                    trade.symbol.upper(),
                    direction,
                    trade.lots,
                    trade.open_time,
                    trade.close_time,
                    trade.open_price,
                    trade.close_price,
                    trade.stop_loss,
                    trade.take_profit,
                    trade.commission or 0.0,
                    trade.swap or 0.0,
                    gross_pnl,
                    pnl,
                    status,
                    trade.comment or "",
                    now_str,
                    now_str
                ))
                inserted_trades += 1

            # 5. Process any candle bars attached to the trade
            if trade.candles:
                for c in trade.candles:
                    cursor.execute("""
                        INSERT OR REPLACE INTO market_candles (symbol, timeframe, timestamp, open, high, low, close, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """, (
                        trade.symbol.upper(),
                        "M15",
                        c.time,
                        c.open,
                        c.high,
                        c.low,
                        c.close,
                        c.volume or 0.0
                    ))
                    candles_saved += 1

        # Also process open trades (status = OPEN)
        for trade in (payload.open_trades or []):
            direction = "BUY" if trade.type == 0 else "SELL"
            cursor.execute("SELECT id FROM trades WHERE account_id = ? AND ticket = ?;", (account_id, trade.ticket))
            existing = cursor.fetchone()
            if not existing:
                cursor.execute("""
                    INSERT INTO trades (
                        account_id, ticket, symbol, direction, volume,
                        open_time, open_price, stop_loss, take_profit,
                        commission, swap, net_profit, status,
                        notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?);
                """, (
                    account_id,
                    trade.ticket,
                    trade.symbol.upper(),
                    direction,
                    trade.lots,
                    trade.open_time,
                    trade.open_price,
                    trade.stop_loss,
                    trade.take_profit,
                    trade.commission or 0.0,
                    trade.swap or 0.0,
                    trade.profit or 0.0,
                    trade.comment or "",
                    now_str,
                    now_str
                ))
                inserted_trades += 1

        conn.commit()

    logger.info(f"Sync successful for Account {account_id}: inserted={inserted_trades}, updated={updated_trades}, candles={candles_saved}")
    return {
        "status": "success",
        "account_id": account_id,
        "inserted_trades": inserted_trades,
        "updated_trades": updated_trades,
        "candles_saved": candles_saved,
        "synced_at": now_str
    }

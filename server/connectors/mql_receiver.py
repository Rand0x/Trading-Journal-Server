"""
MQL Receiver Connector for MetaTrader 4, MetaTrader 5, and the cTrader cBot.
Receives incoming JSON payloads from the TradeJournalSync Expert Advisor/cBot.
Updates account balance, equity, closed trades, and stores market candle bars.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import sqlite3
from server.database import get_connection
from server.models import MQLSyncPayload
from server.analytics import compute_r_multiple

logger = logging.getLogger(__name__)

def _save_candles(cursor, symbol: str, candles) -> int:
    rows = []
    for candle in candles or []:
        if isinstance(candle, dict):
            c_sym = candle.get("symbol") or symbol
            tf = candle.get("timeframe", "M15") or "M15"
            c_time = int(candle.get("time", candle.get("timestamp", 0)))
            c_open = float(candle["open"])
            c_high = float(candle["high"])
            c_low = float(candle["low"])
            c_close = float(candle["close"])
            c_vol = float(candle.get("volume", 0.0) or 0.0)
        else:
            c_sym = getattr(candle, "symbol", None) or symbol
            tf = getattr(candle, "timeframe", "M15") or "M15"
            c_time = int(getattr(candle, "time", getattr(candle, "timestamp", 0)))
            c_open = float(candle.open)
            c_high = float(candle.high)
            c_low = float(candle.low)
            c_close = float(candle.close)
            c_vol = float(getattr(candle, "volume", 0.0) or 0.0)

        if c_sym and c_time > 0:
            rows.append((
                c_sym.strip().upper(),
                tf.strip().upper(),
                c_time,
                c_open,
                c_high,
                c_low,
                c_close,
                c_vol
            ))

    if rows:
        cursor.executemany("""
            INSERT OR REPLACE INTO market_candles (symbol, timeframe, timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, rows)
    return len(rows)

def _process_ctrader_grouped_trade(cursor, account_id: int, trade, now_str: str):
    """Persist one cTrader position and all of its closing deals."""
    cursor.execute(
        "SELECT id, volume FROM trades WHERE account_id = ? AND ticket = ?;",
        (account_id, trade.ticket)
    )
    existing = cursor.fetchone()
    if existing:
        trade_id = existing["id"]
        original_volume = float(existing["volume"] or 0.0)
        clean_sl = trade.stop_loss if trade.stop_loss and trade.stop_loss > 0 else None
        clean_tp = trade.take_profit if trade.take_profit and trade.take_profit > 0 else None
        cursor.execute("""
            UPDATE trades
            SET symbol = ?, direction = ?, open_time = ?, open_price = ?,
                stop_loss = COALESCE(?, stop_loss), take_profit = COALESCE(?, take_profit),
                notes = CASE WHEN notes IS NOT NULL AND notes != '' THEN notes ELSE ? END,
                updated_at = ?
            WHERE id = ?;
        """, (
            trade.symbol.upper(), "BUY" if trade.type == 0 else "SELL",
            trade.open_time, trade.open_price, clean_sl, clean_tp,
            trade.comment or "", now_str, trade_id
        ))
        updated = 1
    else:
        trade_id = None
        original_volume = float(trade.lots)
        cursor.execute("""
            INSERT INTO trades (
                account_id, ticket, symbol, direction, volume,
                open_time, open_price, stop_loss, take_profit,
                commission, swap, gross_profit, net_profit, status,
                notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, 0.0, 0.0, 'OPEN', ?, ?, ?);
        """, (
            account_id, trade.ticket, trade.symbol.upper(),
            "BUY" if trade.type == 0 else "SELL", trade.lots,
            trade.open_time, trade.open_price, trade.stop_loss, trade.take_profit,
            trade.comment or "", now_str, now_str
        ))
        trade_id = cursor.lastrowid
        updated = 0

    legacy_rows = []
    for index, partial in enumerate(trade.partial_closes or [], start=1):
        partial_ticket = partial.ticket or f"{trade.ticket}-partial-{index}"
        # Older cTrader cBot versions stored each closing deal as its own
        # top-level trade (ctrader-deal-*). Migrate those rows into the new
        # partial-close table when the grouped payload arrives.
        cursor.execute("""
            SELECT id, setup_id, mistake_id, notes, emotions, rating, tags, timeframe,
                   pre_trade_notes, post_trade_notes, key_learnings, emotion_pre, emotion_during,
                   signals, initial_risk, risk_mode, is_missed
            FROM trades
            WHERE account_id = ? AND ticket = ? AND id != ?;
        """, (account_id, partial_ticket, trade_id))
        legacy = cursor.fetchone()
        if legacy:
            legacy_rows.append(legacy)
        commission = partial.commission or 0.0
        swap = partial.swap or 0.0
        net_profit = partial.net_profit or 0.0
        gross_profit = partial.gross_profit if partial.gross_profit is not None else net_profit - commission - swap
        cursor.execute("""
            INSERT OR IGNORE INTO trade_partial_closes (
                trade_id, ticket, volume, close_time, close_price,
                commission, swap, gross_profit, net_profit, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            trade_id, partial_ticket, partial.volume, partial.close_time,
            partial.close_price, commission, swap, gross_profit, net_profit,
            now_str, now_str
        ))

    if legacy_rows:
        # Keep manually added annotations from the legacy row when the new
        # grouped parent does not already have them.
        legacy = legacy_rows[0]
        cursor.execute("""
            UPDATE trades
            SET setup_id = COALESCE(setup_id, ?),
                mistake_id = COALESCE(mistake_id, ?),
                notes = CASE WHEN notes = '' THEN ? ELSE notes END,
                emotions = CASE WHEN emotions = 'Disciplined' THEN ? ELSE emotions END,
                rating = CASE WHEN rating = 5 THEN ? ELSE rating END,
                tags = CASE WHEN tags = '' THEN ? ELSE tags END,
                timeframe = CASE WHEN timeframe = 'M15' THEN ? ELSE timeframe END,
                pre_trade_notes = CASE WHEN pre_trade_notes = '' THEN ? ELSE pre_trade_notes END,
                post_trade_notes = CASE WHEN post_trade_notes = '' THEN ? ELSE post_trade_notes END,
                key_learnings = CASE WHEN key_learnings = '' THEN ? ELSE key_learnings END,
                emotion_pre = CASE WHEN emotion_pre = '' THEN ? ELSE emotion_pre END,
                emotion_during = CASE WHEN emotion_during = '' THEN ? ELSE emotion_during END,
                signals = CASE WHEN signals = '' THEN ? ELSE signals END,
                initial_risk = COALESCE(initial_risk, ?),
                risk_mode = CASE WHEN risk_mode = 'CURRENCY' THEN ? ELSE risk_mode END,
                is_missed = CASE WHEN is_missed = 0 THEN ? ELSE is_missed END
            WHERE id = ?;
        """, (
            legacy["setup_id"], legacy["mistake_id"], legacy["notes"] or "",
            legacy["emotions"] or "Disciplined", legacy["rating"] or 5,
            legacy["tags"] or "", legacy["timeframe"] or "M15",
            legacy["pre_trade_notes"] or "", legacy["post_trade_notes"] or "",
            legacy["key_learnings"] or "", legacy["emotion_pre"] or "",
            legacy["emotion_during"] or "", legacy["signals"] or "",
            legacy["initial_risk"], legacy["risk_mode"] or "CURRENCY",
            legacy["is_missed"] or 0,
            trade_id
        ))
        cursor.executemany(
            "DELETE FROM trades WHERE id = ?;",
            [(legacy_row["id"],) for legacy_row in legacy_rows]
        )

    cursor.execute("""
        SELECT volume, close_time, close_price, commission, swap, gross_profit, net_profit
        FROM trade_partial_closes
        WHERE trade_id = ?
        ORDER BY close_time ASC, id ASC;
    """, (trade_id,))
    partials = cursor.fetchall()
    total_volume = sum(float(row["volume"] or 0.0) for row in partials)
    parent_volume = max(original_volume, total_volume)
    total_commission = sum(float(row["commission"] or 0.0) for row in partials)
    total_swap = sum(float(row["swap"] or 0.0) for row in partials)
    total_gross = sum(float(row["gross_profit"] or 0.0) for row in partials)
    total_net = sum(float(row["net_profit"] or 0.0) for row in partials)
    weighted_close_price = (
        sum(float(row["volume"]) * float(row["close_price"]) for row in partials) / total_volume
        if total_volume > 0 else None
    )
    last_close_time = partials[-1]["close_time"] if partials else None
    is_complete = total_volume >= parent_volume - 1e-9
    status = "WIN" if total_net > 0.001 else ("LOSS" if total_net < -0.001 else "BE")
    if not is_complete:
        status = "OPEN"

    cursor.execute("""
        SELECT direction, open_price, stop_loss, initial_risk, r_multiple
        FROM trades WHERE id = ?;
    """, (trade_id,))
    p_info = cursor.fetchone()
    calc_r = p_info["r_multiple"] if p_info and p_info["r_multiple"] is not None else compute_r_multiple(
        direction=p_info["direction"] if p_info else "BUY",
        open_price=p_info["open_price"] if p_info else 0.0,
        stop_loss=p_info["stop_loss"] if p_info else None,
        close_price=weighted_close_price,
        net_profit=total_net,
        initial_risk=p_info["initial_risk"] if p_info else None,
        partial_closes=[dict(p) for p in partials],
        volume=parent_volume
    )

    cursor.execute("""
        UPDATE trades
        SET volume = ?, close_time = ?, close_price = ?, commission = ?, swap = ?,
            gross_profit = ?, net_profit = ?, status = ?,
            r_multiple = COALESCE(r_multiple, ?),
            updated_at = ?
        WHERE id = ?;
    """, (
        parent_volume, last_close_time, weighted_close_price,
        total_commission, total_swap, total_gross, total_net, status,
        calc_r, now_str, trade_id
    ))
    return trade_id, updated, _save_candles(cursor, trade.symbol, trade.candles)

def process_mql_payload(api_key: str, payload: MQLSyncPayload) -> Dict[str, Any]:
    """
    Validates API key and processes data sent by MT4/MT5 EA or cTrader cBot:
    1. Authenticate account by api_key
    2. Update current balance, equity, margin, free margin, leverage, broker, platform
    3. Record equity history snapshot
    4. Upsert closed trades
    5. Save market candle bars for chart replay
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. Authenticate solely by the account-specific sync key. Account
        # numbers are not secret and must never act as an authentication fallback.
        cursor.execute("SELECT id, name, initial_balance FROM accounts WHERE api_key = ?;", (api_key,))
        account = cursor.fetchone()
        if not account:
            raise ValueError("Invalid Journal API Key.")

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
            (payload.currency or "").strip().upper(),
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

        # 3.5 Process pending orders (status = PENDING)
        candles_saved = 0
        active_pending_tickets = set()
        for p_order in (payload.pending_orders or []):
            p_ticket = p_order.ticket or (f"ctrader-order-{p_order.order_id}" if p_order.order_id else "")
            if not p_ticket:
                continue
            active_pending_tickets.add(p_ticket)
            direction = "BUY" if p_order.type == 0 else "SELL"

            cursor.execute("SELECT id, status FROM trades WHERE account_id = ? AND ticket = ?;", (account_id, p_ticket))
            existing_pending = cursor.fetchone()
            if existing_pending:
                if existing_pending["status"] == "PENDING":
                    cursor.execute("""
                        UPDATE trades
                        SET symbol = ?, direction = ?, volume = ?, open_price = ?,
                            stop_loss = ?, take_profit = ?, updated_at = ?
                        WHERE id = ?;
                    """, (
                        p_order.symbol.upper(), direction, p_order.lots, p_order.open_price,
                        p_order.stop_loss, p_order.take_profit, now_str, existing_pending["id"]
                    ))
            else:
                cursor.execute("""
                    INSERT INTO trades (
                        account_id, ticket, symbol, direction, volume,
                        open_time, open_price, stop_loss, take_profit,
                        commission, swap, gross_profit, net_profit, status,
                        notes, order_id, order_type, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, 0.0, 0.0, 'PENDING', ?, ?, ?, ?, ?);
                """, (
                    account_id,
                    p_ticket,
                    p_order.symbol.upper(),
                    direction,
                    p_order.lots,
                    p_order.open_time,
                    p_order.open_price,
                    p_order.stop_loss,
                    p_order.take_profit,
                    p_order.comment or "",
                    str(p_order.order_id or ""),
                    str(p_order.order_type or "Limit"),
                    now_str,
                    now_str
                ))

            if p_order.candles:
                candles_saved += _save_candles(cursor, p_order.symbol, p_order.candles)

        # 4. Upsert closed trades
        inserted_trades = 0
        updated_trades = 0

        for trade in (payload.closed_trades or []):
            if payload.source == "ctrader-cbot" and trade.partial_closes:
                _, was_updated, saved_candles = _process_ctrader_grouped_trade(
                    cursor, account_id, trade, now_str
                )
                if was_updated:
                    updated_trades += 1
                else:
                    inserted_trades += 1
                candles_saved += saved_candles
                continue

            direction = "BUY" if trade.type == 0 else "SELL"
            pnl = trade.profit or 0.0
            gross_pnl = pnl - (trade.commission or 0.0) - (trade.swap or 0.0)
            status = "WIN" if pnl > 0.001 else ("LOSS" if pnl < -0.001 else "BE")

            clean_sl = trade.stop_loss if trade.stop_loss and trade.stop_loss > 0 else None
            clean_tp = trade.take_profit if trade.take_profit and trade.take_profit > 0 else None

            # Check if trade already exists
            cursor.execute("SELECT id FROM trades WHERE account_id = ? AND ticket = ?;", (account_id, trade.ticket))
            existing = cursor.fetchone()

            if not existing and trade.order_id:
                cursor.execute("""
                    SELECT id, open_price, stop_loss, initial_risk, r_multiple, direction FROM trades
                    WHERE account_id = ? AND status = 'PENDING'
                      AND (order_id = ? OR ticket = ? OR ticket = ? OR ticket = ?);
                """, (account_id, str(trade.order_id), f"ctrader-order-{trade.order_id}", f"mt5-order-{trade.order_id}", str(trade.order_id)))
                pending_match = cursor.fetchone()
                if pending_match:
                    resolved_sl = clean_sl or (pending_match["stop_loss"] if pending_match["stop_loss"] and pending_match["stop_loss"] > 0 else None)
                    resolved_op = trade.open_price or pending_match["open_price"]
                    calc_r = pending_match["r_multiple"] if pending_match["r_multiple"] is not None else compute_r_multiple(
                        direction=direction,
                        open_price=resolved_op,
                        stop_loss=resolved_sl,
                        close_price=trade.close_price,
                        net_profit=pnl,
                        initial_risk=pending_match["initial_risk"],
                        volume=trade.lots
                    )
                    cursor.execute("""
                        UPDATE trades
                        SET ticket = ?, order_id = ?, symbol = ?, direction = ?, volume = ?, open_time = ?, close_time = ?,
                            open_price = ?, close_price = ?, stop_loss = COALESCE(?, stop_loss),
                            take_profit = COALESCE(?, take_profit), commission = ?, swap = ?,
                            gross_profit = ?, net_profit = ?, status = ?,
                            r_multiple = COALESCE(r_multiple, ?),
                            updated_at = ?
                        WHERE id = ?;
                    """, (
                        trade.ticket, str(trade.order_id), trade.symbol.upper(), direction, trade.lots, trade.open_time, trade.close_time,
                        trade.open_price, trade.close_price, clean_sl, clean_tp,
                        trade.commission or 0.0, trade.swap or 0.0, gross_pnl, pnl, status,
                        calc_r, now_str, pending_match["id"]
                    ))
                    existing = pending_match
                    updated_trades += 1

            if existing:
                cursor.execute("SELECT direction, open_price, stop_loss, initial_risk, r_multiple FROM trades WHERE id = ?;", (existing["id"],))
                t_info = cursor.fetchone()
                resolved_sl = clean_sl or (t_info["stop_loss"] if t_info and t_info["stop_loss"] and t_info["stop_loss"] > 0 else None)
                resolved_op = trade.open_price or (t_info["open_price"] if t_info else 0.0)
                calc_r = t_info["r_multiple"] if t_info and t_info["r_multiple"] is not None else compute_r_multiple(
                    direction=direction,
                    open_price=resolved_op,
                    stop_loss=resolved_sl,
                    close_price=trade.close_price,
                    net_profit=pnl,
                    initial_risk=t_info["initial_risk"] if t_info else None,
                    volume=trade.lots
                )
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
                        r_multiple = COALESCE(r_multiple, ?),
                        updated_at = ?
                    WHERE id = ?;
                """, (
                    trade.close_time,
                    trade.close_price,
                    clean_sl,
                    clean_tp,
                    trade.commission or 0.0,
                    trade.swap or 0.0,
                    gross_pnl,
                    pnl,
                    status,
                    calc_r,
                    now_str,
                    existing["id"]
                ))
                updated_trades += 1
            else:
                calc_r = compute_r_multiple(
                    direction=direction,
                    open_price=trade.open_price,
                    stop_loss=clean_sl,
                    close_price=trade.close_price,
                    net_profit=pnl,
                    volume=trade.lots
                )
                cursor.execute("""
                    INSERT INTO trades (
                        account_id, ticket, symbol, direction, volume,
                        open_time, close_time, open_price, close_price,
                        stop_loss, take_profit, commission, swap,
                        gross_profit, net_profit, status,
                        notes, r_multiple, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                    clean_sl,
                    clean_tp,
                    trade.commission or 0.0,
                    trade.swap or 0.0,
                    gross_pnl,
                    pnl,
                    status,
                    trade.comment or "",
                    calc_r,
                    now_str,
                    now_str
                ))
                inserted_trades += 1

            # 5. Process any candle bars attached to the trade
            if trade.candles:
                candles_saved += _save_candles(cursor, trade.symbol, trade.candles)

        # Also process open trades (status = OPEN)
        active_ctrader_tickets = set()
        for trade in (payload.open_trades or []):
            direction = "BUY" if trade.type == 0 else "SELL"
            clean_sl = trade.stop_loss if trade.stop_loss and trade.stop_loss > 0 else None
            clean_tp = trade.take_profit if trade.take_profit and trade.take_profit > 0 else None
            if payload.source == "ctrader-cbot":
                active_ctrader_tickets.add(trade.ticket)

            # A grouped cTrader position uses the same ticket for its parent
            # trade and its live position snapshot. Preserve the partial-exit
            # aggregate while updating the remaining live volume and prices.
            if payload.source == "ctrader-cbot" and trade.position_id:
                cursor.execute("""
                    SELECT t.id, COALESCE(SUM(pc.volume), 0.0) AS closed_volume
                    FROM trades t
                    LEFT JOIN trade_partial_closes pc ON pc.trade_id = t.id
                    WHERE t.account_id = ? AND t.ticket = ?
                    GROUP BY t.id;
                """, (account_id, trade.ticket))
                grouped_position = cursor.fetchone()
                if grouped_position and grouped_position["closed_volume"] > 0:
                    total_volume = float(grouped_position["closed_volume"]) + float(trade.lots)
                    cursor.execute("""
                        UPDATE trades
                        SET symbol = ?, direction = ?, volume = ?, open_time = ?, open_price = ?,
                            stop_loss = COALESCE(?, stop_loss), take_profit = COALESCE(?, take_profit),
                            status = 'OPEN',
                            notes = CASE WHEN notes IS NOT NULL AND notes != '' THEN notes ELSE ? END,
                            updated_at = ?
                        WHERE id = ?;
                    """, (
                        trade.symbol.upper(), direction, total_volume, trade.open_time,
                        trade.open_price, clean_sl, clean_tp,
                        trade.comment or "", now_str, grouped_position["id"]
                    ))
                    updated_trades += 1
                    continue

            cursor.execute("SELECT id FROM trades WHERE account_id = ? AND ticket = ?;", (account_id, trade.ticket))
            existing = cursor.fetchone()

            if not existing and trade.order_id:
                cursor.execute("""
                    SELECT id FROM trades
                    WHERE account_id = ? AND status = 'PENDING'
                      AND (order_id = ? OR ticket = ? OR ticket = ? OR ticket = ?);
                """, (account_id, str(trade.order_id), f"ctrader-order-{trade.order_id}", f"mt5-order-{trade.order_id}", str(trade.order_id)))
                pending_match = cursor.fetchone()
                if pending_match:
                    cursor.execute("""
                        UPDATE trades
                        SET ticket = ?, order_id = ?, symbol = ?, direction = ?, volume = ?, open_time = ?, open_price = ?,
                            stop_loss = COALESCE(?, stop_loss), take_profit = COALESCE(?, take_profit),
                            commission = ?, swap = ?, gross_profit = ?, net_profit = ?, status = 'OPEN', updated_at = ?
                        WHERE id = ?;
                    """, (
                        trade.ticket, str(trade.order_id), trade.symbol.upper(), direction, trade.lots, trade.open_time, trade.open_price,
                        clean_sl, clean_tp, trade.commission or 0.0, trade.swap or 0.0,
                        (trade.profit or 0.0) - (trade.commission or 0.0) - (trade.swap or 0.0),
                        trade.profit or 0.0, now_str, pending_match["id"]
                    ))
                    updated_trades += 1
                    continue

            calc_init_risk = abs(trade.open_price - clean_sl) if (clean_sl and trade.open_price and clean_sl != trade.open_price) else None

            if existing:
                cursor.execute("""
                    UPDATE trades
                    SET symbol = ?, direction = ?, volume = ?, open_time = ?, open_price = ?,
                        stop_loss = COALESCE(?, stop_loss), take_profit = COALESCE(?, take_profit),
                        initial_risk = COALESCE(initial_risk, ?),
                        commission = ?, swap = ?, gross_profit = ?, net_profit = ?, status = 'OPEN',
                        notes = CASE WHEN notes IS NOT NULL AND notes != '' THEN notes ELSE ? END,
                        updated_at = ?
                    WHERE id = ?;
                """, (
                    trade.symbol.upper(), direction, trade.lots, trade.open_time, trade.open_price,
                    clean_sl, clean_tp, calc_init_risk, trade.commission or 0.0, trade.swap or 0.0,
                    (trade.profit or 0.0) - (trade.commission or 0.0) - (trade.swap or 0.0),
                    trade.profit or 0.0, trade.comment or "", now_str, existing["id"]
                ))
                updated_trades += 1
            else:
                cursor.execute("""
                    INSERT INTO trades (
                        account_id, ticket, symbol, direction, volume,
                        open_time, open_price, stop_loss, take_profit, initial_risk,
                        commission, swap, net_profit, status,
                        notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?);
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
                    calc_init_risk,
                    trade.commission or 0.0,
                    trade.swap or 0.0,
                    trade.profit or 0.0,
                    trade.comment or "",
                    now_str,
                    now_str
                ))
                inserted_trades += 1

            if trade.candles:
                candles_saved += _save_candles(cursor, trade.symbol, trade.candles)

        # Process any top-level candles attached directly to the payload
        if payload.candles:
            candles_saved += _save_candles(cursor, "", payload.candles)

        # Update any pending orders that were cancelled or expired in the broker
        if payload.pending_orders is not None and payload.source in ("ctrader-cbot", "mql"):
            prefix_pattern = 'ctrader-order-%' if payload.source == "ctrader-cbot" else 'mt5-order-%'
            if active_pending_tickets:
                placeholders = ", ".join("?" for _ in active_pending_tickets)
                cursor.execute(
                    f"""
                    UPDATE trades
                    SET status = 'CANCELLED', updated_at = ?
                    WHERE account_id = ? AND status = 'PENDING'
                      AND (ticket LIKE ? OR order_id != '')
                      AND ticket NOT IN ({placeholders});
                    """,
                    (now_str, account_id, prefix_pattern, *active_pending_tickets),
                )
            else:
                cursor.execute(
                    """
                    UPDATE trades
                    SET status = 'CANCELLED', updated_at = ?
                    WHERE account_id = ? AND status = 'PENDING'
                      AND (ticket LIKE ? OR order_id != '');
                    """,
                    (now_str, account_id, prefix_pattern),
                )

        # cTrader historical deals use distinct deal tickets from currently
        # open position tickets. Remove only stale cBot position snapshots once
        # a position disappears from the latest account snapshot.
        if payload.source == "ctrader-cbot":
            if active_ctrader_tickets:
                placeholders = ", ".join("?" for _ in active_ctrader_tickets)
                cursor.execute(
                    f"""
                    DELETE FROM trades
                    WHERE account_id = ? AND status = 'OPEN'
                      AND ticket LIKE 'ctrader-position-%'
                      AND ticket NOT IN ({placeholders});
                    """,
                    (account_id, *active_ctrader_tickets),
                )
            else:
                cursor.execute("""
                    DELETE FROM trades
                    WHERE account_id = ? AND status = 'OPEN'
                      AND ticket LIKE 'ctrader-position-%';
                """, (account_id,))

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

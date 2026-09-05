"""
Sync Router
Handles all external connectivity:
- MetaTrader 4 / MetaTrader 5 WebRequest payload receiver
- cTrader Open API sync trigger
- Statement file import (HTML & CSV)
- Candlestick and marker serving for TradingView Lightweight Charts
"""

import logging
from typing import Optional, Any, Union, List, Dict
from fastapi import APIRouter, Header, HTTPException, UploadFile, File, Form, Query, Body
from server.models import MQLSyncPayload, CTraderSyncRequest, CandleBatch, CandleUploadPayload
from server.connectors.mql_receiver import process_mql_payload
from server.connectors.ctrader_api import sync_ctrader_account
from server.connectors.ctrader_api import sync_all_active_ctrader_accounts
from server.connectors.statement_parser import parse_and_import_statement
from server.connectors.market_data import get_chart_data_for_trade
from server.database import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["Sync & Connectors"])

@router.post("/mql")
def receive_mql_sync(payload: MQLSyncPayload, x_api_key: Optional[str] = Header(None)):
    """
    Endpoint called by TradeJournalSync.mq4 and TradeJournalSync.mq5.
    Authenticates via X-API-Key header.
    Syncs balance, equity, closed deals, open positions, and market candle bars.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    try:
        result = process_mql_payload(api_key=x_api_key, payload=payload)
        return result
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing MQL sync: {e}")
        raise HTTPException(status_code=500, detail=f"Internal sync error: {str(e)}")

@router.post("/ctrader-push")
def receive_ctrader_cbot_sync(payload: MQLSyncPayload, x_api_key: Optional[str] = Header(None)):
    """Receive a read-only account snapshot from the bundled cTrader cBot."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    if payload.source != "ctrader-cbot" or (payload.platform or "").lower() != "ctrader":
        raise HTTPException(status_code=422, detail="Expected a cTrader cBot sync payload")

    try:
        return process_mql_payload(api_key=x_api_key, payload=payload)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing cTrader cBot sync: {e}")
        raise HTTPException(status_code=500, detail="Internal cTrader cBot sync error")

@router.post("/ctrader")
def trigger_ctrader_sync(req: CTraderSyncRequest):
    """
    Triggers read-only sync with cTrader Open API 2.0.
    Fetches balance, equity, and closed deals.
    """
    # If credentials passed in body, update account first
    if any(value is not None for value in (
        req.client_id,
        req.client_secret,
        req.access_token,
        req.ctrader_account_id,
    )):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE accounts
                SET ctrader_client_id = COALESCE(?, ctrader_client_id),
                    ctrader_client_secret = COALESCE(?, ctrader_client_secret),
                    ctrader_access_token = COALESCE(?, ctrader_access_token),
                    ctrader_account_id = COALESCE(?, ctrader_account_id),
                    ctrader_is_live = ?
                WHERE id = ?;
            """, (
                req.client_id,
                req.client_secret,
                req.access_token,
                req.ctrader_account_id,
                1 if req.is_live else 0,
                req.account_id,
            ))
            conn.commit()

    if req.is_live:
        # The request can select the live endpoint for a one-off sync. Persist
        # it only when credentials were supplied above; stored auto-sync uses
        # the account setting.
        with get_connection() as conn:
            conn.execute(
                "UPDATE accounts SET ctrader_is_live = ? WHERE id = ?;",
                (1, req.account_id),
            )
            conn.commit()

    res = sync_ctrader_account(req.account_id)
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("error", "cTrader sync failed"))
    return res

@router.post("/auto-sync-all")
def trigger_auto_sync_all():
    """Triggers background synchronization for configured cTrader accounts."""
    return sync_all_active_ctrader_accounts()

@router.post("/import")
async def import_statement_file(file: UploadFile = File(...), account_id: int = Form(...)):
    """
    Drag-and-Drop statement importer:
    Supports MT4 Detailed Statement (HTML), MT5 Report (HTML/CSV),
    cTrader Deals (CSV), and TradeZella format (CSV).
    """
    try:
        content_bytes = await file.read()
        # Decode as utf-8 or latin-1
        try:
            content_str = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content_str = content_bytes.decode("latin-1")

        result = parse_and_import_statement(
            file_content=content_str,
            filename=file.filename,
            account_id=account_id
        )

        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("message"))

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to parse statement file: {e}")
        raise HTTPException(status_code=500, detail=f"Error importing file: {str(e)}")

def _extract_candle_rows(payload: Any, default_symbol: str = "", default_tf: str = "M15") -> list:
    rows = []
    if isinstance(payload, list):
        for item in payload:
            rows.extend(_extract_candle_rows(item, default_symbol, default_tf))
        return rows

    if hasattr(payload, "model_dump"):
        data = payload.model_dump()
    elif isinstance(payload, dict):
        data = payload
    else:
        return rows

    if "batches" in data and isinstance(data["batches"], list):
        for b in data["batches"]:
            rows.extend(_extract_candle_rows(b, default_symbol, default_tf))

    sym = (data.get("symbol") or default_symbol or "").strip().upper()
    batch_tf = (data.get("timeframe") or default_tf or "").strip().upper()

    candles = data.get("candles")
    if isinstance(candles, list):
        for c in candles:
            if hasattr(c, "model_dump"):
                c_dict = c.model_dump()
            elif isinstance(c, dict):
                c_dict = c
            else:
                continue
            c_sym = (c_dict.get("symbol") or sym).strip().upper()
            c_tf = (batch_tf or c_dict.get("timeframe") or "M15").strip().upper()
            c_time = int(c_dict.get("time", c_dict.get("timestamp", 0)))
            if c_sym and c_time > 0 and "open" in c_dict and "close" in c_dict:
                rows.append((
                    c_sym,
                    c_tf,
                    c_time,
                    float(c_dict["open"]),
                    float(c_dict["high"]),
                    float(c_dict["low"]),
                    float(c_dict["close"]),
                    float(c_dict.get("volume", 0.0) or 0.0)
                ))
    elif sym and "time" in data and "open" in data and "close" in data:
        # Single candle object directly passed
        c_time = int(data.get("time", data.get("timestamp", 0)))
        if c_time > 0:
            c_tf = (batch_tf or data.get("timeframe") or "M15").strip().upper()
            rows.append((
                sym,
                c_tf,
                c_time,
                float(data["open"]),
                float(data["high"]),
                float(data["low"]),
                float(data["close"]),
                float(data.get("volume", 0.0) or 0.0)
            ))
    return rows

def _save_candle_records(rows: list) -> int:
    if not rows:
        return 0
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT OR REPLACE INTO market_candles (symbol, timeframe, timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, rows)
        conn.commit()
    return len(rows)

@router.get("/chart-data/{trade_id}")
def get_trade_chart_data(trade_id: int, timeframe: str = Query("AUTO"), bars: int = Query(2000)):
    """
    Provides full dataset for TradingView Lightweight Charts:
    - Candlestick bars (time, open, high, low, close)
    - Volume bars (time, value, color)
    - Trade execution markers (entry arrow, exit circle)
    - Price lines (entry, stop loss, take profit)
    """
    try:
        return get_chart_data_for_trade(trade_id=trade_id, timeframe=timeframe, num_bars=bars)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error preparing chart data for trade {trade_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/latest-candle/{trade_id}")
def get_latest_candle_for_trade(trade_id: int, timeframe: str = Query("AUTO")):
    """
    Returns the newest candle bar for a trade's symbol and timeframe.
    Used by trade_detail.js for 5-second near-real-time live chart updates.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT symbol, status, open_price, close_price FROM trades WHERE id = ?;", (trade_id,))
        trade = cursor.fetchone()
        if not trade:
            raise HTTPException(status_code=404, detail=f"Trade with ID {trade_id} not found.")

        symbol = trade["symbol"].upper()
        target_tf = timeframe.upper()

        if target_tf == "AUTO":
            cursor.execute("""
                SELECT timeframe FROM market_candles
                WHERE symbol = ?
                ORDER BY timestamp DESC LIMIT 1;
            """, (symbol,))
            tf_row = cursor.fetchone()
            target_tf = tf_row["timeframe"].upper() if tf_row else "M15"

        cursor.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM market_candles
            WHERE symbol = ? AND timeframe = ?
            ORDER BY timestamp DESC
            LIMIT 1;
        """, (symbol, target_tf))
        row = cursor.fetchone()

        if not row:
            return {
                "status": "no_data",
                "symbol": symbol,
                "timeframe": target_tf,
                "candle": None,
                "trade_status": trade["status"],
            }

        return {
            "status": "success",
            "symbol": symbol,
            "timeframe": target_tf,
            "candle": {
                "time": int(row["timestamp"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"] or 0.0),
            },
            "trade_status": trade["status"],
            "open_price": float(trade["open_price"]),
            "close_price": float(trade["close_price"]) if trade["close_price"] else None,
        }

@router.get("/latest-candle")
def get_latest_candle(symbol: str = Query(...), timeframe: str = Query("M15")):
    """
    Returns the newest candle bar for any symbol and timeframe.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM market_candles
            WHERE symbol = ? AND timeframe = ?
            ORDER BY timestamp DESC
            LIMIT 1;
        """, (symbol.upper(), timeframe.upper()))
        row = cursor.fetchone()
        if not row:
            return {"status": "no_data", "symbol": symbol.upper(), "timeframe": timeframe.upper(), "candle": None}
        return {
            "status": "success",
            "symbol": symbol.upper(),
            "timeframe": timeframe.upper(),
            "candle": {
                "time": int(row["timestamp"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"] or 0.0),
            }
        }

@router.post("/candles")
@router.post("/live-candles")
def upload_candles(
    payload: Union[CandleUploadPayload, CandleBatch, List[CandleBatch], Dict[str, Any], List[Dict[str, Any]]] = Body(...),
    x_api_key: Optional[str] = Header(None)
):
    """
    Stores candle bars manually or via external collector/EA/cBot.
    Handles single batches, multi-batches, or live forming candle updates.
    Updates in-place based on (symbol, timeframe, timestamp) without creating duplicate ticks.
    """
    rows = _extract_candle_rows(payload)
    count = _save_candle_records(rows)
    return {"status": "success", "count": count}

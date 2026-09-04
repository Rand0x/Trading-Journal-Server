"""
Sync Router
Handles all external connectivity:
- MetaTrader 4 / MetaTrader 5 WebRequest payload receiver
- cTrader Open API sync trigger
- Statement file import (HTML & CSV)
- Candlestick and marker serving for TradingView Lightweight Charts
"""

import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, UploadFile, File, Form, Query
from server.models import MQLSyncPayload, CTraderSyncRequest, CandleBatch
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

@router.get("/chart-data/{trade_id}")
def get_trade_chart_data(trade_id: int, timeframe: str = Query("AUTO"), bars: int = Query(120)):
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

@router.post("/candles")
def upload_candles(batch: CandleBatch):
    """Stores candle bars manually or via external collector."""
    with get_connection() as conn:
        cursor = conn.cursor()
        for c in batch.candles:
            cursor.execute("""
                INSERT OR REPLACE INTO market_candles (symbol, timeframe, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (batch.symbol.upper(), batch.timeframe.upper(), c.time, c.open, c.high, c.low, c.close, c.volume or 0.0))
        conn.commit()
    return {"status": "success", "count": len(batch.candles)}

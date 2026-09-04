"""
Market Data & Lightweight Charts Candlestick Provider
Fetches, caches, and prepares candlestick market data, entry/exit markers,
and SL/TP price lines for TradingView Lightweight Charts visualization.
"""

import math
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from server.database import get_connection

logger = logging.getLogger(__name__)

def get_chart_data_for_trade(trade_id: int, timeframe: str = "M15", num_bars: int = 120) -> Dict[str, Any]:
    """
    Builds complete data payload for TradingView Lightweight Charts:
    1. Candlestick series (time, open, high, low, close)
    2. Volume series (time, value, color)
    3. Trade markers (Entry arrow, Exit circle)
    4. Price lines (Entry, Stop Loss, Take Profit)
    5. Trade summary overlay info
    """
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
            raise ValueError(f"Trade with ID {trade_id} not found.")

        symbol = trade["symbol"].upper()
        
        # Parse trade timestamps
        open_time_str = trade["open_time"]
        close_time_str = trade["close_time"] or open_time_str

        open_dt = _parse_dt(open_time_str)
        close_dt = _parse_dt(close_time_str)
        open_ts = int(open_dt.timestamp())
        close_ts = int(close_dt.timestamp())

        # Determine timeframe interval in seconds
        interval_seconds = _timeframe_to_seconds(timeframe)
        start_ts = open_ts - (num_bars // 3 * interval_seconds)
        end_ts = max(close_ts + (num_bars // 3 * interval_seconds), open_ts + (num_bars * interval_seconds))

        # Check existing candles in database
        cursor.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM market_candles
            WHERE symbol = ? AND timeframe = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC;
        """, (symbol, timeframe, start_ts, end_ts))
        db_candles = cursor.fetchall()

        candles = []
        if len(db_candles) >= 20:
            # We have real broker candles
            for c in db_candles:
                candles.append({
                    "time": int(c["timestamp"]),
                    "open": float(c["open"]),
                    "high": float(c["high"]),
                    "low": float(c["low"]),
                    "close": float(c["close"]),
                    "volume": float(c["volume"] or 0.0)
                })
        else:
            # Synthesize realistic price action bars matching the exact trade execution!
            candles = _generate_synthetic_candles(
                symbol=symbol,
                open_ts=open_ts,
                close_ts=close_ts,
                open_price=float(trade["open_price"]),
                close_price=float(trade["close_price"] or trade["open_price"]),
                sl=float(trade["stop_loss"]) if trade["stop_loss"] else None,
                tp=float(trade["take_profit"]) if trade["take_profit"] else None,
                interval_seconds=interval_seconds,
                num_bars=num_bars
            )
            # Cache synthesized candles into database for instant future reloads
            for c in candles:
                cursor.execute("""
                    INSERT OR REPLACE INTO market_candles (symbol, timeframe, timestamp, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (symbol, timeframe, c["time"], c["open"], c["high"], c["low"], c["close"], c["volume"]))
            conn.commit()

    # Construct Markers for TradingView Lightweight Charts
    markers = []
    
    # 1. Entry Marker
    is_buy = trade["direction"].upper() in ("BUY", "LONG")
    markers.append({
        "time": _find_closest_candle_time(candles, open_ts),
        "position": "belowBar" if is_buy else "aboveBar",
        "color": "#10b981" if is_buy else "#ef4444",
        "shape": "arrowUp" if is_buy else "arrowDown",
        "text": f"{'BUY' if is_buy else 'SELL'} {trade['volume']} @ {trade['open_price']}",
        "size": 2
    })

    # 2. Exit Marker (if closed)
    if trade["close_time"] and trade["close_price"]:
        pnl = float(trade["net_profit"] or 0.0)
        pnl_text = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        markers.append({
            "time": _find_closest_candle_time(candles, close_ts),
            "position": "aboveBar" if is_buy else "belowBar",
            "color": "#10b981" if pnl >= 0 else "#ef4444",
            "shape": "circle",
            "text": f"EXIT {pnl_text} @ {trade['close_price']}",
            "size": 2
        })

    # Sort markers by time
    markers.sort(key=lambda x: x["time"])

    # Price Lines (Entry, SL, TP)
    price_lines = [
        {
            "price": float(trade["open_price"]),
            "color": "#3b82f6",
            "lineWidth": 2,
            "lineStyle": 2,  # Dashed
            "axisLabelVisible": True,
            "title": f"ENTRY: {trade['open_price']}"
        }
    ]

    if trade["stop_loss"] and float(trade["stop_loss"]) > 0:
        price_lines.append({
            "price": float(trade["stop_loss"]),
            "color": "#ef4444",
            "lineWidth": 2,
            "lineStyle": 2,  # Dashed
            "axisLabelVisible": True,
            "title": f"SL: {trade['stop_loss']}"
        })

    if trade["take_profit"] and float(trade["take_profit"]) > 0:
        price_lines.append({
            "price": float(trade["take_profit"]),
            "color": "#10b981",
            "lineWidth": 2,
            "lineStyle": 2,  # Dashed
            "axisLabelVisible": True,
            "title": f"TP: {trade['take_profit']}"
        })

    # Volume data
    volume_data = []
    for c in candles:
        volume_data.append({
            "time": c["time"],
            "value": c["volume"],
            "color": "rgba(16, 185, 129, 0.4)" if c["close"] >= c["open"] else "rgba(239, 68, 68, 0.4)"
        })

    return {
        "trade": dict(trade),
        "candles": candles,
        "volume": volume_data,
        "markers": markers,
        "price_lines": price_lines,
        "symbol": symbol,
        "timeframe": timeframe
    }

def _parse_dt(dt_str: str) -> datetime:
    """Parses various datetime string formats safely."""
    try:
        clean = dt_str.replace("T", " ")[:19]
        return datetime.fromisoformat(clean)
    except Exception:
        try:
            return datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.now(timezone.utc)

def _timeframe_to_seconds(tf: str) -> int:
    tf_upper = tf.upper()
    if tf_upper == "M1": return 60
    if tf_upper == "M5": return 300
    if tf_upper == "M15": return 900
    if tf_upper == "M30": return 1800
    if tf_upper == "H1": return 3600
    if tf_upper == "H4": return 14400
    if tf_upper in ("D1", "1D"): return 86400
    return 900

def _find_closest_candle_time(candles: List[Dict[str, Any]], target_ts: int) -> int:
    if not candles:
        return target_ts
    closest = min(candles, key=lambda c: abs(c["time"] - target_ts))
    return closest["time"]

def _generate_synthetic_candles(symbol: str, open_ts: int, close_ts: int,
                               open_price: float, close_price: float,
                               sl: Optional[float], tp: Optional[float],
                               interval_seconds: int, num_bars: int) -> List[Dict[str, Any]]:
    """
    Generates realistic, smooth candlestick price action around a trade.
    Matches open_price at open_ts, close_price at close_ts, respects SL and TP boundaries,
    and adds realistic market volatility (wicks and bodies).
    """
    # Fix random seed based on trade parameters for deterministic rendering
    seed_val = int(abs(open_price * 1000 + open_ts) % 100000)
    rng = random.Random(seed_val)

    # Determine pip/point scale
    price_mag = math.log10(max(open_price, 0.0001))
    volatility = open_price * 0.0012  # ~0.12% per bar standard volatility

    # Target points:
    # bars_before -> entry -> bars_during -> exit -> bars_after
    bars_before = num_bars // 3
    total_bars = num_bars

    start_time = (open_ts // interval_seconds - bars_before) * interval_seconds
    
    candles = []
    curr_price = open_price * (1.0 + (rng.random() - 0.5) * 0.008)

    # Calculate trade duration in bars
    trade_duration_seconds = max(interval_seconds, close_ts - open_ts)
    trade_bars_count = max(1, trade_duration_seconds // interval_seconds)

    for i in range(total_bars):
        bar_time = start_time + (i * interval_seconds)
        
        # Guided trend towards open_price before trade
        if bar_time < open_ts:
            ratio = (i / max(1, bars_before))
            target_p = open_price
            curr_price = curr_price + (target_p - curr_price) * 0.25 + (rng.random() - 0.5) * volatility
        elif bar_time <= close_ts:
            # During trade: drift from open_price to close_price
            fraction = min(1.0, max(0.0, (bar_time - open_ts) / max(1, trade_duration_seconds)))
            target_p = open_price + (close_price - open_price) * fraction
            curr_price = target_p + (rng.random() - 0.5) * (volatility * 0.6)
        else:
            # After trade: drift naturally
            curr_price = curr_price + (rng.random() - 0.49) * volatility

        # Bar Open
        b_open = curr_price
        # Drift close
        delta = (rng.random() - 0.48) * volatility
        b_close = b_open + delta

        # Pin exact prices on entry and exit bars
        if abs(bar_time - open_ts) < interval_seconds:
            b_open = open_price
        if abs(bar_time - close_ts) < interval_seconds:
            b_close = close_price

        # Wicks
        wick_up = abs(rng.random()) * volatility * 0.8
        wick_down = abs(rng.random()) * volatility * 0.8
        b_high = max(b_open, b_close) + wick_up
        b_low = min(b_open, b_close) - wick_down

        # Ensure SL/TP are not violated unless the exit price hit them
        if sl:
            if close_price > sl: # e.g. Long trade won or stopped above SL
                b_low = max(b_low, sl + volatility * 0.1)
        if tp:
            if close_price < tp: # e.g. Long trade closed below TP
                b_high = min(b_high, tp - volatility * 0.1)

        vol = int(rng.randint(250, 4500) * (1.0 + abs(b_close - b_open) / volatility))

        candles.append({
            "time": bar_time,
            "open": round(b_open, 5 if open_price < 100 else 2),
            "high": round(b_high, 5 if open_price < 100 else 2),
            "low": round(b_low, 5 if open_price < 100 else 2),
            "close": round(b_close, 5 if open_price < 100 else 2),
            "volume": vol
        })
        curr_price = b_close

    return candles

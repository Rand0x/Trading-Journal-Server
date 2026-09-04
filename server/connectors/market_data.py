"""
Real broker candle provider for TradingView Lightweight Charts.

The journal never fabricates price candles. A chart either displays bars received from
MetaTrader/cTrader or explicitly reports that real data is not available yet.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from server.database import get_connection

CHART_TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
AUTO_TIMEFRAMES = ("M15", "H1", "H4", "D1")
MAX_AUTO_CHART_BARS = 500
CONTEXT_BARS = 8


def get_chart_data_for_trade(
    trade_id: int, timeframe: str = "AUTO", num_bars: int = 140
) -> Dict[str, Any]:
    """Return only real candles covering a trade and a small visual context."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT t.*, a.name as account_name, a.currency as account_currency,
                   p.name as setup_name, m.name as mistake_name
            FROM trades t
            LEFT JOIN accounts a ON t.account_id = a.id
            LEFT JOIN playbooks p ON t.setup_id = p.id
            LEFT JOIN mistakes m ON t.mistake_id = m.id
            WHERE t.id = ?;
            """,
            (trade_id,),
        )
        trade = cursor.fetchone()
        if not trade:
            raise ValueError(f"Trade with ID {trade_id} not found.")

        open_ts = int(_parse_dt(trade["open_time"]).timestamp())
        close_ts = int(_parse_dt(trade["close_time"] or trade["open_time"]).timestamp())
        if not trade["close_time"]:
            close_ts = max(close_ts, int(datetime.now(timezone.utc).timestamp()))

        candles, selected_timeframe, interval_seconds = _load_best_candles(
            cursor, trade["symbol"], timeframe, open_ts, close_ts
        )

    has_entry = _has_nearby_candle(candles, open_ts, interval_seconds)
    has_exit = not trade["close_time"] or _has_nearby_candle(candles, close_ts, interval_seconds)
    complete = bool(candles) and has_entry and has_exit
    message = ""
    if not candles:
        message = (
            f"No real {selected_timeframe} broker candles are stored for this trade yet. "
            "Update the EA or cBot and run a new sync."
        )
    elif not complete:
        message = (
            "Only part of the real broker data is available. Entry or exit is outside "
            "the saved candle range; run the updated EA or cBot again."
        )

    markers = _build_markers(trade, candles, open_ts, close_ts) if candles else []
    volume = [
        {
            "time": candle["time"],
            "value": candle["volume"],
            "color": (
                "rgba(16, 185, 129, 0.4)"
                if candle["close"] >= candle["open"]
                else "rgba(239, 68, 68, 0.4)"
            ),
        }
        for candle in candles
    ]

    return {
        "trade": dict(trade),
        "candles": candles,
        "volume": volume,
        "markers": markers,
        "price_lines": _price_lines(trade),
        "symbol": trade["symbol"].upper(),
        "timeframe": selected_timeframe,
        "requested_timeframe": timeframe.upper(),
        "data_available": bool(candles),
        "complete_coverage": complete,
        "message": message,
    }


def _fetch_raw_candles(
    cursor, symbol: str, timeframe: str, start_ts: int, end_ts: int
) -> List[Dict[str, Any]]:
    cursor.execute(
        """
        SELECT timestamp, open, high, low, close, volume
        FROM market_candles
        WHERE symbol = ? AND timeframe = ? AND timestamp >= ? AND timestamp <= ?
        ORDER BY timestamp ASC;
        """,
        (symbol.upper(), timeframe.upper(), start_ts, end_ts),
    )
    return [
        {
            "time": int(row["timestamp"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"] or 0.0),
        }
        for row in cursor.fetchall()
    ]


def _aggregate_candles(
    candles: List[Dict[str, Any]], target_timeframe: str
) -> List[Dict[str, Any]]:
    interval = _timeframe_to_seconds(target_timeframe)
    if not candles or interval <= 0:
        return candles

    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for c in candles:
        bucket = (c["time"] // interval) * interval
        if bucket not in grouped:
            grouped[bucket] = []
        grouped[bucket].append(c)

    aggregated = []
    for bucket in sorted(grouped.keys()):
        bars = grouped[bucket]
        bars.sort(key=lambda b: b["time"])
        aggregated.append({
            "time": bucket,
            "open": bars[0]["open"],
            "high": max(b["high"] for b in bars),
            "low": min(b["low"] for b in bars),
            "close": bars[-1]["close"],
            "volume": sum(b["volume"] for b in bars),
        })
    return aggregated


def _load_best_candles(
    cursor, symbol: str, requested_timeframe: str, open_ts: int, close_ts: int
) -> tuple[List[Dict[str, Any]], str, int]:
    """
    Loads the best available real broker candles covering [open_ts, close_ts].
    Supports automatic timeframe selection and dynamic aggregation from finer real bars
    (e.g., M15 -> H1, H4, D1) without ever generating artificial prices.
    """
    req_tf = requested_timeframe.upper()
    if req_tf == "AUTO":
        target_tf = _select_auto_timeframe(open_ts, close_ts)
    elif req_tf in CHART_TIMEFRAMES:
        target_tf = req_tf
    else:
        raise ValueError(f"Unsupported chart timeframe: {requested_timeframe}")

    target_interval = _timeframe_to_seconds(target_tf)
    start_ts = open_ts - CONTEXT_BARS * target_interval
    end_ts = close_ts + CONTEXT_BARS * target_interval

    # 1. Direct query for target timeframe
    candles = _fetch_raw_candles(cursor, symbol, target_tf, start_ts, end_ts)
    if candles:
        return candles, target_tf, target_interval

    # 2. Try aggregation from lower timeframes (e.g. M15 -> H1, H4, D1)
    lower_candidates = [
        tf for tf in ("M1", "M5", "M15", "M30", "H1", "H4")
        if _timeframe_to_seconds(tf) < target_interval and target_interval % _timeframe_to_seconds(tf) == 0
    ]
    for lower_tf in reversed(lower_candidates):
        raw_bars = _fetch_raw_candles(cursor, symbol, lower_tf, start_ts, end_ts)
        if raw_bars:
            return _aggregate_candles(raw_bars, target_tf), target_tf, target_interval

    # 3. If in AUTO mode, check if ANY other real timeframe is stored for this trade range
    if req_tf == "AUTO":
        cursor.execute(
            """
            SELECT DISTINCT timeframe
            FROM market_candles
            WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?;
            """,
            (symbol.upper(), open_ts - 86400, close_ts + 86400),
        )
        stored_tfs = {row["timeframe"].upper() for row in cursor.fetchall()}
        for alt_tf in AUTO_TIMEFRAMES:
            if alt_tf in stored_tfs:
                alt_interval = _timeframe_to_seconds(alt_tf)
                alt_start = open_ts - CONTEXT_BARS * alt_interval
                alt_end = close_ts + CONTEXT_BARS * alt_interval
                alt_candles = _fetch_raw_candles(cursor, symbol, alt_tf, alt_start, alt_end)
                if alt_candles:
                    return alt_candles, alt_tf, alt_interval

    return [], target_tf, target_interval


def _select_auto_timeframe(open_ts: int, close_ts: int) -> str:
    duration_seconds = max(0, close_ts - open_ts)
    for timeframe in AUTO_TIMEFRAMES:
        interval = _timeframe_to_seconds(timeframe)
        required_bars = duration_seconds / interval + (CONTEXT_BARS * 2)
        if required_bars <= MAX_AUTO_CHART_BARS:
            return timeframe
    return "D1"


def _build_markers(trade, candles: List[Dict[str, Any]], open_ts: int, close_ts: int):
    status = trade["status"] if "status" in trade.keys() else ""
    is_pending = status == "PENDING"
    is_buy = trade["direction"].upper() in ("BUY", "LONG")
    markers = []
    if not is_pending:
        markers.append(
            {
                "time": _find_closest_candle_time(candles, open_ts),
                "position": "belowBar" if is_buy else "aboveBar",
                "color": "#10b981" if is_buy else "#ef4444",
                "shape": "arrowUp" if is_buy else "arrowDown",
                "text": f"{'BUY' if is_buy else 'SELL'} {trade['volume']} @ {trade['open_price']}",
                "size": 2,
            }
        )
    if trade["close_time"] and trade["close_price"]:
        pnl = float(trade["net_profit"] or 0.0)
        markers.append(
            {
                "time": _find_closest_candle_time(candles, close_ts),
                "position": "aboveBar" if is_buy else "belowBar",
                "color": "#10b981" if pnl >= 0 else "#ef4444",
                "shape": "circle",
                "text": f"EXIT {pnl:+.2f} @ {trade['close_price']}",
                "size": 2,
            }
        )
    return sorted(markers, key=lambda marker: marker["time"])


def _price_lines(trade) -> List[Dict[str, Any]]:
    status = trade["status"] if "status" in trade.keys() else ""
    is_pending = status == "PENDING"
    lines = [
        {
            "price": float(trade["open_price"]),
            "color": "#f59e0b" if is_pending else "#3b82f6",
            "lineWidth": 2,
            "lineStyle": 2,
            "axisLabelVisible": True,
            "title": f"LIMIT: {trade['open_price']}" if is_pending else f"ENTRY: {trade['open_price']}",
        }
    ]
    if trade["stop_loss"] and float(trade["stop_loss"]) > 0:
        lines.append(
            {
                "price": float(trade["stop_loss"]),
                "color": "#ef4444",
                "lineWidth": 2,
                "lineStyle": 2,
                "axisLabelVisible": True,
                "title": f"SL: {trade['stop_loss']}",
            }
        )
    if trade["take_profit"] and float(trade["take_profit"]) > 0:
        lines.append(
            {
                "price": float(trade["take_profit"]),
                "color": "#10b981",
                "lineWidth": 2,
                "lineStyle": 2,
                "axisLabelVisible": True,
                "title": f"TP: {trade['take_profit']}",
            }
        )
    return lines


def _parse_dt(value: str) -> datetime:
    clean = value.replace("T", " ").replace("Z", "+00:00")[:26]
    try:
        parsed = datetime.fromisoformat(clean)
    except ValueError:
        parsed = datetime.strptime(clean[:19], "%Y-%m-%d %H:%M:%S")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timeframe_to_seconds(timeframe: str) -> int:
    return {
        "M1": 60,
        "M5": 300,
        "M15": 900,
        "M30": 1800,
        "H1": 3600,
        "H4": 14400,
        "D1": 86400,
    }.get(timeframe.upper(), 900)


def _find_closest_candle_time(candles: List[Dict[str, Any]], target_ts: int) -> int:
    return min(candles, key=lambda candle: abs(candle["time"] - target_ts))["time"]


def _has_nearby_candle(
    candles: List[Dict[str, Any]], target_ts: int, interval_seconds: int
) -> bool:
    return any(abs(candle["time"] - target_ts) <= interval_seconds * 2 for candle in candles)


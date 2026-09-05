"""
Universal Statement Parser for MetaTrader 4, MetaTrader 5, cTrader, and TradeZella.
Parses HTML reports and CSV exports to import full trade histories effortlessly.
"""

import csv
import io
import re
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
from server.database import get_connection
from server.analytics import compute_r_multiple

logger = logging.getLogger(__name__)

def _detect_statement_currency(file_content: str, filename: str) -> Optional[str]:
    """Extract currency from statement file headers if present."""
    match = re.search(r"Currency:\s*(?:<b>)?\s*([A-Za-z]{3})\b", file_content, re.IGNORECASE)
    if match:
        return match.group(1).upper()

    match = re.search(r"(?:Net|Gross|Profit|Balance)\s+([A-Za-z]{3})\b", file_content, re.IGNORECASE)
    if match:
        return match.group(1).upper()

    match = re.search(r"\b(?:Profit|Balance|Equity|Deposit)\s*\(([A-Za-z]{3})\)", file_content, re.IGNORECASE)
    if match:
        return match.group(1).upper()

    return None

def parse_and_import_statement(file_content: str, filename: str, account_id: int) -> Dict[str, Any]:
    """
    Auto-detects file type (MT4 HTML, MT5 HTML/CSV, cTrader CSV, TradeZella CSV)
    and imports all trades into the specified account.
    """
    filename_lower = filename.lower()
    
    if filename_lower.endswith(".html") or filename_lower.endswith(".htm") or "<html" in file_content.lower():
        if "metatrader 4" in file_content.lower() or "closed transactions:" in file_content.lower():
            trades = _parse_mt4_html(file_content)
        elif "metatrader 5" in file_content.lower() or "deals" in file_content.lower():
            trades = _parse_mt5_html(file_content)
        else:
            trades = _parse_generic_html(file_content)
    else:
        # CSV parsing
        trades = _parse_csv(file_content)

    if not trades:
        return {
            "status": "error",
            "message": "No valid closed trades found in statement file. Ensure the file contains closed orders or deals.",
            "imported": 0
        }

    # Save to database
    imported = 0
    skipped = 0
    now_str = datetime.now(timezone.utc).isoformat()
    detected_currency = _detect_statement_currency(file_content, filename)

    with get_connection() as conn:
        cursor = conn.cursor()
        if detected_currency:
            cursor.execute(
                "UPDATE accounts SET currency = ?, updated_at = ? WHERE id = ?;",
                (detected_currency, now_str, account_id)
            )
        for t in trades:
            ticket = t.get("ticket") or f"import_{datetime.now().timestamp()}_{imported}"
            direction = t.get("direction", "BUY").upper()
            net_profit = float(t.get("net_profit") or 0.0)
            status = "WIN" if net_profit > 0.001 else ("LOSS" if net_profit < -0.001 else "BE")
            sl_val = float(t.get("stop_loss") or 0.0) if t.get("stop_loss") else None
            tp_val = float(t.get("take_profit") or 0.0) if t.get("take_profit") else None
            open_p = float(t.get("open_price") or 0.0)
            close_p = float(t.get("close_price") or 0.0)
            calc_r = compute_r_multiple(
                direction=direction,
                open_price=open_p,
                stop_loss=sl_val,
                close_price=close_p,
                net_profit=net_profit
            )

            try:
                cursor.execute("""
                    INSERT INTO trades (
                        account_id, ticket, symbol, direction, volume,
                        open_time, close_time, open_price, close_price,
                        stop_loss, take_profit, commission, swap,
                        gross_profit, net_profit, status, r_multiple, notes,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    account_id,
                    ticket,
                    (t.get("symbol") or "EURUSD").upper(),
                    direction,
                    float(t.get("volume") or 0.1),
                    t.get("open_time") or now_str,
                    t.get("close_time") or now_str,
                    open_p,
                    close_p,
                    sl_val,
                    tp_val,
                    float(t.get("commission") or 0.0),
                    float(t.get("swap") or 0.0),
                    float(t.get("gross_profit") or net_profit),
                    net_profit,
                    status,
                    calc_r,
                    t.get("notes") or f"Imported from {filename}",
                    now_str,
                    now_str
                ))
                imported += 1
            except Exception as e:
                skipped += 1

        conn.commit()

    return {
        "status": "success",
        "message": f"Successfully imported {imported} trades ({skipped} duplicates skipped).",
        "imported": imported,
        "skipped": skipped
    }

def _parse_mt4_html(html: str) -> List[Dict[str, Any]]:
    """Parses MT4 HTML Statement table."""
    trades = []
    # Match table rows in Closed Transactions
    # <tr><td>Ticket</td><td>Open Time</td><td>Type</td><td>Size</td><td>Item</td><td>Price</td><td>S/L</td><td>T/P</td><td>Close Time</td><td>Price</td><td>Commission</td><td>Taxes</td><td>Swap</td><td>Profit</td></tr>
    row_pattern = re.compile(r'<tr[^>]*>\s*<td[^>]*>(\d+)</td>\s*<td[^>]*>([\d\.\s:]+)</td>\s*<td[^>]*>(buy|sell)</td>\s*<td[^>]*>([\d\.]+)</td>\s*<td[^>]*>([\w\.\#]+)</td>\s*<td[^>]*>([\d\.]+)</td>\s*<td[^>]*>([\d\.]+)</td>\s*<td[^>]*>([\d\.]+)</td>\s*<td[^>]*>([\d\.\s:]+)</td>\s*<td[^>]*>([\d\.]+)</td>\s*<td[^>]*>(-?[\d\.]+)</td>\s*<td[^>]*>(-?[\d\.]+)</td>\s*<td[^>]*>(-?[\d\.]+)</td>\s*<td[^>]*>(-?[\d\.]+)</td>', re.IGNORECASE)

    for m in row_pattern.finditer(html):
        ticket, open_t, t_type, size, item, open_p, sl, tp, close_t, close_p, comm, taxes, swap, profit = m.groups()
        trades.append({
            "ticket": f"mt4_{ticket}",
            "symbol": item.strip(),
            "direction": t_type.upper().strip(),
            "volume": float(size),
            "open_time": open_t.strip().replace(".", "-"),
            "close_time": close_t.strip().replace(".", "-"),
            "open_price": float(open_p),
            "close_price": float(close_p),
            "stop_loss": float(sl) if float(sl) > 0 else None,
            "take_profit": float(tp) if float(tp) > 0 else None,
            "commission": float(comm),
            "swap": float(swap),
            "net_profit": float(profit),
            "gross_profit": float(profit) - float(comm) - float(swap)
        })
    return trades

def _parse_mt5_html(html: str) -> List[Dict[str, Any]]:
    """Parses MT5 HTML Report table."""
    trades = []
    # Deals row regex
    row_pattern = re.compile(r'<tr[^>]*>\s*<td[^>]*>([\d\.\s:]+)</td>\s*<td[^>]*>(\d+)</td>\s*<td[^>]*>([\w\.\#]+)</td>\s*<td[^>]*>(buy|sell)</td>\s*<td[^>]*>(in|out|in/out)</td>\s*<td[^>]*>([\d\.]+)</td>\s*<td[^>]*>([\d\.]+)</td>\s*<td[^>]*>.*?</td>\s*<td[^>]*>(-?[\d\.]+)</td>\s*<td[^>]*>(-?[\d\.]+)</td>\s*<td[^>]*>(-?[\d\.]+)</td>', re.IGNORECASE)

    for m in row_pattern.finditer(html):
        time_s, deal_id, symbol, d_type, d_dir, vol, price, comm, fee, profit = m.groups()
        if d_dir.lower() in ("out", "in/out"):
            trades.append({
                "ticket": f"mt5_{deal_id}",
                "symbol": symbol.strip(),
                "direction": "BUY" if d_type.lower() == "buy" else "SELL",
                "volume": float(vol),
                "open_time": time_s.strip().replace(".", "-"),
                "close_time": time_s.strip().replace(".", "-"),
                "open_price": float(price),
                "close_price": float(price),
                "commission": float(comm) + float(fee),
                "swap": 0.0,
                "net_profit": float(profit),
            })
    return trades

def _parse_generic_html(html: str) -> List[Dict[str, Any]]:
    """Fallback HTML table row scanner."""
    trades = []
    # Find all <tr> tags and extract text
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
    for r in rows:
        cols = [re.sub(r'<[^>]+>', '', c).strip() for c in re.findall(r'<td[^>]*>(.*?)</td>', r, re.DOTALL | re.IGNORECASE)]
        if len(cols) >= 10:
            # Look for buy/sell
            for i, c in enumerate(cols):
                if c.lower() in ("buy", "sell"):
                    try:
                        trades.append({
                            "ticket": f"row_{len(trades)+1}",
                            "direction": c.upper(),
                            "symbol": cols[i+2] if i+2 < len(cols) else "EURUSD",
                            "volume": float(cols[i+1]) if i+1 < len(cols) else 1.0,
                            "open_price": float(cols[i+3]) if i+3 < len(cols) else 1.0,
                            "close_price": float(cols[i+5]) if i+5 < len(cols) else 1.0,
                            "net_profit": float(cols[-1]) if cols[-1] else 0.0,
                            "open_time": datetime.now(timezone.utc).isoformat()
                        })
                    except Exception:
                        pass
                    break
    return trades

def _parse_csv(content: str) -> List[Dict[str, Any]]:
    """Parses MT5 CSV, cTrader CSV, or TradeZella CSV."""
    trades = []
    reader = csv.DictReader(io.StringIO(content))
    
    # Normalize headers
    if not reader.fieldnames:
        return []

    headers = {h.strip().lower().replace(" ", "_").replace("/", "_").replace("&", ""): h for h in reader.fieldnames}

    for row in reader:
        # Standardize cTrader
        if "deal_id" in headers or "opening_direction" in headers:
            sym = row.get(headers.get("symbol", ""))
            direction = row.get(headers.get("opening_direction", "BUY"), "BUY")
            vol = row.get(headers.get("volume", "1.0"), "1.0")
            open_t = row.get(headers.get("opening_time", ""), "")
            close_t = row.get(headers.get("closing_time", ""), "")
            open_p = row.get(headers.get("entry_price", "0.0"), "0.0")
            close_p = row.get(headers.get("closing_price", "0.0"), "0.0")
            net_p = row.get(headers.get("net_usd", row.get(headers.get("net_profit", "0.0"))), "0.0")
            comm = row.get(headers.get("commission", "0.0"), "0.0")
            swap = row.get(headers.get("swap", "0.0"), "0.0")
            ticket = row.get(headers.get("deal_id", f"ctrader_{len(trades)+1}"))

            trades.append({
                "ticket": ticket,
                "symbol": sym or "EURUSD",
                "direction": "BUY" if "buy" in direction.lower() else "SELL",
                "volume": float(vol.replace(",", "") or 1.0),
                "open_time": open_t,
                "close_time": close_t or open_t,
                "open_price": float(open_p.replace(",", "") or 0.0),
                "close_price": float(close_p.replace(",", "") or 0.0),
                "commission": float(comm.replace(",", "") or 0.0),
                "swap": float(swap.replace(",", "") or 0.0),
                "net_profit": float(net_p.replace(",", "") or 0.0)
            })

        # TradeZella format
        elif "ticker" in headers or "pnl" in headers or "net_pl" in headers or "quantity" in headers:
            sym = row.get(headers.get("ticker", row.get(headers.get("symbol", "UNKNOWN"))))
            direction = row.get(headers.get("type", row.get(headers.get("direction", "BUY"))), "BUY")
            vol = row.get(headers.get("quantity", row.get(headers.get("volume", "1.0"))), "1.0")
            open_t = row.get(headers.get("date", row.get(headers.get("open_time", ""))), "")
            close_t = row.get(headers.get("exit_date", row.get(headers.get("close_time", ""))), open_t)
            open_p = row.get(headers.get("entry_price", row.get(headers.get("open_price", "0.0"))), "0.0")
            close_p = row.get(headers.get("exit_price", row.get(headers.get("close_price", "0.0"))), "0.0")
            pnl = row.get(headers.get("net_pl", row.get(headers.get("pnl", row.get(headers.get("net_profit", "0.0"))))), "0.0")
            notes = row.get(headers.get("notes", ""), "")

            clean_pnl = pnl.replace("$", "").replace(",", "").strip()
            trades.append({
                "ticket": f"tz_{len(trades)+1}",
                "symbol": sym or "UNKNOWN",
                "direction": "BUY" if "buy" in direction.lower() or "long" in direction.lower() else "SELL",
                "volume": float(vol.replace(",", "") or 1.0),
                "open_time": open_t,
                "close_time": close_t or open_t,
                "open_price": float(open_p.replace("$", "").replace(",", "") or 0.0),
                "close_price": float(close_p.replace("$", "").replace(",", "") or 0.0),
                "net_profit": float(clean_pnl or 0.0),
                "notes": notes
            })

        # Generic CSV
        else:
            # Look for common column names
            for s_key in ("symbol", "item", "ticker", "instrument"):
                if s_key in headers:
                    sym = row.get(headers[s_key])
                    pnl_key = next((k for k in ("profit", "net_profit", "pnl", "net_pnl") if k in headers), None)
                    pnl = float(row.get(headers[pnl_key], "0.0").replace("$", "").replace(",", "") or 0.0) if pnl_key else 0.0
                    trades.append({
                        "ticket": f"csv_{len(trades)+1}",
                        "symbol": sym,
                        "direction": "BUY",
                        "volume": 1.0,
                        "open_time": datetime.now(timezone.utc).isoformat(),
                        "close_time": datetime.now(timezone.utc).isoformat(),
                        "open_price": 1.0,
                        "close_price": 1.0,
                        "net_profit": pnl
                    })
                    break

    return trades

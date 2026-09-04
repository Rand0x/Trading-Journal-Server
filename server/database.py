"""
Database Module for Raspberry Pi Trading Journal
Uses SQLite with Write-Ahead Logging (WAL) and memory optimizations
tailored specifically for low-resource environments (Raspberry Pi 3 Model B, 1 GB RAM).
"""

import sqlite3
import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

DB_DIR = os.getenv("DB_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
DB_PATH = os.path.join(DB_DIR, "journal.db")

def get_db_path() -> str:
    os.makedirs(DB_DIR, exist_ok=True)
    return DB_PATH

def get_connection() -> sqlite3.Connection:
    """
    Get optimized SQLite connection.
    Configured for Raspberry Pi 3 (1 GB RAM):
    - WAL journal mode (fast concurrent reads/writes, reduced SD card wear)
    - synchronous = NORMAL (safe and fast)
    - cache_size = -16000 (~16MB memory cache)
    - temp_store = MEMORY
    """
    conn = sqlite3.connect(get_db_path(), timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA cache_size = -16000;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    return conn

def init_db():
    """Initialize database tables, indexes, and default seeds."""
    os.makedirs(DB_DIR, exist_ok=True)
    with get_connection() as conn:
        cursor = conn.cursor()

        # Accounts table (MT4, MT5, cTrader, Manual)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            broker TEXT DEFAULT '',
            platform TEXT NOT NULL, -- 'MT4', 'MT5', 'cTrader', 'Manual'
            account_number TEXT DEFAULT '',
            currency TEXT DEFAULT 'USD',
            initial_balance REAL DEFAULT 10000.0,
            current_balance REAL DEFAULT 10000.0,
            equity REAL DEFAULT 10000.0,
            margin REAL DEFAULT 0.0,
            free_margin REAL DEFAULT 10000.0,
            leverage INTEGER DEFAULT 100,
            api_key TEXT UNIQUE,
            ctrader_client_id TEXT DEFAULT '',
            ctrader_client_secret TEXT DEFAULT '',
            ctrader_access_token TEXT DEFAULT '',
            ctrader_account_id TEXT DEFAULT '',
            last_synced_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)

        # Equity History (Tracks balance/equity over time for growth curves)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS equity_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            balance REAL NOT NULL,
            equity REAL NOT NULL,
            margin REAL DEFAULT 0.0
        );
        """)

        # Playbooks (Trading Setups)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS playbooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            target_rr REAL DEFAULT 2.0,
            rules TEXT DEFAULT '',
            color TEXT DEFAULT '#3b82f6',
            created_at TEXT NOT NULL
        );
        """)

        # Mistakes (Costly trading behavioral mistakes)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS mistakes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            severity TEXT DEFAULT 'MEDIUM', -- 'LOW', 'MEDIUM', 'HIGH'
            color TEXT DEFAULT '#ef4444',
            created_at TEXT NOT NULL
        );
        """)

        # Trades table (Full trade log matching TradeZella metrics)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            ticket TEXT,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL, -- 'BUY' / 'SELL'
            volume REAL NOT NULL, -- lots or units
            open_time TEXT NOT NULL,
            close_time TEXT,
            open_price REAL NOT NULL,
            close_price REAL,
            stop_loss REAL,
            take_profit REAL,
            commission REAL DEFAULT 0.0,
            swap REAL DEFAULT 0.0,
            gross_profit REAL DEFAULT 0.0,
            net_profit REAL DEFAULT 0.0,
            pnl_percent REAL DEFAULT 0.0,
            status TEXT DEFAULT 'CLOSED', -- 'OPEN', 'CLOSED', 'WIN', 'LOSS', 'BE'
            setup_id INTEGER REFERENCES playbooks(id) ON DELETE SET NULL,
            mistake_id INTEGER REFERENCES mistakes(id) ON DELETE SET NULL,
            notes TEXT DEFAULT '',
            emotions TEXT DEFAULT 'Disciplined', -- 'Disciplined', 'FOMO', 'Greedy', 'Anxious', 'Confident', 'Frustrated'
            rating INTEGER DEFAULT 5, -- 1-5 execution rating
            tags TEXT DEFAULT '', -- Comma-separated or JSON string
            timeframe TEXT DEFAULT 'M15',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(account_id, ticket) ON CONFLICT IGNORE
        );
        """)

        # Market Candlestick Data (Stored for TradingView Lightweight Charts replay/visualization)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_candles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL, -- 'M1', 'M5', 'M15', 'H1', 'H4', 'D1'
            timestamp INTEGER NOT NULL, -- Unix timestamp (seconds)
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL DEFAULT 0.0,
            UNIQUE(symbol, timeframe, timestamp) ON CONFLICT REPLACE
        );
        """)

        # Indexes for fast querying on low-power CPU
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_account ON trades(account_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_open_time ON trades(open_time);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_close_time ON trades(close_time);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_setup ON trades(setup_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_mistake ON trades(mistake_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_equity_account_time ON equity_history(account_id, timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_candles_lookup ON market_candles(symbol, timeframe, timestamp);")

        # Seed default Playbooks and Mistakes if empty
        cursor.execute("SELECT COUNT(*) FROM playbooks;")
        if cursor.fetchone()[0] == 0:
            default_playbooks = [
                ("Break & Retest", "Breakout above key support/resistance followed by clean retest and confirmation candle.", 2.5, "1. Key S/R level identified\n2. High volume breakout\n3. Retest on lower timeframe\n4. Reversal candlestick confirmation", "#3b82f6"),
                ("Order Block / FVG", "Institutional supply/demand zone with Fair Value Gap fill.", 3.0, "1. Liquidity sweep\n2. Market structure shift (MSS)\n3. FVG displacement\n4. Entry at 50% discount", "#8b5cf6"),
                ("Trend Continuation", "Pullback to 20/50 EMA in strong trending market.", 2.0, "1. Higher highs and higher lows\n2. Retest of 20 or 50 EMA\n3. Momentum indicator confirmation", "#10b981"),
                ("London Open Breakout", "Asian range high/low sweep at London 08:00 AM session open.", 2.0, "1. Mark Asian session high/low\n2. Wait for 08:00 London volume injection\n3. Fakeout & reversal entry", "#f59e0b"),
                ("Range Bound Bounce", "Fade at the top or bottom of a sideways consolidation channel.", 1.5, "1. Clear horizontal range with 2+ touches\n2. RSI divergence at extremes", "#ec4899")
            ]
            for name, desc, rr, rules, color in default_playbooks:
                cursor.execute(
                    "INSERT INTO playbooks (name, description, target_rr, rules, color, created_at) VALUES (?, ?, ?, ?, ?, ?);",
                    (name, desc, rr, rules, color, datetime.utcnow().isoformat())
                )

        cursor.execute("SELECT COUNT(*) FROM mistakes;")
        if cursor.fetchone()[0] == 0:
            default_mistakes = [
                ("FOMO Entry", "Chased price after a big move without waiting for a retest or confirmation.", "HIGH", "#ef4444"),
                ("Moved Stop Loss", "Widened or removed stop loss hoping the trade would turn around.", "HIGH", "#dc2626"),
                ("Overleveraged / Oversized", "Exceeded risk management parameter (>2% risk on single trade).", "HIGH", "#b91c1c"),
                ("Early Exit", "Cut a winning trade prematurely out of fear instead of letting it hit TP.", "MEDIUM", "#f97316"),
                ("Revenge Trading", "Entered immediately after a loss to make back money with elevated emotion.", "HIGH", "#e11d48"),
                ("Trading Without Setup", "Random impulse trade without a defined playbook or edge.", "MEDIUM", "#f59e0b"),
                ("Ignoring Trend", "Counter-trend trade against strong multi-timeframe momentum.", "MEDIUM", "#d97706")
            ]
            for name, desc, sev, color in default_mistakes:
                cursor.execute(
                    "INSERT INTO mistakes (name, description, severity, color, created_at) VALUES (?, ?, ?, ?, ?);",
                    (name, desc, sev, color, datetime.utcnow().isoformat())
                )

        # Seed demo account if no accounts exist
        cursor.execute("SELECT COUNT(*) FROM accounts;")
        if cursor.fetchone()[0] == 0:
            now = datetime.utcnow().isoformat()
            cursor.execute("""
            INSERT INTO accounts (name, broker, platform, account_number, currency, initial_balance, current_balance, equity, margin, free_margin, leverage, api_key, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                "Main Demo Account", "MetaQuotes", "MT5", "10052026", "USD",
                50000.0, 53420.50, 53420.50, 0.0, 53420.50, 100,
                "key_demo_tradezella_raspi_mt5", now, now
            ))
            account_id = cursor.lastrowid
            
            # Add initial equity history point
            cursor.execute("""
            INSERT INTO equity_history (account_id, timestamp, balance, equity, margin)
            VALUES (?, ?, ?, ?, ?);
            """, (account_id, now, 53420.50, 53420.50, 0.0))

        conn.commit()
        logger.info("Database initialized successfully with WAL mode.")

if __name__ == "__main__":
    init_db()
    print("Database initialization successful at:", DB_PATH)

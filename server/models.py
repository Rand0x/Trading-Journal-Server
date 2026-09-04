"""
Pydantic Models and Data Transfer Schemas
Clean type validation without external AI or heavy dependencies.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# ================= ACCOUNT SCHEMAS =================
class AccountBase(BaseModel):
    name: str
    broker: Optional[str] = ""
    platform: str = "MT5"  # 'MT4', 'MT5', 'cTrader', 'Manual'
    account_number: Optional[str] = ""
    currency: Optional[str] = "USD"
    initial_balance: Optional[float] = 10000.0
    current_balance: Optional[float] = 10000.0
    equity: Optional[float] = 10000.0
    margin: Optional[float] = 0.0
    free_margin: Optional[float] = 10000.0
    leverage: Optional[int] = 100
    ctrader_client_id: Optional[str] = ""
    ctrader_client_secret: Optional[str] = ""
    ctrader_access_token: Optional[str] = ""
    ctrader_account_id: Optional[str] = ""

class AccountCreate(AccountBase):
    pass

class AccountUpdate(BaseModel):
    name: Optional[str] = None
    broker: Optional[str] = None
    account_number: Optional[str] = None
    currency: Optional[str] = None
    initial_balance: Optional[float] = None
    current_balance: Optional[float] = None
    equity: Optional[float] = None
    margin: Optional[float] = None
    free_margin: Optional[float] = None
    leverage: Optional[int] = None
    ctrader_client_id: Optional[str] = None
    ctrader_client_secret: Optional[str] = None
    ctrader_access_token: Optional[str] = None
    ctrader_account_id: Optional[str] = None

class AccountResponse(AccountBase):
    id: int
    api_key: Optional[str] = None
    last_synced_at: Optional[str] = None
    created_at: str
    updated_at: str

# ================= PLAYBOOK SCHEMAS =================
class PlaybookBase(BaseModel):
    name: str
    description: Optional[str] = ""
    target_rr: Optional[float] = 2.0
    rules: Optional[str] = ""
    color: Optional[str] = "#3b82f6"

class PlaybookCreate(PlaybookBase):
    pass

class PlaybookResponse(PlaybookBase):
    id: int
    created_at: str
    trades_count: Optional[int] = 0
    win_rate: Optional[float] = 0.0
    total_pnl: Optional[float] = 0.0

# ================= MISTAKE SCHEMAS =================
class MistakeBase(BaseModel):
    name: str
    description: Optional[str] = ""
    severity: Optional[str] = "MEDIUM"
    color: Optional[str] = "#ef4444"

class MistakeCreate(MistakeBase):
    pass

class MistakeResponse(MistakeBase):
    id: int
    created_at: str
    occurrence_count: Optional[int] = 0
    total_loss: Optional[float] = 0.0

# ================= TRADE SCHEMAS =================
class TradeBase(BaseModel):
    account_id: int
    ticket: Optional[str] = None
    symbol: str
    direction: str  # 'BUY' or 'SELL'
    volume: float   # Lots or size
    open_time: str
    close_time: Optional[str] = None
    open_price: float
    close_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    commission: Optional[float] = 0.0
    swap: Optional[float] = 0.0
    gross_profit: Optional[float] = 0.0
    net_profit: Optional[float] = 0.0
    pnl_percent: Optional[float] = 0.0
    status: Optional[str] = "CLOSED"  # 'OPEN', 'CLOSED', 'WIN', 'LOSS', 'BE'
    setup_id: Optional[int] = None
    mistake_id: Optional[int] = None
    notes: Optional[str] = ""
    emotions: Optional[str] = "Disciplined"
    rating: Optional[int] = 5
    tags: Optional[str] = ""
    timeframe: Optional[str] = "M15"

class TradeCreate(TradeBase):
    pass

class TradeUpdate(BaseModel):
    symbol: Optional[str] = None
    direction: Optional[str] = None
    volume: Optional[float] = None
    open_time: Optional[str] = None
    close_time: Optional[str] = None
    open_price: Optional[float] = None
    close_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    commission: Optional[float] = None
    swap: Optional[float] = None
    gross_profit: Optional[float] = None
    net_profit: Optional[float] = None
    pnl_percent: Optional[float] = None
    status: Optional[str] = None
    setup_id: Optional[int] = None
    mistake_id: Optional[int] = None
    notes: Optional[str] = None
    emotions: Optional[str] = None
    rating: Optional[int] = None
    tags: Optional[str] = None
    timeframe: Optional[str] = None

class TradeResponse(TradeBase):
    id: int
    created_at: str
    updated_at: str
    setup_name: Optional[str] = None
    mistake_name: Optional[str] = None
    account_name: Optional[str] = None

# ================= MQL / BROKER SYNC SCHEMAS =================
class MQLCandleBar(BaseModel):
    time: int  # UNIX seconds
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = 0.0

class MQLTradeItem(BaseModel):
    ticket: str
    symbol: str
    type: int  # 0 = BUY, 1 = SELL
    lots: float
    open_time: str
    close_time: Optional[str] = None
    open_price: float
    close_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    commission: Optional[float] = 0.0
    swap: Optional[float] = 0.0
    profit: Optional[float] = 0.0
    comment: Optional[str] = ""
    candles: Optional[List[MQLCandleBar]] = None

class MQLSyncPayload(BaseModel):
    account_number: str
    broker: Optional[str] = ""
    platform: Optional[str] = "MT5"  # 'MT4' or 'MT5'
    currency: Optional[str] = "USD"
    balance: float
    equity: float
    margin: Optional[float] = 0.0
    free_margin: Optional[float] = 0.0
    leverage: Optional[int] = 100
    closed_trades: Optional[List[MQLTradeItem]] = []
    open_trades: Optional[List[MQLTradeItem]] = []

# ================= CANDLE SCHEMAS =================
class CandleItem(BaseModel):
    time: int  # Unix timestamp in seconds
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = 0.0

class CandleBatch(BaseModel):
    symbol: str
    timeframe: str
    candles: List[CandleItem]

# ================= CTRADER SYNC SCHEMA =================
class CTraderSyncRequest(BaseModel):
    account_id: int
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    access_token: Optional[str] = None
    ctrader_account_id: Optional[str] = None

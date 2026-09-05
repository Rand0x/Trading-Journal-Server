"""
Pydantic Models and Data Transfer Schemas
Clean type validation without external AI or heavy dependencies.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Literal

Platform = Literal["MT4", "MT5", "cTrader", "Manual"]
Direction = Literal["BUY", "SELL"]
TradeStatus = Literal["OPEN", "CLOSED", "WIN", "LOSS", "BE", "PENDING", "CANCELLED"]
Severity = Literal["LOW", "MEDIUM", "HIGH"]

# ================= ACCOUNT SCHEMAS =================
class AccountBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    broker: Optional[str] = ""
    platform: Platform = "MT5"
    account_number: Optional[str] = ""
    currency: Optional[str] = Field(default="USD", min_length=3, max_length=12)
    initial_balance: Optional[float] = Field(default=10000.0, ge=0)
    current_balance: Optional[float] = Field(default=10000.0, ge=0)
    equity: Optional[float] = Field(default=10000.0, ge=0)
    margin: Optional[float] = Field(default=0.0, ge=0)
    free_margin: Optional[float] = Field(default=10000.0, ge=0)
    leverage: Optional[int] = Field(default=100, ge=1)
    server_name: Optional[str] = ""
    auto_sync_enabled: Optional[bool] = True
    sync_interval_minutes: Optional[int] = Field(default=5, ge=1, le=1440)
    ctrader_client_id: Optional[str] = ""
    ctrader_client_secret: Optional[str] = ""
    ctrader_access_token: Optional[str] = ""
    ctrader_account_id: Optional[str] = ""
    ctrader_is_live: Optional[bool] = False

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, v):
        if v is None:
            return "USD"
        val = str(v).strip().upper()
        return val or "USD"

class AccountCreate(AccountBase):
    pass

class AccountUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    broker: Optional[str] = None
    account_number: Optional[str] = None
    currency: Optional[str] = None

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_update_currency(cls, v):
        if v is None:
            return None
        val = str(v).strip().upper()
        return val or None
    initial_balance: Optional[float] = Field(default=None, ge=0)
    current_balance: Optional[float] = Field(default=None, ge=0)
    equity: Optional[float] = Field(default=None, ge=0)
    margin: Optional[float] = Field(default=None, ge=0)
    free_margin: Optional[float] = Field(default=None, ge=0)
    leverage: Optional[int] = Field(default=None, ge=1)
    server_name: Optional[str] = None
    auto_sync_enabled: Optional[bool] = None
    sync_interval_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    ctrader_client_id: Optional[str] = None
    ctrader_client_secret: Optional[str] = None
    ctrader_access_token: Optional[str] = None
    ctrader_account_id: Optional[str] = None
    ctrader_is_live: Optional[bool] = None

class AccountResponse(BaseModel):
    id: int
    name: str
    broker: Optional[str] = ""
    platform: Platform = "MT5"
    account_number: Optional[str] = ""
    currency: Optional[str] = "USD"
    initial_balance: Optional[float] = 10000.0
    current_balance: Optional[float] = 10000.0
    equity: Optional[float] = 10000.0
    margin: Optional[float] = 0.0
    free_margin: Optional[float] = 10000.0
    leverage: Optional[int] = 100
    server_name: Optional[str] = ""
    auto_sync_enabled: Optional[bool] = True
    sync_interval_minutes: Optional[int] = 5
    ctrader_is_live: Optional[bool] = False
    api_key: Optional[str] = None
    last_synced_at: Optional[str] = None
    created_at: str
    updated_at: str

# ================= PLAYBOOK SCHEMAS =================
class PlaybookBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = ""
    rules: Optional[str] = ""
    color: Optional[str] = "#3b82f6"

class PlaybookCreate(PlaybookBase):
    pass

class PlaybookUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    rules: Optional[str] = None
    color: Optional[str] = None

class PlaybookResponse(PlaybookBase):
    id: int
    created_at: str
    trades_count: Optional[int] = 0
    win_rate: Optional[float] = 0.0
    total_pnl: Optional[float] = 0.0

# ================= MISTAKE SCHEMAS =================
class MistakeBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = ""
    severity: Severity = "MEDIUM"
    color: Optional[str] = "#ef4444"

class MistakeCreate(MistakeBase):
    pass

class MistakeResponse(MistakeBase):
    id: int
    created_at: str
    occurrence_count: Optional[int] = 0
    total_loss: Optional[float] = 0.0

# ================= TRADE SCHEMAS =================
class TradePartialCloseBase(BaseModel):
    ticket: Optional[str] = None
    volume: float = Field(gt=0)
    close_time: str = Field(min_length=1)
    close_price: float = Field(gt=0)
    commission: Optional[float] = 0.0
    swap: Optional[float] = 0.0
    gross_profit: Optional[float] = None
    net_profit: float = 0.0

class TradePartialCloseCreate(TradePartialCloseBase):
    pass

class TradePartialCloseResponse(TradePartialCloseBase):
    id: int
    trade_id: int
    created_at: str
    updated_at: str

class TradeScreenshotCreate(BaseModel):
    source_url: str = Field(min_length=1, max_length=1000)
    image_url: Optional[str] = Field(default=None, max_length=1000)
    caption: Optional[str] = Field(default="", max_length=300)

class TradeScreenshotResponse(TradeScreenshotCreate):
    id: int
    trade_id: int
    created_at: str

class TradeBase(BaseModel):
    account_id: int
    ticket: Optional[str] = None
    symbol: str = Field(min_length=1, max_length=40)
    direction: Direction
    volume: float = Field(gt=0)
    open_time: str = Field(min_length=1)
    close_time: Optional[str] = None
    open_price: float = Field(gt=0)
    close_price: Optional[float] = Field(default=None, gt=0)
    stop_loss: Optional[float] = Field(default=None, gt=0)
    take_profit: Optional[float] = Field(default=None, gt=0)
    commission: Optional[float] = 0.0
    swap: Optional[float] = 0.0
    gross_profit: Optional[float] = 0.0
    net_profit: Optional[float] = 0.0
    pnl_percent: Optional[float] = 0.0
    status: Optional[TradeStatus] = None
    setup_id: Optional[int] = None
    mistake_id: Optional[int] = None
    notes: Optional[str] = ""
    emotions: Optional[str] = "Disciplined"
    rating: Optional[int] = Field(default=5, ge=1, le=5)
    tags: Optional[str] = ""
    timeframe: Optional[str] = "M15"
    partial_closes: List[TradePartialCloseCreate] = Field(default_factory=list)

class TradeCreate(TradeBase):
    pass

class TradeUpdate(BaseModel):
    symbol: Optional[str] = Field(default=None, min_length=1, max_length=40)
    direction: Optional[Direction] = None
    volume: Optional[float] = Field(default=None, gt=0)
    open_time: Optional[str] = None
    close_time: Optional[str] = None
    open_price: Optional[float] = Field(default=None, gt=0)
    close_price: Optional[float] = Field(default=None, gt=0)
    stop_loss: Optional[float] = Field(default=None, gt=0)
    take_profit: Optional[float] = Field(default=None, gt=0)
    commission: Optional[float] = None
    swap: Optional[float] = None
    gross_profit: Optional[float] = None
    net_profit: Optional[float] = None
    pnl_percent: Optional[float] = None
    status: Optional[TradeStatus] = None
    setup_id: Optional[int] = None
    mistake_id: Optional[int] = None
    notes: Optional[str] = None
    emotions: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    tags: Optional[str] = None
    timeframe: Optional[str] = None

class TradeResponse(TradeBase):
    id: int
    created_at: str
    updated_at: str
    setup_name: Optional[str] = None
    mistake_name: Optional[str] = None
    account_name: Optional[str] = None
    account_currency: Optional[str] = None

# ================= MQL / BROKER SYNC SCHEMAS =================
class MQLCandleBar(BaseModel):
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    time: int  # UNIX seconds
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = 0.0

class MQLTradeItem(BaseModel):
    ticket: str
    position_id: Optional[str] = None
    order_id: Optional[str] = None
    order_type: Optional[str] = None
    status: Optional[str] = None
    symbol: str
    type: int = Field(ge=0, le=1)  # 0 = BUY, 1 = SELL
    lots: float = Field(gt=0)
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
    partial_closes: Optional[List[TradePartialCloseBase]] = None

class MQLSyncPayload(BaseModel):
    source: Literal["mql", "ctrader-cbot"] = "mql"
    account_number: str
    broker: Optional[str] = ""
    platform: Optional[str] = "MT5"  # 'MT4' or 'MT5'
    currency: Optional[str] = None
    balance: float = Field(ge=0)
    equity: float = Field(ge=0)
    margin: Optional[float] = 0.0
    free_margin: Optional[float] = 0.0
    leverage: Optional[int] = Field(default=100, ge=1)
    closed_trades: Optional[List[MQLTradeItem]] = Field(default_factory=list)
    open_trades: Optional[List[MQLTradeItem]] = Field(default_factory=list)
    pending_orders: Optional[List[MQLTradeItem]] = Field(default_factory=list)
    candles: Optional[List[MQLCandleBar]] = Field(default_factory=list)

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_mql_currency(cls, v):
        if v is None:
            return None
        val = str(v).strip().upper()
        return val or None

# ================= CANDLE SCHEMAS =================
class CandleItem(BaseModel):
    time: int  # Unix timestamp in seconds
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = 0.0
    symbol: Optional[str] = None
    timeframe: Optional[str] = None

class CandleBatch(BaseModel):
    symbol: str
    timeframe: str
    candles: List[CandleItem]

class CandleUploadPayload(BaseModel):
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    candles: Optional[List[CandleItem]] = None
    batches: Optional[List[CandleBatch]] = None

# ================= CTRADER SYNC SCHEMA =================
class CTraderSyncRequest(BaseModel):
    account_id: int
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    access_token: Optional[str] = None
    ctrader_account_id: Optional[str] = None
    is_live: bool = False

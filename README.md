# 📈 Trading Journal Server (TradeZella Alternative) for Raspberry Pi 3

A full-featured, high-performance Trading Journal inspired by **[TradeZella.com](https://www.tradezilla.com)**, built specifically to run smoothly on a **Raspberry Pi 3 Model B (1 GB RAM)** inside Docker.

**100% Deterministic Quantitative Analytics — Zero AI / No LLM Dependencies.**

---

## 🌟 Key Features

### 1. Executive Dashboard (TradeZella Style)
- **Core KPIs**: Net Cumulative P&L, Win Rate %, Profit Factor, Total Trades, Winning/Losing/Breakeven counts, Average Win, Average Loss, Win/Loss Ratio, Largest Win, Largest Loss.
- **Risk Metrics**: Expected Value per trade (Expectancy), Sharpe Ratio, Maximum Drawdown ($ and %), Win/Loss Streaks.
- **Interactive Calendar Heatmap**: Month-by-month interactive calendar showing daily profit (green) and loss (red) with trade count badges. Clicking any day immediately filters the trade log.
- **Growth & Distribution Charts**: Cumulative Equity Curve and Daily Net P&L bar charts rendered via lightweight canvas.

### 2. TradingView Lightweight Charts Integration
- Embedded offline bundle of **[TradingView Lightweight Charts v4](https://github.com/tradingview/lightweight-charts)** (no external CDN required).
- Candlestick series and Volume histogram.
- **Visual Trade Markers**: Upward green arrow for Buy entries, downward red arrow for Sell entries, and circle marker for exits with net P&L.
- **Price Levels**: Horizontal dashed lines for Entry Price (Blue), Stop Loss (Red), and Take Profit (Green).
- **Timeframe Switcher**: Interactive 1m, 5m, 15m, 1h, 4h, and 1D views.

### 3. Broker & Account Connectivity (Read-Only)
- **MetaTrader 5 (MT5)**: Includes ready-to-use Expert Advisor `TradeJournalSync.mq5`. Pushes balance, equity, closed deals, open positions, and market candlestick bars to the journal server via secure HTTP WebRequest.
- **MetaTrader 4 (MT4)**: Includes ready-to-use Expert Advisor `TradeJournalSync.mq4`. Reads order history, account balance, and sends candle bars.
- **cTrader Open API 2.0**: Direct cloud connection via cTrader Open API to fetch account details, balance, equity, and closed deals without needing an open terminal.
- **Universal Statement Importer**: Drag-and-drop support for:
  - MetaTrader 4 Detailed Statement (HTML)
  - MetaTrader 5 Report (HTML & CSV)
  - cTrader Deals history (CSV)
  - TradeZella format export (CSV)
- **Multi-Account Support**: Manage multiple prop firm accounts (e.g. FTMO, FundedNext) and personal broker accounts with individual currency, leverage, and equity curves.

### 4. Advanced Playbooks & Psychology
- **Playbooks (Setups)**: Define strategies (e.g., Break & Retest, Order Block / FVG, Trend Continuation), checklists, rules, and target Risk:Reward ratios. Automatically calculates strategy win rate and ROI.
- **Mistakes & Psychology**: Track emotional errors (FOMO, Moved Stop Loss, Overleveraged, Revenge Trading). Calculates the exact dollar amount lost to each mistake.
- **Psychological Ratings**: Tag trades with emotional state (Disciplined, Confident, Anxious, FOMO) and 1–5 star execution ratings.

### 5. Deep Analytics & Reports
- Performance by **Day of the Week** (Monday through Sunday win rates & P&L).
- Performance by **Hour of the Day** (Session profitability: London, New York, Asian).
- Performance by **Symbol / Asset** (EURUSD, GBPUSD, XAUUSD, US30, BTCUSD).
- Performance by **Playbook / Setup**.
- Cost of **Mistakes**.

---

## 🍓 Raspberry Pi 3 Model B (1 GB RAM) Optimization

The Raspberry Pi 3 Model B has 1 GB of shared RAM. This journal server has been specifically engineered for minimal memory and CPU usage:

| Metric | Measurement / Configuration |
| :--- | :--- |
| **Container RAM Usage** | **~40 MB – 65 MB RAM** (Under ordinary operations) |
| **Docker Memory Cap** | `mem_limit: 350M` (Strictly guaranteed to not crash the Pi) |
| **Database Engine** | SQLite 3 with **WAL (Write-Ahead Logging)** mode and memory cache |
| **SD Card Protection** | `PRAGMA synchronous = NORMAL;`, minimal I/O wear on MicroSD cards |
| **Static Assets** | Local offline standalone bundle, zero external network queries |
| **Architecture** | Multi-arch: `linux/arm/v7` (32-bit), `linux/arm64` (64-bit), `linux/amd64` |

---

## 🚀 Quick Start with Docker (Raspberry Pi or PC)

### 1. Clone the repository
```bash
git clone https://github.com/your-username/Trading-Journal-Server-Raspi.git
cd Trading-Journal-Server-Raspi
```

### 2. Start the container
```bash
docker compose up -d --build
```

### 3. Open the Web Application
Open your web browser and navigate to:
```
http://<YOUR_RASPBERRY_PI_IP>:8000
```
*(Or `http://localhost:8000` if running on your local machine)*

To view live logs:
```bash
docker compose logs -f
```

---

## 🔌 Connecting MetaTrader 4, MetaTrader 5 & cTrader

### A. MetaTrader 5 (MT5) Setup
1. In the Web UI, go to the **Accounts & Sync** tab.
2. Click **Download MT5 EA (`TradeJournalSync.mq5`)** or download it from:
   `http://<server-ip>:8000/static/downloads/TradeJournalSync.mq5`
3. In MetaTrader 5:
   - Go to **File ➔ Open Data Folder**.
   - Navigate to `MQL5/Experts/` and place `TradeJournalSync.mq5` inside.
   - In MetaEditor, press **Compile** (or restart MetaTrader 5).
4. Go to **Tools ➔ Options ➔ Expert Advisors**:
   - Check **Allow WebRequest for listed URL**.
   - Add your server URL: `http://<YOUR_RASPBERRY_PI_IP>:8000`
5. Drag `TradeJournalSync` onto any chart:
   - Set `InpServerUrl` = `http://<YOUR_RASPBERRY_PI_IP>:8000/api/sync/mql`
   - Set `InpApiKey` = *(Copy from the Accounts tab in the Web UI)*
   - Set `InpSyncCandles` = `true`
6. The EA will immediately synchronize your closed trades, current balance, equity, open positions, and M15 candlestick bars for chart replay!

---

### B. MetaTrader 4 (MT4) Setup
1. In the Web UI, download `TradeJournalSync.mq4`.
2. In MetaTrader 4:
   - Go to **File ➔ Open Data Folder ➔ MQL4/Experts/** and paste the file.
   - Compile in MetaEditor or restart MT4.
3. Go to **Tools ➔ Options ➔ Expert Advisors**:
   - Check **Allow WebRequest for listed URL** and add `http://<YOUR_RASPBERRY_PI_IP>:8000`.
4. Attach `TradeJournalSync` to any chart and enter your API Key.

---

### C. cTrader Open API Setup
1. Log in to your **Spotware / cTrader Open API** developer portal ([openapi.ctrader.com](https://openapi.ctrader.com)).
2. Create an Application to receive your **Client ID** and **Client Secret**.
3. Generate an **Access Token** for your trading account.
4. In the Journal Web UI, go to **Accounts & Sync ➔ cTrader Open API**:
   - Select target account.
   - Enter `Client ID`, `Client Secret`, `Access Token`, and `cTrader Account ID`.
   - Click **⚡ Sync cTrader Now**.

---

### D. Universal File Import
If you prefer not running an EA:
1. Export a report from MT4 (Detailed Statement HTML), MT5 (Report HTML or CSV), cTrader (Deals CSV), or TradeZella (CSV).
2. Go to **Accounts & Sync ➔ Universal Statement Importer**.
3. Select the target account and drop the file onto the dropzone. All trades will be parsed and imported with automatic duplicate protection!

---

## 🧪 Running Locally & Testing (Without Docker)

### Prerequisites
- Python 3.10+
- `pip`

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run Tests
```bash
python -m unittest discover tests
```

### Start the Server
```bash
python -m server.main
```
Navigate to `http://localhost:8000`.

---

## 📂 Project Structure

```
Trading-Journal-Server-Raspi/
├── Dockerfile                     # Multi-arch Docker build for ARM64/ARMv7/AMD64
├── docker-compose.yml             # Container orchestration with 350MB memory limit
├── requirements.txt               # Lightweight Python dependencies
├── README.md                      # Complete documentation and setup guide
├── server/
│   ├── main.py                    # FastAPI server entry point & lifespan
│   ├── database.py                # SQLite schema, WAL mode & memory optimizations
│   ├── models.py                  # Pydantic schemas (Trades, Accounts, Candles)
│   ├── analytics.py               # Pure math/statistics engine (Zero AI)
│   ├── seed_demo.py               # Realistic demo data generator
│   ├── connectors/
│   │   ├── mql_receiver.py        # MT4 / MT5 webhook receiver & candle processor
│   │   ├── ctrader_api.py         # cTrader Open API connector
│   │   ├── statement_parser.py    # MT4/MT5 HTML/CSV and cTrader CSV parser
│   │   └── market_data.py         # Candlestick provider for Lightweight Charts
│   ├── routers/
│   │   ├── accounts.py            # Account CRUD & API Key management
│   │   ├── trades.py              # Trade log filtering, pagination & CSV export
│   │   ├── dashboard.py           # Dashboard KPIs, calendar heatmap & equity curve
│   │   ├── analytics.py           # Day of week, hour of day, symbol reports
│   │   ├── playbooks.py           # Playbook setups management
│   │   ├── mistakes.py            # Mistakes & behavioral errors tracking
│   │   └── sync.py                # MQL webhook, cTrader sync, statement import
│   └── static/
│       ├── index.html             # TradeZella-style Single Page App
│       ├── css/
│       │   └── app.css            # Dark theme stylesheet
│       ├── js/
│       │   ├── lightweight-charts.standalone.production.js # TradingView bundle
│       │   ├── api.js             # REST API client
│       │   ├── dashboard.js       # Calendar heatmap & canvas charts
│       │   ├── trades.js          # Trades datagrid & modal forms
│       │   ├── trade_detail.js    # TradingView Lightweight Charts renderer
│       │   ├── analytics.js       # Deep statistical breakdown reports
│       │   ├── playbooks.js       # Setups & mistakes views
│       │   ├── accounts.js        # Broker sync & statement importer
│       │   └── app.js             # Navigation router & notifications
│       └── downloads/
│           ├── TradeJournalSync.mq4 # Expert Advisor for MetaTrader 4
│           └── TradeJournalSync.mq5 # Expert Advisor for MetaTrader 5
├── data/                          # SQLite database directory (mounted in Docker)
└── tests/
    ├── test_database.py           # Database & WAL mode tests
    ├── test_analytics.py          # Math & statistics verification tests
    ├── test_statement_parser.py   # Statement file parser tests
    └── test_api.py                # API endpoints integration tests
```

---

## 🔒 Security & Privacy
- **100% Self-Hosted**: Your trading data never leaves your Raspberry Pi.
- **Read-Only**: The MQL EAs and cTrader connectors only read trading data and can never place or alter orders.
- **No External Cloud Subscriptions**: No paid third-party API dependencies (like MetaApi).

---

## 📄 License
MIT License. Free for personal and commercial trading journal use.

# Trading Journal Server — Agent & Developer Guide (`AGENTS.md`)

Welcome to the **Trading-Journal-Server** project! This document serves as the central knowledge base for AI assistants (Google Antigravity / Gemini CLI) and developers to quickly navigate the codebase and strictly adhere to existing conventions.

---

## 1. Project Overview & Philosophy

- **Purpose:** A self-hosted, professional trading journal (TradeZella alternative) with dashboard, trade log, playbooks, psychology tracking, interactive TradingView Lightweight Charts, screenshots, and native connectors for cTrader and MetaTrader.
- **Philosophy:** 
  - **100% deterministic / "Zero AI" in the backend:** All metrics, calculations, and data processing are purely mathematical and rule-based. No LLMs in the backend core.
  - **No frontend build step:** The frontend uses modular vanilla JavaScript and CSS. There is no Node.js/Webpack/Vite/React build. HTML and JS are served directly as static files by FastAPI.
  - **Data sovereignty:** All data resides locally in an SQLite database (`data/journal.db`) in WAL mode.

---

## 2. Technology Stack

- **Backend:** Python 3.10+ with [FastAPI](https://fastapi.tiangolo.com/), Uvicorn, Pydantic v2.
- **Database:** SQLite with WAL (`PRAGMA journal_mode=WAL`), foreign keys (`PRAGMA foreign_keys=ON`).
- **Frontend:** Vanilla JavaScript (ES6+), HTML5, CSS3, [TradingView Lightweight Charts v5](https://tradingview.github.io/lightweight-charts/).
- **Deployment:** Docker & Docker Compose (multi-stage Python 3.12-slim image) on a Raspberry Pi / Linux server.
- **Broker Connectors:**
  - **cTrader:** C# cBot (`TradeJournalSync.cbot.cs`) via HTTP Push (`/api/sync/ctrader-push`) + optional Open API (`ctrader_api.py`).
  - **MetaTrader 5:** MQL5 EA (`TradeJournalSync.mq5`) via WebRequest (`/api/sync/mql`).
  - **MetaTrader 4:** MQL4 EA (`TradeJournalSync.mq4`).
  - **Manual / Statement Import:** HTML/CSV parser for MT4, MT5, cTrader, and TradeZella (`statement_parser.py`).

---

## 3. Directory Structure & Responsibilities

```text
Trading-Journal-Server/
├── AGENTS.md                  # This guidance document
├── README.md                  # User documentation & setup guide
├── Dockerfile                 # Docker container definition (Python 3.12-slim)
├── docker-compose.yml         # Container setup with port 8000 & ./data volume mount
├── requirements.txt           # Python dependencies
├── data/                      # Local data folder (contains journal.db, gitignored)
├── server/
│   ├── main.py                # FastAPI app, middleware (Basic Auth), router mounts
│   ├── database.py            # SQLite schema, connection helper, automatic migrations
│   ├── models.py              # Pydantic schemas & validations
│   ├── analytics.py           # Mathematical metrics (Win Rate, Expectancy, Drawdown, etc.)
│   ├── connectors/
│   │   ├── mql_receiver.py    # Ingestion of MT4/MT5 and cBot payloads, order transitions
│   │   ├── ctrader_api.py     # Optional direct cTrader Open API integration
│   │   ├── market_data.py     # Candlestick preparation & markers for Lightweight Charts
│   │   └── statement_parser.py# CSV/HTML parser for offline imports
│   ├── routers/
│   │   ├── accounts.py        # Account management & Journal API key generation
│   │   ├── trades.py          # Trade CRUD, filters, pagination, partial exits, screenshots
│   │   ├── dashboard.py       # KPIs for the main dashboard
│   │   ├── analytics.py       # Detailed analytics evaluations
│   │   ├── playbooks.py       # Setup playbooks (strategies & checklists)
│   │   ├── mistakes.py        # Trading mistake categories & severities
│   │   └── sync.py            # Endpoints for broker synchronization & candle upload
│   └── static/
│       ├── index.html         # Single-Page Application UI
│       ├── css/app.css        # Styles, themes, and badges
│       ├── downloads/         # Downloadable cBot (`.cs`) and EA files (`.mq5`, `.mq4`)
│       └── js/
│           ├── api.js         # HTTP client wrapper
│           ├── app.js         # Global app navigation, account switching, formatting
│           ├── trades.js      # Trade table, filters, add/edit modal
│           ├── trade_detail.js# Detail modal with TradingView chart replay & screenshots
│           ├── dashboard.js   # Dashboard metrics & calendar heatmap
│           ├── analytics.js   # Analytics charts & tables
│           ├── playbooks.js   # Playbook & mistake management
│           └── accounts.js    # Account management & statement import
└── tests/
    ├── test_api.py            # Integration tests for all REST routes & sync workflows
    ├── test_analytics.py      # Mathematical correctness of KPIs and equity curves
    ├── test_chart_data.py     # Replay candles and marker logic
    ├── test_connectors.py     # Broker parsers and connectors
    └── test_database.py       # Schema initialization and isolation
```

---

## 4. Key Business & Architectural Rules

1. **Strict Schema Integrity & Additive Migrations:**
   - The file `server/database.py` is the **single source of truth** for the SQLite schema.
   - All table additions must be **backward compatible**.
   - Always include a migration check for new columns (using `PRAGMA table_info(...)` and `ALTER TABLE ... ADD COLUMN ...`) so existing production databases migrate safely on server startup without data loss.
   - The file `data/journal.db` is gitignored and must never be overwritten.

2. **Trade Lifecycle & Status:**
   - Valid status values: `"PENDING"`, `"OPEN"`, `"CLOSED"`, `"WIN"`, `"LOSS"`, `"BE"`, `"CANCELLED"`.
   - **Limit & Stop Orders (`PENDING`):**
     - Imported by the cBot or MT5 EA before execution.
     - Must **not** distort PnL KPIs (win rate, profit factor, net profit, equity curve).
     - Displayed in the frontend with a `LIMIT` badge and limit price.
     - The trader can already record notes, playbook setups, and screenshots while waiting for the fill.
   - **Fill Transition (`PENDING` -> `OPEN`):**
     - When the broker executes the order, `mql_receiver.py` links the `order_id` to the new position.
     - **Essential:** Already recorded notes, playbooks, and screenshots must be 100% preserved (`CASE WHEN notes != '' THEN notes ELSE ...`).
   - **Cancellation (`CANCELLED`):**
     - When a pending order is cancelled or expires in the broker, the connector sets the status to `CANCELLED`.

3. **Partial Exits & Scale-outs:**
   - In cTrader, each partial execution generates a deal.
   - In the journal, the original position is retained as the parent trade; partial exits are stored in the `trade_partial_closes` table and aggregate PnL, volume, and weighted exit price.

4. **Multi-Currency Handling:**
   - Each account has a fixed account currency (`USD`, `EUR`, `GBP`).
   - All amounts (PnL, balance, equity) are formatted in the UI via `App.formatMoney(amount, currency)` with the correct currency symbol.

---

## 5. Test & Validation Routines

Before any commit or deployment, the following checks **must** be executed:

### 1. Python Test Suite (34+ Tests)
Tests run in isolation in RAM with temporary SQLite databases:
```bash
python -m unittest discover tests
```

### 2. JavaScript Syntax Validation (Vanilla JS)
Since there is no bundler, check for syntax errors using Node.js:
```powershell
Get-ChildItem -Path "server/static/js/*.js" | ForEach-Object { node -c $_.FullName }
```

---

## 6. Remote Deployment (Raspberry Pi / Linux Server)

- **Target System:** Raspberry Pi / Linux server (e.g., `<SERVER_IP>`, User: `<USER>`, SSH Port: 22).
- **Target Directory:** `/home/<USER>/Trading-Journal-Server`
- **Docker Container:** `trading-journal` (exposed on port 8000).
- **Deployment Script:** `scratch/deploy.py` (executes SFTP upload excluding `.git`, `__pycache__`, and `journal.db`, and remotely rebuilds the Docker container).
- **Server Commands:**
  ```bash
  cd /home/<USER>/Trading-Journal-Server
  docker compose down
  docker compose build
  docker compose up -d
  curl -s http://localhost:8000/api/health
  ```
- **Live URL:** `http://<SERVER_IP>:8000`

---

## 7. Behavioral Guidelines for AI Assistants

- Respond to the user by default in **German**, unless they explicitly write in English.
- Never modify existing comments or docstrings that are not directly related to the task.
- Always use clickable markdown links for file references and symbols in the format `[Filename](file:///path)`.
- Always run local tests (`python -m unittest discover tests`) and JS checks before deployments.
- Never overwrite the production database on the server.

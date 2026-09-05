# Trading Journal Server

A self-hosted trading journal featuring a dashboard, trade log, playbooks,
analytics, TradingView charts, screenshots, and native integrations for
MetaTrader and cTrader. The application runs locally on your computer or server
and stores all data in an SQLite database.

All analytics are deterministic and do not require any AI or LLM services.

## Features

- Dashboard with P&L, Win Rate, Profit Factor, Expectancy, Drawdown, and Equity curve
- Trade log with search, filtering, editing, and collapsible detail rows
- Partial profits and scale-outs tracked under a single parent trade
- TradingView Lightweight Charts with candles, volume, entry/exit markers, and SL/TP price lines
- Playbooks with setup name, description, and rules/checklist
- Trade notes, captions, and multiple TradingView screenshots per trade
- Screenshot thumbnails and fullscreen slideshow with arrow-key navigation and ESC to close
- Trading mistake and psychology categories with execution rating
- Multi-account management
- MT4 / MT5 synchronization via an Expert Advisor
- cTrader synchronization via a locally running cBot without cTrader OAuth tokens
- Optional cTrader Open API integration
- Statement importer for MT4, MT5, cTrader, and TradeZella statements
- CSV export for the trade log

## Prerequisites

For Docker installation:

- Docker Engine
- Docker Compose v2

For local installation without Docker:

- Python 3.10 or newer
- pip

For automatic broker synchronization, MetaTrader or cTrader must run on the
machine sending data to the journal server. The server must be reachable from
that network.

## Installation with Docker

This is the recommended installation method.

### 1. Clone the repository

~~~bash
git clone <REPOSITORY_URL> trading-journal-server
cd trading-journal-server
~~~

If the repository is already present locally, navigate directly into its
project directory.

### 2. Create the data directory

Linux/macOS:

~~~bash
mkdir -p data
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Path data -Force
~~~

The `data` directory holds the SQLite database and persists across container rebuilds.

### 3. Configure access (recommended)

Copy the example configuration:

~~~bash
cp .env.example .env
~~~

Windows PowerShell:

~~~powershell
Copy-Item .env.example .env
~~~

By default, the service is accessible only on localhost. To allow access from a
trusted local network, set `HOST_BIND_ADDRESS` to `0.0.0.0` in `.env`.
Optionally, set `JOURNAL_USERNAME` and `JOURNAL_PASSWORD` to protect the web
interface and management API with HTTP Basic Auth. Both values must be set together.

### 4. Build and start the container

~~~bash
docker compose up -d --build
~~~

The application is then reachable at:

~~~text
http://localhost:8000
~~~

If the server is exposed to your local network, use its network IP address:

~~~text
http://<SERVER-IP>:8000
~~~

### 5. Verify the installation

~~~bash
docker compose ps
curl http://localhost:8000/api/health
~~~

The API should return a status of `healthy`. Interactive FastAPI documentation
is available at `http://localhost:8000/docs`.

## Docker Operations

~~~bash
# View live logs
docker compose logs -f

# Stop container
docker compose stop

# Start container
docker compose start

# Remove container while preserving the data folder
docker compose down

# Rebuild and restart after an update
git pull
docker compose up -d --build
~~~

Do not delete the `data` directory if you want to keep your journal data.

### Backup

Stop the container prior to making a backup if possible:

~~~bash
docker compose stop
~~~

Then copy the `data/journal.db` file or the entire `data` directory.
Afterward, restart the container:

~~~bash
docker compose start
~~~

Backups should be performed regularly and stored on a separate physical drive or storage device.

## Local Installation without Docker

### 1. Create a virtual environment

Windows PowerShell:

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
~~~

Linux/macOS:

~~~bash
python3 -m venv .venv
source .venv/bin/activate
~~~

If PowerShell blocks script execution, you can bypass the execution policy for
the current terminal session:

~~~powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
~~~

### 2. Install dependencies

~~~bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
~~~

### 3. Start the server

~~~bash
python -m server.main
~~~

The application is then reachable at `http://localhost:8000`.

The SQLite database is automatically created at `data/journal.db` on first startup.
A custom data directory can be specified via the `DB_DIR` environment variable:

Linux/macOS:

~~~bash
DB_DIR=/path/to/journal-data python -m server.main
~~~

Windows PowerShell:

~~~powershell
$env:DB_DIR = "C:\path\to\journal-data"
python -m server.main
~~~

## Initial Setup in the Web Interface

1. Open the application and navigate to **Accounts & Sync**.
2. Click **Add Trading Account** to create an account.
3. Enter the platform, account number, and optional broker/server name.
4. Save the account.
5. For MT4, MT5, and the cTrader cBot, a **Journal API Key** is generated automatically.

The Journal API Key belongs solely to this journal server. It is neither a
broker password nor a cTrader Open API token.

## MetaTrader 4 and MetaTrader 5

The MetaTrader connector uses the bundled Expert Advisor. The server does not
require any MetaTrader credentials or third-party service tokens.

### Setup

1. In **Accounts & Sync**, create an account with platform **MT4** or **MT5**.
2. Copy the displayed **Journal API Key**.
3. Download the corresponding file from `server/static/downloads/`:
   - `TradeJournalSync.mq4` for MT4
   - `TradeJournalSync.mq5` for MT5
4. Copy the file into your MetaTrader `Experts` folder.
5. Restart MetaTrader or refresh the Navigator window.
6. Attach the Expert Advisor to a chart and configure its inputs:

~~~text
Server URL: http://<SERVER-IP>:8000/api/sync/mql
API Key:    <JOURNAL_API_KEY>
~~~

7. In MetaTrader under **Tools → Options → Expert Advisors**, allow the server
   URL under **Allow WebRequest for listed URL**. Specifying the base URL is sufficient:

~~~text
http://<SERVER-IP>:8000
~~~

8. Enable the Expert Advisor and ensure the **AutoTrading** / **Algo Trading**
   button in MetaTrader is activated.

The Expert Advisor transmits balance, equity, open positions, closed trades,
and candlestick data. It cannot place, modify, or close orders. The MetaTrader
terminal must remain running for new data to sync.

## cTrader cBot without Open API Tokens

The cTrader cBot is the local push alternative to the MetaTrader EA. It requires
no cTrader client secret or OAuth access token.

### Setup

1. In **Accounts & Sync**, create an account with platform **cTrader**.
2. Copy the **Journal API Key** for this account.
3. Download `TradeJournalSync.cbot.cs` from `server/static/downloads/`.
4. In cTrader, open **Algo** and create a new C# cBot.
5. Replace the template code completely with the downloaded code.
6. Build the cBot.
7. Configure the parameters:

~~~text
Journal Server URL: http://<SERVER-IP>:8000/api/sync/ctrader-push
Journal API Key:    <JOURNAL_API_KEY>
~~~

Additionally, the sync lookback period, synchronization interval, and number of
M15 candles can be customized.

8. Start the cBot on the computer running cTrader.

The cBot must be able to reach the journal server over the network. If the
server is on the local network, do not use `localhost`; enter the server's actual
LAN IP address or resolvable hostname instead.

The cBot reads account information, positions, historical deals, and candles.
It never places trade orders. Partial closes are grouped under a single shared
journal trade based on their position ID.

## cTrader Open API (Optional)

As an alternative to the local cBot, the server-side cTrader Open API connector
can be used. This approach requires cTrader Open API application credentials.

1. Create an application in the cTrader Open API portal.
2. Note your Client ID and Client Secret.
3. Generate an Access Token for the desired account.
4. Have your numeric cTrader Account ID ready.
5. In **Accounts & Sync → cTrader Open API**, select the account and environment.
6. Enter Client ID, Client Secret, Access Token, and cTrader Account ID.
7. Click **Sync cTrader Now**.

This connector performs read-only requests exclusively. The credentials are
stored per-account and should be treated like passwords.

## Trade Log and Screenshots

### Collapsible Trade Rows

Click on any trade row in the **Trade Log** to expand it. The complete trade
details load inline below the row, including partial exits, notes, and screenshots.
Clicking the same main row again collapses the details.

Action buttons for Chart, Edit, and Delete remain accessible independently.

### Adding TradingView Screenshots

1. Expand a trade in the Trade Log or open it via the **Chart** modal.
2. In the **Trade Screenshots** section, paste the TradingView link, for example:

~~~text
https://www.tradingview.com/x/oo0a7Ei5/
~~~

3. Optionally enter a caption such as `Entry`, `TP1`, or `News`.
4. Click **Add Screenshot**.

The direct image URL is resolved automatically according to this pattern:

~~~text
https://s3.tradingview.com/snapshots/<first-char-lowercase>/<pattern>.png
~~~

Example:

~~~text
https://www.tradingview.com/x/oo0a7Ei5/
→ https://s3.tradingview.com/snapshots/o/oo0a7Ei5.png
~~~

Multiple screenshots can be attached to the same trade. Thumbnails appear
directly beneath the trade. Clicking a thumbnail opens the fullscreen slideshow;
navigate with arrow keys and press ESC to close.

The application stores the source URL, direct image URL, and caption. The PNG
image files are not stored in SQLite; the browser loads them directly from the
source URL.

## Playbooks

A playbook setup consists of:

- Setup Name
- Description
- Rules / Checklist

A trade can be assigned to a playbook in the trade details. Performance, Win
Rate, and P&L metrics are automatically aggregated per setup.

## Importing Statements

Under **Accounts & Sync → Universal Statement Importer**, historical trades
can be imported from broker files. Supported formats:

- MT4 Detailed Statement as HTML
- MT5 Report as HTML or CSV
- cTrader Deals as CSV
- TradeZella-compatible CSV files

Select the target account before importing. Existing trades are deduplicated
based on their account ID and ticket number.

## API and Important Endpoints

FastAPI documentation is available at `/docs`. Key endpoints:

| Purpose | Method | Endpoint |
|---|---:|---|
| Health check | GET | /api/health |
| Accounts | GET/POST | /api/accounts |
| Trades | GET/POST | /api/trades |
| Trade details | GET | /api/trades/{trade_id} |
| Screenshots | GET/POST/DELETE | /api/trades/{trade_id}/screenshots |
| Playbooks | GET/POST/PUT/DELETE | /api/playbooks |
| MT4/MT5 EA push | POST | /api/sync/mql |
| cTrader cBot push | POST | /api/sync/ctrader-push |
| cTrader Open API | POST | /api/sync/ctrader |

The EA and cBot sync endpoints require the Journal API Key in the HTTP request header:

~~~http
X-API-Key: <JOURNAL_API_KEY>
~~~

## Security

- The Docker configuration binds the service to `127.0.0.1` by default. Only set
  `HOST_BIND_ADDRESS=0.0.0.0` when trusted devices on the local network need access.
- To protect the web UI and management API, set `JOURNAL_USERNAME` and `JOURNAL_PASSWORD`
  in `.env`. The push endpoints for the EA and cBot remain accessible with their
  account-specific Journal API key.
- Never expose the journal server directly to the public internet without protection.
- For remote access, use a VPN or a reverse proxy with HTTPS.
- Do not commit Journal API keys or share them in public repositories or screenshots.
- Protect the `data` directory and `journal.db` from unauthorized access.
- When using cTrader Open API, treat the Client Secret and Access Token like passwords.
- Use the automatically generated unique Journal API Key for each account.
- When upgrading from an older release, re-enter the Journal API Key into your EA
  or cBot: Any earlier public demo key is rotated automatically on startup.

## Tests

Activate your virtual environment and run from the project root:

~~~bash
python -m unittest discover tests
python -m compileall -q server tests
~~~

## Project Structure

~~~text
trading-journal-server/
├── Dockerfile
├── docker-compose.yml
├── .env.example                # Secure sample configuration
├── LICENSE
├── SECURITY.md
├── THIRD_PARTY_NOTICES.md
├── requirements.txt
├── README.md
├── server/
│   ├── main.py                  # FastAPI application & lifespan
│   ├── database.py              # SQLite schema & initialization
│   ├── models.py                # Pydantic data models
│   ├── analytics.py             # Statistical calculations & metrics
│   ├── connectors/
│   │   ├── mql_receiver.py      # MT4/MT5 EA & cBot ingestion
│   │   ├── ctrader_api.py       # Optional cTrader Open API
│   │   ├── statement_parser.py  # HTML/CSV statement import
│   │   └── market_data.py       # Candlestick data & chart markers
│   ├── routers/
│   │   ├── accounts.py
│   │   ├── trades.py
│   │   ├── dashboard.py
│   │   ├── analytics.py
│   │   ├── playbooks.py
│   │   ├── mistakes.py
│   │   └── sync.py
│   └── static/
│       ├── index.html
│       ├── css/app.css
│       ├── js/
│       └── downloads/
│           ├── TradeJournalSync.mq4
│           ├── TradeJournalSync.mq5
│           └── TradeJournalSync.cbot.cs
├── data/                        # Persistent SQLite database
└── tests/
~~~

## License

MIT License. Free to use for private and commercial trading journals.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`AGENTS.md` is the primary project guide (business rules, trade lifecycle, deployment) and is authoritative; this file summarizes it and adds what is not written there. Key conventions from it:

- Reply to the user in **German** unless they write in English.
- Backend stays 100% deterministic — no LLM/AI calls in server code (`/api/health` reports `ai_enabled: false` and a test asserts it).
- No frontend build step: vanilla JS/CSS served as static files. Don't introduce npm, bundlers, frameworks, or ES modules.
- Never touch `data/journal.db` (local or on the Pi). Don't modify unrelated comments/docstrings.

## Commands

```bash
# Run server locally (http://localhost:8000, API docs at /docs)
python -m server.main

# Full Python test suite (unittest, not pytest)
python -m unittest discover tests

# Single file / class / test
python -m unittest tests.test_api
python -m unittest tests.test_api.TestAPI.test_health_check

# Frontend regression tests (Node built-in test runner, loads raw JS into a vm sandbox)
node --test tests/frontend_regressions.test.js

# JS syntax check (no bundler, so this is the "lint")
node -c server/static/js/trades.js

# Byte-compile check
python -m compileall -q server tests

# Docker
docker compose up -d --build
```

Run the Python suite and JS syntax checks before any commit/deploy. `DB_DIR` selects the data directory (default `./data`); it is read at call time, so tests point it at a `tempfile.TemporaryDirectory()` and call `init_db()` in `setUpClass`.

Deployment to the Raspberry Pi is done by `scratch/deploy.py` (gitignored, SFTP upload + remote `docker compose` rebuild; excludes `data/`, `.env`, `journal.db*`).

## Architecture

**Request flow:** `server/main.py` builds the FastAPI app, runs `init_db()` in the lifespan, starts a background loop that calls the cTrader Open API sync every 5 minutes (via `asyncio.to_thread`), and serves `index.html` for the SPA routes (`/dashboard`, `/trades`, …). An optional Basic-Auth middleware (`JOURNAL_USERNAME`/`JOURNAL_PASSWORD`) protects everything except `_UNPROTECTED_PATHS` — the EA/cBot push endpoints authenticate instead via the per-account `X-API-Key` (the account's `api_key`). New unauthenticated endpoints must be added to that set deliberately.

**Database (`server/database.py`):** raw `sqlite3`, no ORM. `get_connection()` is a context manager that sets WAL/foreign-key pragmas; rows are `sqlite3.Row`, converted with `dict(row)`. Schema changes require updating **both** the `CREATE TABLE IF NOT EXISTS` statement and the `PRAGMA table_info` → `ALTER TABLE ADD COLUMN` migration list for that table, so existing production DBs upgrade on startup. One-off data fixes go through `_run_once()` (recorded in `app_migrations`) so they never re-run on later starts; never add unconditional UPDATE/DELETE cleanups to `init_db()`. Uvicorn runs with a single worker because of SQLite.

**Ingestion paths** — all converge on the `trades` table, deduplicated by `(account_id, ticket)`:
- `POST /api/sync/mql` (MT4/MT5 EA) and `POST /api/sync/ctrader-push` (cBot) both accept `MQLSyncPayload` and go through `process_mql_payload()` in `connectors/mql_receiver.py`: updates account balances, writes `equity_history`, upserts trades (including PENDING→OPEN transitions matched by order/position id against `mt4-order-*` / `mt5-order-*` / `ctrader-order-*` tickets while preserving user-entered notes/playbook/screenshots), stores partial closes, and saves `market_candles`. For `source == "mql"` payloads that include `open_trades`, `_reconcile_stale_open_trades()` resolves OPEN rows missing from that snapshot: journal data is merged into the matching closed record, otherwise the row becomes `CANCELLED` (never deleted; `manual_*` tickets are skipped).
- `connectors/ctrader_api.py` — optional server-side Open API pull.
- `connectors/statement_parser.py` — HTML/CSV statement upload via `POST /api/sync/import`.
- The EA/cBot sources live in `server/static/downloads/`; `tests/test_ea_contracts.py` checks their source text and payload shape against `MQLSyncPayload` (it does not compile MQL). Changing payload fields requires keeping the EAs, the Pydantic model, and these tests in sync.

**Analytics:** `server/analytics.py` holds pure functions over lists of trade dicts (with `partial_closes` attached). Routers (`routers/analytics.py::_fetch_filtered_trades`, `routers/dashboard.py`) fetch and filter rows, then call these functions; `/api/dashboard` additionally returns `insights` from `get_dashboard_insights()` (R distribution, long/short, hold times, day stats, monthly results, and a 0–100 journal score whose six component formulas are listed in `_journal_score()`). PnL KPIs must count only realized statuses (`CLOSED`, `WIN`, `LOSS`, `BE`) and exclude `is_missed = 1` trades; `PENDING`/`OPEN`/`CANCELLED` must not distort metrics.

**Trade detail grouping:** `routers/trades.py::_get_trade_with_partials` builds the detail response: attaches partial closes and screenshots, and detects sibling legs to return `is_grouped`, `grouped_count`, `grouped_*` totals, `sub_trades`, and `multiple_tps`. Sibling rule (must stay identical to `Trades.groupOpenTrades()` in `trades.js`): same account/symbol/direction, same status category (WIN/LOSS/BE/CLOSED count as one), `open_price` equal at 4 decimals, not missed, and chained by open-time gaps ≤ 2 h. The frontend uses the `grouped_*` values for live PnL of grouped positions.

**Charts:** `connectors/market_data.py` prepares Lightweight Charts candles/markers from `market_candles` (`/api/sync/chart-data/{trade_id}`, `/api/sync/latest-candle…` for live updates). `prune_market_candles()` runs daily from the background loop in `main.py` and drops only M1/M5 bars older than 45 days that lie outside every trade's replay window.

**Frontend (`server/static/`):** each JS file defines one global object (`API`, `App`, `Trades`, `TradeDetail`, `Dashboard`, …) loaded via plain `<script>` tags in `index.html`, with `app.js` last (navigation, account switching, `App.formatMoney`, filter params). All HTTP goes through `API.request` in `api.js`. Dashboard/analytics bar charts, rings and sparklines use the dependency-free SVG helpers in `charts.js` (`Charts.bars`, `Charts.ring`, …, tooltips via `data-tip`); the equity curve uses Lightweight Charts with a second pane for drawdown (keep its attribution logo on — the license requires it). Colours and components come from the design tokens at the top of `css/app.css`. `index.html` loads every asset with a `?v=` query string — bump it whenever CSS/JS changes so browsers don't serve stale files after a deploy. `tests/frontend_regressions.test.js` evaluates these files in a Node `vm` context with stubbed `document`/`window`/`API`/`App`, so modules must stay loadable as plain scripts without a real DOM at load time.

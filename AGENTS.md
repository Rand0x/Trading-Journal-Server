# Trading Journal Server — Agent & Developer Guide (`AGENTS.md`)

Willkommen im Projekt **Trading-Journal-Server**! Dieses Dokument dient als zentrale Wissensbasis für AI-Assistenten (Google Antigravity / Gemini CLI) und Entwickler, um sich sofort im Projekt zurechtzufinden und bestehende Konventionen strikt einzuhalten.

---

## 1. Projektübersicht & Philosophie

- **Zweck:** Ein selbst gehostetes, professionelles Trading-Journal (Alternative zu TradeZella) mit Dashboard, Trade-Log, Playbooks, Psychologie-Tracking, interaktiven TradingView Lightweight Charts, Screenshots und nativer Anbindung an cTrader und MetaTrader.
- **Philosophie:** 
  - **100 % deterministisch / "Zero AI" im Backend:** Alle Metriken, Berechnungen und Datenverarbeitungen sind rein mathematisch und regelbasiert. Keine LLMs im Backend-Kern.
  - **Kein Frontend-Build-Step:** Das Frontend verwendet modulares Vanilla JavaScript und CSS. Es gibt kein Node.js/Webpack/Vite/React-Build. HTML und JS werden direkt statisch von FastAPI ausgeliefert.
  - **Datensouveränität:** Alle Daten liegen lokal in einer SQLite-Datenbank (`data/journal.db`) im WAL-Modus.

---

## 2. Technologie-Stack

- **Backend:** Python 3.10+ mit [FastAPI](https://fastapi.tiangolo.com/), Uvicorn, Pydantic v2.
- **Datenbank:** SQLite mit WAL (`PRAGMA journal_mode=WAL`), Foreign Keys (`PRAGMA foreign_keys=ON`).
- **Frontend:** Vanilla JavaScript (ES6+), HTML5, CSS3, [TradingView Lightweight Charts v4](https://tradingview.github.io/lightweight-charts/).
- **Deployment:** Docker & Docker Compose (Multi-Stage Python 3.12-slim Image) auf einem Raspberry Pi / Linux-Server.
- **Broker-Konnektoren:**
  - **cTrader:** C# cBot (`TradeJournalSync.cbot.cs`) via HTTP Push (`/api/sync/ctrader-push`) + optionale Open API (`ctrader_api.py`).
  - **MetaTrader 5:** MQL5 EA (`TradeJournalSync.mq5`) via WebRequest (`/api/sync/mql`).
  - **MetaTrader 4:** MQL4 EA (`TradeJournalSync.mq4`).
  - **Manuell / Statement-Import:** HTML-/CSV-Parser für MT4, MT5, cTrader und TradeZella (`statement_parser.py`).

---

## 3. Verzeichnisstruktur & Verantwortlichkeiten

```text
Trading-Journal-Server/
├── AGENTS.md                  # Dieses Orientierungsdokument
├── README.md                  # Benutzerdokumentation & Setup
├── Dockerfile                 # Docker-Containerdefinition (Python 3.12-slim)
├── docker-compose.yml         # Container-Setup mit Port 8000 & ./data Mount
├── requirements.txt           # Python-Abhängigkeiten
├── data/                      # Lokaler Datenordner (enthält journal.db, gitignored)
├── server/
│   ├── main.py                # FastAPI-App, Middleware (Basic Auth), Router-Mounts
│   ├── database.py            # SQLite Schema, Connection Helper, automatische Migrationen
│   ├── models.py              # Pydantic Schemas & Validierungen
│   ├── analytics.py           # Mathematische Kennzahlen (Win Rate, Expectancy, Drawdown, etc.)
│   ├── connectors/
│   │   ├── mql_receiver.py    # Ingestion von MT4/MT5 und cBot-Payloads, Order-Transitions
│   │   ├── ctrader_api.py     # Optionale direkte cTrader Open API Integration
│   │   ├── market_data.py     # Kerzenaufbereitung & Markierungen für Lightweight Charts
│   │   └── statement_parser.py# CSV/HTML Parser für Offline-Imports
│   ├── routers/
│   │   ├── accounts.py        # Kontenverwaltung & Generierung von Journal API-Keys
│   │   ├── trades.py          # Trade-CRUD, Filter, Paginierung, Partial Exits, Screenshots
│   │   ├── dashboard.py       # KPIs für das Haupt-Dashboard
│   │   ├── analytics.py       # Detaillierte Analytics-Auswertungen
│   │   ├── playbooks.py       # Setup-Playbooks (Strategien & Checklisten)
│   │   ├── mistakes.py        # Trading-Fehlerkategorien & Schweregrade
│   │   └── sync.py            # Endpunkte für Broker-Synchronisation & Kerzen-Upload
│   └── static/
│       ├── index.html         # Single-Page-Application UI
│       ├── css/app.css        # Styles, Themes und Badges
│       ├── downloads/         # Downloadbare cBot (`.cs`) und EA-Dateien (`.mq5`, `.mq4`)
│       └── js/
│           ├── api.js         # HTTP Client-Wrapper
│           ├── app.js         # Globale App-Navigation, Kontowechsel, Formatierungen
│           ├── trades.js      # Trade-Tabelle, Filter, modales Anlegen/Bearbeiten
│           ├── trade_detail.js# Detail-Modal mit TradingView Chart Replay & Screenshots
│           ├── dashboard.js   # Dashboard Metriken & Kalender-Heatmap
│           ├── analytics.js   # Analytics-Charts & Tabellen
│           ├── playbooks.js   # Playbook- & Fehlerverwaltung
│           └── accounts.js    # Kontoverwaltung & Statement-Import
└── tests/
    ├── test_api.py            # Integrationstests für alle REST-Routen & Sync-Workflows
    ├── test_analytics.py      # Mathematische Korrektheit von KPIs und Equity-Kurven
    ├── test_chart_data.py     # Replay-Kerzen und Marker-Logik
    ├── test_connectors.py     # Broker-Parser und Konnektoren
    └── test_database.py       # Schema-Initialisierung und Isolation
```

---

## 4. Wichtige Geschäfts- & Architekturregeln

1. **Strikte Schema-Integrität & Additive Migrationen:**
   - Die Datei `server/database.py` ist die **Single Source of Truth** für das SQLite-Schema.
   - Alle Tabellen-Erweiterungen müssen **abwärtskompatibel** sein.
   - Bei neuen Spalten immer einen Migrations-Check einbauen (mittels `PRAGMA table_info(...)` und `ALTER TABLE ... ADD COLUMN ...`), damit bestehende Produktivdatenbanken beim Server-Start ohne Datenverlust migriert werden.
   - Die Datei `data/journal.db` ist in Git ignoriert und darf niemals überschrieben werden.

2. **Trade Lifecycle & Status:**
   - Gültige Statuswerte: `"PENDING"`, `"OPEN"`, `"CLOSED"`, `"WIN"`, `"LOSS"`, `"BE"`, `"CANCELLED"`.
   - **Limit- & Stop-Orders (`PENDING`):**
     - Werden vom cBot oder MT5 EA importiert, bevor sie ausgeführt werden.
     - Dürfen **keine** PnL-KPIs (Win Rate, Profit Factor, Net Profit, Equity Curve) verzerren.
     - Im Frontend mit Badge `LIMIT` und Limitpreis dargestellt.
     - Der Trader kann Notizen, Playbook-Setups und Screenshots bereits während des Wartens auf den Fill erfassen.
   - **Fill-Transition (`PENDING` -> `OPEN`):**
     - Wenn der Broker die Order ausführt, verknüpft `mql_receiver.py` die `order_id` mit der neuen Position.
     - **Essentiell:** Bereits erfasste Notizen, Playbooks und Screenshots müssen zu 100 % erhalten bleiben (`CASE WHEN notes != '' THEN notes ELSE ...`).
   - **Stornierung (`CANCELLED`):**
     - Wenn eine Pending-Order im Broker gelöscht wird oder abläuft, setzt der Konnektor den Status auf `CANCELLED`.

3. **Teilschließungen (Partial Exits & Scale-outs):**
   - Im cTrader erzeugt jeder Teilabschluss einen Deal.
   - Im Journal wird die ursprüngliche Position als übergeordneter Trade behalten; Teilabschlüsse werden in der Tabelle `trade_partial_closes` gespeichert und summieren PnL, Volumen und gewichteten Ausstiegspreis.

4. **Multi-Währungs-Handling:**
   - Jedes Konto hat eine feste Kontowährung (`USD`, `EUR`, `GBP`).
   - Alle Beträge (PnL, Balance, Equity) werden im UI über `App.formatMoney(amount, currency)` mit dem korrekten Währungssymbol formatiert.

---

## 5. Test- & Validierungsroutinen

Vor jedem Commit oder Deployment **müssen** folgende Prüfungen ausgeführt werden:

### 1. Python Test-Suite (34+ Tests)
Die Tests laufen isoliert im RAM mit temporären SQLite-Datenbanken:
```bash
python -m unittest discover tests
```

### 2. JavaScript Syntax-Prüfung (Vanilla JS)
Da kein Bundler vorhanden ist, Syntaxfehler über Node.js prüfen:
```powershell
Get-ChildItem -Path "server/static/js/*.js" | ForEach-Object { node -c $_.FullName }
```

---

## 6. Remote-Deployment (Raspberry Pi / Linux Server)

- **Zielsystem:** Raspberry Pi / Linux-Server (z. B. `<SERVER_IP>`, User: `<USER>`, SSH-Port: 22).
- **Zielverzeichnis:** `/home/<USER>/Trading-Journal-Server`
- **Docker-Container:** `trading-journal` (Exponiert auf Port 8000).
- **Deployment-Skript:** `scratch/deploy.py` (führt SFTP-Upload unter Ausschluss von `.git`, `__pycache__` und `journal.db` durch und baut den Docker-Container remote neu).
- **Befehle auf dem Server:**
  ```bash
  cd /home/<USER>/Trading-Journal-Server
  docker compose down
  docker compose build
  docker compose up -d
  curl -s http://localhost:8000/api/health
  ```
- **Live-URL:** `http://<SERVER_IP>:8000`

---

## 7. Verhaltensrichtlinien für AI-Assistenten

- Antworte dem Nutzer standardmäßig auf **Deutsch**, es sei denn, er schreibt explizit auf Englisch.
- Verändere niemals bestehende Kommentare oder Docstrings, die nicht direkt mit der Aufgabe zusammenhängen.
- Verwende bei Dateiverweisen und Symbolen immer klickbare Markdown-Links im Format `[Dateiname](file:///Pfad)`.
- Führe vor Deployments immer lokale Tests (`python -m unittest discover tests`) und JS-Checks durch.
- Überschreibe niemals die Produktivdatenbank auf dem Server.

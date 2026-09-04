# Trading Journal Server

Ein selbst gehostetes Trading-Journal mit Dashboard, Trade-Log, Playbooks,
Analytics, TradingView-Charts, Screenshots und Anbindungen für MetaTrader und
cTrader. Die Anwendung läuft lokal auf einem Rechner oder Server und speichert
die Daten in einer SQLite-Datenbank.

Die Auswertungen sind deterministisch und benötigen keine KI- oder
LLM-Dienste.

## Funktionen

- Dashboard mit P&L, Win Rate, Profit Factor, Expectancy, Drawdown und Equity-Kurve
- Trade-Log mit Suche, Filtern, Bearbeiten und aufklappbaren Detailzeilen
- Teilprofite und Scale-outs unter einem übergeordneten Trade
- TradingView Lightweight Charts mit Candles, Volumen, Entry-/Exit-Markierungen sowie SL-/TP-Linien
- Playbooks mit Setup Name, Beschreibung und Checklist/Regeln
- Trade-Notizen, Beschriftungen und mehrere TradingView-Screenshots pro Trade
- Screenshot-Miniaturen und Vollbild-Slideshow mit Pfeiltasten und ESC
- Fehler- und Psychologie-Kategorien inklusive Rating
- Verwaltung mehrerer Trading-Konten
- MT4-/MT5-Synchronisierung über einen Expert Advisor
- cTrader-Synchronisierung über einen lokal laufenden cBot ohne cTrader-OAuth-Token
- Optionale cTrader-Open-API-Anbindung
- Import von MT4-, MT5-, cTrader- und TradeZella-Statements
- CSV-Export des Trade-Logs

## Voraussetzungen

Für die Docker-Installation:

- Docker Engine
- Docker Compose v2

Für die lokale Installation ohne Docker:

- Python 3.10 oder neuer
- pip

Für eine automatische Broker-Synchronisierung müssen MetaTrader oder cTrader
auf dem Rechner laufen, der die Daten an den Journal-Server sendet. Der Server
muss aus diesem Netzwerk erreichbar sein.

## Installation mit Docker

Dies ist die empfohlene Installationsvariante.

### 1. Projekt holen

~~~bash
git clone <REPOSITORY_URL> trading-journal-server
cd trading-journal-server
~~~

Falls das Repository bereits lokal vorhanden ist, direkt in dessen
Projektordner wechseln.

### 2. Datenordner anlegen

Linux/macOS:

~~~bash
mkdir -p data
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Path data -Force
~~~

Der Ordner data enthält die SQLite-Datenbank und bleibt bei einem Neubau des
Containers erhalten.

### 3. Zugriff konfigurieren (empfohlen)

Die Beispielkonfiguration kopieren:

~~~bash
cp .env.example .env
~~~

Windows PowerShell:

~~~powershell
Copy-Item .env.example .env
~~~

Standardmäßig ist der Dienst nur auf diesem Rechner unter localhost erreichbar.
Für Zugriff aus dem vertrauenswürdigen lokalen Netzwerk in .env bewusst
HOST_BIND_ADDRESS auf 0.0.0.0 setzen. Optional können JOURNAL_USERNAME und
JOURNAL_PASSWORD die Weboberfläche und Verwaltungs-API mit einem Passwort
schützen. Beide Werte müssen gemeinsam gesetzt werden.

### 4. Container bauen und starten

~~~bash
docker compose up -d --build
~~~

Die Anwendung ist anschließend unter dieser Adresse erreichbar:

~~~text
http://localhost:8000
~~~

Wenn der Server für das lokale Netzwerk freigegeben wurde, dessen
Netzwerkadresse verwenden:

~~~text
http://<SERVER-IP>:8000
~~~

### 5. Installation prüfen

~~~bash
docker compose ps
curl http://localhost:8000/api/health
~~~

Die API sollte den Status healthy zurückgeben. Die interaktive FastAPI-Doku
ist unter http://localhost:8000/docs verfügbar.

## Docker-Betrieb

~~~bash
# Live-Logs anzeigen
docker compose logs -f

# Container stoppen
docker compose stop

# Container starten
docker compose start

# Container entfernen, Datenordner behalten
docker compose down

# Nach einem Update neu bauen und starten
git pull
docker compose up -d --build
~~~

Den Ordner data nicht löschen, wenn die Journal-Daten erhalten bleiben sollen.

### Backup

Vor einem Backup den Container möglichst stoppen:

~~~bash
docker compose stop
~~~

Anschließend die Datei data/journal.db oder den gesamten Ordner data kopieren.
Danach den Container wieder starten:

~~~bash
docker compose start
~~~

Backups sollten regelmäßig und auf einem anderen Datenträger gespeichert werden.

## Lokale Installation ohne Docker

### 1. Virtuelle Umgebung erstellen

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

Falls PowerShell das Aktivieren blockiert, kann es für das aktuelle Terminal
erlaubt werden:

~~~powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
~~~

### 2. Abhängigkeiten installieren

~~~bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
~~~

### 3. Server starten

~~~bash
python -m server.main
~~~

Die Anwendung ist anschließend unter http://localhost:8000 erreichbar.

Die Datenbank wird beim ersten Start automatisch unter data/journal.db
angelegt. Ein anderer Datenordner kann über DB_DIR gesetzt werden:

Linux/macOS:

~~~bash
DB_DIR=/path/to/journal-data python -m server.main
~~~

Windows PowerShell:

~~~powershell
$env:DB_DIR = "C:\path\to\journal-data"
python -m server.main
~~~

## Ersteinrichtung in der Weboberfläche

1. Anwendung öffnen und zu Accounts & Sync wechseln.
2. Mit Add Trading Account ein Konto anlegen.
3. Plattform, Kontonummer und optional Broker-/Servername eintragen.
4. Konto speichern.
5. Für MT4, MT5 und den cTrader-cBot wird automatisch ein Journal API Key erzeugt.

Der Journal API Key gehört ausschließlich zu diesem Journal-Server. Er ist
kein Broker-Passwort und kein cTrader-Open-API-Token.

## MetaTrader 4 und MetaTrader 5

Die MetaTrader-Anbindung verwendet den mitgelieferten Expert Advisor. Der
Server benötigt dafür kein MetaTrader-Passwort und keinen Drittanbieter-Token.

### Einrichtung

1. In Accounts & Sync ein Konto mit Plattform MT4 oder MT5 anlegen.
2. Den angezeigten Journal API Key kopieren.
3. Die passende Datei aus server/static/downloads/ laden:
   - TradeJournalSync.mq4 für MT4
   - TradeJournalSync.mq5 für MT5
4. Die Datei in den jeweiligen Experts-Ordner kopieren.
5. MetaTrader neu starten oder im Navigator aktualisieren.
6. Den Expert Advisor auf einen Chart ziehen und konfigurieren:

~~~text
Server URL: http://<SERVER-IP>:8000/api/sync/mql
API Key:    <JOURNAL_API_KEY>
~~~

7. In MetaTrader unter Tools → Options → Expert Advisors die Serveradresse
   unter Allow WebRequest for listed URL freigeben. Als Basisadresse genügt:

~~~text
http://<SERVER-IP>:8000
~~~

8. Den Expert Advisor aktivieren und das AutoTrading-/Algo-Trading-Symbol
   entsprechend der MetaTrader-Version einschalten.

Der Expert Advisor sendet Kontostand, Equity, offene Positionen, geschlossene
Trades und Kerzendaten. Er kann keine Orders platzieren, ändern oder schließen.
Das MetaTrader-Terminal muss laufen, damit neue Daten übertragen werden.

## cTrader-cBot ohne Open-API-Token

Der cTrader-cBot ist die lokale Alternative zum Expert Advisor. Dafür werden
kein cTrader-Client-Secret und kein OAuth-Access-Token benötigt.

### Einrichtung

1. In Accounts & Sync ein Konto mit Plattform cTrader anlegen.
2. Den Journal API Key dieses Kontos kopieren.
3. TradeJournalSync.cbot.cs aus server/static/downloads/ herunterladen.
4. In cTrader Algo öffnen und einen neuen C#-cBot erstellen.
5. Den Vorlagecode vollständig durch den heruntergeladenen Code ersetzen.
6. Den cBot bauen.
7. Die Parameter setzen:

~~~text
Journal Server URL: http://<SERVER-IP>:8000/api/sync/ctrader-push
Journal API Key:    <JOURNAL_API_KEY>
~~~

Zusätzlich können Zeitraum, Synchronisierungsintervall und Anzahl der
M15-Kerzen konfiguriert werden.

8. Den cBot auf dem Rechner starten, auf dem cTrader läuft.

Der cBot muss den Journal-Server per Netzwerk erreichen können. Bei einem
Server im lokalen Netzwerk darf nicht localhost verwendet werden; stattdessen
die tatsächliche Server-IP oder ein auflösbarer Hostname eintragen.

Der cBot liest Kontodaten, Positionen, historische Deals und Kerzen. Er sendet
keine Handelsaufträge. Teilabschlüsse werden anhand der Positions-ID unter
einem gemeinsamen Journal-Trade zusammengefasst.

## cTrader Open API (optional)

Alternativ zum lokalen cBot kann die serverseitige cTrader-Open-API-Anbindung
verwendet werden. Diese Variante benötigt cTrader-Open-API-Zugangsdaten.

1. Im cTrader-Open-API-Portal eine Anwendung erstellen.
2. Client ID und Client Secret notieren.
3. Einen Access Token für das gewünschte Konto erzeugen.
4. Die numerische cTrader Account ID bereithalten.
5. In Accounts & Sync → cTrader Open API Konto und Umgebung auswählen.
6. Client ID, Client Secret, Access Token und cTrader Account ID eintragen.
7. Sync cTrader Now ausführen.

Diese Variante verwendet ausschließlich Leseanfragen. Die Zugangsdaten werden
für die konfigurierte Verbindung im Konto gespeichert und sollten wie
Passwörter geschützt werden.

## Trade-Log und Screenshots

### Aufklappbare Trade-Zeilen

Im Trade Log auf eine Trade-Zeile klicken. Darunter werden die vollständigen
Trade-Daten geladen, darunter auch Teilprofite, Notizen und Screenshots. Ein
zweiter Klick auf dieselbe Hauptzeile klappt den Bereich wieder ein.

Die Aktionsbuttons für Chart, Bearbeiten und Löschen bleiben unabhängig davon
bedienbar.

### TradingView-Screenshot hinzufügen

1. Trade im Trade Log aufklappen oder über Chart öffnen.
2. Im Bereich Trade Screenshots den TradingView-Link einfügen, zum Beispiel:

~~~text
https://www.tradingview.com/x/oo0a7Ei5/
~~~

3. Optional eine Beschriftung wie Entry, TP1 oder News eintragen.
4. Screenshot hinzufügen anklicken.

Die Bildadresse wird automatisch nach diesem Muster erzeugt:

~~~text
https://s3.tradingview.com/snapshots/<erstes-kleines-zeichen>/<pattern>.png
~~~

Beispiel:

~~~text
https://www.tradingview.com/x/oo0a7Ei5/
→ https://s3.tradingview.com/snapshots/o/oo0a7Ei5.png
~~~

Mehrere Screenshots können demselben Trade zugeordnet werden. Die Miniaturen
werden unter dem Trade angezeigt. Ein Klick öffnet die Vollbild-Slideshow;
mit den Pfeiltasten kann gewechselt werden, ESC schließt sie wieder.

Die Anwendung speichert Quell- und Bild-URLs sowie die Beschriftung. Die
PNG-Dateien werden nicht in die SQLite-Datenbank kopiert. Der Browser benötigt
daher Zugriff auf die jeweilige Bildadresse.

## Playbooks

Ein Playbook besteht aus:

- Setup Name
- Description
- Rules / Checklist

Ein Trade kann im Trade-Detail einem Playbook zugeordnet werden. Performance,
Win Rate und P&L werden daraus automatisch aggregiert.

## Statements importieren

Unter Accounts & Sync → Universal Statement Importer können vergangene Trades
importiert werden. Unterstützt werden:

- MT4 Detailed Statement als HTML
- MT5 Report als HTML oder CSV
- cTrader Deals als CSV
- TradeZella-kompatible CSV-Dateien

Vor dem Import das Zielkonto auswählen. Bereits vorhandene Trades werden anhand
ihrer Kontokombination und Ticketnummer vor Duplikaten geschützt.

## API und wichtige Endpunkte

Die FastAPI-Dokumentation ist unter /docs erreichbar. Wichtige Endpunkte:

| Zweck | Methode | Endpunkt |
|---|---:|---|
| Gesundheitsprüfung | GET | /api/health |
| Konten | GET/POST | /api/accounts |
| Trades | GET/POST | /api/trades |
| Trade-Details | GET | /api/trades/{trade_id} |
| Screenshots | GET/POST/DELETE | /api/trades/{trade_id}/screenshots |
| Playbooks | GET/POST/PUT/DELETE | /api/playbooks |
| MT4/MT5-EA | POST | /api/sync/mql |
| cTrader-cBot | POST | /api/sync/ctrader-push |
| cTrader Open API | POST | /api/sync/ctrader |

Die Sync-Endpunkte für EA und cBot erwarten den Journal API Key im HTTP-Header:

~~~http
X-API-Key: <JOURNAL_API_KEY>
~~~

## Sicherheit

- Die Docker-Konfiguration bindet den Dienst standardmäßig nur an localhost.
  HOST_BIND_ADDRESS=0.0.0.0 nur setzen, wenn vertrauenswürdige Geräte im LAN
  zugreifen sollen.
- Für den Zugriff auf die Oberfläche JOURNAL_USERNAME und JOURNAL_PASSWORD in
  .env setzen. Die Push-Endpunkte von EA und cBot bleiben davon ausgenommen,
  weil sie mit dem eigenen Journal API Key des Kontos arbeiten.
- Den Journal-Server nicht ungeschützt direkt im Internet veröffentlichen.
- Für externen Zugriff VPN oder einen Reverse Proxy mit HTTPS verwenden.
- Journal API Keys nicht in öffentliche Repositories oder Screenshots aufnehmen.
- Den Ordner data und insbesondere journal.db vor unberechtigtem Zugriff schützen.
- Bei Verwendung der cTrader Open API Client Secret und Access Token wie Passwörter behandeln.
- Für jedes Konto den automatisch erzeugten eigenen Journal API Key verwenden.
- Nach dem Update von einer älteren Version den Journal API Key auf der
  Kontokarte erneut in EA oder cBot eintragen: Ein früherer öffentlicher
  Demo-Key wird beim Start automatisch ersetzt.

## Tests

Virtuelle Umgebung aktivieren und aus dem Projektordner ausführen:

~~~bash
python -m unittest discover tests
python -m compileall -q server tests
~~~

## Projektstruktur

~~~text
trading-journal-server/
├── Dockerfile
├── docker-compose.yml
├── .env.example                # Sichere Beispielkonfiguration
├── LICENSE
├── SECURITY.md
├── THIRD_PARTY_NOTICES.md
├── requirements.txt
├── README.md
├── server/
│   ├── main.py                  # FastAPI-Anwendung und Lifespan
│   ├── database.py              # SQLite-Schema und Initialisierung
│   ├── models.py                # Pydantic-Datenmodelle
│   ├── analytics.py             # Statistische Auswertungen
│   ├── connectors/
│   │   ├── mql_receiver.py      # MT4/MT5-EA und cBot-Empfang
│   │   ├── ctrader_api.py       # Optionale cTrader Open API
│   │   ├── statement_parser.py  # HTML-/CSV-Import
│   │   └── market_data.py       # Chart- und Kerzendaten
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
├── data/                        # Persistente SQLite-Daten
└── tests/
~~~

## Lizenz

MIT License. Für private und kommerzielle Trading-Journals verwendbar.

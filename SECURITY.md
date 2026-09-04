# Sicherheitsrichtlinie

## Unterstützte Version

Sicherheitskorrekturen werden für den aktuellen Stand des main-Branches
bereitgestellt.

## Sicherheitslücke melden

Keine Zugangsdaten, Journal API Keys, Datenbanken oder reproduzierbaren
Exploit-Code in einem öffentlichen Issue veröffentlichen. Verwende stattdessen
die private Sicherheitsmeldung der Hosting-Plattform, falls sie aktiviert ist,
oder kontaktiere den Repository-Inhaber über einen privaten Kanal.

## Sicher betreiben

- Die Docker-Konfiguration bindet den Dienst standardmäßig nur an
  127.0.0.1. Für Zugriff aus dem LAN muss HOST_BIND_ADDRESS=0.0.0.0
  bewusst gesetzt werden.
- Für die Weboberfläche kann mit JOURNAL_USERNAME und JOURNAL_PASSWORD
  HTTP Basic Auth aktiviert werden.
- Die MT4-/MT5- und cTrader-Push-Endpunkte sind davon ausgenommen, da sie
  mit ihrem eigenen, pro Konto erzeugten Journal API Key geschützt werden.
- Kein Journal API Key, cTrader Client Secret, Access Token oder Inhalt von
  data/journal.db gehört in ein Repository, einen Chat oder einen Screenshot.
- Für Zugriff außerhalb des lokalen Netzwerks VPN oder einen HTTPS-Reverse-Proxy
  mit zusätzlichem Zugriffsschutz verwenden.

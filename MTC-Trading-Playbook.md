# MTC Trading Playbook: Systematisches Harmonisches Trading
*Basiert auf den Lehren und der Marktphilosophie des Mustermanns Traders Club (MTC) und David Murawski (Mustermann84)*

---

## 1. DIE PHILOSOPHIE: FRAKTALE MARKTGEOMETRIE ("ZAHNROAD-DENKEN")
Der Markt ist kein statistisch zufälliger Prozess (Random Walk). Er bewegt sich in **fraktalen, geometrisch deterministischen Mustern**, die sich über alle Zeiteinheiten (von Monatskerzen bis in den 1-Minuten- und Sekunden-Chart) hinweg wiederholen.
*   **Das Getriebe-Prinzip:** Ein Zielbereich eines kleinen Musters (Intra-Muster) ist oft ein entscheidender Wendepunkt (z.B. Punkt D) eines übergeordneten Musters.
*   **Der "sicherungsfähige Einstieg":** Das Hauptziel des Systems ist es nicht, den maximalen Gewinn zu prognostizieren, sondern einen Einstieg zu finden, der extrem schnell und risikofrei auf **Break-Even (Einstand)** gezogen werden kann.

---

## 2. SETUPS & MUSTER-DEFINITIONEN (DIE SPIELSTEINE)

### SETUP A: Das klassische ABCD-Muster ("Die Bauern")
Das absolute Standardmuster im harmonischen Trading. Es besteht aus den Punkten A, B, C und D.

*   **Messregeln (Koordinaten):**
    *   **Vektor AC (Korrekturtiefe):** Retracement von AB. Muss zwischen **0.618 und 0.886** liegen (ein Wert nahe 0.67 gilt als optimal).
    *   **Vektor BD (Einstiegs-Extension):** Extension von BC. Muss zwischen **1.219 (bzw. 1.272) und 1.618** liegen.
*   **Spezialvarianten:**
    *   **Se Pony:** Korrektur von AC darf maximal **0.50 (50%)** betragen. Der Einstieg zielt auf den Rücklauf zu Punkt C ab, mit einem maximalen Ausdehnungsanschlag bei der 2.618 Extension.
    *   **Partisanen-Muster:** Extrem exaktes Muster, das punktgenau das **0.382er Retracement** auf AC und das **0.618er Retracement** (Goldener Schnitt) aufweist (sehr selten, meist in kleinen Timeframes).

---

### SETUP B: X-ABCD-Strukturen ("Die Offiziere")
5-Punkt-Muster, die einen strukturellen Initialimpuls (XA) voraussetzen, auf den komplexe Korrekturschleifen folgen.

#### 1. Butterfly & Max Butterfly
*   **XB (Retracement von XA):** Exakt **0.786**.
*   **AC (Retracement von AB):** **0.382 bis 0.886**.
*   **BD (Extension von BC):** **1.618 bis 2.618**.
*   **XD (Zielprojektion):** **1.272** (bzw. **1.618** beim Max Butterfly). Dies definiert die *Potential Reversal Zone (PRZ)*.

#### 2. Black Swan ("Der Läufer" - Starkes Trendumkehrmuster)
*   **XB (Extension von XA):** **1.382 bis 2.618** (Punkt B bricht impulsiv über X aus - *Squeeze*).
*   **AC (Retracement von AB):** Sehr flach, **0.236 bis 0.500**.
*   **BD (Extension von BC):** **1.128 bis 2.000**.
*   **XD (Projektion):** **1.128 bis 2.618**.
*   *Besonderheit:* Wird in zwei Abträgen gehandelt – aggressiv über die Strecke AD und konservativ über die Strecke CD.

#### 3. White Swan
*   **XB:** **0.382 bis 0.724**
*   **AC:** **2.000 bis 4.237**
*   **BD:** **0.500 bis 0.886**
*   **XD:** **0.382 bis 0.882**

#### 4. Cypher
*   **XB:** **0.382 bis 0.618**
*   **AC (Extension):** **1.128 bis 1.414**
*   **BD (Extension):** **1.272 bis 2.000**
*   **XD:** **0.786** (Verwendet das spezifische "C-Werkzeug" in TradingView, da BC über eine Extension gemessen wird).

#### 5. Navarro 200
*   **XD (Projektion):** Nutzt das **1.618er** Verhältnis, berechnet als Rebound der Strecke AD (nicht der Strecke CD).

---

### SETUP C: Wolfe Waves ("Die Ausbruch-Struktur")
Ein geometrisches 5-Punkte-System, das oft mit harmonischen Mustern clustert.

*   **Punktebestimmung:** Konstruktion der Punkte 1, 2, 3, 4, und 5.
*   **Die Signallinie (1-3 Linie):** Wird vom Kerzenort (Docht) von Punkt 1 durch die **Kerzenkörper (Schlusskurse)** von Punkt 3 gezogen. Das Nutzen der Kerzenkörper erhöht die Signaldichte massiv im Vergleich zu reinen Docht-Ziehungen.
*   **Die Ziellinie (1-4 Linie - EPA):** Gezogen von Punkt 1 durch den Docht/Körper von Punkt 4. Liefert das maximale Take-Profit-Ziel.
*   **Trigger:** Preis bricht an Punkt 5 durch die Signallinie (Fake-out) und kehrt impulsiv zurück.

---

## 3. CONFIRMATION SIGNALS (DIE FILTER)
Ein harmonischer Punkt D wird erst durch das Zusammenlaufen (*Clustern*) von Filtern zu einem validen Einstiegssignal:

1.  **Fibonacci- und Struktur-Cluster:** Überschneidung von Fibonacci-Marken verschiedener Zeiteinheiten an derselben Preiszone (z.B. übergeordneter RA2 deckt sich mit untergeordnetem Rebound 1.272).
2.  **RSI-Divergenz:** Wenn der Kurs an Punkt D ein neues Extremum (höheres Hoch / tieferes Tief) markiert, der RSI-Indikator diese Bewegung jedoch nicht bestätigt (idealerweise im überkauften Bereich >70 oder überverkauften Bereich <30).
3.  **TD Sequential (Tom DeMark):**
    *   Ein abgeschlossenes **Setup (Count 9)** zeigt eine unmittelbare Trendschwäche der aktuellen Bewegung an.
    *   Ein abgeschlossener **Countdown (Count 13)** identifiziert die hohe Wahrscheinlichkeit einer echten, strukturellen Trendumkehr.
4.  **Spezifische Candlestick-Muster:**
    *   **Doji / Doppel-Doji:** Kerzen ohne nennenswerten Kerzenkörper. Signalisiert Erschöpfung des Trends.
    *   **Marubozu:** Lange Kerzen ohne Docht oder Lunte (nur Kerzenkörper). Zeigt impulsive Marktstärke am Stunden-/Tagesschlusskurs an.
    *   **PopGun:** Eine Inside-Kerze, die komplett von der vorherigen und nachfolgenden Kerze umschlossen wird – Vorbote starker Volatilität.

---

## 4. ENTRY RULES & RISK MANAGEMENT (DAS REGELWERK)

### Das Einstiegsprotokoll
*   **Einstiegspunkt:** Limit-Order direkt in der berechneten PRZ (z.B. am 1.272er Rebound). Bevorzugt wird der Erstkontakt des Kurses mit dem Ziellevel gehandelt.
*   **Stop Loss (SL) Platzierung:** Der SL wird mit etwas Luft für das Marktrauschen knapp hinter den maximalen Parameter des Musters gelegt (z.B. über den 1.618er oder 1.67er Rebound hinaus).

### Das MTC-Positionsmanagement ("Sicherungsmodus")
Um Verluste konsequent zu vermeiden und eine gleichmäßig steigende Equity-Kurve für die Psyche zu gewährleisten, wird ein striktes Teilverkauf-Prozedere angewendet:

```
                  [ Einstieg bei Punkt D / Rebound 1.272 ]
                                     │
                                     ▼
         [ Kurs läuft 15-20 Punkte ODER zum 23.6% Fibo im Plus ]
                                     │
                                     ▼
             [ Sichern: Stop-Loss sofort auf Einstand (BE) ]
             [ Teilverkauf: 25% der Position schließen ]
                                     │
                                     ▼
                  [ Kurs erreicht Regelanlauf 1 (RA1: 0.382) ]
                                     │
                                     ▼
                  [ Kurs erreicht Regelanlauf 2 (RA2: 0.618) ]
                  [ Teilverkauf: Weitere 25% schließen ]
                  [ Stop-Loss aktiv in den Gewinn trailen ]
                                     │
                                     ▼
                [ Kurs läuft zum Rücklauf 13 (0.13 Fibo) ]
                [ ODER Squeeze zu den Rebounds (1.272/1.618) ]
                [ Position komplett schließen (Trade Ende) ]
```

---

## 5. PRE-TRADE CHECKLISTE (VOR DEM JEDEM ENTRY)

- [ ] **Top-Down Analyse durchgeführt?** Woher kommt der Kurs im großen Bild (Monat/Woche)? Befinde ich mich an einer übergeordneten Marke?
- [ ] **Muster-Validität mathematisch geprüft?** Liegen die Retracements von AC und XB exakt in den zulässigen Toleranzgrenzen des Musters (z.B. geprüft über den *MTC Harmonic Ratio Helper*)?
- [ ] **Liegt ein Cluster vor?** Überschneiden sich an der Einstiegszone Fibonacci-Level, Trendlinien, Dreiecksspitzen oder gleitende Durchschnitte (EMA 50 / EMA 200)?
- [ ] **Stimmen die Einstiegsindikatoren?** Zeigt der RSI eine Divergenz? Steht das TD Setup kurz vor der 9 oder 13?
- [ ] **Ist das Verlustrisiko definiert?** Ist die Positionsgröße so berechnet, dass der Stop-Loss (hinter dem 1.618/1.67er Rebound) dem Risikoprofil entspricht?
- [ ] **Befindet sich die Kerze vor dem Schluss?** Nutze die Restlaufzeitanzeige der Kerze. Ein Einstieg erfolgt erst bei Bestätigung durch den Kerzenschluss im Zielbereich!

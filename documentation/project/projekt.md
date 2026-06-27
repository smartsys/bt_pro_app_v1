# BT Pro App — Projektbriefing

> Was dieses Dokument ist: Eine verständliche Übersicht über das Projekt für Einsteiger — Zweck, Funktionsumfang, Architektur-Überblick. Bleibt über die Projekt-Lebenszeit stabil und wird nur bei strategischen Änderungen aktualisiert.
>
> Was dieses Dokument nicht ist: Technische Architektur, Pfade, Deployment-Details. Das steht in `knowledge/project-structure.md`.

---

## Was ist die BT Pro App?

Die **BT Pro App** ist eine Web-Anwendung zum iterativen Entwickeln und Backtesten algorithmischer Crypto-Trading-Strategien. Sie basiert auf [VectorBT Pro](https://vectorbt.pro/) — einer leistungsfähigen Python-Bibliothek für vektorisierten Backtest.

Der Anzeigename „BT Pro App" grenzt die Anwendung bewusst vom zugrundeliegenden Framework „VectorBT Pro" ab, um Verwechslungen zu vermeiden. Intern trägt das Projekt den technischen Bezeichner `bt_pro_app_v1` (Verzeichnis, Docker-Compose-Projektname und Basis-Image `bt_pro_app_v1-vbt`); die einzelnen Container behalten die Kurzform `*_bt_pro_v1` (z.B. `frontend_bt_pro_v1`, `db_bt_pro_v1`).

Der Kern-Workflow: Strategie-Idee formulieren → Parameter definieren → Backtest gegen historische Kursdaten ausführen → Ergebnis auswerten → Hypothese verfeinern → wiederholen.

Die App ist keine Trading-Plattform. Sie führt keinen echten Handel aus. Sie ist eine **Research-Werkbank** — ein Ort, um Strategien zu messen, zu vergleichen und systematisch zu verbessern.

---

## Für wen ist die App gedacht?

**Heute:** Ein einzelner Nutzer (Trader/Entwickler) sitzt am Chart-Playground, lädt ein Setup, passt Parameter an, startet einen Backtest und wertet das Ergebnis im Chart aus.

**Perspektivisch:** Ein KI-Agent kann dieselbe Infrastruktur über die JSON-API nutzen — Konzepte aus einem verknüpften Wissens-Vault lesen, Strategien automatisiert über Multiparameter-Läufe optimieren und Iterationen dokumentieren.

---

## Was kann die App — Funktionsübersicht

### 1. Chart Playground

Der zentrale Arbeitsbereich. Hier werden Strategien definiert, konfiguriert und getestet.

- **Setups:** Ein Setup ist eine gespeicherte Strategie-Konfiguration (welche Indikatoren, welche Ein-/Ausstiegsregeln, welche Portfolio-Parameter). Setups können angelegt, bearbeitet, geklont und gelöscht werden.
- **Spec-Editor:** Strategien werden als strukturierte JSON-Spezifikation (Spec) definiert — kein Python-Code erforderlich. Die Spec beschreibt Indikatoren, Entry- und Exit-Regeln, Stop-Loss/Take-Profit und Portfolio-Einstellungen.
- **Chart laden:** Lädt die Kursdaten des gewählten Symbols und Zeitrahmens samt der live berechneten Indikatoren in den Chart — zum visuellen Prüfen der Strategie, bevor ein Backtest läuft.
- **Schnellbacktest:** Läuft synchron und ohne Datenbankschreibvorgänge — nur die VBT-Kernberechnung. Ergebnis: ein Badge mit Total Return, Anzahl Trades und Laufzeit. Ideal für schnelle Hypothesentests („taugt die Idee überhaupt?"). Den vollständigen, gespeicherten Lauf stößt man über die eigene Start-Seite an (siehe Abschnitt 2).
- **Spec speichern:** Die aktuelle Spec lässt sich als neue Iteration eines bestehenden Konzepts oder als neues Konzept ablegen — oder sie überschreibt die gewählte Iteration.

### 2. Backtest ausführen und verwalten

Vollständige Backtests werden über eine eigene Start-Seite angestoßen, dauerhaft gespeichert und sind durchsuchbar.

- **Backtest starten:** Auf der Start-Seite werden eine Backtest-Config, eine Strategie-Iteration und eine Indikator-Config ausgewählt. Der Lauf läuft asynchron im Hintergrund (RQ-Worker) und speichert alle Trades, Metriken und die Equity-Kurve in der Datenbank.
- **Runs:** Liste aller gestarteten Backtest-Jobs mit Status (pending, running, completed, failed). Jeder Run zeigt Laufzeit, verwendetes Setup und Anzahl der Ergebnisse.
- **Results:** Die eigentlichen Backtest-Ergebnisse — eine oder mehrere Parameter-Kombinationen pro Run. Filterbar nach Symbolen, Strategien, Kennzahlen.
- **Chart-Ansicht:** Interaktiver Chart (LightweightCharts v5) mit Candlestick-Kerzen, Indikator-Overlays, Entry/Exit-Markierungen, Equity-Kurve und Trade-Tabelle. Jede Linie kann ein- und ausgeblendet werden.
- **Favoriten:** Ergebnisse können als Favorit markiert werden — sie sind vor Bulk-Delete geschützt.
- **Bulk-Delete:** Nicht mehr benötigte Ergebnisse können in großen Mengen gelöscht werden.
- **Analyse-Seite:** Aggregierte Übersicht mehrerer Results — Sortierung, Filterung, Vergleich.

### 3. Multiparameter-Läufe

Für systematische Optimierung kann ein einzelner Lauf ein Parameter-Raster über mehrere Werte aufspannen.

- **Parameter-Raster:** Pro Indikator-Parameter werden mehrere Werte angegeben; ein Lauf testet das gesamte Kreuzprodukt in einem Durchgang.
- **Parameter-Produkt:** Die Indicator-Factory berechnet automatisch alle Kombinationen aus den Parameterräumen — z.B. 5 SMA-Längen × 3 Multiplikatoren = 15 Kombinationen in einem Lauf.
- **Ergebnis:** Ein `BacktestRun` mit einem `BacktestResult` pro Kombination — auswertbar über die Analyse-Seite.

### 4. Test-Sets und Leaderboard

Für reproduzierbare Vergleiche zwischen Strategien.

- **Test-Sets:** Definierte Zeiträume und Symbole, gegen die Strategien verglichen werden sollen. Ein Test-Set ist die Grundlage für faire Vergleiche.
- **Testset-Runs:** Führt eine Strategie-Iteration gegen ein Test-Set aus — vergleichbarer Benchmarking-Lauf.
- **Leaderboard:** Aggregierte Rangliste aller Strategien/Iterationen, die gegen ein Test-Set gelaufen sind. Sortierbar nach Gesamtrendite, Sharpe Ratio, Drawdown u.a.

### 5. Strategie-Konzepte und Iterationen

Verwaltung der Strategie-Hierarchie in der App.

- **Strategie-Konzepte:** Top-Level-Einheiten (z.B. „Teststrategie"). Jedes Konzept hat einen Obsidian-Pointer zum zugehörigen Vault-Eintrag.
- **Iterationen:** Versionierte Snapshots einer Strategie-Spec. Jede Iteration hat einen Status (`draft`, `active`, `archived`, `live`) und einen unveränderlichen Spec-Hash. Iterationen werden im Chart-Playground ausdrücklich gespeichert ("Spec speichern"); ein vollständiger Backtest läuft anschließend gegen die gewählte, gespeicherte Iteration.

### 6. Konfiguration

Verwaltung wiederverwendbarer Bausteine.

- **Backtest-Configs:** Portfolio-Parameter-Sets (Symbol, Zeitraum, Startkapital, Gebühren, Stop-Parameter). Können in Setups referenziert werden.
- **Indikator-Configs:** Wiederverwendbare Indikator-Definitionen, die Strategie-Konzepten und Iterationen zugeordnet werden.
- **Playground-Setups:** Direkt im Config-Bereich verwaltbar — gleiche Funktion wie im Playground.

### 7. Knowledge-Dashboard (Vault-Vektordatenbank)

Suche und Erkundung des verknüpften Obsidian-Vaults direkt aus der App.

- **Dashboard:** Übersicht über den indexierten Vault — Anzahl Chunks, Indexierungs-Stand, letzte Aktualisierung.
- **Datei-Browser:** Alle indizierten Vault-Dateien mit Metadaten.
- **Reindex-Jobs:** Manuelles Auslösen und Verfolgen von Indexierungs-Läufen (pgvector-gestützt, Embedding-basiert).
- **Hintergrund:** Der Vault-Indexer liest Markdown-Dateien aus dem Obsidian-Vault, erstellt Embeddings und speichert sie in PostgreSQL (pgvector). Ziel: semantische Suche über Strategie-Konzepte, Iterationen, Lessons.

---

## Wie funktioniert ein Backtest — der Weg einer Strategie

```
1. Nutzer wählt auf der Start-Seite Backtest-Config, Strategie-Iteration und Indikator-Config
        ↓
2. "Backtest starten" → HTTP POST an /api/backtest/start
        ↓
3. FastAPI erstellt BacktestRun-Eintrag in der DB, stellt Job in Redis-Queue
        ↓
4. RQ-Worker holt Job aus der Queue
        ↓
5. Spec-Runner läuft:
   a) OHLCV-Kursdaten aus HDF5-Datei laden
   b) Indicator-Factory: alle Indikatoren berechnen (inkl. Parameterraum)
   c) Rules-Engine: Entry- und Exit-Signale aus Regeln ableiten
   d) VBT Portfolio.from_signals(): Trades simulieren, Kennzahlen berechnen
        ↓
6. Ergebnisse in PostgreSQL speichern (Trades, Metriken, Equity, Indikator-Werte)
        ↓
7. Frontend pollt Status → zeigt Ergebnis an
```

---

## Welche Indikatoren stehen zur Verfügung?

Die Regeln-Engine kennt drei Indikator-Quellen:

| Prefix | Quelle | Beispiel |
|---|---|---|
| `custom:` | Eigene Indikatoren in `custom.py` | `custom:dwsFastSMA`, `custom:dwsCrossover` |
| `vbt:` | VectorBT Pro Indicator-Bibliothek | `vbt:SUPERTREND`, `vbt:RSI` |
| `talib:` | TA-Lib (technische Analyse) | `talib:SMA`, `talib:MACD` |

---

## Wo kommen die Kursdaten her?

OHLCV-Daten (Open, High, Low, Close, Volume) werden von **Binance** heruntergeladen (historische Public-Daten, kein API-Key erforderlich). Der Download läuft über den eingebauten Downloader von VectorBT Pro.

Die Daten werden als **HDF5-Dateien** gespeichert (`user_data/ohlc_data/`) und beim Backtest direkt aus dem Dateisystem gelesen — kein Datenbank-Roundtrip für Kursdaten. Zeitrahmen: 15m, 1h, 4h, 1d — je nach heruntergeladenen Dateien.

---

## Wissenstrennung — was gehört wohin?

| Speicherort | Inhalt |
|---|---|
| **BT Pro App (dieses Projekt)** | Code, Backtest-Infrastruktur, Ergebnis-Datenbank, operative Iterations-Logs |
| **Obsidian-Vault** (Host-Pfad über `OBSIDIAN_VAULT_HOST_PATH` in der `.env`) | Strategie-Konzepte, Lessons Learned, Iterationsnotizen, Forschungsquellen |
| **HDF5-Dateien** (`user_data/ohlc_data/`) | Historische OHLCV-Kursdaten — groß, gitignoriert |

Diese Trennung ist bewusst: Die App ist die Ausführungsplattform, der Vault ist das Wissenssystem. KI-Agenten sollen später beide kombinieren.

---

## Out of Scope

- **Live-Trading / Order-Execution** — die App ist reine Research-Werkbank, kein Broker-Anschluss.
- **Multi-Tenant / User-Accounts** — die App ist für einen einzelnen Nutzer/Forscher gebaut.
- **Produktions-Trading** — kein Risk-Management, kein Positions-Tracking gegen reale Portfolios.

---

## Technischer Rahmen (Kurzfassung)

| Komponente | Technologie |
|---|---|
| Backend | Python 3.13 + FastAPI |
| Backtest-Engine | VectorBT Pro |
| Datenbank | PostgreSQL 17 + TimescaleDB + pgvector |
| Job-Queue | Redis + RQ |
| Frontend | Tabler (Bootstrap 5) + DataTables + LightweightCharts |
| Container | Docker Compose |
| Hosting | lokal (Docker Compose) |

Technische Details: siehe `documentation/knowledge/indicators.md` und `documentation/knowledge/metrics-catalog.md`.

---

## Weiterführend

| Dokument | Inhalt |
|---|---|
| `CHANGELOG.md` | Release-Historie (öffentlich versioniert) |
| `documentation/knowledge/indicators.md` | Indicator-Referenz: unterstützte Indikatoren, Parameter |
| `documentation/knowledge/metrics-catalog.md` | Metriken-Katalog: Backtest-Kennzahlen und Bedeutung |

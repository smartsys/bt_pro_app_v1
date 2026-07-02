# Handbuch — BT Pro App

> Was dieses Dokument ist: Ein Nachschlagewerk zur Bedienung der App — was einzelne
> Funktionen tun und welche Daten dabei entstehen. Wächst mit der Zeit um weitere Kapitel.
>
> Ergänzt das Projektbriefing (`projekt.md`, der Überblick) um die konkrete Bedienung
> einzelner Funktionen.

---

## Inhalt

- [Run-Analyse](#run-analyse)
  - [Erweiterte Datenberechnung](#erweiterte-datenberechnung)
  - [Verfügbare Daten vor und nach der Analyse](#verfügbare-daten-vor-und-nach-der-analyse)
  - [Warum drei Stufen?](#warum-drei-stufen)
- [Toolbox-Werkzeuge](#toolbox-werkzeuge) — alle Werkzeuge des Helfer-Skripts `toolbox.py`

---

## Run-Analyse

Die Run-Analyse rechnet für einen abgeschlossenen Backtest-Run die vollständigen
Detail-Daten jeder Parameter-Kombination nach — Equity-Kurve, Trades, Orders, Positionen
und Indikator-Serien. Bedient wird sie über die Analyse-Seite eines Runs.

**Aufruf:** `http://localhost:5570/backtest/runs/{id}/analyse`

Bei einem **Multiparameter-Lauf** (viele Parameter-Kombinationen in einem Run) werden aus
Performance-Gründen zunächst nur die **Kennzahlen je Kombination** gespeichert. Die
schweren Detail-Daten — Equity-Kurve, Trades, Orders, Positionen, Indikator-Serien —
werden **nicht** für jede Kombination mitgeschrieben. Sie entstehen erst, wenn man eine
Kombination im Detail ansehen will.

Genau das leistet der **Analyse-Lauf**: Er führt den Backtest jeder Kombination, für die
noch Detail-Daten fehlen, einzeln erneut aus und speichert die vollständigen Ergebnisse
nach. Ausgeführt wird das als Hintergrund-Warteschlange (ein Job pro Kombination); der
Fortschrittsbalken misst den Anteil der Kombinationen, für die inzwischen eine
Equity-Kurve vorliegt.

> Bei einem **Single-Combo-Run** (genau eine Kombination) entstehen Kennzahlen **und**
> Detail-Daten bereits im ursprünglichen Backtest — dort braucht man den Analyse-Lauf nicht.

### Erweiterte Datenberechnung

Gesteuert über die drei Buttons **Start**, **Stop** und **Reset** unten auf der Seite.

| Button | Was er tut | Was gelöscht wird |
|---|---|---|
| **Start** | Setzt fort (Resume): sucht Kombinationen ohne Equity, die keinen aktiven Job haben, legt dafür Jobs an und stellt sie in die Warteschlange. Idempotent — beliebig oft wiederholbar, rechnet immer nur das noch Fehlende nach. | Nichts (außer eigenen `failed`-Jobs, damit sie neu versucht werden). |
| **Stop** | Pausiert: leert die Warteschlange und entfernt die wartenden Jobs. Bereits **laufende** Jobs rechnen im Hintergrund zu Ende. Ein späterer Start legt die pausierten Kombinationen neu an. | Nur die **wartenden** Jobs (Buchhaltung). Keine Ergebnisdaten. |
| **Reset** | Verwirft den Berechnungs-Fortschritt: bricht alle Jobs des Runs ab und löscht die Job-Buchhaltung. | **Nur die Job-Zeilen** — die berechneten Ergebnisse (Kennzahlen, Equity, Trades …) **bleiben erhalten.** |

**Wichtig zu Reset:** Reset ist **kein** Backtest-Neustart. Die `backtest_results` und alle
bereits berechneten Detail-Daten bleiben unangetastet. Reset setzt ausschließlich die
Job-Warteschlange zurück; ein anschließendes Start rechnet dann nur noch die weiterhin
fehlenden Kombinationen nach. (Ein echter Ergebnis-Neustart läuft über den gelben
Rerun-Button in der Run-Liste, nicht über diese Seite.)

**Was Start wiederherstellt — Detail-Daten ja, gelöschte Results nein:** Start rechnet nur
die **fehlenden** Detail-Daten nach (Resume), nicht pauschal alle Kombinationen; haben bereits
alle Results eine Equity-Kurve, passiert nichts. Wenn vorher etwas gelöscht wurde, ist
entscheidend, *was*:

- Nur die **Detail-Daten** einer Kombination gelöscht (die Zeile in `backtest_results` besteht
  noch): Start erkennt die fehlende Equity und erzeugt die Detail-Daten wieder.
- Die ganze **Result-Zeile** gelöscht: wird **nicht** wiederhergestellt. Die erweiterte
  Datenberechnung legt keine neuen Results an, sie füllt nur Detail-Daten für bestehende.
  Gelöschte Results kommen nur über einen echten **Rerun** des Runs (gelber Button in der
  Run-Liste) zurück.

### Verfügbare Daten vor und nach der Analyse

Bezugsfall: ein **Multiparameter-Lauf**. Pro Kombination existiert eine Zeile in
`backtest_results`. Welche Felder dieser Zeile schon gefüllt sind, hängt von der
Berechnungsstufe (`metrics_level`) ab.

#### `backtest_results` — Kennzahlen je Kombination

| Feld-Gruppe | Felder | VOR Analyse (`partial`) | NACH Analyse (`chart`) |
|---|---|---|---|
| **Identität / Config** (immer gesetzt) | `run_id`, `params_hash`, `actual_params_json`, `resolved_config_json`, `full_config_snapshot_json`, `iteration_id`, `is_favorite`, `is_doc_favorite` | vorhanden | unverändert |
| **Rendite** | `total_return_pct`, `benchmark_return_pct`, `annualized_return`, `annualized_volatility` | vorhanden | vorhanden (neu berechnet) |
| **Risiko** | `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`, `omega_ratio`, `downside_risk`, `deflated_sharpe_ratio`, `max_drawdown_pct` | vorhanden | vorhanden |
| **Trades (Kern)** | `total_trades`, `win_rate_pct`, `profit_factor`, `expectancy` | vorhanden | vorhanden |
| **Portfolio (Endwert)** | `end_value` | vorhanden | vorhanden |
| **Zeitraum** | `start_index`, `end_index`, `total_duration` | **leer** | wird gefüllt |
| **Portfolio (Verlauf)** | `start_value`, `min_value`, `max_value` | **leer** | wird gefüllt |
| **Exposure** | `position_coverage_pct`, `max_gross_exposure_pct` | **leer** | wird gefüllt |
| **Drawdown-Dauer** | `max_drawdown_duration` | **leer** | wird gefüllt |
| **Orders / Kosten** | `total_orders`, `total_fees_paid` | **leer** | wird gefüllt |
| **Trade-Detail** | `best_trade_pct`, `worst_trade_pct`, `avg_winning_trade_pct`, `avg_losing_trade_pct`, `avg_winning_trade_duration`, `avg_losing_trade_duration` | **leer** | wird gefüllt |
| **Reproduzierbarkeit** | `spec_runner_version` | ggf. leer | gesetzt |
| **Voll-Metriken** | `tail_ratio`, `value_at_risk`, `cond_value_at_risk`, `alpha`, `beta`, `information_ratio`, `sqn`, `edge_ratio` | **leer** | **bleibt leer** — siehe Hinweis |

> **Voll-Metriken (`metrics_level = full`):** Die letzte Gruppe (Tail-Ratio, VaR, cVaR,
> Alpha, Beta, Information Ratio, SQN, Edge Ratio) berechnet der Analyse-Lauf **nicht** —
> sie sind zu rechenintensiv für den Massen-Backtest. Start/Stop/Reset berühren sie nicht.
> Man startet sie **pro einzelnem Result** über den Button **„Vollanalyse starten"** (im
> Chart-Playground und auf der Result-Chart-Ansicht). Er rechnet als Hintergrund-Job nur
> diese acht Felder für das jeweilige Result nach.

#### Detail-Tabellen je Kombination — vorher leer, Analyse-Lauf füllt sie

| Tabelle | Inhalt (Spalten) | VOR Analyse | NACH Analyse |
|---|---|---|---|
| `backtest_result_params` | `param_name`, `param_value` (die konkreten Parameter der Kombination) | **vorhanden** (schon beim Lauf angelegt) | unverändert |
| `backtest_result_equity` | `timestamp`, `value` (Equity-Kurve über die Zeit) | **leer** | wird gefüllt |
| `backtest_result_trades` | `direction`, `status`, `size`, `entry_index`, `avg_entry_price`, `entry_fees`, `exit_index`, `avg_exit_price`, `exit_fees`, `pnl`, `return_pct`, … | **leer** | wird gefüllt |
| `backtest_result_orders` | `signal_index`, `creation_index`, `fill_index`, `size`, `price`, `fees`, `side`, `type`, `stop_type` | **leer** | wird gefüllt |
| `backtest_result_positions` | `direction`, `status`, `size`, `entry_index`, `avg_entry_price`, `exit_index`, `avg_exit_price`, `pnl`, `return_pct`, … | **leer** | wird gefüllt |
| `backtest_result_indicators` | `indicator_name`, `indicator_output`, `timestamp`, `value` (Indikator-Serien) | **leer** | wird gefüllt |

Läuft der Analyse-Lauf für eine Kombination mehrfach, werden ihre Detail-Zeilen vorher
gelöscht und neu geschrieben (idempotent) — es entstehen keine Duplikate.

#### Was Reset tut (Datenebene)

| Tabelle / Ort | Bei Reset |
|---|---|
| `backtest_jobs` (Job-Buchhaltung des Runs) | **komplett gelöscht** |
| Warteschlange (RQ) | offene Jobs abgebrochen |
| `backtest_results` + alle Detail-Tabellen | **bleiben unverändert** |

### Warum drei Stufen?

Die Kennzahlen eines Results entstehen in drei Berechnungsstufen (`metrics_level`):

- **`partial`** — die schnellen Kennzahlen (Rendite, Sharpe, Sortino, Drawdown, Trades …),
  **vektorisiert über alle Kombinationen** eines Runs auf einmal berechnet. Entsteht direkt
  beim Multiparameter-Lauf.
- **`chart`** — die restlichen `stats()`-Kennzahlen plus alle Detail-Serien (Equity, Trades,
  Orders, Positionen, Indikatoren), berechnet **pro Result**. Kommt über die Run-Analyse.
- **`full`** — die acht teuren Kennzahlen (Tail-Ratio, VaR, CVaR, Alpha, Beta, Information
  Ratio, SQN, Edge Ratio), berechnet **pro Result** über „Vollanalyse starten".

Der Grund für die Trennung ist Rechenaufwand gegen Nutzen. Die `partial`-Kennzahlen lassen
sich vektorisiert über alle Kombinationen zugleich berechnen und sind damit praktisch
„gratis" — sie laufen im Run mit. Die `full`-Kennzahlen dagegen sind quantil-basiert und
nicht billig vektorisierbar: allein Tail-Ratio, VaR und CVaR summieren sich auf mehrere
Minuten, die sonst pauschal auf **jeden** Run draufkämen.

Ein Multiparameter-Lauf erzeugt tausende Kombinationen, von denen die allermeisten sofort
verworfen werden — die teuren Detail-Metriken braucht man realistisch nur für die wenigen
Gewinner. Wegen dieser hohen Datenmengen werden die schweren Stufen deshalb **nicht**
automatisch im Run mitgerechnet, sondern **einzeln pro Result** gestartet, dort wo man eine
konkrete Kombination wirklich im Detail ansehen will. So skaliert der Aufwand mit der Zahl
der interessanten Results, nicht mit der Zahl aller Kombinationen.

---

## Toolbox-Werkzeuge

> Alle Werkzeuge des Helfer-Skripts `toolbox.py` (Pfad B des Skills `ds-strategie-session`).
> Jede Maßnahme ist ein einzelnes Werkzeug. Kein Loop, keine vorgegebene Reihenfolge.
> Aufruf: `python3 .claude/skills/ds-strategie-session/scripts/toolbox.py <werkzeug> ...`
>
> Sehr lange GET-Antworten werden auf 4000 Zeichen gekürzt — die Toolbox weist das dann
> immer sichtbar mit der Original-Größe aus (`[gekürzt: 4000 von N Zeichen — Filter nutzen]`),
> nie stillschweigend. Bei betroffenen Werkzeugen gezielt filtern (z.B. `playground-indicators`
> mit `--group`/`--search`) statt den gekürzten Rohdump zu lesen.

### Lesen — ein Objekt als kompaktes Briefing

| Werkzeug | macht |
|---|---|
| `concept:<id>` | Liest ein Strategie-Konzept aus und gibt Name, Slug und Kerndaten zurück. |
| `iteration:<id>` | Liest eine Iteration aus und zeigt Indikatoren und Regeln aus dem spec_json. |
| `indicator-config:<id>` | Liest eine Indicator-Config aus und listet jeden Indikator mit seinen Parametern. |
| `backtest-config:<id>` | Liest eine Backtest-Config aus (Symbol, Zeitraum, Portfolio-Einstellungen). |
| `strategy-config:<id>` | Liest eine Strategy-Config aus (Legacy, hardcoded/generic). |
| `result:<id>` | Liest ein einzelnes Result mit seinen Kennzahlen aus. |
| `run:<id>` | Liest einen Run aus den letzten Runs (kein Einzel-GET, daher Listen-Filter). |
| `testset:<id>` | Liest ein Testset mit seinen zugeordneten Configs aus. |
| `leaderboard:<id>` | Liest einen Leaderboard-Eintrag im Drilldown aus. |
| `playground-setup:<id>` | Liest ein Chart-Playground-Setup aus. |
| `knowledge:"..."` | Semantische Vektorsuche im Vault-Index, gibt die Top-Treffer zurück. |
| `vault:<pfad>` | Listet indizierte Vault-Dateien nach Pfad-Substring. |

### Listen — mehrere Objekte auf einmal

| Werkzeug | macht |
|---|---|
| `concept-list` | Listet alle Strategie-Konzepte. |
| `iteration-list [concept_id]` | Listet alle Iterationen, optional auf ein Konzept gefiltert. |
| `backtest-config-list` | Listet alle Backtest-Configs. |
| `indicator-config-list [concept_id] [iteration_id]` | Listet alle Indicator-Configs, optional auf Konzept/Iteration gefiltert. |
| `result-list --run <id>` | Listet die Results eines Runs, optional nach Symbol/Timeframe gefiltert. |
| `run-list --strategy <slug>` | Listet die Runs einer Strategie, nach Testset-Lauf gruppiert. |
| `testset-list` | Listet alle Testsets. |
| `leaderboard-list [testset_id]` | Listet die Leaderboard-Einträge, optional je Testset. |
| `strategy-config-list` | Listet alle Strategy-Configs (Legacy). |
| `symbol-list <exchange> <timeframe>` | Listet die verfügbaren Symbole je Exchange und Timeframe. |
| `data-files-list` | Listet die vorhandenen OHLCV-Datendateien. |
| `data-jobs-list` | Listet die laufenden und vergangenen Daten-Download-Jobs. |
| `filters-list` | Listet die verfügbaren Backtest-Filter. |
| `playground-setup-list` | Listet alle Chart-Playground-Setups. |
| `playground-sources` | Listet die verfügbaren Datenquellen des Playgrounds. |
| `playground-indicators` | Ohne Filter: Gruppen-Übersicht (Name + Anzahl je Gruppe, z.B. custom/ta/talib/vbt/wqa101). Mit `--group <name>` nur diese Gruppe, mit `--search <text>` case-insensitiv über id/name gefiltert (kombinierbar); Treffer als kompakte Zeile mit id/inputs/params/outputs. |
| `knowledge-runs-list` | Listet die Indizierungs-Läufe der Wissens-Datenbank. |

### Auswerten — Run oder Result im Detail lesen

| Werkzeug | macht |
|---|---|
| `run-parameter-ranking <run_id> [metrik]` | Rangliste der Parameter-Kombinationen eines Runs nach einer Metrik. |
| `run-top-results <run_id> [metrik] [limit] [richtung]` | Die besten N Results eines Runs nach einer Metrik. |
| `run-best <run_id> <metrik> [min_trades] [limit]` | Bester Metrik-Wert eines Runs mit Mindest-Trade-Zahl. |
| `run-bestwerte --run <id>` | Zieht die vier festen Bestwerte eines Runs und markiert sie als roten Doku-Favorit (idempotent). |
| `run-favorites-reset --run <id> [--doc] [--user]` | Setzt die Favoriten einer Run-Menge zurück (ohne Flag beide Sterne; `--doc` rot/Doku, `--user` gelb/persönlich). Selektoren wie `run-bestwerte`. |
| `run-results <id>` | Rohe Result-Liste eines Runs. |
| `run-summary <id>` | Zusammenfassung der Analyse eines Runs. |
| `run-distribution <id>` | Verteilung der Kennzahlen über die Kombinationen eines Runs. |
| `run-equity-overview <id>` | Equity-Übersicht eines Runs. |
| `run-heatmap <id>` | Heatmap-Daten eines Runs. |
| `run-analyse-progress <id>` | Fortschritt einer laufenden Run-Analyse. |
| `result-stats <id>` | Statistik-Kennzahlen eines einzelnen Results. |
| `result-trades <id>` | Trades eines Results. |
| `result-orders <id>` | Orders eines Results. |
| `result-positions <id>` | Positionen eines Results. |
| `result-ohlcv <id>` | OHLCV-Daten eines Results. |
| `result-chart-data <id>` | Chart-Daten eines Results. |
| `result-metrics-level <id>` | Metrik-Ebenen eines Results. |
| `result-full-metrics <id>` | Berechnet und liefert den vollständigen Metrik-Satz eines Results. |
| `knowledge-run <id>` | Details eines einzelnen Wissens-Indizierungs-Laufs. |
| `knowledge-stats` | Statistik der Wissens-Datenbank (Anzahl indizierter Dateien usw.). |

### Anlegen

| Werkzeug | macht |
|---|---|
| `concept-create --slug ... --name ...` | Legt ein neues Strategie-Konzept an. |
| `iteration-create --concept <id> --file spec.json` | Legt eine neue Iteration an (spec_json als Datei). |
| `indicator-config-create --name ... --file config.json` | Legt eine neue Indicator-Config an (Parameter-Raster als Datei). |
| `backtest-config-create --file backtest.json` | Legt eine neue Backtest-Config an (voller Body als Datei). |
| `testset-create --name ... --configs 552,553` | Legt ein neues Testset aus mehreren Backtest-Configs an. |
| `strategy-config-create --file ...` | Legt eine neue Strategy-Config an (Legacy). |
| `playground-setup-create --file ...` | Legt ein neues Chart-Playground-Setup an. |
| `create-indicator-config result:<id>:<segment>` | Erstellt aus den Gewinner-Parametern eines Results eine Single-Point-Indicator-Config. |
| `copy iteration:<id>` | Kopiert eine Iteration, das Original bleibt unverändert. |
| `copy backtest-config:<id>` | Kopiert eine Backtest-Config. |
| `copy indicator-config:<id>` | Kopiert eine Indicator-Config. |

### Starten — einen Lauf auslösen

| Werkzeug | macht |
|---|---|
| `backtest-run-start --backtest-config <id> --indicator-config <id> --iteration <id>` | Startet einen Backtest-Lauf über das Parameter-Raster. |
| `testset-run-start --testset <id> --iteration <id> --indicator-config <id>` | Startet einen Testset-Lauf (ein Run pro Config), Leaderboard nur bei aktiviertem Testset. |
| `walk-forward-start --result <id> --months <n>` | Startet eine Walk-Forward-Analyse auf Basis eines Results. |
| `playground-setup-compute` | Berechnet die Indikatoren eines Playground-Setups. |
| `playground-setup-run-backtest` | Startet einen vollen Backtest aus einem Playground-Setup. |
| `playground-run-backtest-lite` | Startet einen schnellen Lite-Backtest aus einem Playground-Setup (ohne DB). |

### Ändern

| Werkzeug | macht |
|---|---|
| `concept-update --id <n> --file body.json` | Überschreibt ein Konzept mit dem vollen PUT-Body. |
| `iteration-update --id <n> --file body.json` | Überschreibt eine Iteration mit dem vollen PUT-Body. |
| `backtest-config-update --id <n> --file body.json` | Überschreibt eine Backtest-Config. |
| `indicator-config-update --id <n> --file body.json` | Überschreibt eine Indicator-Config. |
| `strategy-config-update --id <n> --file body.json` | Überschreibt eine Strategy-Config (Legacy). |
| `testset-update --id <n> --file body.json` | Überschreibt ein Testset. |
| `playground-setup-update --id <n> --file body.json` | Überschreibt ein Playground-Setup. |
| `indicator-config-generate-labels <id>` | Setzt Name und Beschreibung einer Indicator-Config serverseitig nach fester Notation. |

### Löschen

| Werkzeug | macht |
|---|---|
| `<bereich>-delete <id>` | Löscht ein Objekt (concept/iteration zusätzlich mit `--force --delete_vault`). |
| `<bereich>-bulk-delete --ids 1,2,3` | Löscht mehrere Objekte auf einmal (indicator-config/result/run/playground-setup). |
| `result-delete-all` | Löscht alle Results außer den geschützten Favoriten. |
| `run-delete-all` | Löscht alle Runs außer den geschützten Favoriten. |
| `knowledge-reset` | Setzt die Wissens-Datenbank zurück (leert den Index). |

### Aktionen — Markieren, Vault, Run-Steuerung

| Werkzeug | macht |
|---|---|
| `iteration-favorite <id>` | Setzt den persönlichen (gelben) Favoriten-Marker auf eine Iteration. |
| `iteration-doc-favorite <id>` | Setzt den Doku-Favoriten (roter Stern, geschützt) auf eine Iteration. |
| `result-favorite <id>` | Setzt den persönlichen (gelben) Favoriten-Marker auf ein Result. |
| `result-doc-favorite <id>` | Setzt den Doku-Favoriten (roter Stern, geschützt) auf ein Result. |
| `concept-vault-create <id>` | Legt die Vault-Doku für ein Konzept an. |
| `iteration-vault-create <id>` | Legt die Vault-Doku für eine Iteration an. |
| `run-restart <id>` | Startet einen Run neu. |
| `run-remarks <id> --text "..."` | Schreibt einen Notiz-Text zu einem Run. |
| `run-analyse-start <id>` | Startet die Analyse eines Runs. |
| `run-analyse-stop <id>` | Stoppt eine laufende Run-Analyse. |
| `run-analyse-reset <id>` | Setzt die Analyse eines Runs zurück. |

### Daten und Wissen

| Werkzeug | macht |
|---|---|
| `data-download --file ...` | Stößt einen OHLCV-Daten-Download an. |
| `data-update --timeframe 4h` | Aktualisiert die vorhandenen OHLCV-Daten eines Timeframes. |
| `data-delete-symbol --timeframe 4h --symbol FETUSDT` | Löscht die OHLCV-Daten eines Symbols. |
| `knowledge-reindex` | Indiziert die Wissens-Datenbank neu. |

### Generisch — jede Route direkt

| Werkzeug | macht |
|---|---|
| `api GET <pfad>` | Ruft eine beliebige API-Route lesend auf. |
| `api POST <pfad> --file body.json` | Ruft eine beliebige API-Route schreibend auf. |
| `api DELETE <pfad>` | Löscht über eine beliebige API-Route. |

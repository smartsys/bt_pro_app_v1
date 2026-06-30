# Toolbox-Werkzeuge — vollständige Liste

> Alle Werkzeuge des Helfer-Skripts `toolbox.py` (Pfad B des Skills `ds-strategie-session`).
> Jede Maßnahme ist ein einzelnes Werkzeug. Kein Loop, keine vorgegebene Reihenfolge.
> Aufruf: `python3 .claude/skills/ds-strategie-session/scripts/toolbox.py <werkzeug> ...`

## Lesen — ein Objekt als kompaktes Briefing

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

## Listen — mehrere Objekte auf einmal

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
| `playground-indicators` | Listet alle nutzbaren Indikatoren mit Inputs, Params und Outputs. |
| `knowledge-runs-list` | Listet die Indizierungs-Läufe der Wissens-Datenbank. |

## Auswerten — Run oder Result im Detail lesen

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

## Anlegen

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

## Starten — einen Lauf auslösen

| Werkzeug | macht |
|---|---|
| `backtest-run-start --backtest-config <id> --indicator-config <id> --iteration <id>` | Startet einen Backtest-Lauf über das Parameter-Raster. |
| `testset-run-start --testset <id> --iteration <id> --indicator-config <id>` | Startet einen Testset-Lauf (ein Run pro Config), Leaderboard nur bei aktiviertem Testset. |
| `walk-forward-start --result <id> --months <n>` | Startet eine Walk-Forward-Analyse auf Basis eines Results. |
| `playground-setup-compute` | Berechnet die Indikatoren eines Playground-Setups. |
| `playground-setup-run-backtest` | Startet einen vollen Backtest aus einem Playground-Setup. |
| `playground-run-backtest-lite` | Startet einen schnellen Lite-Backtest aus einem Playground-Setup (ohne DB). |

## Ändern

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

## Löschen

| Werkzeug | macht |
|---|---|
| `<bereich>-delete <id>` | Löscht ein Objekt (concept/iteration zusätzlich mit `--force --delete_vault`). |
| `<bereich>-bulk-delete --ids 1,2,3` | Löscht mehrere Objekte auf einmal (indicator-config/result/run/playground-setup). |
| `result-delete-all` | Löscht alle Results außer den geschützten Favoriten. |
| `run-delete-all` | Löscht alle Runs außer den geschützten Favoriten. |
| `knowledge-reset` | Setzt die Wissens-Datenbank zurück (leert den Index). |

## Aktionen — Markieren, Vault, Run-Steuerung

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

## Daten und Wissen

| Werkzeug | macht |
|---|---|
| `data-download --file ...` | Stößt einen OHLCV-Daten-Download an. |
| `data-update --timeframe 4h` | Aktualisiert die vorhandenen OHLCV-Daten eines Timeframes. |
| `data-delete-symbol --timeframe 4h --symbol FETUSDT` | Löscht die OHLCV-Daten eines Symbols. |
| `knowledge-reindex` | Indiziert die Wissens-Datenbank neu. |

## Generisch — jede Route direkt

| Werkzeug | macht |
|---|---|
| `api GET <pfad>` | Ruft eine beliebige API-Route lesend auf. |
| `api POST <pfad> --file body.json` | Ruft eine beliebige API-Route schreibend auf. |
| `api DELETE <pfad>` | Löscht über eine beliebige API-Route. |
</content>
</invoke>

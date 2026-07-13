# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
## [1.30.90] - 13.07.2026

### Changed
- Backtest-Configs-Übersicht lädt sofort, Datenqualität wird pro Timeframe nachgereicht
  - Die Tabelle wartete bisher auf /api/config/backtest/quality und /api/config/data/files, bevor sie überhaupt gezeichnet wurde. Die Qualitätsberechnung liest den kompletten Zeit-Index aller HDF5-Dateien (allein die 5m-Datei rund 13 Mio. Zeitstempel) und brauchte damit gut 6 Sekunden — unabhängig von der Zahl der Configs.
  - GET /api/config/backtest/quality akzeptiert jetzt den optionalen Parameter timeframe und berechnet dann nur die Configs dieses Timeframes (eine HDF5-Datei statt aller). Ohne Parameter unverändertes Verhalten.
  - Die Übersicht rendert die Tabelle sofort (rund 140 ms statt 6,5 s) und holt die Qualität je Timeframe parallel nach; jede Antwort zeichnet die Spalte neu. Noch nicht berechnete Zellen zeigen einen Spinner, die günstigen Timeframes erscheinen praktisch sofort.
  - Der Qualitäts-Filter (min/max) lässt Zeilen durch, deren Timeframe noch rechnet, statt sie auszublenden.
  - Behoben: solange die Verfügbarkeits-Daten noch luden, markierte der Datums-Renderer jede Zelle fälschlich rot als 'keine OHLC-Daten vorhanden'. Marker werden jetzt erst gesetzt, wenn die Daten wirklich da sind.

### Files
- services/api/routes/api_config.py
- services/frontend/templates/config/backtest_configs.html



## [1.30.89] - 13.07.2026

### Fixed
- Toolbox-Verb vergleichstabelle fasst mehrere Läufe einer Iteration je Symbol+Testset zu einer Zeile zusammen
  - Bisher schrieb der Generator eine Tabellenzeile pro Run. Das stimmte nur, solange eine Iteration genau einen Run je Symbol+Testset hatte.
  - Verteilt eine Iteration eine Sweep-Achse auf mehrere Läufe (VWMA v8: 17 Runs je Zelle, einer je k-Stufe, weil k nicht als Sweep-Achse läuft), entstanden 17 identisch mit v8 beschriftete Zeilen ohne unterscheidendes Merkmal — die Tabelle wuchs auf 208 Zeilen und las sich, als gäbe es 17 v8-Iterationen.
  - Die Zelle ist jetzt Symbol x Iteration: Spitze = bester Total Return und Kern = bester Profitfaktor über alle Läufe der Zelle, also die Decke über die gesamte verteilte Achse.
  - Zellen aus mehreren Läufen werden als 'vN (17 Läufe)' gekennzeichnet, mit erklärender Fußnote unter der Tabelle.

### Files
- .claude/skills/ds-strategie-session/scripts/toolbox.py



## [1.30.88] - 13.07.2026

### Added
- Toolbox: api GET liefert lange Antworten vollständig (--out / --full) mit selbstaufräumendem Temp-Ordner
  - --out [datei]: schreibt die Antwort ungekürzt in eine Datei, auf der Konsole erscheinen nur Pfad und Zeichenzahl (kontextschonend). Ohne Wert wird ein Auto-Name mit Zeitstempel vergeben.
  - --full: gibt die Antwort ungekürzt auf stdout aus. --out und --full zusammen sind ein Fehler.
  - Hintergrund: die Anzeige kappte lange Antworten hart bei 4000 Zeichen, der Schnitt lag mitten im JSON und machte es unparsebar. Der Hinweis 'Filter nutzen' half bei Routen ohne Filter-Query (z.B. parameter-ranking) nicht; als Ausweg blieb nur ein direkter urllib-Fetch an der Toolbox vorbei.
  - Ablageort: --out schreibt immer unter <TEMP>/bt-toolbox-out/. Reine Dateinamen und relative Pfade werden dorthin aufgelöst statt ins Arbeitsverzeichnis, damit keine Wegwerf-Datei im Projektbaum landen kann. Nur absolute Pfade werden wörtlich genommen (ohne Cleanup).
  - Cleanup: bei jedem --out-Schreiben werden Dateien älter als 24 Stunden rekursiv entfernt, leer gewordene Unterordner fallen mit weg. Neues Verb out-clean [--all] räumt auf Zuruf auf (ohne Flag nur Abgelaufenes, mit --all den ganzen Ordner).
  - Doku: Toolbox-Help (--help), Skill SKILL.md und handbuch.md nachgezogen; To-Do 14 in todo-toolbox.md geschlossen.

### Files
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- .claude/skills/ds-strategie-session/SKILL.md
- documentation/project/handbuch.md
- documentation/todo/todo-toolbox.md



## [1.30.87] - 13.07.2026

### Added
- Favoriten-Stern für TestSets — Favoriten stehen in der TestSet-Liste und im Test-Set-Dropdown der Start-Maske oben
  - Neue Spalte testsets.is_favorite (Integer 0/1) samt Alembic-Migration 0017_testset_favorite
  - Neuer Endpunkt POST /api/testsets/{id}/favorite schaltet den Stern um; is_favorite im TestSetOut-Schema. Wie bei den Backtest-Configs wird der Stern nicht über Create/Update gesetzt, sondern nur über den Toggle-Endpunkt
  - list_testsets sortiert jetzt nach is_favorite absteigend, danach nach Name — die bisherige Namens-Sortierung bleibt innerhalb der Gruppen erhalten
  - TestSet-Liste: klickbare Stern-Spalte (gelb = Favorit) ganz links, Sortierung Favoriten zuerst, danach ID absteigend
  - Start-Maske, Test-Set-Lauf: Favoriten in eigener Gruppe „Favoriten" oben, darunter „Weitere TestSets" in der bisherigen Reihenfolge
  - Tests für Toggle und Favoriten-Sortierung ergänzt

### Files
- user_data/utils/database/models.py
- user_data/utils/database/repository_testsets.py
- services/api/routes/api_testsets.py
- services/frontend/templates/testsets/list.html
- services/frontend/templates/backtest/start.html
- alembic/versions/0017_testset_favorite_flag.py
- tests/test_repository_testsets.py



## [1.30.86] - 13.07.2026

### Fixed
- Backtest-Queue überlebt das Hochfahren: Worker warten auf die Datenbank, Recovery holt verwaiste Runs zurück
  - Worker warten vor dem ersten Dequeue auf die Datenbank (wait_for_db in worker_entry.py: SELECT 1 alle 2 Sekunden, Abbruch mit Exit 1 nach 120 Sekunden). Startet der Stack nicht über 'compose up', sondern über 'compose start' oder den Autostart der Docker-Oberfläche, wertet Compose die depends_on-Bedingungen nicht aus. Die Worker waren dann vor Postgres bereit, zogen Jobs, scheiterten sofort an 'the database system is starting up', und RQ schob sie ohne Wiederholung ins FailedJobRegistry - die komplette Queue brannte in Sekunden durch, während die Runs in der Datenbank auf 'queued' stehen blieben.
  - Recovery-Oneshot (worker-init) räumt jetzt zwei Fälle auf: hängende 'running'-Runs (wie bisher) und zusätzlich 'queued'-Runs, zu denen kein RQ-Job mehr existiert. Als lebendig gilt ein Job, der wartend in der Queue oder im StartedJobRegistry liegt - ein zeitgleich anlaufender Worker führt damit nicht zu doppeltem Einreihen. Die im ersten Fall zurückgesetzten Runs werden explizit ausgenommen.
  - Tests für recovery_oneshot ergänzt: 'queued'-Run mit lebendem Job bleibt unberührt, verwaister 'queued'-Run wird neu eingereiht. Die Tests der Datei hängen jetzt zusätzlich an der session-Fixture, die die Tabellen vor jedem Test leert (vorher liefen sie auf Resten voriger Tests).

### Files
- services/api/worker_entry.py
- services/api/recovery_oneshot.py
- services/api/tests/test_recovery_oneshot.py



## [1.30.85] - 13.07.2026

### Added
- Chart-Playground: Button „Vollen Run starten" — Multiparameter-Lauf als Ad-hoc-Run aus dem aktuellen Playground-Zustand
  - Neuer Endpunkt POST /api/chart-playground/run-backtest: nimmt denselben Payload wie der Schnellbacktest, aber ohne Startwert-Reduktion — das eingetragene Parameter-Raster inklusive '_stops' geht vollständig als Multiparameter-Lauf in den Run.
  - Ad-hoc-Run ohne gespeicherte Configs: Zeitraum, Raster, Stops und Portfolio werden als Snapshot in backtest_config_json/indicators_config_json geschrieben; backtest_config_id und indicator_config_id bleiben NULL, iteration_id wird gesetzt.
  - Regel-Abgleich als Schutz vor stiller Divergenz: Der Worker rechnet immer mit iteration.spec_json['rules']. Weichen die Playground-Regeln davon ab, lehnt der Endpunkt den Start mit 409 ab, statt mit den alten Regeln der Iteration zu rechnen. Fehlt die Iteration, kommt 400.
  - Bestätigungsdialog vor dem Start zeigt Symbol, Exchange, Timeframe, Zeitraum und die Anzahl der Kombinationen (gezählt über den bestehenden Endpunkt /api/config/indicator/count-combos, damit es nur eine Zähl-Wahrheit gibt).
  - Nach dem Start Toast mit Run-ID und Link auf die Ergebnisse.

### Files
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html



## [1.30.84] - 12.07.2026

### Fixed
- Phantom-Grenzen-Audit der Rechen-Pipeline: falsche Raises-Behauptung in evaluate_rules korrigiert, zwei tote Parameter markiert
  - evaluate_rules (rules_engine.py): Der Raises-Block kuendigte einen short-spezifischen ValueError an ('Short-Bloecke sind im nativen Pfad nicht unterstuetzt'). Beides existiert nicht: Der Short-Guard fiel mit Ticket 47 (kein entsprechendes raise im Rumpf, nur 'entry fehlt' und 'keine blocks'), und der native Pfad unterstuetzt Short vollstaendig. Der real geworfene ValueError kommt aus _resolve_ref und gilt fuer jedes State-Primitiv, unabhaengig von is_short. Docstring an der Quelle korrigiert und auf die pinnenden Tests verwiesen.
  - Belegt durch Ausfuehrung: tests/test_rules_engine_short.py (TestGuardShortWithStateExit — Fehler kommt aus _resolve_ref, nicht aus einem Short-Guard) und tests/test_native_short.py (TestLongShortNativePath::test_short_only_native_state_exit — Short + State-Exit laeuft nativ durch). 65 Tests gruen.
  - Toter Parameter markiert (nicht entfernt): _state_exit_signal_func_nb(close_arr) — wird im Rumpf nie gelesen, die Preise kommen aus dem Numba-Kontext c; der Aufrufer reicht ihn weiterhin durch.
  - Toter Parameter markiert (nicht entfernt): _build_indicators_results(timeframe) in spec_runner.py — Fossil aus der Zeit vor dem tf-Pflichtfeld; tf steht heute verbatim aus dem Spec.
  - Geprueft und als ECHT bestaetigt (keine Aenderung noetig): Downsampling-Abweisung in tf_resample.validate_tf, TSL-Paar-Laengen-Guard und leere Sweep-Achse in build_stop_kwargs/count_stop_combos/expand_stop_values, State-Ref-plus-shift-Guard in _build_stateful_condition_spec, Verschachtelungs-Abweisung in _assert_flat_group, Combo-Achsen-Konsistenzcheck in _assert_single_combo_axis, State-Ref-Abweisung im Masken-Pfad (_resolve_ref) sowie saemtliche einschraenkenden Aussagen in services/api/routes/ (18 Dateien geprueft, kein Widerspruch).

### Files
- user_data/strategies/generic/rules_engine.py
- user_data/strategies/generic/spec_runner.py



## [1.30.83] - 12.07.2026

### Changed
- Strategie-Doku fuer die normierte Iterationsentwicklung ergaenzt; zweite veraltete Docstring-Aussage korrigiert (Stop-Sweep-Guard existiert ebenfalls nicht)
  - KORREKTUR zu 1.30.82: Dort hiess es, ein engerer Guard bleibe bestehen (Stop-Sweep kombiniert mit Multi-Combo-Indikatoren). Das ist falsch. Auch dieser Guard existiert nicht: Der Parameter stops_swept wird von spec_runner zwar uebergeben, im Rumpf von evaluate_rules_native aber nirgends gelesen (toter Parameter), und tests/test_native_short.py prueft Multi-Combo x Stop-Sweep auf Bit-Paritaet. Der Raises-Block des Docstrings ist jetzt vollstaendig bereinigt; stops_swept ist als toter Parameter markiert statt entfernt (Aufrufer nicht angefasst).
  - Aufgedeckt wurde das durch einen Widerspruch: code-referenz.md beschrieb den Stand die ganze Zeit korrekt, der Docstring nicht.
  - Neuer Workflow workflows/normierte-parameter.md: Rezepte fuer selbstjustierende Parameter ohne neuen Indikator-Code — dynamischer Zeitstopp (td = k x talib:HT_DCPERIOD) und normierte Einstiegstiefe (Band = VWMA x (1 - k x NATR/100)). Beide auf echten Daten verifiziert, inklusive der Falle, dass die talib-Arithmetik-Indikatoren ihre Inputs high/low nennen.
  - Neuer Workflow workflows/entry-qualitaet-messen.md: exit-freie Entry-Bewertung per MFE/MAE gegen ein Null-Modell, First-Touch-Gitter fuer die erreichbare Win-Rate einer TP/SL-Geometrie ohne Backtest, plus die zwei Denkfehler (fehlendes Null-Modell, MFE-Vergleich statt skalenfreier Asymmetrie).
  - code-referenz.md: neuer Abschnitt Indikator-Arithmetik (dwsConst + talib:MULT/DIV/ADD/SUB als Ersatz fuer die fehlende Regel-Arithmetik, damit dynamische Parameter baubar sind). Die Einschraenkung 'Keine Skalar-Arithmetik' ist entsprechend eingeordnet statt als Sackgasse stehen zu lassen.
  - AGENT_ENTRY.md: beide Workflows im Index; Warnung ergaenzt, dass ein Docstring kein Code-Beleg ist (die Phantom-Grenze hatte einen ganzen Arbeitsstrang als blockiert markiert).

### Files
- user_data/strategies/generic/rules_engine.py
- documentation/knowledge/strategy-development/workflows/normierte-parameter.md
- documentation/knowledge/strategy-development/workflows/entry-qualitaet-messen.md
- documentation/knowledge/strategy-development/code-referenz.md
- documentation/knowledge/strategy-development/AGENT_ENTRY.md



## [1.30.82] - 12.07.2026

### Fixed
- Veralteten Docstring in der Rules-Engine korrigiert: Multi-Combo mit Serien-Operanden in stateful Bedingungen wird NICHT abgewiesen
  - Der Docstring von evaluate_rules_native behauptete, Multi-Combo mit stateful Series-Operanden werde hart abgewiesen (sogenannter N5-Guard). Ein entsprechendes raise existiert nicht: Der Guard fiel bereits mit Ticket 47, nachzulesen im Kommentar an _assert_single_combo_axis. Nur die Dokumentation wurde nie nachgezogen und hat als vermeintlicher Code-Beleg eine Werkzeug-Grenze in die Strategie-Planung getragen, die es nicht gibt.
  - Empirisch verifiziert: Ein dynamischer Zeitstopp (Exit-Regel since_entry >= indicator:td_dyn:real) laeuft im Multiparameter-Lauf, inklusive des Faktors k als eigener Sweep-Achse, ohne neuen Indikator-Code (custom:dwsConst fuer k, talib:MULT fuer k x talib:HT_DCPERIOD). Der Multi-Combo-Lauf liefert je Spalte dieselben Ergebnisse wie der Single-Combo-Lauf derselben Konfiguration.
  - Neuer Test test_multi_combo_series_op_variiert_je_combo: prueft einen Serien-Operanden, der PRO COMBO verschieden ist. Der bestehende Test nutzte nur einen globalen Operanden (close), der auf alle Combos broadcastet, und haette einen Fehler im Spalten-Mapping (col % n_combo) des series_bundle nicht bemerkt.
  - Veraltete Klassen-Ueberschrift in tests/test_native_state_exits.py mitkorrigiert (sie kuendigte den entfernten N5-Reject an, waehrend die Tests darunter das Gegenteil pruefen).
  - Weiterhin bestehender, engerer Guard (unveraendert): Stop-Sweep (gesweepte _stops als vbt.Param) kombiniert mit Multi-Combo-Indikatoren wird als Still-falsch-Schutz abgewiesen.

### Files
- user_data/strategies/generic/rules_engine.py
- tests/test_native_state_exits.py



## [1.30.81] - 12.07.2026

### Added
- Exit-freie Entry-Bewertung (MFE/MAE, First-Touch-Geometrie) als wiederverwendbares Analyse-Modul
  - Neues Modul user_data/utils/analysis/entry_quality.py bewertet einen Einstiegszeitpunkt ohne jede Exit-Regel: Vorwaertsfenster je Signal, MFE (maximale Bewegung ins Plus) und MAE (maximale Bewegung ins Minus), skalenfreie Asymmetrie, First-Touch-Gitter ueber Take-Profit/Stop-Loss-Paare, Null-Modell (unbedingter Einstieg) und Bootstrap gegen den Zufall.
  - Strategie-unabhaengig: arbeitet auf beliebigen Signal-Masken, die die vorhandene Engine (build_indicators + evaluate_rules) liefert. Kein Nachbau der Engine, keine DB-Abhaengigkeit.
  - Konventionen an die Engine angelehnt: Einstandspreis = Close des Signalbalkens (from_signals nutzt den VBT-Default), Vorwaertsfenster ab t+1, MFE ueber High und MAE ueber Low (die Stops triggern intrabar).
  - Balken-Kollision (Ziel und Stop im selben Balken) zaehlt konservativ als Stop, weil die Reihenfolge innerhalb des Balkens aus OHLC nicht rekonstruierbar ist.
  - Skalenfreie Asymmetrie statt reiner MFE-Vergleich: MFE und MAE wachsen gemeinsam mit der Volatilitaet, ein MFE-Vergleich gegen das Null-Modell wuerde Volatilitaet als Kante ausweisen.
  - 26 Unit-Tests auf synthetischen OHLC-Serien (tests/test_entry_quality.py), Gesamtsuite gruen (548 Tests).

### Files
- user_data/utils/analysis/entry_quality.py
- tests/test_entry_quality.py



## [1.30.80] - 12.07.2026

### Added
- Toolbox-Verb vergleichstabelle (Iterations-Vergleich aus Doku-Favoriten) plus Skill-Prozess für Analyse-Screenshots
  - Neues Toolbox-Verb vergleichstabelle --strategy <slug> [--save <pfad>] [--json]: generiert je Testset eine Iterations-Vergleichstabelle (Zeilen Symbol × Iteration, Spalten Spitze = Max Total Return und robuster Kern = Profitfaktor >= 30 Trades) ausschließlich aus den roten Doku-Favoriten mit persistierten Bestwert-Kriterien — purge-fest, funktioniert auch für Runs ohne vollen Result-Satz; --save schreibt zusätzlich eine eigenständige Markdown-Notiz mit Frontmatter
  - fetch() und _dt_query() der Toolbox akzeptieren einen optionalen timeout-Parameter (Default unverändert 10s); das neue Verb nutzt 60s, weil die Favoriten-Sortierung auf Runs mit sechsstelligen Result-Zahlen länger als 10s dauert
  - SKILL.md um zwei Prozess-Abschnitte erweitert: Analyse-Screenshots direkt nach run-bestwerte (zeitkritisch, solange der volle Result-Satz lebt) und Iterations-Vergleichstabelle; Trigger-Beschreibung ergänzt
  - Neue Referenz references/screenshot-standard.md: verbindlicher Screenshot-Standard (maximiertes Browserfenster, Übersicht-Tab, Total Return %, beide Heatmaps auf Average, feste Achsenpaare je Strategie, Ablage- und Namenskonvention im Vault) samt erprobtem Subagent-Prompt und bekannten Stolpersteinen
  - Handbuch: Werkzeugliste um vergleichstabelle ergänzt und --json-Aufzählung aktualisiert

### Files
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- .claude/skills/ds-strategie-session/SKILL.md
- .claude/skills/ds-strategie-session/references/screenshot-standard.md
- documentation/project/handbuch.md



## [1.30.79] - 12.07.2026

### Fixed
- Results-Liste lud in der Default-Sortierung (ID) mehrere Sekunden — Tiebreaker machte den Primärschlüssel-Index unbrauchbar
  - Die Results-Liste sortiert per Default nach ID absteigend. Die Sortierung hängte - wie bei den Metrik-Spalten - stur die Tiebreaker (max_drawdown_pct DESC NULLS LAST, id DESC) plus ein NULLS LAST an. Bei der ID ist beides sinnlos: sie ist Primärschlüssel, also nie NULL und bereits eindeutig, ein Tiebreaker kann die Reihenfolge gar nicht mehr ändern. Angehängt macht er den PK-Index jedoch unbrauchbar - PostgreSQL sortierte die kompletten 3 Mio Zeilen durch (Full Sort, 624.854 Blöcke).
  - Sortierung nach ID läuft jetzt ohne NULLS LAST und ohne Tiebreaker über den PK-Index: 1.564 ms auf 0,5 ms (SQL) bzw. ~3 s auf 15 ms (API, unter laufender Worker-Last gemessen). Beide Richtungen geprüft, Reihenfolge unverändert korrekt.
  - Die Metrik-Spalten behalten ihre Tiebreaker - dort sind sie nötig, weil sich Werte wiederholen (u.a. über 1 Mio Results ohne Trades mit identischen Werten).
  - Nebenbefund: Das seit 1.30.78 aktive Auto-Update (5s) legte während der noch laufenden Abfrage nach, sodass sich die Anfragen stapelten - mit dem Fix erledigt.

### Files
- services/api/routes/api_backtest.py



## [1.30.78] - 12.07.2026

### Changed
- Auto-Update in Runs- und Results-Tabelle standardmäßig aktiv; Worker-Replicas lokal auf 4
  - Der Auto-Update-Schalter (5s) in der Runs- und der Results-Tabelle ist jetzt standardmäßig eingeschaltet. Er war bewusst aus, weil ein Reload früher mehrere Sekunden brauchte und sich die Aufrufe stapelten - die Runs-Liste zählte die Results je Run über einen Full-Scan der breiten Result-Tabelle. Seit der Umstellung auf count(*) und die Sortier-Indizes (1.30.77) kostet ein Reload ~0,2-0,35 s (Runs) bzw. ~15 ms (Results).
  - Gemessen während laufender Backtests: Rechenphase und Schreibphase (Tabelle wuchs während der Messung von 2,99 auf 3,02 Mio Zeilen) ändern die Reload-Dauer praktisch nicht - die Runs-Liste überspringt die Result-Zählung für laufende Runs, die Results-Liste nutzt ungefiltert eine Schätzung statt einer echten Zählung.
  - Der Code-Kommentar, der das frühere Abschalten begründete ("Counts erstickten die DB gegenseitig"), wurde durch den aktuellen Stand ersetzt.
  - docker-compose-local.yml: Worker-Replicas von 2 auf 4 erhöht (wirkt erst beim nächsten up).

### Files
- services/frontend/templates/backtest/runs.html
- services/frontend/templates/backtest/results.html
- docker-compose-local.yml



## [1.30.77] - 12.07.2026

### Fixed
- DB-Snapshot-Import repariert (Restore in einer Transaktion), Fortschrittsanzeige ergänzt und Results-/Runs-Listen entscheidend beschleunigt
  - Import-Fehler behoben: pg_restore läuft jetzt mit --single-transaction. Vorher waren die wiederhergestellten Tabellen für Worker und Scheduler bereits sichtbar, während pg_restore die Primär- und Unique-Constraints erst am Ende anlegt. Der 5-Minuten-Reindex des Schedulers schrieb in dieses Fenster hinein und der Restore scheiterte an doppelten Schlüsseln (vault_chunks, vault_reindex_runs) - die DB blieb ohne diese Constraints zurück. In der Transaktion sind die Tabellen bis zum Commit unsichtbar, ein Fehler rollt vollständig zurück. Gilt für GUI-Import und CLI-Skript.
  - Fortschrittsanzeige für den Import: Der Restore läuft als Hintergrund-Job, die Seite pollt /config/seed/import/status. Der Balken zeigt einen echten Prozentwert (pg_restore --verbose meldet jedes verarbeitete Objekt, die Gesamtzahl kommt vorab aus dem Inhaltsverzeichnis des Dumps) samt Phase und Objektzahl. Ein Reload dockt an einen laufenden Import wieder an.
  - ANALYZE nach dem Restore: pg_restore stellt die Planner-Statistiken nicht mit her. Ohne sie plante PostgreSQL blind, die Runs-Liste brauchte 35 s statt 10 s. Ergänzt in GUI-Import und CLI-Skript.
  - Result-Anzahl je Run: count(*) statt count(id). count(id) verlangt die Spalte id, die in keinem der (run_id, ...)-Indizes steckt - PostgreSQL las dafür die komplette breite Result-Tabelle vom Heap (Parallel Seq Scan). Die Runs-Liste fiel von 10 s auf 0,2 s. Analog an drei weiteren Zählstellen (DataTables-Counts, Rest-Zählung beim Löschen eines Results).
  - Sortier-Indizes für die Results-Liste (Migration 0015): Die Liste sortiert mit zwei Tiebreakern (max_drawdown_pct, id), die Indizes aus 0010 deckten nur die erste Spalte und nur DESC ab. Über eine Million Results aus Kombinationen ohne Trades tragen überall den Wert 0 bzw. NULL und bilden bei absteigender Sortierung die Spitzengruppe - PostgreSQL musste sie für 25 angezeigte Zeilen komplett nachsortieren. Je Metrik-Spalte gibt es jetzt einen DESC- und einen ASC-Index über die vollständige Sortierkette. Gesamtliste: 0,2-9.523 ms auf 0,1-4,0 ms.
  - Sortier-Indizes für Results eines einzelnen Runs (Migration 0016): Die (run_id, metrik)-Composites aus 0010 bedienten nur die absteigende Richtung; aufsteigend sortierte PostgreSQL alle Results des Runs durch (1,0-4,3 s). Aufsteigendes Gegenstück je Metrik-Spalte ergänzt: jetzt 0,1-0,7 ms.
  - Index-Speicher der Result-Tabelle wächst dadurch von 1,3 GB auf 3,7 GB.

### Files
- services/api/seed_service.py
- services/api/routes/views_seed.py
- services/api/routes/api_backtest.py
- services/frontend/templates/config/seed_import.html
- db_snapshot/db_import.py
- alembic/versions/0015_result_sort_tiebreaker_indexes.py
- alembic/versions/0016_result_run_sort_asc_indexes.py



## [1.30.76] - 12.07.2026

### Added
- Heatmap-Tooltip zeigt die Anzahl der aggregierten Backtests
  - Der Tooltip der Analyse-Heatmaps nennt jetzt zusaetzlich die Datensaetze pro Zelle, also wie viele Backtest-Results in den angezeigten Wert eingeflossen sind (bei Average wie bei Max). Damit ist erkennbar, wenn eine Zelle auf weniger Ergebnissen beruht als die uebrigen - etwa bei unvollstaendig gerechneten Runs oder wenn die Metrik in einzelnen Results fehlt.
  - Die Anzahl liefert der Heatmap-Endpunkt bereits als count pro Zelle; sie wird nun als vierte Datendimension durchgereicht statt verworfen. visualMap ist dafuer fest auf Dimension 2 gepinnt, damit die Einfaerbung weiterhin ueber den Metrikwert laeuft.

### Files
- services/frontend/templates/backtest/analyse.html



## [1.30.75] - 12.07.2026

### Fixed
- Heatmap auf der Analyse-Seite blieb dauerhaft beim Platzhalter haengen
  - Sobald eine Heatmap den Hinweis Zwei verschiedene Parameter auswaehlen zeigte (X und Y kurzzeitig gleich, z.B. beim Umstellen der zweiten Heatmap auf dieselben Achsen wie die erste), kam sie nicht mehr zurueck: Der Platzhalter ueberschrieb das Canvas per innerHTML, die ECharts-Instanz blieb aber am Container registriert. Der naechste echarts.init() lieferte die alte, canvas-lose Instanz zurueck und setOption() zeichnete ins Leere.
  - Platzhalter-Zweig meldet die Instanz jetzt per dispose() ab statt sie nur zu clear()en; vor dem Neu-Init wird das Platzhalter-Markup aus dem Container entfernt.
  - Verifiziert an Run 231: rechte Heatmap rendert nach dem Platzhalter wieder, auch bei mehrfachem Wechsel.

### Files
- services/frontend/templates/backtest/analyse.html



## [1.30.74] - 12.07.2026

### Changed
- Runs-Tabelle: Datumsspalten Von/Bis im deutschen Format
  - Spalten Von und Bis zeigen das Datum jetzt als TT.MM.JJJJ statt als ISO-Datum
  - Sortierung und Filter arbeiten weiterhin auf dem ISO-Wert, damit die Reihenfolge korrekt bleibt

### Files
- services/frontend/templates/backtest/runs.html



## [1.30.73] - 11.07.2026

### Added
- Runs-Tabelle: Filterzeile (Symbol/TF/Zeitraum/Size Type) und Size Type an der Indikator-Config
  - Neue Filterzeile auf /backtest/runs zum clientseitigen Filtern nach Symbol, TF, Zeitraum (Backtest-Fenster Von-Bis) und Size Type; Werte aus den geladenen Runs abgeleitet, sofort wirksam, mit Reset
  - Size Type (aus dem eingefrorenen Backtest-Config-Block portfolio.size_type) wird hinten an die Indikator-Config-Spalte als Fliesstext angehaengt
  - Spaltenkopf TR in TSR umbenannt (Testset-Run-ID)
  - get_runs liefert zusaetzlich ein size_type-Feld je Run

### Files
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/runs.html



## [1.30.72] - 11.07.2026

### Added
- Results-Tabelle: Size Type in der Iterations-Zelle und als Filter
  - Size Type (aus der Backtest-Config, per Result-Snapshot) wird hinten an die Iterations-Zelle als schlichter Fliesstext angehaengt
  - Neuer Size-Type-Filter in der Filterleiste (Werte aus den vorhandenen Backtest-Configs); Filterung serverseitig ueber den Result-Snapshot
  - Spaltenkopf Bestwert in Best umbenannt
  - Filter-Dropdowns auf die Hoehe der Input-Boxen angeglichen (form-select-sm Padding)
  - Spalten ID, Run und Symbol zentriert

### Files
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/results.html



## [1.30.71] - 11.07.2026

### Changed
- Chart-Playground: Iteration-Dropdown zeigt Version statt ID; Indikatoren beim Result-Laden ausgeblendet
  - Iteration-Dropdown (Haupt-Auswahl und Überschreiben-Modal) zeigt jetzt die Version statt der internen Iterations-ID als Label; der interne value bleibt die ID
  - Label-Trenner von Gedankenstrich auf Bindestrich umgestellt
  - Beim Laden eines Results über ?resultid= sind die Indikator-Anzeige-Checkboxen zunächst nicht angehakt (chartVisible=false via neuem hideIndicators-Flag in applySetupConfig); der normale Setup-Ladepfad behält die gespeicherte Sichtbarkeit

### Files
- services/frontend/templates/chart_playground/index.html



## [1.30.70] - 11.07.2026

### Changed
- Results-Tabelle: Gesamtzahl mit deutschem Tausendertrennzeichen, Trades-Spalte zu TR mit Info-Icon
  - Header-Zaehler Results (N) via toLocaleString(de-DE) formatiert (z.B. 2.975.694)
  - Spalte Trades in TR umbenannt und mit Info-Icon plus Tooltip 'Total Trades: Gesamtzahl der abgeschlossenen Trades.' versehen

### Files
- services/frontend/templates/backtest/results.html



## [1.30.69] - 10.07.2026

### Fixed
- Backtest-Jobs ohne Zeitlimit einreihen (job_timeout=-1), damit große Multiparameter-Läufe nicht mehr am RQ-Timeout scheitern
  - Große Läufe (z.B. 371943 Kombinationen, 143 Chunks) wurden nach 3600 Sekunden von RQ hart abgebrochen (Task exceeded maximum timeout value) und verloren alle bereits gerechneten Chunks
  - Neue Konstante BACKTEST_JOB_TIMEOUT=-1 in redis_conn.py ersetzt das hartcodierte 3600 an allen fünf run_backtest_job-Enqueues (api_backtest.py, api_testset_runs.py, recovery_oneshot.py)
  - OHLC-Download- und Delete-All-Jobs behalten bewusst ihr 3600-Limit
  - Der Speicherbedarf ist über das Chunking gedeckelt, nicht über die Laufzeit - deshalb ist ein Zeitlimit hier der falsche Hebel

### Files
- services/api/redis_conn.py
- services/api/routes/api_backtest.py
- services/api/routes/api_testset_runs.py
- services/api/recovery_oneshot.py



## [1.30.68] - 10.07.2026

### Added
- Config-Vergleich zeigt die Schrittweite von Wertebereichen
  - Wertebereiche erscheinen in der Vergleichsansicht jetzt als 'min-max (n) s: schritt' statt nur 'min-max (n)' — zwei Bereiche mit gleichem Minimum und Maximum, aber unterschiedlichem Raster waren bisher nicht unterscheidbar
  - Schritt kommt beim arange-Dict direkt aus 'step'; bei Listen nur, wenn die Werte gleichmäßig verteilt sind — ungleichmäßige Listen bleiben ohne Schritt
  - Prozent-Stops (TP/SL/TSL) tragen den Schritt auf derselben Skala wie den Wert (10-30% (5) s: 5%), Skalare bleiben unverändert
  - Formatierung bewusst lokal in indicator_compare.py, nicht in indicator_labels.py: dort ist die Notation Single Source für die generierten Config-Namen und -Beschreibungen, die sich sonst alle geändert hätten
  - Vier neue Tests: abweichendes Raster bei gleichen Grenzen, Stop-Sweeps mit Prozent-Schritt, gleichmäßige und ungleichmäßige Listen

### Files
- services/api/utils/indicator_compare.py
- services/api/tests/test_indicator_compare.py



## [1.30.67] - 10.07.2026

### Added
- Vergleich mehrerer Indicator-Configs als Zeilen-Matrix im Modal
  - Button "Vergleichen" im Page Header der Seite /config/indicator, aktiv ab zwei markierten Configs
  - Neuer Endpunkt GET /api/config/indicator/compare?ids=... liefert eine Spalte je Config und eine Zeilengruppe je Indikator (Stops als letzte Gruppe); die Route muss vor /indicator/{config_id} stehen, sonst greift die ID-Route
  - Neues Modul indicator_compare.py stellt die Configs gegenüber; die Wertformatierung delegiert an die kanonischen Formatierer aus indicator_labels.py, damit keine zweite Sweep-Mathematik im Frontend entsteht
  - Der Vergleich blendet nichts aus: auch indicator, tf, enabled, Inputs und Quellen-Verkettungen sind sichtbar; ein Indikator, den eine Config nicht hat, erscheint dort als "fehlt"
  - Modal-Breite wächst mit der Spaltenzahl (modal-xl bis zwei Configs, ab drei modal-full-width); Tabellenkopf und Feld-Spalte bleiben beim Scrollen stehen, lange Config-Namen im Kopf brechen um statt quer zu scrollen
  - Zwei unabhängige Schalter im Modal-Header: "Abweichungen zeigen" färbt abweichende Zeilen ein, "Nur Änderungen zeigen" blendet gleiche Zeilen und komplett gleiche Gruppen aus; beide stehen beim Öffnen auf aus
  - Indikator-Gruppen durch kräftige Oberkante und eingerückte Feldnamen klar voneinander abgegrenzt; die Vergleichstabelle läuft bewusst ohne table-vcenter, dessen Regel .table.table-vcenter > tbody > tr > td erzwingt 0.875rem Zellpadding
  - Zeilenauswahl der Config-Liste liegt jetzt in einem Set statt im DOM und überlebt Seitenwechsel, Suche und Sortierung — ohne das wäre ein Vergleich zweier Configs auf verschiedenen Seiten nicht möglich; der Bulk-Delete profitiert mit
  - Sieben Unit-Tests, darunter der Nachweis, dass ein still beschnittener Wertebereich als Abweichung auffällt

### Files
- services/api/utils/indicator_compare.py
- services/api/routes/api_config.py
- services/api/tests/test_indicator_compare.py
- services/frontend/templates/config/indicator_configs.html



## [1.30.66] - 10.07.2026

### Fixed
- Toolbox: Indikator-Timeframe (tf) wird angezeigt, -indicator-set mergt statt zu ersetzen
  - Lesen: render_spec und indicator_config_read filterten tf aus der Parameter-Anzeige. Der Rechen-Timeframe war damit in keiner Toolbox-Ausgabe sichtbar, obwohl er laufzeit-wirksam ist. Gefiltert werden jetzt nur noch enabled und indicator, die beide anderswo dargestellt werden (Tag bzw. Klammer).
  - Schreiben: iteration-indicator-set und indicator-config-indicator-set ersetzten den kompletten Indikator-Block durch das übergebene Fragment. Beide mergen jetzt über den gemeinsamen Helfer _merge_indicator_block: nur die im Fragment genannten Parameter ändern sich, der Rest des Blocks bleibt bit-genau. Einen einzelnen Wert ändert man also mit --file {"timeperiod": 50}.
  - --replace ersetzt den Block weiterhin komplett (bewusster Vollersatz, Nicht-Genanntes fällt weg). Der bisherige Fehler 'existiert bereits — mit --replace überschreiben' entfällt, da der Merge selbst vor Datenverlust schützt.
  - Zusammenwirken beider Fehler: Wer einen Parameter ändern wollte, baute den Block aus der Toolbox-Ausgabe nach — ohne tf, weil es nicht angezeigt wurde — und schrieb ihn per Vollersatz zurück. Der folgende Backtest brach in indicator_factory.normalize_tf mit ValueError ab (fehlender tf ist kein implizites 'gleich').
  - Ausgabe von -indicator-set nennt jetzt die Aktion präzise: 'aktualisiert (timeperiod)' statt pauschal 'ersetzt'.
  - Tests: tests/test_toolbox_indicator_block_write.py mit 11 Fällen (Merge erhält tf, arange-Ranges als Wert, --replace-Vollersatz, Insert neuer Keys, keine In-place-Mutation des Bestandsblocks, tf-Anzeige in render_spec). Zusammen mit den bestehenden Toolbox-Tests 20 grün.
  - Doku: SKILL.md (Regel 'Vorhandener Key nur mit --replace' war falsch geworden, plus neuer Hinweis zur tf-Pflicht), handbuch.md (Toolbox-Werkzeuge), --help und Docstrings in toolbox.py.

### Files
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- .claude/skills/ds-strategie-session/SKILL.md
- documentation/project/handbuch.md
- tests/test_toolbox_indicator_block_write.py



## [1.30.65] - 09.07.2026

### Changed
- Chart-Playground: Iterations-Dropdowns absteigend sortiert und mit ID plus Versionsname beschriftet
  - Iterations-Auswahl im Playground zeigt statt der reinen fortlaufenden Nummer jetzt die Iterations-ID und den Versionsnamen
  - Sortierung von aufsteigend auf absteigend gedreht - die neueste Iteration steht oben
  - Gleiches Verhalten im Modal 'Spec ueberschreiben', damit beide Dropdowns identisch aussehen
  - Ohne gesetzten Versionsnamen wird nur die ID angezeigt

### Files
- services/frontend/templates/chart_playground/index.html



## [1.30.64] - 09.07.2026

### Removed
- Frontend-Timeout des Schnellbacktests ersatzlos entfernt — das Frontend wartet auf die Server-Antwort
  - CP_BACKTEST_TIMEOUT_MS (90 s), AbortController samt fetch-signal, clearTimeout und der AbortError-Zweig aus runBacktestLite entfernt — der Client brach bisher nur die HTTP-Verbindung ab, während der Server weiterrechnete; jetzt zeigt das Frontend ausschließlich, was der Server wirklich meldet (Ergebnis oder echter Fehler)
  - Verifiziert im echten Browser: kalter Numba-JIT-Lauf (59 s) läuft vollständig durch und rendert das Badge; warmer Lauf unverändert im Sekundenbruchteil
  - Wissens-Doku an vier Stellen korrigiert (strategy-development: _inject.md, begriffe-und-modi.md, code-referenz.md, workflows/neue-strategie.md): spec_json.indicators ist eine vollständige Selbstbeschreibung (Werte wie eingetragen inkl. _stops, vom Playground-Speichern gewollt so geschrieben); laufzeit-wirksam aus der Iteration sind nur die rules — Indikator-Werte und Stops liefert die IndicatorConfig; die bisherige Behauptung „ohne _stops/Raster“ war falsch
  - documentation/todo/schnellbacktest-playground-fehler.md gelöscht — alle Befunde erledigt oder als gewolltes Verhalten geklärt; Code-Verweis auf das Dokument entfernt

### Files
- services/frontend/templates/chart_playground/index.html
- services/api/routes/api_chart_playground.py
- documentation/knowledge/strategy-development/_inject.md
- documentation/knowledge/strategy-development/begriffe-und-modi.md
- documentation/knowledge/strategy-development/code-referenz.md
- documentation/knowledge/strategy-development/workflows/neue-strategie.md



## [1.30.63] - 09.07.2026

### Fixed
- Schnellbacktest rechnet genau eine Kombination: Startwert-Reduktion vor dem Runner-Aufruf
  - Neue Reduktion _reduce_to_start_values() in api_chart_playground.py: arange-Dicts auf den Startwert, Listen auf das erste Element — für alle Parameter aller Indikatoren und die Stops unter _stops, auf einer Kopie (Wertebereiche bleiben in Oberfläche und Setup erhalten)
  - Reduktion läuft VOR run_spec_strategy in /run-backtest-lite und vor build_indicators in /entry-signals — vorher expandierte der Lite-Pfad das volle Parameter-Raster (Setup 5: 21.280 Kombinationen, 8 Minuten, dann KeyError) und der Entry-Hintergrund baute das Raster einmal pro Regelblock
  - portfolios-Zugriff im Lite-Endpunkt abgesichert: gechunkter Rückgabewert (metrics_table statt portfolios) gibt jetzt eine klare 500-Meldung statt KeyError
  - Marker-Preislinien (TP/SL) lesen die Stops aus der reduzierten Config — exakt die Werte, mit denen das Portfolio gerechnet hat
  - Neue Input-Vertrags-Tests tests/test_playground_startwert_reduktion.py: das an Runner/Indikator-Bau übergebene Dict enthält keine arange-Dicts und keine Listen mehr; genau dieser Vertrag fehlte, weil die bestehenden Lite-Tests den Runner mocken
  - Test-Payload in test_run_backtest_lite.py auf das echte Wire-Format gebracht (Flat-Spec ohne inputs-Wrapper, Block-Rules, _stops statt Stops im Portfolio) und veraltete Fehlertext-Assertion korrigiert
  - Verifiziert gegen Voll-Lauf 219: Startwert-Kombination bit-identisch (0 Trades, 0 %); warmer Schnellbacktest 0,11 s statt Timeout

### Files
- services/api/routes/api_chart_playground.py
- tests/test_playground_startwert_reduktion.py
- tests/test_run_backtest_lite.py
- documentation/todo/schnellbacktest-playground-fehler.md



## [1.30.62] - 09.07.2026

### Fixed
- Indicator-Configs-Tabelle sortiert wieder absteigend nach ID
  - Die Standard-Sortierung zeigte auf Spalte 0 (Checkbox-Spalte, orderable: false) und lief daher ins Leere
  - Sortierung auf Spalte 1 (ID) umgestellt, Richtung absteigend

### Files
- services/frontend/templates/config/indicator_configs.html



## [1.30.61] - 09.07.2026

### Added
- Chart-Playground: Bestehende Spec (Iteration) über einen Auswahl-Dialog überschreiben
  - Die Entry/Exit-Logik-Card hat rechts jetzt einen immer sichtbaren Button Speichern, der ein Popup Spec überschreiben öffnet — analog zum Speichern-Button der Indikatoren-Card links.
  - Das Popup bietet zwei Dropdowns (Konzept + Iteration); beim Öffnen sind das aktuell geladene Konzept und dessen gewählte Iteration vorausgewählt, ein Konzept-Wechsel lädt dessen Iterationen nach.
  - Bestätigen ruft PUT /api/strategy/iterations/{id} mit dem aktuellen Playground-Spec — kein Backend-Umbau nötig.
  - Aufgeräumt: die überflüssig gewordene refreshIterActions() (inkl. aller Aufrufe) und die alte saveIteration()-Funktion entfernt; Spec speichern öffnet openSpecSaveModal() jetzt direkt.

### Files
- services/frontend/templates/chart_playground/index.html



## [1.30.60] - 09.07.2026

### Fixed
- Getragene Ketten-Param-Level konsistent id-benennen — behebt 7x-Blowup der Portfolio-Spaltenzahl bei zugleich verkettetem und direkt referenziertem Indikator (Ticket 53)
  - Ursache: Ein Indikator, der einen anderen als Chain-Input traegt, fuehrte dessen Param-Level unter dem Factory-Namen (dwsfastsma_length) statt dem Spec-ID-Namen (fast_sma_length) mit. Wurde derselbe Indikator zugleich direkt in einer Regel referenziert (dort bereits auf den ID-Namen umbenannt), galten die beiden Achsen als disjunkt und wurden von _combine_broadcast gekreuzt statt gefaltet — die Portfolio-Spaltenzahl blaehte sich um den Faktor der geteilten Achse auf (Run 219/iteration 7: 148.960 statt 21.280 Spalten). Belegt: frischer Run 219 meldet jetzt 21.280 Kombis (Chunks je 4480 statt 31.360).
  - Fix (Variante A): indicator_factory.build_indicators benennt jede Indikator-Instanz direkt beim Bauen auf <spec-id>_<param> um (neue Helfer _rename_indicator_instance fuer den Basis-tf-Zweig, _rename_realigned_output fuer den Per-tf-_RealignedIndicator-Wrapper), bevor sie als Chain-Input oder Direkt-Referenz konsumiert wird. Der ID-Name propagiert damit natuerlich in jeden Downstream (auch ueber mehrere Kettenstufen A->B->C).
  - VBTs eingebautes IndicatorBase.rename()/.rename_levels() ist nicht nutzbar: es bricht bei Indikatoren mit genau einem Parameter (z.B. dwsConst, dwsVWMABand) mit IndexError, weil level_names dort strukturell leer ist (empirisch per VBT-MCP verifiziert). _rename_indicator_instance baut die Umbenennung robust ueber param_names auf.
  - _combine_broadcast, _pairwise_alignable_names, _cross_target_from_indexes bleiben unveraendert (kein Eingriff ins Broadcasting). Der Ticket-49-Crash-Schutz (zwei Instanzen derselben Klasse kreuzen korrekt, kein cross_indexes-Crash) bleibt erhalten.
  - views_backtest.py: Result-Chart-Param-Panel von klassenbasiertem Praefix auf Dual-Praefix (Klasse UND Spec-Key) umgestellt (_resolve_ind_params), damit fuer jeden Indikator weiter Param-Werte erscheinen; heilt zugleich einen Bestandsdefekt fuer direkt referenzierte Custom-Indikatoren (Spec-Key != Klasse).
  - Sauberer Schnitt (nur neue Laeufe): persistierte Param-Namen getragener Indikatoren heissen ab dem Fix neu (dwsfastsma_length -> fast_sma_length). Alt-/Neu-Results matchen an dieser Grenze im Cross-Run-Combo-Tracking (lookup_results_across_runs) und in den ?param=value-Filtern nicht mehr namensgleich — bewusster No-Match, kein Bug. Lookups NICHT dual-praefix gemacht, alte Results nicht zurueckgeschrieben. Dokumentiert in indicators.md 6.5.
  - Verifiziert: pytest 593 passed/11 skipped; Run 220/iteration 2 (ohne Doppel-Referenz) nach frischem Rerun bit-identisch zum Vor-Fix-Stand (33.813/33.813 Kombis, 0 Abweichungen, gematcht ueber Param-Werte); Chart-Param-Panel zeigt fuer fast_sma/vwma/sma weiter Werte.

### Files
- user_data/strategies/generic/indicator_factory.py
- user_data/strategies/generic/rules_engine.py
- services/api/routes/views_backtest.py
- tests/test_indicator_factory_id_naming.py
- tests/test_rules_engine_combine_broadcast.py
- tests/test_views_backtest_ind_params.py
- documentation/knowledge/indicators.md



## [1.30.59] - 07.07.2026

### Added
- Toolbox (ds-strategie-session): gezielte Bearbeitungsverben für Konzept, Iteration, IndicatorConfig und BacktestConfig (add/remove/change ohne kompletten Body)
  - Neue Verben (rein client-seitig, GET->einen Teil ändern->zurückschreiben, kein Server-Change): concept-set, iteration-set, backtest-config-set (Felder); iteration-indicator-set/-remove und indicator-config-indicator-set/-remove (Indikatoren, in der Config mit arange-Ranges); indicator-config-stops-set (einzelne _stops, null-fähig); iteration-condition-add/-remove (Regel-Blöcke/Bedingungen)
  - backtest-config-set akzeptiert Feldnamen in Bindestrich- und Unterstrich-Form (--ohlc-start == ohlc_start); BacktestConfig-PUT ist Voll-Replace, daher GET->merge->PUT
  - Doku: Toolbox-Docstring (--help) um Abschnitt 'Gezielt bearbeiten' plus api-GET-Hinweis für rohe Bodys ergänzt; SKILL.md um neue Rubrik und korrigierte no-raw-curl-Passage (Laufzeit-Zuordnung Indikatoren<-Config / Regeln<-Iteration, Immutability=Konvention) erweitert; handbuch.md um Rubrik 'Gezielt bearbeiten' ergänzt; todo-toolbox.md Punkt 13
  - Verifiziert per selbst-aufräumendem Regressionslauf über alle Verben

### Files
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- .claude/skills/ds-strategie-session/SKILL.md
- documentation/project/handbuch.md
- documentation/todo/todo-toolbox.md



## [1.30.58] - 07.07.2026

### Fixed
- Playground-Schnellbacktest: Listen-förmige Stops ließen alle Trade-Marker still verschwinden (Audit-Befund 8)
  - Ein sweep-förmiger Stop (Liste wie tp_stop: [0.02, 0.04] oder Range-Dict) ließ float(stop) im Trade-Marker-Loop einen TypeError werfen; das per-Trade-except verwarf daraufhin jeden Trade — das Badge meldete Trades, der Chart zeigte null Marker, ohne Fehlermeldung.
  - tp_stop/sl_stop laufen vor dem Marker-Loop jetzt durch _coerce_param: Liste wird auf das erste Element aufgelöst, Range-Dict auf den Startwert, Skalar bleibt. Das entspricht der Kombi, die der Lite-Backtest tatsächlich rechnet (immer Kombi 1 = Startwert), sodass die Marker-Preislinie zur Berechnung passt.
  - Nebeneffekt (gewollt): Bei einem Range-Stop wird die TP/SL-Preislinie jetzt am Startwert gezeichnet — vorher entfiel sie ganz (dict-only-Check setzte auf None).
  - Test: tests/test_playground_stop_marker_coercion.py (Skalar bleibt, Liste zu erstem Element, Range-Dict zu Startwert, leere Liste/None zu None).

### Files
- services/api/routes/api_chart_playground.py
- tests/test_playground_stop_marker_coercion.py
- documentation/todo/audit-rechenpfad-spec-runner-indikatoren.md



## [1.30.57] - 06.07.2026

### Fixed
- Playground: Grüner Entry-Hintergrund respektiert jetzt das Handelsfenster (start/end)
  - Der /entry-signals-Endpunkt beschneidet die Entry-Maske auf das Fenster [start, end] der BacktestConfig - dieselbe Date-Maske wie der native Motor. Zuvor markierte der grüne Hintergrund auch Bars im Warmup-Bereich (vor start) und nach end, an denen der Backtest per Definition nie einsteigt.
  - Neuer Helper _apply_entry_date_window (beide Grenzen inklusiv, UTC wie im Runner).
  - Tests: tests/test_entry_signals_date_window.py (5 Fälle). Live gegen Setup mit Warmup verifiziert: Gegenprobe zeigt, dass die Warmup-Signale exakt weggeschnitten werden (642 -> 633).

### Files
- services/api/routes/api_chart_playground.py
- tests/test_entry_signals_date_window.py



## [1.30.56] - 06.07.2026

### Removed
- Playground: „Setup aus Result speichern" entfernt — Results werden nur noch über den flüchtigen Weg ?resultid= angesehen
  - Route POST /api/chart-playground/setups/from-result/{id} samt zugehöriger Funktion entfernt
  - Die drei „Setup speichern"-Knöpfe in den Result-Tabellen entfernt
  - Toolbox-Werkzeug playground-setup-from-result entfernt
  - Geändert: Result-Chartseite „In Playground öffnen" öffnet das Result jetzt flüchtig über ?resultid= (aufgelöste Parameter, kein Setup wird angelegt) statt ein Setup zu forken

### Files
- services/api/routes/api_chart_playground.py
- services/frontend/templates/backtest/results.html
- services/frontend/templates/backtest/analyse.html
- services/frontend/templates/backtest/run_detail.html
- services/frontend/templates/backtest/result_chart.html



## [1.30.55] - 06.07.2026

### Removed
- Custom-Indikator dwsTrendlineTouch (TAP-Trendlinien-Touch) vollständig entfernt
  - Indikator-Definition dwsTrendlineTouch samt Helfern (trendline_touch_inc, _trendline_touch_side_nb, _kuhle_ok) und dem nur dafür genutzten pivot_info_1d_nb-Import aus custom.py entfernt; dwsSMI und die geteilte Pine-EMA _pine_ema_nb bleiben unversehrt
  - Overlay-Heuristik-Keyword 'trendline' aus api_chart_playground.py entfernt (talib 'ht_trendline' bleibt)
  - Zugehörige _touch-Marker-Logik im Chart-Playground-Template entfernt (renderTouchMarkers, State-Slot touchMarkersByClientId, Abraeum- und pruneOrphanSeries-Eintrag) — der Indikator war deren einziger Nutzer
  - Testdatei tests/test_dws_trendline_touch.py entfernt
  - Hintergrund: nie in einer gespeicherten Iteration/IndicatorConfig referenziert (DB-Scan verifiziert). Damit entfaellt die einzige Stelle mit stillen Factory-Defaults — fehlende Indikator-Parameter fuehren bei allen verbleibenden Custom-Indikatoren weiterhin zu einem lauten Fehler statt zu einem stillschweigend angenommenen Standardwert (fail-loud, gewollt; Audit-Befund 4)

### Files
- user_data/utils/indicators/custom.py
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html
- tests/test_dws_trendline_touch.py
- documentation/todo/audit-rechenpfad-spec-runner-indikatoren.md



## [1.30.54] - 06.07.2026

### Fixed
- Negative Shift-Werte in Rules-Conditions werden abgewiesen (Audit-Befund 3: Lookahead-Schutz)
  - Speicher-Klemmung am zentralen Choke-Point repository_strategies._clamp_negative_shifts: negative lhs_shift/rhs_shift in rules.entry/rules.exit werden beim Speichern der Iteration auf 0 gesetzt (create_iteration/update_iteration) - greift fuer alle Schreibwege inkl. der ds-strategie-session-Toolbox ueber die API
  - Engine-Backstop: neuer Helper _read_shift wirft ValueError bei shift < 0 an beiden Lese-Stellen (_evaluate_condition pandas-Pfad + statische Block-Masken; _build_stateful_condition_spec nativer stateful Pfad)
  - Hintergrund: shift(-1) zoege den Wert der Folgekerze auf die aktuelle Kerze (nicht-kausaler Lookahead); in einem kausalen Backtest gibt es dafuer keinen legitimen Fall
  - Tests: tests/test_shift_sign_validation.py (9 Tests: Klemmung, beide Entry-Pfade, stateful Series-Operand, Gegenproben Shift 0/positiv); Regression neq_nan_warmup/native_state_exits/native_short/native_disjoint_axes gruen

### Files
- user_data/strategies/generic/rules_engine.py
- user_data/utils/database/repository_strategies.py
- tests/test_shift_sign_validation.py
- documentation/todo/audit-rechenpfad-spec-runner-indikatoren.md



## [1.30.53] - 06.07.2026

### Fixed
- Rules-Engine: '!='-Vergleich liefert bei NaN-Operanden keine Phantom-Signale mehr
  - Audit-Befund 2: Nach IEEE/Pandas-Semantik ist NaN != x True, wodurch eine '!='-Regel waehrend der Indikator-Warmup-Phase (Wert=NaN) an jeder Kerze ein Signal erzeugte.
  - Beide Rechenpfade zwingen das Ergebnis jetzt auf False, wo ein Operand NaN ist: pandas-Pfad in _evaluate_condition (Series/DataFrame via ~operand.isna(), Skalar via pd.isna), Numba-Pfad in _eval_one_cond_nb (np.isnan-Check vor dem !=).
  - Latenter Fehler: bei ueblichem OHLC-Vorlauf sind Indikatoren im Handelsfenster aufgewaermt; der Fix ist Sicherheitsnetz fuer knappen Vorlauf oder Datenluecken und aendert bei sauberem Warmup kein Ergebnis.
  - Tests: tests/test_neq_nan_warmup.py (6 Tests, beide Pfade plus Gegenprobe auf gueltige Werte); Regression der Rules-Engine-Tests gruen.

### Files
- user_data/strategies/generic/rules_engine.py
- tests/test_neq_nan_warmup.py
- documentation/todo/audit-rechenpfad-spec-runner-indikatoren.md



## [1.30.52] - 06.07.2026

### Removed
- Veraltete Test-Datei tests/test_indicator_labels.py entfernt — sie prüfte die mit 1.30.40 abgelöste Label-Notation und schlug seitdem fehl (8 rote Tests)
  - Die Datei stammte aus 1.30.36 (Beschreibung = Stops-Rendering, Name mit „Kombi.“, Eingabe als nacktes Stops-Dict) und wurde beim Notation-Umbau in 1.30.40 nicht mitentfernt
  - Die aktuelle Notation wird vollständig von services/api/tests/test_indicator_labels.py abgedeckt (Single Source, 10/10 grün — Skalar-, arange- und Sweep-Fälle für Name und Beschreibung)
  - Kein Code-Fix nötig: die Produktions-Aufrufer (api_config.py) übergeben immer das volle config_json, die alte Aufruf-Form (nacktes Stops-Dict) existiert nicht mehr
  - Volle Test-Suite nach der Löschung grün (466 bestanden)

### Files
- tests/test_indicator_labels.py



## [1.30.51] - 06.07.2026

### Fixed
- Rules-Engine (nativer Pfad): disjunkte Entry-/Exit-Sweep-Achsen werden jetzt zum vollen Kreuzprodukt gekreuzt statt still falsch gerechnet (Audit-Befund 1, Ticket 51)
  - Vorher lieferten Läufe, deren Entry- und Exit-Regeln verschiedene Parameter-Achsen sweepen, ohne Fehlermeldung falsche Ergebnisse: Out-of-bounds-Read der Entry-Maske (Numba ohne Boundscheck), stiller Kollaps der stateful Exit-Achse oder Diagonal-Paarung gleich breiter Achsen — der frühere N5-Blanket-Guard war mit Ticket 47 entfallen
  - Kreuz-Logik aus _combine_broadcast (Ticket 49) in geteilte Helper extrahiert (_pairwise_alignable_names, _cross_target_from_indexes); evaluate_rules_native baut die Combo-Achse bei nicht-alignbaren Quellen als Kreuzprodukt und expandiert Entry-Masken, statische Exit-Masken und stateful Series-Bundles darauf (Bundle-Bau in _build_series_bundle ausgelagert)
  - Entry-Achse als echte Teilmenge der Exit-Achse (vorher ebenfalls Out-of-bounds) wird mit expandiert; Portfolio-Spaltenzahl stimmt jetzt mit count_total_combos überein
  - Invarianten-Check _assert_single_combo_axis nach der Expansion: alle mehrspaltigen Quellen müssen die Combo-Achse tragen — künftige Regressionen brechen laut statt still
  - Regressionstests tests/test_native_disjoint_axes.py: alle drei Fehlpfade als Kreuzprodukt-Tests mit Kombi-für-Kombi-Bit-Parität gegen Einzel-Läufe, dazu Teilmengen-Fall und vier Positiv-Konstellationen (8 Tests); bestehende Engine-/Runner-Suiten unverändert grün

### Files
- user_data/strategies/generic/rules_engine.py
- tests/test_native_disjoint_axes.py



## [1.30.50] - 06.07.2026

### Added
- Chart-Playground: Backtest-Config-Browser als Tabellen-Popup neben dem Dropdown
  - Icon-Button neben dem Label 'Backtest-Config' öffnet ein Modal mit allen Backtest-Configs als Tabelle im Stil der Backtest-Config-Liste (Badges für Symbol/Exchange/TF)
  - Zeilen-Klick wählt die Config und füllt die Playground-Felder über den bestehenden Change-Handler vor
  - Gleiche Filter wie auf der Backtest-Config-Seite: TF, Symbol, OHLC-Fenster (ab/bis), Qualität min/max, Zurücksetzen, plus Volltextsuche
  - Datenqualitäts-Spalte (farbige Badges) aus /api/config/backtest/quality, einmal geladen und gecacht; während des Nachladens zeigt die Zelle einen Spinner statt eines Strichs
  - Alle Spalten klickbar sortierbar (numerisch bzw. alphabetisch, leere Werte ans Ende), aktive Spalte mit Sortierpfeil
  - Speist sich aus dem bereits geladenen state.backtestConfigs, kein neuer Endpunkt; das Select-Feld bleibt unangetastet

### Files
- services/frontend/templates/chart_playground/index.html



## [1.30.49] - 05.07.2026

### Changed
- OHLC-Job-Tabelle (Konfiguration -> OHLC-Daten) auf DataTable umgestellt mit Zähler, Status-Badges und Massenlöschung nach Status
  - Job-Tabelle nutzt jetzt eine client-side DataTable nach Design-Guide-Standard: Auswahlbox (10/25/50/100/Alle), Info und Paging im Footer; lädt alle Jobs statt nur die letzten 10
  - Titel zeigt die Gesamtzahl der Jobs, daneben Status-Zähler-Badges (nur Stati mit Anzahl groesser 0), gespeist aus dem bestehenden /data/jobs/summary-Endpunkt
  - Drei Massenlösch-Buttons in der Card-Header-Row: completed, failed und queued löschen; queued storniert zusätzlich die wartenden RQ-Jobs, running ist bewusst ausgenommen
  - Neuer Backend-Endpunkt DELETE /api/config/data/jobs/by-status/{status} (erlaubt completed, failed, queued; sonst 400)
  - Buttons, Titel-Zähler-Badges und Status-Spalte tragen einheitlich dieselben Status-Begriffe (running/completed/failed/queued)
  - Einzel-Löschen/Abbrechen bleibt erhalten und läuft jetzt über einen delegierten Handler, der Polling und Paging übersteht

### Files
- services/api/routes/api_config.py
- services/frontend/templates/config/data_files.html



## [1.30.48] - 05.07.2026

### Added
- Backtest-Config-Tabelle: Auswahl per Checkbox, Download nur für angehakte Configs
  - Neue Auswahl-Checkbox-Spalte pro Zeile plus Select-All im Tabellenkopf (mit Zwischenzustand fuer Teilauswahl)
  - Der Button heisst jetzt 'Ausgewaehlte Daten herunterladen' und legt OHLC-Jobs nur fuer die angehakten Configs an; ohne Auswahl erscheint ein Hinweis statt eines Requests
  - Auswahl wird in einem selectedIds-Set gehalten und uebersteht Paginierung, Filter und Redraw; Select-All wirkt nur auf die aktuell gefilterten Zeilen
  - Endpunkt POST /api/config/data/download-all nimmt optionales config_ids entgegen und filtert die Aggregation per WHERE id = ANY(:config_ids); ohne config_ids bleibt das Altverhalten (alle Configs)
  - Render-Fix: DataTables liefert den Zell-Wert als String und rendert Zeilen-Nodes ohne deferRender einmal vor - Auswahl-State wird daher ueber Number-Normalisierung und rows().invalidate('data').draw(false) zuverlaessig neu gezeichnet

### Files
- services/frontend/templates/config/backtest_configs.html
- services/api/routes/api_config.py



## [1.30.47] - 05.07.2026

### Added
- Backtest-Config-Liste: Filter für Timeframe, Symbol, OHLC-Zeitfenster und Qualität
  - Timeframe- und Symbol-Dropdowns, automatisch aus den geladenen Configs befüllt (exakter Treffer)
  - OHLC-Abdeckungsfenster (ab/bis): zeigt Configs mit ohlc_start >= ab UND ohlc_end <= bis
  - Qualitäts-Filter Min/Max (Prozent); Configs ohne Qualitätswert werden bei gesetztem Min/Max ausgeblendet
  - Zurücksetzen-Button leert alle Filter
  - Alle Filter greifen zusätzlich (UND) zur Volltextsuche über einen DataTable.ext.search-Custom-Filter

### Files
- services/frontend/templates/config/backtest_configs.html



## [1.30.46] - 05.07.2026

### Fixed
- Chart-Playground: Race Condition im grünen Entry-Hintergrund behoben — überlappende Refreshes hinterließen verwaiste Overlays
  - Der grüne Entry-Hintergrund wird bei jeder Regeländerung per entry-signals-Fetch neu geholt. Ein Fetch (~0,9 s über 2 Jahre 5m-Daten) dauert länger als der Debounce (400 ms), sodass sich Refreshes überlappten.
  - Ohne Concurrency-Schutz hängte ein zurückkehrender Fetch sein Overlay auch dann an, wenn bereits ein neuerer Refresh lief — das alte Band blieb als Leiche am Chart hängen und wurde nie entfernt.
  - Folge: Beim Aufbauen einer zweiten UND-Bedingung blieben Overlays aus Zwischenzuständen (z.B. nur die weite Bedingung) liegen und stapelten sich, sodass die grüne Fläche mit mehr Bedingungen größer statt kleiner wirkte.
  - Fix: Generations-Zähler cpEntryBgEpoch — jeder Refresh bekommt eine Nummer; ein Fetch hängt sein Band nur an, wenn seine Nummer noch aktuell ist, sonst wird es verworfen. Rein im Frontend, Engine und Datenmodell unverändert (Backend rechnet nachweislich korrekt UND).
  - Verifiziert im Browser: nach 5 provozierten überlappenden Refreshes bleibt die grüne Fläche bit-genau die saubere Zwei-Bedingungs-Fläche (16652 Pixel), keine Akkumulation.

### Files
- services/frontend/templates/chart_playground/index.html



## [1.30.45] - 05.07.2026

### Changed
- Chart-Playground: Portfolio-Card als eigenständige Card unter die Analyse-Tabs verschoben und Dropdown-Höhe angeglichen
  - Portfolio-Card aus dem Tab-Pane 'Strategie / Iteration' herausgelöst und als eigene Card direkt unter der Tab-Card platziert (bleibt so tab-übergreifend sichtbar)
  - Breite wieder auf 6/12 (col-md-6) wie die Indikatoren-Card
  - Dropdowns in der Portfolio-Card (size_type, stop_exit_price, stop_order_type) auf Input-Höhe angeglichen (27px statt 21px) - form-select-sm erhielt sonst nur Tablers 1px Padding-y, während form-control-sm über die Card-Regel auf 27px kommt; Fix auf #cpPortfolioFields beschränkt

### Files
- services/frontend/templates/chart_playground/index.html
- services/frontend/static/css/app.css



## [1.30.44] - 05.07.2026

### Fixed
- Chart-Playground und Backtest-Runner: TA-Lib-Indikatoren wurden ab der ersten Datenlücke konstant (flache Linie), weil ein einzelnes durch Resampling entstandenes NaN via TA-Lib bis zum Serienende propagiert. Behoben durch NaN-sicheren Indikator-Lauf (skipna).
  - Ursache: Beim Per-Indikator-Timeframe erzeugt das Resampling für Zeitfenster ohne zugrundeliegende Basis-Bars (Datenlücken) NaN-Bars. TA-Lib (und die meisten talib-basierten Indikatoren) propagieren ein einzelnes NaN in der Mitte der Serie bis zum Ende; realign_closing(ffill=True) schrieb den letzten gültigen Wert dann konstant bis zum Rand fort.
  - Fix: Neuer zentraler Helfer run_indicator_nan_safe(factory, ...) ruft factory.run mit skipna=True und split_columns=True auf (kanonischer VBT-Weg). Der Indikator läuft nur auf den Nicht-NaN-Werten, Ergebnisse werden an die Originalpositionen zurückgesetzt. split_columns ist Voraussetzung, damit skipna auch bei Multi-Combo-Läufen greift.
  - Eingesetzt an allen factory.run-Stellen: build_indicators (Basis-tf und Per-Indikator-tf) im Spec-Runner sowie compute_indicators (Chart-Playground-Vorschau) — Vorschau und echter Lauf teilen denselben Pfad.
  - Ohne NaN-Werte ist der Fix ein No-Op: auf lückenlosem Zeitraum bit-identische Indikatorwerte (verifiziert, 20161 Werte je Indikator). Bestehende Test-Suite grün (83 passed).

### Files
- user_data/strategies/generic/indicator_factory.py
- services/api/routes/api_chart_playground.py



## [1.30.43] - 05.07.2026

### Added
- Testset-Detailseite: Spalten OHLC Start, OHLC End und Qualität in der Backtest-Config-Tabelle
  - Drei neue Spalten rechts neben Timeframe: OHLC Start und OHLC End (Anzeige DD.MM.YYYY, chronologisch sortierbar via ISO in data-order) sowie Datenqualität pro Config fuer den eingestellten OHLC-Zeitraum.
  - Qualitaet als farbige Badge (gruen >= 99,5 Prozent / gelb >= 90 Prozent / rot darunter), identische Formatierung wie in der Backtest-Config-Liste.
  - Kein neuer Backend-Code fuer die Qualitaet noetig: bestehender Endpoint /api/config/backtest/quality wird per Fetch nachgeladen und in serverseitig gerenderte Platzhalter-Zellen gefuellt; nicht bestimmbare Werte via data-order -1 einsortiert.
  - views_testsets: ohlc_start/ohlc_end in die Config-Daten des Testset-Formulars aufgenommen.

### Files
- services/api/routes/views_testsets.py
- services/frontend/templates/testsets/detail.html



## [1.30.42] - 05.07.2026

### Added
- Backtest-Configs: Bulk-Download aller OHLC-Daten und zeitraum-bezogene Datenqualitäts-Anzeige
  - Button 'Alle Daten herunterladen' auf /config/backtest: neuer Endpoint POST /api/config/data/download-all aggregiert exchange/symbol/timeframe über alle Backtest-Configs, lädt fehlende Symbole ab frühestem ohlc_start bis jetzt (UTC) und schreibt vorhandene per Update-Job bis heute fort. Nur binance; nicht unterstützte Exchanges werden übersprungen und gemeldet.
  - Neue Spalte 'Qualität' in der Config-Liste: Endpoint GET /api/config/backtest/quality berechnet je Config die Datenqualität im eingestellten OHLC-Zeitraum [ohlc_start, ohlc_end]. Anders als die Gesamtqualität auf /config/data erfasst das auch fehlende Ränder (Datei beginnt später oder endet früher als der Config-Zeitraum).
  - Effiziente Berechnung: HDF5-Datei je (exchange, timeframe) nur einmal geöffnet, Zeit-Index je Symbol einmal via select_column geladen, pro Config per searchsorted gezählt; Wiederverwendung von _quality_pct mit den Config-Grenzen.
  - Fehlende Daten im Zeitraum werden als 0 Prozent (rote Badge) angezeigt statt als Bindestrich; Bindestrich nur noch bei nicht bestimmbarer Kennzahl (unbekannter Timeframe oder fehlender Zeitraum).
  - Unit-Tests für _config_range_quality (volle Abdeckung, fehlender Rand, keine Daten -> 0 Prozent, unbekannter Timeframe, fehlender Zeitraum, negative Zeitspanne).

### Files
- services/api/routes/api_config.py
- services/frontend/templates/config/backtest_configs.html
- tests/test_config_range_quality.py



## [1.30.41] - 05.07.2026

### Changed
- Indicator-Config-Tabelle umgestaltet und Beschreibungs-Freitext vorangestellt
  - Aktionen-Spalte verschlankt: nur der Bearbeiten-Button bleibt sichtbar, Kopieren/Als JSON exportieren/Löschen wandern in ein Drei-Punkte-Dropdown (per position:fixed positioniert, damit es nicht vom table-responsive-Container abgeschnitten wird)
  - Indikatoren-Spalte: Sonderschlüssel _stops wird nicht mehr als Badge angezeigt (steckt in jeder Config)
  - Indikator-Badges brechen nach 4 pro Reihe um, jede Reihe für sich zentriert (auch die letzte Teilreihe)
  - Spaltenbreiten zugunsten von Name/Beschreibung gewichtet: Name 22 Prozent, Beschreibung 32 Prozent, Iteration schmal (8 Prozent), Aktionen-Spalte auf Inhaltsbreite geschrumpft
  - ID-Spalte zentriert
  - Beschreibungs-Generator: manueller Freitext steht jetzt VOR der Indikator-Auflistung (Freitext | Auflistung statt Auflistung | Freitext)

### Files
- services/frontend/templates/config/indicator_configs.html
- services/frontend/templates/config/indicator_config_edit.html
- services/api/utils/indicator_labels.py



## [1.30.40] - 05.07.2026

### Changed
- Indikator-Konfiguration: Name/Beschreibung neu generiert, Dropdown-Beschreibung als schwebender Tooltip
  - Config-Name ist jetzt selbsttragend: <Konzept>-<Iteration>-(<Kombinationen>) <Stops> mit allen Stops (TP/SL/TSL/TD, Format-Wort per Komma, Sweep als min-max (n)); optionaler manueller Freitext hinter ' : '
  - Config-Beschreibung listet jetzt die Indikatoren mit ihren Werten/Wertebereichen in topologischer Reihenfolge (<name>: <param> <wert>, ...; <name2>: ...) statt der Stops; manueller Freitext hinter ' | '
  - Neue Funktion describe_indicator_params in indicator_factory.py als Basis fuer die Indikator-Auflistung (auch feste Skalar-Parameter, ohne Inputs/Meta-Keys)
  - Generier-Buttons 'Titel'/'Beschreibung' im Config-Editor bewahren den manuell gepflegten Freitext (' : ' bzw. ' | ')
  - Chart-Playground: Dropdown 'Indikator-Konfiguration' zeigt pro Zeile nur den Titel; die Beschreibung erscheint beim Hover als schwebender, gut lesbarer Tooltip (verschiebt das Layout nicht)

### Files
- services/api/utils/indicator_labels.py
- user_data/strategies/generic/indicator_factory.py
- services/frontend/templates/config/indicator_config_edit.html
- services/frontend/templates/chart_playground/index.html
- services/api/tests/test_indicator_labels.py



## [1.30.39] - 05.07.2026

### Changed
- Chart-Playground: Indikator-Konfigurations-Dropdown von nativem Select auf Custom-Dropdown mit Beschreibungsspalte umgebaut und nach Konzept/Iteration gefiltert
  - Natives <select> durch Custom-Dropdown ersetzt; der Wert lebt in einem versteckten Input (cpIndCfgSelect), damit alle bestehenden .value-Zugriffe unverändert weiterlaufen
  - Jeder Eintrag zeigt jetzt zwei Spalten: Name (feste Breite) plus dazugehörige Beschreibung, damit gleichnamige Konfigurationen (z.B. mehrfach 'VWMA-4 - 9 Kombi. 30/15') am Anker/result-Verweis unterscheidbar sind
  - Gruppen-Überschriften 'Diese Iteration' / 'Dieses Konzept' im Grün der Setup-ok-Meldung (#2fb344)
  - Hover-Highlight der Einträge im App-Primärblau (var(--tblr-primary)) mit weißer Schrift, angelehnt an das native Select-Verhalten
  - Menü verbreitert (max-width 900px), Beschreibungen umbrechen statt horizontal zu scrollen
  - Filter statt Gruppierung: ohne Auswahl alle Konfigurationen, bei gewähltem Konzept nur dessen, bei gewählter Iteration nur deren Konfigurationen; passt nichts, erscheint ein sichtbarer Hinweis statt leerem Menü
  - Einträge werden in allen Fällen alphabetisch (numerisch-bewusst: VWMA-4 vor VWMA-10) sortiert

### Files
- services/frontend/templates/chart_playground/index.html
- services/frontend/static/css/app.css



## [1.30.38] - 03.07.2026

### Changed
- Chart-Playground: Preisachse mit vier Nachkommastellen bei Preisen unter 1 Euro und breitere Stops-Wertfelder
  - Preis-Nachkommastellen der Candle-Serie und Indikator-Linien an die Groessenordnung gekoppelt: Referenzpreis (letzter Close) unter 1 wird mit Precision 4 (minMove 0.0001) formatiert, sonst weiterhin 2 Stellen
  - Stops-Wertfelder (tp/sl/tsl/td) von 58px auf 90px verbreitert, damit Werte wie 0.017 nicht mehr abgeschnitten werden; Indikator-Param-Felder bleiben bei 58px

### Files
- services/frontend/templates/chart_playground/index.html
- services/frontend/static/css/app.css



## [1.30.37] - 03.07.2026

### Changed
- Chart-Playground: Anzeige-Timeframe und Zoom-Bereich werden im Setup gespeichert und beim Setup-Laden wiederhergestellt statt hart auf 1D+Fit zu setzen
  - collectSetupConfig speichert visual_tf (Anzeige-TF, null = Basis-TF) und visual_range (sichtbarer Zoom-Bereich) in ui_state_json
  - applySetupConfig aktiviert einen Restore-Modus (cpRestoreLayout), sobald visual_tf im Setup vorhanden ist
  - loadChart ueberspringt beim Restore setDefaultVisualTf und fitContent und setzt den gespeicherten Anzeige-TF; runBacktestLite stellt nach dem Equity-Overlay den gespeicherten Zoom-Bereich her statt zu fitten
  - Alt-Setups ohne visual_tf und der Result-Ladepfad behalten unveraendert das Verhalten 1D+Fit
  - Offen/unverifiziert: separater Fit-Button-Reset beim Result-Laden noch nicht abschliessend geprueft; Alt-Setups muessen zum Wirksamwerden neu gespeichert werden

### Files
- services/frontend/templates/chart_playground/index.html



## [1.30.36] - 03.07.2026

### Fixed
- Label-Notation crasht nicht mehr bei Stop-Sweeps (preview-labels/generate-labels)
  - Die Notations-Routen POST /api/config/indicator/preview-labels und /{id}/generate-labels warfen HTTP 500 (TypeError: float() argument must be a string or a real number, not 'list'), sobald ein _stops-Wert eine Sweep-Liste statt eines Skalars war (seit Ticket 47 gueltig).
  - Ursache: Der Label-Builder kannte nur Skalar und arange-Dict; eine Sweep-Liste fiel in den drei Formatierern auf _clean_num durch und rief float() auf einer Liste auf.
  - Fix: Sweep-Erkennung ueber die kanonischen Motor-Detektoren is_stop_sweep + expand_stop_values (Single Source, kein zweiter Parser). Liste und arange-Dict werden nun identisch als kompakter Bereich min-max (n) dargestellt, z. B. TD 1-999 (35) oder TP 10-40% (13); im Namen tp/sl als min-max ohne (n), da die Kombizahl schon im Kombi.-Teil steht. Skalar-Verhalten unveraendert.
  - Neue Unit-Tests in tests/test_indicator_labels.py (Skalar/Liste/arange fuer TP-SL-TD) inklusive Akzeptanzfall der TD-Sweep-Config.

### Files
- services/api/utils/indicator_labels.py
- tests/test_indicator_labels.py



## [1.30.35] - 03.07.2026

### Added
- Schrittweiter Nachbarschafts-Modus (--tolerance-steps) für Result-Lookup, Kreuztest und Combo-Trace
  - Neues Flag --tolerance-steps <N> an result-lookup, kreuztest und combo-trace (Toolbox); spannt die Nachbarschaft je Parameter in N Raster-Schritten statt einer skalaren Distanz. Loest die Plateau-Pruefung fuer Laeufe mit ungleichen Schrittweiten je Achse.
  - Server: get_run_param_steps leitet die Schrittweite je Parameter aus dem kleinsten positiven Abstand der distinct-Werte des Runs ab (eingefrorene Achse mit nur einem Wert -> Schritt 0 -> exakter Match). Bei Mehr-Run-Lookups wird die Schrittweite je Run einzeln abgeleitet (Raster koennen differieren) und die Zweige werden OR-verknuepft.
  - Neuer Query-Param tolerance_steps an GET /api/backtest/runs/{run_id}/results/lookup und GET /api/backtest/results/lookup; tolerance und tolerance_steps schliessen sich aus (400).
  - --tolerance (skalar) bleibt unveraendert rueckwaertskompatibel; Float-Epsilon gegen arange-Artefakte beibehalten.
  - Tests: tests/test_result_lookup_by_params.py um 7 Faelle ergaenzt (Schrittweiten-Ableitung, echte plus/minus 1-Schritt-Nachbarschaft bei ungleichen Rastern, Kontrast zur skalaren Toleranz, eingefrorene Achse, arange-Float-Schritte, N-Skalierung, per-Run-Raster) - 18 gruen.

### Files
- user_data/utils/database/repository.py
- services/api/routes/api_backtest.py
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- tests/test_result_lookup_by_params.py



## [1.30.34] - 03.07.2026

### Changed
- Bestwert-Spalte in der Results-Tabelle verschlankt, sortierbar gemacht und dokumentiert; TP/SL sortierbar
  - Bestwert-Kriterium in der Results-Tabelle als schlichter, zentrierter Fliesstext aus internen Einzelbuchstaben (T/W/S/P), leerzeichengetrennt - kein Badge, keine Farbe; Langform je Buchstabe im Hover-Tooltip. Server liefert je Kriterium {short, long} (criteria_keys_to_badges)
  - Bestwert-Spalte sortierbar gemacht (Server sortiert best_criteria_json als Text; kein Kriterium via NULLIF+nullslast ans Ende)
  - TP/SL sortierbar gemacht - die per-Result aufgeloesten Stops liegen im Snapshot-JSON (full_config_snapshot_json); Sortierung per json_extract_path_text + Float-Cast, orderable:false im Frontend entfernt
  - Datenfehler behoben: best_criteria_json auf JSON(none_as_null=True) gestellt, damit 'kein Kriterium' als echtes SQL-NULL statt JSON-null gespeichert wird (korrektes nullslast)
  - Doku nachgezogen: SKILL.md (indicator-config-set/-labels, Bestwert-Persistenz), handbuch.md (Verb-Katalog + run-bestwerte), multiparameter-lauf.md (Persistenz + T/W/S/P-Spalte)

### Files
- services/api/routes/api_backtest.py
- services/api/utils/best_criteria_labels.py
- user_data/utils/database/models.py
- services/frontend/templates/backtest/results.html
- tests/test_best_criteria_labels.py
- .claude/skills/ds-strategie-session/SKILL.md
- documentation/project/handbuch.md
- documentation/knowledge/strategy-development/workflows/multiparameter-lauf.md
- documentation/todo/todo-toolbox.md



## [1.30.33] - 03.07.2026

### Added
- Toolbox-Lücken: nachträgliche Indicator-Config-Verknüpfung, Label-Generierung mit Zusatz und persistiertes Bestwert-Kriterium am Doku-Favoriten
  - PATCH /api/config/indicator/{id}: partieller Update-Endpoint (Schema IndicatorConfigPatch), schreibt nur uebermittelte Felder (exclude_unset) - config_json/_stops/Rest bleiben bit-genau
  - Toolbox-Verb indicator-config-set: bestehende Config nachtraeglich einem Konzept/einer Iteration zuweisen (oder Name/Beschreibung setzen) ohne vollen Body
  - Toolbox-Verb indicator-config-labels: Standard-Notation via preview-labels erzeugen, individuellen Zusatz als '<Notation> - <Zusatz>' anhaengen, mit --save nur Name/Beschreibung zurueckschreiben
  - DB-Spalte backtest_results.best_criteria_json (JSON, nullable) + Alembic-Migration 0014: haelt fest, welche der vier Bestwert-Kriterien ein Doku-Favorit gewonnen hat (stabile Keys, run-relativ nach Result-Loeschung sonst nicht mehr herleitbar)
  - Serverseitiges Key->Label-Mapping best_criteria_labels.py als Single Source; Results-API liefert fertige Labels im dt-Feld best_criteria
  - Endpoint POST /api/backtest/results/{id}/doc_favorite/mark: setzt roten Stern + Kriterium-Keys idempotent; Toggle-Off leert die Keys gekoppelt mit
  - run-bestwerte sammelt Mehrfach-Sieger-Keys und markiert per mark-Endpoint; run-favorites-list/kreuztest weisen die Kriterien aus der persistierten Spalte aus
  - Frontend: neue kompakte Badge-Spalte 'Bestwert' zwischen Stern- und ID-Spalte in der Results-Tabelle; dt-Spaltenindizes server- und toolboxseitig konsistent verschoben
  - Tests: test_indicator_config_patch, test_best_criteria_labels, test_doc_favorite_criteria (14 neu, gruen)

### Files
- services/api/routes/api_config.py
- services/api/routes/api_backtest.py
- services/api/utils/best_criteria_labels.py
- user_data/utils/database/models.py
- alembic/versions/0014_result_best_criteria.py
- services/frontend/templates/backtest/results.html
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- tests/test_indicator_config_patch.py
- tests/test_best_criteria_labels.py
- tests/test_doc_favorite_criteria.py
- documentation/todo/todo-toolbox.md



## [1.30.32] - 02.07.2026

### Added
- Result-Lookup per Parameter-Werten (API) und Auswerte-Verben für die Strategie-Toolbox (Favoriten-Liste, Metrik-Query, Kreuz-Test, Kombinations-Verfolgung, Plateau-Score, JSON-Ausgabe)
  - Neue API-Route GET /api/backtest/runs/{run_id}/results/lookup: Parameter-Werte als Query-Filter, EXISTS-Subqueries gegen backtest_result_params (Index idx_bpa_result_param); tolerance=0 = exakter Lookup mit Epsilon gegen arange-Float-Artefakte, tolerance>0 = Nachbarschafts-Modus (±Toleranz je Parameter, Plateau-Prüfung); unbekannte Parameter-Namen und nicht-numerische Werte geben 400 mit den vorhandenen Namen des Runs
  - Neue API-Route GET /api/backtest/results/lookup: derselbe Lookup über eine explizite Run-Menge (run_ids), Ergebnis mit Run-Kontext (run_id, symbol, timeframe), sortiert nach run_id
  - Query-Logik testbar in repository.py: lookup_result_rows_by_params, lookup_results_across_runs, get_run_param_names, get_scope_param_names, gemeinsamer Baustein _param_exists_conditions
  - Toolbox-Verb run-favorites-list: markierte Favoriten-Results einer Run-Menge ausgeben (reiner Read), Selektoren/Flags wie run-favorites-reset
  - Toolbox-Verb result-lookup: Results per Parameter-Werten nachschlagen (--tolerance fuer Nachbarschaft, --summary verdichtet zum Plateau-Score: Median/Mittel/Streuung des Total Return, Anteil profitabel, Bester/Schlechtester)
  - Toolbox-Verb result-query: kombinierte Metrik-Filter (--where "sharpe_ratio>=1.5,total_trades>=100", nur >=/<=, UND-verknuepft) ueber die vorhandenen serverseitigen _min/_max-Filter des dt-Endpunkts
  - Toolbox-Verb kreuztest: rote Doku-Favoriten (Bestwerte) aus Run A in Run B nachschlagen, Vergleichstabelle der Metriken; --from-testset-run/--to-testset-run paart ganze Testset-Laeufe per Symbol+Timeframe (Walk-Forward-Auslesung), Runs ohne Gegenstueck werden ausgewiesen
  - Toolbox-Verb combo-trace: eine Parameterkombination ueber eine Run-Menge verfolgen (1:N), Selektoren wie run-bestwerte, Runs ohne Treffer werden ausgewiesen
  - --json-Flag fuer acht Lese-/Auswerte-Verben (result-list, run-top-results, run-best, run-favorites-list, result-lookup, result-query, kreuztest, combo-trace): rohe Items als JSON statt Markdown
  - 11 Tests fuer die Lookup-Query-Logik gegen die PostgreSQL-Test-DB (exakt, Float-Artefakte, Subset, Toleranz, Run-Isolation, Limit/Total, Across-Runs, Scope-Parameter-Namen)
  - Doku nachgezogen: Werkzeug-Tabelle im Handbuch, Toolbox-Hilfetext, Routen-Index in api_backtest.py; To-Do-Dokument unter documentation/todo/ als lebendes Lueckenverzeichnis

### Files
- services/api/routes/api_backtest.py
- user_data/utils/database/repository.py
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- tests/test_result_lookup_by_params.py
- documentation/project/handbuch.md
- documentation/todo/todo.md



## [1.30.31] - 02.07.2026

### Fixed
- Indikator-Inputs mit Nicht-OHLCV-Namen (z.B. series_a/series_b bei custom:dwsCrossover) schlugen im Playground und Config-Editor fehl („Kein Mapping für Input")
  - Ursache: Input-Dropdowns zeigten den Default „close" nur optisch an — in den Zustand geschrieben wurde nichts, und das Backend kennt für frei benannte Inputs keinen Default
  - Inputs werden jetzt beim Anlegen eines Indikators und beim Laden von Setups/Configs sofort mit dem angezeigten Default (defaultInputSource) vorbelegt — Anzeige und Zustand sind deckungsgleich
  - Serialisierungs-Fallback vereinheitlicht: buildBacktestPayload und collectIndicatorConfigJson (Playground + Config-Editor) nutzen dieselbe Default-Quelle statt des rohen Inputnamens, der unbrauchbare Werte wie „series_a" in gespeicherte Configs schrieb
  - Verwaiste Konstante INPUT_DEFAULTS in beiden Templates entfernt

### Files
- services/frontend/templates/chart_playground/index.html
- services/frontend/templates/config/indicator_config_edit.html



## [1.30.30] - 02.07.2026

### Fixed
- Chart-Playground: Aktions-Buttons wieder am unteren Card-Rand, neue Indikatoren landen oberhalb der Stops-Zeile
  - Die Speichern-Leisten der Cards Indikatoren und Entry/Exit-Logic klebten seit dem JSON/Visuell-Umschalter direkt unter dem Inhalt (links unter der Stops-Zeile) statt am unteren Card-Rand — die Visuell-Panels reichen die Flex-Spalte jetzt weiter, damit margin-top:auto wieder greift
  - Beim Hinzufügen eines Indikators rutschte dieser hinter die Stops-Zeile ans Listenende — steht die Stops-Zeile am Ende, wird ihre Position jetzt mitgezogen: der neue Indikator wird letzter Indikator, Stops bleibt darunter
  - Eine bewusst per Drag in die Listenmitte gezogene Stops-Zeile bleibt unangetastet — nur die End-Position ist klebrig

### Files
- services/frontend/static/css/app.css
- services/frontend/templates/chart_playground/index.html



## [1.30.29] - 02.07.2026

### Changed
- Per-Indikator-Timeframe: „gleich“ ist jetzt der explizite Wert 'same' — null/fehlend bedeutet „Wert fehlt“ und schlägt bei der Verarbeitung sichtbar fehl (kein impliziter Fallback mehr)
  - normalize_tf (tf_resample.py): Sentinel TF_SAME='same' eingeführt; 'same' und tf gleich Basis-TF bedeuten „kein Resampling“; None/leer/Nicht-String wirft ValueError mit klarer Meldung statt still als „gleich“ durchzulaufen
  - spec_runner: Result-Metadaten übernehmen den tf verbatim aus dem Spec — kein stiller Default auf den Basis-Timeframe mehr bei fehlendem Key
  - Frontend (Chart-Playground + Indikator-Config-Editor): Dropdown-Wert 'same' mit Label „(gleich)“; ein null-tf erscheint als eigene Option „(fehlt)“ statt als „(gleich)“; neue Indikatoren starten mit 'same'
  - Schnell-Backtest im Playground sendet den tf verbatim statt ihn zum Basis-Timeframe aufzulösen (Inkonsistenz zu den Speicherpfaden beseitigt)
  - Beim Laden bleibt ein null-tf unangetastet (keine Korrektur); nur ein feinerer-als-Basis-tf wird weiterhin sichtbar auf 'same' umgestellt
  - Tests auf neue Semantik umgestellt und erweitert ('same' = No-Op, fehlender tf = ValueError); Doku indicators.md aktualisiert

### Files
- user_data/strategies/generic/tf_resample.py
- user_data/strategies/generic/indicator_factory.py
- user_data/strategies/generic/spec_runner.py
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html
- services/frontend/templates/config/indicator_config_edit.html
- documentation/knowledge/indicators.md
- tests/test_tf_resample.py
- tests/test_build_indicators_tf.py



## [1.30.28] - 02.07.2026

### Added
- Chart-Playground: Umschalter JSON/Visuell für die Indikatoren- und Entry/Exit-Logic-Card
  - Beide Cards haben im Header links neben den Aktions-Buttons eine Btn-Group JSON/Visuell (analog zum Editor der Indikator-Konfiguration)
  - JSON-Modus zeigt read-only die JSON-Quelle: Indikatoren-Card das config_json exakt im Save-Format (collectIndicatorConfigJson, inkl. _stops), Entry/Exit-Card die rules im spec_json-Format (cleanRules)
  - JSON wird bei jedem Umschalten frisch aus dem State erzeugt; die Hinzufügen-Buttons schalten automatisch auf Visuell zurück, damit keine veraltete JSON-Ansicht stehen bleibt
  - Umschalter ist als reines Darstellungs-Control vom Verwerfen des Schnellbacktest-Ergebnisses ausgenommen (Klasse cp-json-toggle in onSettingChanged)
  - Neue CSS-Klasse cp-json-view (formatiertes pre, Tabler-Theme-Variablen für Hell/Dunkel)

### Files
- services/frontend/templates/chart_playground/index.html
- services/frontend/static/css/app.css



## [1.30.27] - 02.07.2026

### Fixed
- Chart-Playground: Result-Laden zeigt konkrete Indikatorwerte des Results statt Sweep-Ranges des Laufs
  - _build_resolved_config prüft jetzt beide Level-Präfix-Schemata (vbt-Klassenname und Spec-Key) — die Rules-Engine benennt Param-Level per _uniquify_param_levels auf <spec_key>_<param> um, wodurch Ranges bislang unaufgelöst im Config-Snapshot blieben (betrifft auch den Recompute-Pfad)
  - GET /api/chart-playground/result-config/{id} löst die Snapshot-Indikatoren beim Lesen zusätzlich gegen actual_params_json nach, damit auch bereits gespeicherte Results mit unaufgelösten Ranges korrekt angezeigt werden
  - Indikator-Config-Dropdown wird beim Result-Laden nicht mehr vorbelegt — die Indikator-Config des Runs trägt das Sweep-Raster, nicht die Werte des Results

### Files
- user_data/utils/database/repository.py
- services/api/routes/api_chart_playground.py



## [1.30.26] - 02.07.2026

### Changed
- Toolbox: Indikator-Katalog filterbar gemacht und stille 4000-Zeichen-Kürzung behoben (Ticket 50)
  - playground-indicators ist jetzt ein eigenes Verb: ohne Filter kompakte Gruppen-Übersicht (Name + Anzahl je Gruppe), mit --group <name> nur diese Gruppe, mit --search <substring> case-insensitiv über id/name — beide Flags kombinierbar
  - Treffer-Ausgabe kompakt: eine Zeile je Indikator mit id/inputs/params (Namen)/outputs statt vollem JSON-Dump mit Defaults
  - _print_data weist Kürzungen jetzt immer sichtbar mit Original-Größe aus ([gekürzt: 4000 von N Zeichen — Filter nutzen]) — betrifft alle generischen GET-Verben, kein stilles Abschneiden mehr
  - Filter- und Format-Logik als reine Funktionen (_filter_indicators, _format_indicator_line) mit pytest-Tests ohne Netzwerk-Abhängigkeit
  - Handbuch-Abschnitt Toolbox-Werkzeuge und code-referenz.md (Service-Check) um die neuen Flags ergänzt

### Files
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- tests/test_toolbox_indicator_filter.py
- documentation/project/handbuch.md
- documentation/knowledge/strategy-development/code-referenz.md
- documentation/tickets/50-toolbox-indikator-katalog-filter-statt-kuerzung.md



## [1.30.25] - 02.07.2026

### Added
- Ticket 50 angelegt: Toolbox-Indikator-Katalog filterbar machen (--group/--search), stille 4000-Zeichen-Kürzung in _print_data durch expliziten Kürzungs-Hinweis ersetzen
  - Befund aus der Strategie-Ideen-Verifikation: toolbox.py playground-indicators zeigt nur die ersten 4000 Zeichen (_print_data, toolbox.py:1195) — die Gruppen talib/vbt/wqa101 (fast 300 Indikatoren) fehlen stillschweigend in der Ausgabe
  - Kürzung betrifft generisch alle GET-Antworten des Routen-Pfads, nicht nur den Katalog
  - Ticket fordert: Filter-Flags statt größerem Dump, kompakte Ausgabe je Indikator, sichtbarer Kürzungs-Hinweis mit Original-Größe, Handbuch-Update

### Files
- documentation/tickets/50-toolbox-indikator-katalog-filter-statt-kuerzung.md



## [1.30.24] - 02.07.2026

### Added
- GUI für DB-Snapshot Export/Import unter Konfiguration
  - Neuer Menuebereich Konfiguration -> DB Snapshot mit den Punkten DB Exportieren und DB Importieren
  - Export erzeugt einen vollstaendigen DB-Snapshot per pg_dump direkt aus dem App-Container (TCP-Verbindung zur DB) und speichert ihn im Ordner db_snapshot/data/ (datierter Snapshot plus seed.dump als Pointer); zusaetzlich Download-Option im Browser
  - Import spielt den gespeicherten Snapshot per pg_restore zurueck - ohne Compose-Stack-Neustart: fremde DB-Verbindungen werden gekappt, das public-Schema neu aufgesetzt, die TimescaleDB-Extension geladen und die gecachte SQLAlchemy-Engine verworfen (pool_pre_ping baut neu auf)
  - postgresql-client-17 ins App-Image aufgenommen (passend zur TimescaleDB-Server-Version pg17, aus dem Debian-Standard-Repo)
  - Bind-Mount des Snapshot-Ordners in den App-Container in der lokalen Compose-Datei
  - Umbenennung: Ordner seed/ nach db_snapshot/, CLI-Skripte export_seed.py/import_seed.py nach db_export.py/db_import.py; .gitignore und Projekt-Doku nachgezogen
  - Verifiziert: Export/Import-Zyklus mit echtem Datenbankbestand verlustfrei - Zeilenzahlen aller Tabellen vor/nach identisch, TimescaleDB-Hypertables korrekt wiederhergestellt, App-Zugriff nach Import intakt

### Files
- services/api/seed_service.py
- services/api/routes/views_seed.py
- services/api/app.py
- services/api/Dockerfile
- services/frontend/templates/config/seed_export.html
- services/frontend/templates/config/seed_import.html
- services/frontend/templates/base.html
- docker-compose-local.yml
- db_snapshot/db_export.py
- db_snapshot/db_import.py
- .gitignore
- CLAUDE.md



## [1.30.23] - 02.07.2026

### Added
- Benutzerhandbuch angelegt und Run-Analyse-Maske sprachlich geschärft
  - Neues documentation/project/handbuch.md als wachsendes Nachschlagewerk zur Bedienung; Kapitel Run-Analyse (Erweiterte Datenberechnung mit Start/Stop/Reset, Vorher/Nachher-Datentabelle auf Feldebene, Abschnitt Warum drei Stufen) und Toolbox-Werkzeuge
  - Inhaltsverzeichnis mit Anker-Links statt nummerierter Ueberschriften, damit Einschuebe kein Umnummerieren erzwingen
  - toolbox-werkzeuge.md ins Handbuch verschoben (Single Source); Verweise in ds-strategie-session (SKILL.md, toolbox.py) nachgezogen
  - Analysemaske: Label Berechnung zu Erweiterte Datenberechnung umbenannt, pretitle Backtesting durch Erklaerungstext ersetzt
  - projekt.md: toter Verweis auf knowledge/project-structure.md (gitignored) entfernt, Verweis auf handbuch.md ergaenzt

### Files
- documentation/project/handbuch.md
- documentation/project/projekt.md
- services/frontend/templates/backtest/analyse.html
- .claude/skills/ds-strategie-session/SKILL.md
- .claude/skills/ds-strategie-session/scripts/toolbox.py



## [1.30.22] - 02.07.2026

### Fixed
- Multiparameter-Lauf kreuzt getrennte Indikator-Achsen jetzt korrekt (Ticket 49)
  - Bug 1 in _combine_broadcast: Disjunkte Indikator-Param-Level gleicher Breite wurden bisher positionsweise gezippt (Diagonale, z.B. 3x3 -> 3 statt 9), weil vbt.broadcast keine Exception warf und der Kreuz-Pfad nie griff. Ersetzt durch einen Gate-Check auf die Spalten-Level-Namen: echt alignbare Level (Teilmenge/Gleichheit, Carrier wie symbol) werden aligned, disjunkte private Level immer ueber cross_indexes gekreuzt.
  - Bug 2 in _build_static_block_arr: Eine Teilmengen-Exit-Maske (schmaler als die volle Combo-Breite, aber >1) sprengte die arr[b]=m-Zuweisung. Sie wird jetzt per vbt.broadcast(columns_from=combo_columns) auf den vollen Combo-Spalten-Index expandiert statt truncatet; combo_columns wird aus evaluate_rules_native durchgereicht.
  - Verifiziert ueber echte Worker-Laeufe: gleiche Laengen 81, ungleiche Laengen mit Teilmengen-Exit 108 (vorher Absturz), zwei gleiche Indikator-Klassen 486, Regression A-D 27/81/81/81, VWMA-Anker 33813 unveraendert.
  - Neuer Unit-Test in tests/test_rules_engine_combine_broadcast.py fuer den Bug-1-Kern (zwei disjunkte Achsen gleicher Breite -> volles Kreuzprodukt statt Diagonale).

### Files
- user_data/strategies/generic/rules_engine.py
- tests/test_rules_engine_combine_broadcast.py



## [1.30.21] - 01.07.2026

### Fixed
- Kombinationen-Anzahl beim Rerun eines Runs korrekt statt 0 anzeigen
  - restart_run() setzte n_combinations hart auf 0 und rechnete die Vorabschaetzung nicht neu; die Runs-Tabelle zeigte deshalb ab dem Rerun bis zum erfolgreichen Abschluss 0 (bei Fehlschlag dauerhaft).
  - Jetzt wird n_combinations analog zum Create-Pfad ueber _count_combinations aus der bestehenden indicators_config_json des Runs neu berechnet - gleiche Zaehl-Wahrheit (count_total_combos) wie create_backtest_run.
  - Verifiziert an Run 28: Neuberechnung ergibt 33813 statt 0.

### Files
- services/api/routes/api_backtest.py



## [1.30.20] - 01.07.2026

### Added
- Job-Übersicht (Monitoring-Maske) für Queues, Worker und Job-Status
  - Neue Seite /monitor, erreichbar über Konfiguration → Job-Übersicht (zwischen OHLC-Daten und Wissens-Index)
  - Live-Sicht aus Redis: RQ-Queues (backtest, recompute, ohlc_download) mit wartend/laufend/fehlgeschlagen sowie aktive Worker mit Zustand, aktuellem Job und letztem Lebenszeichen
  - Status-Zusammenfassung je Job-Tabelle (Backtest-Runs, Recompute-Jobs, OHLC-Downloads, TestSet-Läufe, Vault-Reindex) sowie eine Liste offener Jobs mit Laufzeit zum Erkennen hängender Jobs
  - Auto-Update-Schiebeschalter (5 Sekunden, standardmäßig aus) analog zur Runs-Seite
  - Roter Button 'Fehlgeschlagene löschen' leert per DELETE /api/monitor/failed die RQ-Failed-Registries aller Queues
  - Status-Zählung je Tabelle per SQL-GROUP-BY, damit der Abruf auch bei kurzem Intervall leicht bleibt

### Files
- services/api/routes/api_monitor.py
- services/api/routes/views_monitor.py
- services/frontend/templates/monitor/overview.html
- services/api/app.py
- services/frontend/templates/base.html



## [1.30.19] - 01.07.2026

### Added
- Reaper fuer verwaiste Recompute-Jobs plus Analyse-Seiten-UI (Status, Infobox, Toasts)
  - Reaper (services/api/reap_stale_jobs.py + reap_logic.py): neuer periodischer Scheduler-Task (alle 5 Minuten) gleicht die Tabelle backtest_jobs mit dem echten RQ-Zustand ab. Behebt dauerhaft, dass die Worker-/Berechnungs-Anzeige auf 'aktiv' haengen blieb, wenn ein Worker mitten in einem Job starb.
  - Verwaist-Erkennung versionsunabhaengig ueber Job.exists(): running-Job tot, wenn RQ-Job fehlt oder started_at aelter als Timeout+Puffer (900s); queued-Job, wenn Redis den Job verloren hat. Verwaiste Jobs werden neu eingereiht statt sofort failen; erst nach 3 Startversuchen (Original + 2 Neustarts) -> failed ('3x Abbruch mit Fehler'). Neue Spalte backtest_jobs.retry_count (Migration 0013) zaehlt die Neustarts. Atomarer Claim verhindert das Ueberschreiben gerade abgeschlossener Jobs. Scheduler-Image auf rq==2.10.0 (identisch zu den Workern). Unit-Tests in tests/test_reap_logic.py.
  - Analyse-Seite (services/frontend/templates/backtest/analyse.html): Infobox erklaert die Buttons Start/Stop/Reset und dass es ein laengerer Hintergrund-Job ist (Fliesstext, Befehle in den jeweiligen Button-Farben; d-block hebt das Tabler-Flex des .alert auf).
  - Analyse-Seite: waehrend die Berechnung laeuft wird der Status rot und fett ('laeuft - X / Y ...') und der Fortschrittsbalken animiert, damit der langsame Fortschritt nicht wie eingefroren wirkt. Die Berechnungs-Card ist auf halbe Breite (col-md-6, buendig mit der linken Heatmap) gesetzt.
  - Analyse-Seite: Start/Stop/Reset geben sofort eine Toast-Rueckmeldung ('wird gestartet/gestoppt/zurueckgesetzt - einen Moment') und eine Abschluss- bzw. Fehlermeldung; der Toast-Container sitzt direkt unter der Card.

### Files
- services/api/reap_stale_jobs.py
- services/api/reap_logic.py
- services/scheduler/crontab
- services/scheduler/Dockerfile
- alembic/versions/0013_backtest_job_retry_count.py
- user_data/utils/database/models.py
- tests/test_reap_logic.py
- services/frontend/templates/backtest/analyse.html



## [1.30.18] - 01.07.2026

### Added
- Reaper-Task raeumt verwaiste Recompute-Jobs automatisch auf
  - Neuer periodischer Scheduler-Task (services/api/reap_stale_jobs.py, alle 5 Minuten) gleicht die Tabelle backtest_jobs mit dem echten RQ-Zustand ab. Behebt das Problem, dass die Worker-Anzeige der Runs-Liste dauerhaft 'aktiv' zeigte, wenn ein Worker mitten in einem Recompute-Job starb (Neustart/Absturz/Timeout) und die DB-Zeile fuer immer auf queued/running haengen blieb.
  - Verwaist-Erkennung versionsunabhaengig ueber Job.exists(): running-Job gilt als tot, wenn der RQ-Job fehlt oder started_at aelter als Timeout+Puffer (900s) ist; queued-Job, wenn Redis den Job verloren hat.
  - Verwaiste Jobs werden neu eingereiht statt sofort auf failed gesetzt. Erst nach insgesamt 3 Startversuchen (Original + 2 Neustarts) wird der Job auf failed gesetzt (Meldung '3x Abbruch mit Fehler'). Neue Spalte backtest_jobs.retry_count (Migration 0013) zaehlt die Neustarts.
  - Atomarer Claim (Update nur solange queued/running) verhindert das Ueberschreiben eines Jobs, den ein Worker im selben Moment abschliesst. Der manuelle Rerun-Weg (Run neustarten / Analyse erneut starten) bleibt unberuehrt.
  - Reine Entscheidungslogik in services/api/reap_logic.py ausgelagert (is_stale, classify_job) und per Unit-Test abgedeckt (tests/test_reap_logic.py). Scheduler-Image auf rq==2.10.0 angehoben (identisch zu den Workern).

### Files
- services/api/reap_stale_jobs.py
- services/api/reap_logic.py
- services/scheduler/crontab
- services/scheduler/Dockerfile
- alembic/versions/0013_backtest_job_retry_count.py
- user_data/utils/database/models.py
- tests/test_reap_logic.py



## [1.30.17] - 01.07.2026

### Fixed
- Test-Suite collectet und läuft wieder vollständig durch (493 passed, 1 skipped)
  - pytest_plugins aus services/api/tests/conftest.py in eine neue Top-Level-conftest.py (Projekt-Root) verschoben - seit pytest 7 ist pytest_plugins in Unterverzeichnis-conftest ein harter Collection-Fehler (hier pytest 9)
  - sys.modules-Leak behoben: test_indexer_exclude.py und test_indexer_mount_guard.py registrierten chunker-/embedding-Stubs bereits beim Modul-Import und verdeckten damit den echten Chunk-Import in tests/test_chunker.py waehrend der Collection
  - Alle vier Indexer-Testmodule (exclude, mount_guard, content_hash, sentinel) auf autouse-Fixtures mit sys.modules-Teardown umgestellt, sodass Stubs nach jedem Test wieder entfernt werden

### Files
- conftest.py
- services/api/tests/conftest.py
- services/api/tests/test_indexer_exclude.py
- services/api/tests/test_indexer_mount_guard.py
- services/api/tests/test_indexer_content_hash.py
- services/api/tests/test_indexer_sentinel.py



## [1.30.16] - 01.07.2026

### Fixed
- Runs-Analyse: Parameter-Heatmaps blieben sporadisch leer ("Zwei verschiedene Parameter auswählen"), obwohl Results und variierte Parameter vorhanden waren
  - Ursache 1 (Timing-Race): Das initiale Heatmap-Rendern hing an einem festen setTimeout(500), die Dropdown-Befüllung aber am asynchronen Summary-Fetch. Kam die Summary-Antwort später als 500 ms zurück (große Runs, Kaltstart), traf der Timer die noch leeren Dropdowns und die Heatmap blieb dauerhaft leer. Das Rendern hängt jetzt am Summary-Callback statt am Timer.
  - Ursache 2 (transienter Verbindungsabbruch): Ein einzelnes 'Failed to fetch' auf den Summary-Fetch (z.B. uvicorn-Reload-Neustart oder Docker-Port-Proxy-Reset unter dem Request-Burst beim Seitenaufbau) ließ die Dropdowns leer. Der Summary-Fetch fällt jetzt bei transientem Fehler mehrfach nach (Retry) und meldet endgültiges Scheitern sichtbar in der Konsole.
  - Doku: README um einen Screenshot der Runs-Analyse-Seite ergänzt.

### Files
- services/frontend/templates/backtest/analyse.html
- README.md
- documentation/knowledge/assets/runs-analyse.png



## [1.30.15] - 01.07.2026

### Fixed
- Obsidian-Deeplinks der Strategie-Konzepte-Seite öffnen wieder korrekt (vorher „Vault not found")
  - Ursache: Der Link nutzte den Vault-Namen aus OBSIDIAN_VAULT_NAME, das ungesetzt war und auf den Default 'vault' zurückfiel — Obsidian kennt keinen Vault dieses Namens.
  - Umbau auf die vom Hersteller vorgesehene Methode obsidian://open?path=<absoluter Pfad>: Obsidian ermittelt den Vault selbst aus dem absoluten Pfad, ein separater Vault-Name ist nicht mehr nötig.
  - Der Host-Pfad wird aus OBSIDIAN_VAULT_HOST_PATH abgeleitet (Backslash zu Slash normalisiert) — einzige Konfigurationsquelle, keine doppelte Pflege mehr.
  - OBSIDIAN_VAULT_NAME aus .env.example entfernt; Kommentar auf absoluten Host-Pfad geschärft.

### Files
- services/api/routes/views_config.py
- services/frontend/templates/config/strategy_concepts.html
- .env.example



## [1.30.14] - 01.07.2026

### Added
- 3D-Heatmap-Tab in der Run-Analyse plus Heatmap-Verbesserungen
  - Neuer Tab "3D-Heatmap" auf der Run-Analyse-Seite: interaktiver 3D-Plot ueber drei Parameter-Achsen, serverseitig via VBT volume() als Plotly-Figur gerendert (neuer Endpoint /api/backtest/runs/{id}/analyse/volume, aspectmode cube, plotly.js per CDN)
  - Heatmap-Aggregation pro Zelle zwischen Max (Default) und Average umschaltbar ueber ein neues Dropdown neben dem zweiten Parameter; Endpoint /analyse/heatmap erhaelt agg-Parameter
  - Metrik-Button "Return %" zu "Total Return %" umbenannt und Y-Achsentitel der Heatmaps sichtbar gemacht
  - Fix: Heatmap-Slider zeigte bei aktivem dritten Parameter nichts an (Float-Key-Mismatch zwischen Backend-Dict und JS-Lookup, jetzt index-basierte Slices)
  - Fix: Max-Drawdown-Farbskala und Top-Results-Sortierung waren invertiert (max_drawdown_pct ist negativ gespeichert, naeher 0 = besser); jetzt normale Skala und absteigende Sortierung fuer alle Metriken

### Files
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/analyse.html



## [1.30.13] - 30.06.2026

### Added
- Toolbox-Verb run-favorites-reset zum Zurücksetzen der Favoriten einer ganzen Run-Menge; Sharpe-Band der Bestwerte auf 10 Prozent verengt
  - Neues Verb run-favorites-reset (Skill ds-strategie-session, toolbox.py): räumt die Favoriten einer Run-Menge ab - roter Doku-Stern (is_doc_favorite) und/oder gelber User-Stern (is_favorite). Ohne Flag werden beide Arten entfernt, mit --doc bzw. --user gezielt nur eine. Selektoren identisch zu run-bestwerte (--run | --strategy [--version] | --iteration | --testset-run). Liest die markierten Results aus und toggelt nur gesetzte Sterne zurück (idempotent).
  - Gemeinsamer Run-Auflöser _resolve_runs aus run-bestwerte extrahiert und von beiden Verben geteilt (DRY).
  - Sharpe-Band der vier Standard-Bestwerte von 20 auf 10 Prozent verengt (eigene Konstante _SHARPE_BAND_FRACTION); Win-Rate-Band bleibt bei 20 Prozent. Ziel: der Sharpe-Band-Sieger fällt seltener mit dem Maximalen-Total-Return-Bestwert zusammen, mehr distinkte Doku-Favoriten je Run.
  - Doku nachgezogen: multiparameter-lauf.md, SKILL.md, toolbox-werkzeuge.md.

### Files
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- .claude/skills/ds-strategie-session/SKILL.md
- documentation/knowledge/strategy-development/workflows/multiparameter-lauf.md
- documentation/project/toolbox-werkzeuge.md



## [1.30.12] - 30.06.2026

### Fixed
- Playground-Aufruf aus einem Result wählt Konzept, Iteration, Indicator-Config und Backtest-Config in den oberen Dropdowns wieder vor
  - Der Endpoint GET /api/chart-playground/result-config/{id} lieferte die Rückführungs-IDs bisher hart als None — die vier oberen Dropdowns blieben beim Laden via ?resultid leer.
  - Fix: Endpoint lädt über result.run_id den zugehörigen BacktestRun und füllt selected_configs (iteration_id, backtest_config_id, indicator_config_id) sowie concept_slug (aufgelöst über iteration.concept_id -> StrategyConcept.slug).
  - iteration_id stammt direkt vom Result (FK), Fallback Run; backtest_config_id/indicator_config_id sind lose Herkunfts-Referenzen am Run.
  - Fehlende Referenzen (gelöschte Config nach Cleanup, Ad-hoc-Run ohne gespeicherte Config) bleiben None — das jeweilige Dropdown bleibt wie bisher leer, ohne Fehler.
  - Das Frontend (applySetupConfig) hatte die Vorauswahl-Logik bereits; es bekam nur immer None.

### Files
- services/api/routes/api_chart_playground.py



## [1.30.11] - 30.06.2026

### Changed
- ds-strategie-session: Loop-Denken aus dem Skill entfernt, jede Maßnahme ist ein einzelnes Werkzeug
  - Vorgegebene Schrittfolge (anlegen -> Backtest -> auswerten -> ... -> markieren) aus SKILL.md (Rolle, Pfad-B-Intro, Zwei Naturen) und toolbox.py-Docstring entfernt
  - Werkzeuge werden einzeln aufgerufen, keine feste Arbeitsmethodik mehr vorgegeben
  - Neue Referenz documentation/project/toolbox-werkzeuge.md: vollstaendige Werkzeug-Liste mit je einem Satz pro Werkzeug

### Files
- .claude/skills/ds-strategie-session/SKILL.md
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- documentation/project/toolbox-werkzeuge.md



## [1.30.10] - 30.06.2026

### Changed
- Strategie-Bewertung: Kriterien 2 und 3 der vier Bestwerte auf einheitliche Band-Mechanik umgestellt
  - Krit 2 (Win-Rate-Band): Bandgrenze jetzt 20 Prozent vom Hoechstwert statt 20 Prozentpunkte
  - Krit 3 von 'Max Sharpe' (reines Maximum) auf das Sharpe-Band umgestellt - gleiche Mechanik wie Krit 2; ein hoher Sharpe bei wenigen Trades kapert den Bestwert nicht mehr
  - Gemeinsamer Helper _band_best_return fuer Krit 2 und 3 (DRY); threshold = max - abs(max) * 0.20, das abs() haelt das Band auch bei durchweg negativem Hoechstwert unterhalb des Maximums
  - Win-Rate-Band bleibt bewusst ohne Trade-Floor: niedrige Trade-Zahl ist ein Flag, kein Filter; Kontext liefert das Testset (mehrere Symbole)
  - Veraltetes Verb run-winrate-band-best (rechnete in Prozentpunkten) entfernt; die Band-Sieger zieht nur noch run-bestwerte
  - Doku angeglichen: multiparameter-lauf.md Schritt 5 und SKILL.md Auswertungs-Sektion

### Files
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- documentation/knowledge/strategy-development/workflows/multiparameter-lauf.md
- .claude/skills/ds-strategie-session/SKILL.md



## [1.30.9] - 29.06.2026

### Added
- Backtest-Runs-Tabelle: Spalte TR (Testset-Run-ID) links vor der ID-Spalte
  - Neue Spalte TR zeigt die testset_run_id - die gemeinsame Klammer aller Runs eines Testset-Laufs
  - TR und ID zentriert; Einzel-Runs ohne Testset zeigen -
  - API lieferte testset_run_id bereits (BacktestRunOut), nur Frontend-Template angepasst
  - Sortierung auf ID nachgezogen (Spaltenindex 2 auf 3)

### Files
- services/frontend/templates/backtest/runs.html



## [1.30.8] - 29.06.2026

### Added
- Toolbox-Verb run-bestwerte: die vier kanonischen Bestwerte je Multiparameter-Lauf ziehen und idempotent als Doku-Favorit markieren
  - Neues ds-strategie-session-Verb run-bestwerte (--run | --iteration | --strategy [--version] | --testset-run): kapselt die vier festen Bestwerte (max Total Return, bestes Return im oberen Win-Rate-Band, max Sharpe, max Profitfaktor mit mindestens 30 Trades) ausführbar in einem Aufruf und setzt je Sieger den roten Doku-Favoriten; idempotent - bereits markierte Results werden nicht erneut getoggelt
  - Fix Determinismus: Sortierung in /api/backtest/results/dt ist bei Wertgleichstand jetzt reproduzierbar - sekundär nach geringstem Drawdown, dann Result-ID. Zuvor kürte die Bestwert-Auswahl bei wertgleichen Parameter-Kombinationen (Raster-Dubletten) mal das eine, mal das andere Result; latent betraf das auch run-best/run-winrate-band-best und die Frontend-Results-Tabelle
  - run-list gruppiert jetzt nach Testset-Lauf (testset_run_id = Auftrags-ID) und zeigt diese ID an, run-read ebenfalls - macht den schon vorhandenen --testset-run-Selektor sichtbar nutzbar
  - SKILL.md und Workflow multiparameter-lauf.md (Auswertungs-Sektion) auf run-bestwerte als Normalweg umgestellt; die Einzelverben bleiben als Ad-hoc-Unterbau erhalten

### Files
- services/api/routes/api_backtest.py
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- .claude/skills/ds-strategie-session/SKILL.md



## [1.30.7] - 29.06.2026

### Added
- Runs nach Strategie+Version/Testset filterbar und sprechende Run-Labels
  - API GET /api/backtest/runs nimmt jetzt optionale Filter iteration_id, strategy+version und testset_run_id; (Slug, Version) wird serverseitig zu den passenden iteration_ids aufgeloest (leere Liste statt Fehler, wenn nicht vorhanden)
  - BacktestRunOut gibt iteration_id aus (Anker fuer 'Runs zu Strategie+Version')
  - Toolbox: neues Verb run-list --strategy <slug> --version <n> (auch --iteration / --testset-run), Ergebnis nach Testset gruppiert
  - Toolbox: run:<id> zeigt sprechendes Label 'VWMA v1 - SYMBOL TF' plus Testset-Zugehoerigkeit statt nackter ID
  - Skill-Doku praezisiert: ein Testset-Lauf erzeugt einen Leaderboard-Eintrag nur bei leaderboard_enabled=True (Opt-in); leeres Leaderboard ist kein Beleg gegen einen Testset-Lauf

### Files
- services/api/routes/api_backtest.py
- services/api/schemas/__init__.py
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- .claude/skills/ds-strategie-session/SKILL.md



## [1.30.6] - 28.06.2026

### Changed
- Projekt-Rename von bt_pro_app_v1 auf bt_pro_app_v1 (Ordner, Docker-Projektname, Basis-Image)
  - Lokaler Ordner umbenannt: vectorbtpro/bt_pro_app_v1 -> vectorbtpro/bt_pro_app_v1
  - Docker-Compose-Projektname (name:) und Basis-Image bt_pro_app_v1-vbt -> bt_pro_app_v1-vbt in compose-local/-pve1, Dockerfile FROM, build.sh, install.sh/.bat, README
  - Doku durchgaengig auf bt_pro_app_v1 umgestellt (project-structure.md, AGENT_ENTRY.md, _inject.md, projekt.md) sowie Skill ds-strategie-session (SKILL.md + toolbox.py)
  - Container-Namen (frontend_vbt_v1, db_vbt_v1, redis_vbt_v1) und GitHub-Remote (smartsys/bt_pro_app_v1) bewusst unveraendert; DB nutzt Bind-Mount (data/postgres), kein Volume verwaist
  - Offen (manueller Docker-Schritt): vorhandenes Basis-Image neu taggen via 'docker tag bt_pro_app_v1-vbt:latest bt_pro_app_v1-vbt:latest' oder neu bauen, dann Stack neu hochfahren

### Files
- docker-compose-local.yml
- docker-compose-pve1.yml
- services/api/Dockerfile
- services/vbt/build.sh
- install.sh
- install.bat
- README.md
- documentation/knowledge/project-structure.md
- documentation/knowledge/strategy-development/AGENT_ENTRY.md
- documentation/knowledge/strategy-development/_inject.md
- documentation/project/projekt.md
- .claude/skills/ds-strategie-session/SKILL.md
- .claude/skills/ds-strategie-session/scripts/toolbox.py



## [1.30.5] - 28.06.2026

### Changed
- Chart-Playground- und Konzept-UI angepasst, In-Position-Anzeige korrigiert und Auslieferungs-Baseline aktualisiert
  - Chart-Playground: R-Button (Indikatoren neu berechnen) entfernt, Schnellbacktest-Button gruen gefaerbt; die Berechnen-Funktion laeuft weiter automatisch (Auto-Apply + beim Chart laden)
  - Chart-Playground: Platzhalter der Tabs Stats und Trades/Orders/Positions auf 'In Kuerze.' geaendert
  - Result-Chart Trade-Analyse: 'In Position' wird jetzt als Vereinigung der Trade-Intervalle berechnet statt als stumpfe Summe; bei ueberlappenden Positionen ergaben sich vorher Werte ueber 100 Prozent (z.B. 300 Prozent) und der Balken lief ueber die volle Breite hinaus (gegen Result 120 verifiziert: 300,0 -> 100,0 Prozent)
  - Strategie-Konzepte: Titel des aufgeklappten Iterationen-Panels zeigt 'Iterationen (N)' statt des Konzeptnamens
  - Auslieferungs-Baseline (0009_baseline_data.sql): indicator_configs id 2 auf den angepassten Stand gebracht (Name '136 Kombi.', period arange 3-20, multiplier arange 2-10)

### Files
- services/frontend/templates/chart_playground/index.html
- services/frontend/templates/backtest/result_chart.html
- services/frontend/templates/config/strategy_concepts.html
- alembic/versions/_sql/0009_baseline_data.sql



## [1.30.0] - 27.06.2026

### Added
- Onboarding-Installation: Ein-Aufruf-Setup, Auto-Migration und /install-Seite
  - install.bat (Windows/Docker-Desktop-nativ) und install.sh (Linux/macOS): Frisch-Installation mit Sicherheitsabfrage - baut das VBT-Pro-Basis-Image, löscht den alten DB-/App-Zustand (postgres, postgres_test, redis, pgadmin) und startet den Stack
  - App-Entrypoint (services/api/entrypoint.sh) wartet auf die Datenbank und führt alembic upgrade head automatisch aus - kein manueller Migrations-Schritt mehr; fängt das TimescaleDB-Erststart-Race per Retry ab statt per Crash-Restart
  - App-Healthcheck ergänzt; worker/worker-init/scheduler warten jetzt auf die migrierte App (depends_on app: service_healthy)
  - Onboarding-Seite /install: Installations-Check (Counts der Grundausstattung) plus Button, der die OHLC-Download-Jobs für die Test-Set-Symbole anlegt (idempotent, bereits vorhandene Symbole werden übersprungen)
  - Grundausstattung um eine Demo-Strategie erweitert: Konzept teststrategie + Iteration + zwei Indicator-Configs, IDs auf 1/1/1+2 normalisiert
  - commit.py schreibt APP_VERSION jetzt auch in die getrackte .env.example
  - .env.example neu strukturiert: Pflicht (VBT_SSH_KEY) und Optional getrennt, lokale Defaults vorgegeben, leerer Dummy-Vault als OBSIDIAN-Default
  - backtest_seed.sql samt DB-Init-Mount entfernt (redundant, wurde vom Image ignoriert); export_baseline.py entfernt - die Baseline ist ein eingefrorener Snapshot
  - README: neuer Installationsteil

### Files
- install.sh
- install.bat
- services/api/entrypoint.sh
- services/api/Dockerfile
- docker-compose-local.yml
- services/api/routes/views_install.py
- services/api/routes/api_config.py
- services/api/app.py
- services/frontend/templates/install/dashboard.html
- alembic/versions/_sql/0009_baseline_data.sql
- documentation/git/commit.py
- .env.example
- README.md



## [1.29.1] - 26.06.2026

### Changed
- Indikator-Konfiguration: Visueller Editor ist jetzt die Default-Ansicht beim Laden
  - Beim Laden von /config/indicator/<id> startet nun der visuelle Editor statt der JSON-Ansicht; Aufbau laeuft ueber den regulaeren setEditMode-Pfad inkl. Fallback auf JSON bei ungueltigem JSON
  - Titel generieren: ohne gesetzten Take Profit und Stop Loss entfaellt der Stop-Teil samt Schraegstrich (z.B. '... 10 Kombi.' statt '... 10 Kombi. /')

### Files
- services/frontend/templates/config/indicator_config_edit.html



## [1.29.0] - 26.06.2026

### Added
- Datei-Export/-Import für Strategie-Konzepte, Iterationen und Indicator-Configs
  - Drei unabhängige Export/Import-Paare, je ein Button in der zugehörigen Maske. Export schreibt eigenständige JSON-Dateien nach documentation/backup/strategies/, Import liest eine Datei per OS-Datei-Dialog (Herkunft beliebig). IDs werden beim Import immer neu vergeben.
  - Konzept: Export pro Zeile -> <slug>/concept.json; Import oben legt Konzept an oder aktualisiert es per slug.
  - Iteration: Export pro Zeile -> <slug>/<version>/iteration.json; Import je Konzept lädt die Datei als neue Version (frische Versionsnummer, parent_iteration_id=null).
  - Indicator-Config: Export pro Zeile -> <slug>/<version>/indicator-configs/<name>.json (nach Verknüpfung); Import oben legt eine neue Config an.
  - Neuer Kern services/api/utils/strategy_io.py; Endpunkte in api_strategy.py (Konzept/Iteration) und api_config.py (Indicator-Config); Buttons in strategy_concepts.html und indicator_configs.html.
  - Bind-Mount ./documentation/backup im App-Container ergänzt, damit Export-Dateien auf den Host durchschlagen.
  - python-multipart zu services/api/requirements.txt ergänzt (von den neuen Upload-Endpunkten benötigt; Image neu gebaut).
  - 8 Round-Trip-Unit-Tests (tests/test_strategy_io.py); End-to-End in der laufenden App für alle drei Typen verifiziert.

### Files
- services/api/utils/strategy_io.py
- services/api/routes/api_strategy.py
- services/api/routes/api_config.py
- services/frontend/templates/config/strategy_concepts.html
- services/frontend/templates/config/indicator_configs.html
- docker-compose-local.yml
- services/api/requirements.txt
- tests/test_strategy_io.py



## [1.28.9] - 25.06.2026

### Changed
- Job 'Alle Runs/Results loeschen' auf TRUNCATE-Pfad umgestellt (~30x schneller, gibt Plattenplatz frei)
  - _delete_all_non_favorites sichert die wenigen Favoriten-Zeilen (Results + zugehoerige Runs + Detail-Daten) in Temp-Tabellen, leert alle betroffenen Tabellen per TRUNCATE und schreibt die Favoriten zurueck -- statt 1,47 Mio. Zeilen einzeln ueber TimescaleDB-Hypertables und 18 Indexe zu loeschen
  - Gemessen an realem Stand (1,45 Mio. Results, 31 Favoriten): Job-Laufzeit ~39s statt ~20min; zusaetzlich ~5,4 GB Plattenplatz zurueckgegeben, den der alte zeilenweise Pfad mangels VACUUM nie freigab
  - Semantik unveraendert: beide Stern-Markierungen (is_favorite/is_doc_favorite) bleiben geschuetzt, Runs mit Favoriten bleiben erhalten, verwaiste Runs verschwinden; backtest_jobs behaelt ungebundene (result_id IS NULL) und Favoriten-Jobs
  - Verifiziert: nach dem Lauf 31 Results / 18 Runs / 0 verwaiste Param- oder Run-Zeilen
  - Einzel- und Bulk-Loeschpfade (DELETE /runs/{id}, /results/{id}) unveraendert -- nutzen weiter den zeilenweisen Loeschpfad

### Files
- services/api/worker_tasks.py



## [1.28.8] - 25.06.2026

### Changed
- "Alle löschen" (Results/Runs) committet jetzt batchweise statt erst am Ende
  - Der Hintergrund-Lösch-Job löscht Results inklusive Detaildaten nun in Batches von 5000 und committet nach jedem Batch. Bisher wurde alles in einer einzigen Transaktion gelöscht und erst am Ende committet.
  - Folge: Wird der Job mitten im Lauf abgebrochen, bleibt der bis dahin gelöschte Stand erhalten, statt komplett zurückgerollt zu werden. Die angezeigte Result-Anzahl sinkt dadurch schrittweise und springt nach einem Abbruch nicht mehr auf den Ausgangswert zurück.
  - Verwaiste Runs (ohne Results) werden zum Schluss geräumt; bei einem Abbruch bleiben sie liegen und werden beim nächsten vollen Lauf idempotent mitentfernt.
  - Fortschrittsanzeige meldet jetzt echte, committete Löschungen (x/y Results gelöscht).
  - Aufräumung: nicht mehr genutzten progress_cb-Parameter aus _delete_result_details samt verwaistem Callable-Import entfernt; irreführenden Abbruch-Kommentar korrigiert.

### Files
- services/api/worker_tasks.py
- services/api/routes/api_backtest.py



## [1.28.7] - 25.06.2026

### Fixed
- Backtest-Start: Indicator-Config lud nicht mehr ("Fehler beim Laden")
  - Der TestSet-Detail-Renderer _showTsIndDetails rief noch die beim Kombi-Zaehler-Umbau entfernte Funktion calcCombinations auf (ReferenceError).
  - Da _showTsIndDetails ueber _fillTsIndicators innerhalb von loadIndConfigs laeuft, riss der Fehler auch das Einzel-Lauf-Indicator-Dropdown mit ('-- Fehler beim Laden --').
  - Umgestellt auf updateIndCombos (Server-Endpunkt count-combos) wie im Einzel-Lauf-Pfad - einzige Zaehl-Wahrheit, kein clientseitiger Zaehler mehr.

### Files
- services/frontend/templates/backtest/start.html



## [1.28.6] - 25.06.2026

### Added
- Globaler Lösch-Job-Toast: seitenübergreifende Fortschrittsanzeige mit Abbrechen-Button für Results-/Runs-Massenlöschung
  - Neuer globaler Dauertoast in base.html zeigt auf JEDER Maske den Fortschritt eines laufenden Results- oder Runs-Lösch-Jobs (Spinner, Fortschrittsbalken, Abbrechen-Button); pollt /api/backtest/delete-jobs/active (idle 4s, aktiv 1,5s)
  - DELETE /runs läuft jetzt asynchron als RQ-Hintergrundjob (delete_all_runs_job) analog zu DELETE /results - vorher synchron und ohne jede Statusanzeige
  - Neuer Endpunkt GET /api/backtest/delete-jobs/active liefert alle aktiven Lösch-Jobs (Results + Runs) gebündelt; POST /api/backtest/delete-jobs/{job_id}/cancel bricht wartende (aus Queue) oder laufende (SIGINT) Lösch-Jobs ab
  - _stop_run_jobs greift nur noch echte run_backtest_job-Berechnungen ab (func_name-Filter statt q.empty): ein Runs-Lösch beendet damit keinen parallel laufenden Results-Lösch-Job mehr und sich auch nicht selbst
  - Gemeinsame Löschlogik in worker_tasks._delete_all_non_favorites extrahiert (von Results- und Runs-Job geteilt)
  - Aufgeräumt: die vier alten delete-status/delete-active-Endpunkte und die zwei seiten-lokalen Progressbars/Polling-IIFEs in results.html und runs.html entfernt; beim Job-Ende lädt das vbt:delete-jobs-idle-Event die jeweilige Tabelle neu

### Files
- services/api/routes/api_backtest.py
- services/api/worker_tasks.py
- services/frontend/templates/base.html
- services/frontend/templates/backtest/results.html
- services/frontend/templates/backtest/runs.html



## [1.28.5] - 25.06.2026

### Fixed
- Chart-Playground: Schnellbacktest bringt Candles und Indikatoren bei geändertem Basis-Timeframe erst auf Stand
  - Wurde der Basis-Timeframe (oder Symbol/Exchange/Zeitraum) nach dem Laden geändert und dann der Schnellbacktest gestartet, rechnete der Lauf bereits auf dem neuen tf, während Candles und Indikatoren noch auf dem alten tf standen. Die neue Equity/Trades wurde in denselben Chart eingefügt, lightweight-charts vereinigte die Zeitachsen, und die alten Candles lagen nur noch in größerem Takt auf der feineren Achse - sichtbar als Lücken zwischen den Kerzen
  - runBacktestLite gleicht zu Beginn den eingestellten OHLC-Stand (Exchange/Symbol/tf/Start/End) gegen den zuletzt geladenen ab (cpLoadedOhlcKey/cpOhlcKey); bei Abweichung wird erst loadChart ausgeführt, dann gerechnet
  - Bei unverändertem Stand kein Neuladen - ein reiner Re-Run behält den aktuellen Zoom. 'Chart laden' war bereits korrekt und blieb unverändert

### Files
- services/frontend/templates/chart_playground/index.html



## [1.28.4] - 25.06.2026

### Fixed
- Chart-Playground: Indikator-Timeframe feiner als Basis-Timeframe wird beim Laden korrigiert, Fehler-Anzeige vereinheitlicht
  - Ein Indikator-Timeframe, der feiner als der Basis-Timeframe ist (immer ungültig, da Downsampling der OHLC-Kerzen unmöglich), wird beim Laden eines Setups oder einer Indikator-Konfig auf '(gleich)' normalisiert. Vorher zeigte das Dropdown fälschlich '(gleich)', der Runner rechnete aber weiter den gespeicherten feineren tf - Anzeige und Rechen-tf stimmen jetzt überein
  - Neuer Helfer normalizeLoadedTf deckt beide Lade-Pfade ab; eine sichtbare Hinweis-Meldung nennt pro Indikator Name, Quell-tf und Basis-tf
  - Chart-Lade-Fehler erscheint jetzt zusätzlich als prominentes Banner (wie der Schnellbacktest); beide Banner tragen ein Quell-Präfix 'Chart laden:' bzw. 'Schnellbacktest:'
  - Toast-Meldungen haben ein Schließen-Kreuz (vertikal zentriert) zum manuellen Wegklicken und eine optionale Anzeigedauer (Umstell-Hinweis 12 s statt 6 s)

### Files
- services/frontend/templates/chart_playground/index.html
- services/api/routes/api_chart_playground.py



## [1.28.3] - 25.06.2026

### Added
- Chart-Playground: Per-Indikator-Anzeige-Versatz (Versatz in Kerzen) in den erweiterten Optionen
  - Neues Feld Versatz (Kerzen) in der Visualisierungs-Box je Indikator: verschiebt die Darstellung um N angezeigte Kerzen (positiv = nach rechts/Zukunft, negativ = links), ganze Zahlen, Default 0
  - Reine Anzeige-Verschiebung: nur die gezeichneten Zeitstempel werden verschoben, Berechnung und Output-Cache bleiben unberuehrt (kein Neu-Rechnen, 0 Netzwerk-Requests)
  - Bezugsgroesse ist die angezeigte Kerze (Anzeige-TF): der Versatz wird nach dem Resample angewandt, daher ist +1 immer genau eine sichtbare Kerze - auch wenn der Anzeige-TF groeber als die Berechnungs-TF des Indikators ist
  - Greift einheitlich fuer overlay, subplot-Linie und background (Regime-Baender)
  - Persistiert als reine Anzeige-Eigenschaft mit dem Setup (display_offset, neben line_width/line_style)
  - Verifiziert per Pixel-Diff: Anzeige 1d + Supertrend-Hintergrund +1 verschiebt um genau einen Tages-Bar; Anzeige 5m +20 um 20 Bars

### Files
- services/frontend/templates/chart_playground/index.html



## [1.28.2] - 25.06.2026

### Changed
- Chart-Playground: Hintergrund-Indikatoren werden als Custom Series Primitive gezeichnet statt als eine Serie pro Trend-Lauf
  - Neue Zeichen-Ebene RegimeBandsPrimitive/RegimeBandsPaneView/RegimeBandsRenderer (Vorbild: lightweight-charts Plugin session-highlighting) plus Helper fullBarWidth zeichnet alle Hintergrund-Bänder in einem Canvas-Durchgang
  - Behebt die ~18 s Blockade beim Anzeige-TF-Wechsel auf feine Raster (vorher entstand pro Direction-Lauf eine eigene AreaSeries, bei 5m ~971 Serien; jedes setData löste eine Achsen-Neuberechnung aus). 5m-Wechsel jetzt ~40 ms
  - Behebt fehlende Kerzen an den Farb-Übergängen: das Primitive fügt keine fremden Zeitpunkte mehr in die gemeinsame Zeitachse ein (der halbe-Kerze-Versatz aus 1.28.1 entfällt damit)
  - Behebt Trennlinien im Hintergrund: fullBarWidth rundet linke/rechte Kante separat auf ganze Pixel, dadurch lückenlose Flächen von Kerzen-Kante zu Kerzen-Kante statt Mitte-zu-Mitte
  - Abräumen umgestellt auf detachPrimitive (neues State-Dict backgroundPrimitivesByClientId, auch in pruneOrphanSeries berücksichtigt)

### Files
- services/frontend/templates/chart_playground/index.html



## [1.28.1] - 25.06.2026

### Fixed
- Chart-Playground: Beim Wechsel des Anzeige-Timeframes (visualTf) verschwanden die Candles mit lightweight-charts-Fehler "Value is null"
  - Ursache: applyVisualTf rief candleSeries.setData mit dem neuen TF-Raster auf, waehrend die Equity-Serie noch das alte Raster hielt. lightweight-charts vereinigt beim Reraster die Zeitpunkte beider Serien; an Achsen-Punkten ohne passende Candle-Bar entsteht ein Whitespace-Candle, woraufhin der Candlestick-Renderer im naechsten Frame 'Value is null' wirft (Candles verschwinden).
  - Trigger war nachweislich die Equity-Serie und der Fehler trat nur beim ersten Wechsel zu einem noch ungesehenen TF-Raster auf (transienter Zwischenzustand, finale setData-Daten waren stets sauber).
  - Fix: in applyVisualTf die abhaengigen Serien VOR dem Candle-Reraster leeren (Indikatoren via removeIndFromChart, Equity via setData([])) und danach neu zeichnen - die gemeinsame Zeitachse bleibt durchgehend konsistent.
  - Verifikation: frischer Reload mit 13 TF-Wechseln quer durch alle Raster (inkl. der zuvor fehlerhaften 1d->4h und 4h->6h) ergab 0 Fehler und saubere Console; Candles, Background-Indikator, Equity und Trade-Marker werden korrekt gerendert.

### Files
- services/frontend/templates/chart_playground/index.html



## [1.28.0] - 25.06.2026

### Added
- OHLC-Download mit Einzel-Symbol-Jobs, Live-Intervall-Fortschritt und Aktualisieren-Button in der Backtest-Config
  - Download und Datei-Aktualisierung zerlegen eine Symbol-Liste jetzt in einen eigenen Job pro Symbol+Timeframe (Status und Fortschritt je Symbol abfragbar).
  - Neuer Endpunkt POST /api/config/data/update-symbol legt einen Update-Job fuer genau ein Symbol an (Start = letzter Bar minus 1 Tag, Ende = jetzt UTC).
  - Live-Fortschritt in Intervallen (Bars): der Worker schaetzt intervals_total vorab und zaehlt intervals_done pro Binance-Chunk ueber einen Hook in vbts ProgressBar hoch; die Anzeige aktualisiert sich, ohne die Download-Logik zu veraendern.
  - Backtest-Config-Seite: Spalte mit Aktualisieren-Button je Timeframe in der Verfuegbar-Tabelle; Spinner Aktualisiere... mit mitlaufendem Restzaehler, laedt die Bars nach Abschluss neu.
  - OHLC-Daten-Seite: Job-Tabelle zeigt pro laufendem Job done/total Intervalle, Prozent und noch offene Intervalle.
  - Binance-Schonung env-konfigurierbar: OHLC_FETCH_DELAY (Default 1.5 s Pause zwischen Requests) und OHLC_FETCH_LIMIT (Default 1000 Bars pro Request), in allen drei Compose-Dateien und .env.example.
  - Migration 0012 ergaenzt intervals_total/intervals_done an ohlc_download_jobs (beide nullable).

### Files
- alembic/versions/0012_ohlc_job_progress.py
- user_data/utils/database/models.py
- services/api/worker_tasks.py
- services/api/routes/api_config.py
- services/frontend/templates/config/data_files.html
- services/frontend/templates/config/backtest_config_edit.html
- docker-compose-local.yml
- docker-compose.yml
- docker-compose-pve1.yml
- .env.example
- tests/test_ohlc_job_progress.py



## [1.27.0] - 25.06.2026

### Changed
- Per-Indikator-Timeframe (tf) im echten Spec-Runner scharf geschaltet — tf wirkt jetzt in Lauf UND Chart-Preview über denselben geteilten Helper (Preview == Lauf)
  - Neuer geteilter Helper user_data/strategies/generic/tf_resample.py (resampled_ohlc/realign_to_index/validate_tf/normalize_tf) als Single Source fuer Runner und Preview
  - build_indicators: Ein Indikator mit groeberem tf rechnet nativ auf ohlc_data.resample(tf); jeder Output wird per realign_closing look-ahead-sicher auf den Basis-Index zurueckgeholt (Portfolio + Rules laufen am Basis-Raster)
  - Multi-Combo-DataFrames (param_product) behalten beim Realign alle Param-Spalten; Outputs am tf-Index werden in einen _RealignedIndicator-Wrapper gekapselt, transparent fuer Rules-Engine, Chaining, DB-Persistenz und Report (output_names dafuer instanz-level gelesen)
  - Cross-TF-Chaining: Output eines Indikators wird fuer einen feiner/groeber rechnenden Folge-Indikator via realign_closing (last-in-bucket) auf dessen Rechen-tf gebracht
  - Server-Guard: ein feinerer tf als der Basis-Timeframe (Downsampling) wird in Preview und Runner mit klarer Meldung abgewiesen statt still falsch zu rechnen; tf==Basis ist ein No-Op (ueber durchgereichten base_tf-String erkannt, unabhaengig von wrapper.freq)
  - Chart-Playground-Preview (compute_indicators) auf den geteilten Helper umgestellt; Verhalten bit-genau unveraendert verifiziert (tf=4h==Basis identisch zu tf=none, tf=1d gestuft)
  - BREAKING fuer tf-Specs: Spec-Runner-VERSION 1.2.1 -> 2.0.0. Gespeicherte Iterationen/Setups mit einem nicht-Basis-tf liefern beim naechsten Lauf andere (jetzt korrekte) Ergebnisse — vorher wurde tf im Runner still verworfen. Specs ohne tf bzw. tf==Basis bleiben bit-identisch
  - Verifikation: 32 neue Unit-/Integrationstests (tf_resample + build_indicators_tf) plus Engine-Regression gruen; bit-genauer Beleg Preview == Lauf (RSI tf=1d, FETUSDT 4h: max|diff|=0.0 ueber 2108 Punkte)

### Files
- user_data/strategies/generic/tf_resample.py
- user_data/strategies/generic/indicator_factory.py
- user_data/strategies/generic/spec_runner.py
- user_data/strategies/generic/rules_engine.py
- services/api/routes/api_chart_playground.py
- tests/test_tf_resample.py
- tests/test_build_indicators_tf.py
- documentation/knowledge/indicators.md
- documentation/todo/per-indikator-timeframe-resample-uebergabe.md



## [1.26.13] - 24.06.2026

### Changed
- Chart-Playground: Per-Indikator-Timeframe (tf) im Preview nativ über vbt.Data.resample aufgelöst
  - compute_indicators loest ein gesetztes tf jetzt nativ ueber vbt.Data.resample(tf) auf (kennt die OHLCV-Aggregationsregeln selbst) statt ueber ein handgepflegtes resample_rules-Dict mit pandas series.resample().agg()
  - Das vbt.Data wird lazy aus dem bereits geladenen, start/end-gefilterten df gebaut (Feature-Config via EXCHANGE_DATA_CLASS aus dem Loader wiederverwendet) und pro Ziel-tf gecached; Skip-Guard bei tf == Basis-TF bleibt
  - Output-Realign war bereits nativ (realign_closing) und bleibt unveraendert; chained Indikator-Referenzen ueber TF bleiben vorerst last-in-bucket
  - Damit nutzt der Preview-Pfad denselben nativen Resample-Ansatz wie der kuenftige Runner; live verifiziert (Setup 75, tf none/4h/1d), 19 chart-playground-nahe Tests gruen

### Files
- services/api/routes/api_chart_playground.py



## [1.26.12] - 24.06.2026

### Added
- dwsTrendlineTouch (TAP-Methode): Zwei neue Parameter min_bars_between und dip_min_atr zur Trennung echter Trendlinien von Mini-Swings
  - min_bars_between: Mindest-Bar-Abstand zwischen zwei aufeinanderfolgenden Touch-Pivots (auch Anker 1 und 2); zu eng beieinanderliegende Pivots zählen nicht. 0 = aus.
  - dip_min_atr: Mindest-Tiefe der Kuhle (Rücksetzer) zwischen zwei Touches in ATR-Einheiten, gemessen am Low/High des bestätigten Gegen-Pivots relativ zur Linie. 0 = aus.
  - Rückwärtskompatibel über Factory-Defaults in with_apply_func (min_bars_between=0, dip_min_atr=0.0) - run() bleibt für bestehende Setups/Iterationen ohne diese Werte lauffähig (sonst: missing required positional arguments).
  - Touch-/Kuhle-Prüfung in Helper _kuhle_ok ausgelagert; verwaisten Code (in_band/left_band) im Linien-Detektor entfernt.
  - Tests ergänzt: test_min_bars_between_filters_close_pivots, test_dip_min_atr_filters_shallow_kuhle (10 Tests grün).

### Files
- user_data/utils/indicators/custom.py
- tests/test_dws_trendline_touch.py



## [1.26.11] - 24.06.2026

### Fixed
- Kombinationszählung vereinheitlicht — eine Wahrheit statt sechs handgestrickter Zähler; Listen-Achsen und gekoppeltes TSL-Paar zählen jetzt korrekt
  - Neue Funktion indicator_factory.describe_combos(indicators_json) -> {total, details} als einzige Zaehl-Wahrheit (Indikator-Kombis x Stop-Kombis); count_total_combos als duenner Wrapper. Listen [a,b,c] zaehlen ueber _expand_range mit, das gekoppelte TSL-Paar (tsl_th+tsl_stop) als EINE Achse (count_stop_combos).
  - Gemeinsamer Achsen-Sammler _collect_varying_axes herausgezogen; split_indicators_json_chunks nutzt ihn (bit-identisch, kein Duplikat).
  - Neuer Endpunkt POST /api/config/indicator/count-combos (Body {config_json}) liefert {data:{total,details}} bzw. 400 bei TSL-Paar-Laengen-Mismatch.
  - indicator_labels._count_combinations entfernt -> delegiert an count_total_combos; repository._count_combinations (Vorab-Schaetzung beim Run-Anlegen) delegiert ebenfalls (lokaler Import, damit das DB-Modul ohne vectorbtpro importierbar bleibt).
  - Alle vier Frontend-Buttons (Playground, Config-Edit 'Kombinationen berechnen' + 'Titel generieren', Start-Run) rufen den Endpunkt statt eigener JS-Mathematik; Achsen-Tooltip bleibt erhalten.
  - Vorher: sechs separate Zaehler zaehlten nur arange-Achsen, ignorierten Listen und behandelten Stops uneinheitlich -> Anzeige wich von der Laufzeit-Wahrheit ab.
  - Test tests/test_count_total_combos.py (8 Faelle: Ranges, Listen, deaktiviert, Stops, TSL-Kopplung, Mismatch, Details). UI real verifiziert: /config/indicator/2024 zeigt 48.600, mit Listen-Achse korrekt 64.800.

### Files
- user_data/strategies/generic/indicator_factory.py
- services/api/utils/indicator_labels.py
- services/api/routes/api_config.py
- user_data/utils/database/repository.py
- services/frontend/templates/chart_playground/index.html
- services/frontend/templates/config/indicator_config_edit.html
- services/frontend/templates/backtest/start.html
- tests/test_count_total_combos.py



## [1.26.10] - 24.06.2026

### Changed
- Strategie-spezifische VWMA-Bezüge aus dem öffentlichen Code entfernt (Public-Repo-Hygiene)
  - Ungenutzte VWMA-spezifische Heatmap-Funktionen aus user_data/strategies/__init__.py entfernt (generate_vwma_heatmap, generate_multidimensional_heatmap, generate_all_combinations_heatmap)
  - Hartcodierte dwsvwma-Parameter-Vorselektion der zweiten Heatmap in analyse.html durch eine generische Vorselektion ersetzt
  - Beispiel-Kommentare und Docstrings in ~14 Produktivcode-Dateien generalisiert (neutrale Indikatoren bzw. Platzhalter teststrategie/Iteration 1 statt der konkreten VWMA-Strategie); veraltete Vault-Pfad-Beispiele dabei korrigiert
  - 22 Test-Dateien von eigenständigen VWMA-Bezügen befreit; der Custom-Indikator dwsVWMA/dwsVWMABand und die davon abgeleiteten Param-Keys bleiben unverändert und testbar
  - Skill ds-strategie-session (SKILL.md, toolbox.py): VWMA-Beispiele auf generische teststrategie-Beispiele umgestellt
  - Bewusst belassen: die Custom-Indikatoren in custom.py, der generische TA-Typ vwma in der Overlay-Whitelist, sowie nicht-getrackte Privatdokumente (Tickets, HANDOFF, strategy-development-Doku)

### Files
- user_data/strategies/__init__.py
- services/frontend/templates/backtest/analyse.html
- services/frontend/templates/chart_playground/index.html
- services/frontend/templates/backtest/result_chart.html
- services/api/recompute.py
- services/api/worker_tasks.py
- services/api/routes/api_chart_playground.py
- services/api/routes/views_backtest.py
- services/api/utils/obsidian_paths.py
- services/vbt/knowledge/indexer.py
- user_data/utils/database/models.py
- user_data/utils/database/repository.py
- user_data/utils/database/repository_strategies.py
- user_data/utils/database/repository_testsets.py
- user_data/strategies/generic/spec_runner.py
- user_data/strategies/generic/rules_engine.py
- user_data/strategies/generic/indicator_factory.py
- .claude/skills/ds-strategie-session/SKILL.md
- .claude/skills/ds-strategie-session/scripts/toolbox.py



## [1.26.9] - 24.06.2026

### Changed
- Chart-Playground: Schnellbacktest-Button zeigt während der Berechnung einen drehenden Spinner mit Text 'Berechne...' statt nur 'Analysiert...'

### Files
- services/frontend/templates/chart_playground/index.html



## [1.26.8] - 24.06.2026

### Removed
- Toten Auto-Iterations-Registrierungs-Code entfernt, Lite-Backtest-Tests funktionsbenannt
  - spec_iteration_registry.py geloescht — nach Wegfall des vollen Playground-Backtests rief kein Produktiv-Pfad register_or_get_iteration/compute_spec_hash mehr auf
  - Verwaiste get_iteration_by_spec_hash() aus repository_strategies.py entfernt (nur die Registry nutzte sie); next_iteration_version bleibt (weiterhin von api_strategy genutzt)
  - Testdatei test_ticket23_lite_backtest.py in test_run_backtest_lite.py umbenannt — Tests nach Funktion benennen, nicht nach Ticket-Nummer
  - Obsoleten Equivalenz-Test (Lite vs. entfernter voller Lauf) und verwaisten Registry-Patch entfernt; Ticket-Bezuege aus den Test-Docstrings getilgt
  - Docstring von run_backtest_lite aktualisiert (Registry-Erwaehnung entfernt)

### Files
- user_data/strategies/generic/spec_iteration_registry.py
- tests/test_spec_iteration_registry.py
- tests/test_run_backtest_lite.py
- user_data/utils/database/repository_strategies.py
- services/api/routes/api_chart_playground.py



## [1.26.7] - 24.06.2026

### Changed
- Chart Playground: voller Backtest entfernt, nur noch Schnellbacktest
  - Backtest-Button, JS-Funktion runBacktest und Backend-Route POST /api/chart-playground/run-backtest entfernt — aus dem Playground wird kein voller Backtest-Run mehr erzeugt
  - Schnellbacktest- und Refresh-Button an die alte Backtest-Position oben neben Chart laden verschoben; Refresh-Button auf Beschriftung R reduziert (Tooltip unveraendert)
  - Schnellbacktest-Ergebnis-Badge bleibt an seinem Platz im Analyse-Tab-Header
  - Ergebnisbox (cpResultPanel) samt Kennzahlen-Leiste, Volle-Result-Link und Status-Zeile entfernt; tote Fuell-Funktionen cpRenderResultPanel/cpFillStatsKennzahlen/cpClearPreviousResult geloescht
  - Trade-Marker-Master-Schalter (cpToggleMarkers) entfernt — die Pfeile werden jetzt allein ueber die Long/Short-Buttons in der Chart-Leiste gesteuert
  - Obsolete Testdatei test_chart_playground_no_rules_key.py geloescht (testete ausschliesslich die entfallene Route)

### Files
- services/frontend/templates/chart_playground/index.html
- services/api/routes/api_chart_playground.py
- tests/test_chart_playground_no_rules_key.py



## [1.26.6] - 24.06.2026

### Changed
- Projektweite Umstellung deutscher Textquellen auf echte Umlaute und verschärfte Sprach-Regel
  - Umlaut-Sweep über das gesamte Projekt: deutsche Lesetexte (Kommentare, Docstrings, Fehlermeldungen, Logging, Templates, Markdown-Doku) von der Ersatzschreibung (ae/oe/ue/ss) auf echte Umlaute (ä/ö/ü/ß) umgestellt; 129 Dateien betroffen
  - Code-Identifier (Variablen-, Funktions-, Klassennamen, Keys), englische Wörter und korrekte ss-/Diphthong-Schreibungen blieben bewusst unverändert; py_compile aller geänderten Python-Dateien grün, UTF-8 intakt
  - CLAUDE.md Sprach-Regel verschärft: Deutsch mit echten Umlauten als harte Regel, Englisch nur noch für Code-Identifier, eigener Hinweis zu kontextabhängigen Wörtern (nach Bedeutung wählen statt mechanisch ersetzen)
  - Auto-Commit-Hook um Pausen-Schalter erweitert: Flag-Datei .claude/auto-commit.paused (gitignored) unterdrückt WIP-Commits bei langen Sweep-/Hintergrund-Agenten; in CLAUDE.md dokumentiert

### Files
- .claude/hooks/auto-commit.sh
- CLAUDE.md
- .gitignore



## [1.26.5] - 24.06.2026

### Changed
- Repo für Apache-2.0-Open-Source aufbereitet 
  - Apache-2.0-LICENSE im Repo-Root ergänzt; README um einen Lizenz-Abschnitt und den Abschnitt 'VectorBT Pro — notwendiges externes Framework' (Bezug nur mit eigener VBT-Pro-Lizenz, Build per SSH-Key als BuildKit-Secret) erweitert
  - README-Funktionsumfang um OHLC-Daten-Management ergänzt, Playground-Screenshot eingebunden; Falschaussagen zu synchron/asynchron korrigiert (Playground rechnet synchron und persistiert; asynchroner Run läuft über POST /api/backtest/start)
  - Konzept-anlegen-Modal (strategy_concepts.html): Name als erstes Pflichtfeld, Slug wird automatisch aus dem Namen erzeugt (read-only); beim Bearbeiten bleibt der bestehende Slug stabil
  - Veraltete interne Übergabe-Notiz documentation/per-indikator-timeframe-resample-uebergabe.md gelöscht; documentation/backup/ in .gitignore aufgenommen
  - Obsolete Fine-Grained-Token-Zeile aus .env.example entfernt (Auth läuft über SSH)

### Files
- LICENSE
- README.md
- .gitignore
- .env.example
- documentation/project/projekt.md
- documentation/knowledge/indicators.md
- documentation/per-indikator-timeframe-resample-uebergabe.md
- services/frontend/templates/chart_playground/index.html
- services/frontend/templates/config/strategy_config_edit.html
- services/frontend/templates/config/strategy_iteration_edit.html
- services/frontend/templates/config/strategy_concepts.html



## [1.26.4] - 24.06.2026

### Removed
- Verwaiste Spec-Runner-Bring-up-Artefakte entfernt und Legacy-Baum zusaetzlich abgesichert

### Files
- user_data/strategies/generic/spec_strategy_start.py




## [1.26.3] - 23.06.2026

### Changed
- Strategie-Doku: indicators.md aus dem Custom-Indikator-Workflow erreichbar gemacht + Fallstricke aus dem TAP-Build dokumentiert.
  - AGENT_ENTRY.md verlinkt indicators.md jetzt im Workflow-Index (Custom-Indikator) und in den Verweisen — vorher war die verbindliche Indikator-Referenz aus der Strategie-Entwicklung nicht auffindbar.
  - custom-indikator.md: Cross-Link auf indicators.md + neue Sektion 'Fallstricke' (plot_type-Namens-Heuristik, @njit(cache=True)-Bruch unter pytest, Container!=venv-Dependency, Pine-ta.ema-Seed fuer TradingView-Treue, Wegwerf-Setup-Rezept zum visuellen Verifizieren).
  - indicators.md: plot_type-Heuristik in Sektion 2 geschaerft, neue Custom-Indikatoren dwsSMI/dwsTrendlineTouch in Sektion 3, neue Sektion 3.1 (benannte Indikatoren originalgetreu nachbauen: Lib-Variante pruefen, Pine-EMA, Container-Check).

### Files
- documentation/knowledge/strategy-development/AGENT_ENTRY.md
- documentation/knowledge/strategy-development/workflows/custom-indikator.md
- documentation/knowledge/indicators.md



## [1.26.2] - 23.06.2026

### Changed
- custom:dwsSMI nutzt jetzt eine Pine-exakte EMA (ta.ema-Seed) statt talib.EMA — bit-identisch zum TradingView-SMI ab dem ersten Balken.
  - talib.EMA seedet mit SMA, Pine ta.ema mit dem ersten Quellwert — das wich in der Warmup-Phase ab. Neue _pine_ema_nb (Numba) repliziert ta.ema exakt: alpha=2/(length+1), Seed=erster Wert, NaN-Handling wie Pine.
  - Verifiziert gegen eine Pine-Nachrechnung auf SOL/USDT 4h: max. abs. Abweichung ueber alle 12816 Bars = 0.0 (inkl. erstem Wert), nicht nur nach Warmup.
  - Formel und Defaults (K=10, D=3) unveraendert; nur die EMA-Implementierung ist jetzt Pine-treu.

### Files
- user_data/utils/indicators/custom.py



## [1.26.1] - 23.06.2026

### Changed
- custom:dwsSMI Defaults auf den TradingView-Standard-SMI angeglichen (k_length=10, smooth1=3, smooth2=3) — originalgetreu.
  - Bisherige Defaults (13/25/2) stammten aus einer Spec-Schaetzung; der Plattform-Standard (TAP-Spec: 'Standard-SMI der Plattform') ist K=10, Glaettung D=3.
  - Gegen eine Pine-Style-Nachrechnung (TradingView-EMA, K=10/D=3) auf SOL/USDT 4h verifiziert: Korrelation 1.0, max. Abweichung nach Warmup 0.0 — bit-identisch.
  - Formel unveraendert; nur die Default-Parameter wurden gesetzt, alle Params bleiben im Playground tunebar.

### Files
- user_data/utils/indicators/custom.py
- tests/test_dws_smi.py



## [1.26.0] - 23.06.2026

### Added
- Neuer Custom-Indikator custom:dwsSMI — Stochastic Momentum Index nach Blau (High/Low-Range-basiert, Skala ~+-100) als TAP-Filter.
  - talib-basiert (MAX/MIN + doppelte EMA-Glaettung), keine pandas_ta-Dependency — pandas_ta ist im Container nicht installiert und sein 'smi' waere die Ergodic/TSI-Variante, nicht der Blau-SMI.
  - Skala so kalibriert, dass die Spec-Schwellen +40 (ueberkauft -> Short) / -40 (ueberverkauft -> Long) nativ greifen.
  - Inputs high/low/close; Params k_length, smooth1, smooth2, signal; Outputs smi + signal (Signallinie).
  - Subplot-Keyword 'smi' im Playground-Katalog ergaenzt (Oszillator im eigenen Panel).
  - Unit-Tests mit synthetischen Daten (Skala, Aufwaerts=ueberkauft, Abwaerts=ueberverkauft, Warmup).

### Files
- user_data/utils/indicators/custom.py
- services/api/routes/api_chart_playground.py
- tests/test_dws_smi.py



## [1.25.0] - 23.06.2026

### Added
- Neuer Custom-Indikator custom:dwsTrendlineTouch (TAP-Methode) — erkennt die 3./4. Trendlinien-Beruehrung mit Abpraller.
  - Kausaler, pivot-basierter Touch-Detektor auf VBT pivot_info_1d_nb + talib-ATR, Numba-Schleife mit Hysterese.
  - Multi-Output: short_line/long_line (preisskalierte Trendlinien, Overlay), short_signal/long_signal (Entry-Bars) — direkt in Entry-Regeln nutzbar.
  - Params: up_th/down_th (Pivot-Zigzag), atr_length, touch_tol_atr, break_tol_atr, dev_max_atr, min_touch/max_touch.
  - Overlay-Keyword 'trendline' im Playground-Katalog ergaenzt, damit die Linien ueber dem Preis statt im Subplot liegen.
  - Unit-Tests mit synthetischen Daten (Invarianten + Kausalitaet).

### Files
- user_data/utils/indicators/custom.py
- services/api/routes/api_chart_playground.py
- tests/test_dws_trendline_touch.py



## [1.24.0] - 23.06.2026

### Changed
- Chart-Playground: Anzeige-Schalter (Candles/Equity/Long/Short) als Toggle-Buttons in die Chart-Toolbar verschoben
  - Vier View-Schalter sind jetzt an-/abwählbare Toggle-Buttons (tf-btn) in der Chart-Toolbar rechts neben «Höhe» statt Schiebeschalter in einer eigenen Card
  - Kurzlabels ohne «anzeigen/Positionen»: Candles, Equity, Long, Short
  - Separate Anzeige-Card (#cpDisplayToggles) entfernt
  - Logik unverändert: versteckte Checkbox-Inputs mit gleichen IDs bleiben erhalten, alle bestehenden checked-Reads und change-Listener funktionieren weiter; die .active-Klasse wird per cpSyncViewBtns gespiegelt (auch nach Setup-Laden)
  - Tote #cpDisplayToggles-Referenz im invalidateLiteResult-Listener aufgeräumt

### Files
- services/frontend/templates/chart_playground/index.html
- services/frontend/static/css/app.css



## [1.23.0] - 23.06.2026

### Changed
- Chart-Playground: Layout der Indikator-Cards und der Entry/Exit-Regelblöcke überarbeitet
  - Indikator-Card: Typ-Dropdown (Plot-Position) in die Visualisierungs-Card der erweiterten Optionen verschoben, separate Anzeige-Card entfernt
  - Indikator-Card: Chart-Sichtbarkeit vom Schiebeschalter zu schlichter Checkbox geändert (bleibt rein visuell)
  - Indikator-Card: Löschen-Button und Indikator-aktiv-Schalter als rechtsbündige Spalte rechts neben der Visualisierungs-Card in den erweiterten Optionen (X oben, darunter Label links und Schalter rechts)
  - Entry/Exit-Regelblock: Block-Aktiv-Checkbox zu Schiebeschalter geändert und per ms-auto ganz nach rechts gesetzt
  - Entry/Exit-Regelblock: Entry/Exit-Typ-Label aus dem Footer entfernt und als absolut positionierter Tag oben rechts an der Box angezeigt (ohne zusätzliche Block-Höhe)

### Files
- services/frontend/templates/chart_playground/index.html
- services/frontend/static/css/app.css



## [1.22.1] - 23.06.2026

### Changed
- Dokumentation und Strategie-Toolbox auf Rule-Block- und Indikator-enabled (Ticket 48) nachgezogen
  - Strategie-Kontext-Single-Source (_inject.md): enabled pro Block (Default true, pro Block nicht pro Gruppe) und pro Indikator in die spec_json-Struktur aufgenommen; exit darf null oder {blocks: []} sein
  - code-referenz.md: Block-Format-Abschnitt um enabled-Verhalten erweitert (deaktivierter Block aus ODER gefiltert, kein Fehler; aktiver Block auf deaktivierten Indikator = ValueError) mit Code-Beleg
  - ds-strategie-session-Toolbox render_spec: auf Block-Format (DNF) umgestellt (las zuvor das tote Alt-Format {logic, conditions} und zeigte aktuelle Specs gar nicht an); deaktivierte Bloecke/Indikatoren und Short-Bloecke werden im Briefing markiert

### Files
- documentation/knowledge/strategy-development/_inject.md
- documentation/knowledge/strategy-development/code-referenz.md
- .claude/skills/ds-strategie-session/scripts/toolbox.py



## [1.22.0] - 23.06.2026

### Added
- Ticket 48: Aktiv-Schalter pro Regel-Block und Indikator im Chart-Playground
  - Globaler cpExitEnabled-Schalter entfernt; jeder einzelne ODER-Bedingungs-Block (Entry und Exit) hat jetzt einen eigenen Aktiv-Schalter
  - evaluate_rules_native: deaktivierte Blöcke (enabled: false) werden vor Partitionierung/Auswertung herausgefiltert — abwärtskompatibel (fehlendes Feld = true)
  - Kein Auto-Leer-Exit-Block mehr beim Öffnen des Playgrounds
  - Indikator-Card: enabled-Schalter in Erweiterten Optionen (logik-wirksam, getrennt vom Anzeige-Schalter; invalidiert Schnelltest)
  - Deaktivierte Indikatoren aus Bedingungs-Dropdowns ausgenommen
  - Serialisierung: enabled in allen 3 Indikator-Pfaden (buildBacktestPayload, collectSetupConfig, collectIndicatorConfigJson) und beiden Load-Pfaden
  - _validate_rule_references: nur aktive Blöcke in Referenz-Prüfung — deaktivierter Block kann deaktivierten Indikator referenzieren ohne Fehler
  - 11 neue Tests in test_ticket48_block_enabled.py; test_spec_runner_rule_validation.py auf Blocks-Format aktualisiert

### Files
- user_data/strategies/generic/rules_engine.py
- user_data/strategies/generic/spec_runner.py
- services/frontend/templates/chart_playground/index.html
- tests/test_ticket48_block_enabled.py
- tests/test_spec_runner_rule_validation.py
- documentation/tickets/48-playground-entry-exit-indikator-enabled-schalter.md



## [1.21.2] - 23.06.2026

### Changed
- Strategie-Konzepte: ID-Spalte vor Slug, Konzept-Zeilen starten zugeklappt
  - Neue ID-Spalte (reine Zahl) direkt vor der Slug-Spalte in der Konzepte-Tabelle
  - Standard-Sortierung auf den neuen Slug-Spaltenindex nachgezogen
  - Automatisches Aufklappen aller Zeilen beim Laden entfernt - Zeilen starten zugeklappt, Aufklappen nur per Klick auf den Pfeil
  - Iterationen-Tabelle in der Child-Row unveraendert

### Files
- services/frontend/templates/config/strategy_concepts.html



## [1.21.1] - 23.06.2026

### Changed
- Playground: Slug- und Kategorie-Feld aus "Spec speichern"-Modal entfernt
  - Beim Anlegen eines neuen Konzepts werden nur noch Name und Beschreibung abgefragt
  - Slug wird weiterhin im Hintergrund aus dem Namen abgeleitet, Kategorie bleibt leer

### Files
- services/frontend/templates/chart_playground/index.html



## [1.21.0] - 23.06.2026

### Added
- Playground: Spec als neue Iteration oder neues Konzept speichern
  - Neuer Button "Spec speichern…" im Playground (immer verfügbar) öffnet ein kombiniertes Modal
  - Konzept-Dropdown vereint beide Fälle: bestehendes Konzept = neue Iteration darunter (Vorschau der nächsten Nummer); "+ Neues Konzept…" blendet Name/Slug/Kategorie ein und legt Konzept + Iteration 1 in einem Rutsch an
  - Slug wird live aus dem Namen abgeleitet (Server normalisiert zusätzlich)
  - Überschreiben-Button der gewählten Iteration bleibt erhalten, erscheint nur bei ausgewählter Iteration
  - Nutzt bestehende Endpunkte POST /api/strategy/concepts und POST /api/strategy/iterations, keine Backend-/Migrationsänderung

### Files
- services/frontend/templates/chart_playground/index.html



## [1.20.2] - 23.06.2026

### Added
- Strategie-Toolbox: Verben zur Bestwert-Auswertung von Multiparameter-Läufen
  - run-best <run_id> <metrik> [min_trades=30] [limit=1]: bester Result mit Trade-Floor (gegen Low-Trade-Flukes), serverseitig über /results/dt
  - run-winrate-band-best <run_id> [band_pp=20] [limit=1]: bestes Total Return im oberen Win-Rate-Band (Max-WinR minus band_pp)
  - run-top-results zeigt jetzt zusätzlich die Win-Rate in jeder Ergebniszeile
  - Doku: multiparameter-lauf.md auf nativen Raster-Lauf + vier Bestwerte umgestellt, SKILL.md ds-strategie-session um Auswertungs-Sektion ergänzt

### Files
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- .claude/skills/ds-strategie-session/SKILL.md
- documentation/knowledge/strategy-development/workflows/multiparameter-lauf.md



## [1.20.1] - 21.06.2026

### Fixed
- Multi-Combo im nativen Spec-Runner-Pfad jetzt korrekt vektorisiert statt fehlerhaftem Single-Combo-Pre-Expand (Ticket 47)
  - Der frühere Ticket-47-Phase-2-Pfad zwang ALLE Multi-Combo-Specs in Single-Combo-Chunks (chunk_size=1). Das lieferte zwar bit-identische Metrik-Werte, zerstörte aber die Spalten-Identität: die Indikator-Param-Achse verschwand aus dem Spalten-Index, sodass nicht mehr zuordenbar war, welche Indikatorwerte welche Metrik erzeugt haben (brach Leaderboard/Result-actual_params).
  - rules_engine.evaluate_rules_native verarbeitet Multi-Combo + Stop-Sweep jetzt in EINEM vektorisierten from_signals(signal_func_nb=...)-Aufruf: close wird auf die n_combo Indikator-Spalten gebracht (close_mc mit Indikator-Param-Spalten-Labels), die Stop-vbt.Param-Achse kreuzt VBT-nativ (Stop aussen, Indikator innen).
  - _state_exit_signal_func_nb erhält ein combo_col_map (col % n_combo) und mappt jede Portfolio-Spalte zurück auf die Indikator-Spalte der 2D-Entry-/Exit-/static-Block-Masken. Tracking-Arrays haben jetzt Länge n_total (n_combo * n_stops), da jede Stop-Variante eigenen Trade-State hat.
  - Series-Operanden in stateful Conditions bei Multi-Combo werden über ein combo-major series_bundle + series_col_map ((col % n_combo) * n_slots) korrekt aufgelöst. Der frühere N5-Hard-Reject und der Stop-Sweep-x-Multi-Combo-ValueError sind entfernt; die orphane Funktion _assert_no_series_ops_in_stateful wurde gelöscht.
  - n_combo wird aus der breitesten Quelle abgeleitet (Entry-/Short-Entry-Masken, close, stateful Series-Bundles ODER statische Exit-Conditions). Single-Combo-Chunks behalten ihren Indikator-Param-Spalten-Label (statt Default 0).
  - Ticket-44-Multi-Combo-Sub-Grid-Chunking in spec_runner.run_spec_strategy reaktiviert (kein Single-Combo-Zwang mehr); das OOM-schützende Chunking großer Grids bleibt erhalten. spec_runner.VERSION auf 1.2.1 erhöht.
  - Verifiziert: 3 Indikator-Längen x 2 Stops über run_spec_strategy liefert identischen Spalten-MultiIndex [(stop,ind),...] UND bit-identische total_return wie die per-Kombi-Referenz; gechunkt vs. ungechunkt bit-identisch. Neue Bit-Parity-Tests in test_ticket47_native_short.py (Multi-Combo x Stop-Sweep + Multi-Combo-only). 98 Tests grün.

### Files
- user_data/strategies/generic/rules_engine.py
- user_data/strategies/generic/spec_runner.py
- tests/test_ticket47_native_short.py
- tests/test_combo_batching.py
- tests/test_ticket35_native_state_exits.py



## [1.20.0] - 21.06.2026

### Changed
- Ticket 47 Phase 2: Einheitlicher nativer Pfad — Masken-Pfad aus spec_runner entfernt
  - evaluate_rules_native akzeptiert jetzt Specs ohne exit_spec (Positionen schliessen nur per Stops)
  - spec_runner nutzt ausschliesslich evaluate_rules_native (signal_func_nb) — use_native-Flag und else-Zweig entfernt
  - Multi-Combo-Specs werden automatisch auf Single-Combo-Chunks aufgeteilt (evaluate_rules_native unterstuetzt kein Multi-Combo-Portfolio)
  - Bit-Parity-Test: TestBitParityNativeVsMask prueft Uebereinstimmung nativer Pfad vs. Masken-Pfad fuer statische Long-Only-Specs
  - guide.md: Abschnitt 'Zwei Ausfuehrungs-Pfade' ersetzt durch 'Einheitlicher nativer Pfad'
  - test_combo_batching.py: Drei Tests an neues Single-Combo-Chunking-Verhalten angepasst
  - spec_runner.VERSION auf 1.2.0 (Minor-Bump: neue Feature-Klasse, rueckwaertskompatibel)

### Files
- user_data/strategies/generic/rules_engine.py
- user_data/strategies/generic/spec_runner.py
- tests/test_ticket47_native_short.py
- tests/test_combo_batching.py
- documentation/knowledge/strategy-development/guide.md
- documentation/tickets/47-native-pfad-short-multicombo-vereinheitlichung.md



## [1.19.0] - 21.06.2026

### Added
- Ticket 47 (Teil 1): Short-Unterstützung im nativen Pfad (evaluate_rules_native)
  - _state_exit_signal_func_nb erweitert: nimmt short_entry_mask + vollständige Short-Exit-Block-Kodierung entgegen; wertet per c.last_pos_info['direction'] (0=Long, 1=Short) die korrekte Exit-Gruppe aus
  - Bei Long-Position: Long-Exit-Blöcke auswerten, Short-Entry durchlassen (upon_opposite_entry='Reverse' übernimmt Umkehr)
  - Bei Short-Position: Short-Exit-Blöcke auswerten, Long-Entry durchlassen
  - evaluate_rules_native: Entry- und Exit-Blöcke je nach is_short partitioniert; Long- und Short-Exit-Spec separat kodiert (_build_stateful_condition_spec) und an signal_func_nb übergeben
  - Rein statische Exit-Specs (flat_stateful leer) sind jetzt erlaubt — n_blocks > 0 reicht
  - _check_no_short_blocks_in_native_path-Guard entfernt (Ticket-46-Sperre)
  - Short-Guard aus evaluate_rules() entfernt; State-Refs im Masken-Pfad werfen weiterhin ValueError aus _resolve_ref
  - upon_opposite_entry='Reverse' im from_signals-Aufruf des nativen Pfads ergänzt
  - Platzhalter-Masken/Block-Starts für leere Long-/Short-Exit-Seite (Numba braucht einheitlichen Typ)
  - 27 neue / angepasste Tests in test_rules_engine_short.py und test_ticket47_native_short.py grün

### Files
- user_data/strategies/generic/rules_engine.py
- tests/test_rules_engine_short.py
- tests/test_ticket47_native_short.py



## [1.18.1] - 21.06.2026

### Fixed
- Ticket 46: Short-Block-Guard greift jetzt auch im nativen Pfad (evaluate_rules_native)
  - Neuer Helper _check_no_short_blocks_in_native_path() prüft rules_json auf is_short=True in Entry- und Exit-Gruppe bevor evaluate_rules_native irgendetwas berechnet
  - Guard in evaluate_rules (Masken-Pfad) bleibt unberührt — deckt den direkten Aufruf-Fall ab
  - Neuer Testblock TestGuardShortWithStateExitNativePath (3 Tests) treibt den Guard über evaluate_rules_native direkt (echten Routing-Pfad); bisherige TestGuardShortWithStateExit-Tests bleiben als Ergänzung
  - Falsch-grüner Test war: TestGuardShortWithStateExit rief evaluate_rules direkt auf und umging spec_runner-Routing — bewies nichts über den Produktionspfad

### Files
- user_data/strategies/generic/rules_engine.py
- tests/test_rules_engine_short.py



## [1.18.0] - 21.06.2026

### Added
- Ticket 46: Short-Positionen im Masken-Pfad des Spec-Runners via is_short=True auf Entry/Exit-Blöcken
  - rules_engine.py: SignalMasks-NamedTuple (long_entries, long_exits, short_entries, short_exits) als neuer Rückgabewert von evaluate_rules — ersetzt (entries, exits)-Tupel
  - rules_engine.py: Blöcke mit is_short=True werden zu short_entries/short_exits partitioniert; Long-Blöcke ohne Flag bleiben wie bisher
  - rules_engine.py: Hard-Guard — Short-Blöcke + State-Refs in exit_spec lösen ValueError aus (Ticket 47 bringt Short im nativen Pfad)
  - spec_runner.py: Downstream auf SignalMasks umgestellt; from_signals erhält short_entries/short_exits + upon_opposite_entry='Reverse'; kein direction-Parameter
  - spec_runner.py: VERSION → 1.1.0 (Minor-Bump rückwärtskompatibel)
  - spec_runner.py: signals-Dict enthält jetzt vier Masken statt entries/exits
  - api_chart_playground.py: TP/SL-Preise in run-backtest-lite richtungsabhängig berechnet (Short: tp unterhalb, sl oberhalb)
  - index.html: is_short-Checkbox pro Entry/Exit-Block im Chart-Playground; Short-Blöcke visuell mit rotem Rand
  - index.html: cleanRuleGroup nimmt is_short durch für Persistenz beim Speichern/Laden
  - tests/test_rules_engine_short.py: 14 neue Tests (Long/Short-Signale, Long-Only-Regression, Short-Only, Hard-Guard, SignalMasks-Struktur)
  - Bestehende Tests auf SignalMasks-Interface umgestellt (test_rules_engine_blocks, test_rules_engine_combine_broadcast, test_ticket35_native_state_exits)

### Files
- user_data/strategies/generic/rules_engine.py
- user_data/strategies/generic/spec_runner.py
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html
- tests/test_rules_engine_short.py
- tests/test_rules_engine_blocks.py
- tests/test_rules_engine_combine_broadcast.py
- tests/test_ticket35_native_state_exits.py



## [1.17.45] - 20.06.2026

### Fixed
- Recompute speicherte Detail-Tabellen mehrfach (Faktor 3x) — recompute_single_result ist jetzt idempotent
  - Ursache: recompute_single_result fuegte Equity/Trades/Orders/Positions/Indikatoren ohne vorheriges DELETE ein. Jeder erneute Recompute (mehrere Trigger-Pfade: chart-data, trades/orders/positions, full-metrics, Worker-Job) haengte eine weitere volle Kopie an — die Einzel-Detailzeilen vervielfachten sich (3 Trigger = 3x), waehrend das Aggregat (total_trades) korrekt blieb. Das rekonstruierte Portfolio hatte korrekt nur 1 Spalte; die Engine war nicht die Ursache.
  - Fix: Neuer Helper _clear_result_details(conn, result_id) loescht alle fuenf Detail-Tabellen des Results in derselben Transaktion vor dem Insert. Damit ist der Recompute idempotent, egal ueber welchen Pfad oder wie oft er ausgeloest wird.
  - Verifiziert an Result 3828285: vorher trades 270 / orders 540 / positions 270 / equity 9141 / indicators 18195 — nachher 90 / 180 / 90 / 3047 / 6065, Aggregat total_trades 90 unveraendert, Sell-stop_type-Verteilung TD 75 / SL 10 / TP 5. Zwei aufeinanderfolgende Direkt-Recomputes liessen die Counts unveraendert (Idempotenz bestaetigt).
  - Test: tests/test_recompute_idempotent_details.py prueft Loeschvertrag (nur Ziel-Result betroffen), Idempotenz nach Re-Insert und Vollstaendigkeit der Tabellen-Konstante.
  - Hinweis: Andere bereits mehrfach recomputete Results koennen ebenfalls vervielfachte Detailzeilen tragen (Aggregat stimmt). Kein Massen-Cleanup durchgefuehrt — ein erneuter Recompute heilt betroffene Results jetzt automatisch.

### Files
- services/api/recompute.py
- tests/test_recompute_idempotent_details.py



## [1.17.44] - 19.06.2026

### Removed
- Tote services/api/schemas.py entfernt (vom gleichnamigen Package schemas/__init__.py verschattet, nie geladen)
  - Im selben Verzeichnis lag ein Modul schemas.py und ein Package schemas/ - Python laedt bei import services.api.schemas immer das Package, das Modul war damit unerreichbar
  - Alle Klassen aus schemas.py waren bereits im Package vorhanden (kein Verlust)

### Files
- services/api/schemas.py



## [1.17.43] - 19.06.2026

### Fixed
- Run-Dauer in der Runs-Liste zeigt jetzt die echte Verarbeitungszeit statt der Queue-Wartezeit
  - Neue Spalte backtest_runs.started_at (nullable) via Migration 0011 - wird beim Wechsel des Runs auf Status running gesetzt (Moment, in dem der Worker den Job aufgreift)
  - update_backtest_run_status() schreibt started_at bei status=running
  - Frontend berechnet die Dauer als completed_at - started_at; Fallback auf created_at fuer Alt-Runs ohne started_at
  - Bisher wurde completed_at - created_at gerechnet, wodurch die Queue-Wartezeit faelschlich als Rechenzeit erschien
  - BacktestRunOut um started_at ergaenzt (in services/api/schemas/__init__.py - die gleichnamige schemas.py wird vom Package verschattet und ist toter Code)

### Files
- alembic/versions/0011_run_started_at.py
- user_data/utils/database/models.py
- user_data/utils/database/repository.py
- services/api/schemas/__init__.py
- services/frontend/templates/backtest/runs.html



## [1.17.42] - 19.06.2026

### Fixed
- Results-Header zeigte bei run_id-Filter die Gesamtzahl; Runs-Liste zählte ineffizient
  - Results-Tabelle: Die Header-Zahl 'Results (N)' zeigte bei gefilterter Ansicht (z.B. ?run_id=2454) faelschlich den Gesamt-Schaetzwert der ganzen Tabelle statt des gefilterten Run-Werts. Ursache: Der Header wurde in DataTables' dataSrc gesetzt, das bei JEDEM Response laeuft - auch beim initialen, ueberholten Draw ohne run_id-Filter. Verschoben nach drawCallback (nur akzeptierte Draws, in Reihenfolge); liest page.info().recordsDisplay.
  - Runs-Liste (/api/backtest/runs): Result-Anzahl pro Run wird nicht mehr per GROUP BY ueber die ganze backtest_results-Tabelle gezaehlt, sondern gezielt nur ueber die run_ids der ABGESCHLOSSENEN Runs (completed/failed). Laufende/eingereihte Runs werden uebersprungen (result_count=None -> Frontend zeigt '–'); deren Zeilen werden gerade geschrieben (Count langsam, da Visibility Map nicht gesetzt) und die Zahl waere unvollstaendig - der Chunk-Fortschritt steht in der Status-Spalte.
  - Runs-Seite: Auto-Update-Schalter standardmaessig AUS (wie Results-Seite). Der 5s-Poll lud /api/backtest/runs samt Result-Zaehlung; bei offenen Tabs/Last stapelten sich die Counts und erstickten die DB gegenseitig (Query-Storm). Fuer Live-Fortschritt manuell aktivierbar.

### Files
- services/frontend/templates/backtest/results.html
- services/frontend/templates/backtest/runs.html
- services/api/routes/api_backtest.py



## [1.17.41] - 19.06.2026

### Changed
- Performance der Backtest-Results-Tabelle drastisch verbessert (Indizes + Query-Umbau)
  - Migration 0010: 16 Indizes auf backtest_results - pro Metrik-Spalte (sharpe, sortino, max_drawdown, trades, win_rate, profit_factor, total_return, end_value) je ein Single-Column- und ein Composite-Index (run_id, spalte), beide DESC NULLS LAST passend zur App-Sortierung. Die ungenutzten Plain-ASC-Indizes idx_res_profit_factor/idx_res_total_return wurden ersetzt. Alle Indizes CONCURRENTLY (kein Schreib-Lock).
  - results/dt-Endpoint: Run-Level-Filter (Konzept/Iteration/Symbol/Timeframe) werden vorab zu literalen run_ids aufgeloest und als run_id-IN-Liste auf backtest_results gefiltert, statt als Join-Praedikat. Nur literale run_ids bringen den Planner dazu, die Composite-Indizes zu nutzen (gemessen >11 s -> ms).
  - results/dt-Endpoint: records_total wird ohne den 5er-Join gezaehlt; bei komplett ungefilterter Tabelle via Planner-Schaetzung (pg_class.reltuples) statt Voll-Count (~10 s -> ~10 ms, skaliert mit Datenwachstum). Zweiter count() nur noch bei aktiver Suche.
  - Frontend: Auto-Update-Schalter der Results-Tabelle standardmaessig AUS (der teure 5s-Reload lief sonst dauerhaft; Results werden ohnehin erst nach Run-Ende nachgetragen).
  - Messung (run_id-Filter): 2552 ms -> ~25 ms; run_id + WinRate-Filter + Sort: 71623 ms -> 7 ms; ohne Filter: ~5700 ms -> ~11 ms.

### Files
- alembic/versions/0010_result_filter_sort_indexes.py
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/results.html



## [1.17.40] - 19.06.2026

### Fixed
- Fortschrittsanzeige beim Loeschen aller Backtest-Results ueberlebt jetzt einen Seiten-Reload
  - Bisher lebte die RQ-Job-ID nur in der JS-Closure der Results-Seite - nach F5 war sie verloren, sodass statt der Progressbar wieder der 'Alle loeschen'-Button erschien, obwohl der Loesch-Job in Redis weiterlief.
  - Neuer Endpoint GET /api/backtest/results/delete-active durchsucht die RQ-Registry (queued + StartedJobRegistry) nach einem aktiven delete_all_results_job und liefert job_id plus Fortschritt zurueck (oder job_id=None).
  - Frontend fragt diesen Endpoint beim Page-Load einmal ab und nimmt bei laufendem Job Progressbar und Polling automatisch wieder auf; poll/UI-Helfer dafuer wiederverwendbar gemacht.

### Files
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/results.html



## [1.17.39] - 19.06.2026

### Fixed
- PROCESS.md Phase 1 (Idee) auf das neue Idee-Template und die Dateinamen-Konvention gezogen
  - Phase 1 verwies auf das falsche Template (strategies/_templates/strategy-concept.md) statt auf das Idee-Template strategies-ideas/_templates/idea.md (type: strategy-idea).
  - Dateinamen auf <slug>-concept.md korrigiert (Flow-Diagramm + Phase 1 + Phase 2), Phase-2-Promotion vermerkt den Typ-Wechsel strategy-idea -> strategy-concept.
  - Abschluss-Check der Idee-Phase auf 'baubar' geschaerft: Markt, Quellen mit echten URLs, konkrete Entry-/Exit-Regeln + Handelslogik, Infra-Check.

### Files
- documentation/knowledge/strategy-development/PROCESS.md



## [1.17.38] - 19.06.2026

### Fixed
- Template-Verweise in Strategie-Workflow-Docs auf konsolidierten Vault-Ort umgebogen
  - Nach Vault-Template-Konsolidierung zeigten workflows/iteration.md (2x) und workflows/neue-strategie.md auf den geloeschten/falschen Pfad 99_Meta/templates/trading-*; jetzt auf 30_Trading/strategies/_templates/iteration.md bzw. strategy-concept.md.
  - Vault-seitig (ausserhalb des Repos, kein Commit): Ordner 30_Trading/templates/ samt 5 Vorlagen geloescht (Doppel trading-concept/-iteration/-strategy + ungenutzte trading-mandate/agent-session); neue Idee-Vorlage strategies-ideas/_templates/idea.md; Idee-Notizen auf <slug>-concept.md umbenannt; Vault-CLAUDE.md Note-Typ-Tabelle + Konvention aktualisiert; obsidian-Skill nachgezogen.

### Files
- documentation/knowledge/strategy-development/workflows/iteration.md
- documentation/knowledge/strategy-development/workflows/neue-strategie.md



## [1.17.37] - 19.06.2026

### Fixed
- Iter-Note-Frontmatter-Beispiel in workflows/iteration.md auf das gelebte Schema gebracht
  - Das Pflichtfeld-Beispiel nutzte noch alte Feldnamen (strategy, iteration, date, parent_iter, implementation, setup_id); ersetzt durch das Schema der echten Iter-Notes: iteration_id, concept_id, concept_slug, version (int), version_name, parent_iteration_id, status/workflow_state, hypothesis/verdict, metrics (mit win_rate), result_ids, created_at. 

### Files
- documentation/knowledge/strategy-development/workflows/iteration.md



## [1.17.36] - 19.06.2026

### Fixed
- Strategie-Doku konsistent gemacht: Iter-Note-Pfade, App-URLs als Variable, veraltete Ports/Worker-Namen/Versionsschema
  - Flat-Iter-Note-Pfade auf die Ordner-Konvention iterations/<version>/<slug>-<version>.md gebracht: neue-strategie.md, pine-reproduktion.md, AGENT_ENTRY.md, PROCESS.md (inkl. Versionsschema-Zeile).
  - Hartcodierte App-Host-URLs (192.168.193.12:8888 / :5570 / localhost:5570) in allen Workflow-Docs + project-structure.md durch $VBT_APP_BASE_URL ersetzt (zwei Deployments: lokal + PVE-Staging); Konventions-Notiz in AGENT_ENTRY.md. pgAdmin-Port und Staging-IP bewusst unangetastet.
  - guide.md: Port 8888->5570, logic-Feld-Verweis auf Block-Format (DNF) korrigiert; Worker-Restart auf docker compose ... worker statt fester Container-Name vbt_app-worker-1 (mehrere Docs).
  - project-structure.md: altes Versionsschema <prefix>-vMAJOR.MINOR durch version (Integer) + version_name ersetzt.
  - projekt.md: Vault-Env-Variable von OBSIDIAN_VAULT_PATH (Container) auf OBSIDIAN_VAULT_HOST_PATH (Host/.env) praezisiert.

### Files
- documentation/knowledge/strategy-development/workflows/neue-strategie.md
- documentation/knowledge/strategy-development/workflows/pine-reproduktion.md
- documentation/knowledge/strategy-development/workflows/custom-indikator.md
- documentation/knowledge/strategy-development/workflows/iteration.md
- documentation/knowledge/strategy-development/workflows/multiparameter-lauf.md
- documentation/knowledge/strategy-development/workflows/setup-via-api.md
- documentation/knowledge/strategy-development/guide.md
- documentation/knowledge/strategy-development/AGENT_ENTRY.md
- documentation/knowledge/strategy-development/PROCESS.md
- documentation/knowledge/project-structure.md
- documentation/project/projekt.md



## [1.17.35] - 19.06.2026

### Removed
- Nicht existentes Workflow-Feature (workflow-template/workflow-run) aus ds-strategie-session-Skill und toolbox.py entfernt
  - Skill und Toolbox bewarben workflow-template/workflow-run (lesen/kopieren/anlegen/starten/loeschen), aber im Backend existieren keine /api/workflow-Routen (kein Router, kein DB-Model, kein Frontend) - jeder Aufruf lief in einen 404.
  - toolbox.py: Funktionen workflow_template_read/workflow_run_read/workflow_template_copy, alle /api/workflow-Verb-Mappings, URL-Regex, Typ-Liste, Hilfetexte und der ungenutzte 'workflows'-Anzeigeblock entfernt; py_compile gruen.
  - SKILL.md: Workflow-Objekt aus der Objektliste (Z.3), den Frontend-URL- und <bereich>:<id>-Beispielen (Z.144/145) und der copy-Aufzaehlung (Z.154) gestrichen. Die Methodik-Workflows (Iteration, Vergleichsmessung etc.) bleiben unberuehrt.

### Files
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- .claude/skills/ds-strategie-session/SKILL.md



## [1.17.34] - 19.06.2026

### Changed
- ds-strategie-session-Skill generalisiert (Bedienung statt Methodik) + README um Bedienschicht-Hinweis ergänzt
  - Die fünf harten Verweise des public Skills auf den privaten Ordner documentation/knowledge/strategy-development/ zu optionalen Hinweisen entschärft - ein Public-Clone läuft nicht mehr ins Leere.
  - Trennung: Der Skill liefert die Bedienung (Trigger, Toolbox, Pfad A/B/C, Iter-Note-Pfad); die Methodik (Workflows, Iterations-Logs) bleibt bewusst privat und ist das eigene Vorgehen des Nutzers.
  - README: neuer Abschnitt 'KI-Bedienung & eigenes Strategie-Vorgehen' - nennt Skill + toolbox.py und empfiehlt, sich eine eigene Methodik-Wissensbasis unter documentation/knowledge/strategy-development/ plus optional einen Obsidian-Vault anzulegen.

### Files
- .claude/skills/ds-strategie-session/SKILL.md
- README.md



## [1.17.33] - 19.06.2026

### Fixed
- Iter-Note-Pfad-Konvention in Doku an gelebte Vault-Struktur angeglichen (Ordner pro Version)
  - Vault-Konvention ist iterations/<version>/<slug>-<version>.md (Ordner pro Version, damit Screenshots/Zusatzdokumente daneben liegen koennen) - die Doku beschrieb noch flache Formen.
  - workflows/iteration.md: Schreibpfad + Beispiel auf iterations/42/vwma-42.md korrigiert, Ordner-Begruendung ergaenzt.
  - ds-strategie-session SKILL.md Pfad C: Schreibpfad der Iter-Note von iterations/<version>.md auf iterations/<version>/<slug>-<version>.md korrigiert.

### Files
- documentation/knowledge/strategy-development/workflows/iteration.md
- .claude/skills/ds-strategie-session/SKILL.md



## [1.17.32] - 19.06.2026

### Fixed
- ds-strategie-session: Iter-Note-Suche im Vault auf rekursiven Glob umgestellt
  - Die dokumentierten Befehle in der SKILL.md nutzten den flachen Glob iterations/*.md, der die Iter-Notes verfehlte - diese liegen in Versions-Unterordnern (iterations/<version>/<slug>-<version>.md).
  - Phase 1 (Letzte-Aktivitaet/mtime) nutzt jetzt find -name '*.md' -printf '%T@' kombiniert mit der status.md-mtime, sortiert absteigend.
  - Phase 3 (Auswahl der letzten Iter-Note) listet die Notes ebenfalls rekursiv per find.

### Files
- .claude/skills/ds-strategie-session/SKILL.md



## [1.17.31] - 19.06.2026

### Changed
- Skill ds-strategie-session push-fähig gemacht: Homelab-spezifische Pfade generisch, Skill-Ordner aus der .claude-Sperre freigegeben
  - SKILL.md: hartcodierter Vault-Pfad an 8 Stellen durch $VAULT_ROOT ersetzt, neuer Resolver-Vorspann leitet den Vault-Root per wslpath aus OBSIDIAN_VAULT_HOST_PATH (.env) ab; Konvention 30_Trading/strategies bleibt (deckt sich mit obsidian_paths.py)
  - toolbox.py: Basis-URL aus VBT_APP_BASE_URL (Default http://localhost:5570) statt hartcodiert
  - Persönliche Beispiel-Slugs (vwma-dws/vwma_dws) zu neutralen (ema_cross/ema-cross, vault:vwma) generalisiert
  - .gitignore: Re-Include-Kette gibt nur .claude/skills/ds-strategie-session frei, restliches .claude bleibt privat
  - Verifiziert: secret_scan.py meldet 0 Treffer über beide Dateien, toolbox.py Syntax/Env-Override/--help OK

### Files
- .claude/skills/ds-strategie-session/SKILL.md
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- .gitignore



## [1.17.30] - 19.06.2026

### Added
- API-Endpunkt generate-labels für Indicator-Config-Notation
  - POST /api/config/indicator/{id}/generate-labels erzeugt Name und Beschreibung einer bestehenden Indicator-Config nach fester Notation und schreibt sie zurueck
  - Single Source in services/api/utils/indicator_labels.py (build_indicator_config_name/description/labels) — identische Notation wie die Frontend-Buttons; die KI muss sie beim Anlegen per API nicht selbst nachbauen
  - Name: <Konzept>-<Iteration> - <Kombinationen> Kombi. <tp>/<sl>; Beschreibung: TP, SL, TSL, delta_format (nur bei tsl_th), TD, time_delta_format (nur bei td_stop), null weggelassen
  - 12 Unit-Tests in services/api/tests/test_indicator_labels.py; ds-strategie-session-Skill um Verb indicator-config-generate-labels erweitert

### Files
- services/api/utils/indicator_labels.py
- services/api/routes/api_config.py
- services/api/tests/test_indicator_labels.py



## [1.17.29] - 19.06.2026

### Changed
- Beschreibung-Generierung: Stop-abhaengige Formate korrigiert
  - Reihenfolge TP, SL, TSL, delta_format, TD, time_delta_format
  - delta_format wird nur ausgegeben, wenn tsl_th gesetzt ist; time_delta_format nur, wenn td_stop gesetzt ist
  - TD wird jetzt mit ausgegeben (als ganze Zahl); TP/SL/TSL als Prozent
  - null-Stops und ihre Formate werden weggelassen; ohne Stops bleibt die Beschreibung leer

### Files
- services/frontend/templates/config/indicator_config_edit.html



## [1.17.28] - 19.06.2026

### Changed
- Indicator-Config: Titel- und Beschreibung-Generierung neu
  - "Titel generieren" schreibt jetzt nur ins Namensfeld im Format Konzept-Iteration - X Kombi. tp/sl (z.B. VWMA-2 - 65.637 Kombi. 5/15) und faesst die Beschreibung nicht mehr an
  - Konzept-Schreibweise wird unveraendert aus dem Dropdown uebernommen; ohne Konzept entfaellt der Kopf samt fuehrendem Trenner, mit Konzept aber ohne Iteration entfaellt nur die Iterationsnummer
  - Neuer Button "Beschreibung generieren" erzeugt die Stop-Uebersicht in Reihenfolge TP, SL, TSL (als th/stop), gefolgt vom delta_format; null-Stops werden weggelassen, ohne Stops bleibt die Beschreibung leer
  - Iterations-Optionen tragen die Versionsnummer als data-version-Attribut

### Files
- services/frontend/templates/config/indicator_config_edit.html



## [1.17.27] - 19.06.2026

### Added
- Button "Beschreibung generieren" auf der Indicator-Config-Seite
  - Neuer Button neben "Titel generieren" erzeugt eine kompakte Beschreibung im Format konzept-iteration - X Kombi. tp/sl (z.B. vwma-2 - 65.637 Kombi. 5/15)
  - Konzept (kleingeschrieben) und Iterations-Nummer aus den Strategie-Dropdowns, Kombinationen aus allen Range-Parametern hochgerechnet, TP/SL aus _stops (bei delta_format percent als Prozentzahl)
  - Iterations-Optionen tragen jetzt die Versionsnummer als data-version-Attribut

### Files
- services/frontend/templates/config/indicator_config_edit.html



## [1.17.26] - 19.06.2026

### Changed
- Testset-Dropdown auf /backtest/start zeigt Leaderboard-Hinweis
  - Testsets mit leaderboard_enabled=true bekommen im Auswahl-Dropdown den Zusatz '— Leaderboard' am Ende des Labels
  - Hinweis nur bei tatsächlich leaderboard-aktivierten Testsets; alle anderen unverändert
  - leaderboard_enabled war bereits in der /api/testsets-Response vorhanden, nur das JS-Label wurde erweitert

### Files
- services/frontend/templates/backtest/start.html



## [1.17.25] - 19.06.2026

### Changed
- Grundausstattungs-Daten-Load ans echte Ende der Migrationskette verschoben (neue Migration 0009), damit die Baseline testsets.leaderboard_enabled mit ausliefert
  - Ursache: 0006 lud die Testsets vor 0008 (Spalte leaderboard_enabled); ein Re-Export via pg_dump --column-inserts haette die Spalte ausgegeben und frische Installationen brechen lassen
  - 0006_seed_baseline_data ist jetzt No-op; neue Migration 0009_seed_baseline_data_at_end laedt die Grundausstattung nach allen Schema-Migrationen (gleicher Leerheits-Idempotenz-Schutz)
  - SQL-File _sql/0006_baseline_data.sql nach _sql/0009_baseline_data.sql umbenannt; export_baseline.py schreibt jetzt dorthin
  - Baseline neu exportiert: die 4 Vollzyklus-Testsets (id 4,8,12,16) kommen mit leaderboard_enabled=true, die uebrigen 12 mit false - exakt der aktuelle DB-Stand
  - Verifiziert: frische Migrationskette auf Scratch-DB reproduziert 16 Testsets (4 true) + 896 Configs; Dev-DB auf 0009 nachgezogen (Guard uebersprang den Load, Daten unangetastet); 37 Tests gruen
  - Doku korrigiert (CLAUDE.md, project-structure.md): falsche Aussage 0006 laufe am Kettenende; neue Regel dokumentiert, dass Baseline-Tabellen-Schemaaenderungen den Daten-Load ans Ende nachziehen muessen

### Files
- alembic/versions/0006_seed_baseline_data.py
- alembic/versions/0009_seed_baseline_data_at_end.py
- alembic/versions/_sql/0009_baseline_data.sql
- seed/export_baseline.py
- CLAUDE.md
- documentation/knowledge/project-structure.md



## [1.17.24] - 19.06.2026

### Added
- Spalte Leaderboard in der Testset-Liste zeigt pro Testset, ob ein Leaderboard-Eintrag erstellt wird (Ja/Nein-Badge)
  - Neue Spalte zwischen Beschreibung und Erstellt am, gespeist aus leaderboard_enabled der bestehenden /api/testsets-Antwort

### Files
- services/frontend/templates/testsets/list.html



## [1.17.23] - 19.06.2026

### Added
- Testset-Schalter leaderboard_enabled (Opt-in) steuert, ob ein abgeschlossener Testset-Lauf einen Leaderboard-Eintrag erzeugt
  - Neue Boolean-Spalte testsets.leaderboard_enabled (Default false) via Migration 0008
  - Gate in _build_leaderboard_entry_in_session: bei deaktiviertem Schalter wird der Eintrag bewusst uebersprungen (geloggt, kein Fehler)
  - Schiebeschalter in der Testset-Stammdaten-Maske; Wert ueber Create/Update-API und Repository durchgereicht und in TestSetOut exponiert
  - Opt-in: bestehende Testsets erzeugen ohne Aktivierung keine Leaderboard-Eintraege mehr
  - Build-Test-Fixtures auf enabled=True gesetzt, neuer Gate-Test test_leaderboard_disabled_kein_eintrag ergaenzt

### Files
- user_data/utils/database/models.py
- alembic/versions/0008_testset_leaderboard_flag.py
- user_data/utils/database/repository_testsets.py
- services/api/routes/api_testsets.py
- services/api/routes/views_testsets.py
- services/frontend/templates/testsets/detail.html
- tests/test_leaderboard_aggregat.py
- tests/test_leaderboard_spec_json_snapshot.py



## [1.17.22] - 19.06.2026

### Changed
- Lösch-Bestätigungsdialoge nennen jetzt explizit den Löschschutz-Status
  - Einzel-, Auswahl- und Alle-Löschen-Dialoge für Runs und Results zeigen im confirm() jeweils, ob der Favoriten-Löschschutz greift
  - Ohne Schutz (Einzel- und Auswahl-Löschung): Warnhinweis, dass favorisierte (gelb/rot) Einträge mitgelöscht werden
  - Mit Schutz (Alle löschen): Hinweis, dass Favoriten erhalten bleiben
  - Reine Frontend-Texte, keine Änderung an der Löschlogik

### Files
- services/frontend/templates/backtest/results.html
- services/frontend/templates/backtest/runs.html



## [1.17.21] - 19.06.2026

### Changed
- PVE1-Staging-Ports auf den 55xx-Block (5560-5579) angeglichen wie lokal
  - docker-compose-pve1.yml: Host-Ports umgestellt — App 8888->5570, pgAdmin 8081->5563, PostgreSQL 5432->5560, Redis 6380->5561 (Container-Ports unveraendert). Vollendet die am 2026-05-12 begonnene Port-Migration, die bisher nur das lokale Compose betraf.
  - Hintergrund: gemeinsame Port-Konvention der Trading-System-Projekte auf dem geteilten Host — jedes Projekt bekommt einen 20er-Block im 55xx-Bereich, um Kollisionen zu vermeiden. Lokal und Staging nutzen jetzt identische Ports.
  - Zugriffs-URLs in deploy-new.sh und deploy-update.sh entsprechend aktualisiert.
  - Obsidian port-liste.md angeglichen (vbt_app-Dienste auf 'lokal, PVE1', Historie ergaenzt).
  - Verifiziert: Redeploy via deploy-update datenerhaltend (896 configs / 355462 indicator-Zeilen unveraendert), App auf :5570 (HTTP 200), alter Port :8888 tot.

### Files
- docker-compose-pve1.yml
- documentation/deploy/pve1/deploy-new.sh
- documentation/deploy/pve1/deploy-update.sh



## [1.17.20] - 19.06.2026

### Fixed
- deploy-update.sh (PVE1) funktionsfaehig gemacht: Alembic in den App-Container verdrahtet
  - alembic==1.18.4 in services/api/requirements.txt aufgenommen (war in keinem Image installiert)
  - alembic/ + alembic.ini in den app-Service beider Compose-Dateien (local + pve1) gemountet, sodass Migrationen ueber `docker compose exec app alembic upgrade head` laufen
  - deploy-update.sh: toten backtest_seed.sql-Aufruf und veraltete 'NICHT deployen'-Warnung entfernt, Basis-Image-Absicherung (docker save/load) ergaenzt, Seed-Schritt durch `alembic upgrade head` im App-Container ersetzt (datenerhaltend, kein Dump-Restore)
  - Alembic-Aufruf setzt VBT_TEST_DATABASE_URL leer, damit env.py den POSTGRES_*-Pfad (db_vbt_v1) statt der im Container unerreichbaren Test-DB-URL nimmt
  - Verifiziert: deploy-update gegen Staging laeuft datenerhaltend (896 configs / 3 bt_runs / 131 ts_runs / 355462 indicator-Zeilen unveraendert), Alembic auf head 0007, App HTTP 200

### Files
- services/api/requirements.txt
- docker-compose-local.yml
- docker-compose-pve1.yml
- documentation/deploy/pve1/deploy-update.sh



## [1.17.19] - 19.06.2026

### Changed
- PVE1-Deploy-Pipeline auf Snapshot-Restore umgestellt und funktionsfähig gemacht
  - deploy-new.sh: Basis-Image (bt_pro_app_v1-vbt:latest) wird per docker save/load auf den PVE uebertragen, falls es dort fehlt (kein VBT-Pro-Lizenz-Key auf Staging noetig)
  - deploy-new.sh: DB-Befuellung jetzt ueber pg_restore eines lokalen Snapshots (seed/data/seed.dump) statt des veralteten backtest_seed.sql; Schema + Daten + alembic_version kommen mit dem Dump (landet automatisch auf head 0007)
  - deploy-new.sh: Plausibilitaetspruefung nach Restore (backtest_configs > 0) und Entschaerfung von Phantom-Runs (status='running' zum Snapshot-Zeitpunkt) auf 'failed'
  - deploy-new.sh: seed/data vom rsync ausgeschlossen (grosse Dumps separat per scp), data/ohlc_data wird mit uebertragen
  - docker-compose-pve1.yml: toten initdb-Mount auf user_data/utils/database/schema entfernt (Schema ist auf Alembic umgestellt)
  - Verifiziert: Clean Install auf PVE1, DB bit-genau repliziert (896 configs, 71971 equity- und 355462 indicator-Hypertable-Zeilen), App erreichbar unter :8888

### Files
- documentation/deploy/pve1/deploy-new.sh
- docker-compose-pve1.yml



## [1.17.18] - 18.06.2026

### Fixed
- Zwei weitere veraltete Tests an aktuellen Code-Stand angeglichen (ticket22, ticket42)
  - test_ticket42_result_config: delta_format wird seit Schritt 4d in indicators_config_json['_stops'] geliefert, nicht mehr im portfolio-Block - Assertion an die neue Position gezogen
  - test_ticket22_indicator_config_sorting: die Bucket-Sortierung nutzt is_default DESC, Iterations-Version DESC, name ASC; die zwei Tests erwarteten noch die alte alphabetische bzw. created_at-basierte Reihenfolge - erwartete Reihenfolge + Datei-Docstring korrigiert
  - Reiner Test-Altlasten-Fix wie zuvor bei test_full_config_snapshot - kein Produktivcode betroffen; beide Dateien nun gruen (14 passed) mit dem Projekt-venv-Interpreter

### Files
- tests/test_ticket42_result_config.py
- tests/test_ticket22_indicator_config_sorting.py



## [1.17.17] - 18.06.2026

### Fixed
- Veralteten Test test_full_config_snapshot an Stop-Umbau angepasst
  - Die zwei fehlschlagenden Snapshot-Tests legten td/tp/sl/tsl noch in der backtest_config ab (alte Position) - _build_full_config_snapshot liest Stops seit dem Stop-Umbau (1.15.4/1.15.5) aber ausschliesslich aus indicators_config['_stops']
  - Fixtures korrigiert: Stop-Werte in '_stops' verschoben (Eigentuemer IndicatorConfig), tote backtest_config-Stop-Felder entfernt
  - Kein Produktivcode betroffen - reiner Test-Altlasten-Fix; test_full_config_snapshot nun 11/11 gruen unter WSL

### Files
- tests/test_full_config_snapshot.py



## [1.17.16] - 18.06.2026

### Added
- Chunk-Fortschrittsanzeige für laufende Backtest-Runs im Frontend
  - BacktestRun erhält zwei nullable Spalten current_chunk/total_chunks (Alembic 0007); NULL bei ungechunkten oder Alt-Runs
  - Der Spec-Runner meldet im gechunkten Modus pro Chunk den Fortschritt an die DB - über einen optionalen progress_callback, der den Spec-Runner DB-frei hält (Worker injiziert das DB-Update)
  - Neue schlanke Repository-Funktion update_backtest_run_progress (ein UPDATE pro Chunk, vom Status entkoppelt)
  - Worker injiziert den Callback nur für Strategie-Funktionen, die den Parameter akzeptieren (Hardcoded-Legacy-Strategien bleiben unberührt)
  - BacktestRunOut-Schema und die Runs-Liste zeigen bei laufenden Runs jetzt 'Chunk X/Y' neben dem Status-Badge
  - Greift ab dem nächsten gechunkten Run - die 5s-Polling-Infrastruktur der Runs-Liste war bereits vorhanden

### Files
- user_data/utils/database/models.py
- user_data/utils/database/repository.py
- user_data/strategies/generic/spec_runner.py
- services/api/worker_tasks.py
- services/api/schemas/__init__.py
- services/frontend/templates/backtest/runs.html
- alembic/versions/0007_run_chunk_progress.py



## [1.17.15] - 18.06.2026

### Added
- Runs-Seite: Spalte Indikator-Config mit Namen der verknüpften Konfiguration
  - Neue Tabellenspalte 'Indikator-Config' direkt rechts neben Symbol; zeigt den Namen der ueber indicator_config_id verknuepften IndicatorConfig, sonst '-'
  - GET /api/backtest/runs laedt die Namen per run_id->indicator_config_id-Map (lose Referenz, nicht im Schema) und liefert indicator_config_name pro Run mit

### Files
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/runs.html



## [1.17.14] - 18.06.2026

### Changed
- Felder indicator_config_name und stops auch im /results-Endpoint mitliefern
  - GET /api/backtest/results joint IndicatorConfig lose ueber indicator_config_id und liefert indicator_config_name + aufgeloestes stops-Dict (td/tp/sl/tsl + tsl_th) analog zu /results/dt
  - Vereinheitlicht beide Result-Endpoints auf denselben Datensatz

### Files
- services/api/routes/api_backtest.py



## [1.17.13] - 18.06.2026

### Changed
- Results-Seite: Iterations-Spalte zeigt Stops im Tooltip und Indikator-Config-Namen
  - Iterations-Tooltip (Rover) zeigt jetzt zusaetzlich die aufgeloesten Stops (td/tp/sl/tsl + tsl_th) aus dem Result-Snapshot; gesweepte Stop-Keys werden gegen actual_params entdupliziert
  - Name der verknuepften Indikator-Konfiguration wird gedaempft an die Iterations-Anzeige angehaengt, falls das Result eine indicator_config_id traegt; fehlt/geloescht -> kein Name
  - Endpoint /api/backtest/results/dt joint IndicatorConfig lose ueber indicator_config_id und liefert indicator_config_name + stops-Dict mit

### Files
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/results.html



## [1.17.12] - 18.06.2026

### Fixed
- Run-Neustart bricht jetzt auch einen bereits laufenden alten Job ab, bevor neu eingereiht wird
  - restart_run entfernte bisher nur wartende Jobs aus der Queue (q.jobs). Ein bereits gestarteter Job des Runs lief nach dem Neustart parallel zum neu eingereihten Job weiter und blockierte unnoetig einen Worker.
  - restart_run nutzt jetzt denselben Helper _stop_run_jobs({run_id}) wie die Loesch-Handler: wartende Jobs raus, laufender Job per send_stop_job_command gestoppt, dann erst der neue Job eingereiht.

### Files
- services/api/routes/api_backtest.py



## [1.17.11] - 18.06.2026

### Fixed
- Run-Loeschung bricht jetzt auch bereits laufende Worker-Jobs ab, nicht nur wartende
  - Bisher entfernten delete_run, delete_all_runs und bulk_delete_runs nur wartende Jobs aus der Queue (q.jobs bzw. q.empty()). Ein bereits von einem Worker gestarteter Job lief nach dem Loeschen sinnlos zu Ende und blockierte die Worker-Kapazitaet fuer wartende Runs.
  - Neuer Helper _stop_run_jobs() raeumt wartende Jobs aus der Queue UND stoppt laufende Jobs via send_stop_job_command (SIGINT ans Worker-Horse), ermittelt ueber StartedJobRegistry. run_ids=None deckt den 'Alle loeschen'-Fall ab.
  - Race-sicher: Jobs, die zwischen Registry-Abfrage und Stop bereits enden, werden uebersprungen.

### Files
- services/api/routes/api_backtest.py



## [1.17.10] - 18.06.2026

### Changed
- Indicator-Config-Liste: Iteration-Spalte zeigt jetzt zusätzlich die Versionsnummer und ist anklickbar (öffnet die Iteration im Bearbeitungsmodus in neuem Tab)
  - Spalte rendert Versionsnummer plus Name (z.B. '42 — Crossover + AssetDD + bar1-Exit')
  - Klick auf das Iteration-Badge öffnet /config/strategy-concepts/{cid}/iterations/{iid}/edit in neuem Tab
  - API: neues additives Feld strategy_iteration_number (Integer version) in IndicatorConfigOut; iteration_map traegt nun {version, version_name}
  - strategy_iteration_version (Name-Fallback) unveraendert — backtest/start.html bleibt kompatibel

### Files
- services/api/routes/api_config.py
- services/frontend/templates/config/indicator_configs.html



## [1.17.9] - 18.06.2026

### Added
- Grundausstattung (Stammdaten-Seed) fuer Neuinstallationen: alle Backtest-Configs und Testsets kommen automatisch ueber eine Alembic-Daten-Migration in jede frische DB
  - Neue Alembic-Migration 0006_seed_baseline_data laedt die Grundausstattung (alle backtest_configs + testsets) am Ende der Schema-Kette - bewusst nicht in der Baseline 0001, da die Daten zum finalen Schema-Stand passen muessen (z.B. Spalte is_favorite aus 0005)
  - Idempotent: fuellt nur leere Tabellen, bestehende DBs ueberspringen den Insert sichtbar (kein PK-Konflikt)
  - Neues Skript seed/export_baseline.py regeneriert das Daten-SQL via pg_dump --data-only --column-inserts und bereinigt pg_dump-Eigenheiten, die op.execute brechen (\restrict/\unrestrict, set_config('search_path'))
  - Abgrenzung zum privaten Voll-Seed (export_seed.py/seed.dump, gitignoriert): die Grundausstattung ist neutral und eingecheckt, ohne private Strategien/Runs/Leaderboard
  - Verifiziert: frische DB via alembic upgrade head laedt 896 Configs + 16 Testsets inkl. korrekter Sequences; befuellte DB ueberspringt sauber
  - Dokumentiert in CLAUDE.md (Abschnitt Grundausstattung)

### Files
- alembic/versions/0006_seed_baseline_data.py
- alembic/versions/_sql/0006_baseline_data.sql
- seed/export_baseline.py
- CLAUDE.md



## [1.17.8] - 18.06.2026

### Added
- TestSet-Liste: Klick auf das Configs-Badge öffnet ein Modal mit den enthaltenen Backtest-Configs
  - Badge in der Spalte Anzahl Configs ist jetzt ein klickbarer Button
  - Modal zeigt pro Config eine Zeile mit ID, Name, Symbol und Timeframe
  - Öffnen-Button je Zeile verlinkt /config/backtest/{id} und öffnet die Config in einem neuen Tab (target=_blank, rel=noopener)
  - Config-Stammdaten werden einmalig über /api/config/backtest geladen und gemappt

### Files
- services/frontend/templates/testsets/list.html



## [1.17.7] - 18.06.2026

### Added
- Ausgewählte Configs stehen in der TestSet-Maske beim Laden ganz oben
  - DataTables-Order-Plugin 'dom-checkbox' sortiert die Config-Tabelle nach Auswahl-Zustand (ausgewählte zuerst), dann nach Name
  - Sortierung greift beim Laden — beim Anklicken einzelner Checkboxen springen die Zeilen nicht
  - Klick auf die Header-Checkbox 'Alle auswählen' löst keine Spalten-Sortierung aus (stopPropagation)

### Files
- services/frontend/templates/testsets/detail.html



## [1.17.6] - 18.06.2026

### Added
- Timeframe-Filter-Dropdown in der TestSet-Config-Tabelle (Anlegen + Bearbeiten)
  - Dropdown zwischen 'Symbole in Beschreibung übernehmen' und dem Suchfeld filtert die Config-Tabelle nach Timeframe
  - Optionen serverseitig per Jinja aus all_configs gerendert (unique|sort) — unabhängig vom asynchronen DataTables-Init über language.url
  - Exakter Spalten-Match per Regex (^wert$), damit z.B. '1h' nicht '1d' trifft

### Files
- services/frontend/templates/testsets/detail.html



## [1.17.5] - 18.06.2026

### Changed
- TestSet-Anlegen nutzt die volle Bearbeiten-Maske statt des Modals
  - Neue Route GET /testsets/new rendert dasselbe detail.html-Formular wie /testsets/<id>, nur ohne vorgeladene Daten (testset=None)
  - detail.html arbeitet jetzt im Create- und Edit-Modus: Speichern schaltet zwischen POST /api/testsets und PUT /api/testsets/<id>, Löschen-Button und 'Erstellt am' nur im Edit-Modus
  - Config-Auswahl im Create-Modus über dieselbe durchsuchbare Checkbox-Tabelle wie beim Bearbeiten (statt Multi-Select im Modal)
  - Modal 'Neues TestSet anlegen' samt JS aus list.html entfernt; Button ist jetzt ein Link auf /testsets/new
  - Config-Ladelogik in views_testsets.py in Helper _load_configs_data ausgelagert (DRY)

### Files
- services/api/routes/views_testsets.py
- services/frontend/templates/testsets/detail.html
- services/frontend/templates/testsets/list.html



## [1.17.4] - 18.06.2026

### Fixed
- TestSet-Löschen wird nicht mehr durch vorhandene Läufe blockiert
  - Harte Foreign-Key-Kopplung fk_testset_runs_testset_id entfernt — testset_runs.testset_id ist jetzt ein loser Integer-Verweis (wie LeaderboardEntry.testset_id)
  - Löschen eines TestSets blockiert nicht mehr und lässt die operativen TestSetRuns/BacktestRuns unangetastet
  - Modell models.py angepasst, Constraint in laufender DB per ALTER TABLE DROP CONSTRAINT entfernt

### Files
- user_data/utils/database/models.py



## [1.17.3] - 18.06.2026

### Fixed
- Chart-Playground: Trade-Marker (Long/Short-Positionen) werden im resampelten Anzeige-TF wieder angezeigt
  - Ursache: Der Chart resampled per Default auf 1D (visualTf), wenn der Basis-TF feiner ist. Die Roh-Trade-Zeiten liegen auf dem Basis-TF-Raster (z.B. 4h-Offsets) und damit zwischen den Tagesbars; timeToCoordinate() liefert dann null und der OrderRenderer ueberspringt jeden Trade (overlay.js:76) - alle Marker verschwanden.
  - cpApplyMarkerFilter() snappt die entry_time/exit_time der Marker jetzt auf das aktuelle Anzeige-Raster (Math.floor(time/targetSec)*targetSec, analog resampleCandles), ohne cpCurrentTrades zu mutieren.
  - applyVisualTf() zeichnet die Marker beim visuellen TF-Wechsel neu (cpApplyMarkerFilter), damit sie auf das neue Raster snappen statt auf dem alten zu verharren.
  - Verifiziert im Browser: 8/8 Trades erhalten wieder gueltige X-Koordinaten und werden gezeichnet (vorher 0).

### Files
- services/frontend/templates/chart_playground/index.html



## [1.17.2] - 18.06.2026

### Fixed
- Chart-Playground: Chart-Anzeige folgt jetzt dem OHLC-Datenfenster statt dem Rechenfenster
  - loadChart() laedt die angezeigten Candles jetzt ueber OHLC Start/End (cpOhlcStart/cpOhlcEnd) statt ueber Start/End (cpStart/cpEnd); Fallback auf Start/End, falls die OHLC-Felder leer sind.
  - Damit deckt sich die Chart-Anzeige mit dem Datenbereich, den die Backtest-Engine tatsaechlich laedt (loader.py nutzt ohlc_start/ohlc_end). Start/End bleiben das Rechenfenster fuer Signale/Trades (Date-Mask im Spec-Runner) - Schnelltest und voller Backtest waren bereits korrekt, nur die reine Anzeige wich ab.

### Files
- services/frontend/templates/chart_playground/index.html



## [1.17.1] - 18.06.2026

### Changed
- Backtest-Start-Formular: Config-Dropdown nach Favoriten gruppiert und Indicator-Config-Dropdown mit vorangestellter ID
  - Backtest-Config-Dropdown: Eintraege in zwei optgroups 'Favoriten' (oben) und 'Weitere Configs', jeweils alphabetisch; erste Favoriten-Config wird vorausgewaehlt
  - Indicator-Config-Dropdown (beide Tabs Einzel-Lauf und TestSet-Lauf): ID wird jetzt vorangestellt (ohne Raute), gefolgt von Name/Concept/Iteration
  - Backtest-Config-Tabelle: der zwischenzeitlich ergaenzte Tabellen-Trenner zwischen Favoriten und uebrigen Configs wurde wieder entfernt (gehoerte nicht in die Tabelle); Favoriten-Stern-Spalte und Favoriten-zuerst-Sortierung bleiben erhalten

### Files
- services/frontend/templates/backtest/start.html
- services/frontend/templates/config/backtest_configs.html



## [1.17.0] - 18.06.2026

### Changed
- Backtest-Configs: exklusives Default-Flag durch nicht-exklusiven Favoriten-Stern ersetzt (analog zu Konzepten/Iterationen/Results)
  - DB-Migration 0005: Spalte backtest_configs.is_default in is_favorite umbenannt (Bestand bleibt erhalten), Index idx_bc_default in idx_bc_favorite umbenannt
  - API: neuer Toggle-Endpoint POST /api/config/backtest/{id}/favorite; Eingabe-Schema ohne Flag, keine Exklusiv-Logik mehr; is_favorite wird nur ueber den Toggle gesetzt (Anlegen/Speichern fassen es nicht an)
  - Tabelle: Default-Spalte/Badge entfernt, Favoriten-Stern als erste Spalte; Favoriten zuerst, dann Trenner-Zeile 'Weitere Configs (alphabetisch)', danach uebrige Configs alphabetisch
  - Edit-Formular: Default-Checkbox entfernt (Markierung nur noch ueber den Tabellen-Stern)
  - Backtest-Start-Formular: Favoriten-Configs werden oben sortiert und die erste Favoriten-Config vorausgewaehlt (ersetzt die fruehere Default-Vorauswahl)
  - Tests: test_backtest_config_favorite.py (Toggle an/aus, 404, mehrere Favoriten moeglich, Speichern laesst Favorit unberuehrt)

### Files
- user_data/utils/database/models.py
- alembic/versions/0005_bc_favorite_flag.py
- services/api/routes/api_config.py
- services/api/routes/views_config.py
- services/frontend/templates/config/backtest_configs.html
- services/frontend/templates/config/backtest_config_edit.html
- services/frontend/templates/backtest/start.html
- tests/test_backtest_config_favorite.py



## [1.16.3] - 18.06.2026

### Fixed
- dtype-Ableitung bei arange-Parametern: Float-Werte erzwingen jetzt float64 statt faelschlich int64 zu behalten
  - buildParamValue (Chart-Playground und visueller Indikator-Config-Editor) leitete den dtype eines Wertebereichs ueber prevDtype ab — ein vorhandener int64 gewann immer, auch wenn der Nutzer danach z.B. 0.1 eintippte. Der Bereich blieb faelschlich int64.
  - Fix: dtype wird nur noch aus start und step bestimmt (die einzigen Werte, die bei arange ueber die Nachkommastelle entscheiden) — nicht mehr aus dem per .01 genudgeten, exklusiven stop. Float in start/step erzwingt float64; bei rein ganzzahligem start/step bleibt ein bewusst gesetztes float64 erhalten, sonst int64.
  - Damit kippt das Editieren eines Integer-Parameters (z.B. start aendern bei stop=18.01) nicht mehr faelschlich auf float64, und ein echter Float-Step ergibt korrekt float64.
  - Verifiziert am echten UI-Pfad (Config 1972): step=0.1 -> float64, Integer-Edit -> int64 bleibt, bewusstes float64 (below_pct) bleibt erhalten.

### Files
- services/frontend/templates/chart_playground/index.html
- services/frontend/templates/config/indicator_config_edit.html



## [1.16.2] - 18.06.2026

### Changed
- _stops_pos aus Indikator-Configs entfernt — Stops-Position ist reine Anzeige, gehoert nicht in die config_json
  - Server (_ensure_stops) injiziert kein _stops_pos mehr in die JSON-Ansicht; _sort_indicator_config gibt es nicht mehr aus (der _-Skip bleibt als Crash-Schutz).
  - Config-Seite (Visual-Editor): kein _stops_pos beim Speichern, kein Drag-Reorder mehr, Stops-Zeile sitzt fix am Ende. Begruendung: config_json ist jsonb, Postgres normalisiert die Key-Reihenfolge — Reihenfolge/Position sind keine persistierbaren Config-Eigenschaften.
  - Playground: 'als Indikator-Config speichern' schreibt _stops_pos nicht mehr in die config_json. Die Position bleibt nur im Playground-Setup (collectSetupConfig) erhalten.
  - _stops (Werte + Formate) bleiben unveraendert direkt im JSON sichtbar.

### Files
- services/api/routes/views_config.py
- services/frontend/templates/config/indicator_config_edit.html
- services/frontend/templates/chart_playground/index.html



## [1.16.1] - 18.06.2026

### Removed
- Verwirrenden _stops-Hinweistext unter dem JSON-Editor der Indikator-Config entfernt
  - Der erklaerende Block zur _stops-Struktur ist ueberfluessig, seit die Stops immer im JSON stehen und visuell editierbar sind.

### Files
- services/frontend/templates/config/indicator_config_edit.html



## [1.16.0] - 18.06.2026

### Added
- Indikator-Config-Seite: visueller Editor mit JSON/Visuell-Umschalter (Stops + Ranges wie im Playground)
  - Umschalter JSON<->Visuell im Karten-Header der Indikator-Config-Bearbeitung; JSON bleibt die kanonische Quelle, Speichern serialisiert den Visual-Stand verlustfrei zurueck.
  - Visueller Editor ist eine eigenstaendige, um Chart/Backtest getrimmte Kopie der Playground-Logik (Approach B): Indikator-Liste, Picker zum Hinzufuegen (Katalog /api/chart-playground/indicators), Entfernen, Drag-Reorder, editierbare Felder mit Einzelwert<->Wertebereich-Umschalter.
  - Stops als verschiebbare Zeile innerhalb der Indikator-Liste (tp/sl/tsl/td + Formate), sweep-faehig als Range; Position als Meta-Key _stops_pos.
  - Stops stehen jetzt direkt im JSON beim Laden (serverseitig Default-_stops + _stops_pos injiziert via _ensure_stops), nicht erst nach dem Umschalten; gilt fuer Edit- und Neu-Seite.
  - Fixed: _sort_indicator_config (Server + Frontend) behandelt _-praefixierte Meta-Keys nicht mehr als Indikator - behebt einen latenten TypeError-500 auf der Edit-Seite bei Configs mit _stops_pos und schuetzt _stops_pos vor dem JSON-formatieren-Button.

### Files
- services/frontend/templates/config/indicator_config_edit.html
- services/api/routes/views_config.py



## [1.15.18] - 18.06.2026

### Added
- Playground: Stops als verschiebbare Zeile im Indikator-Layout (Drag-Griff, Position persistiert)
  - Stops sind jetzt eine Drag-Zeile innerhalb der Indikator-Liste (optisch eine Indikator-Card mit Griff, Name + Felder), frei zwischen/über/unter die Indikatoren ziehbar — schliesst die optische Lücke (fehlendes Drag-Icon)
  - Heterogenes Key-basiertes Drag-Reorder (data-row-key = client_id bzw. __stops__): state.indicators und state.stopsPos werden nach dem Drop aus der DOM-Reihenfolge abgeleitet
  - Position persistiert als Meta-Key _stops_pos in indicators_config_json/config_json (Backend ignoriert _-Keys via _is_indicator_key); expliziter Integer-Wert statt Key-Position, da die DB-Spalte (Column(JSON)) die Schluesselreihenfolge nicht stabil haelt — per Round-Trip an Setup verifiziert
  - renderIndicatorList verschachtelt die Stops-Zeile an state.stopsPos; renderStops fuellt den Container in der Zeile (defensiver Null-Check); Load-Pfade (Setup + IndicatorConfig) klammern alle _-Meta-Keys aus und stellen stopsPos via stopsPosFromConfig wieder her
  - Feldgroessen unveraendert deckungsgleich mit den Indikator-Feldern; neuer .cp-stops-name-Stil fuer den Zeilen-Titel

### Files
- services/frontend/templates/chart_playground/index.html
- services/frontend/static/css/app.css



## [1.15.17] - 18.06.2026

### Fixed
- Playground: Stop-Felder pixelgenau an Indikator-Felder angeglichen (Größe wich ab)
  - Stop-Eingabeboxen waren groesser als die Indikator-Felder (Skalar 128x27 statt 58x21, Selects/Labels abweichend), weil die Stops-Card nur globale Form-Defaults erbte statt der kompakten .cp-ind-row-Regeln
  - Vier .cp-ind-row-Feldregeln fuer .cp-stops-fields gespiegelt: Label 0.7rem, form-control-sm/form-select-sm 110px, reduziertes -sm-Padding (gegen die globale .card .form-control-sm-Regel), cp-param-field 58px
  - Verifiziert an Setup 73 (2 Indikatoren): Skalar 58x21 / Range-Zelle 58 / Select 110x21 / Label 11.2px decken sich exakt mit den Indikator-Feldern

### Files
- services/frontend/static/css/app.css



## [1.15.16] - 18.06.2026

### Changed
- Playground: Stops als eigene Card in der Indikator-Spalte mit Range-Erweiterung (sweep-fähig wie Indikator-Parameter)
  - Stops als eigenständige Card in der linken Indikator-Konfigurations-Spalte, ueber den Aktions-Buttons (Kombinationen/Speichern) statt als formlose Sub-Sektion
  - Numerische Stops (tp_stop, sl_stop, tsl_th, tsl_stop, td_stop) per Umschalter zwischen Einzelwert und Wertebereich (start/stop/step) wandelbar — gleiche Range-Mechanik und Feldgroessen (58px) wie Indikator-Parameter (paramRangeFields/buildParamValue wiederverwendet)
  - toggleStopMode mit int/float-Erkennung (td_stop ganzzahlig step 1, Prozent-Stops step 0.1); Range-Dict {type:arange,...} landet im State und reist als indicators._stops mit
  - Formate (delta_format, time_delta_format) bleiben reine Selects ohne Range
  - calcIndCfgCombos zaehlt Stop-Ranges automatisch mit (config_json._stops); onSettingChanged invalidiert den Lite-Badge weiterhin per Delegation
  - CSS cp-stops-fields: identische Feldgroesse wie Indikator-Rows plus Umbruch in der schmalen Spalte

### Files
- services/frontend/templates/chart_playground/index.html
- services/frontend/static/css/app.css



## [1.15.15] - 18.06.2026

### Changed
- Playground: Stops als eigene Card mit Range-Erweiterung (sweep-fähig wie Indikator-Parameter)
  - Stops-Sektion aus der Indikator-Card herausgelöst und als eigenständige Card (analog Portfolio) zwischen Entry/Exit-Logic und Anzeige-Togglen platziert
  - Numerische Stops (tp_stop, sl_stop, tsl_th, tsl_stop, td_stop) per Umschalter zwischen Einzelwert und Wertebereich (start/stop/step) wandelbar — gleiche Range-Mechanik wie Indikator-Parameter (paramRangeFields/buildParamValue wiederverwendet)
  - toggleStopMode mit int/float-Erkennung (td_stop ganzzahlig, step 1; Prozent-Stops step 0.1); Range-Dict {type:arange,...} landet im State und reist als indicators._stops mit
  - Formate (delta_format, time_delta_format) bleiben reine Selects ohne Range
  - calcIndCfgCombos zählt Stop-Ranges automatisch mit (config_json._stops); onSettingChanged invalidiert den Lite-Badge weiterhin per Delegation
  - CSS: cp-stops-fields dimensioniert die Range-Felder wie in den Indikator-Rows und erlaubt Umbruch

### Files
- services/frontend/templates/chart_playground/index.html
- services/frontend/static/css/app.css



## [1.15.14] - 18.06.2026

### Changed
- Strategie-Entwicklungs-Doku auf das neue Stop-Modell synchronisiert: Stops und Formate gehören zur IndicatorConfig (_stops), nicht mehr zur BacktestConfig (Schritt 5, Abschluss Stop-Umbau)
  - app-guide.md, guide.md und _inject.md (Auto-Kontext-Hook-Quelle): Storage-Aussagen korrigiert, BacktestConfig-Portfolio auf init_cash/size/size_type/fees/stop_exit_price/stop_order_type reduziert, IndicatorConfig traegt jetzt Raster + _stops (sweep-faehig)
  - Mechanik-Aussagen (td_stop ist from_signals-Built-in, keine Regel) bewusst belassen
  - workflows/: funktional veraltete API-Payloads in multiparameter-lauf.md und setup-via-api.md korrigiert (Stops reisen als indicators._stops, run()-Wrapper und setup_to_run-Konverter nachgezogen); Storage-Aussagen in strategie-bereinigung.md, iteration.md, neue-strategie.md aktualisiert
  - Hinweis: Diese knowledge-Doku ist git-ignoriert (Whitelist) und daher nicht Teil des Commits



## [1.15.13] - 18.06.2026

### Changed
- Playground: Stops aus der Portfolio-Zeile in eine eigene Stops-Sektion der Indikatoren-Card verschoben; Stops reisen jetzt als indicators._stops (Schritt 4c/4d des Stop-Umbaus)
  - Frontend: neuer state.stops + Stops-Sektion (tp/sl/tsl/td + delta_format/time_delta_format) in der Indikatoren-Card; Portfolio-Card behaelt nur size/size_type/init_cash/fees/stop_exit_price/stop_order_type
  - Wire-Format: Stops werden als Sonderschluessel _stops im indicators-Dict gefuehrt (analog IndicatorConfig.config_json) — in Run-/Lite-Payload, Setup-Persistenz und beim Speichern als IndicatorConfig
  - Backend: _indicators_with_stops reicht req.indicators (inkl. _stops) durch statt aus portfolio zu spiegeln; from-result-/from-config-Endpoints liefern _stops in indicators_config_json; Lite-TP/SL-Linien lesen aus _stops
  - Verifiziert: End-to-End-Lite-Backtest greift (TP-Ratio 1.3, SL-Ratio 0.85), Gegenprobe ohne _stops aendert das Ergebnis; UI im Browser geprueft
  - Hinweis: Vor diesem Umbau gespeicherte Playground-Setups (Stops im portfolio) erhalten beim Laden die Stop-Defaults, da kein _stops vorhanden ist

### Files
- services/frontend/templates/chart_playground/index.html
- services/api/routes/api_chart_playground.py



## [1.15.12] - 18.06.2026

### Fixed
- Config-Snapshot erfasst skalare Stops jetzt aus _stops statt aus der BacktestConfig (Schritt 4c-pre, Vorbedingung für den Playground-Umbau)
  - _build_full_config_snapshot._stop() liest Stop-Werte nun aus indicators_config['_stops']: actual_params (Sweep) hat Vorrang, sonst der skalare _stops-Wert
  - Schliesst eine Luecke aus Schritt 3: skalare Stops, die nur in _stops stehen (nicht mehr im portfolio), gingen bisher im Snapshot verloren (wurden None)
  - Toten backtest_config-Rueckgriff fuer Stops entfernt; ungenutztes _STOP_KEYS entfernt
  - Verifiziert: Snapshot eines bestehenden Runs bleibt bit-genau gleich; Sweep-Vorrang und Range-Dict-Behandlung geprueft

### Files
- user_data/utils/database/repository.py



## [1.15.11] - 18.06.2026

### Fixed
- Backtest-Anzeige liest tp_stop/sl_stop pro Result aus dem Config-Snapshot statt run-weit aus portfolio (Schritt 4b des Stop-Umbaus)
  - Neue Helper-Funktion _result_stops(result) liest die per-Result aufgelösten Skalar-Stops aus full_config_snapshot_json['backtest_config']
  - Vier Stellen umgestellt: Run-Results, alle Results, DataTables-Endpoint und Trade-Chart (TP/SL-Preislinien)
  - Korrekt auch bei gesweepten Stops: jedes Result zeigt seinen konkreten Wert statt eines run-weiten Werts; kein Fallback auf die alte portfolio-Quelle
  - Verwaiste run-Queries und portfolio_config-Bloecke entfernt, die nur noch die Stops lieferten

### Files
- services/api/routes/api_backtest.py



## [1.15.10] - 18.06.2026

### Changed
- IndicatorConfig-Editor: _stops-Sonderblock in den JS-Helfern unterstützt (Schritt 4a des Stop-Umbaus)
  - Kombinationen-Zaehler bezieht Range-Stops (tp/sl/tsl/td) in die Summe ein und ignoriert die Format-Keys (delta_format/time_delta_format)
  - JSON-Formatierer sortiert _stops als Sonderblock ans Ende mit eigener innerer Reihenfolge; Range-Dicts werden wie Indikator-Params sortiert, unbekannte Keys bleiben erhalten
  - Titel-Generator weist _stops als 'Stops (...)' aus statt als Indikator-Label
  - Kurzer Hinweis zum _stops-Aufbau unter dem JSON-Editor ergaenzt

### Files
- services/frontend/templates/config/indicator_config_edit.html



## [1.15.9] - 18.06.2026

### Changed
- Stop-Umbau Schritt 3d: Die Stop-Format-Parameter delta_format/time_delta_format zu den Stops verlagert — sie leben jetzt als Meta-Felder in indicators_json['_stops'] statt in der BacktestConfig
  - delta_format (Prozent/Absolut fuer tp/sl/tsl) und time_delta_format (rows/Index fuer td) interpretieren die Stops und gehoeren damit zur IndicatorConfig; sie sitzen flach in '_stops' neben den Stop-Werten (nicht in STOP_PARAM_KEYS, da nicht sweepbar)
  - Spec-Runner liest die Formate aus '_stops' statt aus dem portfolio-Block (beide Engine-Pfade); _build_full_config_snapshot bezieht sie aus indicators_config['_stops']; from-result uebernimmt sie aus dem Snapshot in die eingefrorene Config
  - Alembic-Migration 0004 backfillt die zwei Format-Keys in '_stops' aller 228 Run-Snapshots (aus backtest_config_json['portfolio'], idempotent) und droppt die zwei Spalten aus backtest_configs; downgrade stellt die Spalten nullable wieder her
  - Format-Zeilen aus allen Run-Start-/Snapshot-/CRUD-/Anzeige-Pfaden und dem BacktestConfig-Editor entfernt (api_backtest, api_testset_runs, api_leaderboard, converters, api_config, views_config, repository_testsets, Frontend)
  - Verifiziert: keine Format-Spalten mehr, 228/228 Runs mit '_stops'-Formaten; Format wirkt aus '_stops' (percent 167.47 vs absolute 160.17); Recompute bit-genau (diff=0); volle Suite 282 passed (2 vorbestehende test_ticket22-Sortierfehler unabhaengig); test_full_config_snapshot + test_ticket43 chirurgisch an die neue '_stops'-Quelle angepasst
  - Playground liest Stops + Formate weiterhin aus dem Request-portfolio (kein Crash, .get mit Default) — Umstellung auf '_stops' folgt mit der Stop-UI in Schritt 4

### Files
- alembic/versions/0004_move_stop_formats_to_stops.py
- user_data/strategies/generic/spec_runner.py
- user_data/utils/database/repository.py
- user_data/utils/database/converters.py
- user_data/utils/database/models.py
- user_data/utils/database/repository_testsets.py
- services/api/routes/api_config.py
- services/api/routes/api_backtest.py
- services/api/routes/api_testset_runs.py
- services/api/routes/api_leaderboard.py
- services/api/routes/views_config.py
- services/frontend/templates/config/backtest_config_edit.html
- tests/test_full_config_snapshot.py
- tests/test_ticket43_from_result_save.py



## [1.15.8] - 18.06.2026

### Removed
- Stop-Umbau Schritt 3c: Die fuenf Stop-Spalten (tp/sl/tsl_th/tsl_stop/td) endgueltig aus backtest_configs entfernt — Stops leben jetzt ausschliesslich im Meta-Key indicators_json['_stops'] (Eigentuemer IndicatorConfig)
  - Alembic-Migration 0003 droppt die 5 Stop-Spalten aus backtest_configs und loescht inkompatible Alt-Leaderboard-Entries (ohne '_stops' im Indikator-Snapshot, nicht reproduzierbar) — 59 Entries entfernt, Results unberuehrt; idempotent, downgrade stellt die Spalten nullable wieder her
  - Alle ORM-Stop-Lesestellen entfernt: ORM-Modell (BacktestConfig), Run-Start-Portfolio-Builder (api_backtest, api_testset_runs), Converter (beide Richtungen), Pydantic-Modelle + CRUD (create/update/copy/from-result) und Anzeige (views_config)
  - Leaderboard zukunftsfest: Stop-Felder aus dem testset_snapshot-Configs-Builder raus; Snapshot-Rerun liest '_stops' jetzt aus dem Indikator-Snapshot statt aus dem portfolio-Block (kuenftige Entries tragen '_stops' automatisch aus testset_run.indicators_config_json)
  - Frontend: Stop-Inputs aus dem BacktestConfig-Editor und die TP/SL/TD-Spalten der Config-Liste entfernt (verwaiste JS-Helper bereinigt)
  - Verifiziert: backtest_configs ohne Stop-Spalten, leaderboard_entries 0, Runs 228 intakt; neuer Lauf mit '_stops' bit-genau zum Original (Run 2411 = 2402); Suite 282 gruen (2 vorbestehende test_ticket22-Sortierfehler unabhaengig); keine bestehenden Tests verbogen

### Files
- alembic/versions/0003_drop_stop_columns.py
- user_data/utils/database/models.py
- user_data/utils/database/converters.py
- user_data/utils/database/repository_testsets.py
- services/api/routes/api_config.py
- services/api/routes/api_backtest.py
- services/api/routes/api_testset_runs.py
- services/api/routes/api_leaderboard.py
- services/api/routes/views_config.py
- services/frontend/templates/config/backtest_config_edit.html
- services/frontend/templates/config/backtest_configs.html



## [1.15.7] - 18.06.2026

### Changed
- Stop-Umbau Schritt 3b: Stop-Lesepfad von der BacktestConfig auf den Meta-Key indicators_json['_stops'] umgebogen — die IndicatorConfig ist jetzt Eigentuemerin der Stops
  - Einzel-Lauf (api_backtest) und TestSet-Lauf (api_testset_runs): kein Ueberschreiben von '_stops' mehr aus dem portfolio-Block; '_stops' fliesst aus der gespeicherten IndicatorConfig (config_json). Fehlt '_stops', gibt es keine Stops (Spec-Runner liest tolerant via .get('_stops', {}))
  - Recompute und Full-Metrics (recompute.py): '_stops' wird aus dem Run-Snapshot (indicators_config_json, 3a-Backfill) re-injiziert statt aus dem portfolio-Block; bit-genaue Reproduktion verifiziert (Result 2703531 diff=0)
  - from-result (Indikator-Config aus Result einfrieren): uebernimmt die per-Result aufgeloesten Stops aus snapshot['backtest_config'] als '_stops' in die eingefrorene Config (Snapshot fuehrt Stops nur im backtest_config, nicht unter indicators)
  - Verwaiste stops_from_portfolio-Importe in api_backtest/api_testset_runs/recompute entfernt; Helfer bleibt fuer Playground (Schritt 4) und from-result erhalten
  - Playground-Pfad bewusst unangetastet (eigener '_stops'-Input folgt in Schritt 4); Leaderboard-Snapshot-Rerun unveraendert (liest aus eingefrorenem Entry-Snapshot, ueberlebt den spaeteren Spalten-Drop)
  - Suite gruen bis auf die 2 vorbestehenden test_ticket22-Sortierfehler; test_ticket43-Assertion auf den neuen '_stops'-Output erweitert

### Files
- services/api/recompute.py
- services/api/routes/api_backtest.py
- services/api/routes/api_testset_runs.py
- services/api/routes/api_config.py
- tests/test_ticket43_from_result_save.py



## [1.15.6] - 18.06.2026

### Added
- Stop-Umbau Schritt 3a: Einmal-Migration backfillt den Meta-Key '_stops' in bestehende Run-Snapshots (Vorbereitung der Stop-Eigentuemerschaft in der IndicatorConfig)
  - Neue Alembic-Migration 0002_backfill_stops_meta_key schreibt fuer jeden Run in backtest_runs den reservierten Meta-Key '_stops' in indicators_config_json, abgeleitet aus dem eigenen eingefrorenen backtest_config_json['portfolio'] (tp/sl/tsl_th/tsl_stop/td)
  - Reine Daten-Migration: keine Schema-Aenderung, kein Spalten-Drop, kein Lesepfad-Eingriff (folgen in Schritt 3b/3c); alle Run-/Result-IDs bleiben erhalten, doku-verlinkte Results bleiben reproduzierbar
  - Idempotent: '_stops' wird nur gesetzt, wo es noch nicht existiert; downgrade bewusst No-op (Backfill nicht eindeutig reversibel)
  - Abgeleitete '_stops'-Form bit-genau identisch zu stops_from_portfolio (gleiche STOP_PARAM_KEYS, fehlende Stops als None); Helfer-Logik inline gespiegelt, da dessen Modul vectorbtpro zieht
  - Verifiziert: 228/228 Runs gebackfillt, Stichproben-Werte = portfolio-Stops, Idempotenz-Lauf 0 Aenderungen, Suite 282 gruen (2 vorbestehende test_ticket22-Sortierfehler unabhaengig)

### Files
- alembic/versions/0002_backfill_stops_meta_key.py



## [1.15.5] - 18.06.2026

### Added
- Stops koennen als Sweep-Achsen durchgetestet werden: Listen-/Range-Werte in indicators_json['_stops'] werden als vbt.Param kartesisch mit dem Indikator-Raster gefahren; tsl_th+tsl_stop koppeln als zip-Paare (Schritt 2 des Stop-Umbaus)
  - build_stop_kwargs (spec_runner) uebersetzt _stops in from_signals-kwargs: Skalar bleibt Skalar, Liste/Range-Dict (arange-Format via convert_range_json_numpy_arrays) wird vbt.Param
  - TSL-Paar-Kopplung: wenn tsl_th UND tsl_stop gesweept sind, gleiches level=0 -> zip statt Kreuzprodukt (Laengen-Mismatch -> ValueError); unabhaengige Stops (tp/sl/td) kreuzen sich
  - Chunker zaehlt Stop-Kombis in n_combos ein (gekoppeltes TSL-Paar = eine Achse) und splittet ohne das Paar zu zerreissen; neue _split_along_stop_axis fuer reinen Stop-Sweep ohne variierende Indikatoren
  - Per-Result-Reproduktion: gesweepte Stops erscheinen als MultiIndex-Level in actual_params; _build_full_config_snapshot ueberschreibt im backtest_config-Block den konkreten Stop-Wert je Result (statt Range) -> bit-genaue Einzellauf-Reproduktion (verifiziert diff=0)
  - Nativer Pfad: Single-Combo-Indikator + Stop-Sweep funktioniert; Multi-Combo-Indikator + Stop-Sweep wird hart als ValueError abgewiesen (VBT broadcastet die 2D-signal_args nicht entlang der Stop-Param-Achse) statt still falsch zu rechnen
  - Verifiziert: Sweep erzeugt N Results mit korrekten Stop-Werten, TSL-Paar = 2 statt 4 Kombis, Chunker 6x4 -> 24 Results; volle Testsuite 282 passed (2 vorbestehende test_ticket22-Sortierfehler unabhaengig)

### Files
- user_data/strategies/generic/spec_runner.py
- user_data/strategies/generic/indicator_factory.py
- user_data/strategies/generic/rules_engine.py
- user_data/utils/database/repository.py



## [1.15.4] - 18.06.2026

### Changed
- Stop-Parameter (tp/sl/tsl/td) werden vom Spec-Runner aus dem reservierten Meta-Key indicators_json['_stops'] gelesen statt aus dem portfolio-Block der BacktestConfig (Schritt 1 des Stop-Umbaus, Skalar; Ranges/Sweep folgen)
  - Spec-Runner liest Stops in beiden Engine-Pfaden (Masken + nativ) aus indicators_json['_stops']; portfolio-Block-Stops werden nicht mehr ausgewertet
  - Reservierte Meta-Keys (Praefix '_') werden von jeder Indikator-Key-Iteration ausgeschlossen: _topological_order/build_indicators/split_indicators_json_chunks via neuem indicator_keys(), zusaetzlich _count_combinations und _build_resolved_config
  - Alle Run-Assembly- und Replay-Pfade legen _stops als Skalar-Dict aus der BacktestConfig ins indicators_json: Einzel-Run, Testset, Playground (full+lite), Leaderboard-Rerun, Recompute + Full-Metrics (Uebergangsbruecke, Wertequelle bleibt vorerst BacktestConfig)
  - _stops fliesst nur ueber indicators_config_json (Run-Ebene), nie in spec_json der Iteration -> spec_hash/Idempotenz unveraendert
  - Verifiziert: sl_stop wirkt in beiden Pfaden (Masken: -0.251->-0.200 / 29->35 Trades; nativ: -0.392->-0.230 / 8->30 Trades), portfolio-Block-Stops werden ignoriert, _stops nicht als Indikator gebaut

### Files
- user_data/strategies/generic/spec_runner.py
- user_data/strategies/generic/indicator_factory.py
- user_data/utils/database/repository.py
- services/api/routes/api_backtest.py
- services/api/routes/api_testset_runs.py
- services/api/routes/api_chart_playground.py
- services/api/routes/api_leaderboard.py
- services/api/recompute.py



## [1.15.3] - 18.06.2026

### Changed
- Iteration-Dropdowns auf Backtest-Start zeigen Versionsnummer + Beschreibung
  - Beide Tabs (Einzel-Lauf und TestSet-Lauf) zeigen in der Iteration-Auswahl jetzt die Versionsnummer (ID) gefolgt von der Beschreibung statt nur der Beschreibung
  - Format ohne Raute: '<Versionsnummer> — <Beschreibung>'
  - Sortierung absteigend nach Versionsnummer (war bereits vorhanden)

### Files
- services/frontend/templates/backtest/start.html



## [1.15.2] - 18.06.2026

### Changed
- Iterationen-Subtabellen auf der Strategie-Konzepte-Seite nach Version absteigend sortiert
  - Sekundärsortierung der Subtabelle von created_at (Spalte 8) auf Version (Spalte 2) absteigend umgestellt
  - Favoriten bleiben weiterhin oben, darunter wird nach Version desc sortiert
  - Re-Sort nach Favoriten-Toggle identisch angepasst

### Files
- services/frontend/templates/config/strategy_concepts.html



## [1.15.1] - 17.06.2026

### Removed
- Hartcodiertes Goal-Gate (goal_gate.py) wieder entfernt — Strategie-Bewertung erfolgt durch KI-Urteil mit Toleranz, nicht durch programmatisches Pass/Fail
  - goal_gate.py und tests/test_goal_gate.py gelöscht; der in 1.15.0 ergaenzte Gate-Block in build_leaderboard_entry zurückgebaut (configs_passed / filter_breached wieder None)
  - Richtungswechsel: Die Zielvorgabe (Mandat) lebt pro Strategie in der Vault-Konzept-Notiz als editierbarer yaml-Block, nicht als hartcodierte Schwelle im Code; die KI bewertet mit Toleranz und im Einzelfall
  - Begründung: feste Schwellen (z. B. 10 % DD) würden ein überproportional gewinnstarkes Ergebnis bei 11 % DD fälschlich aussortieren — genau das Urteil soll die KI treffen
  - Verifizierter Fakt bleibt erhalten (in AUTONOMOUS_LOOP.md dokumentiert): annualized_return ist geometrische CAGR, in der DB als Prozent gespeichert
  - repository_testsets.py inhaltlich auf den Stand vor 1.15.0 zurück; Leaderboard-Tests grün

### Files
- user_data/utils/database/repository_testsets.py



## [1.15.0] - 17.06.2026

### Added
- Goal-Gate: deterministische, regime-asymmetrische Mandat-Bewertung pro Testset-Config (erster Baustein des autonomen Strategie-Loops)
  - Neues Modul user_data/utils/database/goal_gate.py mit reinen Funktionen classify_regime / evaluate_config / aggregate_gate und GateThresholds-Dataclass (Default: 15 %/Monat, 10 % DD, DSR > 0, 75 % Robustheit)
  - Regime wird aus dem Testset-Namen abgeleitet (Bullenmarkt/Bärenmarkt/OoS sowie Jahresbereiche 20/21, 22/23, 24-26 der Cross-Symbol-Testsets); benchmark_return_pct als Diagnose-Regime daneben
  - Pro-Config-Regel regime-asymmetrisch: Bär nur Kapitalerhalt (DD + DSR), Bull/OoS zusätzlich Rendite-Ziel; fehlende Pflicht-Metriken fallen sichtbar mit Begründung durch
  - Monats-Rendite via verifizierter CAGR-Umrechnung (1 + annualized_return/100)^(1/12) - 1; annualized_return ist geometrisch (VBT annualized_return_1d_nb) und in der DB als Prozent gespeichert
  - Aggregation füllt configs_passed / filter_breached im LeaderboardEntry (build_leaderboard_entry); Sweep-Sieger werden als Obergrenze (is_ceiling) gekennzeichnet und nie als echtes Bestanden gewertet
  - 38 Unit-Tests in tests/test_goal_gate.py; gegen echten VWMA-Bull-Testset-Run (281) gegengeprüft
  - Konzept-Doku AUTONOMOUS_LOOP.md: Verifikations-Notiz und Roadmap-Schritt 1 als implementiert markiert

### Files
- user_data/utils/database/goal_gate.py
- user_data/utils/database/repository_testsets.py
- tests/test_goal_gate.py
- documentation/knowledge/strategy-development/AUTONOMOUS_LOOP.md



## [1.14.5] - 17.06.2026

### Changed
- Repo für die öffentliche GitHub-Bereitstellung bereinigt: interne Pfade, Projektnamen und den privaten Obsidian-Vault-Namen aus allen getrackten Dateien entfernt bzw. über Umgebungsvariablen konfigurierbar gemacht
  - projekt.md: Verweis auf internes Begleitprojekt entfernt, Obsidian-Vault-Pfad und VBT-Pro-Versionsnummer generisch, tote Doku-Verweise (auf gitignorete Dateien) und Staging-Hinweis entfernt
  - obsidian_paths.py: hartkodierten Vault-Default-Pfad auf neutralen Wert (/obsidian_vault) gesetzt, weiterhin über OBSIDIAN_VAULT_PATH überschreibbar
  - Frontend: Vault-Name im Obsidian-Deep-Link über neue Env-Variable OBSIDIAN_VAULT_NAME konfigurierbar statt hartkodiert (Server-Injektion in views_config.py)
  - Diverse Code-Kommentare und Docstrings von internen Projekt-/Hostnamen befreit (result_chart.html, models.py, docker-compose-local.yml, worker_entry.py, build.sh, embedding.py)
  - .env.example: alle Secrets/Hosts als Platzhalter, neue Vault-Keys (OBSIDIAN_VAULT_PATH, OBSIDIAN_VAULT_NAME) ergänzt
  - documentation/knowledge: indicators.md und metrics-catalog.md für die öffentliche Doku freigegeben (übrige interne Doku bleibt gesperrt, Whitelist-Prinzip)
  - Tests an die neuen Default-Werte angepasst

### Files
- documentation/project/projekt.md
- services/api/utils/obsidian_paths.py
- services/api/routes/views_config.py
- services/frontend/templates/config/strategy_concepts.html
- services/frontend/templates/backtest/result_chart.html
- docker-compose-local.yml
- user_data/utils/database/models.py
- .env.example
- documentation/knowledge/.gitignore
- tests/test_ticket16.py



## [1.14.4] - 17.06.2026

### Changed
- README überarbeitet: Playground, Test-Sets sowie Strategien/Iterationen ausführlicher erklärt, KI-gestützten Workflow als Kernprodukt herausgestellt, Versionsnummer bei der Backtest-Engine entfernt
  - Einleitung um KI-gestützte Strategie-Entwicklung als eigentliches Produkt ergänzt (KI baut/testet/optimiert Strategien auf Anweisung)
  - Playground-Beschreibung um Performance-Größenordnung erweitert (ca. 30.000 Kombinationen über zwei Jahre in etwa 15 Minuten)
  - Test-Set als feste Symbol/Zeitraum-Kombination für reproduzierbare Vergleiche erklärt
  - Strategie (Konzept) vs. Iteration (versionierte, unveränderliche Umsetzung) erklärt
  - Tech-Stack: VectorBT-Pro-Versionsnummer entfernt, damit die README nicht bei jedem Engine-Update angepasst werden muss

### Files
- README.md



## [1.14.3] - 17.06.2026

### Added
- README.md und .env.example fuer das oeffentliche GitHub-Repository angelegt
  - README.md: deutsche GitHub-Landing-Page (Zweck, Funktionsumfang, Tech-Stack, Architektur-Skizze, Projektstruktur, Schnellstart) - verweist nur auf getrackte, sichtbare Dateien
  - .env.example: Vorlage mit allen Keys der .env, Secrets und Maschinen-Pfade durch Platzhalter ersetzt

### Files
- README.md
- .env.example



## [1.14.2] - 17.06.2026

### Fixed
- Chart-Playground: Sichtbarkeits-Toggle der Indikatoren verwirft nicht mehr den Schnellbacktest, Fit-Button leuchtet beim Laden, Display-Änderungen respektieren den visuellen TF
  - Sichtbarkeits-Schalter (.cp-ind-vis-group) vom delegierten invalidateLiteResult-Listener ausgenommen — Indikatoren ein-/ausblenden behält jetzt das Schnellbacktest-Ergebnis (Badge, Equity, Trade-Marker)
  - Equity-Overlay wird bereits im aktuell sichtbaren TF an den Chart gegeben (resampleLine), damit die rohen Basis-TF-Zeitpunkte die resampelte Candle-Zeitachse nicht remappen
  - Neuer cpFitChartDeferred-Helper (doppeltes requestAnimationFrame) fittet den Chart nach dem finalen Layout — beim Setup-/Result-/Chart-Laden steht der Chart jetzt garantiert auf Fit (1D + leuchtender Fit-Button)
  - runBacktestLite erhält fitAfter-Option: nur im Lade-Pfad wird gefittet, der manuelle Schnellbacktest behält den aktuellen Zoom
  - Neuer renderIndRespectingTf-Helper: Display-Änderungen (Farbe/Transparenz/Linienstärke/Linienstil/Plot-Typ/Sichtbarkeit) zeichnen den Indikator im aktiven visuellen TF resampled statt im Basis-TF

### Files
- services/frontend/templates/chart_playground/index.html



## [1.14.1] - 17.06.2026

### Removed
- Tote/maschinenspezifische Konfig aus dem Repo entfernt: ungenutzte Root-vbt_settings.toml, .mcp.json und documentation/tickets/ nicht mehr getrackt
  - Root-vbt_settings.toml ersatzlos gelöscht + Bind-Mount aus docker-compose-local.yml (und lokal staging) entfernt: im Container verifiziert ungenutzt (VBT_SETTINGS_PATH=None, keine Auto-Discovery -> cache_dir blieb VBT-Default, nicht der hardcodierte Pfad); der MCP-Server nutzt die separate .claude/scripts/vbt-mcp-settings.toml
  - .mcp.json und documentation/tickets/ aus dem Git-Index genommen und in .gitignore aufgenommen (maschinen-/prozesslokale Konfig; .gitignore selbst ist untracked aus der Public-Prep)
  - vbt-Container ohne den Mount sauber neu gestartet

### Files
- docker-compose-local.yml
- vbt_settings.toml



## [1.14.0] - 17.06.2026

### Changed
- OHLC-Datenverwaltung (/config/data): getrennte Buttons "Aktualisierung" und "Neu einlesen" pro Datei sowie lesbare Status-Labels
  - Aktualisierung: Update zieht jetzt ab dem VORLETZTEN Bar (statt ab dem letzten) bis now - der zuletzt gespeicherte, evtl. unvollständige Bar wird so durch den vollständigen ersetzt (Worker: update(start=index[-2], end=now), überschreibt last_index)
  - Neu einlesen: lädt die bestehenden Symbole der Datei komplett neu ab dem Startdatum aus dem Download-Formular bis now (bestehende Bars werden überschrieben) - nutzt den vorhandenen /data/download-Endpoint
  - Status-Labels auf Light-Varianten (bg-*-lt) umgestellt gemäß Design-Guide - solide bg-* erzeugten graue, unlesbare Schrift auf farbigem Grund
  - Verifiziert: Aktualisierung-Job läuft durch, 3 Symbole bis 14:00 fortgeschrieben, 0 Duplikate; Browser-Check: beide Buttons + lesbare Badges vorhanden

### Files
- services/api/worker_tasks.py
- services/frontend/templates/config/data_files.html



## [1.13.8] - 17.06.2026

### Changed
- OHLC-Jobs zeigen unter /config/data jetzt den tatsächlichen Datenbereich statt des relativen Platzhalters "now UTC"
  - Update-Worker schreibt nach erfolgreichem Lauf den echten Range zurück: ältester Start / jüngstes Ende über alle aktualisierten Symbole (job.start_date/end_date als ISO-Datum)
  - Damit zeigt die Job-Liste z.B. '01.01.2020 - 17.06.2026' statt leerem Start und 'now UTC'
  - Frontend (data_files.html): Range-Fallback greift jetzt auch bei nicht-parsebaren Enddaten (wie 'now UTC'), nicht nur bei leerem end_date - dann wird completed_at angezeigt
  - Verifiziert im Browser: Update-Job #6 zeigt vollständigen Range 01.01.2020 - 17.06.2026

### Files
- services/api/worker_tasks.py
- services/frontend/templates/config/data_files.html



## [1.13.7] - 17.06.2026

### Fixed
- OHLC-Update-Job (Aktualisieren-Button unter /config/data) schlug bei Multi-Symbol-Dateien fehl mit "Number of symbols must be equal to the number of matched paths"
  - Ursache: from_hdf wurde mit Default match_paths=True aufgerufen - VBT zählt dann jeden HDF-Key als eigenen Pfad, sodass die einzelne symbols-Angabe nie zur Anzahl gematchter Pfade passt
  - Fix: Symbol als erstes Argument + match_paths=False (identisch zur bewährten Signatur in user_data/utils/ohlc/loader.py)
  - Vorbestehender Bug, unabhängig vom OHLC-Daten-Umzug (an der verschobenen Datei verifiziert)
  - Verifiziert: Update-Job binance/1h läuft durch - 'Update abgeschlossen für 3 Symbole'

### Files
- services/api/worker_tasks.py



## [1.13.6] - 17.06.2026

### Changed
- OHLC-HDF5-Daten von user_data/ohlc_data/ nach data/ohlc_data/ verschoben (Konsolidierung mit den übrigen data/-Verzeichnissen)
  - Config.DATA_PATH nutzt jetzt den Projekt-Root (_project_root) und zeigt auf data/ohlc_data/
  - Bind-Mounts ./data/ohlc_data in allen drei Compose-Dateien ergänzt (App + worker-base-Anchor + vbt-Container)
  - Hardcodierte Pfade in api_chart_playground.py und api_backtest.py auf /data/ohlc_data/ umgestellt
  - Obsolete .gitignore-Zeile user_data/ohlc_data/ entfernt (greift jetzt via /data/*)
  - data/README.md und project-structure.md nachgezogen
  - Verifiziert: Stack neu erstellt, App-Container sieht Dateien unter /app/data/ohlc_data, /chart-playground/sources liefert alle Quellen

### Files
- user_data/config.py
- services/api/routes/api_chart_playground.py
- services/api/routes/api_backtest.py
- docker-compose-local.yml
- docker-compose-staging.yml
- docker-compose.yml
- .gitignore
- data/README.md
- documentation/knowledge/project-structure.md



## [1.13.5] - 17.06.2026

### Changed
- Alembic-Migrationen erneut zu einer einzigen Baseline 0001_baseline_squash zusammengefasst (Stand wie bei Neuinstallation)
  - Die 15 historischen Migrationen (0001-0015) auf einen Initial-Stand gesquasht, der dem aktuellen Schema entspricht
  - Quelle: frische DB via alembic upgrade head der alten Kette aufgebaut, dann pg_dump -s --schema=public; Extensions timescaledb + vector sowie die TimescaleDB-Hypertables manuell ergaenzt (schema-beschraenkter Dump laesst globale Objekte weg)
  - Gegenprobe: Baseline-Schema byte-identisch zum Schema der vollen 0001-0015-Kette (Tabellen, Indizes, Constraints, Hypertables, Extensions)
  - Lokale DBs db_vbt_v1 (5560) und db_vbt_v1_test (5562) per alembic stamp --purge auf 0001_baseline_squash gesetzt - kein DDL, keine Daten angefasst
  - search_path-Preamble aus dem Dump entfernt und create_hypertable public-qualifiziert, damit op.execute die SQL fehlerfrei ausfuehrt

### Files
- alembic/versions/0001_baseline_squash.py
- alembic/versions/_sql/0001_baseline.sql



## [1.13.4] - 17.06.2026

### Fixed
- Deflated Sharpe Ratio (DSR) im Chunked-Lauf quer-schnittlich korrekt berechnet (Ticket 44)
  - DSR ist quer-schnittlich: var_sharpe und N hängen von ALLEN Kombis ab. Im gechunkten Lauf sah jeder Chunk bislang nur seine eigenen Spalten — Chunk 0 (N=2 statt 3) lieferte DSR ~0.456 statt 0.446 (+1.05e-2), Chunk 1 (N=1) lieferte NaN statt 0.446.
  - _run_chunked sammelt jetzt pro Chunk die DSR-Bausteine (nicht-annualisierte Sharpe, Skew, Kurtosis, T). Nach Konkatenation aller Chunks wird DSR global korrekt neu berechnet und in flat_metrics überschrieben. Exakte VBT-Formel 1:1 kopiert (ReturnsAccessor.deflated_sharpe_ratio).
  - test_chunked_matches_unchunked_size1_chunks: deflated_sharpe_ratio aus _SKIP_METRICS entfernt — der Test prüft jetzt alle 16 Felder bit-genau (|Diff| < 1e-9). Garantiert n_block==1-Chunk (length=[10]) und mehrspaltigen Chunk (length=[6,8]) in einem Lauf.
  - Numerischer Beleg: DSR Kombi (6,2): ungechunkt=0.44564347, gechunkt=0.44564347, |Diff|=5.55e-17; Kombi (10,2): |Diff|=5.55e-17. Vorher: Abweichung ~1.05e-2 (Chunk 0) bzw. NaN (Chunk 1).

### Files
- user_data/strategies/generic/spec_runner.py
- tests/test_combo_batching.py



## [1.13.3] - 17.06.2026

### Fixed
- Ticket 44: Schema-brechenden n_block==1-Workaround in _run_chunked durch ursachenbehebenden Fix ersetzt
  - FEHLER: Bei Chunks der Grösse 1 wurde _extract_chart_metrics statt _extract_partial_metrics aufgerufen — lieferte falsches Schema (28 Felder, 4 Pflichtspalten fehlend: annualized_return, annualized_volatility, downside_risk, deflated_sharpe_ratio; ~14 Fremdspalten extra)
  - URSACHE: _extract_partial_metrics schlug bei n_block==1 fehl weil VBT für Einzelspalten-Portfolios numpy-Skalare statt Arrays liefert — pd.DataFrame-Bau scheiterte ohne Index
  - FIX: _vals()-Hilfsfunktion in _extract_partial_metrics um np.atleast_1d() erweitert — wandelt VBT-Skalare in 1-Element-Arrays, für n_block>1 ist atleast_1d() ein No-Op
  - Workaround in _run_chunked entfernt: einheitlich _extract_partial_metrics für alle n_block-Werte, _extract_chart_metrics-Import entfernt
  - Nativer-Pfad-Befund: evaluate_rules_native gibt immer n_block==1 weil close_series eine 1D-Series ist (isinstance(close_series, pd.DataFrame) immer False → n_cols=1) — kein defekter Pfad, korrektes Verhalten
  - Neuer Test test_chunked_matches_unchunked_size1_chunks: Grid length=[6,8,10] x multiplier=[2], chunk_size=2 → Chunk [10] hat garantiert n_block==1; vergleicht alle 15 Metriken bit-genau (ohne deflated_sharpe_ratio wegen shape_2d[1]-Abhängigkeit)
  - Docstrings in test_native_path_chunked_no_crash aktualisiert: beschreibt jetzt atleast_1d-Fix statt veralteten chart_metrics-Workaround
  - 16 Tests grün (60s)

### Files
- user_data/utils/database/repository.py
- user_data/strategies/generic/spec_runner.py
- tests/test_combo_batching.py



## [1.13.2] - 17.06.2026

### Fixed
- Ticket 44: Schema-brechenden n_block==1-Workaround in _run_chunked entfernt; _extract_partial_metrics liefert nun in allen Fällen exakt 16 Felder
  - _vals()-Hilfsfunktion in _extract_partial_metrics verwendet np.atleast_1d(): VBT-Skalare bei Single-Combo-Portfolios werden in 1-Element-Arrays gewandelt, bevor pd.DataFrame gebaut wird
  - Workaround in _run_chunked entfernt: n_block==1-Zweig (der fälschlicherweise _extract_chart_metrics mit ~28 Feldern und metrics_level='chart' rief) durch einheitlichen _extract_partial_metrics-Aufruf ersetzt
  - Unbenutzter Import _extract_chart_metrics aus spec_runner._run_chunked entfernt
  - Neuer Test test_chunked_matches_unchunked_size1_chunks: Grid length=[6,8,10] x multiplier=[2] mit chunk_size=2 garantiert einen n_block==1-Chunk ([10]) und prüft bit-genaue Übereinstimmung aller 15 Metriken mit dem ungechunkten Lauf
  - Docstring test_native_path_chunked_no_crash aktualisiert: beschreibt jetzt den atleast_1d()-Bugfix statt den entfernten _extract_chart_metrics-Workaround

### Files
- user_data/utils/database/repository.py
- user_data/strategies/generic/spec_runner.py
- tests/test_combo_batching.py



## [1.13.1] - 16.06.2026

### Fixed
- Combo-Batching Lücken geschlossen: Single-Combo-Chunk-Bug in _run_chunked behoben, echte Backtest-Tests und Acceptance-Tests ergänzt
  - Lücke 1 (Spalten-Reihenfolge): Verifiziert, dass concat der Chunk-MultiIndexes das kartesische Produkt des ungechunkten Laufs exakt reproduziert — kein Fix nötig, Implementierung korrekt
  - Lücke 2 (Unit-Tests): TestRealBacktestChunkedVsUnchunked hinzugefügt mit 4 echten Backtest-Tests (kein Mocking der Backtest-Logik): test_chunked_matches_unchunked_all_metrics (20 Kombis, 5 Chunks, bit-genauer Vergleich), test_correct_number_of_chunks_created, test_single_combo_path_unaffected, test_native_path_chunked_no_crash
  - Bugfix: _run_chunked rief _extract_partial_metrics auf Single-Combo-Chunks auf — VBT liefert dort Skalare statt Arrays, was pd.DataFrame ohne Index und damit ValueError erzeugte. Fix: n_block==1 → _extract_chart_metrics statt _extract_partial_metrics
  - Nativer Pfad (evaluate_rules_native): produziert mit 1D-Close immer Single-Combo-Portfolio (n_cols=1), unabhängig von der Param-Grid-Größe — jeder Chunk ist ein n_block==1-Fall; Bugfix greift automatisch
  - Lücke 3 (Acceptance-Tests Docker): (a) 42-Kombi-Masken-Lauf gechunkt (chunk_size=10, 7 Chunks) vs. ungechunkt — alle Metriken bit-genau; (b) RSS-Messung belegt kein OOM bei 42 Kombis; (c) MultiIndex-Spalten korrekt über Chunk-Grenzen; (d) Nativer Pfad gechunkt kein Crash; (e) Single-Combo-Pfad liefert korrekte Trades/Orders
  - 15/15 Tests grün, alle temporären Skripte bereinigt

### Files
- user_data/strategies/generic/spec_runner.py
- tests/test_combo_batching.py



## [1.13.0] - 16.06.2026

### Added
- Ticket 44 — Combo-Batching im Spec-Runner: Multiparameter-Läufe mit >5k Kombis werden automatisch chunk-weise verarbeitet um OOM bei 36k+ Kombis zu vermeiden
  - indicator_factory.py: neue Funktion split_indicators_json_chunks(indicators_json, chunk_size=5000) teilt den Parameter-Grid entlang der ersten variierenden Achse in kartesische Sub-Produkte
  - spec_runner.py: run_spec_strategy aktiviert Chunked-Modus automatisch wenn n_combos > chunk_size (konfigurierbar via backtest_config_json['chunk_size']); neue Hilfsfunktion _run_chunked() verarbeitet Chunks sequenziell, extrahiert Metriken pro Block und gibt 'metrics_table' + 'columns' statt 'portfolios' zurück
  - repository.py: save_strategy_results erkennt das neue 'metrics_table'-Format und überspringt _extract_partial_metrics (bereits fertig extrahiert); Single-Combo-Pfad und Trades/Orders/Positions bleiben unverändert
  - Recompute- und Playground-Pfad unberührt: '_disable_chunked': True verhindert Chunking bei Single-Result-Läufen
  - tests/test_combo_batching.py: 11 Unit-Tests für split_indicators_json_chunks (Produktintegrität, Deep-Copy-Isolation, Grenzfälle)

### Files
- user_data/strategies/generic/indicator_factory.py
- user_data/strategies/generic/spec_runner.py
- user_data/utils/database/repository.py
- tests/test_combo_batching.py
- documentation/tickets/44-combo-batching-spec-runner.md



## [1.12.0] - 16.06.2026

### Added
- Ticket 44 — Combo-Batching im Spec-Runner: OOM-Schutz für grosse Multiparameter-Läufe
  - split_indicators_json_chunks() in indicator_factory.py: teilt indicators_json entlang der ersten variierenden Parameterachse in kartesische Sub-Grids
  - _run_chunked() in spec_runner.py: führt Chunks sequenziell aus, extrahiert Metriken pro Block und gibt freien Speicher via gc.collect() wieder frei
  - save_strategy_results() in repository.py: erkennt neues Return-Format (metrics_table + columns) aus gechunkten Läufen und überspringt _extract_partial_metrics
  - Chunking aktiviert sich automatisch wenn n_combos > chunk_size (Default 5000); Recompute-Pfad setzt '_disable_chunked': True zur Umgehung
  - 11 neue Unit-Tests in tests/test_combo_batching.py decken Chunking-Logik, Vollständigkeit des Produkt-Grids und Grenzfälle ab

### Files
- user_data/strategies/generic/indicator_factory.py
- user_data/strategies/generic/spec_runner.py
- user_data/utils/database/repository.py
- tests/test_combo_batching.py



## [1.11.16] - 16.06.2026

### Changed
- Results-Tabelle verschlankt: Aktions-Dropdown und kompakte Metrik-Header
  - Aktions-Buttons Chart, BC, IC, Setup und Löschen in ein Drei-Punkte-Menü pro Zeile zusammengefasst; nur der PG-Button bleibt eigenständig
  - Drei Aktions-Spalten zu einer reduziert — Tabelle passt dadurch ohne horizontalen Scroll in den Viewport
  - Menü liegt im DOM in der Zelle (bestehende Klick-Delegation greift weiter), wird aber per position:fixed positioniert, damit es nicht vom table-responsive-Container abgeschnitten wird; schließt bei Außenklick/Esc/Scroll/Redraw
  - Spalten-Header gekürzt: 'Win Rate %' zu 'WR%' und 'Max DD %' zu 'DD%', jeweils mit Info-Icon und Tooltip-Erklärung (analog PF)

### Files
- services/frontend/templates/backtest/results.html



## [1.11.15] - 16.06.2026

### Fixed
- Playground-Setups- und Testsets-Tabelle: Raute vor ID entfernt
  - ID-Spalte gibt in beiden Tabellen die reine Zahl aus statt '#'+id — wie zuvor bei Backtest-Configs; korrigiert zugleich die numerische Sortierung

### Files
- services/frontend/templates/config/playground_setups.html
- services/frontend/templates/testsets/list.html



## [1.11.14] - 16.06.2026

### Fixed
- Backtest-Results-Tabelle: Raute vor Run-ID entfernt
  - Run-Spalte zeigt die ID jetzt als reine Zahl statt '#'+id

### Files
- services/frontend/templates/backtest/results.html



## [1.11.13] - 16.06.2026

### Fixed
- Backtest-Config-Tabelle: ID-Spalte sortierbar und ohne Raute
  - ID-Spalte gibt jetzt die reine Zahl aus statt '#'+id — die Raute hatte die numerische DataTables-Sortierung lexikalisch gebrochen (#1, #10, #2 ...)
  - Sortierung nach ID funktioniert dadurch wieder korrekt numerisch

### Files
- services/frontend/templates/config/backtest_configs.html



## [1.11.12] - 16.06.2026

### Changed
- Chart-Playground: Default-Linienstärke der Indikatoren von 2 auf 1 Pixel gesenkt
  - Indikatoren ohne explizit gesetzte Linienstaerke werden jetzt mit 1 px statt 2 px gezeichnet
  - Default an allen fuenf Stellen angepasst: Card-Select, Slider-Fallback, Chart-Render, Persistenz und Laden von Setups
  - Die fixe 2-px-Equity-Linie der Result-Seite (overlay.js) bleibt unveraendert

### Files
- services/frontend/templates/chart_playground/index.html



## [1.11.11] - 16.06.2026

### Changed
- Chart-Playground: Indikator-Sichtbarkeits-Switch in die obere Card-Zeile verschoben
  - Der Switch zum Ein-/Ausblenden eines Indikators sitzt jetzt direkt unter dem Farbstrich in der oberen Card-Zeile - kein Aufklappen der erweiterten Optionen mehr noetig
  - Aus dem aufklappbaren Block 'Anzeige' entfernt (kein Doppel-Eintrag); Farbe/Transparenz/Linienstaerke/Linienstil/Typ/Loeschen bleiben unten
  - Neue CSS-Klasse .cp-ind-vis-group (Farbstrich oben, Switch darunter, vertikal zentriert)

### Files
- services/frontend/templates/chart_playground/index.html
- services/frontend/static/css/app.css



## [1.11.10] - 16.06.2026

### Fixed
- Chart-Playground: Misch-URL aus resultid und setupid wird unterbunden und kanonisch umgeleitet
  - Laden-Button entfernt resultid, bevor setupid gesetzt wird — kein Misch-URL-Zustand beim Setup-Laden aus einem geladenen Result
  - On-Load-Guard: URLs mit beiden Parametern werden vor jedem Laden per location.replace auf den persistenten Setup-Zustand (?setupid=) umgeleitet; resultid wird verworfen
  - Behebt das stille Doppel-Laden, bei dem zuerst das Setup angewandt und danach von der flüchtigen Result-Config überschrieben wurde

### Files
- services/frontend/templates/chart_playground/index.html



## [1.11.9] - 16.06.2026

### Changed
- Chart-Playground: Fit-Button ist jetzt ein echter Zustand statt 300-ms-Blinken — leuchtet beim Laden mit 1D und bleibt aktiv, solange die Ansicht alles zeigt
  - Neue Funktion cpUpdateFitButtonState() koppelt den Fit-Button-Zustand an den sichtbaren Bereich: aktiv solange der sichtbare Logical-Range (nahezu) die kompletten Candle-Daten abdeckt
  - Abonniert via subscribeVisibleLogicalRangeChange im createMainChart() — erlischt automatisch bei Zoom/Scroll, leuchtet wieder bei Fit/TF-Wechsel/Laden
  - Fit-Button-Klick fittet und setzt den Zustand persistent (kein setTimeout-Flash mehr)
  - Beim Chart-Laden leuchten damit 1D und Fit gemeinsam

### Files
- services/frontend/templates/chart_playground/index.html



## [1.11.8] - 16.06.2026

### Changed
- Chart-Playground: Beim Laden eines Charts standardmäßig Anzeige-Timeframe 1D aktivieren und auf Fit zoomen
  - Neue Funktion setDefaultVisualTf() setzt visualTf beim Chart-Laden auf 1d, sofern der Basis-TF feiner als 1D ist; bei Basis-TF >= 1D bleibt der Basis-TF aktiv
  - loadChart() resampled die Candles direkt auf den Default-Anzeige-TF, setzt timeVisible passend und fittet den Sichtbereich
  - Greift fuer alle Lade-Pfade (Setup-URL, Result-URL, Laden-Button), da alle ueber loadChart() laufen

### Files
- services/frontend/templates/chart_playground/index.html



## [1.11.7] - 16.06.2026

### Fixed
- Playground: Indikator-Werte werden beim visuellen Timeframe-Wechsel vollständig resampled (Subplots + Equity)
  - Subplot-Indikatoren (z.B. talib:ADX, custom:dwsAssetDD) blieben nach Klick auf einen TF-Button (z.B. 1D) leer. Ursache 1: Die Sync-Handler der Subplot-Charts wurden beim Neuzeichnen nie abgemeldet — tote Handler feuerten auf bereits zerstoerte Charts und warfen 'Object is disposed', was den Sichtbereich-Sync der lebenden Subplots abbrach. Behoben durch Speichern und Abmelden der Handler-Referenz in removeIndFromChart.
  - Ursache 2: Die Subplot-Charts wurden ueber den logischen Bar-Index synchronisiert. Da Indikator-Serien durch Warmup-Trim weniger Bars haben als die Candles, zeigte der Index-Sync ins Leere. Umgestellt auf zeit-basierten Sync (subscribeVisibleTimeRangeChange/setVisibleRange) plus initialem Sync beim Anlegen.
  - Equity-Kurve wurde beim visuellen TF-Wechsel nicht mit-resampled und blieb im feineren Basis-TF-Raster (4h auf 1D-Chart), was die Zeitachse verfaelschte. Rohe Equity-Punkte werden nun aufbewahrt und in applyVisualTf per resampleLine auf den aktuellen TF verdichtet.
  - Verifiziert im Browser an Result 2901988 (LINKUSDT 4h, Wechsel 4h<->1D): Candles, beide EMAs, Equity und beide Subplots resampeln konsistent, keine Konsolen-Fehler.

### Files
- services/frontend/templates/chart_playground/index.html



## [1.11.6] - 16.06.2026

### Added
- Konzept-Filter: Option (ohne Konzept) fuer Results ohne zugeordnete Iteration
  - Konzept-Dropdown bietet die Option (ohne Konzept) mit Sonderwert 'none', wenn solche Results existieren (Flag has_unassigned aus /filters)
  - Datatable filtert bei concept_id=none auf BacktestRun.iteration_id IS NULL
  - Iterations-Dropdown bleibt bei dieser Auswahl leer (kein Iteration hat dieses Konzept)

### Files
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/results.html



## [1.11.5] - 16.06.2026

### Changed
- Iteration in Results zeigt Version statt PK-ID, ohne Raute, Dropdown nach Version absteigend
  - Iterations-Anzeige (Dropdown + Tabellenspalte) nutzt die konzept-interne Version statt der globalen PK-ID; Raute entfernt; optionaler version_name dahinter
  - Dropdown-Reihenfolge nach Version absteigend; Dropdown-Value bleibt die iteration_id (Filter-Key)
  - dt-Response: iteration_version ist jetzt die Integer-Version, iteration_name separat; ungenutztes iteration_id entfernt

### Files
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/results.html



## [1.11.4] - 16.06.2026

### Changed
- Results-Tabelle: Strategie-Spalte in Konzept + Iteration aufgeteilt, Favorit-Spalten schmaler
  - Tabellenspalte Strategie in zwei Spalten Konzept und Iteration getrennt (analog zu den Filtern)
  - Iterations-Spalte zeigt die Iterations-ID (#<id> <name>); Response liefert dafuer iteration_id mit
  - Sortierung: Konzept nach Concept-Name, Iteration nach numerischer Version; Spalten-Index-Mapping (_DT_COLUMNS) um die neue Spalte verschoben
  - Favorit- und Doku-Favorit-Spalte schmaler: Stern-Icon 18->16px, Zell-Padding px-1

### Files
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/results.html



## [1.11.3] - 16.06.2026

### Changed
- Iterations-Filter zeigt die Iterations-ID im Label an
  - Label-Format im Iterations-Dropdown: "#<id> <version_name|vN>" statt nur des Namens

### Files
- services/api/routes/api_backtest.py



## [1.11.2] - 16.06.2026

### Changed
- Results-Filter: Strategie-Dropdown in getrennte Felder Konzept und Iteration aufgeteilt
  - Backend /api/backtest/filters liefert jetzt concepts (id, name) und iterations (id, concept_id, label) statt der flachen strategies-Liste — nur Konzepte/Iterationen mit vorhandenen Runs
  - Datatable-Endpoint /results/dt filtert per concept_id (StrategyConcept.id) bzw. iteration_id (BacktestRun.iteration_id) statt per strategy_name
  - Frontend: zwei Dropdowns Konzept + Iteration; die Iterations-Liste folgt abhaengig dem gewaehlten Konzept (change-Handler)
  - Page-Route /backtest/results: ungenutzten strategy-Query-Parameter entfernt
  - Hinweis: Legacy-Runs ohne Iterations-Verknuepfung haben kein Konzept und erscheinen nur ungefiltert

### Files
- services/api/routes/api_backtest.py
- services/api/routes/views_backtest.py
- services/frontend/templates/backtest/results.html



## [1.11.1] - 16.06.2026

### Removed
- Versehentlich committete leere Stray-Dateien aus Repo-Root entfernt
  - backtest_config- und delta_format (je 0 Byte) waren beim Ticket-43-Lauf durch einen fehlgeleiteten Shell-Redirect entstanden und mitcommittet worden
  - Reine Repo-Hygiene, kein Code-Effekt

### Files
- backtest_config-
- delta_format



## [1.11.0] - 16.06.2026

### Added
- Ticket 40 — Leaderboard-Eintrag allein reproduzierbar: spec_json-Einbettung und Rerun-Endpunkt
  - repository_testsets.py: spec_json aus StrategyIteration in strategy_snapshot_json eingebettet (ein Lookup, kein N+1, kein FK)
  - POST /api/leaderboard/{id}/rerun: Synchroner Rerun allein aus Snapshot-Daten ohne Zugriff auf BacktestConfig/StrategyIteration/BacktestResults
  - Bestandsschutz: Eintraege ohne spec_json werden mit HTTP 422 klar abgelehnt (kein Crash)
  - Rerun-Entry erbt spec_json aus Quell-Snapshot fuer Kettenreproduktion
  - 4 neue Unit-Tests in test_leaderboard_spec_json_snapshot.py
  - Abnahmetest bit-genau verifiziert: total_return_avg=-18.5768 nach Loeschung der operativen Daten reproduziert

### Files
- user_data/utils/database/repository_testsets.py
- services/api/routes/api_leaderboard.py
- tests/test_leaderboard_spec_json_snapshot.py
- documentation/tickets/40-leaderboard-eintrag-selbst-reproduzierbar.md



## [1.10.17] - 16.06.2026

### Added
- Ticket 42: Playground flüchtig aus Result laden (kein Setup anlegen)
  - Neuer GET-Endpunkt GET /api/chart-playground/result-config/{result_id}: liefert Playground-Config aus full_config_snapshot_json im gleichen Schema wie GET /setups/{id} — applySetupConfig() ohne Umbau wiederverwendbar
  - Indikatoren werden als Dict (Name → Flat-Spec) geliefert, nicht als Liste — Object.entries() im Frontend funktioniert korrekt
  - ui_state_json.selected_configs bleibt leer (flüchtiger Modus: Config-Referenzen existieren nach Cleanup ggf. nicht mehr)
  - Flüchtiger Lade-Pfad in init(): ?resultid=<id> ruft neuen Endpunkt per Fetch, kein ChartPlaygroundSetup-Eintrag wird angelegt
  - 'Im Playground öffnen' (PG)-Button neben Chart in results.html, run_detail.html und analyse.html ergänzt
  - Funktioniert auch wenn Run und Iteration des Results gelöscht sind (Daten kommen ausschließlich aus dem Result-Snapshot)
  - Result ohne vollständigen Snapshot → 422 mit klarer Meldung
  - 8 neue Unit-Tests in tests/test_ticket42_result_config.py (Schema, Dict-Indikatoren, leere selected_configs, kein Setup-Eintrag, 422/404-Ablehnung, Run-loses Result)

### Files
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html
- services/frontend/templates/backtest/results.html
- services/frontend/templates/backtest/run_detail.html
- services/frontend/templates/backtest/analyse.html
- tests/test_ticket42_result_config.py
- documentation/tickets/42-playground-fluechtig-aus-result-laden.md



## [1.10.16] - 16.06.2026

### Added
- Ticket 43 — "Aus Result speichern" auf Snapshot vereinheitlicht (alle drei Wege löschfest)
  - Neuer Endpunkt POST /api/config/backtest/from-result/{result_id}: legt BacktestConfig direkt aus full_config_snapshot_json an (kein Run/Iteration-Zugriff)
  - POST /api/config/indicator/from-result/{result_id}: auf Snapshot umgestellt, kein harter 422-Abbruch mehr bei fehlender Iteration
  - POST /api/chart-playground/setups/from-result/{result_id}: stark vereinfacht — kein topo_sort, keine Range-Auflösung, kein StrategyConcept-Query mehr
  - Alle drei Wege: fehlender oder unvollständiger Snapshot wird sichtbar mit 422 + klarer Meldung abgewiesen (kein stiller Fehlschlag)
  - Templates results.html, run_detail.html, analyse.html: neue Speichern-Spalte (BC / IC / Setup) pro Result-Zeile
  - 8 neue Unit-Tests (test_ticket43_from_result_save.py): alle Pfade inkl. gelöschtem Run/Iteration abgedeckt

### Files
- services/api/routes/api_config.py
- services/api/routes/api_chart_playground.py
- services/frontend/templates/backtest/results.html
- services/frontend/templates/backtest/run_detail.html
- services/frontend/templates/backtest/analyse.html
- tests/test_ticket43_from_result_save.py
- documentation/tickets/43-aus-result-speichern-vereinheitlichen.md



## [1.10.15] - 16.06.2026

### Changed
- Ticket 43: Aus-Result-Speichern auf vollständigen Config-Snapshot umgestellt
  - Neuer Endpunkt POST /api/config/backtest/from-result/{result_id}: legt BacktestConfig direkt aus full_config_snapshot_json['backtest_config'] an
  - create_indicator_config_from_result: auf Snapshot umgestellt — kein Zugriff mehr auf Run/Iteration/Concept; keine Range-Auflösung mehr nötig
  - create_setup_from_result: auf Snapshot umgestellt — kein topo_sort, keine Range-Auflösung, kein Run/Iteration/StrategyConcept-Zugriff mehr; stark vereinfacht
  - Fehlender Snapshot wird bei allen drei Endpunkten sichtbar mit 422 abgewiesen (kein stiller Fehlschlag)
  - results.html, run_detail.html, analyse.html: neue Speichern-Spalte mit BC/IC/Setup-Buttons pro Result-Zeile
  - 8 Unit-Tests (SQLite) für alle drei Endpunkte: Happy Path, 422 ohne Snapshot, 404 unbekannt, Robustheit ohne Run/Iteration

### Files
- services/api/routes/api_config.py
- services/api/routes/api_chart_playground.py
- services/frontend/templates/backtest/results.html
- services/frontend/templates/backtest/run_detail.html
- services/frontend/templates/backtest/analyse.html
- tests/test_ticket43_from_result_save.py
- user_data/utils/database/models.py



## [1.10.14] - 15.06.2026

### Added
- Ticket 43 — Speichern aus Result via full_config_snapshot_json (BC/IC/Setup)
  - Neuer Endpunkt POST /api/config/backtest/from-result/{result_id}: legt BacktestConfig aus Snapshot an
  - create_indicator_config_from_result: liest jetzt ausschliesslich aus full_config_snapshot_json['indicators'] — kein Run/Iteration-Zugriff mehr, keine Range-Auflösung
  - create_setup_from_result: liest jetzt ausschliesslich aus full_config_snapshot_json — kein Run/Iteration/StrategyConcept-Zugriff mehr
  - Alle drei Endpunkte: fehlender Snapshot wird sichtbar abgewiesen (422), kein stiller Fehlschlag
  - results.html: Speichern-Buttons BC/IC/Setup pro Zeile in DataTables (neuer Column-Eintrag + JS-Handler)
  - run_detail.html: Speichern-Buttons BC/IC/Setup analog zu results.html
  - analyse.html: Speichern-Buttons BC/IC/Setup in Top-Results-Tabelle
  - full_config_snapshot_json zu BacktestResult-Modell in Worktree ergänzt (war durch Alembic-Migration 0015 vorhanden, fehlte im Worktree-Stand)
  - 8 neue Unit-Tests in tests/test_ticket43_from_result_save.py — alle grün

### Files
- services/api/routes/api_config.py
- services/api/routes/api_chart_playground.py
- services/frontend/templates/backtest/results.html
- services/frontend/templates/backtest/run_detail.html
- services/frontend/templates/backtest/analyse.html
- user_data/utils/database/models.py
- tests/test_ticket43_from_result_save.py



## [1.10.13] - 15.06.2026

### Added
- Ticket 41 — BacktestResult trägt vollständigen Config-Snapshot (full_config_snapshot_json)
  - Neue nullable JSON-Spalte full_config_snapshot_json auf BacktestResult (Alembic-Migration 0015)
  - Snapshot enthält alle drei Reproduktions-Bausteine: backtest_config (Symbol, Exchange, Zeitraum, Sizing, alle Stops, delta_format/time_delta_format), indicators (aufgelöste Werte als Dict), rules {entry, exit}
  - Zentrale Snapshot-Erzeugung in _build_full_config_snapshot() und save_strategy_results() — alle Erzeugungspfade abgedeckt (Playground, Worker, Offline-Skripte)
  - Portfolio-Felder aus verschachtelter Playground-Struktur (portfolio-Key) und flacher BacktestConfig-Struktur (Worker) werden korrekt gelesen
  - Bestandsschutz: Feld nullable, Alt-Results bleiben als NULL erhalten, Konsumenten lesen defensiv
  - Docstring StrategyIteration.spec_json korrigiert: enthält indicators+rules, NICHT backtest_config
  - Abnahmetest bestätigt bit-genaue Reproduktion (total_return_pct 241.2235992360) aus Snapshot nach Löschung von Run und Sub-Daten

### Files
- user_data/utils/database/models.py
- user_data/utils/database/repository.py
- alembic/versions/0015_result_full_config_snapshot.py
- services/api/routes/api_chart_playground.py
- services/api/worker_tasks.py
- user_data/strategies/generic/spec_strategy_start.py
- user_data/strategies/vwma/vwma_v2/vwma_v2_start.py
- tests/test_full_config_snapshot.py
- documentation/tickets/41-result-vollstaendiger-config-snapshot.md



## [1.10.12] - 15.06.2026

### Changed
- Wissens-Vektorindex auf den ganzen Obsidian-Vault ausgeweitet (statt nur 30_Trading)
  - Worker mountet jetzt den kompletten Vault read-only (OBSIDIAN_VAULT_HOST_PATH:/obsidian_vault:ro), VAULT_ROOT auf /obsidian_vault umgestellt; Code-Defaults in indexer.py und worker_tasks.py nachgezogen
  - Indexer schliesst Nicht-Wissens-Verzeichnisse aus: .obsidian, .trash, 00_Inbox und Clippings (unsortiertes Staging) sowie alle Template-Verzeichnisse (Substring 'template')
  - Cleanup loescht jetzt auch Chunks neu ausgeschlossener, aber noch existierender Dateien - Aenderungen an der Ausschlussliste greifen rueckwirkend beim naechsten Reindex
  - Semantische Suchen koennen via path_prefix/tag auf Bereiche eingegrenzt werden (z.B. 30_Trading/); voller Reindex verifiziert: 116 Dateien, Inbox/Clippings nicht mehr im Index
  - 14 neue Unit-Tests fuer die Ausschlusslogik und den Cleanup ausgeschlossener Pfade

### Files
- docker-compose-local.yml
- services/vbt/knowledge/indexer.py
- services/api/worker_tasks.py
- services/api/tests/test_indexer_exclude.py



## [1.10.11] - 15.06.2026

### Removed
- Obsolete Einmal-Skripte aus scripts/ entfernt; project-structure.md auf aktuellen Hook-Stand nachgezogen
  - scripts/backfill_leaderboard_indicator_config.py, scripts/migrate_rules_to_blocks.py, scripts/sync_iter_run.py entfernt (Einmal-Migrations/Backfill-Skripte, Zweck erledigt, nirgends referenziert) — gemaess neuer Cleanup-Konvention
  - project-structure.md: hooks/-Zeile praezisiert (geloeschte Injektoren raus, strategy-context-injector als verbleibender benannt)
  - Handoff durchgefuehrt: HANDOFF.md HEAD + neue Session 'Doku-/Konventions-Umbau', Rotation auf 3 Sessions

### Files
- scripts/
- documentation/knowledge/project-structure.md
- documentation/project/HANDOFF.md



## [1.10.10] - 15.06.2026

### Added
- Cleanup-Konvention für Einmal-/Wegwerf-Dateien in CLAUDE.md verankert
  - Einmal-Operationen ohne neue Datei loesen (inline python3 -c, Pipe, Bash-Einzeiler)
  - Wegwerf-Dateien nur unter /tmp, nie im Projektbaum (besonders nicht in scripts/)
  - Vor Task-Abschluss pruefen und temporaere Dateien entfernen; im Repo bleiben nur dauerhaft nuetzliche Artefakte
  - Konvention (Selbstdisziplin), kein erzwingender Pre-Commit-Scan

### Files
- CLAUDE.md



## [1.10.9] - 15.06.2026

### Changed
- Handoff-Schritt 4 auf deterministischen git-Check umgestellt (project-structure.md-Drift)
  - Statt 'nach Gefuehl ob strukturell' jetzt git diff --name-status gegen den letzten Commit, der project-structure.md beruehrt hat
  - Strukturelle Signale klar definiert: A/D/R-Dateien, neuer Service/Router/Endpoint, neue Alembic-Migration, neue/entfernte Dependency; reine M-Edits zaehlen nicht
  - git ist die Quelle der Wahrheit, kein separater Drift-Ledger; nicht blockierend

### Files
- .claude/skills/handoff/SKILL.md



## [1.10.8] - 15.06.2026

### Changed
- ds-strategie-session-Skill von Nachschlage-Doku entkoppelt: Verweise auf die funktionsuebersicht entfernt
  - Skills referenzieren keine Referenz-/Nachschlage-Doku mehr; einzige lebende Quelle fuer Toolbox-Verben bleibt toolbox.py --help
  - ds-strategie-session-funktionsuebersicht.md (einmalige Abdeckungs-Analyse, durch Ticket 38 erledigt) bleibt als Nachschlage-Doku unter knowledge/strategy-development/skill/ liegen, wird aber von nichts Aktivem mehr referenziert
  - Historische Erwaehnungen in HANDOFF.md und Ticket 38 bewusst als Protokoll belassen

### Files
- .claude/skills/ds-strategie-session/SKILL.md



## [1.10.7] - 15.06.2026

### Changed
- Kontext-Injektion auf on-demand umgestellt: project-structure.md wird nicht mehr pauschal in Subagenten/Gemini injiziert
  - Hooks subagent-context-injector.sh und gemini_deep_injector.sh entfernt (Skripte gelöscht, PreToolUse-Eintrag fuer Task und mcp__gemini-coding aus settings.local.json raus)
  - Begruendung verifiziert: @-Mentions in hook-injizierten Task-Prompts expandieren nicht; Subagenten (ausser Explore/Plan) erben CLAUDE.md ohnehin; Gemini hat keinen Repo-Zugriff (nur attached_files, plus Request-Mechanismus get_gemini_requests)
  - CLAUDE.md: 'MUST read project-structure.md before any task' -> on-demand-Zeiger; Abschnitte zu Sub-Agent- und Gemini-Kontext an die neue Realitaet angepasst
  - Skills code-review/gemini_deep/gemini_quick von Zwangsload/Pflicht-Referenz auf on-demand-Anhang umgestellt; Denkfehler 'Gemini liest Dateien selbst' korrigiert
  - strategy-context-injector.sh bleibt (keyword-gated, kleiner Spickzettel)

### Files
- .claude/settings.local.json
- .claude/hooks/gemini_deep_injector.sh
- .claude/hooks/subagent-context-injector.sh
- CLAUDE.md
- .claude/skills/code-review/SKILL.md
- .claude/skills/gemini_deep/SKILL.md
- .claude/skills/gemini_quick/SKILL.md



## [1.10.6] - 15.06.2026

### Added
- Ticket-Status-Marker eingeführt: Pflichtzeile **Status:** offen|abgeschlossen direkt unter der H1 jedes Tickets
  - Konvention im CLAUDE.md-Ticket-Schema verankert: KI-interner Schnell-Scan-Marker, Single Source pro Ticket, kein zentraler Index (kein Drift), Übersicht via grep
  - Backfill aller 39 bestehenden Tickets (Status je Ticket belegt via Changelog-Suche/git/HANDOFF, nicht geraten) — Ergebnis: 39 abgeschlossen, 0 offen
  - Backfill von einem Sonnet-Subagenten durchgeführt

### Files
- CLAUDE.md
- documentation/tickets/



## [1.10.5] - 15.06.2026

### Changed
- Doku-Struktur nach Publikum getrennt: documentation/ in project/ (User) und knowledge/ (KI/Dev) aufgeteilt
  - project/ enthält nur noch User-Doku: projekt.md und HANDOFF.md
  - Neuer Ordner knowledge/ als KI/Dev-Wissensbasis: project-structure.md, indicators.md, metrics-catalog.md sowie strategy-development/ (per git mv, History erhalten)
  - Ordner reference/ aufgelöst (metrics-catalog.md nach knowledge/ verschoben)
  - Alle Pfad-Verweise nachgezogen: 3 Hooks (gemini_deep_injector, strategy-context-injector, subagent-context-injector), 5 Skills, CLAUDE.md, projekt.md, 4 Tickets und interne Links
  - Konzept-Doc-Regel in CLAUDE.md zeigt jetzt auf documentation/knowledge/ statt documentation/project/
  - user_data/_legacy/ bewusst unangetastet gelassen

### Files
- documentation/knowledge/
- documentation/project/
- CLAUDE.md
- .claude/hooks/gemini_deep_injector.sh
- .claude/hooks/strategy-context-injector.sh
- .claude/hooks/subagent-context-injector.sh



## [1.10.4] - 15.06.2026

### Fixed
- Doku-Audit P21-P30: veraltete und falsche Strategie-/Projekt-Doku gegen Code-Realitaet korrigiert
  - P21: Knowledge/Vault-Reindex-Feature in project-structure.md dokumentiert (services/vbt/knowledge/, Scheduler-Cron, vault_chunks/vault_reindex_runs, Flow-Diagramm)
  - P22: projekt.md-Abschnitt 'Multiparameter-Laeufe (Workflow)' auf die echte param_product-Mechanik umgeschrieben (Workflow-Vorlagen/-Runs existieren nicht)
  - P23: tote .env-Keys REDIS_SERVER/REDIS_PORT entfernt (Code liest REDIS_HOST/REDIS_INTERNAL_PORT, von Compose gesetzt)
  - P24: altes Versions-Schema v<MAJOR>.<MINOR> in guide.md + workflows durch version (Integer-ID) / version_name (Label ohne Nummer) ersetzt
  - P25: altes Rules-Format {logic,conditions} in neue-strategie/multiparameter-lauf/setup-via-api durch Block-DNF {blocks:[{conditions:[...]}]} ersetzt
  - P26: guide.md-Fehleinstufung korrigiert - backtest_configs/indicator_configs sind aktiv (Testset/Multiparameter), nicht totes Legacy
  - P28: vwma_dws-Pfadverweise in den lebenden Strategy-Docs auf vwma/ korrigiert (historische Tickets bewusst unangetastet)
  - P29: vergleichsmessung.md 'Bekannte Luecke' zu Ticket 36 als geloest markiert (build_leaderboard_entry_for_testset_run reicht indicator_config_id durch)
  - P30: geloeschtes Workflow-Feature aus app-guide.md/AGENT_ENTRY.md entfernt, Workflow-Anzahl auf neun korrigiert, strategie-bereinigung in den Index aufgenommen
  - Zusatzfund: 10 tote /api/workflow/*-Routen aus ds-strategie-session-funktionsuebersicht.md entfernt; logic-Kombinator-Beschreibung in project-structure.md auf Block-DNF korrigiert

### Files
- documentation/project/project-structure.md
- documentation/project/projekt.md
- documentation/strategy-development/guide.md
- documentation/strategy-development/AGENT_ENTRY.md
- documentation/strategy-development/app-guide.md
- documentation/strategy-development/workflows/neue-strategie.md
- documentation/strategy-development/workflows/multiparameter-lauf.md
- documentation/strategy-development/workflows/setup-via-api.md
- documentation/strategy-development/workflows/pine-reproduktion.md
- documentation/strategy-development/workflows/custom-indikator.md
- documentation/strategy-development/workflows/vergleichsmessung.md
- documentation/ds-strategie-session-funktionsuebersicht.md
- .env



## [1.10.3] - 15.06.2026

### Fixed
- vectorbtpro-MCP: Token-Regression behoben und VBT-Token eindeutig von Commit-Token getrennt (VBT_GITHUB_TOKEN)
  - Ursache: Beim Entfernen des hartkodierten GitHub-Tokens aus .mcp.json (-> ${GITHUB_TOKEN}) verlor der MCP-Server den Zugriff auf polakowo/vectorbt.pro. Der in .env hinterlegte fine-grained Token hat dort keinen Zugriff (404), wodurch knowledge/custom_assets.py mit 'GitHub token is required' (Zeile 219/294, os.environ.get('GITHUB_TOKEN')) abbrach.
  - Fix: Funktionierender Token zurueck in die gitignorierte .env; der Start-Wrapper reicht ihn per WSLENV an die Windows-python.exe durch. Verifiziert: Repo-/Release-Zugriff 200, echter mcp_server.search-Aufruf liefert Text-Ergebnisse (with_fallback=True greift, faellt ohne Embedding-Provider auf BM25 zurueck).
  - Rename zur Entkopplung: .env-Schluessel GITHUB_TOKEN -> VBT_GITHUB_TOKEN (VBT-spezifisch). Der Wrapper mappt ihn nur im Subprozess auf das von vectorbtpro hart erwartete GITHUB_TOKEN. docker-compose-local/staging Build-Arg-Quelle -> ${VBT_GITHUB_TOKEN}. Der Commit/Push-Token in documentation/git/.env bleibt voellig getrennt und unangetastet.
  - Dedizierte MCP-Settings: .claude/scripts/vbt-mcp-settings.toml mit Windows-cache_dir auf llm/, via VBT_SETTINGS_PATH (WSLENV /p) geladen — damit der Server die bereits vorhandenen Wissens-Assets nutzt statt neu in den Windows-User-Cache zu laden. Bewusst getrennt von der in die Linux-Container gemounteten ./vbt_settings.toml.
  - Hinweis: Fuer das Laden der toml und die lokale Suche wurden im Windows-venv die optionalen Knowledge-Dependencies nachgezogen (tomlkit, PyYAML, bm25s, tiktoken, lmdbm, markdown, beautifulsoup4, tabulate, markdownify). Semantische Suche ueber die mitgelieferten Embeddings braucht zusaetzlich einen Provider-Key (OpenAI/Gemini) und ist separat. Der aktive Token ist der alte klassische und sollte rotiert werden.

### Files
- .claude/scripts/vbt-mcp-start.sh
- .claude/scripts/vbt-mcp-settings.toml
- docker-compose-local.yml
- docker-compose-staging.yml



## [1.10.2] - 15.06.2026

### Fixed
- vectorbtpro-MCP-Server: GITHUB_TOKEN erreicht jetzt zuverlaessig die Windows-python.exe (Start-Wrapper statt .mcp.json-Substitution)
  - Neuer Start-Wrapper .claude/scripts/vbt-mcp-start.sh liest GITHUB_TOKEN aus der gitignorierten .env und reicht es per WSLENV an die Windows-python.exe durch — normale Shell-Exports kommen unter WSL nicht bei Win32-Prozessen an (empirisch verifiziert).
  - .mcp.json: command zeigt jetzt auf den Wrapper, env-Block leer. Damit entfaellt die nicht-funktionierende ${GITHUB_TOKEN}-Substitution (Claude Code laedt die Projekt-.env nicht) und die /doctor-Warnung 'Missing GITHUB_TOKEN'.
  - VBT_SETTINGS_PATH bewusst nicht mehr gesetzt: der bisherige Pfad zeigte auf eine nicht-existente Datei; sobald der korrekte Pfad ankaeme, scheiterte der Server am fehlenden tomlkit im venv. Bleibt ungesetzt, bis das separat geklaert ist — Import laeuft damit sauber wie bisher.
  - Verifiziert: Token-Laenge 93 kommt bei python.exe an; Server startet ueber den Wrapper sauber (exit 0, kein Traceback).

### Files
- .claude/scripts/vbt-mcp-start.sh
- .mcp.json



## [1.10.1] - 15.06.2026

### Fixed
- Git-Workflow-Doku an den tatsächlichen Auto-Commit-Mechanismus angeglichen
  - CLAUDE.md, documentation/git/README.md, .claude/skills/changelog/SKILL.md und project-structure.md beschrieben fälschlich einen manuellen commit.py-Flow
  - Klargestellt: der Hook commit-on-changelog.sh ruft bei jedem Changelog-Eintrag (add_entry) automatisch commit.py auf — Changelog schreiben = committet, kein manueller Schritt
  - Push bleibt manuell und nur auf ausdrücklichen User-Wunsch (push.py)

### Files
- CLAUDE.md
- documentation/git/README.md
- .claude/skills/changelog/SKILL.md
- documentation/project/project-structure.md



## [1.10.0] - 15.06.2026

### Removed
- Workflow-Feature (Templates und Runs) vollständig entfernt
  - Backend-Routen api_workflow.py und views_workflow.py gelöscht, Registrierung aus app.py entfernt
  - Models WorkflowTemplate, WorkflowRun, WorkflowRunItem sowie Spalte backtest_runs.workflow_run_id entfernt
  - Frontend-Templates unter templates/workflow/ gelöscht, Nav-Einträge in base.html und Workflow-Spalte in backtest/runs.html entfernt
  - Worker-Funktion _update_workflow_status samt Aufrufe und workflow_run_id-Parameter aus create_backtest_run entfernt
  - Workflow-Aufräum-Helfer (_nullify_workflow_items_*) und WorkflowTemplate-Mapping in der Indicator-Config-Liste entfernt
  - Alembic-Migration 0014 droppt workflow_templates/_runs/_run_items und die Spalte; auf Live- und Test-DB angewendet, Seed-Snapshot neu exportiert

### Files
- services/api/app.py
- services/api/routes/api_backtest.py
- services/api/routes/api_config.py
- services/api/worker_tasks.py
- services/api/schemas/__init__.py
- user_data/utils/database/models.py
- user_data/utils/database/repository.py
- services/frontend/templates/base.html
- services/frontend/templates/backtest/runs.html
- alembic/versions/0014_drop_workflow.py
- documentation/project/project-structure.md



## [1.9.19] - 15.06.2026

### Changed
- Custom-Indikatoren-Liste auf eine Quelle reduziert: doppelte Tabelle in guide.md durch Verweis auf indicators.md ersetzt
  - guide.md fuehrte eine eigene Custom-Indikator-Tabelle (5 Eintraege) parallel zur verbindlichen Referenz indicators.md Abschnitt 3 (6 Eintraege) — die Listen waren bereits auseinandergelaufen (dwsVolumeRatio fehlte in guide.md)
  - Gegen user_data/utils/indicators/custom.py geprueft: Code hat 6 Custom-Indikatoren, indicators.md ist die korrekte/vollstaendige Liste
  - guide.md behaelt nur noch Pfad + Namens-Konvention und verweist fuer den Katalog auf indicators.md — kuenftig nur eine Pflegestelle

### Files
- documentation/strategy-development/guide.md



## [1.9.18] - 15.06.2026

### Changed
- Skill ds-strategie-session entschlackt: Pfad-B-Befehlskatalog aus SKILL.md entfernt, Detail-Referenz auf zwei kanonische Quellen konsolidiert
  - SKILL.md von 288 auf 209 Zeilen gekuerzt — Pfad B (Toolbox) auf Konzept plus je ein Beispiel pro Verb-Typ reduziert
  - Dreifache Pflege beseitigt: vollstaendige Flag-/Verb-Listen leben jetzt nur noch in toolbox.py --help (Syntax) und documentation/ds-strategie-session-funktionsuebersicht.md (Route-Karte)
  - Frontmatter-description gestrafft, alle drei Trigger-Pfade (Session-Start / Toolbox / Session-Ende) erhalten
  - Pfad-A-Briefing-Block 'Verfuegbar' auf eine Zeile plus Verweis gekuerzt
  - Toolbox-Funktionalitaet unveraendert — reine Doku-Umschichtung, kein Skript-Code angefasst

### Files
- .claude/skills/ds-strategie-session/SKILL.md



## [1.9.17] - 15.06.2026

### Added
- Toolbox auf vollständige API-Abdeckung erweitert — die KI kann jetzt jede operative Route bedienen (ändern, löschen, alle Aktionen); plus neuer Backend-Endpoint zum Löschen eines Konzepts
  - Neue Verben fuer alle PUT (ändern), DELETE (löschen, inkl. bulk + alle-ausser-Favoriten), Toggles/Aktionen (favorite, vault-create, restart, remarks, analyse start/stop/reset, full-metrics, walk-forward) und die restlichen Listen/Reads
  - Generischer Direktbefehl: api <METHOD> <pfad> [--file body.json] erreicht jede (auch kuenftige) Route
  - Deklarative Routen-Tabelle (TABLE_VERBS) mit generischem Executor; Bodies aus Skalar-Flags via eigene Handler; alle 113 Routen abgedeckt (112 benannt + 1 generisch results/dt)
  - Neuer Backend-Endpoint DELETE /api/strategy/concepts/{id} mit Blocker-Pruefung (409) und optionalem force + delete_vault, plus repository delete_concept/force_delete_concept/get_concept_blockers (mirror des Iteration-Patterns)
  - Funktionsuebersicht umgebaut: Spalte KI-Bedarf entfernt, Skill-Spalte fuer jede Route gefuellt (benanntes Verb oder generischer api-Aufruf)
  - Smoke-Tests: concept-create -> concept-delete (neuer Endpoint), Blocker-409, Toggle, Table-Reads, generischer api — alle erfolgreich

### Files
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- services/api/routes/api_strategy.py
- user_data/utils/database/repository_strategies.py
- .claude/skills/ds-strategie-session/SKILL.md
- documentation/ds-strategie-session-funktionsuebersicht.md



## [1.9.16] - 15.06.2026

### Added
- Objekt-Toolbox (ds-strategie-session) um Bau-, Lauf- und Listen-Befehle erweitert — voller Strategie-Loop über die CLI bedienbar (Ticket 38)
  - Neue Listen-Reads: concept-list, iteration-list, backtest-config-list, indicator-config-list, result-list, testset-list, leaderboard-list, symbol-list, run-parameter-ranking, run-top-results
  - Neue Create-Verben: concept-create, iteration-create, indicator-config-create, backtest-config-create, testset-create (komplexe Payloads spec_json/config_json/Backtest-Body per --file als JSON-Datei)
  - Neue Start-Verben: backtest-run-start, testset-run-start (ID-basiert)
  - Alle Routen/Payloads vorab im Code (services/api/routes/api_*.py) verifiziert; kein stiller spec_json-Konverter, kein Fallback
  - Skript von brief_ids.py nach toolbox.py umbenannt (git mv), Referenzen in SKILL.md, Funktionsübersicht und PROCESS.md nachgezogen
  - Smoke-Tests gegen das laufende Backend (Read/Create/Start) erfolgreich, jeweils mit Cleanup

### Files
- .claude/skills/ds-strategie-session/scripts/toolbox.py
- .claude/skills/ds-strategie-session/SKILL.md
- documentation/ds-strategie-session-funktionsuebersicht.md
- documentation/strategy-development/PROCESS.md
- documentation/tickets/38-toolbox-bau-und-lauf-befehle.md



## [1.9.15] - 15.06.2026

### Changed
- Terminologie: englische Abkürzung „OoS"/„Out-of-Sample" durchgängig durch deutsche Projektbegriffe ersetzt (Ticket 39)
  - Ein Backtest-Lauf = Messung, der Gegentest eines Gewinners auf anderen Daten/Symbolen = Vergleichsmessung gegen ein Testset
  - Workflow-Datei workflows/oos-validierung.md nach workflows/vergleichsmessung.md umbenannt (git mv), alle Verweise nachgezogen (AGENT_ENTRY.md, SKILL.md, Ticket 36)
  - Begriffe in strategy-development/ und im Skill ds-strategie-session ersetzt: app-guide, guide, bewertungs-schema, AGENT_ENTRY, cross-symbol-lauf, neue-strategie, multiparameter-lauf, SKILL.md, brief_ids.py
  - Funktionsübersicht ds-strategie-session-funktionsuebersicht.md mit angeglichen
  - _legacy/ und Changelog-Historie bewusst unberührt (Read-Only-Snapshots)

### Files
- documentation/strategy-development/workflows/vergleichsmessung.md
- documentation/strategy-development/AGENT_ENTRY.md
- documentation/strategy-development/app-guide.md
- documentation/strategy-development/guide.md
- documentation/strategy-development/bewertungs-schema.md
- documentation/strategy-development/workflows/cross-symbol-lauf.md
- documentation/strategy-development/workflows/neue-strategie.md
- documentation/strategy-development/workflows/multiparameter-lauf.md
- .claude/skills/ds-strategie-session/SKILL.md
- .claude/skills/ds-strategie-session/scripts/brief_ids.py
- documentation/ds-strategie-session-funktionsuebersicht.md
- documentation/tickets/36-leaderboard-indicator-config-link.md



## [1.9.14] - 15.06.2026

### Changed
- Seed-Export schreibt jetzt datierte, versionierte Dumps
  - export_seed.py erzeugt seed/data/seed-YYYY-MM-DD.dump mit aktuellem Datum
  - seed.dump wird zusaetzlich als Pointer auf den zuletzt exportierten Stand aktualisiert
  - import_seed.py bleibt unveraendert und liest weiterhin seed.dump

### Files
- seed/export_seed.py



## [1.9.13] - 15.06.2026

### Changed
- Stern-Spalten beschriftet (F = Favorit, D = Doku-Favorit) und sortierbar gemacht
  - Header der Favoriten-Spalten in Results- und Strategie-Konzepte-Tabelle zeigen jetzt F (gelb) und D (rot) mit Tooltip statt leerer Zelle
  - Stern-Spalten in der Strategie-Konzepte-Child-Tabelle auf orderable:true gesetzt (Sortier-Logik war bereits vorhanden); Results-Stern-Spalten waren server-seitig schon sortierbar

### Files
- services/frontend/templates/backtest/results.html
- services/frontend/templates/config/strategy_concepts.html



## [1.9.12] - 15.06.2026

### Added
- Doku-Favoriten (roter Stern) als zweite, unabhängige Favoriten-Markierung mit eigenem Löschschutz
  - Neues Flag is_doc_favorite auf BacktestResult (Integer) und StrategyIteration (Boolean), Migration 0013_doc_favorite
  - Roter Stern direkt neben dem gelben in Results-Tabelle, Strategie-Konzepte-Child-Tabelle und Iteration-bearbeiten-Formular
  - Eigene Toggle-Endpoints POST /api/backtest/results/{id}/doc_favorite und POST /api/strategy/iterations/{id}/doc_favorite
  - Alle löschen (Results und Runs) schützt jetzt gelb UND rot markierte Einträge (Filter is_favorite==0 AND is_doc_favorite==0)
  - Hinweis-Kommentar in api_strategy.py: künftiger Iterations-Bulk-Delete muss beide Stern-Flags verschonen
  - DataTables-Sortier-Indizes nach der eingeschobenen Spalte korrigiert (Results und Konzepte-Child-Tabelle)

### Files
- user_data/utils/database/models.py
- alembic/versions/0013_doc_favorite.py
- services/api/routes/api_backtest.py
- services/api/routes/api_strategy.py
- services/api/routes/views_config.py
- services/frontend/templates/backtest/results.html
- services/frontend/templates/config/strategy_concepts.html
- services/frontend/templates/config/strategy_iteration_edit.html



## [1.9.11] - 14.06.2026

### Changed
- Versions-/Doku-Regelwerk: Stops und Portfolio-Einstellungen gehören zur BacktestConfig, nicht ins spec_json
  - spec_json einer Iteration enthält ausschließlich indicators und rules - maßgeblich ist die DB-Struktur
  - init_cash, size, fees und td/tp/sl/tsl liegen in der BacktestConfig; andere Stops sind ein anderer Run derselben Iteration, keine neue Iteration
  - Korrigiert die vorherige Formulierung 'Portfolio-Defaults sind Teil der Iteration' aus der 1.9.9-Doku
  - strategie-bereinigung.md Schritt 4 geschärft: Iterations-Vergleich nur über spec_json-Struktur (indicators + rules); Konsolidierung hängt Favoriten-Runs um, löscht ephemere Results

### Files
- documentation/strategy-development/_inject.md
- documentation/strategy-development/app-guide.md
- documentation/strategy-development/workflows/strategie-bereinigung.md



## [1.9.10] - 13.06.2026

### Fixed
- Obsidian-Link in der Strategie-Konzept-Maske zeigte das Label statt des Dokumentnamens
  - Die Obsidian-Spalte beschriftete den Link mit version_name (seit dessen Bereinigung z.B. 'Supertrend-Filter') statt mit dem eindeutigen Dokumentnamen
  - Zeigt jetzt <slug>-<version> (z.B. vwma-3), identisch zur verlinkten Datei im Pfad iterations/<version>/<slug>-<version>.md

### Files
- services/frontend/templates/config/strategy_concepts.html



## [1.9.9] - 13.06.2026

### Fixed
- Obsidian-Link der Iterations-Tabelle zeigte auf falschen Dateinamen
  - Der Frontend-Link baute den Vault-Pfad als iterations/<version>/<version>.md statt iterations/<version>/<slug>-<version>.md und zeigte dadurch ins Leere
  - Jetzt konsistent mit der Backend-Pfadberechnung (iteration_md_path); Modul-Docstring in obsidian_paths.py mitkorrigiert

### Files
- services/frontend/templates/config/strategy_concepts.html
- services/api/utils/obsidian_paths.py



## [1.9.8] - 13.06.2026

### Changed
- Strategie-Konzept-Maske: Iterations-Tabelle zeigt Version und Versionsname als getrennte Spalten
  - Neue Spalte Version zeigt das Integer-Feld version (zentriert, numerisch sortierbar, traegt den Detail-Link); zuvor stand unter der Ueberschrift Version faelschlich der Inhalt von version_name
  - Spalte Versionsname zeigt jetzt das Feld version_name getrennt an, linksbuendig erzwungen (text-start), sonst richtet DataTables rein-numerische Werte automatisch rechts aus
  - Kurzbeschreibung explizit linksbuendig
  - version_name wird HTML-escaped wie die Kurzbeschreibung

### Files
- services/frontend/templates/config/strategy_concepts.html



## [1.9.7] - 13.06.2026

### Fixed
- Playground: Kurzform-Indikator-Referenzen (indicator:&lt;name&gt; ohne Output) werden in der Rules-Validierung auf den ersten Output aufgelöst statt fälschlich rot als "Indikator deaktiviert" markiert

### Files
- services/frontend/templates/chart_playground/index.html



## [1.9.6] - 12.06.2026

### Changed
- Playground-Anzeige-Einstellungen überarbeitet: Einstellungen-Tab entfernt, Anzeige-Schalter in eine kopflose Card über Portfolio verschoben und um Equity/Long/Short erweitert
  - Einstellungen-Tab im Chart-Playground entfernt; der Candles-Toggle ist jetzt Teil einer kopflosen Card direkt über der Portfolio-Card im Strategie/Iteration-Tab
  - Neue Anzeige-Schalter: Equity anzeigen (blendet die Equity-Overlay-Serie ein/aus), Long-Positionen anzeigen und Short-Positionen anzeigen (filtern die Trade-Marker nach trade.direction)
  - Marker-Rendering in einen zentralen Helfer cpApplyMarkerFilter zusammengeführt (beide Lauf-Pfade + Master-Toggle); volle Trade-Liste in cpCurrentTrades als Filterquelle
  - Zustände der vier Schalter werden analog show_candles in ui_state_json persistiert
  - Fix: Der delegierte invalidateLiteResult-Listener auf #cp-tab-setup verwarf das Schnellbacktest-Ergebnis (Equity + Marker) auch bei reinen Anzeige-Änderungen; Controls in #cpDisplayToggles und .cp-ind-advanced-body (Indikator-Farbe/Transparenz/Linie/Sichtbarkeit/Plot-Typ) sind jetzt ausgenommen
  - Echte Backtest-Änderungen (Parameter, Regeln, Portfolio, Symbol/Timeframe) verwerfen das Ergebnis weiterhin

### Files
- services/frontend/templates/chart_playground/index.html



## [1.9.5] - 12.06.2026

### Fixed
- Chart-Playground: Geister-Serien auch bei Wechsel auf eine Iteration ohne Indikatoren entfernen
  - applyIndicators brach bei leerer Indikatoren-Liste vor dem Aufräumen ab, sodass Geister-Serien hängen blieben
  - pruneOrphanSeries wird jetzt auch im leeren Fall vor dem Early-Return aufgerufen und entfernt alle verbliebenen Serien

### Files
- services/frontend/templates/chart_playground/index.html



## [1.9.4] - 12.06.2026

### Fixed
- Chart-Playground: Geister-Indikatoren auf dem Chart nach Iterations-/Indikator-Config-Wechsel
  - Beim Ersetzen von state.indicators (Iterations- oder Indikator-Config-Wechsel) blieben Chart-Serien entfernter Indikatoren als Geister auf dem Chart, obwohl die Indikatoren-Box korrekt nur die aktuellen zeigte
  - Ursache: renderIndFromCache lief nur ueber die aktuellen state.indicators; Serien nicht mehr vorhandener client_ids wurden nie entfernt
  - Neue Funktion pruneOrphanSeries entfernt am Render-Chokepoint (applyIndicators) alle getrackten Serien, deren client_id nicht mehr in state.indicators steht
  - Wirkt automatisch beim Auto-Apply nach Config-Wechsel und beim manuellen Aktualisieren-Button

### Files
- services/frontend/templates/chart_playground/index.html



## [1.9.3] - 12.06.2026

### Changed
- Chart-Playground: Setup-Dropdown lädt nicht mehr automatisch — neuer "Laden"-Button
  - Auswahl im Setup-Dropdown setzt nur noch das Überschreib-Ziel für Speichern, statt das Setup automatisch zu laden und die laufende Playground-Arbeit zu überschreiben
  - Neuer Laden-Button neben dem Dropdown lädt das gewählte Setup bewusst (navigiert zu ?setupid=<id>)
  - Workflow jetzt möglich: im Playground arbeiten, im Dropdown das zu überschreibende Setup wählen, Speichern drücken

### Files
- services/frontend/templates/chart_playground/index.html



## [1.9.2] - 12.06.2026

### Added
- Chart-Playground: Button "Kombinationen berechnen" in der Indikatoren-Card
  - Neuer Button neben den Speichern-Buttons der Indikatoren-Card zeigt die Anzahl der Parameter-Kombinationen über alle Indikatoren
  - Gleiche Zähl-Logik wie auf der Indicator-Config-Seite: Range-Param ergibt ceil((stop-start)/step), deaktivierte Indikatoren werden übersprungen, Skalare zählen als 1
  - Quelle ist das serialisierte config_json (collectIndicatorConfigJson) — exakt der Save-Stand
  - Farbcodierung wie auf der Config-Seite: grün, ab 10.000 gelb, ab 50.000 rot; Tooltip listet die Kombinationen je Parameter

### Files
- services/frontend/templates/chart_playground/index.html



## [1.9.1] - 12.06.2026

### Added
- Chart-Playground: Umschalter pro Indikator-Parameter zwischen Einzelwert und Wertebereich
  - Inline-Button neben jedem numerischen Parameter in der Indikatoren-Card schaltet zwischen Einzelwert und start/stop/step-Wertebereich um
  - Einzelwert -> Wertebereich: aktueller Wert als start, step 1 (int) bzw. 0.1 (float), stop = start + step -> genau eine Kombination
  - Wertebereich -> Einzelwert: erster Wert (start) wird zum Skalar
  - Float-Rauschen beim Aufaddieren wird vermieden (1.1 + 0.1 -> 1.2)
  - Kein Umschalter bei Boolean- und String-Parametern (kein sinnvoller Wertebereich)

### Files
- services/frontend/templates/chart_playground/index.html
- services/frontend/static/css/app.css



## [1.9.0] - 12.06.2026

### Changed
- Entry/Exit-Regeln in disjunktiver Normalform (Block-Modell)
  - Regeln bestehen jetzt aus Blöcken: Bedingungen innerhalb eines Blocks UND-verknüpft, Blöcke untereinander ODER-verknüpft (DNF). Ersetzt die flache AND/OR-Logik und bildet jede boolesche Verknüpfung ab.
  - Rules-Engine auf Blocks umgestellt: Masken-Pfad (_evaluate_rule_group) und nativer Pfad für State-Exits (_eval_exit_blocks_nb via signal_func_nb) werten je Block UND und zwischen Blöcken ODER aus. Kein Alt-Format mehr zur Laufzeit.
  - Chart-Playground-Frontend: Block-UI mit + Entry-Block / + Exit-Block, + Bedingung je Block und ODER-Trenner; die AND/OR-Dropdowns wurden entfernt.
  - Verlustfreier Konverter (rules_migration.py) und Einmal-Skript (scripts/migrate_rules_to_blocks.py) heben Alt-Format {logic, conditions} auf {blocks}; bestehende Iterationen und Playground-Setups in der DB migriert, spec_hash neu berechnet.
  - Tests für Block-Semantik, DNF-Äquivalenz und Konverter ergänzt; nativer Pfad-Test auf Block-Format migriert.

### Files
- user_data/strategies/generic/rules_engine.py
- user_data/strategies/generic/rules_migration.py
- scripts/migrate_rules_to_blocks.py
- services/frontend/templates/chart_playground/index.html
- services/frontend/static/css/app.css
- tests/test_rules_engine_blocks.py
- tests/test_ticket35_native_state_exits.py



## [1.8.28] - 12.06.2026

### Changed
- Chart-Playground: umfangreiche UI-Überarbeitung (Indikator-Panel, Speichern, Setup-Laden per URL, Schnellbacktest-Verhalten) und OHLCV-Input-Korrektur
  - Indikator-Cards: Identität als statischer Block (einzeilig) — Drag-Griff, editierbarer Name mit erhaltenen Chain-Referenzen, technische Katalog-ID darunter, farbige Linie rechts (zieht bei Farbänderung live mit)
  - Indikator-Cards: aufklappbare Child-Row 'Erweiterte Optionen' mit zwei Cards — 'Visualisierung' (Farbe, Transparenz, Linienstärke, Linienstil) und 'Anzeige' (Anzeigen-Toggle, Plot-Typ, Löschen); neue State-Felder opacity/lineWidth/lineStyle in beiden Render-Pfaden angewendet und persistiert
  - Indikator-Cards: Drag-and-Drop-Reorder mit richtungsabhängiger Einfügemarke; Reihenfolge als explizites indicator_order-Array in ui_state_json persistiert
  - Indikator-Cards: Eltern-Card 'Indikatoren' optisch abgesetzt (cp-ind-panel); Eingabefelder auf einheitliche Tabler-sm-Höhe gebracht (globale .card .form-control-sm-Regel überschrieb nur das Padding der Zahlenfelder, in .cp-ind-row zurückgesetzt)
  - Toolbar: Dropdowns 'Indikator-Konfiguration' und 'Backtest-Config' getauscht (Indikator links); Charthöhe-Default 400px mit Toggle-Button 'Höhe' (400/560); Dark-Mode-Hintergrund der Chart-Übersicht aufgehellt
  - Aktionsleiste: Apply-Button in 'Refresh' umbenannt; Schnellbacktest-Button und Ergebnis-Badge in den Tab-Header verschoben — Badge links (wächst nach links), beide Buttons rechts positionsstabil
  - Indikator-Konfiguration speichern: 'Speichern' öffnet ein Überschreib-Modal mit Ziel-Dropdown (oben eingestellte Config vorausgewählt) statt direkt zu überschreiben — kein Chart-Reload mehr; 'Speichern unter…' unverändert
  - OHLCV-Input-Quellen: Anzeige spiegelt jetzt den JSON-Wert 1:1 (kein Mapping) — Dropdown-Optionswerte auf kanonische Kleinschreibung (vgl. indicator_factory.py: ref.lower()); vorher zeigten aus Results gespeicherte (kleingeschriebene) Setups fälschlich 'Open'
  - OHLCV-Datenkonsistenz: 5 bestehende Indikator-Configs mit großgeschriebenen OHLCV-Werten auf Kleinschreibung normalisiert
  - Setup-Laden per URL: Setup über ?setupid=<id> ladbar (bookmarkbar); Dropdown-Auswahl navigiert einheitlich über die URL (ein einziger Lade-Pfad); Parameter von ?setup= auf ?setupid= vereinheitlicht (Backend from-result, Results-Seite-Button, On-Load-Handler); Setup-Dropdown breiter und mit angezeigter Setup-ID
  - Schnellbacktest-Anzeige: Badge, Equity-Overlay und Trade-Marker werden bei jeder ergebnis-relevanten Änderung (Indikatoren/Regeln/Portfolio/Chart-Config) automatisch verworfen; reiner Candle-Toggle ausgenommen

### Files
- services/frontend/templates/chart_playground/index.html
- services/frontend/static/css/app.css
- services/api/routes/api_chart_playground.py
- services/frontend/templates/config/playground_setups.html



## [1.8.27] - 12.06.2026

### Changed
- Chart-Playground: Indikator-Panel auf zweizeiliges Layout umgestellt
  - Zeile 1: Name + Indikator
  - Zeile 2: Eingabe-Parameter (Inputs, Wertfelder, Timeframe)
  - Anzeige-Steuerung (Anzeigen/Farbe/Typ) und Löschen-Button bleiben rechts über beide Zeilen
  - card-body via Flex-Layout mit linkem Hauptbereich (.cp-ind-main, zweizeilig) und rechtem Aktionsbereich (.cp-ind-actions)

### Files
- services/frontend/templates/chart_playground/index.html
- services/frontend/static/css/app.css



## [1.8.26] - 11.06.2026

### Added
- Leaderboard: Filter nach Strategie und Iteration ergänzt
  - Zwei neue Dropdowns neben dem Test-Set-Filter: Strategie (KT / strategy_family) und Iteration (ITER / strategy_name)
  - Client-seitige Filterung über DataTables-Spaltensuche mit exakter, verankerter Regex
  - Optionen werden aus den geladenen Einträgen befuellt; Iterationsliste kaskadiert nach gewählter Strategie
  - strategy_family-Renderer liefert fuer Nicht-Display-Typen den Rohwert, damit die Spaltensuche/Sortierung nicht am HTML scheitert

### Files
- services/frontend/templates/leaderboard/index.html



## [1.8.25] - 11.06.2026

### Changed
- Leaderboard: Info-Icon der ID-Spalte entfernt
  - ID-Spaltenkopf braucht keinen Tooltip, Info-Icon entfernt

### Files
- services/frontend/templates/leaderboard/index.html



## [1.8.24] - 11.06.2026

### Changed
- Leaderboard: Spaltenkopf Konzept zu KT gekürzt
  - Header Konzept umbenannt zu KT, Info-Icon bleibt erhalten

### Files
- services/frontend/templates/leaderboard/index.html



## [1.8.23] - 11.06.2026

### Fixed
- Leaderboard: Spalte Indikator-Config wieder sortierbar
  - orderable: false stammte noch aus der Badge-Variante und blockierte das Sortieren — jetzt entfernt
  - Sortierung nutzt den rohen IndicatorConfig-Namen (type !== display), nicht das gerenderte HTML

### Files
- services/frontend/templates/leaderboard/index.html



## [1.8.22] - 11.06.2026

### Fixed
- Leaderboard: Indikator-Tooltip hat jetzt deckenden Hintergrund
  - Tooltip-Hintergrund war teiltransparent (Tabler-Default), die Tabelle schien durch und störte beim Lesen
  - Solide Fläche und volle Deckkraft über --bs-tooltip-bg/--bs-tooltip-opacity gesetzt (Pfeil zieht mit), zusaetzlich dezenter Schatten

### Files
- services/frontend/static/css/app.css



## [1.8.21] - 11.06.2026

### Changed
- Leaderboard: Indikator-Hover formatiert (Name als Überschrift, Parameter als Key/Value)
  - Hover-Box der Indikator-Config-Spalte von einfachem Monospace-Fließtext auf strukturiertes HTML umgestellt
  - Pro Indikator ein Block: Name als Überschrift (fett, mit Trennlinie), Parameter darunter als ausgerichtete Key/Value-Zeilen
  - data-bs-html aktiviert; dynamische Werte escaped, statisches Markup mit einfachen Anführungszeichen + Attribut-Escaping gegen Tooltip-Bruch
  - CSS-Styling fuer .indicator-tooltip-Blöcke ergaenzt (Name, Key, Val, leer-Hinweis)

### Files
- services/frontend/templates/leaderboard/index.html
- services/frontend/static/css/app.css



## [1.8.20] - 11.06.2026

### Fixed
- Leaderboard: IndicatorConfig-Titel wird jetzt korrekt aufgelöst (war immer NULL)
  - LeaderboardEntry.indicator_config_id wurde bisher beim Bauen bewusst auf NULL gesetzt und nirgends befüllt; der Name konnte daher nie aufgelöst werden und das Frontend fiel immer auf die Indikatoren-Anzeige zurück
  - build_leaderboard_entry befüllt indicator_config_id jetzt aus den BacktestRuns des TestSet-Runs (alle teilen dieselbe Config); gespeichert wird die ID, nicht der Name, damit ein Umbenennen der Config den Join nicht bricht
  - Lose Referenz ohne Foreign Key bleibt erhalten — Löschen einer IndicatorConfig wird nicht blockiert; bei toter ID greift im Frontend der Fallback auf die Indikatoren-Anzeige
  - Einmaliges Backfill-Skript scripts/backfill_leaderboard_indicator_config.py rekonstruiert die ID für Bestandseinträge über winning_result_ids -> BacktestResult -> BacktestRun (16 Einträge aktualisiert)

### Files
- user_data/utils/database/repository_testsets.py
- scripts/backfill_leaderboard_indicator_config.py



## [1.8.19] - 11.06.2026

### Changed
- Leaderboard: Indikatoren-Spalte zeigt jetzt den IndicatorConfig-Namen statt Badges
  - Spalte umbenannt zu Indikator-Config; zeigt den Namen der zugrundeliegenden IndicatorConfig (z. B. VWMA 2 / Return / 2755455) als Fließtext
  - Hover auf den Namen listet alle Indikatoren mit ihrer Konfiguration (zuvor pro Badge ein eigener Hover)
  - Backend: indicator_config_name wird batched über indicator_config_id aus IndicatorConfig nachgeladen und im LeaderboardEntryOut mitgeliefert
  - Verwaiste Badge-Render-Funktion und CSS-Klasse .indicator-badge entfernt bzw. auf .indicator-config-link umgestellt

### Files
- services/api/routes/api_leaderboard.py
- services/frontend/templates/leaderboard/index.html
- services/frontend/static/css/app.css



## [1.8.18] - 11.06.2026

### Changed
- Leaderboard-Tabelle weiter verschmälert: ID-Spalte ergänzt, Erstellt am in Child-Row, Header gekürzt
  - Neue ID-Spalte (Datensatz-ID) vor der Konzept-Spalte, zentriert
  - Spalte Erstellt am aus der Übersicht entfernt und in die aufklappbare Child-Row verschoben
  - ITER-Spalteninhalt zentriert (text-nowrap entfernt, darf umbrechen)
  - Profit-Faktor-Header zu Ø PF gekürzt
  - text-nowrap bei TestSet und Erstellt am entfernt, damit lange Werte umbrechen und die Tabelle schmaler wird
  - Standard-Sortier-Index auf Sum Return nachgezogen (jetzt Index 13)

### Files
- services/frontend/templates/leaderboard/index.html



## [1.8.17] - 11.06.2026

### Changed
- Leaderboard-Tabelle: Iteration-Spalte zu ITER verschmälert und zentriert, Runner-Version in Child-Row verschoben
  - Spaltenkopf Iteration umbenannt zu ITER und zentriert dargestellt
  - Spalteninhalt der ITER-Spalte zentriert
  - Runner-Version-Spalte aus der Tabellen-Übersicht entfernt und als erster Block in die aufklappbare Child-Row verschoben
  - colspan des Lade-Platzhalters von 18 auf 17 sowie Standard-Sortier-Index von 13 auf 12 (Sum Return) angepasst

### Files
- services/frontend/templates/leaderboard/index.html



## [1.8.16] - 11.06.2026

### Added
- OoS-Validierungs-Werkzeuge: Result zu eingefrorener IndicatorConfig (Endpoint + brief_ids freeze-Verb) plus Workflow-Doku und Skill-Integration
  - Neuer Endpoint POST /api/config/indicator/from-result/{result_id}: friert die Gewinner-Parameter eines Backtest-Results (arange-Range zu Skalar, Matching-Regel <factory_lower>_<feldname>) zu einer Single-Point-IndicatorConfig ein. Concept/Iteration werden vom Run uebernommen, Name nach Konvention <KONZEPT> <version> / <Segment> / <ResultID>.
  - brief_ids.py: neues Verb 'freeze res:ID:Segment' ruft den Endpoint (Segment optional: Return/Sharpe/PF/WinR90, Trenner ':' oder '/'). Hilfe-Docstring und SKILL.md Pfad B dokumentieren es.
  - Neuer Workflow documentation/strategy-development/workflows/oos-validierung.md (Spitzenreiter einfrieren zu IndicatorConfig, Testset-Lauf, Leaderboard) plus Zeile im AGENT_ENTRY-Workflow-Index und in der CLAUDE.md-Workflow-Liste.
  - ds-strategie-session SKILL.md: neue Rolle-Sektion (Strategie-Entwickler und Bewerter) und Werkzeug-/Workflow-Liste im Pfad-A-Briefing.
  - Ticket 36 angelegt: LeaderboardEntry.indicator_config_id bleibt NULL, weil der Builder die ID der Child-Runs nicht durchreicht.
  - Stale Vault-Pfade vwma-dws zu vwma korrigiert in AGENT_ENTRY.md, CLAUDE.md und workflows/iteration.md.

### Files
- services/api/routes/api_config.py
- .claude/skills/ds-strategie-session/scripts/brief_ids.py
- .claude/skills/ds-strategie-session/SKILL.md
- documentation/strategy-development/workflows/oos-validierung.md
- documentation/strategy-development/AGENT_ENTRY.md
- documentation/tickets/36-leaderboard-indicator-config-link.md
- CLAUDE.md



## [1.8.15] - 11.06.2026

### Fixed
- Worker-Restart-Schleife behoben: stabile Redis-Verbindung mit TCP-Keepalive
  - RQ-Worker brachen unter Docker/WSL2 alle ~6-7 Min mit 'Redis connection timeout, quitting...' ab (Exit 0) und respawnten via restart-Policy in einer Schleife - laufende Backtests wurden gekillt, grosse Sweeps wurden nie fertig und blieben als verwaiste 'running'-Runs liegen
  - Ursache: idle TCP-Verbindung zu Redis riss waehrend des blockierenden RQ-Dequeue (BLPOP ~405s) still ab, da socket_keepalive/health_check fehlten
  - get_redis_connection() setzt jetzt socket_keepalive=True, plattformabhaengige Keepalive-Optionen (TCP_KEEPIDLE/INTVL/CNT) und health_check_interval=30
  - Neuer Worker-Entrypoint services/api/worker_entry.py ersetzt 'rq.cli worker --url ...' und nutzt die Keepalive-Verbindung; Queue-Set per CLI-Argumenten je Umgebung erhalten
  - Worker-Command in allen drei Compose-Dateien (local/staging/prod) umgestellt

### Files
- services/api/redis_conn.py
- services/api/worker_entry.py
- docker-compose-local.yml
- docker-compose-staging.yml
- docker-compose.yml



## [1.8.14] - 11.06.2026

### Added
- Backtest-Runs speichern jetzt die Herkunfts-Referenzen backtest_config_id und indicator_config_id
  - Zwei neue lose Referenz-Spalten (kein FK) auf backtest_runs: backtest_config_id, indicator_config_id (Alembic 0012)
  - Befuellt beim Einzel-Run (/api/backtest/start), TestSet-Run und Playground-Run aus den jeweils gewaehlten Configs
  - Playground sendet die gewaehlten Dropdown-IDs (Backtest-/Indikator-Config) jetzt an /run-backtest mit
  - Result-Export (from-result) stellt damit alle vier Dropdowns wieder her: Konzept, Iteration, Backtest-Config, Indikator-Config
  - Die JSON-Spalten bleiben der primaere Eintrag; es werden keine neuen Config-Records angelegt
  - NULL bei ad-hoc-Runs ohne gespeicherte Config

### Files
- user_data/utils/database/models.py
- user_data/utils/database/repository.py
- alembic/versions/0012_backtest_run_config_refs.py
- services/api/routes/api_backtest.py
- services/api/routes/api_testset_runs.py
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html
- tests/test_iteration_id_write_path.py



## [1.8.13] - 11.06.2026

### Fixed
- Chart-Playground: Aus Backtest-Result erzeugte Setups setzen beim Laden wieder Konzept und Iteration
  - create_setup_from_result schreibt jetzt concept_slug (aus run.iteration.concept_id) in strategy_config_json und selected_configs.iteration_id in ui_state_json
  - Vorher fehlten beide Felder, weshalb Konzept- und Iteration-Dropdown beim Setup-Laden leer blieben
  - backtest_config_id/indicator_config_id bleiben null - ein Run referenziert keine gespeicherte Config (liegt als JSON, nicht als FK)
  - Bereits zuvor erzeugte from-result-Setups muessen neu erzeugt werden, um die Verknuepfung zu erhalten

### Files
- services/api/routes/api_chart_playground.py



## [1.8.12] - 11.06.2026

### Changed
- Spec-Runner-Importpfad als zentrale Konstante SPEC_RUNNER_IMPORT_PATH statt 4-fach dupliziertem String-Literal (M5)
  - Neue Konstante SPEC_RUNNER_IMPORT_PATH in spec_runner.py (neben VERSION) als Single Source
  - Ersetzt das Literal 'user_data.strategies.generic.spec_runner.run_spec_strategy' in api_backtest.py, api_chart_playground.py, api_testset_runs.py und spec_strategy_start.py
  - iteration.type == 'hardcoded' bleibt unveraendert - das ist legitime Domaenenlogik (echtes type-Feld mit XOR-Validierung), kein Hardcoding
  - Verifiziert: API laedt (Modul-Import OK), Konstante importierbar mit korrektem Wert

### Files
- user_data/strategies/generic/spec_runner.py
- services/api/routes/api_backtest.py
- services/api/routes/api_chart_playground.py
- services/api/routes/api_testset_runs.py
- user_data/strategies/generic/spec_strategy_start.py



## [1.8.11] - 11.06.2026

### Fixed
- Stilles Fallback beim Speichern von Indikator-Zeitreihen entfernt - unbekanntes Datenformat bricht den Run jetzt hart ab statt Daten lautlos zu verschlucken (M7)
  - save_strategy_results (repository.py) und recompute.py rateten bei fehlendem output_names stillschweigend ['result'] - traf das nicht zu, wurden die Indikator-Daten ohne Fehler oder Log verworfen
  - Jetzt: Datenobjekt ohne output_names loest ValueError aus. Im Run-Pfad rollt die Transaktion zurueck und der Job markiert den Run als 'failed' mit klarer Meldung (sichtbar in Runs-Liste und Workflow); im Recompute-Pfad propagiert der Fehler bis zum Chart-Status
  - Happy-Path unveraendert: bei vorhandenem output_names identisches Verhalten wie zuvor. Der else-Zweig war bei den aktuellen VBT-Indikatoren toter Code - kein laufender Run betroffen
  - Begruendung: In einer Trading-Software duerfen unbekannte/unvollstaendig gespeicherte Indikator-Daten nicht stillschweigend durchgehen

### Files
- user_data/utils/database/repository.py
- services/api/recompute.py



## [1.8.10] - 11.06.2026

### Changed
- Supertrend wird im Result-Chart generisch gerendert - kein hartcodierter Indikator-Name mehr im Anzeige-Layer (K2, K3)
  - initExtraIndicators erkennt den Render-Modus anhand der Daten-Struktur: Punkte mit direction-Feld -> Richtungs-Flaechen (Baender) inkl. Shift-Toggle, sonst Linie
  - Hartcodiertes Supertrend-Panel, die Spezial-Handler (toggle-supertrend/-shift), _HARDCODED_INDS und supertrendBgSeries aus result_chart.html entfernt
  - views_backtest.py: Supertrend-Spezialwerte (supertrend_period/-multiplier/-tf/-enabled) entfernt; Parameter kommen generisch ueber IND_PARAMS aus actual_params (zeigt den echten Result-Wert statt des Sweep-Starts)
  - Verifiziert an Result 2635758: Seite rendert (HTTP 200) ohne Hardcoded-Reste, supertrend als Richtungs-Indikator erkannt, IND_PARAMS period=10/multiplier=3.0

### Files
- services/frontend/templates/backtest/result_chart.html
- services/api/routes/views_backtest.py



## [1.8.9] - 11.06.2026

### Changed
- Chart-Daten-Endpunkt dispatcht Supertrend ueber den Indikator-Typ statt ueber den hartverdrahteten Instanz-Namen (K1)
  - get_chart_data laedt jetzt indicators_config_json des Runs und baut eine name->typ-Map (vbt:SUPERTREND -> supertrend)
  - Dispatch geht ueber den normalisierten Typ statt ueber ind_name == 'supertrend' - robust gegen Umbenennen der Indikator-Instanz in der Spec
  - Output-Key folgt dem Instanz-Namen (ind_name) statt hartcodiertem 'supertrend'
  - Verifiziert an Result 2635758: supertrend mit direction-Feld, vwma und fast_sma als Linien

### Files
- services/api/routes/api_backtest.py



## [1.8.8] - 11.06.2026

### Fixed
- Parameter-Tooltip in der Backtest-Results-Tabelle erscheint wieder beim Hovern über die Strategiezeile
  - Ursache: Frontend las das Feld actual_params_json, die API liefert es aber als actual_params - dadurch wurde nie ein param-tip-Span erzeugt
  - Hartgecodetes Label-Mapping (paramOrder/paramOrder2 fuer VWMA/FastSMA/Supertrend) entfernt - Parameter werden jetzt generisch als key|value angezeigt
  - Doppelten paramOrder-Block zu einer Schleife zusammengefasst

### Files
- services/frontend/templates/backtest/results.html



## [1.8.7] - 11.06.2026

### Fixed
- Sortierung nach der Favorit-Spalte in der Results-Tabelle funktioniert wieder
  - Favorit-Spalte war im Sortier-Mapping (_DT_COLUMNS) als None hinterlegt und fiel auf den Default-Sort (Total Return) zurueck - es erschien nur zufaellig ein Favorit oben
  - Spalte 1 auf is_favorite gemappt und Spezialfall mit deterministischer Sekundaersortierung nach ID ergaenzt, damit die Zeilen beim 5s-Auto-Reload nicht springen

### Files
- services/api/routes/api_backtest.py



## [1.8.6] - 11.06.2026

### Changed
- Filterleiste der Results-Seite folgt jetzt der Tabellen-Spaltenreihenfolge
  - Reihenfolge: Run, Strategie, Symbol, Timeframe, Sharpe, Max DD %, Trades, Win Rate %, Profit Factor, Return % – analog zur Spaltenfolge der Tabelle
  - Nur DOM-Reihenfolge geaendert, Element-IDs unveraendert – Filterlogik bleibt unberuehrt

### Files
- services/frontend/templates/backtest/results.html



## [1.8.5] - 11.06.2026

### Changed
- Spaltentitel Profit Factor in der Results-Tabelle auf PF gekürzt mit Info-Icon-Tooltip
  - Spaltenkopf zeigt jetzt PF plus Bootstrap-Tooltip-Icon (Erklärung des Profit Factors)
  - Umgesetzt nach der Inline-Tabellen-Header-Variante aus documentation/design/design-guide.md (12x12 Icon, text-muted, vertical-align -0.1em)

### Files
- services/frontend/templates/backtest/results.html



## [1.8.4] - 11.06.2026

### Removed
- Spalte Downside Risk aus der Backtest-Results-Tabelle entfernt
  - Spaltenkopf und Column-Definition im Frontend entfernt
  - Sortier-Index-Mapping (_DT_COLUMNS) im /results/dt-Endpoint entsprechend nachgezogen, damit die Sortierung der nachfolgenden Spalten weiter passt

### Files
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/results.html



## [1.8.3] - 11.06.2026

### Added
- Numerische Min/Max-Feld-Filter und ein-/ausblendbare Filterleiste auf der Backtest-Results-Seite
  - Filterleiste um Min/Max-Zahlenfelder fuer Win Rate, Return, Sharpe, Profit Factor, Trades und Max DD erweitert (server-side im /results/dt-Endpoint)
  - Toggle-Button mit Filter-Icon im Page-Header blendet die Filterleiste ein/aus (Default eingeblendet)
  - Scroll-Sprung beim 5s-Auto-Update behoben: Scroll-Position wird um den DataTables-Reload herum gesichert (sprang auf hohen Pagination-Seiten wiederholt ans Tabellenende)

### Files
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/results.html



## [1.8.2] - 11.06.2026

### Fixed
- Result-Chart: Long-Orders erscheinen nach Aus-/Einschalten sofort wieder, statt erst beim naechsten Chart-Invalidate
  - Der Orders-Toggle-ON-Handler rief nur attachPrimitive(orderPrimitive); das loest in Lightweight Charts keinen Repaint aus, da OrderPrimitive keinen requestUpdate/updateAllViews-Mechanismus hat
  - Die Marker erschienen dadurch erst beim naechsten Invalidate (Pan/Zoom/Resize/Crosshair) - wirkte wie eine lange Berechnung
  - Fix: Redraw im Toggle-Handler erzwingen mit derselben detach/attach-Technik, die showTrades und _applyDrawdownBands bereits verwenden

### Files
- services/frontend/templates/backtest/result_chart.html



## [1.8.1] - 11.06.2026

### Fixed
- Result-Chart: Equity/Indikatoren beim Laden korrekt aufs aktive Timeframe resampled; Indikator-Panels vollständig generisch inkl. Parameter-Anzeige
  - Equity blieb beim Laden im Basis-TF (z.B. 4h), weil die Equity-Serie wegen einer Race-Condition erst nach dem 1d-Default-Klick angelegt und mit Rohdaten gesetzt wurde
  - Neuer Helper resampleForActiveTf(points) + getActiveTf() resampled jede spaet aktivierte Linien-Serie (Equity, alle Indikatoren) auf das aktuell aktive TF
  - Hartcodierte fast_sma-/vwma-Panels und Toggle-Handler entfernt; beide laufen jetzt ueber den generischen Indikator-Pfad (initExtraIndicators) wie jeder andere Indikator
  - Generische Panels zeigen die vollstaendige aufgeloeste Konfiguration: neuer Backend-Mechanismus ordnet actual_params (Schema {indicator_class_lower}_{param}) generisch je Indikator zu und gibt sie als ind_params/IND_PARAMS ans Template
  - _HARDCODED_INDS auf supertrend reduziert (Flaechen-Rendering bleibt Sonderfall mit eigenem Panel)
  - Verwaiste run-Felder fast_sma_tf/vwma_tf in views_backtest.py entfernt

### Files
- services/frontend/templates/backtest/result_chart.html
- services/api/routes/views_backtest.py



## [1.8.0] - 11.06.2026

### Changed
- Zentrales Stylesheet app.css eingeführt — Scrollbalken-Sprung-Fix und CSS-Konsolidierung
  - Neue Datei services/frontend/static/css/app.css mit globalem CSS für alle Seiten
  - Scrollbalken-Fix: Tablers :root-margin-Hack neutralisiert (margin-left: 0), html { scrollbar-gutter: stable } verhindert horizontales Springen beim Seitenwechsel
  - Globale Regel .page-body .container-xl { max-width: 100% } — war in 25 Templates dupliziert, jetzt einmalig in app.css
  - DataTables-Boilerplate (.dt-footer-row, .dt-search-input, .dt-search-icon, .dt-search-clear, div.dt-search) aus allen Tabellenseiten entfernt und in app.css zentralisiert
  - Weitere gemeinsame Stile verschoben: .val-pos/.val-neg, Child-Row-Stile (details-control, custom-details-row), Parameter-Tooltip (#param-tooltip), Leaderboard-Stile, Analyse-Stile, Chart-Toolbar (tf-btn), Playground-Stile, Workflow-Template-Stile
  - app.css in base.html eingebunden (nach Tabler-CSS, mit Cache-Busting ?v={{ STATIC_TS }})
  - Leere {% block head %} Blöcke aus bereinigten Templates entfernt
  - design-guide.md aktualisiert: CSS-Regeln gehören zentral in app.css, nicht mehr per {% block head %} pro Seite

### Files
- services/frontend/static/css/app.css
- services/frontend/templates/base.html
- services/frontend/templates/backtest/runs.html
- services/frontend/templates/backtest/results.html
- services/frontend/templates/backtest/run_detail.html
- services/frontend/templates/backtest/analyse.html
- services/frontend/templates/backtest/result_chart.html
- services/frontend/templates/chart_playground/index.html
- services/frontend/templates/config/backtest_config_edit.html
- services/frontend/templates/config/backtest_configs.html
- services/frontend/templates/config/data_files.html
- services/frontend/templates/config/indicator_config_edit.html
- services/frontend/templates/config/indicator_configs.html
- services/frontend/templates/config/playground_setup_edit.html
- services/frontend/templates/config/playground_setups.html
- services/frontend/templates/config/strategy_concepts.html
- services/frontend/templates/config/strategy_configs.html
- services/frontend/templates/knowledge/files.html
- services/frontend/templates/knowledge/run_detail.html
- services/frontend/templates/knowledge/runs.html
- services/frontend/templates/leaderboard/index.html
- services/frontend/templates/testsets/detail.html
- services/frontend/templates/testsets/list.html
- services/frontend/templates/workflow/run_detail.html
- services/frontend/templates/workflow/runs.html
- services/frontend/templates/workflow/template_edit.html
- services/frontend/templates/workflow/templates.html
- documentation/design/design-guide.md



## [1.7.28] - 11.06.2026

### Added
- Bewertungs-Schema: Methodik 'Archetyp-Vertreter aus einem Sweep gewinnen' ergaenzt
  - Neue Sektion in bewertungs-schema.md: Die drei Archetypen sind drei Sortierungen derselben Sweep-Ergebnismenge (Angreifer=Return, Scharfschuetze=Profitfaktor, Dauerlaeufer=Sharpe), nicht ein Vergleich unoptimierter Baselines
  - Stellt klar: eine schwache Baseline ist kein Grund zum Aussortieren, wenn die Iteration im Sweep starke Vertreter liefert
  - Hintergrund: VWMA-v3-Sweep (Run 1807) liefert alle drei Vertreter je nach Sortierung

### Files
- documentation/strategy-development/bewertungs-schema.md



## [1.7.27] - 11.06.2026

### Changed
- vault-create schreibt jetzt das volle Iterations-Frontmatter-Schema
  - Die Route POST /iterations/{id}/vault-create emittiert nun das reiche Schema (iteration, status, workflow_state, archetype, hypothesis, verdict, metrics-Block, result_ids) zusaetzlich zu den DB-Link-Feldern
  - Damit teilen App-Skelett, Vault-Template _templates/iteration.md und die Dataview-Tabellen in den Concept-Notizen dasselbe Frontmatter (Single Source) — vorher schrieb die Route nur ein Minimal-Frontmatter, das die Dataview-Queries nicht lesen konnten
  - Aenderung wirkt auf kuenftige Skelette; API-Container muss dafuer neu geladen/gestartet werden

### Files
- services/api/routes/api_strategy.py



## [1.7.26] - 11.06.2026

### Changed
- Bewertungs-Schema: Archetyp-Namen und Aussortiert-Kategorie ergaenzt
  - Die drei Archetypen tragen jetzt Namen: A = Angreifer (Return-aggressiv), B = Scharfschuetze (Profitfaktor-Praezision), C = Dauerlaeufer (Konsistenz)
  - Neue Reject-Kategorie 'Aussortiert' (kein vierter Archetyp) mit drei Gruenden: dominiert / Artefakt / kein Edge — entspricht Verdict archived
  - Schema auf alle vier VWMA-Baselines angewandt (Ergebnis im Vault-status.md)

### Files
- documentation/strategy-development/bewertungs-schema.md



## [1.7.25] - 11.06.2026

### Fixed
- ds-strategie-session-Skill: status.md-Verortung auf den Vault korrigiert
  - Der Skill las status.md aus user_data/strategies/ (Projekt), schrieb sie aber in den Vault (Pfad C) — Folge-Sessions haetten die Datei am falschen Ort gesucht
  - Phase 1 (Aktivitaets-mtime) und Phase 3 (Briefing-Hauptquelle) lesen status.md jetzt aus <Vault>/30_Trading/strategies/<slug>/status.md
  - Phase-1-Strategie-Erkennung klargestellt: Projekt-Ordner liefert nur optionalen Legacy-Code, die status.md liegt ausschliesslich im Vault

### Files
- .claude/skills/ds-strategie-session/SKILL.md



## [1.7.24] - 11.06.2026

### Removed
- Doku-Konsolidierung — abgeloeste Konzept-Ablage und redundantes Meta-Entscheidungs-Log entfernt
  - documentation/project/strategie-entwicklung-konzept.md geloescht — 429-Zeilen-Vorschlagsgeruest von 2026-05-28, unreferenziert und abgeloest durch documentation/strategy-development/
  - Restliche beilaeufige Bestvariante-Nennungen in project-structure.md und projekt.md bereinigt
  - CLAUDE.md: Prinzip ergaenzt, dass das Software-Changelog nur Code/Infrastruktur dokumentiert, keine Strategie-Ergebnisse (einziges noch gueltiges Prinzip aus dem geloeschten decisions.md)
  - ds-strategie-session-Skill liest decisions.md nicht mehr als Session-Kontext
  - Vault-Datei 30_Trading/decisions.md entfernt — war reine Erinnerungsstuetze, inhaltlich entweder in CLAUDE.md erzwungen oder veraltet (Bestvariante, altes Versions-Praefix-Schema)

### Files
- documentation/project/strategie-entwicklung-konzept.md
- documentation/project/project-structure.md
- documentation/project/projekt.md
- CLAUDE.md
- .claude/skills/ds-strategie-session/SKILL.md



## [1.7.23] - 11.06.2026

### Changed
- Veralteten Bestvariante-Begriff aus der gesamten Strategie-Entwicklungs-Doku entfernt
  - Kompletter Terminologie-Sweep ueber 8 Dateien in documentation/strategy-development/ (19 Stellen)
  - Aktiver Widerspruch behoben: neue-strategie.md legte den geloeschten bestvarianten/-Ordner per mkdir neu an und trug eine veraltete status.md-Sektion 'Aktueller Bestvariante' (jetzt 'Beste Iteration')
  - Begriffe ersetzt durch beste Iteration / Promotion-Kandidat / Sieger je nach Kontext, konsistent mit decisions.md 2026-05-28b und dem neuen Bewertungs-Schema
  - Einzige verbleibende Nennung ist der erklaerende Hinweis in bewertungs-schema.md zur Abschaffung des Begriffs

### Files
- documentation/strategy-development/workflows/neue-strategie.md
- documentation/strategy-development/workflows/parameter-sweep.md
- documentation/strategy-development/workflows/iteration.md
- documentation/strategy-development/workflows/cross-symbol-sweep.md
- documentation/strategy-development/workflows/pine-reproduktion.md
- documentation/strategy-development/workflows/setup-via-api.md
- documentation/strategy-development/app-guide.md
- documentation/strategy-development/AGENT_ENTRY.md



## [1.7.22] - 11.06.2026

### Changed
- Strategie-Doku an das neue Bewertungs-Schema angeglichen
  - metrics-Template in workflows/iteration.md um profit_factor und win_rate erweitert (Lead-Kennzahlen aus dem Schema)
  - PROCESS.md Phase 7 Verdict-Beschreibung von veraltetem Bestvariante-Begriff auf Archetyp-Vertreter (A/B/C) umgestellt, mehrere promoted erlaubt
  - iteration.md Schritt 8 STATUS-Update von Bestvariante-Eintrag auf Beste Iteration / Archetyp-Vertreter umgestellt

### Files
- documentation/strategy-development/workflows/iteration.md
- documentation/strategy-development/PROCESS.md



## [1.7.21] - 10.06.2026

### Added
- Bewertungs-Schema (Akzeptanzkriterien) für die Strategie-Entwicklung dokumentiert
  - Neue Datei documentation/strategy-development/bewertungs-schema.md definiert die bisher nur referenzierten Akzeptanzkriterien
  - Kennzahl-Set mit Lead-Kennzahlen (Total Return, Sharpe, Profitfaktor, Max DD, Winrate, Trades) und Kontext-Kennzahlen (Benchmark/Alpha, Calmar/Sortino)
  - Drei gleichberechtigte Strategie-Archetypen A Return-aggressiv / B Profitfaktor-Praezision / C Konsistenz-linear, statt Pass/Fail-Ranking
  - Trade-Zahl als Flag statt Filter, plus Validierungs-Methode (Out-of-Sample + Cross-Symbol) fuer Artefakt-Verdacht
  - PROCESS.md Phase 6 verweist nun auf das Schema

### Files
- documentation/strategy-development/bewertungs-schema.md
- documentation/strategy-development/PROCESS.md



## [1.7.20] - 10.06.2026

### Added
- Strategie-Session-Skill um Session-Ende erweitert und Mission-Kontext für Auto-Injektion ergänzt
  - Mission-Block in _inject.md: bt_pro_app_v1 als Strategie-Entwicklungsschicht des übergeordneten Trading-Systems, Verweis auf trading-system-index.md. Wird per Hook automatisch in jede Strategie-Session geladen.
  - Skill ds-strategie-session: neuer Pfad C 'Session beenden' - aktualisiert beim Abschluss status.md im Vault und offene Iter-Note/Run-Journal. Description und 'Was du nicht tust' konsistent mitgezogen.

### Files
- documentation/strategy-development/_inject.md
- .claude/skills/ds-strategie-session/SKILL.md



## [1.7.19] - 10.06.2026

### Added
- Guide-Abschnitt zu Timeout (td_stop) vs. bedingtem Fruehausstieg mit Fall-Tabelle
  - Zwei Balken-Hebel klar getrennt: fester Timeout (Portfolio-td_stop, Built-in, ODER-verknuepft) vs. Balken-Zaehlung in der Exit-Regel (since_entry, State-Primitiv, nativer Pfad)
  - Tabelle mit 6 Faellen ergaenzt; Fall 6 als realer Strategie-Typ (v32/v42): native Regel im Minus UND seit Entry>=2, plus td_stop als ODER-Auffanglinie, die VBT automatisch kombiniert
  - Klargestellt: Built-in-Delegation nur fuer unbedingte Timeouts (ODER); bedingte Fruehausstiege (UND mit State) sind nicht delegierbar und muessen Regeln im nativen Pfad sein

### Files
- documentation/strategy-development/guide.md



## [1.7.18] - 10.06.2026

### Fixed
- Vier vorbestehende rote Tests (aus dem 1.6.18-Umbau) auf den aktuellen Code-Stand nachgezogen
  - test_ticket16 test_underscores_to_dashes: Copy-Paste-Fehler korrigiert — Input 'vwma' (ohne Unterstrich) hatte nie underscores getestet; jetzt normalize_slug('vwma_dws') == 'vwma-dws'
  - test_ticket16 test_iteration_md_path + test_iteration_md_path_complex_version: erwarteten noch das alte Dateinamen-Format {version}.md; Code+Docstring nutzen bewusst {slug}-{version}.md (sprechender Name mit Slug-Praefix) — Tests nachgezogen
  - test_vault_chunk_model test_vault_chunk_nullable_regeln: erwartete content und embedding als NOT NULL; beide wurden in Ticket 33 bewusst nullable (leere Sentinel-Rows fuer Stub-Dateien) — Assertions nachgezogen
  - Alle Aenderungen betreffen ausschliesslich Test-Erwartungen, kein Produktivcode; Verifikation: tests/test_ticket16.py + test_vault_chunk_model.py = 38 passed

### Files
- tests/test_ticket16.py
- tests/test_vault_chunk_model.py



## [1.7.17] - 10.06.2026

### Fixed
- Backtest-Job mit 0 Kombinationen (leeres Portfolio) wird jetzt als 'failed' markiert statt still 'completed'
  - Audit-Fund: Bei fehlenden oder leeren OHLCV-Daten (fehlendes Symbol / leerer Zeitbereich) entstand ein Portfolio ohne Spalten. save_strategy_results lief dann in einen kryptischen IndexError (all_metrics[0] auf leerer Liste), und je nach Aufrufer wurde der Run trotzdem als 'completed' gewertet
  - Guard in repository.save_strategy_results ergaenzt: n_combinations == 0 wirft jetzt einen klaren ValueError, bevor DB-Ressourcen geholt werden — der aufrufende Worker-Job faengt ihn ueber den bestehenden except-Pfad und markiert den Run sauber als 'failed' (mit error_message)
  - get_engine()-Aufruf hinter den Guard verschoben (Input erst validieren, dann Ressourcen holen) — schuetzt alle Aufrufer (worker_tasks, recompute)
  - Neuer Unit-Test tests/test_repository_empty_portfolio_guard.py (DB-frei, da der Guard vor jeder DB-Interaktion greift): 1 passed

### Files
- user_data/utils/database/repository.py
- tests/test_repository_empty_portfolio_guard.py



## [1.7.16] - 10.06.2026

### Fixed
- Frontend: Fehlende .catch-Handler an Fetch-Aufrufen mit haengendem UI-State ergaenzt (Endlos-Spinner / dauerhaft gesperrte Buttons / Dropdown-Limbo)
  - analyse.html: btn-recompute-start gab den Button bei Fehler nie wieder frei (disabled blieb haengen); start/stop/reset und der Polling-Loop (pollRecomputeProgress) scheiterten stumm. Alle vier mit .catch abgesichert: Button-Reset + sichtbare Status-Meldung bzw. Fehler-Logging
  - start.html: loadIterations, loadTsIndConfigs, ts-loadIterations und loadIndConfigs liessen bei Fehler das jeweilige Dropdown im Limbo (disabled/leer). .catch zeigt jetzt eine 'Fehler beim Laden'-Option und aktualisiert den Start-Button-Zustand
  - data_files.html: Download-Button liess bei Netzwerkfehler den Status 'Job wird eingereiht...' dauerhaft stehen. .catch ersetzt ihn durch eine Fehlermeldung
  - Die POST-Submit-Buttons (Einzel-Lauf btnStart, TestSet tsBtnStart) waren bereits korrekt mit .catch abgesichert — unveraendert
  - Reine Chart-/Initial-Dropdown-Lader ohne haengenden State (analyse-Charts, Initial-Selects) bewusst unangetastet gelassen (kein Endlos-Spinner, surgical scope)
  - JS-Syntax aller drei Templates per node --check verifiziert

### Files
- services/frontend/templates/backtest/analyse.html
- services/frontend/templates/backtest/start.html
- services/frontend/templates/config/data_files.html



## [1.7.15] - 10.06.2026

### Removed
- Ticket 35 abgeschlossen: Cooldown-Approximation der Rules-Engine zurueckgebaut (State-Exits laufen ausschliesslich nativ)
  - rules_engine.py: Numba-Cooldown-Helfer _cooldown_filter_1d/2d, _entry_pos_ffill_2d, _entry_price_ffill_2d, _rolling_extreme_since_entry_2d sowie _entries_as_2d und _compute_entry_state ersatzlos entfernt (toter Code, nur noch im Masken-Pfad referenziert)
  - evaluate_rules: Parameter trade_cooldown und der uses_state/state-Zweig entfernt; der Masken-Pfad wertet jetzt ausschliesslich rein statische Entry-/Exit-Rules aus
  - state-Parameter aus _evaluate_rule_group/_evaluate_condition/_resolve_ref entfernt; State-Refs im Masken-Pfad werden jetzt hart mit ValueError abgewiesen (kein stilles Falschrechnen) und verweisen auf den nativen Pfad
  - spec_runner.py: trade_cooldown = td_stop or 16 entfernt; behebt zugleich den or-16-Bug (explizites td_stop=0 wurde verschluckt)
  - Tests: test_same_results_when_trades_shorter_than_cooldown und test_old_evaluate_rules_with_state_still_works entfernt, Letzterer ersetzt durch test_evaluate_rules_rejects_state_refs (Guard-Absicherung); obsoleter Spike spike_native_state_exit.py geloescht; toter trade_cooldown-Config-Key aus test_ticket23 entfernt
  - Verifiziert: tests/test_ticket35_native_state_exits.py + test_ticket23 + test_rules_engine_combine_broadcast = 57 passed

### Files
- user_data/strategies/generic/rules_engine.py
- user_data/strategies/generic/spec_runner.py
- tests/test_ticket35_native_state_exits.py
- tests/test_ticket23_lite_backtest.py
- tests/spikes/spike_native_state_exit.py



## [1.7.14] - 02.06.2026

### Fixed
- Chart-Playground /compute: lowercase OHLCV-Input-Namen werden jetzt korrekt auf die col_map-Spalten gemappt
  - Indikator-Configs speichern OHLCV-Inputs durchgaengig lowercase (close/high/low/volume/open/source), die col_map im /compute-Endpoint nutzt aber kapitalisierte Keys (Close/High/...) — explizite lowercase-Werte wurden nicht gemappt und schlugen mit 'Kein Mapping fuer Input' fehl
  - Fix: src_key wird vor dem col_map-Lookup ueber default_input_source case-normalisiert (close->Close, high->High, volume->Volume); bisher griff diese Tabelle nur fuer leere src_keys
  - Behebt alle drei Folgefehler an Config 1933 gemeinsam: dwsFastSMA (source), SUPERTREND (high/low/close) und die Kaskade dwsVWMA (Referenz auf fast_sma 'noch nicht berechnet', weil fast_sma zuvor erroriert war)
  - Topologische Sortierung nach Indikator-Referenzen war bereits korrekt — der Reihenfolge-Fehler war eine Folge des fehlgeschlagenen fast_sma, kein Sortier-Bug

### Files
- services/api/routes/api_chart_playground.py



## [1.7.13] - 01.06.2026

### Added
- Unit-Tests fuer _combine_broadcast (Cross-Produkt disjunkter Indikator-Param-Level)
  - Neue Test-Datei tests/test_rules_engine_combine_broadcast.py mit 23 Tests, alle gruen
  - Abdeckung: zwei disjunkte Bloecke (Cross-Produkt), Subset-Folding (Chaining), gemeinsames symbol-Carrier-Level bleibt aligned statt gekreuzt, rein alignbarer Fall faellt auf vbt.broadcast zurueck
  - Referenz-Invariante verifiziert: Sweep[combo].entries bit-identisch zum Standalone-Single-Combo (assert_series_equal) ueber evaluate_rules
  - Dimensionen bewusst klein gehalten (z.B. 6x4=24 statt 2125x15) — identische Kreuz-Mechanik, Laufzeit ~5s
  - Kein Produktivcode-Bug gefunden; _combine_broadcast verhaelt sich wie in indicators.md §6.6 dokumentiert

### Files
- tests/test_rules_engine_combine_broadcast.py



## [1.7.12] - 01.06.2026

### Fixed
- Chart-Playground: src-Altlast crasht keinen Lite-Backtest mehr — Erkennung in die Lade-Pfade verschoben
  - Neue Helper-Funktion splitLoadedEntry() klassifiziert beim Laden inputs/params und haelt unbekannte Value-Keys (Altlasten wie src, alter Name fuer source) aus dem Arbeits-State heraus, statt sie via fieldKind() in params zu uebernehmen
  - Beide Lade-Pfade umgestellt: applySetupConfig (Setup laden) und der cpIndCfgSelect-Change-Handler (Indikator-Config waehlen)
  - Altlast-Felder werden beim Laden einmalig sichtbar gemeldet (orange Status) statt still mitgeschleppt — spiegelt die Save-Pfad-Logik aus collectIndicatorConfigJson
  - Bei fehlendem Katalog-Meta (meta.params undefined) keine Erkennung, kein Fehlalarm — altes Verhalten bleibt
  - Behebt das Folgeproblem aus 1.7.5: Save-Fix bereinigte nur die DB-Config, der src-Wert landete beim Laden weiter im State und der Backend-Validator _resolve_params lehnte den Run ab

### Files
- services/frontend/templates/chart_playground/index.html



## [1.7.11] - 01.06.2026

### Fixed
- Backtest-Metriken: NaN-Werte werden nun korrekt als NULL gespeichert statt als NaN — behebt fehlerhafte Sortierung der Results-DataTable
  - Write-Path (repository.py): Die NaN/Inf-zu-None-Konvertierung im vektorisierten Partial-Metrics-Pfad war ein No-Op — df.where(np.isfinite(df), None) laesst in Float-Spalten NaN stehen, da pandas None dort wieder zu NaN macht. Konvertierung jetzt auf Record-Ebene nach to_dict.
  - Bestandsdaten bereinigt: 2947 NaN-Werte (profit_factor 1064, win_rate/sharpe/sortino/calmar/omega/expectancy/deflated_sharpe je 269) per einmaligem UPDATE zu NULL umgewandelt.
  - Folgefehler der Sortierung behoben: PostgreSQL behandelt NaN als groessten Wert, daher erschienen fehlende Metriken (Anzeige "-") beim absteigenden Sortieren faelschlich oben.

### Files
- user_data/utils/database/repository.py
- services/api/routes/api_backtest.py



## [1.7.10] - 01.06.2026

### Fixed
- Results-DataTable: NULL-Metriken (als \"-\" angezeigt) werden beim Sortieren numerischer Spalten jetzt einheitlich ans Ende gelegt
  - Bisher legte PostgreSQL NULL-Werte bei absteigender Sortierung an den Anfang, sodass z.B. fehlende Profitfaktoren ("-") oben statt unten erschienen
  - ORDER BY der numerischen Metrik-Spalten (profit_factor, sharpe_ratio, sortino_ratio, max_drawdown_pct, win_rate_pct, total_return_pct, end_value etc.) nutzt jetzt nullslast() in beide Richtungen
  - Default-Sortierung (total_return_pct DESC) ebenfalls auf nullslast() umgestellt

### Files
- services/api/routes/api_backtest.py



## [1.7.9] - 01.06.2026

### Added
- indicators.md: Deep-Dive zu Multi-Combo-Berechnung, Cross-Produkt und Recompute (Abschnitte 6.5-6.9)
  - Dokumentiert Spalten-MultiIndex-Struktur (Level-Namen, symbol-Carrier, Chaining-Vererbung), das Cross-Produkt disjunkter Param-Level im rules_engine (_combine_broadcast/_broadcast_explained, cross_indexes, n_combinations), die Speicher-Asymmetrie Multi- vs. Single-Combo, den Chart-Recompute-Flow inkl. der rules_json- und _build_resolved_config-Praefix-Mechanik sowie verifizierte Fakten und Neustart-Regeln
  - Ziel: naechster Chat findet die Backtest-/Chart-Berechnung sofort, ohne den Code neu zu rekonstruieren

### Files
- documentation/project/indicators.md



## [1.7.8] - 01.06.2026

### Fixed
- Recompute eines Multi-Combo-Results rechnete den vollen Sweep statt der Einzel-Kombination — falsche/identische Equity, langsam, Metriken ueberschrieben
  - _build_resolved_config baute den Param-Praefix aus dem vollen Indikator-Typ ('custom:dwsVWMA'.lower() = 'custom:dwsvwma_'), die actual_params-Keys heissen aber 'dwsvwma_length' / 'supertrend_period' (vbt-Klassenname ohne Namespace). Dadurch matchte kein Parameter, die Ranges blieben stehen und der Recompute fuehrte den kompletten 31875-Combo-Sweep aus und nahm column[0]
  - Folge: jeder geoeffnete Chart zeigte denselben ersten Combo (z.B. 281.85), das Laden dauerte Minuten, und die ueberschriebenen Metriken liessen das Result aus der gefilterten Result-Liste fallen
  - Fix: Praefix = Namespace-Teil nach 'custom:'/'vbt:' kleingeschrieben. Recompute laeuft nun als echter Single-Combo (~4.5s nach JIT-Warmup) mit den korrekten Parametern
  - Verifiziert: Sweep-Wert eines Combos == Standalone-Recompute (bit-identisch), Liste (_extract_partial_metrics) == Chart (_extract_chart_metrics) end_value identisch

### Files
- user_data/utils/database/repository.py



## [1.7.7] - 01.06.2026

### Fixed
- Chart eines Multi-Combo-Results zeigte keine Equity/Indikatoren — Recompute scheiterte an fehlendem rules_json
  - recompute_single_result und compute_full_metrics riefen den Spec-Runner ohne rules_json auf (positional, 3 Args); seit Ticket 12 ist rules_json Pflicht, daher ValueError 'rules_json fehlt' und /chart-data lieferte HTTP 500 (OHLC sichtbar, aber keine Equity/Indikatoren)
  - Beide Funktionen laden rules_json jetzt aus run.iteration.spec_json['rules'] und uebergeben es per inspect.signature-Guard (hartgecodete Strategien ohne rules_json-Parameter bleiben unveraendert) — analog zum Worker-Pfad
  - Pfad konnte vorher nie greifen, da Multi-Combo-Runs bis zum Cross-Fix (1.7.6) nicht liefen; verifiziert: /chart-data liefert nun Equity (4571 Punkte) und Indikatoren

### Files
- services/api/recompute.py



## [1.7.6] - 01.06.2026

### Fixed
- Multi-Indikator-Backtests mit disjunkten Parameter-Leveln brachen mit 'Cannot align indexes' ab — Cross-Produkt der Param-Spalten ergaenzt
  - rules_engine: Neuer cross-faehiger Combine. vbt.broadcast alignt nur gemeinsame/Teilmengen-Level; stammen Operanden aus Indikatoren mit disjunkten Param-Leveln (z.B. vwma-Kette vs. supertrend), gibt es keine gemeinsame Spalten-Achse und VBT scheiterte mit 'Cannot align indexes'
  - Loesung: bei Align-Fehler wird ein Ziel-Spalten-Index als Kartesisches Produkt der disjunkten Param-Level via vbt.base.indexes.cross_indexes gebaut und jeder Operand per columns_from dorthin expandiert; gemeinsame Carrier-Level wie 'symbol' bleiben aligned (werden nicht gekreuzt), Teilmengen-Operanden (fast_sma in vwma) werden vor dem Kreuzen herausgefaltet
  - rules_engine: Broadcast-Fehler liefern jetzt eine aussagekraeftige Meldung mit Operanden-Struktur (Shape, Param-Column-Level, Zeit-Index) statt nacktem 'Cannot align indexes'
  - spec_runner: VERSION Patch-Bump auf 1.0.2 — vorher gar nicht ausfuehrbare Multi-Combo-Specs laufen nun durch, Single-Combo unveraendert

### Files
- user_data/strategies/generic/rules_engine.py
- user_data/strategies/generic/spec_runner.py



## [1.7.5] - 01.06.2026

### Fixed
- Chart-Playground: Indikator-Inputs gehen beim Speichern nicht mehr verloren und Altlast-Felder werden sichtbar entfernt
  - Inputs (z.B. source, volume) werden beim Speichern einer Indikator-Konfiguration jetzt immer mit aufgeloesten Defaults serialisiert (analog buildBacktestPayload). Bisher wurden im UI nicht aktiv angefasste Default-Inputs weggelassen, wodurch source/volume nie persistiert wurden.
  - Unbekannte Param-Keys (Altlasten wie 'src', der alte Name fuer 'source') werden beim Speichern verworfen und in der Status-Zeile sichtbar gemeldet ('Altlast-Felder entfernt: ...'), statt still im Roundtrip Laden->Param->Speichern mitgeschleppt zu werden.
  - Behebt den Fehler 'vwma_pct_below_talib_inc() got an unexpected keyword argument src' beim Backtest, der durch ein gespeichertes src-Feld in der Indikator-Konfiguration verursacht wurde.
  - Bewusst kein Backend-Filter ergaenzt: Altlasten sollen sichtbar bleiben statt zur Laufzeit still geschluckt zu werden. Bereinigung wirkt erst beim naechsten manuellen Speichern der jeweiligen Config.

### Files
- services/frontend/templates/chart_playground/index.html



## [1.7.4] - 01.06.2026

### Fixed
- TestSet-Tab: Iterations-Dropdown sortiert jetzt nach version absteigend (hoch nach klein)
  - Gleiche Sortierung wie beim Einzel-Lauf: version DESC statt created_at

### Files
- services/frontend/templates/backtest/start.html



## [1.7.3] - 01.06.2026

### Fixed
- Backtest-Start-Seite: Iterations- und Indicator-Config-Dropdown sortieren jetzt absteigend (hoch nach klein)
  - Iterations-Dropdown sortiert nach version DESC statt created_at
  - Indicator-Config-Dropdown: serverseitige Sortierung nach is_default DESC, Iterations-Version DESC, name ASC
  - Bucket-Logik (exakter Concept/Iteration-Match zuerst) bleibt erhalten

### Files
- services/frontend/templates/backtest/start.html
- services/api/routes/api_config.py



## [1.7.2] - 01.06.2026

### Changed
- Backtest-Start-Seite leitet nach dem Start nicht mehr auf die Runs-Seite weiter, sondern bleibt stehen und zeigt eine Erfolgsmeldung
  - Einzel-Start-Button: Redirect auf /backtest/runs entfernt
  - Stattdessen gruene Erfolgsmeldung mit Run-Nummer und Link zu den Runs
  - Button wird nach dem Start wieder aktiviert

### Files
- services/frontend/templates/backtest/start.html



## [1.7.1] - 31.05.2026

### Fixed
- Results-Tabelle: Spalte Strategie sortiert jetzt nach Concept-Name und numerischer Iterations-Version (2, 3, 32, 42) statt lexikografisch nach strategy_name. Damit ist die Sortierung der Strategie-Spalte durchgaengig numerisch korrekt.

### Files
- services/api/routes/api_backtest.py



## [1.7.0] - 31.05.2026

### Added
- Native State-Exits per signal_func_nb (Ticket 35, Schritt 1)
  - evaluate_rules_native() in rules_engine.py: Hybrid-Split-Architektur — statische Conditions vorab als Boolean-Array, stateful Conditions (since_entry, entry_price, max/min) per Numba signal_func_nb mit echtem Trade-State aus last_pos_info
  - spec_runner.py ruft nativen Pfad automatisch wenn Exit-Gruppe State-Refs enthält; Masken-Pfad (Cooldown-Approximation) bleibt parallel erhalten
  - Numba-Kern _state_exit_signal_func_nb + _eval_stateful_conditions_nb: Mini-Interpreter fuer alle 6 Operatoren, AND/OR, alle 4 State-Primitive, Series-Bundle fuer OHLCV/Indikator-Operanden
  - N1: from_signals nutzt signal_func_nb statt entries/exits; alle Portfolio-Parameter (sl_stop, tp_stop, tsl_*, td_stop, fees, ...) bleiben identisch
  - N2: Kein uninitalisierter Puffer bei rein stateful Exit-Gruppen
  - N3: Verschachtelte Gruppen werden explizit abgewiesen; fehlerhafter 'rekursiv'-Docstring korrigiert
  - N4: shift auf OHLCV-/Indikator-Seite einer stateful Condition wird Python-seitig in series_bundle vorverlagert
  - N5: Multi-Combo mit Series-Operanden in stateful Conditions wird hard-abgewiesen (kein stilles Falschrechnen); State-Ref/Skalar-only Multi-Combo läuft
  - Guard: position_open = (status==0 AND entry_idx>=0) verhindert nan-Vergleich vor erstem Trade
  - Spike-Szenario verifiziert: since_entry >= 30 → nativ 15 Trades à exakt 30 Balken; alte Cooldown-Krücke (16) lieferte nur 1 Trade über 487 Balken
  - 35 neue pytest-Tests in tests/test_ticket35_native_state_exits.py: State-Ableitung, Mini-Interpreter alle Operatoren, Hybrid-Split AND/OR, Multi-Combo, Randfälle, Validierungen, Regressions-Tests

### Files
- user_data/strategies/generic/rules_engine.py
- user_data/strategies/generic/spec_runner.py
- tests/test_ticket35_native_state_exits.py



## [1.6.26] - 31.05.2026

### Added
- Equity-Tooltip im Chart-Playground: Klick auf die Equity-Linie zeigt ein Label mit dem aktuellen Equity-Wert (analog zur Result-Chart-Ansicht)
  - Wiederverwendbare Funktion ResultOverlay.attachEquityTooltip() im geteilten Modul overlay.js ausgelagert
  - Im Playground in createMainChart() eingebunden, liest die aktuelle Equity-Series via Getter
  - Tooltip-Element cpEquityTooltip im Chart-Container ergaenzt

### Files
- services/frontend/static/js/result/overlay.js
- services/frontend/templates/chart_playground/index.html



## [1.6.25] - 31.05.2026

### Added
- Chart-Playground-Setups speichern jetzt auch die Auswahl der Dropdowns Iteration, Backtest-Config und Indikator-Config und stellen sie beim Laden wieder ein
  - Beim Speichern werden die IDs der drei Dropdowns (cpIterationSelect, cpBacktestCfgSelect, cpIndCfgSelect) zusaetzlich in ui_state_json.selected_configs abgelegt
  - Beim Laden eines Setups werden die Dropdowns optisch wieder gesetzt, ohne change-Events auszuloesen - die gespeicherten Werte bleiben maßgeblich
  - Fehlende oder nicht mehr existierende IDs lassen das jeweilige Dropdown nur leer, das Setup bleibt funktionsfaehig (robust gegen geloeschte Configs)
  - Indikator-Config-Auswahl setzt zusaetzlich state.currentIndCfgId, damit die Ueberschreib-Bindung beim Speichern konsistent ist
  - Konzept-Dropdown wurde bereits zuvor wiederhergestellt (concept_slug)

### Files
- services/frontend/templates/chart_playground/index.html



## [1.6.24] - 31.05.2026

### Changed
- Slug aus der Versions-Spalte der Iterations-Subtabelle auf der Strategy-Concepts-Seite entfernt

### Files
- services/frontend/templates/config/strategy_concepts.html



## [1.6.23] - 31.05.2026

### Changed
- Indikator-Migrationen (Source-Prefix + enabled-Strip) auf alle Indikator-Dict-Tabellen ausgeweitet und angewendet
  - migrate_indicator_sources.py und migrate_strip_enabled.py decken jetzt neben IndicatorConfig auch ChartPlaygroundSetup, BacktestRun, TestSetRun und StrategyIteration.spec_json ab
  - Source-Prefix: 11 Eintraege eindeutig auf custom:/vbt: prefixt (0 mehrdeutig/unaufloesbar), DB durchgaengig prefixt
  - enabled-Strip: 80 Felder entfernt (enabled:true); enabled:false loescht den Eintrag in editierbaren Configs/Setups/Iterationen (chart_playground_setups ID=5: vwma+supertrend), bleibt aber in historischen Lauf-Snapshots BacktestRun/TestSetRun (testset_runs ID=186: nur Feld entfernt)
  - Beide Migrationen idempotent verifiziert (Re-Dry-Run zeigt 0 Aenderungen)
  - Veraltete Notiz in documentation/project/indicators.md korrigiert

### Files
- seed/migrate_indicator_sources.py
- seed/migrate_strip_enabled.py
- documentation/project/indicators.md



## [1.6.22] - 31.05.2026

### Added
- Chart-Playground: Setup speichern unter… belegt Name und Beschreibung automatisch vor
  - Name wird als <slug> <iterationsnummer> in lowercase vorgeschlagen (z.B. vwma 3)
  - Beschreibung kombiniert Konzept, Iterationsnummer, Exchange/Symbol/Timeframe und die verwendeten Indikatoren
  - Felder bleiben editierbar; ohne gewähltes Konzept/Iteration bleibt die Vorbelegung leer

### Files
- services/frontend/templates/chart_playground/index.html



## [1.6.21] - 31.05.2026

### Added
- Chart-Playground Schnellbacktest: Benchmark, Profitfaktor und Max-Drawdown im Ergebnis-Badge
  - Lite-Endpoint /api/chart-playground/run-backtest-lite liefert zusaetzlich benchmark_return, profit_factor und max_drawdown (billige Portfolio-Properties, kein teures pf.stats())
  - Schnellbacktest-Badge zeigt jetzt Total Return, Benchmark, Profitfaktor, Max DD, Trades und Rechendauer

### Files
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html



## [1.6.20] - 31.05.2026

### Added
- Chart-Playground Schnellbacktest: Benchmark, Profitfaktor und Max-Drawdown im Ergebnis-Badge
  - Lite-Endpoint /api/chart-playground/run-backtest-lite liefert zusaetzlich benchmark_return, profit_factor und max_drawdown (billige Portfolio-Properties, kein teures pf.stats())
  - Schnellbacktest-Badge zeigt jetzt Total Return, Benchmark, Profitfaktor, Max DD, Trades und Rechendauer

### Files
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html



## [1.6.19] - 31.05.2026

### Added
- Chart-Detailseite: Metrik-Kachel "Profitfaktor" zwischen Benchmark und Sharpe
  - Neue Kachel zeigt den Profitfaktor (result.profit_factor) in der Metrik-Leiste der Route /backtest/results/{id}/chart
  - profit_factor wird im View result_chart_page in result_data an das Template uebergeben

### Files
- services/frontend/templates/backtest/result_chart.html
- services/api/routes/views_backtest.py



## [1.6.18] - 30.05.2026

### Changed
- Iterations-Versionen auf fortlaufende Integer-Nummern pro Konzept umgestellt (High-Water-Mark, kein Reuse) und Chart-Playground entsprechend erweitert
  - strategy_iterations.version: String-Slug -> Integer; neue Spalte strategy_concepts.iteration_counter als High-Water-Mark (nur steigend, kein Reuse nach Loeschen); Alembic-Migration 0011
  - Bestandsdaten migriert (v2/v3/v32/v42 -> 2/3/32/42), Zaehler je Konzept auf das Maximum initialisiert; Vault-Iterations-Ordner und -Notizen umbenannt (z.B. vwma/iterations/v3 -> .../3)
  - Nummernvergabe zentral ueber next_iteration_version(); create-, copy-Endpoint und Auto-Registrierung (spec_iteration_registry) nutzen den Zaehler statt Slug/playchart-String
  - Chart-Playground: Card 'Strategie' -> 'Konzept-Iteration' umbenannt; Iterations-Dropdown numerisch sortiert und Draft-Iterationen ausgeblendet
  - Chart-Playground: 'Speichern' / 'Speichern unter...' fuer Konzept-Iterationen (Speichern unter zeigt die naechste freie Nummer vor)
  - Chart-Playground: 'Backtest starten' verwendet die gewaehlte Iteration und legt nichts mehr automatisch an; Schnellbacktest bleibt das direkte Editor-Ergebnis
  - Entfernt: Legacy-Lookup get_iteration_by_strategy_name samt Family/Version-Mappings und Auto-Lookup/Fallback in create_backtest_run; sync-slug-Endpoint

### Files
- user_data/utils/database/models.py
- alembic/versions/0011_iteration_version_int.py
- user_data/utils/database/repository_strategies.py
- user_data/utils/database/repository.py
- user_data/strategies/generic/spec_iteration_registry.py
- services/api/routes/api_strategy.py
- services/api/routes/api_chart_playground.py
- services/api/utils/obsidian_paths.py
- services/frontend/templates/chart_playground/index.html



## [1.6.17] - 30.05.2026

### Fixed
- Chart-Playground: Speichern-Buttons der Indikator-Konfiguration werden nur noch bei vorhandenen Indikatoren angezeigt
  - Speichern/Speichern-unter-Buttons im Indikatoren-Bereich sind ausgeblendet, solange keine Indikatoren vorhanden sind
  - Sichtbarkeit per setProperty(display, ..., important), da Tablers .d-flex (display:flex !important) ein normales Inline-Style ueberstimmt
  - Tooltip des Speichern-Buttons praezisiert: ueberschreibt die oben in der Leiste unter Indikator-Konfiguration gewaehlte Konfiguration

### Files
- services/frontend/templates/chart_playground/index.html



## [1.6.16] - 30.05.2026

### Fixed
- Ticket 34: Fehlermeldung fehlgeschlagener Backtest-Runs wird jetzt in der Child-Row der Runs-Tabelle angezeigt.
  - BacktestRunOut-Schema um error_message erweitert — das Feld wurde bisher nicht an die UI durchgereicht.
  - runs.html: formatDetails rendert bei status=failed eine rote Alert-Box mit der error_message oben in der Detail-Zeile (HTML-escaped, Zeilenumbrueche erhalten).
  - Verifiziert: failed-Run zeigt die Run-Start-Validierungsmeldung des Workers.

### Files
- services/api/schemas/__init__.py
- services/frontend/templates/backtest/runs.html



## [1.6.15] - 30.05.2026

### Fixed
- Ticket 34: Exit-/Entry-Bedingungen im Chart-Playground werden auch bei deaktivierten oder fehlenden Indikator-Referenzen sichtbar gerendert; Run bricht bei solchen Referenzen mit klarer Meldung ab.
  - Frontend (chart_playground): Referenzen auf deaktivierte/nicht vorhandene Indikatoren fallen nicht mehr still auf Konstante zurueck, sondern werden grau mit Tooltip 'Indikator deaktiviert' markiert (kein Silent-Fail).
  - Frontend: Deaktivierte Indikatoren werden nicht mehr als waehlbare Referenz im Dropdown angeboten (collectRefOptions filtert visible:false).
  - Worker (spec_runner): Neue Run-Start-Validierung _validate_rule_references bricht ab, wenn eine Regel einen deaktivierten (enabled:false) oder fehlenden Indikator referenziert; klare Fehlermeldung statt generischem Crash in rules_engine._resolve_ref.
  - spec_runner VERSION Patch-Bump auf 1.0.1 (keine Verhaltensaenderung fuer korrekte Specs).
  - Tests: 10 neue Unit-Tests fuer _collect_indicator_refs und _validate_rule_references.

### Files
- services/frontend/templates/chart_playground/index.html
- user_data/strategies/generic/spec_runner.py
- tests/test_spec_runner_rule_validation.py



## [1.6.14] - 30.05.2026

### Changed
- Tests in test_api_strategy.py an den aktuellen Code- und Datenstand angepasst (kein Produktionscode geaendert).
  - get_iteration_by_strategy_name-Tests (vwma_v2, vwma_v2_spec) sind jetzt self-seeding: sie legen Concept und Iteration aus den Code-Konstanten _FAMILY_TO_SLUG / _STRATEGY_NAME_TO_VERSION selbst an, statt persistierte Migrationsdaten zu erwarten. Integration-Marker entfernt, laufen jetzt im Default-Lauf.
  - API-Listen-Tests erwarten jetzt das vorhandene vwma-Konzept bzw. die Iteration v2 (vorher veraltet vwma-dws / v2.0).
  - Iterations-erzeugende API-Tests senden das pflichtige Feld version_name mit (vorher nur version, was zu HTTP 422 fuehrte).

### Files
- tests/test_api_strategy.py



## [1.6.13] - 30.05.2026

### Added
- Iterationen lassen sich jetzt direkt kopieren — neuer Copy-Endpoint plus Kopier-Button in der Iterations-Zeile auf der Strategie-Konzepte-Seite.
  - Neuer Endpoint POST /api/strategy/iterations/{id}/copy: dupliziert eine Iteration im selben Konzept mit identischem spec_json, spec_hash, type, import_path und parent_iteration_id (flache Duplizierung); Original bleibt unveraendert.
  - version_name bekommt den Zusatz (Kopie); bei Namenskollision wird automatisch durchnummeriert (Kopie 2, Kopie 3, ...), damit der UniqueConstraint (concept_id, version) nicht verletzt wird.
  - Kopier-Button (Icon) in der Iterations-Zeile unter /config/strategy-concepts zwischen Bearbeiten und Loeschen, im Stil der bestehenden Copy-Buttons.
  - Skill-Helper brief_ids.py (copy iter:X) nutzt jetzt den neuen Einzel-Endpoint statt GET+POST.

### Files
- services/api/routes/api_strategy.py
- services/frontend/templates/config/strategy_concepts.html
- .claude/skills/ds-strategie-session/scripts/brief_ids.py



## [1.6.12] - 30.05.2026

### Fixed
- v42 Iteration und BT Config #562 auf Referenz-Result #695198 ausgerichtet
  - BT Config #562: td_stop 8→18, end 2026→2022, Name auf '20/22' korrigiert
  - v42 spec_json: lhs_shift in beiden Entry-Bedingungen von 1→0 — mit lhs_shift=1 fehlten 2 Trades und ~94% Return (474% statt 568%)
  - Verifiziert: Run mit Config #562 + Indikator #1971 + Iteration v42 ergibt jetzt 568,44% / 74 Trades = exakt Result #695198

### Files
- documentation/changelog/changelog.md



## [1.6.11] - 30.05.2026

### Fixed
- Chart-Playground: Zwei Rendering-Bugs bei Indikator-/Rules-Darstellung behoben
  - Bug 1: renderRules() wird jetzt nach Indikator-Config-Laden aufgerufen — Entry-Bedingungen zeigten 'Konstante' statt Indikator-Referenzen wenn Iteration vor Indikator-Config geladen wurde
  - Bug 2: Source-Dropdown der Indikatoren zeigt jetzt alle anderen Indikatoren (nicht nur frühere) — VWMA source zeigte 'Open' statt 'indicator:fast_sma:result' weil fast_sma nach VWMA in der Liste stand

### Files
- services/frontend/templates/chart_playground/index.html



## [1.6.10] - 29.05.2026

### Fixed
- Playground Schnellbacktest: sl_stop-Default überschreibt Config-null nicht mehr
  - prefillPortfolioFromBacktestCfg nutzte != null als Filter — null-Werte aus der Config (z.B. sl_stop: null) wurden ignoriert, der Default sl_stop: 0.15 blieb aktiv
  - Fix: hasOwnProperty statt != null — alle in der Config vorhandenen Felder überschreiben jetzt den Default, auch wenn ihr Wert null ist
  - Ursache des 38.438% statt 155.586% Ergebnisses bei manueller Konfiguration im Playground

### Files
- services/frontend/templates/chart_playground/index.html



## [1.6.9] - 29.05.2026

### Fixed
- Rules-Engine: 2-Pass-Berechnung für State-Primitiven korrigiert Approximationsfehler bei Re-Entries
  - Neue Numba-Funktion _simulate_accepted_entries_2d: simuliert echte Trade-Akzeptanz basierend auf Exit-Signalen und td_stop statt festem Cooldown-Block
  - evaluate_rules führt jetzt zwei Passes durch wenn State-Refs genutzt werden: Pass 1 Cooldown-Approximation, Pass 2 Verfeinerung mit echten Exit-Signalen
  - _compute_entry_state akzeptiert optionalen exits-Parameter für den zweiten Pass
  - spec_runner VERSION auf 2.0.0 erhöht (Major: gleiche Spec kann andere Ergebnisse liefern)
  - Fehler: nach Early-Exit (z.B. since_entry==2) wurden Re-Entries bis td_stop blockiert statt sofort erlaubt — entry_price und since_entry für Re-Entries waren falsch
  - 10 neue Unit-Tests in tests/test_rules_engine_two_pass.py

### Files
- user_data/strategies/generic/rules_engine.py
- user_data/strategies/generic/spec_runner.py
- tests/test_rules_engine_two_pass.py



## [1.6.8] - 29.05.2026

### Fixed
- Chart Playground: State-Primitiven, Portfolio-Prefill und UX-Fixes
  - State-Primitiven since_entry und entry_price im Condition-Renderer als eigene Dropdown-Gruppe ergänzt — wurden vorher fälschlicherweise als 'Konstante' angezeigt
  - prefillPortfolioFromBacktestCfg gefixt: API liefert Portfolio-Felder flach (top-level), nicht als cfg.portfolio — Funktion liest jetzt aus cfg direkt
  - Setup-Dropdown: Schnellbacktest-Badge wird beim Wechsel zurückgesetzt und Schnellbacktest automatisch gestartet
  - CSS: .cp-status mit white-space:nowrap damit Status-Text nicht umbricht
  - Zahnrad-Button neben Löschen öffnet /config/playground in neuem Tab

### Files
- services/frontend/templates/chart_playground/index.html



## [1.6.7] - 29.05.2026

### Fixed
- Chart Playground: Entry/Exit-Rules werden beim Wechsel der Iteration automatisch geladen
  - cpIterationSelect-Change-Handler liest jetzt spec_json.rules der gewählten Iteration und setzt state.rules + renderRules()
  - state.iterations wird in loadIterationsForConcept gecacht, damit kein Extra-Fetch nötig ist
  - Status-Meldung zeigt an welche Iteration geladen wurde

### Files
- services/frontend/templates/chart_playground/index.html



## [1.6.6] - 29.05.2026

### Fixed
- Chart Playground: dwsVWMA und dwsCrossover Berechnungsfehler bei gespeicherten Setups behoben
  - _coerce_param() erkennt jetzt Listen und Range-Dicts aus Sweep-Runs und reduziert sie auf den skalaren Start-Wert, statt sie unverändert an factory.run() durchzureichen
  - create_setup_from_result() behandelt auch explizite Listen-Params korrekt (erstes Element statt kompletter Liste)
  - Behebt: 'Parameters at index 0 have length 7 that cannot be broadcast to 12' für dwsVWMA
  - Behebt: 'Referenzierter Indikator vwma noch nicht berechnet' für dwsCrossover (Folge-Fehler aus dem VWMA-Fehler)

### Files
- services/api/routes/api_chart_playground.py



## [1.6.5] - 29.05.2026

### Added
- Kurzbeschreibungsfeld für Strategie-Konzepte im Edit-Modal ergänzt
  - Textarea-Feld `description` im Modal-Dialog für Konzepte hinzugefügt
  - Edit-Button überträgt bestehende Beschreibung via data-description-Attribut
  - Save-Payload schickt description an PUT /api/strategy/concepts/{id}

### Files
- services/frontend/templates/config/strategy_concepts.html



## [1.6.4] - 29.05.2026

### Changed
- Chart Playground Toolbar in zwei Zeilen umstrukturiert
  - Zeile 1: alle Filter-Dropdowns (Konzept, Iteration, Backtest-Config, Exchange, TF, Symbol, Dates) und Aktions-Buttons in einer Zeile
  - Zeile 2: Chart-Buttons (TF, Nav, Fit, Lineal) links, Setup-Verwaltung (Dropdown, Speichern, Speichern unter, Löschen) rechts — als fester Block via ms-auto
  - Status-Anzeige in die rechte Gruppe integriert — verschiebt Buttons nicht mehr bei Text-Erscheinen
  - Candles-Anzeigen-Checkbox aus der Chart-Toolbar in neuen Tab Einstellungen verschoben
  - Neuer Tab Einstellungen in der Analyse-Tab-Leiste
  - Setup-Verwaltungs-Buttons auf btn-sm / form-select-sm verkleinert für einheitliche Höhe mit TF-Buttons
  - Chart-Toolbar-Strip über dem Chart entfernt (Border-Bottom-Leiste)

### Files
- services/frontend/templates/chart_playground/index.html



## [1.6.3] - 29.05.2026

### Fixed
- Vault-Ordner und Iterations-Dateinamen bei Konzept-Slug-Umbenennung synchronisieren
  - Vault-Ordner wird bei Slug-Änderung automatisch umbenannt (api_strategy.py: update_concept_endpoint)
  - Konzept-Notiz wird ebenfalls von {old-slug}-concept.md auf {new-slug}-concept.md umbenannt
  - Iterations-Notizen heißen jetzt {slug}-{version}.md statt {version}.md (obsidian_paths.py)
  - API-Container läuft als user 1000:1000 (tom) — Vault-Ordner entstehen nicht mehr als root
  - NUMBA_CACHE_DIR auf /tmp/numba_cache gesetzt damit Numba als non-root cachen kann

### Files
- services/api/routes/api_strategy.py
- services/api/utils/obsidian_paths.py
- docker-compose-local.yml



## [1.6.2] - 29.05.2026

### Changed
- Iterations-Löschung gibt bei Blockierung Blocker-Details zurück und bietet Force-Cascade-Option
  - GET-Blocker-Check vor Löschversuch statt IntegrityError-Catch
  - 409-Response enthält jetzt blockers-Dict mit Zählern (child_iterations, backtest_runs, backtest_results)
  - Neuer Query-Parameter force=true löscht alle abhängigen Datensätze per Cascade (inkl. Child-Iterationen rekursiv)
  - strategy_concepts.html: 409 zeigt Blocker-Info + confirm() für Force-Delete
  - strategy_iteration_edit.html: 409 zeigt Blocker-Info im Modal, Confirm-Button wechselt zu 'Alles löschen (Cascade)'

### Files
- user_data/utils/database/repository_strategies.py
- services/api/routes/api_strategy.py
- services/frontend/templates/config/strategy_concepts.html
- services/frontend/templates/config/strategy_iteration_edit.html



## [1.6.1] - 29.05.2026

### Changed
- Playground-Iterations-Registry und App-Guide überarbeitet
  - spec_iteration_registry: Präfix chart- → playchart- für Auto-Iterationen
  - spec_iteration_registry: Kurzbeschreibung aus Indikator-Namen wird beim Anlegen gespeichert (description-Feld)
  - spec_iteration_registry: concept_slug nicht mehr hardcoded auf vwma-dws — wird vom Aufrufer übergeben, Fallback bleibt für Abwärtskompatibilität
  - api_chart_playground: RunBacktestIn hat neues optionales Feld concept_slug
  - chart_playground/index.html: Konzept-Dropdown in Toolbar — lädt Konzepte via /api/strategy/concepts, wählt bei einem Konzept automatisch vor
  - app-guide.md: Walk-Forward-Beschreibung präzisiert (OOS-Check, kein Rolling-WF, Abgrenzung zu Testset)
  - app-guide.md: Workflow-Lauf als deprecated markiert und aus Übersichtstabelle entfernt
  - app-guide.md: Kern-Konzepte um Strategiekonzept ergänzt, Indicator-Config und Iteration korrigiert
  - iteration.md + AGENT_ENTRY.md: Versions-Schema vereinfacht zu v<NUMBER>[letter] (war dyn-v0.<MINOR>)
  - ds-strategie-session SKILL.md: liest beim Session-Start readme.md, short-term-memory.md, decisions.md als globalen Trading-Kontext

### Files
- user_data/strategies/generic/spec_iteration_registry.py
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html
- documentation/strategy-development/app-guide.md
- documentation/strategy-development/workflows/iteration.md
- documentation/strategy-development/AGENT_ENTRY.md
- .claude/skills/ds-strategie-session/SKILL.md



## [1.6.0] - 29.05.2026

### Added
- Strategie-Entwicklung Dokumentationsstruktur aufgebaut
  - PROCESS.md: Lebenszyklus end-to-end (Phasen 0-9, Rollen, Sonderfälle)
  - app-guide.md: Lauf-Modi Playground/Einzellauf/Testset/Walk-Forward/Workflow aus Code abgeleitet
  - AGENT_ENTRY.md: Verweise auf PROCESS.md und app-guide.md ergänzt
  - SKILL.md ds-strategie-session: status.md-Pfade aktualisiert
  - workflows/iteration.md, neue-strategie.md, setup-via-api.md: Dateinamen-Verweise aktualisiert
  - scripts/sync_iter_run.py: Helper-Skript für Vault-DB-Sync (Run/Result-IDs in Iter-Notiz)

### Files
- documentation/strategy-development/PROCESS.md
- documentation/strategy-development/app-guide.md
- documentation/strategy-development/AGENT_ENTRY.md
- .claude/skills/ds-strategie-session/SKILL.md
- scripts/sync_iter_run.py



## [1.5.1] - 28.05.2026

### Added
- vault_reindex_runs: JSONB-Spalte files_changed mit reindexierten und gelöschten Vault-Pfaden pro Lauf
  - Alembic-Migration 0010: files_changed JSONB nullable auf vault_reindex_runs
  - Model VaultReindexRun: files_changed = Column(_JsonbCompat, nullable=True)
  - Indexer reindex(): reindexed_paths und deleted_paths im Return-Dict
  - worker_tasks.py reindex_vault_chunk_job: setzt files_changed = {reindexed, deleted} beim Erfolgs-Update; NULL bei Exception
  - API GET /api/knowledge/runs/{id}: files_changed im Response-Schema (KnowledgeRunSchema)
  - Frontend run_detail.html: Sektion Geaenderte Dateien mit ausklappbaren Listen (details/summary)
  - Tests test_reindex_files_changed.py: 6 neue Tests fuer alle Szenarien

### Files
- alembic/versions/0010_vault_reindex_runs_files_changed.py
- user_data/utils/database/models.py
- services/vbt/knowledge/indexer.py
- services/api/worker_tasks.py
- services/api/schemas_knowledge_runs.py
- services/frontend/templates/knowledge/run_detail.html
- services/api/tests/test_reindex_files_changed.py



## [1.5.0] - 28.05.2026

### Added
- Ticket 33 — Vault-Indexer Cleanup-Paket: Sentinel-Row, Reset-Button und Worker-Architektur
  - Teil A — Sentinel-Row: Stub-Dateien (0 Chunks) erhalten eine Marker-Row in vault_chunks (chunk_index=0, content='', embedding=NULL, file_sha1 gesetzt). Der Content-Hash-Skip aus Ticket 32 erkennt sie und überspringt sie bei Folge-Läufen.
  - Teil A — Migration 0009_embedding_nullable: vault_chunks.embedding und content sind jetzt nullable.
  - Teil A — Such-/Listing-Endpoints filtern Sentinel-Rows (WHERE embedding IS NOT NULL).
  - Teil B — DELETE /api/knowledge/reset: leert vault_chunks und vault_reindex_runs in einer Transaktion, gibt Counts zurück.
  - Teil B — Reset-Button im Page-Header von /knowledge/runs mit Tabler-Modal-Bestätigung.
  - Teil C — worker_start.py und vault_scheduler.py gelöscht; Verantwortlichkeiten aufgeteilt.
  - Teil C — recovery_oneshot.py: One-Shot Recovery (running -> queued) als eigener worker-init-Service.
  - Teil C — enqueue_reindex.py: Standalone-Script für den Scheduler-Container.
  - Teil C — services/scheduler/Dockerfile + crontab: dedizierter cron-Container, alle 5 Minuten genau ein Reindex-Job.
  - Teil C — docker-compose-local.yml, staging.yml, .yml umgebaut: YAML-Anchor worker-base, worker mit deploy.replicas, worker-init mit restart=no, scheduler-Service, worker2 entfernt.
  - Tests: test_indexer_sentinel.py (8), test_recovery_oneshot.py (4), test_enqueue_reindex.py (5), test_knowledge_reset.py (3).

### Files
- services/vbt/knowledge/indexer.py
- services/api/recovery_oneshot.py
- services/api/enqueue_reindex.py
- services/api/routes/api_knowledge.py
- services/frontend/templates/knowledge/runs.html
- services/scheduler/Dockerfile
- services/scheduler/crontab
- docker-compose-local.yml
- docker-compose-staging.yml
- docker-compose.yml
- alembic/versions/0009_vault_chunks_embedding_nullable.py
- user_data/utils/database/models.py
- services/api/tests/test_indexer_sentinel.py
- services/api/tests/test_recovery_oneshot.py
- services/api/tests/test_enqueue_reindex.py
- services/api/tests/test_knowledge_reset.py



## [1.4.2] - 28.05.2026

### Added
- Vault-Indexer: Content-Hash-Skip statt reiner mtime-Vergleich (Ticket 32)
  - Neue Spalte file_sha1 (VARCHAR(40)) auf vault_chunks — speichert SHA1-Hash des Datei-Inhalts pro Chunk
  - Alembic-Migration 0008_vault_chunks_file_sha1: ALTER TABLE vault_chunks ADD COLUMN file_sha1
  - VaultChunk-Model in models.py um file_sha1-Feld erweitert (String(40), nullable=False, default='')
  - Indexer: _compute_file_hash() Hilfsfunktion (SHA1, blockweise 64KB-Lesen)
  - _get_db_mtime_map ersetzt durch _get_db_file_state_map — liefert (mtime, sha1) via chunk_index=0
  - _bump_mtime_only() aktualisiert mtime aller Chunks eines vault_path ohne Embeddings zu berechnen
  - Skip-Logik: Fast-Path bei mtime<=db_mtime, Hash-Check bei neuerer mtime, mtime-Update bei identischem Hash
  - Pre-existing Rows mit file_sha1='' matchen nie als unchanged — Backwards-Compat gewährleistet
  - files_unchanged als Result-Feld im Return-Dict (nicht in DB persistiert)
  - 7 neue Tests in test_indexer_content_hash.py (Touch-Skip, Fast-Path, echte Content-Änderung, Erstes Indexieren, Backwards-Compat)
  - Abnahme verifiziert: files_unchanged=1 im Live-Job-Result nach Touch von OVERVIEW.md

### Files
- alembic/versions/0008_vault_chunks_file_sha1.py
- user_data/utils/database/models.py
- services/vbt/knowledge/indexer.py
- services/api/tests/test_indexer_content_hash.py
- services/api/tests/test_indexer_mount_guard.py



## [1.4.1] - 28.05.2026

### Fixed
- Vault-Indexer: Mount-Guard gegen unbeabsichtigtes Mass-Delete bei fehlendem Bind-Mount (Ticket 31)
  - Schritt A: vault_root-Existenzprüfung direkt nach _get_engine(), vor jedem weiteren Code — RuntimeError mit logger.critical wenn vault_root fehlt oder kein Verzeichnis ist
  - Schritt B: Prüfung auf leere .md-Dateiliste beim Voll-Reindex — RuntimeError wenn vault_root zwar existiert, aber keine Dateien liefert (Mount kurzzeitig weg)
  - Lazy-Imports (chunker, embedding) nach den Guards verschoben, damit die Guards ohne Abhängigkeiten feuern können
  - Neue Tests: 5 Fälle (nicht-existenter vault_root, leerer vault_root, vault_root weg + target_path, Single-File-Cleanup, Normalfall) — alle grün ohne echte DB oder Embedding-Calls
  - Exception-Propagation zu reindex_vault_chunk_job (status=failed, error_message) durch bestehenden Ticket-28-Code bereits abgedeckt

### Files
- services/vbt/knowledge/indexer.py
- services/api/tests/test_indexer_mount_guard.py



## [1.4.0] - 28.05.2026

### Added
- Vault-Knowledge-Dashboard: GET /api/knowledge/stats + Übersichts-Seite /knowledge (Ticket 30)
  - GET /api/knowledge/stats: aggregierte Index-Statistiken (chunk_count, file_count, vault_size_bytes, avg_chunks_per_file, Zeitstempel) und Lauf-Statistiken (by_status/by_trigger inkl. 0-Eintraege, last_run/success/failure_at, Durchschnittswerte letzte 10 Erfolge)
  - Neues Pydantic-Schema in services/api/schemas/knowledge_stats.py (KnowledgeIndexStats, KnowledgeRunsStats, KnowledgeTopPathEntry, KnowledgeStatsResponse)
  - Frontend-Seite /knowledge mit 4 KPI-Karten (Chunks, Dateien, Läufe, Erfolgsquote mit Farb-Schwellen), Index-Karte, Runs-Karte, Top-10-Tabelle nach Chunk-Anzahl
  - Auto-Refresh alle 15s solange running>0 oder queued>0, danach Polling gestoppt
  - Sidebar-Dropdown: Eintrag Übersicht (/knowledge) als erster Sub-Eintrag vor Reindex-Verlauf eingefügt
  - Tests: services/api/tests/test_knowledge_stats.py mit 9 Tests (Schema-Vollständigkeit, leerer Index, keine Erfolge, by_status/by_trigger, Top-Pfade, Durchschnittswerte)

### Files
- services/api/routes/api_knowledge.py
- services/api/routes/views_knowledge.py
- services/api/schemas/knowledge_stats.py
- services/frontend/templates/knowledge/dashboard.html
- services/frontend/templates/base.html
- services/api/tests/test_knowledge_stats.py



## [1.3.0] - 28.05.2026

### Added
- Vault-Reindex Frontend: Wissens-Index-Seiten und GET /api/knowledge/files Endpoint (Ticket 29)
  - Navbar: Wissens-Index-Dropdown mit Sub-Eintraegen Reindex-Verlauf (/knowledge/runs) und Indizierte Dateien (/knowledge/files)
  - GET /api/knowledge/files: aggregierte Datei-Liste aus vault_chunks mit q/tag/limit/offset-Filterung
  - Seite /knowledge/runs: DataTables-Tabelle mit Status-Badges (queued/running/success/failed), Auto-Refresh alle 10s solange aktive Laeufe, Reindex-starten-Button mit Toast, Aktualisieren-Button
  - Seite /knowledge/runs/{id}: Detail-Karte mit allen Feldern, chunks_per_second-Zeile, Fehlermeldung als Alert, Zurueck-Link im Page-Header rechts
  - Seite /knowledge/files: DataTables-Tabelle mit Suchfeld und Tag-Multi-Select-Filter
  - 5 neue Tests in services/api/tests/test_knowledge_files.py (q-Filter, Tag-Filter, Pagination, leere DB)

### Files
- services/api/routes/api_knowledge.py
- services/api/routes/views_knowledge.py
- services/api/schemas/knowledge_files.py
- services/api/app.py
- services/frontend/templates/base.html
- services/frontend/templates/knowledge/runs.html
- services/frontend/templates/knowledge/run_detail.html
- services/frontend/templates/knowledge/files.html
- services/api/tests/test_knowledge_files.py



## [1.2.0] - 28.05.2026

### Added
- Ticket 28: Vault-Reindex-Job-History — Persistenz und API
  - Neue Tabelle vault_reindex_runs mit vollstaendigem Status-Lifecycle (queued/running/success/failed)
  - Alembic-Migration 0007_vault_reindex_runs
  - reindex_vault_chunk_job erweitert: Pre-Insert via API und Scheduler, Lifecycle-Updates, Ergebnis-Felder aus Indexer-Dict
  - POST /api/knowledge/reindex legt Run sofort mit status=queued an (trigger=api)
  - Scheduler-Enqueue setzt trigger=scheduler mit Pre-Insert
  - GET /api/knowledge/runs: Liste mit Filter status/scope und Limit
  - GET /api/knowledge/runs/{id}: Einzel-Lauf mit berechnetem chunks_per_second
  - Pydantic-Schemas in services/api/schemas_knowledge_runs.py
  - 13 neue Tests in services/api/tests/test_knowledge_runs.py

### Files
- user_data/utils/database/models.py
- alembic/versions/0007_vault_reindex_runs.py
- services/api/worker_tasks.py
- services/api/routes/api_knowledge.py
- services/api/vault_scheduler.py
- services/api/schemas_knowledge_runs.py
- services/api/schemas/__init__.py
- services/api/tests/test_knowledge_runs.py
- services/api/tests/test_knowledge.py



## [1.1.2] - 28.05.2026

### Fixed
- Ticket 27 — PyYAML-Blocker behoben, Vault-Mount korrigiert, Initial-Reindex und Smoketest erfolgreich
  - PyYAML==6.0.2 explizit in services/vbt/requirements.txt ergaenzt (war fehlende transitive Dep, import yaml schlug im Worker-Container fehl)
  - Vault-Mount in docker-compose-local.yml von WSL-internem Pfad auf Windows-Env-Var ${TRADING_VAULT_HOST_PATH} umgestellt (Docker Desktop WSL2-Backend braucht Windows-Pfade, analog zu OBSIDIAN_VAULT_HOST_PATH)
  - TRADING_VAULT_HOST_PATH=<Vault>\30_Trading in .env ergaenzt
  - VBT-Base-Image und Worker-Images neu gebaut und gestartet
  - Vollindex: 27 Dateien, 193 Chunks, 17.56 s, 10.99 Chunks/s (-15.5% vs. MIRACL-DE-Benchmark, innerhalb +-30%)
  - Smoketest 5/5 PASS: 4 Trading-Queries 0.71-0.76 Similarity, Espresso-Kontrolle 0.60 (Spread ~0.14)
  - Performance-Doku in Vault-Note 50_Company/staging/ki-benchmark-tests/embedding-benchmark/embedding-benchmark-index.md ergaenzt

### Files
- services/vbt/requirements.txt
- docker-compose-local.yml
- .env



## [1.1.1] - 28.05.2026

### Added
- Ticket 26 — Vault-Vektorisierung: REST-Endpoints GET /api/knowledge/search und POST /api/knowledge/reindex
  - GET /api/knowledge/search: semantische Cosine-Distance-Suche ueber vault_chunks (bge-m3, 1024-dim HNSW), Top-K Treffer DESC sortiert nach Similarity
  - Filter: tag (JSONB-Array, ODER-Verknuepfung via jsonb_array_elements_text), path_prefix (LIKE)
  - POST /api/knowledge/reindex: reiht reindex_vault_chunk_job in recompute-Queue ein, antwortet sofort mit job_id (Status 202)
  - Neue Route-Datei services/api/routes/api_knowledge.py mit Pydantic-Schemas (inline, konsistent zum Codebase-Stil)
  - Router in services/api/app.py registriert unter Prefix /api/knowledge
  - 10 Pytest-Tests in services/api/tests/test_knowledge.py: Struktur, Felder, Similarity-Sortierung, Tag-Filter, path_prefix-Filter, k-Limit, Leer-Ergebnis, Reindex full/single-file/leer
  - rq lazy importiert (fehlt im Windows-venv); embed() auf Modul-Ebene fuer Monkeypatch; CAST()-Syntax statt ::-Operator (psycopg2-Kompatibilitaet)

### Files
- services/api/routes/api_knowledge.py
- services/api/app.py
- services/api/tests/conftest.py
- services/api/tests/test_knowledge.py



## [1.1.0] - 28.05.2026

### Added
- Ticket 25 — Vault-Vektorisierung: Embedding-Client, Markdown-Chunker und Indexer-Worker
  - services/vbt/knowledge/embedding.py: HTTP-Client fuer bge-m3-Backend auf staging (1024-dim, Timeout 30s, Env-Var EMBEDDING_BACKEND_URL)
  - services/vbt/knowledge/chunker.py: Markdown-Chunker mit H2/H3-Split, heading_path-Hierarchie, Code-Block-Schutz, Hard-Split bei ~1000 Tokens, Frontmatter-Parse via pyyaml
  - services/vbt/knowledge/indexer.py: Inkrementeller Reindex via mtime-Vergleich, Loeschen verwaister Chunks, CLI-Einstieg via python -m services.vbt.knowledge.indexer
  - services/api/vault_scheduler.py: Daemon-Thread der alle 5 Minuten reindex_vault_chunk_job in die recompute-Queue einreiht
  - services/api/worker_tasks.py: reindex_vault_chunk_job() als enqueue-bare RQ-Task
  - services/api/worker_start.py: Vault-Scheduler-Thread wird vor RQ-Worker-Start gestartet (Subprocess-Muster statt execvp)
  - docker-compose-local.yml: Vault-Bind-Mount <Vault>/30_Trading:/vault/trading:ro fuer worker-Service
  - docker-compose-staging.yml: Mount auskommentiert (Vault auf staging nicht verfuegbar, Kommentar mit Handlungsoptionen), EMBEDDING_BACKEND_URL gesetzt
  - requirements.txt: python-frontmatter==1.3.0 ergaenzt
  - tests/test_chunker.py: 18 Unit-Tests fuer Chunker (alle gruen)

### Files
- services/vbt/knowledge/__init__.py
- services/vbt/knowledge/embedding.py
- services/vbt/knowledge/chunker.py
- services/vbt/knowledge/indexer.py
- services/api/vault_scheduler.py
- services/api/worker_tasks.py
- services/api/worker_start.py
- docker-compose-local.yml
- docker-compose-staging.yml
- requirements.txt
- tests/test_chunker.py



## [1.0.176] - 28.05.2026

### Added
- Ticket 24 — Vault-Vektorisierung: pgvector-Schema und SQLAlchemy-Modell VaultChunk
  - pgvector 0.8.1 (bereits im timescale/timescaledb:latest-pg17 Image enthalten) via Extension aktiviert
  - Tabelle vault_chunks mit allen Pflichtfeldern: id, vault_path, chunk_index, heading_path, content, frontmatter_json, mtime, embedding vector(1024), indexed_at
  - HNSW-Index vault_chunks_embedding_hnsw (vector_cosine_ops) fuer Cosine-Similarity-Suche
  - B-Tree-Index ix_vault_chunks_vault_path fuer inkrementellen Reindex
  - Unique-Constraint uq_vault_chunks_path_index auf (vault_path, chunk_index)
  - Alembic-Migration 0006_vault_chunks_pgvector mit Up/Down
  - SQLAlchemy-Modell VaultChunk in models.py mit _VectorCompat TypeDecorator (pgvector in Produktion, JSON-Fallback in SQLite-Tests)
  - pgvector==0.3.6 Python-Paket in requirements.txt eingetragen
  - Import-Smoketest tests/test_vault_chunk_model.py (4 Tests gruen)

### Files
- user_data/utils/database/models.py
- alembic/versions/0006_vault_chunks_pgvector.py
- requirements.txt
- tests/test_vault_chunk_model.py



## [1.0.175] - 28.05.2026

### Added
- Helper-Script und Skill zum gebuendelten Einlesen von vbt_app-Konfigurationen via URLs oder typ:id-Kurzformen
  - Neues Script tools/brief_ids.py: akzeptiert Frontend-URLs und/oder typ:id-Kurzformen (iter, indicator/ind, bt/backtest, result/res, run), parst sie, ruft die existierenden API-Endpunkte und druckt ein kompaktes Markdown-Briefing aller referenzierten Objekte in einem Call
  - Neuer Skill /ds_brief_ids unter .claude/skills/ds_brief_ids/SKILL.md, der das Script im Slash-Command-Workflow ausloest und die Ausgabe wortwoertlich an den User zurueckgibt
  - Spart pro LLM-Session ~4-5 Einzel-Curls beim Einlesen mehrerer Konfigurationen (Iteration + Indicator-Config + Backtest-Configs + Results)
  - Anlass: Re-Run von vwma-dws v2.0-dyn-v0.32e (Iter 26, Indicator 1970, Backtest-Configs 552/553) zeigte den Workflow-Aufwand

### Files
- tools/brief_ids.py
- .claude/skills/ds_brief_ids/SKILL.md



## [1.0.174] - 28.05.2026

### Changed
- Skill ds_strategie_session ins Projekt-Repo verschoben und Ablauf auf Discovery-First umgestellt (Korrektur zu v1.0.173)
  - Skill liegt jetzt unter .claude/skills/ds_strategie_session/ statt im globalen ~/.claude/skills/ - damit projekt-scoped neben den anderen Projekt-Skills (changelog, code-review, gemini_*, handoff)
  - Kein Slug-Argument mehr noetig: Phase 1 scannt user_data/strategies/ und 30_Trading/strategies/, matched Snake/Kebab-Case, ermittelt pro Strategie Status (aus concept.md) und letzte Aktivitaet (juengste mtime ueber STATUS.md + Vault-Iterationen)
  - Phase 2 gibt Konzept-Uebersicht als Tabelle aus mit Markierung der zuletzt bearbeiteten Strategie, fragt dann mit welcher weitergearbeitet werden soll (Default = letzte)
  - Phase 3 erst nach User-Entscheidung: 5-Block-Briefing zur gewaehlten Strategie + eine Anschluss-Frage
  - Korrektur des Hinweises in v1.0.173: Skill liegt im Projekt-Repo, nicht ausserhalb



## [1.0.173] - 28.05.2026

### Added
- Workflow `setup-via-api.md` fuer Setup-Anlage und Backtest-Ausfuehrung via API ergaenzt
  - Drei Bedienungs-Muster dokumentiert: Ad-hoc Backtest (run-backtest), Setup persistieren (setups POST), Setup aus Result forken (setups/from-result)
  - Konvertierungs-Snippet config_json (Setup) -> run-backtest Payload, weil die Indikator-Strukturen unterschiedlich sind (Liste vs Dict)
  - AGENT_ENTRY.md um den neuen Workflow ergaenzt
  - Begleitend (ausserhalb des Projekt-Repos): Skill /ds_strategie_session unter ~/.claude/skills/ - briefed eine frische Session anhand STATUS.md + letzter Vault-Iter-Notiz + Konzept



## [1.0.172] - 28.05.2026

### Changed
- Strategie-Entwicklungs-Doku auf neue Struktur umgestellt (AGENT_ENTRY + guide + workflows + STATUS-pro-Strategie, Iter-Logs in den Vault verlagert)
  - Neuer Ordner documentation/strategy-development/ mit AGENT_ENTRY.md als Pflicht-Read, guide.md als Mechanik-Referenz und sechs aufgaben-fokussierten Workflows (iteration, neue-strategie, parameter-sweep, cross-symbol-sweep, pine-reproduktion, custom-indikator)
  - Alte Monolithen STRATEGY_DEVELOPMENT_GUIDE.md, STRATEGY_DYNAMIC.md und STRATEGY_DYNAMIC_ONBOARDING.md nach documentation/strategy-development/_legacy/ verschoben (Read-Only, nicht mehr editieren)
  - Pro Strategie kompakter Status-Anker user_data/strategies/<slug>/STATUS.md - VWMA-Dynamic befuellt mit Bestvariante-Profilen, Mess-Tracks, Backlog, Nicht-anfassen-Liste
  - Vault-Niederschlag: fuenf Lessons (tail-edge, exit-vs-entry-filter, regime-vs-trade-filter, pine-drift-meta-lesson, cross-symbol-param-discovery) und zwei kanonische Iter-Anker (v1.0-pine-original, v2.0-dyn-v0.32e) unter <Vault>/30_Trading/strategies/vwma-dws/
  - CLAUDE.md auf neue Doku-Struktur umgestellt - Pflicht-Read ist jetzt documentation/strategy-development/AGENT_ENTRY.md



## [1.0.171] - 28.05.2026

### Added
- Chart-Playground Schnellanalyse zeigt Trade-Marker mit Entry/Exit/PnL im Chart
  - Lite-Endpoint /run-backtest-lite liefert zusaetzlich trades_data im Format des /trades-Endpoints (entry_time/exit_time, entry_price/exit_price, return_pct, pnl, exit_stop_type aus pf.orders Stop-Type, tp_price/sl_price aus Portfolio-Eingabeparametern)
  - Frontend rendert die Trade-Marker (Entry/Exit-Punkte, gepunktete Dauer-Linie, grueneRote Zone, PnL-Label, Tooltip) ueber das bestehende ResultOverlay.renderTradeMarkers direkt nach der Schnellanalyse
  - Bestehende Trade-Marker werden vor jedem Lite-Lauf entfernt, damit Wiederhol-Klicks die Marker sauber ersetzen
  - Tooltip-Element wird wiederverwendet wenn vorhanden, sonst neu angelegt — verhindert DOM-Leak bei mehrfachem Klick
  - Weiterhin keine DB-Persistierung im Lite-Lauf

### Files
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html



## [1.0.170] - 28.05.2026

### Changed
- Chart-Playground: Layout-Feinschliff in der Strategie-Sektion
  - Bedingungs-Reihen unter Entry/Exit bekommen mehr Abstand (gap und margin-bottom erhöht) für bessere Lesbarkeit
  - Label 'Konstante...' im LHS/RHS-Dropdown zu 'Konstante' verkürzt
  - Alle number-Inputs (Konstante, Shift, Indikator-Parameter, Portfolio-Felder) zentriert ausgerichtet statt linksbündig

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.169] - 28.05.2026

### Fixed
- Schnellanalyse: Equity-Kurve wurde nicht ausgeliefert weil pf.value ein DataFrame war
  - Im Lite-Endpoint war pf das Multi-Combo-Wrapper-Portfolio; pf.value liefert dann eine DataFrame und .items() iteriert Spalten statt Zeilen, sodass equity leer blieb
  - Wie in save_strategy_results auf die erste Kombi reduzieren (portfolios[columns[0]]) bevor pf.value ausgelesen wird
  - Damit liefert /run-backtest-lite jetzt tatsaechlich eine equity-Liste und das Frontend rendert die Kurve am Chart

### Files
- services/api/routes/api_chart_playground.py



## [1.0.168] - 28.05.2026

### Fixed
- Chart-Playground /compute: Indikator-Reihenfolge wird per Topo-Sort aufgeloest
  - Wenn ein Indikator (z.B. dwsVWMA) einen anderen Indikator (z.B. fast_sma) via inputs referenziert, aber im Frontend-Array nach diesem steht, scheiterte er bisher mit 'Referenzierter Indikator <name> noch nicht berechnet'
  - Backend sortiert die Indikatoren jetzt vor der Berechnung topologisch nach indicator:<name>:<out>-Referenzen, sodass Abhaengigkeiten unabhaengig von der Array-Reihenfolge zuerst berechnet werden
  - Bei Zyklen oder fehlenden Dependencies bleibt das urspruengliche Fehlerverhalten erhalten (Indikator landet im errors-Array mit klarer Meldung)

### Files
- services/api/routes/api_chart_playground.py



## [1.0.167] - 28.05.2026

### Added
- Chart-Playground Schnellanalyse zeigt Equity-Kurve im Chart
  - Lite-Endpoint /run-backtest-lite liefert zusaetzlich eine equity-Liste aus pf.value (Format identisch zu /chart-data: time als epoch_seconds, value als float)
  - Frontend rendert die Equity-Kurve nach Lite-Lauf ueber das bestehende ResultOverlay.renderEquityCurve als Overlay-Series am Haupt-Chart, identisch zum vollen Lauf
  - Bestehende Equity-Series wird vor jedem Lite-Lauf entfernt, damit wiederholte Klicks die Kurve sauber ersetzen
  - Weiterhin keine DB-Persistierung im Lite-Lauf - Equity wird ausschliesslich inline in der Response transportiert

### Files
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html



## [1.0.166] - 28.05.2026

### Changed
- Chart-Playground: Layout-Refactor mit Card-Aufteilung und formatiertem Total Return
  - Action-Buttons (Schnellanalyse, Backtest starten) in Strategie-Card-Header verschoben, Apply rechts in Tab-Leiste
  - Indikatoren und Strategie als zwei nebeneinanderliegende Cards (col-md-6) statt untereinander
  - Portfolio-Panel als eigene Card mit Header gerendert
  - Total Return in Result-Panel und Schnellanalyse-Badge als formatierte Prozentzahl mit de-DE-Locale (Tausendertrenner)

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.165] - 27.05.2026

### Changed
- Chart-Playground: Schnellanalyse/Backtest-Buttons in obere Action-Zeile verschoben, Lite-Badge-Kontrast verbessert

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.164] - 27.05.2026

### Added
- Ticket 23: Schnellanalyse-Button (Lite-Backtest) im Chart-Playground
  - Neuer Endpoint POST /api/chart-playground/run-backtest-lite: fuehrt run_spec_strategy aus ohne DB-Persistierung (kein create_backtest_run, save_strategy_results, register_or_get_iteration)
  - Response: {data: {total_return, trades, duration_ms}, error: null} — total_return und trades identisch zur vollen Pipeline
  - Refactoring: _build_backtest_config(req) Helper extrahiert, beide Endpoints /run-backtest und /run-backtest-lite nutzen ihn (DRY)
  - Frontend: Schnellanalyse-Button neben Backtest starten (Tabler-Secondary-Style), Badge mit Total Return / Trades / Dauer (gruen/rot je nach Vorzeichen)
  - Frontend: Lite-Badge wird beim Klick auf Backtest starten entfernt; Doppelklick-Schutz via disabled; Timeout teilt CP_BACKTEST_TIMEOUT_MS
  - Frontend: Pre-Check-Logik (_cpPreChecks) in gemeinsame Funktion extrahiert, beide Buttons nutzen sie (DRY)
  - Tests: Happy Path, 400/500-Fehlerfall, DB-Isolations-Assertion (SELECT count(*) unveraendert nach 3 Lite-Calls), Equivalenz-Assertion (Lite total_return == Full total_return)

### Files
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html
- tests/test_ticket23_lite_backtest.py



## [1.0.163] - 27.05.2026

### Added
- Iteration-Edit: "Slug anpassen"-Button erscheint, sobald der aus dem Namen abgeleitete Slug vom aktuellen abweicht
  - Neuer Endpoint POST /api/strategy/iterations/{id}/sync-slug — aktualisiert version auf normalize_version(version_name) und benennt den Obsidian-Iterations-Ordner samt .md-Datei und Frontmatter um, falls vorhanden
  - Frontend-Button im Edit-Form bleibt versteckt, solange Name und Slug zueinander passen; bei Abweichung erscheint er im Slug-Input-Group
  - Konfliktcheck: Sync bricht mit 409 ab, wenn der neue Slug bereits von einer anderen Iteration im selben Concept belegt ist
  - Vor dem Sync wird der aktuelle Name via PUT persistiert, damit der Endpoint den richtigen version_name als Quelle nutzt

### Files
- services/api/routes/api_strategy.py
- services/frontend/templates/config/strategy_iteration_edit.html



## [1.0.162] - 27.05.2026

### Added
- Iteration: separates version_name-Feld als editierbarer Anzeige-Name; version bleibt fixer Slug fuer Vault-Pfad
  - Migration 0005_iteration_version_name fuegt Spalte version_name (VARCHAR 100, nullable) zu strategy_iterations hinzu; Bestand mit version backfillt
  - API: StrategyIterationOut liefert version_name; Create akzeptiert version_name (Pflicht) und leitet version daraus per normalize_version ab; Update akzeptiert version_name (version bleibt nach Create fix)
  - Edit-Template strategy_iteration_edit.html: Name-Feld ist editierbar, Slug (= version) wird schreibgeschuetzt darunter angezeigt und im Create-Modus live aus dem Namen abgeleitet
  - Anzeigen in strategy_concepts.html, backtest/start.html, indicator_config_edit.html, sowie API-Lookups (api_config _load_concept_iteration_maps, api_backtest iteration_version) bevorzugen jetzt version_name mit Fallback auf version
  - Versions-Rename-Logik fuer Obsidian-Ordner im Update-Endpoint entfernt (nicht mehr noetig, da version immutable)

### Files
- alembic/versions/0005_iteration_version_name.py
- user_data/utils/database/models.py
- services/api/routes/api_strategy.py
- services/api/routes/api_config.py
- services/api/routes/api_backtest.py
- services/api/routes/views_config.py
- services/frontend/templates/config/strategy_iteration_edit.html
- services/frontend/templates/config/strategy_concepts.html
- services/frontend/templates/config/indicator_config_edit.html
- services/frontend/templates/backtest/start.html



## [1.0.161] - 27.05.2026

### Changed
- Sortierung und Aktionsbuttons in Backtest-Übersichten überarbeitet
  - Backtest Results: Default-Sortierung von Return % auf ID desc (neueste zuerst)
  - Backtest Runs: Analyse-Button in der Aktionsspalte als Icon (Tabler chart-histogram) rechts neben Tests

### Files
- services/frontend/templates/backtest/results.html
- services/frontend/templates/backtest/runs.html



## [1.0.160] - 27.05.2026

### Changed
- Leaderboard-Child-Row zeigt zusaetzlich Executive Summary und Mini-Report
  - Child-Row im Leaderboard rendert drei Bloecke (Hint, Executive Summary, Mini-Report) mit Trenner und mehr Abstand
  - LeaderboardEntryOut um Feld mini_report erweitert, damit die Child-Row ohne extra Drilldown-Fetch befuellt werden kann

### Files
- services/api/routes/api_leaderboard.py
- services/frontend/templates/leaderboard/index.html



## [1.0.159] - 27.05.2026

### Added
- Leaderboard: Iterations-Kurzbemerkung als Tooltip auf Iteration-Name
  - API liefert iteration_description (aus StrategyIteration.description, via Lookup ueber concept.slug + version)
  - Iterations-Zelle zeigt die Bemerkung als Hover-Tooltip

### Files
- services/api/routes/api_leaderboard.py
- services/frontend/templates/leaderboard/index.html



## [1.0.158] - 27.05.2026

### Changed
- Leaderboard: R/T %-Header und nowrap fuer Iteration/TestSet/Erstellt am
  - Spaltenkopf Return/Tag % auf R/T % verkuerzt
  - Zellen in Iteration, TestSet und Erstellt am brechen nicht mehr um

### Files
- services/frontend/templates/leaderboard/index.html



## [1.0.157] - 27.05.2026

### Fixed
- Leaderboard: Overlap-Badge nur noch bei echten Zeitraum-Ueberschneidungen
  - Identische Zeitraeume (gleiches Symbol/Window ueber mehrere Configs) werden vor der Overlap-Pruefung dedupliziert
  - Damit kein faelschliches overlap-Flag im Normalfall TestSet mit gleichem Backtest-Fenster

### Files
- services/api/routes/api_leaderboard.py



## [1.0.156] - 27.05.2026

### Added
- Leaderboard: Test-Tage (Intervall-Union) und Return/Tag %
  - Neue Spalten Tage und Return/Tag %, berechnet aus den Backtest-Zeitfenstern der Winning-Results
  - Ueberlappende Walk-Forward-Fenster werden nur einmal gezaehlt (Intervall-Union); overlap-Badge bei Ueberschneidungen
  - Return/Tag % = total_return_sum / span_days (Union-Tage)

### Files
- services/api/routes/api_leaderboard.py
- services/frontend/templates/leaderboard/index.html



## [1.0.155] - 27.05.2026

### Changed
- Backtest-Runs: Auto-Update-Intervall von 10s auf 5s reduziert

### Files
- services/frontend/templates/backtest/runs.html



## [1.0.154] - 27.05.2026

### Changed
- Strategie-Iterationen Child-Row: horizontales Zellen-Padding erhöht
  - 0.85rem links/rechts auf alle th/td der iterations-table-* — schmale w-1-Spalten bekommen spürbar mehr Luft

### Files
- services/frontend/templates/config/strategy_concepts.html



## [1.0.153] - 27.05.2026

### Fixed
- Strategie-Iterationen Child-Row: w-1 auf Daten-Zellen mitsetzen
  - w-1/text-nowrap nun als column.className gesetzt — wirkt damit auf <th> UND <td>
  - Verhindert Umbrüche in Version, Erstellt und Aktualisiert; Kurzbeschreibung bleibt der einzige Stretch-Kandidat

### Files
- services/frontend/templates/config/strategy_concepts.html



## [1.0.152] - 27.05.2026

### Changed
- Strategie-Iterationen Child-Row: Spaltenbreiten ausbalanciert
  - Datums-, Status-, Typ-, Obsidian-, Version- und Aktionen-Spalten auf w-1 (schrumpfen auf Inhalt) gesetzt
  - Kurzbeschreibung bekommt dadurch den verbleibenden Platz und ist spürbar breiter
  - Buttonleiste min-width entfernt, da w-1 die Breite aus dem Inhalt ableitet

### Files
- services/frontend/templates/config/strategy_concepts.html



## [1.0.151] - 27.05.2026

### Added
- Strategie-Iterationen: updated_at-Spalte und neue Tabellenspalte 'Aktualisiert'
  - Neue Spalte 'updated_at' (DateTime, nullable) auf strategy_iterations via Alembic-Migration 0004_iteration_updated_at
  - SQLAlchemy onupdate-Hook setzt updated_at automatisch bei jedem PUT auf eine Iteration
  - Schema StrategyIterationSchema um updated_at erweitert
  - Child-Row-Tabelle: neue Spalte 'Aktualisiert' (zeigt updated_at, Fällt auf created_at zurück und stellt Bestand grau dar)
  - Sortierung der Child-Row umgestellt auf is_favorite DESC, updated_at-effektiv DESC (Fallback created_at)

### Files
- alembic/versions/0004_iteration_updated_at.py
- user_data/utils/database/models.py
- services/api/routes/api_strategy.py
- services/frontend/templates/config/strategy_concepts.html



## [1.0.150] - 27.05.2026

### Changed
- Strategie-Iterationen: Sortierung Favoriten oben, dann Erstelldatum absteigend
  - Child-Row-Tabelle sortiert primär nach is_favorite DESC, sekundär nach created_at DESC
  - Sortierung wird nach Toggle des Favoriten-Sterns sofort neu angewendet, sodass markierte Einträge nach oben rutschen
  - Hinweis: strategy_iterations hat kein updated_at — Iterationen sind laut Modell immutable, daher created_at als Tiebreaker

### Files
- services/frontend/templates/config/strategy_concepts.html



## [1.0.149] - 27.05.2026

### Added
- Strategie-Iterationen: Favoriten-Stern und Löschen in der Child-Row
  - Neue Spalte 'is_favorite' (Boolean, default false) auf strategy_iterations via Alembic-Migration 0003_iteration_favorite
  - Neuer Endpoint POST /api/strategy/iterations/{id}/favorite zum Toggeln des Favoriten-Flags
  - StrategyIterationSchema um Feld is_favorite erweitert
  - Child-Row der Strategie-Konzepte: neue erste Spalte mit Stern-Icon zum Setzen/Entfernen des Favoriten
  - Child-Row der Strategie-Konzepte: zusätzlicher Löschen-Button neben dem Edit-Button (mit optionaler Vault-Ordner-Löschung)
  - Iteration-Edit-Page: Stern-Icon links neben dem Seitentitel zum Toggeln des Favoriten

### Files
- alembic/versions/0003_iteration_favorite.py
- user_data/utils/database/models.py
- services/api/routes/api_strategy.py
- services/api/routes/views_config.py
- services/frontend/templates/config/strategy_concepts.html
- services/frontend/templates/config/strategy_iteration_edit.html



## [1.0.148] - 27.05.2026

### Changed
- Strategie-Konzepte aus Konfigurations-Dropdown in die Top-Navigation verschoben und Bulk-Delete fuer Playground-Setups ergaenzt
  - Top-Nav-Eintrag 'Strategie-Konzepte' links neben Leaderboard, aus dem Dropdown entfernt
  - active_nav 'config_strategy' -> 'strategy_concepts' fuer Uebersichts- und Iterations-Edit-Seiten
  - Playground-Setups: Checkbox-Spalte mit Select-All sowie Bulk-Delete-Button im Page Header (immer sichtbar, disabled solange keine Auswahl)
  - Neuer Endpoint POST /api/chart-playground/setups/bulk-delete

### Files
- services/frontend/templates/base.html
- services/api/routes/views_config.py
- services/frontend/templates/config/playground_setups.html
- services/api/routes/api_chart_playground.py



## [1.0.147] - 27.05.2026

### Changed
- Backtest-Runs: TSetID-Spalte zentriert

### Files
- services/frontend/templates/backtest/runs.html



## [1.0.146] - 27.05.2026

### Changed
- Backtest-Runs: Spaltenheader 'TestSet-Run' in 'TSetID' umbenannt

### Files
- services/frontend/templates/backtest/runs.html



## [1.0.145] - 27.05.2026

### Changed
- Backtest-Runs: TestSet-Run-Spalte vor Strategie verschoben

### Files
- services/frontend/templates/backtest/runs.html



## [1.0.144] - 27.05.2026

### Changed
- Backtest-Runs: TestSet-Run-Badge ohne Raute

### Files
- services/frontend/templates/backtest/runs.html



## [1.0.143] - 27.05.2026

### Changed
- Backtest-Runs: TestSet-Spalte zeigt testset_run_id statt TestSet-Name
  - Spaltenheader auf 'TestSet-Run' geaendert
  - Badge zeigt #<testset_run_id>, TestSet-Name als Tooltip

### Files
- services/frontend/templates/backtest/runs.html



## [1.0.142] - 27.05.2026

### Added
- Backtest-Runs: TestSet-Spalte mit Link zum TestSet
  - Neue Spalte 'TestSet' in /backtest/runs zwischen Workflow und Status
  - Badge zeigt TestSet-Namen und verlinkt auf /testsets/{id}, Tooltip nennt testset_run_id
  - Backend: BacktestRunOut um testset_run_id erweitert, /api/backtest/runs liefert testset_id und testset_name via TestSetRun-Join

### Files
- services/api/schemas.py
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/runs.html



## [1.0.141] - 27.05.2026

### Added
- Leaderboard: TestSet-Spalte mit Namen aus dem Snapshot
  - Neue Spalte 'TestSet' im Leaderboard-Grid zwischen Iteration und Indikatoren
  - Backend liefert testset_name aus entry.testset_snapshot_json (Source of Truth nach Cleanup)
  - Default-Sortierung auf neuen Spalten-Index (Sum Return %) angepasst

### Files
- services/api/routes/api_leaderboard.py
- services/frontend/templates/leaderboard/index.html



## [1.0.140] - 27.05.2026

### Changed
- Indicator-Configs-Tabelle: Konzept- und Iteration-Spalten ergaenzt, Workflows/Default entfernt, Indikatoren ohne Zeilenumbruch
  - Neue Spalten Konzept und Iteration zeigen die optionalen Felder aus dem Edit-Formular
  - Spalten Workflows und Default aus der Listenansicht entfernt
  - Indikatoren-Spalte erhaelt text-nowrap (Header und Zelle)

### Files
- services/frontend/templates/config/indicator_configs.html



## [1.0.139] - 27.05.2026

### Changed
- Ticket 22 — Indikator-Config: lose Verknüpfung zu Strategy-Concept und Iteration
  - IndicatorConfig: String-Spalte iteration_id ersetzt durch zwei nullable Integer-Spalten strategy_concept_id und strategy_iteration_id (kein FK, lose Kopplung — Löschen/Umbenennen der Ziele bricht nichts)
  - Alembic-Migration 0002_indicator_strategy_link: legt neue Spalten an, übernimmt bestehende numerische iteration_id-Werte und spiegelt die concept_id aus strategy_iterations, droppt anschließend iteration_id
  - API /api/config/indicator: neue Query-Params concept_id und iteration_id mit 3-Bucket-Sortierung (exakter Match -> nur Concept-Match -> Rest, innerhalb is_default DESC + updated_at/created_at DESC); Pydantic-Schemas um die zwei IDs plus Read-Only-Lookups strategy_concept_name und strategy_iteration_version erweitert
  - Edit-Formular indicator_config_edit.html: zwei abhängige Dropdowns (Konzept -> Iteration), gespeist aus /api/strategy/concepts und /api/strategy/iterations?concept_id=...; Auswahl optional, leer-lassen erlaubt
  - Backtest-Start (Einzel-Lauf + TestSet): Indicator-Config-Dropdown wird nach Concept/Iteration-Auswahl serverseitig sortiert neu geladen; Label-Format Name — Concept/Iteration (oder leer wenn nicht verknüpft)
  - Tests: neue Unit-Tests in test_ticket22_indicator_config_sorting.py decken 3-Bucket-Sortierung, Fallback-Sortierung, Read-Only-Lookups und Null-Safety bei gelöschten Zielen ab; bestehender Test in test_iteration_id_write_path.py auf neue Spaltenstruktur angepasst

### Files
- user_data/utils/database/models.py
- alembic/versions/0002_indicator_strategy_link.py
- services/api/routes/api_config.py
- services/api/routes/views_config.py
- services/frontend/templates/config/indicator_config_edit.html
- services/frontend/templates/backtest/start.html
- tests/test_ticket22_indicator_config_sorting.py
- tests/test_iteration_id_write_path.py
- documentation/tickets/22-indicator-config-strategy-concept-iteration-link.md



## [1.0.138] - 27.05.2026

### Changed
- Leaderboard: Default-Sortierung auf Sum Return % (statt Ø Return %)

### Files
- services/frontend/templates/leaderboard/index.html



## [1.0.137] - 27.05.2026

### Changed
- Leaderboard: Spalten Ø Return % und Sum Return % links neben Erstellt am verschoben (nach Ø Profit-Faktor)

### Files
- services/frontend/templates/leaderboard/index.html



## [1.0.136] - 27.05.2026

### Changed
- Leaderboard: Spalte IndicatorConfig durch generische Spalte Indikatoren ersetzt — Badges aus indicator_config_snapshot_json mit Parameter-Tooltip
  - API: LeaderboardEntryOut um Feld 'indicators' (Dict slot -> params) erweitert, extrahiert generisch aus indicator_config_snapshot_json.config_json
  - Frontend: Spalten-Header 'IndicatorConfig' -> 'Indikatoren', Render-Funktion erzeugt pro Slot einen Tabler-Badge
  - Tooltip pro Badge zeigt alle Parameter als key: value (mehrzeilig, monospace, max-width 320px)
  - drawCallback re-initialisiert Tooltips nach jedem Sort/Filter (DataTables baut die Zellen neu)
  - Kein Indikator-Typ-Mapping noetig — Anzeige rein generisch ueber Object.keys()

### Files
- services/api/routes/api_leaderboard.py
- services/frontend/templates/leaderboard/index.html



## [1.0.135] - 27.05.2026

### Fixed
- Drill-Down: Length-Menu zurück in den Footer (Design-Guide), eigenes Suchfeld mit Lupe und X-Clear über der Tabelle (statt DT-Default)
  - DOM zurück auf 'rt<row dt-footer-row col-auto l, col i, col-auto p>' wie im Design-Guide
  - Eigenes Suchfeld #drilldown-search mit Lupe-SVG (innen links) und X-Clear-Button (rechts, sichtbar nur bei Eingabe via :placeholder-shown)
  - Bindung an dt.search().draw() in renderDrilldownTable
  - Globaler Delegations-Handler für .dt-search-clear

### Files
- services/frontend/templates/leaderboard/index.html



## [1.0.134] - 27.05.2026

### Fixed
- Drill-Down-Modal: Abstand nach oben (margin-top 4rem), Length-Menu links und Suchfeld rechts korrekt platziert, globale dt-search-Ausblendung im Modal aufgehoben

### Files
- services/frontend/templates/leaderboard/index.html



## [1.0.133] - 27.05.2026

### Changed
- Drill-Down-Modal im Leaderboard breiter (95vw) und höher (80vh), Body intern scrollbar

### Files
- services/frontend/templates/leaderboard/index.html



## [1.0.132] - 27.05.2026

### Changed
- Drill-Down-Tabelle im Leaderboard-Modal auf DataTables umgestellt (Sortierung, Pagination, Suche, Length-Menu)
  - Neuer Tabellen-ID drilldown-table; column-render mit type='sort' für numerisch korrekte Sortierung
  - Missing-Rows als table-warning via rowCallback
  - Default-PageLength 25, lengthMenu mit 'Alle'
  - DataTable wird bei jedem Öffnen sauber destroyed und neu instanziiert

### Files
- services/frontend/templates/leaderboard/index.html



## [1.0.131] - 27.05.2026

### Changed
- Leaderboard-Tabelle: Hint in Child Row (Chevron-Toggle), Strategie aufgeteilt in Konzept/Iteration, Spalte Ausgelöst von entfernt, Runner-Version/Configs/Gewinn/Verlust zentriert
  - Neue Control-Spalte links mit Chevron toggelt Child-Row, die den Hint anzeigt
  - Spalte 'Ausgelöst von' (triggered_by) aus der Hauptansicht entfernt
  - Spalte 'Hint' aus der Hauptansicht entfernt (lebt jetzt in Child Row)
  - Spalte 'Strategie' in zwei Spalten 'Konzept' (strategy_family) und 'Iteration' (strategy_name) aufgeteilt
  - Spalten Runner-Version, Configs, Gewinn, Verlust auf text-center umgestellt
  - Default-Sortierung an die neue Spalten-Reihenfolge angepasst

### Files
- services/frontend/templates/leaderboard/index.html



## [1.0.130] - 27.05.2026

### Changed
- Leaderboard: Spalten Gewinn/Verlust (Config-Counts) und Ø Profit-Faktor ergänzt; alle Header-Spalten mit Info-Tooltips erklärt
  - API: configs_win, configs_loss, profit_factor_avg per Aggregation über BacktestResult zur LeaderboardEntryOut hinzugefügt
  - Frontend: Spalten Gewinn/Verlust rechts neben Configs, Ø Profit-Faktor rechts neben Ø Sharpe
  - Frontend: Info-Tooltips pro Header-Spalte gemäß Design-Guide (Jinja-Macro tip)
  - Tooltip-Re-Init nach DataTable-Render, da DataTables die thead-Inhalte klont

### Files
- services/api/routes/api_leaderboard.py
- services/frontend/templates/leaderboard/index.html



## [1.0.129] - 27.05.2026

### Changed
- Leaderboard Drill-Down: Winrate und Profit-Faktor ergänzt, Zeitraum in deutschem Datumsformat (DD.MM.YYYY)

### Files
- services/api/routes/api_leaderboard.py
- services/frontend/templates/leaderboard/index.html



## [1.0.128] - 27.05.2026

### Changed
- TestSet-Lauf vereinheitlicht mit Einzel-Lauf: gleiches Konzept/Iteration-Dropdown und Pflicht-Indicator-Config
  - Frontend (backtest/start.html): TestSet-Panel uebernimmt die Auswahl-Struktur des Einzel-Laufs. Reihenfolge: Strategie (Konzept + Iteration zweistufig) - TestSet - Indicator-Config. Iterationen laden ueber /api/strategy/iterations und defaulten auf die neueste aktive Iteration. Indicator-Config zeigt im TestSet-Tab jetzt ebenfalls Indikator-Badges und Kombinations-Count.
  - Backend (api_testset_runs.py): Schema umgestellt auf { testset_id, iteration_id, indicator_config_id } - alle drei Pflicht. strategy_family/strategy_name/import_path werden aus Concept+Iteration aufgeloest (analog /api/backtest/start), indicators_config_json aus IndicatorConfig.config_json. iteration_id wird explizit an create_backtest_run uebergeben.
  - Legacy: TestSet-Lauf benutzt nicht mehr das strategy_configs-Dropdown und nimmt indicators_config_json nicht mehr direkt im Payload entgegen.
  - Test (test_testset_runs_api.py): test_invalid_testset_id_returns_400 auf das neue Payload-Schema angepasst.

### Files
- services/frontend/templates/backtest/start.html
- services/api/routes/api_testset_runs.py
- tests/test_testset_runs_api.py



## [1.0.127] - 27.05.2026

### Fixed
- Dark-Mode-Darstellung der aufgeklappten Child-Row auf /config/strategy-concepts korrigiert
  - Child-Row-Inset nutzt im Dark-Mode --tblr-bg-surface-secondary statt fixem --tblr-gray-200
  - Card-Table-Header im Dark-Mode ebenfalls auf theme-aware Surface-Variable umgestellt
  - Hover-Hintergrund nutzt Surface-Variable mit gray-100 als Fallback

### Files
- services/frontend/templates/config/strategy_concepts.html



## [1.0.126] - 27.05.2026

### Fixed
- api_backtest.py: import_path fuer generic-Iterationen explizit auf spec_runner setzen
  - Worker warf KeyError bei Backtest-Start mit generic-Iterationen, weil import_path nicht gesetzt war.
  - Loesung: in /backtest/start wird fuer iteration.type != 'hardcoded' der import_path auf 'user_data.strategies.generic.spec_runner.run_spec_strategy' gesetzt.
  - Damit lassen sich Backtests via /backtest/start mit Iteration + BT-Config + Indicator-Config sauber starten.
  - Im Zuge dessen Strategie 'dyn-v0.32e' aus STRATEGY_DYNAMIC.md rekonstruiert: Iteration #26, BT-Config #552, Indicator-Config #1970. Vergleich mit Original-Result #262917 zeigt: 425/426 Trades identisch, Diskrepanz beim ersten Trade kommt aus der OHLC-Datenlage zum Zeitpunkt des Original-Runs (dwsAssetDD reagiert auf abgeschnittene Peak-Fenster).
  - Offenes Backlog-Item: dwsAssetDD sollte Warmup-NaN liefern, damit Backtests stabil gegen Datensatz-Erweiterungen sind.

### Files
- services/api/routes/api_backtest.py



## [1.0.125] - 26.05.2026

### Changed
- Alembic-Migrationen auf eine Baseline zusammengefasst, schema.sql entsorgt
  - Die 13 historischen Alembic-Migrationen in alembic/versions/ zu einer einzigen Baseline 0001_baseline_squash zusammengefasst
  - Baseline-DDL aus pg_dump -s der lokalen DB extrahiert und in alembic/versions/_sql/0001_baseline.sql abgelegt; Migration-Py-Datei laedt die SQL via op.execute()
  - TimescaleDB-Extension und create_hypertable-Calls fuer backtest_result_equity / backtest_result_indicators explizit in die Baseline aufgenommen (pg_dump exportiert die nicht)
  - Verwaiste leere Tabelle test_sets (Rest der alten Rename-Migration test_sets->testsets) gedroppt
  - Lokale DBs db_vbt_v1 und db_vbt_v1_test auf Revision 0001_baseline_squash gestempelt - keine Daten angefasst (9412 Results, 40 Runs, 2 Testsets intakt)
  - Schema-Diff zwischen Prod-DB und frisch aus Baseline aufgebauter Test-DB verifiziert (nur kosmetische CHECK-Constraint-Notation unterschiedlich)
  - Seed-Backup vor dem Squash unter seed/data/seed_pre_alembic_squash.dump abgelegt
  - backtest_schema.sql entsorgt - war doppelgleisig zu Alembic und stark veraltet (kannte testsets/leaderboard/strategy_concepts/iterations gar nicht und hatte alte Tabellennamen)
  - deploy-update.sh fuer staging: psql-Schema-Load entfernt, TODO/Hinweis fuer alembic-upgrade-head eingebaut - staging-Container kennen aktuell weder alembic.ini noch das alembic/-Verzeichnis, deshalb bis zum Container-Setup noch nicht scharf geschaltet

### Files
- alembic/versions/0001_baseline_squash.py
- alembic/versions/_sql/0001_baseline.sql
- alembic/versions/3715803d2a5d_add_spec_runner_version.py
- alembic/versions/77563443bb87_rename_test_set_snapshot_to_testset_.py
- alembic/versions/7990cb8e2ca9_naming_cleanup_backtest_result_und_.py
- alembic/versions/9221c1669180_add_test_sets_table.py
- alembic/versions/93def767e8a5_add_testset_runs_and_leaderboard_.py
- alembic/versions/959be42e071a_add_strategy_concepts_iterations.py
- alembic/versions/a1b2c3d4e5f6_ticket15_json_suffix_and_schema_cleanup.py
- alembic/versions/b7e4c1a9f2d3_add_type_and_import_path_to_strategy_iterations.py
- alembic/versions/c3f8a2d91e47_add_iteration_id_fk_to_runs_results_configs.py
- alembic/versions/d2e9f1c4a8b5_add_description_to_strategy_iterations.py
- alembic/versions/e7f3a1b2c9d4_ticket16_drop_obsidian_fields.py
- alembic/versions/eae947b52264_add_testset_run_id_fk_to_backtest_runs.py
- alembic/versions/f1a2b3c4d5e6_add_spec_hash_to_strategy_iterations.py
- user_data/utils/database/schema/backtest_schema.sql
- documentation/deploy/staging/deploy-update.sh
- seed/data/seed_pre_alembic_squash.dump



## [1.0.124] - 26.05.2026

### Removed
- Indicator-Config: ungenutzte Strategie-Zuordnung entfernt
  - Dropdown 'Strategie' aus indicator_config_edit.html entfernt — wurde nur noch als kosmetischer Prefix im Titel-Generator genutzt
  - Titel-Generator erzeugt jetzt Namen ohne Strategie-Prefix (z.B. '1.234 Kombinationen mit ST')
  - Feld strategy_name aus IndicatorConfigIn/Out, Create/Update-Routen und View-Context entfernt
  - Spalte indicator_configs.strategy_name aus SQLAlchemy-Modell und SQL-Schema entfernt, in lokaler DB (db_vbt_v1, db_vbt_v1_test) per ALTER TABLE DROP COLUMN gedroppt
  - Hintergrund: Seit Ticket 11 leitet api_backtest strategy_family/strategy_name ausschliesslich aus iteration_id oder strategy_config_id ab — die Indicator-Zuordnung wurde nirgends mehr ausgewertet

### Files
- services/frontend/templates/config/indicator_config_edit.html
- services/api/routes/api_config.py
- services/api/routes/views_config.py
- user_data/utils/database/models.py
- user_data/utils/database/schema/backtest_schema.sql



## [1.0.123] - 26.05.2026

### Changed
- Chart-Playground: Button-Label und Confirm-Dialog "Loeschen" → "Löschen" mit echtem Umlaut

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.122] - 26.05.2026

### Changed
- Chart-Playground: Toolbar-Buttons (Chart laden, Speichern, Speichern unter, Löschen) auf normale Größe vereinheitlicht und horizontal ausgerichtet

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.121] - 26.05.2026

### Changed
- Playground-Setup-Edit: Layout der Inputfelder überarbeitet
  - ID-Feld als Inputfeld entfernt und stattdessen ohne Raute hinter dem Titel im Page Header angezeigt (z.B. 'ID 5')
  - Allgemein-Bereich neu angeordnet: Zeile 1 Name + Erstellt, Zeile 2 Beschreibung + Geändert
  - Alle vier JSON-Editoren (backtest_config_json, indicators_config_json, strategy_config_json, ui_state_json) haben jetzt eine einheitliche fixe Höhe von 420px

### Files
- services/frontend/templates/config/playground_setup_edit.html



## [1.0.120] - 26.05.2026

### Changed
- Indikator-Spec-Format vereinheitlicht: flacher Aufbau, source statt src, indicator: statt ind:
  - inputs-Wrapper entfernt: Input-Felder (source, volume, ...) liegen direkt am Indikator-Objekt; Trennung Inputs vs Params erfolgt anhand factory.input_names / factory.param_names
  - Key src in source umbenannt (custom-IFs dwsFastSMA/dwsVWMA/dwsVWMABand/dwsAssetDD: input_names angepasst)
  - Referenz-Prefix ind: in indicator: umbenannt (z.B. indicator:fast_sma:result)
  - DB-Migration: 5 chart_playground_setups, 31 backtest_runs, 3 strategy_iterations auf neues Format umgeschrieben (Script: seed/migrate_indicator_inputs.py, idempotent)
  - Backend: api_chart_playground.py (IndicatorSpec, compute, create_setup_from_result), indicator_factory.py (Topo-Sort + Resolve), spec_runner.py, rules_engine.py
  - Frontend: chart_playground/index.html (Save/Load flach, Dropdowns, Rename), backtest/start.html und workflow/template_edit.html (META_KEYS)

### Files
- services/api/routes/api_chart_playground.py
- user_data/strategies/generic/indicator_factory.py
- user_data/strategies/generic/spec_runner.py
- user_data/strategies/generic/rules_engine.py
- user_data/strategies/generic/specs/vwma_v2_single.py
- user_data/utils/indicators/custom.py
- services/frontend/templates/chart_playground/index.html
- services/frontend/templates/backtest/start.html
- services/frontend/templates/workflow/template_edit.html
- seed/migrate_indicator_inputs.py



## [1.0.119] - 26.05.2026

### Added
- Konfiguration: Verwaltungsseiten für Playground-Setups (Liste + Edit-Maske mit allen Feldern)
  - Neuer Nav-Eintrag 'Playground-Setups' unter Konfiguration.
  - Listen-Seite /config/playground als DataTable mit ID, Name, Beschreibung, Symbol, Exchange, TF, Start/Ende (DE-Datum), Indikator-Anzahl, Erstellt/Geändert sowie Aktionen 'Im Playground öffnen / Bearbeiten / Löschen'.
  - Edit-Maske /config/playground/{id} bzw. /new mit Name, Beschreibung und vier CodeMirror-JSON-Editoren für backtest_config_json, indicators_config_json, strategy_config_json, ui_state_json (inkl. Format-Buttons und JSON-Validierung).
  - Speichern nutzt die bestehende API /api/chart-playground/setups (POST/PUT).

### Files
- services/api/routes/views_config.py
- services/frontend/templates/base.html
- services/frontend/templates/config/playground_setups.html
- services/frontend/templates/config/playground_setup_edit.html



## [1.0.118] - 26.05.2026

### Fixed
- Chart-Playground: TF-Buttons werden nach Setup-Load bzw. Backtest-Config-Wechsel neu gerendert
  - Bisher blieben Buttons unterhalb des Basis-TF sichtbar (z.B. 1H/2H bei 4H-Strategie) und der aktive Button stimmte nicht.
  - applySetupConfig und der Backtest-Config-Change-Handler rufen jetzt visualTf = null + renderTfButtons() nach.

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.117] - 26.05.2026

### Changed
- Chart-Playground: Equity wird als Overlay-Series am Haupt-Chart gerendert statt als Sub-Chart
  - Spiegelt jetzt das Verhalten der Result-Chart-Seite wider (eigene Price-Scale 'equity').
  - Sub-Chart-Div #cpEquityChart und zugehörige CSS/Cleanup-Logik entfernt; Rendering läuft jetzt über ResultOverlay.renderEquityCurve.

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.116] - 26.05.2026

### Fixed
- Result-Chart-Seite: chart-data-Endpoint warf 500-Traceback wegen alter Tabellen-Namen in Raw-SQL
  - Raw-SQL in api_backtest.py verwies noch auf backtest_equity/backtest_indicators/backtest_params; Ticket 13 hatte die Tabellen auf backtest_result_* umbenannt.
  - Folgefehler behoben: Equity-Linie wurde im Chart nicht angezeigt, weil chart-data-Response leer war.

### Files
- services/api/routes/api_backtest.py



## [1.0.115] - 26.05.2026

### Fixed
- test_ticket11: Frontend-Route-Pfad korrigiert (`/config/strategy` → `/config/strategy-concepts`)
  - Zwei Tests in test_ticket11.py riefen einen nicht mehr existierenden Routen-Pfad auf (404).
  - Pfad an die tatsaechliche Route in views_config.py angepasst — alle 11 Tests gruen.

### Files
- tests/test_ticket11.py



## [1.0.114] - 26.05.2026

### Changed
- Indicator-JSON-Schema bereinigt: Tickets 18-21 umgesetzt, dwsFastSMA-Param 'mult' zu 'multiplier' DB-migriert.
  - T18: recompute.py nutzt jetzt _build_resolved_config aus repository.py, hardgecodetes Param-Mapping entfernt; Skalar-Output statt Pseudo-Range
  - T19: dwsFastSMA-Factory von 'mult' auf 'multiplier' umgestellt, _PARAM_ALIASES geleert, alle Caller und Spalten-Namen migriert
  - T20: calcCombinations() in start.html und template_edit.html ueberspringt Meta-Keys (indicator, tf, enabled, inputs) explizit
  - T21: _rules-Legacy-Key aus 4 JSON-Spalten in DB entfernt, Worker-Fallback und stiller Default in api_chart_playground entfernt, Test-Fixture bereinigt; Cleanup-Skript scripts/cleanup_rules_key.py
  - T19-Nachzug: DB-Migration scripts/migrate_dwsfastsma_mult_to_multiplier.py — 25 backtest_runs, 23 backtest_results, 5 playground_setups migriert
  - Aufraeumen: user_data/tmp_analysis/ und documentation/archive/ geloescht

### Files
- services/api/recompute.py
- user_data/utils/database/repository.py
- user_data/utils/indicators/custom.py
- user_data/strategies/generic/indicator_factory.py
- user_data/strategies/vwma_dws/vwma_v1/vwma_v1_s7_strategie_4h_range.py
- user_data/strategies/vwma_dws/vwma_v2/vwma_v2_strategie_4h_range.py
- services/frontend/templates/backtest/start.html
- services/frontend/templates/workflow/template_edit.html
- services/api/worker_tasks.py
- services/api/routes/api_chart_playground.py
- tests/test_spec_runner_reads_iteration.py
- scripts/cleanup_rules_key.py
- scripts/migrate_dwsfastsma_mult_to_multiplier.py
- documentation/tickets/18-recompute-resolved-config-dedupe.md
- documentation/tickets/19-dwsfastsma-mult-rename.md
- documentation/tickets/20-calc-combinations-meta-keys.md
- documentation/tickets/21-rules-key-cleanup.md



## [1.0.113] - 26.05.2026

### Removed
- _rules-Legacy-Key vollständig entfernt: DB gesäubert, Worker- und Chart-Playground-Fallback gelöscht (Ticket 21)
  - DB-Cleanup: _rules-Key aus backtest_runs.indicators_config_json (16 Zeilen) und backtest_results.resolved_config_json (16 Zeilen) entfernt
  - worker_tasks.py: Legacy-Fallback ersatzlos gelöscht — fehlende iteration_id wirft jetzt ValueError statt stillem False
  - api_chart_playground.py: Legacy-Fallback und stiller Default rules={'entry':None,'exit':None} gelöscht — fehlende Iteration wirft HTTPException 422
  - test_spec_runner_reads_iteration.py: Test-Fixture ohne _rules umgeschrieben, neuer Test prüft ValueError bei fehlender Iteration
  - scripts/cleanup_rules_key.py: einmaliges DB-Cleanup-Skript angelegt

### Files
- services/api/worker_tasks.py
- services/api/routes/api_chart_playground.py
- tests/test_spec_runner_reads_iteration.py
- scripts/cleanup_rules_key.py



## [1.0.112] - 26.05.2026

### Changed
- calcCombinations() in beiden Templates haertet: META_KEYS explizit ueberspringen
  - META_KEYS = new Set(['indicator', 'tf', 'enabled', 'inputs']) eingefuehrt
  - Innerhalb der Param-Schleife META_KEYS.has(paramKey) als Skip-Bedingung geprueft
  - Verhindert, dass Meta-Keys mit Range-aehnlicher Struktur faelschlich in die Kombinations-Berechnung einfliessen
  - Bestehende Combo-Zahlen unveraendert (Test bestaetigt Identitaet fuer normale Configs)
  - Ticket 20

### Files
- services/frontend/templates/backtest/start.html
- services/frontend/templates/workflow/template_edit.html



## [1.0.111] - 26.05.2026

### Changed
- Ticket 18 — Recompute auf _build_resolved_config umgestellt, resolved_config_json schreibt Skalare statt Pseudo-Ranges
  - _build_single_indicators_config in recompute.py ersatzlos geloescht (hartcodierte 6-Parameter-Map)
  - Beide Aufrufstellen in recompute_single_result und compute_full_metrics auf _build_resolved_config aus repository.py umgestellt
  - _build_resolved_config schreibt Einzelwerte jetzt als echte Skalare (int/float) statt Pseudo-Range-Dicts
  - dtype-Erhaltung: int64-Params bleiben int, float64-Params bleiben float
  - Fiktive neue Indikatoren (z.B. dwsRSI mit lookback) werden korrekt aufgeloest ohne Aenderung an recompute.py

### Files
- services/api/recompute.py
- user_data/utils/database/repository.py



## [1.0.110] - 26.05.2026

### Changed
- dwsFastSMA-Param `mult` zu `multiplier` umbenannt, Alias-Map entfernt (Ticket 19)
  - custom.py: dws_fast_sma_inc-Param und dwsFastSMA param_names von 'mult' zu 'multiplier' umbenannt
  - indicator_factory.py: _PARAM_ALIASES-Eintraege fuer dwsFastSMA / custom:dwsFastSMA entfernt
  - api_chart_playground.py: _ALIAS_FOR_FACTORY-Eintrag fuer dwsFastSMA entfernt
  - recompute.py: param_mapping-Schluessel 'dwsfastsma_mult' zu 'dwsfastsma_multiplier' geaendert
  - vwma_v1_s7_strategie_4h_range.py / vwma_v2_strategie_4h_range.py / vwma_v2_strategie_4h.py: MultiIndex-Spaltenname 'dwsfastsma_mult' zu 'dwsfastsma_multiplier' aktualisiert
  - vwma_v2_single.py: veralteten Alias-Kommentar durch aktuellen Hinweis ersetzt

### Files
- user_data/utils/indicators/custom.py
- user_data/strategies/generic/indicator_factory.py
- services/api/routes/api_chart_playground.py
- services/api/recompute.py
- user_data/strategies/vwma_dws/vwma_v1/vwma_v1_s7_strategie_4h_range.py
- user_data/strategies/vwma_dws/vwma_v2/vwma_v2_strategie_4h_range.py
- user_data/strategies/vwma_dws/vwma_v2/vwma_v2_strategie_4h.py
- user_data/strategies/generic/specs/vwma_v2_single.py



## [1.0.109] - 26.05.2026

### Fixed
- Chart-Playground: Equity-Kurve sichtbar, Tab-Label und Cleanup korrigiert (Ticket 17 Nachbesserung)
  - Tab 1 in Analyse-Tabs umbenannt von 'Indikatoren / Strategie / Portfolio' zu 'Strategie / Iteration'
  - Equity-Kurve im Result-Panel wurde nicht gerendert: Ursache war autoSize:true — das Panel wurde kurz davor aus display:none sichtbar gemacht, Browser hatte das Layout noch nicht berechnet, LightweightCharts sah clientWidth=0 und renderte nichts. Fix: explizite width/height statt autoSize
  - cpCurrentEquityChart-Referenz ergänzt damit eqChart.remove() im Cleanup korrekt aufgerufen wird (vorher: state.chart.removeSeries mit falscher Chart-Referenz)
  - Weissraum im Result-Panel war Folge des leeren Equity-Containers — wird durch Fix 2 automatisch behoben

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.108] - 26.05.2026

### Added
- Chart-Playground: Backtest-Result inline anzeigen mit Kennzahlen-Panel, Equity-Sub-Chart und Trade-Markern; drei Analyse-Tabs (Indikatoren/Strategie/Portfolio | Stats | Trades); gemeinsame JS-Module result/tabs.js und result/overlay.js für Wiederverwendung mit result_chart.html
  - Playground zeigt nach Backtest-Run sofort Kennzahlen (Return, Sharpe, MaxDD, Trades, Win-Rate, Profit-Factor, Avg Trade Duration) ohne Seitenwechsel
  - Trade-Marker (Entry/Exit-Pfeile mit Tooltip) auf dem OHLC-Chart, Toggle zum Ein-/Ausblenden
  - Equity-Sub-Chart im Result-Panel, Daten aus /chart-data
  - Drei-Tab-Struktur: Tab 1 unveraendert editierbar, Tab 2 Stats, Tab 3 Trades/Orders/Positions
  - Parallele AJAX-Calls nach run_id: /stats, /trades, /chart-data
  - 90s-Timeout mit Toast und Link auf /backtest/runs
  - result/tabs.js: loadStatsTab, loadTradesTab parametrisiert ueber resultId
  - result/overlay.js: renderEquityCurve, renderTradeMarkers, removeTradeMarkers
  - result_chart.html refactored: Inline-Stats-Tab, Inline-Trades-Tab und Inline-Vollanalyse-Code durch Modul-Aufrufe ersetzt

### Files
- services/frontend/static/js/result/tabs.js
- services/frontend/static/js/result/overlay.js
- services/frontend/templates/chart_playground/index.html
- services/frontend/templates/backtest/result_chart.html



## [1.0.107] - 26.05.2026

### Fixed
- Chart-Playground: Setup-Laden baut Strategie und Indikatoren wieder auf
  - Frontend an die vier _json-Spalten von chart_playground_setups angepasst (Ticket 15, Block 2): applySetupConfig konsumiert jetzt backtest_config_json, indicators_config_json, strategy_config_json und ui_state_json statt des nicht mehr existierenden flachen config_json.
  - collectSetupConfig liefert beim Speichern dieselben vier Felder; saveSetup und saveSetupConfirm spreaden sie direkt in den Request-Body statt sie unter config_json zu verschachteln.
  - Indikator-Metadaten (paramsMeta, inputNames, outputNames) werden beim Laden via neuer findIndicatorMeta-Helper aus dem Katalog (/api/chart-playground/indicators) rekonstruiert, da sie laut Ticket 15 nicht persistiert werden.
  - Portfolio wird aus backtest_config_json.portfolio gelesen, Farbe/plot_type pro Indikator aus ui_state_json.indicators[name].

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.106] - 26.05.2026

### Added
- Iteration loeschen mit optionaler Obsidian-Ordner-Entfernung und Vault-Ordner-Rename bei Versionsaenderung
  - Neuer DELETE-Endpoint /api/strategy/iterations/{id} mit Query-Parameter delete_vault — entfernt die Iteration aus der DB und optional den zugehoerigen Obsidian-Ordner inkl. aller Dateien.
  - Loesch-Button im Page-Header der Iteration-Edit-Seite mit Bestaetigungs-Modal — Checkbox fuer optionales Loeschen des Vault-Ordners (nur wenn vorhanden).
  - FK-Integrity-Fehler werden als 409 mit klarer Meldung zurueckgegeben, wenn referenzierende Datensaetze (Backtest-Runs, Child-Iterationen) existieren.
  - Beim Aendern der Iteration-Version wird der Obsidian-Ordner automatisch mitumbenannt: Ordner, .md-Datei sowie Frontmatter-Feld 'version:' und H1-Ueberschrift werden auf die neue Version aktualisiert.
  - Neue Repository-Funktion delete_iteration in repository_strategies.py.

### Files
- services/api/routes/api_strategy.py
- services/frontend/templates/config/strategy_iteration_edit.html
- user_data/utils/database/repository_strategies.py



## [1.0.105] - 26.05.2026

### Fixed
- Ticket 16 Bugfix: Obsidian-Vault-Mount und vault-create Idempotenz
  - BUG 1 — docker-compose-local.yml: Mount <Vault> durch ${OBSIDIAN_VAULT_HOST_PATH}:/obsidian_vault ersetzt; Docker Desktop WSL2-Backend brauchte Windows-Pfad (<Vault>) statt WSL-internem Pfad
  - BUG 2 — vault-create Endpoints waren durch falschen Mount nicht idempotent; mit korrektem Mount greift path.exists()-Check jetzt auf echten Vault; existierende User-Dateien werden nicht überschrieben
  - .env: OBSIDIAN_VAULT_HOST_PATH=<Vault> ergänzt
  - Verifiziert: Container sieht alle 8 echten User-Iterations-Dateien im Vault
  - Verifiziert: Concept vault-create auf vwma-dws-concept.md liefert created:false, Datei unverändert
  - Verifiziert: Iteration vault-create v2.0 legt Datei im echten Host-Vault an, zweiter Call idempotent

### Files
- docker-compose-local.yml
- .env



## [1.0.104] - 26.05.2026

### Added
- Ticket 16 — Deterministische Obsidian-Pfade, vault-create Endpunkte, Frontend-Button
  - Neues Utility-Modul services/api/utils/obsidian_paths.py: vault_root(), normalize_slug(), normalize_version(), concept_md_path(), iteration_md_path() — deterministisch aus slug + version abgeleitet, kein DB-Feld nötig
  - DB-Felder obsidian_slug (strategy_concepts) und obsidian_path (strategy_iterations) entfernt — Alembic-Migration e7f3a1b2c9d4
  - Slugs in strategy_concepts auf ^[a-z0-9-]+$ normalisiert (Unterstriche → Bindestriche, lowercase)
  - vault_exists: bool in allen GET-Responses für Concepts und Iterations (live aus Filesystem, nie gespeichert)
  - Neue Endpunkte POST /api/strategy/concepts/{id}/vault-create und POST /api/strategy/iterations/{id}/vault-create (idempotent, schreiben Markdown-Frontmatter)
  - Frontend strategy_concepts.html: obsidian_slug-Feld entfernt, Obsidian-Spalte nutzt vault_exists für visuellen Status
  - Frontend strategy_iteration_edit.html: obsidian_path-Feld entfernt, Button 'Obsidian-Dokumente anlegen' im Page-Header mit vollständigem JS-State-Management
  - Neues Migrations-Skript scripts/migrate_vault_iterations.py: verschiebt iterations/<version>.md → iterations/<version>/<version>.md (idempotent, --dry-run)
  - docker-compose-local.yml: Obsidian-Vault <Vault> als /obsidian_vault eingebunden, OBSIDIAN_VAULT_PATH gesetzt
  - 34 neue Tests in tests/test_ticket16.py (alle grün)

### Files
- services/api/utils/obsidian_paths.py
- services/api/utils/__init__.py
- services/api/routes/api_strategy.py
- services/api/routes/views_config.py
- services/frontend/templates/config/strategy_concepts.html
- services/frontend/templates/config/strategy_iteration_edit.html
- user_data/utils/database/models.py
- alembic/versions/e7f3a1b2c9d4_ticket16_drop_obsidian_fields.py
- scripts/migrate_vault_iterations.py
- docker-compose-local.yml
- tests/test_ticket16.py



## [1.0.103] - 25.05.2026

### Added
- Strategie-Konzepte-Seite: Child-Rows immer aufgeklappt, Typ-Spalte und Kurzbeschreibung an Iterationen
  - Child-Tabelle der Strategie-Konzepte klappt nach jedem Draw automatisch alle Iterationen auf
  - Neue Spalte 'Typ' in der Iterations-Child-Tabelle: hardcoded (blau) / generic (gruen)
  - Neue Spalte 'description' an strategy_iterations (Text, nullable) inkl. Alembic-Migration d2e9f1c4a8b5
  - Iteration-Edit-Formular: Textarea fuer Kurzbeschreibung ('Was hat sich geaendert?')
  - API-Schemas (Read/Create/Update) um description erweitert
  - Spalte 'Kurzbeschreibung' in der Child-Tabelle

### Files
- alembic/versions/d2e9f1c4a8b5_add_description_to_strategy_iterations.py
- user_data/utils/database/models.py
- services/api/routes/api_strategy.py
- services/frontend/templates/config/strategy_iteration_edit.html
- services/frontend/templates/config/strategy_concepts.html



## [1.0.102] - 25.05.2026

### Added
- Strategie-Iterationen koennen jetzt hartcodiert oder generisch sein
  - Neue Spalten type (NOT NULL, Default generic) und import_path (nullable) auf strategy_iterations
  - Iteration-Edit-Form um Typ-Select und Import-Pfad-Feld erweitert; Import-Pfad ist nur bei type=hardcoded aktiv
  - XOR-Validierung in /api/strategy/iterations: hardcoded erfordert import_path, generic verbietet ihn
  - Run-Erzeugung in api_backtest.py nutzt iteration.import_path bei type=hardcoded statt None
  - Alembic-Merge-Migration b7e4c1a9f2d3 vereint die zuvor parallelen Heads f1a2b3c4d5e6 und a1b2c3d4e5f6

### Files
- user_data/utils/database/models.py
- alembic/versions/b7e4c1a9f2d3_add_type_and_import_path_to_strategy_iterations.py
- services/api/routes/api_strategy.py
- services/api/routes/views_config.py
- services/api/routes/api_backtest.py
- services/frontend/templates/config/strategy_iteration_edit.html



## [1.0.101] - 25.05.2026

### Removed
- Strategie-Konzept-Detailseite /config/strategy-concepts/{id} entfernt
  - Route strategy_concept_detail_page in views_config.py geloescht
  - Template strategy_concept_detail.html geloescht
  - Links zur Detailseite aus strategy_concepts.html entfernt (Slug/Name als Klartext, Aktions-Button 'Iterationen ansehen' entfernt) - Iterationen sind weiterhin ueber die ausklappbaren Zeilen der Listenansicht erreichbar

### Files
- services/api/routes/views_config.py
- services/frontend/templates/config/strategy_concept_detail.html
- services/frontend/templates/config/strategy_concepts.html



## [1.0.100] - 25.05.2026

### Fixed
- Ticket 15 Code-Sweep nachgezogen: übersehene ORM-Attributzugriffe auf alte Spaltennamen behoben
  - views_backtest.py: run.indicators_config → run.indicators_config_json (Z.99, Z.157), result.actual_params → result.actual_params_json (Z.148)
  - views_testsets.py: ts.backtest_config_ids → ts.backtest_config_ids_json (Z.54)
  - views_workflow.py: tpl.indicator_config_ids → tpl.indicator_config_ids_json (Z.58)
  - api_workflow.py: Pydantic-Schema WorkflowTemplateIn/Out hatte indicator_config_ids_json als API-Feldnamen — zurück auf indicator_config_ids (API-Vertrag stabil); ORM-Schreibstellen bleiben indicator_config_ids_json; validation_alias für from_attributes-Mapping
  - api_testsets.py: TestSetOut.backtest_config_ids via validation_alias='backtest_config_ids_json' — API-Vertrag behält backtest_config_ids
  - runs.html: data.backtest_config/indicators_config → data.backtest_config_json/indicators_config_json (API liefert _json-Suffix)
  - results.html: data.actual_params → data.actual_params_json
  - user_data/tmp_analysis/eval_wf.py: Raw-SQL actual_params->> → actual_params_json->>
  - api_chart_playground.py: Docstring-Kommentar mit alten Attributnamen korrigiert

### Files
- services/api/routes/views_backtest.py
- services/api/routes/views_testsets.py
- services/api/routes/views_workflow.py
- services/api/routes/api_workflow.py
- services/api/routes/api_testsets.py
- services/api/routes/api_chart_playground.py
- services/frontend/templates/backtest/runs.html
- services/frontend/templates/backtest/results.html
- user_data/tmp_analysis/eval_wf.py



## [1.0.99] - 25.05.2026

### Changed
- Ticket 15 — Vorlagen- und Setup-Tabellen aufraeumen: JSON-Suffix-Sweep, Schema-Refactoring, Konverter-Pair
  - Einheitlicher _json-Suffix fuer alle JSON-Spalten: 11 Umbenennungen ueber backtest_runs, backtest_results, workflow_templates, testsets, leaderboard_entries (Suffix-Sweep Block 5)
  - strategy_configs: type-Spalte (hardcoded/generic), strategy_config_json hinzugefuegt, import_path nullable gemacht — XOR-Validierung in API
  - chart_playground_setups: config_json aufgeteilt in backtest_config_json, indicators_config_json, strategy_config_json, ui_state_json
  - testset_runs: indicator_config_id FK entfernt, indicators_config_json inline hinzugefuegt
  - leaderboard_entries.indicator_config_id FK-Constraint entfernt
  - indicator_configs.iteration_id: Integer-FK umgewandelt in String(50) ohne FK
  - Neuer Konverter backtest_config_row_to_json / json_to_backtest_config_row_kwargs in converters.py
  - Alembic-Migration a1b2c3d4e5f6 mit 6 sequenziellen Schritten, Backfill-Logik und chart_playground_setups-Guard fuer Test-DB
  - Code-Sweep: routes (api_backtest, api_config, api_workflow, api_testset_runs, api_leaderboard, api_chart_playground), worker_tasks, recompute, repository, repository_testsets, schemas angepasst
  - Alle Tests (84) gruen — Test-DB und Live-DB migriert, Container neugestartet
  - zielbild.md Abschnitt 3.5 aktualisiert

### Files
- alembic/versions/a1b2c3d4e5f6_ticket15_json_suffix_and_schema_cleanup.py
- user_data/utils/database/models.py
- user_data/utils/database/converters.py
- user_data/utils/database/repository.py
- user_data/utils/database/repository_testsets.py
- services/api/schemas.py
- services/api/routes/api_backtest.py
- services/api/routes/api_config.py
- services/api/routes/api_workflow.py
- services/api/routes/api_testset_runs.py
- services/api/routes/api_leaderboard.py
- services/api/routes/api_chart_playground.py
- services/api/worker_tasks.py
- services/api/recompute.py



## [1.0.98] - 25.05.2026

### Changed
- Test-DB auf Bind-Mount umgestellt (Nachbesserung Ticket 14)
  - db_vbt_v1_test: Named Volume db_vbt_v1_test_data ersetzt durch Bind-Mount ./data/postgres_test:/var/lib/postgresql/data (analog zur Arbeits-DB)
  - volumes:-Abschnitt in docker-compose-local.yml bereinigt — Eintrag db_vbt_v1_test_data entfernt
  - .gitignore: /data/ deckt data/postgres_test bereits ab, kein neues Pattern nötig
  - Altes Named Volume bt_pro_app_v1_db_vbt_v1_test_data gelöscht, neuer Container mit Bind-Mount gestartet
  - Schema-Initialisierung: backtest_schema.sql eingespielt, alle 9 Alembic-Migrationen bis Head angewendet
  - documentation/project/project-structure.md: Bind-Mount-Pfad und mkdir-Schritt im Test-DB-Setup-Abschnitt ergänzt
  - pytest: 84 passed, 23 deselected

### Files
- docker-compose-local.yml
- documentation/project/project-structure.md



## [1.0.97] - 25.05.2026

### Added
- Test-Infrastruktur: Dedizierte Test-DB, zentrale Fixtures, Safety-Check gegen Arbeits-DB (Ticket 14)
  - Neuer Docker-Compose-Service db_vbt_v1_test (TimescaleDB, Port 5562, Volume db_vbt_v1_test_data) in docker-compose-local.yml
  - Zentrale db_engine (session-scope) und session (function-scope) Fixtures in tests/conftest.py — Truncate-Pattern statt Rollback
  - Safety-Check: VBT_TEST_DATABASE_URL auf Port 5560 oder Host db_vbt_v1 bricht pytest mit harter Fehlermeldung ab
  - Duplikat-Fixtures aus 7 Test-Dateien entfernt (test_repository_testsets, test_repository_leaderboard, test_backtest_run_testset_link, test_leaderboard_aggregat, test_api_strategy, test_api_leaderboard, test_testset_runs_api)
  - Integration-Marker für Tests mit Prod-Daten-Abhaengigkeiten (Migrations-Seed, Repository-Fallback)
  - collect_ignore fuer vectorbtpro-abhaengige Dateien (kein WSL-Import moeglich)
  - alembic/env.py respektiert VBT_TEST_DATABASE_URL bei Migrationen gegen Test-DB
  - pytest.ini mit addopts=-m 'not integration' und Marker-Definition
  - Doku-Abschnitt in documentation/project/project-structure.md

### Files
- docker-compose-local.yml
- tests/conftest.py
- tests/test_repository_testsets.py
- tests/test_repository_leaderboard.py
- tests/test_backtest_run_testset_link.py
- tests/test_leaderboard_aggregat.py
- tests/test_api_strategy.py
- tests/test_api_leaderboard.py
- tests/test_testset_runs_api.py
- tests/test_chart_playground_no_rules_key.py
- alembic/env.py
- .env
- pytest.ini
- documentation/project/project-structure.md



## [1.0.96] - 25.05.2026

### Fixed
- Ticket 13 Nachbesserung: test_set_snapshot vollständig auf testset_snapshot umbenannt
  - DB-Spalte leaderboard_entries.test_set_snapshot per neuer Alembic-Migration 77563443bb87 auf testset_snapshot umbenannt
  - models.py: Spalte und Docstring aktualisiert
  - repository_testsets.py: Parameter, lokale Variable und LeaderboardEntry-Konstruktor-Aufrufe umgestellt
  - Tests (test_repository_leaderboard, test_api_leaderboard, test_leaderboard_aggregat): Fixture und Assertions auf testset_snapshot umgestellt
  - test_naming_conventions.py: Ausnahme fuer test_set_snapshot entfernt
  - Alle GEAENDERT-Kommentare mit test_set bereinigt — grep auf services/ und user_data/ liefert 0 Treffer
  - Smoke-Test TestSet-Run 186 (TestSet 293, 4 BacktestConfigs): 4 Backtest-Runs (1621-1624) completed, LeaderboardEntry 190 angelegt

### Files
- alembic/versions/77563443bb87_rename_test_set_snapshot_to_testset_.py
- user_data/utils/database/models.py
- user_data/utils/database/repository_testsets.py
- tests/test_repository_leaderboard.py
- tests/test_api_leaderboard.py
- tests/test_leaderboard_aggregat.py
- tests/test_naming_conventions.py
- tests/test_testset_runs_api.py
- tests/test_repository_testsets.py
- services/api/app.py
- services/api/routes/api_testset_runs.py
- services/api/routes/api_testsets.py
- services/api/routes/api_leaderboard.py
- services/api/routes/views_testsets.py
- services/frontend/templates/base.html



## [1.0.95] - 25.05.2026

### Changed
- Ticket 13: Naming-Cleanup — testset (ein Wort) als konsistenter Bezeichner im gesamten Projekt
  - DB-Tabellen umbenannt: backtest_equity/indicators/orders/params/positions/trades → backtest_result_*
  - DB-Tabelle test_sets → testsets, Spalte test_set_id → testset_id in testset_runs und leaderboard_entries
  - Alembic-Migration 7990cb8e2ca9 mit vollständigem upgrade/downgrade
  - Models: TestSet.__tablename__ = 'testsets', TestSetRun.testset_id, LeaderboardEntry.testset_id
  - Repository: Funktionen create_test_set/get/list/update/delete_test_set → create_testset/get_testset/list_testsets/update_testset/delete_testset
  - Route-Dateien: api_test_sets.py → api_testsets.py, views_test_sets.py → views_testsets.py
  - API-Prefix: /api/test-sets → /api/testsets, View-Prefix: /test-sets → /testsets
  - Templates: test_sets/ → testsets/, Kontext-Variable test_set → testset
  - Tests: test_repository_leaderboard, test_api_leaderboard, test_leaderboard_aggregat, test_backtest_run_testset_link, test_testset_runs_api aktualisiert
  - Neu: tests/test_naming_conventions.py — schlägt fehl bei verbotenem test_set_id im aktiven Code
  - Hinweis zur testset-Namenskonvention in documentation/project/zielbild.md Abschnitt 3.3 ergänzt

### Files
- alembic/versions/7990cb8e2ca9_naming_cleanup_backtest_result_und_.py
- user_data/utils/database/models.py
- user_data/utils/database/repository_testsets.py
- services/api/app.py
- services/api/routes/api_testsets.py
- services/api/routes/views_testsets.py
- services/api/routes/api_testset_runs.py
- services/api/routes/api_leaderboard.py
- services/api/routes/views_leaderboard.py
- services/frontend/templates/testsets/list.html
- services/frontend/templates/testsets/detail.html
- services/frontend/templates/leaderboard/index.html
- services/frontend/templates/base.html
- tests/test_naming_conventions.py
- documentation/project/zielbild.md



## [1.0.94] - 25.05.2026

### Changed
- Ticket 12: Chart-Playground-Runs registrieren Spec automatisch als StrategyIteration; _rules-Key-Trick aus BacktestRun.indicators_config entfernt
  - Auto-Iteration-Registrierung: register_or_get_iteration() in spec_iteration_registry.py — SHA-256-Hash-basierter Idempotenz-Lookup ueber strategy_iterations.spec_hash (neue Spalte via Alembic-Migration f1a2b3c4d5e6)
  - Versions-Schema fuer Auto-Iterationen: chart-YYYYMMDD-HHMM-<hash8>, Status draft
  - spec_runner.py: _rules-Fallback entfernt — rules_json ist Pflichtparameter (explizit uebergeben)
  - worker_tasks.py: Rules aus iteration.spec_json laden statt aus indicators_config['_rules']; Legacy-Pop als Sicherheits-Fallback fuer Altdaten
  - api_chart_playground.py: Start-Pfad registriert Iteration vor Run-Anlage; Read-Pfad (create_setup_from_result) liest Rules aus iteration.spec_json mit Legacy-Fallback
  - spec_strategy_start.py: _rules-Key entfernt, Iteration-Registrierung eingebaut
  - Neue Repo-Funktion: get_iteration_by_spec_hash(session, concept_id, spec_hash)
  - Sync-Skript scripts/sync_specs_to_iterations.py: idempotenter Einmal-Sync fuer bestehende Spec-Files
  - Specs-Verzeichnis als deprecated markiert (README)
  - Tests: test_spec_iteration_registry, test_chart_playground_no_rules_key, test_spec_runner_reads_iteration (15 neue Tests, alle gruen)

### Files
- user_data/strategies/generic/spec_iteration_registry.py
- user_data/strategies/generic/spec_runner.py
- user_data/strategies/generic/spec_strategy_start.py
- user_data/utils/database/repository_strategies.py
- user_data/utils/database/models.py
- services/api/routes/api_chart_playground.py
- services/api/worker_tasks.py
- alembic/versions/f1a2b3c4d5e6_add_spec_hash_to_strategy_iterations.py
- scripts/sync_specs_to_iterations.py
- user_data/strategies/generic/specs/README.md
- tests/test_spec_iteration_registry.py
- tests/test_chart_playground_no_rules_key.py
- tests/test_spec_runner_reads_iteration.py



## [1.0.93] - 25.05.2026

### Changed
- Ticket 11: Strategie-UI auf zweistufige Concepts/Iterations-Ansicht umgestellt; /backtest/results zeigt sprechende Concept/Iteration-Spalte; /backtest/start nutzt zweistufiges Dropdown mit iteration_id-Persistierung
  - views_config.py: /config/strategy zeigt jetzt strategy_concepts.html (Concept-Liste) und /config/strategy/concepts/{id} die Iterations-Liste
  - Neue Templates: config/strategy_concepts.html (CRUD-Modals via tabler.Modal, Obsidian-Link, Iterations-Anzahl) und config/strategy_concept_detail.html (spec_json-Viewer, Lineage-Kette, Archivieren)
  - api_backtest.py: /api/backtest/results und /api/backtest/results/dt joinen auf strategy_iterations + strategy_concepts und liefern concept_name + iteration_version
  - results.html: Strategie-Spalte zeigt 'VWMA-DWS / v2.0' wenn Iteration bekannt, sonst Legacy-strategy_name + Hinweis-Icon mit Tooltip
  - start.html: Strategie-Card mit zweistufigem Dropdown (sel-concept -> sel-iteration, Default: neueste aktive Iteration)
  - api_backtest.py /api/backtest/start: akzeptiert iteration_id als Alternative zu strategy_config_id; setzt BacktestRun.iteration_id direkt
  - tests/test_ticket11.py: 11 neue Tests (API DT-Felder, Frontend-Smoke, Start-Endpoint iteration_id-Schreibpfad)

### Files
- services/api/routes/api_backtest.py
- services/api/routes/views_config.py
- services/frontend/templates/config/strategy_concepts.html
- services/frontend/templates/config/strategy_concept_detail.html
- services/frontend/templates/backtest/results.html
- services/frontend/templates/backtest/start.html
- tests/test_ticket11.py



## [1.0.92] - 25.05.2026

### Changed
- Ticket 10: iteration_id FK an indicator_configs, backtest_runs, backtest_results — Backfill + Write-Pfad
  - Alembic-Migration c3f8a2d91e47 (down-revision 959be42e071a): iteration_id INT NULL REFERENCES strategy_iterations(id) an indicator_configs, backtest_runs, backtest_results
  - Indizes idx_indicator_configs_iteration und idx_backtest_runs_iteration
  - Backfill via Bulk-UPDATE-SQL im Upgrade-Pfad: Pass 1 per strategy_name-Mapping, Pass 2 Fallback auf v2.0 fuer generic/playground Runs — 100% Coverage nach Migration
  - SQLAlchemy-Models IndicatorConfig, BacktestRun, BacktestResult um iteration_id-Spalte und relationship erweitert
  - create_backtest_run() setzt iteration_id automatisch per get_iteration_by_strategy_name()-Lookup; Fallback auf Iteration v2.0 von vwma-dws bei keinem Mapping + Warning-Log
  - save_strategy_results() uebernimmt iteration_id konsistent aus dem Run in alle BacktestResult-Records
  - IndicatorConfig-Create und -Update in api_config.py berechnen iteration_id per Lookup auf strategy_name
  - Tests: 7 Unit-Tests (In-Memory-SQLite) + 3 Integrations-Tests (Backfill-Quote >= 95% pro Tabelle) — alle gruen

### Files
- alembic/versions/c3f8a2d91e47_add_iteration_id_fk_to_runs_results_configs.py
- user_data/utils/database/models.py
- user_data/utils/database/repository.py
- services/api/routes/api_config.py
- tests/test_iteration_id_write_path.py
- tests/test_iteration_id_backfill_quote.py



## [1.0.91] - 25.05.2026

### Added
- Ticket 09: Tabellen strategy_concepts + strategy_iterations mit Daten-Migration, Repository, API-Routes und Tests
  - Alembic-Migration 959be42e071a: Tabellen strategy_concepts + strategy_iterations mit CHECK-Constraints, UNIQUE-Index, FK-Constraints
  - Daten-Migration: Concept vwma-dws, Iteration v2.0 (mit spec_json aus vwma_v2_single.py), v1.0-hardcoded (archived), vwma_v2 (archived aus strategy_configs)
  - SQLAlchemy-Models StrategyConcept + StrategyIteration in models.py ergänzt
  - Repository repository_strategies.py: CRUD für Concepts + Iterations, get_iteration_by_strategy_name-Lookup (vwma_v2 + vwma_v2_spec -> v2.0)
  - REST-API services/api/routes/api_strategy.py: GET/POST/PUT /api/strategy/concepts + /api/strategy/iterations
  - Router in app.py registriert
  - 23 neue Tests in tests/test_api_strategy.py (Repository + FastAPI TestClient) - alle grün

### Files
- alembic/versions/959be42e071a_add_strategy_concepts_iterations.py
- user_data/utils/database/models.py
- user_data/utils/database/repository_strategies.py
- services/api/routes/api_strategy.py
- services/api/app.py
- tests/test_api_strategy.py



## [1.0.90] - 25.05.2026

### Changed
- Bulk-Delete Batch-Größe in `_delete_result_details` von 500 auf 5.000 erhöht (Ticket 08) — reduziert Append-Aufrufe über TimescaleDB-Hypertable-Chunks um Faktor 10

### Files
- services/api/routes/api_backtest.py



## [1.0.89] - 25.05.2026

### Changed
- Backtest-Configs auf 22/23-Zeitraum aktualisiert und Workflow-Menue in Konfiguration verschoben
  - Backtest-Configs 382 (BNBUSDT), 383 (BTCUSDT), 384 (DOGEUSDT) und 385 (FETUSDT) auf Zeitraum 2022-01-01 bis 2024-01-01 gesetzt (ohlc_start 2021-12-01, ohlc_end 2024-01-01); Titel auf 22/23 angepasst, (Kopie)-Suffixe entfernt
  - Bug in Config 382 korrigiert: ohlc_end stand auf 2022-01-01 statt 2024-01-01
  - Neues Test-Set 'Bullenmarkt 22/23' (id 293) mit den vier 22/23-Configs angelegt
  - Top-Level-Dropdown 'Workflow' aus der Navigation entfernt; 'Workflow-Templates' und 'Workflow-Runs' stehen jetzt als zwei einzelne Zeilen unter 'OHLC-Daten' im Konfiguration-Dropdown
  - Active-State-Logik fuer workflow_templates und workflow_runs in die Konfiguration-Bedingung uebernommen

### Files
- services/frontend/templates/base.html



## [1.0.88] - 24.05.2026

### Fixed
- Seed-Import restartet jetzt auch den app-Service (FastAPI/Frontend)
  - Nach DROP SCHEMA + pg_restore haelt der SQLAlchemy-Connection-Pool im app-Container alte Tabellen-OIDs -> 'could not open relation with OID' 500-Errors
  - RESTART_SERVICES um 'app' erweitert

### Files
- seed/import_seed.py



## [1.0.87] - 24.05.2026

### Added
- Seed-Snapshot-Mechanismus fuer lokale DB (export/import)
  - seed/export_seed.py: pg_dump -Fc des kompletten DB-Stands nach seed/data/seed.dump
  - seed/import_seed.py: Public-Schema droppen, TimescaleDB-Extension neu laden, pg_restore, vbt/worker/worker2 restarten
  - Snapshots gitignoriert (seed/data/.gitignore)
  - CLAUDE.md um Abschnitt 'Dev-DB-Reset (Seed-Snapshot)' erweitert
  - Einmaliges VACUUM FULL vor Erst-Snapshot durchgefuehrt (backtest_results/params/orders/trades/positions: ~3 GB Bloat -> ~18 MB)
  - Ersten Snapshot erzeugt: 9.14 MB

### Files
- seed/export_seed.py
- seed/import_seed.py
- seed/data/.gitignore
- CLAUDE.md



## [1.0.86] - 24.05.2026

### Changed
- Test-Set-Detail: Backtest-Auswahl als DataTable mit Checkboxen + Symbole-in-Beschreibung-Button; Test-Set-Liste: Aktionen als Icons
  - Detail-Seite (/test-sets/<id>): Multi-Select durch sortierbare DataTable mit Checkbox-Spalte ersetzt (Name, Symbol, Timeframe)
  - Header-Checkbox waehlt alle Zeilen der aktuellen Seite aus/ab
  - Neuer Button 'Symbole in Beschreibung uebernehmen' extrahiert unique Symbole der ausgewaehlten Configs und schreibt sie kommasepariert ins Beschreibungsfeld
  - Listen-Seite (/test-sets): Detail/Loeschen-Buttons auf Icon-Stil umgestellt (Stift + Muelleimer), analog /config/backtest

### Files
- services/frontend/templates/test_sets/detail.html
- services/frontend/templates/test_sets/list.html



## [1.0.85] - 24.05.2026

### Added
- Backtest-Config-Edit: OHLC-Vorschau-Chart mit Toolbar und Verfuegbarkeitsanzeige; Config-Liste mit Verfuegbarkeits-Warnungen und Schnellzugriff zum Downloader
  - Edit-Seite (/config/backtest/<id>): zweispaltiges Fluid-Layout (Form 5/12 links, Chart 7/12 rechts, sticky)
  - Mini-Chart mit Lightweight-Charts; drei vertikale Linien fuer OHLC Start (grau), Start (blau), End (rot); Default-Zoom auf Start/End mit 5% Padding
  - Chart-Toolbar rechtsbuendig wie im Playground: TF-Resampling-Buttons (>= Basis-TF), Nav-Anfang/-Ende, Fit
  - Default-Visual-TF = 1d bei feineren Basis-TFs fuer bessere Uebersicht
  - Verfuegbarkeits-Tabelle pro Symbol/Exchange (alle Timeframes mit Start/End/Bars) unter dem Zeitraum-Card
  - Datums-Aenderungen aktualisieren Linien/Zoom ohne erneuten OHLCV-Roundtrip
  - Listen-Seite (/config/backtest): Datumsformat dd.mm.yyyy fuer Anzeige, ISO bleibt fuer Sortierung
  - Listen-Seite: rote Markierung mit Tooltip fuer Datumsfelder ausserhalb des verfuegbaren OHLC-Bereichs
  - Listen-Seite: neuer 'OHLC'-Button (links vom Edit-Button) verlinkt direkt auf /config/data

### Files
- services/frontend/templates/config/backtest_config_edit.html
- services/frontend/templates/config/backtest_configs.html



## [1.0.84] - 24.05.2026

### Fixed
- Fehlende DataTables-i18n-Datei und Drill-Down-Modal im Leaderboard repariert
  - services/frontend/static/datatables-de.json angelegt - bislang 404 -> Warning 'i18n file loading error' in /test-sets und /leaderboard
  - Leaderboard-Drill-Down: bootstrap.Modal -> tabler.Modal (window.bootstrap ist im Tabler-Build nicht global, Modal-Klasse liegt auf window.tabler.Modal)

### Files
- services/frontend/static/datatables-de.json
- services/frontend/templates/leaderboard/index.html



## [1.0.83] - 24.05.2026

### Added
- Leaderboard-View (Ticket 07): API /api/leaderboard, Drill-Down-API und View /leaderboard mit Navigation
  - GET /api/leaderboard?test_set_id=<int>: LeaderboardEntries eines TestSets, default-sortiert nach total_return_avg DESC NULLS LAST, triggered_by via LEFT JOIN auf testset_runs (NULL wenn Run gelöscht)
  - GET /api/leaderboard/<entry_id>/drilldown: Pro-Config-Ergebnisse aus winning_result_ids inkl. executive_summary + mini_report; null-Positionen werden als missing:true markiert
  - View /leaderboard: Tabler-Seite mit TestSet-Dropdown, DataTable (sortierbar/filterbar), Row-Click öffnet Drill-Down-Modal mit Pro-Config-Tabelle
  - Navigation: Leaderboard-Eintrag in base.html ergänzt (nach Test-Sets)
  - 9 neue pytest-Tests (test_api_leaderboard.py): Default-Sort, NULL-Handling, Filter-Isolation, triggered_by via JOIN, Drilldown-Reihenfolge und null-Markierung

### Files
- services/api/routes/api_leaderboard.py
- services/api/routes/views_leaderboard.py
- services/frontend/templates/leaderboard/index.html
- services/frontend/templates/base.html
- services/api/app.py
- user_data/utils/database/repository_testsets.py
- tests/test_api_leaderboard.py



## [1.0.82] - 24.05.2026

### Added
- Aggregat-Berechnung nach Abschluss aller TestSet-Runs (Ticket 06): LeaderboardEntry wird automatisch im Worker-Prozess erstellt, sobald alle N BacktestRuns eines TestSetRuns completed sind.
  - build_leaderboard_entry_for_testset_run() in repository_testsets.py: ermittelt Sweep-Sieger (höchster total_return_pct) pro Run, berechnet Aggregate (avg/sum return, avg drawdown, avg sharpe), baut vollständige Snapshots (test_set_snapshot, indicator_config_snapshot, strategy_snapshot)
  - Reihenfolge der winning_result_ids folgt deterministisch der backtest_config_ids-Reihenfolge im TestSet-Snapshot
  - Edge-Case: leere Runs (0 Results) werden als null in winning_result_ids erfasst, hint-Feld gesetzt ('K von N Runs hatten keine Results')
  - Idempotenz: expliziter Existenz-Check vor Insert, IntegrityError-Fallback für Race-Conditions (UNIQUE-Constraint auf testset_run_id)
  - Worker-Hook in worker_tasks.py: _trigger_leaderboard_aggregation() nach status='completed' aufgerufen, Exceptions nur geloggt (kein Worker-Absturz)
  - backtest_config_id ins backtest_config-JSON bei TestSet-Run-Start gespeichert (deterministisches Mapping bei Aggregation)
  - 3 neue pytest-Tests: happy path (N=3, je 2 Results), leerer Run, Idempotenz

### Files
- user_data/utils/database/repository_testsets.py
- services/api/worker_tasks.py
- services/api/routes/api_testset_runs.py
- tests/test_leaderboard_aggregat.py



## [1.0.81] - 24.05.2026

### Added
- Ticket 05: TestSet-Lauf-Maske im Frontend mit API-Endpunkt, Worker-Increment-Logik und Tests
  - API-Endpunkt POST /api/testset-runs: legt testset_runs-Record an (status=queued, n_runs_total=N) und enqueued N Backtest-Runs parallel, einer pro BacktestConfig im TestSet
  - Worker-Increment-Logik: atomares SQL UPDATE testset_runs SET n_runs_completed = n_runs_completed + 1 nach jedem Run-Abschluss — kein ORM-Read-Modify-Write
  - Fail-Pfad: status=failed atomar via WHERE status NOT IN (completed, failed); Einzelstart-Pfad unveraendert
  - Completed-Pfad: status=completed + completed_at=NOW() wenn n_runs_completed >= n_runs_total; Hook-Kommentar fuer Ticket-06-Aggregat-Trigger
  - Frontend /backtest/start: Tab-Switch 'Einzel-Lauf' / 'TestSet-Lauf' mit Dropdowns TestSet, Strategie, IndicatorConfig; Erfolgs-Toast mit Link auf Run-Liste
  - Neue Test-Datei tests/test_testset_runs_api.py: 6 Tests fuer API-Logik, Validierung und atomare Increment-Logik (alle gruен)

### Files
- services/api/routes/api_testset_runs.py
- services/api/worker_tasks.py
- services/api/app.py
- services/frontend/templates/backtest/start.html
- tests/test_testset_runs_api.py



## [1.0.80] - 24.05.2026

### Added
- Ticket 04: BacktestRun.testset_run_id FK — optionale Zuordnung eines Backtest-Runs zu einem TestSet-Run
  - SQLAlchemy-Model BacktestRun: Spalte testset_run_id (Integer, FK auf testset_runs.id, nullable, indiziert) ergänzt
  - Alembic-Revision eae947b52264: Spalte, FK-Constraint (fk_backtest_runs_testset_run_id) und Index (ix_backtest_runs_testset_run_id) hinzugefügt — Up/Downgrade getestet
  - Repository-Funktion create_backtest_run: optionaler Parameter testset_run_id=None — Einzelstarts erzeugen NULL (unverändert)
  - 5 neue Pytest-Tests in tests/test_backtest_run_testset_link.py: Einzelstart NULL, Repository ohne/mit testset_run_id, FK-Integrität (IntegrityError bei ungültiger ID)

### Files
- user_data/utils/database/models.py
- user_data/utils/database/repository.py
- alembic/versions/eae947b52264_add_testset_run_id_fk_to_backtest_runs.py
- tests/test_backtest_run_testset_link.py



## [1.0.79] - 24.05.2026

### Added
- Ticket 03: Tabellen testset_runs und leaderboard_entries mit Alembic-Migration, Repository-Funktionen und Tests
  - SQLAlchemy-Models TestSetRun und LeaderboardEntry in models.py (SERIAL PK, JSONB-Snapshots, CHECK-Constraint auf status, UNIQUE auf testset_run_id, FK auf test_sets und indicator_configs)
  - Alembic-Migration 93def767e8a5: beide Tabellen + Index idx_leaderboard_test_set_return (test_set_id, total_return_avg DESC) + CHECK ck_testset_runs_status; Downgrade sauber implementiert
  - Repository-Funktionen in repository_testsets.py: create_testset_run, get_testset_run, update_testset_run_status (status + n_runs_completed + completed_at), create_leaderboard_entry (mit allen drei Snapshots: test_set_snapshot, indicator_config_snapshot, strategy_snapshot + winning_result_ids), get_leaderboard_entry, list_leaderboard_entries_for_test_set (sortiert nach total_return_avg DESC, NULLs zuletzt)
  - 13 neue Pytest-Tests in tests/test_repository_leaderboard.py: Anlage TestSetRun, Status-Transition, LeaderboardEntry mit allen Snapshots und winning_result_ids, Read-Back und Snapshot-Inhalts-Validierung, UNIQUE-Constraint, Sortierung

### Files
- user_data/utils/database/models.py
- user_data/utils/database/repository_testsets.py
- alembic/versions/93def767e8a5_add_testset_runs_and_leaderboard_.py
- tests/test_repository_leaderboard.py



## [1.0.78] - 24.05.2026

### Added
- Ticket 02: Tabelle test_sets mit vollständigem CRUD (Migration, API, Frontend, Tests)
  - SQLAlchemy-Model TestSet in models.py mit JSONB-kompatiblem TypeDecorator (PostgreSQL: JSONB, SQLite-Tests: JSON)
  - Alembic-Revision 9221c1669180: Tabelle test_sets anlegen (id SERIAL PK, name VARCHAR(255) NOT NULL UNIQUE, description TEXT, backtest_config_ids JSONB NOT NULL, created_at TIMESTAMP, created_by VARCHAR(120)) -- upgrade/downgrade getestet
  - Repository-Datei repository_testsets.py mit create/get/list/update/delete_test_set -- Validierung: fehlende backtest_config_ids werden mit klarer ValueError-Meldung (inkl. fehlende IDs) abgelehnt
  - API-Routen api_test_sets.py: GET /api/test-sets, GET /api/test-sets/{id}, POST (Validierung), PUT, DELETE -- Pydantic-Schemas inline -- HTTP 400 bei Validierungsfehler
  - Frontend-Views views_test_sets.py + Templates test_sets/list.html (DataTable: Name, Anzahl Configs, Erstelldatum) und test_sets/detail.html (Multi-Select über BacktestConfigs)
  - Nav-Eintrag Test-Sets in base.html ergänzt
  - 14 Pytest-Tests in test_repository_testsets.py: Create, Read (list+get), Update, Delete + Validierungsfehler (nicht-existierende IDs) -- alle 22 Tests (inkl. Ticket-01-Tests) grün

### Files
- user_data/utils/database/models.py
- user_data/utils/database/repository_testsets.py
- alembic/versions/9221c1669180_add_test_sets_table.py
- services/api/routes/api_test_sets.py
- services/api/routes/views_test_sets.py
- services/api/app.py
- services/frontend/templates/test_sets/list.html
- services/frontend/templates/test_sets/detail.html
- services/frontend/templates/base.html
- tests/test_repository_testsets.py



## [1.0.77] - 24.05.2026

### Added
- spec_runner.VERSION-Konstante und Spalten spec_runner_version in backtest_runs und backtest_results (Ticket 01)
  - spec_runner.py: VERSION = "1.0.0" am Modulanfang, SemVer-Konvention im Docstring dokumentiert (Major/Minor/Patch)
  - SQLAlchemy-Models: Spalte spec_runner_version VARCHAR(20) nullable an BacktestRun und BacktestResult ergänzt
  - Alembic-Migration 3715803d2a5d: ADD COLUMN spec_runner_version an beiden Tabellen, Downgrade implementiert, auf Dev-DB angewendet
  - Schreibpfade: create_backtest_run() und save_strategy_results() in repository.py um spec_runner_version-Parameter erweitert
  - Schreibpfade: run_backtest_job() in worker_tasks.py liest VERSION und übergibt ihn an save_strategy_results()
  - Schreibpfade: recompute_single_result() in recompute.py schreibt VERSION beim Metriken-UPDATE mit
  - Schreibpfade: api_backtest.py, api_chart_playground.py, api_workflow.py übergeben VERSION an create_backtest_run()
  - Tests: 8 pytest-Tests in tests/test_spec_runner_version.py — alle grün (VERSION-Format, Spalten nullable/nicht-nullable, Mocked-Engine-Insert)
  - Worker-Container nach Migration neu gestartet

### Files
- user_data/strategies/generic/spec_runner.py
- user_data/utils/database/models.py
- user_data/utils/database/repository.py
- alembic/versions/3715803d2a5d_add_spec_runner_version.py
- alembic/env.py
- alembic.ini
- services/api/worker_tasks.py
- services/api/recompute.py
- services/api/routes/api_backtest.py
- services/api/routes/api_chart_playground.py
- services/api/routes/api_workflow.py
- tests/test_spec_runner_version.py
- tests/conftest.py



## [1.0.76] - 23.05.2026

### Fixed
- Worker-Startup-Race: Postgres-Healthcheck verifiziert jetzt echte Query-Bereitschaft
  - pg_isready meldete bei TimescaleDB-Erststart faelschlich OK, weil der Postmaster mehrfach neu startet (initdb -> init-scripts -> restart)
  - Worker traf das Fenster und crashte mit psycopg2.OperationalError: 'the database system is starting up' beim Recovery-Lookup
  - Healthcheck erweitert um echten SELECT-1-Query: 'pg_isready && psql -c SELECT 1'
  - Aenderung in docker-compose-local.yml und docker-compose-staging.yml gespiegelt

### Files
- docker-compose-local.yml
- docker-compose-staging.yml



## [1.0.75] - 22.05.2026

### Added
- Bulk-Löschen für Backtest Runs und Results
  - Checkbox-Spalte und Select-All in /backtest/runs und /backtest/results
  - Neuer Button 'Auswahl löschen (N)' loescht alle markierten Eintraege in einer Operation
  - Neue API-Endpoints POST /api/backtest/runs/bulk-delete und POST /api/backtest/results/bulk-delete (Body: {ids: [...]})
  - Auswahl bleibt ueber Seitenwechsel und Auto-Reload erhalten (via Set + draw-Event-Restore)
  - Reduziert Roundtrips und Lock-Druck bei hoher Anzahl Runs/Results

### Files
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/runs.html
- services/frontend/templates/backtest/results.html



## [1.0.74] - 22.05.2026

### Fixed
- Worker-Container crashen nicht mehr in Restart-Loop, wenn Postgres beim Start noch in der Recovery-Phase ist
  - docker-compose-local.yml: Healthcheck fuer db_vbt_v1 via pg_isready (interval 5s, start_period 30s, retries 20)
  - docker-compose-local.yml: Healthcheck fuer redis_vbt_v1 via redis-cli ping (interval 5s, retries 10)
  - docker-compose-local.yml: worker, worker2, app und vbt warten via depends_on condition: service_healthy auf db_vbt_v1 (worker/worker2 zusaetzlich auf redis_vbt_v1)
  - Ursache: worker_start.py ruft beim Start sofort recover_stale_runs() auf - bei DB im Recovery-Zustand (FATAL: the database system is starting up) crashte der Container, restart unless-stopped fuehrte zur Endlos-Schleife
  - Lange depends_on-Form ersetzt die Kurzform, die nur auf Container-Start (nicht Service-Readiness) wartete

### Files
- docker-compose-local.yml



## [1.0.73] - 12.05.2026

### Changed
- Projekt-Rename auf bt_pro_app_v1, Port-Migration und Vault-Restrukturierung
  - Ordner-Rename vbt_app -> bt_pro_app_v1 inkl. Docker-Compose name, Dockerfile-FROM, vbt_settings.toml und Image-Retag (kein Rebuild)
  - Port-Migration lokal: PostgreSQL 5433 -> 5560, Redis 6380 -> 5561, pgAdmin 8081 -> 5563, FastAPI 8888 -> 5570 (Block 5560-5579, da 5520-5539 von einem anderen lokalen Projekt belegt)
  - project-structure.md durchgaengig auf bt_pro_app_v1 und neue Ports umgestellt
  - HANDOFF.md mit neuer Session-Sektion fuer 2026-05-12 aktualisiert

### Files
- docker-compose-local.yml
- services/api/Dockerfile
- vbt_settings.toml
- documentation/project/project-structure.md
- documentation/project/HANDOFF.md



## [1.0.72] - 11.05.2026

### Changed
- CLAUDE.md in Teil A (Standard) und Teil B (vbt_app-spezifisch) unterteilt, drei Anomalien behoben
  - Neue Zwei-Teilung: Teil A (A.1–A.14) für projektübergreifende Standards, Teil B (B.1–B.2) für vbt_app-spezifische Regeln
  - Anomalie 1: Obsolete CRITICAL-Zeile mit falschem project-structure.md-Pfad entfernt; dezenter Verweis in den Lead-Block verschoben
  - Anomalie 2: Umlaut-Regel dedupliziert — eine konsolidierte Formulierung in A.1, Duplikat aus A.3 entfernt
  - Anomalie 3: OBLIGATORISCH-VBT-MCP-Bullet aus A.2.1 (Think Before Coding) herausgelöst und als Schritt 1 in B.2.2 (VBT-Entwicklung Workflow) eingebaut
  - Alle bestehenden Inhalte vollständig erhalten und auf die neuen Unterabschnitte A.2.1–A.2.6 und A.3.1–A.3.6 verteilt

### Files
- CLAUDE.md



## [1.0.71] - 11.05.2026

### Changed
- Arbeitsweise aus einem Schwesterprojekt vollständig übernommen — CLAUDE.md, HANDOFF.md, Tickets-Konvention
  - CLAUDE.md: Vier Verhaltens-Prinzipien ergänzt (Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution) mit konkreten Regeln gegen typische LLM-Coding-Fehler
  - CLAUDE.md: Konzept-Doc-Regel hinzugefügt (erst nach drittem Erklären dokumentieren)
  - CLAUDE.md: File Organization & Modularity (max. 350 Zeilen, Single Responsibility)
  - CLAUDE.md: Security First, Error Handling, Pydantic-Schema-Suffix-Konvention ergänzt
  - CLAUDE.md: Docker-Regeln verschärft (benannte Volumes, Port-Regel Prod vs Local)
  - CLAUDE.md: WIP-Push-Verbot dokumentiert (commit.py vor push.py Pflicht)
  - CLAUDE.md: Gemini-Server-Sektion ausgebaut (Wann nutzen, Context Injection, Advisory-Hinweis)
  - CLAUDE.md: Handoff-Workflow und Tickets-Konvention als eigene Sektionen aufgenommen
  - CLAUDE.md: Post-Task Completion Protocol (pytest grün, Changelog, Handoff)
  - HANDOFF.md: Skelett angelegt unter documentation/project/HANDOFF.md mit HEAD-Block und initialem Session-Block
  - documentation/tickets/README.md: Tickets-Konvention dokumentiert (Namensschema, Regeln, Schema, Beispiel-Frontmatter)

### Files
- CLAUDE.md
- documentation/project/HANDOFF.md
- documentation/tickets/README.md



## [1.0.70] - 11.05.2026

### Changed
- Git-Workflow: Squash-Logik und WIP-Guard aus einem Schwesterprojekt übernommen
  - commit.py: Squash-Logik hinzugefügt — zusammenhängende WIP-Commits von HEAD abwärts werden per Soft-Reset zusammengefasst, bevor der reguläre Versions-Commit erstellt wird
  - commit.py: update_app_version() übernommen — synchronisiert APP_VERSION in der Projekt-Root .env bei jedem Commit automatisch
  - push.py: WIP-Guard hinzugefügt — Push wird blockiert wenn noch WIP-Commits in der Push-Range sind (Override via --allow-wip)
  - push.py: update-ref nach erfolgreichem Push hinzugefügt — aktualisiert den lokalen Tracking-Ref origin/main, damit commit.py den Squash-Bereich ohne git fetch korrekt ermitteln kann

### Files
- documentation/git/commit.py
- documentation/git/push.py



## [1.0.69] - 11.05.2026

### Changed
- Projekt-Doku auf neue schlanke Struktur umgestellt und Strategie-Konzept-Wissen nach Obsidian verlagert
  - docs/ Ordner komplett entfernt: ai-context/ (project-structure, deployment-infrastructure, spec, progress, docs-overview), CONTEXT-tier2/3, Beispiel-specs/open-issues, leere Platzhalter business/legal/design-brand
  - documentation/project/project-structure.md neu geschrieben als Briefing-Datei fuer Sub-Agents und Gemini (310 Z., 20 KB) — Tech-Stack, Service-Topologie, Spec-Runner-Pipeline, Multi-Combo-State-Primitiven, DB-Schema, Versionierungs-Streams, Smoke-Test
  - documentation/project/projekt.md schlank gemacht zur Ein-Seiten-Projektbeschreibung (Zweck, Nutzer, Architektur in einem Satz, Wissens-Trennung Projekt vs Obsidian)
  - documentation/project/VERSION_TEMPLATE.md entfernt (obsolet)
  - documentation/tickets/ Ordner angelegt als operativer Scope-Container fuer Feature-/Bug-/Refactor-Arbeit (flat, nummeriert)
  - user_data/strategies/vwma_dws/STRATEGY_OVERVIEW.md entfernt — Strategie-Konzept lebt jetzt in Obsidian unter <Vault>/30_Trading/strategies/vwma-dws/concept.md
  - scripts/ Ordner entfernt — split_indicator_config_22.py nach documentation/archive/ verschoben (obsoletes Einmal-Tool)
  - CLAUDE.md, GEMINI.md, STRATEGY_DEVELOPMENT_GUIDE.md, STRATEGY_DYNAMIC_ONBOARDING.md mit neuen Doku-Pfaden aktualisiert
  - .claude/hooks/ (subagent-context-injector, gemini-context-injector, README) auf neue Doku-Pfade umgestellt
  - .claude/skills/ (full-context, gemini-consult, code-review, refactor, handoff) auf neue Doku-Pfade umgestellt; update-docs Skill mit Deprecated-Hinweis versehen
  - GitHub-Repo umbenannt: vectorbtpro_app -> vbt_app (Remote-URL lokal aktualisiert)
  - Obsidian-Schema fuer Trading-Strategien etabliert: 7 Note-Typen (concept, iteration, bestvariante, source-channel, source-video, mandate, agent-session), Templates in 99_Meta/templates/, Status-Lifecycle idea -> implementing -> tested -> promoted -> archived
  - Obsidian-Konvention: Konzept-Note-Frontmatter ist maschinen-lesbar und kompatibel mit dem vbt_app Spec-Runner (indicators mit type_id, entry_rule/exit_rule im Rules-Engine-Format)
  - VWMA-DWS in Obsidian neu organisiert: concept.md (ersetzt overview.md), bestvarianten/2026-04-17_dyn-v0.41_cross-symbol.md, iteration-Notes dyn-v0.40/dyn-v0.41 mit implementation-Feld ergaenzt

### Files
- docs/
- documentation/project/project-structure.md
- documentation/project/projekt.md
- documentation/tickets/
- documentation/archive/split_indicator_config_22.py
- user_data/strategies/vwma_dws/STRATEGY_OVERVIEW.md
- user_data/strategies/STRATEGY_DEVELOPMENT_GUIDE.md
- user_data/strategies/vwma_dws/STRATEGY_DYNAMIC_ONBOARDING.md
- CLAUDE.md
- GEMINI.md
- .claude/hooks/
- .claude/skills/
- scripts/



## [1.0.68] - 17.04.2026

### Added
- dyn-v0.41 Cross-Symbol-Validierung bar2+AssetDD-Schichten abgeschlossen
  - 96 Runs (12 Symbole x 8 td_stop) x 4116 Indikator-Kombis = 395.136 Backtests erfolgreich durchgelaufen, keine Fehler
  - Pro-Symbol-Plateau-Bestvariante nach mean-0.5*std Sharpe ueber 8 td_stop ermittelt
  - 9/12 Symbole erfuellen alle Akzeptanz-Kriterien (mean>=0.8, min>=0.3, wdd>=-35%) vs 2/12 in dyn-v0.40 Baseline
  - 10/12 Symbole verbessern mean-Sharpe, 11/12 verbessern worst-DD durch die Schichten
  - Spitzen-Deltas: FETUSDT +0.92 Sharpe / +34.7pp DD, TRXUSDT +0.48 / +29.6pp, ETHUSDT +0.42 / +25.9pp, BTCUSDT +0.12 / +27.8pp
  - Grenzfaelle (wdd knapp ueber -35%): LINKUSDT -42.4%, XRPUSDT -39.0%, BNBUSDT -37.9% - Kandidaten fuer AssetDD-Feintuning
  - Median-Max-DD auf FETUSDT td=8 Param-Raster von -45.8% auf -27.2% gesunken, profitable Kombis von 1/4116 auf 3399/4116 gestiegen
  - Ergebnis-Block und Session-Update in STRATEGY_DYNAMIC.md eingetragen

### Files
- user_data/strategies/vwma_dws/STRATEGY_DYNAMIC.md



## [1.0.67] - 17.04.2026

### Added
- Multi-Combo-State-Primitiven in rules_engine.py + zweiter Worker-Container
  - rules_engine.py: since_entry, entry_price, max_price_since_entry, min_price_since_entry vektorisieren pro Combo-Column (DataFrame-Input statt nur Series). Erlaubt bar2-Exit und aehnliche State-Rules im Multi-Combo-Sweep.
  - 4 Numba-kompilierte 2D-Kernel (_cooldown_filter_2d, _entry_pos_ffill_2d, _entry_price_ffill_2d, _rolling_extreme_since_entry_2d) fuer Performance bei grossen Sweeps.
  - State-Primitiv-Guard in evaluate_rules entfernt. Single-Combo-Pfad (Series-Input) bleibt backward-kompatibel.
  - Smoke-Tests: Single-Combo + bar2 Regression passt (998 entries / 125 exits), Multi-Combo 4-Kombi-Sweep funktioniert, State-Werte pro Column identisch zu Einzel-Berechnung.
  - docker-compose-local.yml: zweiter RQ-Worker-Container (worker2) auf denselben Queues fuer Parallelisierung groesserer Sweeps. Recovery-Script laeuft weiter nur ueber Worker #1 um Race-Conditions zu vermeiden.

### Files
- user_data/strategies/generic/rules_engine.py
- docker-compose-local.yml



## [1.0.66] - 17.04.2026

### Added
- dyn-v0.40 W1-Auswertung in STRATEGY_DYNAMIC.md dokumentiert
  - 12 Symbole x 8 td_stop-Werte = 96 Runs mit je 4116 Indikator-Kombis durchgelaufen, alle completed, 394.736 Backtests persistiert
  - Pro-Symbol-Plateau-Bestvarianten nach mean-0.5*std Sharpe ueber 8 td_stop-Werte ermittelt
  - Haupthypothese bestaetigt: alle 12 Symbole Sharpe-profitabel bekommbar (mean-Sharpe 1.37-3.25, min-Sharpe 0.89-2.70)
  - Max-DD-Akzeptanzkriterium (<=-35%) nur von AVAXUSDT und ADAUSDT erfuellt, 10/12 Symbole verletzen es wegen 2022-Bearmarket-Anteil und fehlender DD-Schutzschichten
  - Spec-Abweichungen dokumentiert: nur W1 statt W1-W5, groesserer Param-Space 7x7x7x12 statt 4x4x4x8, Plateau-Score ueber td_stop statt ueber Fenster
  - Cross-Symbol-Muster: below_pct=1.0 dominiert bei 6/12 Symbolen (BTC, ETH, LINK, TRX, DOGE, BNB), High-Vol bei 8-10 (FET, AVAX, SOL), Mitte bei 3/12
  - Session-Update-Block fuer 2026-04-17 ergaenzt mit offenen Folge-Schritten (W2-W5-Rollout, bar2+AssetDD auf Cross-Symbol-Bestvarianten, Weg B dwsQuantileBand Pilot)

### Files
- user_data/strategies/vwma_dws/STRATEGY_DYNAMIC.md



## [1.0.65] - 15.04.2026

### Added
- rules_engine: State-Primitiv-Guard fuer Multi-Combo-Sweeps und dyn-v0.40 Pilot durchgefuehrt
  - evaluate_rules() wirft jetzt einen klaren ValueError, wenn Exit-Rules State-Primitiven (since_entry, entry_price, max_price_since_entry, min_price_since_entry) referenzieren und gleichzeitig die Entries ein DataFrame mit mehr als einer Spalte sind (Multi-Combo-Sweep). Vorher hat _entries_to_series() stillschweigend .iloc[:, 0] genommen und den State fuer alle Combos aus der ersten Column abgeleitet - semantisch falsch, aber ohne Fehler-Signal.
  - Neue Helper-Funktion _rule_group_uses_state_refs() prueft rekursiv, ob eine Rule-Group eine State-Primitive referenziert. State wird nur noch berechnet wenn wirklich gebraucht.
  - Regression-Check mit 4 Szenarien: A Single-Combo ohne State, B Multi-Combo ohne State, C Single-Combo mit since_entry-Exit (Backward-Compat), D Multi-Combo + since_entry (muss ValueError werfen) - alle 4 bestanden.
  - dyn-v0.40 Pilot auf FETUSDT W1 (2020-02-01 bis 2022-02-01) durchgefuehrt. Phase 1 Mini (32 Kombinationen) und Phase 2 Full (512 Kombinationen, Pine-Urstrategie mit dwsCrossover bidirektional) beide erfolgreich ausgefuehrt. Durchsatz 53 Kombinationen/Sekunde im run_spec_strategy-Pfad.
  - Pilot-Sanity-Check: Die Pine-Urstrategie-Top-Kombinationen auf FET W1 liegen NICHT in der aus dyn-v0.1-0.35 bekannten Sweet-Spot-Zone (below_pct 1.0-2.0, fast_sma_length 6-7). Top-Sharpe 1.76 bei below_pct=1.5, vwma_length=4, fast_sma 8/8. Die Top-10 below_pct-Werte verteilen sich ueber den gesamten Bereich (1.5 bis 4.5). Das bestaetigt die dyn-v0.39-Meta-Erkenntnis empirisch: die unidirektionale Sweet-Spot-Zone der dyn-v0.x-Reihe ist eine andere Zone als die bidirektionale Pine-Urstrategie-Zone. Die Multi-Combo-Infrastruktur ist damit vollstaendig validiert und einsatzbereit fuer den 6-Batch-Rollout auf den 12 Symbolen.
  - Hinweis: Der in STRATEGY_DYNAMIC.md dokumentierte 'spec_runner Single-Combo Blocker' war bereits in 1.0.61 durch den Wechsel auf _expand_range + param_product=True behoben. Die vorliegende Session hat die verbleibende Luecke (silent state-primitive fallback) geschlossen und den Pilot ausgefuehrt, der zeigt dass die Pipeline end-to-end funktioniert.

### Files
- user_data/strategies/generic/rules_engine.py



## [1.0.64] - 15.04.2026

### Fixed
- OHLC-Update-Endpoint: Einzel-Symbol-Loop statt wide-Merge verhindert Datenverlust
  - Bug: Der Aktualisieren-Button (POST /api/config/data/update) hat vbt.BinanceData.from_hdf aufgerufen, das alle Symbole in ein gemeinsames wide-Data-Objekt laedt. Bei Symbolen mit stark abweichendem Listing-Datum (z.B. TONUSDT 2024 vs BTCUSDT 2019) warnte vbt mit Symbols have mismatching index. Setting missing data points to NaN und verwarf dabei die spaet gelisteten Symbole - sie waren nach dem Update aus der HDF verschwunden
  - Fix: Der Update-Worker iteriert jetzt pro existierendem HDF-Key und ruft vbt.BinanceData.from_hdf(paths=datafile, symbols=sym) einzeln auf, gefolgt von .update() und .to_hdf(). Jedes Symbol behaelt seinen eigenen Index, kein wide-Merge mehr
  - Nebenbei: pandas als pd importiert, um existing_symbols per HDFStore zu ermitteln
  - Sichtbar geworden als nur 12 von 16 Symbolen in ohlcv_4h_binance.h5 nach einem Update-Klick - APT, ICP, SHIB, TON waren weg. Nach Re-Download und Fix sind alle 16 mit echten Listing-Daten wieder da

### Files
- services/api/worker_tasks.py



## [1.0.63] - 15.04.2026

### Fixed
- OHLC-Download: NaN-Padding vor Listing-Datum beseitigt (Einzel-Symbol-Pull statt Multi-Symbol-Pull)
  - run_ohlc_download_job pullt jetzt pro Symbol einzeln via vbt.BinanceData.pull, statt alle Symbole in einem Aufruf zu buendeln
  - Grund: vbt.Data erzwingt bei Multi-Symbol-Pulls einen gemeinsamen Index, wodurch Zeilen vor dem jeweiligen Listing-Datum mit NaN aufgefuellt wurden (z.B. APTUSDT zeigte faelschlich Daten ab 2019-12-01)
  - Pro-Symbol-Pull liefert nur die tatsaechlich auf Binance verfuegbaren Bars; Fehler einzelner Symbole brechen den Gesamtjob nicht mehr ab, sondern werden in der message gesammelt
  - Symbol-Duplikate werden vor dem Pull dedupliziert (behebt Duplicate keys provided Fehler)
  - 4h-Datei wurde komplett neu geladen, echte Listing-Daten sichtbar (APT 2022-10, TON 2024-08, ICP/SHIB 2021-05, SOL 2020-08, AVAX 2020-09)

### Files
- services/api/worker_tasks.py



## [1.0.62] - 15.04.2026

### Changed
- OHLC-Datenverwaltung: Symbol-Tabellen pro Datei sind jetzt sortierbar (DataTables)
  - Spalten Symbol, Bars, Start und End in /config/data per Klick sortierbar
  - DataTables-Init nach jedem loadFiles-Aufruf, destroy vor Re-Init um Mehrfach-Instanzen zu vermeiden
  - Paging, Info und Suche deaktiviert - nur Sortierung aktiv

### Files
- services/frontend/templates/config/data_files.html



## [1.0.61] - 15.04.2026

### Changed
- spec_runner Pipeline auf Always-Range umgestellt (Single-Pfad fuer Single-Combo und Multi-Combo)
  - indicator_factory._collapse_range entfernt, durch _expand_range ersetzt - jeder Parameter wird jetzt immer als Array behandelt (Length 1 fuer Skalare, Length N fuer arange/Listen)
  - build_indicators ruft factory.run(..., param_product=True) immer auf - Length-1-Arrays erzeugen 1 Kombi (Single-Combo-Sonderfall), Length-N-Arrays erzeugen den kartesischen Produkt-Sweep
  - Kein Branching mehr zwischen Single-Combo und Multi-Combo: ein einziger Code-Pfad, rules_engine und spec_runner sind durch bereits vorhandenes vbt.broadcast und DataFrame-Handling beide Faelle abgedeckt
  - rules_engine.py unveraendert - State-Primitiven (since_entry etc.) funktionieren weiter, weil sie 1D bleiben und via vbt.broadcast gegen MultiIndex-Columns gebroadcastet werden
  - Unblockt dyn-v0.40 Parameter-Sweep ueber spec_runner mit der Pine-Urstrategie (dwsCrossover bidirektional)
  - Regression-Tests (4 Szenarien): Single-Combo backward-compat, Multi-Combo 3x3 Sweep, State-Primitiv (since_entry) in Single-Combo, End-to-End DB-Integration mit 9 Kombinationen und korrekten actual_params - alle bestanden
  - Docstring-Notizen 'Aktuell Single-Combo' in spec_runner.py und indicator_factory.py entfernt

### Files
- user_data/strategies/generic/indicator_factory.py
- user_data/strategies/generic/spec_runner.py



## [1.0.60] - 15.04.2026

### Added
- Neuer Custom-Indikator dwsCrossover fuer bidirektionale Cross-Detektion
  - Emuliert Pine Script's ta.cross(a, b) Semantik: feuert an jedem Bar an dem zwei Zeitreihen das Vorzeichen ihrer Differenz wechseln, in beide Richtungen (up-cross und down-cross).
  - Einsatzzweck: Mean-Reversion-Strategien die sowohl das Dip-Signal (Preis faellt unter Schwelle) als auch das Bounce-Signal (Preis steigt von unten zurueck ueber Schwelle) als gueltige Entries nehmen wollen. Das Bounce-Signal ist empirisch der hoehere Anteil des Alphas, weil es nicht in ein fallendes Messer greift sondern auf die Recovery-Bewegung wartet.
  - API: Inputs series_a und series_b (beliebige Zeitreihen), Parameter keine, Output 'result' als Numpy-Array mit 1.0 an Cross-Bars und 0.0 sonst.
  - Verwendung in Rules-Engine-Specs ueber 'custom:dwsCrossover' und Entry-Condition 'ind:<id>:result == 1'.
  - Hintergrund: Beim Reproduktions-Versuch der TradingView-Urstrategie auf DOGEUSDT hat sich herausgestellt, dass der bisher verwendete unidirektionale Crossover-Nachbau (low <= vwma_below und low_prev > vwma_below) 41 von 322 Signalen verpasste - genau die profitablen Bounce-Signale in Rally-Phasen. Mit dem neuen Indikator stieg die PnL von +210 USDT auf +389 USDT (83% Parity zur TradingView-Referenz).

### Files
- user_data/utils/indicators/custom.py



## [1.0.59] - 15.04.2026

### Fixed
- Playground-Chart: VWMA friert nicht mehr ein bei Symbolen mit OHLCV-Gap-Bars
  - Compute-Endpunkt im Chart-Playground hat bei gleichem Ziel- und Quell-Timeframe unnoetig resampled.
  - pandas.resample baut ein lueckenloses Zeit-Gitter auf und erzeugt NaN-Slots fuer fehlende Index-Eintraege (z.B. Binance-Wartungsfenster 2020-02-19 12:00). Close/Open/High/Low wurden NaN, Volume wurde 0 - asymmetrisches dropna() fuehrte zu Index-Mismatch, talib.SUM lockte permanent auf NaN, realign_closing ffillte den letzten validen Wert bis zum Ende.
  - Visueller Effekt: VWMA-Linie auf LINKUSDT, BTCUSDT, ETHUSDT, FETUSDT etc. als konstante Gerade ab 2020-02-19.
  - Betroffen nur das Chart-Rendering im Playground - der Backtest-Worker laedt Daten ueber vbt.Data.from_hdf und ist vom Bug nicht betroffen. Alle bisherigen Iterationen und Leaderboard-Zahlen bleiben valide.
  - Fix: Wenn spec.timeframe dem req.timeframe entspricht, wird target_tf auf None gesetzt und der Resample-Pfad komplett uebersprungen. Resample findet nur noch statt wenn ein Indikator explizit auf einem hoeheren TF rechnen soll.

### Files
- services/api/routes/api_chart_playground.py



## [1.0.58] - 15.04.2026

### Fixed
- OHLC-Download scheiterte beim Mergen mit bestehenden HDF5-Daten (tz_convert-Mismatch)
  - Ursache: vbt.BinanceData.merge([existing, new]) verlangt identische tz_convert-Settings zwischen from_hdf-Objekt und frisch gepullten Daten, sonst 'Objects to be merged must have compatible tz_convert'
  - Fix: Merge-Logik komplett entfernt. vbt.Data.to_hdf() schreibt pro Symbol einen eigenen HDF-Key via pd.DataFrame.to_hdf und laesst existierende Keys unberuehrt -- dadurch werden neue Symbole einfach appended, gleiche Symbole beim erneuten Download ueberschrieben
  - Die 5 zuvor fehlgeschlagenen Jobs (XRP, SOL, AVAX, LINK, DOGE) wurden nach dem Fix erfolgreich abgeschlossen

### Files
- services/api/worker_tasks.py



## [1.0.57] - 15.04.2026

### Fixed
- OHLC-Download-Jobs blieben im Status queued haengen (RQ-Enqueue TypeError)
  - Ursache: q.enqueue(..., job_id=int) hat den reservierten RQ-Kwarg job_id (Job-ID, muss String sein) ueberschrieben, nicht an die Task-Funktion weitergereicht.
  - Fix: Funktions-Argumente explizit ueber kwargs={'job_id': ...} uebergeben
  - 5 haengende Jobs wurden nachtraeglich in die Queue eingereiht und laufen jetzt an

### Files
- services/api/routes/api_config.py



## [1.0.56] - 15.04.2026

### Changed
- Default-Startdatum im OHLC-Download-Formular auf 2019-12-01 gesetzt

### Files
- services/frontend/templates/config/data_files.html



## [1.0.55] - 15.04.2026

### Added
- Neue Seite /config/data zur Verwaltung der OHLC-HDF5-Dateien mit Download, Update, Delete
  - Uebersicht aller HDF5-Dateien unter user_data/ohlc_data/ mit Symbol-Liste, Bar-Count, Start/End-Datum (schnelles Metadaten-Lesen via pd.HDFStore.get_storer.nrows, ohne OHLC zu laden)
  - Download-Formular fuer neue Binance-Symbole: Exchange/Timeframe/Symbole/Start-/End-Date -> asynchroner Job via neuer Redis-Queue 'ohlc_download'
  - Update-Button pro Datei: ruft vbt.BinanceData.from_hdf(...).update(end=now).to_hdf(...) im Worker auf
  - Delete-Button pro Symbol: entfernt Key direkt aus HDF5-Datei via HDFStore.remove
  - Job-Status-Polling alle 2s, automatische Dateiliste-Aktualisierung nach Abschluss
  - Neue DB-Tabelle ohlc_download_jobs + SQLAlchemy-Model OhlcDownloadJob fuer Job-Tracking
  - Neuer Worker-Task run_ohlc_download_job in worker_tasks.py; Queue-Name in redis_conn.py als Konstante; docker-compose-local.yml Worker-Command um 'ohlc_download' erweitert
  - Nav-Eintrag 'OHLC-Daten' unter Konfiguration

### Files
- user_data/utils/database/schema/backtest_schema.sql
- user_data/utils/database/models.py
- services/api/redis_conn.py
- services/api/worker_tasks.py
- services/api/routes/api_config.py
- services/api/routes/views_config.py
- services/frontend/templates/config/data_files.html
- services/frontend/templates/base.html
- docker-compose-local.yml



## [1.0.54] - 15.04.2026

### Changed
- Symbol-Auswahl in Backtest-Config als Dropdown der verfuegbaren HDF5-Symbole
  - Neuer Endpoint GET /api/config/symbols?exchange=...&timeframe=... liest Top-Level-Keys aus user_data/ohlc_data/ohlcv_{tf}_{exchange}.h5 via pandas HDFStore
  - Template backtest_config_edit.html: Freitext-Input fuer Symbol durch Select ersetzt, laedt initial und bei Exchange-/Timeframe-Aenderung neu
  - Bei fehlender HDF5-Datei oder nicht vorhandenem bisherigen Symbol wird eine Hinweismeldung angezeigt

### Files
- services/api/routes/api_config.py
- services/frontend/templates/config/backtest_config_edit.html



## [1.0.53] - 14.04.2026

### Added
- Custom-Indikator dwsVolumeRatio als Infrastruktur fuer Volume-basierte Filter
  - Neuer Custom-Indikator dwsVolumeRatio berechnet das Verhaeltnis des aktuellen Volumens zum rollenden Volume-Durchschnitt ueber N Balken
  - Inputs: volume. Params: window. Output: result (>1.0 ueberdurchschnittlich, <1.0 unterdurchschnittlich)
  - Wurde in der VWMA-Strategie als Entry-Filter getestet (dyn-v0.37) und als kontra-produktiv verworfen — hohe Volume-Peaks bei Pullbacks signalisieren Liquidation, nicht Kaufinteresse. Bleibt als Infrastruktur verfuegbar fuer zukuenftige Strategien

### Files
- user_data/utils/indicators/custom.py



## [1.0.52] - 14.04.2026

### Fixed
- Delete-Routinen setzen workflow_run_items.run_id jetzt auf NULL, wenn referenzierte Runs geloescht werden
  - DELETE /api/backtest/results/{id}, DELETE /api/backtest/runs/{id}, DELETE /api/backtest/results und DELETE /api/backtest/runs raeumen jetzt workflow_run_items mit auf, sodass keine Waisen mit stale run_ids entstehen
  - Neue Helper: _nullify_workflow_items_for_runs(session, run_ids) setzt gezielt auf NULL, _nullify_workflow_items_for_missing_runs(session) als Sicherheitsnetz fuer Bulk-Deletes
  - Workflow-Historie (Template-Name, Workflow-Run-Status) bleibt erhalten, nur der run_id-Pointer wird nullifiziert, um DB-Konsistenz zu sichern
  - Zusaetzliche Altlast-Bereinigung: einen hartnaeckig in 'running' haengenden Workflow-Run (Workflow #9 vom 2026-04-07 mit 3 Items auf toten Runs) plus drei Zombie-Playground-Setups (IDs 11/12/13 mit Referenzen auf geloeschte Results) manuell entfernt

### Files
- services/api/routes/api_backtest.py



## [1.0.51] - 14.04.2026

### Fixed
- Playground-Setup aus Backtest-Result laedt Indikator-Chains jetzt korrekt (topologische Sortierung)
  - POST /api/chart-playground/setups/from-result/{id} sortiert die Indikatoren jetzt topologisch anhand ihrer inputs-Chain-Dependencies, bevor das Setup gespeichert wird
  - Hintergrund: PostgreSQL JSONB speichert dict-Keys nach Laenge/Alphabet, nicht nach Insertion-Order. Dadurch konnten chained Indikatoren (z.B. VWMA mit src=ind:fast_sma:result) im Setup vor ihrer Dependency landen. Der Playground-Frontend rendert Input-Dropdowns mit vorher definierten Indikatoren als Chain-Optionen - war die Reihenfolge falsch, fiel das src-Feld still auf Open zurueck
  - Fix in api_chart_playground.py: neuer _topo_sort_indicators()-Helper im from-result-Endpoint, scannt ind.inputs nach ind:<name>:-Referenzen und reiht sie in korrekter Abhaengigkeits-Reihenfolge in die Setup-config_json ein

### Files
- services/api/routes/api_chart_playground.py



## [1.0.50] - 14.04.2026

### Fixed
- Legacy-Strategie-Results koennen als Playground-Setup geoeffnet werden
  - renderRules crashte mit 'Cannot read properties of null' wenn ein Setup rules.entry=null enthielt. Jetzt wird defensiv auf leeres AND-Default gesetzt
  - setups/from-result normalisiert jetzt Legacy-Indikator-IDs: 'dwsFastSMA' -> 'custom:dwsFastSMA', 'supertrend' -> 'vbt:SUPERTREND' usw. via _extract_factory-Probe
  - Parameter-Aliase werden angewendet: Legacy speichert 'multiplier', die Factory erwartet 'mult' - analog zu indicator_factory._PARAM_ALIASES
  - Fehlende Inputs werden per OHLCV-Default aufgefuellt (z.B. supertrend bekommt high/low/close automatisch), damit der Playground das Setup ohne weitere Anpassungen rendern kann

### Files
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html



## [1.0.49] - 14.04.2026

### Changed
- Startdatum und Enddatum in der Results-Tabelle in deutscher Notation
  - results.html zeigt start_date und end_date jetzt als DD.MM.YYYY statt YYYY-MM-DD
  - Neuer fmtDateDe-Helper wandelt ISO-Datum in deutsche Schreibweise

### Files
- services/frontend/templates/backtest/results.html



## [1.0.48] - 13.04.2026

### Added
- Button "In Playground oeffnen" auf der Result-Chart-Seite
  - Neuer Endpoint POST /api/chart-playground/setups/from-result/{result_id} erzeugt aus einem Backtest-Result ein komplettes Playground-Setup: liest run.indicators_config und run.backtest_config, ersetzt Range-Parameter durch die konkreten Werte aus result.actual_params, zieht Indikator-Metadaten (inputNames/outputNames/paramsMeta) per _extract_factory aus der Registry und speichert das Ganze als ChartPlaygroundSetup
  - Button auf der Chart-Seite (result_chart.html) ruft den Endpoint und navigiert direkt zu /chart-playground?setup=<id>
  - Playground init liest ?setup=<id> aus der URL und laedt das Setup automatisch via applySetupConfig

### Files
- services/api/routes/api_chart_playground.py
- services/frontend/templates/backtest/result_chart.html
- services/frontend/templates/chart_playground/index.html



## [1.0.47] - 13.04.2026

### Fixed
- Favoriten-Results werden bei Alle-Loeschen auf der Runs-Seite nicht mehr mitgeloescht
  - DELETE /api/backtest/runs hat bisher alle Runs und Results blind entfernt, ohne den is_favorite-Status zu beachten. Jetzt respektiert der Endpoint Favoriten analog zu DELETE /api/backtest/results: nicht-favoritisierte Results werden inkl. Detail-Daten geloescht, verwaiste Runs (ohne verbleibende Results) werden entfernt, Runs mit Favoriten bleiben mit ihren Favoriten-Results erhalten
  - Confirm-Dialog der Runs-Seite weist jetzt auf die Favoriten-Ausnahme hin

### Files
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/runs.html



## [1.0.46] - 13.04.2026

### Fixed
- Drawdown-Baender bleiben auf allen TFs und beim Toggle-Cycling sichtbar
  - Das epochbasierte Bucket-Floor (Math.floor(ts/targetSec)*targetSec) hat bei 1w nicht zu den tatsaechlichen Wochen-Anfaengen der Kerzen gepasst (Unix-Epoche startet Donnerstag) - timeToCoordinate hat dann null zurueckgegeben und nichts wurde gezeichnet. Neuer _snapPeriodsToCandleTimes-Helper snappt stattdessen auf die tatsaechlichen Timestamps der aktuell gesetzten Kerzen via Binaersuche
  - Zentraler _applyDrawdownBands-Helper wird von Toggle-Handler UND TF-Switcher genutzt. Bisher fehlte dem Toggle-Handler die Snap-Logik - nach Off/On-Cycle auf einem Nicht-Basis-TF waren die Timestamps falsch ausgerichtet
  - Redraw-Forcing per detach/attach wie im orderPrimitive-Pattern, damit nach mehrfachem Cycling der letzte Attach auch wirklich neu zeichnet
  - Neues currentCandles-Modul-Var haelt den aktuell auf candleSeries gesetzten Kerzenstand vor - dient als Snap-Referenz

### Files
- services/frontend/templates/backtest/result_chart.html



## [1.0.45] - 13.04.2026

### Fixed
- Drawdown-Baender bleiben beim Wechsel des Chart-Timeframes erhalten
  - Der TF-Switcher hat bisher nur das OrderPrimitive auf das neue Timeframe-Bucket gesnappt und neu angehaengt - das DrawdownBandPrimitive blieb auf dem alten candleSeries-State haengen und wurde nicht mehr gezeichnet
  - Jetzt wird das Primitive beim TF-Wechsel detached, die Drawdown-Perioden (start/end) auf die Bucket-Sekunden des neuen TF gesnappt und ein neues Primitive an candleSeries angehaengt

### Files
- services/frontend/templates/backtest/result_chart.html



## [1.0.44] - 13.04.2026

### Changed
- Drawdown-Visualisierung als vertikale Hintergrundbaender pro Drawdown-Periode
  - chart-data-Endpoint liefert jetzt drawdown_periods statt running_max/drawdown-Zeitreihen. Jede Periode hat start (letzter Peak), valley (tiefster Punkt), end (Recovery oder Datenende), status (recovered/active) und dd_pct
  - Neue DrawdownBandPrimitive im result_chart.html zeichnet pro Periode ein farbiges Rechteck ueber die komplette Chart-Hoehe: rot fuer erholte Drawdowns, gelb fuer aktive. Perioden mit |dd_pct| < 0.5% werden ausgefiltert, damit das Chart nicht vollgemuellt wird
  - Ersetzt die vorherige running_max-AreaSeries. Analog zur bestehenden OrderPrimitive-Implementierung, gleiche attachPrimitive-Mechanik auf candleSeries

### Files
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/result_chart.html



## [1.0.43] - 13.04.2026

### Changed
- Drawdown-Visualisierung: rote Area fuer running_max ohne Maske
  - running_max wird als semi-transparente rote AreaSeries auf der Equity-Skala gerendert, mit Gradient von 45% Deckung oben zu 10% unten. Die Equity-Linie laeuft durch die rote Flaeche hindurch und zeigt visuell den Abstand zwischen Peak und aktueller Equity
  - Maskensystem entfernt - kein dunkles Overlay mehr ueber dem Chart

### Files
- services/frontend/templates/backtest/result_chart.html



## [1.0.42] - 13.04.2026

### Changed
- Drawdown-Visualisierung: rote gestrichelte Peak-Linie statt fuellender Flaeche
  - Der vorherige Layering-Ansatz mit Area + Maske hat den kompletten Chart verdeckt. Jetzt wird running_max als duenne gestrichelte rote Linie auf der Equity-Skala gerendert - der Abstand zwischen Peak-Linie und Equity-Linie zeigt den laufenden Drawdown an, ohne den Chart zu ueberdecken
  - Maskensystem und Chart-Hintergrund-Detection entfernt

### Files
- services/frontend/templates/backtest/result_chart.html



## [1.0.41] - 13.04.2026

### Changed
- Drawdown-Visualisierung rendert jetzt die Flaeche zwischen Equity-Peak und aktueller Equity im Chart
  - chart-data-Endpoint liefert zusaetzlich running_max (monoton steigende Peak-Linie der Equity)
  - Drawdown-Toggle rendert drei gelayerte Serien: rote AreaSeries fuer running_max (fuellt bis Skalenboden), opake Area in Chart-Hintergrundfarbe in Form der Equity (ueberdeckt das Rote unterhalb der Equity) und die Equity-Linie on top. Sichtbar bleibt nur die rote Flaeche zwischen Peak und aktueller Equity - der eigentliche Drawdown
  - Ersetzt die vorherige separate Prozent-Area unterhalb des Charts

### Files
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/result_chart.html



## [1.0.40] - 13.04.2026

### Added
- Drawdown-Kurve im Ergebnis-Chart als optionale Area-Serie
  - /api/backtest/results/{id}/chart-data liefert zusaetzlich ein drawdown-Feld mit der prozentualen Drawdown-Zeitreihe, on-the-fly aus der Equity-Serie berechnet ((equity - running_max) / running_max * 100)
  - result_chart.html: neuer Toggle 'Drawdown anzeigen' im Chart-Optionen-Panel, rendert eine rote AreaSeries auf eigener Preisskala unterhalb des Charts mit Prozent-Formatierung
  - Keine DB-Migration noetig - Drawdown wird aus den bereits gespeicherten Equity-Werten abgeleitet, funktioniert damit auch fuer alle bestehenden Results

### Files
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/result_chart.html



## [1.0.39] - 13.04.2026

### Fixed
- Chart-Playground Backtest bricht nicht mehr ab wenn Indikatoren in der Chart-Darstellung ausgeblendet sind
  - buildBacktestPayload setzt enabled=true unabhaengig von ind.visible: Chart-Sichtbarkeit betrifft nur die Darstellung und darf die Strategie-Berechnung nicht beeinflussen. Vorher wurden unsichtbare Indikatoren mit enabled=false geschickt, build_indicators hat sie uebersprungen und die Rules-Engine ist beim Referenzieren gecrasht
  - Toast-Fehleranzeige liest jetzt auch j.detail aus FastAPI-HTTPException-Responses, damit statt 'Fehler: unbekannt' die echte Fehlermeldung erscheint

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.38] - 13.04.2026

### Fixed
- Fast SMA und VWMA Indikatoren zeigen jetzt den aktuellen Wert an der Preisskala des Charts
  - result_chart.html: fastSmaSeries und vwmaSeries mit lastValueVisible=true konfiguriert, damit der letzte Wert analog zur Equity-Series am rechten Chart-Rand sichtbar ist

### Files
- services/frontend/templates/backtest/result_chart.html



## [1.0.37] - 13.04.2026

### Changed
- Chart-Playground Backtest-Response liefert jetzt direkten Chart-Link statt Run-Link
  - /api/chart-playground/run-backtest gibt nach erfolgreichem Backtest result_id und url=/backtest/results/{result_id}/chart zurueck, damit der Fertig-Toast direkt auf die Chart-Seite verlinkt statt auf die Run-Detailseite
  - Fallback auf /backtest/runs/{run_id} bleibt bestehen falls result_id nicht ermittelt werden kann

### Files
- services/api/routes/api_chart_playground.py



## [1.0.36] - 13.04.2026

### Fixed
- Indikator-Parameter aus Chart-Playground-Backtests werden jetzt korrekt in actual_params gespeichert und auf der Chart-Seite angezeigt
  - indicator_factory._collapse_range liefert Parameter als 1-Element-Liste statt Skalar, damit VBT's IndicatorFactory einen param_product-MultiIndex mit Level-Namen (z.B. dwsfastsma_length, dwsvwma_below_pct) erzeugt
  - rules_engine: _squeeze entfernt; _evaluate_condition broadcastet Operanden via vbt.broadcast, _evaluate_rule_group broadcastet alle Condition-Results vor AND/OR-Kombination damit MultiIndex-Columns mehrerer Indikatoren zur gemeinsamen Struktur vereinigt werden
  - spec_runner: neuer _apply_row_mask-Helfer fuer zeilenweises Anwenden der Date-Mask auf DataFrame-Signals; entries.sum()-Print handhabt Series-Rueckgabe bei MultiIndex-Columns
  - Ursache war: spec_runner lief im Single-Combo-Modus mit Skalar-Parametern, wodurch portfolios.wrapper.columns keinen MultiIndex hatte und save_strategy_results nur {'param': 'SYMBOL'} in actual_params speicherte - die eigentlichen Indikator-Parameter fehlten komplett
  - Keine Aenderungen am Template result_chart.html oder an repository.save_strategy_results noetig - die Parameter werden jetzt automatisch aus dem MultiIndex extrahiert

### Files
- user_data/strategies/generic/indicator_factory.py
- user_data/strategies/generic/rules_engine.py
- user_data/strategies/generic/spec_runner.py



## [1.0.35] - 13.04.2026

### Added
- Generic Spec Runner und Strategy Builder im Chart Playground
  - Neuer Generic Spec Runner in user_data/strategies/generic/ - fuehrt JSON-basierte Strategien aus (indicators_json + backtest_config_json + rules_json) ohne handgeschriebenen Python-Strategie-Code
  - Spec Runner ist byte-identisch zu handgeschriebenen Strategien verifiziert (vwma_v2: Total Return 5.3725259579073175, Sharpe 2.576, Max DD -0.2522, 244 Trades, diff = 0.000e+00 gegen vwma_v2_4h_range)
  - Zentrale Indikator-Registry resolve_indicator_factory() - api_chart_playground._extract_factory delegiert dorthin
  - Indicator Factory mit Chain-Resolver (Topo-Sort), Single-Combo-Validierung, Param-Alias-Map (multiplier -> mult fuer dwsFastSMA)
  - Rules Engine mit Conditions LHS/RHS/op/shift, AND/OR-Kombination, OHLCV+Indikator-Output+Konstante als Referenzen, DataFrame-auf-Series-Squeeze bei Single-Col
  - Spec Runner liefert strategy_results im selben Format wie handgeschriebene Strategien (portfolios, indicators_results, signals, analysis_results_dict) und ist damit kompatibel zu create_backtest_run + save_strategy_results
  - Strategy Builder im Chart Playground - vollstaendig funktional: Indikatoren auswaehlen, parametrisieren, verketten; Rules definieren (Entry+Exit); Portfolio editieren; Backtest starten
  - Name-basierte Indikator-Identifier im Playground - Auto-Slug beim Hinzufuegen (dwsFastSMA -> fast_sma, dwsVWMA -> vwma, bei Kollision _2/_3), editierbares Name-Feld, Rename propagiert automatisch zu ind:<name>:<output>-Referenzen in anderen Indikator-Inputs und in Rules
  - Neue Card Strategie mit Entry/Exit-Rules: Dropdown fuer LHS/RHS (OHLCV + Indikator-Outputs + Konstante), Shift-Feld immer sichtbar, AND/OR-Toggle, Exit optional
  - Neue Card Portfolio mit allen Feldern (fees, size, size_type, init_cash, tp_stop, sl_stop, tsl_th, tsl_stop, td_stop, delta_format, time_delta_format, stop_exit_price, stop_order_type), Vorbelegung aus Backtest-Config-Dropdown, editierbar
  - Zwei neue Date-Felder OHLC Start / OHLC End neben Start / End - ermoeglicht getrenntes Warmup-Fenster fuer Indikator-Berechnung (noetig fuer exakte Reproduktion bestehender Strategien)
  - Backtest starten-Button mit Toast-Meldung (Run-ID, Return, Sharpe, Max DD, Trade-Count + Link zum Run), Playground bleibt offen - schnelles Iterieren ohne Tab-Wechsel
  - Setup speichern/laden erweitert um rules, portfolio, ohlc_start, ohlc_end - komplette Playground-Konfiguration persistierbar
  - Referenz-Setup vwma_v2 als Chart-Playground-Setup hinterlegt - byte-identische Reproduktion der handgeschriebenen vwma_v2-Strategie mit einem Klick im Browser startbar
  - Neuer Backend-Endpoint POST /api/chart-playground/run-backtest - nimmt indicators + rules + portfolio + data, baut backtest_config_json zusammen, startet Spec Runner, persistiert Run ueber create_backtest_run + save_strategy_results, liefert Kennzahlen zurueck
  - Compute-Endpoint /api/chart-playground/compute auf Namen-basierte Referenzen umgestellt - ind:<name>:<output> statt ind:<client_id>:<output> im gesamten Flow

### Files
- user_data/strategies/generic/__init__.py
- user_data/strategies/generic/registry.py
- user_data/strategies/generic/indicator_factory.py
- user_data/strategies/generic/rules_engine.py
- user_data/strategies/generic/spec_runner.py
- user_data/strategies/generic/spec_strategy_start.py
- user_data/strategies/generic/verify_vwma_v2.py
- user_data/strategies/generic/specs/__init__.py
- user_data/strategies/generic/specs/vwma_v2_single.py
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html



## [1.0.34] - 13.04.2026

### Added
- Chart Playground: Chart-Toolbar, Live-Apply, Candles-Toggle, komplette Setup-Persistenz
  - Chart-Toolbar analog zum Backtest-Chart: Fit-Button, Nav-zum-Anfang, Nav-zum-Ende, Lineal (Preis-Differenz messen mit %, absolut, Kerzen-Anzahl), TF-Buttons fuer client-seitigen Visual-Resample (nur >= Basis-TF, aendert keine Server-Berechnung)
  - Live-Apply bei Param-/Input-/TF-/Add-Aenderungen mit 300ms Debounce - Apply-Button bleibt als expliziter Trigger bestehen
  - Auto-Apply feuert erst nachdem OHLCV geladen wurde
  - Candles-anzeigen-Toggle: Candle-Farben auf transparent schalten um nur Indikatoren zu sehen
  - Setup-Speicherung vollstaendig: client_id (fuer Chaining-Referenzen), show_candles, timeframe pro Indikator, visible, inputs - beim Laden werden alte client_ids auf frische remappt, damit ind:<id>:<out>-Referenzen intakt bleiben
  - Zoom/Scroll-Position bleibt bei Auto-Apply und Indikator-Aenderungen erhalten (nur Chart-Laden/Fit/TF-Button-Klick fitten)
  - TF-Dropdown pro Indikator zeigt nur noch TFs >= Chart-TF (kleinere ergeben keinen Sinn beim Resample)

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.33] - 13.04.2026

### Changed
- Chart Playground: TF-Dropdown pro Indikator (Resample universell fuer alle Indikatoren)
  - Jeder Indikator hat ein eigenes TF-Feld als separate Spalte (nicht mehr versteckt im paramsMeta) - auch fuer vbt- und custom-Indikatoren, die keinen timeframe-Parameter in ihrer Signatur haben
  - Backend /compute macht das Resampling selbst statt es an VBT zu delegieren: Inputs werden mit passenden Aggregatoren hochgesamplet (Open=first, High=max, Low=min, Close=last, Volume=sum), Indikator rechnet auf dem hoeheren TF, Outputs werden via vbt.realign_closing zurueck auf den Chart-Index broadcastet
  - timeframe wird im IndicatorSpec als eigenes Feld (nicht in params) erwartet - beim Load/Save von Setups mitgesichert

### Files
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html



## [1.0.32] - 13.04.2026

### Added
- Chart Playground: Resampling per Dropdown beim timeframe-Parameter
  - VBT unterstuetzt bei talib/vbt-Indikatoren einen timeframe-Parameter in run() - der Indikator wird auf den angegebenen hoeheren Timeframe resamplet und auf den Chart-Index zurueckgebroadcastet
  - Timeframe-Parameter wird jetzt als Dropdown gerendert (statt type=number wo 4h nicht eingegeben werden konnte) mit Optionen: leer/1m/5m/15m/30m/1h/2h/4h/6h/12h/1d/1w
  - Leerer Wert = gleicher Timeframe wie Chart (keine Resample)

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.31] - 13.04.2026

### Added
- Chart Playground: Indikator-Typ Hintergrund fuer Supertrend-aehnliche Visualisierung
  - Neuer Plot-Typ Hintergrund im Typ-Dropdown neben Overlay und Subplot
  - Indikator wird als farbige AreaSeries ueber die volle Chart-Hoehe gerendert - gruen bei direction > 0, rot bei direction < 0 (analog result_chart.html)
  - Erkennt direction/dir-Output automatisch, faellt auf ersten Output zurueck
  - Beispiel: vbt:SUPERTREND auf Hintergrund stellen zeigt die Up/Down-Phasen als farbige Baender hinter den Kerzen

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.30] - 13.04.2026

### Fixed
- Chart Playground: Einheitliche Feldbreiten und Layout-Ausrichtung
  - Alle Selects und Inputs der Indikator-Zeilen haben jetzt feste Breite 110px - vorher passte sich der src-Select an die laengste Option an (bei Chaining wurde er doppelt so breit)
  - Anzeigen/Farbe/Typ-Gruppe sowie der Entfernen-Button sind jetzt immer rechtsbuendig (ms-auto auf der Gruppe statt nur auf dem X-Button) - unabhaengig von der Anzahl der Inputs/Params davor
  - Gestrichelte Trennlinien zwischen den Feld-Gruppen entfernt - Selektor war inkonsistent und wirkte willkuerlich

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.29] - 13.04.2026

### Changed
- Chart Playground: Parameter-Felder mit Up/Down-Spinnern
  - Indikator-Parameter sind jetzt type=number statt type=text - native Pfeil-Buttons zum Hoch/Runter-Klicken
  - Step automatisch 1 bei Integer-Defaults, 0.1 bei Float-Defaults

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.28] - 13.04.2026

### Changed
- Chart Playground: Indikator-Eingabefelder nach Tabler Design-Guide
  - Jeder Indikator ist jetzt eine card card-sm statt generischer Div mit custom Border
  - Selects/Inputs nutzen Tabler form-select-sm / form-control-sm / form-label
  - Anzeigen-Checkbox als Tabler form-check form-switch (Indikator ohne Chart-Rendering verfuegbar als Chaining-Input)
  - Remove-Button als btn-ghost-danger btn-icon mit Tabler-X-SVG

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.27] - 13.04.2026

### Added
- Chart Playground: Indikator-Chaining - Output eines Indikators als Input fuer einen nachfolgenden
  - Input-Source-Dropdown zeigt neben OHLCV jetzt auch Outputs aller frueher in der Liste stehenden Indikatoren als Optionen (gruppiert)
  - Backend /compute verarbeitet Indikatoren in der uebergebenen Reihenfolge und cached Series fuer Chaining-Referenzen im Format ind:<client_id>:<output_name>
  - Positionsbasierter Fallback fuer Parameter-Defaults bei Custom-Indikatoren, deren apply_func abweichende Parameter-Namen verwendet (z.B. vwma_len vs. length bei dwsVWMA)

### Files
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html



## [1.0.26] - 13.04.2026

### Changed
- Chart Playground: Indikator-Zeilen kompakt in einer Zeile, Toolbar zurueckgesetzt
  - Indikator-Eingabefelder sind jetzt horizontal in einer Zeile gruppiert (Inputs | Params | Farbe+Typ | Remove) - deutlich weniger Platzverbrauch
  - Top-Toolbar wieder in einer Zeile wie urspruenglich

### Files
- services/frontend/templates/chart_playground/index.html



## [1.0.25] - 13.04.2026

### Changed
- Chart Playground: Input-Source-Auswahl und umgeordnete Toolbar
  - Input-Mapping pro Indikator: OHLCV-Quelle (Open/High/Low/Close/Volume) fuer jeden Input einzeln waehlbar - auch fuer Custom-Indikatoren mit 'src'
  - Param-Defaults fuer Custom-Indikatoren werden jetzt auch aus apply_func-Signatur gelesen (vorher nur run-Signatur, wodurch dwsFastSMA ohne Defaults landete)
  - Toolbar in 2 Zeilen neu gegliedert: Zeile 1 = Setup/Preset-Auswahl + Save-Buttons, Zeile 2 = Markt + Zeitraum + Chart laden

### Files
- services/api/routes/api_chart_playground.py
- services/frontend/templates/chart_playground/index.html



## [1.0.24] - 13.04.2026

### Added
- Chart Playground fuer Strategie-Entwicklung ohne Backtest
  - Neue Seite /chart-playground mit LightweightCharts fuer interaktives Candlestick-Chart
  - Dynamische Symbol/Exchange/Timeframe-Auswahl aus verfuegbaren HDF5-Dateien
  - Live-Indikator-Berechnung serverseitig via VBT Pro - unterstuetzt vbt/talib/ta/wqa101/custom (~336 Indikatoren)
  - Custom-Indikatoren aus user_data/utils/indicators/custom.py werden per Introspection erkannt (dwsFastSMA, dwsVWMA)
  - Indikator-Panel mit Picker-Modal, Parameter-Editor, Farbwahl und Overlay/Subplot-Umschaltung (Heuristik-Default)
  - Gespeicherte Setups in neuer Tabelle chart_playground_setups (Markt + Zeitraum + Indikator-Liste) mit CRUD-API
  - Backtest-Config-Dropdown als Preset zum Vorbefuellen der Marktfelder
  - Navigation: neuer Top-Level-Eintrag Chart Playground in base.html

### Files
- services/api/routes/api_chart_playground.py
- services/api/routes/views_chart_playground.py
- services/frontend/templates/chart_playground/index.html
- services/api/app.py
- services/frontend/templates/base.html
- user_data/utils/database/models.py



## [1.0.23] - 07.04.2026

### Added
- Worker-System Hardening: Queue-basierter Status-Flow, Recovery bei Stromausfall, Redis-Persistenz
  - Runs werden mit status='queued' angelegt, Worker setzt 'running' bei Job-Start
  - Redis AOF-Persistenz aktiviert (Queue-Jobs ueberleben Container-Neustarts)
  - Recovery-Script (worker_start.py): haengende Runs werden beim Worker-Start automatisch neu eingereiht
  - backtest_params werden vor Re-Run geloescht (verhindert Duplikate bei Recovery)
  - RQ-Jobs werden bei Run-Delete gecancelt (delete_run + delete_all_runs)
  - n_combinations wird bei Run-Erstellung aus Indicator-Config berechnet (nicht erst am Ende)
  - queued-Badge (blau) in allen Frontend-Views (backtest/runs, workflow/runs, workflow/run_detail)
  - APP_VERSION aus .env im Footer angezeigt (VBT Pro App vX.Y.Z)
  - STRATEGY_OVERVIEW.md bereinigt: unbelegte Korrelationswerte und v3/v4 Sektionen entfernt
  - Split-Script fuer Indicator-Config #22: 63 Mio Kombinationen in 1.910 Configs a 35k aufgeteilt

### Files
- docker-compose-staging.yml
- docker-compose-local.yml
- services/api/worker_start.py (NEU)
- services/api/worker_tasks.py
- services/api/routes/api_backtest.py
- services/api/app.py
- services/frontend/templates/base.html
- services/frontend/templates/backtest/runs.html
- services/frontend/templates/workflow/runs.html
- services/frontend/templates/workflow/run_detail.html
- user_data/utils/database/repository.py
- user_data/utils/database/models.py
- user_data/utils/database/schema/backtest_schema.sql
- user_data/strategies/vwma_dws/STRATEGY_OVERVIEW.md
- scripts/split_indicator_config_22.py (NEU)
- .claude/skills/changelog/SKILL.md



## [1.0.22] - 06.04.2026

### Added
- Walk-Forward Analyse: Verkettete Backtests mit automatischer Parameter-Uebernahme
  - Neue DB-Felder auf BacktestRun: parent_run_id, parent_result_id, selection_metric fuer Walk-Forward Verkettung
  - Neues DB-Feld auf BacktestResult: resolved_config (JSON) — aufgeloeste Indicator-Config mit festen Werten statt Ranges
  - Hilfsfunktion _build_resolved_config() erstellt die aufgeloeste Config beim Speichern der Results (generisch fuer alle Strategien)
  - Neuer API-Endpoint POST /api/backtest/walk-forward — nimmt Result-ID und Monats-Offset, erstellt neuen Run mit verschobenem Zeitraum
  - Walk Forward Button im Chart: Dropdown mit 3/6/12 Monate, startet Validierungs-Run und leitet zur Analyse weiter
  - OHLC-Vorlauf wird automatisch beibehalten (Differenz ohlc_start zu start vom Parent-Run)

### Files
- user_data/utils/database/models.py
- user_data/utils/database/repository.py
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/result_chart.html



## [1.0.21] - 06.04.2026

### Added
- Heatmap auf ECharts migriert mit Slider fuer dritte Dimension, Multi-Select Loeschen fuer Indicator-Configs
  - Heatmap: Von HTML-Tabelle auf interaktives ECharts-Heatmap-Chart migriert mit Farbskala, Zoom und Tooltip
  - Heatmap: Neuer Slider-Parameter (param_z) fuer dritte Dimension — alle Z-Slices in einem API-Call vorgeladen
  - Zweite Heatmap (col-md-6) neben der ersten mit automatischer Vorselektion auf dwsvwma-Parameter
  - Heatmap-Code generisch refactored: eine renderHeatmapChart()-Funktion fuer beliebig viele Instanzen
  - API: Heatmap-Endpoint erweitert um optionalen param_z mit gruppierten Slices pro Z-Wert
  - Indicator-Configs: Multi-Select mit Checkboxen zum Loeschen mehrerer Configs auf einmal
  - API: Neuer Endpoint POST /api/config/indicator/bulk-delete fuer Massen-Loeschung
  - Chart-Fix: Equity-Daten werden auf OHLCV-Zeitbereich gefiltert (verhindert Lightweight Charts Crash)

### Files
- services/frontend/templates/backtest/analyse.html
- services/api/routes/api_backtest.py
- services/api/routes/api_config.py
- services/frontend/templates/config/indicator_configs.html
- services/frontend/templates/backtest/result_chart.html



## [1.0.20] - 06.04.2026

### Added
- Analyse-Seite: Übersicht-Tab mit Charts und Top Results, Wechsel auf Apache ECharts
  - Horizontale Tabs (Übersicht / Indikatoren) unter der Metrik-Auswahl eingeführt
  - Neues Chart: Total Return aller Backtests — sortierte Verteilungskurve mit Avg/Min/Max pro Bucket, rot/grün Farbsplit am Nullpunkt
  - Neues Chart: Verteilung Gewinn/Verlust Zonen — Histogramm mit dynamischen Intervallen (teilbar durch 10/20/25/50), Y-Achse in Prozent
  - Top 10 Results Tabelle in den Übersicht-Tab verschoben (3-Spalten-Layout col-md-4)
  - Alle Charts von Chart.js 4 auf Apache ECharts 5 migriert (Tabler-Standard)
  - Neuer API-Endpoint: /analyse/distribution — gleichmässige Intervalle über den Return-Bereich mit intelligentem Step
  - Neuer API-Endpoint: /analyse/equity-overview — sortierte Endwerte mit Bucket-Sampling (Avg/Min/Max pro Bucket, max 500 Punkte)
  - Info-Icons (16x16) mit Tooltip an Chart-Titeln und Tabellen-Headern
  - Profit Factor Spalte als PF abgekürzt mit Info-Icon
  - Summary-Cards Reihenfolge angepasst: Results, Profitabel, Best Return, Avg Return, Avg DD, Sharpe > 1, Best Sharpe, Avg Sharpe
  - Design Guide aktualisiert: Icon-Größe immer 16x16, Macro ohne size-Parameter

### Files
- services/frontend/templates/backtest/analyse.html
- services/api/routes/api_backtest.py
- documentation/design/design-guide.md



## [1.0.19] - 06.04.2026

### Added
- Sensitivitaets-Analyse durchgefuehrt, optimale Parameter ermittelt, PVE1 Worker RAM erhoeht
  - Sensitivitaets-Analyse Workflow mit 4 isolierten Runs (Fast SMA, VWMA, Supertrend, SMA+VWMA kombiniert)
  - Feiner Sweep (432 Kombinationen) und Micro Sweep (108 Kombinationen) fuer Sweet Spots
  - 3 optimierte Indicator-Config Profile: Konservativ (DD -20%), Ausgewogen (Sharpe 2.56), Aggressiv (Return 566%)
  - Workflow-Spalte in Indicator-Config Uebersicht (zeigt verwendete Workflows)
  - PVE1 Worker RAM-Limit auf 64 GB fuer 250k+ Kombinationen
  - Dokumentation: workflow-sensitivitaet.md mit Analyse-Anleitung und Auswertungsmethodik
  - Docs aktualisiert: spec.md, project-structure.md, progress.md

### Files
- docker-compose-staging.yml
- services/api/routes/api_config.py
- services/api/routes/api_backtest.py
- services/frontend/templates/config/indicator_configs.html
- services/frontend/templates/backtest/runs.html
- documentation/project/workflow-sensitivitaet.md
- docs/ai-context/spec.md
- docs/ai-context/project-structure.md
- docs/ai-context/progress.md



## [1.0.18] - 06.04.2026

### Added
- Workflow-System fuer Batch-Backtests mit wiederverwendbaren Templates
  - 3 neue DB-Tabellen: workflow_templates, workflow_runs, workflow_run_items
  - workflow_run_id Feld auf backtest_runs fuer Batch-Zuordnung
  - Workflow-Templates CRUD: erstellen, bearbeiten, kopieren, loeschen
  - Template-Editor mit Checkbox-Liste fuer Indicator-Configs und Kombinationen-Anzeige
  - Ein-Klick Workflow-Ausfuehrung: erstellt N Backtest-Runs und reiht sie in die Queue ein
  - Workflow-Runs Uebersicht mit Fortschrittsbalken und Auto-Reload
  - Workflow-Run Detail mit Item-Status und Analyse-Links
  - Automatische Status-Aktualisierung: Items und Gesamt-Status nach jedem Backtest-Abschluss
  - Navbar: neues Dropdown Workflow mit Templates und Runs
  - Workflow-Spalte in Backtest-Runs Tabelle mit Link zum Workflow-Run
  - Neustarten-Button in Runs-Tabelle (loescht Results, setzt Status zurueck, reiht Job neu ein)
  - Dauer-Spalte in Runs-Tabelle (live-Zaehler bei laufenden Runs)
  - Fehlende BacktestResult Import in api_workflow.py gefixt

### Files
- user_data/utils/database/models.py
- user_data/utils/database/schema/backtest_schema.sql
- user_data/utils/database/repository.py
- services/api/routes/api_workflow.py
- services/api/routes/views_workflow.py
- services/api/routes/api_backtest.py
- services/api/app.py
- services/api/schemas.py
- services/api/worker_tasks.py
- services/frontend/templates/base.html
- services/frontend/templates/backtest/runs.html
- services/frontend/templates/workflow/templates.html
- services/frontend/templates/workflow/template_edit.html
- services/frontend/templates/workflow/runs.html
- services/frontend/templates/workflow/run_detail.html



## [1.0.17] - 06.04.2026

### Added
- Indicator-Config Verbesserungen und Sensitivitaets-Configs
  - CodeMirror JSON-Editor mit Code-Folding im Indicator-Config Editor
  - Kombinationen-Berechnung Button (beruecksichtigt enabled=false)
  - Titel generieren Button mit Strategie-Prefix und Kombinationen
  - Strategie-Dropdown im Indicator-Config Editor (strategy_name Feld)
  - JSON-Sortierung: indicator, tf, enabled zuerst, dann Parameter mit start/stop/step/type/dtype
  - Indicator-Badges in Uebersicht: gruen=aktiv, rot=disabled
  - 4 Sensitivitaets-Configs angelegt (nur Fast SMA, nur VWMA, nur Supertrend, SMA+VWMA grob)
  - Downside Risk Spalte in Results-Tabelle
  - Chart-Button primaer wenn metrics_level=chart/full
  - Indicator-Cards auf Analyse-Seite mit Parameter-Sensitivitaets-Charts pro Indikator
  - Indicators Config und Backtest Config als Raw-JSON in Runs Child-Row

### Files
- services/frontend/templates/config/indicator_config_edit.html
- services/frontend/templates/config/indicator_configs.html
- services/frontend/templates/backtest/results.html
- services/frontend/templates/backtest/runs.html
- services/frontend/templates/backtest/analyse.html
- services/api/routes/api_backtest.py
- services/api/routes/api_config.py
- services/api/routes/views_config.py
- services/api/schemas.py
- user_data/utils/database/models.py
- user_data/utils/database/schema/backtest_schema.sql



## [1.0.16] - 05.04.2026

### Fixed
- Tooltips in erweiterten Metriken repariert und Schriftgröße angepasst
  - Tooltip-Initialisierung ohne bootstrap-Abhaengigkeit (Tabler exportiert kein globales bootstrap-Objekt)
  - Tooltip-Text wird in data-tip Attribut gespeichert statt title (verhindert nativen Browser-Tooltip)
  - Tooltip-Schriftgroesse auf 0.85rem erhoeht

### Files
- services/frontend/templates/backtest/result_chart.html



## [1.0.15] - 05.04.2026

### Changed
- Erweiterte Metriken im Stats-Tab mit Tooltips, SQN und Edge Ratio nach full verschoben
  - SQN und Edge Ratio aus partial nach full verschoben (Trade-Qualitaet nur bei Vollanalyse)
  - Hover-Tooltips mit Erklaerungen an allen erweiterten Metriken im Stats-Tab
  - Erweiterte Metriken-Anzeige in Stats-Tab integriert (statt separate Card)
  - Vollanalyse-Button onclick-Bug behoben (Funktion war nicht global erreichbar)
  - Hinweistext aktualisiert: Trade-Qualitaet, Benchmark und Extremrisiko nur nach Vollanalyse

### Files
- user_data/utils/database/repository.py
- services/frontend/templates/backtest/result_chart.html
- documentation/project/analyse.md



## [1.0.14] - 05.04.2026

### Added
- 3-Stufen Metriken-System für Backtests (partial, chart, full)
  - _extract_partial_metrics um 11 neue Metriken erweitert (Sharpe, Sortino, Calmar, Omega, Expectancy, SQN, Edge Ratio, Annualized Return/Volatility, Downside Risk, Deflated Sharpe)
  - _extract_chart_metrics (ehemals _extract_all_metrics) für schnelles Chart-Öffnen — nur pf.stats(), keine langsamen Properties
  - _extract_full_metrics für Hintergrund-Job — berechnet die 6 langsamen Metriken (Tail Ratio, VaR, CVaR, Alpha, Beta, Information Ratio)
  - Neues Feld metrics_level auf backtest_results (partial/chart/full)
  - Vollanalyse-Button im Stats-Tab der Chart-Seite mit Spinner und Status-Feedback
  - API-Endpunkte POST /results/{id}/full-metrics und GET /results/{id}/metrics-level
  - Worker-Task run_full_metrics_job für Hintergrund-Berechnung
  - Erweiterte Metriken-Anzeige im Stats-Tab (3 Gruppen: Rendite und Risiko, Trade-Qualität, Benchmark und Extremrisiko)
  - _ANALYSE_METRICS um 12 neue Metriken erweitert für Analyse-Seite (Heatmap, Ranking, Top-Results)
  - Dokumentation: analyse.md mit vollständigem Metriken-Katalog und Performance-Ergebnissen

### Files
- user_data/utils/database/models.py
- user_data/utils/database/schema/backtest_schema.sql
- user_data/utils/database/repository.py
- services/api/recompute.py
- services/api/worker_tasks.py
- services/api/routes/api_backtest.py
- services/frontend/templates/backtest/result_chart.html
- documentation/project/analyse.md
- documentation/project/projekt.md



## [1.0.13] - 04.04.2026

### Fixed
- Worker-Fortschrittsanzeige in Runs-Tabelle korrigiert und Status-Badge hinzugefügt
  - Worker-Spalte nutzt n_combinations als Total statt Job-Summe — zeigt korrekten Prozentsatz
  - Status-Badge aktiv/gestoppt zeigt ob der Worker gerade läuft oder pausiert

### Files
- services/frontend/templates/backtest/runs.html — Worker-Spalte mit Status-Badge und korrektem Total



## [1.0.12] - 04.04.2026

### Fixed
- Analyse-Worker: Stop/Start-Logik, Fortschrittsanzeige, DB-Seeds, PVE1 Deploy
  - Stop löscht queued Jobs statt sie auf failed zu setzen — ermöglicht Neustart
  - Stop leert die RQ-Queue komplett (q.empty()) statt einzeln zu canceln
  - Start kann nach Stop die restlichen Results neu einreihen (failed Jobs werden gelöscht)
  - Fortschrittsanzeige: total = Gesamtzahl Results, completed = Results mit Equity
  - Start-Button disabled wenn alles fertig (completed >= total)
  - DB-Seeds: Default Backtest-Configs, Indicator-Configs und Strategy-Config im Schema
  - PVE1 Deploy-Script: Clean Install mit sudo rm, OHLC-Daten werden mitgesynct, .env Pfade angepasst
  - Redis timeout/tcp-keepalive in docker-compose-staging.yml

### Files
- services/api/routes/api_backtest.py — Stop/Start/Progress Logik
- services/frontend/templates/backtest/analyse.html — Button-States
- user_data/utils/database/schema/backtest_schema.sql — strategy_configs Tabelle + Seeds
- docker-compose-staging.yml — Redis timeout/keepalive
- documentation/install/staging/deploy.sh — Clean Install mit sudo



## [1.0.11] - 04.04.2026

### Fixed
- Start-Seite Reihenfolge, SQLAlchemy Type-Casts, __pycache__ Bereinigung
  - Start-Seite: Reihenfolge geändert — Strategie, Backtest-Config, Indicator-Config
  - SQLAlchemy JSON-Felder mit dict() gecastet — behebt PyCharm InstrumentedAttribute Warnungen
  - Container __pycache__ bereinigt — altes UNIX_TIMESTAMP aus .pyc Dateien entfernt

### Files
- services/frontend/templates/backtest/start.html — Reihenfolge der Dropdowns
- services/api/routes/api_backtest.py — dict() Cast für ind.config_json
- services/api/worker_tasks.py — dict() Cast für run.backtest_config/indicators_config
- services/api/recompute.py — dict() Cast für run.backtest_config/indicators_config



## [1.0.10] - 04.04.2026

### Added
- Strategie-Verwaltung: Neue Config-Maske, dynamischer Strategie-Import, drittes Dropdown auf Start-Seite
  - Neues DB-Model StrategyConfig (strategy_family, strategy_name, import_path)
  - CRUD API-Endpoints unter /api/config/strategy
  - Verwaltungs-UI unter /config/strategy (Liste + Formular)
  - Start-Seite: Drittes Dropdown fuer Strategie-Auswahl, Button leitet direkt auf /runs weiter
  - API-Endpoint start_backtest() liest strategy_family, strategy_name und import_path aus StrategyConfig
  - Worker run_backtest_job() laedt Strategie-Funktion dynamisch per import_path aus der DB
  - recompute.py: STRATEGY_REGISTRY durch dynamischen Import via import_path ersetzt
  - load_strategy_function() als gemeinsame Funktion fuer Worker und Recompute
  - Navigation: Neuer Eintrag Strategien unter Konfiguration
  - Default-Strategie VWMA V2 4h Range automatisch angelegt

### Files
- user_data/utils/database/models.py — Neues Model StrategyConfig
- services/api/routes/api_config.py — CRUD-Routes + Schemas fuer Strategien
- services/api/routes/views_config.py — View-Routes fuer Strategie-Seiten
- services/frontend/templates/config/strategy_configs.html — NEU: Strategie-Liste
- services/frontend/templates/config/strategy_config_edit.html — NEU: Strategie-Formular
- services/frontend/templates/backtest/start.html — Drittes Dropdown, Redirect nach Klick
- services/api/routes/api_backtest.py — strategy_config_id verarbeiten
- services/api/worker_tasks.py — Dynamischer Strategie-Import per import_path
- services/api/recompute.py — load_strategy_function() statt STRATEGY_REGISTRY
- services/frontend/templates/base.html — Nav-Eintrag Strategien



## [1.0.9] - 04.04.2026

### Changed
- Code-Qualität: Inline-Imports entfernt, Start-Seite vereinfacht, OHLC-Loader mit Exchange-Mapping
  - api_backtest.py: Alle Inline-Imports an den Dateianfang verschoben (ca. 30 redundante Imports entfernt)
  - api_backtest.py: start_backtest() vereinfacht — baut backtest_config_json direkt aus DB-Config, kein Zwischendict mehr
  - Start-Seite: Button-Klick leitet direkt auf /backtest/runs weiter statt Erfolgsmeldung anzuzeigen
  - load_ohlc_data(): Exchange-Mapping (EXCHANGE_DATA_CLASS) statt hardcoded BinanceData
  - recompute.py: Nutzt jetzt load_ohlc_data() statt eigener OHLC-Ladelogik

### Files
- services/api/routes/api_backtest.py — Imports aufgeräumt, start_backtest() vereinfacht
- services/frontend/templates/backtest/start.html — Redirect nach Klick
- user_data/utils/ohlc/loader.py — Exchange-Mapping für Feature-Config
- services/api/recompute.py — Nutzt load_ohlc_data()



## [1.0.8] - 04.04.2026

### Changed
- Backtest-Architektur vereinfacht und OHLC-Loader extrahiert
  - create_backtest_run() auf 2 Parameter reduziert — strategy_family/name und symbol kommen aus backtest_config
  - Worker run_backtest_job() braucht nur noch run_id — liest Configs aus der DB
  - API-Endpoint baut backtest_config_json mit strategy_family/name und übergibt nur run_id an Worker
  - load_ohlc_data() als eigene Funktion in user_data/utils/ohlc/loader.py extrahiert
  - vwma_v2_start.py vereinfacht — nutzt load_ohlc_data(), doppeltes try/catch für sauberes Error-Handling
  - Remarks-Feld für BacktestRun — Spalte, API-Route PUT /runs/{id}/remarks, Frontend funktioniert
  - Runs-Tabelle nach ID absteigend sortiert, # aus ID-Spalte entfernt

### Files
- user_data/utils/database/repository.py — create_backtest_run() vereinfacht
- user_data/utils/ohlc/loader.py — NEU: load_ohlc_data() Funktion
- user_data/strategies/vwma_dws/vwma_v2/vwma_v2_start.py — vereinfacht mit load_ohlc_data()
- services/api/worker_tasks.py — nur noch run_id, liest Configs aus DB
- services/api/routes/api_backtest.py — Run-Erstellung im Endpoint, nur run_id an Worker, Remarks-Route
- user_data/utils/database/models.py — remarks Spalte
- services/api/schemas.py — remarks Feld
- services/frontend/templates/backtest/runs.html — ID-Sortierung, # entfernt



## [1.0.7] - 04.04.2026

### Fixed
- PostgreSQL-Migration: Kritische Bugs gefixt und Run-Erstellung refactored
  - lastrowid Bug gefixt — PostgreSQL gibt lastrowid nicht zurueck, ersetzt durch returning().scalar()
  - MySQL-Funktionen durch PostgreSQL-Aequivalente ersetzt (UNIX_TIMESTAMP, TIMESTAMPDIFF)
  - Run-Erstellung aus save_strategy_results() herausgeloest in eigene create_backtest_run() Funktion
  - BacktestRun wird VOR der Strategie-Ausfuehrung angelegt — sofort in /runs sichtbar
  - save_strategy_results() vereinfacht auf 2 Parameter (run_id, strategy_results)
  - Fehler-Handling: Bei Exception wird Run-Status auf failed gesetzt
  - OHLC-Laden aus config.py entfernt — aktiver Code gehoert in start.py
  - symbols in backtest_config integriert statt separater Variable
  - Redis Timeout behoben — timeout 0 und tcp-keepalive 60 konfiguriert
  - psycopg2-binary fuer Windows-venv installiert
  - .env auf localhost:5433 umgestellt — Docker ueberschreibt per environment

### Files
- user_data/utils/database/repository.py — create_backtest_run(), update_backtest_run_status(), save_strategy_results() vereinfacht
- services/api/worker_tasks.py — Run-Erstellung vor Strategie, Fehler-Handling
- services/api/routes/api_backtest.py — UNIX_TIMESTAMP und TIMESTAMPDIFF ersetzt
- user_data/strategies/vwma_dws/config.py — symbols in Config, OHLC-Laden entfernt
- user_data/strategies/vwma_dws/vwma_v2/vwma_v2_start.py — OHLC-Laden, Run-Erstellung, Error-Handling
- docker-compose-local.yml — Redis timeout und tcp-keepalive
- .env — POSTGRES_SERVER/PORT fuer Windows-Zugriff



## [1.0.6] - 04.04.2026

### Changed
- Datenbank von MySQL auf PostgreSQL + TimescaleDB umgestellt
  - MySQL 8 ersetzt durch TimescaleDB (PostgreSQL 17 mit Zeitreihen-Extension)
  - phpMyAdmin ersetzt durch pgAdmin 4
  - Hypertables fuer backtest_equity und backtest_indicators (schnelleres Loeschen und Zeitreihen-Queries)
  - pymysql ersetzt durch psycopg2-binary
  - MySQL-Dialekt (on_duplicate_key_update, prefix IGNORE) auf PostgreSQL-Dialekt (on_conflict_do_update/do_nothing, excluded) umgestellt
  - DOUBLE durch DOUBLE PRECISION, ENUM durch VARCHAR, AUTO_INCREMENT durch SERIAL ersetzt
  - Symbol-Feld in Backtest-Config aufgenommen (Markt-Karte: Symbol + Exchange + Timeframe)
  - Start-Maske unter /backtest/start: Backtest-Config + Indicator-Config auswaehlen und als Worker-Job starten
  - Neue backtest Queue fuer RQ-Worker neben bestehender recompute Queue
  - Delete-Logik auf Batch-Verarbeitung umgestellt (500er Chunks statt Subquery)
  - Indicator-Configs Verwaltung: DB-Tabelle, API (CRUD + Copy), Uebersichts- und Edit-Seite mit JSON-Editor
  - Alle Docker-Compose-Dateien (local, staging) und Deploy-Script auf PostgreSQL umgestellt

### Files
- docker-compose-local.yml
- docker-compose-staging.yml
- .env
- user_data/utils/database/db.py
- user_data/utils/database/models.py
- user_data/utils/database/schema/backtest_schema.sql
- user_data/utils/database/repository.py
- services/api/requirements.txt
- services/api/recompute.py
- services/api/redis_conn.py
- services/api/worker_tasks.py
- services/api/routes/api_backtest.py
- services/api/routes/api_config.py
- services/api/routes/views_backtest.py
- services/api/routes/views_config.py
- services/frontend/templates/base.html
- services/frontend/templates/backtest/start.html
- services/frontend/templates/config/indicator_configs.html
- services/frontend/templates/config/indicator_config_edit.html
- services/frontend/templates/config/backtest_configs.html
- services/frontend/templates/config/backtest_config_edit.html
- documentation/install/staging/deploy.sh



## [1.0.5] - 04.04.2026

### Added
- Backtest-Configs Verwaltung im Frontend (CRUD + Kopieren)
  - Neue DB-Tabelle backtest_configs mit allen Portfolio-, Stop- und Zeitraum-Parametern
  - API-Endpoints: GET/POST/PUT/DELETE /api/config/backtest + Copy-Endpoint
  - Uebersichtsseite /config/backtest mit DataTable (Liste, Kopieren, Loeschen)
  - Eigene Edit-Seite /config/backtest/{id} und /config/backtest/new fuer Erstellen/Bearbeiten
  - Navigation: Dropdown-Menue 'Konfiguration' mit Unterseite 'Backtest-Configs'
  - Seed-Daten: Standard Value (size_type=value) und Standard Percent (size_type=percent100)
  - Stop-Parameter logisch gruppiert: TP/SL mit Delta Format, TSL zusammen, TD mit Time Delta Format

### Files
- services/api/routes/api_config.py
- services/api/routes/views_config.py
- services/api/app.py
- services/frontend/templates/config/backtest_configs.html
- services/frontend/templates/config/backtest_config_edit.html
- services/frontend/templates/base.html
- user_data/utils/database/models.py
- user_data/utils/database/schema/backtest_schema.sql



## [1.0.4] - 04.04.2026

### Added
- PVE1 Staging-Umgebung eingerichtet 
- PVE1 Staging-Umgebung eingerichtet z
  - docker-compose-staging.yml mit allen Services (App, Worker, DB, Redis, phpMyAdmin) und Healthchecks
  - Deploy-Script (documentation/install/staging/deploy.sh) mit rsync-Sync und automatischer Pfad-Anpassung
  - PVE1-Zugangsdaten in .env integriert (PVE1_HOST, PVE1_USER, PVE1_PASSWORD)
  - DB-Schema um fehlende Tabellen ergänzt: backtest_jobs, backtest_equity, backtest_params
  - Spalte is_favorite in backtest_results ins Schema aufgenommen
  - Deploy-Script importiert Schema explizit nach Container-Start (unabhängig von Docker-Init)

### Files
- docker-compose-staging.yml
- documentation/install/staging/deploy.sh
- .env
- user_data/utils/database/schema/backtest_schema.sql



## [1.0.3] - 03.04.2026

### Added
- Worker-Status in Runs-Tabelle, ETA-Anzeige, Log-Filter
  - Runs-Tabelle zeigt Worker-Spalte mit Job-Status (fertig/fehler/offen + Prozent)
  - Analyse-Seite zeigt voraussichtliche Fertigstellung (ETA) basierend auf Avg Job-Dauer und Worker-Anzahl
  - Uvicorn Access-Log filtert haeufige Polling-Requests (DataTables, Auto-Update)

### Files
- services/api/routes/api_backtest.py
- services/api/app.py
- services/frontend/templates/backtest/runs.html
- services/frontend/templates/backtest/analyse.html



## [1.0.2] - 03.04.2026

### Added
- Analyse-Seite mit Parameter-Sensitivitaet, Heatmap, Top-Results und Background-Worker fuer Recompute
  - Analyse-Seite (/backtest/runs/{id}/analyse) mit Zusammenfassung, Metrik-Auswahl (10 Metriken), Parameter-Sensitivitaets-Charts (Chart.js), Heatmap und Top-10 Tabelle
  - BacktestJob Tabelle fuer persistentes Job-Logging (Status, Fehler, Dauer)
  - BacktestParam Tabelle fuer Analyse-Queries (Parameter-Werte pro Result, indiziert)
  - RQ Worker-Service in Docker (skalierbar via --scale worker=N)
  - API-Endpoints: start/stop/reset/progress fuer Hintergrund-Recompute
  - Frontend: Start/Stop/Reset Buttons mit Fortschrittsbalken und Polling
  - recompute.py: sync Parameter fuer Worker-Kontext (kein Background-Thread)
  - Runs-Seite: Analyse + Tests Buttons, Delete als Icon
  - Partial Metriken erweitert um max_drawdown_pct
  - Delete-Endpoints optimiert mit Subquery statt IN-Clause bei vielen IDs
  - Verwaiste Runs werden nach Bulk-Delete automatisch aufgeraeumt

### Files
- services/api/routes/api_backtest.py
- services/api/routes/views_backtest.py
- services/api/recompute.py
- services/api/redis_conn.py (neu)
- services/api/worker_tasks.py (neu)
- services/api/requirements.txt
- services/frontend/templates/backtest/analyse.html (neu)
- services/frontend/templates/backtest/runs.html
- services/frontend/templates/backtest/results.html
- user_data/utils/database/models.py
- user_data/utils/database/repository.py
- docker-compose-local.yml



## [1.0.1] - 03.04.2026

### Added
- Chart-System auf DB-Basis, Recompute fuer Multi-Kombination-Results, Analyse-Vorbereitung
  - BacktestEquity Tabelle und BacktestParam Tabelle angelegt
  - is_favorite Spalte in BacktestResult fuer Favoriten-Markierung
  - Equity-Kurve wird beim Speichern in backtest_equity persistiert
  - Parameter werden in backtest_params fuer Analyse-Queries gespeichert
  - API: chart-data, stats, favorite Endpoints (Raw-SQL fuer Performance)
  - Recompute: Einzelner Backtest wird bei fehlendem Equity automatisch nachberechnet
  - Recompute Phase 1 (Equity+Trades+Orders+Indikatoren) synchron, Phase 2 (Positions) im Hintergrund
  - Trades-Endpoint um exit_stop_type erweitert fuer Exit-Verteilung im Chart
  - Delete-Endpoints loeschen jetzt alle Detail-Tabellen mit, Favoriten werden geschuetzt
  - Verwaiste Runs ohne Results werden automatisch aufgeraeumt
  - Partial Metriken vektorisiert (end_value, total_trades, win_rate_pct, max_drawdown_pct)
  - Runs-Seite: Analyse + Tests Buttons
  - Backtest-Config als Funktionen statt JSON-Strings
  - chart_cache.py entfernt (ersetzt durch DB-Endpoints)

### Files
- user_data/utils/database/models.py
- user_data/utils/database/repository.py
- services/api/recompute.py (neu)
- services/api/routes/api_backtest.py
- services/api/routes/views_backtest.py
- services/frontend/templates/backtest/result_chart.html
- services/frontend/templates/backtest/results.html
- services/frontend/templates/backtest/runs.html
- user_data/strategies/vwma_dws/config.py
- docker-compose-local.yml



## [1.0.0] - 03.04.2026

### Added
- Chart-Seite für Backtest-Results auf DB-Basis implementiert
  - BacktestEquity Tabelle und is_favorite Spalte in BacktestResult angelegt
  - Equity-Kurve wird beim Backtest-Speichern in backtest_equity persistiert
  - API-Endpoint GET /api/backtest/results/{id}/chart-data (Equity + Indikatoren aus DB)
  - API-Endpoint GET /api/backtest/results/{id}/stats (Metriken aus BacktestResult-Spalten)
  - API-Endpoint POST /api/backtest/results/{id}/favorite (Favorit-Toggle)
  - Trades-Endpoint um exit_stop_type, entry_order_id, exit_order_id erweitert
  - Veralteten chart_cache.py (JSON-Datei-Cache) entfernt

### Files
- user_data/utils/database/models.py
- user_data/utils/database/repository.py
- services/api/routes/api_backtest.py
- services/api/routes/views_backtest.py
- services/api/chart_cache.py (entfernt)




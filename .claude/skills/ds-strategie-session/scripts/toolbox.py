#!/usr/bin/env python3
"""Objekt-Toolbox für bt_pro_app_v1.

Nimmt eine Liste aus URLs und/oder `<bereich>:<wert>`-Strings und druckt ein
kompaktes Markdown-Briefing der referenzierten Objekte. Spart pro LLM-Session
mehrere Einzel-Curls und deckt jede briefbare API-Route ab.

Namens-Konvention: Funktionen heißen `<bereich>_<aktion>` (z.B. `iteration_read`,
`backtest_config_copy`). Aktionen: read, list, create, copy, start. Keine Jargon-Begriffe.

Jede Maßnahme ist ein einzelnes Werkzeug, einzeln aufrufbar. Es gibt keine
vorgegebene Reihenfolge. Vollständige Werkzeug-Liste mit je einem Satz:
documentation/project/handbuch.md (Abschnitt "Toolbox-Werkzeuge").

Wichtig zum Leaderboard: Ein Testset-Lauf erzeugt NICHT automatisch einen Leaderboard-
Eintrag. Das passiert nur, wenn das Testset 'leaderboard_enabled=True' gesetzt hat
(Opt-in, Default False). Sinn: Viele Testsets dienen nur dem Testen über mehrere Symbole/
kurze Zeiträume; ins Leaderboard gehören bewusst nur wenige, über lange Zeiträume
vergleichbare Läufe. Ein leeres Leaderboard ist also KEIN Beleg dafür, dass kein
Testset-Lauf stattfand.

Beispiele (Lesen — Default, kein Verb):
  python3 toolbox.py http://localhost:5570/config/strategy-concepts/1/iterations/26/edit \\
                       http://localhost:5570/config/backtest/553 \\
                       http://localhost:5570/config/indicator/1970

  python3 toolbox.py iteration:26 indicator-config:1970 backtest-config:552 result:2635737 run:1753
  python3 toolbox.py concept:1 strategy-config:12 testset:4 leaderboard:88
  python3 toolbox.py knowledge:"teststrategie exit logik" vault:30_Trading/strategies
  python3 toolbox.py knowledge:"teststrategie exit logik" --k 10
      --k <n>: Trefferzahl der Wissenssuche (Default 5), gilt für alle knowledge:-Aufrufe
      im selben Kommando.

Kopieren (Schreib-Aktion — erzeugt neue Objekte, Originale bleiben unverändert):
  python3 toolbox.py copy iteration:2
  python3 toolbox.py copy backtest-config:553 indicator-config:1970
  Kopierbar: iteration, backtest-config, indicator-config.

IndicatorConfig aus Result erstellen (Schreib-Aktion):
  python3 toolbox.py create-indicator-config result:2706026:Sharpe
  python3 toolbox.py create-indicator-config result:2755455:Return result:2734638:PF
  Erstellt aus den Gewinner-Parametern eines Results eine Single-Point-IndicatorConfig
  (Range -> Skalar) nach Konvention `<KONZEPT> <version> / <Segment> / <ResultID>`.
  Segment ist optional (Return/Sharpe/PF/WinR90); Trenner ':' oder '/'.
  Nur Results sind als Quelle zulässig. Für die Vergleichsmessung via Testset.

Listen-Reads (kompaktes Markdown, eigene Verben):
  python3 toolbox.py concept-list                             # je Zeile Ziel-Marker (Ziel: ja/-) auf Basis von has_goal
  python3 toolbox.py iteration-list 1            # optional: concept_id
  python3 toolbox.py iteration-log-list --id 41  # alle Log-Einträge chronologisch, --json für rohe Items
  python3 toolbox.py befund --id 205             # EIN Befund per Befund-ID (NICHT die Testset-Lauf-Nummer!): Kontext,
                                                  #   Soll, fünf Ist-Gruppen, Deutung getrennt — leere Felder mit Grund
  python3 toolbox.py befund --testset-run 100    # jüngster Befund dieses Testset-Laufs — der direkte
                                                  #   Anschluss an testset-run-start/run-wait; meldet zusätzlich die
                                                  #   Gesamtzahl der Befunde dieses Testset-Laufs (Rerun-Historie).
                                                  #   --id und --testset-run schließen sich aus.
  python3 toolbox.py befund --iteration 41       # Befund-Historie der Iteration, chronologisch (kein Sortieren/Filtern,
                                                  #   kein Verdict); --json für rohe Items bei allen drei Formen
  python3 toolbox.py backtest-config-list
  python3 toolbox.py indicator-config-list 1 41  # optional: concept_id iteration_id
  python3 toolbox.py result-list --run 1812 --limit 20   # optional: --symbol --timeframe
  python3 toolbox.py run-list --strategy teststrategie --version 1 # Runs zu Strategie+Version, nach Testset gruppiert
                                                          #   alt: --iteration <id> | --testset-run <id>
  python3 toolbox.py testset-list
  python3 toolbox.py leaderboard-list 293        # optional: testset_id
  python3 toolbox.py symbol-list binance 4h      # exchange timeframe (Pflicht)
  python3 toolbox.py symbol-correlation binance 4h --symbols BTCUSDT,ETHUSDT,FETUSDT
                                                 # Korrelation der Tages-Log-Renditen + effektive Symbolzahl
                                                 #   [--start 2020-01-01] [--end 2025-01-01] [--window 90] [--min-overlap 30]
                                                 #   je Paar: Gesamtwert, Länge der Überlappung, rollierend min/Median/max
                                                 #   N_eff auf zwei Wegen (mittlere Paarkorrelation und Eigenwerte)
  python3 toolbox.py run-parameter-ranking 1812 sharpe_ratio   # run_id [metric]
  python3 toolbox.py run-top-results 1812 sharpe_ratio 20 desc # run_id [metric] [limit] [direction]
  python3 toolbox.py run-best 1812 profit_factor 30 1         # run_id metrik [min_trades=30] [limit=1] — bester Metrik-Wert mit >= min_trades Trades
  python3 toolbox.py run-bestwerte --run 1812                 # vier feste Bestwerte je Run ziehen + als Doku-Favorit (roter Stern) markieren (idempotent)
                                                              #   mehrere Runs: --strategy teststrategie [--version 1] | --iteration <id> | --testset-run <id>
  python3 toolbox.py run-favorites-reset --testset-run 6      # Favoriten einer Run-Menge zuruecksetzen; ohne Flag beide Sterne, sonst --doc (rot) und/oder --user (gelb)
                                                              #   Selektoren wie run-bestwerte: --run | --strategy [--version] | --iteration | --testset-run
  python3 toolbox.py vergleichstabelle --strategy teststrategie        # Iterations-Vergleichstabelle je Testset aus roten Doku-Favoriten (purge-fest);
                                                              #   optional --save <pfad> schreibt sie als Vault-Notiz (z.B. .../strategies/<slug>/iterationen-vergleich.md)
  python3 toolbox.py run-favorites-list --testset-run 6       # markierte Favoriten-Results ausgeben (reiner Read); Selektoren/Flags wie run-favorites-reset
  python3 toolbox.py result-lookup --run 1812 --params "supertrend_period=10,supertrend_multiplier=3.0"    # Result(s) per Parameter-Werten nachschlagen (Subset, serverseitig)
                                                              #   [--tolerance 1] = skalare Nachbarschaft (±t je Parameter) | [--tolerance-steps 1] = ±N Raster-Schritte je Achse, [--limit 20]
                                                              #   [--summary] = Plateau-Score (Median/Mittel/Streuung/Anteil profitabel) statt Trefferliste
  python3 toolbox.py result-query --run 1812 --where "sharpe_ratio>=1.5,total_trades>=100"  # kombinierte Metrik-Filter (nur >= und <=, UND-verknüpft)
                                                              #   [--sort <metrik>] [--direction asc|desc] [--limit 20]; Metriken: total_return_pct,
                                                              #   win_rate_pct, sharpe_ratio, profit_factor, max_drawdown_pct, total_trades
  python3 toolbox.py kreuztest --from-run 10 --to-run 11      # Bestwerte (rote Doku-Favoriten) aus Run A in Run B nachschlagen, Vergleichstabelle
                                                              #   [--user] = gelbe Sterne zusätzlich, [--tolerance <t> | --tolerance-steps <N>] wie result-lookup
  python3 toolbox.py kreuztest --from-testset-run 2 --to-testset-run 3  # ganze Testset-Läufe: Runs werden per Symbol+Timeframe gepaart (Walk-Forward)
  python3 toolbox.py combo-trace --testset-run 3 --params "supertrend_period=10,…"  # eine Kombination über eine Run-Menge verfolgen (1:N); Selektoren wie
                                                              #   run-bestwerte (--run | --strategy [--version] | --iteration | --testset-run)
  --json (bei result-list, run-top-results, run-best, run-favorites-list, result-lookup,
          result-query, kreuztest, combo-trace, symbol-correlation, iteration-log-list,
          vergleichstabelle, befund): rohe Items als JSON statt Markdown — für Folge-Analysen.
          Dazu kombinierbar (wie beim `api`-Verb): --out [datei] schreibt das
          vollständige JSON unter <TEMP>/bt-toolbox-out/ statt auf stdout; --full/--out
          schließen sich aus. Ohne --out bleibt das JSON ungekürzt auf stdout (bisheriges
          Verhalten).
  python3 toolbox.py playground-indicators                    # Gruppen-Übersicht (Name + Anzahl), kein voller Dump
  python3 toolbox.py playground-indicators --group talib      # nur diese Gruppe, kompakt: id/inputs/params/outputs
  python3 toolbox.py playground-indicators --search ema       # case-insensitiv über id/name, --group kombinierbar

Anlegen (create — Schreib-Aktion). Komplexe Payloads per --file als JSON-Datei.
KEIN stiller Konverter, kein Fallback: spec_json/config_json wird unverändert
durchgereicht und scheitert beim Lauf laut, wenn falsch geformt.
  python3 toolbox.py concept-create --slug teststrategie --name "Teststrategie" [--category ... --description ... --status active]
        [--goal <datei-oder-inline-json> --goal-prompt <datei-oder-text>]: Entwicklungsziel,
        kein Gate — --goal ist strukturiertes JSON (Objekt), --goal-prompt der Original-Auftrag im Wortlaut.
        Beide erkennen einen Dateipfad automatisch (wie --file), sonst wird der Wert inline übernommen.
  python3 toolbox.py iteration-create --concept 1 --file spec.json [--name "v5" --type generic --description ... --parent 41]
        --file = das spec_json (Flat-Dict indicators + DNF-rules). type=hardcoded braucht --import-path.
  python3 toolbox.py indicator-config-create --file config.json [--concept 1 --iteration 41 --name "..." --description ...]
        --file = das config_json (Parameter-Raster, arange je Indikator).
        Ohne --name: Standard-Titel (und Beschreibung) nach Notation über den Server (preview-labels).
        Mit --name: individueller Name, verbatim. --description überschreibt die Auto-Beschreibung.
  python3 toolbox.py indicator-config-set --id 4 [--concept 2 --iteration 2 --name "..." --description "..."]
        Teil-Update (PATCH): schreibt NUR die gesetzten Felder; config_json/_stops bleiben unangetastet.
        Kernfall: bestehende Config nachträglich einem Konzept/einer Iteration zuweisen.
  python3 toolbox.py indicator-config-labels --id 4 [--name-freetext "..." --desc-freetext "..." --save]
        Standard-Notation erzeugen (preview-labels), optional Freitext setzen (Titel: `<Notation> : <Freitext>`,
        Beschreibung: `<Freitext> | <Auflistung>`), mit --save via PATCH nur Name/Beschreibung zurückschreiben.
        Ohne --save nur Vorschau. Freitext ausschreiben, keine kryptischen Kürzel.
  python3 toolbox.py indicator-config-generate-labels 4
        Setzt Name UND Beschreibung serverseitig auf die reine Standard-Notation (ohne Freitext,
        überschreibt beide Felder). Für Freitext stattdessen indicator-config-labels --save.
  python3 toolbox.py backtest-config-create --file backtest.json
        --file = der volle Body (Pflicht: name, start, end, ohlc_start, ohlc_end; Defaults: symbol BTCUSDT, exchange binance, timeframe 4h, size 100, size_type value, init_cash 100, fees 0.001, slippage 0.0).
        stop_exit_price/stop_order_type optional (leer/nicht gesetzt = VBT-Default).
  python3 toolbox.py testset-create --name "OoS 22/23" --configs 552,553,554 [--description ...]
  python3 toolbox.py iteration-log-add --id 41 --text "..." [--run 1812]
        Hängt einen Freitext-Eintrag ans append-only Denkprotokoll der Iteration.
        Kein Update-/Delete-Verb — Einträge sind unveränderlich. --run optional (lose Referenz, kein FK).

Ausführen (start — Schreib-Aktion, ID-basiert):
  python3 toolbox.py backtest-run-start --backtest-config 552 --indicator-config 1970 --iteration 41 [--metrics kern|voll|auto|<gruppe1,gruppe2,...>]
  python3 toolbox.py testset-run-start --testset 293 --iteration 41 --indicator-config 1973 [--metrics kern|voll|auto|<gruppe1,gruppe2,...>]
        Raster-Quelle alternativ inline: --indicators raster.json statt --indicator-config <id>. Die Datei trägt dasselbe Format wie indicator-config-create --file
        (Inhalt von config_json inklusive '_stops'); es entsteht keine IndicatorConfig-Zeile
        und der Befund trägt indicator_config_id = NULL. Genau eine der beiden Angaben ist
        Pflicht — beides oder keines endet mit Fehler.
  python3 toolbox.py walk-forward-start --result 2706026 --months 6
        --metrics: welche Kennzahl-Gruppen der Lauf rechnet. Ohne Angabe
        gilt 'auto' (Server-Default) — volle Rechnung unterhalb der Rastergrößen-
        Schwelle, sonst 'kern'. Eine Kommaliste benennt zusätzlich zu den Pflicht-
        gruppen gewünschte Gruppen-Keys (z.B. drawdown,benchmark); die Prüfung auf
        gültige Stufen/Keys macht der Server, nicht die Toolbox.

Prüfen vor dem Start / Warten aufs Ende:
  python3 toolbox.py preflight --iteration 41 --indicator-config 1970 --backtest-config 552
      Raster-Quelle alternativ inline: --indicators raster.json statt --indicator-config <id>
      (dieselbe Genau-eines-Regel wie testset-run-start).
      Billiger Vorlauf auf EINER Kombination (Startwerte, kein DB-Schreiben): Entry-/Exit-
      Signalzahl + erster/letzter Signalzeitpunkt, NaN-Anteil je Indikator-Output, tatsächlicher
      Vorlauf, Kombinationszahl des vollen Rasters, grobe Laufzeit-Hochrechnung. Berichtet nur,
      startet nichts und verhindert nichts.
  python3 toolbox.py run-wait --run 1812 [--timeout 1800]      # oder: --testset-run 6
      Pollt aktiv bis der/die Run(s) 'completed'/'failed' sind (Default-Timeout 1800s); danach
      je Run Dauer, Result-Zahl, ggf. Fehlermeldung. Timeout meldet sich als Timeout, nicht als
      Fehlschlag.

Signifikanztest je Kandidat — berichtet, filtert nicht:
  python3 toolbox.py signifikanz-start --result 2706026 [--method permutation] [--n 300] [--seed 42]
                                       [--metrics sharpe_ratio,profit_factor] [--wait [--timeout 1800]]
      permutation (Default): die Strategie läuft auf N synthetischen Preisreihen (Bar-Permutation,
      Default N=300) — der p-Wert sagt, wie oft ein so gutes Ergebnis aus strukturlosen Daten
      entsteht. Läuft als Hintergrund-Job. Vor dem ersten synthetischen Lauf prüft der Test sich
      selbst: der Referenzlauf auf der echten Reihe muss die am Result gespeicherten Kennzahlen
      reproduzieren, sonst bricht er sichtbar ab.
      bootstrap: Resampling der gespeicherten Trade-Renditen (Default 2000 Runden) — Konfidenzbänder,
      KEIN Nullmodell und deshalb KEIN p-Wert. Rechnet direkt im Aufruf. Ohne Trades bricht er mit
      Hinweis auf den Recompute-Weg ab (es wird bewusst nicht automatisch nachgerechnet).
      --wait pollt bis completed/failed; Exit-Codes wie run-wait: 0 fertig, 2 Timeout.
  python3 toolbox.py signifikanz --id 7            # ein Test: Methode, N, Seed und je Metrik
                                                    #   echter Wert + Null-Verteilungs-Kennwerte + p-Wert
                                                    #   nebeneinander — ein p-Wert erscheint NIE ohne
                                                    #   seine Null-Verteilung. --json für rohe Daten.
  python3 toolbox.py signifikanz-list --result 2706026   # Historie, chronologisch (keine Sortierung
                                                    #   nach p-Wert, kein Bestanden-Feld)

Walk-Forward-Fold-Kette — Messwerkzeug, kein Ertragsbringer:
  python3 toolbox.py walk-forward-chain-start --run 614 --folds 3 --oos-monate 3
                                       [--is-monate 12] --selection-metric sharpe_ratio
                                       [--selection-direction max|min] [--trade-floor 5]
                                       [--metrics kern|voll|auto] [--timeout 1800]
      Fährt N-mal „auf einem Zeitfenster optimieren -> Sieger einfrieren -> auf dem nächsten,
      ungesehenen Zeitfenster testen" im Vordergrund. Fold-Zahl, Fensterlängen und Kriterium
      werden beim Start festgeschrieben (Vorregistrierung) und stur vollzogen — kein
      Nachjustieren nach Zwischenblick. Fold 1 nutzt den Anker-Lauf selbst als IS-Lauf, wenn
      sein IS-Fenster exakt das Anker-Fenster ist (also ohne --is-monate). Ein Fold ohne
      Sieger (kein Kandidat über dem Trade-Floor) wird ausgewiesen, nicht verschluckt; die
      Kette läuft weiter. Bricht ein Lauf ab, schließt die Kette als 'failed' mit Grund.
      Exit-Codes wie run-wait: 0 fertig, 1 Fehlschlag, 2 Timeout. Es entstehen nur Runs und
      Results — keine neuen Backtest-/Indicator-Configs und keine Testsets.
  python3 toolbox.py walk-forward-chain --id 3        # Plan, Fold-Tabelle (IS-Wert NEBEN
                                                    #   OOS-Wert), Sieger-Kopien, Gesamtblock,
                                                    #   Methodenhinweis. --json für rohe Daten.
  python3 toolbox.py walk-forward-chain-list [--iteration 41]   # Historie, chronologisch
      Regel: das Aggregat wird NIE ohne seine Fold-Tabelle zitiert — die Streuung über die
      Folds gehört zur Zahl. Kein Verdict, keine Güte-Sortierung: die Kette misst, sie urteilt
      nicht. Die Gesamtrechnung lebt einmal serverseitig (POST .../close); die Toolbox ruft sie
      nur ab. Methodisch: verkettete Kapitalkurven der Testfenster, KEIN durchgehendes
      Portfolio über alle Folds (Signal-Splice) — der Methodenhinweis an der Kette sagt das.

Gezielt bearbeiten (Schreib-Aktion — GET, EINEN Teil ändern, zurückschreiben; der Rest
bleibt bit-genau). Für den Alltagsfall "kopieren und einen Indikator/eine Regel/ein Feld
ergänzen" — KEIN kompletter Body nötig:
  Felder (Meta/flach):
    concept-set --id N [--name --slug --category --description --status --goal --goal-prompt]
        --goal/--goal-prompt wie bei concept-create (Datei-Erkennung wie --file, sonst inline).
    iteration-set --id N [--version-name --description --status]
    backtest-config-set --id N [--symbol --exchange --timeframe --start --end --ohlc-start
                                --ohlc-end --size --size-type --init-cash --fees --slippage
                                --stop-exit-price --stop-order-type --name --description]
        --stop-exit-price/--stop-order-type: gültige Werte Stop/HardStop/Close bzw. Market/Limit
        (Groß-/Kleinschreibung egal); --stop-exit-price "" (leerer String) setzt VBT-Default
        zurück. Feld weglassen lässt den bestehenden Wert unangetastet.
  Indikatoren (spec_json.indicators bzw. config_json):
    iteration-indicator-set --id N --name <key> --file frag.json [--replace]
    iteration-indicator-remove --id N --name <key>
    indicator-config-indicator-set --id N --name <key> --file frag.json [--replace]
    indicator-config-indicator-remove --id N --name <key>
        frag.json = ein Indikator-Block, z.B. {"indicator":"talib:SMA","tf":"4h","close":"close","timeperiod":50}.
        Existiert der Key, wird gemergt: nur die genannten Parameter ändern sich, der Rest
        des Blocks bleibt bit-genau. Einzelnen Wert ändern: --file {"timeperiod":50}.
        --replace ersetzt den Block komplett (alles Nicht-Genannte fällt weg).
        In der Config dürfen Param-Werte arange-Ranges sein (Multiparameter): "timeperiod":{"type":"arange",...}.
  Stops (config_json._stops, einzeln):
    indicator-config-stops-set --id N [--tp --sl --td --tsl --tsl-th --delta-format --time-delta-format]
        Zahlen/null werden gecastet, Format-Felder bleiben String; nicht genannte Stops bleiben.
  Regeln (spec_json.rules):
    iteration-condition-add --id N [--exit] [--block K | --new-block [--short]] --file cond.json
    iteration-condition-remove --id N [--exit] --block K [--index J | --remove-block]
        cond.json = eine Bedingung, z.B. {"op":">","lhs":"close","rhs":"indicator:sma:real"} (opt. lhs_shift/rhs_shift).
        Ohne --block hängt condition-add an Block 1 (UND-verknüpft); --new-block macht einen ODER-Block.

Ändern (PUT, voller Body per --file): <bereich>-update --id <n> --file body.json
  Voll-Replace für den ganzen Body. Für gezielte Teiländerungen die "Gezielt bearbeiten"-Verben
  oben nehmen. Braucht man doch den rohen Ist-Body: `api GET <route>` (roher JSON-Dump), editieren,
  per <bereich>-update --file zurück.
  concept-update · iteration-update · backtest-config-update · indicator-config-update ·
  strategy-config-update · testset-update · playground-setup-update

Löschen (DELETE): <bereich>-delete <id>   (concept/iteration zusätzlich: --force --delete_vault)
  concept-delete · iteration-delete · backtest-config-delete · indicator-config-delete ·
  strategy-config-delete · result-delete · run-delete · testset-delete · leaderboard-delete ·
  playground-setup-delete · knowledge-reset
  Sammellöschen: <bereich>-bulk-delete --ids 1,2,3 (indicator-config/result/run/playground-setup)
  Alle (außer Favoriten): result-delete-all [--run <id> | --testset-run <id>] · run-delete-all
      Ohne Flag global (Hintergrund-Job); mit --run/--testset-run synchron
      auf die Menge eingegrenzt — Antwort nennt deleted_results/deleted_runs/deleted_run_ids.
      run-delete-all bleibt ausschließlich global.

Aktionen (POST): iteration-favorite/iteration-doc-favorite/result-favorite/result-doc-favorite <id>
      [--off] (setzend statt umschaltend: ohne --off wird der Stern gesetzt,
      mit --off gezielt entfernt; beides idempotent. result-doc-favorite zusätzlich
      [--criteria k1,k2] wie run-bestwerte, nur ohne --off zulässig) ·
  concept-vault-create <id> (Ordner + <slug>-concept.md + status.md) ·
  iteration-vault-create <id> (iterations/<version>/<slug>-<version>.md) · beide idempotent ·
  run-restart <id> (löscht die Results und rechnet von vorn) ·
  run-resume <id> (setzt einen abgebrochenen Lauf fort: behält die gespeicherten
      Chunks und rechnet ab dem ersten fehlenden weiter) ·
  run-remarks <id> --text "..." ·
  run-analyse-start/stop/reset <id>

Weitere Anlegen (POST, --file): strategy-config-create ·
  playground-setup-create · playground-compute/run-backtest/run-backtest-lite · knowledge-reindex
  data-update --timeframe 4h [--wait] [--timeout 1800] · data-download --file jobs.json [--wait] [--timeout 1800]
      · data-delete-symbol --timeframe 4h --symbol FETUSDT
      --wait: wartet auf das Ende aller angelegten Jobs (5s-Poll, Default-
      Timeout 1800s) und druckt die Bilanz — Gesamtzahl, erfolgreich, fehlgeschlagene
      Symbole namentlich mit Grund. Exit-Codes: 0 alle erfolgreich, 1 mindestens ein
      Fehlschlag, 2 Timeout. Ohne --wait bleibt das Verhalten asynchron (nur Job-IDs).
  playground-run-backtest-lite: Sondierungspfad des Chart-Playgrounds — rechnet
      GENAU EINE Kombination (Startwerte aller Parameter/Stops, kein Raster) und schreibt
      nichts in die DB. Antwort-Felder: total_return, benchmark_return, profit_factor,
      max_drawdown, sharpe_ratio, position_coverage_pct (Marktpräsenz — Anteil der Balken mit
      offener Position), trades, open_trades, duration_ms, equity, trades_data. sharpe_ratio
      und position_coverage_pct kommen direkt vom gerechneten VBT-Portfolio (Handelsfenster-
      Slice wie beim vollen Lauf), keine Ersatzrechnung. Gemessen gegen einen vollen Lauf
      derselben Kombination: sharpe_ratio und position_coverage_pct sind in beiden Pfaden
      bit-identisch — keine rechnerische Abweichung. Der einzige Unterschied ist konzeptionell:
      Lite deckt bei einer Sweep-Config immer nur die Startwert-Kombination ab, nie das volle
      Raster — die beste Kombination eines vollen Multiparameter-Laufs kann deshalb an anderer
      Stelle im Raster liegen als die von Lite gerechnete.
      GEÄNDERT: die Antwort trägt bei Vollzyklen ~12.000 Equity-Punkte und
      sprengt damit die 4000-Zeichen-Anzeige; anders als bei den übrigen schreibenden
      Verben ist `--out [datei]` (und `--full`) hier trotzdem erlaubt, weil dieser POST
      serverseitig nichts persistiert: python3 toolbox.py playground-run-backtest-lite
      --file spec.json --out ergebnis.json. Außerdem eigener Timeout-Default (90s statt
      der globalen 10s) für den Numba-Warmup nach Container-Start, per --timeout <s>
      überschreibbar; siehe VERB_TIMEOUT_OVERRIDES.
      GEÄNDERT: --concept <id> ordnet die Sondierung einem Konzept zu und
      zählt sie dort mit (strategy_concepts.probe_count, atomar; die Antwort trägt den
      neuen Stand als concept_probe_count). Im Auftragskontext IMMER mitgeben:
      python3 toolbox.py playground-run-backtest-lite --file spec.json --concept 12
      Ohne --concept läuft der Aufruf unverändert und zählt nichts. Der Zählerstand
      steht im Befund neben der Rastergröße — reiner Ausweis des Suchumfangs, ohne
      Bewertung und ohne Verrechnung in N oder DSR.

Weitere Listen/Reads: strategy-config-list · data-files-list · data-jobs-list · filters-list ·
  run-results/run-summary/run-distribution/run-equity-overview/run-heatmap/run-analyse-progress <id> ·
  result-stats/result-trades/result-orders/result-positions/result-ohlcv/result-chart-data <id> ·
  knowledge-runs-list · knowledge-run <id> · knowledge-stats ·
  playground-sources/playground-ohlcv/playground-setup-list
  Lange Antworten kappt die Anzeige bei 4000 Zeichen — wie beim `api`-Verb (siehe unten)
  lösen `--out [datei]` und `--full` das auf: python3 toolbox.py run-results 1812 --out
  Beide Flags gibt es nur bei diesen Lese-Verben (GET) sowie bei den in
  WRITE_VERBS_ALLOW_OUT gelisteten schreibfreien POST-Verben (aktuell
  playground-run-backtest-lite); bei allen anderen (Ändern/Löschen/
  Aktionen/Anlegen) sind sie nicht verfügbar und führen zu einem Fehler.

Analyse-Screenshot — fotografiert die echte Analyse-Seite serverseitig,
kein Browser-Werkzeug/Subagent mehr nötig:
  python3 toolbox.py analyse-screenshot --run 866 --x supertrend_period --y supertrend_multiplier \
      --out /pfad/zum/ziel.png [--metric sharpe_ratio] [--agg max]
  Ruft NUR die Route `GET /api/backtest/runs/<id>/analyse/screenshot` (Renderer-Container,
  Playwright, wartet auf window.__analyseReady statt fester Wartezeit) und schreibt das
  gelieferte PNG unverändert an --out. Ein absoluter --out-Pfad wird wörtlich genommen
  (gleiche _out_path()-Semantik wie überall), das Bild landet direkt am Zielort — kein
  Zwischenschritt über <TEMP>/bt-toolbox-out/. Ohne --metric/--agg zieht die Route ihre
  Sollwerte (Average, Metrik total_return_pct). Scheitert die Route (Run ohne Results,
  unbekannter Achsenname, Renderer-Timeout), bricht das Verb mit dem Server-Fehlertext ab
  (Exit-Code ungleich 0) und schreibt KEINE Datei. Das Namensschema für --out steht im
  Screenshot-Standard (.claude/skills/ds-strategie-session/references/screenshot-standard.md).

Generischer Direktzugriff auf JEDE (auch künftige) Route:
  python3 toolbox.py api GET /api/backtest/runs
  python3 toolbox.py api POST /api/testsets --file body.json
  python3 toolbox.py api DELETE /api/backtest/runs/1234
  Lange Antworten: die Anzeige kappt bei 4000 Zeichen (Schnitt mitten im JSON, nicht parsebar).
    --out [datei]  ungekürzt in eine Datei, Konsole nur Pfad + Zeichenzahl (kontextschonend, bevorzugt)
    --full         ungekürzt auf stdout
  python3 toolbox.py api GET "/api/backtest/runs/222/analyse/parameter-ranking?metric=total_return_pct" --out ranking.json

  --out schreibt IMMER unter <TEMP>/bt-toolbox-out/ (ohne Wert: Auto-Name mit Zeitstempel).
  Ein reiner Dateiname bzw. relativer Pfad landet dort, nicht im Arbeitsverzeichnis — so kann
  nichts im Repo landen. Nur ein absoluter Pfad wird wörtlich genommen (dann aber kein Cleanup).
  Aufräumen: passiert automatisch bei jedem --out-Schreiben (Dateien älter als 24h fliegen raus).
  Sofort/komplett aufräumen:
    python3 toolbox.py out-clean          # nur abgelaufene (>24h)
    python3 toolbox.py out-clean --all    # Ordner komplett leeren

Unterstützte Bereiche:
  ID-basiert:
    concept             — Strategie-Konzept
    iteration           — Iteration
    indicator-config    — Indicator-Config
    backtest-config     — Backtest-Config
    strategy-config     — Strategy-Config (hardcoded/generic, Legacy)
    result              — Backtest-Result (Stats)
    run                 — Backtest-Run (Einzel-GET)
    testset             — Testset
    leaderboard         — Leaderboard-Eintrag (Drilldown)
    playground-setup    — Chart-Playground-Setup
  String-basiert:
    knowledge           — semantische Vektorsuche im Vault-Index
    vault               — indizierte Vault-Dateien (Pfad-Substring)
"""

import datetime
import json
import os
import pathlib
import re
import statistics
import sys
import tempfile
import urllib.parse
import urllib.request
import urllib.error

# Basis-URL des FastAPI-Backends. Default lokal; per Env VBT_APP_BASE_URL überschreibbar.
BASE = os.environ.get("VBT_APP_BASE_URL", "http://localhost:5570").rstrip("/")
TIMEOUT = 10
# GEÄNDERT: playground-run-backtest-lite braucht mehr Zeit als der globale
# Default: der erste Aufruf nach Container-Start übersetzt Numba neu (30–60s), erst
# danach läuft die eigentliche Portfolio-Rechnung. --timeout <s> überschreibt das je
# Aufruf; ohne Flag greift dieser Verb-Default. Auch Grundlage für den erklärenden
# Timeout-Fehlertext in _run_table_verb.
VERB_TIMEOUT_OVERRIDES = {
    "playground-run-backtest-lite": 90,
    # GEÄNDERT: die Route wartet selbst bis zu 90s auf den Renderer und
    # gibt sich intern 30s Luft darüber (timeout_ms/1000 + 30, siehe
    # api_analyse_screenshot.py); die Toolbox braucht also mehr als die Route selbst.
    "analyse-screenshot": 150,
}
# GEÄNDERT: --out/--full sind für Nicht-GET-Verben grundsätzlich gesperrt
# (siehe _run_table_verb), weil sie i.d.R. etwas verändern/löschen und die Sperre vor
# blindem Wiederholen bei gekappter Antwort schützt. playground-run-backtest-lite ist
# ein POST, das serverseitig NICHTS persistiert (kein create_backtest_run, kein
# save_strategy_results) und dessen Antwort mit der vollen Kapitalkurve (~12.000 Punkte
# im Vollzyklus) genauso lang wie ein Lese-Verb werden kann — die Begründung der Sperre
# trifft hier nicht zu.
WRITE_VERBS_ALLOW_OUT = {
    "playground-run-backtest-lite",
}
# Maximale Run-Liste für echte Listen-Reads (run-list, run-wait --testset-run).
# GEÄNDERT: run:<id> und run-wait --run nutzen den Einzel-GET und
# sind von diesem Limit nicht mehr betroffen.
RUN_LIST_LIMIT = 500

URL_PATTERNS = [
    (re.compile(r"/config/strategy-concepts/\d+/iterations/(\d+)"), "iteration"),
    (re.compile(r"/strategy/iterations/(\d+)"), "iteration"),
    (re.compile(r"/config/backtest/(\d+)"), "backtest-config"),
    (re.compile(r"/config/indicator/(\d+)"), "indicator-config"),
    (re.compile(r"/config/playground/(\d+)"), "playground-setup"),
    (re.compile(r"/backtest/results/(\d+)"), "result"),
    (re.compile(r"/backtest/runs/(\d+)"), "run"),
    (re.compile(r"/testsets/(\d+)"), "testset"),
]

# Gültige Bereiche (kanonisch, keine Kurz-Aliasse). Reihenfolge = Doku-Reihenfolge.
VALID_TYPES = {
    "concept",
    "iteration",
    "indicator-config",
    "backtest-config",
    "strategy-config",
    "result",
    "run",
    "testset",
    "leaderboard",
    "playground-setup",
    "knowledge",
    "vault",
}

# Bereiche, deren Wert ein String ist (Query/Pfad) statt einer Integer-ID
STRING_TYPES = {"knowledge", "vault"}


def parse_arg(arg: str):
    """Liefert (typ, wert) oder (None, None). wert ist int (ID-Typen) oder str (String-Typen)."""
    if arg.startswith("http"):
        for pat, t in URL_PATTERNS:
            m = pat.search(arg)
            if m:
                return t, int(m.group(1))
        return None, None
    if ":" in arg:
        t, val = arg.split(":", 1)
        t = t.lower()
        if t not in VALID_TYPES:
            return None, None
        if t in STRING_TYPES:
            return t, val.strip()
        if val.isdigit():
            return t, int(val)
    return None, None


def fetch(path: str, timeout: int = TIMEOUT) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=timeout) as r:
        return json.loads(r.read())


def post(path: str, body: dict = None, timeout: int = TIMEOUT) -> dict:
    """POST mit optionalem JSON-Body. Gibt die geparste Antwort zurück.

    timeout überschreitbar für Routen, die tatsächlich rechnen (z.B. preflight —
    baut Indikatoren und rechnet eine Kombination, das dauert länger als ein reiner
    DB-Read).
    """
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def request(method: str, path: str, body: dict = None, timeout: int = TIMEOUT) -> dict:
    """Beliebige HTTP-Methode mit optionalem JSON-Body. Leere Antwort -> {}.

    GEÄNDERT: timeout überschreitbar, analog zu post() (z.B. für
    playground-run-backtest-lite über VERB_TIMEOUT_OVERRIDES bzw. --timeout).
    """
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method.upper(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def num(v, fmt: str = "{:.2f}", dash: str = "—") -> str:
    """None-sichere Zahlenformatierung."""
    return fmt.format(v) if isinstance(v, (int, float)) else dash


def trades_str(r: dict, total_key: str = "total_trades") -> str:
    """Trade-Anzahl mit Long/Short-Aufteilung und den am Fensterende offenen Positionen.

    Trefferquote und Profitfaktor rechnen ueber die geschlossenen Trades
    (total_trades - open_trades). Die Trade-Anzahl allein ist deshalb nicht mehr
    der Nenner der Quote - die offenen Positionen werden mit ausgegeben, sobald
    es welche gibt. Long/Short-Aufteilung (long_trades + short_trades =
    total_trades) wird angehaengt, sobald beide Felder vorhanden sind.
    Ältere Results haben die Zusatzfelder als None und werden
    unveraendert als reine Zahl ausgegeben.
    """
    total = r.get(total_key)
    if total is None:
        return "—"
    open_n = r.get("open_trades")
    long_n, short_n = r.get("long_trades"), r.get("short_trades")
    extras = []
    if long_n is not None and short_n is not None:
        extras.append(f"{long_n}L/{short_n}S")
    if open_n:
        extras.append(f"{open_n} offen")
    if not extras:
        return str(total)
    return f"{total} ({', '.join(extras)})"


def fmt_cond(c: dict) -> str:
    lhs = c.get("lhs"); op = c.get("op"); rhs = c.get("rhs")
    lhs_s = c.get("lhs_shift", 0); rhs_s = c.get("rhs_shift", 0)
    parts = [str(lhs)]
    if lhs_s: parts.append(f".shift({lhs_s})")
    parts.append(f" {op} {rhs}")
    if rhs_s: parts.append(f" (rhs.shift({rhs_s}))")
    return "".join(parts)


def render_spec(spec: dict) -> None:
    """Druckt Indikatoren und Entry/Exit-Rules aus einem spec_json/strategy_config_json."""
    inds = spec.get("indicators", {})
    if inds:
        print("- Indikatoren:")
        for name, p in inds.items():
            # GEÄNDERT: tf nicht mehr filtern — der Rechen-Timeframe ist laufzeit-wirksam
            # (fehlt er beim Zurückschreiben, bricht der Lauf mit ValueError ab)
            params = ", ".join(f"{k}={v}" for k, v in p.items() if k not in ("enabled", "indicator"))
            # GEAENDERT: deaktivierte Indikatoren (enabled: false) markieren
            tag = "" if p.get("enabled", True) else " [deaktiviert]"
            print(f"  - **{name}** ({p.get('indicator')}){tag}: {params}")
    rules = spec.get("rules", {})
    # GEAENDERT: Block-Format (DNF) statt Alt-Format {logic, conditions};
    # Blöcke sind ODER-verknüpft, Short- und deaktivierte Blöcke (enabled: false) werden markiert.
    for kind in ("entry", "exit"):
        r = rules.get(kind) or {}
        blocks = r.get("blocks") or []
        if not blocks:
            continue
        print(f"- {kind.capitalize()}-Rules (Blöcke ODER-verknüpft):")
        for n, b in enumerate(blocks, 1):
            tags = []
            if b.get("is_short"):
                tags.append("SHORT")
            if not b.get("enabled", True):
                tags.append("deaktiviert")
            suffix = f" [{', '.join(tags)}]" if tags else ""
            conds = b.get("conditions", [])
            cond_txt = " UND ".join(fmt_cond(c) for c in conds) if conds else "(leer)"
            print(f"  - Block {n}{suffix}: `{cond_txt}`")


# ---------------------------------------------------------------------------
# Lese-Handler (read). Nehmen eine ID, rufen die passende API-Route und drucken
# ein eingedampftes Markdown-Briefing. Funktionsname: <bereich>_read.
# ---------------------------------------------------------------------------

def concept_read(i: int) -> None:
    d = fetch(f"/api/strategy/concepts/{i}")["data"]
    print(f"## Concept {i} — {d.get('name')} ({d.get('slug')})")
    print(f"- Status: {d.get('status')} · Kategorie: {d.get('category') or '—'} · Vault: {d.get('vault_exists')}")
    # GEÄNDERT: Zählerstand der Lite-Sondierungen (reiner Ausweis)
    print(f"- Lite-Sondierungen (probe_count): {d.get('probe_count')}")
    if d.get("description"):
        print(f"- {d['description']}")
    # GEÄNDERT: Entwicklungsziel rendern (kein Gate, reine Anzeige)
    if d.get("goal_prompt"):
        print("- Ziel-Prompt:")
        print(f"  {d['goal_prompt']}")
    if d.get("goal_json"):
        print("- Ziel-JSON:")
        for line in json.dumps(d["goal_json"], indent=2, ensure_ascii=False).splitlines():
            print(f"  {line}")
    print()


def iteration_read(i: int) -> None:
    d = fetch(f"/api/strategy/iterations/{i}")["data"]
    name = d.get("version_name") or d.get("version")
    print(f"## Iteration {i} — {name}")
    print(f"- Concept-ID: {d.get('concept_id')} · Typ: {d.get('type')} · Status: {d.get('status')} · Vault: {d.get('vault_exists')}")
    if d.get("description"):
        print(f"- {d['description']}")
    render_spec(d.get("spec_json") or {})
    # GEÄNDERT: Anzahl + letzte 3 Log-Einträge (Text auf 200 Zeichen gekürzt);
    # für den vollen Verlauf: iteration-log-list
    log_items = fetch(f"/api/strategy/iterations/{i}/logs")["data"]["items"]
    print(f"- Log-Einträge: {len(log_items)}")
    for e in log_items[-3:]:
        txt = e.get("text") or ""
        if len(txt) > 200:
            txt = txt[:200] + "…"
        run_part = f" · run:{e['run_id']}" if e.get("run_id") else ""
        print(f"  - [{e.get('created_at')}]{run_part} {txt}")
    print()


def indicator_config_read(i: int) -> None:
    d = fetch(f"/api/config/indicator/{i}")["data"]
    print(f"## Indicator-Config {i} — {d.get('name')}")
    print(f"- Strategie: {d.get('strategy_concept_name')} · Iter: {d.get('strategy_iteration_version')} (id {d.get('strategy_iteration_id')})")
    if d.get("description"):
        print(f"- {d['description']}")
    for name, p in (d.get("config_json") or {}).items():
        # GEÄNDERT: tf nicht mehr filtern — der Rechen-Timeframe ist laufzeit-wirksam
        # (fehlt er beim Zurückschreiben, bricht der Lauf mit ValueError ab)
        params = ", ".join(f"{k}={v}" for k, v in p.items() if k not in ("enabled", "indicator"))
        # GEAENDERT: deaktivierte Indikatoren (enabled: false) markieren
        tag = "" if p.get("enabled", True) else " [deaktiviert]"
        print(f"  - **{name}** ({p.get('indicator')}){tag}: {params}")
    print()


def backtest_config_read(i: int) -> None:
    d = fetch(f"/api/config/backtest/{i}")["data"]
    print(f"## Backtest-Config {i} — {d.get('name')}")
    if d.get("description"):
        print(f"- {d['description']}")
    print(f"- {d['symbol']} {d['timeframe']} · {d['start']} → {d['end']} · exchange {d.get('exchange')}")
    print(f"- Sizing: {d['size']} {d['size_type']}, init_cash {d['init_cash']}, fees {d['fees']}, slippage {d.get('slippage')}")
    # GEÄNDERT: stop_exit_price/stop_order_type ausgeben; None = VBT-Default,
    # nicht als 0/aus verwechselbar. Die alte td_stop/tp_stop/sl_stop/tsl_stop-Zeile referenzierte
    # Felder, die die API seit dem Umzug der Stops in indicators_json['_stops'] nicht mehr liefert
    # (Stale Read seit Schritt 3d) — hier durch die tatsächlich vorhandenen Portfolio-Felder ersetzt.
    print(f"- Stop-Ausführung: stop_exit_price={d.get('stop_exit_price') or 'VBT-Default'} "
          f"stop_order_type={d.get('stop_order_type') or 'VBT-Default'}")
    print()


def strategy_config_read(i: int) -> None:
    d = fetch(f"/api/config/strategy/{i}")["data"]
    print(f"## Strategy-Config {i} — {d.get('name')}")
    if d.get("description"):
        print(f"- {d['description']}")
    print(f"- Familie: {d.get('strategy_family')} · Name: {d.get('strategy_name')} · Typ: {d.get('type')}")
    if d.get("import_path"):
        print(f"- Import: `{d['import_path']}`")
    cfg = d.get("strategy_config_json")
    if cfg:
        render_spec(cfg)
    print()


def result_read(i: int) -> None:
    s = fetch(f"/api/backtest/results/{i}/stats")["stats"]
    print(f"## Result {i}")
    print(f"- Return: {num(s.get('Total Return [%]'))}% (Benchmark {num(s.get('Benchmark Return [%]'))}%)")
    print(f"- Sharpe {num(s.get('Sharpe Ratio'))} / Sortino {num(s.get('Sortino Ratio'))} / Calmar {num(s.get('Calmar Ratio'))}")
    print(f"- Max DD {num(s.get('Max Drawdown [%]'))}% (Dauer {s.get('Max Drawdown Duration')})")
    # GEAENDERT: offene Positionen ausweisen; Win-Rate und Profit-Factor
    # rechnen ueber die geschlossenen Trades (Total Trades - Open Trades).
    # GEAENDERT: Long/Short-Aufteilung ueber trades_str() mit ausweisen.
    _tr = trades_str({
        "total_trades": s.get('Total Trades'), "open_trades": s.get('Open Trades'),
        "long_trades": s.get('Long Trades'), "short_trades": s.get('Short Trades'),
    })
    print(f"- Trades: {_tr} · Win-Rate {num(s.get('Win Rate [%]'))}% · Profit-Factor {num(s.get('Profit Factor'))}")
    print(f"- Value: {s.get('Start Value')} → {num(s.get('End Value'))}")
    # GEAENDERT: tatsaechlich gerechneter Zeitraum + Balkenzahl (nicht der
    # angefragte Run-Zeitraum). NULL bei älteren Results.
    if s.get('Start Index') or s.get('End Index') or s.get('Bar Count'):
        print(f"- Gerechnet: {str(s.get('Start Index') or '—')[:10]} → {str(s.get('End Index') or '—')[:10]} "
              f"({s.get('Bar Count') or '—'} Balken)")
    print()


def run_read(i: int) -> None:
    # GEÄNDERT: Einzel-GET statt Listen-Filter; damit ist ein Run
    # unabhängig davon lesbar, ob er unter den letzten RUN_LIST_LIMIT Runs liegt.
    try:
        r = fetch(f"/api/backtest/runs/{i}")["data"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"## Run {i} — nicht gefunden\n")
            return
        raise
    # Sprechendes Label: Strategie+Version statt nackter ID (strategy_family=Slug,
    # strategy_name=Versionsnummer). Testset-Zugehoerigkeit, falls der Run aus einem
    # TestSet-Lauf stammt.
    fam = (r.get("strategy_family") or "").upper()
    ver = r.get("strategy_name")
    label = f"{fam} v{ver}" if fam else f"Run {i}"
    print(f"## Run {i} — {label} · {r.get('symbol')} {r.get('timeframe')}")
    print(f"- Status: {r.get('status')} · {r.get('n_combinations')} Kombinationen")
    # GEAENDERT: Selbstauskunft des Laufs: Kennzeichnung (nicht Ausblenden),
    # wenn ein Lauf keine Signale erzeugt hat oder die Historie nicht reichte.
    usability = r.get("usability")
    if usability and usability != "usable":
        print(f"- **NICHT VERWERTBAR ({usability}):** {r.get('usability_note') or '(kein Grund hinterlegt)'}")
    elif usability == "usable" and r.get("usability_note"):
        print(f"- {r['usability_note']}")
    # Vorlauf-Pruefung: nur melden, wenn tatsaechlich ein Vorlauf-Problem vorliegt
    # (warmup_bars < warmup_required_bars). Ausreichender Vorlauf bleibt stumm.
    wb, wrb = r.get("warmup_bars"), r.get("warmup_required_bars")
    if wb is not None and wrb is not None and wrb > 0 and wb < wrb:
        print(f"- **VORLAUF-WARNUNG:** {r.get('warmup_note') or f'{wb}/{wrb} Balken Vorlauf'}")
    # GEÄNDERT: wirksame Metrik-Auswahl aus backtest_config_json. Ohne
    # explizite Angabe zeigt 'metrics_resolved' die 'auto'-Entscheidung (voll/kern);
    # eine gesetzte Kürzungs-Notiz erscheint bereits oben über usability_note.
    bc = r.get("backtest_config_json") or {}
    metrics_raw = bc.get("metrics")
    metrics_resolved = bc.get("metrics_resolved")
    if metrics_resolved:
        label = metrics_raw if metrics_raw is not None else "auto"
        print(f"- Metrik-Auswahl: {label} → {', '.join(metrics_resolved)}")
    if r.get("testset_name"):
        ts = f"testset:{r.get('testset_id')}"
        if r.get("testset_run_id"):
            ts += f" · testset-run:{r.get('testset_run_id')}"
        print(f"- Testset: {r.get('testset_name')} ({ts})")
    print(f"- Zeitraum: {str(r.get('start_date', ''))[:10]} → {str(r.get('end_date', ''))[:10]}")
    # Aggregat-Kennzahlen aus der Analyse (falls berechnet)
    try:
        summ = fetch(f"/api/backtest/runs/{i}/analyse/summary")
        print(f"- Analyse: {summ.get('total_results')} Results · {summ.get('profitable_count')} profitabel · "
              f"avg Return {num(summ.get('avg_return'))} / avg Sharpe {num(summ.get('avg_sharpe'))} / max Sharpe {num(summ.get('max_sharpe'))}")
    except Exception:
        pass
    # Verlinkte Results
    try:
        results = fetch(f"/api/backtest/runs/{i}/results")["data"]["items"]
        if results:
            ids = ", ".join(str(x["id"]) for x in results[:5])
            print(f"- Result-IDs: {ids}{' ...' if len(results) > 5 else ''}")
    except Exception:
        pass
    print()


def testset_read(i: int) -> None:
    d = fetch(f"/api/testsets/{i}")["data"]
    print(f"## Testset {i} — {d.get('name')}")
    if d.get("description"):
        print(f"- {d['description']}")
    ids = d.get("backtest_config_ids") or []
    shown = ", ".join(str(x) for x in ids[:10])
    print(f"- {len(ids)} Backtest-Configs: {shown}{' ...' if len(ids) > 10 else ''}")
    if d.get("created_by"):
        print(f"- Erstellt von: {d['created_by']}")
    print()


def leaderboard_read(i: int) -> None:
    d = fetch(f"/api/leaderboard/{i}/drilldown")["data"]
    print(f"## Leaderboard-Eintrag {i}")
    if d.get("executive_summary"):
        print(f"- {d['executive_summary']}")
    results = d.get("results") or []
    print(f"- {len(results)} Configs:")
    for r in results[:10]:
        if r.get("missing"):
            print(f"  - #{r.get('position')}: (Result fehlt)")
            continue
        print(f"  - #{r.get('position')} result:{r.get('result_id')} {r.get('symbol') or ''} — "
              f"Ret {num(r.get('total_return_pct'))}% / Sharpe {num(r.get('sharpe_ratio'))} / "
              f"DD {num(r.get('max_drawdown_pct'))}% / {r.get('n_trades')} Trades")
    print()


def playground_setup_read(i: int) -> None:
    d = fetch(f"/api/chart-playground/setups/{i}")["data"]
    print(f"## Playground-Setup {i} — {d.get('name')}")
    if d.get("description"):
        print(f"- {d['description']}")
    print()


def knowledge_search(query: str, k: int = 5) -> None:
    # GEÄNDERT: Trefferzahl wählbar (--k <n> in main()), Default bleibt 5.
    qs = urllib.parse.urlencode({"q": query, "k": k})
    d = fetch(f"/api/knowledge/search?{qs}")
    results = d.get("results") or []
    print(f"## Knowledge-Suche — \"{query}\" ({len(results)} Treffer)")
    for r in results:
        print(f"- **{r.get('vault_path')}** (Chunk #{r.get('chunk_index')}, sim {num(r.get('similarity'), '{:.3f}')})")
        if r.get("heading_path"):
            print(f"  - {r['heading_path']}")
        content = (r.get("content") or "").strip().replace("\n", " ")
        if len(content) > 300:
            content = content[:300] + "…"
        if content:
            print(f"  - {content}")
    print()


def vault_list(path: str) -> None:
    qs = urllib.parse.urlencode({"q": path, "limit": 20})
    d = fetch(f"/api/knowledge/files?{qs}")
    files = d.get("files") or []
    print(f"## Vault-Dateien — Filter \"{path}\" ({d.get('total', len(files))} gesamt)")
    for f in files[:20]:
        tags = ", ".join(f.get("tags") or [])
        print(f"- **{f.get('vault_path')}** — {f.get('chunk_count')} Chunks · Tags: {tags or '—'}")
    print()


# ---------------------------------------------------------------------------
# Kopier-Handler (copy). Erzeugen jeweils ein neues Objekt und lassen das
# Original unverändert. Funktionsname: <bereich>_copy.
# ---------------------------------------------------------------------------

def backtest_config_copy(i: int) -> None:
    d = post(f"/api/config/backtest/{i}/copy")["data"]
    print(f"## Kopiert: Backtest-Config {i} -> **{d['id']}** ({d.get('name')})\n")


def indicator_config_copy(i: int) -> None:
    d = post(f"/api/config/indicator/{i}/copy")["data"]
    print(f"## Kopiert: Indicator-Config {i} -> **{d['id']}** ({d.get('name')})\n")


def iteration_copy(i: int) -> None:
    d = post(f"/api/strategy/iterations/{i}/copy")["data"]
    name = d.get("version_name") or d.get("version")
    print(f"## Kopiert: Iteration {i} -> **{d['id']}** ({name}, Concept {d.get('concept_id')})\n")


COPY_HANDLERS = {
    "iteration": iteration_copy,
    "backtest-config": backtest_config_copy,
    "indicator-config": indicator_config_copy,
}


# ---------------------------------------------------------------------------
# Erstell-Handler: IndicatorConfig aus einem Result erstellen. Friert die
# Gewinner-Parameter fest (Range -> Skalar) und legt eine Single-Point-Config
# an. Eigener Parser, weil das Segment-Label (Return/Sharpe/PF/WinR90) kein
# numerischer Wert ist.
# ---------------------------------------------------------------------------

def _parse_result_segment_arg(a: str):
    """Arg -> (result_id:str, segment:str|None).

    Akzeptierte Formen: `result:2706026`, `result:2706026:Sharpe`, `2706026`,
    `2706026/Sharpe`. Trenner ':' oder '/'. Gibt (None, None) bei ungültig.
    """
    s = a.strip()
    low = s.lower()
    if low.startswith("result:"):
        s = s[len("result:"):]
    s = s.replace("/", ":")
    parts = s.split(":", 1)
    rid = parts[0].strip()
    seg = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    if not rid.isdigit():
        return None, None
    return rid, seg


def indicator_config_create_from_result(rid: str, segment) -> None:
    body = {"segment": segment} if segment else None
    d = post(f"/api/config/indicator/from-result/{rid}", body)["data"]
    print(f"## Erstellt: IndicatorConfig **{d['id']}** ({d.get('name')}) aus Result {rid}\n")


# ---------------------------------------------------------------------------
# Flag-Parser für Create-/Start-Verben. Liest `--key value` und `--key=value`
# in ein Dict. Positionsargumente landen unter "_positional".
# ---------------------------------------------------------------------------

def _parse_flags(tokens: list) -> dict:
    """Parst `--key value` / `--key=value` in ein Dict. Rest -> _positional."""
    flags: dict = {}
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("--"):
            key = t[2:]
            if "=" in key:
                k, v = key.split("=", 1)
                flags[k] = v
                i += 1
            elif i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                flags[key] = tokens[i + 1]
                i += 2
            else:
                flags[key] = True
                i += 1
        else:
            flags.setdefault("_positional", []).append(t)
            i += 1
    return flags


def _maybe_json(flags: dict, payload, verb: str = "json") -> bool:
    """Gibt bei --json das rohe Payload als JSON aus und meldet True (Verb ist fertig).

    Maschinenlesbarer Ausgabe-Modus für Folge-Analysen — statt die formatierten
    Markdown-Zeilen zurückzuparsen, bekommt der Aufrufer die Items direkt.

    GEÄNDERT: --out schreibt das vollständige JSON in eine Datei unter
    OUT_DIR (Konsole nur Pfad + Zeichenzahl), analog zum `api`-Verb (_print_data);
    --full und --out schließen sich aus. Ohne beide Flags bleibt das bisherige
    Verhalten (volles JSON auf stdout, maschinenlesbar/parsebar) unverändert — kein
    Markdown-Rahmen wie bei _print_data, sonst wäre `json.loads(stdout)` kaputt.
    """
    if not flags.get("json"):
        return False
    full = bool(flags.get("full"))
    out = flags.get("out")
    if out and full:
        raise ValueError(f"{verb}: --out und --full schließen sich aus")
    text_out = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    if out:
        path = _out_path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        pruned = _prune_out_dir()
        written = path.write_text(text_out, encoding="utf-8")
        note = f" · {pruned} abgelaufene aufgeraeumt" if pruned else ""
        print(f"## {verb}: vollständiges JSON geschrieben — {path} ({written} Zeichen){note}\n")
        return True
    print(text_out)
    return True


def _require(flags: dict, key: str, verb: str):
    """Holt einen Pflicht-Flag-Wert oder wirft ValueError."""
    val = flags.get(key)
    if not val or val is True:
        raise ValueError(f"--{key} fehlt (z.B. {verb} --{key} <wert>)")
    return val


def _read_json_file(path: str):
    """Lädt eine JSON-Datei. Wirft bei Fehler — kein stiller Fallback."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# GEÄNDERT: Raster-Quelle für testset-run-start und preflight:
# --indicator-config <id> (gespeicherte Config) oder --indicators <datei> (Raster inline).
def _indicators_source_body(flags: dict, verb: str) -> dict:
    """Baut den Raster-Teil des Request-Bodys aus --indicator-config oder --indicators.

    Genau eines von beiden ist Pflicht — beides oder keines wirft, statt still eine
    Quelle zu bevorzugen. Die Datei trägt dasselbe Format wie bei
    ``indicator-config-create --file`` (Inhalt von config_json, inklusive '_stops').

    Args:
        flags: Geparste Flags des Verbs.
        verb: Verb-Name für die Fehlermeldung.

    Returns:
        {"indicator_config_id": <id>} oder {"indicators": <dict>}.

    Raises:
        ValueError: Wenn beide oder keine der beiden Angaben gesetzt sind.
    """
    cfg_raw = flags.get("indicator-config")
    file_raw = flags.get("indicators")
    has_cfg = bool(cfg_raw) and cfg_raw is not True
    has_file = bool(file_raw) and file_raw is not True
    if has_cfg and has_file:
        raise ValueError(
            f"{verb}: --indicator-config und --indicators schließen sich aus — "
            "genau eine Raster-Quelle angeben"
        )
    if not has_cfg and not has_file:
        raise ValueError(
            f"{verb}: Raster-Quelle fehlt — entweder --indicator-config <id> oder "
            "--indicators <datei> angeben (genau eines von beiden)"
        )
    if has_cfg:
        return {"indicator_config_id": int(cfg_raw)}
    return {"indicators": _read_json_file(str(file_raw))}


def _read_file_or_inline(value: str) -> str:
    """Liest value als Dateiinhalt, wenn eine Datei mit diesem Pfad existiert,
    sonst wird value unverändert als Inline-Wert zurückgegeben (
    --goal/--goal-prompt akzeptieren wahlweise einen Dateipfad oder den
    Inhalt direkt)."""
    path = pathlib.Path(value)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return value


# ---------------------------------------------------------------------------
# Listen-Reads (list). Drucken eine kompakte Markdown-Liste briefbarer Objekte.
# Funktionsname: <bereich>_list. Argumente positionsbasiert (optional/erforderlich
# je Verb), result_list nutzt Flags.
# ---------------------------------------------------------------------------

def concept_list(args: list) -> int:
    items = fetch("/api/strategy/concepts")["data"]["items"]
    print(f"## Konzepte ({len(items)})")
    for c in items:
        # GEÄNDERT: Ziel-Marker auf Basis von has_goal (Abgleich Recherche-Fundsachen mit Bestand)
        goal_marker = "Ziel: ja" if c.get("has_goal") else "Ziel: -"
        print(f"- concept:{c['id']} **{c.get('name')}** ({c.get('slug')}) · {c.get('status')} · Iter-Zähler {c.get('iteration_counter')} · {goal_marker}")
    print()
    return 0


def iteration_list(args: list) -> int:
    qs = f"?concept_id={int(args[0])}" if args else ""
    items = fetch(f"/api/strategy/iterations{qs}")["data"]["items"]
    print(f"## Iterationen ({len(items)})")
    for it in items:
        nm = it.get("version_name") or ""
        print(f"- iteration:{it['id']} v{it.get('version')} {nm} · Concept {it.get('concept_id')} · {it.get('type')} · {it.get('status')}")
    print()
    return 0


def backtest_config_list(args: list) -> int:
    items = fetch("/api/config/backtest")["data"]
    print(f"## Backtest-Configs ({len(items)})")
    for c in items:
        print(f"- backtest-config:{c['id']} **{c.get('name')}** · {c.get('symbol')} {c.get('timeframe')} · {c.get('start')} -> {c.get('end')}")
    print()
    return 0


def indicator_config_list(args: list) -> int:
    parts = []
    if len(args) >= 1:
        parts.append(f"concept_id={int(args[0])}")
    if len(args) >= 2:
        parts.append(f"iteration_id={int(args[1])}")
    q = ("?" + "&".join(parts)) if parts else ""
    items = fetch(f"/api/config/indicator{q}")["data"]
    print(f"## Indicator-Configs ({len(items)})")
    for c in items:
        print(f"- indicator-config:{c['id']} **{c.get('name')}** · Concept {c.get('strategy_concept_id')} Iter {c.get('strategy_iteration_id')}")
    print()
    return 0


def result_list(args: list) -> int:
    f = _parse_flags(args)
    params = {"limit": f.get("limit", 20)}
    if f.get("run"):
        params["run_id"] = f["run"]
    if f.get("symbol"):
        params["symbol"] = f["symbol"]
    if f.get("timeframe"):
        params["timeframe"] = f["timeframe"]
    items = fetch(f"/api/backtest/results?{urllib.parse.urlencode(params)}")["data"]["items"]
    if _maybe_json(f, {"total": len(items), "items": items}, "result-list"):
        return 0
    print(f"## Results ({len(items)})")
    for r in items:
        print(f"- result:{r['id']} run:{r.get('run_id')} {r.get('symbol')} — "
              f"Ret {num(r.get('total_return_pct'))}% / Sharpe {num(r.get('sharpe_ratio'))} / "
              f"DD {num(r.get('max_drawdown_pct'))}% / {trades_str(r)} Trades")
    print()
    return 0


def run_list(args: list) -> int:
    """Runs zu einer Strategie+Version (oder Iteration / TestSet-Lauf), nach Testset gruppiert.

    Flags: --strategy <slug> [--version <n>] | --iteration <id> | --testset-run <id> [--limit <n>]
    Die API loest (Slug, Version) serverseitig zu iteration_ids auf — der Aufrufer
    denkt in Strategie+Version, nicht in Datensatz-IDs.
    """
    f = _parse_flags(args)
    params: dict = {"limit": f.get("limit", 10000)}
    if f.get("strategy"):
        params["strategy"] = f["strategy"]
    if f.get("version"):
        params["version"] = f["version"]
    if f.get("iteration"):
        params["iteration_id"] = f["iteration"]
    if f.get("testset-run"):
        params["testset_run_id"] = f["testset-run"]
    items = fetch(f"/api/backtest/runs?{urllib.parse.urlencode(params)}")["data"]["items"]

    scope = []
    if f.get("strategy"):
        scope.append(str(f["strategy"]).upper() + (f" v{f['version']}" if f.get("version") else ""))
    if f.get("iteration"):
        scope.append(f"iteration:{f['iteration']}")
    if f.get("testset-run"):
        scope.append(f"testset-run:{f['testset-run']}")
    print(f"## Runs — {' · '.join(scope) if scope else 'alle'} ({len(items)})")
    if not items:
        print("- (keine)\n")
        return 0

    # Nach Testset-Lauf (testset_run_id = Auftrags-ID) gruppieren: ein Testset-Lauf
    # umfasst alle Symbol-Runs eines Auftrags. So ist sichtbar, welche Runs als ein
    # Auftrag zusammengehören — und die ID ist direkt als --testset-run-Selektor nutzbar.
    # Einzel-Backtests ohne Testset-Lauf kommen in eine eigene Gruppe.
    groups: dict = {}
    for r in items:
        groups.setdefault(r.get("testset_run_id"), []).append(r)
    # Auftrags-Gruppen zuerst (nach ID), Einzel-Backtests (None) ans Ende.
    for gkey in sorted(groups, key=lambda k: (k is None, k or 0)):
        rs = sorted(groups[gkey], key=lambda x: x["id"])
        if gkey is None:
            print("\n### Einzel-Backtests (kein Testset-Lauf)")
        else:
            name = rs[0].get("testset_name") or "Testset-Lauf"
            tsid = rs[0].get("testset_id")
            ts = f"testset:{tsid} · " if tsid else ""
            print(f"\n### {name} ({ts}testset-run:{gkey})")
        for r in rs:
            # GEAENDERT: Selbstauskunft des Laufs in der Listenzeile: Kennzeichnung
            # nicht verwertbarer Laeufe (Kennzeichnung, kein Ausblenden — die Zeile bleibt stehen).
            usability = r.get("usability")
            flag = f" · NICHT VERWERTBAR ({usability})" if usability and usability != "usable" else ""
            print(f"- run:{r['id']} · {r.get('symbol')} {r.get('timeframe')} · {r.get('status')} · "
                  f"{r.get('n_combinations')} Kombinationen · "
                  f"{str(r.get('start_date', ''))[:10]}→{str(r.get('end_date', ''))[:10]}{flag}")
    print()
    return 0


def testset_list(args: list) -> int:
    items = fetch("/api/testsets")["data"]
    print(f"## Testsets ({len(items)})")
    for t in items:
        n = len(t.get("backtest_config_ids") or [])
        print(f"- testset:{t['id']} **{t.get('name')}** · {n} Backtest-Configs")
    print()
    return 0


def leaderboard_list(args: list) -> int:
    qs = f"?testset_id={int(args[0])}" if args else ""
    items = fetch(f"/api/leaderboard{qs}")["data"]["items"]
    print(f"## Leaderboard ({len(items)})")
    for e in items:
        print(f"- leaderboard:{e['id']} {e.get('testset_name') or ''} {e.get('strategy_family')} {e.get('strategy_name')} — "
              f"Ø Ret {num(e.get('total_return_avg'))}% / Sharpe {num(e.get('sharpe_avg'))} / "
              f"{e.get('configs_win')}W-{e.get('configs_loss')}L")
    print()
    return 0


def symbol_list(args: list) -> int:
    if len(args) < 2:
        raise ValueError("symbol-list braucht <exchange> <timeframe> (z.B. symbol-list binance 4h)")
    exchange, timeframe = args[0], args[1]
    qs = urllib.parse.urlencode({"exchange": exchange, "timeframe": timeframe})
    d = fetch(f"/api/config/symbols?{qs}")["data"]
    syms = d.get("symbols") or []
    print(f"## Symbole {exchange}/{timeframe} ({len(syms)}) — Datei {d.get('file')}, vorhanden {d.get('exists')}")
    if syms:
        print(", ".join(syms))
    print()
    return 0


def symbol_correlation(args: list) -> int:
    """Korrelation zwischen Symbolen und daraus die effektive Symbolzahl.

    Aufruf: symbol-correlation <exchange> <timeframe> --symbols A,B,C
            [--start 2020-01-01] [--end 2025-01-01] [--window 90] [--min-overlap 30] [--json]

    Gerechnet wird serverseitig auf den Log-Renditen der Tagesschlusskurse (die
    Quelldatei wird dafür auf Tagesbasis resampelt). Je Paar zählt nur der gemeinsame
    Zeitraum; dessen Länge steht mit in der Ausgabe. Neben dem Gesamtwert kommt die
    rollierende Korrelation (Minimum/Median/Maximum) — Korrelation steigt in
    Stressphasen, ein Gesamtwert verdeckt genau den Fall, auf den es ankommt.

    Die effektive Symbolzahl wird auf zwei Wegen ausgewiesen: aus der mittleren
    Paarkorrelation und über die Eigenwerte der Korrelationsmatrix. Weichen beide
    stark voneinander ab, ist das selbst eine Information.
    """
    f = _parse_flags(args)
    positional = f.get("_positional") or []
    if len(positional) < 2:
        raise ValueError(
            "symbol-correlation braucht <exchange> <timeframe> --symbols A,B,C "
            "(z.B. symbol-correlation binance 4h --symbols BTCUSDT,ETHUSDT)"
        )
    if not f.get("symbols"):
        raise ValueError("symbol-correlation braucht --symbols A,B,C (mindestens zwei Symbole)")
    params = {
        "exchange": positional[0],
        "timeframe": positional[1],
        "symbols": f["symbols"],
    }
    for flag, key in (("start", "start"), ("end", "end"), ("window", "window"),
                      ("min-overlap", "min_overlap")):
        if f.get(flag):
            params[key] = f[flag]
    d = fetch(f"/api/config/symbols/correlation?{urllib.parse.urlencode(params)}")["data"]
    if _maybe_json(f, d, "symbol-correlation"):
        return 0

    syms = d["symbols"]
    print(f"## Symbol-Korrelation {d['exchange']}/{d['source_timeframe']} — {len(syms)} Symbole")
    print(f"Tages-Log-Renditen · rollendes Fenster {d['window']} Tage · "
          f"Mindest-Überlappung {d['min_overlap']} Tage\n")

    print("### Abdeckung")
    print("| Symbol | von | bis | Tage | Lücken |")
    print("|---|---|---|---|---|")
    for c in d["coverage"]:
        print(f"| {c['symbol']} | {str(c['start'])[:10]} | {str(c['end'])[:10]} | "
              f"{c['days']} | {c['missing_days']} |")

    print("\n### Korrelationsmatrix (gesamter gemeinsamer Zeitraum)")
    print("| | " + " | ".join(syms) + " |")
    print("|---" * (len(syms) + 1) + "|")
    for row in syms:
        cells = [num(d["correlation_matrix"][row].get(col)) for col in syms]
        print(f"| **{row}** | " + " | ".join(cells) + " |")

    print("\n### Paare — gemeinsamer Zeitraum und rollierende Extremwerte")
    print("| Paar | Korrelation | Überlappung | von | bis | roll. min | roll. Median | roll. max |")
    print("|---|---|---|---|---|---|---|---|")
    for p in d["pairs"]:
        print(f"| {p['a']} / {p['b']} | {num(p['correlation'])} | {p['overlap_days']} Tage | "
              f"{str(p['overlap_start'])[:10]} | {str(p['overlap_end'])[:10]} | "
              f"{num(p['rolling_min'])} | {num(p['rolling_median'])} | {num(p['rolling_max'])} |")

    print("\n### Effektive Symbolzahl")
    print(f"- Mittlere Paarkorrelation: {num(d['mean_correlation'], '{:.4f}')}")
    print(f"- N_eff (mittlere Paarkorrelation): {num(d['effective_symbols_mean_corr'], '{:.3f}')} von {len(syms)}")
    print(f"- N_eff (Eigenwerte): {num(d['effective_symbols_eigenvalues'], '{:.3f}')} von {len(syms)}")
    print(f"- Eigenwerte: " + ", ".join(num(v, "{:.4f}") for v in d["eigenvalues"]))
    print()
    return 0


def _filter_indicators(groups: list, group_filter: str = None, search: str = "") -> list:
    """Filtert die Indikator-Gruppen des Katalogs nach Gruppe und/oder Suchtext.

    Reine Funktion (kein Netzwerk-Zugriff) — testbar ohne laufenden Server.

    Args:
        groups: Liste der Gruppen-Objekte (`{"name": ..., "indicators": [...]}`),
            wie von `GET /api/chart-playground/indicators` geliefert.
        group_filter: Falls gesetzt, nur Indikatoren dieser Gruppe (exakter Name-Match).
        search: Case-insensitiver Substring-Filter über `id` und `name`. Leerer
            String = kein Filter.

    Returns:
        Liste der passenden Indikator-Objekte über alle betroffenen Gruppen hinweg.
    """
    search = (search or "").lower()
    matches = []
    for g in groups:
        if group_filter and g["name"] != group_filter:
            continue
        for ind in g["indicators"]:
            if search and search not in ind["id"].lower() and search not in ind["name"].lower():
                continue
            matches.append(ind)
    return matches


def _format_indicator_line(ind: dict) -> str:
    """Formatiert einen Indikator als kompakte Markdown-Zeile (id/inputs/params/outputs).

    Args:
        ind: Indikator-Objekt aus dem Katalog (`id`, `inputs`, `params`, `outputs`).

    Returns:
        Eine einzelne Markdown-Bullet-Zeile ohne Defaults-Ballast.
    """
    params = ", ".join(p["name"] for p in ind.get("params", []))
    return (f"- **{ind['id']}** — inputs: {', '.join(ind.get('inputs', [])) or '—'} | "
            f"params: {params or '—'} | outputs: {', '.join(ind.get('outputs', [])) or '—'}")


def playground_indicators_list(args: list) -> int:
    """Indikator-Katalog des Chart-Playgrounds — gefiltert statt voll gedumpt.

    Ohne Filter: kompakte Gruppen-Übersicht (Name + Anzahl je Gruppe).
    Mit --group <name>: nur diese Gruppe (z.B. talib, vbt, custom, ta, wqa101).
    Mit --search <substring>: case-insensitiv über id/name gefiltert (z.B. "ema").
    Beide Flags kombinierbar. Bei Treffern: eine Zeile je Indikator mit
    id/inputs/params(Namen)/outputs — kein voller JSON-Dump mit Defaults.
    """
    f = _parse_flags(args)
    group_filter = f.get("group")
    search = f.get("search") or ""
    groups = fetch("/api/chart-playground/indicators")["data"]["groups"]

    if not group_filter and not search:
        total = sum(len(g["indicators"]) for g in groups)
        print(f"## Indikator-Katalog ({total} gesamt)")
        for g in groups:
            print(f"- {g['name']}: {len(g['indicators'])}")
        print("\nFilter: --group <name> und/oder --search <substring>\n")
        return 0

    matches = _filter_indicators(groups, group_filter, search)
    label = " / ".join(
        p for p in (f"Gruppe {group_filter}" if group_filter else None,
                    f"Suche '{search}'" if search else None) if p
    )
    print(f"## Indikator-Katalog — {label} ({len(matches)} Treffer)")
    for ind in matches:
        print(_format_indicator_line(ind))
    print()
    return 0


def run_parameter_ranking(args: list) -> int:
    if not args:
        raise ValueError("run-parameter-ranking braucht <run_id> [metric]")
    run_id = int(args[0])
    metric = args[1] if len(args) > 1 else "sharpe_ratio"
    d = fetch(f"/api/backtest/runs/{run_id}/analyse/parameter-ranking?metric={urllib.parse.quote(metric)}")
    print(f"## Parameter-Ranking Run {run_id} — {d.get('metric_label', metric)}")
    for pname, vals in (d.get("parameters") or {}).items():
        print(f"- **{pname}**:")
        for v in vals[:10]:
            print(f"  - {v.get('value')}: Ø {num(v.get('avg'), '{:.4f}')} "
                  f"(min {num(v.get('min'), '{:.4f}')} / max {num(v.get('max'), '{:.4f}')}, n {v.get('count')})")
    print()
    return 0


def run_top_results(args: list) -> int:
    f = _parse_flags(args)
    pos = f.get("_positional") or []
    if not pos:
        raise ValueError("run-top-results braucht <run_id> [metric] [limit] [direction] [--json] [--out|--full]")
    run_id = int(pos[0])
    metric = pos[1] if len(pos) > 1 else "sharpe_ratio"
    limit = pos[2] if len(pos) > 2 else "20"
    direction = pos[3] if len(pos) > 3 else "desc"
    qs = urllib.parse.urlencode({"metric": metric, "limit": limit, "direction": direction})
    d = fetch(f"/api/backtest/runs/{run_id}/analyse/top-results?{qs}")
    results = d.get("results") or []
    if _maybe_json(f, {"total": len(results), "items": results}, "run-top-results"):
        return 0
    print(f"## Top-Results Run {run_id} — {d.get('metric_label', metric)} {direction} ({len(results)})")
    for r in results:
        params = r.get("actual_params") or {}
        pstr = ", ".join(f"{k}={v}" for k, v in params.items()) if isinstance(params, dict) else ""
        print(f"- result:{r['id']} — Ret {num(r.get('total_return_pct'))}% / WinR {num(r.get('win_rate_pct'))}% / "
              f"Sharpe {num(r.get('sharpe_ratio'))} / DD {num(r.get('max_drawdown_pct'))}% / "
              f"PF {num(r.get('profit_factor'))} / {trades_str(r)} Trades")
        if pstr:
            print(f"  - {pstr}")
    print()
    return 0


# Spalten-Index im /results/dt-Endpoint (Sortier-Parameter order[0][column])
_DT_SORT_IDX = {
    # GEAENDERT: ToDo 10 — alle Indizes +1 (neue Bestwert-Badge-Spalte an Index 3 im /results/dt)
    "sharpe_ratio": 14, "max_drawdown_pct": 16, "total_trades": 17,
    "win_rate_pct": 18, "profit_factor": 19, "total_return_pct": 20,
}
_METRIC_LABEL = {
    "total_return_pct": "Total Return", "win_rate_pct": "Win Rate",
    "sharpe_ratio": "Sharpe", "profit_factor": "Profit Factor",
    "max_drawdown_pct": "Max Drawdown", "total_trades": "Trades",
}


def run_best(args: list) -> int:
    """Bester Result eines Runs nach <metrik>, gefiltert auf >= min_trades.

    Einfaches Regelwerk gegen Low-Trade-Flukes: erst alle Results mit
    mindestens <min_trades> Trades, davon der höchste Wert der Metrik.
    Filter (total_trades_min) + Sortierung laufen serverseitig über
    /api/backtest/results/dt. Default-Floor 30 Trades.
    """
    f = _parse_flags(args)
    pos = f.get("_positional") or []
    if len(pos) < 2:
        raise ValueError("run-best braucht <run_id> <metrik> [min_trades=30] [limit=1] [--json] [--out|--full]")
    run_id = int(pos[0])
    metric = pos[1]
    if metric not in _DT_SORT_IDX:
        raise ValueError(f"Unbekannte Metrik {metric!r}. Erlaubt: {', '.join(_DT_SORT_IDX)}")
    min_trades = int(pos[2]) if len(pos) > 2 else 30
    limit = int(pos[3]) if len(pos) > 3 else 1
    qs = urllib.parse.urlencode({
        "run_id": run_id, "total_trades_min": min_trades,
        "order[0][column]": _DT_SORT_IDX[metric], "order[0][dir]": "desc",
        "start": 0, "length": limit, "draw": 1,
    })
    dd = fetch(f"/api/backtest/results/dt?{qs}")
    rows = dd.get("data") or []
    n = dd.get("recordsFiltered")
    if _maybe_json(f, {"total": n, "items": rows}, "run-best"):
        return 0
    print(f"## Best Run {run_id} — {_METRIC_LABEL[metric]} desc, min {min_trades} Trades "
          f"({n} Results >= {min_trades} Trades), Top {limit}")
    for r in rows:
        params = r.get("actual_params") or {}
        pstr = ", ".join(f"{k}={v}" for k, v in params.items()) if isinstance(params, dict) else ""
        print(f"- result:{r['id']} — Ret {num(r.get('total_return_pct'))}% / WinR {num(r.get('win_rate_pct'))}% / "
              f"Sharpe {num(r.get('sharpe_ratio'))} / DD {num(r.get('max_drawdown_pct'))}% / "
              f"PF {num(r.get('profit_factor'))} / {trades_str(r)} Trades")
        if pstr:
            print(f"  - {pstr}")
    print()
    return 0


def result_query(args: list) -> int:
    """Results eines Runs mit kombinierten Metrik-Filtern abfragen.

    Flags: --run <id> --where "sharpe_ratio>=1.5,total_trades>=100,max_drawdown_pct>=-40"
           [--sort <metrik>] [--direction asc|desc] [--limit <n=20>] [--json]
    Bedingungen nur >= und <=, UND-verknüpft — sie werden 1:1 auf die
    serverseitigen _min/_max-Filter des dt-Endpunkts abgebildet. Erlaubte
    Metriken: die Keys aus _DT_SORT_IDX (total_return_pct, win_rate_pct,
    sharpe_ratio, profit_factor, max_drawdown_pct, total_trades).
    """
    f = _parse_flags(args)
    run_id = int(_require(f, "run", "result-query"))
    raw = _require(f, "where", "result-query")
    sort = f.get("sort", "total_return_pct")
    if sort not in _DT_SORT_IDX:
        raise ValueError(f"Unbekannte Sortier-Metrik {sort!r}. Erlaubt: {', '.join(_DT_SORT_IDX)}")
    direction = f.get("direction", "desc")
    if direction not in ("asc", "desc"):
        raise ValueError("--direction erlaubt nur asc|desc")
    limit = int(f.get("limit", 20))

    params = {
        "run_id": run_id,
        "order[0][column]": _DT_SORT_IDX[sort], "order[0][dir]": direction,
        "start": 0, "length": limit, "draw": 1,
    }
    conds = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\w+)\s*(>=|<=)\s*(-?\d+(?:\.\d+)?)$", part)
        if not m:
            raise ValueError(f"--where erwartet <metrik>>=<wert> oder <metrik><=<wert>, bekommen: {part!r}")
        metric, op, val = m.groups()
        if metric not in _DT_SORT_IDX:
            raise ValueError(f"Unbekannte Metrik {metric!r}. Erlaubt: {', '.join(_DT_SORT_IDX)}")
        params[f"{metric}_{'min' if op == '>=' else 'max'}"] = val
        conds.append(part)
    if not conds:
        raise ValueError("--where ist leer")

    dd = fetch(f"/api/backtest/results/dt?{urllib.parse.urlencode(params)}")
    rows = dd.get("data") or []
    n = dd.get("recordsFiltered")
    if _maybe_json(f, {"total": n, "items": rows}, "result-query"):
        return 0
    print(f"## Result-Query Run {run_id} — {' UND '.join(conds)} — Sortierung {sort} {direction} ({n} Treffer, Top {limit})")
    if not rows:
        print("- (keine Treffer)")
    for r in rows:
        print(f"- {_fmt_result_line(r)}")
    print()
    return 0


# ---------------------------------------------------------------------------
# Result-Lookup per Parameter-Werten (result-lookup) + Kreuz-Test (kreuztest).
# Serverseitig über GET /api/backtest/runs/{id}/results/lookup — exakter Lookup
# einer Kombination oder Nachbarschafts-Modus (±tolerance je Parameter,
# Plateau-Prüfung). kreuztest schlägt die markierten Bestwerte aus Run A in
# Run B nach und stellt die Metriken gegenüber.
# ---------------------------------------------------------------------------

def _parse_params_flag(raw: str) -> dict:
    """Zerlegt --params "key=wert,key2=wert2" in ein Dict (Werte verbatim als Strings)."""
    wanted: dict = {}
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"--params erwartet key=wert-Paare (Komma-getrennt), bekommen: {part!r}")
        k, v = part.split("=", 1)
        wanted[k.strip()] = v.strip()
    if not wanted:
        raise ValueError("--params ist leer")
    return wanted


def _lookup(run_id: int, params: dict, tolerance=None, limit=None, tolerance_steps=None) -> dict:
    """Ruft die Lookup-Route auf und gibt deren data-Block (items/total) zurück."""
    qp = dict(params)
    if tolerance is not None:
        qp["tolerance"] = tolerance
    if tolerance_steps is not None:
        qp["tolerance_steps"] = tolerance_steps
    if limit is not None:
        qp["limit"] = limit
    return fetch(f"/api/backtest/runs/{run_id}/results/lookup?{urllib.parse.urlencode(qp)}")["data"]


def _tolerance_kwargs(f: dict) -> dict:
    """Liest --tolerance / --tolerance-steps in _lookup-kwargs (schließen sich aus)."""
    tol = f.get("tolerance")
    steps = f.get("tolerance-steps")
    if tol and steps:
        raise ValueError("--tolerance und --tolerance-steps schließen sich aus — nur eins angeben")
    kwargs: dict = {}
    if tol:
        kwargs["tolerance"] = tol
    if steps:
        kwargs["tolerance_steps"] = steps
    return kwargs


def _tolerance_label(f: dict) -> str:
    """Einheitlicher Toleranz-Zusatz für die Markdown-Überschriften."""
    if f.get("tolerance-steps"):
        return f" · Toleranz ±{f['tolerance-steps']} Schritt(e)"
    if f.get("tolerance"):
        return f" · Toleranz ±{f['tolerance']}"
    return ""


def _neighborhood_summary(items: list) -> dict:
    """Verdichtet eine Nachbarschafts-Treffermenge zum Plateau-Score.

    Beantwortet „Plateau oder Nadel?" in wenigen Kennzahlen statt N Zeilen:
    Median/Mittel/Streuung des Total Return, Anteil profitabel, Bester/Schlechtester.
    """
    rets = [(r["total_return_pct"], r["id"]) for r in items
            if isinstance(r.get("total_return_pct"), (int, float))]
    if not rets:
        return {"n": len(items), "n_mit_return": 0}
    values = [v for v, _ in rets]
    best = max(rets)
    worst = min(rets)
    return {
        "n": len(items),
        "n_mit_return": len(values),
        "anteil_profitabel_pct": round(100.0 * sum(1 for v in values if v > 0) / len(values), 1),
        "return_median": round(statistics.median(values), 2),
        "return_mittel": round(statistics.fmean(values), 2),
        "return_streuung": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
        "return_bester": {"result_id": best[1], "total_return_pct": round(best[0], 2)},
        "return_schlechtester": {"result_id": worst[1], "total_return_pct": round(worst[0], 2)},
    }


def result_lookup(args: list) -> int:
    """Results eines Runs per Parameter-Werten nachschlagen (serverseitig).

    Flags: --run <id> --params "key=wert,key2=wert2"
           [--tolerance <t> | --tolerance-steps <N>] [--limit <n=20>] [--summary] [--json]
    Ohne Toleranz exakter Lookup der einen Kombination; mit --tolerance alle
    Results, deren Parameter je ±t (skalar) um die Zielwerte liegen; mit
    --tolerance-steps N je Parameter ±N Raster-Schritte (Schrittweite aus dem
    Run abgeleitet — bildet die echte ±N-Schritt-Nachbarschaft auch bei
    ungleichen Schrittweiten je Achse). Subset: nur die angegebenen Keys müssen
    passen. Unbekannte Parameter-Namen meldet der Server mit den vorhandenen
    Namen des Runs. --summary verdichtet die Nachbarschaft zum Plateau-Score
    (holt dafür die volle Treffermenge, --limit spielt dann keine Rolle).
    """
    f = _parse_flags(args)
    run_id = int(_require(f, "run", "result-lookup"))
    wanted = _parse_params_flag(_require(f, "params", "result-lookup"))
    pstr = ", ".join(f"{k}={v}" for k, v in wanted.items())
    tkw = _tolerance_kwargs(f)
    tol = _tolerance_label(f)

    if f.get("summary"):
        d = _lookup(run_id, wanted, limit=100000, **tkw)
        items = d.get("items") or []
        summ = _neighborhood_summary(items)
        if _maybe_json(f, summ, "result-lookup"):
            return 0
        print(f"## Plateau-Score Run {run_id} — {pstr}{tol}")
        if not items:
            print("- (keine Treffer)\n")
            return 0
        print(f"- Nachbarschaft: {summ['n']} Results · {summ['anteil_profitabel_pct']}% profitabel")
        print(f"- Total Return: Median {num(summ['return_median'])}% · Mittel {num(summ['return_mittel'])}% · "
              f"Streuung {num(summ['return_streuung'])}")
        print(f"- Bester: result:{summ['return_bester']['result_id']} ({num(summ['return_bester']['total_return_pct'])}%) · "
              f"Schlechtester: result:{summ['return_schlechtester']['result_id']} "
              f"({num(summ['return_schlechtester']['total_return_pct'])}%)")
        print()
        return 0

    out_limit = int(f.get("limit", 20))
    d = _lookup(run_id, wanted, limit=out_limit, **tkw)
    items = d.get("items") or []
    total = d.get("total") or 0
    if _maybe_json(f, {"total": total, "items": items}, "result-lookup"):
        return 0

    print(f"## Result-Lookup Run {run_id} — {pstr}{tol} ({total} Treffer)")
    if not items:
        print("- (keine Treffer)")
    for r in items:
        print(f"- {_fmt_result_line(r)}")
    if total > len(items):
        print(f"- … {total - len(items)} weitere Treffer (--limit erhöhen)")
    print()
    return 0


def _favorite_results(run_id: int, kinds: list) -> list:
    """Markierte Favoriten-Results eines Runs (dedupliziert über die Sterne-Arten)."""
    favorites: list = []
    seen: set = set()
    for kind in kinds:
        col_idx, field, _suffix, _label = _FAV_KINDS[kind]
        rows, _ = _dt_query(run_id, col_idx, length=200)
        for r in rows:
            if r.get(field) and r["id"] not in seen:
                seen.add(r["id"])
                favorites.append(r)
    return favorites


def _kreuztest_rows(run_a: int, run_b: int, kinds: list, tol_kwargs: dict) -> list:
    """Vergleichszeilen eines Run-Paars: je Favorit aus A das Gegenstück aus B (oder None)."""
    rows = []
    for a in sorted(_favorite_results(run_a, kinds), key=lambda x: x["id"]):
        num_params = {k: v for k, v in (a.get("actual_params") or {}).items()
                      if isinstance(v, (int, float)) and not isinstance(v, bool)}
        b = None
        if num_params:
            items = _lookup(run_b, num_params, limit=1, **tol_kwargs).get("items") or []
            b = items[0] if items else None
        rows.append({"params": num_params, "a": a, "b": b})
    return rows


def _print_kreuztest_table(rows: list) -> None:
    """Markdown-Vergleichstabelle für die Zeilen eines Run-Paars."""
    print("| Params | Result A→B | Ret % | Sharpe | PF | WinR % | Trades |")
    print("|---|---|---|---|---|---|---|")
    for row in rows:
        a, b = row["a"], row["b"]

        def pair(key: str) -> str:
            return f"{num(a.get(key))} → {num(b.get(key)) if b else '—'}"

        pstr = ", ".join(f"{k}={v}" for k, v in row["params"].items()) or "(keine numerischen Params)"
        ab = f"{a['id']} → {b['id'] if b else 'nicht gefunden'}"
        print(f"| {pstr} | {ab} | {pair('total_return_pct')} | {pair('sharpe_ratio')} | "
              f"{pair('profit_factor')} | {pair('win_rate_pct')} | "
              f"{trades_str(a)} → {trades_str(b) if b else '—'} |")


def kreuztest(args: list) -> int:
    """Markierte Bestwerte aus Run/Testset-Lauf A in B nachschlagen (Vergleichstabelle).

    Flags: --from-run <A> --to-run <B>                        (Einzel-Paar)
       oder --from-testset-run <A> --to-testset-run <B>       (ganze Fenster/Testsets,
            Runs werden per Symbol+Timeframe gepaart — BTC-Run zu BTC-Run usw.)
       dazu [--user] [--tolerance <t> | --tolerance-steps <N>] [--json]
    Quelle sind die roten Doku-Favoriten (Bestwerte) der A-Seite; --user nimmt
    zusätzlich die gelben User-Sterne. Je Kombination wird das Result mit
    denselben Parameterwerten auf der B-Seite nachgeschlagen (nur numerische
    Parameter; run-gebundene Keys wie symbol bleiben außen vor). Mit
    --tolerance (skalar) oder --tolerance-steps (±N Raster-Schritte je
    Parameter) zählt bei mehreren Nachbarschafts-Treffern der beste Total Return.
    """
    f = _parse_flags(args)
    kinds = ["doc"] + (["user"] if f.get("user") else [])
    tol_kwargs = _tolerance_kwargs(f)
    label = "rote Doku-Favoriten" + (" + gelbe User-Sterne" if f.get("user") else "")
    tol = _tolerance_label(f)

    # Paar-Auflösung: Einzel-Paar oder Testset-Lauf gegen Testset-Lauf.
    unmatched: list = []
    if f.get("from-testset-run") or f.get("to-testset-run"):
        ts_a = int(_require(f, "from-testset-run", "kreuztest"))
        ts_b = int(_require(f, "to-testset-run", "kreuztest"))
        runs_a = fetch(f"/api/backtest/runs?testset_run_id={ts_a}&limit=10000")["data"]["items"]
        runs_b = fetch(f"/api/backtest/runs?testset_run_id={ts_b}&limit=10000")["data"]["items"]
        by_key_b = {(r.get("symbol"), r.get("timeframe")): r for r in runs_b}
        pairs = []
        for ra in sorted(runs_a, key=lambda x: x["id"]):
            key = (ra.get("symbol"), ra.get("timeframe"))
            rb = by_key_b.pop(key, None)
            if rb is None:
                unmatched.append(f"run:{ra['id']} ({key[0]} {key[1]}) ohne Gegenstück in testset-run:{ts_b}")
            else:
                pairs.append((ra["id"], rb["id"], f"{key[0]} {key[1]}"))
        unmatched += [f"run:{r['id']} ({k[0]} {k[1]}) ohne Gegenstück in testset-run:{ts_a}"
                      for k, r in by_key_b.items()]
        scope = f"testset-run:{ts_a} → testset-run:{ts_b}"
    else:
        run_a = int(_require(f, "from-run", "kreuztest"))
        run_b = int(_require(f, "to-run", "kreuztest"))
        pairs = [(run_a, run_b, "")]
        scope = f"run:{run_a} → run:{run_b}"

    results = [{"run_a": a, "run_b": b, "match": m, "rows": _kreuztest_rows(a, b, kinds, tol_kwargs)}
               for a, b, m in pairs]
    if _maybe_json(f, {"scope": scope, "pairs": results, "unmatched": unmatched}, "kreuztest"):
        return 0

    print(f"## Kreuz-Test {scope} — {label}{tol} ({len(pairs)} Paar(e))")
    for entry in results:
        suffix = f" ({entry['match']})" if entry["match"] else ""
        print(f"\n### run:{entry['run_a']} → run:{entry['run_b']}{suffix} — {len(entry['rows'])} Kombination(en)")
        if not entry["rows"]:
            print("- (keine markierten Results auf der A-Seite)")
            continue
        _print_kreuztest_table(entry["rows"])
    for line in unmatched:
        print(f"- OHNE PAAR: {line}")
    print()
    return 0


def combo_trace(args: list) -> int:
    """Eine Parameterkombination über eine Run-Menge verfolgen (1:N-Kreuz-Test).

    Flags: --params "key=wert,key2=wert2" + Selektor wie run-bestwerte
           (--run <id> | --strategy <slug> [--version <n>] | --iteration <id> |
            --testset-run <id>)   [--tolerance <t> | --tolerance-steps <N>] [--limit <n=200>] [--json]
    Schlägt die Kombination in jedem Run des Scopes nach (serverseitig über
    /api/backtest/results/lookup) und listet je Treffer Run-Kontext
    (Symbol/Timeframe) plus Kennzahlen. Runs ohne Treffer werden ausgewiesen.
    Im Schritt-Modus (--tolerance-steps) wird die Schrittweite je Run einzeln
    abgeleitet (Raster können differieren).
    """
    f = _parse_flags(args)
    wanted = _parse_params_flag(_require(f, "params", "combo-trace"))
    tkw = _tolerance_kwargs(f)
    runs, scope = _resolve_runs(f, "combo-trace")
    if not runs:
        print(f"## Kombinations-Verfolgung — {scope}\n- (keine Runs)\n")
        return 0
    run_ids = sorted(r["id"] for r in runs)

    qp = dict(wanted)
    qp["run_ids"] = ",".join(str(i) for i in run_ids)
    if "tolerance" in tkw:
        qp["tolerance"] = tkw["tolerance"]
    if "tolerance_steps" in tkw:
        qp["tolerance_steps"] = tkw["tolerance_steps"]
    qp["limit"] = f.get("limit", 200)
    d = fetch(f"/api/backtest/results/lookup?{urllib.parse.urlencode(qp)}")["data"]
    items = d.get("items") or []
    total = d.get("total") or 0
    if _maybe_json(f, {"scope": scope, "run_ids": run_ids, "total": total, "items": items}, "combo-trace"):
        return 0

    pstr = ", ".join(f"{k}={v}" for k, v in wanted.items())
    tol = _tolerance_label(f)
    print(f"## Kombinations-Verfolgung — {scope} ({len(run_ids)} Run(s)) — {pstr}{tol} ({total} Treffer)")
    hit_runs = set()
    for r in items:
        hit_runs.add(r["run_id"])
        print(f"- run:{r['run_id']} {r.get('symbol')} {r.get('timeframe')} — {_fmt_result_line(r)}")
    if total > len(items):
        print(f"- … {total - len(items)} weitere Treffer (--limit erhöhen)")
    missing = [i for i in run_ids if i not in hit_runs]
    if missing:
        print(f"- OHNE TREFFER: {', '.join(f'run:{i}' for i in missing)}")
    print()
    return 0


# ---------------------------------------------------------------------------
# Bestwerte (bestwerte). EIN Verb, das die kanonische 4er-Definition aus
# multiparameter-lauf.md ausführbar kapselt — damit sie nicht je Aufruf von Hand
# falsch zusammengesetzt wird — und die Gewinner als Doku-Favorit (roter Stern)
# markiert. Die Definitionswerte (Band 20% vom Höchstwert, PF-Floor 30 Trades) sind
# bewusst fest verdrahtet, NICHT parametrisierbar: das Verb IST die Definition.
# ---------------------------------------------------------------------------

# Feste Definitionswerte der vier Bestwerte (multiparameter-lauf.md Schritt 5).
# Oberes Band für Krit 2 (Win-Rate) und Krit 3 (Sharpe) — Anteil vom jeweiligen
# Höchstwert, innerhalb des Bands wird nach Total Return gekürt. Die beiden Bänder
# sind BEWUSST unterschiedlich breit: das Sharpe-Band ist mit 10 Prozent enger als
# das Win-Rate-Band (20 Prozent), damit der Sharpe-Band-Sieger seltener mit dem
# Max-Total-Return-Bestwert zusammenfällt (mehr distinkte Doku-Favoriten je Run).
_WINRATE_BAND_FRACTION = 0.20
_SHARPE_BAND_FRACTION = 0.10
_PF_MIN_TRADES = 30


def _dt_query(run_id: int, order_idx: int, *, win_rate_pct_min=None,
              sharpe_ratio_min=None, total_trades_min=None, length: int = 1,
              timeout: int = TIMEOUT) -> tuple:
    """Top-<length> Results eines Runs nach Spalte <order_idx> absteigend.

    Geteilte Low-Level-Abfrage über /api/backtest/results/dt für die vier
    Bestwerte (Spalten-Indizes in _DT_SORT_IDX). Optionale serverseitige Filter
    win_rate_pct_min / sharpe_ratio_min / total_trades_min. Gibt (rows, recordsFiltered) zurück.
    """
    params = {
        "run_id": run_id,
        "order[0][column]": order_idx, "order[0][dir]": "desc",
        "start": 0, "length": length, "draw": 1,
    }
    if win_rate_pct_min is not None:
        params["win_rate_pct_min"] = win_rate_pct_min
    if sharpe_ratio_min is not None:
        params["sharpe_ratio_min"] = sharpe_ratio_min
    if total_trades_min is not None:
        params["total_trades_min"] = total_trades_min
    dd = fetch(f"/api/backtest/results/dt?{urllib.parse.urlencode(params)}", timeout=timeout)
    return dd.get("data") or [], dd.get("recordsFiltered")


def _band_best_return(run_id: int, metric_key: str, filter_param: str, fraction: float) -> tuple:
    """Bestes Total Return im oberen <metric>-Band eines Runs als (result|None, info).

    Gemeinsame Mechanik für Krit 2 (Win-Rate-Band) und Krit 3 (Sharpe-Band): nimmt
    den Höchstwert der Metrik im Run, zieht den Bandanteil <fraction> vom Höchstwert
    ab und wählt aus allen Results im Band [max - fraction, max] das mit dem
    höchsten Total Return. So kann ein Low-Trade-Fluke (hoher Sharpe/100% Win-Rate
    bei 2 Trades) den Bestwert nicht mehr direkt kapern — im Band gewinnt der echte
    Return. Der Abzug nutzt abs(), damit das Band auch bei durchweg negativem
    Höchstwert (z.B. negativer Sharpe) korrekt unterhalb des Maximums liegt.
    """
    top_rows, _ = _dt_query(run_id, _DT_SORT_IDX[metric_key])
    if not top_rows or top_rows[0].get(metric_key) is None:
        return None, f"keine {_METRIC_LABEL[metric_key]}-Results"
    max_val = top_rows[0][metric_key]
    threshold = max_val - abs(max_val) * fraction
    band_rows, n_band = _dt_query(run_id, _DT_SORT_IDX["total_return_pct"],
                                  **{filter_param: threshold})
    info = f"Band {num(threshold)}..{num(max_val)} ({n_band} im Band)"
    return (band_rows[0] if band_rows else None), info


# Stabile Bestwert-Keys in kanonischer Reihenfolge — parallel zu den vier Einträgen von
# _bestwerte_for_run. Single Source des Klartext-Labels ist der Server
# (services/api/utils/best_criteria_labels.py); hier stehen NUR die Keys.
_BESTWERTE_KEYS = ["max_return", "winrate_band", "sharpe_band", "pf_min30"]


def _bestwerte_for_run(run_id: int) -> list:
    """Die vier kanonischen Bestwerte eines Runs als Liste (label, result|None, info).

    1) Max Total Return (kein Trade-Floor)
    2) Bestes Total Return im oberen Win-Rate-Band (höchste Win-Rate minus 20% vom Höchstwert)
    3) Bestes Total Return im oberen Sharpe-Band (höchster Sharpe minus 10% vom Höchstwert)
    4) Max Profitfaktor mit mindestens 30 Trades
    """
    out = []
    # 1) Max Total Return
    rows, _ = _dt_query(run_id, _DT_SORT_IDX["total_return_pct"])
    out.append(("Max Total Return", rows[0] if rows else None, ""))
    # 2) Win-Rate-Band -> bestes Total Return (Band 20%)
    res2, info2 = _band_best_return(run_id, "win_rate_pct", "win_rate_pct_min", _WINRATE_BAND_FRACTION)
    out.append(("Bestes Return im Win-Rate-Band", res2, info2))
    # 3) Sharpe-Band -> bestes Total Return (Band 10% — enger als Win-Rate)
    res3, info3 = _band_best_return(run_id, "sharpe_ratio", "sharpe_ratio_min", _SHARPE_BAND_FRACTION)
    out.append(("Bestes Return im Sharpe-Band", res3, info3))
    # 4) Max Profitfaktor mit >= 30 Trades
    rows, n = _dt_query(run_id, _DT_SORT_IDX["profit_factor"], total_trades_min=_PF_MIN_TRADES)
    out.append((f"Max Profitfaktor (>= {_PF_MIN_TRADES} Trades)",
                rows[0] if rows else None, f"{n} mit >= {_PF_MIN_TRADES} Trades"))
    return out


def _fmt_result_line(r: dict) -> str:
    """Eine Result-Zeile mit Kennzahlen + actual_params (gleiches Format wie run-best)."""
    params = r.get("actual_params") or {}
    pstr = ", ".join(f"{k}={v}" for k, v in params.items()) if isinstance(params, dict) else ""
    line = (f"result:{r['id']} — Ret {num(r.get('total_return_pct'))}% / WinR {num(r.get('win_rate_pct'))}% / "
            f"Sharpe {num(r.get('sharpe_ratio'))} / DD {num(r.get('max_drawdown_pct'))}% / "
            f"PF {num(r.get('profit_factor'))} / {trades_str(r)} Trades")
    # GEAENDERT: ToDo 10 — gewonnene Bestwert-Kriterien anhaengen. Der Server liefert
    # Badge-Objekte {short, long}; fuer die Text-Ausgabe die Langform verwenden.
    crit = r.get("best_criteria") or []
    labels = [c.get("long") if isinstance(c, dict) else c for c in crit]
    crit_str = f"  ·  Bestwert: {', '.join(labels)}" if labels else ""
    return line + (f"  ·  {pstr}" if pstr else "") + crit_str


def _resolve_runs(f: dict, verb: str) -> tuple:
    """Loest die Run-Auswahl aus den Selektor-Flags auf -> (runs, scope).

    Geteilt von run-bestwerte und run-favorites-reset. Genau ein Selektor:
    --run <id> | --strategy <slug> [--version <n>] | --iteration <id> | --testset-run <id>.
    Liefert die Run-Dicts (wie /api/backtest/runs) und einen lesbaren Scope-String.
    """
    if f.get("run"):
        return [{"id": int(f["run"])}], f"run:{f['run']}"
    params: dict = {"limit": f.get("limit", 10000)}
    if f.get("strategy"):
        params["strategy"] = f["strategy"]
    if f.get("version"):
        params["version"] = f["version"]
    if f.get("iteration"):
        params["iteration_id"] = f["iteration"]
    if f.get("testset-run"):
        params["testset_run_id"] = f["testset-run"]
    if len(params) == 1:
        raise ValueError(f"{verb} braucht einen Selektor: --run | --strategy [--version] | --iteration | --testset-run")
    runs = fetch(f"/api/backtest/runs?{urllib.parse.urlencode(params)}")["data"]["items"]
    sc = []
    if f.get("strategy"):
        sc.append(str(f["strategy"]).upper() + (f" v{f['version']}" if f.get("version") else ""))
    if f.get("iteration"):
        sc.append(f"iteration:{f['iteration']}")
    if f.get("testset-run"):
        sc.append(f"testset-run:{f['testset-run']}")
    return runs, (" · ".join(sc) if sc else "alle")


def run_bestwerte(args: list) -> int:
    """Vier feste Bestwerte je Run ziehen UND als Doku-Favorit (roter Stern) markieren.

    Flags: --run <id> | --strategy <slug> [--version <n>] | --iteration <id> | --testset-run <id> [--limit <n>]
    Kapselt die kanonische 4er-Definition aus multiparameter-lauf.md (max Total
    Return · bestes Return im oberen Win-Rate-Band [Max-WinR - 20% vom Höchstwert] · bestes
    Return im oberen Sharpe-Band [Max-Sharpe - 10% vom Höchstwert] · max Profitfaktor mit
    >= 30 Trades), damit sie nicht von Hand falsch
    zusammengesetzt werden kann. Mehrere Runs über die gleiche Auflösung wie
    run-list (Strategie+Version / Iteration / TestSet-Lauf).

    Markiert idempotent: Ein Gewinner-Result, das den roten Stern schon trägt
    (oder ihn in diesem Lauf als Mehrfach-Sieger bereits bekommen hat), wird NICHT
    erneut getoggelt — der doc_favorite-Endpunkt ist ein Toggle.
    """
    f = _parse_flags(args)
    runs, scope = _resolve_runs(f, "run-bestwerte")

    print(f"## Bestwerte — {scope} ({len(runs)} Run(s)) — vier feste Kriterien, rote Doku-Favoriten")
    if not runs:
        print("- (keine Runs)\n")
        return 0

    now_on: set = set()   # Result-IDs, die nach diesem Lauf den roten Stern tragen
    newly: set = set()    # davon: in diesem Lauf neu gesetzt
    for run in sorted(runs, key=lambda x: x["id"]):
        rid = run["id"]
        meta = []
        if run.get("symbol"):
            meta.append(f"{run['symbol']} {run.get('timeframe', '')}".strip())
        if run.get("testset_name"):
            tn = run["testset_name"]
            if run.get("testset_run_id"):
                tn += f" (testset-run:{run['testset_run_id']})"
            meta.append(tn)
        print(f"\n### run:{rid}{(' · ' + ' · '.join(meta)) if meta else ''}")
        # GEAENDERT: ToDo 10 — pro Sieger-Result die gewonnenen Kriterium-Keys sammeln
        # (ein Result kann mehrere Kriterien gleichzeitig gewinnen) und den roten Stern
        # samt Keys idempotent ueber den mark-Endpunkt setzen (kein Toggle, ueberschreibt
        # die Keys auch bei bereits gesetztem Stern).
        run_keys: dict = {}       # res_id -> [keys] (geordnet, dedup)
        was_starred: dict = {}    # res_id -> war vor diesem Lauf schon roter Favorit?
        for idx, (label, res, info) in enumerate(_bestwerte_for_run(rid)):
            suffix = f" — {info}" if info else ""
            if not res:
                print(f"- **{label}**{suffix}: kein Result")
                continue
            print(f"- **{label}**{suffix}")
            print(f"  - {_fmt_result_line(res)}")
            res_id = res["id"]
            key = _BESTWERTE_KEYS[idx]
            keys = run_keys.setdefault(res_id, [])
            if key not in keys:
                keys.append(key)
            was_starred[res_id] = bool(res.get("is_doc_favorite"))
        # Markieren: pro Result einmal, mit allen gewonnenen Keys
        for res_id, keys in run_keys.items():
            post(f"/api/backtest/results/{res_id}/doc_favorite/mark", {"criteria": keys})
            now_on.add(res_id)
            if not was_starred.get(res_id):
                newly.add(res_id)
            state = "gesetzt" if not was_starred.get(res_id) else "aktualisiert"
            print(f"- result:{res_id} — roter Stern {state} (Kriterien: {', '.join(keys)})")

    already = len(now_on) - len(newly)
    print(f"\n**{len(now_on)} Results sind rote Doku-Favoriten** — {len(newly)} neu gesetzt, {already} bereits zuvor markiert.")
    if newly:
        print(f"Neu: {', '.join(f'result:{i}' for i in sorted(newly))}")
    print()
    return 0


# Favoriten-Reset. Raeumt die Favoriten einer ganzen Run-Menge ab: roter Doku-Stern
# (is_doc_favorite) UND/ODER gelber User-Stern (is_favorite). Beide Endpunkte sind
# Toggles -> erst markierte Results auslesen, dann gezielt zuruecktoggeln (kein
# Blind-Toggle, der ungesetzte Sterne anschalten wuerde).
_FAV_KINDS = {
    # flag -> (dt-Spaltenindex [Favoriten sortieren zuerst], Result-Feld, Endpunkt-Suffix, Label)
    "doc": (2, "is_doc_favorite", "doc_favorite", "roter Stern (Doku)"),
    "user": (1, "is_favorite", "favorite", "gelber Stern (User)"),
}


def run_favorites_reset(args: list) -> int:
    """Favoriten einer Run-Menge zuruecksetzen (roter Doku-Stern und/oder gelber User-Stern).

    Flags: --run <id> | --strategy <slug> [--version <n>] | --iteration <id> | --testset-run <id>
           [--doc] [--user]
    Ohne --doc/--user werden BEIDE Favoriten-Arten abgeraeumt ("ganzer Run reset").
    Mit genau einem der beiden Flags nur diese Art. Run-Aufloesung identisch zu run-bestwerte.

    Liest je Run die aktuell markierten Results aus (dt-Endpunkt, Favoriten zuerst
    sortiert) und toggelt jeden gesetzten Stern einzeln aus. Idempotent: ein bereits
    sternloses Result wird nicht angefasst.
    """
    f = _parse_flags(args)
    kinds = [k for k in ("doc", "user") if f.get(k)] or ["doc", "user"]
    runs, scope = _resolve_runs(f, "run-favorites-reset")

    kind_labels = ", ".join(_FAV_KINDS[k][3] for k in kinds)
    print(f"## Favoriten-Reset — {scope} ({len(runs)} Run(s)) — {kind_labels}")
    if not runs:
        print("- (keine Runs)\n")
        return 0

    removed_total = 0
    for run in sorted(runs, key=lambda x: x["id"]):
        rid = run["id"]
        for kind in kinds:
            col_idx, field, suffix, label = _FAV_KINDS[kind]
            # Favoriten sortieren zuerst -> length deckt jede realistische Favoriten-Zahl je Run ab
            rows, _ = _dt_query(rid, col_idx, length=200)
            marked = [r["id"] for r in rows if r.get(field)]
            for res_id in marked:
                post(f"/api/backtest/results/{res_id}/{suffix}")   # Toggle aus
            removed_total += len(marked)
            ids = ", ".join(f"result:{i}" for i in marked) if marked else "—"
            print(f"- run:{rid} · {label}: {len(marked)} entfernt ({ids})")

    print(f"\n**{removed_total} Favoriten-Markierungen entfernt.**\n")
    return 0


def run_favorites_list(args: list) -> int:
    """Aktuell markierte Favoriten-Results einer Run-Menge ausgeben (reiner Read).

    Flags wie run-favorites-reset: --run <id> | --strategy <slug> [--version <n>] |
           --iteration <id> | --testset-run <id>   [--doc] [--user]
    Ohne --doc/--user werden BEIDE Favoriten-Arten gelistet. Nutzt denselben
    dt-Abruf wie der Reset (Favoriten zuerst sortiert), ändert aber nichts.
    """
    f = _parse_flags(args)
    kinds = [k for k in ("doc", "user") if f.get(k)] or ["doc", "user"]
    runs, scope = _resolve_runs(f, "run-favorites-list")

    # Erst einsammeln (auch für --json), dann ausgeben.
    collected: list = []
    for run in sorted(runs, key=lambda x: x["id"]):
        rid = run["id"]
        for kind in kinds:
            col_idx, field, _suffix, label = _FAV_KINDS[kind]
            # Favoriten sortieren zuerst -> length deckt jede realistische Favoriten-Zahl je Run ab
            rows, _ = _dt_query(rid, col_idx, length=200)
            marked = [r for r in rows if r.get(field)]
            collected.append({"run_id": rid, "kind": kind, "label": label, "results": marked})
    if _maybe_json(f, {"scope": scope, "groups": collected}, "run-favorites-list"):
        return 0

    kind_labels = ", ".join(_FAV_KINDS[k][3] for k in kinds)
    print(f"## Favoriten — {scope} ({len(runs)} Run(s)) — {kind_labels}")
    if not runs:
        print("- (keine Runs)\n")
        return 0

    found_total = 0
    for group in collected:
        found_total += len(group["results"])
        print(f"- run:{group['run_id']} · {group['label']}: {len(group['results'])}")
        for r in group["results"]:
            print(f"  - {_fmt_result_line(r)}")

    print(f"\n**{found_total} Favoriten-Markierungen gefunden.**\n")
    return 0


# GEÄNDERT: Favoriten-Verben setzend statt umschaltend. Vorher liefen
# result-doc-favorite/iteration-doc-favorite/result-favorite/iteration-favorite ueber
# TABLE_VERBS direkt auf die Toggle-Routen (POST .../favorite bzw. .../doc_favorite) —
# ein zweiter Aufruf auf ein bereits markiertes Objekt hat den Stern wieder entfernt
# In der Praxis wurden dadurch bereits gesetzte Doku-Favoriten durch einen
# Wiederholungsaufruf versehentlich geloescht.
# Jetzt idempotent ueber eigene mark/unmark-Routen; --off steuert das gezielte, ebenso
# idempotente Entfernen. Der manuelle Frontend-Stern bleibt der reine Toggle.
# verb -> (mark_pfad, unmark_pfad, feld, label, unterstuetzt_criteria)
_FAVORITE_VERBS = {
    "result-doc-favorite": ("/api/backtest/results/{}/doc_favorite/mark",
                             "/api/backtest/results/{}/doc_favorite/unmark",
                             "is_doc_favorite", "roter Stern (Doku)", True),
    "result-favorite": ("/api/backtest/results/{}/favorite/mark",
                         "/api/backtest/results/{}/favorite/unmark",
                         "is_favorite", "gelber Stern (User)", False),
    "iteration-doc-favorite": ("/api/strategy/iterations/{}/doc_favorite/mark",
                                "/api/strategy/iterations/{}/doc_favorite/unmark",
                                "is_doc_favorite", "roter Stern (Doku)", False),
    "iteration-favorite": ("/api/strategy/iterations/{}/favorite/mark",
                            "/api/strategy/iterations/{}/favorite/unmark",
                            "is_favorite", "gelber Stern (User)", False),
}


def _favorite_set(verb: str, args: list) -> int:
    """Setzt (Default) oder entfernt (--off) einen Favoriten-Stern idempotent.

    <id> [--off] [--criteria k1,k2 (nur result-doc-favorite, optional)]
    Kein Toggle mehr: ein zweiter Aufruf ohne --off laesst den Stern gesetzt, ein
    zweiter Aufruf mit --off laesst ihn aus. Die Ausgabe nennt die tatsaechliche
    Aenderung ("war aus -> jetzt gesetzt" / "bereits gesetzt, keine Aenderung").
    """
    mark_path, unmark_path, field, label, supports_criteria = _FAVORITE_VERBS[verb]
    f = _parse_flags(args)
    pos = f.get("_positional", [])
    oid = f.get("id")
    if oid is None and pos:
        oid = pos[0]
    if oid is None:
        raise ValueError(f"{verb}: ID fehlt (--id <n> oder als erstes Argument)")
    oid = int(oid)
    off = bool(f.get("off"))

    if off:
        if f.get("criteria"):
            raise ValueError(f"{verb}: --criteria nur ohne --off sinnvoll (beim Entfernen werden Kriterien ohnehin geleert)")
        resp = request("POST", unmark_path.format(oid), None)
    else:
        body = None
        if supports_criteria and f.get("criteria"):
            keys = [k.strip() for k in str(f["criteria"]).split(",") if k.strip()]
            body = {"criteria": keys}
        resp = post(mark_path.format(oid), body)

    data = resp.get("data", resp) if isinstance(resp, dict) else resp
    changed = bool(data.get("changed"))
    if off:
        change_text = "war gesetzt -> jetzt aus" if changed else "bereits aus, keine Aenderung"
    else:
        change_text = "war aus -> jetzt gesetzt" if changed else "bereits gesetzt, keine Aenderung"
    extra = ""
    if supports_criteria and not off and data.get("best_criteria"):
        extra = f" (Kriterien: {', '.join(data['best_criteria'])})"
    print(f"## {verb}: OK — {label} bei id {oid}: {change_text}{extra}\n")
    return 0


def result_doc_favorite_set(args: list) -> int:
    return _favorite_set("result-doc-favorite", args)


def result_favorite_set(args: list) -> int:
    return _favorite_set("result-favorite", args)


def iteration_doc_favorite_set(args: list) -> int:
    return _favorite_set("iteration-doc-favorite", args)


def iteration_favorite_set(args: list) -> int:
    return _favorite_set("iteration-favorite", args)


def vergleichstabelle(args: list) -> int:
    """Iterations-Vergleichstabelle aus roten Doku-Favoriten (nur Testset-Läufe).

    Flags: --strategy <slug> [--save <pfad>] [--json]
    Je Testset ein Abschnitt; Zeilen = Symbol × Iteration, Spalten = Spitze
    (Bestwert „Max Total Return") und robuster Kern (Bestwert „Profitfaktor
    >= 30 Trades") — dasselbe Format wie die Benchmark-Tabellen in status.md.
    Quelle sind ausschließlich rote Doku-Favoriten mit gespeicherten
    Bestwert-Kriterien (best_criteria); die Tabelle funktioniert daher auch für
    Runs, deren volle Result-Sätze bereits gelöscht wurden. Einzel-Läufe ohne
    Testset bleiben bewusst außen vor. --save schreibt zusätzlich eine
    eigenständige Markdown-Notiz (mit Frontmatter) an den angegebenen Pfad.
    """
    f = _parse_flags(args)
    if not f.get("strategy") or f.get("strategy") is True:
        raise ValueError("vergleichstabelle braucht --strategy <slug> (z.B. --strategy teststrategie)")
    slug = str(f["strategy"])
    runs, _scope = _resolve_runs({"strategy": slug, "limit": f.get("limit", 10000)}, "vergleichstabelle")
    ts_runs = [r for r in runs if r.get("testset_run_id")]

    # Je Run die zwei Tabellen-Bestwerte aus den roten Doku-Favoriten ziehen.
    # Kürzel-Katalog ist Single Source am Server (best_criteria_labels.py):
    # T = Max Total Return (Spitze), P = Profitfaktor >= 30 Trades (Kern).
    def _fav_by_short(marked: list, letter: str):
        for r in marked:
            for c in (r.get("best_criteria") or []):
                if isinstance(c, dict) and c.get("short") == letter:
                    return r
        return None

    def _version_num(run: dict) -> int:
        try:
            return int(run.get("strategy_name"))
        except (TypeError, ValueError):
            return 0

    def _metric(result: dict, key: str) -> float:
        """Metrik als Zahl; fehlende/ungueltige Werte verlieren jeden Vergleich."""
        try:
            return float(result.get(key))
        except (TypeError, ValueError):
            return float("-inf")

    # GEAENDERT: Zelle = Symbol x Iteration, NICHT mehr eine Zeile je Run.
    # Eine Iteration kann mehrere Runs je Symbol+Testset haben, wenn eine
    # Sweep-Achse auf Laeufe verteilt werden musste (VWMA v8: 17 Runs, einer je
    # k-Stufe, weil k nicht als Sweep-Achse laeuft). Frueher ergab das 17
    # identisch mit "v8" beschriftete Zeilen. Jetzt wird die Zelle ueber alle
    # Runs zur Decke zusammengefasst: beste Spitze (max Total Return) und bester
    # Kern (max Profitfaktor) — genau das, was "Spitze/Kern dieser Iteration in
    # dieser Zelle" bedeutet.
    groups: dict = {}
    missing: list = []
    for run in sorted(ts_runs, key=lambda x: x["id"]):
        # Doku-Favoriten zuerst; 60s-Timeout, weil die Favoriten-Sortierung auf
        # Runs mit sechsstelligen Result-Zahlen (z.B. 371k) über 10s dauern kann.
        rows, _n = _dt_query(run["id"], _FAV_KINDS["doc"][0], length=200, timeout=60)
        marked = [r for r in rows if r.get(_FAV_KINDS["doc"][1])]
        spitze, kern = _fav_by_short(marked, "T"), _fav_by_short(marked, "P")
        if spitze is None and kern is None:
            missing.append(run["id"])
        key = run.get("testset_name") or f"testset-run:{run['testset_run_id']}"
        cells = groups.setdefault(key, {})
        cell_key = (run["symbol"], _version_num(run))
        cell = cells.get(cell_key)
        if cell is None:
            cells[cell_key] = {"run": run, "spitze": spitze, "kern": kern, "runs": 1}
            continue
        cell["runs"] += 1
        if spitze is not None and (cell["spitze"] is None or _metric(spitze, "total_return_pct")
                                   > _metric(cell["spitze"], "total_return_pct")):
            cell["spitze"] = spitze
        if kern is not None and (cell["kern"] is None or _metric(kern, "profit_factor")
                                 > _metric(cell["kern"], "profit_factor")):
            cell["kern"] = kern

    if _maybe_json(f, {"strategy": slug,
                       "groups": {ts: list(cells.values()) for ts, cells in groups.items()},
                       "runs_ohne_bestwerte": missing}, "vergleichstabelle"):
        return 0

    def _cell_spitze(r) -> str:
        if not r:
            return "—"
        return (f"{num(r.get('total_return_pct'), '{:.0f}')} % · Sharpe {num(r.get('sharpe_ratio'))} · "
                f"DD {num(r.get('max_drawdown_pct'), '{:.0f}')} % · result:{r['id']}")

    def _cell_kern(r) -> str:
        if not r:
            return "—"
        return (f"{num(r.get('total_return_pct'), '{:.0f}')} % · PF {num(r.get('profit_factor'))} · "
                f"WinR {num(r.get('win_rate_pct'), '{:.0f}')} % · {trades_str(r)} Tr · "
                f"DD {num(r.get('max_drawdown_pct'), '{:.0f}')} % · result:{r['id']}")

    lines = [f"## Iterations-Vergleich — {slug.upper()} (nur Testset-Läufe, aus roten Doku-Favoriten)", ""]
    if not ts_runs:
        lines.append("- (keine Testset-Läufe gefunden)")
        lines.append("")
    aggregiert = False
    for ts_name in sorted(groups):
        entries = sorted(groups[ts_name].values(), key=lambda e: (e["run"]["symbol"], _version_num(e["run"])))
        lines.append(f"### {ts_name}")
        lines.append("")
        lines.append("| Symbol | Iteration | Spitze (Max Total Return) | Robuster Kern (PF ≥ 30 Trades) |")
        lines.append("|---|---|---|---|")
        for e in entries:
            run = e["run"]
            label = f"v{run.get('strategy_name')}"
            if e["runs"] > 1:
                aggregiert = True
                label += f" ({e['runs']} Läufe)"
            lines.append(f"| {run['symbol']} | {label} "
                         f"| {_cell_spitze(e['spitze'])} | {_cell_kern(e['kern'])} |")
        lines.append("")
    if aggregiert:
        lines.append("> Zellen mit „(N Läufe)“: Die Iteration hat mehrere Runs je Symbol+Testset, weil eine "
                     "Sweep-Achse auf Läufe verteilt werden musste. Spitze und Kern sind die **Decke über "
                     "alle diese Läufe** — also über die gesamte verteilte Achse, nicht über einen einzelnen Lauf.")
        lines.append("")
    if missing:
        lines.append("> Läufe ohne markierte Bestwerte (erst `run-bestwerte` laufen lassen): "
                     + ", ".join(f"run:{i}" for i in sorted(missing)))
        lines.append("")

    out = "\n".join(lines)
    print(out)

    if f.get("save") and f.get("save") is not True:
        header = (
            "---\n"
            "type: strategy-vergleich\n"
            f"strategy: {slug}\n"
            f"updated: {datetime.date.today().isoformat()}\n"
            "---\n\n"
            f"# {slug.upper()} — Iterations-Vergleich\n\n"
            f"> Generiert mit `toolbox.py vergleichstabelle --strategy {slug} --save <pfad>` aus den roten "
            "Doku-Favoriten (purge-fest). Nicht von Hand editieren — nach neuen Testset-Läufen "
            "(und `run-bestwerte`) neu generieren.\n\n"
        )
        with open(f["save"], "w", encoding="utf-8") as fh:
            fh.write(header + out + "\n")
        print(f"Gespeichert: {f['save']}\n")
    return 0


# ---------------------------------------------------------------------------
# Anlegen (create). Erzeugen jeweils ein neues Objekt per POST. Komplexe
# Payloads (spec_json, config_json, volle Backtest-Config) per --file als
# JSON-Datei. KEIN stiller Konverter, kein Fallback: das spec_json/config_json
# wird unverändert durchgereicht und scheitert beim Lauf laut, wenn falsch
# geformt. Funktionsname: <bereich>_create.
# ---------------------------------------------------------------------------

def concept_create(args: list) -> int:
    f = _parse_flags(args)
    body = {"slug": _require(f, "slug", "concept-create"), "name": _require(f, "name", "concept-create")}
    for key in ("category", "description", "status"):
        if f.get(key):
            body[key] = f[key]
    # GEÄNDERT: --goal (JSON, Datei oder Inline) und --goal-prompt (Text, Datei oder Inline)
    if f.get("goal"):
        body["goal_json"] = json.loads(_read_file_or_inline(f["goal"]))
    if f.get("goal-prompt"):
        body["goal_prompt"] = _read_file_or_inline(f["goal-prompt"])
    d = post("/api/strategy/concepts", body)["data"]
    print(f"## Erstellt: Concept **{d['id']}** ({d.get('name')}, {d.get('slug')})\n")
    return 0


def iteration_create(args: list) -> int:
    f = _parse_flags(args)
    concept_id = int(_require(f, "concept", "iteration-create"))
    spec = _read_json_file(_require(f, "file", "iteration-create"))
    body = {"concept_id": concept_id, "spec_json": spec, "type": f.get("type", "generic")}
    if f.get("name"):
        body["version_name"] = f["name"]
    if f.get("import-path"):
        body["import_path"] = f["import-path"]
    if f.get("parent"):
        body["parent_iteration_id"] = int(f["parent"])
    if f.get("description"):
        body["description"] = f["description"]
    d = post("/api/strategy/iterations", body)["data"]
    nm = d.get("version_name") or ""
    print(f"## Erstellt: Iteration **{d['id']}** (v{d.get('version')} {nm}, Concept {d.get('concept_id')})\n")
    return 0


def iteration_log_add(args: list) -> int:
    """Log-Eintrag an einer Iteration anlegen (append-only)."""
    f = _parse_flags(args)
    iid = int(_require(f, "id", "iteration-log-add"))
    log_text = _require(f, "text", "iteration-log-add")
    body = {"text": log_text}
    if f.get("run"):
        body["run_id"] = int(f["run"])
    d = post(f"/api/strategy/iterations/{iid}/logs", body)["data"]
    print(f"## Log-Eintrag {d['id']} an Iteration {iid}\n")
    return 0


def iteration_log_list(args: list) -> int:
    """Log-Einträge einer Iteration chronologisch auflisten."""
    f = _parse_flags(args)
    iid = int(_require(f, "id", "iteration-log-list"))
    items = fetch(f"/api/strategy/iterations/{iid}/logs")["data"]["items"]
    if _maybe_json(f, {"total": len(items), "items": items}, "iteration-log-list"):
        return 0
    print(f"## Log-Einträge Iteration {iid} ({len(items)})")
    for e in items:
        run_part = f" · run:{e['run_id']}" if e.get("run_id") else ""
        print(f"- [{e.get('created_at')}]{run_part} {e.get('text')}")
    print()
    return 0


def _print_befund(d: dict) -> None:
    """Druckt einen Befund vollständig als Markdown.

    Kontext + Soll, dann die fünf Ist-Gruppen (falls der Befund schon geschlossen
    ist), zuletzt die Deutung — ausdrücklich als Interpretation gekennzeichnet und
    getrennt von den Zahlen. Leere Felder werden mit ihrem hinterlegten Grund
    ausgegeben, nie mit 0 und nie weggelassen. Keine Sortierung, kein Verdict.
    """
    print(f"## Befund {d['id']} — Iteration {d['iteration_id']} / Testset {d['testset_id']}")
    tsr = d.get("testset_run_id")
    print(
        f"- Kontext: TestSetRun {tsr if tsr is not None else '(gelöscht — Befund bleibt erhalten)'} · "
        f"IndicatorConfig {d.get('indicator_config_id') or '—'} · "
        f"Spec-Runner {d.get('spec_runner_version') or '—'}"
    )
    print(
        f"- Angelegt: {d.get('created_at')} · "
        f"Geschlossen: {d.get('closed_at') or 'noch offen (Lauf läuft/wartet)'}"
    )

    print("\n### Soll")
    goal = d.get("goal_snapshot_json")
    if goal:
        print(f"- Ziel (Schnappschuss aus goal_json): {json.dumps(goal, ensure_ascii=False)}")
    else:
        print(f"- Ziel: leer — {d.get('goal_missing_reason') or 'kein Grund hinterlegt'}")
    print(f"- Bestwert-Kriterien: {', '.join(d.get('best_criteria_json') or [])}")
    combos = d.get("planned_combos_per_run")
    if combos is not None:
        print(
            f"- Geplante Rastergröße: {d.get('planned_n_runs')} Runs × {combos} = "
            f"{d.get('planned_combos_total')} Kombinationen"
        )
    else:
        print(f"- Geplante Rastergröße: leer — {d.get('planned_grid_reason') or 'kein Grund hinterlegt'}")

    if d.get("closed_at") is None:
        print("\n### Ist — noch nicht vorhanden (Lauf noch nicht abgeschlossen)")
    else:
        scope = d.get("scope_json") or {}
        print("\n### Ist — Umfang der Suche")
        print(
            f"- Runs: {scope.get('n_runs')} ({scope.get('n_runs_completed')} completed) · "
            f"Symbole: {', '.join(scope.get('symbols') or [])} · "
            f"Kombinationen gesamt: {scope.get('combos_total')}"
        )
        n_eff = scope.get("n_eff")
        print(f"- N_eff: {n_eff if n_eff is not None else 'leer — ' + str(scope.get('n_eff_reason'))}")
        # GEÄNDERT: Sondierungs-Zähler des Konzepts neben der Rastergröße.
        # Reiner Ausweis: nicht in combos_total enthalten, nicht in N/DSR verrechnet.
        # Ältere Befunde tragen das Feld nicht — dann bleibt die Zeile weg (kein
        # Rückwirken, keine erfundene 0).
        if "probe_count" in scope:
            probe = scope.get("probe_count")
            probe_txt = (
                f"{probe} (nicht in den Kombinationen enthalten, nicht in N/DSR verrechnet)"
                if probe is not None else f"leer — {scope.get('probe_count_reason')}"
            )
            print(f"- Lite-Sondierungen des Konzepts: {probe_txt}")
        for run in scope.get("runs") or []:
            skipped = run.get("metric_groups_skipped") or []
            skip_note = f" · übersprungene Metrik-Gruppen: {', '.join(skipped)}" if skipped else ""
            print(
                f"  - run:{run['run_id']} {run['symbol']} {run['timeframe']} · "
                f"n_combinations={run['n_combinations']} · n_results={run['n_results']}{skip_note}"
            )

        print("\n### Ist — Kandidaten (mehrere nebeneinander, kein Gesamtsieger)")
        candidates = d.get("candidates_json") or {}
        for entry in candidates.get("per_run") or []:
            print(f"- run:{entry['run_id']} ({entry['symbol']})")
            for key, c in (entry.get("criteria") or {}).items():
                winner = c.get("winner")
                if winner is None:
                    print(f"  - {key}: kein Sieger — {c.get('reason')}")
                    continue
                m = winner["metrics"]
                missing_note = (
                    f" · leer mit Grund: {winner['metrics_missing_reason']}"
                    if winner.get("metrics_missing_reason") else ""
                )
                print(
                    f"  - {key}: result:{winner['result_id']} · "
                    f"Return {num(m.get('total_return_pct'))}% · Sharpe {num(m.get('sharpe_ratio'))} · "
                    f"PF {num(m.get('profit_factor'))} · WinRate {num(m.get('win_rate_pct'))}% · "
                    f"Trades {m.get('total_trades')} · MaxDD {num(m.get('max_drawdown_pct'))}%{missing_note}"
                )

        print("\n### Ist — Robustheit (DSR nie ohne N und SR0)")
        robustness = d.get("robustness_json") or {}
        for block in robustness.get("dsr") or []:
            best = block.get("best")
            best_txt = (
                f"DSR {best['deflated_sharpe_ratio']:.4f} (result:{best['result_id']})"
                if best else f"leer — {block.get('best_reason')}"
            )
            print(
                f"- run:{block['run_id']} ({block.get('symbol')}): N={block['n']} · "
                f"SR0={num(block.get('sr0'), '{:.4f}')} · bester {best_txt}"
            )
        for entry in robustness.get("plateau") or []:
            for nb in entry.get("neighborhoods") or []:
                if nb.get("summary"):
                    s = nb["summary"]
                    print(
                        f"  - Plateau run:{entry['run_id']} {nb['criterion']}: n={s.get('n')} · "
                        f"Median Return {num(s.get('return_median'))}% · "
                        f"Anteil profitabel {num(s.get('anteil_profitabel_pct'), '{:.1f}')}%"
                    )
                else:
                    print(f"  - Plateau run:{entry['run_id']} {nb['criterion']}: leer — {nb.get('reason')}")
        disp = robustness.get("symbol_dispersion") or {}
        n_eff2 = disp.get("n_eff")
        spitzen_spanne = (disp.get("spitzen_total_return_pct") or {}).get("spanne")
        print(
            f"- Streuung über Symbole: Spitzen-Spanne {num(spitzen_spanne)}% · "
            f"N_eff: {n_eff2 if n_eff2 is not None else 'leer — ' + str(disp.get('n_eff_reason'))}"
        )

        print("\n### Ist — Vergleichsanker")
        bm = d.get("benchmarks_json") or {}
        for bh in bm.get("buy_and_hold") or []:
            if bh.get("buy_and_hold_return_pct") is not None:
                print(
                    f"- run:{bh['run_id']} Buy&Hold {num(bh['buy_and_hold_return_pct'])}% · "
                    f"bestes Ist {num(bh.get('best_total_return_pct'))}% · "
                    f"Differenz {num(bh.get('differenz_pct'))}pp"
                )
            else:
                print(f"- run:{bh['run_id']} Buy&Hold: leer — {bh.get('buy_and_hold_reason')}")
        cbl = bm.get("concept_benchmark_line")
        print(
            f"- Benchmark-Linie des Konzepts: "
            f"{cbl if cbl is not None else 'leer — ' + str(bm.get('concept_benchmark_line_reason'))}"
        )
        goal_cmp = bm.get("goal") or {}
        if goal_cmp.get("soll"):
            print(f"- Ist gegen Soll: {json.dumps(goal_cmp['soll'], ensure_ascii=False)}")
        else:
            print(f"- Ist gegen Soll: leer — {goal_cmp.get('soll_reason')}")
        if goal_cmp.get("hinweis"):
            print(f"  {goal_cmp['hinweis']}")

        print("\n### Ist — Warnhinweise")
        warn = d.get("warnings_json") or {}
        items = warn.get("items") or []
        if items:
            for it in items:
                print(f"- {it.get('text')}")
        else:
            print("- keine Warnhinweise")
        for ne in warn.get("not_evaluated") or []:
            print(f"- ungeprüft ({ne['code']}): {ne['reason']}")

    print("\n### Deutung (Interpretation — Freitext, getrennt von den Zahlen)")
    interp = d.get("interpretation") or {}
    if interp.get("text"):
        print(f"- {interp['text']} (Stand: {interp.get('interpreted_at')})")
    else:
        print("- keine Deutung hinterlegt")
    print()


def befund_read(args: list) -> int:
    """Befund eines Testset-Laufs: ein Befund per --id, jüngster Befund
    eines Testset-Laufs per --testset-run, Historie per --iteration.

    --id ist die Befund-ID (NICHT die Testset-Lauf-Nummer, die testset-run-start
    zurückgibt) — der direkte Anschluss an testset-run-start/run-wait ist
    --testset-run. --id und --testset-run schließen sich aus. Keine Sortier-/
    Filter-Option, kein Verdict (Anforderung 7): die Historie ist ausnahmslos
    chronologisch.
    """
    f = _parse_flags(args)
    if f.get("id") and f.get("testset-run"):
        raise ValueError("befund: --id und --testset-run schließen sich aus")
    if f.get("id"):
        d = fetch(f"/api/testset-run-findings/{int(f['id'])}")["data"]
        if _maybe_json(f, d, "befund"):
            return 0
        _print_befund(d)
        return 0
    if f.get("testset-run"):
        d = fetch(f"/api/testset-run-findings/by-testset-run/{int(f['testset-run'])}")["data"]
        if _maybe_json(f, d, "befund"):
            return 0
        print(f"## Befund zu testset-run:{f['testset-run']} — jüngster von "
              f"{d['total_for_testset_run']} Befund(en) dieses Testset-Laufs\n")
        _print_befund(d["finding"])
        return 0
    if f.get("iteration"):
        items = fetch(f"/api/testset-run-findings/by-iteration/{int(f['iteration'])}")["data"]["items"]
        if _maybe_json(f, {"total": len(items), "items": items}, "befund"):
            return 0
        print(f"## Befund-Historie Iteration {f['iteration']} ({len(items)}, chronologisch)\n")
        for d in items:
            _print_befund(d)
        return 0
    raise ValueError(
        "befund braucht --id <n> (eine Befund-ID), --testset-run <n> (jüngster Befund "
        "dieses Testset-Laufs) oder --iteration <n> (Historie, chronologisch)"
    )


def _preview_labels(config_json: dict, concept_id, iteration_id) -> dict:
    """Standard-Labels (Name + Beschreibung) über den Server-Endpunkt berechnen.

    Nutzt dieselbe zustandslose Route wie die Frontend-Buttons
    (/api/config/indicator/preview-labels) — einzige Notations-Wahrheit ist
    services/api/utils/indicator_labels.py. Konzeptname und Iterations-Nummer werden
    aus den verknüpften IDs aufgelöst; ohne Verknüpfung entfällt der jeweilige Teil.
    """
    concept_name = None
    iteration_number = None
    if iteration_id:
        it = fetch(f"/api/strategy/iterations/{iteration_id}")["data"]
        iteration_number = it.get("version")
        if not concept_id:
            concept_id = it.get("concept_id")
    if concept_id:
        concept_name = fetch(f"/api/strategy/concepts/{concept_id}")["data"].get("name")
    body = {
        "config_json": config_json,
        "concept_name": concept_name,
        "iteration_number": iteration_number,
    }
    return post("/api/config/indicator/preview-labels", body)["data"]


def indicator_config_create(args: list) -> int:
    f = _parse_flags(args)
    config_json = _read_json_file(_require(f, "file", "indicator-config-create"))
    concept_id = int(f["concept"]) if f.get("concept") else None
    iteration_id = int(f["iteration"]) if f.get("iteration") else None
    name = f.get("name") if f.get("name") and f.get("name") is not True else None
    description = f.get("description") if f.get("description") and f.get("description") is not True else None
    # Ohne --name: Standard-Titel (und, falls keine --description, Standard-Beschreibung)
    # nach Notation über den Server erzeugen. Mit --name: individuell, verbatim.
    if name is None:
        labels = _preview_labels(config_json, concept_id, iteration_id)
        name = labels.get("name")
        if description is None:
            description = labels.get("description")
    body = {"name": name, "config_json": config_json}
    if concept_id:
        body["strategy_concept_id"] = concept_id
    if iteration_id:
        body["strategy_iteration_id"] = iteration_id
    if description:
        body["description"] = description
    d = post("/api/config/indicator", body)["data"]
    print(f"## Erstellt: Indicator-Config **{d['id']}** ({d.get('name')})\n")
    return 0


def indicator_config_set(args: list) -> int:
    """Bestehende Indicator-Config gezielt aktualisieren (nur die gesetzten Felder).

    Flags: --id <n> (oder erstes Positional) und mindestens eines von
      --concept <n> · --iteration <n> · --name "..." · --description "..."
    Nutzt PATCH /api/config/indicator/{id} (Teil-Update): config_json, _stops und
    alle nicht übergebenen Felder bleiben bit-genau unangetastet. Kernfall:
    nachträgliche Konzept-/Iterations-Verknüpfung einer Config.
    """
    f = _parse_flags(args)
    pos = f.get("_positional", [])
    cid = f.get("id") or (pos[0] if pos else None)
    if not cid:
        raise ValueError("indicator-config-set: ID fehlt (--id <n> oder erstes Argument)")
    body: dict = {}
    if f.get("concept"):
        body["strategy_concept_id"] = int(f["concept"])
    if f.get("iteration"):
        body["strategy_iteration_id"] = int(f["iteration"])
    if f.get("name") and f.get("name") is not True:
        body["name"] = f["name"]
    if f.get("description") and f.get("description") is not True:
        body["description"] = f["description"]
    if not body:
        raise ValueError("indicator-config-set: mindestens ein Feld nötig (--concept | --iteration | --name | --description)")
    d = request("PATCH", f"/api/config/indicator/{int(cid)}", body)["data"]
    print(f"## indicator-config-set: OK — Config {d['id']} aktualisiert "
          f"(Concept {d.get('strategy_concept_id')} · Iter {d.get('strategy_iteration_id')} · {d.get('name')})\n")
    return 0


def indicator_config_labels(args: list) -> int:
    """Standard-Notation einer Config erzeugen, optional um Freitext erweitern, optional speichern.

    Flags: --id <n> (oder erstes Positional)
           [--name-freetext "..."]  kurze lesbare Kennung, hängt hinten per " : " an den Titel
           [--desc-freetext "..."]  Freitext, steht VOR der Auflistung: "<Freitext> | <Auflistung>"
           [--save]                 Ergebnis via PATCH zurückschreiben
    Bildet den Frontend-Flow nach: dieselbe zustandslose Route
    (/api/config/indicator/preview-labels, einzige Notations-Wahrheit) liefert Name +
    Indikator-Auflistung; der KI-Freitext wird an die richtige Stelle gesetzt und getrennt
    gespeichert. Freitext immer ausschreiben, keine kryptischen Kürzel. Ohne --save nur Anzeige.
    """
    f = _parse_flags(args)
    pos = f.get("_positional", [])
    cid = f.get("id") or (pos[0] if pos else None)
    if not cid:
        raise ValueError("indicator-config-labels: ID fehlt (--id <n> oder erstes Argument)")
    d = fetch(f"/api/config/indicator/{int(cid)}")["data"]
    labels = _preview_labels(d.get("config_json") or {},
                             d.get("strategy_concept_id"), d.get("strategy_iteration_id"))
    name = labels.get("name") or ""
    description = labels.get("description") or ""
    name_freetext = f.get("name-freetext")
    desc_freetext = f.get("desc-freetext")
    # Titel-Freitext hängt hinten per " : " (kurze, lesbare Kennung: Symbol + Regime)
    if name_freetext and name_freetext is not True:
        name = f"{name} : {name_freetext}"
    # Beschreibungs-Freitext steht VOR der Auflistung, per " | " getrennt
    if desc_freetext and desc_freetext is not True:
        description = f"{desc_freetext} | {description}"

    print(f"## indicator-config-labels — Config {int(cid)}")
    print(f"- Name: {name}")
    print(f"- Beschreibung: {description}")
    if f.get("save"):
        upd = request("PATCH", f"/api/config/indicator/{int(cid)}",
                      {"name": name, "description": description})["data"]
        print(f"- gespeichert (PATCH): Config {upd['id']}")
    else:
        print("- nur Vorschau (kein --save) — mit --save zurückschreiben")
    print()
    return 0


def backtest_config_create(args: list) -> int:
    f = _parse_flags(args)
    body = _read_json_file(_require(f, "file", "backtest-config-create"))
    d = post("/api/config/backtest", body)["data"]
    print(f"## Erstellt: Backtest-Config **{d['id']}** ({d.get('name')})\n")
    return 0


def testset_create(args: list) -> int:
    f = _parse_flags(args)
    name = _require(f, "name", "testset-create")
    raw = _require(f, "configs", "testset-create")
    ids = [int(x) for x in str(raw).split(",") if x.strip()]
    body = {"name": name, "backtest_config_ids": ids}
    if f.get("description"):
        body["description"] = f["description"]
    d = post("/api/testsets", body)["data"]
    print(f"## Erstellt: Testset **{d['id']}** ({d.get('name')}, {len(ids)} Backtest-Configs)\n")
    return 0


# ---------------------------------------------------------------------------
# Ausführen (start). Stoßen einen Lauf an. ID-basiert, keine Payload-Datei.
# Funktionsname: <bereich>_start.
# ---------------------------------------------------------------------------

def _metrics_body_value(f: dict):
    """Wandelt --metrics in den JSON-Wert für den Request-Body.

    Stdlib-only wie der Rest der Toolbox: kennt keine Gruppen-Keys, prüft nichts —
    die Stufen kern/voll/auto laufen als Zeichenkette durch, alles andere wird an
    Kommas zu einer Liste von Gruppen-Keys zerlegt. Gültigkeit prüft ausschließlich
    der Server (validate_metrics_selection); ein unbekannter Wert kommt als
    HTTP-Fehler zurück, kein stilles Client-seitiges Raten.

    Args:
        f: Geparste Flags aus _parse_flags.

    Returns:
        Stufenname, Liste von Gruppen-Keys, oder None (kein --metrics gesetzt).
    """
    raw = f.get("metrics")
    if raw is None or raw is True:
        return None
    raw = str(raw)
    if raw in ("kern", "voll", "auto"):
        return raw
    return [x.strip() for x in raw.split(",") if x.strip()]


def backtest_run_start(args: list) -> int:
    f = _parse_flags(args)
    body = {
        "backtest_config_id": int(_require(f, "backtest-config", "backtest-run-start")),
        "indicator_config_id": int(_require(f, "indicator-config", "backtest-run-start")),
        "iteration_id": int(_require(f, "iteration", "backtest-run-start")),
    }
    metrics = _metrics_body_value(f)
    if metrics is not None:
        body["metrics"] = metrics
    d = post("/api/backtest/start", body)["data"]
    print(f"## Gestartet: Backtest-Run **{d['run_id']}** "
          f"(backtest-config {body['backtest_config_id']}, indicator-config {body['indicator_config_id']}, iteration {body['iteration_id']})\n")
    return 0


def testset_run_start(args: list) -> int:
    f = _parse_flags(args)
    body = {
        "testset_id": int(_require(f, "testset", "testset-run-start")),
        "iteration_id": int(_require(f, "iteration", "testset-run-start")),
    }
    # GEÄNDERT: Raster wahlweise als Config-ID oder inline aus Datei.
    body.update(_indicators_source_body(f, "testset-run-start"))
    metrics = _metrics_body_value(f)
    if metrics is not None:
        body["metrics"] = metrics
    d = post("/api/testset-runs", body)["data"]
    run_ids = d.get("run_ids", [])
    quelle = (f"indicator-config {body['indicator_config_id']}"
              if "indicator_config_id" in body else "Raster inline")
    print(f"## Gestartet: Testset-Run **{d['testset_run_id']}** — {len(run_ids)} Runs "
          f"({', '.join(str(x) for x in run_ids)}) · {quelle}\n")
    return 0


# GEÄNDERT: Preflight: billiger Vorlauf auf EINER
# Kombination, adressiert über gespeicherte Objekte statt Playground-Request.
def preflight_run(args: list) -> int:
    """Preflight vor dem teuren Multiparameter-Lauf (Anforderung 5).

    Aufruf: preflight --iteration N --backtest-config K
            (--indicator-config M | --indicators <datei>)
    Ruft /api/chart-playground/preflight — rechnet dort EINE Kombination
    (Startwerte, kein DB-Schreiben) und meldet Entry-/Exit-Signalzahl samt erstem/
    letztem Signalzeitpunkt, NaN-Anteil je Indikator-Output, tatsächlichen Vorlauf
    (check_warmup), die Kombinationszahl des vollen Rasters (count_total_combos)
    und eine grobe Laufzeit-Hochrechnung. Berichtet nur — startet nichts, verhindert
    nichts (Report statt Gate).
    """
    f = _parse_flags(args)
    body = {
        "iteration_id": int(_require(f, "iteration", "preflight")),
        "backtest_config_id": int(_require(f, "backtest-config", "preflight")),
    }
    # GEÄNDERT: Raster wahlweise als Config-ID oder inline aus Datei.
    body.update(_indicators_source_body(f, "preflight"))
    # GEÄNDERT: längerer Timeout — die Route baut Indikatoren und rechnet eine
    # echte Kombination, das dauert länger als ein reiner DB-Read.
    d = post("/api/chart-playground/preflight", body, timeout=120)["data"]

    # GEÄNDERT: ohne gespeicherte Config meldet der Server hier None.
    raster = (f"indicator-config:{d['indicator_config_id']}"
              if d.get("indicator_config_id") is not None else "Raster inline")
    print(f"## Preflight — iteration:{d['iteration_id']} · {raster} "
          f"· backtest-config:{d['backtest_config_id']}\n")
    print(f"- Kombinationen (volles Raster): **{d['n_combinations']}**")

    es, xs = d["entry_signals"], d["exit_signals"]
    print(f"- Entry-Signale: {es['count']} (erstes {es.get('first_time') or '—'}, "
          f"letztes {es.get('last_time') or '—'})" + (f" · {es['note']}" if es.get("note") else ""))
    print(f"- Exit-Signale: {xs['count']} (erstes {xs.get('first_time') or '—'}, "
          f"letztes {xs.get('last_time') or '—'})" + (f" · {xs['note']}" if xs.get("note") else ""))

    w = d["warmup"]
    print(f"- Vorlauf: {w['level']} — {w['note']}")

    nan = d.get("indicator_nan_ratio") or {}
    if nan:
        print("- NaN-Anteil je Indikator-Output:")
        for k, v in nan.items():
            print(f"  - {k}: {v * 100:.1f}%")

    single_ms, est_ms = d["single_combo_duration_ms"], d["estimated_full_runtime_ms"]
    print(f"- Einzelkombi-Dauer: {single_ms} ms")
    print(f"- Laufzeit-Schätzung volles Raster: ~{est_ms / 1000:.1f}s ({d['estimated_full_runtime_note']})")

    if es.get("count") == 0:
        print("\n**WARNUNG: keine Entry-Signale in dieser Kombination — der volle Lauf wird "
              "vermutlich 0 Trades liefern.**")
    print()
    return 0


# GEÄNDERT: aktives Warten auf das Lauf-Ende, rein
# clientseitig (keine Server-Änderung): pollt die bestehende Runs-Liste.
def run_wait(args: list) -> int:
    """Wartet aktiv auf das Ende eines oder mehrerer Runs (Anforderung 6).

    Aufruf: run-wait --run N [--timeout M]
            run-wait --testset-run N [--timeout M]
    Pollt /api/backtest/runs im Abstand von 5s, bis alle Ziel-Runs 'completed' oder
    'failed' sind (Default-Timeout 1800s = 30 Min). Danach je Run: Status, Dauer
    (completed_at - started_at), Anzahl Results, bei 'failed' die Fehlermeldung.
    Greift der Timeout, wird das explizit als Timeout gemeldet — nicht als
    Fehlschlag der Runs (Rückgabecode 2 statt 1).
    """
    import time as _time
    f = _parse_flags(args)
    timeout = int(f.get("timeout", 1800))
    poll_interval = 5

    # GEÄNDERT: --run pollt jetzt über den Einzel-GET, nicht mehr
    # über die Liste (löst die RUN_LIST_LIMIT-Grenze für den Einzelfall auf).
    # --testset-run bleibt auf der Liste: der Server filtert dort bereits über
    # testset_run_id, die Runmenge ist von Natur aus klein.
    single_run = bool(f.get("run"))
    if single_run:
        run_ids = [int(f["run"])]
        scope = f"run:{run_ids[0]}"
    elif f.get("testset-run"):
        tsr = int(f["testset-run"])
        items = fetch(f"/api/backtest/runs?testset_run_id={tsr}&limit={RUN_LIST_LIMIT}")["data"]["items"]
        run_ids = [r["id"] for r in items]
        scope = f"testset-run:{tsr}"
        if not run_ids:
            print(f"## run-wait: keine Runs zu {scope} gefunden\n")
            return 1
    else:
        raise ValueError("run-wait braucht --run <id> oder --testset-run <id>")

    print(f"## run-wait — {scope} · {len(run_ids)} Run(s) · Timeout {timeout}s")
    t0 = _time.monotonic()
    pending = set(run_ids)
    last: dict = {}
    while pending:
        if single_run:
            by_id = {}
            for rid in pending:
                try:
                    by_id[rid] = fetch(f"/api/backtest/runs/{rid}")["data"]
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        raise ValueError(f"run-wait: run:{rid} nicht gefunden") from e
                    raise
        else:
            items = fetch(f"/api/backtest/runs?limit={RUN_LIST_LIMIT}")["data"]["items"]
            by_id = {r["id"]: r for r in items}
        for rid in list(pending):
            r = by_id.get(rid)
            if r is None:
                continue
            last[rid] = r
            if r.get("status") in ("completed", "failed"):
                pending.discard(rid)
        if not pending:
            break
        if _time.monotonic() - t0 > timeout:
            print(f"- **TIMEOUT** nach {int(_time.monotonic() - t0)}s — noch offen: "
                  f"{', '.join('run:' + str(r) for r in sorted(pending))}\n")
            return 2
        _time.sleep(poll_interval)

    print(f"- Fertig nach {int(_time.monotonic() - t0)}s\n")
    for rid in run_ids:
        r = last.get(rid, {})
        status = r.get("status")
        duration = "—"
        started, completed = r.get("started_at"), r.get("completed_at")
        if started and completed:
            try:
                d_sec = (datetime.datetime.fromisoformat(completed)
                         - datetime.datetime.fromisoformat(started)).total_seconds()
                duration = f"{d_sec:.1f}s"
            except ValueError:
                pass
        n_results = "—"
        try:
            n_results = fetch(f"/api/backtest/runs/{rid}/results?limit=1")["data"]["total"]
        except (urllib.error.HTTPError, urllib.error.URLError, KeyError):
            pass
        line = f"- run:{rid} · **{status}** · Dauer {duration} · {n_results} Results"
        if status == "failed" and r.get("error_message"):
            line += f" · Fehler: {r['error_message']}"
        print(line)
    print()
    return 0


# ---------------------------------------------------------------------------
# Signifikanztest je Kandidat. Zwei Methoden, ein Datensatz-Typ:
# permutation (Nullmodell, liefert p-Werte) und bootstrap (Unsicherheitsband der
# eigenen Trades, KEIN p-Wert). Harte Ausgabe-Regel: ein p-Wert erscheint nie ohne
# die Kennwerte seiner Null-Verteilung — sinngemäß dieselbe Regel wie „DSR nie ohne
# N und SR0". Es gibt keine Sortierung nach p-Wert und kein Bestanden-Feld.
# ---------------------------------------------------------------------------

def _print_significance(d: dict) -> None:
    """Druckt einen Signifikanztest als Markdown.

    Beim Permutationstest steht je Metrik der echte Wert, danach die Kennwerte der
    Null-Verteilung und erst dann der p-Wert — in einer Zeile, damit der p-Wert
    nicht ohne seine Verteilung zitierbar ist. Beim Bootstrap gibt es
    ausdrücklich keinen p-Wert; ausgegeben werden Konfidenzbänder und der
    Bootstrap-Anteil.
    """
    method = d.get("method")
    print(f"### Signifikanztest {d.get('id')} — {method} · **{d.get('status')}**")
    print(f"- Result {d.get('result_id')} · Run {d.get('run_id')} · Iteration {d.get('iteration_id')}")
    label_n = "Reihen" if method == "permutation" else "Bootstrap-Runden"
    print(f"- N ({label_n}): {d.get('n_iterations')} · Seed: {d.get('seed')} · "
          f"Dauer: {num(d.get('duration_seconds'), '{:.1f}s')}")
    cfg = d.get("config_snapshot_json") or {}
    if cfg:
        print(f"- Kandidat: {cfg.get('symbol')} {cfg.get('exchange')} {cfg.get('timeframe')} · "
              f"{cfg.get('start')} .. {cfg.get('end')}")
    if d.get("error_message"):
        print(f"- **Fehler:** {d['error_message']}")
    summary = d.get("summary_json") or {}
    if not summary:
        print()
        return

    if method == "permutation":
        metrics = summary.get("metrics") or {}
        print("\n| Metrik | echter Wert | Null-Verteilung (mean / median / p05 / p95 / max) | k >= echt | p-Wert |")
        print("|---|---|---|---|---|")
        for name, m in metrics.items():
            nd = m.get("null_distribution") or {}
            null_cell = " / ".join(num(nd.get(key), "{:.4f}") for key in
                                   ("mean", "median", "p05", "p95", "max"))
            p_cell = num(m.get("p_value"), "{:.4f}")
            if m.get("p_value") is None and m.get("p_value_missing_reason"):
                p_cell = f"— ({m['p_value_missing_reason']})"
            print(f"| {name} | {num(m.get('real_value'), '{:.4f}')} | {null_cell} | "
                  f"{m.get('n_ge_real')} / {m.get('n_iterations')} | {p_cell} |")
        no_trade = summary.get("no_trade_runs") or {}
        share = no_trade.get("share")
        print(f"\n- Läufe ohne Trades: {no_trade.get('count')} "
              f"({num(share * 100 if isinstance(share, (int, float)) else None, '{:.1f}')} %) — mitgezählt, nicht verworfen")
        check = summary.get("reference_check") or {}
        if check:
            compared = check.get("compared") or {}
            print(f"- Selbstprüfung: {len(compared)} Kennzahl(en) gegen das Result geprüft "
                  f"(relative Toleranz {check.get('tolerance')})")
            for name, reason in (check.get("unchecked") or {}).items():
                print(f"  - ungeprüft: {name} — {reason}")
        print("\n- Lesart: der p-Wert sagt, wie oft ein so gutes Ergebnis aus strukturlosen "
              "Daten entsteht. Kleinster erreichbarer Wert ist 1/(N+1). Report, kein Filter.")
    else:
        obs = summary.get("observed") or {}
        bands = summary.get("bands") or {}
        print(f"\n- Trades: {summary.get('n_trades')} (geschlossene)")
        print("\n| Kennzahl | beobachtet | p05 | p50 | p95 |")
        print("|---|---|---|---|---|")
        for name in ("mean_return_pct", "median_return_pct", "profit_factor"):
            band = bands.get(name) or {}
            print(f"| {name} | {num(obs.get(name), '{:.4f}')} | {num(band.get('p05'), '{:.4f}')} | "
                  f"{num(band.get('p50'), '{:.4f}')} | {num(band.get('p95'), '{:.4f}')} |")
        share = summary.get("share_pf_le_one")
        print(f"\n- Anteil der Resamples mit Profitfaktor <= 1: "
              f"{num(share * 100 if isinstance(share, (int, float)) else None, '{:.1f}')} %")
        print(f"- {summary.get('share_pf_le_one_note', '')}")
        print(f"- Profitfaktor-Basis: {summary.get('profit_factor_basis', '')}")
    print()


def significance_start(args: list) -> int:
    """Startet einen Signifikanztest für einen Kandidaten.

    Aufruf: signifikanz-start --result N [--method permutation|bootstrap]
                              [--n 300] [--seed 42] [--wait [--timeout M]]

    `permutation` läuft als Hintergrund-Job (N synthetische Preisreihen, Default 300);
    `bootstrap` rechnet direkt im Aufruf (Default 2000 Runden). Mit --wait wird bis
    completed/failed gepollt — Exit-Codes wie run-wait: 0 fertig, 2 Timeout.
    """
    import time as _time
    f = _parse_flags(args)
    result_id = int(_require(f, "result", "signifikanz-start"))
    method = f.get("method") or "permutation"
    if method not in ("permutation", "bootstrap"):
        raise ValueError(f"signifikanz-start: --method muss permutation oder bootstrap sein, ist {method}")
    body = {"method": method, "seed": int(f.get("seed", 42))}
    if f.get("n") and f["n"] is not True:
        body["n"] = int(f["n"])
    if f.get("metrics") and f["metrics"] is not True:
        body["metrics"] = [m.strip() for m in str(f["metrics"]).split(",") if m.strip()]

    # Der Bootstrap rechnet synchron in der Route — dafür braucht der POST mehr Zeit
    # als ein DB-Read (2000 Runden).
    d = post(f"/api/backtest/results/{result_id}/significance", body,
             timeout=TIMEOUT if method == "permutation" else 120)["data"]
    test_id = d["test_id"]
    print(f"## signifikanz-start: {method} für result:{result_id} — Test-ID {test_id} "
          f"(Status {d['test'].get('status')})\n")

    if not f.get("wait"):
        if method == "bootstrap":
            _print_significance(d["test"])
        return 0

    timeout = int(f.get("timeout", 1800))
    poll_interval = 5
    t0 = _time.monotonic()
    while True:
        test = fetch(f"/api/significance-tests/{test_id}")["data"]
        if test.get("status") in ("completed", "failed"):
            print(f"- Fertig nach {int(_time.monotonic() - t0)}s\n")
            _print_significance(test)
            return 0
        if _time.monotonic() - t0 > timeout:
            print(f"- **TIMEOUT** nach {int(_time.monotonic() - t0)}s — "
                  f"Test {test_id} steht auf '{test.get('status')}'\n")
            return 2
        _time.sleep(poll_interval)


def significance_read(args: list) -> int:
    """Liest einen Signifikanztest per --id.

    Ausgabe je Metrik: echter Wert, Kennwerte der Null-Verteilung und p-Wert
    nebeneinander — ein p-Wert erscheint hier nie ohne seine Null-Verteilung.
    """
    f = _parse_flags(args)
    test_id = int(_require(f, "id", "signifikanz"))
    d = fetch(f"/api/significance-tests/{test_id}")["data"]
    if _maybe_json(f, d, "signifikanz"):
        return 0
    _print_significance(d)
    return 0


def significance_list(args: list) -> int:
    """Test-Historie eines Results — chronologisch, ohne Sortierung nach p-Wert."""
    f = _parse_flags(args)
    result_id = int(_require(f, "result", "signifikanz-list"))
    items = fetch(f"/api/significance-tests?result_id={result_id}")["data"]["items"]
    if _maybe_json(f, {"total": len(items), "items": items}, "signifikanz-list"):
        return 0
    print(f"## Signifikanztest-Historie result:{result_id} ({len(items)}, chronologisch)\n")
    if not items:
        print("- keine Tests vorhanden\n")
        return 0
    for d in items:
        _print_significance(d)
    return 0


# ---------------------------------------------------------------------------
# Walk-Forward-Fold-Kette. Die Kette läuft client-getrieben über die
# vorhandenen Bausteine: Kette anlegen -> je Fold IS-Lauf, run-wait, Siegerwahl,
# OOS-Lauf, run-wait, Recompute -> Fold anhängen -> schließen. Bricht etwas ab,
# wird die Kette mit 'failed' und Grund geschlossen; sie bleibt nie offen hängen.
#
# Die Aggregation rechnet ausschließlich der Server (POST /close). Hier wird sie
# nur abgerufen und dargestellt — eine zweite Rechnung in der Toolbox würde
# unbemerkt auseinanderlaufen (Drift-Warnung).
#
# Ausgabe-Regeln: das Aggregat erscheint nie ohne die Fold-Tabelle, aus der es
# entstanden ist, und je Fold steht der IS-Wert neben dem OOS-Wert (die
# Degradation ist die eigentliche Aussage). Kein Verdict, keine Güte-Sortierung.
# ---------------------------------------------------------------------------

WF_CHAIN_BASE = "/api/backtest/walk-forward-chains"
# Der Recompute eines Testfenster-Results rechnet einen echten Einzel-Backtest
# nach — das braucht deutlich mehr Zeit als ein DB-Read.
WF_RECOMPUTE_TIMEOUT = 600


def _wf_window_str(window: dict, empty: str = "—") -> str:
    """Formatiert ein Fold-Fenster als `start..end`.

    Args:
        window: Fensterblock mit start/end (darf None sein).
        empty: Ausgabe, wenn gar kein Fenster vorliegt (z.B. 'entfällt' beim
            Testfenster eines Folds ohne Sieger).

    Returns:
        Zeichenkette `start..end`, fehlende Grenzen als Gedankenstrich.
    """
    if not window:
        return empty
    return f"{window.get('start') or '—'}..{window.get('end') or '—'}"


def _wf_params_str(params) -> str:
    """Formatiert die Sieger-Parameter einer Kombination als `k=v`-Liste.

    Args:
        params: `actual_params` des Sieger-Results (Dict) oder None.

    Returns:
        Kompakte, sortierte Parameter-Liste oder ein Gedankenstrich.
    """
    if not isinstance(params, dict) or not params:
        return "—"
    return ", ".join(f"{k}={params[k]}" for k in sorted(params))


def _print_walk_forward_plan(chain: dict) -> None:
    """Druckt Kopf und vorregistrierten Plan einer Kette.

    Der Plan ist die Vorregistrierung: Fold-Zahl, Fensterlängen und Kriterium
    stehen seit dem Anlegen fest. Er wird deshalb immer vollständig ausgegeben,
    auch wenn die Kette abgebrochen ist.

    Args:
        chain: Serialisierte Kette aus der API.
    """
    plan = chain.get("plan_json") or {}
    cfg = chain.get("config_snapshot_json") or {}
    anchor = plan.get("anchor_window") or {}
    print(f"## Walk-Forward-Kette {chain.get('id')} — **{chain.get('status')}**")
    print(f"- Anker-Run {chain.get('anchor_run_id')} · Iteration {chain.get('iteration_id')} "
          f"· Konzept {chain.get('concept_id')}")
    print(f"- {cfg.get('symbol')} {cfg.get('exchange')} {cfg.get('timeframe')} "
          f"· Anker-Fenster {_wf_window_str(anchor)}")
    print(f"- Angelegt {chain.get('created_at') or '—'} · Abgeschlossen "
          f"{chain.get('completed_at') or '—'}")
    if chain.get("error_message"):
        print(f"- **Abbruch:** {chain['error_message']}")

    is_len = plan.get("is_months")
    is_text = f"{is_len} Monate" if is_len else "Länge des Anker-Fensters"
    print("\n### Plan (vorregistriert, beim Anlegen festgeschrieben)")
    print(f"- Folds: **{plan.get('n_folds')}** · IS-Länge: {is_text} · OOS-Länge: "
          f"{plan.get('oos_months')} Monate · Vorlauf: {plan.get('warmup_days')} Tage")
    print(f"- Kriterium: **{plan.get('selection_metric')}** "
          f"({plan.get('selection_direction')}), Trade-Floor "
          f"{plan.get('trade_floor')} · Metrik-Stufe der IS-Läufe: "
          f"{plan.get('metrics_level') if plan.get('metrics_level') is not None else 'auto (Server-Default)'}")
    print("\n| Fold | IS-Fenster (geplant) | OOS-Fenster (geplant) |")
    print("|---|---|---|")
    for fold in plan.get("folds") or []:
        print(f"| {fold.get('fold_index')} | {_wf_window_str(fold.get('is_window'))} "
              f"| {_wf_window_str(fold.get('oos_window'))} |")
    print()


def _print_walk_forward_chain(chain: dict) -> None:
    """Druckt eine Kette vollständig: Plan, Fold-Tabelle, Aggregat, Methodenhinweis.

    Harte Reihenfolge-Regel: Das Aggregat steht **nie** ohne die Fold-Tabelle, aus
    der es entstanden ist. Fehlen die Fold-Blöcke, wird auch kein Aggregat
    ausgegeben — sonst wäre eine Gesamtzahl zitierbar, ohne dass die Streuung über
    die Folds danebensteht.

    Args:
        chain: Serialisierte Kette aus der API.
    """
    _print_walk_forward_plan(chain)
    folds = chain.get("folds_json") or []
    metric = (chain.get("plan_json") or {}).get("selection_metric")

    print("### Folds — IS-Wert neben OOS-Wert (Degradation)")
    if not folds:
        print("\n- keine Fold-Blöcke vorhanden — ohne Fold-Tabelle wird kein Aggregat "
              "ausgegeben.\n")
        print(f"### Methodenhinweis\n\n{chain.get('method_note') or '—'}\n")
        return

    print(f"\n| Fold | IS-Fenster | IS-{metric} | OOS-Fenster | OOS-{metric} | "
          f"OOS-Return % | OOS-Trades | Sieger |")
    print("|---|---|---|---|---|---|---|---|")
    for fold in folds:
        winner = fold.get("winner") or {}
        oos = fold.get("oos_metrics") or {}
        is_value = winner.get("selection_value") if winner else None
        oos_value = oos.get(metric) if metric else None
        sieger = (f"result {winner.get('result_id')}" if winner
                  else f"kein Sieger — {fold.get('no_winner_reason') or 'Grund nicht angegeben'}")
        print(f"| {fold.get('fold_index')} | {_wf_window_str(fold.get('is_window'))} "
              f"| {num(is_value, '{:.4f}')} "
              f"| {_wf_window_str(fold.get('oos_window'), 'entfällt')} "
              f"| {num(oos_value, '{:.4f}')} | {num(oos.get('total_return_pct'), '{:.2f}')} "
              f"| {oos.get('total_trades') if oos else '—'} | {sieger} |")

    print("\n#### Sieger-Kopien je Fold (eingefroren, überleben das Aufräumen)")
    for fold in folds:
        winner = fold.get("winner")
        idx = fold.get("fold_index")
        if not winner:
            print(f"- Fold {idx}: **kein Sieger** — "
                  f"{fold.get('no_winner_reason') or 'Grund nicht angegeben'} "
                  f"(IS-Lauf {fold.get('is_run_id')}, Testfenster entfällt)")
            continue
        print(f"- Fold {idx}: IS-Lauf {fold.get('is_run_id')} → result "
              f"{winner.get('result_id')} · {metric} = "
              f"{num(winner.get('selection_value'), '{:.4f}')} · "
              f"OOS-Lauf {fold.get('oos_run_id')} / result {fold.get('oos_result_id')} "
              f"· ann_factor {num(fold.get('ann_factor'), '{:.2f}')}")
        print(f"  - Parameter: {_wf_params_str(winner.get('actual_params'))}")

    aggregate = chain.get("aggregate_json") or {}
    print("\n### Gesamt (verkettete OOS-Kurve, serverseitig gerechnet)")
    if not aggregate:
        print("\n- kein Aggregat vorhanden (Kette noch offen).\n")
    else:
        print(f"\n- Gesamt-Return: {num(aggregate.get('total_return_pct'))} % · "
              f"Sharpe (annualisiert, Faktor {num(aggregate.get('ann_factor'), '{:.2f}')}): "
              f"{num(aggregate.get('sharpe_ratio'), '{:.4f}')} · Max Drawdown: "
              f"{num(aggregate.get('max_drawdown_pct'))} %")
        print(f"- Profitfaktor: {num(aggregate.get('profit_factor'), '{:.4f}')} · Trades: "
              f"{aggregate.get('total_trades')} (geschlossen {aggregate.get('closed_trades')}, "
              f"offen {aggregate.get('open_trades')}) · Balken: {aggregate.get('bar_count')}")
        print(f"- Folds: {aggregate.get('folds_total')} gesamt, "
              f"{aggregate.get('folds_with_winner')} mit Sieger, "
              f"{aggregate.get('folds_without_winner')} ohne Sieger, "
              f"{aggregate.get('folds_in_curve')} in der Kurve")
        print(f"- Profitable Folds: {aggregate.get('profitable_folds')} "
              f"({num(aggregate.get('profitable_folds_pct'))} %)")
        for note in aggregate.get("notes") or []:
            print(f"- Hinweis: {note}")
        print()

    print(f"### Methodenhinweis\n\n{chain.get('method_note') or '—'}\n")


def _wf_wait_for_run(run_id: int, timeout: int, label: str):
    """Wartet auf einen Ketten-Lauf und meldet sein Ergebnis.

    Nutzt das vorhandene `run-wait`-Verb (gleiches Poll-Verhalten, gleiche
    Fortschrittsausgabe) und liest danach den Endstatus des Laufs.

    Args:
        run_id: Zu beobachtender Lauf.
        timeout: Timeout in Sekunden (wie bei run-wait).
        label: Bezeichnung für die Fehlermeldung ('IS-Lauf'/'OOS-Lauf').

    Returns:
        Tupel (status, meldung). status ist 'completed', 'failed' oder 'timeout';
        die Meldung ist bei 'completed' None.
    """
    rc = run_wait(["--run", str(run_id), "--timeout", str(timeout)])
    if rc == 2:
        return "timeout", f"{label} run:{run_id}: Timeout nach {timeout}s"
    run = fetch(f"/api/backtest/runs/{run_id}")["data"]
    status = run.get("status")
    if status != "completed":
        detail = f" — {run['error_message']}" if run.get("error_message") else ""
        return "failed", f"{label} run:{run_id}: Status '{status}'{detail}"
    return "completed", None


def _wf_single_result_id(run_id: int) -> int:
    """Liest die Result-ID eines Einzelkombinations-Laufs.

    Args:
        run_id: Testfenster-Lauf (rechnet genau eine Kombination).

    Returns:
        Die Result-ID.

    Raises:
        ValueError: Wenn der Lauf kein Result hat.
    """
    items = fetch(f"/api/backtest/runs/{run_id}/results?limit=1")["data"]["items"]
    if not items:
        raise ValueError(f"OOS-Lauf {run_id} hat kein Result — Kette kann den Fold nicht anhängen.")
    return int(items[0]["id"])


def _wf_recompute_equity(result_id: int) -> int:
    """Rechnet die balkengenaue Kapitalkurve eines Results nach.

    Nutzt den vorhandenen Recompute-Weg (`chart-data` rechnet nach, wenn keine
    Equity-Zeilen vorliegen). Die Kurve ist die Grundlage der serverseitigen
    Aggregation.

    Args:
        result_id: Testfenster-Result.

    Returns:
        Anzahl der Balken der Kapitalkurve.

    Raises:
        ValueError: Wenn keine Kurve entsteht.
    """
    d = fetch(f"/api/backtest/results/{result_id}/chart-data", timeout=WF_RECOMPUTE_TIMEOUT)
    bars = len(d.get("equity") or [])
    if bars == 0:
        raise ValueError(
            f"Recompute von result:{result_id} lieferte keine Kapitalkurve — "
            f"ohne Kurve kann der Fold nicht in die Aggregation eingehen."
        )
    return bars


def _wf_close_chain(chain_id: int, error_message: str = None) -> dict:
    """Schließt eine Kette und gibt den versiegelten Datensatz zurück.

    Args:
        chain_id: Die Kette.
        error_message: Gesetzt = Abbruch, die Kette schließt als 'failed'.

    Returns:
        Die vollständige Kette aus der Antwort.
    """
    body = {"error_message": error_message} if error_message else {}
    return post(f"{WF_CHAIN_BASE}/{chain_id}/close", body, timeout=WF_RECOMPUTE_TIMEOUT)["data"]


def walk_forward_chain_start(args: list) -> int:
    """Fährt eine komplette Walk-Forward-Fold-Kette im Vordergrund.

    Aufruf: walk-forward-chain-start --run <anker-run-id> --folds N --oos-monate M
            [--is-monate K] --selection-metric <metrik> [--selection-direction max|min]
            [--trade-floor T] [--metrics kern|voll|auto|<gruppen>] [--timeout <s>]

    Je Fold: IS-Lauf starten (Fold 1 nutzt den Anker-Lauf selbst, wenn sein
    IS-Fenster exakt das Anker-Fenster ist — kein Doppelrechnen), warten, Sieger
    serverseitig nach dem vorregistrierten Kriterium wählen, OOS-Lauf starten,
    warten, Kapitalkurve nachrechnen, Fold anhängen. Am Ende schließt die Kette
    und der Server rechnet die Aggregation.

    Ein Fold ohne Sieger (kein Kandidat über dem Trade-Floor) ist ein Ergebnis
    und kein Fehler: er wird als solcher angehängt, die Kette läuft weiter.
    Bricht dagegen ein Lauf ab oder greift der Timeout, wird die Kette mit
    'failed' und Grund geschlossen — kein stilles Hängenbleiben.

    Returns:
        Exit-Code wie run-wait: 0 fertig, 1 Fehlschlag, 2 Timeout.
    """
    f = _parse_flags(args)
    verb = "walk-forward-chain-start"
    body = {
        "anchor_run_id": int(_require(f, "run", verb)),
        "folds": int(_require(f, "folds", verb)),
        "oos_months": int(_require(f, "oos-monate", verb)),
        "selection_metric": str(_require(f, "selection-metric", verb)),
        "selection_direction": str(f.get("selection-direction") or "max"),
        "trade_floor": int(f.get("trade-floor") or 0),
    }
    if f.get("is-monate") and f["is-monate"] is not True:
        body["is_months"] = int(f["is-monate"])
    metrics = _metrics_body_value(f)
    if metrics is not None:
        body["metrics"] = metrics
    timeout = int(f.get("timeout", 1800))

    # Der Server prüft Kriterium, Plan und Datenabdeckung, BEVOR ein Datensatz
    # entsteht — ein Plan außerhalb der Daten scheitert hier, nicht mitten im Lauf.
    started = post(WF_CHAIN_BASE, body)["data"]
    chain_id = started["chain_id"]
    chain = started["chain"]
    plan = chain.get("plan_json") or {}
    _print_walk_forward_plan(chain)

    anchor_window = plan.get("anchor_window") or {}
    exit_code = 0
    abort_message = None
    try:
        for planned in plan.get("folds") or []:
            fold_index = planned["fold_index"]
            is_window = planned["is_window"]
            oos_window = planned["oos_window"]
            print(f"### Fold {fold_index}/{plan.get('n_folds')} — IS {_wf_window_str(is_window)} "
                  f"→ OOS {_wf_window_str(oos_window)}\n")

            # Fold 1 rechnet nicht doppelt, wenn sein IS-Fenster exakt das
            # Anker-Fenster ist (Plan ohne eigene IS-Länge).
            reuses_anchor = (
                fold_index == 1
                and is_window.get("start") == anchor_window.get("start")
                and is_window.get("end") == anchor_window.get("end")
            )
            if reuses_anchor:
                is_run_id = chain["anchor_run_id"]
                print(f"- IS-Lauf: Anker-Run {is_run_id} (IS-Fenster = Anker-Fenster, "
                      f"kein Doppelrechnen)\n")
            else:
                is_started = post(f"{WF_CHAIN_BASE}/{chain_id}/is-run",
                                  {"fold_index": fold_index})["data"]
                is_run_id = is_started["run_id"]
                print(f"- IS-Lauf {is_run_id} gestartet (Anker-Raster auf dem Planfenster)")
                status, message = _wf_wait_for_run(is_run_id, timeout, "IS-Lauf")
                if status != "completed":
                    abort_message = message
                    exit_code = 2 if status == "timeout" else 1
                    break

            oos = post(f"{WF_CHAIN_BASE}/{chain_id}/oos-run",
                       {"fold_index": fold_index, "is_run_id": is_run_id})["data"]
            fold_body = {
                "fold_index": fold_index,
                "is_window": is_window,
                "is_run_id": is_run_id,
            }
            winner = oos.get("winner")
            if winner is None:
                print(f"- **Kein Sieger** — {oos.get('no_winner_reason')}")
                print("  (ausgewiesen, nicht verschluckt; Testfenster entfällt für diesen Fold)\n")
                fold_body["no_winner_reason"] = oos.get("no_winner_reason")
                post(f"{WF_CHAIN_BASE}/{chain_id}/folds", fold_body)
                print(f"- Fold {fold_index} angehängt (ohne Sieger)\n")
                continue

            print(f"- Sieger: result {winner.get('result_id')} · "
                  f"{winner.get('selection_metric')} = "
                  f"{num(winner.get('selection_value'), '{:.4f}')} · "
                  f"{_wf_params_str(winner.get('actual_params'))}")
            oos_run_id = oos["oos_run_id"]
            print(f"- OOS-Lauf {oos_run_id} gestartet (eingefrorene Kombination)")
            status, message = _wf_wait_for_run(oos_run_id, timeout, "OOS-Lauf")
            if status != "completed":
                abort_message = message
                exit_code = 2 if status == "timeout" else 1
                break

            oos_result_id = _wf_single_result_id(oos_run_id)
            bars = _wf_recompute_equity(oos_result_id)
            print(f"- OOS-Result {oos_result_id} · Kapitalkurve {bars} Balken")

            fold_body.update({
                "oos_window": oos.get("oos_window") or oos_window,
                "winner": winner,
                "oos_run_id": oos_run_id,
                "oos_result_id": oos_result_id,
            })
            appended = post(f"{WF_CHAIN_BASE}/{chain_id}/folds", fold_body)["data"]
            print(f"- Fold {fold_index} angehängt ({appended.get('folds_total')}/"
                  f"{plan.get('n_folds')})\n")
    except urllib.error.HTTPError as e:
        abort_message = f"HTTP {e.code} {e.reason}: {e.read().decode(errors='replace')[:500]}"
        exit_code = 1
    except (ValueError, KeyError, urllib.error.URLError) as e:
        abort_message = f"{type(e).__name__}: {e}"
        exit_code = 1

    if abort_message:
        print(f"- **Abbruch:** {abort_message}\n")
    closed = _wf_close_chain(chain_id, abort_message)
    _print_walk_forward_chain(closed)
    return exit_code


def walk_forward_chain_read(args: list) -> int:
    """Liest eine Walk-Forward-Kette per --id.

    Ausgabe: Plan mit Kriterium, Fold-Tabelle mit IS-Wert neben OOS-Wert,
    Sieger-Kopien, Gesamtblock und Methodenhinweis — das Aggregat erscheint nie
    ohne seine Fold-Tabelle.
    """
    f = _parse_flags(args)
    chain_id = int(_require(f, "id", "walk-forward-chain"))
    d = fetch(f"/api/walk-forward-chains/{chain_id}")["data"]
    if _maybe_json(f, d, "walk-forward-chain"):
        return 0
    _print_walk_forward_chain(d)
    return 0


def walk_forward_chain_list(args: list) -> int:
    """Ketten-Historie, chronologisch.

    Bewusst ohne Kennzahlen: das Aggregat wird nur zusammen mit der Fold-Tabelle
    ausgegeben (`walk-forward-chain --id <id>`), damit aus der Historie keine
    Bestenliste wird.
    """
    f = _parse_flags(args)
    path = "/api/walk-forward-chains"
    scope = "alle Iterationen"
    if f.get("iteration") and f["iteration"] is not True:
        path += f"?iteration_id={int(f['iteration'])}"
        scope = f"iteration:{int(f['iteration'])}"
    items = fetch(path)["data"]["items"]
    if _maybe_json(f, {"total": len(items), "items": items}, "walk-forward-chain-list"):
        return 0
    print(f"## Walk-Forward-Ketten — {scope} ({len(items)}, chronologisch)\n")
    if not items:
        print("- keine Ketten vorhanden\n")
        return 0
    print("| Kette | angelegt | Status | Anker-Run | Folds (Plan) | mit Sieger | Kriterium |")
    print("|---|---|---|---|---|---|---|")
    for d in items:
        plan = d.get("plan_json") or {}
        folds = d.get("folds_json") or []
        with_winner = sum(1 for fold in folds if fold.get("winner"))
        print(f"| {d.get('id')} | {d.get('created_at') or '—'} | {d.get('status')} "
              f"| {d.get('anchor_run_id')} | {plan.get('n_folds')} | {with_winner}/{len(folds)} "
              f"| {plan.get('selection_metric')} ({plan.get('selection_direction')}), "
              f"Floor {plan.get('trade_floor')} |")
    print("\n- Kennzahlen bewusst nicht in der Historie: das Aggregat wird nur mit seiner "
          "Fold-Tabelle ausgegeben — `walk-forward-chain --id <id>`.\n")
    return 0


# ---------------------------------------------------------------------------
# Ändern / Löschen / Aktionen / restliche Reads. Damit deckt die Toolbox JEDE
# operative API-Route ab. Einfache Fälle laufen über eine deklarative Tabelle
# (TABLE_VERBS) mit generischem Executor; Bodies aus mehreren Skalar-Flags haben
# eigene kleine Handler. Der generische `api`-Befehl erreicht zusätzlich jede
# beliebige (auch künftige) Route direkt.
# ---------------------------------------------------------------------------

# Ausgabe-Ordner für --out. Immer unter Temp — die Dateien sind Zwischenergebnisse
# für genau eine Folge-Analyse, kein Artefakt, das im Projektbaum landen darf.
OUT_DIR = pathlib.Path(tempfile.gettempdir()) / "bt-toolbox-out"
OUT_MAX_AGE_HOURS = 24


def _out_path(out) -> pathlib.Path:
    """Löst den --out-Wert zu einem Pfad unter OUT_DIR auf.

    out=True (Flag ohne Wert) -> Auto-Name mit Zeitstempel. Ein reiner Dateiname
    oder ein relativer Pfad landet ebenfalls unter OUT_DIR (nie im Arbeitsverzeichnis
    und damit nie im Repo). Nur ein absoluter Pfad wird wörtlich genommen — bewusste
    Ausnahme, die dann aber auch nicht mit aufgeräumt wird.
    """
    if out is True:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        return OUT_DIR / f"api-{stamp}.json"
    p = pathlib.Path(str(out)).expanduser()
    return p if p.is_absolute() else OUT_DIR / p


def _drop_empty_out_dirs() -> None:
    """Entfernt leer gewordene Unterordner in OUT_DIR (tiefste zuerst). OUT_DIR bleibt."""
    dirs = sorted((p for p in OUT_DIR.rglob("*") if p.is_dir()),
                  key=lambda p: len(p.parts), reverse=True)
    for d in dirs:
        try:
            d.rmdir()
        except OSError:
            continue


def _prune_out_dir(max_age_hours: int = OUT_MAX_AGE_HOURS) -> int:
    """Löscht abgelaufene --out-Dateien aus OUT_DIR. Gibt die Anzahl zurück.

    Läuft bei jedem --out-Schreiben mit: der Ordner räumt sich selbst auf, ohne dass
    der Aufrufer daran denken muss. Rekursiv (auch Dateien in Unterordnern, die ein
    relativer --out-Pfad angelegt hat); leer gewordene Unterordner fallen mit weg.
    Fasst ausschließlich OUT_DIR an.
    """
    if not OUT_DIR.is_dir():
        return 0
    cutoff = datetime.datetime.now().timestamp() - max_age_hours * 3600
    removed = 0
    for f in OUT_DIR.rglob("*"):
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        _drop_empty_out_dirs()
    return removed


def out_clean(args: list) -> int:
    """Räumt den --out-Ordner auf: out-clean [--all].

    Ohne Flag fallen nur abgelaufene Dateien (aelter als OUT_MAX_AGE_HOURS) weg —
    dasselbe, was beim Schreiben automatisch passiert. Mit --all wird der Ordner
    komplett geleert (auch noch frische Dateien).
    """
    f = _parse_flags(args)
    if not OUT_DIR.is_dir():
        print(f"## out-clean: nichts zu tun — {OUT_DIR} existiert nicht\n")
        return 0
    if f.get("all"):
        removed = 0
        for p in OUT_DIR.rglob("*"):
            try:
                if p.is_file():
                    p.unlink()
                    removed += 1
            except OSError:
                continue
        _drop_empty_out_dirs()
        print(f"## out-clean: {removed} Datei(en) geloescht — {OUT_DIR} geleert\n")
        return 0
    removed = _prune_out_dir()
    rest = sum(1 for p in OUT_DIR.rglob("*") if p.is_file())
    print(f"## out-clean: {removed} abgelaufene Datei(en) geloescht (aelter als "
          f"{OUT_MAX_AGE_HOURS}h), {rest} verbleiben — {OUT_DIR}\n")
    return 0


def _print_data(verb: str, resp, full: bool = False, out=None) -> None:
    """Druckt die Antwort einer Route als kompakten JSON-Block.

    Kürzt sehr lange Antworten auf 4000 Zeichen, weist die Kürzung dabei aber
    immer sichtbar mit Original-Größe aus — nie stilles Abschneiden. Der Schnitt
    liegt mitten im JSON, das Ergebnis ist also nicht mehr parsebar; wer die
    vollständige Antwort braucht, nimmt out (ungekürzt in Datei unter OUT_DIR,
    Konsole bleibt klein) oder full (ungekürzt auf stdout).
    """
    payload = resp.get("data", resp) if isinstance(resp, dict) else resp
    text = json.dumps(payload, ensure_ascii=False, indent=2)

    if out:
        path = _out_path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        pruned = _prune_out_dir()
        written = path.write_text(text, encoding="utf-8")
        note = f" · {pruned} abgelaufene aufgeraeumt" if pruned else ""
        print(f"## {verb}: vollständiges JSON geschrieben — {path} ({written} Zeichen){note}\n")
        return

    print(f"## {verb}")
    print("```json")
    if len(text) > 4000 and not full:
        print(text[:4000])
        print(f"[gekürzt: 4000 von {len(text)} Zeichen — --full oder --out <datei> für die volle Antwort]")
    else:
        print(text)
    print("```\n")


def _run_table_verb(verb: str, spec: tuple, args: list, body_extra: dict = None) -> int:
    """Generischer Executor für TABLE_VERBS.

    spec = (method, path_template, n_path_args, body_mode, use_query)
      - path_template nutzt '{}' für (max. 1) Pfad-Argument (aus --id oder erstem Positional)
      - body_mode: None | 'file' (--file = JSON-Body) | 'ids' (--ids 1,2,3 -> {ids:[...]})
      - use_query: True -> übrige --flags werden als Query-String angehängt

    body_extra ergänzt den Body um Felder, die nicht aus der --file-Datei kommen
    (--concept <id> beim Lite-Lauf). Es überschreibt gleichnamige
    Felder der Datei, damit das Flag am Aufruf gewinnt und nicht still verpufft.

    Bei GET-Verben stehen zusätzlich --out [datei] und --full zur Verfügung (gleiche
    Semantik wie beim generischen `api`-Verb, siehe _print_data). Beide Flags fließen
    NIE in den Query-String ein, auch nicht bei use_query=True. Für Nicht-GET-Verben
    (Schreiben/Löschen/Aktionen) gibt es keine gekappte Ausgabe, die --out/--full
    aufheben könnte — hier wird ein Fehler geworfen statt die Flags still zu schlucken.
    GEÄNDERT: Ausnahme WRITE_VERBS_ALLOW_OUT: schreibfreie POST-Verben wie
    playground-run-backtest-lite persistieren serverseitig nichts, ihre Antwort darf
    trotzdem wie bei GET lang werden und über --out/--full ungekürzt rausgehen.

    --timeout <s> überschreibt den Timeout für diesen einen Aufruf (Default: der
    Verb-spezifische Wert aus VERB_TIMEOUT_OVERRIDES, sonst der globale TIMEOUT).
    Läuft der Aufruf für einen Verb mit Override in den Timeout, weist
    die Fehlermeldung auf die wahrscheinliche Ursache (Numba-Warmup) hin.
    """
    method, path_tmpl, n_path, body_mode, use_query = spec
    f = _parse_flags(args)
    pos = f.get("_positional", [])
    full = bool(f.get("full"))
    out = f.get("out")
    if out and full:
        raise ValueError(f"{verb}: --out und --full schließen sich aus")
    if (out or full) and method != "GET" and verb not in WRITE_VERBS_ALLOW_OUT:
        raise ValueError(f"{verb}: --out/--full gibt es nur bei Lese-Verben (GET)")
    timeout_flag = f.get("timeout")
    timeout = int(timeout_flag) if timeout_flag else VERB_TIMEOUT_OVERRIDES.get(verb, TIMEOUT)
    fmt_args = []
    if n_path:
        val = f.get("id")
        if val is None and pos:
            val = pos[0]
        if val is None:
            raise ValueError(f"{verb}: ID fehlt (--id <n> oder als erstes Argument)")
        fmt_args.append(val)
    path = path_tmpl.format(*fmt_args)

    if use_query:
        q = {}
        for k, v in f.items():
            if k in ("file", "id", "ids", "_positional", "out", "full", "timeout"):
                continue
            q[k] = "true" if v is True else v
        if q:
            path += ("&" if "?" in path else "?") + urllib.parse.urlencode(q)

    body = None
    if body_mode == "file":
        body = _read_json_file(_require(f, "file", verb))
    elif body_mode == "ids":
        raw = f.get("ids") or (pos[0] if pos else None)
        if not raw:
            raise ValueError(f"{verb}: --ids 1,2,3 fehlt")
        body = {"ids": [int(x) for x in str(raw).split(",") if x.strip()]}
    if body_extra:
        body = {**(body or {}), **body_extra}

    try:
        resp = request(method, path, body, timeout=timeout)
    except (TimeoutError, urllib.error.URLError) as e:
        is_timeout = isinstance(e, TimeoutError) or isinstance(getattr(e, "reason", None), TimeoutError)
        if is_timeout and verb in VERB_TIMEOUT_OVERRIDES:
            raise TimeoutError(
                f"{verb}: Zeitüberschreitung nach {timeout}s — wahrscheinliche Ursache: "
                "Numba-Warmup nach Container-Start (der Server rechnet ggf. weiter). "
                "Mit --timeout <s> höher setzen oder erneut versuchen."
            ) from e
        raise
    if method == "GET" or out or full:
        _print_data(verb, resp, full=full, out=out)
    else:
        payload = resp.get("data", resp) if isinstance(resp, dict) else resp
        print(f"## {verb}: OK — {json.dumps(payload, ensure_ascii=False)[:300]}\n")
    return 0


def api_call(args: list) -> int:
    """Generischer Direktaufruf: api <METHOD> <pfad> [--file body.json] [--out [datei.json] | --full].

    Erreicht JEDE Route — auch solche ohne eigenes Verb und künftige.
    Die Anzeige kappt lange Antworten bei 4000 Zeichen (unparsebar!). Für die
    vollständige Antwort: --out (ungekürzt in eine Datei unter OUT_DIR, Konsole nur
    Pfad + Zeichenzahl — kontextschonend; ohne Wert Auto-Name mit Zeitstempel) oder
    --full (ungekürzt auf stdout). Der Ordner räumt sich selbst auf, siehe out-clean.
    """
    if len(args) < 2:
        raise ValueError("api braucht <METHOD> <pfad> (z.B. api GET /api/backtest/runs)")
    method = args[0].upper()
    path = args[1]
    if not path.startswith("/"):
        path = "/" + path
    f = _parse_flags(args[2:])
    full = bool(f.get("full"))
    out = f.get("out")
    if out and full:
        raise ValueError("api: --out und --full schließen sich aus")
    body = _read_json_file(f["file"]) if f.get("file") else None
    resp = request(method, path, body)
    _print_data(f"api {method} {path}", resp, full=full, out=out)
    return 0


def playground_run_backtest_lite(args: list) -> int:
    """Lite-Sondierung mit optionaler Zuordnung zum Konzept.

    Zusätzlich zum generischen Verhalten (siehe `_run_table_verb` und die
    Verb-Beschreibung im Modul-Docstring) nimmt das Verb `--concept <id>`: die ID
    wandert als `concept_id` in den Request-Body, der Server zählt die Sondierung
    am Konzept mit (`strategy_concepts.probe_count`) und gibt den neuen Stand als
    `concept_probe_count` zurück. Ohne `--concept` bleibt alles unverändert.

    Args:
        args: CLI-Argumente hinter dem Verb.

    Returns:
        Exit-Code (0 = OK).
    """
    f = _parse_flags(args)
    body_extra = {}
    concept = f.get("concept")
    if concept is not None:
        if concept is True:
            raise ValueError("playground-run-backtest-lite: --concept braucht eine Konzept-ID")
        body_extra["concept_id"] = int(concept)
    return _run_table_verb(
        "playground-run-backtest-lite",
        TABLE_VERBS["playground-run-backtest-lite"],
        args,
        body_extra=body_extra,
    )


# Flag-Body-Handler: Bodies aus mehreren Skalar-Flags (kein --file).

def walk_forward_start(args: list) -> int:
    f = _parse_flags(args)
    body = {"result_id": int(_require(f, "result", "walk-forward-start"))}
    if f.get("months"):
        body["months"] = int(f["months"])
    if f.get("metric"):
        body["metric"] = f["metric"]
    d = post("/api/backtest/walk-forward", body)["data"]
    print(f"## Gestartet: Walk-Forward-Run **{d['run_id']}** "
          f"(aus Result {d.get('parent_result_id')}, {d.get('start')} → {d.get('end')})\n")
    return 0


def run_remarks_set(args: list) -> int:
    f = _parse_flags(args)
    pos = f.get("_positional", [])
    rid = f.get("id") or (pos[0] if pos else None)
    if not rid:
        raise ValueError("run-remarks: ID fehlt (--id <n> oder erstes Argument)")
    text = _require(f, "text", "run-remarks")
    request("PUT", f"/api/backtest/runs/{int(rid)}/remarks", {"remarks": text})
    print(f"## run-remarks: OK — Run {int(rid)} Bemerkung gesetzt\n")
    return 0


def _data_jobs_wait(created: list, timeout: int) -> int:
    """Wartet auf das Ende angelegter OHLC-Jobs und druckt die Bilanz.

    Geteilte Wartelogik für data-update UND data-download: pollt den Job-Status im
    5s-Abstand (wie run_wait/significance_start), bis alle Jobs 'completed' oder
    'failed' sind oder das Timeout greift.

    Args:
        created: Liste von {id, symbol, rq_job_id} aus der Anlege-Antwort.
        timeout: Maximale Wartezeit in Sekunden.

    Returns:
        Exit-Code: 0 alle erfolgreich, 1 mindestens ein Fehlschlag, 2 Timeout.
    """
    import time as _time
    symbol_by_id = {c["id"]: c["symbol"] for c in created}
    pending = set(symbol_by_id)
    total = len(pending)
    poll_interval = 5
    print(f"## data-wait — {total} Job(s) · Timeout {timeout}s")
    t0 = _time.monotonic()
    last: dict = {}
    while pending:
        items = fetch("/api/config/data/jobs?limit=200")["data"]["items"]
        by_id = {it["id"]: it for it in items}
        for jid in list(pending):
            job = by_id.get(jid)
            if job is None:
                continue
            last[jid] = job
            if job.get("status") in ("completed", "failed"):
                pending.discard(jid)
        if not pending:
            break
        if _time.monotonic() - t0 > timeout:
            offen = ", ".join(symbol_by_id[j] for j in sorted(pending))
            print(f"- **TIMEOUT** nach {int(_time.monotonic() - t0)}s — noch offen: {offen}\n")
            return 2
        _time.sleep(poll_interval)

    print(f"- Fertig nach {int(_time.monotonic() - t0)}s\n")
    succeeded, failed = [], []
    for jid, symbol in symbol_by_id.items():
        job = last.get(jid, {})
        if job.get("status") == "completed":
            succeeded.append(symbol)
        else:
            reason = job.get("message") or "kein Status ermittelt"
            failed.append((symbol, reason))

    print(f"- Bilanz: {total} gesamt, {len(succeeded)} erfolgreich, {len(failed)} fehlgeschlagen")
    for symbol, reason in sorted(failed):
        print(f"  - {symbol}: {reason}")
    print()
    return 1 if failed else 0


def data_update(args: list) -> int:
    """Legt je Symbol der Datei einen Update-Job an; optional --wait auf die Bilanz."""
    f = _parse_flags(args)
    body = {"exchange": f.get("exchange", "binance"), "timeframe": _require(f, "timeframe", "data-update")}
    d = post("/api/config/data/update", body)["data"]
    jobs = d.get("jobs", [])
    print(f"## data-update: OK — {len(jobs)} Job(s) angelegt (id {d.get('id')})\n")
    if not f.get("wait"):
        return 0
    return _data_jobs_wait(jobs, int(f.get("timeout", 1800)))


def data_download(args: list) -> int:
    """Legt Download-Jobs per --file an; optional --wait auf die Bilanz.

    Eigener Handler statt des generischen TABLE_VERBS-Executors, weil --wait/--timeout
    zusätzliche, nicht body-relevante Flags sind (wie bei playground-run-backtest-lite).
    """
    f = _parse_flags(args)
    body = _read_json_file(_require(f, "file", "data-download"))
    d = post("/api/config/data/download", body)["data"]
    jobs = d.get("jobs", [])
    print(f"## data-download: OK — {len(jobs)} Job(s) angelegt (id {d.get('id')})\n")
    if not f.get("wait"):
        return 0
    return _data_jobs_wait(jobs, int(f.get("timeout", 1800)))


def data_delete_symbol(args: list) -> int:
    f = _parse_flags(args)
    body = {
        "exchange": f.get("exchange", "binance"),
        "timeframe": _require(f, "timeframe", "data-delete-symbol"),
        "symbol": _require(f, "symbol", "data-delete-symbol"),
    }
    d = request("POST", "/api/config/data/delete-symbol", body).get("data", {})
    print(f"## data-delete-symbol: OK — {d}\n")
    return 0


def result_delete_all(args: list) -> int:
    """Löscht Results außer Favoriten — global oder eingegrenzt.

    Ohne Flag: unverändertes globales Verhalten (Hintergrund-Job über die komplette
    Tabelle, HTTP 202). Mit --run <id> ODER --testset-run <id> (schließen sich aus):
    synchrone, auf die Menge eingegrenzte Löschung — Favoriten (gelb und rot) sowie
    fremde Objekte bleiben unberührt; die Antwort benennt deleted_results/
    deleted_runs/deleted_run_ids (Scope-Regel: kein globaler Orphan-Sweep).
    """
    f = _parse_flags(args)
    if f.get("run") and f.get("testset-run"):
        raise ValueError("result-delete-all: --run und --testset-run schließen sich aus")
    params = {}
    if f.get("run"):
        params["run_id"] = int(f["run"])
    elif f.get("testset-run"):
        params["testset_run_id"] = int(f["testset-run"])
    path = "/api/backtest/results"
    if params:
        path += "?" + urllib.parse.urlencode(params)
    payload = request("DELETE", path)
    print(f"## result-delete-all: OK — {json.dumps(payload, ensure_ascii=False)[:300]}\n")
    return 0


def analyse_screenshot(args: list) -> int:
    """Analyse-Screenshot einer Run-Ansicht: ruft nur die Screenshot-Route
    und schreibt das gelieferte PNG an den in --out genannten Pfad.

    analyse-screenshot --run <id> --x <param> --y <param> [--metric <kennzahl>]
                        [--agg <max|avg>] --out <pfad>

    --out nutzt dieselbe _out_path()-Semantik wie die übrigen Verben: ein absoluter
    Pfad wird wörtlich genommen (kein Umweg über OUT_DIR), ein relativer/reiner
    Dateiname landet dort. Die Datei wird erst geschrieben, wenn die Antwort ein
    gültiges PNG ist — scheitert die Route (Run ohne Results, ungültiger Achsenname,
    Renderer-Timeout), bleibt nichts Halbes/Leeres auf der Platte liegen; der
    HTTPError-Body mit dem Klartext-Grund der Route läuft über die zentrale
    Fehlerbehandlung in main() unverändert durch.
    """
    f = _parse_flags(args)
    run_id = _require(f, "run", "analyse-screenshot")
    x = _require(f, "x", "analyse-screenshot")
    y = _require(f, "y", "analyse-screenshot")
    out = _require(f, "out", "analyse-screenshot")

    query = {"x": x, "y": y}
    if f.get("metric") not in (None, True):
        query["metric"] = f["metric"]
    if f.get("agg") not in (None, True):
        query["agg"] = f["agg"]

    path = f"/api/backtest/runs/{run_id}/analyse/screenshot?{urllib.parse.urlencode(query)}"
    timeout = (
        int(f["timeout"]) if f.get("timeout") not in (None, True)
        else VERB_TIMEOUT_OVERRIDES.get("analyse-screenshot", TIMEOUT)
    )

    req = urllib.request.Request(f"{BASE}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        content_type = r.headers.get("Content-Type", "")
        data = r.read()

    if not content_type.startswith("image/png"):
        raise ValueError(
            f"analyse-screenshot: keine PNG-Antwort (Content-Type {content_type or '—'}) "
            f"— nichts geschrieben"
        )

    target = _out_path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    print(f"## analyse-screenshot: PNG geschrieben — {target} ({len(data)} Bytes)\n")
    return 0


# ---------------------------------------------------------------------------
# Bearbeitungs-Verben (add/remove/change). Gemeinsames Muster: das aktuelle
# Objekt per GET holen, gezielt EINEN Teil aendern (ein Feld, einen Indikator,
# einen Stop, eine Regel-Bedingung) und zurueckschreiben. So muss nie der ganze
# Body von Hand neu gebaut werden. Server-PUTs sind teils partiell (concept,
# iteration), teils Voll-Replace (backtest-config) — der jeweilige Helfer kennt
# das und macht das Richtige.
# ---------------------------------------------------------------------------

def _require_id(f: dict, verb: str) -> int:
    """ID aus --id oder erstem Positional. Wirft, wenn keine da ist."""
    pos = f.get("_positional", [])
    val = f.get("id") or (pos[0] if pos else None)
    if val is None or val is True:
        raise ValueError(f"{verb}: ID fehlt (--id <n> oder als erstes Argument)")
    return int(val)


def _coerce_scalar(v: str):
    """String-Flagwert -> passender JSON-Typ. 'null'->None, 'true'/'false'->bool,
    ganze Zahl->int, Dezimal->float, sonst String. Fuer Feld-/Stop-Werte, deren
    Typ am CLI nicht explizit angegeben wird."""
    if v is True:
        return True
    s = str(v).strip()
    low = s.lower()
    if low in ("null", "none"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _iteration_get_spec(iid: int) -> dict:
    """spec_json einer Iteration holen (leeres Dict wenn None)."""
    return fetch(f"/api/strategy/iterations/{iid}")["data"].get("spec_json") or {}


def _iteration_put_spec(iid: int, spec: dict) -> dict:
    """spec_json partiell zurueckschreiben (nur dieses Feld, PUT ist exclude_unset)."""
    return request("PUT", f"/api/strategy/iterations/{iid}", {"spec_json": spec})["data"]


def _indicator_config_get_json(cid: int) -> dict:
    """config_json einer IndicatorConfig holen (leeres Dict wenn None)."""
    return fetch(f"/api/config/indicator/{cid}")["data"].get("config_json") or {}


def _indicator_config_patch_json(cid: int, cfg: dict) -> dict:
    """config_json per PATCH zurueckschreiben (Teil-Update, Rest der Config bleibt)."""
    return request("PATCH", f"/api/config/indicator/{cid}", {"config_json": cfg})["data"]


# --- Feld-set (Meta/flache Felder) ---

def concept_set(args: list) -> int:
    """concept-set --id N [--name ... --slug ... --category ... --description ... --status ...
    --goal <datei-oder-inline-json> --goal-prompt <datei-oder-text>]

    Partieller PUT: nur gesetzte Felder werden geschrieben (Server: exclude_none).
    """
    f = _parse_flags(args)
    cid = _require_id(f, "concept-set")
    body = {k: f[k] for k in ("name", "slug", "category", "description", "status") if k in f and f[k] is not True}
    # GEÄNDERT: --goal (JSON, Datei oder Inline) und --goal-prompt (Text, Datei oder Inline)
    if f.get("goal") and f["goal"] is not True:
        body["goal_json"] = json.loads(_read_file_or_inline(f["goal"]))
    if f.get("goal-prompt") and f["goal-prompt"] is not True:
        body["goal_prompt"] = _read_file_or_inline(f["goal-prompt"])
    if not body:
        raise ValueError("concept-set: mindestens ein Feld noetig (--name | --slug | --category | --description | --status | --goal | --goal-prompt)")
    d = request("PUT", f"/api/strategy/concepts/{cid}", body)["data"]
    print(f"## concept-set: OK — Konzept {d['id']} ({d.get('name')}) aktualisiert: {', '.join(body)}\n")
    return 0


def iteration_set(args: list) -> int:
    """iteration-set --id N [--version-name ... --description ... --status ...]

    Partieller PUT (Server: exclude_unset). Nur Meta-Felder — Indikatoren/Regeln
    laufen ueber die iteration-indicator-*/iteration-condition-*-Verben.
    """
    f = _parse_flags(args)
    iid = _require_id(f, "iteration-set")
    mapping = {"version-name": "version_name", "description": "description", "status": "status"}
    body = {dst: f[src] for src, dst in mapping.items() if src in f and f[src] is not True}
    if not body:
        raise ValueError("iteration-set: mindestens ein Feld noetig (--version-name | --description | --status)")
    d = request("PUT", f"/api/strategy/iterations/{iid}", body)["data"]
    name = d.get("version_name") or d.get("version")
    print(f"## iteration-set: OK — Iteration {d['id']} ({name}) aktualisiert: {', '.join(body)}\n")
    return 0


# Editierbare Felder der BacktestConfig (Voll-Replace-PUT -> GET, mergen, zurueck).
# GEÄNDERT: slippage/stop_exit_price/stop_order_type analog fees ergänzt.
_BACKTEST_FIELDS = (
    "name", "description", "symbol", "exchange", "timeframe", "start", "end",
    "ohlc_start", "ohlc_end", "size", "size_type", "init_cash", "fees",
    "slippage", "stop_exit_price", "stop_order_type",
)
# Kurz-Flags -> Feldname; numerische Felder werden gecastet.
_BACKTEST_NUMERIC = {"size": float, "init_cash": float, "fees": float, "slippage": float}


def backtest_config_set(args: list) -> int:
    """backtest-config-set --id N [--symbol ... --timeframe ... --fees ... --size ... --start ... --end ... --name ... ]

    BacktestConfig-PUT ist Voll-Replace: aktuelle Config holen, gesetzte Felder
    drueberlegen, kompletten Body zurueckschreiben. Stops liegen NICHT hier
    (die stecken in der IndicatorConfig unter _stops).
    """
    f = _parse_flags(args)
    cid = _require_id(f, "backtest-config-set")
    # Flag-Wert holen: akzeptiert Feldnamen in Unterstrich- ODER Bindestrich-Form
    # (--ohlc-start == ohlc_start), da _parse_flags die Bindestriche im Key belaesst.
    def _flag(field):
        for key in (field, field.replace("_", "-")):
            if key in f and f[key] is not True:
                return f[key]
        return None
    changed = {k for k in _BACKTEST_FIELDS if _flag(k) is not None}
    if not changed:
        opts = " | ".join("--" + x.replace("_", "-") for x in _BACKTEST_FIELDS)
        raise ValueError(f"backtest-config-set: mindestens ein Feld noetig ({opts})")
    cur = fetch(f"/api/config/backtest/{cid}")["data"]
    body = {k: cur.get(k) for k in _BACKTEST_FIELDS}
    for k in changed:
        v = _flag(k)
        body[k] = _BACKTEST_NUMERIC[k](v) if k in _BACKTEST_NUMERIC else v
    d = request("PUT", f"/api/config/backtest/{cid}", body)["data"]
    print(f"## backtest-config-set: OK — Backtest-Config {d['id']} ({d.get('name')}) aktualisiert: {', '.join(sorted(changed))}\n")
    return 0


# --- Indikatoren (dict-Sammlung) ---

def _merge_indicator_block(coll: dict, name: str, frag: dict, replace: bool) -> tuple:
    """Schreibt frag in coll[name] — als Merge (Default) oder Vollersatz (replace).

    Merge aktualisiert nur die im Fragment genannten Parameter; alles andere im
    bestehenden Block bleibt unangetastet. Damit verliert ein unvollstaendiges
    Fragment keine laufzeit-wirksamen Felder (z.B. tf, dessen Fehlen den Lauf mit
    ValueError abbricht). Neue Keys werden schlicht eingefuegt.

    Returns:
        (verb, block): verb beschreibt die Aktion fuer die Ausgabe, block ist der
        geschriebene Indikator-Block.
    """
    if name not in coll:
        coll[name] = frag
        return "hinzugefuegt", frag
    if replace:
        coll[name] = frag
        return "ersetzt", frag
    block = dict(coll[name])
    block.update(frag)
    coll[name] = block
    geaendert = ", ".join(sorted(frag))
    return f"aktualisiert ({geaendert})", block


def iteration_indicator_set(args: list) -> int:
    """iteration-indicator-set --id N --name <key> --file frag.json [--replace]

    Schreibt einen Indikator nach spec_json.indicators[key]. Existiert der Key,
    werden nur die im Fragment genannten Parameter aktualisiert, der Rest des
    Blocks bleibt bit-genau (Merge, wie indicator-config-stops-set). Mit --replace
    wird der Block komplett ersetzt. frag.json ist der Indikator-Block bzw. der zu
    aendernde Ausschnitt, z.B. {"timeperiod": 50} oder ein voller Block.
    """
    f = _parse_flags(args)
    iid = _require_id(f, "iteration-indicator-set")
    name = _require(f, "name", "iteration-indicator-set")
    frag = _read_json_file(_require(f, "file", "iteration-indicator-set"))
    spec = _iteration_get_spec(iid)
    inds = spec.setdefault("indicators", {})
    # GEÄNDERT: Merge statt Vollersatz — ein unvollstaendiges Fragment darf keine
    # bestehenden Parameter (z.B. tf) still verlieren. --replace erzwingt Vollersatz.
    verb, block = _merge_indicator_block(inds, name, frag, bool(f.get("replace")))
    _iteration_put_spec(iid, spec)
    print(f"## iteration-indicator-set: OK — Iteration {iid}: Indikator '{name}' {verb} ({block.get('indicator')})\n")
    return 0


def iteration_indicator_remove(args: list) -> int:
    """iteration-indicator-remove --id N --name <key>

    Entfernt einen Indikator aus spec_json.indicators. Warnt, wenn Regeln ihn
    noch referenzieren (indicator:<key>:...), bricht aber nicht ab.
    """
    f = _parse_flags(args)
    iid = _require_id(f, "iteration-indicator-remove")
    name = _require(f, "name", "iteration-indicator-remove")
    spec = _iteration_get_spec(iid)
    inds = spec.get("indicators", {})
    if name not in inds:
        raise ValueError(f"iteration-indicator-remove: Indikator '{name}' nicht vorhanden (da: {', '.join(inds) or '—'})")
    del inds[name]
    _iteration_put_spec(iid, spec)
    ref = f"indicator:{name}:"
    still = ref in json.dumps(spec.get("rules", {}))
    warn = f"  WARNUNG: Regeln referenzieren '{name}' noch ({ref}...)\n" if still else ""
    print(f"## iteration-indicator-remove: OK — Iteration {iid}: Indikator '{name}' entfernt\n{warn}")
    return 0


def indicator_config_indicator_set(args: list) -> int:
    """indicator-config-indicator-set --id N --name <key> --file frag.json [--replace]

    Schreibt einen Indikator nach config_json[key]. Existiert der Key, werden nur
    die im Fragment genannten Parameter aktualisiert, der Rest des Blocks bleibt
    bit-genau (Merge); --replace ersetzt den Block komplett. frag.json ist der
    Parameter-Block bzw. der zu aendernde Ausschnitt (Werte skalar ODER als
    arange-Range fuer Multiparameter), z.B. {"indicator": "talib:SMA", "tf": "same",
    "close": "close", "timeperiod": {"type":"arange","start":20,"stop":101,"step":10,"dtype":"int64"}}.
    """
    f = _parse_flags(args)
    cid = _require_id(f, "indicator-config-indicator-set")
    name = _require(f, "name", "indicator-config-indicator-set")
    if name == "_stops":
        raise ValueError("indicator-config-indicator-set: '_stops' ist reserviert — nutze indicator-config-stops-set")
    frag = _read_json_file(_require(f, "file", "indicator-config-indicator-set"))
    cfg = _indicator_config_get_json(cid)
    # GEÄNDERT: Merge statt Vollersatz — siehe _merge_indicator_block
    verb, block = _merge_indicator_block(cfg, name, frag, bool(f.get("replace")))
    _indicator_config_patch_json(cid, cfg)
    print(f"## indicator-config-indicator-set: OK — Config {cid}: Indikator '{name}' {verb} ({block.get('indicator')})\n")
    return 0


def indicator_config_indicator_remove(args: list) -> int:
    """indicator-config-indicator-remove --id N --name <key>

    Entfernt einen Indikator aus config_json. '_stops' ist geschuetzt.
    """
    f = _parse_flags(args)
    cid = _require_id(f, "indicator-config-indicator-remove")
    name = _require(f, "name", "indicator-config-indicator-remove")
    if name == "_stops":
        raise ValueError("indicator-config-indicator-remove: '_stops' nicht ueber dieses Verb entfernen")
    cfg = _indicator_config_get_json(cid)
    if name not in cfg:
        keys = [k for k in cfg if k != "_stops"]
        raise ValueError(f"indicator-config-indicator-remove: Indikator '{name}' nicht vorhanden (da: {', '.join(keys) or '—'})")
    del cfg[name]
    _indicator_config_patch_json(cid, cfg)
    print(f"## indicator-config-indicator-remove: OK — Config {cid}: Indikator '{name}' entfernt\n")
    return 0


# --- Stops (config_json._stops) ---

# Kurz-Flag -> _stops-Feld. Werte gecastet (null/Zahl); Formate bleiben String.
_STOP_FLAGS = {
    "tp": "tp_stop", "sl": "sl_stop", "td": "td_stop", "tsl": "tsl_stop",
    "tsl-th": "tsl_th", "delta-format": "delta_format", "time-delta-format": "time_delta_format",
}
_STOP_STRING_FIELDS = {"delta_format", "time_delta_format"}


def indicator_config_stops_set(args: list) -> int:
    """indicator-config-stops-set --id N [--tp .. --sl .. --td .. --tsl .. --tsl-th .. --delta-format .. --time-delta-format ..]

    Setzt einzelne Werte in config_json._stops; nicht genannte Stops bleiben.
    Zahlen/null werden gecastet, die Format-Felder bleiben String. 'null' loescht
    einen Stop-Wert (setzt ihn auf None).
    """
    f = _parse_flags(args)
    cid = _require_id(f, "indicator-config-stops-set")
    changed = {flag: dst for flag, dst in _STOP_FLAGS.items() if flag in f}
    if not changed:
        raise ValueError(f"indicator-config-stops-set: mindestens ein Stop noetig ({' | '.join('--' + x for x in _STOP_FLAGS)})")
    cfg = _indicator_config_get_json(cid)
    stops = cfg.setdefault("_stops", {})
    for flag, dst in changed.items():
        v = f[flag]
        stops[dst] = str(v) if dst in _STOP_STRING_FIELDS else _coerce_scalar(v)
    _indicator_config_patch_json(cid, cfg)
    print(f"## indicator-config-stops-set: OK — Config {cid}: _stops aktualisiert ({', '.join(changed[k] for k in changed)})\n")
    return 0


# --- Regeln (spec_json.rules) ---

def _rules_side(spec: dict, exit_side: bool) -> tuple:
    """Liefert (rules_dict, side_key). Legt rules/entry|exit-Geruest an, falls fehlt."""
    rules = spec.setdefault("rules", {})
    side = "exit" if exit_side else "entry"
    if not isinstance(rules.get(side), dict):
        rules[side] = {"blocks": []}
    rules[side].setdefault("blocks", [])
    return rules, side


def iteration_condition_add(args: list) -> int:
    """iteration-condition-add --id N [--exit] [--block K | --new-block [--short]] --file cond.json

    Haengt eine Bedingung an einen Regel-Block. Ohne --block: Block 1 (erster).
    --new-block legt einen neuen ODER-Block an (--short markiert ihn als Short).
    cond.json ist ein Bedingungs-Dict, z.B.
    {"op": ">", "lhs": "close", "rhs": "indicator:sma:real"} (optional lhs_shift/rhs_shift).
    """
    f = _parse_flags(args)
    iid = _require_id(f, "iteration-condition-add")
    cond = _read_json_file(_require(f, "file", "iteration-condition-add"))
    exit_side = bool(f.get("exit"))
    spec = _iteration_get_spec(iid)
    rules, side = _rules_side(spec, exit_side)
    blocks = rules[side]["blocks"]
    if f.get("new-block"):
        new_block = {"conditions": [cond]}
        if f.get("short"):
            new_block["is_short"] = True
        blocks.append(new_block)
        pos = len(blocks)
    else:
        if not blocks:
            blocks.append({"conditions": []})
        idx = int(f["block"]) - 1 if f.get("block") and f["block"] is not True else 0
        if idx < 0 or idx >= len(blocks):
            raise ValueError(f"iteration-condition-add: Block {idx + 1} existiert nicht ({len(blocks)} Bloecke)")
        blocks[idx].setdefault("conditions", []).append(cond)
        pos = idx + 1
    _iteration_put_spec(iid, spec)
    print(f"## iteration-condition-add: OK — Iteration {iid}: Bedingung in {side}-Block {pos} ({fmt_cond(cond)})\n")
    return 0


def iteration_condition_remove(args: list) -> int:
    """iteration-condition-remove --id N [--exit] --block K [--index J | --remove-block]

    Entfernt eine Bedingung (--index J, 1-basiert) aus einem Block, oder mit
    --remove-block den ganzen Block. Ohne --index und ohne --remove-block: Fehler.
    """
    f = _parse_flags(args)
    iid = _require_id(f, "iteration-condition-remove")
    exit_side = bool(f.get("exit"))
    if not f.get("block") or f["block"] is True:
        raise ValueError("iteration-condition-remove: --block K noetig")
    bidx = int(f["block"]) - 1
    spec = _iteration_get_spec(iid)
    rules = spec.get("rules", {})
    side = "exit" if exit_side else "entry"
    blocks = (rules.get(side) or {}).get("blocks") or []
    if bidx < 0 or bidx >= len(blocks):
        raise ValueError(f"iteration-condition-remove: {side}-Block {bidx + 1} existiert nicht ({len(blocks)} Bloecke)")
    if f.get("remove-block"):
        blocks.pop(bidx)
        _iteration_put_spec(iid, spec)
        print(f"## iteration-condition-remove: OK — Iteration {iid}: {side}-Block {bidx + 1} entfernt ({len(blocks)} verbleiben)\n")
        return 0
    if not f.get("index") or f["index"] is True:
        raise ValueError("iteration-condition-remove: --index J (1-basiert) oder --remove-block noetig")
    cidx = int(f["index"]) - 1
    conds = blocks[bidx].get("conditions") or []
    if cidx < 0 or cidx >= len(conds):
        raise ValueError(f"iteration-condition-remove: Bedingung {cidx + 1} in Block {bidx + 1} existiert nicht ({len(conds)} Bedingungen)")
    removed = conds.pop(cidx)
    _iteration_put_spec(iid, spec)
    print(f"## iteration-condition-remove: OK — Iteration {iid}: Bedingung {cidx + 1} aus {side}-Block {bidx + 1} entfernt ({fmt_cond(removed)})\n")
    return 0


# Deklarative Tabelle: verb -> (METHOD, pfad_template, n_pfad_args, body_mode, use_query)
TABLE_VERBS = {
    # Ändern (PUT, voller Body per --file)
    "concept-update": ("PUT", "/api/strategy/concepts/{}", 1, "file", False),
    "iteration-update": ("PUT", "/api/strategy/iterations/{}", 1, "file", False),
    "backtest-config-update": ("PUT", "/api/config/backtest/{}", 1, "file", False),
    "indicator-config-update": ("PUT", "/api/config/indicator/{}", 1, "file", False),
    "strategy-config-update": ("PUT", "/api/config/strategy/{}", 1, "file", False),
    "testset-update": ("PUT", "/api/testsets/{}", 1, "file", False),
    "playground-setup-update": ("PUT", "/api/chart-playground/setups/{}", 1, "file", False),
    # Löschen (DELETE). concept/iteration unterstützen --force und --delete_vault.
    "concept-delete": ("DELETE", "/api/strategy/concepts/{}", 1, None, True),
    "iteration-delete": ("DELETE", "/api/strategy/iterations/{}", 1, None, True),
    "backtest-config-delete": ("DELETE", "/api/config/backtest/{}", 1, None, False),
    "indicator-config-delete": ("DELETE", "/api/config/indicator/{}", 1, None, False),
    "strategy-config-delete": ("DELETE", "/api/config/strategy/{}", 1, None, False),
    "result-delete": ("DELETE", "/api/backtest/results/{}", 1, None, False),
    "run-delete": ("DELETE", "/api/backtest/runs/{}", 1, None, False),
    "run-delete-all": ("DELETE", "/api/backtest/runs", 0, None, False),
    "testset-delete": ("DELETE", "/api/testsets/{}", 1, None, False),
    "leaderboard-delete": ("DELETE", "/api/leaderboard/{}", 1, None, False),
    "playground-setup-delete": ("DELETE", "/api/chart-playground/setups/{}", 1, None, False),
    "knowledge-reset": ("DELETE", "/api/knowledge/reset", 0, None, False),
    # Sammellöschen (POST, --ids 1,2,3)
    "indicator-config-bulk-delete": ("POST", "/api/config/indicator/bulk-delete", 0, "ids", False),
    "result-bulk-delete": ("POST", "/api/backtest/results/bulk-delete", 0, "ids", False),
    "run-bulk-delete": ("POST", "/api/backtest/runs/bulk-delete", 0, "ids", False),
    "playground-setup-bulk-delete": ("POST", "/api/chart-playground/setups/bulk-delete", 0, "ids", False),
    # Aktionen / Toggles (POST, kein Body)
    # GEÄNDERT: iteration-favorite/iteration-doc-favorite/result-favorite/
    # result-doc-favorite sind keine TABLE_VERBS-Toggles mehr, sondern eigene, idempotent
    # setzende SINGLE_VERBS (siehe _favorite_set weiter oben). Die zugrundeliegenden
    # Toggle-Routen bleiben unveraendert fuer den manuellen Frontend-Stern.
    "indicator-config-generate-labels": ("POST", "/api/config/indicator/{}/generate-labels", 1, None, False),
    "concept-vault-create": ("POST", "/api/strategy/concepts/{}/vault-create", 1, None, False),
    "iteration-vault-create": ("POST", "/api/strategy/iterations/{}/vault-create", 1, None, False),
    "run-restart": ("POST", "/api/backtest/runs/{}/restart", 1, None, False),
    "run-resume": ("POST", "/api/backtest/runs/{}/resume", 1, None, False),
    "run-analyse-start": ("POST", "/api/backtest/runs/{}/analyse/start", 1, None, False),
    "run-analyse-stop": ("POST", "/api/backtest/runs/{}/analyse/stop", 1, None, False),
    "run-analyse-reset": ("POST", "/api/backtest/runs/{}/analyse/reset", 1, None, False),
    # Anlegen (POST, voller Body per --file)
    "strategy-config-create": ("POST", "/api/config/strategy", 0, "file", False),
    # GEÄNDERT: Route-Spec bleibt hier (Dokumentation), ausgeführt wird
    # das Verb aber über den eigenen Handler in SINGLE_VERBS, weil --wait/--timeout
    # zusätzliche Flags sind, die der generische --file-Executor nicht kennt.
    "data-download": ("POST", "/api/config/data/download", 0, "file", False),
    "playground-setup-create": ("POST", "/api/chart-playground/setups", 0, "file", False),
    "playground-compute": ("POST", "/api/chart-playground/compute", 0, "file", False),
    "playground-run-backtest": ("POST", "/api/chart-playground/run-backtest", 0, "file", False),
    # GEÄNDERT: Route-Spec bleibt hier, ausgeführt wird das Verb aber über
    # den eigenen Handler in SINGLE_VERBS (playground_run_backtest_lite), weil --concept
    # ein zusätzliches Body-Feld erzeugt. SINGLE_VERBS wird zuerst geprüft.
    "playground-run-backtest-lite": ("POST", "/api/chart-playground/run-backtest-lite", 0, "file", False),
    "knowledge-reindex": ("POST", "/api/knowledge/reindex", 0, None, False),
    # Lesen (GET)
    "strategy-config-list": ("GET", "/api/config/strategy", 0, None, False),
    "data-files-list": ("GET", "/api/config/data/files", 0, None, False),
    "data-jobs-list": ("GET", "/api/config/data/jobs", 0, None, True),
    "filters-list": ("GET", "/api/backtest/filters", 0, None, False),
    "run-results": ("GET", "/api/backtest/runs/{}/results", 1, None, True),
    "result-stats": ("GET", "/api/backtest/results/{}/stats", 1, None, False),
    "result-trades": ("GET", "/api/backtest/results/{}/trades", 1, None, False),
    "result-orders": ("GET", "/api/backtest/results/{}/orders", 1, None, False),
    "result-positions": ("GET", "/api/backtest/results/{}/positions", 1, None, False),
    "result-ohlcv": ("GET", "/api/backtest/results/{}/ohlcv", 1, None, False),
    "result-chart-data": ("GET", "/api/backtest/results/{}/chart-data", 1, None, False),
    "run-summary": ("GET", "/api/backtest/runs/{}/analyse/summary", 1, None, False),
    "run-distribution": ("GET", "/api/backtest/runs/{}/analyse/distribution", 1, None, False),
    "run-equity-overview": ("GET", "/api/backtest/runs/{}/analyse/equity-overview", 1, None, True),
    "run-heatmap": ("GET", "/api/backtest/runs/{}/analyse/heatmap", 1, None, True),
    "run-analyse-progress": ("GET", "/api/backtest/runs/{}/analyse/progress", 1, None, False),
    "knowledge-runs-list": ("GET", "/api/knowledge/runs", 0, None, False),
    "knowledge-run": ("GET", "/api/knowledge/runs/{}", 1, None, False),
    "knowledge-stats": ("GET", "/api/knowledge/stats", 0, None, False),
    "playground-sources": ("GET", "/api/chart-playground/sources", 0, None, False),
    "playground-ohlcv": ("GET", "/api/chart-playground/ohlcv", 0, None, True),
    "playground-setup-list": ("GET", "/api/chart-playground/setups", 0, None, False),
}


# Einzel-Verben mit eigener Argument-Form (Liste/Create/Start). Erstes CLI-Argument.
SINGLE_VERBS = {
    "api": api_call,
    "out-clean": out_clean,
    # GEÄNDERT: eigener Handler wegen --concept (Body-Feld concept_id)
    "playground-run-backtest-lite": playground_run_backtest_lite,
    "walk-forward-start": walk_forward_start,
    "run-remarks": run_remarks_set,
    "data-update": data_update,
    "data-download": data_download,
    "data-delete-symbol": data_delete_symbol,
    "result-delete-all": result_delete_all,
    "analyse-screenshot": analyse_screenshot,
    "concept-list": concept_list,
    "iteration-list": iteration_list,
    "backtest-config-list": backtest_config_list,
    "indicator-config-list": indicator_config_list,
    "result-list": result_list,
    "run-list": run_list,
    "testset-list": testset_list,
    "leaderboard-list": leaderboard_list,
    "symbol-list": symbol_list,
    "symbol-correlation": symbol_correlation,
    "playground-indicators": playground_indicators_list,
    "run-parameter-ranking": run_parameter_ranking,
    "run-top-results": run_top_results,
    "run-best": run_best,
    "run-bestwerte": run_bestwerte,
    "run-favorites-reset": run_favorites_reset,
    "run-favorites-list": run_favorites_list,
    "result-doc-favorite": result_doc_favorite_set,
    "result-favorite": result_favorite_set,
    "iteration-doc-favorite": iteration_doc_favorite_set,
    "iteration-favorite": iteration_favorite_set,
    "vergleichstabelle": vergleichstabelle,
    "result-lookup": result_lookup,
    "result-query": result_query,
    "kreuztest": kreuztest,
    "combo-trace": combo_trace,
    "concept-create": concept_create,
    "iteration-create": iteration_create,
    "iteration-log-add": iteration_log_add,
    "iteration-log-list": iteration_log_list,
    "befund": befund_read,
    "indicator-config-create": indicator_config_create,
    "indicator-config-set": indicator_config_set,
    "indicator-config-labels": indicator_config_labels,
    # Bearbeitungs-Verben (add/remove/change): GET -> gezielt aendern -> zurueckschreiben
    "concept-set": concept_set,
    "iteration-set": iteration_set,
    "backtest-config-set": backtest_config_set,
    "iteration-indicator-set": iteration_indicator_set,
    "iteration-indicator-remove": iteration_indicator_remove,
    "indicator-config-indicator-set": indicator_config_indicator_set,
    "indicator-config-indicator-remove": indicator_config_indicator_remove,
    "indicator-config-stops-set": indicator_config_stops_set,
    "iteration-condition-add": iteration_condition_add,
    "iteration-condition-remove": iteration_condition_remove,
    "backtest-config-create": backtest_config_create,
    "testset-create": testset_create,
    "backtest-run-start": backtest_run_start,
    "testset-run-start": testset_run_start,
    "preflight": preflight_run,
    "run-wait": run_wait,
    "signifikanz-start": significance_start,
    "signifikanz": significance_read,
    "signifikanz-list": significance_list,
    "walk-forward-chain-start": walk_forward_chain_start,
    "walk-forward-chain": walk_forward_chain_read,
    "walk-forward-chain-list": walk_forward_chain_list,
}


HANDLERS = {
    "concept": concept_read,
    "iteration": iteration_read,
    "indicator-config": indicator_config_read,
    "backtest-config": backtest_config_read,
    "strategy-config": strategy_config_read,
    "result": result_read,
    "run": run_read,
    "testset": testset_read,
    "leaderboard": leaderboard_read,
    "playground-setup": playground_setup_read,
    "knowledge": knowledge_search,
    "vault": vault_list,
}


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    # Einzel-Verben (Liste/Create/Start): erstes Argument ist das Verb, jedes Verb
    # parst seine eigene Argument-Form. Zentrale Fehlerbehandlung inkl. Server-Body.
    verb = args[0].lower()
    if verb in SINGLE_VERBS:
        try:
            return SINGLE_VERBS[verb](args[1:])
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            print(f"## {verb} — HTTP {e.code} {e.reason}\n{body}\n")
            return 1
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
            print(f"## {verb} — {e}\n")
            return 1
        except Exception as e:
            print(f"## {verb} — Fehler: {e}\n")
            return 1

    # Tabellen-Verben (Ändern/Löschen/Aktionen/restliche Reads): generischer Executor.
    if verb in TABLE_VERBS:
        try:
            return _run_table_verb(verb, TABLE_VERBS[verb], args[1:])
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            print(f"## {verb} — HTTP {e.code} {e.reason}\n{body}\n")
            return 1
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
            print(f"## {verb} — {e}\n")
            return 1
        except Exception as e:
            print(f"## {verb} — Fehler: {e}\n")
            return 1

    # Verb-Modi: erstes Argument ist "copy" oder "create-indicator-config", Rest sind Ziel-IDs
    mode = "read"
    if args[0].lower() == "copy":
        mode = "copy"
        args = args[1:]
        if not args:
            print("## copy: keine Ziel-IDs angegeben (z.B. `copy iteration:2 backtest-config:553`)\n")
            return 2
    elif args[0].lower() == "create-indicator-config":
        mode = "create-indicator-config"
        args = args[1:]
        if not args:
            print("## create-indicator-config: keine Result-IDs angegeben (z.B. `create-indicator-config result:2706026:Sharpe`)\n")
            return 2
    if mode == "copy":
        print(f"# Kopier-Aktion (Ziel: {BASE})\n")
    elif mode == "create-indicator-config":
        print(f"# IndicatorConfig aus Result erstellen (Ziel: {BASE})\n")
    else:
        print(f"# Briefing (Quelle: {BASE})\n")

    # GEÄNDERT: optionales --k <n> für knowledge:-Aufrufe (Trefferzahl,
    # Default 5). Vorab aus den Positions-Argumenten herausgezogen, weil die
    # Flag-Syntax nicht ins <bereich>:<wert>-Muster der Briefing-Schleife passt.
    knowledge_k = 5
    filtered_args = []
    i = 0
    while i < len(args):
        if args[i] == "--k" and i + 1 < len(args):
            knowledge_k = int(args[i + 1])
            i += 2
        else:
            filtered_args.append(args[i])
            i += 1
    args = filtered_args

    rc = 0
    for a in args:
        if mode == "create-indicator-config":
            rid, seg = _parse_result_segment_arg(a)
            if not rid:
                print(f"## Konnte nicht parsen: `{a}` (erwartet result:ID oder result:ID:Segment)\n")
                rc = 1
                continue
            try:
                indicator_config_create_from_result(rid, seg)
            except urllib.error.HTTPError as e:
                print(f"## result:{rid} — HTTP {e.code} {e.reason}\n")
                rc = 1
            except Exception as e:
                print(f"## result:{rid} — Fehler: {e}\n")
                rc = 1
            continue
        t, val = parse_arg(a)
        if not t:
            print(f"## Konnte nicht parsen: `{a}`\n")
            rc = 1
            continue
        if mode == "copy":
            handler = COPY_HANDLERS.get(t)
            if not handler:
                print(f"## copy {t}:{val} — nicht kopierbar (kein Copy-Endpoint; kopierbar: iteration, backtest-config, indicator-config)\n")
                rc = 1
                continue
        else:
            handler = HANDLERS[t]
        try:
            if t == "knowledge":
                handler(val, knowledge_k)
            else:
                handler(val)
        except urllib.error.HTTPError as e:
            print(f"## {t}:{val} — HTTP {e.code} {e.reason}\n")
            rc = 1
        except Exception as e:
            print(f"## {t}:{val} — Fehler: {e}\n")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())

# Changelog

## [1.30.94] - 2026-07-14

### Added
- Analyse-Maske: Tabs an der Heatmap-Position mit neuem Chart-Tab (OHLC-Candles des Runs) (1.30.94)
- Runs-Übersicht: Filter nach Konzept und Iteration (1.30.93)
- Toolbox: api GET liefert lange Antworten vollständig (--out / --full) mit selbstaufräumendem Temp-Ordner (1.30.88)
- Favoriten-Stern für TestSets — Favoriten stehen in der TestSet-Liste und im Test-Set-Dropdown der Start-Maske oben (1.30.87)
- Chart-Playground: Button „Vollen Run starten" — Multiparameter-Lauf als Ad-hoc-Run aus dem aktuellen Playground-Zustand (1.30.85)
- Exit-freie Entry-Bewertung (MFE/MAE, First-Touch-Geometrie) als wiederverwendbares Analyse-Modul (1.30.81)
- Toolbox-Verb vergleichstabelle (Iterations-Vergleich aus Doku-Favoriten) plus Skill-Prozess für Analyse-Screenshots (1.30.80)
- Heatmap-Tooltip zeigt die Anzahl der aggregierten Backtests (1.30.76)

### Changed
- Backtest-Configs-Übersicht lädt sofort, Datenqualität wird pro Timeframe nachgereicht (1.30.90)
- Strategie-Doku fuer die normierte Iterationsentwicklung ergaenzt; zweite veraltete Docstring-Aussage korrigiert (Stop-Sweep-Guard existiert ebenfalls nicht) (1.30.83)
- Auto-Update in Runs- und Results-Tabelle standardmäßig aktiv; Worker-Replicas lokal auf 4 (1.30.78)

### Fixed
- Walk-Forward-Route: Indikator-Vorlauf blieb nicht erhalten (1.30.92)
- Leaderboard: Result-ID im Drilldown öffnet den Playground, Tabellen-Ladefehler behoben (1.30.91)
- Toolbox-Verb vergleichstabelle fasst mehrere Läufe einer Iteration je Symbol+Testset zu einer Zeile zusammen (1.30.89)
- Backtest-Queue überlebt das Hochfahren: Worker warten auf die Datenbank, Recovery holt verwaiste Runs zurück (1.30.86)
- Phantom-Grenzen-Audit der Rechen-Pipeline: falsche Raises-Behauptung in evaluate_rules korrigiert, zwei tote Parameter markiert (1.30.84)
- Veralteten Docstring in der Rules-Engine korrigiert: Multi-Combo mit Serien-Operanden in stateful Bedingungen wird NICHT abgewiesen (1.30.82)
- Results-Liste lud in der Default-Sortierung (ID) mehrere Sekunden — Tiebreaker machte den Primärschlüssel-Index unbrauchbar (1.30.79)
- DB-Snapshot-Import repariert (Restore in einer Transaktion), Fortschrittsanzeige ergänzt und Results-/Runs-Listen entscheidend beschleunigt (1.30.77)
- Heatmap auf der Analyse-Seite blieb dauerhaft beim Platzhalter haengen (1.30.75)


## [1.30.74] - 2026-07-12

### Added
- Runs-Tabelle: Filterzeile (Symbol/TF/Zeitraum/Size Type) und Size Type an der Indikator-Config (1.30.73)
- Results-Tabelle: Size Type in der Iterations-Zelle und als Filter (1.30.72)
- Config-Vergleich zeigt die Schrittweite von Wertebereichen (1.30.68)
- Vergleich mehrerer Indicator-Configs als Zeilen-Matrix im Modal (1.30.67)
- Chart-Playground: Bestehende Spec (Iteration) über einen Auswahl-Dialog überschreiben (1.30.61)
- Toolbox (ds-strategie-session): gezielte Bearbeitungsverben für Konzept, Iteration, IndicatorConfig und BacktestConfig (add/remove/change ohne kompletten Body) (1.30.59)

### Changed
- Runs-Tabelle: Datumsspalten Von/Bis im deutschen Format (1.30.74)
- Chart-Playground: Iteration-Dropdown zeigt Version statt ID; Indikatoren beim Result-Laden ausgeblendet (1.30.71)
- Results-Tabelle: Gesamtzahl mit deutschem Tausendertrennzeichen, Trades-Spalte zu TR mit Info-Icon (1.30.70)
- Chart-Playground: Iterations-Dropdowns absteigend sortiert und mit ID plus Versionsname beschriftet (1.30.65)

### Removed
- Frontend-Timeout des Schnellbacktests ersatzlos entfernt — das Frontend wartet auf die Server-Antwort (1.30.64)
- Playground: „Setup aus Result speichern" entfernt — Results werden nur noch über den flüchtigen Weg ?resultid= angesehen (1.30.56)
- Custom-Indikator dwsTrendlineTouch (TAP-Trendlinien-Touch) vollständig entfernt (1.30.55)

### Fixed
- Backtest-Jobs ohne Zeitlimit einreihen (job_timeout=-1), damit große Multiparameter-Läufe nicht mehr am RQ-Timeout scheitern (1.30.69)
- Toolbox: Indikator-Timeframe (tf) wird angezeigt, -indicator-set mergt statt zu ersetzen (1.30.66)
- Schnellbacktest rechnet genau eine Kombination: Startwert-Reduktion vor dem Runner-Aufruf (1.30.63)
- Indicator-Configs-Tabelle sortiert wieder absteigend nach ID (1.30.62)
- Getragene Ketten-Param-Level konsistent id-benennen — behebt 7x-Blowup der Portfolio-Spaltenzahl bei zugleich verkettetem und direkt referenziertem Indikator (Ticket 53) (1.30.60)
- Playground-Schnellbacktest: Listen-förmige Stops ließen alle Trade-Marker still verschwinden (Audit-Befund 8) (1.30.58)
- Playground: Grüner Entry-Hintergrund respektiert jetzt das Handelsfenster (start/end) (1.30.57)


## [1.30.54] - 2026-07-06

### Added
- Chart-Playground: Backtest-Config-Browser als Tabellen-Popup neben dem Dropdown (1.30.50)
- Backtest-Config-Tabelle: Auswahl per Checkbox, Download nur für angehakte Configs (1.30.48)
- Backtest-Config-Liste: Filter für Timeframe, Symbol, OHLC-Zeitfenster und Qualität (1.30.47)
- Testset-Detailseite: Spalten OHLC Start, OHLC End und Qualität in der Backtest-Config-Tabelle (1.30.43)
- Backtest-Configs: Bulk-Download aller OHLC-Daten und zeitraum-bezogene Datenqualitäts-Anzeige (1.30.42)
- Schrittweiter Nachbarschafts-Modus (--tolerance-steps) für Result-Lookup, Kreuztest und Combo-Trace (1.30.35)

### Changed
- OHLC-Job-Tabelle (Konfiguration -> OHLC-Daten) auf DataTable umgestellt mit Zähler, Status-Badges und Massenlöschung nach Status (1.30.49)
- Chart-Playground: Portfolio-Card als eigenständige Card unter die Analyse-Tabs verschoben und Dropdown-Höhe angeglichen (1.30.45)
- Indicator-Config-Tabelle umgestaltet und Beschreibungs-Freitext vorangestellt (1.30.41)
- Indikator-Konfiguration: Name/Beschreibung neu generiert, Dropdown-Beschreibung als schwebender Tooltip (1.30.40)
- Chart-Playground: Indikator-Konfigurations-Dropdown von nativem Select auf Custom-Dropdown mit Beschreibungsspalte umgebaut und nach Konzept/Iteration gefiltert (1.30.39)
- Chart-Playground: Preisachse mit vier Nachkommastellen bei Preisen unter 1 Euro und breitere Stops-Wertfelder (1.30.38)
- Chart-Playground: Anzeige-Timeframe und Zoom-Bereich werden im Setup gespeichert und beim Setup-Laden wiederhergestellt statt hart auf 1D+Fit zu setzen (1.30.37)

### Removed
- Veraltete Test-Datei tests/test_indicator_labels.py entfernt — sie prüfte die mit 1.30.40 abgelöste Label-Notation und schlug seitdem fehl (8 rote Tests) (1.30.52)

### Fixed
- Negative Shift-Werte in Rules-Conditions werden abgewiesen (Audit-Befund 3: Lookahead-Schutz) (1.30.54)
- Rules-Engine: '!='-Vergleich liefert bei NaN-Operanden keine Phantom-Signale mehr (1.30.53)
- Rules-Engine (nativer Pfad): disjunkte Entry-/Exit-Sweep-Achsen werden jetzt zum vollen Kreuzprodukt gekreuzt statt still falsch gerechnet (Audit-Befund 1, Ticket 51) (1.30.51)
- Chart-Playground: Race Condition im grünen Entry-Hintergrund behoben — überlappende Refreshes hinterließen verwaiste Overlays (1.30.46)
- Chart-Playground und Backtest-Runner: TA-Lib-Indikatoren wurden ab der ersten Datenlücke konstant (flache Linie), weil ein einzelnes durch Resampling entstandenes NaN via TA-Lib bis zum Serienende propagiert. Behoben durch NaN-sicheren Indikator-Lauf (skipna). (1.30.44)
- Label-Notation crasht nicht mehr bei Stop-Sweeps (preview-labels/generate-labels) (1.30.36)


## [1.30.34] - 2026-07-03

### Added
- Toolbox-Lücken: nachträgliche Indicator-Config-Verknüpfung, Label-Generierung mit Zusatz und persistiertes Bestwert-Kriterium am Doku-Favoriten (1.30.33)
- Result-Lookup per Parameter-Werten (API) und Auswerte-Verben für die Strategie-Toolbox (Favoriten-Liste, Metrik-Query, Kreuz-Test, Kombinations-Verfolgung, Plateau-Score, JSON-Ausgabe) (1.30.32)
- Chart-Playground: Umschalter JSON/Visuell für die Indikatoren- und Entry/Exit-Logic-Card (1.30.28)
- Ticket 50 angelegt: Toolbox-Indikator-Katalog filterbar machen (--group/--search), stille 4000-Zeichen-Kürzung in _print_data durch expliziten Kürzungs-Hinweis ersetzen (1.30.25)
- GUI für DB-Snapshot Export/Import unter Konfiguration (1.30.24)
- Benutzerhandbuch angelegt und Run-Analyse-Maske sprachlich geschärft (1.30.23)
- Job-Übersicht (Monitoring-Maske) für Queues, Worker und Job-Status (1.30.20)
- Reaper fuer verwaiste Recompute-Jobs plus Analyse-Seiten-UI (Status, Infobox, Toasts) (1.30.19)
- Reaper-Task raeumt verwaiste Recompute-Jobs automatisch auf (1.30.18)

### Changed
- Bestwert-Spalte in der Results-Tabelle verschlankt, sortierbar gemacht und dokumentiert; TP/SL sortierbar (1.30.34)
- Per-Indikator-Timeframe: „gleich“ ist jetzt der explizite Wert 'same' — null/fehlend bedeutet „Wert fehlt“ und schlägt bei der Verarbeitung sichtbar fehl (kein impliziter Fallback mehr) (1.30.29)
- Toolbox: Indikator-Katalog filterbar gemacht und stille 4000-Zeichen-Kürzung behoben (Ticket 50) (1.30.26)

### Fixed
- Indikator-Inputs mit Nicht-OHLCV-Namen (z.B. series_a/series_b bei custom:dwsCrossover) schlugen im Playground und Config-Editor fehl („Kein Mapping für Input") (1.30.31)
- Chart-Playground: Aktions-Buttons wieder am unteren Card-Rand, neue Indikatoren landen oberhalb der Stops-Zeile (1.30.30)
- Chart-Playground: Result-Laden zeigt konkrete Indikatorwerte des Results statt Sweep-Ranges des Laufs (1.30.27)
- Multiparameter-Lauf kreuzt getrennte Indikator-Achsen jetzt korrekt (Ticket 49) (1.30.22)
- Kombinationen-Anzahl beim Rerun eines Runs korrekt statt 0 anzeigen (1.30.21)
- Test-Suite collectet und läuft wieder vollständig durch (493 passed, 1 skipped) (1.30.17)
- Runs-Analyse: Parameter-Heatmaps blieben sporadisch leer ("Zwei verschiedene Parameter auswählen"), obwohl Results und variierte Parameter vorhanden waren (1.30.16)
- Obsidian-Deeplinks der Strategie-Konzepte-Seite öffnen wieder korrekt (vorher „Vault not found") (1.30.15)


## [1.30.14] - 2026-07-01

### Added
- 3D-Heatmap-Tab in der Run-Analyse plus Heatmap-Verbesserungen (1.30.14)
- Toolbox-Verb run-favorites-reset zum Zurücksetzen der Favoriten einer ganzen Run-Menge; Sharpe-Band der Bestwerte auf 10 Prozent verengt (1.30.13)
- Backtest-Runs-Tabelle: Spalte TR (Testset-Run-ID) links vor der ID-Spalte (1.30.9)
- Toolbox-Verb run-bestwerte: die vier kanonischen Bestwerte je Multiparameter-Lauf ziehen und idempotent als Doku-Favorit markieren (1.30.8)
- Runs nach Strategie+Version/Testset filterbar und sprechende Run-Labels (1.30.7)
- Onboarding-Installation: Ein-Aufruf-Setup, Auto-Migration und /install-Seite (1.30.0)
- Datei-Export/-Import für Strategie-Konzepte, Iterationen und Indicator-Configs (1.29.0)
- Globaler Lösch-Job-Toast: seitenübergreifende Fortschrittsanzeige mit Abbrechen-Button für Results-/Runs-Massenlöschung (1.28.6)
- Chart-Playground: Per-Indikator-Anzeige-Versatz (Versatz in Kerzen) in den erweiterten Optionen (1.28.3)

### Changed
- ds-strategie-session: Loop-Denken aus dem Skill entfernt, jede Maßnahme ist ein einzelnes Werkzeug (1.30.11)
- Strategie-Bewertung: Kriterien 2 und 3 der vier Bestwerte auf einheitliche Band-Mechanik umgestellt (1.30.10)
- Projekt-Rename von bt_pro_app_v1 auf bt_pro_app_v1 (Ordner, Docker-Projektname, Basis-Image) (1.30.6)
- Chart-Playground- und Konzept-UI angepasst, In-Position-Anzeige korrigiert und Auslieferungs-Baseline aktualisiert (1.30.5)
- Indikator-Konfiguration: Visueller Editor ist jetzt die Default-Ansicht beim Laden (1.29.1)
- Job 'Alle Runs/Results loeschen' auf TRUNCATE-Pfad umgestellt (~30x schneller, gibt Plattenplatz frei) (1.28.9)
- "Alle löschen" (Results/Runs) committet jetzt batchweise statt erst am Ende (1.28.8)

### Fixed
- Playground-Aufruf aus einem Result wählt Konzept, Iteration, Indicator-Config und Backtest-Config in den oberen Dropdowns wieder vor (1.30.12)
- Backtest-Start: Indicator-Config lud nicht mehr ("Fehler beim Laden") (1.28.7)
- Chart-Playground: Schnellbacktest bringt Candles und Indikatoren bei geändertem Basis-Timeframe erst auf Stand (1.28.5)
- Chart-Playground: Indikator-Timeframe feiner als Basis-Timeframe wird beim Laden korrigiert, Fehler-Anzeige vereinheitlicht (1.28.4)


## [1.28.2] - 2026-06-25

### Added
- OHLC-Download mit Einzel-Symbol-Jobs, Live-Intervall-Fortschritt und Aktualisieren-Button in der Backtest-Config (1.28.0)
- dwsTrendlineTouch (TAP-Methode): Zwei neue Parameter min_bars_between und dip_min_atr zur Trennung echter Trendlinien von Mini-Swings (1.26.12)
- Neuer Custom-Indikator custom:dwsSMI — Stochastic Momentum Index nach Blau (High/Low-Range-basiert, Skala ~+-100) als TAP-Filter. (1.26.0)
- Neuer Custom-Indikator custom:dwsTrendlineTouch (TAP-Methode) — erkennt die 3./4. Trendlinien-Beruehrung mit Abpraller. (1.25.0)

### Changed
- Chart-Playground: Hintergrund-Indikatoren werden als Custom Series Primitive gezeichnet statt als eine Serie pro Trend-Lauf (1.28.2)
- Per-Indikator-Timeframe (tf) im echten Spec-Runner scharf geschaltet — tf wirkt jetzt in Lauf UND Chart-Preview über denselben geteilten Helper (Preview == Lauf) (1.27.0)
- Chart-Playground: Per-Indikator-Timeframe (tf) im Preview nativ über vbt.Data.resample aufgelöst (1.26.13)
- Strategie-spezifische VWMA-Bezüge aus dem öffentlichen Code entfernt (Public-Repo-Hygiene) (1.26.10)
- Chart-Playground: Schnellbacktest-Button zeigt während der Berechnung einen drehenden Spinner mit Text 'Berechne...' statt nur 'Analysiert...' (1.26.9)
- Chart Playground: voller Backtest entfernt, nur noch Schnellbacktest (1.26.7)
- Projektweite Umstellung deutscher Textquellen auf echte Umlaute und verschärfte Sprach-Regel (1.26.6)
- Repo für Apache-2.0-Open-Source aufbereitet (1.26.5)
- Strategie-Doku: indicators.md aus dem Custom-Indikator-Workflow erreichbar gemacht + Fallstricke aus dem TAP-Build dokumentiert. (1.26.3)
- custom:dwsSMI nutzt jetzt eine Pine-exakte EMA (ta.ema-Seed) statt talib.EMA — bit-identisch zum TradingView-SMI ab dem ersten Balken. (1.26.2)
- custom:dwsSMI Defaults auf den TradingView-Standard-SMI angeglichen (k_length=10, smooth1=3, smooth2=3) — originalgetreu. (1.26.1)
- Chart-Playground: Anzeige-Schalter (Candles/Equity/Long/Short) als Toggle-Buttons in die Chart-Toolbar verschoben (1.24.0)

### Removed
- Toten Auto-Iterations-Registrierungs-Code entfernt, Lite-Backtest-Tests funktionsbenannt (1.26.8)
- Verwaiste Spec-Runner-Bring-up-Artefakte entfernt und Legacy-Baum zusaetzlich abgesichert (1.26.4)

### Fixed
- Chart-Playground: Beim Wechsel des Anzeige-Timeframes (visualTf) verschwanden die Candles mit lightweight-charts-Fehler "Value is null" (1.28.1)
- Kombinationszählung vereinheitlicht — eine Wahrheit statt sechs handgestrickter Zähler; Listen-Achsen und gekoppeltes TSL-Paar zählen jetzt korrekt (1.26.11)


## [1.23.0] - 2026-06-23

### Added
- Ticket 48: Aktiv-Schalter pro Regel-Block und Indikator im Chart-Playground (1.22.0)
- Playground: Spec als neue Iteration oder neues Konzept speichern (1.21.0)
- Strategie-Toolbox: Verben zur Bestwert-Auswertung von Multiparameter-Läufen (1.20.2)
- Ticket 47 (Teil 1): Short-Unterstützung im nativen Pfad (evaluate_rules_native) (1.19.0)
- Ticket 46: Short-Positionen im Masken-Pfad des Spec-Runners via is_short=True auf Entry/Exit-Blöcken (1.18.0)

### Changed
- Chart-Playground: Layout der Indikator-Cards und der Entry/Exit-Regelblöcke überarbeitet (1.23.0)
- Dokumentation und Strategie-Toolbox auf Rule-Block- und Indikator-enabled (Ticket 48) nachgezogen (1.22.1)
- Strategie-Konzepte: ID-Spalte vor Slug, Konzept-Zeilen starten zugeklappt (1.21.2)
- Playground: Slug- und Kategorie-Feld aus "Spec speichern"-Modal entfernt (1.21.1)
- Ticket 47 Phase 2: Einheitlicher nativer Pfad — Masken-Pfad aus spec_runner entfernt (1.20.0)
- Performance der Backtest-Results-Tabelle drastisch verbessert (Indizes + Query-Umbau) (1.17.41)

### Removed
- Tote services/api/schemas.py entfernt (vom gleichnamigen Package schemas/__init__.py verschattet, nie geladen) (1.17.44)

### Fixed
- Multi-Combo im nativen Spec-Runner-Pfad jetzt korrekt vektorisiert statt fehlerhaftem Single-Combo-Pre-Expand (Ticket 47) (1.20.1)
- Ticket 46: Short-Block-Guard greift jetzt auch im nativen Pfad (evaluate_rules_native) (1.18.1)
- Recompute speicherte Detail-Tabellen mehrfach (Faktor 3x) — recompute_single_result ist jetzt idempotent (1.17.45)
- Run-Dauer in der Runs-Liste zeigt jetzt die echte Verarbeitungszeit statt der Queue-Wartezeit (1.17.43)
- Results-Header zeigte bei run_id-Filter die Gesamtzahl; Runs-Liste zählte ineffizient (1.17.42)
- Fortschrittsanzeige beim Loeschen aller Backtest-Results ueberlebt jetzt einen Seiten-Reload (1.17.40)
- PROCESS.md Phase 1 (Idee) auf das neue Idee-Template und die Dateinamen-Konvention gezogen (1.17.39)
- Template-Verweise in Strategie-Workflow-Docs auf konsolidierten Vault-Ort umgebogen (1.17.38)


## [1.17.37] - 2026-06-19

### Added
- API-Endpunkt generate-labels für Indicator-Config-Notation (1.17.30)
- Button "Beschreibung generieren" auf der Indicator-Config-Seite (1.17.27)
- Spalte Leaderboard in der Testset-Liste zeigt pro Testset, ob ein Leaderboard-Eintrag erstellt wird (Ja/Nein-Badge) (1.17.24)
- Testset-Schalter leaderboard_enabled (Opt-in) steuert, ob ein abgeschlossener Testset-Lauf einen Leaderboard-Eintrag erzeugt (1.17.23)

### Changed
- ds-strategie-session-Skill generalisiert (Bedienung statt Methodik) + README um Bedienschicht-Hinweis ergänzt (1.17.34)
- Skill ds-strategie-session push-fähig gemacht: Homelab-spezifische Pfade generisch, Skill-Ordner aus der .claude-Sperre freigegeben (1.17.31)
- Beschreibung-Generierung: Stop-abhaengige Formate korrigiert (1.17.29)
- Indicator-Config: Titel- und Beschreibung-Generierung neu (1.17.28)
- Testset-Dropdown auf /backtest/start zeigt Leaderboard-Hinweis (1.17.26)
- Grundausstattungs-Daten-Load ans echte Ende der Migrationskette verschoben (neue Migration 0009), damit die Baseline testsets.leaderboard_enabled mit ausliefert (1.17.25)
- Lösch-Bestätigungsdialoge nennen jetzt explizit den Löschschutz-Status (1.17.22)

### Removed
- Nicht existentes Workflow-Feature (workflow-template/workflow-run) aus ds-strategie-session-Skill und toolbox.py entfernt (1.17.35)

### Fixed
- Iter-Note-Frontmatter-Beispiel in workflows/iteration.md auf das gelebte Schema gebracht (1.17.37)
- Strategie-Doku konsistent gemacht: Iter-Note-Pfade, App-URLs als Variable, veraltete Ports/Worker-Namen/Versionsschema (1.17.36)
- Iter-Note-Pfad-Konvention in Doku an gelebte Vault-Struktur angeglichen (Ordner pro Version) (1.17.33)
- ds-strategie-session: Iter-Note-Suche im Vault auf rekursiven Glob umgestellt (1.17.32)
- Zwei weitere veraltete Tests an aktuellen Code-Stand angeglichen (ticket22, ticket42) (1.17.18)


## [1.17.17] - 2026-06-18

### Added
- Chunk-Fortschrittsanzeige für laufende Backtest-Runs im Frontend (1.17.16)
- Runs-Seite: Spalte Indikator-Config mit Namen der verknüpften Konfiguration (1.17.15)
- Grundausstattung (Stammdaten-Seed) fuer Neuinstallationen: alle Backtest-Configs und Testsets kommen automatisch ueber eine Alembic-Daten-Migration in jede frische DB (1.17.9)
- TestSet-Liste: Klick auf das Configs-Badge öffnet ein Modal mit den enthaltenen Backtest-Configs (1.17.8)
- Ausgewählte Configs stehen in der TestSet-Maske beim Laden ganz oben (1.17.7)
- Timeframe-Filter-Dropdown in der TestSet-Config-Tabelle (Anlegen + Bearbeiten) (1.17.6)

### Changed
- Felder indicator_config_name und stops auch im /results-Endpoint mitliefern (1.17.14)
- Results-Seite: Iterations-Spalte zeigt Stops im Tooltip und Indikator-Config-Namen (1.17.13)
- Indicator-Config-Liste: Iteration-Spalte zeigt jetzt zusätzlich die Versionsnummer und ist anklickbar (öffnet die Iteration im Bearbeitungsmodus in neuem Tab) (1.17.10)
- TestSet-Anlegen nutzt die volle Bearbeiten-Maske statt des Modals (1.17.5)
- Backtest-Start-Formular: Config-Dropdown nach Favoriten gruppiert und Indicator-Config-Dropdown mit vorangestellter ID (1.17.1)
- Backtest-Configs: exklusives Default-Flag durch nicht-exklusiven Favoriten-Stern ersetzt (analog zu Konzepten/Iterationen/Results) (1.17.0)
- _stops_pos aus Indikator-Configs entfernt — Stops-Position ist reine Anzeige, gehoert nicht in die config_json (1.16.2)

### Fixed
- Veralteten Test test_full_config_snapshot an Stop-Umbau angepasst (1.17.17)
- Run-Neustart bricht jetzt auch einen bereits laufenden alten Job ab, bevor neu eingereiht wird (1.17.12)
- Run-Loeschung bricht jetzt auch bereits laufende Worker-Jobs ab, nicht nur wartende (1.17.11)
- TestSet-Löschen wird nicht mehr durch vorhandene Läufe blockiert (1.17.4)
- Chart-Playground: Trade-Marker (Long/Short-Positionen) werden im resampelten Anzeige-TF wieder angezeigt (1.17.3)
- Chart-Playground: Chart-Anzeige folgt jetzt dem OHLC-Datenfenster statt dem Rechenfenster (1.17.2)
- dtype-Ableitung bei arange-Parametern: Float-Werte erzwingen jetzt float64 statt faelschlich int64 zu behalten (1.16.3)


## [1.16.1] - 2026-06-18

### Added
- Indikator-Config-Seite: visueller Editor mit JSON/Visuell-Umschalter (Stops + Ranges wie im Playground) (1.16.0)
- Playground: Stops als verschiebbare Zeile im Indikator-Layout (Drag-Griff, Position persistiert) (1.15.18)
- Stop-Umbau Schritt 3a: Einmal-Migration backfillt den Meta-Key '_stops' in bestehende Run-Snapshots (Vorbereitung der Stop-Eigentuemerschaft in der IndicatorConfig) (1.15.6)
- Stops koennen als Sweep-Achsen durchgetestet werden: Listen-/Range-Werte in indicators_json['_stops'] werden als vbt.Param kartesisch mit dem Indikator-Raster gefahren; tsl_th+tsl_stop koppeln als zip-Paare (Schritt 2 des Stop-Umbaus) (1.15.5)

### Changed
- Playground: Stops als eigene Card in der Indikator-Spalte mit Range-Erweiterung (sweep-fähig wie Indikator-Parameter) (1.15.16)
- Playground: Stops als eigene Card mit Range-Erweiterung (sweep-fähig wie Indikator-Parameter) (1.15.15)
- Strategie-Entwicklungs-Doku auf das neue Stop-Modell synchronisiert: Stops und Formate gehören zur IndicatorConfig (_stops), nicht mehr zur BacktestConfig (Schritt 5, Abschluss Stop-Umbau) (1.15.14)
- Playground: Stops aus der Portfolio-Zeile in eine eigene Stops-Sektion der Indikatoren-Card verschoben; Stops reisen jetzt als indicators._stops (Schritt 4c/4d des Stop-Umbaus) (1.15.13)
- IndicatorConfig-Editor: _stops-Sonderblock in den JS-Helfern unterstützt (Schritt 4a des Stop-Umbaus) (1.15.10)
- Stop-Umbau Schritt 3d: Die Stop-Format-Parameter delta_format/time_delta_format zu den Stops verlagert — sie leben jetzt als Meta-Felder in indicators_json['_stops'] statt in der BacktestConfig (1.15.9)
- Stop-Umbau Schritt 3b: Stop-Lesepfad von der BacktestConfig auf den Meta-Key indicators_json['_stops'] umgebogen — die IndicatorConfig ist jetzt Eigentuemerin der Stops (1.15.7)
- Stop-Parameter (tp/sl/tsl/td) werden vom Spec-Runner aus dem reservierten Meta-Key indicators_json['_stops'] gelesen statt aus dem portfolio-Block der BacktestConfig (Schritt 1 des Stop-Umbaus, Skalar; Ranges/Sweep folgen) (1.15.4)
- Iteration-Dropdowns auf Backtest-Start zeigen Versionsnummer + Beschreibung (1.15.3)
- Iterationen-Subtabellen auf der Strategie-Konzepte-Seite nach Version absteigend sortiert (1.15.2)

### Removed
- Verwirrenden _stops-Hinweistext unter dem JSON-Editor der Indikator-Config entfernt (1.16.1)
- Stop-Umbau Schritt 3c: Die fuenf Stop-Spalten (tp/sl/tsl_th/tsl_stop/td) endgueltig aus backtest_configs entfernt — Stops leben jetzt ausschliesslich im Meta-Key indicators_json['_stops'] (Eigentuemer IndicatorConfig) (1.15.8)
- Hartcodiertes Goal-Gate (goal_gate.py) wieder entfernt — Strategie-Bewertung erfolgt durch KI-Urteil mit Toleranz, nicht durch programmatisches Pass/Fail (1.15.1)

### Fixed
- Playground: Stop-Felder pixelgenau an Indikator-Felder angeglichen (Größe wich ab) (1.15.17)
- Config-Snapshot erfasst skalare Stops jetzt aus _stops statt aus der BacktestConfig (Schritt 4c-pre, Vorbedingung für den Playground-Umbau) (1.15.12)
- Backtest-Anzeige liest tp_stop/sl_stop pro Result aus dem Config-Snapshot statt run-weit aus portfolio (Schritt 4b des Stop-Umbaus) (1.15.11)


## [1.15.0] - 2026-06-17

### Added
- Goal-Gate: deterministische, regime-asymmetrische Mandat-Bewertung pro Testset-Config (erster Baustein des autonomen Strategie-Loops) (1.15.0)
- README.md und .env.example fuer das oeffentliche GitHub-Repository angelegt (1.14.3)
- Ticket 44 — Combo-Batching im Spec-Runner: Multiparameter-Läufe mit >5k Kombis werden automatisch chunk-weise verarbeitet um OOM bei 36k+ Kombis zu vermeiden (1.13.0)
- Ticket 44 — Combo-Batching im Spec-Runner: OOM-Schutz für grosse Multiparameter-Läufe (1.12.0)

### Changed
- Repo für die öffentliche GitHub-Bereitstellung bereinigt: interne Pfade, Projektnamen und den privaten Obsidian-Vault-Namen aus allen getrackten Dateien entfernt bzw. über Umgebungsvariablen konfigurierbar gemacht (1.14.5)
- README überarbeitet: Playground, Test-Sets sowie Strategien/Iterationen ausführlicher erklärt, KI-gestützten Workflow als Kernprodukt herausgestellt, Versionsnummer bei der Backtest-Engine entfernt (1.14.4)
- OHLC-Datenverwaltung (/config/data): getrennte Buttons "Aktualisierung" und "Neu einlesen" pro Datei sowie lesbare Status-Labels (1.14.0)
- OHLC-Jobs zeigen unter /config/data jetzt den tatsächlichen Datenbereich statt des relativen Platzhalters "now UTC" (1.13.8)
- OHLC-HDF5-Daten von user_data/ohlc_data/ nach data/ohlc_data/ verschoben (Konsolidierung mit den übrigen data/-Verzeichnissen) (1.13.6)
- Alembic-Migrationen erneut zu einer einzigen Baseline 0001_baseline_squash zusammengefasst (Stand wie bei Neuinstallation) (1.13.5)
- Results-Tabelle verschlankt: Aktions-Dropdown und kompakte Metrik-Header (1.11.16)

### Removed
- Tote/maschinenspezifische Konfig aus dem Repo entfernt: ungenutzte Root-vbt_settings.toml, .mcp.json und documentation/tickets/ nicht mehr getrackt (1.14.1)

### Fixed
- Chart-Playground: Sichtbarkeits-Toggle der Indikatoren verwirft nicht mehr den Schnellbacktest, Fit-Button leuchtet beim Laden, Display-Änderungen respektieren den visuellen TF (1.14.2)
- OHLC-Update-Job (Aktualisieren-Button unter /config/data) schlug bei Multi-Symbol-Dateien fehl mit "Number of symbols must be equal to the number of matched paths" (1.13.7)
- Deflated Sharpe Ratio (DSR) im Chunked-Lauf quer-schnittlich korrekt berechnet (Ticket 44) (1.13.4)
- Ticket 44: Schema-brechenden n_block==1-Workaround in _run_chunked durch ursachenbehebenden Fix ersetzt (1.13.3)
- Ticket 44: Schema-brechenden n_block==1-Workaround in _run_chunked entfernt; _extract_partial_metrics liefert nun in allen Fällen exakt 16 Felder (1.13.2)
- Combo-Batching Lücken geschlossen: Single-Combo-Chunk-Bug in _run_chunked behoben, echte Backtest-Tests und Acceptance-Tests ergänzt (1.13.1)
- Playground-Setups- und Testsets-Tabelle: Raute vor ID entfernt (1.11.15)
- Backtest-Results-Tabelle: Raute vor Run-ID entfernt (1.11.14)


## [1.11.13] - 2026-06-16

### Added
- Konzept-Filter: Option (ohne Konzept) fuer Results ohne zugeordnete Iteration (1.11.6)
- Ticket 40 — Leaderboard-Eintrag allein reproduzierbar: spec_json-Einbettung und Rerun-Endpunkt (1.11.0)
- Ticket 42: Playground flüchtig aus Result laden (kein Setup anlegen) (1.10.17)
- Ticket 43 — "Aus Result speichern" auf Snapshot vereinheitlicht (alle drei Wege löschfest) (1.10.16)
- Ticket 43 — Speichern aus Result via full_config_snapshot_json (BC/IC/Setup) (1.10.14)
- Ticket 41 — BacktestResult trägt vollständigen Config-Snapshot (full_config_snapshot_json) (1.10.13)

### Changed
- Chart-Playground: Default-Linienstärke der Indikatoren von 2 auf 1 Pixel gesenkt (1.11.12)
- Chart-Playground: Indikator-Sichtbarkeits-Switch in die obere Card-Zeile verschoben (1.11.11)
- Chart-Playground: Fit-Button ist jetzt ein echter Zustand statt 300-ms-Blinken — leuchtet beim Laden mit 1D und bleibt aktiv, solange die Ansicht alles zeigt (1.11.9)
- Chart-Playground: Beim Laden eines Charts standardmäßig Anzeige-Timeframe 1D aktivieren und auf Fit zoomen (1.11.8)
- Iteration in Results zeigt Version statt PK-ID, ohne Raute, Dropdown nach Version absteigend (1.11.5)
- Results-Tabelle: Strategie-Spalte in Konzept + Iteration aufgeteilt, Favorit-Spalten schmaler (1.11.4)
- Iterations-Filter zeigt die Iterations-ID im Label an (1.11.3)
- Results-Filter: Strategie-Dropdown in getrennte Felder Konzept und Iteration aufgeteilt (1.11.2)
- Ticket 43: Aus-Result-Speichern auf vollständigen Config-Snapshot umgestellt (1.10.15)
- Wissens-Vektorindex auf den ganzen Obsidian-Vault ausgeweitet (statt nur 30_Trading) (1.10.12)

### Removed
- Versehentlich committete leere Stray-Dateien aus Repo-Root entfernt (1.11.1)

### Fixed
- Backtest-Config-Tabelle: ID-Spalte sortierbar und ohne Raute (1.11.13)
- Chart-Playground: Misch-URL aus resultid und setupid wird unterbunden und kanonisch umgeleitet (1.11.10)
- Playground: Indikator-Werte werden beim visuellen Timeframe-Wechsel vollständig resampled (Subplots + Equity) (1.11.7)


## [1.10.11] - 2026-06-15

### Added
- Cleanup-Konvention für Einmal-/Wegwerf-Dateien in CLAUDE.md verankert (1.10.10)
- Ticket-Status-Marker eingeführt: Pflichtzeile **Status:** offen|abgeschlossen direkt unter der H1 jedes Tickets (1.10.6)
- Toolbox auf vollständige API-Abdeckung erweitert — die KI kann jetzt jede operative Route bedienen (ändern, löschen, alle Aktionen); plus neuer Backend-Endpoint zum Löschen eines Konzepts (1.9.17)
- Objekt-Toolbox (ds-strategie-session) um Bau-, Lauf- und Listen-Befehle erweitert — voller Strategie-Loop über die CLI bedienbar (Ticket 38) (1.9.16)
- Doku-Favoriten (roter Stern) als zweite, unabhängige Favoriten-Markierung mit eigenem Löschschutz (1.9.12)

### Changed
- Handoff-Schritt 4 auf deterministischen git-Check umgestellt (project-structure.md-Drift) (1.10.9)
- ds-strategie-session-Skill von Nachschlage-Doku entkoppelt: Verweise auf die funktionsuebersicht entfernt (1.10.8)
- Kontext-Injektion auf on-demand umgestellt: project-structure.md wird nicht mehr pauschal in Subagenten/Gemini injiziert (1.10.7)
- Doku-Struktur nach Publikum getrennt: documentation/ in project/ (User) und knowledge/ (KI/Dev) aufgeteilt (1.10.5)
- Custom-Indikatoren-Liste auf eine Quelle reduziert: doppelte Tabelle in guide.md durch Verweis auf indicators.md ersetzt (1.9.19)
- Skill ds-strategie-session entschlackt: Pfad-B-Befehlskatalog aus SKILL.md entfernt, Detail-Referenz auf zwei kanonische Quellen konsolidiert (1.9.18)
- Terminologie: englische Abkürzung „OoS"/„Out-of-Sample" durchgängig durch deutsche Projektbegriffe ersetzt (Ticket 39) (1.9.15)
- Seed-Export schreibt jetzt datierte, versionierte Dumps (1.9.14)
- Stern-Spalten beschriftet (F = Favorit, D = Doku-Favorit) und sortierbar gemacht (1.9.13)

### Removed
- Obsolete Einmal-Skripte aus scripts/ entfernt; project-structure.md auf aktuellen Hook-Stand nachgezogen (1.10.11)
- Workflow-Feature (Templates und Runs) vollständig entfernt (1.10.0)

### Fixed
- Doku-Audit P21-P30: veraltete und falsche Strategie-/Projekt-Doku gegen Code-Realitaet korrigiert (1.10.4)
- vectorbtpro-MCP: Token-Regression behoben und VBT-Token eindeutig von Commit-Token getrennt (VBT_GITHUB_TOKEN) (1.10.3)
- vectorbtpro-MCP-Server: GITHUB_TOKEN erreicht jetzt zuverlaessig die Windows-python.exe (Start-Wrapper statt .mcp.json-Substitution) (1.10.2)
- Git-Workflow-Doku an den tatsächlichen Auto-Commit-Mechanismus angeglichen (1.10.1)


## [1.9.11] - 2026-06-14

### Added
- Chart-Playground: Button "Kombinationen berechnen" in der Indikatoren-Card (1.9.2)
- Chart-Playground: Umschalter pro Indikator-Parameter zwischen Einzelwert und Wertebereich (1.9.1)
- Leaderboard: Filter nach Strategie und Iteration ergänzt (1.8.26)

### Changed
- Versions-/Doku-Regelwerk: Stops und Portfolio-Einstellungen gehören zur BacktestConfig, nicht ins spec_json (1.9.11)
- Strategie-Konzept-Maske: Iterations-Tabelle zeigt Version und Versionsname als getrennte Spalten (1.9.8)
- Playground-Anzeige-Einstellungen überarbeitet: Einstellungen-Tab entfernt, Anzeige-Schalter in eine kopflose Card über Portfolio verschoben und um Equity/Long/Short erweitert (1.9.6)
- Chart-Playground: Setup-Dropdown lädt nicht mehr automatisch — neuer "Laden"-Button (1.9.3)
- Entry/Exit-Regeln in disjunktiver Normalform (Block-Modell) (1.9.0)
- Chart-Playground: umfangreiche UI-Überarbeitung (Indikator-Panel, Speichern, Setup-Laden per URL, Schnellbacktest-Verhalten) und OHLCV-Input-Korrektur (1.8.28)
- Chart-Playground: Indikator-Panel auf zweizeiliges Layout umgestellt (1.8.27)
- Leaderboard: Info-Icon der ID-Spalte entfernt (1.8.25)
- Leaderboard: Spaltenkopf Konzept zu KT gekürzt (1.8.24)
- Leaderboard: Indikator-Hover formatiert (Name als Überschrift, Parameter als Key/Value) (1.8.21)

### Fixed
- Obsidian-Link in der Strategie-Konzept-Maske zeigte das Label statt des Dokumentnamens (1.9.10)
- Obsidian-Link der Iterations-Tabelle zeigte auf falschen Dateinamen (1.9.9)
- Playground: Kurzform-Indikator-Referenzen (indicator:&lt;name&gt; ohne Output) werden in der Rules-Validierung auf den ersten Output aufgelöst statt fälschlich rot als "Indikator deaktiviert" markiert (1.9.7)
- Chart-Playground: Geister-Serien auch bei Wechsel auf eine Iteration ohne Indikatoren entfernen (1.9.5)
- Chart-Playground: Geister-Indikatoren auf dem Chart nach Iterations-/Indikator-Config-Wechsel (1.9.4)
- Leaderboard: Spalte Indikator-Config wieder sortierbar (1.8.23)
- Leaderboard: Indikator-Tooltip hat jetzt deckenden Hintergrund (1.8.22)


## [1.8.20] - 2026-06-11

### Added
- OoS-Validierungs-Werkzeuge: Result zu eingefrorener IndicatorConfig (Endpoint + brief_ids freeze-Verb) plus Workflow-Doku und Skill-Integration (1.8.16)
- Backtest-Runs speichern jetzt die Herkunfts-Referenzen backtest_config_id und indicator_config_id (1.8.14)
- Numerische Min/Max-Feld-Filter und ein-/ausblendbare Filterleiste auf der Backtest-Results-Seite (1.8.3)

### Changed
- Leaderboard: Indikatoren-Spalte zeigt jetzt den IndicatorConfig-Namen statt Badges (1.8.19)
- Leaderboard-Tabelle weiter verschmälert: ID-Spalte ergänzt, Erstellt am in Child-Row, Header gekürzt (1.8.18)
- Leaderboard-Tabelle: Iteration-Spalte zu ITER verschmälert und zentriert, Runner-Version in Child-Row verschoben (1.8.17)
- Spec-Runner-Importpfad als zentrale Konstante SPEC_RUNNER_IMPORT_PATH statt 4-fach dupliziertem String-Literal (M5) (1.8.12)
- Supertrend wird im Result-Chart generisch gerendert - kein hartcodierter Indikator-Name mehr im Anzeige-Layer (K2, K3) (1.8.10)
- Chart-Daten-Endpunkt dispatcht Supertrend ueber den Indikator-Typ statt ueber den hartverdrahteten Instanz-Namen (K1) (1.8.9)
- Filterleiste der Results-Seite folgt jetzt der Tabellen-Spaltenreihenfolge (1.8.6)
- Spaltentitel Profit Factor in der Results-Tabelle auf PF gekürzt mit Info-Icon-Tooltip (1.8.5)

### Removed
- Spalte Downside Risk aus der Backtest-Results-Tabelle entfernt (1.8.4)

### Fixed
- Leaderboard: IndicatorConfig-Titel wird jetzt korrekt aufgelöst (war immer NULL) (1.8.20)
- Worker-Restart-Schleife behoben: stabile Redis-Verbindung mit TCP-Keepalive (1.8.15)
- Chart-Playground: Aus Backtest-Result erzeugte Setups setzen beim Laden wieder Konzept und Iteration (1.8.13)
- Stilles Fallback beim Speichern von Indikator-Zeitreihen entfernt - unbekanntes Datenformat bricht den Run jetzt hart ab statt Daten lautlos zu verschlucken (M7) (1.8.11)
- Parameter-Tooltip in der Backtest-Results-Tabelle erscheint wieder beim Hovern über die Strategiezeile (1.8.8)
- Sortierung nach der Favorit-Spalte in der Results-Tabelle funktioniert wieder (1.8.7)
- Result-Chart: Long-Orders erscheinen nach Aus-/Einschalten sofort wieder, statt erst beim naechsten Chart-Invalidate (1.8.2)
- Result-Chart: Equity/Indikatoren beim Laden korrekt aufs aktive Timeframe resampled; Indikator-Panels vollständig generisch inkl. Parameter-Anzeige (1.8.1)


## [1.8.0] - 2026-06-11

### Added
- Bewertungs-Schema: Methodik 'Archetyp-Vertreter aus einem Sweep gewinnen' ergaenzt (1.7.28)
- Bewertungs-Schema (Akzeptanzkriterien) für die Strategie-Entwicklung dokumentiert (1.7.21)
- Strategie-Session-Skill um Session-Ende erweitert und Mission-Kontext für Auto-Injektion ergänzt (1.7.20)
- Guide-Abschnitt zu Timeout (td_stop) vs. bedingtem Fruehausstieg mit Fall-Tabelle (1.7.19)
- Unit-Tests fuer _combine_broadcast (Cross-Produkt disjunkter Indikator-Param-Level) (1.7.13)

### Changed
- Zentrales Stylesheet app.css eingeführt — Scrollbalken-Sprung-Fix und CSS-Konsolidierung (1.8.0)
- vault-create schreibt jetzt das volle Iterations-Frontmatter-Schema (1.7.27)
- Bewertungs-Schema: Archetyp-Namen und Aussortiert-Kategorie ergaenzt (1.7.26)
- Veralteten Bestvariante-Begriff aus der gesamten Strategie-Entwicklungs-Doku entfernt (1.7.23)
- Strategie-Doku an das neue Bewertungs-Schema angeglichen (1.7.22)

### Removed
- Doku-Konsolidierung — abgeloeste Konzept-Ablage und redundantes Meta-Entscheidungs-Log entfernt (1.7.24)
- Ticket 35 abgeschlossen: Cooldown-Approximation der Rules-Engine zurueckgebaut (State-Exits laufen ausschliesslich nativ) (1.7.15)

### Fixed
- ds-strategie-session-Skill: status.md-Verortung auf den Vault korrigiert (1.7.25)
- Vier vorbestehende rote Tests (aus dem 1.6.18-Umbau) auf den aktuellen Code-Stand nachgezogen (1.7.18)
- Backtest-Job mit 0 Kombinationen (leeres Portfolio) wird jetzt als 'failed' markiert statt still 'completed' (1.7.17)
- Frontend: Fehlende .catch-Handler an Fetch-Aufrufen mit haengendem UI-State ergaenzt (Endlos-Spinner / dauerhaft gesperrte Buttons / Dropdown-Limbo) (1.7.16)
- Chart-Playground /compute: lowercase OHLCV-Input-Namen werden jetzt korrekt auf die col_map-Spalten gemappt (1.7.14)
- Chart-Playground: src-Altlast crasht keinen Lite-Backtest mehr — Erkennung in die Lade-Pfade verschoben (1.7.12)
- Backtest-Metriken: NaN-Werte werden nun korrekt als NULL gespeichert statt als NaN — behebt fehlerhafte Sortierung der Results-DataTable (1.7.11)
- Results-DataTable: NULL-Metriken (als \"-\" angezeigt) werden beim Sortieren numerischer Spalten jetzt einheitlich ans Ende gelegt (1.7.10)


## [1.7.9] - 2026-06-01

### Added
- indicators.md: Deep-Dive zu Multi-Combo-Berechnung, Cross-Produkt und Recompute (Abschnitte 6.5-6.9) (1.7.9)
- Native State-Exits per signal_func_nb (Ticket 35, Schritt 1) (1.7.0)
- Equity-Tooltip im Chart-Playground: Klick auf die Equity-Linie zeigt ein Label mit dem aktuellen Equity-Wert (analog zur Result-Chart-Ansicht) (1.6.26)
- Chart-Playground-Setups speichern jetzt auch die Auswahl der Dropdowns Iteration, Backtest-Config und Indikator-Config und stellen sie beim Laden wieder ein (1.6.25)
- Chart-Playground: Setup speichern unter… belegt Name und Beschreibung automatisch vor (1.6.22)
- Chart-Playground Schnellbacktest: Benchmark, Profitfaktor und Max-Drawdown im Ergebnis-Badge (1.6.21)
- Chart-Playground Schnellbacktest: Benchmark, Profitfaktor und Max-Drawdown im Ergebnis-Badge (1.6.20)
- Chart-Detailseite: Metrik-Kachel "Profitfaktor" zwischen Benchmark und Sharpe (1.6.19)

### Changed
- Backtest-Start-Seite leitet nach dem Start nicht mehr auf die Runs-Seite weiter, sondern bleibt stehen und zeigt eine Erfolgsmeldung (1.7.2)
- Slug aus der Versions-Spalte der Iterations-Subtabelle auf der Strategy-Concepts-Seite entfernt (1.6.24)
- Indikator-Migrationen (Source-Prefix + enabled-Strip) auf alle Indikator-Dict-Tabellen ausgeweitet und angewendet (1.6.23)
- Iterations-Versionen auf fortlaufende Integer-Nummern pro Konzept umgestellt (High-Water-Mark, kein Reuse) und Chart-Playground entsprechend erweitert (1.6.18)

### Fixed
- Recompute eines Multi-Combo-Results rechnete den vollen Sweep statt der Einzel-Kombination — falsche/identische Equity, langsam, Metriken ueberschrieben (1.7.8)
- Chart eines Multi-Combo-Results zeigte keine Equity/Indikatoren — Recompute scheiterte an fehlendem rules_json (1.7.7)
- Multi-Indikator-Backtests mit disjunkten Parameter-Leveln brachen mit 'Cannot align indexes' ab — Cross-Produkt der Param-Spalten ergaenzt (1.7.6)
- Chart-Playground: Indikator-Inputs gehen beim Speichern nicht mehr verloren und Altlast-Felder werden sichtbar entfernt (1.7.5)
- TestSet-Tab: Iterations-Dropdown sortiert jetzt nach version absteigend (hoch nach klein) (1.7.4)
- Backtest-Start-Seite: Iterations- und Indicator-Config-Dropdown sortieren jetzt absteigend (hoch nach klein) (1.7.3)
- Results-Tabelle: Spalte Strategie sortiert jetzt nach Concept-Name und numerischer Iterations-Version (2, 3, 32, 42) statt lexikografisch nach strategy_name. Damit ist die Sortierung der Strategie-Spalte durchgaengig numerisch korrekt. (1.7.1)
- Chart-Playground: Speichern-Buttons der Indikator-Konfiguration werden nur noch bei vorhandenen Indikatoren angezeigt (1.6.17)


## [1.6.16] - 2026-05-30

### Added
- Iterationen lassen sich jetzt direkt kopieren — neuer Copy-Endpoint plus Kopier-Button in der Iterations-Zeile auf der Strategie-Konzepte-Seite. (1.6.13)
- Kurzbeschreibungsfeld für Strategie-Konzepte im Edit-Modal ergänzt (1.6.5)
- Strategie-Entwicklung Dokumentationsstruktur aufgebaut (1.6.0)
- vault_reindex_runs: JSONB-Spalte files_changed mit reindexierten und gelöschten Vault-Pfaden pro Lauf (1.5.1)
- Ticket 33 — Vault-Indexer Cleanup-Paket: Sentinel-Row, Reset-Button und Worker-Architektur (1.5.0)
- Vault-Indexer: Content-Hash-Skip statt reiner mtime-Vergleich (Ticket 32) (1.4.2)

### Changed
- Tests in test_api_strategy.py an den aktuellen Code- und Datenstand angepasst (kein Produktionscode geaendert). (1.6.14)
- Chart Playground Toolbar in zwei Zeilen umstrukturiert (1.6.4)
- Iterations-Löschung gibt bei Blockierung Blocker-Details zurück und bietet Force-Cascade-Option (1.6.2)
- Playground-Iterations-Registry und App-Guide überarbeitet (1.6.1)

### Fixed
- Ticket 34: Fehlermeldung fehlgeschlagener Backtest-Runs wird jetzt in der Child-Row der Runs-Tabelle angezeigt. (1.6.16)
- Ticket 34: Exit-/Entry-Bedingungen im Chart-Playground werden auch bei deaktivierten oder fehlenden Indikator-Referenzen sichtbar gerendert; Run bricht bei solchen Referenzen mit klarer Meldung ab. (1.6.15)
- v42 Iteration und BT Config #562 auf Referenz-Result #695198 ausgerichtet (1.6.12)
- Chart-Playground: Zwei Rendering-Bugs bei Indikator-/Rules-Darstellung behoben (1.6.11)
- Playground Schnellbacktest: sl_stop-Default überschreibt Config-null nicht mehr (1.6.10)
- Rules-Engine: 2-Pass-Berechnung für State-Primitiven korrigiert Approximationsfehler bei Re-Entries (1.6.9)
- Chart Playground: State-Primitiven, Portfolio-Prefill und UX-Fixes (1.6.8)
- Chart Playground: Entry/Exit-Rules werden beim Wechsel der Iteration automatisch geladen (1.6.7)
- Chart Playground: dwsVWMA und dwsCrossover Berechnungsfehler bei gespeicherten Setups behoben (1.6.6)
- Vault-Ordner und Iterations-Dateinamen bei Konzept-Slug-Umbenennung synchronisieren (1.6.3)


## [1.4.1] - 2026-05-28

### Added
- Vault-Knowledge-Dashboard: GET /api/knowledge/stats + Übersichts-Seite /knowledge (Ticket 30) (1.4.0)
- Vault-Reindex Frontend: Wissens-Index-Seiten und GET /api/knowledge/files Endpoint (Ticket 29) (1.3.0)
- Ticket 28: Vault-Reindex-Job-History — Persistenz und API (1.2.0)
- Ticket 26 — Vault-Vektorisierung: REST-Endpoints GET /api/knowledge/search und POST /api/knowledge/reindex (1.1.1)
- Ticket 25 — Vault-Vektorisierung: Embedding-Client, Markdown-Chunker und Indexer-Worker (1.1.0)
- Ticket 24 — Vault-Vektorisierung: pgvector-Schema und SQLAlchemy-Modell VaultChunk (1.0.176)
- Helper-Script und Skill zum gebuendelten Einlesen von vbt_app-Konfigurationen via URLs oder typ:id-Kurzformen (1.0.175)
- Workflow `setup-via-api.md` fuer Setup-Anlage und Backtest-Ausfuehrung via API ergaenzt (1.0.173)
- Chart-Playground Schnellanalyse zeigt Trade-Marker mit Entry/Exit/PnL im Chart (1.0.171)
- Chart-Playground Schnellanalyse zeigt Equity-Kurve im Chart (1.0.167)
- Ticket 23: Schnellanalyse-Button (Lite-Backtest) im Chart-Playground (1.0.164)

### Changed
- Skill ds_strategie_session ins Projekt-Repo verschoben und Ablauf auf Discovery-First umgestellt (Korrektur zu v1.0.173) (1.0.174)
- Strategie-Entwicklungs-Doku auf neue Struktur umgestellt (AGENT_ENTRY + guide + workflows + STATUS-pro-Strategie, Iter-Logs in den Vault verlagert) (1.0.172)
- Chart-Playground: Layout-Feinschliff in der Strategie-Sektion (1.0.170)
- Chart-Playground: Layout-Refactor mit Card-Aufteilung und formatiertem Total Return (1.0.166)
- Chart-Playground: Schnellanalyse/Backtest-Buttons in obere Action-Zeile verschoben, Lite-Badge-Kontrast verbessert (1.0.165)

### Fixed
- Vault-Indexer: Mount-Guard gegen unbeabsichtigtes Mass-Delete bei fehlendem Bind-Mount (Ticket 31) (1.4.1)
- Ticket 27 — PyYAML-Blocker behoben, Vault-Mount korrigiert, Initial-Reindex und Smoketest erfolgreich (1.1.2)
- Schnellanalyse: Equity-Kurve wurde nicht ausgeliefert weil pf.value ein DataFrame war (1.0.169)
- Chart-Playground /compute: Indikator-Reihenfolge wird per Topo-Sort aufgeloest (1.0.168)


## [1.0.163] - 2026-05-27

### Added
- Iteration-Edit: "Slug anpassen"-Button erscheint, sobald der aus dem Namen abgeleitete Slug vom aktuellen abweicht (1.0.163)
- Iteration: separates version_name-Feld als editierbarer Anzeige-Name; version bleibt fixer Slug fuer Vault-Pfad (1.0.162)
- Leaderboard: Iterations-Kurzbemerkung als Tooltip auf Iteration-Name (1.0.159)
- Leaderboard: Test-Tage (Intervall-Union) und Return/Tag % (1.0.156)
- Strategie-Iterationen: updated_at-Spalte und neue Tabellenspalte 'Aktualisiert' (1.0.151)
- Strategie-Iterationen: Favoriten-Stern und Löschen in der Child-Row (1.0.149)

### Changed
- Sortierung und Aktionsbuttons in Backtest-Übersichten überarbeitet (1.0.161)
- Leaderboard-Child-Row zeigt zusaetzlich Executive Summary und Mini-Report (1.0.160)
- Leaderboard: R/T %-Header und nowrap fuer Iteration/TestSet/Erstellt am (1.0.158)
- Backtest-Runs: Auto-Update-Intervall von 10s auf 5s reduziert (1.0.155)
- Strategie-Iterationen Child-Row: horizontales Zellen-Padding erhöht (1.0.154)
- Strategie-Iterationen Child-Row: Spaltenbreiten ausbalanciert (1.0.152)
- Strategie-Iterationen: Sortierung Favoriten oben, dann Erstelldatum absteigend (1.0.150)
- Strategie-Konzepte aus Konfigurations-Dropdown in die Top-Navigation verschoben und Bulk-Delete fuer Playground-Setups ergaenzt (1.0.148)
- Backtest-Runs: TSetID-Spalte zentriert (1.0.147)
- Backtest-Runs: Spaltenheader 'TestSet-Run' in 'TSetID' umbenannt (1.0.146)
- Backtest-Runs: TestSet-Run-Spalte vor Strategie verschoben (1.0.145)
- Backtest-Runs: TestSet-Run-Badge ohne Raute (1.0.144)

### Fixed
- Leaderboard: Overlap-Badge nur noch bei echten Zeitraum-Ueberschneidungen (1.0.157)
- Strategie-Iterationen Child-Row: w-1 auf Daten-Zellen mitsetzen (1.0.153)


## [1.0.143] - 2026-05-27

### Added
- Backtest-Runs: TestSet-Spalte mit Link zum TestSet (1.0.142)
- Leaderboard: TestSet-Spalte mit Namen aus dem Snapshot (1.0.141)

### Changed
- Backtest-Runs: TestSet-Spalte zeigt testset_run_id statt TestSet-Name (1.0.143)
- Indicator-Configs-Tabelle: Konzept- und Iteration-Spalten ergaenzt, Workflows/Default entfernt, Indikatoren ohne Zeilenumbruch (1.0.140)
- Ticket 22 — Indikator-Config: lose Verknüpfung zu Strategy-Concept und Iteration (1.0.139)
- Leaderboard: Default-Sortierung auf Sum Return % (statt Ø Return %) (1.0.138)
- Leaderboard: Spalten Ø Return % und Sum Return % links neben Erstellt am verschoben (nach Ø Profit-Faktor) (1.0.137)
- Leaderboard: Spalte IndicatorConfig durch generische Spalte Indikatoren ersetzt — Badges aus indicator_config_snapshot_json mit Parameter-Tooltip (1.0.136)
- Drill-Down-Modal im Leaderboard breiter (95vw) und höher (80vh), Body intern scrollbar (1.0.133)
- Drill-Down-Tabelle im Leaderboard-Modal auf DataTables umgestellt (Sortierung, Pagination, Suche, Length-Menu) (1.0.132)
- Leaderboard-Tabelle: Hint in Child Row (Chevron-Toggle), Strategie aufgeteilt in Konzept/Iteration, Spalte Ausgelöst von entfernt, Runner-Version/Configs/Gewinn/Verlust zentriert (1.0.131)
- Leaderboard: Spalten Gewinn/Verlust (Config-Counts) und Ø Profit-Faktor ergänzt; alle Header-Spalten mit Info-Tooltips erklärt (1.0.130)
- Leaderboard Drill-Down: Winrate und Profit-Faktor ergänzt, Zeitraum in deutschem Datumsformat (DD.MM.YYYY) (1.0.129)
- TestSet-Lauf vereinheitlicht mit Einzel-Lauf: gleiches Konzept/Iteration-Dropdown und Pflicht-Indicator-Config (1.0.128)
- Alembic-Migrationen auf eine Baseline zusammengefasst, schema.sql entsorgt (1.0.125)

### Removed
- Indicator-Config: ungenutzte Strategie-Zuordnung entfernt (1.0.124)

### Fixed
- Drill-Down: Length-Menu zurück in den Footer (Design-Guide), eigenes Suchfeld mit Lupe und X-Clear über der Tabelle (statt DT-Default) (1.0.135)
- Drill-Down-Modal: Abstand nach oben (margin-top 4rem), Length-Menu links und Suchfeld rechts korrekt platziert, globale dt-search-Ausblendung im Modal aufgehoben (1.0.134)
- Dark-Mode-Darstellung der aufgeklappten Child-Row auf /config/strategy-concepts korrigiert (1.0.127)
- api_backtest.py: import_path fuer generic-Iterationen explizit auf spec_runner setzen (1.0.126)


## [1.0.123] - 2026-05-26

### Added
- Konfiguration: Verwaltungsseiten für Playground-Setups (Liste + Edit-Maske mit allen Feldern) (1.0.119)
- Chart-Playground: Backtest-Result inline anzeigen mit Kennzahlen-Panel, Equity-Sub-Chart und Trade-Markern; drei Analyse-Tabs (Indikatoren/Strategie/Portfolio | Stats | Trades); gemeinsame JS-Module result/tabs.js und result/overlay.js für Wiederverwendung mit result_chart.html (1.0.108)
- Iteration loeschen mit optionaler Obsidian-Ordner-Entfernung und Vault-Ordner-Rename bei Versionsaenderung (1.0.106)
- Ticket 16 — Deterministische Obsidian-Pfade, vault-create Endpunkte, Frontend-Button (1.0.104)

### Changed
- Chart-Playground: Button-Label und Confirm-Dialog "Loeschen" → "Löschen" mit echtem Umlaut (1.0.123)
- Chart-Playground: Toolbar-Buttons (Chart laden, Speichern, Speichern unter, Löschen) auf normale Größe vereinheitlicht und horizontal ausgerichtet (1.0.122)
- Playground-Setup-Edit: Layout der Inputfelder überarbeitet (1.0.121)
- Indikator-Spec-Format vereinheitlicht: flacher Aufbau, source statt src, indicator: statt ind: (1.0.120)
- Chart-Playground: Equity wird als Overlay-Series am Haupt-Chart gerendert statt als Sub-Chart (1.0.117)
- Indicator-JSON-Schema bereinigt: Tickets 18-21 umgesetzt, dwsFastSMA-Param 'mult' zu 'multiplier' DB-migriert. (1.0.114)
- calcCombinations() in beiden Templates haertet: META_KEYS explizit ueberspringen (1.0.112)
- Ticket 18 — Recompute auf _build_resolved_config umgestellt, resolved_config_json schreibt Skalare statt Pseudo-Ranges (1.0.111)
- dwsFastSMA-Param `mult` zu `multiplier` umbenannt, Alias-Map entfernt (Ticket 19) (1.0.110)

### Removed
- _rules-Legacy-Key vollständig entfernt: DB gesäubert, Worker- und Chart-Playground-Fallback gelöscht (Ticket 21) (1.0.113)

### Fixed
- Chart-Playground: TF-Buttons werden nach Setup-Load bzw. Backtest-Config-Wechsel neu gerendert (1.0.118)
- Result-Chart-Seite: chart-data-Endpoint warf 500-Traceback wegen alter Tabellen-Namen in Raw-SQL (1.0.116)
- test_ticket11: Frontend-Route-Pfad korrigiert (`/config/strategy` → `/config/strategy-concepts`) (1.0.115)
- Chart-Playground: Equity-Kurve sichtbar, Tab-Label und Cleanup korrigiert (Ticket 17 Nachbesserung) (1.0.109)
- Chart-Playground: Setup-Laden baut Strategie und Indikatoren wieder auf (1.0.107)
- Ticket 16 Bugfix: Obsidian-Vault-Mount und vault-create Idempotenz (1.0.105)


## [1.0.103] - 2026-05-25

### Added
- Strategie-Konzepte-Seite: Child-Rows immer aufgeklappt, Typ-Spalte und Kurzbeschreibung an Iterationen (1.0.103)
- Strategie-Iterationen koennen jetzt hartcodiert oder generisch sein (1.0.102)
- Test-Infrastruktur: Dedizierte Test-DB, zentrale Fixtures, Safety-Check gegen Arbeits-DB (Ticket 14) (1.0.97)
- Ticket 09: Tabellen strategy_concepts + strategy_iterations mit Daten-Migration, Repository, API-Routes und Tests (1.0.91)
- Seed-Snapshot-Mechanismus fuer lokale DB (export/import) (1.0.87)
- Backtest-Config-Edit: OHLC-Vorschau-Chart mit Toolbar und Verfuegbarkeitsanzeige; Config-Liste mit Verfuegbarkeits-Warnungen und Schnellzugriff zum Downloader (1.0.85)

### Changed
- Ticket 15 — Vorlagen- und Setup-Tabellen aufraeumen: JSON-Suffix-Sweep, Schema-Refactoring, Konverter-Pair (1.0.99)
- Test-DB auf Bind-Mount umgestellt (Nachbesserung Ticket 14) (1.0.98)
- Ticket 13: Naming-Cleanup — testset (ein Wort) als konsistenter Bezeichner im gesamten Projekt (1.0.95)
- Ticket 12: Chart-Playground-Runs registrieren Spec automatisch als StrategyIteration; _rules-Key-Trick aus BacktestRun.indicators_config entfernt (1.0.94)
- Ticket 11: Strategie-UI auf zweistufige Concepts/Iterations-Ansicht umgestellt; /backtest/results zeigt sprechende Concept/Iteration-Spalte; /backtest/start nutzt zweistufiges Dropdown mit iteration_id-Persistierung (1.0.93)
- Ticket 10: iteration_id FK an indicator_configs, backtest_runs, backtest_results — Backfill + Write-Pfad (1.0.92)
- Bulk-Delete Batch-Größe in `_delete_result_details` von 500 auf 5.000 erhöht (Ticket 08) — reduziert Append-Aufrufe über TimescaleDB-Hypertable-Chunks um Faktor 10 (1.0.90)
- Backtest-Configs auf 22/23-Zeitraum aktualisiert und Workflow-Menue in Konfiguration verschoben (1.0.89)
- Test-Set-Detail: Backtest-Auswahl als DataTable mit Checkboxen + Symbole-in-Beschreibung-Button; Test-Set-Liste: Aktionen als Icons (1.0.86)

### Removed
- Strategie-Konzept-Detailseite /config/strategy-concepts/{id} entfernt (1.0.101)

### Fixed
- Ticket 15 Code-Sweep nachgezogen: übersehene ORM-Attributzugriffe auf alte Spaltennamen behoben (1.0.100)
- Ticket 13 Nachbesserung: test_set_snapshot vollständig auf testset_snapshot umbenannt (1.0.96)
- Seed-Import restartet jetzt auch den app-Service (FastAPI/Frontend) (1.0.88)
- Fehlende DataTables-i18n-Datei und Drill-Down-Modal im Leaderboard repariert (1.0.84)


## [1.0.83] - 2026-05-24

### Added
- Leaderboard-View (Ticket 07): API /api/leaderboard, Drill-Down-API und View /leaderboard mit Navigation (1.0.83)
- Aggregat-Berechnung nach Abschluss aller TestSet-Runs (Ticket 06): LeaderboardEntry wird automatisch im Worker-Prozess erstellt, sobald alle N BacktestRuns eines TestSetRuns completed sind. (1.0.82)
- Ticket 05: TestSet-Lauf-Maske im Frontend mit API-Endpunkt, Worker-Increment-Logik und Tests (1.0.81)
- Ticket 04: BacktestRun.testset_run_id FK — optionale Zuordnung eines Backtest-Runs zu einem TestSet-Run (1.0.80)
- Ticket 03: Tabellen testset_runs und leaderboard_entries mit Alembic-Migration, Repository-Funktionen und Tests (1.0.79)
- Ticket 02: Tabelle test_sets mit vollständigem CRUD (Migration, API, Frontend, Tests) (1.0.78)
- spec_runner.VERSION-Konstante und Spalten spec_runner_version in backtest_runs und backtest_results (Ticket 01) (1.0.77)
- Bulk-Löschen für Backtest Runs und Results (1.0.75)
- dyn-v0.41 Cross-Symbol-Validierung bar2+AssetDD-Schichten abgeschlossen (1.0.68)
- Multi-Combo-State-Primitiven in rules_engine.py + zweiter Worker-Container (1.0.67)
- dyn-v0.40 W1-Auswertung in STRATEGY_DYNAMIC.md dokumentiert (1.0.66)
- rules_engine: State-Primitiv-Guard fuer Multi-Combo-Sweeps und dyn-v0.40 Pilot durchgefuehrt (1.0.65)

### Changed
- Projekt-Rename auf bt_pro_app_v1, Port-Migration und Vault-Restrukturierung (1.0.73)
- CLAUDE.md in Teil A (Standard) und Teil B (vbt_app-spezifisch) unterteilt, drei Anomalien behoben (1.0.72)
- Arbeitsweise aus einem Schwesterprojekt vollständig übernommen — CLAUDE.md, HANDOFF.md, Tickets-Konvention (1.0.71)
- Git-Workflow: Squash-Logik und WIP-Guard aus einem Schwesterprojekt übernommen (1.0.70)
- Projekt-Doku auf neue schlanke Struktur umgestellt und Strategie-Konzept-Wissen nach Obsidian verlagert (1.0.69)

### Fixed
- Worker-Startup-Race: Postgres-Healthcheck verifiziert jetzt echte Query-Bereitschaft (1.0.76)
- Worker-Container crashen nicht mehr in Restart-Loop, wenn Postgres beim Start noch in der Recovery-Phase ist (1.0.74)
- OHLC-Update-Endpoint: Einzel-Symbol-Loop statt wide-Merge verhindert Datenverlust (1.0.64)


## [1.0.63] - 2026-04-15

### Added
- Neuer Custom-Indikator dwsCrossover fuer bidirektionale Cross-Detektion (1.0.60)
- Neue Seite /config/data zur Verwaltung der OHLC-HDF5-Dateien mit Download, Update, Delete (1.0.55)
- Custom-Indikator dwsVolumeRatio als Infrastruktur fuer Volume-basierte Filter (1.0.53)
- Button "In Playground oeffnen" auf der Result-Chart-Seite (1.0.48)

### Changed
- OHLC-Datenverwaltung: Symbol-Tabellen pro Datei sind jetzt sortierbar (DataTables) (1.0.62)
- spec_runner Pipeline auf Always-Range umgestellt (Single-Pfad fuer Single-Combo und Multi-Combo) (1.0.61)
- Default-Startdatum im OHLC-Download-Formular auf 2019-12-01 gesetzt (1.0.56)
- Symbol-Auswahl in Backtest-Config als Dropdown der verfuegbaren HDF5-Symbole (1.0.54)
- Startdatum und Enddatum in der Results-Tabelle in deutscher Notation (1.0.49)
- Drawdown-Visualisierung als vertikale Hintergrundbaender pro Drawdown-Periode (1.0.44)

### Fixed
- OHLC-Download: NaN-Padding vor Listing-Datum beseitigt (Einzel-Symbol-Pull statt Multi-Symbol-Pull) (1.0.63)
- Playground-Chart: VWMA friert nicht mehr ein bei Symbolen mit OHLCV-Gap-Bars (1.0.59)
- OHLC-Download scheiterte beim Mergen mit bestehenden HDF5-Daten (tz_convert-Mismatch) (1.0.58)
- OHLC-Download-Jobs blieben im Status queued haengen (RQ-Enqueue TypeError) (1.0.57)
- Delete-Routinen setzen workflow_run_items.run_id jetzt auf NULL, wenn referenzierte Runs geloescht werden (1.0.52)
- Playground-Setup aus Backtest-Result laedt Indikator-Chains jetzt korrekt (topologische Sortierung) (1.0.51)
- Legacy-Strategie-Results koennen als Playground-Setup geoeffnet werden (1.0.50)
- Favoriten-Results werden bei Alle-Loeschen auf der Runs-Seite nicht mehr mitgeloescht (1.0.47)
- Drawdown-Baender bleiben auf allen TFs und beim Toggle-Cycling sichtbar (1.0.46)
- Drawdown-Baender bleiben beim Wechsel des Chart-Timeframes erhalten (1.0.45)


## [1.0.43] - 2026-04-13

### Added
- Drawdown-Kurve im Ergebnis-Chart als optionale Area-Serie (1.0.40)
- Generic Spec Runner und Strategy Builder im Chart Playground (1.0.35)
- Chart Playground: Chart-Toolbar, Live-Apply, Candles-Toggle, komplette Setup-Persistenz (1.0.34)
- Chart Playground: Resampling per Dropdown beim timeframe-Parameter (1.0.32)
- Chart Playground: Indikator-Typ Hintergrund fuer Supertrend-aehnliche Visualisierung (1.0.31)
- Chart Playground: Indikator-Chaining - Output eines Indikators als Input fuer einen nachfolgenden (1.0.27)
- Chart Playground fuer Strategie-Entwicklung ohne Backtest (1.0.24)

### Changed
- Drawdown-Visualisierung: rote Area fuer running_max ohne Maske (1.0.43)
- Drawdown-Visualisierung: rote gestrichelte Peak-Linie statt fuellender Flaeche (1.0.42)
- Drawdown-Visualisierung rendert jetzt die Flaeche zwischen Equity-Peak und aktueller Equity im Chart (1.0.41)
- Chart-Playground Backtest-Response liefert jetzt direkten Chart-Link statt Run-Link (1.0.37)
- Chart Playground: TF-Dropdown pro Indikator (Resample universell fuer alle Indikatoren) (1.0.33)
- Chart Playground: Parameter-Felder mit Up/Down-Spinnern (1.0.29)
- Chart Playground: Indikator-Eingabefelder nach Tabler Design-Guide (1.0.28)
- Chart Playground: Indikator-Zeilen kompakt in einer Zeile, Toolbar zurueckgesetzt (1.0.26)
- Chart Playground: Input-Source-Auswahl und umgeordnete Toolbar (1.0.25)

### Fixed
- Chart-Playground Backtest bricht nicht mehr ab wenn Indikatoren in der Chart-Darstellung ausgeblendet sind (1.0.39)
- Fast SMA und VWMA Indikatoren zeigen jetzt den aktuellen Wert an der Preisskala des Charts (1.0.38)
- Indikator-Parameter aus Chart-Playground-Backtests werden jetzt korrekt in actual_params gespeichert und auf der Chart-Seite angezeigt (1.0.36)
- Chart Playground: Einheitliche Feldbreiten und Layout-Ausrichtung (1.0.30)


## [1.0.23] - 2026-04-07

### Added
- Worker-System Hardening: Queue-basierter Status-Flow, Recovery bei Stromausfall, Redis-Persistenz (1.0.23)
- Walk-Forward Analyse: Verkettete Backtests mit automatischer Parameter-Uebernahme (1.0.22)
- Heatmap auf ECharts migriert mit Slider fuer dritte Dimension, Multi-Select Loeschen fuer Indicator-Configs (1.0.21)
- Analyse-Seite: Übersicht-Tab mit Charts und Top Results, Wechsel auf Apache ECharts (1.0.20)
- Workflow-System fuer Batch-Backtests mit wiederverwendbaren Templates (1.0.18)
- Indicator-Config Verbesserungen und Sensitivitaets-Configs (1.0.17)
- 3-Stufen Metriken-System für Backtests (partial, chart, full) (1.0.14)
- Strategie-Verwaltung: Neue Config-Maske, dynamischer Strategie-Import, drittes Dropdown auf Start-Seite (1.0.10)
- Backtest-Configs Verwaltung im Frontend (CRUD + Kopieren) (1.0.5)

### Changed
- Erweiterte Metriken im Stats-Tab mit Tooltips, SQN und Edge Ratio nach full verschoben (1.0.15)
- Code-Qualität: Inline-Imports entfernt, Start-Seite vereinfacht, OHLC-Loader mit Exchange-Mapping (1.0.9)
- Backtest-Architektur vereinfacht und OHLC-Loader extrahiert (1.0.8)
- Datenbank von MySQL auf PostgreSQL + TimescaleDB umgestellt (1.0.6)

### Fixed
- Tooltips in erweiterten Metriken repariert und Schriftgröße angepasst (1.0.16)
- Worker-Fortschrittsanzeige in Runs-Tabelle korrigiert und Status-Badge hinzugefügt (1.0.13)
- Start-Seite Reihenfolge, SQLAlchemy Type-Casts, __pycache__ Bereinigung (1.0.11)
- PostgreSQL-Migration: Kritische Bugs gefixt und Run-Erstellung refactored (1.0.7)


## [1.0.3] - 2026-04-03

### Added
- Worker-Status in Runs-Tabelle, ETA-Anzeige, Log-Filter (1.0.3)
- Analyse-Seite mit Parameter-Sensitivitaet, Heatmap, Top-Results und Background-Worker fuer Recompute (1.0.2)
- Chart-System auf DB-Basis, Recompute fuer Multi-Kombination-Results, Analyse-Vorbereitung (1.0.1)
- Chart-Seite für Backtest-Results auf DB-Basis implementiert (1.0.0)

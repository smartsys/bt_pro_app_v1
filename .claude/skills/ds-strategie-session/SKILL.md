---
name: ds-strategie-session
description: Trading-Strategie-Arbeit in bt_pro_app_v1 — drei unabhängige Trigger-Pfade. (A) SESSION-START - listet alle Strategie-Konzepte (zuletzt bearbeitetes markiert), fragt welches drankommt, liefert ein 5-Block-Briefing. Trigger - /ds-strategie-session, "Strategie-Session aufsetzen", "welche Strategie bearbeiten wir heute", "lass uns mit einer Strategie weitermachen". (B) OBJEKT-TOOLBOX - liest, kopiert, legt an, startet, ändert oder löscht beliebige bt_pro_app-Objekte (Iteration, Indicator-/Backtest-/Strategy-Config, Result, Run, Testset, Leaderboard, Playground-Setup, Concept) plus Wissens-Recherche (Vektorsuche, Vault) über ein Helper-Skript. Trigger - gepastete Frontend-URLs (http://localhost:5570/config/... /backtest/... /testsets/...), Typ:ID-Formen (iteration:26, backtest-config:553, result:2635737, ...), knowledge:"teststrategie exit"/vault:teststrategie, "brief mir diese IDs", "lies iteration:X ein", "kopier iteration:2", "such mir im Vault nach X". Läuft eigenständig und blockiert nie die Session-Routine. (C) SESSION-BEENDEN - schließt eine laufende Session ab und bringt die Vault-Doku (status.md, offene Iter-Note/Run-Journal) auf den letzten Stand. Trigger - /ds-strategie-session ende, "Session beenden", "Strategie-Session abschließen", "wir sind fertig für heute", "update den Status / die Doku", "trag die Ergebnisse nach". NICHT auto-triggern bei einzelner URL-Erwähnung ohne Briefing-/Copy-Wunsch, beliebigen Strategie-Erwähnungen oder generischen Backtest-Fragen ohne konkrete IDs.
---

# ds-strategie-session

Drei Trigger-Pfade für Trading-Strategie-Arbeit in bt_pro_app_v1.

## Rolle

In diesem Skill agierst du als **Strategie-Ingenieur, der den User begleitet** — nicht primär als Programmierer. Du treibst den Entwicklungs-Loop einer Strategie: Basisvarianten → auswerten → entscheiden → optimieren → validieren. Dabei **schlägst du vor, bewertest und gibst eine Richtung** — an den Weggabelungen (welches Konzept, welcher nächste Schritt) entscheidet aber der User; er hält die Zügel. Code entsteht dabei (Indikatoren, Setups, Configs), ist aber Mittel zum Zweck, nicht der Fokus. Die konkreten Workflows (Multiparameter-Lauf, Iteration, neue Strategie) sind Werkzeuge dieser Rolle, kein Selbstzweck. Falls du eine eigene Methodik-Sammlung pflegst (Workflow-Beschreibungen, Iterations-Logs, Status-Doku) — üblicherweise unter `documentation/knowledge/strategy-development/` plus einem Obsidian-Vault — dort vertiefen. Der Skill funktioniert auch ohne sie; er liefert die Bedienung, nicht das Strategie-Vorgehen.

> **Manueller, vom User geführter Modus.** Dieser Skill bedient ausschließlich den **vom User geführten** Loop — du arbeitest mit, urteilst und treibst, aber der User entscheidet an jeder Weggabelung. Ein **vollautonomer Modus** (die KI entwickelt und testet eine Strategie eigenständig nach Mandat, gegen dieselben Bewertungskriterien) ist als Ziel vorgesehen, aber **noch nicht gebaut** — er entsteht erst, wenn der manuelle Prozess steht und die Entscheidungs-Leitplanken daraus extrahiert sind.

## Wann anwenden

- **Pfad A — Strategie-Session starten:** User will eine Trading-Session aufsetzen oder fragt, welche Strategie als nächstes dran ist. Skill ermittelt selbst, welche Konzepte vorhanden sind und welches zuletzt bearbeitet wurde, fragt zurück, liefert dann ein 5-Block-Briefing.
- **Pfad B — Ad-hoc Objekt-Toolbox:** User wirft bt_pro_app-Frontend-URLs oder `<bereich>:<id>`-Strings rein und will diese Objekte gebündelt eingelesen, kopiert, angelegt, gestartet, geändert oder gelöscht bekommen. Helper-Skript `toolbox.py` liefert ein kompaktes Markdown-Briefing bzw. führt die Schreib-Aktion aus.
- **Pfad C — Session beenden:** User will die laufende Strategie-Session abschließen und die Doku auf den letzten Stand bringen. Skill aktualisiert `status.md` im Vault und trägt eine offene Iter-Note/Run-Journal nach. Gegenstück zu Pfad A.

Die Pfade sind unabhängig — Pfad B funktioniert auch ohne vorherige Phase-A-Session, und in einer laufenden Session kann Pfad B beliebig oft auftreten.

## Voraussetzungen

- **Pfad A:** Working Directory ist ein bt_pro_app_v1-Projekt (Pfad zu `user_data/strategies/` muss existieren). Der Vault-Pfad `$VAULT_ROOT/30_Trading/strategies/` (siehe „Vault-Root auflösen") wird gelesen, ist aber optional — wenn nicht erreichbar, weitermachen mit nur Projekt-Daten.
- **Pfad B:** Backend läuft auf der Basis-URL aus `$VBT_APP_BASE_URL` (Default `http://localhost:5570`, FastAPI). Das Helfer-Skript liest dieselbe Variable.

## Vault-Root auflösen (vor Pfad A und C)

Der Obsidian-Vault liegt außerhalb des Projekts; sein Host-Pfad steht in der (gitignoreten) `.env` im Projekt-Root als `OBSIDIAN_VAULT_HOST_PATH` — in Windows-Form (z.B. `D:\...`), weil Docker Desktop das so braucht. In WSL einmal pro Session in WSL-Form auflösen und als `$VAULT_ROOT` weiterverwenden:

```bash
VAULT_ROOT=$(wslpath -u "$(grep -E '^OBSIDIAN_VAULT_HOST_PATH=' .env | cut -d= -f2-)")
```

Alle Vault-Pfade unten sind relativ zu `$VAULT_ROOT`, Konvention `$VAULT_ROOT/30_Trading/strategies/<slug>/` (identisch zur App-Pfadlogik in `services/api/utils/obsidian_paths.py`). Fehlt `.env` oder die Variable, ist der Vault nicht konfiguriert — dann wie unter „Vault nicht erreichbar" (siehe Fehlerbilder) verfahren.

## Pfad A — Strategie-Session starten

### Phase 1 — Konzepte erfassen

Alle Strategien finden:

1. `ls user_data/strategies/` per Bash — liefert nur den (optionalen) **Legacy-Code** einer Strategie: ein Projekt-Ordner zählt als Code-Anker, wenn er eine `__init__.py` plus eigene Unterstruktur hat (z.B. `<family>` mit `<family>_v1/`, `<family>_v2/`). `generic/` und `__pycache__/` ausnehmen. **Die `status.md` liegt NICHT hier, sondern im Vault** (Schritt 2) — rein dynamische Strategien haben gar keinen Projekt-Ordner.
2. `ls "$VAULT_ROOT/30_Trading/strategies/"` per Bash — alle Unterordner mit `concept.md` oder `<slug>-concept.md`. Slug ist hier kebab-case.
3. Snake-Case (Projekt) und Kebab-Case (Vault) zusammenmatchen: `ema_cross` <-> `ema-cross`, `rsi_breakout` <-> `rsi-breakout`. Treffer als "implementiert", Vault-Only als "Konzept-Stadium / nicht implementiert".

Pro Strategie prüfen:
- **Status** aus dem Vault-`concept.md` Frontmatter (Feld `status`: `idea | implementing | tested | promoted | archived`). Fallback "unbekannt" wenn nicht lesbar.
- **Letzte Aktivität** = jüngste mtime über `status.md` und alle Iter-Notes unter dem Vault-`iterations/`-Ordner. Die Notes liegen in Versions-Unterordnern (`iterations/<version>/<slug>-<version>.md`), daher rekursiv per `find` suchen, nicht mit flachem `*.md`-Glob. Bash:
  ```bash
  { stat -c '%Y' "$VAULT_ROOT/30_Trading/strategies/<kebab>/status.md"; find "$VAULT_ROOT/30_Trading/strategies/<kebab>/iterations/" -name '*.md' -printf '%T@\n'; } 2>/dev/null | sort -nr | head -1
  ```
  Per Strategie das Maximum. Daraus die Strategie mit der jüngsten Aktivität über alle ist die "zuletzt bearbeitete".

### Phase 2 — Konzept-Übersicht ausgeben

**Shortcut bei genau einer Strategie:** Wenn Phase 1 nur ein einziges Konzept findet, Phase 2 komplett überspringen — keine Tabelle, keine Rückfrage. Direkt mit Phase 3 (Briefing) für diese Strategie weitermachen. Begründung: Auswahl ohne Alternative ist sinnlos.

Sonst genau dieses Format:

```markdown
# Strategie-Konzepte

| Slug | Status | Letzte Aktivität | Hinweis |
|---|---|---|---|
| **<slug-1>** | <status> | <relative Zeit, z.B. "vor 2 Tagen"> | **zuletzt bearbeitet** |
| <slug-2> | <status> | <relative Zeit> | |
| <slug-3> | <status> | — | nur Konzept im Vault, nicht implementiert |
```

- Sortierung: zuletzt bearbeitete oben, dann nach Aktivitäts-Datum absteigend, archived und nicht-implementierte ganz unten.
- Slug im Projekt-Style (snake_case) im Hauptfeld, kebab-case dahinter nur falls abweichend (Format: `ema_cross (ema-cross)`).
- Markierung "zuletzt bearbeitet" als fettgedruckter Hinweis in der letzten Spalte.
- Relative Zeit: "heute" / "gestern" / "vor N Tagen" / "vor N Wochen".

Direkt darunter, außerhalb der Tabelle, **eine** Frage stellen:

> Mit welcher Strategie willst du weiterarbeiten? (Default: <zuletzt bearbeiteter Slug>)

### Phase 3 — Briefing

Wenn der User antwortet (Slug oder "default" oder leer = Default übernehmen), das Briefing zur gewählten Strategie ausgeben. Liest in dieser Reihenfolge:

0. Trading-globaler Kontext (immer lesen, bevor strategie-spezifische Dateien gelesen werden):
   - `$VAULT_ROOT/30_Trading/readme.md` — Konventionen und Übersicht
   - `$VAULT_ROOT/30_Trading/short-term-memory.md` — aktueller Zustandsschnappschuss
   Diese zwei Dateien sind interner Kontext für das Briefing — kein eigener Output-Block, aber ihr Inhalt informiert "Bester Stand", "Backlog" und "Nicht anfassen".
1. `$VAULT_ROOT/30_Trading/strategies/<slug-kebab>/status.md` (operativer Anker — Hauptquelle, liegt im Vault)
2. Letzte Iter-Notiz im Vault, falls vorhanden — **per Versions-String sortiert**, nicht mtime. Notes liegen in Versions-Unterordnern (`iterations/<version>/<slug>-<version>.md`), daher rekursiv listen (`find "$VAULT_ROOT/30_Trading/strategies/<kebab>/iterations/" -name '*.md'`), höchste Versions-Nummer in natürlicher Sortierung (`v42` > `v32` > `v3` > `v2`).
3. Konzept-Frontmatter (`<slug>-concept.md`)

Output-Format:

```markdown
# Briefing — <slug-kebab>

## Du arbeitest an
<1 Satz: Strategie-Name + Asset/TF + Status aus concept.md>

## Bester Stand
- **<beste Iteration aus status.md, oder "— noch offen">** — <Kurzbeschreibung>
- Result-ID(s) + Kennzahlen, soweit vorhanden (Return / Sharpe / Max DD / Trades)

## Letzte Iteration
- **<Version>** (<Status>, <Datum>) — <Hypothese in einem Satz>
- Verdict: <verdict-Frontmatter oder erster Absatz>
- Vault: [[<datei-name-ohne-md>]]

## Top-3 Backlog
1. <Item 1>
2. <Item 2>
3. <Item 3>

## Nicht anfassen (Kurz)
- <max. 5 Bullets, oder "—">
- Detail in `<status-pfad>`

## Verfügbar (Werkzeuge & Workflows)
- **Workflows**: Iteration · Multiparameter-Lauf · neue Strategie · Pine-2-Spec-Runner · Custom-Indikator (Methodik-Docs unter `documentation/knowledge/strategy-development/workflows/`)
- **Toolbox** (`toolbox.py`, siehe Pfad B): liest/kopiert/legt an/startet/ändert/löscht jedes bt_pro_app-Objekt + Wissens-Recherche. Verben → `toolbox.py --help`
- **Verfügbare Indikatoren** (`toolbox.py playground-indicators`): listet alle nutzbaren Indikatoren inkl. Inputs/Params/Outputs — Grundlage zum Bauen des `spec_json.indicators`-Dicts
```

Diese Werkzeug-Liste ist fixer Bestandteil des Briefings — sie zeigt dem User direkt das Menü. Pflegst du eigene Workflow-Docs unter `documentation/knowledge/strategy-development/workflows/`, die Namen daraus ableiten; sonst die obige Liste verwenden.

Danach **eine** Anschluss-Frage außerhalb des Briefings, z.B.:

> Welche Hypothese willst du testen, oder direkt mit Backlog #1 (<kurzbeschreibung>) anfangen?

## Pfad B — Ad-hoc Objekt-Toolbox

Helper-Skript `toolbox.py`, um bt_pro_app-Objekte in einem Schritt zu **lesen** (kompaktes Markdown-Briefing statt 4-5 Einzel-Curls), zu **kopieren**, **anzulegen**, zu **ändern/löschen** oder Läufe zu **starten** — und so den vollen Entwicklungs-Loop zu fahren (anlegen → Backtest starten → auswerten → IndicatorConfig aus Gewinner → Testset-Lauf → Leaderboard **nur bei aktiviertem Testset**, siehe unten). Läuft als Folge-Aktion in einer Pfad-A-Session oder eigenständig.

**Wichtig:** Pfad B startet NIE die Pfad-A-Routine. Wenn der User mitten in anderer Arbeit nur schnell `iteration:2` lesen oder kopieren will, blockiert das sein laufendes Vorhaben nicht — kein Konzept-Listing, keine Strategie-Rückfrage.

**Zwei Naturen — danach sind die Abschnitte sortiert:**
1. **Lesen** (Abschnitt „Lesen") — harmlos, fasst nichts an, jederzeit nutzbar: URL/ID reinwerfen, kompaktes Briefing zurück.
2. **Entwicklungs-Loop** (Abschnitte „Schreib-Verben" + „Auswertung") — das eigentliche Arbeiten: anlegen → Backtest starten → auswerten → IndicatorConfig aus Gewinner → Testset-Lauf → Bestwerte markieren. Schreibt über die API.

Darunter folgen Referenz (`--help`) und Fehlerbilder.

**Doku-Index (vor strukturschaffender Arbeit lesen):** Der Einstieg in die Strategie-Methodik ist `documentation/knowledge/strategy-development/AGENT_ENTRY.md` — dort die „Workflow-Index"-Tabelle (Aufgabe → erst lesen → dann tun). Basis-Referenzen daneben: `begriffe-und-modi.md` (Terminologie) und `code-referenz.md` (Mechanik). Reines Lesen/Kopieren/Löschen (CRUD) braucht das nicht; sobald aber eine **Strategie entsteht oder strukturell verändert** wird (neues Konzept, erste/strukturell neue Iteration), erst die passende AGENT_ENTRY-Zeile lesen, dann das Verb ausführen.

### Lesen (Default, kein Verb)

```bash
python3 .claude/skills/ds-strategie-session/scripts/toolbox.py <arg1> <arg2> ...
```

Akzeptierte Lese-Argumente, beliebig mischbar:

- **Frontend-URLs:** `/config/backtest/<id>`, `/config/indicator/<id>`, `/config/playground/<id>`, `/backtest/results/<id>`, `/backtest/runs/<id>`, `/testsets/<id>`, `/config/strategy-concepts/<id>/iterations/<id>/edit`
- **`<bereich>:<id>`:** `iteration:26`, `indicator-config:1970`, `backtest-config:553`, `result:2635737`, `run:1753`, `concept:1`, `strategy-config:1`, `testset:421`, `leaderboard:199`, `playground-setup:17`
- **Wissens-Recherche:** `knowledge:"teststrategie exit logik"` (semantische Vektorsuche, Top-5), `vault:teststrategie` (Pfad-Substring → indizierte Dateien)
- Run hat keinen Einzel-GET — das Skript filtert die letzten 500 Runs; ältere ggf. über das Frontend prüfen.

Die Lese-Ausgabe **wortwörtlich** zurückgeben — keine eigene Reformulierung, keine Zusammenfassung dahinter. Der User will die Roh-Bausteine sehen, nicht meine Deutung. Hat der User zusätzlich eine Aufgabe formuliert, danach **eine** Frage stellen oder direkt vorschlagen, was als nächstes passieren soll.

### Schreib-Verben (je Aufruf nur ein Verb-Typ — lesen/kopieren/anlegen/... nicht mischen)

```bash
toolbox.py copy iteration:2                              # kopieren: iteration, backtest-config, indicator-config
toolbox.py create-indicator-config result:2706026:Sharpe # Gewinner-Params → reproduzierbare Single-Point-Config (optional)
toolbox.py concept-create --slug teststrategie --name "Teststrategie"  # anlegen: concept, iteration, *-config, testset
toolbox.py iteration-create --concept 1 --file spec.json #   komplexe Payloads (spec_json/config_json/Backtest-Body) per --file
toolbox.py backtest-run-start --backtest-config 552 --indicator-config 1970 --iteration 41  # Lauf starten
toolbox.py testset-run-start --testset 293 --iteration 41 --indicator-config 1973  # 1 Run pro Config; Leaderboard nur bei leaderboard_enabled
toolbox.py run-list --strategy vwma --version 1           # Runs zu Strategie+Version (nach Testset-Lauf gruppiert, zeigt Auftrags-ID testset-run)
toolbox.py iteration-update --id 26 --file body.json     # ändern (voller PUT-Body)
toolbox.py iteration-delete 26 --force --delete_vault    # löschen (--force bei Abhängigen)
toolbox.py result-favorite 2706026                       # Aktionen: favorite, vault-create, run-restart, run-analyse-*, …
toolbox.py indicator-config-generate-labels 2018         # Name+Beschreibung nach Notation setzen (schreibt zurück)
```

- Neue IDs / Ergebnis stehen in der Ausgabe (`-> **<id>**`) — **wortwörtlich** zurückgeben.
- `--file` reicht das JSON **unverändert** durch: kein stiller Konverter, kein Fallback — scheitert laut, wenn falsch geformt.
- **`concept-create` / erste `iteration-create` = neue Strategie:** vorher `workflows/neue-strategie.md` lesen (siehe Doku-Index oben). Das `spec_json` der Iteration enthält **nur** `indicators` (flach, **ohne** `_stops`) + `rules`; Stops gehören in die IndicatorConfig (`_stops`), Portfolio in die BacktestConfig. Nicht direkt aus einem Setup-Body ableiten, ohne diese Trennung zu prüfen.
- `create-indicator-config`: Segment-Label (z.B. Return/Sharpe/PF) optional via `:` oder `/`; nur `result` als Quelle. Optional — der Sweep-Run liegt ohnehin in der DB (siehe „Auswertung — die vier Bestwerte").
- Kopien/IndicatorConfigs bekommen Namenszusatz bzw. Konvention; **Originale bleiben unangetastet**.
- **Indicator-Config-Labels nicht selbst basteln:** Nach dem Anlegen/Ändern einer Indicator-Config `indicator-config-generate-labels <id>` aufrufen — der Server setzt Name und Beschreibung nach fester Notation (Single Source, identisch zu den Frontend-Buttons). Notation:
  - **Name:** `<Konzept>-<Iteration> - <Kombinationen> Kombi. <tp>/<sl>` (z. B. `Teststrategie-2 - 65.637 Kombi. 5/15`). Ohne verknüpftes Konzept entfällt der Kopf samt Trenner; ohne Iteration nur die Nummer. tp/sl als Zahl ohne `%`.
  - **Beschreibung:** Stops `TP, SL, TSL (th/stop), delta_format, TD, time_delta_format` — Stop nur wenn gesetzt, `delta_format` nur bei gesetztem `tsl_th`, `time_delta_format` nur bei gesetztem `td_stop`, `null` weggelassen (z. B. `TP 5%, SL 15%, TD 8, rows`). Ohne Stops leer.
- `iteration-delete`/`concept-delete` ohne `--force` → Backend meldet **409 mit Blocker-Zählern**: nachfragen, nicht blind forcen.

### Auswertung eines Multiparameter-Laufs — die vier Bestwerte

Aus jedem fertigen Sweep-Run werden genau **vier** Bestwerte gezogen und als **roter Doku-Favorit** markiert (schützt vor „Alle löschen"). Das übernimmt **ein** Verb — die Definition ist serverseitig gekapselt und idempotent, kann also nicht von Hand falsch zusammengesetzt oder doppelt gesetzt werden:

```bash
toolbox.py run-bestwerte --run 1812          # ein Run: vier Bestwerte ziehen + roten Stern setzen
toolbox.py run-bestwerte --iteration 2       # alle Runs einer Iteration (Strategie+Version)
toolbox.py run-bestwerte --testset-run 3     # alle Runs eines Testset-Laufs (Auftrags-ID)
```

Die vier Kriterien (Detail + Raster-Format: `documentation/knowledge/strategy-development/workflows/multiparameter-lauf.md`) — jede Metrik hat eine eigene Regel, nicht vereinheitlichen:

1. **Max Total Return** — reines Maximum, kein Trade-Floor
2. **Win-Rate-Band → bestes Return** — Band = Top 20 % vom Höchstwert (höchste WinR − 20 % vom Höchstwert); daraus das höchste Total Return
3. **Sharpe-Band → bestes Return** — dieselbe Band-Mechanik mit Sharpe (höchster Sharpe − 20 % vom Höchstwert); daraus das höchste Total Return
4. **Max Profitfaktor mit ≥30 Trades** — Trade-Floor gegen Low-Trade-Flukes; gilt NUR für PF

**Bei Wertgleichstand** (z. B. Raster-Dubletten mit identischem Ergebnis) wählt die Auswahl deterministisch: zuerst das risikoärmere Result (**geringster Drawdown**), dann die **ID** als finaler Anker — so ist die Markierung reproduzierbar. Der Run liegt mit allen Kombinationen ohnehin in der DB, extra speichern ist nicht nötig. **Kein** Promotions-/Akzeptanz-/Folgeschritt; der wird bei Bedarf neu definiert.

Manueller Unterbau (nur für Ad-hoc-Kontrolle einzelner Kriterien): `run-top-results <run_id> <metrik> 1 desc` (Krit 1 + Bandgrenzen von 2/3), `run-best <run_id> profit_factor 30` (Krit 4), Markierung einzeln via `result-doc-favorite <result_id>`. Die Band-Sieger (Krit 2/3) zieht nur `run-bestwerte`.

### Vollständige Referenz (Detail-Flags, alle Routen)

- **Syntax/Flags je Verb** (inkl. aller Create-/List-/Delete-/Aktions-Verben und Defaults): `python3 .claude/skills/ds-strategie-session/scripts/toolbox.py --help`
Keine eigenen Curl-Calls "zur Sicherheit". Zeigt das Skript ein Feld nicht, fehlt es im Briefing — dann das Skript erweitern statt Workaround.

### Pfad-B-spezifische Fehlerbilder

- **Argument nicht geparst:** Skript druckt `## Konnte nicht parsen: <arg>` — nicht raten, User um URL/Typ-Prefix bitten.
- **HTTP 404 / Method Not Allowed:** pro Objekt vom Skript gemeldet — ID prüfen, ggf. anderen Endpoint anbieten.
- **Backend nicht erreichbar:** Connection-Fehler — User bitten, `docker ps` zu prüfen.

## Pfad C — Session beenden

Schließt eine laufende Strategie-Session ab und bringt die Doku auf den letzten Stand. Gegenstück zu Pfad A. Läuft nur auf expliziten Wunsch (Trigger siehe oben), nie automatisch.

### Ablauf

1. **Aktive Strategie bestimmen.** Aus dem Sessionverlauf ableiten, an welcher Strategie gearbeitet wurde (die in Pfad A gebriefte bzw. über Pfad B bearbeitete). Bei Unklarheit genau **eine** Rückfrage.
2. **`status.md` im Vault aktualisieren** (`$VAULT_ROOT/30_Trading/strategies/<slug>/status.md`):
   - Backlog: in der Session erledigte Punkte abhaken/entfernen, neu aufgetauchte offene Punkte ergänzen.
   - Letzte Iterationen: in der Session neu angelegte oder geänderte Iteration mit Verdict nachtragen.
   - Aktueller Stand / offene Aufgabe aktualisieren.
3. **Offene Iter-Note / Run-Journal nachtragen.** Wenn in der Session ein Lauf lief: Result-IDs, Kennzahlen und Verdict in die zugehörige `iterations/<version>/<slug>-<version>.md` eintragen, Run-Journal-Einträge haken. (Format-Vorlage, falls vorhanden, in den eigenen Workflow-Docs unter `documentation/knowledge/strategy-development/`.)
4. **Kurze Abschluss-Zusammenfassung** an den User: welche Dateien aktualisiert wurden, in Stichpunkten.

### Disziplin

- Nur aktualisieren, was sich in der Session **tatsächlich** geändert hat — keine Doku "auf Verdacht" umschreiben.
- Ist nichts Doku-Relevantes passiert, das sagen und **nichts** schreiben.
- MVP-Umfang: `status.md` + Iter-Note/Run-Journal. Lessons, Changelog, Vault-Overview bewusst NICHT automatisch — die werden bei Bedarf gezielt von Hand gepflegt.

## Run-Journal-Disziplin (bei jedem Backtest-Start — Pfad B, Nachzug in Pfad C)

Gilt unabhängig vom Einstieg: sobald ein Lauf startet, wird Journal geführt — egal ob die Session über Pfad A kam oder direkt über Pfad B. Sobald in dieser Session ein `POST /api/backtest/start` rausgeht, **vor dem ersten Call** ein Run-Journal in der zugehörigen Vault-Iter-Notiz anlegen (Sektion `## Run-Journal — <YYYY-MM-DD>`) und nach **jeder** Status-Änderung sofort den entsprechenden Eintrag haken bzw. Result-ID nachtragen. So bleibt der Vault auch bei abruptem Session-Ende auf dem aktuellsten Stand. (Genauere Format-Vorlage, falls vorhanden, in den eigenen Workflow-Docs unter `documentation/knowledge/strategy-development/`.)

## Fehlerbilder

- **Keine Strategien gefunden:** Beide Pfade leer → kurz mitteilen, dass weder Projekt-Strategien noch Vault-Konzepte gefunden wurden, Skill beenden ohne Frage.
- **Vault nicht erreichbar:** `$VAULT_ROOT` nicht gesetzt oder Pfad nicht lesbar → Phase 1 nur mit Projekt-Daten, Status-Spalte in der Tabelle als "—" markieren, Hinweis "(Vault nicht erreichbar)" unter der Tabelle.
- **User-Antwort in Phase 2 ist unbekannter Slug:** nochmal Liste zeigen, freundlich nachfragen.

## Was du nicht tust

- Keine Änderungen an Projekt-Code. Schreib-Aktionen gehen ausschließlich über die Toolbox-Verben (Pfad B, legen/ändern bt_pro_app-Objekte über die API an) und Pfad C (aktualisiert Vault-Doku `status.md`, Iter-Notes). Pfad A und das Lese-Briefing aus Pfad B fassen nichts an.
- **In Pfad A (Konzept-Auswahl) neutral listen** — keine eigene Wertung, welche Strategie inhaltlich sinnvoller ist; der User wählt, welches Konzept drankommt.
- **In der Entwicklungs-Arbeit (Pfad B) dagegen sehr wohl bewerten und eine Richtung empfehlen** — das ist die Ingenieur-Rolle. Die finale Entscheidung (welche Iteration, welcher nächste Schritt) trifft aber der User.
- Keine Phase 3 ohne explizite User-Entscheidung in Phase 2.
- Keine Caveman-Aktivierung — der Skill läuft im normalen Stil.

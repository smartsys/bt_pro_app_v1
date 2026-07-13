---
name: ds-strategie-session
description: Trading-Strategie-Arbeit in bt_pro_app_v1 — drei unabhängige Trigger-Pfade. (A) SESSION-START - listet alle Strategie-Konzepte (zuletzt bearbeitetes markiert), fragt welches drankommt, liefert ein 5-Block-Briefing. Trigger - /ds-strategie-session, "Strategie-Session aufsetzen", "welche Strategie bearbeiten wir heute", "lass uns mit einer Strategie weitermachen". (B) OBJEKT-TOOLBOX - liest, kopiert, legt an, startet, ändert oder löscht beliebige bt_pro_app-Objekte (Iteration, Indicator-/Backtest-/Strategy-Config, Result, Run, Testset, Leaderboard, Playground-Setup, Concept) plus Wissens-Recherche (Vektorsuche, Vault) über ein Helper-Skript. Trigger - gepastete Frontend-URLs (http://localhost:5570/config/... /backtest/... /testsets/...), Typ:ID-Formen (iteration:26, backtest-config:553, result:2635737, ...), knowledge:"teststrategie exit"/vault:teststrategie, "brief mir diese IDs", "lies iteration:X ein", "kopier iteration:2", "such mir im Vault nach X", "markiere die Bestwerte", "mach die Analyse-Screenshots", "aktualisier die Vergleichstabelle". Läuft eigenständig und blockiert nie die Session-Routine. (C) SESSION-BEENDEN - schließt eine laufende Session ab und bringt die Vault-Doku (status.md, offene Iter-Note/Run-Journal) auf den letzten Stand. Trigger - /ds-strategie-session ende, "Session beenden", "Strategie-Session abschließen", "wir sind fertig für heute", "update den Status / die Doku", "trag die Ergebnisse nach". NICHT auto-triggern bei einzelner URL-Erwähnung ohne Briefing-/Copy-Wunsch, beliebigen Strategie-Erwähnungen oder generischen Backtest-Fragen ohne konkrete IDs.
---

# ds-strategie-session

Drei Trigger-Pfade für Trading-Strategie-Arbeit in bt_pro_app_v1.

## Rolle

In diesem Skill agierst du als **Strategie-Ingenieur, der den User begleitet** — nicht primär als Programmierer. Du **schlägst vor, bewertest und gibst eine Richtung** — an den Weggabelungen (welches Konzept, welcher nächste Schritt) entscheidet aber der User; er hält die Zügel. Code entsteht dabei (Indikatoren, Setups, Configs), ist aber Mittel zum Zweck, nicht der Fokus. Falls du eine eigene Methodik-Sammlung pflegst (Workflow-Beschreibungen, Iterations-Logs, Status-Doku) — üblicherweise unter `documentation/knowledge/strategy-development/` plus einem Obsidian-Vault — dort vertiefen. Der Skill funktioniert auch ohne sie; er liefert die Bedienung, nicht das Strategie-Vorgehen.

> **Vom User geführt.** Der User entscheidet an jeder Weggabelung; du arbeitest mit, urteilst und schlägst vor. Es gibt **keine vorgegebene Schrittfolge** — jede Maßnahme (Pfad B) ist ein einzelnes Werkzeug, das du einzeln aufrufst. Eine feste Arbeitsmethodik wird noch gesucht.

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

> **WICHTIG — die Version ist eine reine Integer-Zahl, KEIN `v`-Präfix.** Der Iterations-Ordner und die Notiz heißen `iterations/<version>/<slug>-<version>.md` mit `version` als blanker Zahl. Richtig: `iterations/1/teststrategie-1.md`, `iterations/1/vwma-1.md`, `iterations/12/vwma-12.md`. **Falsch (gibt es nicht):** `iterations/v1/...`, `vwma-v1.md`, `# v1 — …`. Das gilt für Ordner, Dateiname UND Überschrift in der Notiz. Die App baut ihre Obsidian-Links exakt aus dieser Integer-Form (`strategy_concepts.html` + `obsidian_paths.py`) — ein `v` im Pfad bricht den Link (Notiz erscheint als „nicht vorhanden").

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
2. Letzte Iter-Notiz im Vault, falls vorhanden — **per Versions-String sortiert**, nicht mtime. Notes liegen in Versions-Unterordnern (`iterations/<version>/<slug>-<version>.md`), daher rekursiv listen (`find "$VAULT_ROOT/30_Trading/strategies/<kebab>/iterations/" -name '*.md'`), höchste Versions-Nummer numerisch sortiert (`42` > `32` > `3` > `2` > `1` — reine Integer, kein `v`-Präfix).
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
- **Toolbox** (`toolbox.py`, siehe Pfad B): liest/kopiert/legt an/startet/ändert/löscht jedes bt_pro_app-Objekt + Wissens-Recherche. Aktionen → `toolbox.py --help`
- **Verfügbare Indikatoren** (`toolbox.py playground-indicators`): listet alle nutzbaren Indikatoren inkl. Inputs/Params/Outputs — Grundlage zum Bauen des `spec_json.indicators`-Dicts
```

Diese Werkzeug-Liste ist fixer Bestandteil des Briefings — sie zeigt dem User direkt das Menü. Pflegst du eigene Workflow-Docs unter `documentation/knowledge/strategy-development/workflows/`, die Namen daraus ableiten; sonst die obige Liste verwenden.

Danach **eine** Anschluss-Frage außerhalb des Briefings, z.B.:

> Welche Hypothese willst du testen, oder direkt mit Backlog #1 (<kurzbeschreibung>) anfangen?

## Pfad B — Ad-hoc Objekt-Toolbox

Helper-Skript `toolbox.py`, um bt_pro_app-Objekte in einem Schritt zu **lesen** (kompaktes Markdown-Briefing statt 4-5 Einzel-Curls), zu **kopieren**, **anzulegen**, zu **ändern/löschen** oder Läufe zu **starten**. Jede Maßnahme ist ein **einzelnes Werkzeug**, einzeln aufgerufen — keine vorgegebene Reihenfolge. Vollständige Werkzeug-Liste mit je einem Satz: `documentation/project/handbuch.md` (Abschnitt „Toolbox-Werkzeuge"). Läuft als Folge-Aktion in einer Pfad-A-Session oder eigenständig.

**Wichtig:** Pfad B startet NIE die Pfad-A-Routine. Wenn der User mitten in anderer Arbeit nur schnell `iteration:2` lesen oder kopieren will, blockiert das sein laufendes Vorhaben nicht — kein Konzept-Listing, keine Strategie-Rückfrage.

**Zwei Naturen — danach sind die Abschnitte sortiert:**
1. **Lesen** (Abschnitt „Lesen") — harmlos, fasst nichts an, jederzeit nutzbar: URL/ID reinwerfen, kompaktes Briefing zurück.
2. **Schreiben** (Abschnitte „Schreib-Aktionen" + „Auswertung") — das eigentliche Arbeiten: anlegen, kopieren, Lauf starten, auswerten, ändern, löschen, markieren. Jede Maßnahme einzeln. Schreibt über die API.

Darunter folgen Referenz (`--help`) und Fehlerbilder.

**Doku-Index (vor strukturschaffender Arbeit lesen):** Der Einstieg in die Strategie-Methodik ist `documentation/knowledge/strategy-development/AGENT_ENTRY.md` — dort die „Workflow-Index"-Tabelle (Aufgabe → erst lesen → dann tun). Basis-Referenzen daneben: `begriffe-und-modi.md` (Terminologie) und `code-referenz.md` (Mechanik). Reines Lesen/Kopieren/Löschen (CRUD) braucht das nicht; sobald aber eine **Strategie entsteht oder strukturell verändert** wird (neues Konzept, erste/strukturell neue Iteration), erst die passende AGENT_ENTRY-Zeile lesen, dann die Aktion ausführen.

### Lesen (Default, keine Aktion)

```bash
python3 .claude/skills/ds-strategie-session/scripts/toolbox.py <arg1> <arg2> ...
```

Akzeptierte Lese-Argumente, beliebig mischbar:

- **Frontend-URLs:** `/config/backtest/<id>`, `/config/indicator/<id>`, `/config/playground/<id>`, `/backtest/results/<id>`, `/backtest/runs/<id>`, `/testsets/<id>`, `/config/strategy-concepts/<id>/iterations/<id>/edit`
- **`<bereich>:<id>`:** `iteration:26`, `indicator-config:1970`, `backtest-config:553`, `result:2635737`, `run:1753`, `concept:1`, `strategy-config:1`, `testset:421`, `leaderboard:199`, `playground-setup:17`
- **Wissens-Recherche:** `knowledge:"teststrategie exit logik"` (semantische Vektorsuche, Top-5), `vault:teststrategie` (Pfad-Substring → indizierte Dateien)
- Run hat keinen Einzel-GET — das Skript filtert die letzten 500 Runs; ältere ggf. über das Frontend prüfen.

Die Lese-Ausgabe **wortwörtlich** zurückgeben — keine eigene Reformulierung, keine Zusammenfassung dahinter. Der User will die Roh-Bausteine sehen, nicht meine Deutung. Hat der User zusätzlich eine Aufgabe formuliert, danach **eine** Frage stellen oder direkt vorschlagen, was als nächstes passieren soll.

### Schreib-Aktionen (je Aufruf nur ein Aktions-Typ — lesen/kopieren/anlegen/... nicht mischen)

```bash
toolbox.py copy iteration:2                              # kopieren: iteration, backtest-config, indicator-config
toolbox.py create-indicator-config result:2706026:Sharpe # Gewinner-Params → reproduzierbare Single-Point-Config (optional)
toolbox.py concept-create --slug teststrategie --name "Teststrategie"  # anlegen: concept, iteration, *-config, testset
toolbox.py iteration-create --concept 1 --file spec.json #   komplexe Payloads (spec_json/config_json/Backtest-Body) per --file
toolbox.py backtest-run-start --backtest-config 552 --indicator-config 1970 --iteration 41  # Lauf starten
toolbox.py testset-run-start --testset 293 --iteration 41 --indicator-config 1973  # 1 Run pro Config; Leaderboard nur bei leaderboard_enabled
toolbox.py run-list --strategy teststrategie --version 1  # Runs zu Strategie+Version (nach Testset-Lauf gruppiert, zeigt Auftrags-ID testset-run)
toolbox.py iteration-update --id 26 --file body.json     # ändern (voller PUT-Body — für gezielte Teiländerungen die -set/-add-Verben unten)
toolbox.py indicator-config-set --id 4 --concept 2 --iteration 2  # Teil-Update (PATCH): nur gesetzte Felder, config_json/_stops bleiben
toolbox.py iteration-indicator-set --id 8 --name sma --file frag.json  # Indikator in spec_json.indicators anlegen/mergen (--replace = Vollersatz)
toolbox.py indicator-config-indicator-set --id 34 --name sma --file frag.json  # dito in config_json (Param-Werte dürfen arange-Range sein)
toolbox.py iteration-condition-add --id 8 --block 1 --file cond.json   # Regel-Bedingung an Entry-Block anhängen (UND)
toolbox.py indicator-config-stops-set --id 34 --tp 0.25 --sl 0.15      # einzelne Stops in _stops setzen
toolbox.py backtest-config-set --id 552 --fees 0.0005 --timeframe 1h   # einzelne BacktestConfig-Felder ändern
toolbox.py iteration-delete 26 --force --delete_vault    # löschen (--force bei Abhängigen)
toolbox.py result-favorite 2706026                       # Aktionen: favorite, vault-create, run-restart, run-analyse-*, …
toolbox.py indicator-config-generate-labels 2018         # Name+Beschreibung nach Notation setzen (überschreibt beide, ohne Freitext)
toolbox.py indicator-config-labels --id 2018 --name-freetext "BNB Plateau" --desc-freetext "Gate-Sweep, VWMA-fix auf BNB im Plateau-Regime" --save  # Notation + Freitext, nur Name/Beschreibung
```

- Neue IDs / Ergebnis stehen in der Ausgabe (`-> **<id>**`) — **wortwörtlich** zurückgeben.
- `--file` reicht das JSON **unverändert** durch: kein stiller Konverter, kein Fallback — scheitert laut, wenn falsch geformt.
- **`concept-create` / erste `iteration-create` = neue Strategie:** vorher `workflows/neue-strategie.md` lesen (siehe Doku-Index oben). Das `spec_json` der Iteration enthält **nur** `indicators` (flach, **ohne** `_stops`) + `rules`; Stops gehören in die IndicatorConfig (`_stops`), Portfolio in die BacktestConfig. Nicht direkt aus einem Setup-Body ableiten, ohne diese Trennung zu prüfen.
- `create-indicator-config`: Segment-Label (z.B. Return/Sharpe/PF) optional via `:` oder `/`; nur `result` als Quelle. Optional — der Sweep-Run liegt ohnehin in der DB (siehe „Auswertung — die vier Bestwerte").
- Kopien/IndicatorConfigs bekommen Namenszusatz bzw. Konvention; **Originale bleiben unangetastet**.
- **Nachträgliche Verknüpfung:** Eine bestehende Indicator-Config einem Konzept/einer Iteration zuweisen (oder gezielt Name/Beschreibung setzen) über `indicator-config-set --id <n> [--concept … --iteration … --name … --description …]` — Teil-Update, `config_json`/`_stops` bleiben bit-genau. NICHT `indicator-config-update` (das ist ein voller Replace und braucht den kompletten Body).
- **Indicator-Config-Labels nicht selbst basteln:** Für die reine Standard-Notation `indicator-config-generate-labels <id>` (überschreibt Name+Beschreibung komplett, ohne Freitext). Für einen **individuellen Freitext** stattdessen `indicator-config-labels --id <n> [--name-freetext … --desc-freetext …] --save` — holt die Notation zustandslos, setzt den Freitext an die richtige Stelle und schreibt nur Name/Beschreibung zurück (ohne `--save` nur Vorschau). Beide nutzen dieselbe Server-Notation (Single Source, identisch zu den Frontend-Buttons):
  - **Name:** `<Konzept>-<Iteration>-(<Kombinationen>) <Stops>` (z. B. `VWMA-3-(35) TP 30% SL 15% TD 1-999 (35), rows`). Ohne verknüpftes Konzept nur `(<Kombinationen>)`; ohne Iteration nur die Nummer. Stops leerzeichengetrennt (`TP`, `SL`, `TSL`, `TD`; Format-Wort per Komma am Stop), Sweep-Achsen als `min-max (n)`. Ein **Freitext** (`--name-freetext`) hängt hinten per ` : ` an — kurze, lesbare Kennung (Symbol + Regime/Kontext), z. B. ` : BNB Spitze Bull 20/21`.
  - **Beschreibung:** Auflistung der Indikatoren mit Werten/Wertebereichen — `<name>: <param> <wert>, <param> <min-max (n)>; …` (z. B. `fast_sma: length 12, multiplier 9; vwma: length 3, below_pct 7`). Ein **Freitext** (`--desc-freetext`) steht **vor** der Auflistung, per ` | ` getrennt (`<Freitext> | <Auflistung>`).
  - **Freitext IMMER ausschreiben — keine kryptischen Kürzel.** Statt `v9 bp2 s5x8` sprechende Klartext-Erklärungen; deutsch formuliert (Eigenwörter wie `Total Return` bleiben englisch). Der Freitext ist das, was Titel/Beschreibung menschenlesbar unterscheidet — er muss ohne Vorwissen verständlich sein.
- `iteration-delete`/`concept-delete` ohne `--force` → Backend meldet **409 mit Blocker-Zählern**: nachfragen, nicht blind forcen.

### Gezielt bearbeiten (add / remove / change — der Alltagsfall)

Für „kopieren und dann einen Indikator/eine Regel/ein Feld ergänzen oder entfernen" gibt es **gezielte Bearbeitungsverben**. Sie holen das Objekt, ändern **genau einen Teil** und schreiben zurück — der Rest bleibt bit-genau. **Kein** kompletter Body per `--file` nötig (das ist nur `-update`, der Voll-Replace). Jede Maßnahme ein Einzelaufruf.

- **Felder (Meta/flach):** `concept-set` · `iteration-set` · `backtest-config-set` (partieller PUT; bei BacktestConfig GET→merge→PUT). Beispiel: `backtest-config-set --id 552 --fees 0.0005 --symbol ETHUSDT`.
- **Indikatoren:** `iteration-indicator-set/-remove` (spec_json.indicators) · `indicator-config-indicator-set/-remove` (config_json). `--file` ist **nur der eine Indikator-Block** (z. B. `{"indicator":"talib:SMA","tf":"4h","close":"close","timeperiod":50}`); in der Config dürfen Werte arange-Ranges sein. Existiert der Key, wird **gemergt**: nur die genannten Parameter ändern sich, der Rest des Blocks bleibt bit-genau — einen einzelnen Wert ändert man also mit `--file {"timeperiod":50}`. `--replace` ersetzt den Block komplett (alles Nicht-Genannte fällt weg, auch `tf`).
  - **`tf` ist Pflicht und laufzeit-wirksam** (`indicator_factory.py`: fehlender/leerer `tf` → ValueError). Es steht in jeder Lese-Ausgabe der Toolbox mit drin. Bei `--replace` gehört es in den Block; beim Merge bleibt es von allein erhalten.
- **Stops:** `indicator-config-stops-set --id N [--tp --sl --td --tsl --tsl-th --delta-format --time-delta-format]` — einzelne Werte in `_stops`, Rest bleibt. `null` löscht einen Stop-Wert.
- **Regeln:** `iteration-condition-add --id N [--exit] [--block K | --new-block [--short]] --file cond.json` · `iteration-condition-remove --id N [--exit] --block K [--index J | --remove-block]`. `--file` ist **eine** Bedingung (`{"op":">","lhs":"close","rhs":"indicator:sma:real"}`). Ohne `--block` an Block 1 (UND); `--new-block` erzeugt einen ODER-Block.

**Wichtig — Laufzeit-Zuordnung (am Code belegt, `worker_tasks.py`):** Bei einem Backtest kommen die **Indikatoren aus der IndicatorConfig** (`config_json`), die **Regeln aus der Iteration** (`spec_json.rules`). Wer also einen Indikator ergänzt, der logik-wirksam werden soll, muss ihn in die **Config** (mit Range, `indicator-config-indicator-set`) UND die referenzierende Regel in die **Iteration** (`iteration-condition-add`) legen. `spec_json.indicators` ist die kanonische Iterations-Definition, wird beim Run aber nicht als Indikator-Quelle genutzt.

**Immutability ist Konvention, kein Gate:** Der Server editiert Iterationen in-place (kein Run-/Result-Check). Struktur-Änderungen trotzdem per `copy` auf eine frische Iteration und dort bearbeiten — das schützt gelaufene Stände. Die Edit-Verben wirken technisch auf jede ID.

### Auswertung eines Multiparameter-Laufs — die vier Bestwerte

**Auslösen.** Der Lauf wird meist locker benannt — „bewerte die Ergebnisse aus dem neuen Testset-Lauf", „markiere die Bestwerte der Teststrategie", „zieh die Bestwerte aus Run X". Die Bezeichnungen **Run**, **Testset-Lauf** und **„alle neuen"** sind gleichwertig: sie meinen dieselben Results, die markiert werden — **gruppiert nach Run**. Der gemeinte Lauf wird per Recherche aufgelöst (`run-list`, siehe „Lesen"), nicht per Rückfrage. **Standard-Weg ist `run-bestwerte --testset-run <id>` — ein Aufruf je Testset-Lauf.** Umfasst der Auftrag mehrere Läufe („alle neuen", „beide Testsets"), folgt je ein `--testset-run`-Aufruf pro Lauf; entscheidend ist **Vollständigkeit** — kein zum Auftrag gehörender Lauf wird ausgelassen (`--iteration`/`--run` sind Sonderfälle und gleichwertig, solange sie wirklich alle gemeinten Läufe abdecken). Nur wenn unklar bleibt, welcher von mehreren gleichwertigen Läufen gemeint ist, folgt eine gezielte Rückfrage.

Aus jedem fertigen Sweep-Run werden genau **vier** Bestwerte gezogen und als **roter Doku-Favorit** markiert (schützt vor „Alle löschen"). Das übernimmt **eine** Aktion — die Definition ist serverseitig gekapselt und idempotent, kann also nicht von Hand falsch zusammengesetzt oder doppelt gesetzt werden:

```bash
toolbox.py run-bestwerte --testset-run 3     # STANDARD: alle Runs eines Testset-Laufs (Auftrags-ID)
toolbox.py run-bestwerte --iteration 2       # Sonderfall: alle Runs einer Iteration (Strategie+Version)
toolbox.py run-bestwerte --run 1812          # Sonderfall: nur ein einzelner Run
```

Welches Kriterium ein Result gewonnen hat, wird **am Result persistiert** (`best_criteria_json`) — ein Result kann mehrere gleichzeitig gewinnen. In der Results-Tabelle steht es als Kürzel-Spalte „Bestwert" (`T` Max Total Return · `W` Win-Rate-Band · `S` Sharpe-Band · `P` Profitfaktor ≥30 Trades, Langform im Hover); `run-favorites-list` und `kreuztest` weisen es aus der Spalte aus. Beim Zurücksetzen (`run-favorites-reset`) wird es mit dem roten Stern gekoppelt geleert. Nötig, weil die Bänder run-relativ sind und nach dem Löschen der übrigen Run-Results nicht mehr herleitbar wären.

Die vier Kriterien (Detail + Raster-Format: `documentation/knowledge/strategy-development/workflows/multiparameter-lauf.md`) — jede Metrik hat eine eigene Regel, nicht vereinheitlichen:

1. **Max Total Return** — reines Maximum, kein Trade-Floor
2. **Win-Rate-Band → bestes Return** — Band = Top 20 % vom Höchstwert (höchste WinR − 20 % vom Höchstwert); daraus das höchste Total Return
3. **Sharpe-Band → bestes Return** — dieselbe Band-Mechanik mit Sharpe, aber engeres Band: Top 10 % (höchster Sharpe − 10 % vom Höchstwert); daraus das höchste Total Return. Bewusst enger als das Win-Rate-Band, damit der Sieger seltener mit Krit 1 (Max Total Return) zusammenfällt
4. **Max Profitfaktor mit ≥30 Trades** — Trade-Floor gegen Low-Trade-Flukes; gilt NUR für PF

**Bei Wertgleichstand** (z. B. Raster-Dubletten mit identischem Ergebnis) wählt die Auswahl deterministisch: zuerst das risikoärmere Result (**geringster Drawdown**), dann die **ID** als finaler Anker — so ist die Markierung reproduzierbar. Der Run liegt mit allen Kombinationen ohnehin in der DB, extra speichern ist nicht nötig. **Kein** Promotions-/Akzeptanz-/Folgeschritt; der wird bei Bedarf neu definiert.

Manueller Unterbau (nur für Ad-hoc-Kontrolle einzelner Kriterien): `run-top-results <run_id> <metrik> 1 desc` (Krit 1 + Bandgrenzen von 2/3), `run-best <run_id> profit_factor 30` (Krit 4), Markierung einzeln via `result-doc-favorite <result_id>`. Die Band-Sieger (Krit 2/3) zieht nur `run-bestwerte`.

### Direkt nach den Bestwerten — Analyse-Screenshots (zeitkritisch)

Die Analyse-Seite eines Runs (`/backtest/runs/<id>/analyse`) ist nur aussagekräftig, solange der volle Result-Satz lebt — nach dem Ergebnis-Purge bleiben nur die Favoriten übrig, Heatmaps und Verteilung sind dann unwiederbringlich weg. Deshalb gehört zu jedem `run-bestwerte`-Durchgang **direkt danach** ein Screenshot-Durchgang: pro Run ein Vollseiten-PNG im Standard-Zustand, abgelegt im Vault beim Iterations-Ordner (`iterations/<version>/img/`). Die Arbeit ist mechanisch — an einen Subagenten mit einfachem Modell (z. B. Haiku) delegieren. Standard, Ablage-Konvention und fertiger Subagent-Prompt: `references/screenshot-standard.md`. In der Iter-Note werden die Bilder relativ eingebettet (`![](img/run-<id>-….png)`).

### Iterations-Vergleichstabelle (ein Verb, purge-fest)

`vergleichstabelle --strategy <slug>` stellt je Testset die markierten Bestwerte aller Iterationen nebeneinander — Zeilen Symbol × Iteration, Spalten Spitze (Max Total Return) und robuster Kern (Profitfaktor ≥ 30 Trades), dasselbe Format wie die Benchmark-Tabellen in `status.md`. Quelle sind ausschließlich die roten Doku-Favoriten samt persistierter Bestwert-Kriterien — die Tabelle funktioniert daher auch für Läufe, deren volle Result-Sätze längst gelöscht sind. Einzel-Läufe ohne Testset bleiben bewusst außen vor. Nach jedem neuen Testset-Lauf (nach `run-bestwerte`) neu generieren und die Vault-Notiz überschreiben:

```bash
toolbox.py vergleichstabelle --strategy <slug> --save "$VAULT_ROOT/30_Trading/strategies/<slug>/iterationen-vergleich.md"
```

Läufe ohne markierte Bestwerte weist die Ausgabe explizit aus (erst `run-bestwerte` nachholen). Große Runs (sechsstellige Result-Zahlen) brauchen einige Sekunden pro Run — das Verb wartet selbst (60s-Timeout je Abfrage).

### Vollständige Referenz (Detail-Flags, alle Routen)

- **Syntax/Flags je Aktion** (inkl. aller Anlege-, Listen-, Lösch- und sonstigen Aktionen und Defaults): `python3 .claude/skills/ds-strategie-session/scripts/toolbox.py --help`

**Kein fabrizierter Curl / kein `sys.path`-Import des Skripts.** Wenn du den **rohen** Ist-Body eines Objekts brauchst (z. B. um einen `-update --file` zu bauen), nimm den vorhandenen generischen Verb `api GET <route>` — der gibt das rohe JSON aus (z. B. `toolbox.py api GET /api/strategy/iterations/8`). Für gezielte Teiländerungen die `-set`/`-indicator-set`/`-condition-add`/`-stops-set`-Verben oben — die machen GET→ändern→zurück selbst.

**Lange `api GET`-Antworten:** Die Anzeige kappt bei 4000 Zeichen — der Schnitt liegt mitten im JSON, das Ergebnis ist dann **nicht mehr parsebar**. Wer die vollständige Antwort braucht (z. B. `parameter-ranking` mit allen Achsen), nimmt eines der beiden Flags — nicht den Umweg über einen eigenen `urllib`-Fetch:

```bash
toolbox.py api GET "/api/backtest/runs/222/analyse/parameter-ranking?metric=total_return_pct" --out ranking.json
toolbox.py api GET "/api/…" --out          # ohne Wert: Auto-Name mit Zeitstempel
toolbox.py api GET "/api/…" --full         # ungekürzt in den Kontext
```

`--out` schreibt ungekürzt in eine Datei und gibt auf der Konsole nur Pfad + Zeichenzahl aus — **die bevorzugte Variante**, weil das Kontextfenster klein bleibt und Folge-Analysen die Datei per `json.load` lesen können. `--full` gibt alles auf stdout aus (nur wenn die Antwort wirklich in den Kontext soll). Beide zusammen sind ein Fehler.

**Ablageort und Aufräumen (kein Müll im Repo):** `--out` schreibt **immer** unter `<TEMP>/bt-toolbox-out/`. Ein reiner Dateiname oder relativer Pfad landet dort — **nicht** im Arbeitsverzeichnis, es kann also nichts versehentlich im Projektbaum landen. Nur ein absoluter Pfad wird wörtlich genommen (bewusste Ausnahme, die dann aber vom Cleanup ausgenommen ist). Aufgeräumt wird automatisch: bei **jedem** `--out`-Schreiben fliegen Dateien raus, die älter als 24 h sind. Sofortiges Aufräumen von Hand:

```bash
toolbox.py out-clean          # nur abgelaufene (>24h)
toolbox.py out-clean --all    # Ordner komplett leeren
```

Du musst also nach einer Analyse **nichts** von Hand löschen — der Ordner hält sich selbst sauber. **Erst wenn wirklich ein Verb/Feld fehlt**, das weder ein Bearbeitungsverb noch `api GET/PUT/PATCH/POST/DELETE` abdeckt, die Lücke in `documentation/todo/todo-toolbox.md` eintragen (unter `## Offen`, nächste freie Nummer).

**Eintrags-Qualität (Pflicht):** Der Eintrag muss **für sich allein verständlich** sein — ein frischer Chat ohne den heutigen Gesprächskontext muss ihn nachvollziehen und umsetzen können. Also nicht der knappe Einzeiler, der nur im Moment Sinn ergibt („Feld X fehlt"), sondern:
- **Ziel** — was soll gehen, das heute nicht geht.
- **Hintergrund / Warum blockiert** — **am Code belegt** (Datei:Zeile, Route, Schema), nicht behauptet. Bei falscher Ortsangabe verläuft sich der frische Chat (z.B. Server- vs. Toolbox-Logik verwechseln) — deshalb die Stelle vorher per grep/Read prüfen.
- **Umsetzungsidee** — ein bis zwei konkrete Wege (Verb/Flag/Route), keine fertige Lösung nötig.
- **Akzeptanzkriterium** — woran „fertig" erkennbar ist, verifizierbar.

Momentaufnahmen (konkrete IDs, Datenstände) als solche markieren („Stand <Datum>, vor Umsetzung prüfen"), nicht als Dauerzustand — sie veralten.

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

- Keine Änderungen an Projekt-Code. Schreib-Aktionen gehen ausschließlich über die Toolbox-Aktionen (Pfad B, legen/ändern bt_pro_app-Objekte über die API an) und Pfad C (aktualisiert Vault-Doku `status.md`, Iter-Notes). Pfad A und das Lese-Briefing aus Pfad B fassen nichts an.
- **In Pfad A (Konzept-Auswahl) neutral listen** — keine eigene Wertung, welche Strategie inhaltlich sinnvoller ist; der User wählt, welches Konzept drankommt.
- **In der Entwicklungs-Arbeit (Pfad B) dagegen sehr wohl bewerten und eine Richtung empfehlen** — das ist die Ingenieur-Rolle. Die finale Entscheidung (welche Iteration, welcher nächste Schritt) trifft aber der User.
- Keine Phase 3 ohne explizite User-Entscheidung in Phase 2.
- Keine Caveman-Aktivierung — der Skill läuft im normalen Stil.

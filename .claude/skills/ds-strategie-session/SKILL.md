---
name: ds-strategie-session
description: Agentische Trading-Strategie-Entwicklung in bt_pro_app_v1 — zwei Trigger-Klassen. (1) ENTWICKLUNGSAUFTRAG - der User nennt ein Ziel und will, dass dafür eine Strategie entwickelt, gesucht, verbessert oder optimiert wird; der Skill führt den Loop vom Auftrag über Recherche, Bauen, Pflicht-Preflight, kleines Raster, Befund-Bewertung, Iteration, Härtung bis Abschluss, Aufräumen und Werkzeug-Lücken-Meldung. Trigger - "entwickle eine Strategie mit Sharpe über 1,5", "finde mir eine Strategie für ETH 4h", "optimiere die Strategie X auf Ziel Y", "bau mir eine Strategie, die ... erfüllt", "mach so lange weiter, bis die Kriterien erfüllt sind", "verbessere die Iteration bis das Ziel steht", /ds-strategie-session. (2) OBJEKT-TOOLBOX - liest, kopiert, legt an, startet, ändert oder löscht beliebige bt_pro_app-Objekte (Iteration, Indicator-/Backtest-/Strategy-Config, Result, Run, Testset, Leaderboard, Playground-Setup, Concept) plus Wissens-Recherche (Vektorsuche, Vault) über ein Helper-Skript. Trigger - gepastete Frontend-URLs (http://localhost:5570/config/... /backtest/... /testsets/...), Typ:ID-Formen (iteration:26, backtest-config:553, result:2635737, ...), knowledge:"teststrategie exit"/vault:teststrategie, "brief mir diese IDs", "lies iteration:X ein", "kopier iteration:2", "such mir im Vault nach X", "markiere die Bestwerte", "mach die Analyse-Screenshots", "aktualisier die Vergleichstabelle". Die Toolbox läuft eigenständig und startet nie von allein einen Entwicklungs-Loop. NICHT auto-triggern bei einzelner URL-Erwähnung ohne Lese-/Kopier-Wunsch, beliebigen Strategie-Erwähnungen oder generischen Backtest-Fragen ohne konkrete IDs.
---

# ds-strategie-session

Zwei Trigger-Klassen für Trading-Strategie-Arbeit in bt_pro_app_v1:

- **Entwicklungsauftrag** — Teil 1 unten: der Loop von Phase 0 bis Phase 10.
- **Objekt-Toolbox** — Teil 2 unten: einzelne Werkzeuge, jederzeit, ohne Loop.

Die Klassen sind unabhängig. Ein Toolbox-Aufruf startet **nie** einen Entwicklungs-Loop; im
laufenden Loop sind die Toolbox-Werkzeuge die einzige Art zu arbeiten.

## Rolle

**Strategie-Ingenieur.** Im Entwicklungsauftrag arbeitest du eigenständig auf ein Ziel hin:
bewerten, entscheiden, iterieren, berichten. Rückfragen nur bei echten Mehrdeutigkeiten des
Auftrags — und die vor dem ersten Lauf, nicht mittendrin. Sagt der Auftrag „nicht
unterbrechen", triffst du Routine-Entscheidungen selbst und **sagst sie an**, statt zu fragen.
In der reinen Toolbox-Nutzung führt der User; da bedienst du.

Code entsteht dabei (Configs, Setups, Specs), ist aber Mittel zum Zweck. **Kein neuer
Indikator-Code für die Optimierung** — es wird mit dem vorhandenen Arsenal gearbeitet
(Messwerkzeuge sind davon ausgenommen).

## Voraussetzungen

- Backend läuft auf der Basis-URL aus `$VBT_APP_BASE_URL` (Default `http://localhost:5570`,
  FastAPI). Das Helfer-Skript liest dieselbe Variable.
- Aufruf durchgängig:
  `python3 .claude/skills/ds-strategie-session/scripts/toolbox.py <werkzeug> ...`
- Der Vault ist optional und wird nur **gelesen** bzw. über Toolbox-Verben beschrieben (siehe
  „Vault-Root auflösen").

## Vault-Root auflösen (nur bei Vault-Ablage nötig)

Der Obsidian-Vault liegt außerhalb des Projekts; sein Host-Pfad steht in der (gitignoreten)
`.env` im Projekt-Root als `OBSIDIAN_VAULT_HOST_PATH` — in Windows-Form, weil Docker Desktop
das so braucht. In WSL einmal pro Session in WSL-Form auflösen und als `$VAULT_ROOT`
weiterverwenden:

```bash
VAULT_ROOT=$(wslpath -u "$(grep -E '^OBSIDIAN_VAULT_HOST_PATH=' .env | cut -d= -f2-)")
```

Alle Vault-Pfade sind relativ dazu, Konvention
`$VAULT_ROOT/30_Trading/strategies/<slug>/vbt/` (identisch zur App-Pfadlogik in
`services/api/utils/obsidian_paths.py`). Fehlt `.env` oder die Variable, ist der Vault nicht
konfiguriert — dann ohne Vault weiterarbeiten und das im Bericht ausweisen.

> **WICHTIG — die Version ist eine reine Integer-Zahl, KEIN `v`-Präfix.** Iterations-Ordner
> und Notiz heißen `iterations/<version>/<slug>-<version>.md`. Richtig:
> `iterations/1/teststrategie-1.md`, `iterations/12/teststrategie-12.md`. **Falsch (gibt es nicht):**
> `iterations/v1/...`, `teststrategie-v1.md`. Die App baut ihre Obsidian-Links exakt aus dieser
> Integer-Form — ein `v` im Pfad bricht den Link.

---

# Teil 1 — Der Entwicklungs-Loop (Phasen 0–10)

## Die vier Kernregeln (gelten in jeder Phase)

1. **Log-Pflicht vor Lauf und nach Befund.** Vor jedem Lauf ein Eintrag „warum dieser
   Versuch", nach jedem Befund ein Fazit-Eintrag — `iteration-log-add --id N --text "…"`
   (append-only, ein Satz reicht, keine Vorlage). Das Log ist das *Warum*; Runs und Befunde
   sind das *Was gemessen*; `goal_json` ist das *Wohin*. Ohne Log ist eine Iterationskette in
   einem frischen Kontext nicht mehr rekonstruierbar.
2. **Preflight ist Pflicht, nicht Kür.** Vor **jedem** Lauf `preflight`. Bei 0 Entry-Signalen
   oder absurder Laufzeit-Hochrechnung wird nicht gestartet, sondern korrigiert.
3. **Klein sweepen.** Die Beweislatte wächst mit der Rastergröße: gemessen hat eine
   **Verachtfachung** des Rasters nur **+0,16 % Sharpe** gebracht, die nötige Beweislatte aber
   um **+13 %** gehoben — mehr Suchen hat das Ergebnis also *verschlechtert*. Raster so klein
   wie möglich schneiden; erst verfeinern, wenn eine konkrete Frage es verlangt.
4. **DSR ist Warnlampe, nie Filter.** Die Deflated Sharpe Ratio erkennt reale kleine Edges
   nicht (belegt) — sie darf keinen Kandidaten aussortieren, nur einen Vorbehalt setzen. Und
   **nie ohne `N` und `SR0` zitieren** (beide stehen im Befund). Ebenso: **Null-Trade-Results
   nie ausblenden** — sie haben Informationswert (Regel greift nicht, Raster falsch platziert).

## Phase 0 — Auftrag entgegennehmen

- Zielgrößen aus dem Prompt extrahieren (z.B. Sharpe-Minimum, Risiko je Trade, Timeframe,
  Zeitraum, Symbole) und als Konzept anlegen:
  `concept-create --slug <slug> --name "<Name>" --goal <json-datei-oder-inline> --goal-prompt <datei-oder-text>`.
- `--goal` ist die **maschinenlesbare** Zielvorgabe (JSON-Objekt), `--goal-prompt` der
  **Original-Auftrag im Wortlaut** (verbatim, nicht paraphrasieren). Beide erkennen einen
  Dateipfad automatisch, sonst wird der Wert inline übernommen. Später nachziehen:
  `concept-set --id N --goal … --goal-prompt …`.
- Warum am Konzept: Der Befund kopiert das Soll aus `goal_json`, nicht aus dem Chat-Kontext —
  damit driftet das Ziel auch in einem frischen Kontext nicht weg. Die Felder halten das Ziel,
  sie urteilen nicht (kein Gate).
- Mehrdeutige Ziele **vor** dem ersten Lauf klären. Eine Ansage ist keine Rückfrage.
- Iterationen tragen **kein** eigenes Ziel: Was sich je Iteration ändert, ist die Hypothese —
  die gehört ins Log.

## Phase 1 — Recherche und Abgleich mit dem Bestand

- **Strategie-Idee:** aus Web-Recherche oder intrinsischem Wissen — beides zulässig. **Welcher
  Weg es war, gehört ins Log.**
- **Die interne Wissensbasis ist nicht die Ideenquelle.** `knowledge:"<frage>" --k <n>`
  (semantische Vektorsuche) und `vault:<pfad-substring>` liefern kondensierte
  **Projekt-Erfahrung**: was hier schon versucht wurde und woran es scheiterte. Zweck ist,
  Sackgassen nicht zu wiederholen.
- **Werkzeug-Verfügbarkeit vor dem Bauen prüfen:** Indikator-Katalog über
  `playground-indicators` (`--group`, `--search` zum Filtern); bei VBT-Fragen der VBT-MCP
  (`find`/`get_attrs`/`get_source` laufen ohne Token).
- **Abgleich mit dem Bestand:** `concept-list` (je Zeile ein Ziel-Marker) und `concept:<id>`.
  Gibt es die Idee schon, wird das bestehende Konzept **aufgegriffen oder ergänzt** — kein
  Duplikat. Das Abgleich-Ergebnis steht im Log.
- Weitere Fundsachen als Ideenspeicher ablegen: je Fundsache ein Konzept mit
  `--status idee`, eigenem `--goal` und der Recherche-Begründung in `--description`. Beim
  Aufgreifen später `concept-set --id N --status active`.

## Phase 2 — Bauen

- Iteration mit `spec_json` (Indikatoren + DNF-Regeln):
  `iteration-create --concept <id> --file spec.json [--parent <id>]`.
- Parameter-Raster als Datei `config.json` (Sweep-Achsen **immer im arange-Standardschema**,
  nie als Liste — der visuelle Editor rendert Listen leer). Stops gehören ins Raster
  (`_stops`), Portfolio-Parameter in die BacktestConfig, `spec_json` trägt **nur**
  `indicators` + `rules`.
- **Die Wahl: inline messen oder als IndicatorConfig anlegen.** Beides misst identisch, der
  Unterschied ist allein, ob ein benanntes Objekt zurückbleibt.
  - **Inline (Regelfall im Loop):** Die Raster-Datei geht direkt in Preflight und Lauf
    (`--indicators config.json`). Es entsteht keine Zeile, nichts ist danach aufzuräumen,
    der Befund trägt `indicator_config_id = NULL`. So laufen Zwischenmessungen und
    Rastervarianten, die nur den nächsten Schritt entscheiden.
  - **Als IndicatorConfig (benannter Messpunkt):** `indicator-config-create --file config.json`,
    danach mit `--indicator-config <id>` messen. Das ist der Standard, wenn der Messpunkt
    einen Namen tragen soll — Spitzenreiter, Vergleichsmessung, Härtung — also überall dort,
    wo später jemand auf genau dieses Raster zeigen können muss.
  - Was als Config angelegt wurde und diesen Rang am Ende nicht behält, wird in Phase 9
    zurückgebaut.
- **Sondieren vor dem Raster:** Varianten schnell durchrechnen mit
  `playground-run-backtest-lite --file spec.json --concept <id>` (eine Kombination, kein
  DB-Schreiben, ~200 ms). **Das `--concept` ist im Auftragskontext Pflicht** — es zählt die
  Sondierung am Konzept mit, sonst versickert der halbe Suchumfang unsichtbar und das im
  Befund ausgewiesene `N` unterschätzt die Selektionsstrafe. Der Zähler wird nur
  ausgewiesen, nie bewertet.
- Messrahmen: `backtest-config-create --file backtest.json`, dann
  `testset-create --name "…" --configs 552,553`. Auch eine Einzelmessung läuft als Testset mit
  genau einer BacktestConfig — kein Sonderweg, denn nur der Testset-Lauf erzeugt einen Befund.
- **Vor dem Lauf: Log-Eintrag „warum dieser Versuch"** (Kernregel 1).

## Phase 3 — Preflight (Pflicht)

```bash
toolbox.py preflight --iteration 41 --backtest-config 552 --indicators config.json
toolbox.py preflight --iteration 41 --backtest-config 552 --indicator-config 1970
```

Die Raster-Quelle folgt der Wahl aus Phase 2 — genau eine der beiden Angaben, beides oder
keines endet mit Fehler. Der Bericht ist auf beiden Wegen derselbe.

Rechnet **eine** Kombination (kein DB-Schreiben) und meldet: Entry-/Exit-Signalzahl mit
erstem/letztem Signalzeitpunkt, NaN-Anteil je Indikator-Output, tatsächlichen Vorlauf,
Kombinationszahl des vollen Rasters, grobe Laufzeit-Hochrechnung. Dazu — sofern
einschlägig — die **Herkunft der Stop-Werte** (welcher Indikator, welcher Faktor, fest oder
laufend nachgeführt) und bei risikobasierter Größe oder Hebel die **Positionsgröße**
(Risikoanteil, Hebel, Hebelmodus, Quelle des Stopabstands) samt Probe-Bericht: wie viele
Orders eine gerechnete Größe bekamen und wie viele VBT still auf das verfügbare Geld gekürzt
hat. Eine gemeldete Kürzung heißt: die Risikoregel greift insoweit nicht — Hebel erhöhen oder
Risikoanteil senken, sonst misst der Lauf eine andere Strategie als gedacht. Es berichtet nur — es
verhindert nichts. **Die Entscheidung ist deine:** 0 Entry-Signale oder eine absurde
Hochrechnung heißt Spec/Raster korrigieren, nicht starten.

## Phase 4 — Klein sweepen

```bash
toolbox.py testset-run-start --testset 293 --iteration 41 --indicators config.json [--metrics kern|voll|auto|<liste>]
toolbox.py testset-run-start --testset 293 --iteration 41 --indicator-config 1973 [--metrics …]
toolbox.py run-wait --testset-run 6 [--timeout 1800]
```

- **Raster-Quelle wie in Phase 2 gewählt** (genau eine der beiden Angaben): `--indicators`
  für die Zwischenmessung, `--indicator-config` für den benannten Messpunkt. Beide Wege
  erzeugen denselben Befund; bei inline steht dort `indicator_config_id = NULL`.
- Einzellauf analog: `backtest-run-start --backtest-config … --indicator-config … --iteration …`
  (dieser Weg bleibt ID-basiert).
- **Metrik-Stufe zur Frage wählen:** Grobsuche `kern` (billige Kennzahlen) oder eine gezielte
  Gruppenliste; Feinmessung `voll`. Ohne Angabe gilt `auto` (Server-Default: volle Rechnung
  unterhalb der Rastergrößen-Schwelle, darüber `kern`).
- Raster klein halten (Kernregel 3).
- `run-wait` pollt bis `completed`/`failed` und meldet Dauer, Result-Zahl, ggf. Fehler; ein
  Timeout meldet sich als Timeout, nicht als Fehlschlag.

## Phase 5 — Bewerten

- **Der Befund ist die Bewertung** — nicht selbst erzählen, sondern lesen:
  `befund --testset-run <testset-run-id>` (direkter Anschluss an `testset-run-start`/
  `run-wait` — liefert den jüngsten Befund dieses Testset-Laufs plus Gesamtzahl, Ticket
  77/A). `--id <befund-id>` adressiert einen konkreten Befund direkt (das ist die
  Befund-ID, NICHT die Testset-Lauf-Nummer); Historie einer Iteration:
  `befund --iteration <id>`. Er entsteht automatisch je Testset-Lauf, ist zweiphasig (Soll beim Start aus `goal_json`
  kopiert, Ist nach dem Lauf), immutable und **ohne Verdict**. Er verdichtet Suchumfang (inkl.
  N_eff der Symbole), Kandidaten je Bestwert-Kriterium, Robustheit (DSR mit N und SR0,
  Plateau-Score, Streuung über Symbole), die drei Vergleichsanker (Buy-and-Hold,
  Benchmark-Linie, Soll/Ist) und Warnhinweise. Leere Felder tragen ihren Grund.
- Einzelzahlen bei Bedarf: `run-summary <id>`, `run-best <run_id> <metrik> [min_trades]`,
  `result-lookup --run <id> --params "…" --summary`.
- **Regeln beim Deuten:** DSR ist Warnlampe, nie Filter; DSR nie ohne N und SR0;
  Null-Trade-Results nie ausblenden; Zonen-/Kandidaten-Aussagen nur mit Trade-Floor rechnen
  (sonst entstehen Mini-Trade-Artefakte).
- Die Deutung ist dein Freitext — **und dein Fazit gehört als Log-Eintrag an die Iteration**
  (Kernregel 1).

## Phase 6 — Iterieren oder verwerfen

- Weiter: neue Iteration in der `parent`-Kette
  (`iteration-create --concept <id> --parent <id> --file spec.json`) — **eine Änderung je
  Iteration**, sonst ist der Effekt nicht zuzuordnen.
- Die Schleifen-Semantik des Auftrags bindet an das **Ziel**, nicht an das Konzept: Ein
  Konzept wird iteriert, solange die Befund-Kette Fortschritt zeigt. Bei Stagnation oder
  Kill-Signal wird es abgelegt (`concept-set --id N --status archived` plus Log-Begründung)
  und ein **neues Konzept mit kopiertem Ziel** begonnen (`goal_json`/`goal_prompt`
  übernehmen).
- Vorregistrierte Kriterien nach der Messung **nie** nachschärfen. Ein Kill ist ein
  vollwertiges Ergebnis.
- Fehlt ein Werkzeug: melden (Phase 10) und mit dem vorhandenen Arsenal weiterarbeiten.
- Fertig ist der Auftrag, wenn ein Befund das Soll erfüllt zeigt **und** die Härtung hält.

## Phase 7 — Härten

Erst wenn ein Kandidat das Soll im kleinen Raster erreicht:

- **Plateau-Nachbarschaft:**
  `result-lookup --run <id> --params "…" --tolerance-steps 1 --summary` — liegt der Kandidat
  auf einem Plateau oder auf einer Nadel?
- **Kreuztest** auf andere Zeiträume/Symbole: `kreuztest --from-run A --to-run B` bzw.
  `kreuztest --from-testset-run A --to-testset-run B` (paart die Runs per Symbol+Timeframe);
  eine einzelne Kombination über eine Run-Menge verfolgen:
  `combo-trace --params "…" --testset-run <id>`.
- **Regel: Zeit schlägt Symbol.** Vier Symbole sind rund zwei unabhängige Tests —
  `symbol-correlation <exchange> <timeframe> --symbols A,B,C` weist `N_eff` aus. Ein weiteres
  Symbol ersetzt keinen weiteren Zeitraum.
- **Signifikanztest je Kandidat** — der Test **berichtet, er filtert nicht**:
  - `signifikanz-start --result <id> --n 99 --wait` rechnet den Monte-Carlo-Permutationstest:
    die Strategie läuft auf N synthetischen Preisreihen (Bar-Permutation — Randverteilung der
    Bar-Renditen erhalten, zeitliche Struktur zerstört). Der p-Wert sagt, wie oft ein so gutes
    Ergebnis aus strukturlosen Daten entsteht. Vor dem ersten synthetischen Lauf prüft der
    Test sich selbst gegen die am Result gespeicherten Kennzahlen.
  - `signifikanz-start --result <id> --method bootstrap` resampelt die gespeicherten
    Trade-Renditen → Konfidenzbänder. **Kein Nullmodell, deshalb kein p-Wert.** Braucht
    vorhandene Trades (Recompute), rechnet sonst nichts nach.
  - `signifikanz --id <n>` liest einen Test, `signifikanz-list --result <id>` die Historie
    (chronologisch, keine Sortierung nach p-Wert, kein Bestanden-Feld).
  - **Regel: ein p-Wert wird nie ohne seine Null-Verteilung zitiert** (sinngemäß wie „DSR nie
    ohne N und SR0"). Immer zusammen nennen: echter Wert, Kennwerte der Null-Verteilung, N und
    p-Wert. Kein Kandidat wird wegen eines p-Werts verworfen oder befördert — der Wert geht als
    Zahl in Befund-Deutung und Abschlussbericht.
  - **N bewusst wählen:** der kleinste erreichbare p-Wert ist 1/(N+1). Unter N = 19 ist p ≤ 0,05
    rechnerisch unmöglich; N = 99 gibt eine Auflösung von 0,01. Hintergrund und
    Kalibrierungs-Belege: [`documentation/knowledge/signifikanztest.md`](../../../documentation/knowledge/signifikanztest.md).
  - **Zwei Grenzen, die in jede Deutung gehören** (beide gemessen, Tickets 79/80): Der Test
    prüft **nicht** auf Look-ahead-Bias — ein Vorteil, der unter der Permutation invariant ist,
    bleibt unsichtbar. Und ein einzelner kleiner p-Wert ist ein **Hinweis, kein Beweis**: Ein
    Kandidat ohne Reihenfolge-Vorteil landet per Konstruktion in 5 Prozent der Fälle bei
    p ≤ 0,05. Wer über mehrere Kandidaten testet, sagt das dazu.
- **Walk-Forward-Fold-Kette** — N-mal „auf einem Zeitfenster optimieren → Sieger
  einfrieren → auf dem nächsten, ungesehenen Zeitfenster testen":
  - `walk-forward-chain-start --run <anker-run-id> --folds 3 --oos-monate 3
    --selection-metric sharpe_ratio --trade-floor <t> [--is-monate <k>] [--timeout <s>]`
    fährt die Kette im Vordergrund. Fold-Zahl, Fensterlängen und Kriterium werden beim Start
    festgeschrieben (**Vorregistrierung**) und stur vollzogen — Nachjustieren nach
    Zwischenblick ist strukturell ausgeschlossen. Ohne `--is-monate` ist das IS-Fenster von
    Fold 1 exakt das Anker-Fenster, der Anker-Lauf dient dann selbst als IS-Lauf.
  - `walk-forward-chain --id <id>` liest das Artefakt, `walk-forward-chain-list
    [--iteration <id>]` die Historie (chronologisch, keine Güte-Sortierung).
  - **Regel: das Aggregat wird nie ohne die Fold-Tabelle zitiert** (sinngemäß wie „p-Wert nie
    ohne Null-Verteilung"). Zur Gesamtzahl gehören immer die Folds mit IS-Wert **neben**
    OOS-Wert — die Degradation ist die eigentliche Aussage — sowie der Methodenhinweis
    (verkettete Kapitalkurven der Testfenster, **kein** durchgehendes Portfolio über alle
    Folds). Es gibt kein Verdict: **Report, kein Filter.**
  - Ein Fold ohne Sieger (kein Kandidat über dem Trade-Floor) wird ausgewiesen, nicht
    verschluckt; er gehört genauso in die Deutung wie ein Fold mit Sieger.
  - **Einordnung: Messwerkzeug, kein Ertragsbringer.** Die Kette misst, ob ein Ergebnis über
    ungesehene Fenster trägt — sie erzeugt keinen Ertrag. Re-Fitting je Fenster hat in
    früheren Messungen reine Rausch-Anpassung produziert.
    Wer die Kette startet, erwartet also **keine** bessere Strategie, sondern eine ehrliche
    Zahl über die vorhandene.
- **Holdout — versiegelte Finalmessung** (Testsets „R11 HOLDOUT (versiegelt)"): Diese
  Testsets werden während Entwicklung, Optimierung und Auswahl **nie** verwendet — kein Lauf,
  kein Hinsehen. Erst wenn der Kandidat feststeht und die übrige Härtung gelaufen ist:
  `data-update --timeframe <tf> --wait` ausführen und die Bilanz prüfen — das Zielsymbol
  muss darin als erfolgreich ausgewiesen sein (sonst rechnet der Testset-Lauf
  gegen veraltete oder fehlende Candles, ohne dass es auffällt). Erst danach `end`/`ohlc_end`
  der Holdout-Configs auf den neuen Datenstand ziehen, dann **genau ein** Testset-Lauf. Danach
  ist der Zeitraum für diesen Auftrag verbraucht — wer nach der Messung weiter optimiert, hat
  keinen Holdout mehr; jede weitere Berührung gehört als Vorbehalt in Befund-Deutung und
  Abschlussbericht.

## Phase 8 — Abschluss

1. **Sieger sichern:** Playground-Setup des Gewinners speichern
   (`playground-setup-create --file setup.json`) — per `?setupid=` verlinkbar.
2. **Doku-Sterne setzen:** `result-doc-favorite <id>` (setzend) auf **genau die Results, die
   Befund-Deutung und Vault-Doku referenzieren** — den gewählten Kandidaten und seine
   Härtungs-/Regime-Messungen. Der rote Stern bedeutet „dieses Ergebnis ist es wert,
   dokumentiert zu werden"; dass er löschfest ist, ist Nebeneffekt, nicht Zweck. Was du
   dokumentierst, sternst du — was du nicht sternst, verschwindet in Phase 9.
   `run-bestwerte` (vier Extremwert-Kriterien, Teil 2) ist ein Werkzeug für User-Aufträge
   und **keine Loop-Pflicht**: Es sternt Rasterspitzen, die niemand gewählt hat, und
   schützt die Wahl nicht — in beiden ersten Aufträgen stand der Kandidat dadurch
   ungeschützt da.
3. **Analyse-Screenshots sind keine Loop-Pflicht.** Der Loop entscheidet nichts anhand eines
   Bildes, und die Struktur-Aussage der Analyse-Seite steht als **Zahl** im Befund
   (Plateau-Nachbarschaft je Kandidat, Symbol-Streuung, DSR mit N und SR0) — purge-fest und
   auch in einem frischen Kontext lesbar. Die Bilder sind ein Werkzeug für den Menschen.
   Verlangt der Auftrag oder der User sie, gilt: **dann zeitkritisch** — vor dem Purge, weil
   Heatmaps und Verteilung danach unwiederbringlich weg sind. Verfahren (Toolbox-Verb
   `analyse-screenshot`) in
   [`references/screenshot-standard.md`](references/screenshot-standard.md).
4. **Abschlussbericht Ist-gegen-Soll** mit **allen** Vorbehalten (Rastergröße, `N_eff`,
   Holdout-Berührungen) — als Deutung zum Befund und als Log-Eintrag an der Iteration. Liegt
   ein Signifikanztest vor, gehören p-Wert **und** Null-Verteilung samt N mit in den Bericht;
   liegt keiner vor, ist das ein Vorbehalt. Dasselbe gilt für die Walk-Forward-Kette: liegt
   eine vor, wird die Chain-ID genannt und das Aggregat **nur zusammen mit der Fold-Tabelle**
   zitiert; liegt keine vor, ist das ein Vorbehalt. Verweise auf Sieger-Setup (`?setupid=N`) und
   finalen Analyse-Lauf (`/backtest/runs/N/analyse`) **als volle URL** in die Deutung schreiben —
   die Konzept-Detailseite (`/config/strategy-concepts/{id}`) rendert sie dann klickbar
   (Auto-Linking).

## Phase 9 — Aufräumen

**Der Purge ist Pflicht, keine Ermessensfrage.** Am Ende des Auftrags existieren nur noch
Results mit rotem Doku-Stern. „Der volle Result-Satz könnte für spätere Analyse-Ansichten
nützlich sein" ist **keine** gültige Begründung, ihn stehen zu lassen — die Erkenntnis lebt
im Befund (Plateau-Nachbarschaft, Streuung, DSR mit N und SR0) und in den Logs; wer die
Analyse-**Ansicht** als Bild braucht, holt sie vorher (Teil 2, „Analyse-Screenshots"). (Die
ersten beiden Aufträge haben den Purge mit genau dieser Begründung übersprungen; das war
falsch und musste vom User nachgeräumt werden.)

- Rechenspuren löschen, die weder im Befund noch in der Doku referenziert sind:
  `result-delete-all --testset-run <id>` (bzw. `--run <id>` für einen einzelnen Run) räumt
  in einem Aufruf alle Nicht-Favoriten der Menge weg, Favoriten und fremde Objekte bleiben
  unberührt — bevorzugt gegenüber händischem ID-Diffing. Für Einzelfälle:
  `run-delete <id>`, `run-bulk-delete --ids 1,2,3`, `result-delete <id>`,
  `result-bulk-delete --ids …`.
- **Im Auftrag angelegte IndicatorConfigs zurückbauen:** `indicator-config-delete <id>`.
  Was inline gemessen wurde, hat ohnehin keine Zeile hinterlassen; was als benannter
  Messpunkt angelegt wurde und diesen Rang am Ende nicht behält, wird gelöscht statt
  liegengelassen. **Behalten** wird nur, was bewusst als benannter Messpunkt bleiben soll
  (Spitzenreiter, Vergleichsmessung, Härtung) — dann mit Log-Eintrag, warum; dieselbe Regel
  wie bei Results mit rotem Doku-Stern. Configs aus früheren Aufträgen bleiben unangetastet.
- **Was bleibt:** ausschließlich Results mit rotem Doku-Stern (samt ihrer Runs), die
  Befunde, die Iterations-Logs, die bewusst behaltenen IndicatorConfigs und die
  eingefrorenen Artefakte (Signifikanztests, Walk-Forward-Ketten).
- Interessante Nebenfunde dürfen bleiben — dann `result-doc-favorite <id>` **plus**
  Log-Eintrag, warum.
- Die Wegwerfbarkeit ist Absicht: Erkenntnis lebt in Befund und Log, nicht in Millionen
  Result-Zeilen.

## Phase 10 — Werkzeug-Lücken melden

Fehlt unterwegs ein Werkzeug, ein Indikator oder eine Fähigkeit, entsteht ein Eintrag in
`documentation/todo/ki-strategy-development/werkzeug-luecken.md` — nach dem dort im Kopf
festgelegten Schema (`## JJJJ-MM-TT — <Kurztitel>` mit Auftrag/Kontext, Was fehlte, Wie
improvisiert wurde, Was ein Werkzeug ändern würde). **Vor jedem Eintrag Duplikat-Prüfung**:
bei Treffer den bestehenden Eintrag ergänzen statt einen neuen anzulegen. Die Datei ist Input
für den User — kein Status, kein Abarbeiten durch dich.

**Stilles Ausweichen in projektfremde Wegwerf-Skripte ist verboten.** Muss improvisiert
werden, dann dokumentiert und in `user_data/ablage_uebungen/` (das Windows-venv sieht kein
WSL-`/tmp`), mit Aufräumen danach.

---

# Teil 2 — Objekt-Toolbox

Helper-Skript `toolbox.py`, um bt_pro_app-Objekte in einem Schritt zu **lesen** (kompaktes
Markdown-Briefing statt 4-5 Einzel-Curls), zu **kopieren**, **anzulegen**, zu
**ändern/löschen** oder Läufe zu **starten**. Jede Maßnahme ist ein **einzelnes Werkzeug**,
einzeln aufgerufen. Vollständige Werkzeug-Liste mit je einem Satz:
`documentation/project/handbuch.md` (Abschnitt „Toolbox-Werkzeuge").

**Zwei Naturen — danach sind die Abschnitte sortiert:**
1. **Lesen** — harmlos, fasst nichts an, jederzeit nutzbar: URL/ID reinwerfen, Briefing zurück.
2. **Schreiben** — anlegen, kopieren, Lauf starten, auswerten, ändern, löschen, markieren.
   Schreibt über die API.

**Doku-Index (vor strukturschaffender Arbeit lesen):** Einstieg in die Strategie-Methodik ist
`documentation/knowledge/strategy-development/AGENT_ENTRY.md` — dort die
„Workflow-Index"-Tabelle (Aufgabe → erst lesen → dann tun). Basis-Referenzen daneben:
`begriffe-und-modi.md` (Terminologie) und `code-referenz.md` (Mechanik). Reines
Lesen/Kopieren/Löschen braucht das nicht; sobald aber eine **Strategie entsteht oder
strukturell verändert** wird, erst die passende AGENT_ENTRY-Zeile lesen, dann handeln.

### Lesen (Default, keine Aktion)

```bash
python3 .claude/skills/ds-strategie-session/scripts/toolbox.py <arg1> <arg2> ...
```

Akzeptierte Lese-Argumente, beliebig mischbar:

- **Frontend-URLs:** `/config/backtest/<id>`, `/config/indicator/<id>`,
  `/config/playground/<id>`, `/backtest/results/<id>`, `/backtest/runs/<id>`, `/testsets/<id>`,
  `/config/strategy-concepts/<id>/iterations/<id>/edit`
- **`<bereich>:<id>`:** `iteration:26`, `indicator-config:1970`, `backtest-config:553`,
  `result:2635737`, `run:1753`, `concept:1`, `strategy-config:1`, `testset:421`,
  `leaderboard:199`, `playground-setup:17`
- **Wissens-Recherche:** `knowledge:"teststrategie exit logik"` (semantische Vektorsuche,
  Top-5, `--k <n>` für mehr Treffer), `vault:teststrategie` (Pfad-Substring → indizierte
  Dateien)
- `run:<id>` nutzt den Einzel-GET — unabhängig davon, ob der Run unter den letzten Läufen liegt.

Die Lese-Ausgabe **wortwörtlich** zurückgeben — keine eigene Reformulierung, keine
Zusammenfassung dahinter. Der User will die Roh-Bausteine sehen, nicht die Deutung.

### Schreib-Aktionen (je Aufruf nur ein Aktions-Typ)

```bash
toolbox.py copy iteration:2                              # kopieren: iteration, backtest-config, indicator-config
toolbox.py create-indicator-config result:2706026:Sharpe # Gewinner-Params → reproduzierbare Single-Point-Config (optional)
toolbox.py concept-create --slug teststrategie --name "Teststrategie"  # anlegen: concept, iteration, *-config, testset
toolbox.py iteration-create --concept 1 --file spec.json #   komplexe Payloads (spec_json/config_json/Backtest-Body) per --file
toolbox.py backtest-run-start --backtest-config 552 --indicator-config 1970 --iteration 41  # Lauf starten
toolbox.py testset-run-start --testset 293 --iteration 41 --indicator-config 1973  # 1 Run pro Config; Leaderboard nur bei leaderboard_enabled
toolbox.py testset-run-start --testset 293 --iteration 41 --indicators config.json #   Raster inline statt Config-ID (genau eines von beiden); auch preflight kennt --indicators
toolbox.py run-list --strategy teststrategie --version 1  # Runs zu Strategie+Version (nach Testset-Lauf gruppiert, zeigt Auftrags-ID testset-run)
toolbox.py iteration-log-add --id 41 --text "..." [--run 1812]  # Denkprotokoll, append-only
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
- `--file` reicht das JSON **unverändert** durch: kein stiller Konverter, kein Fallback —
  scheitert laut, wenn falsch geformt.
- **`concept-create` / erste `iteration-create` = neue Strategie:** vorher
  `workflows/neue-strategie.md` lesen (siehe Doku-Index oben). Das `spec_json` enthält **nur**
  `indicators` (flach, **ohne** `_stops`) + `rules`; Stops gehören in die IndicatorConfig
  (`_stops`), Portfolio in die BacktestConfig.
- `create-indicator-config`: Segment-Label (z.B. Return/Sharpe/PF) optional via `:` oder `/`;
  nur `result` als Quelle. Optional — der Sweep-Run liegt ohnehin in der DB.
- Kopien/IndicatorConfigs bekommen Namenszusatz bzw. Konvention; **Originale bleiben
  unangetastet**.
- **Nachträgliche Verknüpfung:** Eine bestehende Indicator-Config einem Konzept/einer Iteration
  zuweisen (oder gezielt Name/Beschreibung setzen) über
  `indicator-config-set --id <n> [--concept … --iteration … --name … --description …]` —
  Teil-Update, `config_json`/`_stops` bleiben bit-genau. NICHT `indicator-config-update` (voller
  Replace, braucht den kompletten Body).
- **Indicator-Config-Labels nicht selbst basteln:** Für die reine Standard-Notation
  `indicator-config-generate-labels <id>` (überschreibt Name+Beschreibung komplett, ohne
  Freitext). Für einen **individuellen Freitext** stattdessen
  `indicator-config-labels --id <n> [--name-freetext … --desc-freetext …] --save` — holt die
  Notation zustandslos, setzt den Freitext an die richtige Stelle und schreibt nur
  Name/Beschreibung zurück (ohne `--save` nur Vorschau). Beide nutzen dieselbe
  Server-Notation (Single Source, identisch zu den Frontend-Buttons):
  - **Name:** `<Konzept>-<Iteration>-(<Kombinationen>) <Stops>` (z. B.
    `VWMA-3-(35) TP 30% SL 15% TD 1-999 (35), rows`). Ohne verknüpftes Konzept nur
    `(<Kombinationen>)`; ohne Iteration nur die Nummer. Stops leerzeichengetrennt (`TP`, `SL`,
    `TSL`, `TD`; Format-Wort per Komma am Stop), Sweep-Achsen als `min-max (n)`. Ein
    **Freitext** (`--name-freetext`) hängt hinten per ` : ` an — kurze, lesbare Kennung (Symbol
    + Regime/Kontext).
  - **Beschreibung:** Auflistung der Indikatoren mit Werten/Wertebereichen —
    `<name>: <param> <wert>, <param> <min-max (n)>; …`. Ein **Freitext** (`--desc-freetext`)
    steht **vor** der Auflistung, per ` | ` getrennt (`<Freitext> | <Auflistung>`).
  - **Freitext IMMER ausschreiben — keine kryptischen Kürzel.** Deutsch formuliert
    (Eigenwörter wie `Total Return` bleiben englisch); ohne Vorwissen verständlich.
- `iteration-delete`/`concept-delete` ohne `--force` → Backend meldet **409 mit
  Blocker-Zählern**: nachfragen, nicht blind forcen.

### Gezielt bearbeiten (add / remove / change — der Alltagsfall)

Für „kopieren und dann einen Indikator/eine Regel/ein Feld ergänzen oder entfernen" gibt es
**gezielte Bearbeitungsverben**. Sie holen das Objekt, ändern **genau einen Teil** und
schreiben zurück — der Rest bleibt bit-genau. **Kein** kompletter Body per `--file` nötig (das
ist nur `-update`, der Voll-Replace).

- **Felder (Meta/flach):** `concept-set` · `iteration-set` · `backtest-config-set`. Beispiel:
  `backtest-config-set --id 552 --fees 0.0005 --symbol ETHUSDT`.
- **Indikatoren:** `iteration-indicator-set/-remove` (spec_json.indicators) ·
  `indicator-config-indicator-set/-remove` (config_json). `--file` ist **nur der eine
  Indikator-Block** (z. B. `{"indicator":"talib:SMA","tf":"4h","close":"close","timeperiod":50}`);
  in der Config dürfen Werte arange-Ranges sein. Existiert der Key, wird **gemergt**: nur die
  genannten Parameter ändern sich — einen einzelnen Wert ändert man also mit
  `--file {"timeperiod":50}`. `--replace` ersetzt den Block komplett (auch `tf` fällt weg).
  - **`tf` ist Pflicht und laufzeit-wirksam** (`indicator_factory.py`: fehlender/leerer `tf` →
    ValueError). Bei `--replace` gehört es in den Block; beim Merge bleibt es von allein.
- **Stops:** `indicator-config-stops-set --id N [--tp --sl --td --tsl --tsl-th --delta-format
  --time-delta-format]` — einzelne Werte in `_stops`, Rest bleibt. `null` löscht einen Wert.
- **Regeln:** `iteration-condition-add --id N [--exit] [--block K | --new-block [--short]]
  --file cond.json` · `iteration-condition-remove --id N [--exit] --block K [--index J |
  --remove-block]`. `--file` ist **eine** Bedingung
  (`{"op":">","lhs":"close","rhs":"indicator:sma:real"}`). Ohne `--block` an Block 1 (UND);
  `--new-block` erzeugt einen ODER-Block.

**Wichtig — Laufzeit-Zuordnung (am Code belegt, `worker_tasks.py`):** Bei einem Backtest kommen
die **Indikatoren aus der IndicatorConfig** (`config_json`), die **Regeln aus der Iteration**
(`spec_json.rules`). Wer einen Indikator ergänzt, der logik-wirksam werden soll, muss ihn in die
**Config** (mit Range, `indicator-config-indicator-set`) UND die referenzierende Regel in die
**Iteration** (`iteration-condition-add`) legen. `spec_json.indicators` ist die kanonische
Iterations-Definition, wird beim Run aber nicht als Indikator-Quelle genutzt.

**Immutability ist Konvention, kein Gate:** Der Server editiert Iterationen in-place (kein
Run-/Result-Check). Struktur-Änderungen trotzdem per `copy` auf eine frische Iteration und dort
bearbeiten — das schützt gelaufene Stände.

### Auswertung eines Multiparameter-Laufs — die vier Bestwerte

**Auslösen.** Der Lauf wird meist locker benannt — „bewerte die Ergebnisse aus dem neuen
Testset-Lauf", „markiere die Bestwerte", „zieh die Bestwerte aus Run X". Die Bezeichnungen
**Run**, **Testset-Lauf** und **„alle neuen"** sind gleichwertig: sie meinen dieselben Results,
die markiert werden — **gruppiert nach Run**. Der gemeinte Lauf wird per Recherche aufgelöst
(`run-list`), nicht per Rückfrage. **Standard-Weg ist `run-bestwerte --testset-run <id>` — ein
Aufruf je Testset-Lauf.** Umfasst der Auftrag mehrere Läufe, folgt je ein Aufruf pro Lauf;
entscheidend ist **Vollständigkeit** (`--iteration`/`--run` sind Sonderfälle). Nur wenn unklar
bleibt, welcher von mehreren gleichwertigen Läufen gemeint ist, folgt eine gezielte Rückfrage.

Aus jedem fertigen Sweep-Run werden genau **vier** Bestwerte gezogen und als **roter
Doku-Favorit** markiert (schützt vor „Alle löschen"). Das übernimmt **eine** Aktion — die
Definition ist serverseitig gekapselt und idempotent, kann also nicht von Hand falsch
zusammengesetzt oder doppelt gesetzt werden:

```bash
toolbox.py run-bestwerte --testset-run 3     # STANDARD: alle Runs eines Testset-Laufs (Auftrags-ID)
toolbox.py run-bestwerte --iteration 2       # Sonderfall: alle Runs einer Iteration (Strategie+Version)
toolbox.py run-bestwerte --run 1812          # Sonderfall: nur ein einzelner Run
```

Welches Kriterium ein Result gewonnen hat, wird **am Result persistiert**
(`best_criteria_json`) — ein Result kann mehrere gleichzeitig gewinnen. In der Results-Tabelle
steht es als Kürzel-Spalte „Bestwert" (`T` Max Total Return · `W` Win-Rate-Band · `S`
Sharpe-Band · `P` Profitfaktor ≥30 Trades, Langform im Hover); `run-favorites-list` und
`kreuztest` weisen es aus der Spalte aus. Beim Zurücksetzen (`run-favorites-reset`) wird es mit
dem roten Stern gekoppelt geleert. Nötig, weil die Bänder run-relativ sind und nach dem Löschen
der übrigen Run-Results nicht mehr herleitbar wären.

Die vier Kriterien (Detail + Raster-Format:
`documentation/knowledge/strategy-development/workflows/multiparameter-lauf.md`) — jede Metrik
hat eine eigene Regel, nicht vereinheitlichen:

1. **Max Total Return** — reines Maximum, kein Trade-Floor
2. **Win-Rate-Band → bestes Return** — Band = Top 20 % vom Höchstwert (höchste WinR − 20 % vom
   Höchstwert); daraus das höchste Total Return
3. **Sharpe-Band → bestes Return** — dieselbe Band-Mechanik mit Sharpe, aber engeres Band:
   Top 10 %; daraus das höchste Total Return. Bewusst enger als das Win-Rate-Band, damit der
   Sieger seltener mit Max Total Return zusammenfällt
4. **Max Profitfaktor mit ≥30 Trades** — Trade-Floor gegen Low-Trade-Flukes; gilt NUR für PF

**Bei Wertgleichstand** (z. B. Raster-Dubletten mit identischem Ergebnis) wählt die Auswahl
deterministisch: zuerst das risikoärmere Result (**geringster Drawdown**), dann die **ID** als
finaler Anker — so ist die Markierung reproduzierbar. **Kein** Promotions-/Akzeptanz-Schritt.

Manueller Unterbau (nur für Ad-hoc-Kontrolle einzelner Kriterien):
`run-top-results <run_id> <metrik> 1 desc` (Kriterium 1 + Bandgrenzen von 2/3),
`run-best <run_id> profit_factor 30` (Kriterium 4), Markierung einzeln via
`result-doc-favorite <result_id>`. Die Band-Sieger zieht nur `run-bestwerte`.

### Analyse-Screenshots (auf Zuruf — dann zeitkritisch)

Die Analyse-Seite eines Runs (`/backtest/runs/<id>/analyse`) ist nur aussagekräftig, solange
der volle Result-Satz lebt — nach dem Ergebnis-Purge bleiben nur die Favoriten übrig, Heatmaps
und Verteilung sind dann unwiederbringlich weg. Wer Bilder will, holt sie also **vor** dem
Purge. Im Entwicklungs-Loop ist der Schritt **keine Pflicht** (Phase 8); verlangt ihn ein
User-Auftrag, folgt er **direkt** auf den zugehörigen Lauf bzw.
`run-bestwerte`-Durchgang: pro Run zwei
Vollseiten-PNG im Standard-Zustand (Referenzschuss auf Total Return plus Schuss auf die
Zielkennzahl des Auftrags), abgelegt im Vault beim Iterations-Ordner
(`iterations/<version>/img/`). Hauptweg ist das Toolbox-Verb `analyse-screenshot` — ein Aufruf pro Bild, das PNG landet direkt am Zielpfad, kein Browser-Werkzeug
mehr nötig. Details, Sollwerte und Namensschema in
[`references/screenshot-standard.md`](references/screenshot-standard.md). In der Iter-Note
werden die Bilder relativ eingebettet (`![](img/run-<id>-….png)`).

### Iterations-Vergleichstabelle (ein Verb, purge-fest)

`vergleichstabelle --strategy <slug>` stellt je Testset die markierten Bestwerte aller
Iterationen nebeneinander — Zeilen Symbol × Iteration, Spalten Spitze (Max Total Return) und
robuster Kern (Profitfaktor ≥ 30 Trades). Quelle sind ausschließlich die roten Doku-Favoriten
samt persistierter Bestwert-Kriterien — die Tabelle funktioniert daher auch für Läufe, deren
volle Result-Sätze längst gelöscht sind. Einzel-Läufe ohne Testset bleiben bewusst außen vor.
Nach jedem neuen Testset-Lauf (nach `run-bestwerte`) neu generieren:

```bash
toolbox.py vergleichstabelle --strategy <slug> --save "$VAULT_ROOT/30_Trading/strategies/<slug>/vbt/iterationen-vergleich.md"
```

Läufe ohne markierte Bestwerte weist die Ausgabe explizit aus (erst `run-bestwerte`
nachholen). Große Runs brauchen einige Sekunden pro Run — das Verb wartet selbst.

### Vollständige Referenz (Detail-Flags, alle Routen)

- **Syntax/Flags je Aktion:**
  `python3 .claude/skills/ds-strategie-session/scripts/toolbox.py --help`

**Lite-Sondierung immer mit `--concept`:** `playground-run-backtest-lite --file spec.json
--concept <id>` rechnet eine Kombination ohne DB-Schreiben und zählt den Aufruf am Konzept mit
(`probe_count`, in der Antwort als `concept_probe_count`, im Konzept-Briefing und im Befund
neben der Rastergröße sichtbar). Im Auftragskontext gehört das Flag an **jeden** Lite-Aufruf —
ohne es bleibt der Suchumfang der Sondierungsschleife unsichtbar. Der Zählerstand wird
ausgewiesen, nicht bewertet: keine Schwelle, keine Verrechnung in `N` oder DSR.

**Kein fabrizierter Curl / kein `sys.path`-Import des Skripts.** Wenn du den **rohen** Ist-Body
eines Objekts brauchst (z. B. um einen `-update --file` zu bauen), nimm das generische Verb
`api GET <route>` — das gibt das rohe JSON aus (z. B.
`toolbox.py api GET /api/strategy/iterations/8`). Für gezielte Teiländerungen die
`-set`/`-indicator-set`/`-condition-add`/`-stops-set`-Verben oben.

**Lange Antworten:** Die Anzeige kappt bei 4000 Zeichen — der Schnitt liegt mitten im JSON, das
Ergebnis ist dann **nicht mehr parsebar**. Zwei Flags lösen das auf (bei allen Lese-Verben
(GET) und beim `api`-Verb; bei Nicht-GET-Verben führen sie zu einem Fehler):

```bash
toolbox.py run-results 1812 --out                                # ohne Wert: Auto-Name mit Zeitstempel
toolbox.py api GET "/api/backtest/runs/222/analyse/parameter-ranking?metric=total_return_pct" --out ranking.json
toolbox.py api GET "/api/…" --full                               # ungekürzt in den Kontext
```

`--out` schreibt ungekürzt in eine Datei und gibt auf der Konsole nur Pfad + Zeichenzahl aus —
**die bevorzugte Variante**, weil das Kontextfenster klein bleibt und Folge-Analysen die Datei
per `json.load` lesen können. `--full` gibt alles auf stdout aus. Beide zusammen sind ein
Fehler.

**Ablageort und Aufräumen (kein Müll im Repo):** `--out` schreibt **immer** unter
`<TEMP>/bt-toolbox-out/`. Ein reiner Dateiname oder relativer Pfad landet dort — **nicht** im
Arbeitsverzeichnis. Nur ein absoluter Pfad wird wörtlich genommen (dann ohne Cleanup).
Aufgeräumt wird automatisch: bei **jedem** `--out`-Schreiben fliegen Dateien raus, die älter
als 24 h sind. Sofort von Hand:

```bash
toolbox.py out-clean          # nur abgelaufene (>24h)
toolbox.py out-clean --all    # Ordner komplett leeren
```

**Fehlt wirklich ein Verb/Feld**, das weder ein Bearbeitungsverb noch
`api GET/PUT/PATCH/POST/DELETE` abdeckt, ist das eine Werkzeug-Lücke → Phase 10.

### Fehlerbilder

- **Argument nicht geparst:** Skript druckt `## Konnte nicht parsen: <arg>` — nicht raten, User
  um URL/Typ-Prefix bitten.
- **HTTP 404 / Method Not Allowed:** pro Objekt vom Skript gemeldet — ID prüfen, ggf. anderen
  Endpoint anbieten.
- **Backend nicht erreichbar:** Connection-Fehler — User bitten, `docker ps` zu prüfen.
- **Vault nicht erreichbar:** `$VAULT_ROOT` nicht gesetzt oder Pfad nicht lesbar — ohne Vault
  weiterarbeiten und den Ausfall im Bericht ausweisen.

## Was du nicht tust

- **Keine Änderungen an Projekt-Code.** Schreib-Aktionen gehen ausschließlich über die
  Toolbox-Verben (legen/ändern bt_pro_app-Objekte über die API an).
- **Kein neuer Indikator-Code für die Optimierung** — mit dem vorhandenen Arsenal arbeiten
  (Messwerkzeuge ausgenommen).
- **Keine improvisierten Ersatzrechnungen für fehlende Werkzeuge** — Vorbehalt ausweisen,
  Lücke melden. Für den Signifikanztest gibt es das Werkzeug (`signifikanz-start`, Phase 7),
  für Walk-Forward die Fold-Kette (`walk-forward-chain-start`, Phase 7); eigene Nullmodelle
  und selbstgebaute Fold-Schleifen sind damit unnötig.
- **Keine nachträglich geänderten Bewertungskriterien** und keine erfundenen Schwellen: nur an
  dokumentierten Leitplanken und am `goal_json` messen.
- **Keine Caveman-Aktivierung** — der Skill läuft im normalen Stil.

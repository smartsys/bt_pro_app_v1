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
- [Abgebrochenen Lauf fortsetzen](#abgebrochenen-lauf-fortsetzen) — Teilergebnisse behalten statt neu rechnen
- [Konzept-Detailseite](#konzept-detailseite) — Ziel neben Befund-Historie, klickbare Verweise
- [Leaderboard-Rerun](#leaderboard-rerun) — Eintrag aus dem Snapshot reproduzieren
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
`backtest_results`.

**Die Kennzahlen sind vollständig, bevor die Analyse startet.** Seit Ticket 64 entstehen
sie in genau einer Funktion, die für jeden Lauf denselben Satz liefert — egal ob der Lauf
eine Kombination hatte oder dreitausend. Die früheren Berechnungsstufen (`partial`,
`chart`, `full`), das Feld `metrics_level` und der Knopf „Vollanalyse starten" gibt es
nicht mehr. Die Frage „welchen Rechenpfad ist dieses Result gelaufen?" ist damit nicht
mehr stellbar.

> **Bruch mit dem Altbestand — bewusst und ohne Umrechnung:** Results, die vor Ticket 64
> entstanden sind, tragen weiterhin nur die Felder ihrer damaligen Stufe; bei ihnen sind
> unter anderem `sqn`, `edge_ratio`, `tail_ratio` oder die Trade-Detail-Felder leer, und
> `skew`/`kurtosis` fehlen ganz. Sie werden **nicht** nachgerechnet. Alte und neue Results
> sind in ihrer Feldmenge nicht vergleichbar.

#### `backtest_results` — Kennzahlen je Kombination

| Feld-Gruppe | Felder | Nach dem Lauf | Nach der Analyse |
|---|---|---|---|
| **Identität / Config** | `run_id`, `params_hash`, `actual_params_json`, `resolved_config_json`, `full_config_snapshot_json`, `iteration_id`, `is_favorite`, `is_doc_favorite` | vorhanden | unverändert |
| **Zeitraum / Umfang** | `start_index`, `end_index`, `total_duration`, `bar_count` | vorhanden | unverändert |
| **Portfolio** | `start_value`, `min_value`, `max_value`, `end_value` | vorhanden | unverändert |
| **Rendite** | `total_return_pct`, `benchmark_return_pct`, `annualized_return`, `annualized_volatility` | vorhanden | unverändert |
| **Exposure** | `position_coverage_pct`, `max_gross_exposure_pct` | vorhanden | unverändert |
| **Drawdown** | `max_drawdown_pct`, `max_drawdown_duration` | vorhanden | unverändert |
| **Orders / Kosten** | `total_orders`, `total_fees_paid` | vorhanden | unverändert |
| **Trades** | `total_trades`, `open_trades`, `long_trades`, `short_trades` | vorhanden | unverändert |
| **Trade-Qualität** | `win_rate_pct`, `profit_factor`, `expectancy`, `sqn`, `edge_ratio`, `best_trade_pct`, `worst_trade_pct`, `avg_winning_trade_pct`, `avg_losing_trade_pct`, `avg_winning_trade_duration`, `avg_losing_trade_duration` | vorhanden | unverändert |
| **Risiko** | `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`, `omega_ratio`, `downside_risk` | vorhanden | unverändert |
| **Extremrisiko** | `tail_ratio`, `value_at_risk`, `cond_value_at_risk` | vorhanden | unverändert |
| **Benchmark-relativ** | `alpha`, `beta`, `information_ratio` | vorhanden | unverändert |
| **Verteilungsform** | `skew`, `kurtosis` | vorhanden | unverändert |
| **Overfitting-Kontrolle** | `deflated_sharpe_ratio` | vorhanden | unverändert — siehe Hinweis |
| **Reproduzierbarkeit** | `spec_runner_version` | vorhanden | unverändert |

> **`kurtosis` ist die rohe Wölbung**, nicht die Excess-Wölbung: eine Normalverteilung
> liegt bei rund 3, nicht bei 0.

> **`deflated_sharpe_ratio` entsteht als Nachlauf über den ganzen Lauf** und wird von der
> Analyse nicht mehr angefasst (seit Ticket 54). Sie misst, ob der beste Kandidat nur der
> Gewinner einer Zufallsauswahl ist, und rechnet dafür über **alle** Kombinationen des
> Rasters — ein einzeln nachgerechnetes Result sieht nur sich selbst und könnte sie gar
> nicht bestimmen. Bis dahin überschrieb jede gestartete Analyse den vorhandenen Wert mit
> NULL; dieser Schaden ist behoben. Die Zahl ist ein **Report, nie ein Filter**: sie
> schließt nichts aus und sortiert nichts weg. Ihr Vergleich zwischen Läufen trägt, ihr
> absoluter Wert ist bei sehr schiefen Renditeverteilungen mit Vorsicht zu lesen. Ein
> leeres Feld bedeutet: Für dieses Result fehlen die Bausteine (keine Trades, keine
> Momente) oder es stammt aus einem Lauf vor der Korrektur.

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

## Abgebrochenen Lauf fortsetzen

Ein Multiparameterlauf mit vielen Kombinationen wird in **Chunks** gerechnet (Blöcke von
höchstens 5000 Kombinationen). Jeder fertig gerechnete Chunk wird sofort gespeichert. Wird
der Lauf mittendrin hart beendet — Speichermangel, Container-Neustart, harter Abbruch des
Worker-Prozesses —, bleiben die Ergebnisse der abgeschlossenen Chunks erhalten; verloren ist
höchstens der Chunk, an dem gerade gerechnet wurde.

**Bedienung:** In der Run-Liste zeigt ein abgebrochener Lauf mit gespeicherten Chunks einen
grünen **Fortsetzen**-Knopf. Er reiht den Lauf wieder ein; gerechnet wird ab dem ersten noch
nicht gespeicherten Chunk. Über die Toolbox: `python3 toolbox.py run-resume <run-id>`.

**Fortsetzen ist nicht Rerun.** Die beiden Knöpfe liegen nebeneinander und tun
Gegensätzliches:

| Knopf | Was er tut | Was mit den Results passiert |
|---|---|---|
| **Fortsetzen** (grün) | Rechnet ab dem ersten fehlenden Chunk weiter. | Bleiben erhalten. |
| **Rerun** (gelb) | Rechnet den ganzen Lauf von vorn. | Werden gelöscht und neu erzeugt. |

Ein fortgesetzter Lauf liefert am Ende genau dasselbe Ergebnis wie ein Lauf, der in einem
Stück durchgelaufen ist — gleiche Kombinationszahl, keine Dubletten und dieselben
Kennzahlen. Das gilt ausdrücklich auch für die Deflated Sharpe Ratio, die über das gesamte
Raster gerechnet wird: sie entsteht als Nachlauf, nachdem der letzte Chunk gespeichert ist.

**Der Anstoß bleibt manuell.** Abgebrochene Läufe werden nicht automatisch neu gestartet.
Ein Lauf wird erst fortsetzbar, wenn er als abgebrochen erkannt ist — das erledigt der
periodische Aufräumer, der tote Läufe von `running` auf `failed` setzt und den Grund
(z.B. Speichermangel) an den Lauf schreibt.

---

## Konzept-Detailseite

Zeigt das Ziel eines Strategie-Konzepts neben seiner vollständigen Befund-Historie — der
Abschluss eines Auftrags wird damit im System selbst lesbar: Was war das Soll, was haben
die Messungen ergeben, wo stehen Sieger-Setup und finale Analyse.

**Aufruf:** aus der Konzept-Übersicht (`/config/strategy-concepts`) über den Konzept-Namen,
oder direkt `http://localhost:5570/config/strategy-concepts/{concept_id}`.

Die Seite liest nur — Ziel bearbeiten bleibt der Übersicht vorbehalten. Sie zeigt:

- **Ziel:** `goal_prompt` im Wortlaut (Blockzitat) und `goal_json` lesbar formatiert; fehlt
  beides, steht das explizit da statt eines leeren Kastens.
- **Befund-Historie:** alle Befunde des Konzepts chronologisch, je Befund einklappbar mit
  Soll-Schnappschuss neben Ist-Kern (Kandidaten je Bestwert-Kriterium), Robustheit (die
  Deflated Sharpe Ratio immer zusammen mit Rastergröße N und Rauschlatte SR0),
  Warnhinweisen und Deutung. Leere Felder zeigen ihren Grund statt zu verschwinden.
- **Kein Verdict:** keine Ampel, kein Ranking, keine Sortierung nach Kennzahlen — die
  Reihenfolge ist strikt chronologisch, die Seite zeigt, sie urteilt nicht.
- **Klickbare Verweise:** URLs und projektinterne Pfade im Deutungstext
  (`?setupid=`-Deeplinks zum Chart-Playground, `/backtest/runs/{id}/analyse`) werden
  automatisch als Links erkannt (Auto-Linking); der restliche Text bleibt reiner,
  escapeter Text — kein HTML aus der Deutung wird ausgeführt.

## Leaderboard-Rerun

Reproduziert einen bestehenden Leaderboard-Eintrag ausschließlich aus seinem eingefrorenen
Snapshot — unabhängig davon, ob sich die zugrundeliegende Config oder Iteration seither
geändert hat.

**Aufruf:** Knopf „Erneut ausführen" je Zeile im Leaderboard (`/leaderboard`).

Ein Klick öffnet einen Bestätigungsdialog (`tabler.Modal`, kein `window.bootstrap`); nach
Bestätigung läuft der Rerun und das Ergebnis erscheint im selben Dialog: die ID des neu
angelegten Leaderboard-Eintrags plus Anzahl der Configs, dazu die bit-genaue Reproduktion
(„exakt reproduziert" / „weicht ab" / „nicht vergleichbar" ohne Vergleichswert). Schlägt der
Rerun fehl — etwa weil der Eintrag keinen verwertbaren Snapshot besitzt —, erscheint die
Fehlermeldung an derselben Stelle statt einer stumm bleibenden Seite. Der bestehende
Eintrag bleibt in jedem Fall unverändert.

---

## Toolbox-Werkzeuge

> Alle Werkzeuge des Helfer-Skripts `toolbox.py` aus dem Skill `ds-strategie-session`. Der
> Skill hat zwei Seiten: den **agentischen Entwicklungs-Loop** (Phasen 0–10 vom Auftrag bis
> zum Abschluss, siehe SKILL.md) und diese **Objekt-Toolbox**, die auch einzeln nutzbar ist.
> Jede Maßnahme ist ein einzelnes Werkzeug; die Toolbox startet nie von allein einen Loop.
> Aufruf: `python3 .claude/skills/ds-strategie-session/scripts/toolbox.py <werkzeug> ...`
>
> Sehr lange GET-Antworten werden auf 4000 Zeichen gekürzt — die Toolbox weist das dann
> immer sichtbar mit der Original-Größe aus (`[gekürzt: 4000 von N Zeichen — --full oder
> --out <datei> für die volle Antwort]`), nie stillschweigend. Bei betroffenen Werkzeugen
> gezielt filtern (z.B. `playground-indicators` mit `--group`/`--search`) statt den
> gekürzten Rohdump zu lesen, oder die Kappung mit `--out [datei]` (vollständig in eine
> Datei unter `<TEMP>/bt-toolbox-out/`, Konsole nur Pfad + Zeichenzahl) bzw. `--full`
> (vollständig auf stdout) umgehen. Beide Flags gibt es bei **allen Lese-Werkzeugen**
> (GET) — nicht nur beim generischen `api`-Verb (siehe „Generisch" unten) — und schließen
> sich gegenseitig aus.

### Lesen — ein Objekt als kompaktes Briefing

| Werkzeug | macht |
|---|---|
| `concept:<id>` | Liest ein Strategie-Konzept aus und gibt Name, Slug und Kerndaten zurück. |
| `iteration:<id>` | Liest eine Iteration aus und zeigt Indikatoren und Regeln aus dem spec_json, dazu die Anzahl der Log-Einträge und die letzten 3 (Text auf 200 Zeichen gekürzt, Ticket 67) — für den vollen Verlauf `iteration-log-list`. |
| `indicator-config:<id>` | Liest eine Indicator-Config aus und listet jeden Indikator mit seinen Parametern. |
| `backtest-config:<id>` | Liest eine Backtest-Config aus (Symbol, Zeitraum, Portfolio-Einstellungen). |
| `strategy-config:<id>` | Liest eine Strategy-Config aus (Legacy, hardcoded/generic). |
| `result:<id>` | Liest ein einzelnes Result mit seinen Kennzahlen aus. |
| `run:<id>` | Liest einen Run über den Einzel-GET aus (Ticket 70/C — unabhängig von den letzten N Runs). |
| `testset:<id>` | Liest ein Testset mit seinen zugeordneten Configs aus. |
| `leaderboard:<id>` | Liest einen Leaderboard-Eintrag im Drilldown aus. |
| `playground-setup:<id>` | Liest ein Chart-Playground-Setup aus. |
| `knowledge:"..." [--k <n>]` | Semantische Vektorsuche im Vault-Index, gibt die Top-Treffer zurück (Default 5, Ticket 70/D). |
| `vault:<pfad>` | Listet indizierte Vault-Dateien nach Pfad-Substring. |

### Listen — mehrere Objekte auf einmal

| Werkzeug | macht |
|---|---|
| `concept-list` | Listet alle Strategie-Konzepte. |
| `iteration-list [concept_id]` | Listet alle Iterationen, optional auf ein Konzept gefiltert. |
| `iteration-log-list --id <iteration_id>` | Listet alle Log-Einträge einer Iteration chronologisch aufsteigend mit Zeitstempel, Run-Bezug (falls gesetzt) und Text (Ticket 67). `--json` liefert die rohen Items. |
| `backtest-config-list` | Listet alle Backtest-Configs. |
| `indicator-config-list [concept_id] [iteration_id]` | Listet alle Indicator-Configs, optional auf Konzept/Iteration gefiltert. |
| `result-list --run <id>` | Listet die Results eines Runs, optional nach Symbol/Timeframe gefiltert. |
| `run-list --strategy <slug>` | Listet die Runs einer Strategie, nach Testset-Lauf gruppiert. |
| `testset-list` | Listet alle Testsets. |
| `leaderboard-list [testset_id]` | Listet die Leaderboard-Einträge, optional je Testset. |
| `strategy-config-list` | Listet alle Strategy-Configs (Legacy). |
| `symbol-list <exchange> <timeframe>` | Listet die verfügbaren Symbole je Exchange und Timeframe. |
| `symbol-correlation <exchange> <timeframe> --symbols A,B,C` | Misst die Korrelation der Tages-Log-Renditen zwischen Symbolen (je Paar Gesamtwert, Länge der Überlappung, rollierend Minimum/Median/Maximum) und weist die effektive Symbolzahl auf zwei Wegen aus — aus der mittleren Paarkorrelation und über die Eigenwerte. Optional `--start`, `--end`, `--window` (Default 90 Tage), `--min-overlap` (Default 30 Tage), `--json`. |
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
| `run-bestwerte --run <id>` | Zieht die vier festen Bestwerte eines Runs und markiert sie als roten Doku-Favorit (idempotent). Das gewonnene Kriterium wird am Result persistiert (`best_criteria_json`) und in der Results-Tabelle als Kürzel-Spalte „Bestwert" angezeigt (T/W/S/P, Langform im Hover). |
| `run-favorites-reset --run <id> [--doc] [--user]` | Setzt die Favoriten einer Run-Menge zurück (ohne Flag beide Sterne; `--doc` rot/Doku, `--user` gelb/persönlich). Selektoren wie `run-bestwerte`. |
| `run-favorites-list --run <id> [--doc] [--user]` | Gibt die markierten Favoriten-Results einer Run-Menge mit Kennzahlen und Parametern aus (reiner Read). Selektoren/Flags wie `run-favorites-reset`. |
| `vergleichstabelle --strategy <slug> [--save <pfad>]` | Iterations-Vergleichstabelle je Testset aus den roten Doku-Favoriten (Zeilen Symbol × Iteration, Spalten Spitze = Max Total Return und robuster Kern = Profitfaktor ≥ 30 Trades). Purge-fest, weil nur markierte Bestwerte gelesen werden; nur Testset-Läufe. `--save` schreibt zusätzlich eine eigenständige Markdown-Notiz (mit Frontmatter) an den Pfad. |
| `result-lookup --run <id> --params "k=w,…" [--tolerance <t> \| --tolerance-steps <N>] [--limit <n>] [--summary]` | Schlägt Results per Parameter-Werten nach (Subset, serverseitig). Ohne Toleranz exakter Lookup der einen Kombination; mit `--tolerance` alle Results je ±t um die Zielwerte (absolute Toleranz je Parameter, skalare Nachbarschaft); mit `--tolerance-steps` alle Results je ±N Raster-Schritte je Achse statt einer absoluten Toleranz (beide Flags schließen sich aus). `--summary` verdichtet die Nachbarschaft zum Plateau-Score (Median/Mittel/Streuung, Anteil profitabel, Bester/Schlechtester). |
| `result-query --run <id> --where "sharpe_ratio>=1.5,total_trades>=100" [--sort <metrik>] [--direction asc\|desc] [--limit <n>]` | Fragt Results mit kombinierten Metrik-Filtern ab (nur `>=`/`<=`, UND-verknüpft, serverseitig). Metriken: total_return_pct, win_rate_pct, sharpe_ratio, profit_factor, max_drawdown_pct, total_trades. |
| `kreuztest --from-run <A> --to-run <B> [--user] [--tolerance <t> \| --tolerance-steps <N>]` | Schlägt die roten Doku-Favoriten (Bestwerte) aus Run A in Run B nach und gibt eine Vergleichstabelle der Metriken aus (`--user` nimmt gelbe Sterne dazu). Toleranz-Flags wie bei `result-lookup` (schließen sich aus). |
| `kreuztest --from-testset-run <A> --to-testset-run <B> [--user] [--tolerance <t> \| --tolerance-steps <N>]` | Kreuz-Test über ganze Testset-Läufe: Runs werden per Symbol+Timeframe gepaart (BTC-Run zu BTC-Run usw.), je Paar eine Vergleichstabelle; Runs ohne Gegenstück werden ausgewiesen. **Achtung:** Bei mehreren Runs mit gleichem Symbol+Timeframe (z.B. eine Fold-Kette über Zeitfenster) trägt die Paarung nicht — je Schlüssel überlebt nur ein Paar, der Rest wird „OHNE PAAR" gemeldet (belegt 14.08.2026; Fold-Ketten-Auslesung kommt mit Roadmap Paket 7). |
| `combo-trace --params "k=w,…" --testset-run <id> [--tolerance <t>] [--limit <n>]` | Verfolgt eine Parameterkombination über eine Run-Menge (1:N) und listet je Run den Treffer mit Symbol/Timeframe und Kennzahlen; Runs ohne Treffer werden ausgewiesen. Selektoren wie `run-bestwerte` (`--run` \| `--strategy [--version]` \| `--iteration` \| `--testset-run`). |
| `befund --testset-run <testset_run_id>` | Liefert den jüngsten Befund dieses Testset-Laufs plus Gesamtzahl aller Befunde dieses Laufs (Ticket 77/A) — der direkte Anschluss an `testset-run-start`/`run-wait`, ohne den Umweg über `--iteration` und Ablesen der Befund-Nummer. |
| `befund --id <befund_id>` | Liefert einen einzelnen Befund per **Befund-ID** (NICHT die Testset-Lauf-Nummer): Kontext + Soll, fünf Ist-Gruppen, Deutung getrennt gekennzeichnet, leere Felder mit Grund (Ticket 56). `--id` und `--testset-run` schließen sich aus. |
| `befund --iteration <id>` | Befund-Historie einer Iteration, chronologisch (kein Sortieren/Filtern, kein Verdict). |

Die Lese-Werkzeuge `result-list`, `symbol-correlation`, `run-top-results`, `run-best`, `run-favorites-list`, `vergleichstabelle`, `result-lookup`, `result-query`, `kreuztest`, `combo-trace`, `iteration-log-list` und `befund` kennen zusätzlich das Flag **`--json`**: Ausgabe der rohen Items als JSON statt formatiertem Markdown — für Folge-Analysen, ohne Zahlen aus Text zurückzuparsen. Seit Ticket 77/C kombinierbar mit **`--out [datei]`**/**`--full`** (schließen sich aus, gleiche Semantik wie beim `api`-Verb): `--out` schreibt das vollständige JSON in eine Datei unter `<TEMP>/bt-toolbox-out/` statt auf stdout (Konsole nur Pfad + Zeichenzahl); ohne `--out`/`--full` bleibt die Konsolen-Ausgabe unverändert vollständig (kein 4000-Zeichen-Limit wie bei den GET-Werkzeugen unten — die `--json`-Ausgabe ist als maschinenlesbares, direkt parsebares JSON gedacht).

Die folgenden rohen GET-Werkzeuge kennen zusätzlich **`--out [datei]`**/**`--full`** gegen die 4000-Zeichen-Kappung (gleiche Semantik wie beim `api`-Verb, siehe „Generisch" unten; schließen sich gegenseitig aus):

| Werkzeug | macht |
|---|---|
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
| `iteration-log-add --id <iteration_id> --text "..." [--run <run_id>]` | Hängt einen Freitext-Eintrag ans append-only Denkprotokoll einer Iteration (Ticket 67) — warum ein Versuch unternommen wurde, was aus dem Ergebnis geschlossen wird. Kein Update-/Delete-Verb, Einträge sind unveränderlich. `--run` ist eine optionale lose Referenz (kein FK). |

### Starten — einen Lauf auslösen

| Werkzeug | macht |
|---|---|
| `backtest-run-start --backtest-config <id> --indicator-config <id> --iteration <id>` | Startet einen Backtest-Lauf über das Parameter-Raster. |
| `testset-run-start --testset <id> --iteration <id> --indicator-config <id>` | Startet einen Testset-Lauf (ein Run pro Config), Leaderboard nur bei aktiviertem Testset. |
| `walk-forward-start --result <id> --months <n>` | Startet eine Walk-Forward-Analyse auf Basis eines Results. |
| `playground-setup-compute` | Berechnet die Indikatoren eines Playground-Setups. |
| `playground-setup-run-backtest` | Startet einen vollen Backtest aus einem Playground-Setup. |
| `playground-run-backtest-lite` | Startet einen schnellen Lite-Backtest aus einem Playground-Setup (ohne DB). |

### Prüfen vor dem Start / Warten aufs Ende (Ticket 60)

| Werkzeug | macht |
|---|---|
| `preflight --iteration <id> --indicator-config <id> --backtest-config <id>` | Billiger Vorlauf auf EINER Kombination (Startwerte, kein DB-Schreiben): Entry-/Exit-Signalzahl + erster/letzter Signalzeitpunkt, NaN-Anteil je Indikator-Output, tatsächlicher Vorlauf, Kombinationszahl des vollen Rasters, grobe Laufzeit-Hochrechnung. Berichtet nur, startet und verhindert nichts. |
| `run-wait --run <id> [--timeout <s>]` | Pollt aktiv bis der Run `completed`/`failed` ist (Default-Timeout 1800s), dann Dauer, Result-Zahl, ggf. Fehlermeldung. Timeout meldet sich als Timeout, nicht als Fehlschlag. |
| `run-wait --testset-run <id> [--timeout <s>]` | Dasselbe für alle Runs eines Testset-Laufs. |

### Signifikanztest je Kandidat (Ticket 79)

Berichtet, filtert nicht: es gibt kein Bestanden-Feld und keine Sortierung nach p-Wert.

| Werkzeug | macht |
|---|---|
| `signifikanz-start --result <id> [--method permutation\|bootstrap] [--n <n>] [--seed <n>] [--metrics <a,b>] [--wait [--timeout <s>]]` | Startet einen Signifikanztest. `permutation` (Default, N=300) lässt die Strategie auf N synthetischen Preisreihen laufen und liefert je Metrik einen p-Wert; läuft als Hintergrund-Job und prüft sich vorher selbst (Referenzlauf auf der echten Reihe muss die Result-Kennzahlen reproduzieren, sonst sichtbarer Abbruch). `bootstrap` (Default 2000 Runden) resampelt die gespeicherten Trade-Renditen und liefert Konfidenzbänder — kein Nullmodell, deshalb kein p-Wert; rechnet direkt im Aufruf und bricht ohne Trades mit Hinweis auf den Recompute-Weg ab. `--wait` pollt bis `completed`/`failed` (Exit-Codes wie `run-wait`: 0 fertig, 2 Timeout). |
| `signifikanz --id <id>` | Ein Test: Methode, N, Seed und je Metrik echter Wert **plus** Null-Verteilungs-Kennwerte **plus** p-Wert nebeneinander — ein p-Wert erscheint nie ohne seine Null-Verteilung. `--json` für die rohen Daten. |
| `signifikanz-list --result <id>` | Test-Historie eines Results, chronologisch. |

### Walk-Forward-Fold-Kette (Ticket 82)

N-mal „auf einem Zeitfenster optimieren → Sieger einfrieren → auf dem nächsten, ungesehenen
Zeitfenster testen". Fold-Zahl, Fensterlängen und Auswahlkriterium stehen beim Start fest
(Vorregistrierung) und werden stur vollzogen; das Ergebnis ist ein nach Abschluss
unveränderliches Artefakt. Die Kette misst, sie urteilt nicht: kein Verdict, keine
Güte-Sortierung — und das Aggregat wird nie ohne seine Fold-Tabelle zitiert. Sie ist ein
**Messwerkzeug, kein Ertragsbringer**.

| Werkzeug | macht |
|---|---|
| `walk-forward-chain-start --run <anker-run-id> --folds <n> --oos-monate <m> [--is-monate <k>] --selection-metric <metrik> [--selection-direction max\|min] [--trade-floor <t>] [--metrics kern\|voll\|auto] [--timeout <s>]` | Fährt die komplette Kette im Vordergrund: Kette anlegen (Plan wird vorher gegen die vorhandenen OHLC-Daten geprüft — ein Fenster außerhalb der Abdeckung bricht ab, bevor ein Datensatz oder ein Lauf entsteht) → je Fold IS-Lauf, warten, Sieger nach dem vorregistrierten Kriterium wählen, OOS-Lauf, warten, Kapitalkurve nachrechnen, Fold anhängen → schließen. Fold 1 nutzt den Anker-Lauf selbst als IS-Lauf, wenn sein IS-Fenster exakt das Anker-Fenster ist (also ohne `--is-monate`). Ein Fold ohne Sieger (kein Kandidat über dem Trade-Floor) wird ausgewiesen, die Kette läuft weiter; bricht ein Lauf ab, schließt die Kette als `failed` mit Grund. Es entstehen nur Runs und Results, keine neuen Configs oder Testsets. Exit-Codes wie `run-wait`: 0 fertig, 1 Fehlschlag, 2 Timeout. |
| `walk-forward-chain --id <id>` | Liest eine Kette: Plan mit Kriterium, Fold-Tabelle mit IS-Wert **neben** OOS-Wert (die Degradation ist die Aussage), Sieger-Kopien, Gesamtblock und Methodenhinweis. Das Aggregat erscheint nie ohne die Fold-Tabelle. `--json` für die rohen Daten. |
| `walk-forward-chain-list [--iteration <id>]` | Ketten-Historie, chronologisch. Bewusst ohne Kennzahlen — die stehen nur zusammen mit ihrer Fold-Tabelle im Einzel-Read. |

### Analyse-Screenshot (Ticket 100)

| Werkzeug | macht |
|---|---|
| `analyse-screenshot --run <id> --x <param> --y <param> [--metric <kennzahl>] [--agg avg\|max] --out <pfad>` | Fotografiert die Analyse-Seite eines Runs serverseitig (Renderer-Container, Playwright) und schreibt das PNG unverändert an `--out` — ein absoluter Pfad wird wörtlich genommen, kein Zwischenschritt über den Temp-Ordner. Ohne `--metric`/`--agg` gelten die Sollwerte (Average, Total Return %). Scheitert die Route (Run ohne Results, ungültiger Achsenname, Renderer-Timeout), bricht das Verb mit dem Server-Fehlertext ab und schreibt keine Datei. Details: [`references/screenshot-standard.md`](../../.claude/skills/ds-strategie-session/references/screenshot-standard.md). |

### Ändern

| Werkzeug | macht |
|---|---|
| `concept-update --id <n> --file body.json` | Überschreibt ein Konzept mit dem vollen PUT-Body. |
| `iteration-update --id <n> --file body.json` | Überschreibt eine Iteration mit dem vollen PUT-Body. |
| `backtest-config-update --id <n> --file body.json` | Überschreibt eine Backtest-Config. |
| `indicator-config-update --id <n> --file body.json` | Überschreibt eine Indicator-Config (voller PUT-Body). |
| `indicator-config-set --id <n> [--concept <id> --iteration <id> --name … --description …]` | Teil-Update (PATCH): schreibt NUR die gesetzten Felder; `config_json`/`_stops` bleiben unangetastet. Kernfall: bestehende Config nachträglich einem Konzept/einer Iteration zuweisen. |
| `strategy-config-update --id <n> --file body.json` | Überschreibt eine Strategy-Config (Legacy). |
| `testset-update --id <n> --file body.json` | Überschreibt ein Testset. |
| `playground-setup-update --id <n> --file body.json` | Überschreibt ein Playground-Setup. |
| `indicator-config-generate-labels <id>` | Setzt Name und Beschreibung einer Indicator-Config serverseitig nach fester Notation (überschreibt beide komplett). |
| `indicator-config-labels --id <n> [--name-suffix … --desc-suffix … --save]` | Erzeugt die Standard-Notation (wie der Frontend-Button), hängt optional einen individuellen Zusatz an (`<Notation> — <Zusatz>`) und schreibt mit `--save` nur Name/Beschreibung zurück. Ohne `--save` nur Vorschau. |

### Gezielt bearbeiten — einen Teil ändern, ohne den ganzen Body

> Für den Alltagsfall „kopieren und einen Indikator/eine Regel/ein Feld ergänzen, entfernen oder ändern". Jedes Werkzeug holt das Objekt, ändert genau einen Teil und schreibt zurück — der Rest bleibt bit-genau. Kein kompletter `--file`-Body nötig (das ist nur `-update`). Laufzeit-Zuordnung (am Code belegt, `worker_tasks.py`): Indikatoren zum Backtest kommen aus der **IndicatorConfig** (`config_json`), Regeln aus der **Iteration** (`spec_json.rules`) — ein logik-wirksamer Indikator muss also in die Config (mit Range) UND die referenzierende Regel in die Iteration.

| Werkzeug | macht |
|---|---|
| `concept-set --id <n> [--name --slug --category --description --status]` | Ändert einzelne Konzept-Felder (partieller PUT). |
| `iteration-set --id <n> [--version-name --description --status]` | Ändert einzelne Iterations-Meta-Felder (partieller PUT). |
| `backtest-config-set --id <n> [--symbol --exchange --timeframe --start --end --ohlc-start --ohlc-end --size --size-type --init-cash --fees --name --description]` | Ändert einzelne Backtest-Config-Felder (GET→merge→voller PUT, da der Endpoint Voll-Replace ist). Stops liegen hier nicht. |
| `iteration-indicator-set --id <n> --name <key> --file frag.json [--replace]` | Schreibt einen Indikator nach `spec_json.indicators[key]` (`--file` = ein Indikator-Block). Neuer Key: einfügen. Vorhandener Key: **mergen** — nur die genannten Parameter ändern sich, der Rest (auch `tf`) bleibt bit-genau. `--replace` ersetzt den Block komplett. |
| `iteration-indicator-remove --id <n> --name <key>` | Entfernt einen Indikator aus `spec_json.indicators` (warnt, wenn Regeln ihn noch referenzieren). |
| `indicator-config-indicator-set --id <n> --name <key> --file frag.json [--replace]` | Wie oben, für `config_json[key]`; Param-Werte dürfen arange-Ranges (Multiparameter) sein. |
| `indicator-config-indicator-remove --id <n> --name <key>` | Entfernt einen Indikator aus `config_json` (`_stops` geschützt). |
| `indicator-config-stops-set --id <n> [--tp --sl --td --tsl --tsl-th --delta-format --time-delta-format]` | Setzt einzelne Werte in `config_json._stops`; Zahlen/`null` werden gecastet, Format-Felder bleiben String, nicht genannte Stops bleiben. |
| `iteration-condition-add --id <n> [--exit] [--block K \| --new-block [--short]] --file cond.json` | Hängt eine Regel-Bedingung an einen Block (ohne `--block` an Block 1, UND-verknüpft; `--new-block` erzeugt einen ODER-Block). |
| `iteration-condition-remove --id <n> [--exit] --block K [--index J \| --remove-block]` | Entfernt eine Bedingung (`--index J`, 1-basiert) oder den ganzen Block (`--remove-block`). |

### Löschen

| Werkzeug | macht |
|---|---|
| `<bereich>-delete <id>` | Löscht ein Objekt (concept/iteration zusätzlich mit `--force --delete_vault`). |
| `<bereich>-bulk-delete --ids 1,2,3` | Löscht mehrere Objekte auf einmal (indicator-config/result/run/playground-setup). |
| `result-delete-all [--run <id> \| --testset-run <id>]` | Löscht Results außer den geschützten Favoriten. Ohne Flag global (asynchroner Hintergrund-Job). Mit `--run`/`--testset-run` (schließen sich aus, Ticket 77/B) synchron auf die Menge eingegrenzt — Favoriten und fremde Objekte bleiben unberührt; die Antwort benennt `deleted_results`/`deleted_runs`/`deleted_run_ids` (kein globaler Orphan-Sweep, Ticket-75-Scope-Regel). |
| `run-delete-all` | Löscht alle Runs außer den geschützten Favoriten (ausschließlich global). |
| `knowledge-reset` | Setzt die Wissens-Datenbank zurück (leert den Index). |

### Aktionen — Markieren, Vault, Run-Steuerung

| Werkzeug | macht |
|---|---|
| `iteration-favorite <id> [--off]` | Setzt den persönlichen (gelben) Favoriten-Marker auf eine Iteration, idempotent; `--off` entfernt ihn gezielt, ebenso idempotent. |
| `iteration-doc-favorite <id> [--off]` | Setzt den Doku-Favoriten (roter Stern, geschützt) auf eine Iteration, idempotent; `--off` entfernt ihn gezielt. |
| `result-favorite <id> [--off]` | Setzt den persönlichen (gelben) Favoriten-Marker auf ein Result, idempotent; `--off` entfernt ihn gezielt. |
| `result-doc-favorite <id> [--off] [--criteria k1,k2]` | Setzt den Doku-Favoriten (roter Stern, geschützt) auf ein Result, idempotent; `--off` entfernt ihn gezielt (löscht dabei auch die gespeicherten Bestwert-Kriterien). |
| `concept-vault-create <id>` | Legt die Vault-Doku für ein Konzept an. |
| `iteration-vault-create <id>` | Legt die Vault-Doku für eine Iteration an. |
| `run-restart <id>` | Startet einen Run neu: löscht seine Results und rechnet von vorn. |
| `run-resume <id>` | Setzt einen abgebrochenen Run fort: behält die gespeicherten Chunks und rechnet ab dem ersten fehlenden weiter. |
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
| `api GET <pfad>` | Ruft eine beliebige API-Route lesend auf. Die Anzeige kappt bei 4000 Zeichen. |
| `api GET <pfad> --out [datei.json]` | Schreibt die vollständige Antwort ungekürzt in eine Datei unter `<TEMP>/bt-toolbox-out/` (Konsole: nur Pfad + Zeichenzahl). Ohne Wert: Auto-Name mit Zeitstempel. |
| `api GET <pfad> --full` | Gibt die vollständige Antwort ungekürzt auf der Konsole aus. |
| `api POST <pfad> --file body.json` | Ruft eine beliebige API-Route schreibend auf. |
| `api DELETE <pfad>` | Löscht über eine beliebige API-Route. |
| `out-clean [--all]` | Räumt den `--out`-Ordner auf: ohne Flag nur Abgelaufenes (>24 h), mit `--all` komplett. Passiert bei jedem `--out`-Schreiben ohnehin automatisch. |

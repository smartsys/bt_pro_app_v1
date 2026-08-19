# Analyse-Screenshots — Verfahren und Standard

> Referenz zum Skill `ds-strategie-session`. **Der Schritt ist keine Loop-Pflicht** — er läuft
> auf User-Auftrag bzw. wenn ein Auftrags-Prompt ihn ausdrücklich verlangt (SKILL.md Teil 2,
> „Analyse-Screenshots"; Phase 8 nennt die Begründung). Dann aber zeitkritisch: vor dem
> Ergebnis-Purge.

## Warum und wann

Die Analyse-Seite eines Runs (`$VBT_APP_BASE_URL/backtest/runs/<id>/analyse`) rechnet
ihre Heatmaps und die Gewinn/Verlust-Verteilung dynamisch aus dem **vollen** Result-Satz.
Nach dem Ergebnis-Purge bleiben nur die Favoriten — die Ansicht ist dann unwiederbringlich
leer. Deshalb: **Screenshots direkt nach `run-bestwerte`**, für jeden Run des Testset-Laufs,
solange die Results vollständig sind.

Vor dem ersten Bild kurz per SQL prüfen, dass der Run überhaupt noch seinen Bestand hat —
ein leerer Run sieht auf dem Bild wie ein kaputter Lauf aus:

```bash
docker exec db_bt_pro_v1 psql -U vbt -d vbt -c \
  "SELECT run_id, count(*) FROM backtest_results WHERE run_id IN (781) GROUP BY run_id;"
```

## Hauptweg: Toolbox-Verb `analyse-screenshot` (Ticket 100)

Das Bild entsteht mit **einem** Toolbox-Aufruf, der das fertige PNG direkt an seinen
endgültigen Platz schreibt — kein Browser-Werkzeug, kein DOM-Wissen, kein blindes Warten:

```bash
python3 .claude/skills/ds-strategie-session/scripts/toolbox.py analyse-screenshot \
  --run 866 --x mom_timeperiod --y tsl_th \
  --out "$VAULT_ROOT/30_Trading/vbt/strategies/<slug>/iterations/<version>/img/run-866-fet-bull-2021.png"
```

Das Verb ruft ausschließlich die Route `GET /api/backtest/runs/<id>/analyse/screenshot`
(Renderer-Container mit langlebigem Chromium, wartet auf `window.__analyseReady` statt auf
eine feste Wartezeit) und schreibt die PNG-Antwort unverändert an `--out`. Ein absoluter
`--out`-Pfad wird wörtlich genommen — das Bild landet ohne Zwischenschritt am Zielort, es
gibt keinen Temp-Ordner-Umweg mehr. Scheitert die Route (Run ohne Results, ungültiger
Achsenname, Renderer-Timeout), bricht das Verb mit dem Server-Fehlertext ab und schreibt
**keine** Datei.

`--x`/`--y` sind Pflicht (Feldnamen wie auf der Seite: `<indikator>_<parameter>` für
Indikatoren, Stops ohne Präfix, z. B. `tsl_th`). Ohne `--metric`/`--agg` zieht die Route ihre
Sollwerte (siehe unten). Für den Zielkennzahl-Schuss desselben Runs zusätzlich mit
`--metric sharpe_ratio` (o. ä.) aufrufen — zwei Aufrufe, zwei Dateien.

## Sollwerte (serverseitig festgeschrieben, Ticket 100)

Die Route trägt diese Werte als Vorgaben im Code (nicht mehr als Prosa, die jeder Durchlauf
neu befolgen muss). Abweichen kann nur, wer sie ausdrücklich als Parameter setzt.

| Punkt | Wert |
|---|---|
| Seite | `/backtest/runs/<RUN_ID>/analyse`, Tab **Übersicht** (die 3D-Ansicht liegt in einem inaktiven Tab-Bereich und kommt nicht mit aufs Bild) |
| Fenster | mindestens 1920×1080, Vollseiten-Schuss (`full_page`), PNG |
| Metrik | **Total Return %** (`total_return_pct`) für den Referenzschuss; zusätzlicher Schuss mit der Zielkennzahl per `--metric`, siehe „Welche Bilder ein Raster braucht" |
| Aggregation | **beide** Heatmaps auf **Average** — der Seiten-Default ist `max`! |
| Slider | **beide** leer (kein Slider) |
| Achsen | Rollen-Konvention: **waagerecht (X) der Indikator-Parameter, senkrecht (Y) der Stop-Parameter** — über alle Iterationen konstant, auch wenn die konkreten Felder wechseln |

Average statt Max, weil die Doku **robuste Zonen** zeigen soll (Plateau-Denken der
Bestwert-Methodik) — Max zeigt überfittete Einzelpunkt-Nadeln.

Zur Achsen-Konvention: „ein Achsenpaar je Strategie einmal festlegen" hält bei wechselnden
Rastern nicht. Tragfähig ist die Rolle, nicht der Feldname. Sweept ein Raster zwei
Indikator-Parameter und keinen Stop, gilt ersatzweise: waagerecht der Parameter, um den die
Iteration geht, senkrecht der zweite.

## Welche Bilder ein Raster braucht

Die Kernregel „klein sweepen" erzeugt systematisch **kleine** Raster. Die Bildmenge richtet
sich deshalb nach der Zahl der gesweepten Achsen, nicht nach einer festen Vorgabe.

**Zwei Sweep-Achsen (Regelfall).** Es gibt nur ein Achsenpaar — `--x`/`--y` decken beide
Heatmaps gleichzeitig ab (die Route stellt `x2`/`y2` automatisch auf dieselben Werte, wenn
sie nicht abweichend gesetzt werden). Damit die zweite Kachel nicht bloß die erste
wiederholt, entsteht ein **zweiter Vollseiten-Schuss** mit der **Zielkennzahl des Auftrags**
(`--metric <primary_metric>`) — abzulesen aus `goal_json.primary_metric` des Konzepts:

```bash
docker exec db_bt_pro_v1 psql -U vbt -d vbt -t -c \
  "SELECT goal_json->>'primary_metric' FROM strategy_concepts WHERE id=<CONCEPT_ID>;"
```

Der standardkonforme Total-Return-Schuss (Aufruf ohne `--metric`) bleibt unverändert daneben
liegen — die Vergleichbarkeit über Iterationen ist nicht angetastet, es kommt nur etwas dazu.
Grund: Die Entscheidung über eine Iteration fällt auf der Zielkennzahl; ein Bild, das sie gar
nicht zeigt, dokumentiert die Entscheidung nicht. (Belegt am Kill von Iteration 4 des
Auftrags `bb-squeeze`: in der Total-Return-Ansicht von Lauf 697 war das Sharpe-Plateau nicht
ablesbar.) Die Metrik gilt seitenweit für beide Heatmaps; eine Metrik je Heatmap gibt es im
Frontend nicht.

**Eine Sweep-Achse.** Es gibt keine Heatmap-Geometrie. `--x` = die gesweepte Achse, `--y` =
ein konstanter Parameter. Die Aussage tragen dort Verteilung und Top-Tabelle, die Heatmap ist
nur die Einordnung. Auch hier beide Schüsse (Total Return und Zielkennzahl).

**Gezippte Stop-Sweeps.** Zwei Stop-Achsen (z. B. `tsl_th` und `tsl_stop`) werden
serverseitig **gezippt statt gekreuzt**. Ein Trailing-Feld ist deshalb nur als **mehrere
Läufe mit je fester Schwelle** messbar — jeder Lauf ist einachsig und bekommt seinen eigenen
Satz Bilder. Diese Bilder werden **nur zusammen** gelesen: erst die Reihe ergibt das
Plateau. In der Iterations-Notiz entsprechend als Gruppe einbetten und die feste Schwelle je
Bild benennen.

## Ablage im Vault

```
$VAULT_ROOT/30_Trading/vbt/strategies/<slug>/iterations/<version>/img/run-<id>-<symbol>-<fenster>.png
$VAULT_ROOT/30_Trading/vbt/strategies/<slug>/iterations/<version>/img/run-<id>-<symbol>-<fenster>-<metrik>.png
```

- `<version>` = blanke Integer-Zahl (wie der Iterations-Ordner, kein `v`-Präfix).
- `<symbol>` kurz und klein (bnb, btc, doge, fet), `<fenster>` z. B. `bull-2021`, `baer-2223`.
- `<metrik>` nur beim Zielkennzahl-Schuss, kurz und klein (`sharpe`, `pf`, `calmar`).
- Kebab-case, keine Großbuchstaben.
- Einbettung in der Iter-Note relativ: `![](img/run-233-fet-bull-2021.png)`.

Dieses Namensschema ist die Quelle für den `--out`-Wert des Toolbox-Verbs — das Verb selbst
kennt weder Vault noch Namensregel, es nimmt `--out` wörtlich entgegen.

## Verifikation

Der Erfolgsmeldung des Verbs nicht blind glauben: mindestens ein PNG selbst öffnen (Read)
und prüfen, dass die Seite vollständig gezeichnet ist, **beide Aggregations-Auswahlen auf
Average** stehen, **beide Slider auf „— keiner —"** und die Metrik-Beschriftung über den
Heatmaps die erwartete Kennzahl nennt.

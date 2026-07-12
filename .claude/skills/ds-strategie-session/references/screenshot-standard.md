# Analyse-Screenshots — Standard und Subagent-Prompt

> Referenz für Pfad B des Skills `ds-strategie-session`. Wann dieser Schritt fällig ist,
> steht in SKILL.md („Direkt nach den Bestwerten — Analyse-Screenshots").

## Warum und wann

Die Analyse-Seite eines Runs (`$VBT_APP_BASE_URL/backtest/runs/<id>/analyse`) rechnet
ihre Heatmaps und die Gewinn/Verlust-Verteilung dynamisch aus dem **vollen** Result-Satz.
Nach dem Ergebnis-Purge bleiben nur die Favoriten — die Ansicht ist dann unwiederbringlich
leer. Deshalb: **Screenshots direkt nach `run-bestwerte`**, für jeden Run des Testset-Laufs,
solange die Results vollständig sind.

## Der Standard (nicht abweichen — sonst sind Iterationen nicht vergleichbar)

| Punkt | Wert |
|---|---|
| Seite | `/backtest/runs/<RUN_ID>/analyse`, Tab **Übersicht** |
| Fenster | Browser **maximieren** (maximale Fenstergröße, per resize_page auf die volle Bildschirmauflösung — mindestens 1920×1080); Vollseiten-Screenshot (fullPage), PNG |
| Metrik | **Total Return %** (Seiten-Default, nichts umschalten) |
| Aggregation | **beide** Heatmaps auf **Average** stellen (`#heatmap-agg`, `#heatmap2-agg`) — der Seiten-Default ist Max! |
| Achsenpaare | pro Strategie **einmal festlegen und über alle Iterationen konstant halten**. VWMA: Heatmap 1 `#heatmap-x`=fast_sma_length, `#heatmap-y`=fast_sma_multiplier · Heatmap 2 `#heatmap2-x`=vwma_length, `#heatmap2-y`=vwma_below_pct |
| Slider | unangetastet („— keiner —") |

Average statt Max, weil die Doku **robuste Zonen** zeigen soll (Plateau-Denken der
Bestwert-Methodik) — Max zeigt überfittete Einzelpunkt-Nadeln.

## Ablage im Vault

```
$VAULT_ROOT/30_Trading/strategies/<slug>/iterations/<version>/img/run-<id>-<symbol>-<fenster>.png
```

- `<version>` = blanke Integer-Zahl (wie der Iterations-Ordner, kein `v`-Präfix).
- `<symbol>` kurz und klein (bnb, btc, doge, fet), `<fenster>` z. B. `bull-2021`, `baer-2223`.
- Kebab-case, keine Großbuchstaben.
- Einbettung in der Iter-Note relativ: `![](img/run-233-fet-bull-2021.png)`.

## Delegation an einen Subagenten (einfaches Modell, z. B. Haiku)

Die Arbeit ist rein mechanisch — per Agent-Tool mit `model: haiku` delegieren.
Bewährter Prompt (Run-Liste und Pfade einsetzen; `<IMG_DIR>` = aufgelöster
`img/`-Pfad der Iteration):

```text
Du machst standardisierte Screenshots von Analyse-Seiten der BT Pro App.
Browser-Steuerung AUSSCHLIESSLICH über die chrome-devtools-MCP-Tools (per ToolSearch
laden: new_page, navigate_page, resize_page, wait_for, take_screenshot, close_page).
Auf den Seiten nichts anklicken außer den unten genannten Dropdowns.

Vorbereitung: mkdir -p <IMG_DIR>; Browser-Seite öffnen und das Fenster MAXIMIEREN
(resize_page auf die volle Bildschirmauflösung, mindestens 1920×1080).

Für JEDE Zeile der Liste (RUN_ID → Zieldatei):
1. navigate_page auf <BASE_URL>/backtest/runs/<RUN_ID>/analyse; warten bis die
   Heatmap-Zellen sichtbar sind (große Runs mit >100k Results: bis 60 s Geduld).
2. Diese Dropdowns setzen (per fill):
   #heatmap-x → <ACHSE_1A> · #heatmap-y → <ACHSE_1B> · #heatmap-agg → Average
   #heatmap2-x → <ACHSE_2A> · #heatmap2-y → <ACHSE_2B> · #heatmap2-agg → Average
3. Warten bis beide Heatmaps neu gezeichnet sind (Daten werden nachgeladen).
4. Vollseiten-Screenshot (fullPage, PNG) mit der filePath-Option direkt auf den
   Zieldateipfad speichern.

Liste:
<RUN_ID → IMG_DIR/run-<id>-<symbol>-<fenster>.png, eine Zeile je Run>

Abschluss: per Bash prüfen, dass alle PNGs existieren und > 100 KB sind (sonst mit
längerer Wartezeit wiederholen); ALLE geöffneten Browser-Seiten schließen (close_page).
Rückgabe: kompakte Liste Run-ID → Datei → Größe plus eventuelle Fehlschläge.
Keine Bilder in die Antwort einbetten.
```

**Bekannte Stolpersteine (in den Prompt aufnehmen bzw. danach prüfen):**

- Das Screenshot-Tool kann nur innerhalb der Workspace-Roots schreiben, nicht direkt
  in den Vault. Lösung: mit `filePath` in einen Temp-Ordner **außerhalb des Repos**
  speichern (Session-Scratchpad; zur Not `/tmp`), dann per Bash in den Vault
  verschieben. Temp-Ordner im **Projektbaum** vermeiden — der Auto-Commit-Hook
  committet ihn sonst als WIP; falls doch passiert: Ordner löschen, die Deletion geht
  im nächsten Changelog-Squash auf.
- Der letzte Browser-Tab lässt sich per Tool nicht schließen — der Chrome-Prozess
  bleibt stehen und hält den Profil-Lock. Nach dem Subagenten-Lauf prüfen und ggf.
  eng gemustert beenden: `pkill -f chrome-profile`.

## Verifikation durch den Delegierenden

Der Erfolgsmeldung des Subagenten nicht blind glauben: mindestens ein PNG selbst
öffnen (Read) und prüfen, dass die Seite vollständig gerendert ist und **beide
Aggregations-Dropdowns auf Average** stehen.

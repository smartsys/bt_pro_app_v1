# Indikatoren — Vollständige Referenz

> Wie Indikatoren im Projekt definiert, klassifiziert, angezeigt, verarbeitet und gespeichert werden. Diese Datei ist die verbindliche Referenz. Bei Arbeit an Indikatoren (Chart-Playground, Spec-Runner, Configs) zuerst hier lesen. Stand: 2026-06-23.
>
> **Multi-Combo-Backtests, Cross-Produkt der Parameter, Ergebnis-Speicherung und der Chart-Recompute** sind in den Abschnitten **6.5–6.9** dokumentiert (Deep-Dive vom 2026-06-01). Wer einen Backtest mit Multiparameter-Läufen über mehrere Indikatoren debuggt oder warum ein Chart keine Equity/Indikatoren zeigt, liest dort.

---

## 0. Kernprinzipien (Invarianten — nicht verletzen)

Diese Regeln sind aus konkreten Bugs entstanden. Wer sie bricht, baut dieselben Fehler erneut.

1. **Ein Config-Eintrag ist ein flaches Dict.** Form: `{ "<name>": { "indicator": "...", "tf": "...", "<feld>": <wert>, ... } }`. Es gibt keine verschachtelten `inputs`/`params`-Sektionen in der gespeicherten Form — alles liegt flach nebeneinander.

2. **Nur `indicator` und `tf` sind Strukturfelder** mit eigenem Widget. `indicator` = Bibliotheks-ID (read-only Anzeige), `tf` = Timeframe-Override (Dropdown). **Alles andere ist ein normales Datenfeld** und wird angezeigt.

3. **Kein Feld wird je versteckt.** Es gibt keine "Ausblende-Liste". Jeder Key im Eintrag bekommt garantiert ein Widget. (Historischer Bug: `enabled` lag in einer META-Filterliste und verschwand aus der Anzeige.)

4. **Defaults nie aus fehlenden Daten erfinden.** Das Muster `X !== false` / `.get('x', True)` als "wenn nicht explizit false, dann true" erzeugt Phantomwerte, die in der Config gar nicht stehen. Ein Wert kommt aus den Daten — oder das Feld existiert nicht. (Historischer Bug: `enabled` wurde als `true` angezeigt, obwohl es in der Config nicht existierte.)

5. **Eine Klassifizierung, ein Renderer.** Im Frontend entscheidet genau eine Funktion (`fieldKind`), was ein Feld ist, und genau eine (`renderField`), wie es gezeichnet wird. Keine parallelen Sonderfall-Pfade.

6. **Die `indicator`-ID trägt immer den Bibliotheks-Prefix** (`custom:`, `vbt:`, `talib:`, ...). Kurz-IDs ohne Prefix sind Alt-Daten und mehrdeutig (mehrere Bibliotheken können denselben Namen haben).

7. **Quelle der Wahrheit für inputs/params/outputs ist der Katalog**, der aus der VBT-`IndicatorFactory` gebaut wird (`factory.input_names` / `param_names` / `output_names`). Nichts davon ist im Frontend hartcodiert.

---

## 1. Das Datenmodell — der flache Config-Eintrag

Ein Indikator-Eintrag (in `config_json` / `indicators_config_json`):

```json
{
  "fast_sma": {
    "indicator": "custom:dwsFastSMA",
    "tf": "4h",
    "source": "Close",
    "length": { "type": "arange", "start": 12, "stop": 13, "step": 1, "dtype": "int64" },
    "multiplier": { "type": "arange", "start": 1, "stop": 1.01, "step": 0.1, "dtype": "float64" }
  }
}
```

- **Key** (`"fast_sma"`) = eindeutiger Slug-Name im Setup (frei umbenennbar). Wird in Regeln und Input-Referenzen verwendet.
- `indicator` = aufgelöste Katalog-ID inkl. Bibliotheks-Prefix.
- `tf` = Rechen-Timeframe des Indikators (`null`/fehlt = gleicher TF wie der Chart/Run). Ein gesetzter, **gröberer** tf lässt den Indikator nativ auf `vbt.Data.resample(tf)` rechnen und holt die Outputs look-ahead-sicher (`realign_closing`) aufs Basis-Raster zurück — **sowohl im Chart-Preview als auch im echten Run** (seit Paket B identischer Pfad, Preview == Lauf). Ein **feinerer** tf (Downsampling) wird abgewiesen.
- Alle weiteren Keys sind entweder **Inputs** (Wert = OHLCV-Spalte oder Referenz `indicator:<name>:<output>`) oder **Parameter** (Skalar oder Multiparameter-Lauf-Range-Objekt). Ob ein Key Input oder Parameter ist, ergibt sich aus dem Katalog (`factory.input_names`), nicht aus der gespeicherten Form.

### Wertformen eines Feldes
- **Skalar**: Zahl (`10`) oder String (`"1h"`).
- **Multiparameter-Lauf-Range** (Objekt): `{ "type": "arange", "start": N, "stop": N, "step": N, "dtype": "int64"|"float64" }`. Anzahl Werte = `ceil((stop - start) / step)`, mind. 1.
- **Boolean**: `true`/`false`.

---

## 2. Der Katalog — `GET /api/chart-playground/indicators`

Gebaut in `services/api/routes/api_chart_playground.py` → `_build_catalog()` (`@lru_cache(maxsize=1)`, einmal pro Prozess).

**Eintrag pro Indikator (exakt):**
```python
{
  'id':        full_id,          # z.B. 'vbt:SUPERTREND', 'custom:dwsFastSMA', 'talib:SMA'
  'name':      name,             # Teil nach ':'  (z.B. 'SUPERTREND')
  'group':     grp,              # Teil vor ':'   (z.B. 'vbt', 'talib', 'custom')
  'inputs':    [...],            # = factory.input_names
  'params':    [{'name': p, 'default': <wert|None>}, ...],   # = factory.param_names + Defaults
  'outputs':   [...],            # = factory.output_names
  'plot_type': 'overlay'|'subplot',   # _guess_plot_type()
}
```

- **VBT-Indikatoren**: aus `vbt.IF.list_indicators()`. Prefix vor `:` wird zur Gruppe; ohne `:` → Gruppe `vbt`.
- **Custom-Indikatoren**: aus `user_data/utils/indicators/custom.py`, Gruppe `custom`, ID `custom:<name>`. Erkennung per Duck-Typing (Attribute `input_names`, `param_names`, `output_names`, `run`).
- **Defaults** (`_factory_param_defaults`): 3 Fallback-Stufen — `run()`-Signatur, `apply_func`-Signatur (namentlich), positionsbasiert ab Index `len(input_names)`. `_sanitize_default` reduziert auf `int|float|str|bool|None`.
- **Sortierung**: Gruppe `custom` zuerst, dann übrige Gruppen alphabetisch; innerhalb alphabetisch nach `name`.
- **`plot_type`** (`_guess_plot_type`): **Namens-Heuristik**, kein gespeichertes Feld. Der Name-Suffix wird gegen `OVERLAY_KEYWORDS` (Preis-Niveau-Indikatoren wie MA/Bands/Trendlinien → `overlay`) bzw. `SUBPLOT_KEYWORDS` (Oszillatoren wie RSI/Stoch/SMI → `subplot`) gematcht. **Kein Treffer → Default `subplot`.** Folge: ein neuer **preisskalierter** Custom-Indikator, dessen Name kein Overlay-Keyword trifft, landet **stumm im eigenen Panel** statt über dem Chart — dann ein Keyword in `OVERLAY_KEYWORDS` ergänzen (so geschehen für `trendline`). Im Setup überschreibt `ui_state.plot_type ∈ {overlay, subplot, background}` den Typ pro Indikator (ein **unbekannter** Wert wie `"line"` fällt im Frontend ebenfalls auf subplot).

**Beispiele (verifiziert):**
| Katalog-ID | inputs | params | outputs |
|---|---|---|---|
| `vbt:SUPERTREND` | `high, low, close` | `period, multiplier` | `trend, direction, long, short` |
| `custom:dwsFastSMA` | `source` | `length, multiplier` | `result` |

---

## 3. Custom-Indikatoren — `user_data/utils/indicators/custom.py`

Muster: `vbt.IF(class_name=..., input_names=[...], param_names=[...], output_names=[...]).with_apply_func(func, takes_1d=True)`.

| Name | input_names | param_names | output_names | Zweck |
|---|---|---|---|---|
| `dwsFastSMA` | `source` | `length, multiplier` | `result` | Gewichtetes SMA (WSMA) |
| `dwsAssetDD` | `source` | `window` | `result` | Drawdown vom rollenden Peak |
| `dwsVolumeRatio` | `volume` | `window` | `result` | Volumen / rollender Durchschnitt |
| `dwsCrossover` | `series_a, series_b` | (keine) | `result` | Bidirektionaler Crossover (Pine `ta.cross`), 1.0/0.0 |
| `dwsSMI` | `high, low, close` | `k_length, smooth1, smooth2, signal` | `smi, signal` | Stochastic Momentum Index (Blau, Skala ±100, TradingView-treu) |
| `dwsTrendlineTouch` | `high, low, close` | `up_th, down_th, atr_length, touch_tol_atr, break_tol_atr, dev_max_atr, min_touch, max_touch` | `short_line, long_line, short_signal, long_signal` | TAP: 3./4. Trendlinien-Berührung mit Abpraller (Pivot-basiert) |

Neue Custom-Indikatoren hier als `IndicatorFactory` ergänzen — sie erscheinen automatisch im Katalog (Gruppe `custom`).

### 3.1 Benannte/Standard-Indikatoren originalgetreu nachbauen

Aus dem `dwsSMI`-Build (TAP-Methode) — gilt für jeden „benannten" Indikator:

- **Lib-Variante vor dem Wrappen verifizieren.** Gleicher Name heißt nicht gleiche Formel: `pandas_ta.smi` ist der **SMI Ergodic** (TSI-basiert, close-only, Nulldurchgang), **nicht** der Blau **Stochastic Momentum Index** (High/Low-Range, ±40 überkauft/überverkauft). `dwsSMI` baut Letzteren nach.
- **TradingView-Bit-Treue = Pine-`ta.ema`.** TV `ta.ema` seedet den ersten Wert mit dem **ersten Quellwert**, `talib.EMA` mit **SMA(length)** → Abweichung in der Warmup-Phase. Für Bit-Identität eine eigene Pine-EMA nutzen (`_pine_ema_nb` in `custom.py`: `alpha=2/(length+1)`, Seed=erster Wert, NaN-Skip). `dwsSMI` ist damit gegen die Pine-Formel bit-identisch (verifiziert auf SOL/USDT 4h, Diff 0.0 über alle Bars, inkl. erstem Wert).
- **Container-Check vor neuer Dependency.** Eine `requirements.txt`-Lib kann im laufenden Container fehlen (`pandas-ta` steht drin, ist aber nicht installiert). Im Zweifel talib-Eigenbau statt neuer Runtime-Dependency — Verhalten in der Lauf-Umgebung prüfen (`docker compose ... exec worker python -c "import x"`).

---

## 4. ID-Auflösung & Bibliotheks-Prefixe — `user_data/strategies/generic/registry.py`

`resolve_indicator_factory(type_id)` — eine Stelle für Playground und Spec-Runner (Playground delegiert via `_extract_factory`).

| ID-Form | Auflösung |
|---|---|
| `custom:dwsFastSMA` | `_load_custom('dwsFastSMA')` aus `user_data.utils.indicators.custom` |
| `vbt:SUPERTREND` | `vbt.indicator('vbt:SUPERTREND')` |
| `talib:SMA` | `vbt.indicator('talib:SMA')` |
| `dwsFastSMA` (ohne `:`) | erst Custom-Lookup; wenn nicht gefunden → `vbt.indicator(...)` |

Der Resolver akzeptiert beide Formen (mit/ohne Prefix), die prefixte ist die robuste und wird überall bevorzugt. Frontend-Lookup `findIndicatorMeta` matcht zuerst exakt, dann case-insensitiv gegen den ID-Suffix (Teil nach letztem `:`) — so trifft die Alt-Kurz-ID `supertrend` noch auf `vbt:SUPERTREND`.

---

## 5. Frontend-Lebenszyklus (Chart-Playground)

Datei: `services/frontend/templates/chart_playground/index.html`.

### 5.1 State pro Indikator (`state.indicators[]`)
`client_id`, `name`, `id` (= aufgelöste Katalog-ID), `display_name`, `paramsMeta` (Katalog-Params), `params` (eingestellte Werte), `inputNames` (Katalog-Inputs), `outputNames`, `inputs` (Key→Quelle), `timeframe`, `color`, `plot_type`, `chartVisible`, `outputs` (Berechnungsergebnis, initial `null`).

Erzeugt an 3 Stellen: `addIndicator` (Picker), `cpIndCfgSelect`-Handler (Indikator-Config laden), `applySetupConfig` (Setup laden). **Kein `enabled`-Feld mehr.** `chartVisible` ist rein die Chart-Sichtbarkeit (kein Strategie-Konzept).

### 5.2 Die EINE Klassifizierung — `fieldKind`
```js
function fieldKind(key, meta) {
  if (key === 'indicator') return 'identity';
  if (key === 'tf') return 'timeframe';
  const inputs = (meta && meta.inputs) ? meta.inputs : [];
  if (inputs.includes(key)) return 'input';
  return 'value';
}
```
Wird in beiden Lade-Pfaden genutzt: `identity`/`timeframe` → eigene State-Slots (`id`/`timeframe`), `input` → `inputs`-Topf, `value` → `params`-Topf. **Nichts wird verworfen.**

### 5.3 Der EINE Renderer — `renderField` + `renderValueWidget`
`renderField(ind, key, kind, ctx)` zeichnet je `kind`:
- `identity` → read-only Textfeld mit `ind.display_name`.
- `timeframe` → TF-Dropdown (nur TFs >= Chart-TF).
- `input` → Quellen-Select (OHLCV + `indicator:<name>:<out>`-Referenzen anderer Indikatoren).
- `value` → `renderValueWidget` nach Wertform:
  - Boolean → Schiebeschalter (`data-parambool`).
  - Range-Objekt → drei Felder start/stop/step (`data-param` + `data-range`).
  - Skalar (Zahl/String) → ein Einzelfeld (`data-paramscalar` + `data-numeric`).

Render-Reihenfolge im Panel: Name, `identity`, Inputs (`ind.inputNames`), Wertfelder (Union aus `paramsMeta`-Namen + Keys in `ind.params`), `tf`. Danach rechts: `chartVisible`-Schalter, Farbe, Plot-Typ, Entfernen.

Hilfsfunktionen: `paramRangeFields(value, dflt)` (zerlegt Wert für Anzeige), `buildParamValue(start, stop, step, prev)` (baut Skalar oder Range-Objekt zurück, erhält `dtype`).

### 5.4 Laden
- **Indikator-Config** (`cpIndCfgSelect`): `GET /api/config/indicator` (Liste gecached in `state.indicatorConfigs`), beim Wählen wird `cfg.config_json` zerlegt. `state.currentIndCfgId` gemerkt (für Überschreiben). `id` = `meta.id || indId` (Prefix wird verlustfrei übernommen).
- **Setup** (`applySetupConfig`): nimmt `backtest_config_json` / `indicators_config_json` / `strategy_config_json` / `ui_state_json`. UI-Felder (Farbe, plot_type, chart_visible) kommen aus `ui_state_json.indicators[name]`.

### 5.5 Speichern
- **`collectIndicatorConfigJson()`** → flaches `{name: entry}` ohne UI-Felder. `entry = { indicator: i.id, tf: i.timeframe||null, ...i.inputs, ...i.params }`. `META_KEYS = ['indicator','tf']` nur als Spread-Schutz (verhindert Doppelschreibung), keine Ausblende-Liste.
- **`saveIndicatorConfig(forceNew)`**: bei geladener Config (`currentIndCfgId`) `PUT /api/config/indicator/{id}` (behält name/description/concept/iteration); sonst Modal → `POST /api/config/indicator` (neu, **ohne** Konzept/Iterations-Zuordnung). Inline-Status neben den Buttons (`cpIndCfgStatus`).
- **`collectSetupConfig()`** → vier `*_json`-Felder; `saveSetup`/`saveSetupConfirm` gegen `/api/chart-playground/setups`.

### 5.6 Compute-Payload (`POST /api/chart-playground/compute`)
Pro Indikator gesendet: `{ id, name, client_id, params, inputs, timeframe }`. Input-Fallback im Frontend: `INPUT_DEFAULTS = { source:'close', close:'close', open:'open', high:'high', low:'low', volume:'volume' }`.

### 5.7 Regel-Referenzen
`collectRefOptions` bietet Indikator-Outputs als `indicator:<name>:<output>` an (Label `name.output`; Fallback-Output `result`). `renameIndicator` zieht beim Umbenennen alle `indicator:<oldName>:`-Referenzen in anderen Inputs **und** in den Rules (`lhs`/`rhs`) nach.

---

## 6. Backend-Verarbeitung

### 6.1 Playground-Compute (Einzelkombi) — `api_chart_playground.py`
- Topologische Sortierung nach `indicator:<name>:<out>`-Abhängigkeiten (Indikatoren, die andere referenzieren, werden später berechnet).
- Input-Mapping: `spec.inputs[name]` → OHLCV-Spalte (`default_input_source`: source/close→Close, open→Open, ...) oder Output eines vorher berechneten Indikators. Bei gesetztem `tf`: nativ über den **geteilten Helper** `generic/tf_resample.py` (`resampled_ohlc`/`realign_to_index`/`validate_tf`) — exakt derselbe Code wie der echte Runner (`build_indicators`), daher Preview == Lauf. OHLCV-Inputs aus `vbt.Data.resample(tf)` (Open=first/High=max/Low=min/Close=last/Volume=sum); Indikator-Outputs (Chaining) und Rück-Realign aufs Basis-Raster über `realign_closing` (look-ahead-sicher, last-in-bucket).
- **`_coerce_param`** reduziert Multiparameter-Lauf-Range-Werte auf Einzelwerte (Playground = keine Kombinatorik): Liste → erstes Element; Range-Dict → `start` (bzw. `value`); leere/`None`-Params werden entfernt, damit Factory-Defaults greifen; `timeframe` wird aus den Params entfernt.

### 6.2 Multiparameter-Lauf/Backtest (generic engine) — `user_data/strategies/generic/indicator_factory.py`
- `build_indicators(indicators_json, ohlc_data)`: `_topological_order` (Kahn), dann je Indikator `resolve_indicator_factory` + Inputs/Params auflösen + `factory.run(..., param_product=True)` (volle Kombinatorik).
- **Param-Extraktion**: jeder Key, der **nicht** in `_META_KEYS = {'indicator','tf','enabled'}` und **nicht** in `factory.input_names` steht, ist ein Parameter. Range-Dicts werden via `convert_range_json_numpy_arrays` zu Arrays expandiert; Skalare zu `[value]`.
- **Input-Auflösung**: Defaults `source→close`, sonst Input-Name; Referenz `indicator:<id>:<output>` → Output des vorherigen Indikators.

### 6.3 Spec-Runner — `user_data/strategies/generic/spec_runner.py`
`_validate_rule_references` prüft vor dem Run alle `indicator:<id>:...`-Referenzen in `rules_json`: fehlende IDs → Fehler; deaktivierte (`enabled: false`) → Fehler. Danach `evaluate_rules(...)` mit dem `indicators`-Dict.

### 6.4 Kombinationszählung — `user_data/utils/database/repository.py:283` (`_count_combinations`)
Kreuzprodukt aller `arange`-Felder über alle Indikatoren; `ceil((stop-start)/step)` pro Range, mind. 1. Skalare zählen nicht.

### 6.5 Multi-Combo: Spalten-Struktur und Chaining

Jeder Indikator wird **unabhängig** mit `factory.run(..., param_product=True)` gebaut (`indicator_factory.py`, `build_indicators`). Ergebnis ist ein DataFrame, dessen **Columns ein MultiIndex** sind — ein Level pro Parameter.

- **Level-Namen** = `<vbt-Klassenname kleingeschrieben>_<param>`, also `dwsfastsma_length`, `dwsfastsma_multiplier`, `supertrend_period`, `supertrend_multiplier`. Der Klassenname ist der Teil **nach** `custom:`/`vbt:` (vbt prefixt die Param-Level mit dem Klassennamen, nicht mit der vollen Typ-ID).
- **Carrier-Level `symbol`**: `vbt.Data` hängt jedem Indikator-Output ein zusätzliches Column-Level `symbol` an (auch bei Single-Symbol, dann konstant z.B. `FETUSDT`).
- **Chaining**: Ist ein Input eine Referenz `indicator:<id>:<out>` (z.B. ein nachgelagerter Indikator `B` mit `source = indicator:fast_sma:result`), erbt `B` die **Param-Level des Vorgängers**. Beispiel: die Columns von `B` tragen neben den eigenen Param-Leveln zusätzlich `dwsfastsma_length, dwsfastsma_multiplier` und `symbol`. Die topologische Sortierung (`_topological_order`, Kahn) stellt sicher, dass Abhängigkeiten zuerst gebaut werden.

Damit hat jeder Indikator-Block **disjunkte** Param-Level (außer dem gemeinsamen `symbol`): die Kette aus `fast_sma`+`B` und `supertrend` teilen kein Param-Level.

### 6.6 Cross-Produkt der Param-Level — `rules_engine.py`

Die Entry-/Exit-Regeln verknüpfen Conditions, deren Operanden aus verschiedenen Indikator-Blöcken stammen. Zwei Broadcast-Stellen:

- `_evaluate_condition` — broadcastet `lhs`/`rhs` einer einzelnen Condition.
- `_evaluate_rule_group` — broadcastet alle Condition-**Ergebnisse** einer Gruppe vor dem AND/OR.

**Kernproblem:** `vbt.broadcast` **alignt** Indizes nur — es bildet **kein** Kartesisches Produkt. Bei disjunkten Param-Leveln mit Länge > 1 (z.B. Block `B` mit 2125 Spalten vs. `supertrend`-Block mit 15 Spalten) gibt es keine gemeinsame Spalten-Achse → VBT bricht mit `ValueError: Cannot align indexes` ab. Das gemeinsame, konstante `symbol`-Level reicht nicht zum Alignen (es ist nicht eindeutig → genau dieser Branch in `align_index_to` schlägt zu).

**Lösung (`_combine_broadcast`):**
1. Zuerst normales `vbt.broadcast` versuchen — deckt rein alignbare Fälle ab (inkl. Teilmengen, z.B. fast_sma ⊂ `B`, weil die fast_sma-Level eine Teilmenge der `B`-Level sind).
2. Schlägt das fehl: **Ziel-Spalten-Index** als Kartesisches Produkt der disjunkten Param-Level via **`vbt.base.indexes.cross_indexes`** bauen, dann jeden Operanden per `vbt.broadcast(..., columns_from=target, align_index=False)` dorthin expandieren.
3. Gemeinsame Carrier-Level (`symbol`) bleiben **aligned** (werden nicht gekreuzt); Teilmengen-Operanden werden vor dem Kreuzen herausgefaltet (sonst doppelte Level).

`_broadcast_explained` umschließt das und liefert bei einem echten Fehler eine **aussagekräftige Meldung** mit Operanden-Struktur (Shape, Param-Column-Level, Zeit-Index) — damit Zeit-Index- (Timeframe/Resampling) von Param-Column-Problemen unterscheidbar sind.

**`n_combinations`** (`_count_combinations`) = volles Kreuzprodukt **aller** Param-Dimensionen über alle Indikatoren. Beispiel: fast_sma(5×5) × `B`(17×5) × supertrend(5×3) = 2125 × 15 = **31.875**. Diese Zahl wird vorab berechnet — der Cross-Produkt-Pfad in `_combine_broadcast` ist das, was sie tatsächlich materialisiert.

> Historie: Bis 1.7.6 existierte der Cross-Pfad nicht — `_evaluate_rule_group` rief direkt `vbt.broadcast(*results)`. Single-Combo-Runs (alle Params Länge 1 → reine Series) funktionierten, jeder echte Multi-Indikator-Multiparameter-Lauf brach mit `Cannot align indexes` ab. Verifiziert: Multiparameter-Lauf-Wert eines Combos == Standalone-Single-Combo bit-identisch → die Spalten-Zuordnung im Cross ist korrekt, die 31.875 Metriken sind nicht vertauscht.

### 6.7 Ergebnis-Speicherung — `repository.py` (`save_strategy_results`)

Pro Spalte (= Kombination) wird eine `BacktestResult`-Zeile mit Metriken + `actual_params_json` (die konkreten Param-Werte aus dem Column-MultiIndex) geschrieben.

**Asymmetrie nach Kombinationszahl (`if n_combinations == 1`):**
- **Single-Combo**: volle Detail-Daten — Equity-Kurve, Indikator-Serien, Trades, Orders, Positions — werden gespeichert.
- **Multi-Combo**: **nur die Metriken** pro Result (via `_extract_partial_metrics`, vektorisiert über alle Spalten). **Keine** Equity/Indikator-Zeitreihen (das wären pro Artefakt `n_combinations × bars` Zeilen — bei 31.875 × 4571 unhaltbar).

Konsequenz: Ein Multi-Combo-Result hat zunächst **keine** Equity/Indikator-Zeitreihen in der DB. `_extract_partial_metrics` (Liste) und `_extract_chart_metrics` (Recompute) liefern für denselben Combo **identische** `end_value` (verifiziert, bit-gleich).

### 6.8 Recompute — Chart eines Multi-Combo-Results — `recompute.py`

Beim Öffnen eines Charts ruft `GET /api/backtest/results/{id}/chart-data` (`api_backtest.py`) zuerst einen `COUNT` auf `backtest_result_equity`. Ist er 0 (Multi-Combo-Result), wird **synchron im API-Prozess** `recompute_single_result(result_id)` ausgeführt: die Strategie wird mit den **exakten Einzel-Parametern** dieses Results neu gerechnet (Single-Combo) und alle Detail-Daten gespeichert. `compute_full_metrics` ist der nachgelagerte Job für die langsamen Metriken.

Zwei kritische Mechaniken (beide waren Bugs, behoben in 1.7.7 / 1.7.8):

1. **`rules_json` muss übergeben werden.** Der Spec-Runner verlangt seit Ticket 12 zwingend `rules_json`. `recompute_single_result` **und** `compute_full_metrics` laden es aus `run.iteration.spec_json['rules']` und übergeben es per `inspect.signature`-Guard (hartgecodete Strategien ohne den Parameter bleiben unberührt) — analog `worker_tasks.py`. Fehlte das → `ValueError: rules_json fehlt` → `/chart-data` lieferte HTTP 500 (OHLC sichtbar, aber keine Equity/Indikatoren).

2. **`_build_resolved_config` (repository.py) baut den Param-Präfix korrekt.** Es ersetzt die Multiparameter-Lauf-Ranges der Indikator-Config durch die festen Werte aus `actual_params`. Der Match-Präfix ist der **Namespace-bereinigte, kleingeschriebene Klassenname** (`custom:dwsFastSMA` → `dwsfastsma_`), denn die `actual_params`-Keys heißen `dwsfastsma_length`, nicht `custom:dwsfastsma_length`. Früher wurde die volle Typ-ID als Präfix genutzt → kein Param matchte → die Ranges blieben stehen → der Recompute rechnete den **vollständigen Multiparameter-Lauf** und nahm `column[0]`. Symptom: jeder Chart zeigte denselben ersten Combo (immer derselbe Equity-Endwert), das Laden dauerte Minuten, und die mit `column[0]`-Werten überschriebenen Metriken ließen das Result aus der gefilterten Result-Liste fallen.

Korrekt aufgelöst läuft der Recompute als echter Single-Combo (~4.5s; der **erste** Aufruf nach Container-Neustart zahlt zusätzlich ~30–40s **Numba-JIT-Cold-Compile**).

### 6.9 Verifizierte Fakten & Fallstricke (2026-06-01)

- **Cross-Korrektheit**: `Multiparameter-Lauf[combo].end_value == Standalone-Single-Combo.end_value` bit-identisch → Cross-Produkt ordnet Spalten korrekt zu.
- **Liste == Chart**: `_extract_partial_metrics[combo].end_value == _extract_chart_metrics(pf).end_value` identisch.
- **Versions-Stempel**: `spec_runner_version` wird **bei Run-Erstellung im API-Prozess** (`api_backtest.py`) gesetzt, nicht im Worker. Nach einer `spec_runner.VERSION`-Erhöhung muss **auch der `app`-Container** neu gestartet werden (nicht nur `worker`), sonst tragen neue Runs die alte Version. Aktuell `VERSION = "1.0.2"`.
- **Worker-Neustart**: Code-Änderungen an `rules_engine`/`spec_runner`/`indicator_factory` greifen erst nach `docker compose -f docker-compose-local.yml restart worker` (Recompute zusätzlich `app`).
- **Bekannter Minor-Bug (offen)**: `recompute_single_result` löscht vorhandene Equity **nicht** vor dem Insert. Bei Doppel-Öffnen/Race entsteht doppelte Equity (z.B. 9142 statt 4571 Zeilen). Fix-Ansatz: `DELETE FROM backtest_result_equity WHERE result_id = :rid` vor dem Schreiben.
- **stdout-Buffering**: Worker-`print()`-Ausgaben ("Indikatoren gebaut", Fortschritt) sind im Docker-Log gepuffert — fehlende Zeilen heißen nicht zwingend "hängt".

---

## 7. Storage — wo Indikator-Configs liegen

`user_data/utils/database/models.py`:

| Model | Spalte | DB-Typ | Inhalt |
|---|---|---|---|
| `IndicatorConfig` | `config_json` | JSON | flaches `{name: {indicator, tf, ...}}` (eigenständige, wiederverwendbare Indikator-Konfiguration) |
| `ChartPlaygroundSetup` | `indicators_config_json` | JSON | gleiche Struktur (+ `backtest_config_json`, `strategy_config_json`, `ui_state_json`) |
| `BacktestRun` | `indicators_config_json` | JSON | gleiche Struktur (direkt an `build_indicators` / `_count_combinations`) |
| `TestSetRun` | `indicators_config_json` | JSONB | gleiche Struktur |
| `StrategyIteration` | `spec_json` | JSONB | verschachtelt: `{ indicators: {...}, rules: {entry, exit}, ... }` |

`IndicatorConfig` zusätzlich: `name`, `description`, `is_default`, `strategy_concept_id`, `strategy_iteration_id` (lose Verknüpfung, **kein** FK), `created_at`, `updated_at`. API-Schema `IndicatorConfigIn`/`Out` in `services/api/routes/api_config.py`. CRUD: `GET/POST/PUT/DELETE /api/config/indicator(/{id})`, `/{id}/copy`, `/bulk-delete`.

---

## 8. `enabled` — Status (WICHTIG: inkonsistenter Übergang)

Das Konzept "Indikator deaktivieren" wird abgeschafft. Neue Logik: ein nicht gewünschter Indikator wird **entfernt**, nicht per Flag deaktiviert.

**Bereits erledigt:**
- Frontend: kein `enabled`-Widget, kein State-Feld, kein Lesen/Schreiben mehr (`services/frontend/templates/chart_playground/index.html`). Einziges verbleibendes `enabled` dort ist `cpExitEnabled` (Exit-Regeln, anderes Konzept).
- DB-Tabelle `IndicatorConfig`: `enabled` aus allen Einträgen entfernt (`enabled:true` → Feld gelöscht, `enabled:false` → ganzer Indikator-Eintrag gelöscht). Skript `seed/migrate_strip_enabled.py`.

**NOCH OFFEN (Backend nutzt `enabled` weiter — bei Bedarf bereinigen):**
- `user_data/strategies/generic/indicator_factory.py:65` (`entry.get('enabled', True) is False` → skip) und `:264` (schreibt `enabled` ins Result); `_META_KEYS` enthält `'enabled'`.
- `user_data/strategies/generic/spec_runner.py:207` (Referenz-Validierung gegen deaktivierte).
- `user_data/utils/database/repository.py:300` (`_count_combinations` überspringt deaktivierte).
- `services/api/routes/api_chart_playground.py:813/874/901` (Recompute-Pfad rechnet `enabled` ↔ `visible` um und schreibt `enabled` in `new_indicators_config_json` zurück — **kann `enabled` in Setups/Runs neu einführen**).
- Nicht migrierte Tabellen: `ChartPlaygroundSetup`, `BacktestRun`, `TestSetRun`, `StrategyIteration.spec_json` können noch `enabled` enthalten.

Da der Backend-Default überall `enabled=True` ist, ist das funktional unkritisch (fehlt `enabled` → Indikator aktiv), aber das Muster `.get('enabled', True)` widerspricht Invariante 4 und sollte beim Aufräumen entfernt werden.

---

## 9. Migrationen (einmalig, idempotent)

Skripte liegen in `seed/`, sind aber **nicht** über den `app`-Mount erreichbar (nur `services/` ist gemountet). Ausführen im Container:
```bash
docker compose -f docker-compose-local.yml cp seed/<datei>.py app:/app/<datei>.py
docker compose -f docker-compose-local.yml exec -T app python /app/<datei>.py --dry-run   # erst prüfen
docker compose -f docker-compose-local.yml exec -T app python /app/<datei>.py --apply
```

- **`seed/migrate_indicator_sources.py`** — schreibt Kurz-IDs auf prefixte Katalog-IDs (`dwsFastSMA`→`custom:dwsFastSMA`, `supertrend`→`vbt:SUPERTREND`). Eindeutig (Custom-Modul oder genau ein VBT-Suffix-Match) → migriert; mehrdeutig/unauflösbar → unverändert + gemeldet.
- **`seed/migrate_strip_enabled.py`** — `enabled:true` → Feld entfernt. `enabled:false`: in editierbaren Configs/Setups/Iterationen (`IndicatorConfig`, `ChartPlaygroundSetup`, `StrategyIteration`) → ganzer Eintrag gelöscht; in historischen Lauf-Snapshots (`BacktestRun`, `TestSetRun`) → nur Feld entfernt, Eintrag bleibt.

Beide auf **alle** Indikator-Dict-Tabellen angewendet (`IndicatorConfig`, `ChartPlaygroundSetup`, `BacktestRun`, `TestSetRun`, `StrategyIteration.spec_json`) — Migration abgeschlossen, DB durchgängig prefixt und ohne `enabled`-Feld.

---

## 10. Offene Baustellen

- Backend-`enabled` vollständig entfernen (Abschnitt 8).
- Quellen-Prefix + `enabled`-Strip auf die übrigen Tabellen ausweiten (Abschnitt 9).
- Datenmodell-Frage (nicht umgesetzt): den flachen Eintrag in `{ indicator, tf, inputs:{}, params:{} }` entflechten würde die Klassifizierung überflüssig machen — hoher Aufwand (Backend + Migration), nur als eigenes Ticket.

# Kennzahlen-Katalog — was ein Result trägt und wer es rechnet

> Alle Kennzahlen eines `backtest_results`-Datensatzes, ihre Herkunft und die Gruppe, über
> die sie beim Run-Start an- oder abgewählt werden.
> Die **Kosten- und Architekturfragen** (warum es eine Funktion statt drei gibt, was die
> Kennzahlen kosten, wo die `auto`-Schwelle liegt und warum) stehen in
> [`metriken-architektur.md`](metriken-architektur.md) — hier steht, **was es gibt**.

## Übersicht

Ein Result trägt **46 Kennzahl-Felder** plus die 47. Spalte `deflated_sharpe_ratio`.

- Die 46 entstehen in **einer** Funktion: `_extract_metrics(portfolios, columns,
  backtest_config, groups=None)` in `user_data/utils/database/repository.py` — derselbe Weg
  für Einzellauf, Multiparameterlauf und Recompute. Es gibt kein `metrics_level` und keine
  Verzweigung nach Rastergröße mehr (Ticket 64).
- Die 47. Spalte `deflated_sharpe_ratio` ist **rasterweit** und entsteht als Nachlauf über
  den ganzen Lauf (`_calculate_deflated_sharpe`), nachdem alle Results geschrieben sind.
  Sie steht in **keiner** Gruppe und läuft bei jeder Auswahl mit.

Maßgeblich ist immer der Code, nicht diese Tabelle.

## Die Auswahl beim Run-Start (Ticket 68)

Beim Start eines Laufs ist wählbar, welche Kennzahl-Gruppen gerechnet werden. Die Auswahl
lebt **am Lauf**, nicht an der BacktestConfig: dieselbe Config dient mal der Grobsuche, mal
der Feinmessung.

- **Parameter:** `metrics` im Body von `POST /api/backtest/start` und
  `POST /api/testset-runs` (dort für alle N erzeugten Runs), sowie `--metrics` in der
  Toolbox (`backtest-run-start`, `testset-run-start`).
- **Zulässige Werte:**

| Wert | Bedeutung |
|---|---|
| `voll` | alle zehn Gruppen |
| `kern` | alle Gruppen außer `tail_risk` (die drei teuren Extremrisiko-Kennzahlen) |
| `auto` | **Default.** Unterhalb der Schwelle `voll`, ab der Schwelle `kern` |
| Liste von Gruppen-Keys | genau diese Gruppen **zusätzlich zu den Pflichtgruppen**; leere Liste = nur Pflichtgruppen |

- **Unbekannte Stufe oder unbekannter Gruppen-Key:** HTTP 400 beim Start, bevor ein Run
  angelegt wird — kein stilles Ignorieren.
- **Ablage:** Die Rohangabe steht als `metrics` im `backtest_config_json` des Runs, die
  aufgelöste Gruppenmenge als `metrics_resolved` (Vorbild `chunk_size`). Aufgelöst wird
  genau einmal, in `create_backtest_run` — dort steht die Rastergröße des ganzen Laufs
  fest. Runner, Chunks und Persistenz lesen danach nur noch `metrics_resolved`.
- **Nicht gerechnete Felder sind NULL** — ausdrücklich geschrieben, auch im Upsert. Ein
  Result zeigt nie einen Mix aus zwei Läufen mit verschiedener Auswahl.
- **Der Recompute** („Analyse starten") rechnet immer **voll**, unabhängig von der Auswahl
  des Laufs. Er ist der Weg, einem Sieger-Result nachträglich alle Kennzahlen zu geben; bei
  Rastergröße 1 sind die Kosten belanglos.

### Was `auto` tut

`auto` entscheidet allein an der Rastergröße (`backtest_runs.n_combinations`):

```
n_combinations <  AUTO_FULL_COMBINATION_THRESHOLD   ->  voll
n_combinations >= AUTO_FULL_COMBINATION_THRESHOLD   ->  kern
```

Die Schwelle steht als **eine** Konstante an **einer** Stelle:
`AUTO_FULL_COMBINATION_THRESHOLD` in `user_data/utils/metrics/metric_sets.py`. Ihre Messung
und Herleitung stehen in [`metriken-architektur.md`](metriken-architektur.md), Abschnitt 7.

Kürzt `auto`, **sagt der Lauf das**: `backtest_runs.usability_note` trägt hinter der
Verwertbarkeits-Bewertung einen Zusatz, der Rastergröße, Schwelle und die entfallenen
Felder benennt. Bei **expliziter** Auswahl (`kern`, `voll`, Liste) bleibt `usability_note`
frei für echte Warnungen — die Auswahl steht dann im `backtest_config_json` und wird in der
Run-Detailansicht sowie im `run:<id>`-Briefing der Toolbox angezeigt.

**Report, kein Gate:** Nichts blockiert einen teuren Lauf, wenn `voll` gewählt ist.

## Die Gruppen

Fünf Gruppen sind **Pflicht** und in keiner Aufruf-Form abwählbar: `scope` ist die
Selbstauskunft des Laufs, `returns`/`trades` sind das Basisergebnis samt Vergleichsanker und
Trade-Floor, und `risk_ratios` + `moments` liefern zusammen mit `bar_count` aus `scope`
genau die vier Eingänge des Nachlaufs für die Deflated Sharpe Ratio (`sharpe_ratio`, `skew`,
`kurtosis`, `bar_count`) — wären sie abwählbar, fiele die DSR aus.

Granularität ist die **Gruppe**, nicht das Einzelfeld: Felder einer Gruppe teilen dieselben
teuren Zwischenobjekte, eine Feld-Granularität spart nichts und vervielfacht nur die
Kombinatorik der Auswahl.

| Gruppen-Key | Felder | Pflicht? |
|---|---|---|
| `scope` | `start_index`, `end_index`, `total_duration`, `bar_count` | **Pflicht** |
| `returns` | `start_value`, `min_value`, `max_value`, `end_value`, `total_return_pct`, `benchmark_return_pct`, `position_coverage_pct`, `max_gross_exposure_pct` | **Pflicht** |
| `trades` | `total_orders`, `total_fees_paid`, `total_trades`, `open_trades`, `long_trades`, `short_trades` | **Pflicht** |
| `risk_ratios` | `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`, `omega_ratio`, `annualized_return`, `annualized_volatility`, `downside_risk` | **Pflicht** |
| `moments` | `skew`, `kurtosis` | **Pflicht** |
| `drawdown` | `max_drawdown_pct`, `max_drawdown_duration` | abwählbar |
| `trade_quality` | `win_rate_pct`, `profit_factor`, `expectancy`, `best_trade_pct`, `worst_trade_pct`, `avg_winning_trade_pct`, `avg_losing_trade_pct`, `avg_winning_trade_duration`, `avg_losing_trade_duration` | abwählbar |
| `sqn_edge` | `sqn`, `edge_ratio` | abwählbar |
| `tail_risk` | `tail_ratio`, `value_at_risk`, `cond_value_at_risk` | abwählbar (die drei teuren) |
| `benchmark` | `alpha`, `beta`, `information_ratio` | abwählbar |

Die Zuordnung steht als Single Source in `user_data/utils/metrics/metric_sets.py`
(`METRIC_GROUPS`); Runner, Persistenz und Anzeige beziehen sie ausschließlich von dort.

---

## Katalog

### `scope` — gerechneter Zeitraum und Umfang (Pflicht)

| DB-Feld | Herkunft | Beschreibung |
|---|---|---|
| `start_index` | `wrapper.index[0]` | Erster Balken des gerechneten Fensters (nach Zuschnitt auf `start`..`end`) |
| `end_index` | `wrapper.index[-1]` | Letzter Balken des gerechneten Fensters |
| `total_duration` | `bar_count * wrapper.freq` | Länge des gerechneten Zeitraums — dieselbe Definition wie `pf.stats()['Total Duration']`, **nicht** `index[-1] - index[0]` |
| `bar_count` | `wrapper.index.shape[0]` | Zahl der gerechneten Balken; zugleich Eingang der Deflated Sharpe Ratio |

### `returns` — Portfolio-Werte und Rendite (Pflicht)

| DB-Feld | Herkunft | Beschreibung |
|---|---|---|
| `start_value` | `pf.init_value` | Startkapital |
| `min_value` | `pf.value.vbt.min()` | Tiefster Portfoliowert im Fenster |
| `max_value` | `pf.value.vbt.max()` | Höchster Portfoliowert im Fenster |
| `end_value` | `pf.final_value` | Endwert des Portfolios |
| `total_return_pct` | `pf.total_return * 100` | Gesamtrendite in Prozent |
| `benchmark_return_pct` | `pf.total_market_return * 100` | Buy-and-Hold-Rendite des Marktes — der Vergleichsanker |
| `position_coverage_pct` | `pf.position_coverage * 100` | Anteil der Balken mit offener Position — wie viel Zeit die Strategie im Markt war |
| `max_gross_exposure_pct` | `pf.gross_exposure.vbt.max() * 100` | Höchste Brutto-Positionsgröße in Prozent des Portfoliowerts |

### `trades` — Orders und Trade-Zahlen (Pflicht)

| DB-Feld | Herkunft | Beschreibung |
|---|---|---|
| `total_orders` | `pf.orders.count()` | Zahl der ausgeführten Orders |
| `total_fees_paid` | `pf.orders.fees.sum()` | Summe aller Gebühren |
| `total_trades` | `pf.trades.count()` | Zahl der Trades **inklusive** einer offenen Position — der Trade-Floor jeder Auswertung |
| `open_trades` | `count_open_trades(pf)` | Davon am Fensterende noch offen |
| `long_trades` | `pf.trades.direction_long.count()` | Long-Trades (Summe mit `short_trades` = `total_trades`) |
| `short_trades` | `pf.trades.direction_short.count()` | Short-Trades |

### `risk_ratios` — Risiko- und Rendite-Verhältnisse (Pflicht)

| DB-Feld | Herkunft | Beschreibung |
|---|---|---|
| `sharpe_ratio` | `pf.sharpe_ratio` | Rendite pro Risikoeinheit (Gesamtvolatilität); Eingang der Deflated Sharpe Ratio |
| `sortino_ratio` | `pf.sortino_ratio` | Wie Sharpe, aber nur Abwärtsvolatilität im Nenner |
| `calmar_ratio` | `pf.calmar_ratio` | Annualisierte Rendite geteilt durch maximalen Rückgang |
| `omega_ratio` | `pf.omega_ratio` | Verhältnis der Gewinn- zur Verlustfläche der Renditeverteilung |
| `annualized_return` | `pf.annualized_return * 100` | Jährliche Rendite — macht verschieden lange Zeiträume vergleichbar |
| `annualized_volatility` | `pf.annualized_volatility * 100` | Jährliche Schwankungsbreite |
| `downside_risk` | `pf.downside_risk * 100` | Nur die negative Volatilität |

### `moments` — Verteilungsform der Renditen (Pflicht)

| DB-Feld | Herkunft | Beschreibung |
|---|---|---|
| `skew` | `scipy.stats.skew(returns, bias=True)` | Schiefe der Renditeverteilung; Eingang der Deflated Sharpe Ratio |
| `kurtosis` | `scipy.stats.kurtosis(returns, bias=True, fisher=False)` | **Rohe** Wölbung (Normalverteilung rund 3), nicht die Excess-Wölbung — die Formel der Deflated Sharpe Ratio erwartet die rohe (Ticket 54) |

> Beide werden auf der Renditematrix mit `NaN -> 0` gerechnet, exakt so, wie VBT es intern
> für die DSR tut. Dass sie nie gespeichert wurden, ist der Grund, warum der Altbestand die
> Deflated Sharpe Ratio nicht nachrechnen kann.

### `drawdown` — Rückgang (abwählbar)

| DB-Feld | Herkunft | Beschreibung |
|---|---|---|
| `max_drawdown_pct` | `pf.max_drawdown * 100` | Größter Wertverlust vom Höchststand; wird **negativ** gespeichert, wie VBT ihn liefert |
| `max_drawdown_duration` | `pf.drawdowns.max_duration` | Längste Dauer eines Rückgangs bis zur Erholung |

### `trade_quality` — Trade-Qualität (abwählbar)

Alle Felder dieser Gruppe rechnen auf **geschlossenen** Trades (`trades.status_closed`) —
eine offene Position hat noch kein Ergebnis. Die Auswahl auf geschlossene Trades ist selbst
schon Arbeit und entsteht nur, wenn `trade_quality` oder `sqn_edge` aktiv ist.

| DB-Feld | Herkunft | Beschreibung |
|---|---|---|
| `win_rate_pct` | `closed.win_rate * 100` | Anteil profitabler Trades |
| `profit_factor` | `closed.profit_factor` | Bruttogewinn geteilt durch Bruttoverlust; > 1 heißt profitabel |
| `expectancy` | `closed.expectancy` | Erwarteter Gewinn je Trade in Basiswährung |
| `best_trade_pct` | `closed.returns.max() * 100` | Bester Einzeltrade |
| `worst_trade_pct` | `closed.returns.min() * 100` | Schlechtester Einzeltrade |
| `avg_winning_trade_pct` | `closed.winning.returns.mean() * 100` | Mittlerer Gewinn der Gewinner |
| `avg_losing_trade_pct` | `closed.losing.returns.mean() * 100` | Mittlerer Verlust der Verlierer |
| `avg_winning_trade_duration` | `closed.winning.duration.mean()` | Mittlere Haltedauer der Gewinner |
| `avg_losing_trade_duration` | `closed.losing.duration.mean()` | Mittlere Haltedauer der Verlierer |

> Ohne geschlossene Trades liefert VBT `NaN` -> `None`, **nicht** `0`.

### `sqn_edge` — Systemqualität (abwählbar)

| DB-Feld | Herkunft | Beschreibung |
|---|---|---|
| `sqn` | `closed.sqn` | System Quality Number (Van Tharp) — reduziert über die Trade-Records und skaliert deshalb **nicht** mit der Rastergröße |
| `edge_ratio` | `closed.get_edge_ratio(volatility=…)` | MFE/MAE-Verhältnis: wird Gewinnpotenzial besser genutzt als Verlust begrenzt |

> **Die Volatilität wird ausdrücklich mitgegeben.** Ohne das Argument baut VBT sie über
> `atr_nb(high=to_2d_array(...), …)`, und `atr_nb` greift mit `high[:, col]` unmittelbar auf
> die Spalte zu. In diesem System trägt ein Portfolio aber genau **eine** OHLC-Spalte für
> beliebig viele Kombinationen — ab Spalte 1 liest numba versetzt weiter und die
> `edge_ratio` wird falsch. Spalte 0 blieb dabei immer richtig; ein Vergleich, der nur die
> erste Spalte prüft, sieht den Fehler nie (Ticket 64).

### `tail_risk` — Extremrisiko (abwählbar, die drei teuren)

Perzentil-basiert und damit sortierend — die einzigen Kennzahlen, die spürbar mit der
Rastergröße skalieren. Sie werden ausdrücklich parallel gerechnet
(`jitted=dict(parallel=True)`); die Werte sind bitgenau dieselben wie sequenziell. Genau
diese drei lässt `kern` weg, und genau sie überspringt `auto` ab der Schwelle.

| DB-Feld | Herkunft | Beschreibung |
|---|---|---|
| `tail_ratio` | `pf.get_tail_ratio(jitted=dict(parallel=True))` | Verhältnis des rechten (Gewinn-) zum linken (Verlust-)Verteilungsende; > 1 heißt Gewinne sind extremer als Verluste |
| `value_at_risk` | `pf.get_value_at_risk(jitted=dict(parallel=True))` | Value at Risk (95 %) — erwarteter Verlust im schlechten Fall unter normalen Bedingungen |
| `cond_value_at_risk` | `pf.get_cond_value_at_risk(jitted=dict(parallel=True))` | Conditional VaR (Expected Shortfall) — erwarteter Verlust, wenn der VaR überschritten wird |

### `benchmark` — benchmark-relative Kennzahlen (abwählbar)

| DB-Feld | Herkunft | Beschreibung |
|---|---|---|
| `alpha` | `pf.alpha` | Überrendite gegenüber der Benchmark |
| `beta` | `pf.beta` | Marktsensitivität: 1 bewegt sich wie der Markt, < 1 defensiver, > 1 aggressiver |
| `information_ratio` | `pf.information_ratio` | Überrendite je Tracking-Error — wie beständig die Benchmark geschlagen wird |

### Außerhalb der Gruppen: `deflated_sharpe_ratio`

| DB-Feld | Herkunft | Beschreibung |
|---|---|---|
| `deflated_sharpe_ratio` | `_calculate_deflated_sharpe(conn, run_id)` | Für Mehrfachtestung korrigierter Sharpe — läuft **nach** allen Chunks über das ganze Raster |

> **Seit Ticket 54 (13.08.2026) nicht mehr aus VBT.** `ReturnsAccessor.deflated_sharpe_ratio`
> trug zwei Formelfehler (der bewertete Kandidat kürzte sich aus dem Zähler heraus, und im
> Nenner stand die Excess- statt der rohen Wölbung). Die Kennzahl ist außerdem **rasterweit**
> — ihr Wert hängt davon ab, wie viele andere Kombinationen mitgelaufen sind — und gehört
> damit nicht in eine Funktion, die je Kombination rechnet. Sie entsteht als Nachlauf über
> den ganzen Lauf auf Basis der eigenen Rechnung in
> `user_data/utils/metrics/deflated_sharpe.py`, mit `N = backtest_runs.n_combinations`.
> Ihre vier Eingänge liegen deshalb alle in Pflichtgruppen. Results vor Spec-Runner 4.0.0
> tragen entweder die alte, defekte Zahl oder gar keine (Werte ohne persistierte Momente
> wurden mit Migration 0025 geleert). Die Zahl ist ein Report, nie ein Filter.

---

## Anzeige und Auswertung

Die Kennzahlen werden in diesen Analyse-Endpunkten verwendet:

| Endpunkt | Beschreibung |
|---|---|
| `/analyse/summary` | Zusammenfassung: AVG/MIN/MAX über alle Results eines Runs |
| `/analyse/parameter-ranking` | Welche Parameter-Werte liefern die beste Leistung je Kennzahl |
| `/analyse/top-results` | Top-N Results, sortiert nach wählbarer Kennzahl |
| `/analyse/heatmap` | 2D-Heatmap für zwei Parameter-Achsen und eine Kennzahl |

**NULL verträgt die Anzeige.** SQL-Aggregate übergehen NULL ohnehin; im Frontend erscheint
ein nicht gerechnetes Feld als „–", nicht als leere Zelle und nicht als 0. Ein `kern`-Lauf
wirft auf keiner Analyse-Seite einen Fehler.

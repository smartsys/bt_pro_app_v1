# Analyse-Metriken -- Backtest-Auswertung

> Dokumentation aller Metriken die für die Analyse-Seite `/backtest/runs/{id}/analyse` zur Verfügung stehen.
> Siehe auch: [projekt.md](../project/projekt.md) für Gesamtprojekt-Übersicht.

## Übersicht

Die Metriken werden in zwei Stufen erhoben:

- **Partial Metriken** (`_extract_partial_metrics`): Vektorisiert beim Massen-Backtest (300k Kombinationen). Schnell, für Übersicht und Analyse.
- **All Metriken** (`_extract_all_metrics`): Einzeln beim Recompute via `pf.stats()`. Vollständig, für Chart-Detail-Ansicht.

## Metriken-Katalog

### Basis-Metriken (Schritt 1 -- bereits vorhanden)

| DB-Feld | VBT-Property | Beschreibung | Erhebung |
|---|---|---|---|
| `total_return_pct` | `portfolios.total_return * 100` | Gesamtrendite in Prozent -- wie viel hat die Strategie insgesamt verdient/verloren | partial + all |
| `benchmark_return_pct` | `portfolios.total_market_return * 100` | Buy-and-Hold Rendite des Marktes zum Vergleich -- hätte einfaches Halten mehr gebracht? | partial + all |
| `end_value` | `portfolios.final_value` | Endwert des Portfolios in der Basiswährung | partial + all |
| `total_trades` | `portfolios.trades.count()` | Gesamtzahl der Trades -- zeigt Handelsaktivität der Strategie | partial + all |
| `win_rate_pct` | `portfolios.trades.win_rate * 100` | Anteil profitabler Trades in Prozent | partial + all |
| `profit_factor` | `portfolios.trades.profit_factor` | Verhältnis Bruttogewinn zu Bruttoverlust -- >1 bedeutet profitabel | partial + all |
| `max_drawdown_pct` | `portfolios.max_drawdown * 100` | Maximaler Wertverlust vom Höchststand in Prozent -- Worst-Case-Szenario | partial + all |

### Risiko-Kennzahlen (Gruppe A -- DB-Spalte vorhanden, neu in partial)

| DB-Feld | VBT-Property | Beschreibung | Erhebung |
|---|---|---|---|
| `sharpe_ratio` | `portfolios.sharpe_ratio` | Rendite pro Risikoeinheit (Volatilität) -- Standardmaß für risikoadjustierte Performance. >1 gut, >2 sehr gut | partial + all |
| `sortino_ratio` | `portfolios.sortino_ratio` | Wie Sharpe, aber nur Abwärtsvolatilität -- bestraft nur negative Schwankungen, nicht positive | partial + all |
| `calmar_ratio` | `portfolios.calmar_ratio` | Annualisierte Rendite geteilt durch Max Drawdown -- wie gut wird Risiko in Rendite umgewandelt | partial + all |
| `omega_ratio` | `portfolios.omega_ratio` | Verhältnis der Gewinn- zur Verlustfläche der Renditeverteilung -- berücksichtigt die gesamte Verteilung, nicht nur Mittelwert/Varianz | partial + all |
| `expectancy` | `portfolios.trades.expectancy` | Erwarteter Gewinn pro Trade in Basiswährung -- was bringt ein durchschnittlicher Trade | partial + all |

### Annualisierte Metriken (Gruppe B -- komplett neu)

| DB-Feld | VBT-Property | Beschreibung | Erhebung |
|---|---|---|---|
| `annualized_return` | `portfolios.annualized_return * 100` | Jährliche Rendite -- ermöglicht Vergleich über verschiedene Backtestzeiträume hinweg | partial + all |
| `annualized_volatility` | `portfolios.annualized_volatility * 100` | Jährliche Schwankungsbreite -- wie stark schwankt der Portfoliowert auf Jahressicht | partial + all |

### Erweiterte Risiko-Metriken (Gruppe B -- komplett neu)

| DB-Feld | VBT-Property | Beschreibung | Erhebung |
|---|---|---|---|
| `downside_risk` | `portfolios.downside_risk * 100` | Nur die negative Volatilität -- aussagekräftiger als Gesamtvolatilität für Trading | partial + all |
| `tail_ratio` | `portfolios.tail_ratio` | Verhältnis der rechten (Gewinn) zur linken (Verlust) Verteilungsenden -- misst Extremrisiko. >1 bedeutet Gewinne sind extremer als Verluste | nur all (61s bei 5k) |
| `value_at_risk` | `portfolios.value_at_risk` | Value at Risk (95%) -- maximaler erwarteter Tagesverlust unter normalen Marktbedingungen | nur all (47s bei 5k) |
| `cond_value_at_risk` | `portfolios.cond_value_at_risk` | Conditional VaR (Expected Shortfall) -- erwarteter Verlust wenn VaR überschritten wird. Worst-Case-Szenario | nur all (43s bei 5k) |

### Benchmark-relative Metriken (Gruppe B -- komplett neu)

| DB-Feld | VBT-Property | Beschreibung | Erhebung |
|---|---|---|---|
| `alpha` | `portfolios.alpha` | Überrendite gegenüber der Benchmark -- positives Alpha bedeutet die Strategie schlägt den Markt | nur all (7s bei 5k) |
| `beta` | `portfolios.beta` | Markt-Sensitivität -- Beta=1 bewegt sich wie der Markt, <1 defensiver, >1 aggressiver | nur all (7s bei 5k) |
| `information_ratio` | `portfolios.information_ratio` | Überrendite pro Tracking-Error -- wie konsistent schlägt die Strategie die Benchmark | nur all (7s bei 5k) |

### Trade-Qualität (Gruppe B -- komplett neu)

| DB-Feld | VBT-Property | Beschreibung | Erhebung |
|---|---|---|---|
| `sqn` | `portfolios.trades.sqn` | System Quality Number (Van Tharp) -- Gesamtbewertung der Strategie-Qualität. <1.7 schlecht, 1.7-2.5 durchschnittlich, 2.5-4 gut, >4 exzellent | nur all |
| `edge_ratio` | `portfolios.trades.edge_ratio` | MFE/MAE Verhältnis -- wie gut werden Gewinne mitgenommen vs. Verluste begrenzt. >1 bedeutet Gewinnpotential wird besser genutzt als Verluste begrenzt | nur all |

### Overfitting-Kontrolle (Gruppe B -- komplett neu)

| DB-Feld | VBT-Property | Beschreibung | Erhebung |
|---|---|---|---|
| `deflated_sharpe_ratio` | `portfolios.deflated_sharpe_ratio` | Korrigierter Sharpe Ratio für Multiple-Testing -- extrem wichtig bei >1000 Parameter-Kombinationen. Berücksichtigt dass bei vielen Tests zufällig gute Ergebnisse auftreten | partial + all |

## Analyse-Funktionen

Die Metriken werden in folgenden Analyse-Endpunkten verwendet:

| Endpunkt | Beschreibung |
|---|---|
| `/analyse/summary` | Zusammenfassung: AVG/MIN/MAX über alle Results eines Runs |
| `/analyse/parameter-ranking` | Welche Parameter-Werte liefern die beste Performance pro Metrik |
| `/analyse/top-results` | Top-N Results sortiert nach wählbarer Metrik |
| `/analyse/heatmap` | 2D-Heatmap für zwei Parameter-Achsen und eine Metrik |

## Performance-Ergebnisse (5040 Kombinationen, 2026-04-05)

Gemessene Zeiten pro Metrik bei 5040 Kombinationen:

| Metrik | Zeit | In partial? |
|---|---|---|
| total_return | 0.1s | ja |
| total_market_return | 0.3s | ja |
| profit_factor | 0.8s | ja |
| final_value | 0.0s | ja |
| trade_count | 0.0s | ja |
| win_rate | 0.3s | ja |
| max_drawdown | 4.6s | ja |
| expectancy | 0.3s | ja |
| sqn | 0.4s | **nein** — Trade-Qualität, nur full |
| edge_ratio | 0.1s | **nein** — Trade-Qualität, nur full |
| sharpe_ratio | 5.3s | ja |
| sortino_ratio | 4.8s | ja |
| calmar_ratio | 3.2s | ja |
| omega_ratio | 4.8s | ja |
| annualized_return | 5.3s | ja |
| annualized_volatility | 5.9s | ja |
| downside_risk | 4.7s | ja |
| deflated_sharpe_ratio | 5.7s | ja |
| alpha | 7.1s | **nein** — zu langsam |
| beta | 7.4s | **nein** — zu langsam |
| information_ratio | 7.2s | **nein** — zu langsam |
| tail_ratio | 61.0s | **nein** — viel zu langsam |
| value_at_risk | 46.7s | **nein** — viel zu langsam |
| cond_value_at_risk | 42.8s | **nein** — viel zu langsam |

**Entscheidung:** 8 Metriken nur in `_extract_full_metrics` (Hintergrund-Job), 16 Metriken in `_extract_partial_metrics` (Massen-Backtest).

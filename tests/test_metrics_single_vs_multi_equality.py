"""Gleichheits-Test: Einzellauf- gegen Multiparameterlauf-Kennzahlen (Ticket 64).

Rechnet **denselben** Backtest zweimal — einmal als einzelne Kombination (das,
was ein Einzellauf und der Recompute rechnen) und einmal als Spalte 0 eines
Zwei-Kombinationen-Sweeps (das, was ein Multiparameterlauf rechnet) — und
vergleicht jede Kennzahl.

**War beim ersten Lauf rot, mit Absicht.** Er hat die Feldmengen-Lücke aus
`documentation/knowledge/metriken-architektur.md` sichtbar gemacht (34 gegen 24
Felder, 18 Befunde, davon keine einzige Wertabweichung), bevor Ticket 64
Anforderung 3 sie mit einer gemeinsamen `_extract_metrics`-Funktion geschlossen
hat. Das Protokoll des ersten Laufs steht im Abnahme-Vermerk des Tickets.

Seither geht **ein** Weg durch beide Fälle. Der Test prüft damit nicht mehr zwei
Implementierungen gegeneinander, sondern das, was übrig bleibt: dass VBT dieselben
Zahlen liefert, wenn es über eine einzelne Spalte reduziert wie über eine von
mehreren — Skalar gegen Series, Zeitspannen-Formatierung, NaN-Behandlung.
"""

import math

import numpy as np
import pandas as pd
import pytest
import vectorbtpro as vbt

from user_data.utils.database.repository import _extract_metrics
from user_data.utils.metrics.metric_sets import fields_for_groups, resolve_metric_groups
from user_data.utils.metrics.trading_window import build_trading_window

_START = '2020-02-01'
_END = '2020-02-20'


def _config() -> dict:
    """Minimale BacktestConfig mit Handelsfenster (identisch für beide Pfade)."""
    return {'start': _START, 'end': _END}


def _price_series(n: int = 1600, seed: int = 7) -> pd.Series:
    """Deterministische Preisreihe über n Stundenbalken ab 2020-01-01."""
    idx = pd.date_range('2020-01-01', periods=n, freq='1h', tz='UTC')
    rng = np.random.default_rng(seed)
    values = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, n))
    return pd.Series(values, index=idx)


def _build_portfolio(close: pd.Series, sweep: bool):
    """Portfolio mit Long- UND Short-Trades, alle innerhalb des Fensters geschlossen.

    Bei `sweep=True` entsteht eine zweite Spalte über `fees=vbt.Param([0.0, 0.001])`
    — Spalte 0 (fees=0.0) ist dann exakt dieselbe Kombination wie das
    Einzel-Kombinations-Portfolio (`sweep=False`, fees defaultet ebenfalls auf 0.0).
    Dasselbe Muster wie `_portfolio_with_long_and_short_entries` in
    `tests/test_trading_window_slice.py` (Ticket 58/60).
    """
    start, end = build_trading_window(_config())
    idx = close.index
    in_window = (idx >= start) & (idx <= end)
    last_in_window = int(np.max(np.flatnonzero(in_window)))
    long_entries = pd.Series(False, index=idx)
    long_exits = pd.Series(False, index=idx)
    short_entries = pd.Series(False, index=idx)
    short_exits = pd.Series(False, index=idx)
    entry_positions = [
        i for i in range(len(idx))
        if in_window[i] and i % 40 == 0 and i + 20 <= last_in_window
    ]
    for n, pos in enumerate(entry_positions):
        if n % 2 == 0:
            long_entries.iloc[pos] = True
            long_exits.iloc[pos + 20] = True
        else:
            short_entries.iloc[pos] = True
            short_exits.iloc[pos + 20] = True
    kwargs = dict(
        close=close, entries=long_entries, exits=long_exits,
        short_entries=short_entries, short_exits=short_exits,
        freq='1h', init_cash=100, size=100, size_type='value',
    )
    if sweep:
        kwargs['fees'] = vbt.Param([0.0, 0.001])
    return vbt.PF.from_signals(**kwargs)


_ENTRY_STEPS = (40, 50, 60)


def _signal_masks(close: pd.Series, step: int) -> tuple:
    """Ein Einstieg alle `step` Balken im Fenster, Ausstieg 20 Balken später."""
    start, end = build_trading_window(_config())
    idx = close.index
    in_window = (idx >= start) & (idx <= end)
    last_in_window = int(np.max(np.flatnonzero(in_window)))
    entries = pd.Series(False, index=idx)
    exits = pd.Series(False, index=idx)
    for i in range(len(idx)):
        if in_window[i] and i % step == 0 and i + 20 <= last_in_window:
            entries.iloc[i] = True
            exits.iloc[i + 20] = True
    return entries, exits


def _ohlc_kwargs(close: pd.Series) -> dict:
    """Portfolio-Argumente mit einspaltigem Open/High/Low — nötig für die edge_ratio.

    Ohne High und Low normiert `Trades.get_edge_ratio` über eine rollende
    Standardabweichung des Schlusskurses; erst mit High und Low greift VBT zum ATR,
    und nur dort schlägt der Spaltenversatz zu, den der Test unten absichert.
    """
    return dict(
        open=close * 0.999, high=close * 1.004, low=close * 0.996,
        freq='1h', init_cash=100, size=100, size_type='value', fees=0.001,
    )


def test_edge_ratio_equal_for_every_column_of_a_sweep():
    """Die edge_ratio jeder Spalte stimmt mit dem einzeln gerechneten Portfolio überein.

    Pinnt einen gemessenen Formfehler in VBT, der erst auffiel, als die edge_ratio
    mit Ticket 64 in jeden Lauf wanderte: `Trades.get_edge_ratio` baut ohne
    ausdrückliche Volatilität einen ATR über
    `atr_nb(high=to_2d_array(self._high), ..., close=to_2d_array(self._close))`, und
    `atr_nb` greift dort mit `high[:, col]` unmittelbar auf die Spalte zu, statt sie
    flexibel auszuwählen.

    Genau diese Form baut die Rules-Engine: sie übergibt `from_signals` einen
    mehrspaltigen Schlusskurs (`close_mc`, eine Spalte je Kombination), während
    Open/High/Low einspaltig bleiben — alle Kombinationen rechnen auf demselben
    Symbol und Zeitfenster. Ab Spalte 1 liest numba deshalb ohne Bereichsprüfung um
    `col` Zeilen versetzt weiter, teils über das Pufferende hinaus. Spalte 0 blieb
    immer richtig; ein Vergleich, der nur die erste Spalte prüft, hätte den Fehler
    nie gesehen. Gemessen an diesem Aufbau ohne die Korrektur:
    1,1881 / 5,1170 / 1,0932 gegen die Referenz 1,1881 / 4,7651 / 1,1086.
    """
    close = _price_series()
    kwargs = _ohlc_kwargs(close)
    masks = [_signal_masks(close, step) for step in _ENTRY_STEPS]
    close_mc = pd.DataFrame(
        {step: close.values for step in _ENTRY_STEPS}, index=close.index
    )
    pf_sweep = vbt.PF.from_signals(
        close=close_mc,
        entries=pd.DataFrame(
            {step: m[0].values for step, m in zip(_ENTRY_STEPS, masks)}, index=close.index
        ),
        exits=pd.DataFrame(
            {step: m[1].values for step, m in zip(_ENTRY_STEPS, masks)}, index=close.index
        ),
        **kwargs,
    )
    sweep_metrics = _extract_metrics(pf_sweep, pf_sweep.wrapper.columns, _config())
    assert len(sweep_metrics) == len(_ENTRY_STEPS)

    for column, (step, (entries, exits)) in enumerate(zip(_ENTRY_STEPS, masks)):
        pf_single = vbt.PF.from_signals(
            close=close, entries=entries, exits=exits, **kwargs
        )
        single = _extract_metrics(pf_single, pf_single.wrapper.columns, _config())[0]
        assert single['edge_ratio'] is not None
        assert sweep_metrics[column]['edge_ratio'] == pytest.approx(
            single['edge_ratio'], rel=1e-12
        ), f"edge_ratio weicht in Spalte {column} (Einstieg alle {step} Balken) ab"


def _diff_report(single: dict, multi: dict) -> list[str]:
    """Vergleicht zwei Metrik-Dicts Feld für Feld und protokolliert jede Abweichung.

    Meldet drei Arten von Befunden getrennt:
    - Feld nur im Einzellauf vorhanden (fehlt dem Multiparameterlauf).
    - Feld nur im Multiparameterlauf vorhanden (fehlt dem Einzellauf).
    - Feld auf beiden Seiten vorhanden, aber mit unterschiedlichem Wert.

    Args:
        single: Kennzahlen der einzelnen Kombination (Einzellauf).
        multi: Kennzahlen an der Vergleichs-Spalte des Sweeps (Multiparameterlauf).

    Returns:
        Liste von Klartext-Befunden, leer wenn beide Seiten übereinstimmen.
    """
    mismatches: list[str] = []
    all_keys = sorted(set(single) | set(multi))
    for key in all_keys:
        in_single = key in single
        in_multi = key in multi
        if in_single and not in_multi:
            mismatches.append(f"{key}: nur im Einzellauf vorhanden (Wert {single[key]!r})")
            continue
        if in_multi and not in_single:
            mismatches.append(f"{key}: nur im Multiparameterlauf vorhanden (Wert {multi[key]!r})")
            continue
        sval, mval = single[key], multi[key]
        if sval is None and mval is None:
            continue
        if sval is None or mval is None:
            mismatches.append(f"{key}: Einzellauf={sval!r}, Multiparameterlauf={mval!r}")
            continue
        if isinstance(sval, (int, float)) and isinstance(mval, (int, float)):
            if isinstance(sval, float) and math.isnan(sval) and isinstance(mval, float) and math.isnan(mval):
                continue
            if not math.isclose(sval, mval, rel_tol=1e-9, abs_tol=1e-9):
                mismatches.append(
                    f"{key}: Einzellauf={sval}, Multiparameterlauf={mval}, "
                    f"Differenz={sval - mval}"
                )
        else:
            if sval != mval:
                mismatches.append(f"{key}: Einzellauf={sval!r}, Multiparameterlauf={mval!r}")
    return mismatches


def test_same_backtest_single_vs_multi_run_all_metrics_equal():
    """Derselbe Backtest über beide Pfade muss dieselben Kennzahlen liefern.

    Baut denselben Long/Short-Backtest einmal als Einzel-Kombination (Einzellauf)
    und einmal als Spalte 0 eines Zwei-Kombinationen-Sweeps (Multiparameterlauf,
    fees=0.0 wie im Einzellauf) und vergleicht jedes Feld beider Extraktionspfade.

    **Ohne Ausnahme.** Bis Ticket 54 war die `deflated_sharpe_ratio` hier
    ausgenommen: Sie ist rasterweit und musste für N=1 und N=2 verschieden
    ausfallen. Seit sie nicht mehr aus `_extract_metrics` kommt, sondern als
    Nachlauf über den ganzen Lauf entsteht, ist die Ausnahme gegenstandslos — die
    Funktion liefert nur noch spaltenlokale Kennzahlen, und für die gilt Gleichheit
    ohne Sonderfall.
    """
    close = _price_series()
    pf_single = _build_portfolio(close, sweep=False)
    pf_multi = _build_portfolio(close, sweep=True)

    single_metrics = _extract_metrics(
        pf_single, pf_single.wrapper.columns, _config()
    )[0]
    multi_metrics = _extract_metrics(
        pf_multi, pf_multi.wrapper.columns, _config()
    )[0]

    mismatches = _diff_report(single_metrics, multi_metrics)

    assert not mismatches, (
        f"Kennzahlen weichen zwischen Einzellauf und Multiparameterlauf ab "
        f"({len(mismatches)} Befunde):\n" + "\n".join(mismatches)
    )


def test_same_backtest_single_vs_multi_run_equal_under_every_metric_selection():
    """Auch mit Metrik-Auswahl bleiben Einzel- und Multiparameterlauf gleich (Ticket 68).

    Die Auswahl darf die Gleichheit nicht wieder aufmachen: Sie entscheidet, **ob** ein
    Abschnitt gerechnet wird, nie **wie**. Geprüft über alle drei Formen, in denen eine
    Auswahl auftreten kann — die volle Menge, die Stufe `kern` und die schmalste Auswahl
    (nur Pflichtgruppen).

    Die volle Auswahl ist zugleich die Gegenprobe zum Stand vor dem Ticket: Sie muss
    Feld für Feld dasselbe liefern wie der Aufruf ohne `groups`.
    """
    close = _price_series()
    pf_single = _build_portfolio(close, sweep=False)
    pf_multi = _build_portfolio(close, sweep=True)

    reference = _extract_metrics(pf_single, pf_single.wrapper.columns, _config())[0]

    for selection in ('voll', 'kern', []):
        groups = resolve_metric_groups(selection)
        single_metrics = _extract_metrics(
            pf_single, pf_single.wrapper.columns, _config(), groups=groups
        )[0]
        multi_metrics = _extract_metrics(
            pf_multi, pf_multi.wrapper.columns, _config(), groups=groups
        )[0]

        assert set(single_metrics) == set(fields_for_groups(groups))
        mismatches = _diff_report(single_metrics, multi_metrics)
        assert not mismatches, (
            f"Auswahl {selection!r}: Kennzahlen weichen zwischen Einzellauf und "
            f"Multiparameterlauf ab ({len(mismatches)} Befunde):\n"
            + "\n".join(mismatches)
        )

        # Die Auswahl verändert keinen Wert — sie lässt nur Felder weg.
        against_reference = _diff_report(
            {k: reference[k] for k in single_metrics}, single_metrics
        )
        assert not against_reference, (
            f"Auswahl {selection!r} verändert Werte gegenüber der vollen Rechnung:\n"
            + "\n".join(against_reference)
        )

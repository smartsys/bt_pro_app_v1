"""Tests der Gruppen-Auswahl in `repository._extract_metrics`.

Geprüft wird das, worauf sich Runner und Persistenz verlassen:

- Ohne Angabe und mit der vollen Gruppenmenge liefert die Funktion **Feld für Feld
  dasselbe** wie vor der Auswahl-Mechanik.
- Eine schmalere Auswahl liefert die abgewählten Felder gar nicht — und verändert
  die übrigen Werte nicht.
- Die Pflichtgruppen sind auch bei der schmalsten Auswahl dabei, samt der vier
  Eingänge des DSR-Nachlaufs.
- Ein unbekannter Gruppen-Key bricht ab, statt still alles zu rechnen.
"""

import math

import numpy as np
import pandas as pd
import pytest
import vectorbtpro as vbt

from user_data.utils.database.repository import _extract_metrics
from user_data.utils.metrics.metric_sets import (
    ALL_GROUPS,
    ALL_METRIC_FIELDS,
    METRIC_GROUPS,
    REQUIRED_GROUPS,
    fields_for_groups,
    resolve_metric_groups,
    skipped_fields,
)
from user_data.utils.metrics.trading_window import build_trading_window

_START = '2020-02-01'
_END = '2020-02-20'


def _config() -> dict:
    """Minimale BacktestConfig mit Handelsfenster."""
    return {'start': _START, 'end': _END}


def _price_series(n: int = 1600, seed: int = 11) -> pd.Series:
    """Deterministische Preisreihe über n Stundenbalken ab 2020-01-01."""
    idx = pd.date_range('2020-01-01', periods=n, freq='1h', tz='UTC')
    rng = np.random.default_rng(seed)
    values = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, n))
    return pd.Series(values, index=idx)


def _portfolio(n_columns: int = 2):
    """Portfolio mit Gewinn- und Verlust-Trades über mehrere Kombinationen.

    Mehrspaltig, weil ein Einspalter die Skalar-Sonderfälle in `_vals`/`_durations`
    nicht trifft — genau dort greifen die Gruppen-Weichen in den Zusammenbau ein.
    """
    close = _price_series()
    start, end = build_trading_window(_config())
    idx = close.index
    in_window = (idx >= start) & (idx <= end)
    last_in_window = int(np.max(np.flatnonzero(in_window)))

    steps = [40, 55, 70][:n_columns]
    entries = pd.DataFrame(False, index=idx, columns=steps)
    exits = pd.DataFrame(False, index=idx, columns=steps)
    for step in steps:
        for i in range(len(idx)):
            if in_window[i] and i % step == 0 and i + 20 <= last_in_window:
                entries.iloc[i, entries.columns.get_loc(step)] = True
                exits.iloc[i + 20, exits.columns.get_loc(step)] = True

    close_mc = pd.DataFrame({step: close.values for step in steps}, index=idx)
    return vbt.PF.from_signals(
        close=close_mc,
        entries=entries,
        exits=exits,
        open=close * 0.999,
        high=close * 1.004,
        low=close * 0.996,
        freq='1h',
        init_cash=100,
        size=100,
        size_type='value',
        fees=0.001,
    )


def _same_value(left, right) -> bool:
    """Vergleicht zwei Kennzahl-Werte exakt (NaN und None inbegriffen)."""
    if left is None or right is None:
        return left is right
    if isinstance(left, float) and isinstance(right, float):
        if math.isnan(left) and math.isnan(right):
            return True
    return left == right


def test_full_selection_matches_the_call_without_selection():
    """Die volle Gruppenmenge liefert exakt dasselbe wie der Aufruf ohne Angabe."""
    pf = _portfolio()
    columns = pf.wrapper.columns

    default_records = _extract_metrics(pf, columns, _config())
    full_records = _extract_metrics(pf, columns, _config(), groups=ALL_GROUPS)

    assert len(default_records) == len(full_records) == len(columns)
    for default, full in zip(default_records, full_records):
        assert set(default) == set(ALL_METRIC_FIELDS)
        assert set(full) == set(ALL_METRIC_FIELDS)
        for field in ALL_METRIC_FIELDS:
            assert _same_value(default[field], full[field]), f"{field} weicht ab"


def test_core_selection_omits_the_tail_risk_fields_and_changes_nothing_else():
    """`kern` liefert die drei teuren Felder nicht — die übrigen Werte bleiben gleich."""
    pf = _portfolio()
    columns = pf.wrapper.columns

    full_records = _extract_metrics(pf, columns, _config(), groups=ALL_GROUPS)
    core_records = _extract_metrics(
        pf, columns, _config(), groups=resolve_metric_groups('kern')
    )

    for full, core in zip(full_records, core_records):
        for field in METRIC_GROUPS['tail_risk']:
            assert field not in core
        assert set(core) == set(ALL_METRIC_FIELDS) - set(METRIC_GROUPS['tail_risk'])
        for field in core:
            assert _same_value(full[field], core[field]), f"{field} weicht ab"


def test_smallest_selection_yields_exactly_the_mandatory_fields():
    """Die leere Liste rechnet genau die Pflichtgruppen — nicht mehr, nicht weniger."""
    pf = _portfolio()
    columns = pf.wrapper.columns

    full_records = _extract_metrics(pf, columns, _config(), groups=ALL_GROUPS)
    lean_records = _extract_metrics(
        pf, columns, _config(), groups=resolve_metric_groups([])
    )

    expected = set(fields_for_groups([]))
    for full, lean in zip(full_records, lean_records):
        assert set(lean) == expected
        for field in skipped_fields(REQUIRED_GROUPS):
            assert field not in lean
        for field in lean:
            assert _same_value(full[field], lean[field]), f"{field} weicht ab"


def test_smallest_selection_keeps_the_deflated_sharpe_inputs():
    """Auch die schmalste Auswahl trägt die vier Bausteine des DSR-Nachlaufs."""
    pf = _portfolio()
    lean = _extract_metrics(
        pf, pf.wrapper.columns, _config(), groups=resolve_metric_groups([])
    )[0]

    for field in ('sharpe_ratio', 'skew', 'kurtosis', 'bar_count'):
        assert lean[field] is not None


def test_selecting_a_single_optional_group_adds_only_that_group():
    """Eine einzelne abwählbare Gruppe kommt zu den Pflichtgruppen hinzu."""
    pf = _portfolio()
    records = _extract_metrics(
        pf, pf.wrapper.columns, _config(), groups=resolve_metric_groups(['drawdown'])
    )

    assert set(records[0]) == set(fields_for_groups(['drawdown']))
    assert 'max_drawdown_pct' in records[0]
    assert 'max_drawdown_duration' in records[0]
    assert 'sqn' not in records[0]
    assert 'alpha' not in records[0]


def test_unknown_group_key_raises():
    """Ein unbekannter Gruppen-Key bricht die Extraktion ab."""
    pf = _portfolio()
    with pytest.raises(ValueError, match='Unbekannte Metrik-Gruppe'):
        _extract_metrics(pf, pf.wrapper.columns, _config(), groups=['gibtsnicht'])


def test_single_combination_selection_behaves_like_the_multi_column_case():
    """Auch mit einer einzelnen Kombination greift die Auswahl gleich.

    Skalar statt Series ist der Sonderfall, an dem der Zusammenbau schon einmal
    auseinandergelaufen ist.
    """
    pf = _portfolio(n_columns=1)
    columns = pf.wrapper.columns

    full = _extract_metrics(pf, columns, _config(), groups=ALL_GROUPS)[0]
    core = _extract_metrics(pf, columns, _config(), groups=resolve_metric_groups('kern'))[0]

    assert set(full) == set(ALL_METRIC_FIELDS)
    assert set(core) == set(ALL_METRIC_FIELDS) - set(METRIC_GROUPS['tail_risk'])
    for field in core:
        assert _same_value(full[field], core[field]), f"{field} weicht ab"

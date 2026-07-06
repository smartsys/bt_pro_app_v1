"""Tests für Audit-Befund 2 (2026-07-06): '!=' darf bei NaN-Operanden kein Signal liefern.

IEEE-Semantik: NaN != x ist True, alle anderen Vergleiche mit NaN sind False.
Ohne Gegenmaßnahme erzeugt eine '!='-Condition während der Indikator-Warmup-Phase
(Wert=NaN) an jeder Kerze ein Phantom-Signal.

Prüft beide Rechenpfade:
  1. pandas-Pfad (_evaluate_rule_group, deckt Masken-Pfad + statische Masken des
     nativen Pfads ab): NaN-Warmup → Maske False, gültige Werte → Maske korrekt.
  2. Numba-Pfad (stateful Exit-Conditions): NaN-Series-Operand mit '!=' feuert
     keinen Exit; gültige Werte feuern weiterhin.

Methodik: deterministischer OHLCV-DataFrame, Fake-Indikator mit NaN-Warmup (kein Mock
der Engine selbst).
"""

import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import numpy as np
import pandas as pd
import pytest

from user_data.strategies.generic.rules_engine import (
    _evaluate_rule_group,
    evaluate_rules_native,
)


# ============================================================================
# Fixtures / Hilfsmittel
# ============================================================================

WARMUP = 20  # Balken mit NaN am Serienanfang


class _OhlcWrapper:
    """Minimaler ohlc_data-Wrapper: implementiert .get(key) für OHLCV-Spalten."""

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def get(self, key: str) -> pd.Series:
        return self._df[key]


class _FakeIndicator:
    """Minimale Indikator-Instanz mit einem Output 'value'."""

    output_names = ('value',)
    param_names = ()
    short_name = 'fake'

    def __init__(self, series: pd.Series) -> None:
        self.value = series


def _make_ohlc_df(n: int = 120) -> pd.DataFrame:
    """Deterministischer OHLCV-DataFrame (close steigt linear von 90 auf 150)."""
    idx = pd.date_range("2022-01-01", periods=n, freq="1h")
    close = np.linspace(90.0, 150.0, n)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": np.arange(n, dtype=float),
        },
        index=idx,
    )


def _warmup_series(idx: pd.Index, value: float = 2.0) -> pd.Series:
    """Series mit NaN in den ersten WARMUP Balken, danach konstant `value`."""
    vals = np.full(len(idx), value)
    vals[:WARMUP] = np.nan
    return pd.Series(vals, index=idx, name='value')


@pytest.fixture
def ohlc_df() -> pd.DataFrame:
    return _make_ohlc_df(120)


@pytest.fixture
def ohlc_data(ohlc_df: pd.DataFrame) -> _OhlcWrapper:
    return _OhlcWrapper(ohlc_df)


def _make_pf_kwargs(ohlc_df: pd.DataFrame) -> dict:
    """Minimale pf_kwargs für evaluate_rules_native."""
    return {
        'close': ohlc_df['Close'],
        'open': ohlc_df['Open'],
        'high': ohlc_df['High'],
        'low': ohlc_df['Low'],
        'fees': 0.0,
        'tp_stop': None,
        'sl_stop': None,
        'tsl_th': None,
        'tsl_stop': None,
        'freq': '1h',
        'init_cash': 10_000.0,
        'size': 1.0,
        'size_type': 'amount',
        'td_stop': None,
        'delta_format': None,
        'time_delta_format': None,
        'stop_exit_price': None,
        'stop_order_type': None,
        'chunked': False,
    }


def _cond(lhs, op, rhs, lhs_shift: int = 0, rhs_shift: int = 0) -> dict:
    """Baut eine Condition im Engine-Format."""
    return {'lhs': lhs, 'lhs_shift': lhs_shift, 'op': op, 'rhs': rhs, 'rhs_shift': rhs_shift}


# ============================================================================
# 1. pandas-Pfad: NaN-Warmup erzeugt bei '!=' keine Maske
# ============================================================================

class TestPandasPathNeqNan:
    """'!='-Maske ist während des NaN-Warmups False, danach korrekt."""

    def test_neq_false_during_warmup(self, ohlc_data, ohlc_df):
        """NaN != 1.0 muss False sein (kein Phantom-Signal im Warmup)."""
        indicators = {'ind': _FakeIndicator(_warmup_series(ohlc_df.index, value=2.0))}
        mask = _evaluate_rule_group(
            {'blocks': [{'conditions': [_cond('indicator:ind:value', '!=', 1.0)]}]},
            ohlc_data,
            indicators,
        )
        assert not mask.iloc[:WARMUP].any(), (
            "'!=' darf während der NaN-Warmup-Phase keine Signale erzeugen"
        )
        assert mask.iloc[WARMUP:].all(), (
            "'!=' muss auf gültigen Werten (2.0 != 1.0) weiterhin True liefern"
        )

    def test_neq_still_false_on_equal_values(self, ohlc_data, ohlc_df):
        """Gültige gleiche Werte (2.0 != 2.0) bleiben False — keine Überkorrektur."""
        indicators = {'ind': _FakeIndicator(_warmup_series(ohlc_df.index, value=2.0))}
        mask = _evaluate_rule_group(
            {'blocks': [{'conditions': [_cond('indicator:ind:value', '!=', 2.0)]}]},
            ohlc_data,
            indicators,
        )
        assert not mask.any(), "2.0 != 2.0 muss überall False sein (NaN-Warmup inklusive)"

    def test_neq_between_two_series(self, ohlc_data, ohlc_df):
        """NaN auf einer der beiden Seiten eines Series-Vergleichs → False."""
        indicators = {
            'a': _FakeIndicator(_warmup_series(ohlc_df.index, value=2.0)),
            'b': _FakeIndicator(pd.Series(1.0, index=ohlc_df.index, name='value')),
        }
        mask = _evaluate_rule_group(
            {'blocks': [{'conditions': [_cond('indicator:a:value', '!=', 'indicator:b:value')]}]},
            ohlc_data,
            indicators,
        )
        assert not mask.iloc[:WARMUP].any(), "NaN != Series muss False sein"
        assert mask.iloc[WARMUP:].all(), "2.0 != 1.0 muss True bleiben"


# ============================================================================
# 2. Nativer Pfad, statische Entry-Regeln: kein Entry im Warmup
# ============================================================================

class TestNativeEntryNeqNan:
    """Entry-Regel mit '!=' auf Warmup-NaN-Indikator: erster Entry erst nach Warmup."""

    def test_first_entry_after_warmup(self, ohlc_data, ohlc_df):
        """Entry 'indicator != 1.0' → erster Trade frühestens am ersten gültigen Balken."""
        indicators = {'ind': _FakeIndicator(_warmup_series(ohlc_df.index, value=2.0))}
        rules = {
            'entry': {'blocks': [{'conditions': [_cond('indicator:ind:value', '!=', 1.0)]}]},
            'exit': None,
        }
        pf = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators=indicators,
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        entry_idx = pf.trades.records['entry_idx']
        assert len(entry_idx) > 0, "Auf gültigen Werten muss ein Entry entstehen"
        assert entry_idx.min() >= WARMUP, (
            f"Erster Entry bei Balken {entry_idx.min()}, erwartet >= {WARMUP} "
            f"(kein Phantom-Entry in der NaN-Warmup-Phase)"
        )


# ============================================================================
# 3. Numba-Pfad (stateful Exits): NaN-Series-Operand mit '!=' feuert keinen Exit
# ============================================================================

class TestNumbaStatefulNeqNan:
    """Stateful Exit-Block mit '!='-Series-Condition auf NaN-Indikator."""

    def test_nan_series_neq_fires_no_exit(self, ohlc_data, ohlc_df):
        """Indikator komplett NaN → '!= 999' darf keinen Exit auslösen
        (Verhalten identisch zu exit: null)."""
        nan_series = pd.Series(np.nan, index=ohlc_df.index, name='value')
        indicators = {'ind': _FakeIndicator(nan_series)}
        rules_nan_exit = {
            'entry': {'blocks': [{'conditions': [_cond('close', '<', 110.0)]}]},
            'exit': {
                'blocks': [
                    {
                        'conditions': [
                            _cond('since_entry', '>=', 1),
                            _cond('indicator:ind:value', '!=', 999.0),
                        ]
                    }
                ]
            },
        }
        rules_no_exit = {
            'entry': {'blocks': [{'conditions': [_cond('close', '<', 110.0)]}]},
            'exit': None,
        }
        pf_nan_exit = evaluate_rules_native(
            rules_json=rules_nan_exit,
            ohlc_data=ohlc_data,
            indicators=indicators,
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        pf_no_exit = evaluate_rules_native(
            rules_json=rules_no_exit,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        assert len(pf_nan_exit.trades.records) == len(pf_no_exit.trades.records), (
            "'!=' auf NaN-Indikator muss sich identisch zu exit: null verhalten "
            "(kein Phantom-Exit)"
        )
        assert (
            pf_nan_exit.trades.records['exit_idx'].tolist()
            == pf_no_exit.trades.records['exit_idx'].tolist()
        ), "Exit-Zeitpunkte müssen identisch zu exit: null sein"

    def test_valid_series_neq_still_fires_exit(self, ohlc_data, ohlc_df):
        """Gültiger Indikator (5.0) → '!= 999' feuert weiterhin (keine Überkorrektur)."""
        valid_series = pd.Series(5.0, index=ohlc_df.index, name='value')
        indicators = {'ind': _FakeIndicator(valid_series)}
        rules = {
            'entry': {'blocks': [{'conditions': [_cond('close', '<', 110.0)]}]},
            'exit': {
                'blocks': [
                    {
                        'conditions': [
                            _cond('since_entry', '>=', 1),
                            _cond('indicator:ind:value', '!=', 999.0),
                        ]
                    }
                ]
            },
        }
        pf = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators=indicators,
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        records = pf.trades.records
        assert len(records) > 0, "Es müssen Trades entstehen"
        first = records.iloc[0]
        assert first['exit_idx'] == first['entry_idx'] + 1, (
            "Auf gültigen Werten muss der '!='-Exit auf der Folgekerze feuern"
        )

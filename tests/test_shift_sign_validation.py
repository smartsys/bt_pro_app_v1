"""Tests für die Vorzeichen-Absicherung von lhs_shift/rhs_shift.

Ein negativer Shift (series.shift(-n)) zöge den Wert einer Zukunftskerze auf die
aktuelle Kerze — nicht-kausaler Lookahead. In einem kausalen Backtest gibt es
dafür keinen legitimen Fall (eine Prognose lebt bereits auf der aktuellen Kerze
und wird mit Shift 0 gelesen).

Zwei Verteidigungslinien werden geprüft:
  1. Speicher-Klemmung (Choke-Point repository_strategies._clamp_negative_shifts):
     negativer Shift im spec_json wird beim Speichern auf 0 gesetzt; positive und
     fehlende Shifts bleiben unverändert.
  2. Engine-Backstop (rules_engine): beide Rechenpfade weisen einen negativen
     Shift zur Laufzeit mit ValueError ab —
       a) pandas-Pfad (_evaluate_rule_group, deckt Masken-Pfad + statische Masken
          des nativen Pfads ab),
       b) nativer statischer Entry-Pfad (evaluate_rules_native),
       c) nativer stateful Exit-Pfad (Series-Operand einer stateful Condition).
     Gegenprobe: Shift 0 und positiver Shift laufen normal durch.

Methodik: deterministischer OHLCV-DataFrame, Fake-Indikator (kein Mock der Engine).
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
from user_data.utils.database.repository_strategies import _clamp_negative_shifts


# ============================================================================
# Fixtures / Hilfsmittel
# ============================================================================

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


@pytest.fixture
def ohlc_df() -> pd.DataFrame:
    return _make_ohlc_df(120)


@pytest.fixture
def ohlc_data(ohlc_df: pd.DataFrame) -> _OhlcWrapper:
    return _OhlcWrapper(ohlc_df)


# ============================================================================
# 1. Speicher-Klemmung (_clamp_negative_shifts)
# ============================================================================

class TestClampNegativeShifts:
    """Der Choke-Point setzt negative Shifts beim Speichern auf 0."""

    def test_negative_shifts_clamped_to_zero(self):
        """lhs_shift/rhs_shift < 0 werden in entry und exit auf 0 geklemmt."""
        spec = {
            'indicators': {},
            'rules': {
                'entry': {'blocks': [{'conditions': [
                    _cond('close', '>', 'indicator:x:value', lhs_shift=-1, rhs_shift=-3),
                ]}]},
                'exit': {'blocks': [{'conditions': [
                    _cond('close', '<', 100.0, lhs_shift=-2),
                ]}]},
            },
        }
        _clamp_negative_shifts(spec)
        entry_cond = spec['rules']['entry']['blocks'][0]['conditions'][0]
        exit_cond = spec['rules']['exit']['blocks'][0]['conditions'][0]
        assert entry_cond['lhs_shift'] == 0
        assert entry_cond['rhs_shift'] == 0
        assert exit_cond['lhs_shift'] == 0

    def test_positive_and_zero_shifts_untouched(self):
        """Positive und Null-Shifts bleiben unverändert (keine Überkorrektur)."""
        spec = {
            'indicators': {},
            'rules': {
                'entry': {'blocks': [{'conditions': [
                    _cond('close', '>', 100.0, lhs_shift=2, rhs_shift=0),
                ]}]},
                'exit': None,
            },
        }
        _clamp_negative_shifts(spec)
        entry_cond = spec['rules']['entry']['blocks'][0]['conditions'][0]
        assert entry_cond['lhs_shift'] == 2
        assert entry_cond['rhs_shift'] == 0

    def test_missing_rules_is_noop(self):
        """spec_json ohne rules (oder None) darf nicht crashen."""
        _clamp_negative_shifts(None)
        _clamp_negative_shifts({})
        _clamp_negative_shifts({'indicators': {}})  # kein 'rules'-Key


# ============================================================================
# 2a. Engine-Backstop: pandas-Pfad
# ============================================================================

class TestPandasPathShift:
    """_evaluate_rule_group weist negative Shifts ab, lässt positive durch."""

    def test_negative_lhs_shift_raises(self, ohlc_data):
        with pytest.raises(ValueError, match="Shift"):
            _evaluate_rule_group(
                {'blocks': [{'conditions': [_cond('close', '>', 100.0, lhs_shift=-1)]}]},
                ohlc_data,
                {},
            )

    def test_negative_rhs_shift_raises(self, ohlc_data):
        with pytest.raises(ValueError, match="Shift"):
            _evaluate_rule_group(
                {'blocks': [{'conditions': [_cond('close', '>', 'open', rhs_shift=-2)]}]},
                ohlc_data,
                {},
            )

    def test_positive_shift_runs(self, ohlc_data):
        """Positiver Shift (Blick zurück) ist kausal und läuft normal durch."""
        mask = _evaluate_rule_group(
            {'blocks': [{'conditions': [_cond('close', '>', 'open', lhs_shift=1)]}]},
            ohlc_data,
            {},
        )
        assert mask.dtype == bool
        assert len(mask) == 120


# ============================================================================
# 2b. Engine-Backstop: nativer statischer Entry-Pfad
# ============================================================================

class TestNativeEntryShift:
    """evaluate_rules_native weist einen negativen Entry-Shift ab."""

    def test_negative_entry_shift_raises(self, ohlc_data, ohlc_df):
        rules = {
            'entry': {'blocks': [{'conditions': [_cond('close', '<', 130.0, lhs_shift=-1)]}]},
            'exit': None,
        }
        with pytest.raises(ValueError, match="Shift"):
            evaluate_rules_native(
                rules_json=rules,
                ohlc_data=ohlc_data,
                indicators={},
                pf_kwargs=_make_pf_kwargs(ohlc_df),
            )

    def test_positive_entry_shift_runs(self, ohlc_data, ohlc_df):
        """Positiver Entry-Shift läuft und erzeugt ein Portfolio."""
        rules = {
            'entry': {'blocks': [{'conditions': [_cond('close', '<', 130.0, lhs_shift=1)]}]},
            'exit': None,
        }
        pf = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        assert len(pf.trades.records) > 0


# ============================================================================
# 2c. Engine-Backstop: nativer stateful Exit-Pfad
# ============================================================================

class TestNativeStatefulShift:
    """Series-Operand einer stateful Exit-Condition mit negativem Shift wird abgewiesen."""

    def test_negative_stateful_series_shift_raises(self, ohlc_data, ohlc_df):
        """since_entry >= <indicator mit rhs_shift=-1> → ValueError im Spec-Bau."""
        indicators = {'ind': _FakeIndicator(pd.Series(5.0, index=ohlc_df.index, name='value'))}
        rules = {
            'entry': {'blocks': [{'conditions': [_cond('close', '<', 110.0)]}]},
            'exit': {'blocks': [{'conditions': [
                _cond('since_entry', '>=', 'indicator:ind:value', rhs_shift=-1),
            ]}]},
        }
        with pytest.raises(ValueError, match="Shift"):
            evaluate_rules_native(
                rules_json=rules,
                ohlc_data=ohlc_data,
                indicators=indicators,
                pf_kwargs=_make_pf_kwargs(ohlc_df),
            )

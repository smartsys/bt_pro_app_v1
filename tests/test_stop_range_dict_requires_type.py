"""Tests für die Abweisung eines fehlgeformten Wertebereichs in '_stops'.

Ein Wertebereich wird als arange-Dict mit dem Schlüssel ``type`` geschrieben. Ein
Dict mit ``start``/``stop``/``step``, aber ohne ``type``, ist kein Wertebereich —
es wurde bisher still als Skalar an ``from_signals`` durchgereicht und riss den
Lauf erst tief in VBT ab. Geprüft wird:

  1. Abweisung: Der Lauf bricht mit Klartext ab — Stop-Schlüssel, vorgefundener
     Wert und die gültige Schreibweise stehen in der Meldung.
  2. Gemeinsame Stelle: Derselbe Riegel greift auch in der Kombinationszählung
     und im Chunking, nicht nur an einer einzelnen Aufrufstelle.
  3. Keine Nebenwirkung: arange-Dict, Indikator-Referenz, Skalar und ``null``
     laufen unverändert durch.
  4. Sicherheitsriegel: Zusammen mit ``size_type: 'risk_percent'`` bzw. einem
     Block-Hebel ungleich 1 bricht der Lauf mit der neuen Meldung ab — nicht mit
     einer VBT-internen und nicht still.
  5. Indikator-Parameter: Dieselbe fehlgeformte Schreibweise an einem
     Indikator-Parameter nennt ebenfalls die gültige Schreibweise.

Methodik wie in ``test_stop_indicator_reference.py``: deterministische OHLCV-Reihe,
echter Spec-Runner, kein Mocking.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import vectorbtpro as vbt

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from user_data.strategies.generic.indicator_factory import (  # noqa: E402
    _collect_varying_axes,
    count_stop_combos,
    count_total_combos,
    is_stop_sweep,
    split_indicators_json_chunks,
)
from user_data.strategies.generic.spec_runner import run_spec_strategy  # noqa: E402


# Der fehlgeformte Wert aus dem Ticket: sieht wie ein Wertebereich aus, trägt aber
# kein 'type'.
_MALFORMED = {'start': 0.01, 'stop': 0.03, 'step': 0.01}

# Derselbe Bereich in der gültigen Schreibweise — arange(0.01, 0.031, 0.01) = 3 Werte.
_VALID = {'type': 'arange', 'start': 0.01, 'stop': 0.031, 'step': 0.01,
          'dtype': 'float64'}

_BASE_PORTFOLIO = {
    'fees': 0.0,
    'init_cash': 10_000.0,
    'size': 1.0,
    'size_type': 'amount',
}

_RULES = {
    'entry': {
        'blocks': [
            {
                'conditions': [
                    {'lhs': 'close', 'lhs_shift': 0, 'op': '>',
                     'rhs': 'indicator:sma_trend:real', 'rhs_shift': 0}
                ]
            }
        ]
    },
}


def _make_ohlc_data(n: int = 600) -> vbt.Data:
    """Deterministische OHLCV-Reihe mit abwechselnd ruhigen und bewegten Abschnitten."""
    rng = np.random.default_rng(107)
    idx = pd.date_range('2023-01-01', periods=n, freq='1h', tz='UTC')
    volatility = np.where((np.arange(n) // 120) % 2 == 0, 0.20, 1.10)
    steps = rng.normal(0, 1, n) * volatility
    close = 300.0 + np.cumsum(steps)
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 1, n)) * volatility
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 1, n)) * volatility
    df = pd.DataFrame(
        {'Open': open_, 'High': high, 'Low': low, 'Close': close,
         'Volume': np.full(n, 1000.0)},
        index=idx,
    )
    data = vbt.Data.from_data({'X': df})
    data.use_feature_config_of(vbt.BinanceData)
    return data


def _indicators(stops: dict) -> dict:
    """Spec mit ATR (für Referenz-Stops) und SMA (Entry-Bedingung) plus '_stops'."""
    return {
        'atr_ref': {'indicator': 'talib:ATR', 'tf': 'same', 'timeperiod': 14},
        'sma_trend': {'indicator': 'talib:SMA', 'tf': 'same', 'timeperiod': 20},
        '_stops': stops,
    }


def _config(**portfolio) -> dict:
    return {
        'timeframe': '1h',
        'start': '2023-01-02',
        'end': '2023-01-25',
        'portfolio': {**_BASE_PORTFOLIO, **portfolio},
        '_disable_chunked': True,
    }


def _run(indicators_json: dict, data, config: dict = None, rules: dict = None) -> dict:
    return run_spec_strategy(
        ohlc_data=data,
        indicators_json=indicators_json,
        backtest_config_json=config or _config(),
        rules_json=rules or _RULES,
    )


def _n_columns(result: dict) -> int:
    """Spaltenzahl des gelaufenen Portfolios."""
    shape = result['portfolios'].wrapper.shape
    return 1 if len(shape) == 1 else shape[1]


@pytest.fixture(scope='module')
def ohlc_data():
    return _make_ohlc_data()


# ============================================================================
# 1. Abweisung mit Klartext
# ============================================================================

class TestMalformedStopRangeIsRejected:
    """Ein Dict ohne 'type' wird beim Lauf mit Klartext abgewiesen."""

    def test_the_message_names_key_value_and_valid_notation(self, ohlc_data):
        with pytest.raises(ValueError) as exc:
            _run(_indicators({'sl_stop': dict(_MALFORMED),
                              'delta_format': 'percent'}), ohlc_data)
        message = str(exc.value)
        assert "'sl_stop'" in message
        assert "'start': 0.01" in message and "'step': 0.01" in message
        assert "type" in message and "arange" in message

    def test_every_stop_field_is_covered(self, ohlc_data):
        for stop_key in ('tp_stop', 'sl_stop', 'tsl_th', 'tsl_stop', 'td_stop'):
            with pytest.raises(ValueError) as exc:
                _run(_indicators({stop_key: dict(_MALFORMED)}), ohlc_data)
            assert f"{stop_key!r}" in str(exc.value)


# ============================================================================
# 2. Der Riegel sitzt an der gemeinsam genutzten Stelle
# ============================================================================

class TestGuardSitsOnTheSharedPath:
    """Jeder Weg, der einen Stop-Wert einordnet, geht durch denselben Riegel."""

    def test_the_classifier_itself_rejects_the_value(self):
        with pytest.raises(ValueError) as exc:
            is_stop_sweep(dict(_MALFORMED), 'sl_stop')
        assert "arange" in str(exc.value)

    def test_the_combination_count_rejects_the_value(self):
        with pytest.raises(ValueError):
            count_stop_combos({'sl_stop': dict(_MALFORMED)})
        with pytest.raises(ValueError):
            count_total_combos(_indicators({'sl_stop': dict(_MALFORMED)}))

    def test_the_chunking_rejects_the_value(self):
        with pytest.raises(ValueError):
            split_indicators_json_chunks(
                _indicators({'sl_stop': dict(_MALFORMED)}), chunk_size=2
            )


# ============================================================================
# 3. Gültige Formen laufen unverändert
# ============================================================================

class TestValidStopFormsStillRun:
    """arange-Dict, Indikator-Referenz, Skalar und null bleiben unberührt."""

    def test_the_same_range_with_type_arange_produces_three_stop_combinations(
        self, ohlc_data
    ):
        indicators_json = _indicators({'sl_stop': dict(_VALID),
                                       'delta_format': 'percent'})
        assert count_stop_combos(indicators_json['_stops']) == 3
        assert count_total_combos(indicators_json) == 3
        result = _run(indicators_json, ohlc_data)
        assert _n_columns(result) == 3

    def test_a_stop_indicator_reference_passes_unchanged(self, ohlc_data):
        indicators_json = _indicators({
            'sl_stop': {'ref': 'indicator:atr_ref:real', 'mult': 5.0},
            'delta_format': 'absolute',
        })
        assert is_stop_sweep(indicators_json['_stops']['sl_stop'], 'sl_stop') is False
        assert count_total_combos(indicators_json) == 1
        result = _run(indicators_json, ohlc_data)
        assert _n_columns(result) == 1

    def test_a_scalar_stop_and_null_pass_unchanged(self, ohlc_data):
        indicators_json = _indicators({'sl_stop': 0.02, 'tp_stop': None,
                                       'delta_format': 'percent'})
        assert count_total_combos(indicators_json) == 1
        result = _run(indicators_json, ohlc_data)
        assert _n_columns(result) == 1


# ============================================================================
# 4. Die Sicherheitsriegel schweigen nicht mehr
# ============================================================================

class TestRiskSizingAndBlockLeverageDoNotStayQuiet:
    """Beide Riegel hängen an der Sweep-Erkennung — der Lauf bricht sichtbar ab."""

    _NEEDLE = "arange"

    def test_risk_percent_sizing_aborts_with_the_new_message(self, ohlc_data):
        with pytest.raises(ValueError) as exc:
            _run(
                _indicators({'sl_stop': dict(_MALFORMED), 'delta_format': 'percent'}),
                ohlc_data,
                _config(size_type='risk_percent', risk_pct=0.01),
            )
        message = str(exc.value)
        assert "'sl_stop'" in message
        assert self._NEEDLE in message

    def test_a_block_leverage_aborts_with_the_new_message(self, ohlc_data):
        rules = {
            'entry': {
                'blocks': [
                    {**_RULES['entry']['blocks'][0], 'leverage': 3.0}
                ]
            }
        }
        with pytest.raises(ValueError) as exc:
            _run(
                _indicators({'sl_stop': dict(_MALFORMED), 'delta_format': 'percent'}),
                ohlc_data,
                _config(),
                rules,
            )
        message = str(exc.value)
        assert "'sl_stop'" in message
        assert self._NEEDLE in message


# ============================================================================
# 5. Indikator-Parameter
# ============================================================================

class TestMalformedIndicatorParameterRange:
    """Derselbe Fehler an einem Indikator-Parameter nennt die gültige Schreibweise."""

    def test_the_message_names_indicator_parameter_and_valid_notation(self, ohlc_data):
        indicators_json = _indicators({'sl_stop': 0.02, 'delta_format': 'percent'})
        indicators_json['sma_trend']['timeperiod'] = {'start': 10, 'stop': 30, 'step': 10}
        with pytest.raises(ValueError) as exc:
            _run(indicators_json, ohlc_data)
        message = str(exc.value)
        assert "'sma_trend'" in message and "'timeperiod'" in message
        assert "type" in message and "arange" in message


# ============================================================================
# 6. Doku am Code
# ============================================================================

class TestVaryingAxesDocstringMatchesTheCode:
    """Der Docstring darf keine Schreibweise nennen, die der Code abweist."""

    def test_the_docstring_names_the_notation_the_code_requires(self):
        doc = _collect_varying_axes.__doc__
        assert '{start, stop, step}' not in doc
        assert 'arange' in doc and "'type'" in doc

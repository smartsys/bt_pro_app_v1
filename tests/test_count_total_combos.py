"""Unit-Tests für die einzige Zähl-Wahrheit: describe_combos / count_total_combos.

Prüft, dass die Kombinationszählung exakt das abbildet, was der Motor läuft:
  - Range-Achsen ({type: arange, start, stop, step}) über ceil
  - Listen-Achsen ([a, b, c]) zählen mit (nicht als Skalar = 1)
  - deaktivierte Indikatoren zählen nicht
  - Stops multiplizieren; das gekoppelte TSL-Paar zählt als EINE Achse
  - TSL-Paar-Längen-Mismatch wirft ValueError
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from user_data.strategies.generic.indicator_factory import (
    count_total_combos,
    describe_combos,
)

# 'source' ist ein Input (zählt nie), 'length'/'multiplier' sind Parameter.
_FACTORY_MOCK = MagicMock()
_FACTORY_MOCK.input_names = ('source',)
_FACTORY_MOCK.param_names = ('length', 'multiplier')

_PATCH_TARGET = 'user_data.strategies.generic.indicator_factory.resolve_indicator_factory'


def _arange(start, stop, step, dtype='int64'):
    return {'type': 'arange', 'start': start, 'stop': stop, 'step': step, 'dtype': dtype}


def test_range_axes_product():
    """Zwei Range-Achsen multiplizieren über ceil((stop-start)/step)."""
    cfg = {
        'sma': {
            'indicator': 'custom:SMA', 'tf': '4h', 'source': 'close',
            'length': _arange(2, 14.01, 1),      # 13 Werte
            'multiplier': _arange(1, 9.01, 1),   # 9 Werte
        }
    }
    with patch(_PATCH_TARGET, return_value=_FACTORY_MOCK):
        assert count_total_combos(cfg) == 13 * 9


def test_list_axis_counted():
    """Eine Listen-Achse [a, b, c] zählt mit ihrer Länge — nicht als Skalar."""
    cfg = {
        'sma': {
            'indicator': 'custom:SMA', 'tf': '4h', 'source': 'close',
            'length': _arange(2, 14.01, 1),   # 13 Werte
            'multiplier': [1, 3, 5, 7],       # 4 Werte (Liste)
        }
    }
    with patch(_PATCH_TARGET, return_value=_FACTORY_MOCK):
        assert count_total_combos(cfg) == 13 * 4


def test_scalar_axis_is_one():
    """Skalare Parameter zählen als 1 (keine Achse)."""
    cfg = {
        'sma': {
            'indicator': 'custom:SMA', 'tf': '4h', 'source': 'close',
            'length': 14,        # Skalar
            'multiplier': [1, 2],  # 2 Werte
        }
    }
    with patch(_PATCH_TARGET, return_value=_FACTORY_MOCK):
        assert count_total_combos(cfg) == 2


def test_disabled_indicator_skipped():
    """Deaktivierte Indikatoren tragen keine Achse bei."""
    cfg = {
        'sma': {
            'indicator': 'custom:SMA', 'tf': '4h', 'source': 'close',
            'enabled': False,
            'length': [10, 20, 30, 40, 50],
        }
    }
    with patch(_PATCH_TARGET, return_value=_FACTORY_MOCK):
        assert count_total_combos(cfg) == 1


def test_independent_stops_multiply():
    """Unabhängige Stop-Sweeps (tp/sl) multiplizieren mit den Indikator-Achsen."""
    cfg = {
        'sma': {
            'indicator': 'custom:SMA', 'tf': '4h', 'source': 'close',
            'length': [10, 20, 30],  # 3 Werte
        },
        '_stops': {
            'tp_stop': _arange(0.01, 0.051, 0.01, dtype='float64'),  # 5 Werte
            'sl_stop': 0.15,  # Skalar
        },
    }
    with patch(_PATCH_TARGET, return_value=_FACTORY_MOCK):
        assert count_total_combos(cfg) == 3 * 5


def test_tsl_pair_counts_as_one_axis():
    """Gekoppeltes TSL-Paar (tsl_th + tsl_stop) zählt als EINE Achse (zip), kein Kreuzprodukt."""
    cfg = {
        'sma': {
            'indicator': 'custom:SMA', 'tf': '4h', 'source': 'close',
            'length': [10, 20, 30],  # 3 Werte
        },
        '_stops': {
            'tsl_th': _arange(0.01, 0.051, 0.01, dtype='float64'),    # 5 Werte
            'tsl_stop': _arange(0.02, 0.061, 0.01, dtype='float64'),  # 5 Werte
        },
    }
    with patch(_PATCH_TARGET, return_value=_FACTORY_MOCK):
        # 3 * 5, NICHT 3 * 5 * 5
        assert count_total_combos(cfg) == 3 * 5


def test_tsl_pair_length_mismatch_raises():
    """Ungleich lange TSL-Paar-Achsen werfen einen klaren ValueError."""
    cfg = {
        '_stops': {
            'tsl_th': _arange(0.01, 0.051, 0.01, dtype='float64'),    # 5 Werte
            'tsl_stop': _arange(0.02, 0.041, 0.01, dtype='float64'),  # 3 Werte
        },
    }
    with patch(_PATCH_TARGET, return_value=_FACTORY_MOCK):
        with pytest.raises(ValueError, match='TSL'):
            count_total_combos(cfg)


def test_describe_combos_details():
    """describe_combos liefert Total plus benannte Achsen-Aufschlüsselung."""
    cfg = {
        'sma': {
            'indicator': 'custom:SMA', 'tf': '4h', 'source': 'close',
            'length': [10, 20, 30],  # 3 Werte
        },
        '_stops': {
            'tp_stop': _arange(0.01, 0.051, 0.01, dtype='float64'),  # 5 Werte
        },
    }
    with patch(_PATCH_TARGET, return_value=_FACTORY_MOCK):
        result = describe_combos(cfg)
    assert result['total'] == 3 * 5
    assert 'sma.length: 3' in result['details']
    assert '_stops.tp_stop: 5' in result['details']

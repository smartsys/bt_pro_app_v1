"""Tests für die Run-Start-Validierung der Rastergröße (Anforderung 3).

Stellt sicher, dass run_spec_strategy abbricht, wenn ein aktivierter (`enabled`)
Indikator eine variierende Sweep-Achse trägt, die über keine Erreichbarkeits-
Kette aus aktiven Chain-Referenzen in einer aktiven Regel endet — direkt oder
über beliebig viele Zwischen-Indikatoren, die selbst aktiviert sein müssen.
Eine Achse ohne diese Erreichbarkeit zählt sonst in
describe_combos/count_total_combos mit, ohne dass sich die Portfolio-Spalten
unterscheiden (kollidierender params_hash, still überschriebene Ergebnisse).
"""

from unittest.mock import MagicMock, patch

import pytest

from user_data.strategies.generic.spec_runner import _validate_swept_indicators_referenced

# 'source' ist ein Input (zählt nie als Sweep-Achse), 'length' ist ein Parameter.
_FACTORY_MOCK = MagicMock()
_FACTORY_MOCK.input_names = ('source',)
_FACTORY_MOCK.param_names = ('length',)

_PATCH_TARGET = 'user_data.strategies.generic.indicator_factory.resolve_indicator_factory'


def _entry_rule(lhs, op='>', rhs='close') -> dict:
    """Baut ein minimales rules_json mit einer Entry-Condition im Blocks-Format."""
    return {
        'entry': {'blocks': [{'conditions': [{'lhs': lhs, 'lhs_shift': 0, 'op': op, 'rhs': rhs, 'rhs_shift': 0}]}]},
        'exit': None,
    }


# ============================================================================
# Fehlerfall — gesweepter, unreferenzierter Indikator
# ============================================================================

def test_raises_when_swept_indicator_unused():
    """Aktivierter Indikator mit Sweep-Achse, in keiner Regel referenziert -> Abbruch mit Namen."""
    rules = _entry_rule('close', rhs='open')  # keine Indikator-Referenz
    indicators = {
        'rsi': {'indicator': 'custom:RSI', 'source': 'close', 'length': [10, 20]},
    }
    with patch(_PATCH_TARGET, return_value=_FACTORY_MOCK):
        with pytest.raises(ValueError) as exc:
            _validate_swept_indicators_referenced(rules, indicators)
    assert 'rsi' in str(exc.value)


# ============================================================================
# Gegenprobe — gesweepter Indikator, in Regel referenziert -> läuft durch
# ============================================================================

def test_passes_when_swept_indicator_referenced_in_rule():
    """Derselbe gesweepte Indikator, in einer Regel referenziert -> keine Exception."""
    rules = _entry_rule('indicator:rsi:real', rhs=0)
    indicators = {
        'rsi': {'indicator': 'custom:RSI', 'source': 'close', 'length': [10, 20]},
    }
    with patch(_PATCH_TARGET, return_value=_FACTORY_MOCK):
        _validate_swept_indicators_referenced(rules, indicators)


# ============================================================================
# Chain-Input zählt ebenfalls als Verwendung
# ============================================================================

def test_passes_when_swept_indicator_used_as_chain_input():
    """Ein gesweepter Indikator, der nur als Input eines anderen Indikators dient, ist benutzt."""
    rules = _entry_rule('indicator:signal:real', rhs=0)
    indicators = {
        'rsi': {'indicator': 'custom:RSI', 'source': 'close', 'length': [10, 20]},
        'signal': {'indicator': 'custom:SIGNAL', 'source': 'indicator:rsi:real', 'length': 5},
    }
    with patch(_PATCH_TARGET, return_value=_FACTORY_MOCK):
        _validate_swept_indicators_referenced(rules, indicators)


# ============================================================================
# Achsen, die den Guard NICHT auslösen
# ============================================================================

def test_disabled_indicator_not_flagged_even_when_swept_and_unused():
    """Ein deaktivierter Indikator (enabled: False) wird nie gemeldet."""
    rules = _entry_rule('close', rhs='open')
    indicators = {
        'rsi': {'indicator': 'custom:RSI', 'source': 'close', 'length': [10, 20], 'enabled': False},
    }
    with patch(_PATCH_TARGET, return_value=_FACTORY_MOCK):
        _validate_swept_indicators_referenced(rules, indicators)


def test_scalar_param_not_flagged_even_when_unused():
    """Ein Skalar-Parameter (keine Sweep-Achse) löst den Guard nie aus."""
    rules = _entry_rule('close', rhs='open')
    indicators = {
        'rsi': {'indicator': 'custom:RSI', 'source': 'close', 'length': 14},
    }
    with patch(_PATCH_TARGET, return_value=_FACTORY_MOCK):
        _validate_swept_indicators_referenced(rules, indicators)


# ============================================================================
# Erreichbarkeits-Schließung über mehrstufige Chains — Nachbesserung
# ============================================================================
# Eine flache "wird irgendwo als Chain-Input referenziert"-Prüfung würde eine
# Kette durchwinken, die selbst nirgends in einer aktiven Regel endet, oder
# deren haltendes Zwischenglied deaktiviert ist. Beides muss abgewiesen werden.

def _chained_indicators(slope_enabled: bool = True) -> dict:
    """Zwei-stufige Chain: sma_a (gesweept) -> slope_b (Skalar, konsumiert sma_a)."""
    return {
        'sma_a': {'indicator': 'custom:SMA', 'source': 'close', 'length': [5, 10, 15, 20]},
        'slope_b': {
            'indicator': 'custom:SLOPE', 'source': 'indicator:sma_a:real', 'length': 14,
            'enabled': slope_enabled,
        },
    }


def test_raises_when_chain_holder_itself_reaches_no_active_rule():
    """sma_a -> slope_b, aber weder sma_a noch slope_b landet in einer Regel -> Abbruch mit sma_a."""
    rules = _entry_rule('close', rhs='open')  # referenziert weder sma_a noch slope_b
    indicators = _chained_indicators(slope_enabled=True)
    with patch(_PATCH_TARGET, return_value=_FACTORY_MOCK):
        with pytest.raises(ValueError) as exc:
            _validate_swept_indicators_referenced(rules, indicators)
    assert 'sma_a' in str(exc.value)


def test_disabled_chain_holder_does_not_propagate_reachability_to_its_input():
    """slope_b ist referenziert, aber deaktiviert -> gibt die Referenz auf sma_a nicht weiter."""
    rules = _entry_rule('indicator:slope_b:real', rhs=0)
    indicators = _chained_indicators(slope_enabled=False)
    with patch(_PATCH_TARGET, return_value=_FACTORY_MOCK):
        with pytest.raises(ValueError) as exc:
            _validate_swept_indicators_referenced(rules, indicators)
    assert 'sma_a' in str(exc.value)


def test_passes_when_swept_indicator_reachable_through_active_chain_to_rule():
    """slope_b ist aktiviert und referenziert -> sma_a ist über die aktive Chain erreichbar."""
    rules = _entry_rule('indicator:slope_b:real', rhs=0)
    indicators = _chained_indicators(slope_enabled=True)
    with patch(_PATCH_TARGET, return_value=_FACTORY_MOCK):
        _validate_swept_indicators_referenced(rules, indicators)

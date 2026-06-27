"""Tests für die Run-Start-Validierung von Indikator-Referenzen (Ticket 34).

Stellt sicher, dass run_spec_strategy abbricht, wenn eine Entry-/Exit-Regel
einen deaktivierten (enabled: false) oder ganz fehlenden Indikator referenziert.
"""

import pytest

from user_data.strategies.generic.spec_runner import (
    _collect_indicator_refs,
    _validate_rule_references,
)


# ============================================================================
# Helper
# ============================================================================

def _entry_rule(lhs, op='>', rhs='close') -> dict:
    """Baut ein minimales rules_json mit einer Entry-Condition im Blocks-Format."""
    # GEÄNDERT: Ticket 48 — Blocks-Format (Produktionsformat seit Ticket 46);
    # _validate_rule_references prüft nur aktive Blöcke (block.get('enabled', True)).
    return {
        'entry': {'blocks': [{'conditions': [{'lhs': lhs, 'lhs_shift': 0, 'op': op, 'rhs': rhs, 'rhs_shift': 0}]}]},
        'exit': None,
    }


# ============================================================================
# Tests: _collect_indicator_refs
# ============================================================================

def test_collect_refs_entry_and_exit():
    """Sammelt Indikator-IDs aus Entry- und Exit-Conditions."""
    rules = {
        'entry': {'logic': 'AND', 'conditions': [
            {'lhs': 'indicator:teststrategie:teststrategie', 'op': '>', 'rhs': 'close'},
        ]},
        'exit': {'logic': 'OR', 'conditions': [
            {'lhs': 'indicator:supertrend:direction', 'op': '==', 'rhs': -1},
        ]},
    }
    assert _collect_indicator_refs(rules) == {'teststrategie', 'supertrend'}


def test_collect_refs_ignores_ohlcv_and_state():
    """OHLCV-Felder und State-Primitiven sind keine Indikator-Referenzen."""
    rules = _entry_rule('close', rhs='since_entry')
    assert _collect_indicator_refs(rules) == set()


def test_collect_refs_short_form_without_output():
    """Auch die Kurzform 'indicator:<id>' (ohne Output) wird erfasst."""
    rules = _entry_rule('indicator:rsi')
    assert _collect_indicator_refs(rules) == {'rsi'}


# ============================================================================
# Tests: _validate_rule_references — gültige Fälle
# ============================================================================

def test_validate_passes_when_indicator_enabled():
    """Aktivierter, referenzierter Indikator -> keine Exception."""
    rules = _entry_rule('indicator:teststrategie:teststrategie')
    indicators = {'teststrategie': {'indicator': 'vbt:VWMA', 'enabled': True}}
    _validate_rule_references(rules, indicators)


def test_validate_passes_when_enabled_key_absent():
    """Fehlendes 'enabled'-Flag bedeutet aktiv (Default True)."""
    rules = _entry_rule('indicator:teststrategie:teststrategie')
    indicators = {'teststrategie': {'indicator': 'vbt:VWMA'}}
    _validate_rule_references(rules, indicators)


def test_validate_passes_without_indicator_refs():
    """Regeln ohne Indikator-Referenzen sind immer gültig."""
    rules = _entry_rule('close', rhs='open')
    _validate_rule_references(rules, {})


# ============================================================================
# Tests: _validate_rule_references — Fehlerfälle
# ============================================================================

def test_validate_raises_on_disabled_indicator():
    """Deaktivierter, referenzierter Indikator -> klare Fehlermeldung."""
    rules = _entry_rule('indicator:supertrend:direction')
    indicators = {'supertrend': {'indicator': 'vbt:SUPERTREND', 'enabled': False}}
    with pytest.raises(ValueError) as exc:
        _validate_rule_references(rules, indicators)
    msg = str(exc.value)
    assert 'supertrend' in msg
    assert 'deaktiviert' in msg.lower()


def test_validate_raises_on_missing_indicator():
    """Fehlender, referenzierter Indikator -> klare Fehlermeldung."""
    rules = _entry_rule('indicator:supertrend:direction')
    indicators = {'teststrategie': {'indicator': 'vbt:VWMA', 'enabled': True}}
    with pytest.raises(ValueError) as exc:
        _validate_rule_references(rules, indicators)
    msg = str(exc.value)
    assert 'supertrend' in msg
    assert 'fehlend' in msg.lower()


def test_validate_raises_on_disabled_in_exit():
    """Deaktivierter Indikator auch in Exit-Conditions wird erkannt."""
    # GEÄNDERT: Ticket 48 — Blocks-Format
    rules = {
        'entry': {'blocks': [{'conditions': [
            {'lhs': 'close', 'lhs_shift': 0, 'op': '>', 'rhs': 'indicator:teststrategie:teststrategie', 'rhs_shift': 0},
        ]}]},
        'exit': {'blocks': [{'conditions': [
            {'lhs': 'indicator:supertrend:direction', 'lhs_shift': 0, 'op': '==', 'rhs': -1, 'rhs_shift': 0},
        ]}]},
    }
    indicators = {
        'teststrategie': {'indicator': 'vbt:VWMA', 'enabled': True},
        'supertrend': {'indicator': 'vbt:SUPERTREND', 'enabled': False},
    }
    with pytest.raises(ValueError) as exc:
        _validate_rule_references(rules, indicators)
    assert 'supertrend' in str(exc.value)


def test_validate_reports_disabled_and_missing_together():
    """Deaktivierte und fehlende Indikatoren werden gemeinsam gemeldet."""
    # GEÄNDERT: Ticket 48 — Blocks-Format
    rules = {
        'entry': {'blocks': [{'conditions': [
            {'lhs': 'indicator:supertrend:direction', 'lhs_shift': 0, 'op': '>', 'rhs': 0, 'rhs_shift': 0},
            {'lhs': 'indicator:atr:atr', 'lhs_shift': 0, 'op': '>', 'rhs': 0, 'rhs_shift': 0},
        ]}]},
        'exit': None,
    }
    indicators = {'supertrend': {'indicator': 'x', 'enabled': False}}
    with pytest.raises(ValueError) as exc:
        _validate_rule_references(rules, indicators)
    msg = str(exc.value)
    assert 'supertrend' in msg  # deaktiviert
    assert 'atr' in msg         # fehlend

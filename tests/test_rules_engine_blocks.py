"""Tests für das Block-Format (disjunktive Normalform) der Rules-Engine.

Prüft:
  - Block intern UND, zwischen Blöcken ODER (_evaluate_rule_group / evaluate_rules)
  - DNF-Äquivalenz: faktorisierte Form A UND (B ODER C) == ausgesplittete Form
    (A UND B) ODER (A UND C)
  - State-Ref-Erkennung über Blöcke hinweg
  - Konverter rules_migration: Alt-Format {logic, conditions} -> {blocks}

Methodik: deterministischer OHLCV-DataFrame, Conditions auf OHLCV-Feldern und
Konstanten. Erwartete Masken werden direkt per pandas berechnet und bit-genau
gegen die Engine verglichen. Kein Mocking der Engine selbst.
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
    evaluate_rules,
    _rule_group_uses_state_refs,
)
from user_data.strategies.generic.rules_migration import (
    legacy_group_to_blocks,
    migrate_rules_json,
)


# ============================================================================
# Fixtures / Hilfsmittel
# ============================================================================

class _OhlcWrapper:
    """Minimaler ohlc_data-Wrapper: implementiert .get(key) für OHLCV-Spalten."""

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def get(self, key: str) -> pd.Series:
        return self._df[key]


def _make_ohlc_df(n: int = 60) -> pd.DataFrame:
    """Deterministischer OHLCV-DataFrame mit gut streuenden Werten.

    close steigt linear von 90 auf knapp 150, volume zählt 0..n-1 hoch.
    Damit liefern die Test-Conditions gemischte True/False-Masken.
    """
    idx = pd.date_range("2022-01-01", periods=n, freq="1h")
    close = np.linspace(90.0, 150.0, n)
    volume = np.arange(n, dtype=float)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": volume,
        },
        index=idx,
    )


def _cond(lhs, op, rhs) -> dict:
    """Baut eine Condition im Engine-Format (shift = 0)."""
    return {'lhs': lhs, 'lhs_shift': 0, 'op': op, 'rhs': rhs, 'rhs_shift': 0}


@pytest.fixture
def ohlc_df() -> pd.DataFrame:
    return _make_ohlc_df(60)


@pytest.fixture
def ohlc_data(ohlc_df: pd.DataFrame) -> _OhlcWrapper:
    return _OhlcWrapper(ohlc_df)


# Referenz-Conditions (als Masken direkt aus dem df berechenbar)
#   A: close > 100
#   B: close < 130
#   C: volume > 40
def _mask_A(df): return df['Close'] > 100
def _mask_B(df): return df['Close'] < 130
def _mask_C(df): return df['Volume'] > 40

_COND_A = _cond('close', '>', 100)
_COND_B = _cond('close', '<', 130)
_COND_C = _cond('volume', '>', 40)


def _assert_mask_equal(actual: pd.Series, expected: pd.Series, msg: str) -> None:
    """Vergleicht zwei Boolean-Masken bit-genau (Index-unabhängig)."""
    pd.testing.assert_series_equal(
        actual.reset_index(drop=True).astype(bool),
        expected.reset_index(drop=True).astype(bool),
        check_names=False,
        obj=msg,
    )


# ============================================================================
# (a) Block intern UND
# ============================================================================

class TestBlockInternalAnd:
    """Ein Block mit mehreren Conditions verknüpft diese mit UND."""

    def test_single_block_two_conditions_is_and(self, ohlc_data, ohlc_df):
        rules = {'entry': {'blocks': [{'conditions': [_COND_A, _COND_B]}]}}
        # GEÄNDERT: Ticket 46 — SignalMasks statt (entries, exits)-Tupel
        masks = evaluate_rules(rules, ohlc_data, {})
        expected = _mask_A(ohlc_df) & _mask_B(ohlc_df)
        _assert_mask_equal(masks.long_entries, expected, "Block intern muss UND sein")
        # Kein Exit-Spec -> long_exits ist all-False (nicht None)
        assert not masks.long_exits.any()

    def test_single_block_single_condition(self, ohlc_data, ohlc_df):
        rules = {'entry': {'blocks': [{'conditions': [_COND_A]}]}}
        masks = evaluate_rules(rules, ohlc_data, {})
        _assert_mask_equal(masks.long_entries, _mask_A(ohlc_df), "Einzelbedingung")


# ============================================================================
# (b) Zwischen Blöcken ODER
# ============================================================================

class TestBlocksOr:
    """Mehrere Blöcke werden mit ODER verknüpft."""

    def test_two_single_condition_blocks_is_or(self, ohlc_data, ohlc_df):
        rules = {'entry': {'blocks': [
            {'conditions': [_COND_A]},
            {'conditions': [_COND_C]},
        ]}}
        masks = evaluate_rules(rules, ohlc_data, {})
        expected = _mask_A(ohlc_df) | _mask_C(ohlc_df)
        _assert_mask_equal(masks.long_entries, expected, "Zwischen Blöcken muss ODER sein")


# ============================================================================
# (c) DNF-Äquivalenz: faktorisiert == ausgesplittet
# ============================================================================

class TestDnfEquivalence:
    """A UND (B ODER C) == (A UND B) ODER (A UND C)."""

    def test_expanded_equals_factored(self, ohlc_data, ohlc_df):
        # Ausgesplittete (DNF-)Form: zwei Blöcke, beide enthalten A
        rules_expanded = {'entry': {'blocks': [
            {'conditions': [_COND_A, _COND_B]},
            {'conditions': [_COND_A, _COND_C]},
        ]}}
        masks = evaluate_rules(rules_expanded, ohlc_data, {})

        a, b, c = _mask_A(ohlc_df), _mask_B(ohlc_df), _mask_C(ohlc_df)
        factored = a & (b | c)
        expanded = (a & b) | (a & c)
        # Algebraische Identität als Selbstkontrolle
        _assert_mask_equal(expanded, factored, "Boolesche Identität")
        # Engine-Ergebnis == beide Referenzformen
        _assert_mask_equal(masks.long_entries, factored, "Engine(DNF) == faktorisierte Form")

    def test_exit_blocks_also_dnf(self, ohlc_data, ohlc_df):
        # Exit symmetrisch: (A UND B) ODER (C)
        rules = {
            'entry': {'blocks': [{'conditions': [_COND_A]}]},
            'exit': {'blocks': [
                {'conditions': [_COND_A, _COND_B]},
                {'conditions': [_COND_C]},
            ]},
        }
        masks = evaluate_rules(rules, ohlc_data, {})
        a, b, c = _mask_A(ohlc_df), _mask_B(ohlc_df), _mask_C(ohlc_df)
        expected = (a & b) | c
        _assert_mask_equal(masks.long_exits, expected, "Exit-Blöcke ebenfalls DNF")


# ============================================================================
# (d) Fehlerfälle
# ============================================================================

class TestBlockErrors:
    """Leere Strukturen werden klar abgewiesen."""

    def test_empty_blocks_raises(self, ohlc_data):
        rules = {'entry': {'blocks': []}}
        with pytest.raises(ValueError, match="blocks"):
            evaluate_rules(rules, ohlc_data, {})

    def test_block_without_conditions_raises(self, ohlc_data):
        rules = {'entry': {'blocks': [{'conditions': []}]}}
        with pytest.raises(ValueError, match="conditions"):
            evaluate_rules(rules, ohlc_data, {})


# ============================================================================
# (e) State-Ref-Erkennung über Blöcke hinweg
# ============================================================================

class TestStateRefDetection:
    """_rule_group_uses_state_refs findet State-Primitiven in jedem Block."""

    def test_state_ref_in_second_block(self):
        group = {'blocks': [
            {'conditions': [_cond('close', '>', 100)]},
            {'conditions': [_cond('since_entry', '>', 5)]},
        ]}
        assert _rule_group_uses_state_refs(group) is True

    def test_no_state_ref(self):
        group = {'blocks': [
            {'conditions': [_cond('close', '>', 100), _cond('volume', '>', 10)]},
        ]}
        assert _rule_group_uses_state_refs(group) is False

    def test_empty_group(self):
        assert _rule_group_uses_state_refs({'blocks': []}) is False


# ============================================================================
# (f) Konverter rules_migration: Alt-Format -> Block-Format
# ============================================================================

class TestLegacyConverter:
    """{logic, conditions} wird verlustfrei in {blocks} übersetzt."""

    def test_legacy_and_becomes_single_block(self):
        legacy = {'logic': 'AND', 'conditions': [_COND_A, _COND_B]}
        result = legacy_group_to_blocks(legacy)
        assert result == {'blocks': [{'conditions': [_COND_A, _COND_B]}]}

    def test_legacy_or_becomes_one_block_per_condition(self):
        legacy = {'logic': 'OR', 'conditions': [_COND_A, _COND_B, _COND_C]}
        result = legacy_group_to_blocks(legacy)
        assert result == {'blocks': [
            {'conditions': [_COND_A]},
            {'conditions': [_COND_B]},
            {'conditions': [_COND_C]},
        ]}

    def test_legacy_missing_logic_defaults_and(self):
        legacy = {'conditions': [_COND_A]}
        result = legacy_group_to_blocks(legacy)
        assert result == {'blocks': [{'conditions': [_COND_A]}]}

    def test_already_block_format_is_idempotent(self):
        group = {'blocks': [{'conditions': [_COND_A]}]}
        assert legacy_group_to_blocks(group) is group

    def test_none_stays_none(self):
        assert legacy_group_to_blocks(None) is None

    def test_migrate_rules_json_entry_and_exit(self):
        legacy = {
            'entry': {'logic': 'AND', 'conditions': [_COND_A, _COND_B]},
            'exit': {'logic': 'OR', 'conditions': [_COND_A, _COND_C]},
        }
        result = migrate_rules_json(legacy)
        assert result['entry'] == {'blocks': [{'conditions': [_COND_A, _COND_B]}]}
        assert result['exit'] == {'blocks': [
            {'conditions': [_COND_A]},
            {'conditions': [_COND_C]},
        ]}

    def test_migrate_rules_json_exit_none(self):
        legacy = {'entry': {'logic': 'AND', 'conditions': [_COND_A]}, 'exit': None}
        result = migrate_rules_json(legacy)
        assert result['entry'] == {'blocks': [{'conditions': [_COND_A]}]}
        assert result['exit'] is None


# ============================================================================
# (g) Konverter + Engine: migrierte Alt-Specs liefern die erwartete Maske
# ============================================================================

class TestConverterEngineEquivalence:
    """Migrierte Alt-Specs ergeben in der Engine die korrekte Logik."""

    def test_migrated_legacy_and_matches_manual_and(self, ohlc_data, ohlc_df):
        legacy = {'entry': {'logic': 'AND', 'conditions': [_COND_A, _COND_B]}}
        rules = migrate_rules_json(legacy)
        masks = evaluate_rules(rules, ohlc_data, {})
        expected = _mask_A(ohlc_df) & _mask_B(ohlc_df)
        _assert_mask_equal(masks.long_entries, expected, "migriertes AND == manuelles UND")

    def test_migrated_legacy_or_matches_manual_or(self, ohlc_data, ohlc_df):
        legacy = {'entry': {'logic': 'OR', 'conditions': [_COND_A, _COND_C]}}
        rules = migrate_rules_json(legacy)
        masks = evaluate_rules(rules, ohlc_data, {})
        expected = _mask_A(ohlc_df) | _mask_C(ohlc_df)
        _assert_mask_equal(masks.long_entries, expected, "migriertes OR == manuelles ODER")

"""Tests für Short-Positionen im Masken-Pfad der Rules-Engine (Ticket 46 + 47).

Prüft:
  a. test_long_short_signals: Gemischte Long- und Short-Blöcke → richtige Partitionierung
  b. test_long_only_regression: Nur Long-Blöcke (kein is_short) → Rückwärtskompatibilität
  c. test_short_only: Nur Short-Blöcke → long_entries/exits all-False, short_entries hat Signale
  d. TestGuardShortWithStateExit: Short+State-Ref — Guard entfernt (Ticket 47); State-Ref-Fehler
     kommt weiterhin aus _resolve_ref
  d2. TestGuardShortWithStateExitNativePath: Short im nativen Pfad funktioniert jetzt (kein Guard)

Methodik: deterministischer OHLCV-DataFrame, Conditions auf OHLCV-Feldern und
Konstanten. Erwartete Masken werden direkt per pandas berechnet und bit-genau
gegen die Engine verglichen. Kein Mocking.
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
    evaluate_rules_native,
    SignalMasks,
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
    Damit liefern Test-Conditions gemischte True/False-Masken.
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


def _assert_mask_equal(actual: pd.Series, expected: pd.Series, msg: str) -> None:
    """Vergleicht zwei Boolean-Masken bit-genau (Index-unabhängig)."""
    pd.testing.assert_series_equal(
        actual.reset_index(drop=True).astype(bool),
        expected.reset_index(drop=True).astype(bool),
        check_names=False,
        obj=msg,
    )


def _assert_all_false(mask: pd.Series, msg: str) -> None:
    """Prüft dass eine Maske ausschließlich False-Werte enthält."""
    assert not mask.any(), f"{msg}: Maske enthält unerwartete True-Werte"


# Referenz-Conditions (als Masken direkt aus dem df berechenbar)
#   A: close > 100   (Long-Entry)
#   B: close > 130   (Short-Entry — höheres Niveau)
#   C: close < 120   (Exit)
def _mask_A(df): return df['Close'] > 100.0
def _mask_B(df): return df['Close'] > 130.0
def _mask_C(df): return df['Close'] < 120.0

_COND_A = _cond('close', '>', 100.0)
_COND_B = _cond('close', '>', 130.0)
_COND_C = _cond('close', '<', 120.0)


# ============================================================================
# (a) Gemischte Long- und Short-Blöcke
# ============================================================================

class TestLongShortSignals:
    """Blöcke mit is_short=True landen in short_entries, andere in long_entries."""

    def test_long_short_signals(self, ohlc_data, ohlc_df):
        """Ein Long-Block und ein Short-Block erzeugen korrekte Partitionierung."""
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [_COND_A], 'is_short': False},   # Long
                    {'conditions': [_COND_B], 'is_short': True},    # Short
                ]
            }
        }
        masks = evaluate_rules(rules, ohlc_data, {})

        assert isinstance(masks, SignalMasks), "Rückgabe muss SignalMasks sein"

        # Long-Entries: Blöcke ohne is_short → Maske A
        _assert_mask_equal(masks.long_entries, _mask_A(ohlc_df), "long_entries muss Maske A entsprechen")

        # Short-Entries: Blöcke mit is_short=True → Maske B
        _assert_mask_equal(masks.short_entries, _mask_B(ohlc_df), "short_entries muss Maske B entsprechen")

        # Kein Exit-Spec → beide Exit-Masken all-False
        _assert_all_false(masks.long_exits, "long_exits")
        _assert_all_false(masks.short_exits, "short_exits")

    def test_long_short_signals_with_exits(self, ohlc_data, ohlc_df):
        """Long- und Short-Exits werden ebenfalls korrekt partitioniert."""
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [_COND_A]},                    # Long (kein is_short)
                    {'conditions': [_COND_B], 'is_short': True},  # Short
                ]
            },
            'exit': {
                'blocks': [
                    {'conditions': [_COND_C]},                    # Long-Exit
                    {'conditions': [_COND_C], 'is_short': True},  # Short-Exit (gleiche Maske)
                ]
            },
        }
        masks = evaluate_rules(rules, ohlc_data, {})

        _assert_mask_equal(masks.long_entries, _mask_A(ohlc_df), "long_entries")
        _assert_mask_equal(masks.short_entries, _mask_B(ohlc_df), "short_entries")
        _assert_mask_equal(masks.long_exits, _mask_C(ohlc_df), "long_exits")
        _assert_mask_equal(masks.short_exits, _mask_C(ohlc_df), "short_exits")


# ============================================================================
# (b) Long-Only-Regression: Bestehende Specs ohne is_short unverändert
# ============================================================================

class TestLongOnlyRegression:
    """Specs ohne is_short=True liefern identisches Ergebnis wie vor Ticket 46."""

    def test_long_only_entries_unchanged(self, ohlc_data, ohlc_df):
        """Nur Long-Blöcke (kein is_short) → long_entries wie bisher, short-Masken all-False."""
        rules = {
            'entry': {'blocks': [{'conditions': [_COND_A]}]},
            'exit': {'blocks': [{'conditions': [_COND_C]}]},
        }
        masks = evaluate_rules(rules, ohlc_data, {})

        _assert_mask_equal(masks.long_entries, _mask_A(ohlc_df), "long_entries")
        _assert_mask_equal(masks.long_exits, _mask_C(ohlc_df), "long_exits")
        _assert_all_false(masks.short_entries, "short_entries muss all-False sein")
        _assert_all_false(masks.short_exits, "short_exits muss all-False sein")

    def test_long_only_without_exit(self, ohlc_data, ohlc_df):
        """Long-Only ohne Exit → long_exits all-False (nicht None)."""
        rules = {'entry': {'blocks': [{'conditions': [_COND_A]}]}}
        masks = evaluate_rules(rules, ohlc_data, {})

        _assert_mask_equal(masks.long_entries, _mask_A(ohlc_df), "long_entries")
        _assert_all_false(masks.long_exits, "long_exits muss all-False sein")
        _assert_all_false(masks.short_entries, "short_entries muss all-False sein")
        _assert_all_false(masks.short_exits, "short_exits muss all-False sein")

    def test_is_short_false_treated_as_long(self, ohlc_data, ohlc_df):
        """is_short=False ist semantisch identisch zu fehlendem is_short."""
        rules_explicit = {
            'entry': {'blocks': [{'conditions': [_COND_A], 'is_short': False}]},
        }
        rules_implicit = {
            'entry': {'blocks': [{'conditions': [_COND_A]}]},
        }
        masks_explicit = evaluate_rules(rules_explicit, ohlc_data, {})
        masks_implicit = evaluate_rules(rules_implicit, ohlc_data, {})

        _assert_mask_equal(
            masks_explicit.long_entries,
            masks_implicit.long_entries,
            "is_short=False und kein is_short müssen gleich sein",
        )


# ============================================================================
# (c) Short-Only: Nur Short-Blöcke, Long-Masken all-False
# ============================================================================

class TestShortOnly:
    """Nur Short-Blöcke → long_entries/exits all-False, short_entries hat Signale."""

    def test_short_only_entries(self, ohlc_data, ohlc_df):
        """Nur ein Short-Entry-Block → long_entries all-False, short_entries hat Signale."""
        rules = {
            'entry': {'blocks': [{'conditions': [_COND_B], 'is_short': True}]},
        }
        masks = evaluate_rules(rules, ohlc_data, {})

        _assert_all_false(masks.long_entries, "long_entries muss all-False sein")
        _assert_all_false(masks.long_exits, "long_exits muss all-False sein")
        _assert_mask_equal(masks.short_entries, _mask_B(ohlc_df), "short_entries")
        _assert_all_false(masks.short_exits, "short_exits muss all-False sein")

    def test_short_only_entries_and_exits(self, ohlc_data, ohlc_df):
        """Short-Entry und Short-Exit → Long-Masken all-False, Short-Masken korrekt."""
        rules = {
            'entry': {'blocks': [{'conditions': [_COND_B], 'is_short': True}]},
            'exit': {'blocks': [{'conditions': [_COND_C], 'is_short': True}]},
        }
        masks = evaluate_rules(rules, ohlc_data, {})

        _assert_all_false(masks.long_entries, "long_entries")
        _assert_all_false(masks.long_exits, "long_exits")
        _assert_mask_equal(masks.short_entries, _mask_B(ohlc_df), "short_entries")
        _assert_mask_equal(masks.short_exits, _mask_C(ohlc_df), "short_exits")

    def test_short_signals_non_empty(self, ohlc_data, ohlc_df):
        """Short-Signale enthalten tatsächlich True-Werte (Maske ist nicht leer)."""
        rules = {
            'entry': {'blocks': [{'conditions': [_COND_B], 'is_short': True}]},
        }
        masks = evaluate_rules(rules, ohlc_data, {})

        # close > 130: da close von 90 auf 150 steigt, gibt es True-Werte
        expected_count = _mask_B(ohlc_df).sum()
        assert masks.short_entries.sum() == expected_count, (
            f"short_entries sollte {expected_count} True-Werte haben, "
            f"hat aber {masks.short_entries.sum()}"
        )


# ============================================================================
# (d) Short-Block + State-Ref: Guard entfernt (Ticket 47) — Fehler kommt aus _resolve_ref
# ============================================================================

class TestGuardShortWithStateExit:
    """GEÄNDERT: Ticket 47 — Short-Guard aus evaluate_rules() entfernt.

    State-Refs sind im Masken-Pfad (evaluate_rules) grundsätzlich unzulässig —
    der Fehler kommt weiterhin aus _resolve_ref, unabhängig von Short-Blöcken.
    Short+State-Exit läuft jetzt korrekt über evaluate_rules_native.
    """

    def test_short_entry_with_state_exit_raises_state_ref_error(self, ohlc_data):
        """Short-Entry-Block + since_entry in Exit → ValueError wegen State-Primitiv.

        Ticket 47: Short-Guard entfernt. Aber State-Refs sind im Masken-Pfad
        weiterhin unzulässig — _resolve_ref wirft ValueError("State-Primitiv").
        """
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [_COND_A]},                    # Long
                    {'conditions': [_COND_B], 'is_short': True},  # Short
                ]
            },
            'exit': {
                'blocks': [
                    {'conditions': [_cond('since_entry', '>=', 5)]},  # State-Ref
                ]
            },
        }
        # Kein Short-Guard mehr — aber State-Ref im Masken-Pfad → Fehler aus _resolve_ref
        with pytest.raises(ValueError, match="State-Primitiv"):
            evaluate_rules(rules, ohlc_data, {})

    def test_short_exit_with_state_ref_raises_state_ref_error(self, ohlc_data):
        """Short-Exit-Block + entry_price in Exit → ValueError wegen State-Primitiv."""
        rules = {
            'entry': {'blocks': [{'conditions': [_COND_A]}]},
            'exit': {
                'blocks': [
                    {'conditions': [_cond('entry_price', '>', 100)], 'is_short': True},
                ]
            },
        }
        # State-Ref im Masken-Pfad → Fehler aus _resolve_ref
        with pytest.raises(ValueError, match="State-Primitiv"):
            evaluate_rules(rules, ohlc_data, {})

    def test_long_only_with_state_exit_raises_state_ref_error(self, ohlc_data):
        """Long-Only + State-Ref in Exit → ValueError wegen State-Primitiv aus _resolve_ref."""
        rules = {
            'entry': {'blocks': [{'conditions': [_COND_A]}]},
            'exit': {
                'blocks': [
                    {'conditions': [_cond('since_entry', '>=', 5)]},
                ]
            },
        }
        with pytest.raises(ValueError, match="State-Primitiv"):
            evaluate_rules(rules, ohlc_data, {})


# ============================================================================
# (d2) Short im nativen Pfad — GEÄNDERT: Ticket 47 (kein Guard mehr)
#      Short-Blöcke + nativer Pfad laufen jetzt korrekt durch.
# ============================================================================

class TestGuardShortWithStateExitNativePath:
    """GEÄNDERT: Ticket 47 — Short-Guard im nativen Pfad entfernt.

    Short-Blöcke + State-Exits laufen jetzt korrekt über evaluate_rules_native.
    Statt ValueError wird ein Portfolio gebaut, das Short-Trades enthält.
    """

    def _make_pf_kwargs(self, ohlc_df: pd.DataFrame) -> dict:
        """Minimale pf_kwargs für evaluate_rules_native (nur 'close' zwingend)."""
        return {
            'close': ohlc_df['Close'],
            'open': ohlc_df['Open'],
            'high': ohlc_df['High'],
            'low': ohlc_df['Low'],
            'fees': 0.001,
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

    def test_short_entry_block_in_native_path_works(self, ohlc_data, ohlc_df):
        """GEÄNDERT: Ticket 47 — Short-Entry-Block + State-Exit läuft korrekt durch.

        Vorher: ValueError("Short-Blöcke"). Jetzt: Portfolio mit Short-Trades.
        Nicht-überlappende Entry-Conditions: Long-Entry früh (close < 110),
        Short-Entry spät (close > 130) — damit Reverse korrekt greifen kann.
        """
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [_cond('close', '<', 110.0)]},               # Long: frühe Bars
                    {'conditions': [_cond('close', '>', 130.0)], 'is_short': True},  # Short: späte Bars
                ]
            },
            'exit': {
                'blocks': [
                    {'conditions': [_cond('since_entry', '>=', 5)]},  # State-Ref → nativer Pfad
                ]
            },
        }
        result = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=self._make_pf_kwargs(ohlc_df),
        )
        assert result is not None
        # Es müssen Short-Trades entstanden sein
        directions = result.trades.records['direction'].tolist() if len(result.trades.records) > 0 else []
        assert 1 in directions, f"Keine Short-Trades (direction=1) gefunden. Trades: {directions}"

    def test_short_exit_block_in_native_path_works(self, ohlc_data, ohlc_df):
        """GEÄNDERT: Ticket 47 — Short-Exit-Block + State-Exit läuft korrekt durch."""
        rules = {
            'entry': {'blocks': [{'conditions': [_COND_A]}]},
            'exit': {
                'blocks': [
                    {'conditions': [_cond('since_entry', '>=', 5)]},               # Long-Exit (State-Ref)
                    {'conditions': [_COND_C], 'is_short': True},                   # Short-Exit (statisch)
                ]
            },
        }
        result = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=self._make_pf_kwargs(ohlc_df),
        )
        assert result is not None
        assert len(result.trades.records) > 0, "Es müssen Long-Trades entstanden sein"

    def test_long_only_with_state_exit_native_path_does_not_raise(self, ohlc_data, ohlc_df):
        """Long-Only + State-Exit im nativen Pfad: Regressions-Test (weiterhin kein Fehler)."""
        rules = {
            'entry': {'blocks': [{'conditions': [_COND_A]}]},
            'exit': {
                'blocks': [
                    {'conditions': [_cond('since_entry', '>=', 5)]},
                ]
            },
        }
        result = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=self._make_pf_kwargs(ohlc_df),
        )
        assert result is not None


# ============================================================================
# (e) SignalMasks-Struktur
# ============================================================================

class TestSignalMasksStructure:
    """Prüft die Struktur und den Typ des Rückgabewerts."""

    def test_returns_signal_masks_namedtuple(self, ohlc_data):
        """evaluate_rules gibt ein SignalMasks-NamedTuple zurück."""
        rules = {'entry': {'blocks': [{'conditions': [_COND_A]}]}}
        result = evaluate_rules(rules, ohlc_data, {})
        assert isinstance(result, SignalMasks), f"Erwartet SignalMasks, erhalten {type(result)}"

    def test_all_four_masks_present(self, ohlc_data):
        """Alle vier Felder sind vorhanden und keine ist None."""
        rules = {'entry': {'blocks': [{'conditions': [_COND_A]}]}}
        masks = evaluate_rules(rules, ohlc_data, {})
        assert masks.long_entries is not None
        assert masks.long_exits is not None
        assert masks.short_entries is not None
        assert masks.short_exits is not None

    def test_all_false_masks_have_same_index(self, ohlc_data, ohlc_df):
        """All-False-Masken haben denselben Index wie die echten Signale."""
        rules = {'entry': {'blocks': [{'conditions': [_COND_A]}]}}
        masks = evaluate_rules(rules, ohlc_data, {})

        assert list(masks.short_entries.index) == list(ohlc_df.index), (
            "short_entries-Index stimmt nicht mit ohlc_df-Index überein"
        )
        assert list(masks.long_exits.index) == list(ohlc_df.index), (
            "long_exits-Index stimmt nicht mit ohlc_df-Index überein"
        )

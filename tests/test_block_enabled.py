"""Tests für Ticket 48: Block-enabled-Filter in evaluate_rules_native + Referenz-Validierung.

Prüft:
  1. Alle Entry-Blöcke deaktiviert → 0 Trades, kein ValueError
  2. Exit-Blöcke deaktiviert → Exit-Signale ignoriert (Positionen schließen nur per Stops/Time-Limit)
  3. Einzelner Block deaktiviert in Gruppe mit aktiven Blöcken → nur aktive Blöcke wirken
  4. Fehlendes 'enabled'-Feld → bit-genau wie vorher (Abwärtskompatibilität)
  5. D-Fall: deaktivierter Block referenziert deaktivierten Indikator → kein ValueError
  6. D-Fall: aktiver Block referenziert deaktivierten Indikator → weiterhin ValueError

Methodik: deterministischer OHLCV-DataFrame, Conditions auf OHLCV-Feldern (kein Mock).
"""

import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import numpy as np
import pandas as pd
import pytest

from user_data.strategies.generic.rules_engine import evaluate_rules_native
from user_data.strategies.generic.spec_runner import _validate_rule_references


# ============================================================================
# Fixtures / Hilfsmittel
# ============================================================================

class _OhlcWrapper:
    """Minimaler ohlc_data-Wrapper: implementiert .get(key) für OHLCV-Spalten."""

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def get(self, key: str) -> pd.Series:
        return self._df[key]


def _make_ohlc_df(n: int = 120) -> pd.DataFrame:
    """Deterministischer OHLCV-DataFrame mit gut streuenden Werten.

    close steigt linear von 90 auf 150, sodass Conditions gemischte Masken liefern.
    """
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


def _cond(lhs, op, rhs) -> dict:
    """Baut eine Condition im Engine-Format."""
    return {'lhs': lhs, 'lhs_shift': 0, 'op': op, 'rhs': rhs, 'rhs_shift': 0}


# Referenz-Conditions
_COND_ENTRY = _cond('close', '<', 110.0)    # True in frühen Bars (close 90-110)
_COND_ENTRY2 = _cond('close', '>', 130.0)   # True in späten Bars (close 130-150)
_COND_EXIT = _cond('close', '>', 140.0)     # Statischer Exit


# ============================================================================
# 1. Alle Entry-Blöcke deaktiviert → 0 Trades, kein ValueError
# ============================================================================

class TestAllEntryBlocksDisabled:
    """Alle Entry-Blöcke deaktiviert: Portfolio ohne Trades, kein Fehler."""

    def test_all_entry_blocks_disabled_no_trades(self, ohlc_data, ohlc_df):
        """Alle Entry-Blöcke haben enabled: false → Portfolio hat 0 Trades, kein ValueError."""
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [_COND_ENTRY], 'enabled': False},
                    {'conditions': [_COND_ENTRY2], 'enabled': False},
                ]
            },
            'exit': None,
        }
        pf = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        assert pf is not None, "evaluate_rules_native darf keinen Fehler werfen"
        assert len(pf.trades.records) == 0, (
            f"Bei deaktivierten Entry-Blöcken muss 0 Trades entstehen, "
            f"hat aber {len(pf.trades.records)}"
        )

    def test_all_entry_blocks_disabled_single_block(self, ohlc_data, ohlc_df):
        """Ein einziger deaktivierter Entry-Block → 0 Trades, kein Fehler."""
        rules = {
            'entry': {'blocks': [{'conditions': [_COND_ENTRY], 'enabled': False}]},
            'exit': None,
        }
        pf = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        assert len(pf.trades.records) == 0


# ============================================================================
# 2. Exit-Blöcke deaktiviert → Exit-Signale ignoriert
# ============================================================================

class TestExitBlocksDisabled:
    """Deaktivierte Exit-Blöcke werden nicht ausgewertet."""

    def test_disabled_exit_block_ignored(self, ohlc_data, ohlc_df):
        """Exit-Block mit enabled: false → Portfolio mit Trades (Entry wirkt),
        Exit-Signale werden ignoriert (Positionen nur per Time-Limit oder Stop)."""
        rules = {
            'entry': {'blocks': [{'conditions': [_COND_ENTRY]}]},
            'exit': {'blocks': [{'conditions': [_COND_EXIT], 'enabled': False}]},
        }
        pf_with_disabled_exit = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        # Zum Vergleich: ohne Exit-Spec (exit: null) muss identisch sein
        rules_no_exit = {
            'entry': {'blocks': [{'conditions': [_COND_ENTRY]}]},
            'exit': None,
        }
        pf_no_exit = evaluate_rules_native(
            rules_json=rules_no_exit,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        # Beide Portfolios müssen identische Trade-Anzahl haben
        assert len(pf_with_disabled_exit.trades.records) == len(pf_no_exit.trades.records), (
            "Deaktivierter Exit-Block muss sich identisch zu exit: null verhalten"
        )


# ============================================================================
# 3. Einzelner Block deaktiviert in Gruppe mit aktiven Blöcken
# ============================================================================

class TestSingleBlockDisabledInGroup:
    """Einzelner deaktivierter Block wird aus der ODER-Verknüpfung herausgenommen."""

    def test_disabled_block_removed_from_or(self, ohlc_data, ohlc_df):
        """Gruppe aus 2 Blöcken, einer deaktiviert: nur aktiver Block wirkt."""
        # Aktiver Block: COND_ENTRY (close < 110)
        # Deaktivierter Block: COND_ENTRY2 (close > 130) — darf nicht wirken
        rules_with_disabled = {
            'entry': {
                'blocks': [
                    {'conditions': [_COND_ENTRY], 'enabled': True},
                    {'conditions': [_COND_ENTRY2], 'enabled': False},
                ]
            },
            'exit': None,
        }
        rules_only_active = {
            'entry': {'blocks': [{'conditions': [_COND_ENTRY]}]},
            'exit': None,
        }
        pf_disabled = evaluate_rules_native(
            rules_json=rules_with_disabled,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        pf_only_active = evaluate_rules_native(
            rules_json=rules_only_active,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        assert len(pf_disabled.trades.records) == len(pf_only_active.trades.records), (
            "Deaktivierter Block darf keine zusätzlichen Trades erzeugen"
        )

    def test_disabled_block_doesnt_add_exit_signals(self, ohlc_data, ohlc_df):
        """Deaktivierter Exit-Block in Gruppe mit aktivem Exit-Block: nur aktiver Exit wirkt."""
        rules_mixed = {
            'entry': {'blocks': [{'conditions': [_COND_ENTRY]}]},
            'exit': {
                'blocks': [
                    {'conditions': [_COND_EXIT], 'enabled': True},
                    # deaktivierter Block mit früherer Exit-Condition darf nicht wirken
                    {'conditions': [_cond('close', '>', 100.0)], 'enabled': False},
                ]
            },
        }
        rules_only_active_exit = {
            'entry': {'blocks': [{'conditions': [_COND_ENTRY]}]},
            'exit': {'blocks': [{'conditions': [_COND_EXIT]}]},
        }
        pf_mixed = evaluate_rules_native(
            rules_json=rules_mixed,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        pf_only_active = evaluate_rules_native(
            rules_json=rules_only_active_exit,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        assert len(pf_mixed.trades.records) == len(pf_only_active.trades.records), (
            "Deaktivierter Exit-Block darf das Exit-Verhalten nicht ändern"
        )


# ============================================================================
# 4. Fehlendes 'enabled'-Feld → bit-genau wie vorher (Abwärtskompatibilität)
# ============================================================================

class TestMissingEnabledField:
    """Fehlendes 'enabled' gilt als True — identisches Verhalten zu explizit enabled: true."""

    def test_missing_enabled_identical_to_enabled_true(self, ohlc_data, ohlc_df):
        """Spec ohne 'enabled'-Feld muss bit-genau mit enabled: true übereinstimmen."""
        pf_kwargs = _make_pf_kwargs(ohlc_df)

        rules_without_enabled = {
            'entry': {'blocks': [{'conditions': [_COND_ENTRY]}]},
            'exit': {'blocks': [{'conditions': [_COND_EXIT]}]},
        }
        rules_with_enabled_true = {
            'entry': {'blocks': [{'conditions': [_COND_ENTRY], 'enabled': True}]},
            'exit': {'blocks': [{'conditions': [_COND_EXIT], 'enabled': True}]},
        }

        pf_without = evaluate_rules_native(
            rules_json=rules_without_enabled,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=pf_kwargs,
        )
        pf_with_true = evaluate_rules_native(
            rules_json=rules_with_enabled_true,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=pf_kwargs,
        )

        trades_without = pf_without.trades.records
        trades_with_true = pf_with_true.trades.records
        assert len(trades_without) == len(trades_with_true), (
            f"Fehlendes enabled muss identisch zu enabled: true sein. "
            f"Ohne: {len(trades_without)} Trades, mit enabled:true: {len(trades_with_true)} Trades"
        )

    def test_missing_enabled_preserves_trade_count(self, ohlc_data, ohlc_df):
        """Bestehende Spec ohne enabled produziert weiterhin Trades (Regression)."""
        rules = {
            'entry': {'blocks': [{'conditions': [_COND_ENTRY]}]},
            'exit': None,
        }
        pf = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        # Die Condition _COND_ENTRY (close < 110) greift in frühen Bars → Trades vorhanden
        assert len(pf.trades.records) > 0, (
            "Spec ohne enabled muss unverändert Trades erzeugen (Regressions-Check)"
        )


# ============================================================================
# 5. D-Fall: deaktivierter Block referenziert deaktivierten Indikator → kein ValueError
# ============================================================================

class TestReferenceValidationBlockEnabled:
    """_validate_rule_references beachtet Block-enabled beim Referenz-Check."""

    def test_disabled_block_with_disabled_indicator_no_error(self):
        """Deaktivierter Block referenziert deaktivierten Indikator → kein ValueError."""
        rules = {
            'entry': {
                'blocks': [
                    # Deaktivierter Block: darf deaktivierten Indikator referenzieren
                    {'conditions': [{'lhs': 'indicator:myrsi:rsi', 'lhs_shift': 0, 'op': '>', 'rhs': 50, 'rhs_shift': 0}], 'enabled': False},
                ]
            },
            'exit': None,
        }
        indicators = {
            'myrsi': {'indicator': 'vbt:RSI', 'enabled': False},
        }
        # Kein Fehler erwartet: deaktivierter Block kann deaktivierten Indikator referenzieren
        _validate_rule_references(rules, indicators)  # kein raise

    def test_disabled_block_and_disabled_indicator_with_active_block_no_error(self):
        """Aktiver Block ohne Indikator-Ref + deaktivierter Block mit deaktiviertem Indikator → kein Fehler."""
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [{'lhs': 'close', 'lhs_shift': 0, 'op': '>', 'rhs': 100, 'rhs_shift': 0}]},  # aktiv, kein Ind.-Ref.
                    {'conditions': [{'lhs': 'indicator:myrsi:rsi', 'lhs_shift': 0, 'op': '>', 'rhs': 50, 'rhs_shift': 0}], 'enabled': False},  # inaktiv
                ]
            },
            'exit': None,
        }
        indicators = {
            'myrsi': {'indicator': 'vbt:RSI', 'enabled': False},
        }
        _validate_rule_references(rules, indicators)  # kein raise

    # ============================================================================
    # 6. D-Fall: aktiver Block referenziert deaktivierten Indikator → weiterhin ValueError
    # ============================================================================

    def test_active_block_with_disabled_indicator_raises(self):
        """Aktiver Block referenziert deaktivierten Indikator → weiterhin ValueError."""
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [{'lhs': 'indicator:myrsi:rsi', 'lhs_shift': 0, 'op': '>', 'rhs': 50, 'rhs_shift': 0}], 'enabled': True},
                ]
            },
            'exit': None,
        }
        indicators = {
            'myrsi': {'indicator': 'vbt:RSI', 'enabled': False},
        }
        with pytest.raises(ValueError, match="deaktivierte Indikatoren"):
            _validate_rule_references(rules, indicators)

    def test_active_block_without_enabled_field_with_disabled_indicator_raises(self):
        """Aktiver Block (kein enabled-Feld) referenziert deaktivierten Indikator → ValueError."""
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [{'lhs': 'indicator:myrsi:rsi', 'lhs_shift': 0, 'op': '>', 'rhs': 50, 'rhs_shift': 0}]},  # kein enabled → gilt als True
                ]
            },
            'exit': None,
        }
        indicators = {
            'myrsi': {'indicator': 'vbt:RSI', 'enabled': False},
        }
        with pytest.raises(ValueError, match="deaktivierte Indikatoren"):
            _validate_rule_references(rules, indicators)

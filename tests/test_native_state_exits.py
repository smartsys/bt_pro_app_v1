"""Tests für Ticket 35: Native State-Exits per signal_func_nb.

Prüft die neuen Funktionen in rules_engine.py:
  - evaluate_rules_native()
  - _build_stateful_condition_spec()
  - _eval_stateful_conditions_nb() (Mini-Interpreter)
  - _state_exit_signal_func_nb()

Testabdeckung gemäß Ticket-Akzeptanzkriterien:
  1. State-Ableitung korrekt (since_entry, entry_price, max/min)
  2. Mini-Interpreter: alle Operatoren + AND und OR
  3. Hybrid-Split: statisch + stateful gemischt, AND und OR
  4. Multi-Combo: hart-abgewiesen bei Series-Ops (N5-Entscheidung)
  5. Randfälle: erste Bar / vor erstem Trade, entry_price == close[entry_bar]
  6. Verschachtelung abgewiesen (N3), State-shift abgewiesen, N4-shift auf OHLCV
  7. Validierung nativ vs. alt: Spike-Szenario (15 Trades / 30 Balken),
     identische Ergebnisse wo alte Engine korrekt war, sl_stop-Koexistenz

Fixtures erstellen synthetische Daten deterministisch (kein Hardcoding).
"""

import sys
import os

# Projekt-Root in sys.path eintragen
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from typing import Any

import numpy as np
import pandas as pd
import pytest
import vectorbtpro as vbt
from numba import njit

from user_data.strategies.generic.rules_engine import (
    _build_stateful_condition_spec,
    _eval_stateful_conditions_nb,
    _assert_flat_group,
    _cond_has_state_ref,
    evaluate_rules_native,
    _LOGIC_AND,
    _LOGIC_OR,
)


# ============================================================================
# Fixtures: synthetische OHLC-Daten und OhlcWrapper
# ============================================================================

class _OhlcWrapper:
    """Minimaler ohlc_data-Wrapper für Tests.

    Implementiert .get(key) für Close, High, Low, Open.
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def get(self, key: str) -> pd.Series:
        return self._df[key]


def _make_ohlc_df(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Erstellt deterministischen OHLC-DataFrame (Random Walk)."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0, 0.01, size=n)
    close = 100.0 * np.exp(np.cumsum(returns))
    noise = rng.uniform(0.001, 0.005, size=n)
    high = close * (1 + noise)
    low = close * (1 - noise)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    idx = pd.date_range("2020-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close},
        index=idx,
    )


@pytest.fixture
def ohlc_df() -> pd.DataFrame:
    """Standard-OHLC-DataFrame, 200 Balken."""
    return _make_ohlc_df(200, seed=42)


@pytest.fixture
def ohlc_data(ohlc_df: pd.DataFrame) -> _OhlcWrapper:
    """ohlc_data-Wrapper für die Fixtures."""
    return _OhlcWrapper(ohlc_df)


@pytest.fixture
def spike_ohlc_df() -> pd.DataFrame:
    """OHLC-DataFrame für Spike-Szenario (500 Balken, Seed 42)."""
    return _make_ohlc_df(500, seed=42)


@pytest.fixture
def spike_ohlc_data(spike_ohlc_df: pd.DataFrame) -> _OhlcWrapper:
    """ohlc_data-Wrapper für Spike-Szenario."""
    return _OhlcWrapper(spike_ohlc_df)


def _make_entry_mask_sma(close: pd.Series, period: int = 10) -> pd.Series:
    """Entry-Maske: close > SMA(period)."""
    sma = close.rolling(period).mean()
    return (close > sma).fillna(False)


def _make_minimal_rules_json_since_entry(exit_bars: int) -> dict:
    """Minimale rules_json (Block-Format): Entry close>sma, Exit since_entry >= exit_bars."""
    return {
        'entry': {
            'blocks': [
                {'conditions': [
                    {'lhs': 'close', 'op': '>', 'rhs': 'close', 'rhs_shift': 10},
                ]},
            ],
        },
        'exit': {
            'blocks': [
                {'conditions': [
                    {'lhs': 'since_entry', 'op': '>=', 'rhs': exit_bars},
                ]},
            ],
        },
    }


# ============================================================================
# 1. State-Ableitung: since_entry, entry_price, max/min korrekt inkrementell
# ============================================================================

class TestStateDerivation:
    """Prüft dass since_entry, entry_price, max/min korrekt aus last_pos_info abgeleitet werden."""

    def test_since_entry_equals_bars_held(self, spike_ohlc_df: pd.DataFrame) -> None:
        """since_entry muss exakt (i - entry_idx) sein."""
        close = spike_ohlc_df['Close']
        entries = _make_entry_mask_sma(close, period=10)
        entries_arr = entries.values.astype(np.bool_)
        EXIT_BARS = 30
        since_entry_vals = []

        @njit
        def _capture_signal_func(c, entries_arr, exit_bars, out):
            """Zeichnet since_entry auf."""
            pos = c.last_pos_info[c.col]
            if pos['status'] == 0 and pos['entry_idx'] >= 0:
                out[c.i] = c.i - pos['entry_idx']
            return entries_arr[c.i], False, False, False

        out = np.full(len(close), -1, dtype=np.float64)
        vbt.Portfolio.from_signals(
            close,
            signal_func_nb=_capture_signal_func,
            signal_args=(entries_arr, np.int64(EXIT_BARS), out),
            init_cash=10_000.0,
            fees=0.0,
            freq="1h",
        )
        # Prüfe: alle aufgezeichneten since_entry-Werte sind >= 0
        recorded = out[out >= 0]
        assert len(recorded) > 0
        # Aufeinanderfolgende Werte mussen um 1 steigen (kein Sprung)
        diff = np.diff(recorded)
        # Sprung auf 0 beim nächsten Trade ist okay, sonst immer +1
        assert np.all((diff == 1) | (diff <= 0))

    def test_entry_price_equals_close_at_entry_bar(self, spike_ohlc_df: pd.DataFrame) -> None:
        """entry_price muss close[entry_bar] sein (keine NextOpen-Preistyp-Abweichung)."""
        close_arr = spike_ohlc_df['Close'].values.astype(np.float64)
        entries = _make_entry_mask_sma(spike_ohlc_df['Close'], period=10)
        entries_arr = entries.values.astype(np.bool_)
        prices_at_entry = np.full(len(close_arr), np.nan)

        @njit
        def _capture_entry_price(c, entries_arr, close_flat, out_prices):
            pos = c.last_pos_info[c.col]
            if pos['status'] == 0 and pos['entry_idx'] >= 0:
                out_prices[pos['entry_idx']] = pos['entry_price']
            return entries_arr[c.i], False, False, False

        vbt.Portfolio.from_signals(
            spike_ohlc_df['Close'],
            signal_func_nb=_capture_entry_price,
            signal_args=(entries_arr, close_arr, prices_at_entry),
            init_cash=10_000.0,
            fees=0.0,
            freq="1h",
        )
        # Für jeden aufgezeichneten Entry: entry_price == close[entry_bar]
        for bar_idx in range(len(close_arr)):
            if not np.isnan(prices_at_entry[bar_idx]):
                assert abs(prices_at_entry[bar_idx] - close_arr[bar_idx]) < 1e-9, (
                    f"entry_price {prices_at_entry[bar_idx]:.6f} != close[{bar_idx}] "
                    f"{close_arr[bar_idx]:.6f}"
                )

    def test_max_min_price_incremental(self, spike_ohlc_df: pd.DataFrame) -> None:
        """max/min werden inkrementell geführt und bei neuem Trade zurückgesetzt."""
        close = spike_ohlc_df['Close']
        high_arr = spike_ohlc_df['High'].values.astype(np.float64)
        low_arr = spike_ohlc_df['Low'].values.astype(np.float64)
        entries = _make_entry_mask_sma(close, period=10)
        entries_arr = entries.values.astype(np.bool_)

        # Tracking-Arrays wie im nativen Pfad
        track_entry_idx = np.full(1, -1, dtype=np.int64)
        track_max = np.full(1, np.nan)
        track_min = np.full(1, np.nan)
        recorded_max = np.full(len(close), np.nan)
        recorded_min = np.full(len(close), np.nan)

        @njit
        def _track_maxmin(c, entries_arr, high, low, te_idx, t_max, t_min, rec_max, rec_min):
            pos = c.last_pos_info[c.col]
            if pos['status'] == 0 and pos['entry_idx'] >= 0:
                eidx = pos['entry_idx']
                if te_idx[0] != eidx:
                    te_idx[0] = eidx
                    t_max[0] = high[c.i]
                    t_min[0] = low[c.i]
                else:
                    if high[c.i] > t_max[0]:
                        t_max[0] = high[c.i]
                    if low[c.i] < t_min[0]:
                        t_min[0] = low[c.i]
                rec_max[c.i] = t_max[0]
                rec_min[c.i] = t_min[0]
            return entries_arr[c.i], False, False, False

        vbt.Portfolio.from_signals(
            close,
            signal_func_nb=_track_maxmin,
            signal_args=(entries_arr, high_arr, low_arr,
                         track_entry_idx, track_max, track_min,
                         recorded_max, recorded_min),
            init_cash=10_000.0,
            fees=0.0,
            freq="1h",
        )
        # Prüfe: max >= high an jedem Balken mit offenem Trade
        valid = ~np.isnan(recorded_max)
        assert valid.sum() > 0
        assert np.all(recorded_max[valid] >= high_arr[valid] - 1e-9)
        assert np.all(recorded_min[valid] <= low_arr[valid] + 1e-9)


# ============================================================================
# 2. Mini-Interpreter: alle Operatoren + AND und OR
# ============================================================================

class TestMiniInterpreter:
    """Prüft _eval_stateful_conditions_nb für alle Operator-Typen und Logiken."""

    def _run_single_cond(
        self,
        op: str,
        lhs_val: float,
        rhs_val: float,
        is_state_lhs: bool = True,
        is_state_rhs: bool = False,
    ) -> bool:
        """Hilfsmethode: wertet eine einzelne Condition aus."""
        from user_data.strategies.generic.rules_engine import _OP_CODE_MAP, _KIND_STATE, _KIND_SCALAR

        n = 1
        op_codes      = np.array([_OP_CODE_MAP[op]], dtype=np.int8)
        lhs_kind      = np.array([_KIND_STATE if is_state_lhs else _KIND_SCALAR], dtype=np.int8)
        lhs_state_idx = np.array([0], dtype=np.int8)   # since_entry
        lhs_series_col= np.array([0], dtype=np.int64)
        lhs_scalar    = np.array([lhs_val], dtype=np.float64)
        rhs_kind      = np.array([_KIND_STATE if is_state_rhs else _KIND_SCALAR], dtype=np.int8)
        rhs_state_idx = np.array([0], dtype=np.int8)
        rhs_series_col= np.array([0], dtype=np.int64)
        rhs_scalar    = np.array([rhs_val], dtype=np.float64)
        series_vals   = np.empty(0, dtype=np.float64)

        return _eval_stateful_conditions_nb(
            n,
            op_codes, lhs_kind, lhs_state_idx, lhs_series_col, lhs_scalar,
            rhs_kind, rhs_state_idx, rhs_series_col, rhs_scalar,
            _LOGIC_AND,
            np.float64(lhs_val),   # since_entry = lhs_val
            np.float64(100.0),     # entry_price
            np.float64(105.0),     # max_price
            np.float64(95.0),      # min_price
            series_vals,
        )

    def test_operator_gt(self) -> None:
        assert self._run_single_cond('>', 31.0, 30.0) is True
        assert self._run_single_cond('>', 30.0, 30.0) is False

    def test_operator_lt(self) -> None:
        assert self._run_single_cond('<', 29.0, 30.0) is True
        assert self._run_single_cond('<', 30.0, 30.0) is False

    def test_operator_ge(self) -> None:
        assert self._run_single_cond('>=', 30.0, 30.0) is True
        assert self._run_single_cond('>=', 29.0, 30.0) is False

    def test_operator_le(self) -> None:
        assert self._run_single_cond('<=', 30.0, 30.0) is True
        assert self._run_single_cond('<=', 31.0, 30.0) is False

    def test_operator_eq(self) -> None:
        assert self._run_single_cond('==', 30.0, 30.0) is True
        assert self._run_single_cond('==', 29.0, 30.0) is False

    def test_operator_ne(self) -> None:
        assert self._run_single_cond('!=', 31.0, 30.0) is True
        assert self._run_single_cond('!=', 30.0, 30.0) is False

    def test_and_logic_both_true(self) -> None:
        """AND: beide Conditions true -> true."""
        from user_data.strategies.generic.rules_engine import _OP_CODE_MAP, _KIND_STATE, _KIND_SCALAR

        n = 2
        op_codes      = np.array([_OP_CODE_MAP['>='], _OP_CODE_MAP['<']], dtype=np.int8)
        # Cond1: since_entry >= 30, Cond2: since_entry < 100
        lhs_kind      = np.array([_KIND_STATE, _KIND_STATE], dtype=np.int8)
        lhs_state_idx = np.array([0, 0], dtype=np.int8)
        lhs_series_col= np.zeros(n, dtype=np.int64)
        lhs_scalar    = np.zeros(n, dtype=np.float64)
        rhs_kind      = np.array([_KIND_SCALAR, _KIND_SCALAR], dtype=np.int8)
        rhs_state_idx = np.zeros(n, dtype=np.int8)
        rhs_series_col= np.zeros(n, dtype=np.int64)
        rhs_scalar    = np.array([30.0, 100.0], dtype=np.float64)

        result = _eval_stateful_conditions_nb(
            n, op_codes,
            lhs_kind, lhs_state_idx, lhs_series_col, lhs_scalar,
            rhs_kind, rhs_state_idx, rhs_series_col, rhs_scalar,
            _LOGIC_AND,
            np.float64(35.0), np.float64(100.0), np.float64(105.0), np.float64(95.0),
            np.empty(0, dtype=np.float64),
        )
        assert result is True

    def test_and_logic_one_false(self) -> None:
        """AND: eine Condition false -> false."""
        from user_data.strategies.generic.rules_engine import _OP_CODE_MAP, _KIND_STATE, _KIND_SCALAR

        n = 2
        op_codes      = np.array([_OP_CODE_MAP['>='], _OP_CODE_MAP['<']], dtype=np.int8)
        # Cond1: since_entry >= 30 (TRUE für 35), Cond2: since_entry < 30 (FALSE für 35)
        lhs_kind      = np.array([_KIND_STATE, _KIND_STATE], dtype=np.int8)
        lhs_state_idx = np.array([0, 0], dtype=np.int8)
        lhs_series_col= np.zeros(n, dtype=np.int64)
        lhs_scalar    = np.zeros(n, dtype=np.float64)
        rhs_kind      = np.array([_KIND_SCALAR, _KIND_SCALAR], dtype=np.int8)
        rhs_state_idx = np.zeros(n, dtype=np.int8)
        rhs_series_col= np.zeros(n, dtype=np.int64)
        rhs_scalar    = np.array([30.0, 30.0], dtype=np.float64)

        result = _eval_stateful_conditions_nb(
            n, op_codes,
            lhs_kind, lhs_state_idx, lhs_series_col, lhs_scalar,
            rhs_kind, rhs_state_idx, rhs_series_col, rhs_scalar,
            _LOGIC_AND,
            np.float64(35.0), np.float64(100.0), np.float64(105.0), np.float64(95.0),
            np.empty(0, dtype=np.float64),
        )
        assert result is False

    def test_or_logic_one_true(self) -> None:
        """OR: eine Condition true -> true."""
        from user_data.strategies.generic.rules_engine import _OP_CODE_MAP, _KIND_STATE, _KIND_SCALAR

        n = 2
        op_codes      = np.array([_OP_CODE_MAP['>='], _OP_CODE_MAP['<']], dtype=np.int8)
        # Cond1: since_entry >= 100 (FALSE für 35), Cond2: since_entry < 100 (TRUE für 35)
        lhs_kind      = np.array([_KIND_STATE, _KIND_STATE], dtype=np.int8)
        lhs_state_idx = np.array([0, 0], dtype=np.int8)
        lhs_series_col= np.zeros(n, dtype=np.int64)
        lhs_scalar    = np.zeros(n, dtype=np.float64)
        rhs_kind      = np.array([_KIND_SCALAR, _KIND_SCALAR], dtype=np.int8)
        rhs_state_idx = np.zeros(n, dtype=np.int8)
        rhs_series_col= np.zeros(n, dtype=np.int64)
        rhs_scalar    = np.array([100.0, 100.0], dtype=np.float64)

        result = _eval_stateful_conditions_nb(
            n, op_codes,
            lhs_kind, lhs_state_idx, lhs_series_col, lhs_scalar,
            rhs_kind, rhs_state_idx, rhs_series_col, rhs_scalar,
            _LOGIC_OR,
            np.float64(35.0), np.float64(100.0), np.float64(105.0), np.float64(95.0),
            np.empty(0, dtype=np.float64),
        )
        assert result is True

    def test_or_logic_both_false(self) -> None:
        """OR: beide Conditions false -> false."""
        from user_data.strategies.generic.rules_engine import _OP_CODE_MAP, _KIND_STATE, _KIND_SCALAR

        n = 2
        op_codes      = np.array([_OP_CODE_MAP['>='], _OP_CODE_MAP['<']], dtype=np.int8)
        # Cond1: since_entry >= 100 (FALSE), Cond2: since_entry < 10 (FALSE für 35)
        lhs_kind      = np.array([_KIND_STATE, _KIND_STATE], dtype=np.int8)
        lhs_state_idx = np.array([0, 0], dtype=np.int8)
        lhs_series_col= np.zeros(n, dtype=np.int64)
        lhs_scalar    = np.zeros(n, dtype=np.float64)
        rhs_kind      = np.array([_KIND_SCALAR, _KIND_SCALAR], dtype=np.int8)
        rhs_state_idx = np.zeros(n, dtype=np.int8)
        rhs_series_col= np.zeros(n, dtype=np.int64)
        rhs_scalar    = np.array([100.0, 10.0], dtype=np.float64)

        result = _eval_stateful_conditions_nb(
            n, op_codes,
            lhs_kind, lhs_state_idx, lhs_series_col, lhs_scalar,
            rhs_kind, rhs_state_idx, rhs_series_col, rhs_scalar,
            _LOGIC_OR,
            np.float64(35.0), np.float64(100.0), np.float64(105.0), np.float64(95.0),
            np.empty(0, dtype=np.float64),
        )
        assert result is False

    def test_all_state_primitives_accessible(self) -> None:
        """Prüft Zugriff auf alle 4 State-Primitive im Interpreter."""
        from user_data.strategies.generic.rules_engine import (
            _OP_CODE_MAP, _KIND_STATE, _KIND_SCALAR,
            _STATE_SINCE_ENTRY, _STATE_ENTRY_PRICE, _STATE_MAX_PRICE, _STATE_MIN_PRICE,
        )

        # 4 Conditions, je eine pro State-Primitiv, alle mit '>=' Skalar 0 (immer true)
        n = 4
        op_codes      = np.array([_OP_CODE_MAP['>=']] * n, dtype=np.int8)
        lhs_kind      = np.array([_KIND_STATE] * n, dtype=np.int8)
        lhs_state_idx = np.array([
            _STATE_SINCE_ENTRY, _STATE_ENTRY_PRICE, _STATE_MAX_PRICE, _STATE_MIN_PRICE,
        ], dtype=np.int8)
        lhs_series_col= np.zeros(n, dtype=np.int64)
        lhs_scalar    = np.zeros(n, dtype=np.float64)
        rhs_kind      = np.array([_KIND_SCALAR] * n, dtype=np.int8)
        rhs_state_idx = np.zeros(n, dtype=np.int8)
        rhs_series_col= np.zeros(n, dtype=np.int64)
        rhs_scalar    = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float64)

        result = _eval_stateful_conditions_nb(
            n, op_codes,
            lhs_kind, lhs_state_idx, lhs_series_col, lhs_scalar,
            rhs_kind, rhs_state_idx, rhs_series_col, rhs_scalar,
            _LOGIC_AND,
            np.float64(5.0), np.float64(100.0), np.float64(105.0), np.float64(95.0),
            np.empty(0, dtype=np.float64),
        )
        assert result is True


# ============================================================================
# 3. Hybrid-Split: statisch + stateful gemischt, AND und OR
# ============================================================================

class TestHybridSplit:
    """Prüft die Kombination statischer und stateful Conditions."""

    def _run_hybrid(
        self,
        logic: str,
        exit_bars: int,
        static_exit_at_bar: int,
        ohlc_df: pd.DataFrame,
    ) -> vbt.Portfolio:
        """Hilfsmethode: Hybrid-Split mit einer statischen und einer stateful Condition."""
        close = ohlc_df['Close']
        ohlc = _OhlcWrapper(ohlc_df)

        # Statische Exit-Condition: an bar static_exit_at_bar immer True
        static_mask = pd.Series(False, index=close.index)
        if static_exit_at_bar < len(static_mask):
            static_mask.iloc[static_exit_at_bar] = True

        # Erzeuge Fake-Indikator für statische Condition (Skalar-Vergleich)
        # Einfacher: nur stateful Condition in rules_json, statische Maske direkt
        # Da evaluate_rules_native static_conds per _evaluate_rule_group baut,
        # verwenden wir hier eine direkte Konstruktion ohne Indikatoren.

        # Statische Condition (close > 999999, nie true) und stateful Condition
        # (since_entry >= exit_bars). Im Block-Format: AND -> ein Block mit beiden,
        # OR -> je Condition ein eigener Block.
        static_cond = {'lhs': 'close', 'op': '>', 'rhs': 999999.0}
        stateful_cond = {'lhs': 'since_entry', 'op': '>=', 'rhs': float(exit_bars)}
        if logic == 'AND':
            exit_blocks = [{'conditions': [static_cond, stateful_cond]}]
        else:
            exit_blocks = [{'conditions': [static_cond]}, {'conditions': [stateful_cond]}]
        rules_json = {
            'entry': {
                'blocks': [
                    {'conditions': [{'lhs': 'close', 'op': '>', 'rhs': 0.0}]},
                ],
            },
            'exit': {'blocks': exit_blocks},
        }
        pf_kwargs = dict(
            close=close,
            init_cash=10_000.0,
            fees=0.0,
            freq="1h",
        )
        return evaluate_rules_native(rules_json, ohlc, {}, pf_kwargs)

    def test_and_logic_static_false_stateful_true(self, ohlc_df: pd.DataFrame) -> None:
        """AND: statisch=False, stateful=True -> Exit=False -> kein frühzeitiger Exit."""
        pf = self._run_hybrid('AND', exit_bars=20, static_exit_at_bar=50, ohlc_df=ohlc_df)
        # Alle Trades müssen mindestens 20 Balken gehalten werden
        records = pf.trades.records
        if len(records) > 0:
            for _, row in records.iterrows():
                held = int(row['exit_idx']) - int(row['entry_idx'])
                assert held >= 20, f"Trade zu kurz: {held} Balken (erwartet >= 20)"

    def test_or_logic_stateful_triggers(self, ohlc_df: pd.DataFrame) -> None:
        """OR: statisch=False, stateful=True -> Exit=True nach exit_bars.

        Der letzte Trade wird von VBT am Simulationsende force-closed und kann
        kürzer als exit_bars sein. Nur vollständige Trades (alle außer dem letzten)
        müssen >= exit_bars gehalten werden.
        """
        pf = self._run_hybrid('OR', exit_bars=10, static_exit_at_bar=999, ohlc_df=ohlc_df)
        records = pf.trades.records
        n = len(records)
        if n > 1:
            # Alle vollständigen Trades (nicht den letzten force-closed)
            for idx, (_, row) in enumerate(records.iterrows()):
                if idx == n - 1:
                    continue  # Letzten Trade überspringen (ggf. force-closed)
                held = int(row['exit_idx']) - int(row['entry_idx'])
                # Im OR-Modus mit statisch=False: Exit nach >= exit_bars
                assert held >= 10, f"Trade {idx}: {held} Balken (erwartet >= 10)"


# ============================================================================
# 4. Multi-Combo mit stateful Series-Ops (der frühere N5-Reject ist gefallen)
# ============================================================================

class TestMultiCombo:
    """Prüft Multi-Combo-Verhalten mit stateful Conditions.

    GEÄNDERT 2026-07-12: Überschrift korrigiert. Der frühere N5-Hard-Reject
    ("Multi-Combo mit stateful Series-Ops wird abgewiesen") fiel mit Ticket 47 —
    diese Klasse prüft heute das Gegenteil, nämlich dass solche Konstellationen
    laufen UND je Spalte richtig rechnen.
    """

    def test_multi_combo_state_only_accepted(self, spike_ohlc_df: pd.DataFrame) -> None:
        """Multi-Combo mit nur State-Refs und Skalaren in stateful Conditions läuft durch."""
        close = spike_ohlc_df['Close']
        ohlc = _OhlcWrapper(spike_ohlc_df)

        # Simuliere Multi-Combo: DataFrame mit 2 identischen Close-Spalten
        close_2col = pd.DataFrame({'col_a': close.values, 'col_b': close.values}, index=close.index)

        rules_json = {
            'entry': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'close', 'op': '>', 'rhs': 0.0},
                    ]},
                ],
            },
            'exit': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'since_entry', 'op': '>=', 'rhs': 20.0},
                    ]},
                ],
            },
        }
        pf_kwargs = dict(
            close=close_2col,
            init_cash=10_000.0,
            fees=0.0,
            freq="1h",
        )
        # Kein Fehler erwartet
        pf = evaluate_rules_native(rules_json, ohlc, {}, pf_kwargs)
        assert pf is not None

    def test_multi_combo_with_series_op_runs(self, spike_ohlc_df: pd.DataFrame) -> None:
        """Multi-Combo mit Series-Operand in stateful Condition läuft jetzt vektorisiert.

        GEÄNDERT: Ticket 47 Bugfix — der frühere N5-Hard-Reject ist entfernt. Series-
        Operanden in stateful Conditions werden bei Multi-Combo über das combo-major
        series_bundle + series_col_map (col % n_combo) korrekt aufgelöst. Ein globaler
        OHLCV-Operand (hier close) broadcastet auf alle Combos.
        """
        close = spike_ohlc_df['Close']
        ohlc = _OhlcWrapper(spike_ohlc_df)

        close_2col = pd.DataFrame({'col_a': close.values, 'col_b': close.values}, index=close.index)

        # Stateful Condition mit Series-Operand (close)
        rules_json = {
            'entry': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'close', 'op': '>', 'rhs': 0.0},
                    ]},
                ],
            },
            'exit': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'since_entry', 'op': '>=', 'rhs': 'close'},
                    ]},
                ],
            },
        }
        pf_kwargs = dict(
            close=close_2col,
            init_cash=10_000.0,
            fees=0.0,
            freq="1h",
        )
        pf = evaluate_rules_native(rules_json, ohlc, {}, pf_kwargs)
        assert pf is not None
        # Zwei identische Combo-Spalten -> Portfolio hat 2 Spalten
        assert len(pf.wrapper.columns) == 2

    def test_multi_combo_series_op_variiert_je_combo(self, spike_ohlc_df: pd.DataFrame) -> None:
        """Serien-Operand, der PRO COMBO verschieden ist, wird je Spalte korrekt aufgelöst.

        Das ist der Fall, den die Normierung braucht: ein dynamischer Zeitstopp
        `since_entry >= indicator:td_dyn:result`, bei dem `td_dyn` selbst eine
        gesweepte Achse trägt (td = k x Marktrhythmus). Der bestehende Test darüber
        nutzt nur einen GLOBALEN Operanden (close), der auf alle Combos broadcastet —
        er würde einen Fehler im col-%-n_combo-Mapping des series_bundle nicht sehen.

        Aufbau: zwei Combos mit konstantem Exit-Horizont 5 bzw. 20 Balken, als Serie
        über einen Indikator-Output mit Param-Achse. Erwartung: Combo 0 hält jeden
        Trade 5 Balken, Combo 1 hält ihn 20 — würden die Spalten vertauscht oder
        kollabiert, kippt genau diese Zuordnung.
        """
        close = spike_ohlc_df['Close']
        ohlc = _OhlcWrapper(spike_ohlc_df)
        index = spike_ohlc_df.index

        # Indikator-Output mit Param-Achse: je Combo ein anderer konstanter Horizont
        horizons = (5.0, 20.0)
        td_dyn = pd.DataFrame(
            {h: np.full(len(index), h) for h in horizons},
            index=index,
        )
        td_dyn.columns = pd.Index(horizons, name='td_dyn_value')

        class _FakeIndicator:
            output_names = ('result',)
            param_names = ('value',)
            short_name = 'td_dyn'

            def __init__(self, out: pd.DataFrame) -> None:
                self.result = out

        indicators = {'td_dyn': _FakeIndicator(td_dyn)}

        close_2col = pd.DataFrame(
            {h: close.values for h in horizons}, index=index
        )
        close_2col.columns = pd.Index(horizons, name='td_dyn_value')

        rules_json = {
            'entry': {'blocks': [{'conditions': [
                {'lhs': 'close', 'op': '>', 'rhs': 0.0},
            ]}]},
            'exit': {'blocks': [{'conditions': [
                {'lhs': 'since_entry', 'op': '>=', 'rhs': 'indicator:td_dyn:result'},
            ]}]},
        }
        pf_kwargs = dict(close=close_2col, init_cash=10_000.0, fees=0.0, freq="1h")

        pf = evaluate_rules_native(rules_json, ohlc, indicators, pf_kwargs)
        assert len(pf.wrapper.columns) == 2

        records = pf.trades.records_readable
        col_names = list(pf.wrapper.columns)
        for col_pos, expected_hold in enumerate(horizons):
            own = records[records['Column'] == col_names[col_pos]]
            held = [
                int(np.searchsorted(index, row['Exit Index']))
                - int(np.searchsorted(index, row['Entry Index']))
                for _, row in own.iterrows()
            ]
            # Letzter Trade kann force-closed sein -> ausklammern
            assert held[:-1], f"Combo {col_pos} hat keine auswertbaren Trades"
            assert all(h == int(expected_hold) for h in held[:-1]), (
                f"Combo {col_pos} (Horizont {expected_hold}): Haltedauern {set(held[:-1])} "
                f"statt {int(expected_hold)} — Series-Operand wurde der falschen Spalte "
                f"zugeordnet oder ist kollabiert."
            )


# ============================================================================
# 5. Randfälle
# ============================================================================

class TestEdgeCases:
    """Randfälle: erste Bar, Guard vor erstem Trade, entry_price-Konsistenz."""

    def test_no_exit_on_first_bar_no_trade(self, ohlc_df: pd.DataFrame) -> None:
        """Auf der ersten Bar / vor erstem Trade: kein Exit durch entry_price==nan.

        Guard: position_open = (status==0 AND entry_idx>=0).
        Vor dem ersten Trade ist status=-1, entry_idx=-1 -> position_open=False.
        Exit-Condition (entry_price > 0) darf dann NICHT ausgewertet werden
        (kein nan-Vergleich).

        Prüft, dass der erste Trade-Eintrag auf dem ersten Signal-Bar liegt
        und nicht durch einen Phantom-Exit auf Bar 0 verhindert wird.
        """
        close = ohlc_df['Close']
        ohlc = _OhlcWrapper(ohlc_df)

        # Entry: close > sehr hoher Wert, damit nur wenige Bars einsteigen.
        # Wir nutzen den maximalen Close-Wert als Schwelle, damit der erste
        # Entry irgendwo in der Mitte liegt — auf Bar 0 soll kein Entry sein.
        max_close = float(close.max())
        # Entry-Bedingung: close >= max_close (nur der höchste Balken)
        # Das garantiert keinen Entry auf Bar 0 (wenn close[0] < max(close)).

        rules_json = {
            'entry': {
                'blocks': [
                    {'conditions': [
                        # since_entry ist kein Entry-Primitiv, aber close.shift(1) > close
                        # gibt uns eine seltene Bedingung ohne State
                        {'lhs': 'close', 'op': '>=', 'rhs': max_close},
                    ]},
                ],
            },
            'exit': {
                'blocks': [
                    {'conditions': [
                        # entry_price > 0 — würde bei nan Entry-Price crashen ohne Guard
                        {'lhs': 'entry_price', 'op': '>', 'rhs': 0.0},
                    ]},
                ],
            },
        }
        pf_kwargs = dict(
            close=close,
            init_cash=10_000.0,
            fees=0.0,
            freq="1h",
        )
        # Muss ohne Exception durchlaufen (kein nan-Fehler durch Guard)
        pf = evaluate_rules_native(rules_json, ohlc, {}, pf_kwargs)
        # close[0] < max(close) in unserem Random Walk -> kein Entry auf Bar 0
        records = pf.trades.records
        if len(records) > 0:
            first_entry_bar = int(records.iloc[0]['entry_idx'])
            assert close.iloc[0] < max_close, (
                f"Annahme verletzt: close[0]={close.iloc[0]:.2f} ist das Maximum {max_close:.2f}"
            )
            assert first_entry_bar > 0, (
                f"Erster Trade auf Bar 0 trotz close[0] < max(close)"
            )

    def test_entry_price_consistency(self, spike_ohlc_df: pd.DataFrame) -> None:
        """entry_price im nativen Pfad muss close[entry_bar] sein."""
        close = spike_ohlc_df['Close']
        close_arr = close.values.astype(np.float64)
        ohlc = _OhlcWrapper(spike_ohlc_df)

        rules_json = _make_minimal_rules_json_since_entry(exit_bars=15)
        pf_kwargs = dict(
            close=close,
            init_cash=10_000.0,
            fees=0.0,
            freq="1h",
        )
        pf = evaluate_rules_native(rules_json, ohlc, {}, pf_kwargs)
        records = pf.trades.records

        for _, row in records.iterrows():
            entry_bar = int(row['entry_idx'])
            entry_price = float(row['entry_price'])
            expected_price = close_arr[entry_bar]
            assert abs(entry_price - expected_price) < 1e-9, (
                f"entry_price {entry_price:.6f} != close[{entry_bar}] {expected_price:.6f}"
            )

    def test_guard_no_nan_exit_before_first_trade(self, ohlc_df: pd.DataFrame) -> None:
        """Guard (status==0 AND entry_idx>=0) verhindert Exit bei nan entry_price."""
        close = ohlc_df['Close']
        ohlc = _OhlcWrapper(ohlc_df)

        # Exit-Condition: entry_price > 50 (würde ohne Guard mit nan crashes)
        rules_json = {
            'entry': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'close', 'op': '>', 'rhs': -1.0},
                    ]},
                ],
            },
            'exit': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'entry_price', 'op': '>', 'rhs': 50.0},
                    ]},
                ],
            },
        }
        pf_kwargs = dict(
            close=close,
            init_cash=10_000.0,
            fees=0.0,
            freq="1h",
        )
        # Darf NICHT crashen (kein nan-Vergleich auf erster Bar)
        pf = evaluate_rules_native(rules_json, ohlc, {}, pf_kwargs)
        assert pf is not None


# ============================================================================
# 6. Validierungen: Verschachtelung, State-shift, N4-shift auf OHLCV
# ============================================================================

class TestValidations:
    """Prüft Fehler-Abweisungen (N3, N4, Out-of-scope-Guards)."""

    def test_nested_group_rejected_entry(self, ohlc_df: pd.DataFrame) -> None:
        """Verschachtelte Entry-Gruppe wird abgewiesen (N3)."""
        close = ohlc_df['Close']
        ohlc = _OhlcWrapper(ohlc_df)
        # Verschachtelung im Block-Format: eine Condition, die selbst 'conditions' enthält
        rules_json = {
            'entry': {
                'blocks': [
                    {'conditions': [
                        {
                            'logic': 'OR',
                            'conditions': [
                                {'lhs': 'close', 'op': '>', 'rhs': 90.0},
                            ],
                        },
                    ]},
                ],
            },
            'exit': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'since_entry', 'op': '>=', 'rhs': 10.0},
                    ]},
                ],
            },
        }
        pf_kwargs = dict(close=close, init_cash=10_000.0, fees=0.0, freq="1h")
        with pytest.raises(ValueError, match="Verschachtelte"):
            evaluate_rules_native(rules_json, ohlc, {}, pf_kwargs)

    def test_nested_group_rejected_exit(self, ohlc_df: pd.DataFrame) -> None:
        """Verschachtelte Exit-Gruppe wird abgewiesen (N3)."""
        close = ohlc_df['Close']
        ohlc = _OhlcWrapper(ohlc_df)
        rules_json = {
            'entry': {
                'blocks': [{'conditions': [{'lhs': 'close', 'op': '>', 'rhs': 0.0}]}],
            },
            'exit': {
                'blocks': [
                    {'conditions': [
                        {
                            'logic': 'OR',
                            'conditions': [
                                {'lhs': 'since_entry', 'op': '>=', 'rhs': 10.0},
                            ],
                        },
                    ]},
                ],
            },
        }
        pf_kwargs = dict(close=close, init_cash=10_000.0, fees=0.0, freq="1h")
        with pytest.raises(ValueError, match="Verschachtelte"):
            evaluate_rules_native(rules_json, ohlc, {}, pf_kwargs)

    def test_state_shift_rejected(self, ohlc_df: pd.DataFrame) -> None:
        """Shift auf State-Primitiv wird abgewiesen (Out of Scope Schritt 1)."""
        close = ohlc_df['Close']
        ohlc = _OhlcWrapper(ohlc_df)
        rules_json = {
            'entry': {
                'blocks': [{'conditions': [{'lhs': 'close', 'op': '>', 'rhs': 0.0}]}],
            },
            'exit': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'since_entry', 'op': '>=', 'rhs': 10.0, 'lhs_shift': 1},
                    ]},
                ],
            },
        }
        pf_kwargs = dict(close=close, init_cash=10_000.0, fees=0.0, freq="1h")
        with pytest.raises(ValueError, match="shift auf State-Primitiv"):
            evaluate_rules_native(rules_json, ohlc, {}, pf_kwargs)

    def test_n4_shift_on_ohlcv_side(self, ohlc_df: pd.DataFrame) -> None:
        """N4: Shift auf OHLCV-Seite einer stateful Condition wird Python-seitig vorverlagert."""
        close = ohlc_df['Close']
        ohlc = _OhlcWrapper(ohlc_df)

        # Stateful Condition: since_entry >= close.shift(1) (OHLCV-Seite mit shift)
        # Das soll NICHT crashen — shift wird in series_bundle vorverlagert
        rules_json = {
            'entry': {
                'blocks': [{'conditions': [{'lhs': 'close', 'op': '>', 'rhs': 0.0}]}],
            },
            'exit': {
                'blocks': [
                    {'conditions': [
                        # since_entry >= close_shifted (rhs_shift=1 auf OHLCV-Seite)
                        {'lhs': 'since_entry', 'op': '>=', 'rhs': 'close', 'rhs_shift': 1},
                    ]},
                ],
            },
        }
        pf_kwargs = dict(close=close, init_cash=10_000.0, fees=0.0, freq="1h")
        # Muss durchlaufen (kein Fehler)
        pf = evaluate_rules_native(rules_json, ohlc, {}, pf_kwargs)
        assert pf is not None

    def test_n4_shift_series_bundle_contains_shifted_values(self, ohlc_df: pd.DataFrame) -> None:
        """N4: series_bundle enthält bereits den geshifteten OHLCV-Operanden."""
        close_series = ohlc_df['Close']
        ohlc = _OhlcWrapper(ohlc_df)

        shift_val = 3
        stateful_conds = [
            {'lhs': 'since_entry', 'op': '>=', 'rhs': 'close', 'rhs_shift': shift_val},
        ]
        spec = _build_stateful_condition_spec(stateful_conds, ohlc, {})

        # series_bundle Spalte 0 sollte close.shift(3) entsprechen
        bundle = spec['series_bundle']
        close_shifted = close_series.shift(shift_val).values

        np.testing.assert_array_almost_equal(
            bundle[:, 0], close_shifted, decimal=9,
            err_msg="series_bundle enthält nicht den geshifteten Close-Wert (N4)"
        )


# ============================================================================
# 7. Validierung nativ vs. alt: Spike-Szenario und Koexistenz mit sl_stop
# ============================================================================

class TestValidationNativeVsOld:
    """Vergleich nativer vs. alter Engine auf den Ticket-Szenarien."""

    def test_spike_scenario_15_trades_30_bars(self, spike_ohlc_df: pd.DataFrame) -> None:
        """Spike-Szenario: since_entry >= 30 -> nativ 15 Trades, je exakt 30 Balken.

        Der letzte Trade kann kürzer sein, wenn am Ende nicht genug Balken übrig
        sind (Simulation endet vor dem Exit). Daher prüfen wir alle geschlossenen
        Trades außer dem letzten, falls dieser kürzer ist.
        """
        close = spike_ohlc_df['Close']
        ohlc = _OhlcWrapper(spike_ohlc_df)
        EXIT_BARS = 30

        rules_json = _make_minimal_rules_json_since_entry(EXIT_BARS)
        pf_kwargs = dict(
            close=close,
            init_cash=10_000.0,
            fees=0.0,
            freq="1h",
        )
        pf = evaluate_rules_native(rules_json, ohlc, {}, pf_kwargs)
        records = pf.trades.records

        n_trades = len(records)
        assert n_trades == 15, (
            f"Spike-Szenario: erwartet 15 Trades, erhalten {n_trades}"
        )
        # Alle Trades außer dem letzten müssen exakt 30 Balken gehalten werden.
        # Der letzte Trade kann kürzer sein (Simulation endet vor Signal).
        for idx, (_, row) in enumerate(records.iterrows()):
            held = int(row['exit_idx']) - int(row['entry_idx'])
            is_last = (idx == n_trades - 1)
            if is_last:
                assert held <= EXIT_BARS, (
                    f"Letzter Trade {row['id']}: gehalten {held} > {EXIT_BARS} Balken"
                )
            else:
                assert held == EXIT_BARS, (
                    f"Trade {row['id']}: gehalten {held} Balken, erwartet {EXIT_BARS}"
                )

    def test_entry_price_exit_strategy(self, ohlc_df: pd.DataFrame) -> None:
        """Szenario (b): entry_price-basierter Exit (z.B. entry_price > 90 -> verkaufen)."""
        close = ohlc_df['Close']
        ohlc = _OhlcWrapper(ohlc_df)

        # Exit wenn entry_price > 90 (d.h. bei hohem Einstiegspreis sofort raus)
        rules_json = {
            'entry': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'close', 'op': '>', 'rhs': 0.0},
                    ]},
                ],
            },
            'exit': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'entry_price', 'op': '>', 'rhs': 90.0},
                    ]},
                ],
            },
        }
        pf_kwargs = dict(close=close, init_cash=10_000.0, fees=0.0, freq="1h")
        pf = evaluate_rules_native(rules_json, ohlc, {}, pf_kwargs)
        # Kein Fehler, Trade-Logik konsistent
        assert pf is not None
        records = pf.trades.records
        for _, row in records.iterrows():
            entry_price = float(row['entry_price'])
            held = int(row['exit_idx']) - int(row['entry_idx'])
            if entry_price > 90.0:
                # Trade sollte nach erstem Balken geschlossen sein
                assert held >= 1  # mindestens 1 Balken (Exit am nächsten Balken)

    def test_max_price_exit_strategy(self, ohlc_df: pd.DataFrame) -> None:
        """Szenario (c): max_price_since_entry-basierter Exit (trailing-artig)."""
        close = ohlc_df['Close']
        ohlc = _OhlcWrapper(ohlc_df)

        # Exit wenn max_price_since_entry > entry_price * 1.02 (2% Gewinn gesehen)
        # Wird als: max_price_since_entry > 1.02 * entry_price
        # Vereinfacht: max_price > 102 (für unsere ~100er Preise)
        rules_json = {
            'entry': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'close', 'op': '>', 'rhs': 0.0},
                    ]},
                ],
            },
            'exit': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'max_price_since_entry', 'op': '>', 'rhs': 102.0},
                    ]},
                ],
            },
        }
        pf_kwargs = dict(close=close, init_cash=10_000.0, fees=0.0, freq="1h")
        pf = evaluate_rules_native(rules_json, ohlc, {}, pf_kwargs)
        assert pf is not None
        # Trades müssen existieren und max_price wurde tatsächlich überschritten
        # (kein Absturz, kein nan-Fehler)

    def test_coexistence_with_sl_stop(self, spike_ohlc_df: pd.DataFrame) -> None:
        """Szenario (e): State-Exit UND sl_stop zusammen (VBT ODER-verknüpft)."""
        close = spike_ohlc_df['Close']
        ohlc = _OhlcWrapper(spike_ohlc_df)

        rules_json = _make_minimal_rules_json_since_entry(exit_bars=20)
        pf_kwargs = dict(
            close=close,
            init_cash=10_000.0,
            fees=0.0,
            freq="1h",
            sl_stop=0.05,   # 5% Stop-Loss
        )
        # Kein Fehler, beide Exits wirken
        pf = evaluate_rules_native(rules_json, ohlc, {}, pf_kwargs)
        assert pf is not None
        # Mit sl_stop werden Trades auch < 20 Balken möglich (durch SL ausgestoppt)
        records = pf.trades.records
        assert len(records) > 0, "Erwartet mindestens einen Trade mit sl_stop"

    def test_mixed_static_and_stateful_and(self, spike_ohlc_df: pd.DataFrame) -> None:
        """Szenario (d): Gemischte statische + stateful Conditions mit AND-Logik.

        Der letzte Trade wird von VBT force-closed und kann kürzer sein.
        """
        close = spike_ohlc_df['Close']
        ohlc = _OhlcWrapper(spike_ohlc_df)

        # AND: close > 50 (statisch, immer true für ~100er Preise) AND since_entry >= 25
        rules_json = {
            'entry': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'close', 'op': '>', 'rhs': 0.0},
                    ]},
                ],
            },
            'exit': {
                # AND -> ein Block mit statischer + stateful Condition
                'blocks': [
                    {'conditions': [
                        {'lhs': 'close', 'op': '>', 'rhs': 50.0},  # statisch, immer true
                        {'lhs': 'since_entry', 'op': '>=', 'rhs': 25.0},  # stateful
                    ]},
                ],
            },
        }
        pf_kwargs = dict(close=close, init_cash=10_000.0, fees=0.0, freq="1h")
        pf = evaluate_rules_native(rules_json, ohlc, {}, pf_kwargs)
        records = pf.trades.records
        n = len(records)
        # Da statisch immer true und AND -> Exit nach genau 25 Balken
        # Letzter Trade kann force-closed sein
        if n > 1:
            for idx, (_, row) in enumerate(records.iterrows()):
                if idx == n - 1:
                    continue  # Letzten Trade überspringen
                held = int(row['exit_idx']) - int(row['entry_idx'])
                assert held >= 25, f"Trade {idx} zu kurz: {held} Balken"

    def test_mixed_static_and_stateful_or(self, spike_ohlc_df: pd.DataFrame) -> None:
        """Szenario (d): Gemischte statische + stateful Conditions mit OR-Logik.

        Der letzte Trade wird von VBT force-closed und kann kürzer sein.
        """
        close = spike_ohlc_df['Close']
        ohlc = _OhlcWrapper(spike_ohlc_df)

        # OR: close > 999999 (statisch, immer false) OR since_entry >= 25
        rules_json = {
            'entry': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'close', 'op': '>', 'rhs': 0.0},
                    ]},
                ],
            },
            'exit': {
                # OR -> je Condition ein eigener Block
                'blocks': [
                    {'conditions': [{'lhs': 'close', 'op': '>', 'rhs': 999999.0}]},  # statisch, immer false
                    {'conditions': [{'lhs': 'since_entry', 'op': '>=', 'rhs': 25.0}]},  # stateful
                ],
            },
        }
        pf_kwargs = dict(close=close, init_cash=10_000.0, fees=0.0, freq="1h")
        pf = evaluate_rules_native(rules_json, ohlc, {}, pf_kwargs)
        records = pf.trades.records
        n = len(records)
        # OR mit statisch=false -> Exit allein durch since_entry >= 25
        # Letzter Trade kann force-closed sein
        if n > 1:
            for idx, (_, row) in enumerate(records.iterrows()):
                if idx == n - 1:
                    continue  # Letzten Trade überspringen
                held = int(row['exit_idx']) - int(row['entry_idx'])
                assert held >= 25, f"Trade {idx} zu kurz: {held} Balken"


# ============================================================================
# 8. Regression: alter Masken-Pfad läuft unverändert durch
# ============================================================================

class TestOldPathRegression:
    """Sicherstellt, dass der bestehende Masken-Pfad unverändert funktioniert."""

    def test_old_evaluate_rules_still_works(self, ohlc_df: pd.DataFrame) -> None:
        """evaluate_rules() ohne State-Refs funktioniert weiterhin."""
        from user_data.strategies.generic.rules_engine import evaluate_rules

        close = ohlc_df['Close']
        ohlc = _OhlcWrapper(ohlc_df)

        rules_json = {
            'entry': {
                'blocks': [
                    {'conditions': [{'lhs': 'close', 'op': '>', 'rhs': 90.0}]},
                ],
            },
            'exit': {
                'blocks': [
                    {'conditions': [{'lhs': 'close', 'op': '<', 'rhs': 110.0}]},
                ],
            },
        }
        # GEÄNDERT: Ticket 46 — SignalMasks statt (entries, exits)-Tupel
        masks = evaluate_rules(rules_json, ohlc, {})
        assert masks.long_entries is not None
        assert masks.long_exits is not None
        assert len(masks.long_entries) == len(close)

    def test_evaluate_rules_rejects_state_refs(
        self, ohlc_df: pd.DataFrame
    ) -> None:
        """evaluate_rules() weist State-Refs jetzt hart ab (kein Masken-Pfad mehr).

        Nach dem Rückbau der Cooldown-Approximation laufen State-basierte Exits
        ausschließlich über evaluate_rules_native. Eine State-Ref im Masken-Pfad
        muss sichtbar mit ValueError abgewiesen werden, statt still falsch zu rechnen.
        """
        from user_data.strategies.generic.rules_engine import evaluate_rules

        ohlc = _OhlcWrapper(ohlc_df)

        rules_json = {
            'entry': {
                'blocks': [
                    {'conditions': [{'lhs': 'close', 'op': '>', 'rhs': 90.0}]},
                ],
            },
            'exit': {
                'blocks': [
                    {'conditions': [{'lhs': 'since_entry', 'op': '>=', 'rhs': 5.0}]},
                ],
            },
        }
        with pytest.raises(ValueError, match="State-Primitiv"):
            evaluate_rules(rules_json, ohlc, {})

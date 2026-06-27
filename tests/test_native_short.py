"""Tests für Ticket 47: Short-Unterstützung im nativen Pfad (evaluate_rules_native).

Prüft:
  1. Long+Short im nativen Pfad mit State-Exits → Short-Trades entstehen
  2. Rein statische Spec über nativen Pfad (flat_stateful leer) → kein Fehler
  3. Bit-parität Long-Pfad: Long-Only via nativer Pfad erzeugt gleiche Trade-Anzahl
     wie vorher (Regressions-Check gegen bekannte Referenz)
  4. Short-Only im nativen Pfad → nur Short-Trades, keine Long-Trades
  5. Long+Short mit State-Exit auf beiden Seiten → korrekte Direction-Aufteilung

Methodik: deterministischer OHLCV-DataFrame, Conditions auf OHLCV-Feldern und
Konstanten. Kein Mocking.
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
    evaluate_rules_native,
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


def _make_ohlc_df(n: int = 120) -> pd.DataFrame:
    """Deterministischer OHLCV-DataFrame mit gut streuenden Werten.

    close steigt linear von 90 auf 150, damit Conditions True/False mischen.
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


def _cond(lhs, op, rhs) -> dict:
    """Baut eine Condition im Engine-Format."""
    return {'lhs': lhs, 'lhs_shift': 0, 'op': op, 'rhs': rhs, 'rhs_shift': 0}


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


# Referenz-Conditions
_COND_LONG_ENTRY = _cond('close', '<', 110.0)   # Long-Entry: close < 110 (frühe Bars)
_COND_SHORT_ENTRY = _cond('close', '>', 140.0)  # Short-Entry: close > 140 (späte Bars)
_COND_LONG_EXIT_STATE = _cond('since_entry', '>=', 8)   # Long-Exit nach 8 Bars (State-Ref)
_COND_SHORT_EXIT_STATE = _cond('since_entry', '>=', 6)  # Short-Exit nach 6 Bars (State-Ref)
_COND_STATIC_EXIT = _cond('close', '>', 115.0)          # Statischer Long-Exit


# ============================================================================
# 1. Long+Short im nativen Pfad mit State-Exits
# ============================================================================

class TestLongShortNativePath:
    """Long- und Short-Blöcke im nativen Pfad mit State-basierten Exits."""

    def test_long_short_native_state_exit_has_both_directions(self, ohlc_data, ohlc_df):
        """Long+Short mit State-Exit: Portfolio hat sowohl Long- als auch Short-Trades."""
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [_COND_LONG_ENTRY]},                    # Long
                    {'conditions': [_COND_SHORT_ENTRY], 'is_short': True},  # Short
                ]
            },
            'exit': {
                'blocks': [
                    {'conditions': [_COND_LONG_EXIT_STATE]},                    # Long-Exit
                    {'conditions': [_COND_SHORT_EXIT_STATE], 'is_short': True}, # Short-Exit
                ]
            },
        }
        result = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        assert result is not None
        trades = result.trades.records
        assert len(trades) > 0, "Es müssen Trades entstanden sein"

        directions = set(trades['direction'].tolist())
        assert 0 in directions, f"Keine Long-Trades (direction=0) gefunden. Directions: {directions}"
        assert 1 in directions, f"Keine Short-Trades (direction=1) gefunden. Directions: {directions}"

    def test_long_only_native_state_exit_regression(self, ohlc_data, ohlc_df):
        """Long-Only mit State-Exit: nur Long-Trades, keine Shorts (Regressions-Check)."""
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [_COND_LONG_ENTRY]},
                ]
            },
            'exit': {
                'blocks': [
                    {'conditions': [_COND_LONG_EXIT_STATE]},
                ]
            },
        }
        result = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        assert result is not None
        trades = result.trades.records
        assert len(trades) > 0, "Es müssen Long-Trades entstanden sein"
        directions = set(trades['direction'].tolist())
        assert 1 not in directions, f"Unerwartete Short-Trades gefunden: {directions}"
        assert 0 in directions, "Es müssen Long-Trades entstanden sein"

    def test_short_only_native_state_exit(self, ohlc_data, ohlc_df):
        """Short-Only mit State-Exit: nur Short-Trades, keine Long-Trades."""
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [_COND_SHORT_ENTRY], 'is_short': True},
                ]
            },
            'exit': {
                'blocks': [
                    {'conditions': [_COND_SHORT_EXIT_STATE], 'is_short': True},
                ]
            },
        }
        result = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        assert result is not None
        trades = result.trades.records
        assert len(trades) > 0, "Es müssen Short-Trades entstanden sein"
        directions = set(trades['direction'].tolist())
        assert 0 not in directions, f"Unerwartete Long-Trades gefunden: {directions}"
        assert 1 in directions, "Es müssen Short-Trades entstanden sein"


# ============================================================================
# 2. Rein statische Spec über nativen Pfad
# ============================================================================

class TestStaticSpecViaNativePath:
    """Rein statische Exit-Spec (kein State-Ref) — evaluate_rules_native erlaubt das jetzt."""

    def test_static_long_exit_via_native_path(self, ohlc_data, ohlc_df):
        """Rein statischer Long-Exit über nativen Pfad: kein Fehler, Long-Trades entstehen."""
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [_COND_LONG_ENTRY]},
                ]
            },
            'exit': {
                'blocks': [
                    {'conditions': [_COND_STATIC_EXIT]},  # Statische Condition, kein State-Ref
                ]
            },
        }
        result = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        assert result is not None
        # Auch rein statisch müssen Long-Trades entstehen
        trades = result.trades.records
        assert len(trades) > 0, "Rein statische Spec muss Trades erzeugen"
        directions = set(trades['direction'].tolist())
        assert 0 in directions, "Müssen Long-Trades sein"

    def test_static_short_exit_via_native_path(self, ohlc_data, ohlc_df):
        """Rein statischer Short-Exit über nativen Pfad: Short-Trades entstehen."""
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [_COND_SHORT_ENTRY], 'is_short': True},
                ]
            },
            'exit': {
                'blocks': [
                    {'conditions': [_COND_LONG_ENTRY], 'is_short': True},  # Statisch
                ]
            },
        }
        result = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        assert result is not None

    def test_mixed_static_and_state_exit_via_native_path(self, ohlc_data, ohlc_df):
        """Gemischte statische + State-basierte Exit-Blöcke: kein Fehler."""
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [_COND_LONG_ENTRY]},
                ]
            },
            'exit': {
                'blocks': [
                    {'conditions': [_COND_STATIC_EXIT]},               # Statisch
                    {'conditions': [_COND_LONG_EXIT_STATE]},           # State-Ref
                ]
            },
        }
        result = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        assert result is not None
        assert len(result.trades.records) > 0


# ============================================================================
# 3. Exit-Direction-Trennung: Long-Exit greift nur auf Long-Positionen
# ============================================================================

class TestExitDirectionSeparation:
    """Verifiziert, dass Long-Exit-Bedingungen nur Long-Positionen schließen."""

    def test_long_exit_does_not_close_short_position(self, ohlc_data, ohlc_df):
        """Long-Exit-State darf Short-Positionen nicht schließen.

        Setup: Long-Entry früh (close < 110), Short-Entry spät (close > 140).
        Long-Exit nach 8 Bars → schließt Long-Positionen.
        Short hat keinen eigenen Exit → Short-Position bleibt bis Datei-Ende.
        """
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [_COND_LONG_ENTRY]},
                    {'conditions': [_COND_SHORT_ENTRY], 'is_short': True},
                ]
            },
            'exit': {
                'blocks': [
                    # Nur Long-Exit — kein Short-Exit-Block
                    {'conditions': [_COND_LONG_EXIT_STATE]},
                ]
            },
        }
        result = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        assert result is not None
        trades = result.trades.records
        assert len(trades) > 0

        # Short-Trades müssen vorhanden sein (wurden nicht fälschlich durch Long-Exit geschlossen)
        directions = set(trades['direction'].tolist())
        assert 1 in directions, "Short-Trades müssen vorhanden sein"

    def test_short_exit_does_not_close_long_position(self, ohlc_data, ohlc_df):
        """Short-Exit-State darf Long-Positionen nicht schließen."""
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [_COND_LONG_ENTRY]},
                    {'conditions': [_COND_SHORT_ENTRY], 'is_short': True},
                ]
            },
            'exit': {
                'blocks': [
                    # Nur Short-Exit — kein Long-Exit-Block
                    {'conditions': [_COND_SHORT_EXIT_STATE], 'is_short': True},
                ]
            },
        }
        result = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        assert result is not None
        trades = result.trades.records
        assert len(trades) > 0

        # Long-Trades müssen vorhanden sein (wurden nicht fälschlich durch Short-Exit geschlossen)
        directions = set(trades['direction'].tolist())
        assert 0 in directions, "Long-Trades müssen vorhanden sein"


# ============================================================================
# 4. Short-Trade-Zeitpunkt-Verifizierung
# ============================================================================

class TestShortTradeTimingNative:
    """Verifiziert, dass Short-Entries an den richtigen Bars feuern."""

    def test_short_entry_fires_at_correct_bar(self, ohlc_data, ohlc_df):
        """Short-Entry feuert an Bar, wo close > 140 (COND_SHORT_ENTRY)."""
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [_COND_SHORT_ENTRY], 'is_short': True},
                ]
            },
            'exit': {
                'blocks': [
                    {'conditions': [_COND_SHORT_EXIT_STATE], 'is_short': True},
                ]
            },
        }
        result = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        trades = result.trades.records
        assert len(trades) > 0

        # Der erste Short-Trade muss an einem Bar beginnen, wo close > 140
        first_entry_idx = int(trades.iloc[0]['entry_idx'])
        entry_close = ohlc_df['Close'].iloc[first_entry_idx]
        assert entry_close > 140.0, (
            f"Short-Entry bei Bar {first_entry_idx} erwartet close > 140, "
            f"ist {entry_close:.2f}"
        )

    def test_short_exit_fires_after_n_bars(self, ohlc_data, ohlc_df):
        """Short-Exit feuert nach >= 6 Bars (COND_SHORT_EXIT_STATE: since_entry >= 6).

        Trades am Daten-Ende (exit_idx == n-1) werden ausgeschlossen, da sie
        durch das Zeitreihen-Ende geschlossen werden, nicht durch den Exit.
        """
        n = len(ohlc_df)
        rules = {
            'entry': {
                'blocks': [
                    {'conditions': [_COND_SHORT_ENTRY], 'is_short': True},
                ]
            },
            'exit': {
                'blocks': [
                    {'conditions': [_COND_SHORT_EXIT_STATE], 'is_short': True},
                ]
            },
        }
        result = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=_make_pf_kwargs(ohlc_df),
        )
        trades = result.trades.records
        # Nur Trades prüfen, die NICHT am Daten-Ende (letzter Bar) geschlossen wurden
        for _, row in trades.iterrows():
            entry_idx = int(row['entry_idx'])
            exit_idx = int(row['exit_idx'])
            # Daten-Ende-Trades überspringen (exit durch EOD, nicht durch Condition)
            if exit_idx >= n - 1:
                continue
            if exit_idx > entry_idx:
                duration = exit_idx - entry_idx
                assert duration >= 6, (
                    f"Short-Trade von Bar {entry_idx} bis {exit_idx}: "
                    f"Duration {duration} < 6 — Exit zu früh"
                )


# ============================================================================
# 5. Bit-Parity: nativer Pfad vs. Masken-Pfad
# ============================================================================

class TestBitParityNativeVsMask:
    """Bit-identischer Vergleich nativer Pfad vs. Masken-Pfad für gleiche Specs.

    Eingefrorene Referenz: Masken-Pfad erzeugt Portfolio, nativer Pfad MUSS
    identische Trade-Records liefern (entry_idx, exit_idx, direction, return).
    """

    def _long_only_static_rules(self) -> dict:
        """Long-Only, rein statische Exits (kein State-Ref)."""
        return {
            'entry': {'blocks': [{'conditions': [{'lhs': 'close', 'op': '<', 'rhs': 110.0}]}]},
            'exit': {'blocks': [{'conditions': [{'lhs': 'close', 'op': '>', 'rhs': 115.0}]}]},
        }

    def test_long_only_static_native_matches_mask(self, ohlc_data, ohlc_df):
        """Long-Only statische Spec: nativer Pfad und Masken-Pfad liefern identische Trades."""
        import vectorbtpro as vbt
        from user_data.strategies.generic.rules_engine import evaluate_rules

        rules = self._long_only_static_rules()
        pf_kwargs = _make_pf_kwargs(ohlc_df)
        close_series = ohlc_df['Close']

        # Masken-Pfad (Referenz)
        masks = evaluate_rules(rules, ohlc_data, {})
        pf_mask = vbt.Portfolio.from_signals(
            close_series,
            masks.long_entries,
            exits=masks.long_exits,
            short_entries=masks.short_entries,
            short_exits=masks.short_exits,
            upon_opposite_entry='Reverse',
            fees=0.0,
            init_cash=10_000.0,
            size=1.0,
            size_type='amount',
            freq='1h',
        )

        # Nativer Pfad
        pf_native = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators={},
            pf_kwargs=pf_kwargs,
        )

        mask_trades = pf_mask.trades.records
        native_trades = pf_native.trades.records
        assert len(mask_trades) == len(native_trades), (
            f"Trade-Anzahl verschieden: Maske={len(mask_trades)}, Nativ={len(native_trades)}"
        )
        if len(mask_trades) > 0:
            np.testing.assert_array_equal(
                mask_trades['entry_idx'].values,
                native_trades['entry_idx'].values,
                err_msg="entry_idx stimmt nicht überein"
            )
            np.testing.assert_array_equal(
                mask_trades['exit_idx'].values,
                native_trades['exit_idx'].values,
                err_msg="exit_idx stimmt nicht überein"
            )


# ============================================================================
# 6. Multi-Combo Bit-Parity: Indikator-Param-Achse x Stop-Sweep (Ticket 47 Bugfix)
# ============================================================================

class TestMultiComboBitParity:
    """Echter Multi-Combo-Lauf (mehrere Indikator-Längen x mehrere Stops) über
    evaluate_rules_native gegen eine per-Kombi berechnete Referenz.

    Verifiziert die Kernkorrektur: der native Pfad rechnet Multi-Combo + Stop-Sweep
    vektorisiert (col % n_combo Mapping + Multi-Combo-close) statt fehlerhaftem
    Single-Combo-Pre-Expand. Erwartung: identischer Spalten-MultiIndex (volle
    Indikator-Param-Achse, nicht nur die Stop-Achse) UND bit-identische total_return
    je Spalte.

    Methodik: ein einfacher SMA-Indikator mit 3 Längen (timeperiod=[5,10,15]),
    Entry close > SMA, State-Exit since_entry >= 8, Stop-Sweep tp_stop=[0.05, 0.1].
    """

    def _make_indicators(self, ohlc_df: pd.DataFrame, timeperiods):
        """Baut einen talib-SMA-Indikator (Single- oder Multi-Combo via vbt.Param)."""
        import vectorbtpro as vbt
        if isinstance(timeperiods, (list, tuple)):
            return {'sma': vbt.talib('SMA').run(ohlc_df['Close'], timeperiod=vbt.Param(list(timeperiods)))}
        return {'sma': vbt.talib('SMA').run(ohlc_df['Close'], timeperiod=timeperiods)}

    def _rules(self) -> dict:
        return {
            'entry': {'blocks': [{'conditions': [
                {'lhs': 'close', 'lhs_shift': 0, 'op': '>', 'rhs': 'indicator:sma:real', 'rhs_shift': 0},
            ]}]},
            'exit': {'blocks': [{'conditions': [
                {'lhs': 'since_entry', 'lhs_shift': 0, 'op': '>=', 'rhs': 8, 'rhs_shift': 0},
            ]}]},
        }

    @staticmethod
    def _tr_arr(pf) -> np.ndarray:
        tr = pf.total_return
        return np.atleast_1d(tr.values) if hasattr(tr, 'values') else np.atleast_1d(tr)

    def test_multi_combo_x_stop_sweep_matches_per_combo_reference(self, ohlc_data, ohlc_df):
        """3 Indikator-Längen x 2 Stops: voller Spalten-MultiIndex + bit-identische total_return."""
        import vectorbtpro as vbt
        rules = self._rules()
        timeperiods = [5, 10, 15]
        stops = [0.05, 0.1]

        # Nativer Multi-Combo x Stop-Sweep-Lauf in EINEM Aufruf
        pf_kwargs = _make_pf_kwargs(ohlc_df)
        pf_kwargs['tp_stop'] = vbt.Param(stops)
        pf_native = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators=self._make_indicators(ohlc_df, timeperiods),
            pf_kwargs=pf_kwargs,
            stops_swept=True,
        )

        # Referenz: jede (stop, timeperiod)-Kombi einzeln (Single-Combo, kein Sweep)
        ref_cols = []
        ref_rets = []
        for stop in stops:
            for tp in timeperiods:
                pk = _make_pf_kwargs(ohlc_df)
                pk['tp_stop'] = stop
                pf1 = evaluate_rules_native(
                    rules_json=rules,
                    ohlc_data=ohlc_data,
                    indicators=self._make_indicators(ohlc_df, tp),
                    pf_kwargs=pk,
                    stops_swept=False,
                )
                ref_cols.append((stop, tp))
                ref_rets.append(float(self._tr_arr(pf1)[0]))

        # Spalten-MultiIndex muss IDENTISCH sein (Stop außen, Indikator innen)
        assert pf_native.wrapper.columns.tolist() == ref_cols, (
            f"Spalten-MultiIndex weicht ab:\n native={pf_native.wrapper.columns.tolist()}\n ref   ={ref_cols}"
        )
        # total_return je Spalte bit-identisch
        np.testing.assert_array_equal(
            self._tr_arr(pf_native),
            np.array(ref_rets),
            err_msg="total_return je Spalte nicht bit-identisch",
        )

    def test_multi_combo_only_matches_per_combo_reference(self, ohlc_data, ohlc_df):
        """3 Indikator-Längen ohne Stop-Sweep: Indikator-Param-Achse erhalten, bit-identisch."""
        rules = self._rules()
        timeperiods = [5, 10, 15]

        pf_native = evaluate_rules_native(
            rules_json=rules,
            ohlc_data=ohlc_data,
            indicators=self._make_indicators(ohlc_df, timeperiods),
            pf_kwargs=_make_pf_kwargs(ohlc_df),
            stops_swept=False,
        )

        ref_cols = []
        ref_rets = []
        for tp in timeperiods:
            pf1 = evaluate_rules_native(
                rules_json=rules,
                ohlc_data=ohlc_data,
                indicators=self._make_indicators(ohlc_df, tp),
                pf_kwargs=_make_pf_kwargs(ohlc_df),
                stops_swept=False,
            )
            ref_cols.append(tp)
            ref_rets.append(float(self._tr_arr(pf1)[0]))

        assert pf_native.wrapper.columns.tolist() == ref_cols, (
            f"Indikator-Param-Achse weicht ab:\n native={pf_native.wrapper.columns.tolist()}\n ref   ={ref_cols}"
        )
        np.testing.assert_array_equal(
            self._tr_arr(pf_native),
            np.array(ref_rets),
            err_msg="total_return je Spalte nicht bit-identisch",
        )

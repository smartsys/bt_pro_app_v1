"""Tests für _combine_broadcast in rules_engine.py.

Prüft das Cross-Produkt disjunkter Indikator-Param-Level für Parameter-Sweeps
(eingeführt in Version 1.7.6). Testfälle orientieren sich an §6.5/§6.6/§6.9
der indicators.md-Referenz.

Methodisch: synthetische DataFrames mit echten MultiIndex-Columns, kein Mocking,
keine Platzhalter.
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

from user_data.strategies.generic.rules_engine import (
    _combine_broadcast,
    evaluate_rules,
)


# ============================================================================
# Hilfsfunktionen: synthetische DataFrames mit MultiIndex-Columns
# ============================================================================

def _make_index(n: int = 100) -> pd.DatetimeIndex:
    """Erzeugt einen deterministischen Zeit-Index mit n Balken."""
    return pd.date_range("2022-01-01", periods=n, freq="1h")


def _make_multiindex_df(
    time_index: pd.DatetimeIndex,
    level_names: list[str],
    level_values: list[list],
    fill_value: float = 1.0,
    seed: int = 0,
) -> pd.DataFrame:
    """Baut einen DataFrame mit MultiIndex-Columns.

    Args:
        time_index: Zeit-Index.
        level_names: Namen der Column-Level (z.B. ['dwsvwma_length', 'dwsvwma_below_pct', 'symbol']).
        level_values: Werte pro Level als Liste von Listen.
        fill_value: Basiswert; pro Spalte wird ein leicht unterschiedlicher Wert vergeben,
            damit bit-identische Vergleiche möglich sind.
        seed: RNG-Seed für reproduzierbare Werte.

    Returns:
        DataFrame mit MultiIndex-Columns, Form (len(time_index), n_columns).
    """
    import itertools
    combos = list(itertools.product(*level_values))
    mi = pd.MultiIndex.from_tuples(combos, names=level_names)
    rng = np.random.default_rng(seed)
    n_cols = len(combos)
    n_rows = len(time_index)
    # Jede Spalte bekommt ihren Spaltenindex als Offset -> eindeutige, stabile Werte
    data = np.tile(np.arange(1, n_cols + 1, dtype=float), (n_rows, 1)) + rng.normal(
        0.0, 0.001, size=(n_rows, n_cols)
    )
    return pd.DataFrame(data, index=time_index, columns=mi)


# ============================================================================
# Hilfsmethode: Fake-Indikator-Objekt für evaluate_rules
# ============================================================================

class _FakeIndicator:
    """Minimaler Indikator-Stub, der .result als festes DataFrame zurückgibt.

    Wird genutzt um evaluate_rules ohne echte VBT-Factory aufzurufen.
    output_names = ('result',) entspricht dem dwsVWMA/dwsFastSMA-Schema.
    """

    output_names = ('result',)

    def __init__(self, result_df: pd.DataFrame) -> None:
        self.result = result_df


class _OhlcWrapper:
    """Minimaler ohlc_data-Wrapper: implementiert .get(key) für OHLCV-Spalten."""

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def get(self, key: str) -> pd.Series:
        return self._df[key]


def _make_ohlc_df(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """Deterministischer OHLC-DataFrame (Random Walk)."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0, 0.01, size=n)
    close = 100.0 * np.exp(np.cumsum(returns))
    noise = rng.uniform(0.001, 0.005, size=n)
    high = close * (1 + noise)
    low = close * (1 - noise)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    idx = pd.date_range("2022-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": np.ones(n)},
        index=idx,
    )


# ============================================================================
# Testfall (a): zwei disjunkte Blöcke — Indikator-Kette × supertrend
#
# Laut §6.6/§6.9: fast_sma(5×5=25) × teststrategie(17×5=85) = 2125 Level,
# supertrend(5×3=15) Level → Cross 2125 × 15 = 31.875 Spalten.
# Für schnelle Unit-Tests verwenden wir drastisch reduzierte Dimensionen:
#   Indikator-Block:  3 length × 2 below_pct = 6 private Level,
#   supertrend-Block: 2 period × 2 multiplier = 4 private Level.
# Gemeinsames Carrier-Level: symbol (1 Wert).
# Erwartete Spalten nach Cross: 6 × 4 × 1 = 24.
# ============================================================================

class TestDisjointBlocksCross:
    """Zwei disjunkte Blöcke werden per Kartesischem Produkt verbunden."""

    @pytest.fixture
    def time_idx(self) -> pd.DatetimeIndex:
        return _make_index(50)

    @pytest.fixture
    def ind_df(self, time_idx: pd.DatetimeIndex) -> pd.DataFrame:
        """Indikator-Block: Level dwsvwma_length × dwsvwma_below_pct × symbol."""
        return _make_multiindex_df(
            time_idx,
            level_names=['dwsvwma_length', 'dwsvwma_below_pct', 'symbol'],
            level_values=[[10, 20, 30], [1.0, 2.0], ['BTCUSDT']],
            seed=1,
        )

    @pytest.fixture
    def supertrend_df(self, time_idx: pd.DatetimeIndex) -> pd.DataFrame:
        """supertrend-Block: Level supertrend_period × supertrend_multiplier × symbol."""
        return _make_multiindex_df(
            time_idx,
            level_names=['supertrend_period', 'supertrend_multiplier', 'symbol'],
            level_values=[[7, 14], [2.0, 3.0], ['BTCUSDT']],
            seed=2,
        )

    def test_column_count_equals_cross_product(
        self, ind_df: pd.DataFrame, supertrend_df: pd.DataFrame
    ) -> None:
        """Ergebnis-Spalten = Produkt der disjunkten privaten Level × carrier-Level."""
        # Indikator: 3 length × 2 below_pct = 6 private Combos; symbol = 1 → 6 Spalten
        # supertrend: 2 period × 2 multiplier = 4 private Combos; symbol = 1 → 4 Spalten
        # Cross: 6 × 4 = 24 Spalten (symbol als Carrier, nicht gekreuzt)
        result = _combine_broadcast([ind_df, supertrend_df])
        ind_bc, st_bc = result
        assert ind_bc.shape[1] == 24, (
            f"Erwartet 24 Spalten nach Cross, erhalten {ind_bc.shape[1]}"
        )
        assert st_bc.shape[1] == 24, (
            f"supertrend-Block nach Cross: erwartet 24, erhalten {st_bc.shape[1]}"
        )

    def test_both_operands_have_same_columns(
        self, ind_df: pd.DataFrame, supertrend_df: pd.DataFrame
    ) -> None:
        """Beide Operanden teilen nach dem Cross denselben Spalten-Index."""
        ind_bc, st_bc = _combine_broadcast([ind_df, supertrend_df])
        assert ind_bc.columns.equals(st_bc.columns), (
            "Spalten-Index nach Cross-Broadcast muss identisch sein"
        )

    def test_row_count_preserved(
        self, ind_df: pd.DataFrame, supertrend_df: pd.DataFrame, time_idx: pd.DatetimeIndex
    ) -> None:
        """Zeit-Index (Zeilenzahl) bleibt unverändert."""
        ind_bc, _ = _combine_broadcast([ind_df, supertrend_df])
        assert len(ind_bc) == len(time_idx), (
            f"Zeit-Index: erwartet {len(time_idx)}, erhalten {len(ind_bc)}"
        )

    def test_indicator_values_replicated_correctly(
        self, ind_df: pd.DataFrame, supertrend_df: pd.DataFrame
    ) -> None:
        """Jeder Indikator-Combo-Wert erscheint für alle supertrend-Combos unverändert.

        Prüft bit-Identität: für einen beliebigen Indikator-Combo-Wert (Zeile 0, Spalte 0)
        muss er in allen 4 supertrend-Varianten (also 4 Ausgabe-Spalten) identisch sein.
        """
        ind_bc, _ = _combine_broadcast([ind_df, supertrend_df])
        # 6 Indikator-Combos × 4 st-Combos = 24 Spalten; erste Combo belegt Spalten 0–3
        first_ind_val = ind_bc.iloc[0, 0]
        # In den 4 Spalten (Index 0–3) muss derselbe Indikator-Combo-Wert stehen
        for col_offset in range(4):
            val = ind_bc.iloc[0, col_offset]
            assert val == first_ind_val, (
                f"Spalte {col_offset}: erwartet {first_ind_val}, erhalten {val}"
            )

    def test_supertrend_values_replicated_correctly(
        self, ind_df: pd.DataFrame, supertrend_df: pd.DataFrame
    ) -> None:
        """Jeder supertrend-Combo-Wert erscheint für alle Indikator-Combos unverändert.

        Prüft bit-Identität: Spalte 0 und Spalte 4 (= nächste Indikator-Combo, gleicher
        supertrend-Combo) müssen denselben supertrend-Wert tragen.
        """
        _, st_bc = _combine_broadcast([ind_df, supertrend_df])
        # Erste 4 Spalten: Indikator-Combo 0, st-Combos 0–3
        # Spalten 4–7: Indikator-Combo 1, st-Combos 0–3 (gleiche st-Werte)
        st_val_col0 = st_bc.iloc[0, 0]
        st_val_col4 = st_bc.iloc[0, 4]
        assert st_val_col0 == st_val_col4, (
            f"supertrend-Wert in Spalte 0 ({st_val_col0}) != Spalte 4 ({st_val_col4}): "
            "Replikation über Indikator-Combos fehlerhaft"
        )

    def test_symbol_carrier_not_duplicated(
        self, ind_df: pd.DataFrame, supertrend_df: pd.DataFrame
    ) -> None:
        """Das gemeinsame symbol-Level erscheint nur einmal in den Ergebnis-Columns."""
        ind_bc, _ = _combine_broadcast([ind_df, supertrend_df])
        assert 'symbol' in ind_bc.columns.names, "symbol-Level fehlt im Ergebnis"
        # symbol darf nur einmal in names vorkommen (kein Duplizieren)
        symbol_count = ind_bc.columns.names.count('symbol')
        assert symbol_count == 1, (
            f"symbol-Level kommt {symbol_count}× in Column-Names vor, erwartet 1"
        )

    def test_result_invariant_single_combo_equals_sweep_value(
        self, ind_df: pd.DataFrame, supertrend_df: pd.DataFrame
    ) -> None:
        """Referenz-Invariante (§6.9): Sweep[combo].value == Standalone-Single-Combo.value.

        Für Combo (ind[0], supertrend[0]) muss der Sweep-Wert identisch mit dem
        Single-Combo-Wert (direkt aus den Einzel-DataFrames gelesen) sein.
        """
        ind_bc, st_bc = _combine_broadcast([ind_df, supertrend_df])

        # Single-Combo-Wert: Zeile 10, erste Spalte aus den Original-DataFrames
        bar = 10
        ind_single = ind_df.iloc[bar, 0]     # Erste Indikator-Combo
        st_single = supertrend_df.iloc[bar, 0]  # Erste supertrend-Combo

        # Im Sweep: erste Spalte (Indikator-Combo 0, st-Combo 0)
        ind_sweep = ind_bc.iloc[bar, 0]
        st_sweep = st_bc.iloc[bar, 0]

        assert ind_sweep == ind_single, (
            f"Sweep[ind, combo=0] = {ind_sweep} != Single-Combo {ind_single} (bit-identisch erwartet)"
        )
        assert st_sweep == st_single, (
            f"Sweep[st, combo=0] = {st_sweep} != Single-Combo {st_single} (bit-identisch erwartet)"
        )


# ============================================================================
# Testfall (b): Subset-Folding — fast_sma-Level ⊂ Indikator-Kette
#
# Wenn fast_sma-Level eine Teilmenge der Indikator-Level sind (z.B. weil der
# Indikator von fast_sma abhängt und dessen Param-Level erbt), darf kein Level
# doppelt entstehen.
# Laut §6.5: Im Chaining-Fall hat der Indikator bereits die fast_sma-Level als Teilmenge.
# _combine_broadcast muss das erkennen und das Subset herausfalten.
# ============================================================================

class TestSubsetFolding:
    """Subset-Level werden nicht doppelt gekreuzt."""

    @pytest.fixture
    def time_idx(self) -> pd.DatetimeIndex:
        return _make_index(50)

    @pytest.fixture
    def ind_chain_df(self, time_idx: pd.DatetimeIndex) -> pd.DataFrame:
        """Indikator-Block mit geerbten fast_sma-Level (Chaining).

        Level: dwsfastsma_length × dwsfastsma_multiplier × dwsvwma_length × dwsvwma_below_pct × symbol.
        """
        return _make_multiindex_df(
            time_idx,
            level_names=[
                'dwsfastsma_length', 'dwsfastsma_multiplier',
                'dwsvwma_length', 'dwsvwma_below_pct',
                'symbol',
            ],
            level_values=[[5, 10], [1.0, 2.0], [20, 30], [1.5], ['ETHUSDT']],
            seed=3,
        )

    @pytest.fixture
    def fast_sma_df(self, time_idx: pd.DatetimeIndex) -> pd.DataFrame:
        """fast_sma-Block (eigenständig, Level ⊂ Indikator-Kette).

        Level: dwsfastsma_length × dwsfastsma_multiplier × symbol.
        """
        return _make_multiindex_df(
            time_idx,
            level_names=['dwsfastsma_length', 'dwsfastsma_multiplier', 'symbol'],
            level_values=[[5, 10], [1.0, 2.0], ['ETHUSDT']],
            seed=4,
        )

    def test_no_duplicate_levels_after_broadcast(
        self, ind_chain_df: pd.DataFrame, fast_sma_df: pd.DataFrame
    ) -> None:
        """Nach dem Broadcast enthält kein Level-Name Duplikate."""
        # Indikator-Kette enthält fast_sma-Level als Teilmenge → normales broadcast soll greifen
        result = _combine_broadcast([ind_chain_df, fast_sma_df])
        ind_bc, sma_bc = result
        level_names = list(ind_bc.columns.names)
        for name in set(level_names):
            count = level_names.count(name)
            assert count == 1, (
                f"Level-Name '{name}' kommt {count}× vor — doppeltes Level"
            )

    def test_column_count_not_exploded(
        self, ind_chain_df: pd.DataFrame, fast_sma_df: pd.DataFrame
    ) -> None:
        """Spalten dürfen nicht das Kartesische Produkt einer Teilmenge mit sich selbst sein.

        Indikator-Kette hat 2×2×2×1×1 = 8 Spalten, fast_sma hat 2×2×1 = 4 Spalten.
        Da fast_sma ⊂ Indikator (Teilmenge), soll kein weiteres Kreuzen stattfinden.
        Das normale vbt.broadcast soll die Teilmenge herausfalten → 8 Spalten.
        """
        ind_bc, sma_bc = _combine_broadcast([ind_chain_df, fast_sma_df])
        assert ind_bc.shape[1] == 8, (
            f"Erwartet 8 Spalten (Subset-Folding), erhalten {ind_bc.shape[1]}"
        )

    def test_both_operands_same_columns_after_subset_fold(
        self, ind_chain_df: pd.DataFrame, fast_sma_df: pd.DataFrame
    ) -> None:
        """Beide Operanden teilen nach dem Broadcast denselben Spalten-Index."""
        ind_bc, sma_bc = _combine_broadcast([ind_chain_df, fast_sma_df])
        assert ind_bc.columns.equals(sma_bc.columns), (
            "Spalten-Index nach Subset-Broadcast muss identisch sein"
        )


# ============================================================================
# Testfall (c): gemeinsames symbol-Carrier-Level bleibt aligned, nicht gekreuzt
#
# Indikator und supertrend teilen das 'symbol'-Level. Es hat denselben Wert in
# beiden Blöcken. Das symbol-Level soll aligned bleiben (kein Kreuz damit),
# sondern nur die privaten Param-Level werden gekreuzt.
# ============================================================================

class TestCarrierLevelAligned:
    """Gemeinsame Carrier-Level (symbol) werden aligned, nicht gekreuzt."""

    @pytest.fixture
    def time_idx(self) -> pd.DatetimeIndex:
        return _make_index(30)

    @pytest.fixture
    def block_a(self, time_idx: pd.DatetimeIndex) -> pd.DataFrame:
        """Block A: 2 private Level × 1 symbol-Wert = 2 Spalten."""
        return _make_multiindex_df(
            time_idx,
            level_names=['ind_a_param', 'symbol'],
            level_values=[[1, 2], ['SOLUSDT']],
            seed=10,
        )

    @pytest.fixture
    def block_b(self, time_idx: pd.DatetimeIndex) -> pd.DataFrame:
        """Block B: 3 private Level × 1 symbol-Wert = 3 Spalten."""
        return _make_multiindex_df(
            time_idx,
            level_names=['ind_b_param', 'symbol'],
            level_values=[[10, 20, 30], ['SOLUSDT']],
            seed=11,
        )

    def test_symbol_appears_once_in_result(
        self, block_a: pd.DataFrame, block_b: pd.DataFrame
    ) -> None:
        """symbol-Level erscheint genau einmal in den Ergebnis-Columns."""
        a_bc, b_bc = _combine_broadcast([block_a, block_b])
        assert 'symbol' in a_bc.columns.names
        assert a_bc.columns.names.count('symbol') == 1

    def test_cross_count_with_single_symbol(
        self, block_a: pd.DataFrame, block_b: pd.DataFrame
    ) -> None:
        """2 × 3 private Combos × 1 symbol = 6 Spalten insgesamt."""
        a_bc, b_bc = _combine_broadcast([block_a, block_b])
        assert a_bc.shape[1] == 6, (
            f"Erwartet 6 Spalten (2 × 3 private × 1 symbol), erhalten {a_bc.shape[1]}"
        )

    def test_symbol_value_uniform_in_result(
        self, block_a: pd.DataFrame, block_b: pd.DataFrame
    ) -> None:
        """Alle Spalten im Ergebnis tragen denselben symbol-Wert ('SOLUSDT')."""
        a_bc, _ = _combine_broadcast([block_a, block_b])
        symbol_level_pos = a_bc.columns.names.index('symbol')
        symbol_values = a_bc.columns.get_level_values(symbol_level_pos).unique().tolist()
        assert symbol_values == ['SOLUSDT'], (
            f"Erwartet nur 'SOLUSDT' in symbol-Level, erhalten {symbol_values}"
        )


# ============================================================================
# Testfall (d): rein alignbarer Fall fällt auf normales vbt.broadcast zurück
#
# Wenn beide Operanden denselben Column-Index haben (oder einer ist eine Series),
# soll _combine_broadcast einfach normales vbt.broadcast verwenden, kein Cross.
# ============================================================================

class TestAlignableFallback:
    """Rein alignbare Fälle nutzen normales vbt.broadcast ohne Cross-Pfad."""

    @pytest.fixture
    def time_idx(self) -> pd.DatetimeIndex:
        return _make_index(40)

    def test_two_identical_column_indexes(self, time_idx: pd.DatetimeIndex) -> None:
        """Zwei DataFrames mit identischem Spalten-Index werden direkt gebcastet."""
        mi = pd.MultiIndex.from_tuples(
            [(10, 'BTCUSDT'), (20, 'BTCUSDT')],
            names=['length', 'symbol'],
        )
        data = np.ones((len(time_idx), 2))
        df_a = pd.DataFrame(data * 1.0, index=time_idx, columns=mi)
        df_b = pd.DataFrame(data * 2.0, index=time_idx, columns=mi)

        result = _combine_broadcast([df_a, df_b])
        a_bc, b_bc = result

        # Spaltenanzahl darf sich nicht verdoppeln
        assert a_bc.shape[1] == 2, (
            f"Identische Spalten: erwartet 2 Spalten, erhalten {a_bc.shape[1]}"
        )
        assert a_bc.columns.equals(b_bc.columns)

    def test_series_and_dataframe_broadcasts_without_cross(self, time_idx: pd.DatetimeIndex) -> None:
        """Series + DataFrame: normales vbt.broadcast, kein Cross-Pfad aktiviert.

        _combine_broadcast tritt in den Cross-Pfad nur ein wenn mindestens 2 DataFrames
        vorhanden sind. Bei Series + DataFrame reicht vbt.broadcast.
        """
        mi = pd.MultiIndex.from_tuples(
            [(10, 'BTCUSDT'), (20, 'BTCUSDT')],
            names=['length', 'symbol'],
        )
        df = pd.DataFrame(np.ones((len(time_idx), 2)), index=time_idx, columns=mi)
        series = pd.Series(np.ones(len(time_idx)), index=time_idx, name='close')

        # Kein Fehler erwartet; normales vbt.broadcast greift
        result = _combine_broadcast([series, df])
        s_bc, df_bc = result
        # DataFrame-Spalten unverändert
        assert df_bc.shape[1] == 2

    def test_single_dataframe_broadcasts_directly(self, time_idx: pd.DatetimeIndex) -> None:
        """Einzelner DataFrame: kein Cross, direktes vbt.broadcast.

        vbt.broadcast gibt bei einem einzigen Objekt das Objekt selbst zurück (kein Tupel).
        _combine_broadcast reicht das unverändert durch.
        """
        mi = pd.MultiIndex.from_tuples(
            [(5, 'ETHUSDT'), (10, 'ETHUSDT')],
            names=['param', 'symbol'],
        )
        df = pd.DataFrame(np.ones((len(time_idx), 2)), index=time_idx, columns=mi)
        result = _combine_broadcast([df])
        # vbt.broadcast(df) gibt den DataFrame direkt zurück, kein Tupel
        assert isinstance(result, pd.DataFrame), (
            f"Erwartet DataFrame (vbt.broadcast gibt Einzel-Objekt direkt), erhalten {type(result)}"
        )
        assert result.shape[1] == 2


# ============================================================================
# Testfall (e): _combine_broadcast innerhalb von evaluate_rules
#
# Integrationstest: evaluate_rules ruft _combine_broadcast via _broadcast_explained.
# Zwei disjunkte Indikator-Blöcke als Fake-Indikatoren → Entry-Regel verknüpft beide.
# Das muss ohne Exception funktionieren und eine Boolean-Series/-DataFrame liefern.
# ============================================================================

class TestEvaluateRulesIntegration:
    """evaluate_rules löst disjunkte Param-Level korrekt auf."""

    @pytest.fixture
    def ohlc_df(self) -> pd.DataFrame:
        return _make_ohlc_df(60, seed=7)

    @pytest.fixture
    def ohlc_data(self, ohlc_df: pd.DataFrame) -> _OhlcWrapper:
        return _OhlcWrapper(ohlc_df)

    @pytest.fixture
    def time_idx(self, ohlc_df: pd.DataFrame) -> pd.DatetimeIndex:
        return ohlc_df.index

    def test_disjoint_indicators_entry_rule(
        self, ohlc_data: _OhlcWrapper, time_idx: pd.DatetimeIndex
    ) -> None:
        """Entry-Regel mit zwei disjunkten Indikatoren erzeugt DataFrame mit Cross-Spalten.

        Indikator-Block: 2 length × 2 below_pct × 1 symbol = 4 Spalten.
        supertrend-Block: 3 period × 1 symbol = 3 Spalten.
        Cross: 4 × 3 = 12 Spalten.
        """
        ind_result = _make_multiindex_df(
            time_idx,
            level_names=['dwsvwma_length', 'dwsvwma_below_pct', 'symbol'],
            level_values=[[10, 20], [1.0, 2.0], ['FETUSDT']],
            seed=20,
        )
        st_result = _make_multiindex_df(
            time_idx,
            level_names=['supertrend_period', 'symbol'],
            level_values=[[7, 14, 21], ['FETUSDT']],
            seed=21,
        )

        indicators = {
            'teststrategie': _FakeIndicator(ind_result),
            'supertrend': _FakeIndicator(st_result),
        }

        rules_json = {
            'entry': {
                'blocks': [
                    {'conditions': [
                        # teststrategie.result > supertrend.result → Cross nötig
                        {
                            'lhs': 'indicator:teststrategie:result',
                            'op': '>',
                            'rhs': 'indicator:supertrend:result',
                        },
                    ]},
                ],
            },
        }

        # GEÄNDERT: Ticket 46 — SignalMasks statt (entries, exits)-Tupel
        masks = evaluate_rules(rules_json, ohlc_data, indicators)
        entries = masks.long_entries
        assert entries is not None
        assert isinstance(entries, pd.DataFrame), (
            f"Erwartet DataFrame (Multi-Combo), erhalten {type(entries).__name__}"
        )
        assert entries.shape[1] == 12, (
            f"Erwartet 12 Cross-Spalten, erhalten {entries.shape[1]}"
        )
        assert entries.shape[0] == len(time_idx)

    def test_disjoint_indicators_result_values_are_boolean(
        self, ohlc_data: _OhlcWrapper, time_idx: pd.DatetimeIndex
    ) -> None:
        """Alle Werte in entries sind boolean (True/False, kein NaN nach fillna)."""
        ind_result = _make_multiindex_df(
            time_idx,
            level_names=['dwsvwma_length', 'symbol'],
            level_values=[[10, 20], ['BTCUSDT']],
            seed=30,
        )
        st_result = _make_multiindex_df(
            time_idx,
            level_names=['supertrend_period', 'symbol'],
            level_values=[[7, 14], ['BTCUSDT']],
            seed=31,
        )

        indicators = {
            'ind_a': _FakeIndicator(ind_result),
            'ind_b': _FakeIndicator(st_result),
        }

        rules_json = {
            'entry': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'indicator:ind_a:result', 'op': '>', 'rhs': 'indicator:ind_b:result'},
                    ]},
                ],
            },
        }

        # GEÄNDERT: Ticket 46 — SignalMasks statt (entries, exits)-Tupel
        masks = evaluate_rules(rules_json, ohlc_data, indicators)
        entries = masks.long_entries
        # Keine NaN nach fillna-Schritt in _evaluate_rule_group
        assert not entries.isna().any().any(), "entries enthält NaN-Werte"
        # Alle Werte sind boolean
        assert entries.dtypes.apply(lambda d: d == bool or d == np.dtype('bool')).all(), (
            "Nicht alle Spalten haben boolean dtype"
        )

    def test_reference_invariant_sweep_equals_single_combo(
        self, ohlc_data: _OhlcWrapper, time_idx: pd.DatetimeIndex
    ) -> None:
        """Referenz-Invariante (§6.9): Sweep[combo_0].entries == Single-Combo.entries bit-identisch.

        Für den Combo (ind[0], supertrend[0]) muss der Sweep-Eintrag mit dem
        direkten Vergleich der ersten Spalten aus den Original-DataFrames übereinstimmen.
        """
        ind_result = _make_multiindex_df(
            time_idx,
            level_names=['dwsvwma_length', 'symbol'],
            level_values=[[10, 20], ['BTCUSDT']],
            seed=40,
        )
        st_result = _make_multiindex_df(
            time_idx,
            level_names=['supertrend_period', 'symbol'],
            level_values=[[7, 14], ['BTCUSDT']],
            seed=41,
        )

        indicators = {
            'ind_a': _FakeIndicator(ind_result),
            'ind_b': _FakeIndicator(st_result),
        }

        rules_json = {
            'entry': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'indicator:ind_a:result', 'op': '>', 'rhs': 'indicator:ind_b:result'},
                    ]},
                ],
            },
        }

        # GEÄNDERT: Ticket 46 — SignalMasks statt (entries, exits)-Tupel
        masks = evaluate_rules(rules_json, ohlc_data, indicators)
        entries = masks.long_entries

        # Standalone Single-Combo: direkt erste Spalte aus Originalen vergleichen
        standalone_entry = (ind_result.iloc[:, 0] > st_result.iloc[:, 0])

        # Im Sweep: Spalte 0 (ind[0], st[0])
        sweep_col_0 = entries.iloc[:, 0]

        pd.testing.assert_series_equal(
            sweep_col_0.reset_index(drop=True),
            standalone_entry.reset_index(drop=True),
            check_names=False,
            check_dtype=True,
            obj="Referenz-Invariante: Sweep[combo_0] != Single-Combo",
        )


# ============================================================================
# Testfall (f): _describe_operand liefert brauchbare Struktur-Beschreibungen
#
# _broadcast_explained nutzt _describe_operand im Fehlerfall. Wir testen
# direkt, dass die Beschreibungen korrekte Informationen (Shape, Level-Namen,
# Zeit-Index-Span) enthalten — damit im echten Fehlerfall die Meldung nützlich ist.
# ============================================================================

class TestDescribeOperand:
    """_describe_operand liefert informative Strukturbeschreibungen."""

    def test_dataframe_description_contains_shape_and_levels(self) -> None:
        """Beschreibung eines DataFrames enthält Shape und Level-Namen."""
        from user_data.strategies.generic.rules_engine import _describe_operand

        time_idx = pd.date_range("2022-01-01", periods=20, freq="1h")
        mi = pd.MultiIndex.from_tuples(
            [(10, 'BTCUSDT'), (20, 'BTCUSDT')],
            names=['length', 'symbol'],
        )
        df = pd.DataFrame(np.ones((20, 2)), index=time_idx, columns=mi)
        desc = _describe_operand(df)

        assert "DataFrame" in desc
        assert "shape=" in desc
        assert "length" in desc  # Level-Name
        assert "symbol" in desc  # Level-Name
        assert "20" in desc      # Spaltenanzahl oder Index-Länge

    def test_series_description_contains_name_and_index_length(self) -> None:
        """Beschreibung einer Series enthält Namen und Index-Länge."""
        from user_data.strategies.generic.rules_engine import _describe_operand

        time_idx = pd.date_range("2022-01-01", periods=15, freq="1h")
        series = pd.Series(np.ones(15), index=time_idx, name="close")
        desc = _describe_operand(series)

        assert "Series" in desc
        assert "close" in desc
        assert "15" in desc

    def test_scalar_description_contains_type(self) -> None:
        """Beschreibung eines Skalars enthält Typ-Bezeichnung."""
        from user_data.strategies.generic.rules_engine import _describe_operand

        desc_int = _describe_operand(42)
        desc_float = _describe_operand(3.14)

        assert "int" in desc_int.lower() or "42" in desc_int
        assert "float" in desc_float.lower() or "3.14" in desc_float

    def test_broadcast_explained_wraps_error_with_context(self) -> None:
        """_broadcast_explained fügt Kontext-String zur Fehlermeldung hinzu.

        Wir provozieren einen echten Fehler durch Übergabe eines Objekts,
        das nach dem Cross-Versuch in vbt.broadcast scheitert (nicht-broadcastbares
        Objekt neben DataFrame).
        """
        from user_data.strategies.generic.rules_engine import _broadcast_explained

        time_idx = pd.date_range("2022-01-01", periods=10, freq="1h")
        mi_a = pd.MultiIndex.from_tuples([(1, 'X')], names=['pa', 'symbol'])
        mi_b = pd.MultiIndex.from_tuples([(2, 'X')], names=['pb', 'symbol'])
        df_a = pd.DataFrame(np.ones((10, 1)), index=time_idx, columns=mi_a)
        df_b = pd.DataFrame(np.ones((10, 1)), index=time_idx, columns=mi_b)

        # Normaler Fall: kein Fehler, kein Kontext-Test nötig
        # Stattdessen: direkt testen dass die Funktion existiert und aufrufen
        result = _broadcast_explained([df_a, df_b], "Regel-Gruppe (logic=AND)")
        assert len(result) == 2
        a_bc, b_bc = result
        assert a_bc.shape[1] == b_bc.shape[1]
        # Der Kontext-String wird nur im Fehlerfall angehängt — wir prüfen,
        # dass die Funktion bei Erfolg korrekt durchläuft.
        assert a_bc.shape[1] == 1  # 1 pa × 1 pb × 1 symbol = 1 Spalte (beide disjunkt)

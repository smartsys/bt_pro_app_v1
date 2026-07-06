"""Tests für das Kreuzen disjunkter Entry-/Exit-Sweep-Achsen im nativen Pfad
(Audit 2026-07-06 Befund 1, Ticket 51).

Sweepen Entry- und Exit-Regeln verschiedene Parameter-Achsen, baut
evaluate_rules_native die Combo-Achse als Kreuzprodukt der disjunkten Achsen
und expandiert alle Quellen darauf (Entry-Masken, statische Exit-Masken,
stateful Series-Slots). Vorher entstanden stille Falschergebnisse:
  (a) Out-of-bounds-Read der Entry-Maske (Achsen ungleicher Breite),
  (b) stiller Kollaps einer stateful Exit-Achse,
  (c) Diagonal-Paarung gleich breiter disjunkter Achsen.

Kern-Nachweis: jede Kombination des Kreuzprodukts ist bit-identisch zum
Einzel-Lauf mit fixierten Parametern (per Spalten-Slice derselben Daten).
Zusätzlich pinnen Positiv-Tests fest, dass die schon vorher unterstützten
Konstellationen (gemeinsame Achse, Achse nur im Exit, Teilmengen-Exit-Maske,
stateful Exit auf der Entry-Achse) unverändert laufen.

Fixtures erstellen synthetische Daten deterministisch (kein Hardcoding).
"""

import sys
import os

# Projekt-Root in sys.path eintragen
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import itertools

import numpy as np
import pandas as pd
import pytest

from user_data.strategies.generic.rules_engine import evaluate_rules_native


# ============================================================================
# Fixtures und Hilfen: synthetische OHLC-Daten und Fake-Indikatoren
# ============================================================================

class _OhlcWrapper:
    """Minimaler ohlc_data-Wrapper: implementiert .get(key) für OHLCV-Spalten."""

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def get(self, key: str) -> pd.Series:
        return self._df[key]


class _FakeIndicator:
    """Minimaler Indikator-Stub, der .result als festes DataFrame zurückgibt."""

    output_names = ('result',)

    def __init__(self, result_df: pd.DataFrame) -> None:
        self.result = result_df


def _make_ohlc_df(n: int = 120, seed: int = 42) -> pd.DataFrame:
    """Deterministischer OHLC-DataFrame (Random Walk um ~100)."""
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


def _make_const_df(
    time_index: pd.DatetimeIndex,
    level_name: str,
    values: list,
) -> pd.DataFrame:
    """Baut einen Indikator-DataFrame: Spalte j ist konstant values[j].

    Die Konstanten liegen im Preisbereich der OHLC-Daten (~100), damit
    Vergleiche gegen close/max_price je Spalte unterschiedliche Masken erzeugen —
    jede Achsen-Position wirkt nachweislich aufs Ergebnis.
    """
    mi = pd.MultiIndex.from_tuples([(v,) for v in values], names=[level_name])
    data = np.tile(np.asarray(values, dtype=float), (len(time_index), 1))
    return pd.DataFrame(data, index=time_index, columns=mi)


@pytest.fixture
def ohlc_df() -> pd.DataFrame:
    return _make_ohlc_df(120, seed=42)


@pytest.fixture
def ohlc_data(ohlc_df: pd.DataFrame) -> _OhlcWrapper:
    return _OhlcWrapper(ohlc_df)


@pytest.fixture
def pf_kwargs(ohlc_df: pd.DataFrame) -> dict:
    return dict(
        close=ohlc_df['Close'],
        init_cash=10_000.0,
        fees=0.0,
        freq="1h",
    )


def _rules(entry_conditions: list, exit_conditions: list) -> dict:
    """Minimale rules_json im Block-Format mit je einem Entry-/Exit-Block."""
    rules: dict = {
        'entry': {'blocks': [{'conditions': entry_conditions}]},
    }
    if exit_conditions:
        rules['exit'] = {'blocks': [{'conditions': exit_conditions}]}
    return rules


def _total_return_scalar(pf) -> float:
    """Liest den Total Return eines 1-Spalten-Portfolios als float."""
    tr = pf.total_return
    if isinstance(tr, pd.Series):
        assert len(tr) == 1
        return float(tr.iloc[0])
    return float(tr)


def _select_combo(series: pd.Series, level_values: dict) -> float:
    """Selektiert genau einen Wert aus einer MultiIndex-Series per Level-Werten."""
    mask = np.ones(len(series), dtype=bool)
    for level, value in level_values.items():
        mask &= series.index.get_level_values(level) == value
    sel = series[mask]
    assert len(sel) == 1, (
        f"Combo {level_values}: erwartet genau 1 Treffer, erhalten {len(sel)}"
    )
    return float(sel.iloc[0])


def _assert_cross_parity(
    ohlc_data: _OhlcWrapper,
    pf_kwargs: dict,
    rules_json: dict,
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    level_a: str,
    level_b: str,
) -> pd.Series:
    """Fährt den Sweep und vergleicht JEDE Kombi bit-genau mit ihrem Einzel-Lauf.

    Die Einzel-Läufe nutzen Spalten-Slices derselben DataFrames — identische
    Daten, fixierte Parameter. Liefert die Sweep-total_return-Series zurück.
    """
    indicators = {'ind_a': _FakeIndicator(df_a), 'ind_b': _FakeIndicator(df_b)}
    pf = evaluate_rules_native(rules_json, ohlc_data, indicators, dict(pf_kwargs))

    n_a, n_b = df_a.shape[1], df_b.shape[1]
    assert len(pf.wrapper.columns) == n_a * n_b, (
        f"Erwartet {n_a * n_b} Kreuz-Spalten, erhalten {len(pf.wrapper.columns)}"
    )
    assert set(pf.wrapper.columns.names) >= {level_a, level_b}, (
        f"Spalten-Labels tragen nicht beide Achsen: {pf.wrapper.columns.names}"
    )

    sweep_tr = pf.total_return
    for i, j in itertools.product(range(n_a), range(n_b)):
        single_indicators = {
            'ind_a': _FakeIndicator(df_a.iloc[:, [i]]),
            'ind_b': _FakeIndicator(df_b.iloc[:, [j]]),
        }
        pf_single = evaluate_rules_native(
            rules_json, ohlc_data, single_indicators, dict(pf_kwargs)
        )
        single_val = _total_return_scalar(pf_single)
        sweep_val = _select_combo(sweep_tr, {
            level_a: df_a.columns.get_level_values(level_a)[i],
            level_b: df_b.columns.get_level_values(level_b)[j],
        })
        assert sweep_val == single_val, (
            f"Kombi (a={df_a.columns[i]}, b={df_b.columns[j]}): Sweep {sweep_val} "
            f"!= Einzel-Lauf {single_val} (bit-identisch erwartet)"
        )
    return sweep_tr


# ============================================================================
# Kreuzprodukt-Fälle: die drei früheren Audit-Fehlpfade laufen jetzt korrekt
# ============================================================================

class TestDisjointAxesCrossed:
    """Disjunkte Entry-/Exit-Achsen werden gekreuzt und rechnen je Kombi korrekt."""

    def test_unequal_width_axes_cross(
        self, ohlc_df: pd.DataFrame, ohlc_data: _OhlcWrapper, pf_kwargs: dict
    ) -> None:
        """Ehemals Fehlpfad (a): Entry-Achse Breite 2 x statische Exit-Achse Breite 3.

        Vorher: n_combo=3, Entry-Maske (T, 2) -> Out-of-bounds-Read in der
        njit-Funktion. Jetzt: 6 Kombis, jede bit-identisch zum Einzel-Lauf.
        """
        df_a = _make_const_df(ohlc_df.index, 'ind_a_level', [95.0, 105.0])
        df_b = _make_const_df(ohlc_df.index, 'ind_b_level', [90.0, 100.0, 110.0])
        rules_json = _rules(
            entry_conditions=[{'lhs': 'close', 'op': '>', 'rhs': 'indicator:ind_a:result'}],
            exit_conditions=[{'lhs': 'close', 'op': '<', 'rhs': 'indicator:ind_b:result'}],
        )
        sweep_tr = _assert_cross_parity(
            ohlc_data, pf_kwargs, rules_json, df_a, df_b, 'ind_a_level', 'ind_b_level'
        )
        # Die Exit-Achse wirkt: nicht alle Kombis liefern dasselbe Ergebnis.
        assert sweep_tr.nunique() > 1, "Exit-Achse ohne Wirkung — Achsen-Kollaps?"

    def test_equal_width_axes_cross_not_diagonal(
        self, ohlc_df: pd.DataFrame, ohlc_data: _OhlcWrapper, pf_kwargs: dict
    ) -> None:
        """Ehemals Fehlpfad (c): disjunkte Achsen GLEICHER Breite (2 x 2).

        Vorher: Diagonal-Paarung (2 Ergebnisse statt 4) mit falschen Labels.
        Jetzt: volles Kreuzprodukt, 4 Kombis, Einzel-Lauf-Parität.
        """
        df_a = _make_const_df(ohlc_df.index, 'ind_a_level', [95.0, 105.0])
        df_b = _make_const_df(ohlc_df.index, 'ind_b_level', [98.0, 108.0])
        rules_json = _rules(
            entry_conditions=[{'lhs': 'close', 'op': '>', 'rhs': 'indicator:ind_a:result'}],
            exit_conditions=[{'lhs': 'close', 'op': '<', 'rhs': 'indicator:ind_b:result'}],
        )
        _assert_cross_parity(
            ohlc_data, pf_kwargs, rules_json, df_a, df_b, 'ind_a_level', 'ind_b_level'
        )

    def test_stateful_exit_own_axis_cross(
        self, ohlc_df: pd.DataFrame, ohlc_data: _OhlcWrapper, pf_kwargs: dict
    ) -> None:
        """Ehemals Fehlpfad (b): stateful Exit-Operand mit eigener Sweep-Achse.

        Vorher: n_series_per_col = 2 // 3 = 0, alle Spalten lasen Bundle-Offset 0 —
        die Exit-Achse verschwand still. Jetzt: Kreuz 2 x 2, Bundle expandiert,
        jede Kombi bit-identisch zum Einzel-Lauf.
        """
        df_a = _make_const_df(ohlc_df.index, 'ind_a_level', [95.0, 105.0])
        df_b = _make_const_df(ohlc_df.index, 'ind_b_level', [103.0, 115.0])
        rules_json = _rules(
            entry_conditions=[{'lhs': 'close', 'op': '>', 'rhs': 'indicator:ind_a:result'}],
            exit_conditions=[{
                'lhs': 'max_price_since_entry', 'op': '>', 'rhs': 'indicator:ind_b:result',
            }],
        )
        sweep_tr = _assert_cross_parity(
            ohlc_data, pf_kwargs, rules_json, df_a, df_b, 'ind_a_level', 'ind_b_level'
        )
        # Die stateful Exit-Achse wirkt (kein stiller Kollaps auf Kombi 0).
        b_level = sweep_tr.index.get_level_values('ind_b_level')
        tr_b0 = sweep_tr[b_level == 103.0].values
        tr_b1 = sweep_tr[b_level == 115.0].values
        assert not np.array_equal(tr_b0, tr_b1), (
            "Beide Exit-Kombis identisch — stateful Exit-Achse ohne Wirkung"
        )

    def test_entry_axis_subset_of_exit_axis(
        self, ohlc_df: pd.DataFrame, ohlc_data: _OhlcWrapper, pf_kwargs: dict
    ) -> None:
        """Entry-Achse als echte Teilmenge der Exit-Kreuz-Achse (alignbarer Fall).

        Entry sweept nur A (Breite 2); die statische Exit-Condition kreuzt A x B
        (2 x 3 = 6). Die Entry-Maske (Breite 2) muss auf die volle Achse
        expandiert werden — vorher Out-of-bounds-Read trotz alignbarer Namen.
        """
        df_a = _make_const_df(ohlc_df.index, 'ind_a_level', [95.0, 105.0])
        df_b = _make_const_df(ohlc_df.index, 'ind_b_level', [90.0, 100.0, 110.0])
        indicators = {'ind_a': _FakeIndicator(df_a), 'ind_b': _FakeIndicator(df_b)}
        rules_json = _rules(
            entry_conditions=[{'lhs': 'close', 'op': '>', 'rhs': 'indicator:ind_a:result'}],
            exit_conditions=[{
                'lhs': 'indicator:ind_a:result', 'op': '>', 'rhs': 'indicator:ind_b:result',
            }],
        )
        pf = evaluate_rules_native(rules_json, ohlc_data, indicators, dict(pf_kwargs))
        assert len(pf.wrapper.columns) == 6, (
            f"Erwartet 6 Spalten (Entry-Teilmenge auf A x B expandiert), "
            f"erhalten {len(pf.wrapper.columns)}"
        )


# ============================================================================
# Positiv-Fälle: schon vorher unterstützte Konstellationen bleiben unverändert
# ============================================================================

class TestSupportedConstellationsStillRun:
    """Geteilte Achsen und Teilmengen-Exits laufen wie vor Ticket 51."""

    def _indicators(self, ohlc_df: pd.DataFrame, axes: dict) -> dict:
        """Baut Fake-Indikatoren: axes = {ind_id: (level_name, werte_liste)}."""
        return {
            ind_id: _FakeIndicator(_make_const_df(ohlc_df.index, level_name, values))
            for ind_id, (level_name, values) in axes.items()
        }

    def test_shared_axis_entry_and_exit_runs(
        self, ohlc_df: pd.DataFrame, ohlc_data: _OhlcWrapper, pf_kwargs: dict
    ) -> None:
        """Gemeinsame Achse: Entry und statischer Exit sweepen denselben Indikator."""
        indicators = self._indicators(ohlc_df, {
            'ind_a': ('ind_a_level', [95.0, 100.0, 105.0]),
        })
        rules_json = _rules(
            entry_conditions=[{'lhs': 'close', 'op': '>', 'rhs': 'indicator:ind_a:result'}],
            exit_conditions=[{'lhs': 'close', 'op': '<', 'rhs': 'indicator:ind_a:result'}],
        )
        pf = evaluate_rules_native(rules_json, ohlc_data, indicators, dict(pf_kwargs))
        assert len(pf.wrapper.columns) == 3

    def test_axis_only_in_exit_runs(
        self, ohlc_df: pd.DataFrame, ohlc_data: _OhlcWrapper, pf_kwargs: dict
    ) -> None:
        """Achse nur im Exit: Entry 1-spaltig, statische Exit-Condition trägt den Sweep."""
        indicators = self._indicators(ohlc_df, {
            'ind_b': ('ind_b_level', [90.0, 100.0, 110.0, 120.0]),
        })
        rules_json = _rules(
            entry_conditions=[{'lhs': 'close', 'op': '>', 'rhs': 0.0}],
            exit_conditions=[{'lhs': 'close', 'op': '<', 'rhs': 'indicator:ind_b:result'}],
        )
        pf = evaluate_rules_native(rules_json, ohlc_data, indicators, dict(pf_kwargs))
        assert len(pf.wrapper.columns) == 4

    def test_subset_exit_mask_runs(
        self, ohlc_df: pd.DataFrame, ohlc_data: _OhlcWrapper, pf_kwargs: dict
    ) -> None:
        """Teilmengen-Exit: Entry kreuzt A x B (6 Spalten), Exit nutzt nur Achse A."""
        indicators = self._indicators(ohlc_df, {
            'ind_a': ('ind_a_level', [95.0, 100.0, 105.0]),
            'ind_b': ('ind_b_level', [98.0, 108.0]),
        })
        rules_json = _rules(
            entry_conditions=[{
                'lhs': 'indicator:ind_a:result', 'op': '<', 'rhs': 'indicator:ind_b:result',
            }],
            exit_conditions=[{'lhs': 'close', 'op': '<', 'rhs': 'indicator:ind_a:result'}],
        )
        pf = evaluate_rules_native(rules_json, ohlc_data, indicators, dict(pf_kwargs))
        assert len(pf.wrapper.columns) == 6

    def test_stateful_exit_on_entry_axis_runs(
        self, ohlc_df: pd.DataFrame, ohlc_data: _OhlcWrapper, pf_kwargs: dict
    ) -> None:
        """Stateful Exit-Operand auf der Entry-Achse: gleiche Achse, kein Kreuz."""
        indicators = self._indicators(ohlc_df, {
            'ind_a': ('ind_a_level', [95.0, 100.0, 105.0]),
        })
        rules_json = _rules(
            entry_conditions=[{'lhs': 'close', 'op': '>', 'rhs': 'indicator:ind_a:result'}],
            exit_conditions=[{
                'lhs': 'max_price_since_entry', 'op': '>', 'rhs': 'indicator:ind_a:result',
            }],
        )
        pf = evaluate_rules_native(rules_json, ohlc_data, indicators, dict(pf_kwargs))
        assert len(pf.wrapper.columns) == 3

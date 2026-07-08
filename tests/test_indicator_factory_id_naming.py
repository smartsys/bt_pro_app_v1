"""Regressionstests fuer Ticket 53 — Getragene Ketten-Param-Level id-benennen.

Kernbefund (Ticket 53): Ein Indikator, der einen anderen als Chain-Input traegt,
fuehrte dessen Param-Level bisher unter dem Factory-Namen (z.B. 'dwsfastsma_length')
statt dem Spec-ID-Namen ('fast_sma_length') mit. Wird derselbe Indikator zugleich
direkt referenziert (dort von rules_engine._uniquify_param_levels bereits auf den
ID-Namen umbenannt), galten die beiden Achsen als disjunkt und wurden von
_combine_broadcast gekreuzt statt gefaltet — die Portfolio-Spaltenzahl blaeht sich
um den Faktor der geteilten Achse auf (7x-Blowup, Run 219/iteration 7).

Fix (Variante A, siehe indicator_factory.py): jede Indikator-Instanz wird direkt
beim Bauen auf `<ind_id>_<param>` umbenannt, bevor sie als Chain-Input oder
Direkt-Referenz konsumiert wird.

Empirisch verifiziert (VBT-MCP run_code, vor der Implementierung): VBTs eingebautes
`IndicatorBase.rename()`/`.rename_levels()` bricht mit `IndexError: tuple index out
of range` bei Indikatoren mit genau EINEM Parameter (z.B. dwsConst, dwsVWMABand) —
`level_names` ist dort strukturell leer (`_tuple_mapper` liefert nur ab zwei Params
ein MultiIndex). Deshalb reimplementiert `_rename_indicator_instance` das Renaming
robust ueber `param_names` statt `level_names`.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import vectorbtpro as vbt

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from user_data.strategies.generic.indicator_factory import (
    build_indicators,
    count_total_combos,
    _RealignedIndicator,
)
from user_data.strategies.generic.rules_engine import evaluate_rules


@pytest.fixture
def base_data() -> vbt.Data:
    """5min-Basis-Daten (3 Tage, lueckenlos) als konfiguriertes vbt.Data."""
    idx = pd.date_range("2020-01-01", periods=3 * 24 * 12, freq="5min", tz="UTC")
    n = len(idx)
    rng = np.random.default_rng(11)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 0.1, n)), index=idx, name="Close")
    df = pd.DataFrame({
        "Open": close.shift(1).bfill(),
        "High": close + 0.5,
        "Low": close - 0.5,
        "Close": close,
        "Volume": pd.Series(rng.uniform(1, 5, n), index=idx),
    })
    data = vbt.Data.from_data({"X": df})
    data.use_feature_config_of(vbt.BinanceData)
    return data


# ============================================================================
# Kernfall: getragener Indikator wird zugleich direkt referenziert
# (iteration-7-Muster: fast_sma direkt UND als Chain-Input von vwma)
# ============================================================================

class TestCarriedAndDirectReference:
    """fast_sma direkt referenziert + zugleich Chain-Input von vwma -> KEIN Blowup."""

    @pytest.fixture
    def spec(self) -> dict:
        return {
            "fast_sma": {"indicator": "custom:dwsFastSMA", "tf": "same",
                        "source": "close", "length": [5, 10, 15], "multiplier": 1},
            "vwma": {"indicator": "custom:dwsVWMA", "tf": "same",
                    "source": "indicator:fast_sma:result", "volume": "volume",
                    "length": [10, 20], "below_pct": 1},
            "sma": {"indicator": "talib:SMA", "tf": "same",
                    "close": "close", "timeperiod": [7, 14]},
        }

    def test_carried_axis_uses_id_name_not_factory_name(self, base_data, spec):
        """vwma traegt die fast_sma-Achse als 'fast_sma_length', nicht 'dwsfastsma_length'."""
        results = build_indicators(spec, base_data, base_tf="5min")
        vwma_cols = results["vwma"].result.columns.names
        assert "fast_sma_length" in vwma_cols, (
            f"Erwartet 'fast_sma_length' in vwma-Columns, erhalten {vwma_cols}"
        )
        assert "dwsfastsma_length" not in vwma_cols, (
            "Factory-Name 'dwsfastsma_length' haette umbenannt sein muessen"
        )

    def test_direct_and_carried_axis_share_identical_name(self, base_data, spec):
        """Direkt-Referenz (fast_sma.result) und getragene Achse (in vwma) tragen denselben Namen."""
        results = build_indicators(spec, base_data, base_tf="5min")
        direct_cols = set(results["fast_sma"].result.columns.names)
        carried_cols = set(results["vwma"].result.columns.names)
        assert direct_cols <= carried_cols, (
            f"fast_sma direkt {direct_cols} muss Teilmenge der vwma-Columns {carried_cols} sein"
        )

    def test_column_count_matches_count_total_combos_no_blowup(self, base_data, spec):
        """Portfolio-Spaltenzahl == count_total_combos, kein Faktor auf der geteilten Achse.

        Ohne Fix: 12 (echte Kombis) x 3 (fast_sma.length erneut gekreuzt) = 36.
        Mit Fix: 12 (fast_sma.length=3 x vwma.length=2 x sma.timeperiod=2).
        """
        results = build_indicators(spec, base_data, base_tf="5min")
        rules_json = {
            "entry": {
                "blocks": [
                    {"conditions": [
                        {"lhs": "close", "op": "<", "rhs": "indicator:vwma:result"},
                        {"lhs": "close", "op": ">", "rhs": "indicator:sma:real"},
                        {"lhs": "close", "op": ">", "rhs": "indicator:fast_sma:result"},
                    ]},
                ],
            },
        }
        masks = evaluate_rules(rules_json, base_data, results)
        expected = count_total_combos(spec)
        assert expected == 12, f"Testannahme verletzt: erwartet 12 Kombis, Spec liefert {expected}"
        assert masks.long_entries.shape[1] == expected, (
            f"Erwartet {expected} Spalten (kein Blowup), erhalten {masks.long_entries.shape[1]}"
        )


# ============================================================================
# Robustheitstestfall (i): tiefere Kette A -> B -> C
# ============================================================================

class TestDeepChainPropagation:
    """Der id-Name propagiert ueber zwei Kettenstufen, keine Achsen-Verdopplung."""

    @pytest.fixture
    def spec(self) -> dict:
        return {
            "fast_sma": {"indicator": "custom:dwsFastSMA", "tf": "same",
                        "source": "close", "length": [5, 10], "multiplier": 1},
            "vwma": {"indicator": "custom:dwsVWMA", "tf": "same",
                    "source": "indicator:fast_sma:result", "volume": "volume",
                    "length": [10, 20], "below_pct": 1},
            "band": {"indicator": "custom:dwsVWMABand", "tf": "same",
                    "source": "indicator:vwma:result", "volume": "volume",
                    "below_series": "close", "length": [7, 14]},
        }

    def test_fast_sma_axis_propagates_through_two_levels(self, base_data, spec):
        """band (C) traegt die fast_sma-Achse (A) ueber vwma (B) hinweg als 'fast_sma_length'."""
        results = build_indicators(spec, base_data, base_tf="5min")
        band_cols = results["band"].result.columns.names
        assert "fast_sma_length" in band_cols, (
            f"Erwartet 'fast_sma_length' in band-Columns (A->B->C), erhalten {band_cols}"
        )
        # Kein Level-Name-Duplikat
        for name in set(band_cols):
            assert band_cols.count(name) == 1, f"Level '{name}' kommt {band_cols.count(name)}x vor"

    def test_no_axis_duplication_in_column_count(self, base_data, spec):
        """band-Spaltenzahl = Produkt ALLER varianten Achsen genau einmal (2x2x2=8), kein Blowup."""
        results = build_indicators(spec, base_data, base_tf="5min")
        assert results["band"].result.shape[1] == 8, (
            f"Erwartet 8 Spalten (2 fast_sma x 2 vwma x 2 band), erhalten "
            f"{results['band'].result.shape[1]}"
        )


# ============================================================================
# Robustheitstestfall (ii): zwei verschiedene Instanzen derselben Klasse,
# BEIDE als Chain-Input in denselben Downstream getragen (Ticket-49-Crash-Schutz)
# ============================================================================

class TestTwoInstancesSameClassAsChainInputs:
    """Zwei dwsConst-Instanzen, je als Chain-Input in einen eigenen Downstream getragen,
    kreuzen ueber _combine_broadcast korrekt — anders als der 9-Spalten-Fall in
    test_rules_engine_combine_broadcast.py (dort direkt referenziert), hier ERST ueber
    eine Kettenstufe (sma_a/sma_b) getragen. Deckt ab, dass die id-Umbenennung des
    CARRIED Levels (nicht nur des direkt referenzierten) die Ticket-49-Instanz-
    Eindeutigkeit nicht bricht.
    """

    @pytest.fixture
    def spec(self) -> dict:
        return {
            "thr_a": {"indicator": "custom:dwsConst", "tf": "same",
                     "source": "close", "value": [1.0, 2.0, 3.0]},
            "thr_b": {"indicator": "custom:dwsConst", "tf": "same",
                     "source": "close", "value": [10.0, 20.0, 30.0]},
            # sma_a/sma_b: gleiche Klasse (dwsFastSMA), eigene Params fix (keine
            # eigene Achse) — tragen je NUR die getragene thr_a-/thr_b-Achse.
            "sma_a": {"indicator": "custom:dwsFastSMA", "tf": "same",
                     "source": "indicator:thr_a:result", "length": 5, "multiplier": 1},
            "sma_b": {"indicator": "custom:dwsFastSMA", "tf": "same",
                     "source": "indicator:thr_b:result", "length": 5, "multiplier": 1},
        }

    def test_build_does_not_crash_on_single_param_instances(self, base_data, spec):
        """dwsConst (Einzel-Param) darf nicht mit IndexError crashen (VBT-Rename-Bug)."""
        results = build_indicators(spec, base_data, base_tf="5min")
        assert results["thr_a"].result.columns.names == ["thr_a_value"]
        assert results["thr_b"].result.columns.names == ["thr_b_value"]

    def test_carried_axes_keep_distinct_names(self, base_data, spec):
        """sma_a/sma_b tragen je die eigene thr_a-/thr_b-Achse unter deren ID-Namen."""
        results = build_indicators(spec, base_data, base_tf="5min")
        assert "thr_a_value" in results["sma_a"].result.columns.names
        assert "thr_b_value" in results["sma_b"].result.columns.names

    def test_both_carried_axes_cross_correctly_via_rule_no_crash(self, base_data, spec):
        """Regel referenziert sma_a UND sma_b -> _combine_broadcast kreuzt die getragenen
        thr_a-/thr_b-Achsen (3x3=9), kein cross_indexes-Crash (Ticket 49 bleibt geschuetzt)."""
        results = build_indicators(spec, base_data, base_tf="5min")
        rules_json = {
            "entry": {
                "blocks": [{"conditions": [
                    {"lhs": "close", "op": ">", "rhs": "indicator:sma_a:result"},
                    {"lhs": "close", "op": ">", "rhs": "indicator:sma_b:result"},
                ]}],
            },
        }
        masks = evaluate_rules(rules_json, base_data, results)
        assert masks.long_entries.shape[1] == 9, (
            f"Erwartet 9 Spalten (3x3 Kreuz der getragenen Achsen, kein Crash), "
            f"erhalten {masks.long_entries.shape[1]}"
        )


# ============================================================================
# Robustheitstestfall (iii): Per-tf-Indikator in Kette bzw. direkt referenziert
# ============================================================================

class TestPerTfIdNamePropagation:
    """Der id-Name greift auch ueber den _RealignedIndicator-Wrapper (Per-tf-Zweig)."""

    @pytest.fixture
    def spec(self) -> dict:
        return {
            "rsi": {"indicator": "talib:RSI", "tf": "4h",
                    "close": "close", "timeperiod": [7, 14]},
            "ema": {"indicator": "talib:EMA", "tf": "4h",
                    "close": "indicator:rsi:real", "timeperiod": [5, 10]},
        }

    def test_per_tf_direct_reference_uses_id_name(self, base_data, spec):
        results = build_indicators(spec, base_data, base_tf="5min")
        assert isinstance(results["rsi"], _RealignedIndicator)
        assert results["rsi"].real.columns.names == ["rsi_timeperiod"]

    def test_per_tf_chained_input_carries_id_name(self, base_data, spec):
        """ema (per-tf, chained auf rsi) traegt 'rsi_timeperiod' als geteilte Achse."""
        results = build_indicators(spec, base_data, base_tf="5min")
        ema_cols = results["ema"].real.columns.names
        assert "rsi_timeperiod" in ema_cols, (
            f"Erwartet 'rsi_timeperiod' in ema-Columns, erhalten {ema_cols}"
        )

    def test_per_tf_column_count_no_blowup(self, base_data, spec):
        """2 rsi x 2 ema = 4 Spalten, kein Kreuzen der geteilten rsi-Achse."""
        results = build_indicators(spec, base_data, base_tf="5min")
        assert results["ema"].real.shape[1] == 4, (
            f"Erwartet 4 Spalten (2x2), erhalten {results['ema'].real.shape[1]}"
        )


# ============================================================================
# Bit-Paritaet: Spec OHNE Doppel-Referenz bleibt in den Werten unveraendert
# (Anforderung 4) — nur die Spalten-NAMEN aendern sich (Anforderung 6, sauberer
# Schnitt), nicht die Werte.
# ============================================================================

class TestNoDoubleReferenceBitParity:
    """Ohne Doppel-Referenz (nur Chain, kein Direkt-Bezug) bleiben die Werte identisch."""

    @pytest.fixture
    def spec(self) -> dict:
        return {
            "fast_sma": {"indicator": "custom:dwsFastSMA", "tf": "same",
                        "source": "close", "length": [5, 10], "multiplier": 1},
            "vwma": {"indicator": "custom:dwsVWMA", "tf": "same",
                    "source": "indicator:fast_sma:result", "volume": "volume",
                    "length": [10, 20], "below_pct": 1},
        }

    def test_vwma_values_unaffected_by_rename(self, base_data, spec):
        """Die numerischen Werte von vwma.result sind unabhaengig vom Spalten-Namen identisch
        mit einem manuell (ohne Rename) berechneten Referenzlauf."""
        from user_data.strategies.generic.registry import resolve_indicator_factory
        from user_data.strategies.generic.indicator_factory import run_indicator_nan_safe

        results = build_indicators(spec, base_data, base_tf="5min")

        fast_sma_factory = resolve_indicator_factory("custom:dwsFastSMA")
        vwma_factory = resolve_indicator_factory("custom:dwsVWMA")
        ref_fast = run_indicator_nan_safe(
            fast_sma_factory, source=base_data.get("Close"),
            length=[5, 10], multiplier=[1], param_product=True,
        )
        ref_vwma = run_indicator_nan_safe(
            vwma_factory, source=ref_fast.result, volume=base_data.get("Volume"),
            length=[10, 20], below_pct=[1], param_product=True,
        )
        # Werte (nicht Spaltennamen!) muessen bit-identisch sein — beide Spalten-Reihenfolgen
        # entsprechen demselben kartesischen Produkt in derselben Erzeugungsreihenfolge.
        np.testing.assert_array_equal(
            np.asarray(results["vwma"].result), np.asarray(ref_vwma.result),
        )

    def test_column_count_unaffected(self, base_data, spec):
        results = build_indicators(spec, base_data, base_tf="5min")
        assert results["vwma"].result.shape[1] == 4, "2 fast_sma x 2 vwma = 4 (kein Blowup ohne Doppel-Ref)"

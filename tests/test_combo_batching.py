"""Unit-Tests für Combo-Batching in indicator_factory.split_indicators_json_chunks.

Teil 1: Chunking-Logik ohne echte VBT-Backtests (Mocks).
Teil 2: Echter End-to-End-Backtest-Vergleich — gechunkter vs. ungechunkter Lauf.
        Prüft bit-genaue Metrik-Gleichheit per Combo-Key (nicht positionsbasiert).
        Deckt Lücke 1 ab: Spaltenreihenfolge / Combo-Metrik-Mapping korrekt.

Ticket 44: Chunk-basierte Verarbeitung großer Multi-Parameter-Backtests.
"""

import copy
import itertools
import sys
import os
from typing import Any
from unittest.mock import MagicMock, patch

# GEÄNDERT: Ticket 44 — Lücke 2: Projekt-Root für direkte Ausführung ohne installed package
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pytest


# ---------------------------------------------------------------------------
# Hilfsfunktionen für die Tests
# ---------------------------------------------------------------------------

def _make_factory_mock(input_names: tuple = (), param_names: tuple = ()) -> MagicMock:
    """Erstellt einen minimalen Factory-Mock mit input_names und param_names."""
    m = MagicMock()
    m.input_names = input_names
    m.param_names = param_names
    return m


def _full_product(indicators_json: dict) -> list[dict]:
    """Berechnet das volle kartesische Produkt aus einem indicators_json.

    Gibt eine Liste von Dicts zurück, jedes repräsentiert eine Kombi.
    Nur variierende Parameter (Listen mit len > 1) werden aufgenommen.
    Skalare Parameter werden ignoriert (sie variieren nicht).
    """
    axes: list[tuple[str, str, list]] = []
    for ind_id, entry in indicators_json.items():
        if not isinstance(entry, dict) or entry.get('enabled', True) is False:
            continue
        for key, value in entry.items():
            if key in ('indicator', 'tf', 'enabled'):
                continue
            if isinstance(value, list) and len(value) > 1:
                axes.append((ind_id, key, value))
            elif isinstance(value, (int, float)):
                axes.append((ind_id, key, [value]))

    if not axes:
        return [{}]

    keys = [(ind_id, k) for ind_id, k, _ in axes]
    values = [v for _, _, v in axes]

    return [
        {(ind_id, k): val for (ind_id, k), val in zip(keys, combo)}
        for combo in itertools.product(*values)
    ]


def _chunk_product(chunks: list[dict]) -> list[dict]:
    """Gibt das kartesische Produkt aller Chunks als flache Liste zurück."""
    result = []
    for chunk in chunks:
        result.extend(_full_product(chunk))
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSplitIndicatorsJsonChunksNoSplit:
    """Tests für den Fall: kein Chunking erforderlich."""

    def test_no_varying_params_returns_single_chunk(self):
        """Skalar-Parameter: kein Chunking — immer ein einzelner Block."""
        indicators_json = {
            'sma': {
                'indicator': 'custom:SMA',
                'enabled': True,
                'length': 20,
            }
        }
        factory_mock = _make_factory_mock(input_names=('source',), param_names=('length',))

        with patch('user_data.strategies.generic.indicator_factory.resolve_indicator_factory',
                   return_value=factory_mock):
            from user_data.strategies.generic.indicator_factory import split_indicators_json_chunks
            chunks = split_indicators_json_chunks(indicators_json, chunk_size=5000)

        assert len(chunks) == 1
        assert chunks[0] is indicators_json

    def test_total_combos_within_chunk_size(self):
        """Gesamtzahl Kombis <= chunk_size: kein Chunking."""
        indicators_json = {
            'sma': {
                'indicator': 'custom:SMA',
                'enabled': True,
                'length': [10, 20, 30],  # 3 Werte
            }
        }
        factory_mock = _make_factory_mock(input_names=('source',), param_names=('length',))

        with patch('user_data.strategies.generic.indicator_factory.resolve_indicator_factory',
                   return_value=factory_mock):
            from user_data.strategies.generic.indicator_factory import split_indicators_json_chunks
            chunks = split_indicators_json_chunks(indicators_json, chunk_size=10)

        assert len(chunks) == 1

    def test_disabled_indicator_skipped(self):
        """Deaktivierter Indikator wird ignoriert — kein Chunking."""
        indicators_json = {
            'sma': {
                'indicator': 'custom:SMA',
                'enabled': False,   # deaktiviert
                'length': [10, 20, 30, 40, 50],
            }
        }
        factory_mock = _make_factory_mock(input_names=('source',), param_names=('length',))

        with patch('user_data.strategies.generic.indicator_factory.resolve_indicator_factory',
                   return_value=factory_mock):
            from user_data.strategies.generic.indicator_factory import split_indicators_json_chunks
            chunks = split_indicators_json_chunks(indicators_json, chunk_size=2)

        # Deaktiviert → keine variierenden Params → 1 Block
        assert len(chunks) == 1


class TestSplitIndicatorsJsonChunksBasic:
    """Tests für einfaches Chunking entlang einer Achse."""

    def test_single_param_three_chunks(self):
        """length=[10,20,30], chunk_size=2 → 2 Chunks (2+1 Werte)."""
        indicators_json = {
            'sma': {
                'indicator': 'custom:SMA',
                'enabled': True,
                'length': [10, 20, 30],
            }
        }
        factory_mock = _make_factory_mock(input_names=('source',), param_names=('length',))

        with patch('user_data.strategies.generic.indicator_factory.resolve_indicator_factory',
                   return_value=factory_mock):
            from user_data.strategies.generic.indicator_factory import split_indicators_json_chunks
            chunks = split_indicators_json_chunks(indicators_json, chunk_size=2)

        assert len(chunks) == 2
        assert chunks[0]['sma']['length'] == [10, 20]
        assert chunks[1]['sma']['length'] == [30]

    def test_two_params_chunk_along_first_axis(self):
        """length=[10,20,30], period=[5,10] → 6 Kombis.
        chunk_size=2 → inner_size=2, step=1 → 3 Chunks à 1 length-Wert.
        Jeder Chunk hat period vollständig (beide Werte).
        """
        indicators_json = {
            'sma': {
                'indicator': 'custom:SMA',
                'enabled': True,
                'length': [10, 20, 30],
                'period': [5, 10],
            }
        }
        factory_mock = _make_factory_mock(input_names=('source',), param_names=('length', 'period'))

        with patch('user_data.strategies.generic.indicator_factory.resolve_indicator_factory',
                   return_value=factory_mock):
            from user_data.strategies.generic.indicator_factory import split_indicators_json_chunks
            chunks = split_indicators_json_chunks(indicators_json, chunk_size=2)

        assert len(chunks) == 3
        # Jeder Chunk hat genau 1 length-Wert (outer-Achse)
        for chunk in chunks:
            assert len(chunk['sma']['length']) == 1
        # Jeder Chunk hat period vollständig
        for chunk in chunks:
            assert chunk['sma']['period'] == [5, 10]

    def test_chunks_are_deep_copies(self):
        """Jeder Chunk ist eine tiefe Kopie — Mutation des einen beeinflusst nicht andere."""
        indicators_json = {
            'sma': {
                'indicator': 'custom:SMA',
                'enabled': True,
                'length': [10, 20, 30],
                'period': [5, 10],
            }
        }
        factory_mock = _make_factory_mock(input_names=('source',), param_names=('length', 'period'))

        with patch('user_data.strategies.generic.indicator_factory.resolve_indicator_factory',
                   return_value=factory_mock):
            from user_data.strategies.generic.indicator_factory import split_indicators_json_chunks
            chunks = split_indicators_json_chunks(indicators_json, chunk_size=2)

        # Chunk 0 mutieren
        chunks[0]['sma']['length'] = [999]
        # Chunk 1 darf nicht beeinflusst sein
        assert chunks[1]['sma']['length'] != [999]

    def test_chunk_size_exactly_matches_total(self):
        """chunk_size == n_combos → kein Chunking (1 Block)."""
        indicators_json = {
            'sma': {
                'indicator': 'custom:SMA',
                'enabled': True,
                'length': [10, 20, 30],  # 3 Kombis
            }
        }
        factory_mock = _make_factory_mock(input_names=('source',), param_names=('length',))

        with patch('user_data.strategies.generic.indicator_factory.resolve_indicator_factory',
                   return_value=factory_mock):
            from user_data.strategies.generic.indicator_factory import split_indicators_json_chunks
            chunks = split_indicators_json_chunks(indicators_json, chunk_size=3)

        assert len(chunks) == 1


class TestSplitIndicatorsJsonChunksProductIntegrity:
    """Tests die sicherstellen, dass die Chunks zusammen das volle Produkt abdecken."""

    def test_all_combos_covered_single_indicator(self):
        """Alle Kombis aus dem Voll-Grid erscheinen genau einmal über alle Chunks."""
        indicators_json = {
            'sma': {
                'indicator': 'custom:SMA',
                'enabled': True,
                'length': list(range(1, 11)),   # 10 Werte
            }
        }
        factory_mock = _make_factory_mock(input_names=('source',), param_names=('length',))

        with patch('user_data.strategies.generic.indicator_factory.resolve_indicator_factory',
                   return_value=factory_mock):
            from user_data.strategies.generic.indicator_factory import split_indicators_json_chunks
            chunks = split_indicators_json_chunks(indicators_json, chunk_size=3)

        # Alle outer-Werte müssen in den Chunks enthalten sein
        all_outer_vals = []
        for chunk in chunks:
            all_outer_vals.extend(chunk['sma']['length'])

        assert sorted(all_outer_vals) == list(range(1, 11))

    def test_all_combos_covered_two_indicators(self):
        """Zwei-Achsen-Grid: Alle Kombis erscheinen genau einmal."""
        indicators_json = {
            'sma': {
                'indicator': 'custom:SMA',
                'enabled': True,
                'length': [10, 20, 30, 40, 50],   # 5 Werte — outer-Achse
                'period': [5, 10, 15],              # 3 Werte — inner-Achse
            }
        }
        # n_combos = 15, chunk_size=6 → inner_size=3, step=2 → 3 Chunks
        factory_mock = _make_factory_mock(input_names=('source',), param_names=('length', 'period'))

        with patch('user_data.strategies.generic.indicator_factory.resolve_indicator_factory',
                   return_value=factory_mock):
            from user_data.strategies.generic.indicator_factory import split_indicators_json_chunks
            chunks = split_indicators_json_chunks(indicators_json, chunk_size=6)

        # outer-Werte über alle Chunks
        all_lengths = []
        for chunk in chunks:
            all_lengths.extend(chunk['sma']['length'])
        assert sorted(all_lengths) == [10, 20, 30, 40, 50]

        # inner-Achse (period) bleibt vollständig in jedem Chunk
        for chunk in chunks:
            assert chunk['sma']['period'] == [5, 10, 15]

    def test_no_outer_value_lost_large_grid(self):
        """Großes Grid: kein outer-Wert geht verloren."""
        n_outer = 43
        indicators_json = {
            'ind': {
                'indicator': 'custom:IND',
                'enabled': True,
                'param_a': list(range(1, n_outer + 1)),  # 43 Werte
                'param_b': list(range(1, 11)),             # 10 Werte
                # n_combos = 430
            }
        }
        factory_mock = _make_factory_mock(input_names=(), param_names=('param_a', 'param_b'))

        with patch('user_data.strategies.generic.indicator_factory.resolve_indicator_factory',
                   return_value=factory_mock):
            from user_data.strategies.generic.indicator_factory import split_indicators_json_chunks
            chunks = split_indicators_json_chunks(indicators_json, chunk_size=50)

        all_a = []
        for chunk in chunks:
            all_a.extend(chunk['ind']['param_a'])

        # Keine Duplikate in param_a über Chunks
        assert len(all_a) == len(set(all_a))
        # Vollständigkeit
        assert sorted(all_a) == list(range(1, n_outer + 1))


class TestSplitIndicatorsJsonChunksMinStep:
    """Grenzfälle wenn inner_size >= chunk_size (step = 1)."""

    def test_step_one_when_inner_exceeds_chunk_size(self):
        """inner_size > chunk_size → step=1, jeder outer-Wert bekommt eigenen Chunk."""
        indicators_json = {
            'ind': {
                'indicator': 'custom:IND',
                'enabled': True,
                'param_a': [1, 2, 3],    # outer, 3 Werte
                'param_b': list(range(1, 101)),  # inner, 100 Werte → inner_size=100
                # n_combos = 300, chunk_size = 50
                # step = max(1, 50 // 100) = max(1, 0) = 1
            }
        }
        factory_mock = _make_factory_mock(input_names=(), param_names=('param_a', 'param_b'))

        with patch('user_data.strategies.generic.indicator_factory.resolve_indicator_factory',
                   return_value=factory_mock):
            from user_data.strategies.generic.indicator_factory import split_indicators_json_chunks
            chunks = split_indicators_json_chunks(indicators_json, chunk_size=50)

        # step=1 → 3 Chunks (je 1 param_a-Wert)
        assert len(chunks) == 3
        for chunk in chunks:
            assert len(chunk['ind']['param_a']) == 1
            assert len(chunk['ind']['param_b']) == 100


# ===========================================================================
# GEÄNDERT: Ticket 44 — Lücke 2: Echter Backtest-Vergleich (gechunkt vs. ungechunkt)
# ===========================================================================
# Diese Tests benötigen vectorbtpro und laufen NUR mit dem Windows-venv.
# Sie sind als separate Klasse mit pytest.mark.vbt_required markiert.
# ===========================================================================

def _make_synthetic_ohlc_data(n: int = 500, seed: int = 42):
    """Erstellt einen minimalen ohlc_data-Wrapper mit synthetischen OHLC-Daten.

    Reproduziert das _OhlcWrapper-Muster aus test_ticket35_native_state_exits.py.
    Gibt ein Objekt mit .get(key) zurück das Close/Open/High/Low/Volume liefert.
    """
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0, 0.01, size=n)
    close = 100.0 * np.exp(np.cumsum(returns))
    noise = rng.uniform(0.001, 0.005, size=n)
    high = close * (1 + noise)
    low = close * (1 - noise)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = rng.uniform(1000, 10000, size=n)
    idx = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")

    df = pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )

    class _OhlcWrapper:
        """Minimaler ohlc_data-Wrapper mit .get(key) Schnittstelle."""

        def __init__(self, df_: pd.DataFrame) -> None:
            self._df = df_

        def get(self, key: str):
            return self._df[key]

    return _OhlcWrapper(df)


def _build_fastsma_indicators_json(length_values: list, multiplier_values: list) -> dict:
    """Baut ein indicators_json mit dwsFastSMA und variierenden length + multiplier."""
    return {
        'fast_sma': {
            'indicator': 'custom:dwsFastSMA',
            'tf': '4h',
            'enabled': True,
            'source': 'close',
            'length': length_values,
            'multiplier': multiplier_values,
        }
    }


def _build_fastsma_backtest_config(chunk_size: int = 9999) -> dict:
    """Baut eine minimale Backtest-Config für dwsFastSMA-Tests."""
    return {
        'start': '2020-01-01',
        'end': '2020-12-31',
        'timeframe': '4h',
        'chunk_size': chunk_size,
        'portfolio': {
            'fees': 0.001,
            'size': 100.0,
            'size_type': 'value',
            'init_cash': 100.0,
            'tp_stop': None,
            'sl_stop': None,
            'tsl_th': None,
            'tsl_stop': None,
            'td_stop': None,
            'delta_format': None,
            'time_delta_format': None,
        },
    }


def _build_fastsma_rules_json() -> dict:
    """Einfache Entry/Exit-Regeln: close > fast_sma.result."""
    return {
        'entry': {
            'blocks': [
                {'conditions': [
                    {'lhs': 'close', 'op': '>', 'rhs': 'indicator:fast_sma:result'},
                ]},
            ],
        },
        'exit': {
            'blocks': [
                {'conditions': [
                    {'lhs': 'close', 'op': '<', 'rhs': 'indicator:fast_sma:result'},
                ]},
            ],
        },
    }


class TestRealBacktestChunkedVsUnchunked:
    """Echter End-to-End-Vergleich: gechunkter Lauf == ungechunkter Lauf.

    Lücke 2: Echter Backtest, Combo-Key-basierter Metrik-Vergleich.
    Lücke 1 (Spaltenreihenfolge): Wird durch Key-basierten Vergleich abgesichert —
    falsche Reihenfolge würde Metriken auf falsche Kombis mappen und den Test brechen.

    Anforderungen:
    - Mindestens 20 Kombis (hier: 5 length x 4 multiplier = 20)
    - >= 2 Chunks beim kleinen chunk_size
    - Alle Metriken aus _extract_partial_metrics werden verglichen
    - Kein Mock für Backtest-Logik
    - Kein Hardcoding von Metrik-Werten
    """

    def _run_backtest(self, chunk_size: int) -> list:
        """Führt einen Backtest mit gegebenem chunk_size aus und gibt Metriken-Liste zurück.

        GEÄNDERT: Ticket 47 Bugfix — der native Pfad verarbeitet Multi-Combo direkt.
        Bei chunk_size >= Anzahl Kombis kommt ein Multi-Combo-Portfolio ('portfolios')
        zurück, bei kleinerem chunk_size eine 'metrics_table'. Der Helper normalisiert
        beide Rückgabeformen auf eine positionsbasierte Metriken-Liste.

        Returns:
            list[dict] — Metriken-Records je Kombi, sortiert nach Eingangsreihenfolge.
        """
        from user_data.strategies.generic.spec_runner import run_spec_strategy
        from user_data.utils.database.repository import _extract_partial_metrics

        # length=[6,8,10,12,14] (5 Werte), multiplier=[2,3,4,5] (4 Werte) -> 20 Kombis
        length_vals = [6, 8, 10, 12, 14]
        multiplier_vals = [2, 3, 4, 5]

        ohlc_data = _make_synthetic_ohlc_data(n=500, seed=42)
        indicators_json = _build_fastsma_indicators_json(length_vals, multiplier_vals)
        backtest_config = _build_fastsma_backtest_config(chunk_size=chunk_size)
        rules_json = _build_fastsma_rules_json()

        result = run_spec_strategy(
            ohlc_data=ohlc_data,
            indicators_json=indicators_json,
            backtest_config_json=backtest_config,
            rules_json=rules_json,
        )

        # Beide Rückgabeformen auf eine Metriken-Liste normalisieren
        if 'metrics_table' in result:
            metrics_list = result['metrics_table']
        else:
            pf = result['portfolios']
            metrics_list = _extract_partial_metrics(pf, pf.wrapper.columns)

        # Metriken ohne 'metrics_level' normalisieren
        return [
            {k: v for k, v in m.items() if k != 'metrics_level'}
            for m in metrics_list
        ]

    def test_chunked_matches_unchunked_all_metrics(self) -> None:
        """Gechunkter Lauf produziert bit-genaue Metriken (positionsbasiert).

        GEÄNDERT: Ticket 47 Phase 2 — Multi-Combo läuft jetzt immer Single-Combo-
        gechunkt (nativer Pfad unterstützt kein Multi-Combo-Portfolio). Beide Läufe
        erzeugen 20 Single-Combo-Chunks. Der Vergleich erfolgt positionsbasiert.

        chunk_size=9999 → Auto-Split auf 20 Single-Combo-Chunks (Multi-Combo erkannt)
        chunk_size=5    → 5 outer-Chunks, jeder nochmals auf Single-Combo gesplittet
        Beide Läufe: 20 Kombis gesamt, positionsbasiert verglichen.
        """
        # Beide Läufe produzieren 20 Metriken-Einträge (positionsbasiert)
        unchunked = self._run_backtest(chunk_size=9999)
        chunked = self._run_backtest(chunk_size=5)

        # Gleiche Anzahl Kombis
        assert len(unchunked) == len(chunked), (
            f"Anzahl Kombis: ungechunkt={len(unchunked)}, gechunkt={len(chunked)}"
        )
        assert len(unchunked) == 20, f"Erwarte 20 Kombis, erhalten {len(unchunked)}"

        # GEÄNDERT: Ticket 47 Phase 2 — Positionsbasierter Vergleich (kein Key-Mapping).
        # Alle 16 Metriken müssen bit-genau übereinstimmen (abs-Diff < 1e-9).
        # DSR kann bei unterschiedlicher Chunk-Aufteilung leicht abweichen (globale
        # Varianz hängt von allen Kombis ab — gleich wenn alle 20 Kombis identisch).
        import math
        mismatches = []
        for i, (ref, chunked_m) in enumerate(zip(unchunked, chunked)):
            for metric_name, ref_val in ref.items():
                chunked_val = chunked_m.get(metric_name)
                if ref_val is None and chunked_val is None:
                    continue
                if ref_val is None or chunked_val is None:
                    mismatches.append(
                        f"  Kombi {i}: {metric_name}: ref={ref_val}, gechunkt={chunked_val}"
                    )
                    continue
                if math.isnan(ref_val) and math.isnan(chunked_val):
                    continue
                if abs(ref_val - chunked_val) > 1e-9:
                    mismatches.append(
                        f"  Kombi {i}: {metric_name}: ref={ref_val:.6f}, gechunkt={chunked_val:.6f}"
                    )

        assert not mismatches, (
            f"Metriken weichen ab ({len(mismatches)} Differenzen):\n"
            + "\n".join(mismatches[:20])
        )

    def test_correct_number_of_chunks_created(self) -> None:
        """Überprüft dass chunk_size=5 tatsächlich 5 Chunks erzeugt.

        20 Kombis, inner_size=4 (multiplier hat 4 Werte), step=max(1, 5//4)=1,
        → je 1 length-Wert pro Chunk → 5 Chunks (1 pro length-Wert).
        """
        from user_data.strategies.generic.indicator_factory import split_indicators_json_chunks

        indicators_json = _build_fastsma_indicators_json(
            length_values=[6, 8, 10, 12, 14],
            multiplier_values=[2, 3, 4, 5],
        )
        chunks = split_indicators_json_chunks(indicators_json, chunk_size=5)
        # 5 length-Werte x 4 multiplier = 20 Kombis
        # inner_size=4, step=max(1, 5//4)=max(1,1)=1 → 5 Chunks (je 1 length-Wert)
        assert len(chunks) == 5, f"Erwarte 5 Chunks, erhalten {len(chunks)}"
        # Jeder Chunk hat genau 1 length-Wert und alle 4 multiplier-Werte
        for chunk in chunks:
            assert len(chunk['fast_sma']['length']) == 1
            assert chunk['fast_sma']['multiplier'] == [2, 3, 4, 5]

    def test_single_combo_path_unaffected(self) -> None:
        """Single-Combo-Pfad (1 Kombination): kein Chunking, Metriken korrekt.

        Lücke 2 (Punkt e): n_combinations==1 läuft nicht durch Chunking-Pfad.
        """
        import vectorbtpro as vbt
        from user_data.strategies.generic.spec_runner import run_spec_strategy

        ohlc_data = _make_synthetic_ohlc_data(n=300, seed=99)
        # Genau 1 Kombination (Skalare statt Listen)
        indicators_json = {
            'fast_sma': {
                'indicator': 'custom:dwsFastSMA',
                'tf': '4h',
                'enabled': True,
                'source': 'close',
                'length': [10],          # Single-Wert-Liste → 1 Kombi
                'multiplier': [2],
            }
        }
        backtest_config = _build_fastsma_backtest_config(chunk_size=5)
        rules_json = _build_fastsma_rules_json()

        result = run_spec_strategy(
            ohlc_data=ohlc_data,
            indicators_json=indicators_json,
            backtest_config_json=backtest_config,
            rules_json=rules_json,
        )

        # Single-Combo muss 'portfolios' zurückgeben, NICHT 'metrics_table'
        assert 'portfolios' in result, (
            "Single-Combo muss 'portfolios' zurückgeben (kein Chunking-Pfad)"
        )
        assert 'metrics_table' not in result, (
            "Single-Combo darf 'metrics_table' NICHT zurückgeben"
        )

        pf = result['portfolios']
        columns = pf.wrapper.columns
        assert len(columns) == 1, f"Erwarte 1 Spalte, erhalten {len(columns)}"

    def test_native_path_chunked_no_crash(self) -> None:
        """Nativer Pfad (State-Exits + Multi-Combo): gechunkter Lauf crasht nicht.

        GEÄNDERT: Ticket 47 Bugfix — der native Pfad verarbeitet Multi-Combo direkt.
        4 Kombis bei chunk_size=2 → 2 Multi-Combo-Sub-Grid-Chunks à 2 Kombis. Die
        metrics_table enthält 4 Einträge (alle Kombis), columns trägt den vollen
        Spalten-MultiIndex.

        Dieser Test verifiziert:
          1. kein Crash beim gechunkten Lauf mit State-Exit und Multi-Combo
          2. metrics_table hat 4 Einträge (4 Kombis)
          3. jeder Eintrag enthält die erwarteten Metrik-Keys
        """
        from user_data.strategies.generic.spec_runner import run_spec_strategy

        # State-basierter Exit: nativer Pfad; Multi-Combo-Indikatoren → Single-Combo-Split
        rules_json_native = {
            'entry': {
                'blocks': [
                    {'conditions': [
                        {'lhs': 'close', 'op': '>', 'rhs': 'indicator:fast_sma:result'},
                    ]},
                ],
            },
            'exit': {
                'blocks': [
                    {'conditions': [
                        # State-Ref: nativer Pfad
                        {'lhs': 'since_entry', 'op': '>=', 'rhs': 10.0},
                    ]},
                ],
            },
        }

        # 4 length x 1 multiplier = 4 Kombis
        # GEÄNDERT: Ticket 47 Phase 2 — chunk_size spielt keine Rolle mehr für die
        # Anzahl der Chunks; Multi-Combo erzwingt immer Single-Combo (4 Chunks).
        length_vals = [8, 10, 12, 14]
        multiplier_vals = [2]

        ohlc_data = _make_synthetic_ohlc_data(n=500, seed=42)
        indicators_json = _build_fastsma_indicators_json(
            length_values=length_vals,
            multiplier_values=multiplier_vals,
        )
        backtest_config = _build_fastsma_backtest_config(chunk_size=2)

        # Muss ohne ValueError crashen
        result = run_spec_strategy(
            ohlc_data=ohlc_data,
            indicators_json=indicators_json,
            backtest_config_json=backtest_config,
            rules_json=rules_json_native,
        )

        # Multi-Combo gibt immer metrics_table zurück
        assert 'metrics_table' in result, (
            "Nativer Pfad gechunkt: Ergebnis enthält kein 'metrics_table'"
        )
        metrics_table = result['metrics_table']
        columns = result['columns']

        # 4 Kombis → 4 Single-Combo-Chunks → 4 Einträge in metrics_table
        assert len(metrics_table) == 4, (
            f"Erwartet 4 Metriken (4 Single-Combo-Chunks), "
            f"bekommen: {len(metrics_table)}"
        )
        assert len(columns) == 4, (
            f"Erwartet 4 Spalten im kombinierten Index, bekommen: {len(columns)}"
        )

        # Jeder Eintrag muss die Kern-Metrik-Keys enthalten
        _EXPECTED_KEYS = {
            'total_return_pct', 'win_rate_pct', 'profit_factor',
            'total_trades', 'max_drawdown_pct', 'sharpe_ratio',
        }
        for i, row in enumerate(metrics_table):
            missing = _EXPECTED_KEYS - set(row.keys())
            assert not missing, (
                f"Metrik-Eintrag {i} fehlen Keys: {missing}"
            )

    def test_chunked_matches_unchunked_size1_chunks(self) -> None:
        """Multi-Combo-Chunking liefert bit-genaue Metriken — inkl. DSR.

        GEÄNDERT: Ticket 47 Bugfix — der native Pfad verarbeitet Multi-Combo direkt.
        chunk_size=9999 (>= 3 Kombis) → ein Multi-Combo-Portfolio; chunk_size=2 → zwei
        Multi-Combo-Sub-Grid-Chunks. DSR wird global korrekt nach Konkatenation berechnet.

        Grid: length=[6, 8, 10] (outer=3), multiplier=[2] (inner=1) → 3 Kombis.
        Positionsbasierter Vergleich (kein Key-Mapping ohne MultiIndex).
        """
        import math
        from user_data.strategies.generic.spec_runner import run_spec_strategy
        from user_data.utils.database.repository import _extract_partial_metrics

        ohlc_data = _make_synthetic_ohlc_data(n=500, seed=42)
        # length=[6,8,10] (outer=3), multiplier=[2] (inner=1) → 3 Kombis gesamt
        indicators_json = _build_fastsma_indicators_json(
            length_values=[6, 8, 10],
            multiplier_values=[2],
        )
        rules_json = _build_fastsma_rules_json()

        def _run(chunk_size: int) -> list:
            """Hilfsfunktion: Lauf → Metriken-Liste (positionsbasiert).

            Normalisiert beide Rückgabeformen (Multi-Combo-'portfolios' oder
            gechunkte 'metrics_table') auf eine Metriken-Liste.
            """
            config = _build_fastsma_backtest_config(chunk_size=chunk_size)
            result = run_spec_strategy(
                ohlc_data=ohlc_data,
                indicators_json=indicators_json,
                backtest_config_json=config,
                rules_json=rules_json,
            )
            if 'metrics_table' in result:
                metrics_list = result['metrics_table']
            else:
                pf = result['portfolios']
                metrics_list = _extract_partial_metrics(pf, pf.wrapper.columns)
            return [
                {k: v for k, v in m.items() if k != 'metrics_level'}
                for m in metrics_list
            ]

        # Beide Läufe → 3 Kombis (Multi-Combo direkt bzw. gechunkt)
        unchunked = _run(chunk_size=9999)
        chunked = _run(chunk_size=2)

        # Gleiche Anzahl
        assert len(unchunked) == 3, f"Erwarte 3 Kombis (ungechunkt), bekommen {len(unchunked)}"
        assert len(chunked) == 3, f"Erwarte 3 Kombis (gechunkt), bekommen {len(chunked)}"

        # Positionsbasierter Metriken-Vergleich (bit-genau)
        mismatches = []
        for i, (ref, chk) in enumerate(zip(unchunked, chunked)):
            for metric_name, ref_val in ref.items():
                chk_val = chk.get(metric_name)
                if ref_val is None and chk_val is None:
                    continue
                if ref_val is None or chk_val is None:
                    mismatches.append(
                        f"  Kombi {i}: {metric_name}: ref={ref_val}, gechunkt={chk_val}"
                    )
                    continue
                if math.isnan(ref_val) and math.isnan(chk_val):
                    continue
                if abs(ref_val - chk_val) > 1e-9:
                    mismatches.append(
                        f"  Kombi {i}: {metric_name}: ref={ref_val:.6f}, gechunkt={chk_val:.6f}"
                    )

        assert not mismatches, (
            f"Metriken weichen ab ({len(mismatches)} Differenzen):\n"
            + "\n".join(mismatches[:30])
        )

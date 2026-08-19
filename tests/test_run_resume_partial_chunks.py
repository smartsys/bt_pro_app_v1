"""Teilergebnisse gechunkter Läufe sichern und fortsetzen (Ticket 71).

Zwei Ebenen:

* **Spec-Runner** — gibt jeden fertig gerechneten Chunk sofort an die Senke ab und
  überspringt beim Fortsetzen die bereits gespeicherten Chunks. Gefahren wird mit
  echtem Backtest auf synthetischen Kursen (Muster aus `test_combo_batching.py`),
  ohne Mock für die Rechenlogik.
* **Persistenz** — ein chunkweise gespeicherter Lauf ergibt denselben Datenbestand
  wie derselbe Lauf in einem Stück, inklusive der rasterweit gerechneten Deflated
  Sharpe Ratio, und wiederholtes Speichern desselben Chunks erzeugt keine Dubletten.
"""

import math

import pandas as pd
import pytest
from sqlalchemy import text

from user_data.utils.metrics.metric_sets import ALL_METRIC_FIELDS


# ---------------------------------------------------------------------------
# Ebene 1: Spec-Runner mit Chunk-Senke
# ---------------------------------------------------------------------------

def _synthetic_ohlc(n: int = 400, seed: int = 7):
    """Minimaler ohlc_data-Wrapper mit synthetischen OHLC-Reihen."""
    import numpy as np

    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0, 0.01, size=n)
    close = 100.0 * np.exp(np.cumsum(returns))
    noise = rng.uniform(0.001, 0.005, size=n)
    high = close * (1 + noise)
    low = close * (1 - noise)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = rng.uniform(1000, 10000, size=n)
    idx = pd.date_range('2020-01-01', periods=n, freq='4h', tz='UTC')
    df = pd.DataFrame(
        {'Open': open_, 'High': high, 'Low': low, 'Close': close, 'Volume': volume},
        index=idx,
    )

    class _OhlcWrapper:
        """Reicht die Spalten über .get(key) heraus."""

        def get(self, key: str):
            return df[key]

    return _OhlcWrapper()


def _indicators_json(length_values: list, multiplier_values: list) -> dict:
    """Indikator-Spec mit zwei variierenden Achsen."""
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


def _backtest_config(chunk_size: int) -> dict:
    """Minimale Backtest-Config mit steuerbarer Chunk-Größe."""
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
        },
    }


def _rules_json() -> dict:
    """Einfache Entry-/Exit-Regeln über den Indikator."""
    return {
        'entry': {'blocks': [{'conditions': [
            {'lhs': 'close', 'op': '>', 'rhs': 'indicator:fast_sma:result'},
        ]}]},
        'exit': {'blocks': [{'conditions': [
            {'lhs': 'close', 'op': '<', 'rhs': 'indicator:fast_sma:result'},
        ]}]},
    }


def _run_with_sink(chunk_size: int, completed_chunks: int = 0) -> tuple:
    """Führt einen gechunkten Lauf mit Senke aus.

    Args:
        chunk_size: Maximale Kombi-Zahl je Chunk.
        completed_chunks: Zahl der zu überspringenden Chunks.

    Returns:
        Tupel (Ergebnis-Dict, aufgezeichnete Senken-Aufrufe).
    """
    from user_data.strategies.generic.spec_runner import run_spec_strategy

    seen: list[dict] = []

    def _sink(chunk_index, metrics_table, columns, ann_factor) -> None:
        """Zeichnet den abgegebenen Chunk auf, ohne ihn zu speichern."""
        seen.append({
            'chunk_index': chunk_index,
            'n': len(columns),
            'columns': list(columns),
            'metrics': list(metrics_table),
            'ann_factor': ann_factor,
        })

    result = run_spec_strategy(
        ohlc_data=_synthetic_ohlc(),
        indicators_json=_indicators_json([6, 8, 10, 12], [2, 3, 4, 5]),
        backtest_config_json=_backtest_config(chunk_size),
        rules_json=_rules_json(),
        chunk_sink=_sink,
        completed_chunks=completed_chunks,
    )
    return result, seen


def test_every_chunk_reaches_the_sink_instead_of_being_collected() -> None:
    """Mit Senke gibt der Runner jeden Chunk ab und sammelt nichts mehr."""
    result, seen = _run_with_sink(chunk_size=4)

    assert len(seen) > 1, 'Testaufbau verfehlt: es entstand nur ein Chunk'
    assert [c['chunk_index'] for c in seen] == list(range(len(seen)))
    assert sum(c['n'] for c in seen) == 16
    assert result['chunks_saved'] == 16
    assert 'metrics_table' not in result, (
        'Mit Senke darf der Runner die Kennzahlen nicht zusätzlich zurückgeben'
    )
    assert result['ann_factor'] is not None


def test_completed_chunks_skips_the_already_saved_chunks() -> None:
    """Ein fortgesetzter Lauf rechnet die gespeicherten Chunks nicht erneut."""
    full, seen_full = _run_with_sink(chunk_size=4)
    n_chunks = len(seen_full)
    skip = n_chunks - 1

    resumed, seen_resumed = _run_with_sink(chunk_size=4, completed_chunks=skip)

    assert [c['chunk_index'] for c in seen_resumed] == list(range(skip, n_chunks))
    assert resumed['chunks_saved'] == sum(c['n'] for c in seen_full[skip:])
    assert full['chunks_saved'] - resumed['chunks_saved'] == sum(
        c['n'] for c in seen_full[:skip]
    )


def test_resumed_chunks_carry_the_same_values_as_the_uninterrupted_run() -> None:
    """Die übersprungenen Chunks ändern nichts an den Werten der gerechneten."""
    full, seen_full = _run_with_sink(chunk_size=4)
    skip = len(seen_full) - 1
    _resumed, seen_resumed = _run_with_sink(chunk_size=4, completed_chunks=skip)

    reference = seen_full[skip:]
    assert len(reference) == len(seen_resumed)
    for ref_chunk, new_chunk in zip(reference, seen_resumed):
        assert ref_chunk['columns'] == new_chunk['columns']
        for ref_row, new_row in zip(ref_chunk['metrics'], new_chunk['metrics']):
            for field, ref_val in ref_row.items():
                new_val = new_row.get(field)
                if isinstance(ref_val, float) and isinstance(new_val, float):
                    if math.isnan(ref_val) and math.isnan(new_val):
                        continue
                    assert abs(ref_val - new_val) < 1e-12, field
                else:
                    assert ref_val == new_val, field


def test_skipping_chunks_without_a_sink_is_rejected() -> None:
    """Überspringen ohne Senke wäre stiller Datenverlust und bricht ab."""
    from user_data.strategies.generic.spec_runner import run_spec_strategy

    with pytest.raises(ValueError, match='completed_chunks'):
        run_spec_strategy(
            ohlc_data=_synthetic_ohlc(),
            indicators_json=_indicators_json([6, 8, 10, 12], [2, 3, 4, 5]),
            backtest_config_json=_backtest_config(4),
            rules_json=_rules_json(),
            completed_chunks=1,
        )


# ---------------------------------------------------------------------------
# Ebene 2: Persistenz — chunkweise gespeichert gegen in einem Stück gespeichert
# ---------------------------------------------------------------------------

_ANN_FACTOR = 2190.0
_N_COMBOS = 12
_CHUNK_LEN = 4


def _columns(start: int, stop: int) -> pd.MultiIndex:
    """Spalten-Index für die Kombinationen [start, stop)."""
    return pd.MultiIndex.from_tuples(
        [(3 + i, 2.0 + i) for i in range(start, stop)],
        names=['fast_sma_length', 'fast_sma_multiplier'],
    )


def _metrics_rows(start: int, stop: int) -> list:
    """Kennzahl-Dicts für die Kombinationen [start, stop).

    Nur die Felder, die die Deflated Sharpe Ratio braucht, tragen streuende Werte —
    die übrigen bleiben leer (NULL), was der Persistenz-Semantik entspricht.
    """
    rows = []
    for i in range(start, stop):
        rows.append({
            'sharpe_ratio': 0.5 + 0.1 * i,
            'skew': -0.2 + 0.05 * i,
            'kurtosis': 3.0 + 0.1 * i,
            'bar_count': 1000 + i,
            'total_return_pct': 10.0 + i,
        })
    return rows


def _insert_run(session, run_id: int) -> None:
    """Legt einen minimalen backtest_runs-Datensatz an."""
    session.execute(text(
        "INSERT INTO backtest_runs (id, strategy_family, strategy_name, symbol, exchange, "
        "timeframe, start_date, end_date, backtest_config_json, indicators_config_json, "
        "n_combinations, status, completed_chunks, created_at) "
        "VALUES (:id, 'test', 'v1', 'FETUSDT', 'binance', '4h', '2022-01-01', '2024-01-01', "
        "'{}', '{}', :n, 'running', 0, NOW())"
    ), {'id': run_id, 'n': _N_COMBOS})


@pytest.fixture()
def repo_against_test_db(session, monkeypatch):
    """Verdrahtet das Repository mit der Test-DB."""
    import user_data.utils.database.repository as repo

    monkeypatch.setattr(repo, 'get_engine', lambda: session.get_bind())
    yield session


# Die Deflated Sharpe Ratio steht bewusst NICHT in ALL_METRIC_FIELDS: sie ist
# rasterweit und entsteht erst im Nachlauf. Genau sie muss der Vergleich aber
# mitnehmen — sie ist die Kennzahl, die ein fortgesetzter Lauf verfehlen könnte.
_COMPARED_FIELDS = list(ALL_METRIC_FIELDS) + ['deflated_sharpe_ratio']


def _read_rows(session, run_id: int) -> list:
    """Liest alle Kennzahl-Spalten plus Parameter der Results, stabil sortiert."""
    columns = ', '.join(_COMPARED_FIELDS)
    return session.execute(text(
        f'SELECT actual_params_json, {columns} FROM backtest_results '
        f'WHERE run_id = :run_id ORDER BY actual_params_json::text'
    ), {'run_id': run_id}).fetchall()


def test_chunkwise_saving_yields_the_same_rows_as_saving_in_one_piece(
    repo_against_test_db,
) -> None:
    """Chunkweise gespeichert == in einem Stück gespeichert, DSR eingeschlossen."""
    from user_data.utils.database.repository import (
        finalize_backtest_run,
        save_result_chunk,
        save_strategy_results,
    )

    session = repo_against_test_db
    one_piece_run, chunked_run = 940001, 940002
    _insert_run(session, one_piece_run)
    _insert_run(session, chunked_run)
    session.commit()

    # a) In einem Stück
    save_strategy_results(
        run_id=one_piece_run,
        strategy_results={
            'metrics_table': _metrics_rows(0, _N_COMBOS),
            'columns': _columns(0, _N_COMBOS),
            'ann_factor': _ANN_FACTOR,
        },
    )

    # b) Chunkweise, wie es der Lauf mit Senke tut
    for chunk_index, start in enumerate(range(0, _N_COMBOS, _CHUNK_LEN)):
        stop = start + _CHUNK_LEN
        save_result_chunk(
            run_id=chunked_run,
            metrics_table=_metrics_rows(start, stop),
            columns=_columns(start, stop),
            chunk_index=chunk_index,
            ann_factor=_ANN_FACTOR,
        )
    finalize_backtest_run(chunked_run, _ANN_FACTOR)
    session.rollback()

    rows_one_piece = _read_rows(session, one_piece_run)
    rows_chunked = _read_rows(session, chunked_run)
    assert len(rows_one_piece) == _N_COMBOS
    assert len(rows_chunked) == _N_COMBOS

    for ref, new in zip(rows_one_piece, rows_chunked):
        assert ref.actual_params_json == new.actual_params_json
        for field in _COMPARED_FIELDS:
            ref_val, new_val = getattr(ref, field), getattr(new, field)
            if ref_val is None:
                assert new_val is None, field
            else:
                assert abs(float(ref_val) - float(new_val)) < 1e-12, field

    # Die rasterweite Kennzahl ist tatsächlich gefüllt — sonst prüfte der Vergleich
    # oben nur leere Felder gegen leere Felder.
    assert all(row.deflated_sharpe_ratio is not None for row in rows_chunked)

    runs = dict(session.execute(text(
        'SELECT id, n_combinations FROM backtest_runs WHERE id IN (:a, :b)'
    ), {'a': one_piece_run, 'b': chunked_run}).fetchall())
    assert runs[one_piece_run] == _N_COMBOS
    assert runs[chunked_run] == _N_COMBOS


def test_saving_a_chunk_twice_creates_no_duplicates(repo_against_test_db) -> None:
    """Ein nach dem Abbruch erneut gerechneter Chunk überschreibt statt zu doppeln."""
    from user_data.utils.database.repository import save_result_chunk

    session = repo_against_test_db
    run_id = 940003
    _insert_run(session, run_id)
    session.commit()

    for _ in range(2):
        save_result_chunk(
            run_id=run_id,
            metrics_table=_metrics_rows(0, _CHUNK_LEN),
            columns=_columns(0, _CHUNK_LEN),
            chunk_index=0,
            ann_factor=_ANN_FACTOR,
        )
    session.rollback()

    n_results = session.execute(text(
        'SELECT count(*) FROM backtest_results WHERE run_id = :r'
    ), {'r': run_id}).scalar()
    n_signatures = session.execute(text(
        'SELECT count(DISTINCT actual_params_json::text) FROM backtest_results '
        'WHERE run_id = :r'
    ), {'r': run_id}).scalar()
    n_params = session.execute(text(
        'SELECT count(*) FROM backtest_result_params p '
        'JOIN backtest_results r ON r.id = p.result_id WHERE r.run_id = :r'
    ), {'r': run_id}).scalar()

    assert n_results == _CHUNK_LEN
    assert n_signatures == _CHUNK_LEN
    assert n_params == _CHUNK_LEN * 2  # zwei Parameter je Kombination


def test_chunk_save_records_the_resume_point_and_the_annualisation_factor(
    repo_against_test_db,
) -> None:
    """Der Fortsetzungspunkt steht nach jedem Chunk am Lauf, der Faktor auch."""
    from user_data.utils.database.repository import (
        finalize_backtest_run,
        save_result_chunk,
    )

    session = repo_against_test_db
    run_id = 940004
    _insert_run(session, run_id)
    session.commit()

    save_result_chunk(
        run_id=run_id,
        metrics_table=_metrics_rows(0, _CHUNK_LEN),
        columns=_columns(0, _CHUNK_LEN),
        chunk_index=0,
        ann_factor=_ANN_FACTOR,
    )
    session.rollback()
    row = session.execute(text(
        'SELECT status, completed_chunks, ann_factor FROM backtest_runs WHERE id = :r'
    ), {'r': run_id}).fetchone()
    assert row.completed_chunks == 1
    assert float(row.ann_factor) == _ANN_FACTOR
    assert row.status == 'running', 'Ein Chunk darf den Lauf nicht abschließen'

    # Fortsetzen, bei dem kein Chunk mehr zu rechnen war: der Abschluss muss ohne
    # mitgegebenen Faktor auskommen und den gespeicherten benutzen.
    finalize_backtest_run(run_id, None)
    session.rollback()
    row = session.execute(text(
        'SELECT status, n_combinations, ann_factor FROM backtest_runs WHERE id = :r'
    ), {'r': run_id}).fetchone()
    assert row.status == 'completed'
    assert row.n_combinations == _CHUNK_LEN
    assert float(row.ann_factor) == _ANN_FACTOR
    dsr_filled = session.execute(text(
        'SELECT count(*) FROM backtest_results '
        'WHERE run_id = :r AND deflated_sharpe_ratio IS NOT NULL'
    ), {'r': run_id}).scalar()
    assert dsr_filled == _CHUNK_LEN

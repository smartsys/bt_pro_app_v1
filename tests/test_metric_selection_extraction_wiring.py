"""Tests, dass die aufgelöste Metrik-Auswahl tatsächlich bei `_extract_metrics` ankommt
(Ticket 68, Anforderung 2).

Die Auflösung selbst sitzt in `create_backtest_run` (siehe
test_metric_selection_run_creation.py) und schreibt das Ergebnis als
`backtest_config_json['metrics_resolved']`. Hier wird geprüft, dass die beiden
Konsumenten diesen Wert wirklich lesen:

- `save_strategy_results` (Einzel-/kleiner Multiparameterlauf, 'portfolios'-Pfad)
- `spec_runner._run_chunked` (großer Multiparameterlauf, 'metrics_table'-Pfad) — und
  zwar in JEDEM Chunk, nicht nur im ersten.

Reproduziert das Backtest-Setup aus test_combo_batching.py (dwsFastSMA + synthetische
OHLC), weil das der einzige Weg ist, ein echtes Portfolio ohne DB-Fixtures zu bekommen.
Läuft nur mit vectorbtpro (Windows-venv).
"""

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from user_data.utils.metrics.metric_sets import CORE_GROUPS, METRIC_GROUPS

_RUN_ID = 930101


def _make_synthetic_ohlc_data(n: int = 400, seed: int = 7):
    """Minimaler ohlc_data-Wrapper mit synthetischen OHLC-Daten (4h-Balken)."""
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
        def __init__(self, df_: pd.DataFrame) -> None:
            self._df = df_

        def get(self, key: str):
            return self._df[key]

    return _OhlcWrapper(df)


def _indicators_json(length_values: list, multiplier_values: list) -> dict:
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


def _rules_json() -> dict:
    return {
        'entry': {'blocks': [{'conditions': [
            {'lhs': 'close', 'op': '>', 'rhs': 'indicator:fast_sma:result'},
        ]}]},
        'exit': {'blocks': [{'conditions': [
            {'lhs': 'close', 'op': '<', 'rhs': 'indicator:fast_sma:result'},
        ]}]},
    }


def _backtest_config(chunk_size: int, metrics_resolved) -> dict:
    return {
        'start': '2020-01-01',
        'end': '2020-12-31',
        'timeframe': '4h',
        'chunk_size': chunk_size,
        # GEÄNDERT: Ticket 68 — so, wie create_backtest_run es persistiert: bereits
        # aufgelöste Gruppenmenge, kein 'metrics'-Rohwert mehr.
        'metrics_resolved': sorted(metrics_resolved),
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


def test_non_chunked_run_omits_deselected_groups_from_extracted_metrics():
    """Kleiner Lauf (kein Chunking): _extract_metrics bekommt 'metrics_resolved' aus
    backtest_config_json über run_spec_strategy -> save_strategy_results.
    """
    from user_data.strategies.generic.spec_runner import run_spec_strategy
    from user_data.utils.database.repository import _extract_metrics

    ohlc_data = _make_synthetic_ohlc_data(n=400, seed=7)
    indicators_json = _indicators_json([10, 14], [2, 3])  # 4 Kombis, kein Chunking
    backtest_config = _backtest_config(chunk_size=9999, metrics_resolved=CORE_GROUPS)
    rules_json = _rules_json()

    result = run_spec_strategy(
        ohlc_data=ohlc_data,
        indicators_json=indicators_json,
        backtest_config_json=backtest_config,
        rules_json=rules_json,
    )
    assert 'portfolios' in result, "4 Kombis bei chunk_size=9999 dürfen nicht chunken"

    pf = result['portfolios']
    metrics = _extract_metrics(
        pf, pf.wrapper.columns, backtest_config,
        groups=backtest_config.get('metrics_resolved'),
    )
    assert len(metrics) == 4
    for row in metrics:
        for field in METRIC_GROUPS['tail_risk']:
            assert field not in row, f'{field} sollte bei kern nicht extrahiert werden'
        assert 'sharpe_ratio' in row and row['sharpe_ratio'] is not None


@pytest.fixture()
def repo_against_test_db(session, monkeypatch):
    """Verdrahtet save_strategy_results mit der Test-DB (Muster aus
    test_result_metric_null_semantics.py) und legt einen minimalen Run an."""
    import user_data.utils.database.repository as repo

    session.execute(text(
        "INSERT INTO backtest_runs (id, strategy_family, strategy_name, symbol, exchange, "
        "timeframe, start_date, end_date, backtest_config_json, indicators_config_json, "
        "n_combinations, status, created_at) "
        "VALUES (:id, 'test', 'v1', 'FETUSDT', 'binance', '4h', '2020-01-01', '2020-12-31', "
        "'{}', '{}', 4, 'queued', NOW())"
    ), {'id': _RUN_ID})
    session.commit()
    monkeypatch.setattr(repo, 'get_engine', lambda: session.get_bind())
    yield session


def test_save_strategy_results_persists_null_for_groups_the_portfolios_path_skipped(
    repo_against_test_db,
):
    """Ende-zu-Ende über save_strategy_results: 'metrics_resolved' aus backtest_config_json
    entscheidet, welche Spalten NULL bleiben — auch im 'portfolios'-Pfad (nicht nur im
    bereits getesteten 'metrics_table'-Pfad).
    """
    from user_data.strategies.generic.spec_runner import run_spec_strategy
    from user_data.utils.database.repository import ALL_METRIC_FIELDS, save_strategy_results

    session = repo_against_test_db
    ohlc_data = _make_synthetic_ohlc_data(n=400, seed=7)
    indicators_json = _indicators_json([10, 14], [2, 3])  # 4 Kombis
    backtest_config = _backtest_config(chunk_size=9999, metrics_resolved=CORE_GROUPS)
    rules_json = _rules_json()

    result = run_spec_strategy(
        ohlc_data=ohlc_data,
        indicators_json=indicators_json,
        backtest_config_json=backtest_config,
        rules_json=rules_json,
    )

    save_strategy_results(
        run_id=_RUN_ID,
        strategy_results=result,
        backtest_config=backtest_config,
    )
    session.rollback()

    columns = ', '.join(ALL_METRIC_FIELDS)
    rows = session.execute(text(
        f'SELECT {columns} FROM backtest_results WHERE run_id = :run_id'
    ), {'run_id': _RUN_ID}).fetchall()
    assert len(rows) == 4
    for row in rows:
        for field in METRIC_GROUPS['tail_risk']:
            assert getattr(row, field) is None, f'{field} sollte NULL sein (kern)'
        assert row.sharpe_ratio is not None


def test_chunked_run_applies_the_resolved_groups_in_every_chunk():
    """Gechunkter Lauf (mehrere Chunks): jeder Chunk bekommt dieselbe aufgelöste
    Gruppenmenge — nicht nur der erste (Chunk-Erbschaft, Ticket 68 Anforderung 2/8).
    """
    from user_data.strategies.generic.indicator_factory import split_indicators_json_chunks
    from user_data.strategies.generic.spec_runner import run_spec_strategy

    ohlc_data = _make_synthetic_ohlc_data(n=400, seed=11)
    # 5 length x 4 multiplier = 20 Kombis
    indicators_json = _indicators_json([6, 8, 10, 12, 14], [2, 3, 4, 5])
    backtest_config = _backtest_config(chunk_size=5, metrics_resolved=CORE_GROUPS)
    rules_json = _rules_json()

    # Gegenprobe, dass der Lauf tatsächlich mehrfach chunkt (sonst testet dieser Test
    # nichts über Chunk-Erbschaft).
    chunks = split_indicators_json_chunks(indicators_json, chunk_size=5)
    assert len(chunks) > 1, 'Testaufbau muss mehrere Chunks erzeugen'

    result = run_spec_strategy(
        ohlc_data=ohlc_data,
        indicators_json=indicators_json,
        backtest_config_json=backtest_config,
        rules_json=rules_json,
    )
    assert 'metrics_table' in result
    metrics_table = result['metrics_table']
    assert len(metrics_table) == 20

    for row in metrics_table:
        for field in METRIC_GROUPS['tail_risk']:
            assert field not in row, (
                f'{field} in einem Chunk-Ergebnis — Auswahl wurde nicht vererbt'
            )
        assert 'sharpe_ratio' in row and row['sharpe_ratio'] is not None

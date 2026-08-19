"""Der Recompute füllt ein schmal gerechnetes Result wieder vollständig (Ticket 68).

Ein Lauf mit der Auswahl `kern` lässt die drei `tail_risk`-Spalten leer. Der
Recompute (`services/api/recompute.py`) ist der festgelegte Weg, einem Sieger-Result
nachträglich **alle** Kennzahlen zu geben: er rechnet immer voll, unabhängig von der
Auswahl des Laufs, weil er ohnehin nur eine einzige Kombination rechnet.

Geprüft wird beides, was daran tragen muss:

1. Die Aufrufform im Recompute engt die Gruppen nicht ein — ein `groups=`-Argument an
   dieser Stelle wäre der einzige Weg, wie die Auswahl des Laufs in den Recompute
   durchschlagen könnte.
2. Der Weg von einem `kern`-Result zurück zu vollen Kennzahlen: dieselbe
   Extraktionsform und dasselbe UPDATE, die der Recompute fährt, füllen die vorher
   leeren Spalten.

Nicht geprüft (bewusst): der Recompute als Ganzes. Er lädt OHLCV, Iteration und
Indikatoren aus der Datenbank und führt die Strategie aus — dafür bräuchte der Test
einen vollständigen Datenbestand, ohne dass er über die Kennzahl-Auswahl mehr aussagen
würde als die beiden Prüfungen hier.

Lauf im Test-Container (hat vectorbtpro und die PostgreSQL-Test-DB):
    docker compose -f docker-compose-local.yml run --rm test \
        python -m pytest tests/test_recompute_refills_narrow_metrics.py
"""

import inspect
import re

import numpy as np
import pandas as pd
import pytest
import vectorbtpro as vbt
from sqlalchemy import text

from services.api import recompute as recompute_module
from user_data.utils.database.models import BacktestResult
from user_data.utils.database.repository import _extract_metrics, save_strategy_results
from user_data.utils.metrics.metric_sets import (
    ALL_METRIC_FIELDS,
    METRIC_GROUPS,
    resolve_metric_groups,
)
from user_data.utils.metrics.trading_window import build_trading_window

_START = '2020-02-01'
_END = '2020-02-20'
_RUN_ID = 940001
_ANN_FACTOR = 2190.0


def _config() -> dict:
    """Minimale BacktestConfig mit Handelsfenster."""
    return {'start': _START, 'end': _END}


def _portfolio(n_columns: int = 2):
    """Portfolio mit geschlossenen Long- und Short-Trades über n Kombinationen.

    Mehrspaltig wie ein Multiparameterlauf; die Spalten unterscheiden sich über die
    Gebühren, damit jede Kombination eigene Kennzahlen bekommt.
    """
    idx = pd.date_range('2020-01-01', periods=1600, freq='1h', tz='UTC')
    rng = np.random.default_rng(23)
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0.0005, 0.01, len(idx))), index=idx)

    start, end = build_trading_window(_config())
    in_window = (idx >= start) & (idx <= end)
    last_in_window = int(np.max(np.flatnonzero(in_window)))

    long_entries = pd.Series(False, index=idx)
    long_exits = pd.Series(False, index=idx)
    short_entries = pd.Series(False, index=idx)
    short_exits = pd.Series(False, index=idx)
    entries = [
        i for i in range(len(idx))
        if in_window[i] and i % 40 == 0 and i + 20 <= last_in_window
    ]
    for n, pos in enumerate(entries):
        if n % 2 == 0:
            long_entries.iloc[pos] = True
            long_exits.iloc[pos + 20] = True
        else:
            short_entries.iloc[pos] = True
            short_exits.iloc[pos + 20] = True

    return vbt.PF.from_signals(
        close=close,
        open=close * 0.999, high=close * 1.004, low=close * 0.996,
        entries=long_entries, exits=long_exits,
        short_entries=short_entries, short_exits=short_exits,
        freq='1h', init_cash=100, size=100, size_type='value',
        fees=vbt.Param([0.0, 0.001][:n_columns]),
    )


def _insert_run(session) -> None:
    """Legt den minimalen backtest_runs-Datensatz für die Results an."""
    session.execute(text(
        "INSERT INTO backtest_runs (id, strategy_family, strategy_name, symbol, exchange, "
        "timeframe, start_date, end_date, backtest_config_json, indicators_config_json, "
        "n_combinations, status, created_at) "
        "VALUES (:id, 'test', 'v1', 'FETUSDT', 'binance', '4h', '2022-01-01', '2024-01-01', "
        "'{}', '{}', 2, 'queued', NOW())"
    ), {'id': _RUN_ID})


@pytest.fixture()
def repo_against_test_db(session, monkeypatch):
    """Verdrahtet das Repository mit der Test-DB und legt den Lauf an."""
    import user_data.utils.database.repository as repo

    _insert_run(session)
    session.commit()
    monkeypatch.setattr(repo, 'get_engine', lambda: session.get_bind())
    yield session


def test_recompute_extraction_is_never_narrowed_to_a_group_selection():
    """Der Recompute ruft `_extract_metrics` ohne `groups` auf — er rechnet immer voll.

    Ein `groups=`-Argument an dieser einen Aufrufstelle wäre der einzige Weg, wie die
    Auswahl eines Laufs in den Recompute durchschlagen könnte; die Prüfung liest den
    Aufruf deshalb direkt im Quelltext.
    """
    source = inspect.getsource(recompute_module.recompute_single_result)
    calls = re.findall(r'_extract_metrics\((.*?)\)\[', source, flags=re.S)
    assert len(calls) == 1, f'Erwarte genau einen _extract_metrics-Aufruf, fand {len(calls)}'
    assert 'groups' not in calls[0], (
        'Der Recompute engt die Kennzahl-Gruppen ein — er muss immer voll rechnen '
        f'(gefundener Aufruf: _extract_metrics({calls[0]}))'
    )


def test_full_extraction_refills_the_empty_columns_of_a_core_result(repo_against_test_db):
    """Ein `kern`-Result bekommt über den Recompute-Weg alle 46 Kennzahlen zurück.

    Erst wie ein `kern`-Lauf speichern (die drei `tail_risk`-Spalten bleiben leer),
    dann mit derselben Extraktionsform und demselben UPDATE nachrechnen, die der
    Recompute fährt.
    """
    session = repo_against_test_db
    pf = _portfolio()
    columns = pf.wrapper.columns

    core_metrics = _extract_metrics(
        pf, columns, _config(), groups=resolve_metric_groups('kern')
    )
    save_strategy_results(
        run_id=_RUN_ID,
        strategy_results={
            'metrics_table': core_metrics,
            'columns': columns,
            'ann_factor': _ANN_FACTOR,
        },
    )
    session.rollback()

    rows = session.execute(text(
        'SELECT id, tail_ratio FROM backtest_results WHERE run_id = :run_id ORDER BY id'
    ), {'run_id': _RUN_ID}).fetchall()
    assert len(rows) == len(columns)
    assert all(row.tail_ratio is None for row in rows)

    # Aufrufform des Recompute: eine Kombination, keine Gruppen-Einengung.
    pf_single = _portfolio(n_columns=1)
    all_metrics = _extract_metrics(
        pf_single, pf_single.wrapper.columns, _config()
    )[0]
    assert set(all_metrics) == set(ALL_METRIC_FIELDS)

    result_id = rows[0].id
    engine = session.get_bind()
    with engine.begin() as conn:
        conn.execute(
            BacktestResult.__table__.update()
            .where(BacktestResult.id == result_id)
            .values(**all_metrics, spec_runner_version='test')
        )
    session.rollback()

    refilled = session.execute(text(
        f"SELECT {', '.join(ALL_METRIC_FIELDS)} FROM backtest_results WHERE id = :id"
    ), {'id': result_id}).fetchone()
    for field in ALL_METRIC_FIELDS:
        assert getattr(refilled, field) is not None, f'{field} ist nach dem Recompute leer'

    # Die Nachbar-Kombination bleibt unangetastet — der Recompute füllt genau ein Result.
    untouched = session.execute(text(
        f"SELECT {', '.join(METRIC_GROUPS['tail_risk'])} FROM backtest_results "
        f"WHERE id = :id"
    ), {'id': rows[1].id}).fetchone()
    for field in METRIC_GROUPS['tail_risk']:
        assert getattr(untouched, field) is None, f'{field} unerwartet gefüllt'

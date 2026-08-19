"""Tests für api_monitor._active_testset_runs — Karteileichen-Filter.

Ticket 62: GET /api/monitor/overview führte fünf Testset-Läufe dauerhaft als
aktive Jobs, obwohl kein Backtest-Run mehr dahinterstand (weder in der DB noch
in Redis). _active_testset_runs verlangt seitdem zusätzlich zum Status in
ACTIVE_STATES, dass mindestens ein zugehöriger BacktestRun existiert —
start_testset_run legt die BacktestRuns synchron an, bevor es sie enqueued,
ein wirklich aktiver Lauf hat also immer mindestens einen.

Tests laufen gegen die echte PostgreSQL-Test-DB (session-Fixture aus
tests/conftest.py, truncate-basierte Isolation je Test).
"""

from datetime import datetime

from user_data.utils.database.models import BacktestRun, TestSetRun
from services.api.routes.api_monitor import _active_testset_runs


def _make_testset_run(session, status: str, n_runs_total: int = 1) -> TestSetRun:
    """Legt einen minimalen Testset-Lauf mit gegebenem Status an."""
    run = TestSetRun(
        testset_id=1,
        strategy_family='test_family',
        strategy_name='test_strategy',
        indicators_config_json={},
        status=status,
        n_runs_total=n_runs_total,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _make_backtest_run(session, testset_run_id: int) -> BacktestRun:
    """Legt einen minimalen Backtest-Run an, der auf den Testset-Lauf zeigt."""
    run = BacktestRun(
        strategy_family='test_family',
        strategy_name='test_strategy',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        backtest_config_json={},
        indicators_config_json={},
        n_combinations=1,
        status='queued',
        testset_run_id=testset_run_id,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def test_queued_testset_run_with_backtest_run_appears(session):
    """Ein 'queued'-Lauf mit echtem BacktestRun gilt als aktiv."""
    testset_run = _make_testset_run(session, status='queued')
    _make_backtest_run(session, testset_run.id)

    ids = [item['id'] for item in _active_testset_runs(session)]

    assert testset_run.id in ids


def test_running_testset_run_with_backtest_run_appears(session):
    """Ein 'running'-Lauf mit echtem BacktestRun gilt als aktiv."""
    testset_run = _make_testset_run(session, status='running')
    _make_backtest_run(session, testset_run.id)

    ids = [item['id'] for item in _active_testset_runs(session)]

    assert testset_run.id in ids


def test_queued_testset_run_without_backtest_runs_is_excluded(session):
    """Karteileichen-Regel: 'queued' ohne jeden BacktestRun gilt nicht als aktiv."""
    testset_run = _make_testset_run(session, status='queued')

    ids = [item['id'] for item in _active_testset_runs(session)]

    assert testset_run.id not in ids


def test_completed_testset_run_with_backtest_runs_is_excluded(session):
    """ACTIVE_STATES greift weiterhin: 'completed' erscheint nicht, auch mit BacktestRuns."""
    testset_run = _make_testset_run(session, status='completed')
    _make_backtest_run(session, testset_run.id)

    ids = [item['id'] for item in _active_testset_runs(session)]

    assert testset_run.id not in ids

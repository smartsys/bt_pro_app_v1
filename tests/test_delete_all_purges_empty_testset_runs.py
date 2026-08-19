"""Test für den 'Alle löschen'-Job: leer gewordene Testset-Läufe verschwinden mit.

Ticket 61: _delete_all_non_favorites leert die Run-/Result-Tabellen. Danach darf kein
Testset-Lauf ohne die Backtest-Runs zurückbleiben, aus denen er bestand.

Läuft gegen die PostgreSQL-Test-DB (Fixtures aus tests/conftest.py). rq ist eine
Worker-Abhängigkeit und im venv nicht installiert — get_current_job wird gestubbt.
"""

import sys
import types
from datetime import datetime
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from services.api import worker_tasks as wt
from user_data.utils.database.models import (
    BacktestConfig,
    BacktestResult,
    BacktestRun,
    TestSet,
    TestSetRun,
)


def _stub_rq() -> None:
    """Registriert ein Minimal-rq-Modul, damit der Lazy-Import im Job trägt."""
    if 'rq' not in sys.modules:
        rq_stub = types.ModuleType('rq')
        rq_stub.get_current_job = lambda: None
        sys.modules['rq'] = rq_stub
    elif not hasattr(sys.modules['rq'], 'get_current_job'):
        sys.modules['rq'].get_current_job = lambda: None


def test_delete_all_removes_testset_run_without_backtest_runs(session, db_engine):
    """Nach dem 'Alle löschen'-Job existiert der leer gewordene Testset-Lauf nicht mehr."""
    _stub_rq()

    # testset_runs.testset_id trägt einen Fremdschlüssel — das TestSet muss existieren
    config = BacktestConfig(
        name='T61-DeleteAll-Config',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start='2024-01-01',
        end='2024-12-31',
        ohlc_start='2023-12-01',
        ohlc_end='2025-01-01',
    )
    session.add(config)
    session.commit()

    testset = TestSet(
        name='T61-DeleteAll-TestSet',
        backtest_config_ids_json=[config.id],
        leaderboard_enabled=False,
    )
    session.add(testset)
    session.commit()

    testset_run = TestSetRun(
        testset_id=testset.id,
        strategy_family='test_family',
        strategy_name='test_strategy',
        indicators_config_json={},
        status='completed',
        n_runs_total=1,
    )
    session.add(testset_run)
    session.commit()
    testset_run_id = testset_run.id

    backtest_run = BacktestRun(
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
        status='completed',
        testset_run_id=testset_run_id,
    )
    session.add(backtest_run)
    session.commit()
    backtest_run_id = backtest_run.id

    session.add(BacktestResult(
        run_id=backtest_run_id,
        params_hash='t61hash',
        actual_params_json={},
        total_return_pct=1.0,
    ))
    session.commit()

    Session = sessionmaker(bind=db_engine)
    with patch.object(wt, 'get_session', side_effect=lambda: Session()):
        wt._delete_all_non_favorites()

    check_session = Session()
    assert check_session.query(BacktestRun).filter(BacktestRun.id == backtest_run_id).first() is None
    assert check_session.query(TestSetRun).filter(TestSetRun.id == testset_run_id).first() is None
    check_session.close()

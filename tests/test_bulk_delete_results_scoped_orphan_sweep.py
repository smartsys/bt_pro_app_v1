"""Regressionstests für den eingegrenzten Orphan-Sweep in bulk_delete_results (Ticket 75).

Fundfall: der Orphan-Sweep in POST /results/bulk-delete lief bisher global über die
gesamte backtest_runs-Tabelle (`DELETE ... WHERE id NOT IN (SELECT DISTINCT run_id
FROM backtest_results)`). Jeder result-lose Run der gesamten DB — nicht nur die von
der Operation betroffenen — wurde dabei mitgerissen. Result-lose Runs sind aber ein
legitimer Zustand (failed-Läufe, Läufe mit gezielt geleerten Results).

Die Fixtures brauchen die echte PostgreSQL-Test-DB (session/db_engine aus
tests/conftest.py), weil die Route rohes SQL mit `ANY(:run_ids)` und `RETURNING`
ausführt — beides nicht SQLite-kompatibel.
"""

import json
import sys
import types
from datetime import datetime

# rq-Familie stubben (nur im Worker-Container installiert), damit api_backtest importierbar ist
for _m in ('rq', 'rq.job', 'rq.registry', 'rq.command'):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)
sys.modules['rq'].Queue = object
sys.modules['rq.job'].Job = object
sys.modules['rq.registry'].StartedJobRegistry = object
sys.modules['rq.command'].send_stop_job_command = lambda *a, **k: None

from sqlalchemy.orm import sessionmaker  # noqa: E402

from services.api.routes import api_backtest as api_backtest_module  # noqa: E402
from user_data.utils.database.models import (  # noqa: E402
    BacktestResult,
    BacktestRun,
    TestSet,
    TestSetRun,
)

_BACKTEST_CONFIG = {
    'strategy_family': 'test_family',
    'strategy_name': 'test_strategy',
    'symbols': ['BTCUSDT'],
    'exchange': 'binance',
    'timeframe': '4h',
    'start': '2024-01-01',
    'end': '2024-12-31',
}


def _decode(resp) -> dict:
    """JSONResponse-Body als Dict."""
    return json.loads(resp.body)


def _make_run(session, testset_run_id=None) -> int:
    """Minimalen BacktestRun in die Test-DB schreiben, gibt die id zurück."""
    run = BacktestRun(
        strategy_family='test_family',
        strategy_name='test_strategy',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        backtest_config_json=_BACKTEST_CONFIG,
        indicators_config_json={},
        n_combinations=1,
        status='completed',
        testset_run_id=testset_run_id,
    )
    session.add(run)
    session.commit()
    return run.id


def _make_result(session, run_id: int) -> int:
    """Minimales BacktestResult in die Test-DB schreiben, gibt die id zurück."""
    result = BacktestResult(
        run_id=run_id,
        params_hash=f'hash-{run_id}',
        actual_params_json={},
        total_return_pct=1.0,
    )
    session.add(result)
    session.commit()
    return result.id


def _make_testset_run(session) -> int:
    """Testset + zugehörigen TestSetRun anlegen, gibt die testset_run_id zurück."""
    testset = TestSet(
        name=f'T75-TestSet-{datetime.now().timestamp()}',
        backtest_config_ids_json=[],
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
    return testset_run.id


def test_bulk_delete_results_leaves_foreign_result_less_run_untouched(session, db_engine, monkeypatch):
    """Fundfall: ein fremder, result-loser Run überlebt eine Bulk-Löschung fremder Results.

    run_foreign hat nie Results (z.B. failed-Lauf) und ist an der Löschoperation nicht
    beteiligt. run_own besitzt genau ein Result, das gelöscht wird. Vor der Umsetzung
    hätte der globale Orphan-Sweep run_foreign trotzdem entfernt.
    """
    Session = sessionmaker(bind=db_engine)
    s = Session()
    run_foreign_id = _make_run(s)
    run_own_id = _make_run(s)
    own_result_id = _make_result(s, run_own_id)
    s.close()

    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())

    resp = api_backtest_module.bulk_delete_results({'ids': [own_result_id]})
    body = _decode(resp)

    check = Session()
    assert check.query(BacktestRun).filter(BacktestRun.id == run_foreign_id).first() is not None
    check.close()
    assert run_foreign_id not in body['deleted_run_ids']


def test_bulk_delete_results_removes_own_orphaned_run_and_lists_it(session, db_engine, monkeypatch):
    """Ein eigener Run ohne verbleibende Results wird entfernt und in deleted_run_ids benannt."""
    Session = sessionmaker(bind=db_engine)
    s = Session()
    run_id = _make_run(s)
    result_id = _make_result(s, run_id)
    s.close()

    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())

    resp = api_backtest_module.bulk_delete_results({'ids': [result_id]})
    body = _decode(resp)

    assert body['deleted_runs'] == 1
    assert body['deleted_run_ids'] == [run_id]

    check = Session()
    assert check.query(BacktestRun).filter(BacktestRun.id == run_id).first() is None
    check.close()


def test_bulk_delete_results_purges_only_the_testset_run_that_actually_emptied(session, db_engine, monkeypatch):
    """purge_empty_testset_runs läuft nur über die tatsächlich betroffenen testset_run_ids.

    testset_run_untouched hängt an run_foreign, der außerhalb der Operation liegt und
    bestehen bleibt — sein Testset-Lauf darf also nicht verschwinden. testset_run_emptied
    hängt an run_own, dessen letztes Result gelöscht wird — der Run UND sein Testset-Lauf
    werden entfernt.
    """
    Session = sessionmaker(bind=db_engine)
    s = Session()
    testset_run_untouched_id = _make_testset_run(s)
    run_foreign_id = _make_run(s, testset_run_id=testset_run_untouched_id)

    testset_run_emptied_id = _make_testset_run(s)
    run_own_id = _make_run(s, testset_run_id=testset_run_emptied_id)
    own_result_id = _make_result(s, run_own_id)
    s.close()

    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())

    api_backtest_module.bulk_delete_results({'ids': [own_result_id]})

    check = Session()
    assert check.query(TestSetRun).filter(TestSetRun.id == testset_run_untouched_id).first() is not None
    assert check.query(BacktestRun).filter(BacktestRun.id == run_foreign_id).first() is not None
    assert check.query(TestSetRun).filter(TestSetRun.id == testset_run_emptied_id).first() is None
    check.close()

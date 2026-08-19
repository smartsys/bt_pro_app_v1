"""Tests für DELETE /api/testsets/{id} — Rückfrage statt Sperre.

Ein TestSet ist nur die Zusammenstellung von Backtest-Configs. Es zu löschen darf
die damit erzeugten Daten nicht mitnehmen, soll aber auch nicht unbemerkt passieren.

Erwartetes Verhalten:
  - Hängen Testset-Läufe am TestSet, antwortet der Endpunkt ohne ``force`` mit
    HTTP 409 und nennt die Anzahl der Läufe und der daran hängenden Backtest-Runs.
    Gelöscht wird dabei nichts.
  - Mit ``force=true`` verschwindet ausschließlich die TestSet-Zeile. Testset-Läufe,
    Backtest-Runs und Results bleiben unverändert bestehen.
  - Ohne anhängende Läufe wird direkt gelöscht, ohne Rückfrage.

Tests laufen gegen die echte PostgreSQL-Test-DB (VBT_TEST_DATABASE_URL, Port 5562).
db_engine kommt aus tests/conftest.py.
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from services.api.routes import api_testsets as api_testsets_module
from user_data.utils.database.models import BacktestConfig, BacktestRun, TestSet, TestSetRun


def _make_testset(session, name: str) -> TestSet:
    """Legt eine BacktestConfig und ein TestSet mit dem gegebenen Namen an."""
    config = BacktestConfig(
        name='T61-Config',
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
        name=name,
        backtest_config_ids_json=[config.id],
        leaderboard_enabled=False,
    )
    session.add(testset)
    session.commit()
    session.refresh(testset)
    return testset


def _make_testset_run(session, testset_id: int) -> TestSetRun:
    """Legt einen minimalen Testset-Lauf an."""
    run = TestSetRun(
        testset_id=testset_id,
        strategy_family='test_family',
        strategy_name='test_strategy',
        indicators_config_json={},
        status='completed',
        n_runs_total=1,
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
        status='completed',
        testset_run_id=testset_run_id,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _call_delete(testset_id: int, route_session, force: bool = False):
    """Ruft den Lösch-Endpunkt mit der übergebenen Session auf."""
    with patch.object(api_testsets_module, 'get_session', return_value=route_session):
        return api_testsets_module.delete_testset_endpoint(testset_id, force=force)


def test_delete_testset_without_runs_deletes_directly(db_engine):
    """Ohne anhängende Läufe wird sofort gelöscht — keine Rückfrage."""
    Session = sessionmaker(bind=db_engine)
    setup_session = Session()
    testset = _make_testset(setup_session, 'TestSet-Ohne-Laeufe')
    testset_id = testset.id
    setup_session.close()

    response = _call_delete(testset_id, Session())

    assert response['error'] is None
    assert response['data']['deleted'] is True

    check_session = Session()
    assert check_session.query(TestSet).filter(TestSet.id == testset_id).first() is None
    check_session.close()


def test_delete_testset_with_runs_asks_back_and_deletes_nothing(db_engine):
    """Anhängende Läufe führen zu HTTP 409 mit den Anzahlen — nichts wird gelöscht."""
    Session = sessionmaker(bind=db_engine)
    setup_session = Session()
    testset = _make_testset(setup_session, 'TestSet-Mit-Laeufen')
    testset_run = _make_testset_run(setup_session, testset.id)
    _make_backtest_run(setup_session, testset_run.id)
    _make_backtest_run(setup_session, testset_run.id)
    testset_id = testset.id
    testset_run_id = testset_run.id
    setup_session.close()

    with pytest.raises(HTTPException) as exc_info:
        _call_delete(testset_id, Session())

    assert exc_info.value.status_code == 409
    assert '1 Testset-Läufe' in exc_info.value.detail
    assert '2 Backtest-Runs' in exc_info.value.detail

    check_session = Session()
    assert check_session.query(TestSet).filter(TestSet.id == testset_id).first() is not None
    assert check_session.query(TestSetRun).filter(TestSetRun.id == testset_run_id).first() is not None
    check_session.close()


def test_delete_testset_with_force_keeps_runs_and_results(db_engine):
    """Mit force verschwindet nur das TestSet — Läufe und Backtest-Runs bleiben."""
    Session = sessionmaker(bind=db_engine)
    setup_session = Session()
    testset = _make_testset(setup_session, 'TestSet-Force')
    testset_run = _make_testset_run(setup_session, testset.id)
    backtest_run = _make_backtest_run(setup_session, testset_run.id)
    testset_id = testset.id
    testset_run_id = testset_run.id
    backtest_run_id = backtest_run.id
    setup_session.close()

    response = _call_delete(testset_id, Session(), force=True)

    assert response['error'] is None
    assert response['data']['deleted'] is True

    check_session = Session()
    assert check_session.query(TestSet).filter(TestSet.id == testset_id).first() is None
    surviving_run = check_session.query(TestSetRun).filter(TestSetRun.id == testset_run_id).first()
    assert surviving_run is not None
    # Die lose Referenz bleibt erhalten und zeigt jetzt auf ein gelöschtes TestSet
    assert surviving_run.testset_id == testset_id
    assert check_session.query(BacktestRun).filter(BacktestRun.id == backtest_run_id).first() is not None
    check_session.close()


def test_delete_empty_testset_runs_are_kept(db_engine):
    """Auch leere Testset-Läufe bleiben stehen — es wird nichts mitgelöscht."""
    Session = sessionmaker(bind=db_engine)
    setup_session = Session()
    testset = _make_testset(setup_session, 'TestSet-Leere-Laeufe')
    first_run = _make_testset_run(setup_session, testset.id)
    second_run = _make_testset_run(setup_session, testset.id)
    testset_id = testset.id
    run_ids = [first_run.id, second_run.id]
    setup_session.close()

    response = _call_delete(testset_id, Session(), force=True)

    assert response['data']['deleted'] is True

    check_session = Session()
    assert check_session.query(TestSet).filter(TestSet.id == testset_id).first() is None
    assert check_session.query(TestSetRun).filter(TestSetRun.id.in_(run_ids)).count() == 2
    check_session.close()


def test_delete_unknown_testset_returns_404(db_engine):
    """Unbekannte ID ergibt weiterhin HTTP 404."""
    Session = sessionmaker(bind=db_engine)

    with pytest.raises(HTTPException) as exc_info:
        _call_delete(99999999, Session())

    assert exc_info.value.status_code == 404

"""Tests für die Leaderboard-API (Ticket 07).

Testet direkt die Repository-Funktionen und die Endpunkt-Logik:
- list_leaderboard_entries_with_triggered_by — Default-Sort, NULL-Handling, Filter
- get_leaderboard_entry + drilldown-Logik — Reihenfolge, null-Markierung

Verwendet PostgreSQL (JSONB-kompatibel), Test-DB via VBT_TEST_DATABASE_URL (Port 5562).
db_engine und session kommen aus tests/conftest.py (Ticket 14).
"""

# GEÄNDERT: Ticket 14 — Lokale db_engine/session-Fixtures entfernt, zentrale
# Fixtures aus conftest.py werden automatisch injiziert.
from datetime import datetime as dt
from decimal import Decimal
from typing import Any, List, Optional

import pytest

from user_data.utils.database.models import (
    BacktestConfig,
    BacktestResult,
    BacktestRun,
    LeaderboardEntry,
    TestSet,
    TestSetRun,
)
from user_data.utils.database.repository_testsets import (
    get_leaderboard_entry,
    list_leaderboard_entries_with_triggered_by,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope='function')
def backtest_config(session):
    """Minimale BacktestConfig."""
    config = BacktestConfig(
        name='API-Leaderboard-Test-Config',
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
    session.refresh(config)
    return config


@pytest.fixture(scope='function')
def test_set(session, backtest_config):
    """TestSet für API-Tests."""
    ts = TestSet(
        name='API-Leaderboard-TestSet',
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_ids_json=[backtest_config.id],
    )
    session.add(ts)
    session.commit()
    session.refresh(ts)
    return ts


@pytest.fixture(scope='function')
def other_test_set(session, backtest_config):
    """Zweites TestSet, um Filter-Isolation zu prüfen."""
    ts = TestSet(
        name='API-Leaderboard-OtherTestSet',
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_ids_json=[backtest_config.id],
    )
    session.add(ts)
    session.commit()
    session.refresh(ts)
    return ts


def _make_entry(session, test_set, strategy_name: str, total_return_avg=None, testset_run=None, winning_result_ids=None):
    """Hilfsfunktion: LeaderboardEntry anlegen."""
    entry = LeaderboardEntry(
        testset_id=test_set.id,
        testset_run_id=testset_run.id if testset_run else None,
        strategy_family='teststrategie',
        strategy_name=strategy_name,
        configs_total=3,
        # GEÄNDERT: Ticket 15 — _json-Suffix
        testset_snapshot_json={'name': test_set.name},
        strategy_snapshot_json={'strategy_family': 'teststrategie', 'strategy_name': strategy_name},
        winning_result_ids_json=winning_result_ids or [],
        total_return_avg=Decimal(str(total_return_avg)) if total_return_avg is not None else None,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def _make_testset_run(session, test_set, triggered_by=None):
    """Hilfsfunktion: TestSetRun anlegen."""
    run = TestSetRun(
        testset_id=test_set.id,
        strategy_family='teststrategie',
        strategy_name='v1',
        n_runs_total=1,
        triggered_by=triggered_by,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _make_backtest_run(session):
    """Hilfsfunktion: minimalen BacktestRun anlegen."""
    run = BacktestRun(
        strategy_family='teststrategie',
        strategy_name='v1',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date=dt(2024, 1, 1),
        end_date=dt(2024, 12, 31),
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_json={'symbol': 'BTCUSDT'},
        indicators_config_json={},
        status='completed',
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


# ============================================================================
# Test: list_leaderboard_entries_with_triggered_by — Default-Sort
# ============================================================================

def test_list_leaderboard_default_sort(session, test_set):
    """Einträge kommen nach total_return_avg DESC sortiert zurück."""
    _make_entry(session, test_set, 'v1', total_return_avg=5.0)
    _make_entry(session, test_set, 'v2', total_return_avg=42.5)
    _make_entry(session, test_set, 'v3', total_return_avg=18.0)

    rows = list_leaderboard_entries_with_triggered_by(session, test_set.id)
    assert len(rows) == 3
    returns = [float(r['entry'].total_return_avg) for r in rows]
    # Höchster Wert zuerst
    assert returns[0] == pytest.approx(42.5, abs=0.01)
    assert returns[1] == pytest.approx(18.0, abs=0.01)
    assert returns[2] == pytest.approx(5.0, abs=0.01)


def test_list_leaderboard_null_last(session, test_set):
    """Einträge mit total_return_avg NULL erscheinen am Ende."""
    _make_entry(session, test_set, 'v_null', total_return_avg=None)
    _make_entry(session, test_set, 'v_pos', total_return_avg=10.0)

    rows = list_leaderboard_entries_with_triggered_by(session, test_set.id)
    assert len(rows) == 2
    # Nicht-NULL zuerst
    assert rows[0]['entry'].total_return_avg is not None
    assert float(rows[0]['entry'].total_return_avg) == pytest.approx(10.0, abs=0.01)
    # NULL zuletzt
    assert rows[1]['entry'].total_return_avg is None


def test_list_leaderboard_filter_by_test_set(session, test_set, other_test_set):
    """Nur Einträge des angegebenen TestSets werden zurückgegeben."""
    _make_entry(session, test_set, 'target', total_return_avg=7.0)
    _make_entry(session, other_test_set, 'other', total_return_avg=99.0)

    rows = list_leaderboard_entries_with_triggered_by(session, test_set.id)
    assert len(rows) == 1
    assert rows[0]['entry'].strategy_name == 'target'


def test_list_leaderboard_triggered_by_from_run(session, test_set):
    """triggered_by wird via LEFT JOIN aus testset_runs geholt."""
    run = _make_testset_run(session, test_set, triggered_by='user:tom')
    _make_entry(session, test_set, 'v_with_run', total_return_avg=5.0, testset_run=run)

    rows = list_leaderboard_entries_with_triggered_by(session, test_set.id)
    assert len(rows) == 1
    assert rows[0]['triggered_by'] == 'user:tom'


def test_list_leaderboard_triggered_by_null_when_no_run(session, test_set):
    """triggered_by ist NULL wenn kein testset_run verknüpft ist."""
    _make_entry(session, test_set, 'orphan', total_return_avg=3.0, testset_run=None)

    rows = list_leaderboard_entries_with_triggered_by(session, test_set.id)
    assert len(rows) == 1
    assert rows[0]['triggered_by'] is None


# ============================================================================
# Test: Drilldown-Logik (winner_result_ids Reihenfolge + null-Markierung)
# ============================================================================

def test_drilldown_winning_result_ids_order(session, test_set):
    """winning_result_ids sind in der richtigen Reihenfolge gespeichert."""
    bt_run = _make_backtest_run(session)

    r1 = BacktestResult(
        run_id=bt_run.id, params_hash='aaa',
        # GEÄNDERT: Ticket 15 — _json-Suffix
        actual_params_json={'symbol': 'BTCUSDT'},
        total_return_pct=10.0, total_trades=5,
    )
    r2 = BacktestResult(
        run_id=bt_run.id, params_hash='bbb',
        actual_params_json={'symbol': 'ETHUSDT'},
        total_return_pct=20.0, total_trades=10,
    )
    session.add(r1)
    session.add(r2)
    session.commit()
    session.refresh(r1)
    session.refresh(r2)

    entry = _make_entry(
        session, test_set, 'drilldown_v1',
        total_return_avg=15.0,
        winning_result_ids=[r1.id, r2.id],
    )

    fetched = get_leaderboard_entry(session, entry.id)
    assert fetched is not None
    # GEÄNDERT: Ticket 15 — _json-Suffix
    assert fetched.winning_result_ids_json[0] == r1.id
    assert fetched.winning_result_ids_json[1] == r2.id

    # Result-Daten für Position 0 laden und prüfen
    res0 = session.query(BacktestResult).filter(BacktestResult.id == fetched.winning_result_ids_json[0]).first()
    assert res0 is not None
    assert res0.total_return_pct == pytest.approx(10.0, abs=0.01)


def test_drilldown_null_positions_in_winning_ids(session, test_set):
    """NULL-Einträge in winning_result_ids werden korrekt persistiert."""
    entry = _make_entry(
        session, test_set, 'missing_v1',
        total_return_avg=5.0,
        winning_result_ids=[None, None],
    )

    fetched = get_leaderboard_entry(session, entry.id)
    assert fetched is not None
    # GEÄNDERT: Ticket 15 — _json-Suffix
    assert len(fetched.winning_result_ids_json) == 2
    assert fetched.winning_result_ids_json[0] is None
    assert fetched.winning_result_ids_json[1] is None


def test_drilldown_mixed_null_and_real_ids(session, test_set):
    """Gemischte winning_result_ids: ein NULL, ein echtes Result."""
    bt_run = _make_backtest_run(session)
    r = BacktestResult(
        run_id=bt_run.id, params_hash='ccc',
        # GEÄNDERT: Ticket 15 — _json-Suffix
        actual_params_json={'symbol': 'BTCUSDT'},
        total_return_pct=8.0, total_trades=3,
    )
    session.add(r)
    session.commit()
    session.refresh(r)

    entry = _make_entry(
        session, test_set, 'mixed_v1',
        total_return_avg=4.0,
        winning_result_ids=[None, r.id],
    )

    fetched = get_leaderboard_entry(session, entry.id)
    assert fetched is not None
    # GEÄNDERT: Ticket 15 — _json-Suffix
    ids = fetched.winning_result_ids_json
    assert len(ids) == 2
    assert ids[0] is None     # Position 0: leer
    assert ids[1] == r.id     # Position 1: echtes Result


def test_drilldown_entry_not_found(session):
    """get_leaderboard_entry gibt None für nicht-existierende ID zurück."""
    result = get_leaderboard_entry(session, 99999999)
    assert result is None

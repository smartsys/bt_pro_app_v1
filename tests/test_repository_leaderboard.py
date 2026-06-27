"""Tests für TestSetRun- und LeaderboardEntry-Repository-Funktionen.

Ticket 03: Stellt sicher, dass TestSetRun- und LeaderboardEntry-CRUD korrekt
funktioniert, Snapshots vollständig persistiert und gelesen werden und der
UNIQUE-Constraint auf testset_run_id greift.

Hinweis: JSONB (PostgreSQL-spezifisch) wird im Model verwendet. Tests laufen
daher gegen die echte PostgreSQL-Test-DB (VBT_TEST_DATABASE_URL, Port 5562).
db_engine und session kommen aus tests/conftest.py (Ticket 14).
"""

# GEÄNDERT: Ticket 14 — Lokale db_engine/session-Fixtures entfernt, zentrale
# Fixtures aus conftest.py werden automatisch injiziert.
import pytest
from datetime import datetime

from user_data.utils.database.models import (
    BacktestConfig,
    IndicatorConfig,
    LeaderboardEntry,
    TestSet,
    TestSetRun,
)
from user_data.utils.database.repository_testsets import (
    create_leaderboard_entry,
    create_testset_run,
    get_leaderboard_entry,
    get_testset_run,
    list_leaderboard_entries_for_testset,
    update_testset_run_status,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope='function')
def backtest_config(session):
    """Minimale BacktestConfig als Voraussetzung für TestSet."""
    config = BacktestConfig(
        name='Leaderboard-Test-Config',
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
    """TestSet als FK-Voraussetzung für TestSetRun."""
    ts = TestSet(
        name='Leaderboard-TestSet',
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_ids_json=[backtest_config.id],
        created_by='test-user',
    )
    session.add(ts)
    session.commit()
    session.refresh(ts)
    return ts


@pytest.fixture(scope='function')
def indicator_config(session):
    """Minimale IndicatorConfig für optionale FK-Tests."""
    ic = IndicatorConfig(
        name='Test-IndicatorConfig',
        config_json={'teststrategie_period': 20},
    )
    session.add(ic)
    session.commit()
    session.refresh(ic)
    return ic


@pytest.fixture(scope='function')
def testset_run(session, test_set):
    """TestSetRun als FK-Voraussetzung für LeaderboardEntry."""
    run = create_testset_run(
        session=session,
        testset_id=test_set.id,
        strategy_family='teststrategie',
        strategy_name='teststrategie_v1',
        n_runs_total=3,
        created_by='test-user',
    )
    return run


@pytest.fixture
def example_testset_snapshot(test_set, backtest_config):
    """Realistischer testset_snapshot für LeaderboardEntry-Tests."""
    return {
        'name': test_set.name,
        'backtest_config_ids': [backtest_config.id],
        'configs': [
            {
                'id': backtest_config.id,
                'symbol': 'BTCUSDT',
                'timeframe': '4h',
                'start': '2024-01-01',
                'end': '2024-12-31',
            }
        ],
    }


@pytest.fixture
def example_strategy_snapshot():
    """Minimaler strategy_snapshot gemäß Ticket 03 MVP-Definition."""
    return {
        'strategy_family': 'teststrategie',
        'strategy_name': 'teststrategie_v1',
        'spec_runner_version': '1.0.0',
    }


@pytest.fixture
def example_indicator_config_snapshot():
    """Vollständiger indicator_config_snapshot."""
    return {
        'name': 'Test-IndicatorConfig',
        'config_json': {'teststrategie_period': 20, 'signal_threshold': 0.5},
    }


# ============================================================================
# Tests: TestSetRun anlegen
# ============================================================================

def test_create_testset_run(session, test_set):
    """Anlegen eines TestSetRun mit Pflichtfeldern."""
    run = create_testset_run(
        session=session,
        testset_id=test_set.id,
        strategy_family='teststrategie',
        strategy_name='teststrategie_v1',
        n_runs_total=5,
    )
    assert run.id is not None
    assert run.testset_id == test_set.id
    assert run.strategy_family == 'teststrategie'
    assert run.strategy_name == 'teststrategie_v1'
    assert run.n_runs_total == 5
    assert run.n_runs_completed == 0
    assert run.status == 'queued'
    assert run.created_at is not None
    assert run.completed_at is None


def test_create_testset_run_with_indicator_config(session, test_set, indicator_config):
    """Anlegen eines TestSetRun mit optionalem Indicator-Config-JSON."""
    # GEÄNDERT: Ticket 15 — indicator_config_id → indicators_config_json
    run = create_testset_run(
        session=session,
        testset_id=test_set.id,
        strategy_family='teststrategie',
        strategy_name='teststrategie_v1',
        n_runs_total=2,
        indicators_config_json=indicator_config.config_json,
        triggered_by='user:tom',
        created_by='tom',
    )
    assert run.indicators_config_json == indicator_config.config_json
    assert run.triggered_by == 'user:tom'
    assert run.created_by == 'tom'


# ============================================================================
# Tests: TestSetRun lesen
# ============================================================================

def test_get_testset_run(session, testset_run):
    """Einzelnen TestSetRun abrufen."""
    result = get_testset_run(session, testset_run.id)
    assert result is not None
    assert result.id == testset_run.id
    assert result.strategy_family == 'teststrategie'


def test_get_testset_run_not_found(session):
    """Nicht-existierender TestSetRun gibt None zurück."""
    result = get_testset_run(session, 99999999)
    assert result is None


# ============================================================================
# Tests: Status-Transition
# ============================================================================

def test_update_testset_run_status_to_running(session, testset_run):
    """Status-Übergang von queued auf running."""
    updated = update_testset_run_status(
        session=session,
        testset_run_id=testset_run.id,
        status='running',
        n_runs_completed=0,
    )
    assert updated is not None
    assert updated.status == 'running'
    assert updated.n_runs_completed == 0
    assert updated.completed_at is None


def test_update_testset_run_status_to_completed(session, testset_run):
    """Status-Übergang auf completed mit completed_at."""
    ts = datetime(2026, 5, 24, 12, 0, 0)
    updated = update_testset_run_status(
        session=session,
        testset_run_id=testset_run.id,
        status='completed',
        n_runs_completed=3,
        completed_at=ts,
    )
    assert updated.status == 'completed'
    assert updated.n_runs_completed == 3
    assert updated.completed_at == ts


def test_update_testset_run_status_not_found(session):
    """Update eines nicht-existierenden TestSetRuns gibt None zurück."""
    result = update_testset_run_status(session, 99999999, status='running')
    assert result is None


# ============================================================================
# Tests: LeaderboardEntry anlegen
# ============================================================================

def test_create_leaderboard_entry_full(
    session,
    test_set,
    testset_run,
    example_testset_snapshot,
    example_strategy_snapshot,
    example_indicator_config_snapshot,
):
    """Anlegen eines LeaderboardEntry mit allen drei Snapshots und winning_result_ids."""
    winning_ids = [101, 202, 303]
    entry = create_leaderboard_entry(
        session=session,
        testset_id=test_set.id,
        testset_run_id=testset_run.id,
        strategy_family='teststrategie',
        strategy_name='teststrategie_v1',
        configs_total=3,
        testset_snapshot=example_testset_snapshot,
        strategy_snapshot=example_strategy_snapshot,
        indicator_config_snapshot=example_indicator_config_snapshot,
        winning_result_ids=winning_ids,
        spec_runner_version='1.0.0',
        hint='Testlauf',
    )
    assert entry.id is not None
    assert entry.testset_id == test_set.id
    assert entry.testset_run_id == testset_run.id
    assert entry.strategy_family == 'teststrategie'
    assert entry.strategy_name == 'teststrategie_v1'
    assert entry.configs_total == 3
    assert entry.created_at is not None

    # Aggregate initial NULL
    assert entry.total_return_avg is None
    assert entry.max_drawdown_avg is None
    assert entry.sharpe_avg is None
    assert entry.configs_passed is None
    assert entry.filter_breached is None


def test_create_leaderboard_entry_snapshot_content(
    session,
    test_set,
    example_testset_snapshot,
    example_strategy_snapshot,
    example_indicator_config_snapshot,
):
    """Snapshot-Inhalte werden vollständig gespeichert und gelesen."""
    entry = create_leaderboard_entry(
        session=session,
        testset_id=test_set.id,
        strategy_family='teststrategie',
        strategy_name='teststrategie_v1',
        configs_total=1,
        testset_snapshot=example_testset_snapshot,
        strategy_snapshot=example_strategy_snapshot,
        indicator_config_snapshot=example_indicator_config_snapshot,
        winning_result_ids=[42],
    )

    # Read-Back über get_leaderboard_entry
    fetched = get_leaderboard_entry(session, entry.id)
    assert fetched is not None

    # GEÄNDERT: Ticket 15 — _json-Suffix für alle Snapshot-Felder
    # testset_snapshot prüfen
    assert fetched.testset_snapshot_json['name'] == example_testset_snapshot['name']
    assert fetched.testset_snapshot_json['backtest_config_ids'] == example_testset_snapshot['backtest_config_ids']
    assert len(fetched.testset_snapshot_json['configs']) == 1

    # strategy_snapshot prüfen
    assert fetched.strategy_snapshot_json['strategy_family'] == 'teststrategie'
    assert fetched.strategy_snapshot_json['strategy_name'] == 'teststrategie_v1'
    assert fetched.strategy_snapshot_json['spec_runner_version'] == '1.0.0'

    # indicator_config_snapshot prüfen
    assert fetched.indicator_config_snapshot_json['config_json']['teststrategie_period'] == 20

    # winning_result_ids prüfen
    assert fetched.winning_result_ids_json == [42]


def test_create_leaderboard_entry_without_indicator_snapshot(
    session,
    test_set,
    example_testset_snapshot,
    example_strategy_snapshot,
):
    """LeaderboardEntry ohne indicator_config_snapshot ist erlaubt (nullable)."""
    entry = create_leaderboard_entry(
        session=session,
        testset_id=test_set.id,
        strategy_family='teststrategie',
        strategy_name='teststrategie_v1',
        configs_total=2,
        testset_snapshot=example_testset_snapshot,
        strategy_snapshot=example_strategy_snapshot,
        winning_result_ids=[1, 2],
    )
    # GEÄNDERT: Ticket 15 — _json-Suffix
    assert entry.indicator_config_snapshot_json is None
    fetched = get_leaderboard_entry(session, entry.id)
    assert fetched.indicator_config_snapshot_json is None


# ============================================================================
# Tests: UNIQUE-Constraint auf testset_run_id
# ============================================================================

def test_unique_constraint_testset_run_id(
    session,
    test_set,
    testset_run,
    example_testset_snapshot,
    example_strategy_snapshot,
):
    """Zweiter LeaderboardEntry mit gleicher testset_run_id schlägt mit IntegrityError fehl."""
    from sqlalchemy.exc import IntegrityError

    create_leaderboard_entry(
        session=session,
        testset_id=test_set.id,
        testset_run_id=testset_run.id,
        strategy_family='teststrategie',
        strategy_name='teststrategie_v1',
        configs_total=1,
        testset_snapshot=example_testset_snapshot,
        strategy_snapshot=example_strategy_snapshot,
        winning_result_ids=[1],
    )

    with pytest.raises(IntegrityError):
        create_leaderboard_entry(
            session=session,
            testset_id=test_set.id,
            testset_run_id=testset_run.id,  # Gleiche testset_run_id -> UNIQUE-Verletzung
            strategy_family='teststrategie',
            strategy_name='teststrategie_v1',
            configs_total=2,
            testset_snapshot=example_testset_snapshot,
            strategy_snapshot=example_strategy_snapshot,
            winning_result_ids=[2],
        )


# ============================================================================
# Tests: Leaderboard-Liste für TestSet
# ============================================================================

def test_list_leaderboard_entries_for_testset_empty(session, test_set):
    """Leere Liste wenn kein Eintrag für TestSet vorhanden."""
    result = list_leaderboard_entries_for_testset(session, test_set.id)
    assert result == []


def test_list_leaderboard_entries_sorted_by_return(
    session,
    test_set,
    example_testset_snapshot,
    example_strategy_snapshot,
):
    """Einträge werden nach total_return_avg DESC sortiert zurückgegeben."""
    from decimal import Decimal

    # Drei Einträge mit unterschiedlichen Aggregaten anlegen
    entry_low = create_leaderboard_entry(
        session=session,
        testset_id=test_set.id,
        strategy_family='teststrategie',
        strategy_name='v1',
        configs_total=1,
        testset_snapshot=example_testset_snapshot,
        strategy_snapshot=example_strategy_snapshot,
        winning_result_ids=[1],
    )
    entry_low.total_return_avg = Decimal('5.0000')

    entry_high = create_leaderboard_entry(
        session=session,
        testset_id=test_set.id,
        strategy_family='teststrategie',
        strategy_name='v2',
        configs_total=1,
        testset_snapshot=example_testset_snapshot,
        strategy_snapshot=example_strategy_snapshot,
        winning_result_ids=[2],
    )
    entry_high.total_return_avg = Decimal('42.5000')

    # Eintrag ohne Aggregat (NULL) -> soll zuletzt erscheinen
    create_leaderboard_entry(
        session=session,
        testset_id=test_set.id,
        strategy_family='teststrategie',
        strategy_name='v3',
        configs_total=1,
        testset_snapshot=example_testset_snapshot,
        strategy_snapshot=example_strategy_snapshot,
        winning_result_ids=[3],
    )
    session.commit()

    entries = list_leaderboard_entries_for_testset(session, test_set.id)
    assert len(entries) == 3
    # Höchster Wert zuerst
    assert entries[0].total_return_avg == Decimal('42.5000')
    assert entries[1].total_return_avg == Decimal('5.0000')
    # NULL zuletzt
    assert entries[2].total_return_avg is None

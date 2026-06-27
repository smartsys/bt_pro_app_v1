"""Tests für iteration_id-Write-Pfad.

Stellt sicher, dass:
1. create_backtest_run die ÜBERGEBENE iteration_id im INSERT schreibt (kein Lookup).
2. Wird keine iteration_id übergeben, bleibt sie NULL (kein Crash, kein Fallback).
3. BacktestRun/BacktestResult akzeptieren die iteration_id-Spalte.

GEÄNDERT: Der frühere Ticket-10-Auto-Lookup (get_iteration_by_strategy_name)
ist entfernt — iteration_id wird ausschließlich vom Aufrufer mitgegeben.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from user_data.utils.database.models import (
    Base, BacktestRun, BacktestResult, StrategyConcept, StrategyIteration,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope='function')
def db_engine():
    """In-Memory-SQLite-Engine für Isolations-Tests."""
    engine = create_engine('sqlite://', echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope='function')
def db_session(db_engine):
    """Test-Session, isoliert pro Test."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope='function')
def seed_iteration(db_session) -> StrategyIteration:
    """Legt Concept teststrategie + Iteration v2.0 in der Test-DB an."""
    concept = StrategyConcept(
        slug='teststrategie',
        name='Teststrategie',
        status='active',
        created_at=datetime.now(),
    )
    db_session.add(concept)
    db_session.flush()

    iteration = StrategyIteration(
        concept_id=concept.id,
        version=1,
        status='active',
        created_at=datetime.now(),
    )
    db_session.add(iteration)
    db_session.commit()
    db_session.refresh(iteration)
    return iteration


def _minimal_backtest_config(strategy_family: str = 'teststrategie', strategy_name: str = 'teststrategie_v2') -> dict:
    """Gibt eine minimale gültige backtest_config zurück."""
    return {
        'strategy_family': strategy_family,
        'strategy_name': strategy_name,
        'symbols': ['BTCUSDT'],
        'exchange': 'binance',
        'timeframe': '4h',
        'start': '2024-01-01',
        'end': '2024-12-31',
        'import_path': 'user_data.strategies.generic.spec_runner.run_spec_strategy',
    }


# ============================================================================
# Tests: Model-Ebene — iteration_id Spalte vorhanden
# ============================================================================

def test_backtest_run_has_iteration_id_column(db_session, seed_iteration):
    """BacktestRun akzeptiert und speichert iteration_id."""
    run = BacktestRun(
        strategy_family='teststrategie',
        strategy_name='teststrategie_v2',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_json={},
        indicators_config_json={},
        n_combinations=1,
        status='queued',
        iteration_id=seed_iteration.id,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    assert run.iteration_id == seed_iteration.id


def test_backtest_result_has_iteration_id_column(db_session, seed_iteration):
    """BacktestResult akzeptiert und speichert iteration_id."""
    result = BacktestResult(
        run_id=999,
        params_hash='abc123',
        # GEÄNDERT: Ticket 15 — _json-Suffix
        actual_params_json={'x': 1},
        metrics_level='partial',
        is_favorite=0,
        iteration_id=seed_iteration.id,
    )
    db_session.add(result)
    db_session.commit()
    db_session.refresh(result)

    assert result.iteration_id == seed_iteration.id


def test_indicator_config_has_strategy_concept_iteration_columns(db_session, seed_iteration):
    """IndicatorConfig akzeptiert und speichert strategy_concept_id + strategy_iteration_id (Ticket 22, lose Verknüpfung)."""
    from user_data.utils.database.models import IndicatorConfig
    # GEÄNDERT: Ticket 22 — zwei Integer-Spalten ohne FK; alte String-iteration_id entfernt
    ic = IndicatorConfig(
        name='Test-Config',
        config_json={},
        is_default=0,
        strategy_concept_id=seed_iteration.concept_id,
        strategy_iteration_id=seed_iteration.id,
    )
    db_session.add(ic)
    db_session.commit()
    db_session.refresh(ic)

    assert ic.strategy_concept_id == seed_iteration.concept_id
    assert ic.strategy_iteration_id == seed_iteration.id


# ============================================================================
# Tests: create_backtest_run — iteration_id wird vom Aufrufer mitgegeben (kein Lookup)
# ============================================================================

def test_create_backtest_run_writes_passed_iteration_id():
    """create_backtest_run schreibt die ÜBERGEBENE iteration_id in den INSERT.

    Kein Lookup mehr — die iteration_id kommt direkt vom Aufrufer.
    Testet den realen Code-Pfad über Mock (kein echter DB-Zugriff).
    """
    import user_data.utils.database.repository as repo

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value.scalar.return_value = 99
    mock_engine.begin.return_value = mock_conn

    with patch('user_data.utils.database.repository.get_engine', return_value=mock_engine):
        run_id = repo.create_backtest_run(
            backtest_config=_minimal_backtest_config(),
            indicators_config={},
            iteration_id=42,
        )

    assert run_id == 99
    # Das ausgeführte INSERT-Statement trägt iteration_id=42
    insert_stmt = mock_conn.execute.call_args.args[0]
    assert insert_stmt.compile().params['iteration_id'] == 42


def test_create_backtest_run_iteration_id_null_when_omitted():
    """Ohne übergebene iteration_id bleibt sie NULL (kein Lookup, kein Fallback)."""
    import user_data.utils.database.repository as repo

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value.scalar.return_value = 77
    mock_engine.begin.return_value = mock_conn

    with patch('user_data.utils.database.repository.get_engine', return_value=mock_engine):
        run_id = repo.create_backtest_run(
            backtest_config=_minimal_backtest_config('unknown', 'unknown'),
            indicators_config={},
        )

    assert run_id == 77
    insert_stmt = mock_conn.execute.call_args.args[0]
    assert insert_stmt.compile().params['iteration_id'] is None


# ============================================================================
# Tests: create_backtest_run — Herkunfts-Config-IDs (backtest_config_id / indicator_config_id)
# ============================================================================

def test_backtest_run_has_config_id_columns(db_session, seed_iteration):
    """BacktestRun akzeptiert und speichert backtest_config_id + indicator_config_id."""
    run = BacktestRun(
        strategy_family='teststrategie',
        strategy_name='teststrategie_v2',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        backtest_config_json={},
        indicators_config_json={},
        n_combinations=1,
        status='queued',
        backtest_config_id=7,
        indicator_config_id=21,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    assert run.backtest_config_id == 7
    assert run.indicator_config_id == 21


def test_create_backtest_run_writes_passed_config_ids():
    """create_backtest_run schreibt die ÜBERGEBENEN Config-IDs in den INSERT (lose Referenz)."""
    import user_data.utils.database.repository as repo

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value.scalar.return_value = 55
    mock_engine.begin.return_value = mock_conn

    with patch('user_data.utils.database.repository.get_engine', return_value=mock_engine):
        run_id = repo.create_backtest_run(
            backtest_config=_minimal_backtest_config(),
            indicators_config={},
            backtest_config_id=7,
            indicator_config_id=21,
        )

    assert run_id == 55
    insert_stmt = mock_conn.execute.call_args.args[0]
    params = insert_stmt.compile().params
    assert params['backtest_config_id'] == 7
    assert params['indicator_config_id'] == 21


def test_create_backtest_run_config_ids_null_when_omitted():
    """Ohne übergebene Config-IDs bleiben beide NULL (ad-hoc-Run ohne gespeicherte Config)."""
    import user_data.utils.database.repository as repo

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value.scalar.return_value = 88
    mock_engine.begin.return_value = mock_conn

    with patch('user_data.utils.database.repository.get_engine', return_value=mock_engine):
        run_id = repo.create_backtest_run(
            backtest_config=_minimal_backtest_config(),
            indicators_config={},
        )

    assert run_id == 88
    params = mock_conn.execute.call_args.args[0].compile().params
    assert params['backtest_config_id'] is None
    assert params['indicator_config_id'] is None

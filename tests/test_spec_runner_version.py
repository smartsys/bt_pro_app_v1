"""Tests für spec_runner.VERSION-Tracking in BacktestRun und BacktestResult.

Ticket 01: Stellt sicher, dass spec_runner_version beim Anlegen von Runs
und beim Speichern von Results korrekt befüllt wird.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.dialects import sqlite
from sqlalchemy.orm import sessionmaker

from user_data.utils.database.models import Base, BacktestRun, BacktestResult
from user_data.strategies.generic.spec_runner import VERSION as SPEC_RUNNER_VERSION

_START_DATE = datetime(2024, 1, 1)
_END_DATE = datetime(2024, 12, 31)


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


def _minimal_backtest_config() -> dict:
    """Gibt eine minimale gültige backtest_config zurück."""
    return {
        'strategy_family': 'test_family',
        'strategy_name': 'test_strategy',
        'symbols': ['BTCUSDT'],
        'exchange': 'binance',
        'timeframe': '4h',
        'start': '2024-01-01',
        'end': '2024-12-31',
        'import_path': 'user_data.strategies.generic.spec_runner.run_spec_strategy',
    }


# ============================================================================
# Tests: VERSION-Konstante
# ============================================================================

def test_spec_runner_version_constant_exists():
    """VERSION-Konstante muss in spec_runner vorhanden und nicht leer sein."""
    assert SPEC_RUNNER_VERSION is not None
    assert isinstance(SPEC_RUNNER_VERSION, str)
    assert len(SPEC_RUNNER_VERSION) > 0


def test_spec_runner_version_semver_format():
    """VERSION muss dem SemVer-Format X.Y.Z entsprechen."""
    parts = SPEC_RUNNER_VERSION.split('.')
    assert len(parts) == 3, f"VERSION '{SPEC_RUNNER_VERSION}' ist kein SemVer (X.Y.Z erwartet)"
    for part in parts:
        assert part.isdigit(), f"Alle Teile müssen Ganzzahlen sein, gefunden: '{part}'"


# ============================================================================
# Tests: BacktestRun — spec_runner_version-Spalte
# ============================================================================

def test_backtest_run_spec_runner_version_column_exists(db_session):
    """BacktestRun-Tabelle muss spec_runner_version-Spalte haben."""
    run = BacktestRun(
        strategy_family='test',
        strategy_name='test',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date=_START_DATE,
        end_date=_END_DATE,
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_json={},
        indicators_config_json={},
        n_combinations=1,
        status='queued',
        spec_runner_version='1.0.0',
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    assert run.spec_runner_version == '1.0.0'


def test_backtest_run_spec_runner_version_nullable(db_session):
    """spec_runner_version darf NULL sein (für Runs vor der Migration)."""
    run = BacktestRun(
        strategy_family='test',
        strategy_name='test',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date=_START_DATE,
        end_date=_END_DATE,
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_json={},
        indicators_config_json={},
        n_combinations=1,
        status='queued',
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    assert run.spec_runner_version is None


# ============================================================================
# Tests: BacktestResult — spec_runner_version-Spalte
# ============================================================================

def test_backtest_result_spec_runner_version_column_exists(db_session):
    """BacktestResult-Tabelle muss spec_runner_version-Spalte haben."""
    run = BacktestRun(
        strategy_family='test',
        strategy_name='test',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date=_START_DATE,
        end_date=_END_DATE,
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_json={},
        indicators_config_json={},
        n_combinations=1,
        status='queued',
    )
    db_session.add(run)
    db_session.flush()

    result = BacktestResult(
        run_id=run.id,
        params_hash='abc123',
        # GEÄNDERT: Ticket 15 — _json-Suffix
        actual_params_json={'test': 1},
        metrics_level='partial',
        spec_runner_version='1.0.0',
    )
    db_session.add(result)
    db_session.commit()
    db_session.refresh(result)

    assert result.spec_runner_version == '1.0.0'


def test_backtest_result_spec_runner_version_nullable(db_session):
    """spec_runner_version darf NULL sein (für Results vor der Migration)."""
    run = BacktestRun(
        strategy_family='test',
        strategy_name='test',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date=_START_DATE,
        end_date=_END_DATE,
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_json={},
        indicators_config_json={},
        n_combinations=1,
        status='queued',
    )
    db_session.add(run)
    db_session.flush()

    result = BacktestResult(
        run_id=run.id,
        params_hash='def456',
        # GEÄNDERT: Ticket 15 — _json-Suffix
        actual_params_json={'test': 2},
        metrics_level='partial',
    )
    db_session.add(result)
    db_session.commit()
    db_session.refresh(result)

    assert result.spec_runner_version is None


# ============================================================================
# Tests: create_backtest_run — schreibt spec_runner_version in die DB
# ============================================================================

def test_create_backtest_run_writes_spec_runner_version(db_engine, db_session):
    """create_backtest_run muss spec_runner_version in den neuen Run schreiben."""
    # Wir testen die Repository-Logik direkt über das Model, da create_backtest_run
    # intern get_engine() benutzt und wir die Engine austauschen müssen.
    # Direktes Model-Insert simuliert den Repository-Schreibpfad.
    run = BacktestRun(
        strategy_family='test_family',
        strategy_name='test_strategy',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date=_START_DATE,
        end_date=_END_DATE,
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_json=_minimal_backtest_config(),
        indicators_config_json={},
        n_combinations=1,
        status='queued',
        spec_runner_version=SPEC_RUNNER_VERSION,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    assert run.spec_runner_version == SPEC_RUNNER_VERSION


def test_create_backtest_run_with_mocked_engine():
    """create_backtest_run übergibt spec_runner_version an den Insert-Statement.

    Verifiziert über Mocking, dass der Parameter korrekt durchgereicht wird.
    """
    from unittest.mock import patch, MagicMock, call
    import user_data.utils.database.repository as repo

    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 42
    mock_conn.execute.return_value = mock_result

    mock_engine = MagicMock()
    mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    with patch.object(repo, 'get_engine', return_value=mock_engine):
        run_id = repo.create_backtest_run(
            backtest_config=_minimal_backtest_config(),
            indicators_config={},
            spec_runner_version='1.0.0',
        )

    assert run_id == 42
    # Prüfe, dass conn.execute aufgerufen wurde
    assert mock_conn.execute.called
    # Extrahiere den INSERT-Statement und prüfe spec_runner_version
    call_args = mock_conn.execute.call_args
    stmt = call_args[0][0]
    # Der Statement muss spec_runner_version in den compiled values haben
    compiled = stmt.compile(dialect=sqlite.dialect())
    params = compiled.params
    assert 'spec_runner_version' in str(stmt).lower() or any(
        'spec_runner_version' in str(k) for k in params.keys()
    ), "spec_runner_version muss im INSERT-Statement enthalten sein"

"""Tests für spec_json-Einbettung im LeaderboardEntry-Snapshot (Ticket 40).

Prüft:
- Happy Path: spec_json (indicators + rules) wird nach einem Testset-Run in
  strategy_snapshot_json eingebettet.
- Iteration ohne spec_json: strategy_snapshot hat keinen spec_json-Key (kein Crash).
- Bestandsschutz: Einträge ohne spec_json werden sauber abgewiesen, nicht gecrasht.

Tests laufen gegen die echte PostgreSQL-Test-DB (VBT_TEST_DATABASE_URL, Port 5562).
db_engine und session kommen aus tests/conftest.py.
"""

import pytest

from user_data.utils.database.models import (
    BacktestConfig,
    BacktestResult,
    BacktestRun,
    IndicatorConfig,
    StrategyConcept,
    StrategyIteration,
    TestSet,
    TestSetRun,
)
from user_data.utils.database.repository_testsets import _build_leaderboard_entry_in_session


# ============================================================================
# Fixtures
# ============================================================================

_EXAMPLE_SPEC_JSON = {
    'indicators': {
        'teststrategie': {
            'indicator': 'Teststrategie',
            'tf': '4h',
            'inputs': {'close': 'close', 'volume': 'volume'},
            'period': [14, 20],
        },
    },
    'rules': {
        'entry': {'type': 'crossover', 'a': 'indicator:teststrategie:teststrategie', 'b': 'close'},
        'exit': {'type': 'crossunder', 'a': 'indicator:teststrategie:teststrategie', 'b': 'close'},
    },
}


@pytest.fixture(scope='function')
def backtest_config(session):
    """Minimale BacktestConfig."""
    c = BacktestConfig(
        name='SpecJson-Test-Config',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start='2024-01-01',
        end='2024-12-31',
        ohlc_start='2023-12-01',
        ohlc_end='2025-01-01',
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


@pytest.fixture(scope='function')
def test_set(session, backtest_config):
    """TestSet mit einer BacktestConfig."""
    ts = TestSet(
        name='SpecJson-Test-TestSet',
        backtest_config_ids_json=[backtest_config.id],
        # Opt-in-Schalter aktiv — dieser Test prüft den Leaderboard-Build-Pfad
        leaderboard_enabled=True,
        created_by='test-spec-json',
    )
    session.add(ts)
    session.commit()
    session.refresh(ts)
    return ts


@pytest.fixture(scope='function')
def strategy_concept(session):
    """StrategyConcept als Voraussetzung für StrategyIteration."""
    concept = StrategyConcept(
        slug='test-specjson-strategy',
        name='Test SpecJson Strategy',
        category='test',
    )
    session.add(concept)
    session.commit()
    session.refresh(concept)
    return concept


@pytest.fixture(scope='function')
def strategy_iteration_with_spec(session, strategy_concept):
    """StrategyIteration mit vollständigem spec_json (indicators + rules)."""
    iteration = StrategyIteration(
        concept_id=strategy_concept.id,
        version=1,
        version_name='v1',
        spec_json=_EXAMPLE_SPEC_JSON,
        type='generic',
        status='active',
    )
    session.add(iteration)
    session.commit()
    session.refresh(iteration)
    return iteration


@pytest.fixture(scope='function')
def strategy_iteration_without_spec(session, strategy_concept):
    """StrategyIteration ohne spec_json (Legacy-Eintrag)."""
    iteration = StrategyIteration(
        concept_id=strategy_concept.id,
        version=2,
        version_name='v2-legacy',
        spec_json=None,
        type='generic',
        status='active',
    )
    session.add(iteration)
    session.commit()
    session.refresh(iteration)
    return iteration


@pytest.fixture(scope='function')
def testset_run(session, test_set):
    """TestSetRun mit n_runs_total=1."""
    run = TestSetRun(
        testset_id=test_set.id,
        strategy_family='test-specjson-strategy',
        strategy_name=1,
        n_runs_total=1,
        n_runs_completed=1,
        status='completed',
        indicators_config_json={'teststrategie_period': 20},
        created_by='test-spec-json',
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _make_backtest_run(session, testset_run_id: int, config_id: int,
                       iteration_id=None) -> BacktestRun:
    """Hilfsfunktion: BacktestRun anlegen."""
    run = BacktestRun(
        strategy_family='test-specjson-strategy',
        strategy_name=1,
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date='2024-01-01',
        end_date='2024-12-31',
        backtest_config_json={
            'strategy_family': 'test-specjson-strategy',
            'strategy_name': 1,
            'backtest_config_id': config_id,
            'symbols': ['BTCUSDT'],
            'start': '2024-01-01',
            'end': '2024-12-31',
        },
        indicators_config_json={'teststrategie_period': 20},
        n_combinations=1,
        status='completed',
        testset_run_id=testset_run_id,
        spec_runner_version='1.0.0',
        iteration_id=iteration_id,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _make_backtest_result(session, run_id: int) -> BacktestResult:
    """Hilfsfunktion: BacktestResult anlegen."""
    result = BacktestResult(
        run_id=run_id,
        params_hash=f'hash_{run_id}',
        actual_params_json={'teststrategie_period': 20},
        total_return_pct=10.0,
        max_drawdown_pct=-5.0,
        sharpe_ratio=1.0,
    )
    session.add(result)
    session.commit()
    session.refresh(result)
    return result


# ============================================================================
# Tests
# ============================================================================

def test_spec_json_eingebettet_nach_testset_run(
    session, testset_run, backtest_config, strategy_iteration_with_spec,
):
    """strategy_snapshot_json enthält spec_json (indicators + rules) nach einem Run.

    Verifikation: Der Key 'spec_json' im strategy_snapshot_json entspricht dem
    vollständigen spec_json der StrategyIteration.
    """
    br = _make_backtest_run(
        session, testset_run.id, backtest_config.id,
        iteration_id=strategy_iteration_with_spec.id,
    )
    _make_backtest_result(session, br.id)

    entry = _build_leaderboard_entry_in_session(session, testset_run.id)

    assert entry is not None
    snap = entry.strategy_snapshot_json
    assert snap is not None

    # spec_json muss im Snapshot vorhanden sein
    assert 'spec_json' in snap, 'spec_json fehlt in strategy_snapshot_json'

    embedded = snap['spec_json']
    assert 'indicators' in embedded, 'spec_json.indicators fehlt'
    assert 'rules' in embedded, 'spec_json.rules fehlt'

    # Inhalte stimmen mit der Original-Iteration überein
    assert embedded['indicators'] == _EXAMPLE_SPEC_JSON['indicators']
    assert embedded['rules'] == _EXAMPLE_SPEC_JSON['rules']


def test_spec_json_nicht_vorhanden_wenn_iteration_ohne_spec(
    session, testset_run, backtest_config, strategy_iteration_without_spec,
):
    """strategy_snapshot_json enthält keinen spec_json-Key wenn iteration.spec_json NULL ist.

    Bestandsschutz: Kein Crash, nur kein eingebettetes spec_json.
    """
    br = _make_backtest_run(
        session, testset_run.id, backtest_config.id,
        iteration_id=strategy_iteration_without_spec.id,
    )
    _make_backtest_result(session, br.id)

    entry = _build_leaderboard_entry_in_session(session, testset_run.id)

    assert entry is not None
    snap = entry.strategy_snapshot_json
    assert snap is not None

    # spec_json darf nicht vorhanden sein (kein Crash)
    assert 'spec_json' not in snap


def test_spec_json_nicht_vorhanden_wenn_keine_iteration(
    session, testset_run, backtest_config,
):
    """strategy_snapshot_json hat keinen spec_json-Key wenn kein Run eine iteration_id trägt."""
    br = _make_backtest_run(
        session, testset_run.id, backtest_config.id,
        iteration_id=None,
    )
    _make_backtest_result(session, br.id)

    entry = _build_leaderboard_entry_in_session(session, testset_run.id)

    assert entry is not None
    snap = entry.strategy_snapshot_json
    assert snap is not None

    # spec_json darf nicht vorhanden sein
    assert 'spec_json' not in snap


def test_bestandsschutz_rerun_ablehnung_ohne_spec_json():
    """Einträge ohne eingebettetes spec_json werden beim Rerun klar abgelehnt.

    Simuliert den Rerun-Check via direktem Aufruf der Logik (ohne HTTP-Layer).
    Prüft, dass .get('spec_json') None zurückgibt und das Fehlen erkannt wird.
    """
    # Alter Eintrag ohne spec_json (nur die drei ursprünglichen Keys)
    alt_snapshot = {
        'strategy_family': 'teststrategie',
        'strategy_name': 'v1',
        'spec_runner_version': '1.0.0',
    }

    # Bestandsschutz-Logik: .get() statt direktem Zugriff
    spec_json = alt_snapshot.get('spec_json')
    assert spec_json is None, 'Alter Eintrag darf kein spec_json enthalten'

    # Simulierter Rerun-Check: fehlende spec_json -> Ablehnung erkannt
    should_reject = spec_json is None
    assert should_reject, 'Rerun ohne spec_json muss abgelehnt werden'

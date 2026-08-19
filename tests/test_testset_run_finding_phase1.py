"""Unit-Tests für Phase 1 des Befunds am Testset-Lauf (Ticket 56).

Geprüft wird ausschließlich, was Phase 1 leistet:
  - Anlage mit Kontext und Soll aus dem Konzept-Schnappschuss
  - Konzept ohne Ziel: Soll bleibt leer, der Grund steht dabei
  - Schnappschuss-Semantik: eine spätere Änderung der Quelle ändert den Befund nicht
  - Schreibschutz: Kontext und Soll sind nach der Anlage unveränderlich
  - Phase-2- und Deutungs-Felder bleiben schreibbar
  - Ein zweiter Lauf erzeugt einen zweiten Befund (nie überschreiben)
  - Der Befund überlebt das Löschen des Testset-Laufs
  - Kein Verdict-Feld im Schema
  - Der Start-Endpunkt legt den Befund tatsächlich an (Verdrahtungs-Test)

Die reinen Datensatz-Tests laufen gegen SQLite (test_session), die Verdrahtungs-
Tests des Endpunkts gegen die PostgreSQL-Test-DB (session/db_engine).
"""

import os
import sys
import types
from datetime import datetime

import pytest
from sqlalchemy.orm import sessionmaker

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from services.api.routes.api_testset_runs import TestSetRunIn, start_testset_run
from services.api.utils.best_criteria_labels import BEST_CRITERIA_LABELS
from user_data.utils.database.models import (
    BacktestConfig,
    FindingImmutableError,
    IndicatorConfig,
    StrategyConcept,
    StrategyIteration,
    TestSet,
    TestSetRun,
    TestSetRunFinding,
)
from user_data.utils.database.repository_findings import (
    GOAL_MISSING_REASON,
    create_testset_run_finding,
    get_testset_run_finding,
)


@pytest.fixture
def goal_snapshot() -> dict:
    """Beispielhaftes Entwicklungsziel eines Konzepts (frei formuliert, kein festes Schema)."""
    return {'sharpe_min': 1.2, 'note': 'Beispielziel'}


@pytest.fixture
def best_criteria() -> list:
    """Die vier Bestwert-Kriterien als stabile Keys aus der Single Source."""
    return list(BEST_CRITERIA_LABELS.keys())


@pytest.fixture
def testset_run(test_session) -> TestSetRun:
    """Ein Testset-Lauf, an dem der Befund hängt (lose Referenz, kein FK)."""
    run = TestSetRun(
        testset_id=7,
        strategy_family='teststrategie',
        strategy_name='1',
        n_runs_total=4,
        indicators_config_json={},
        status='queued',
    )
    test_session.add(run)
    test_session.commit()
    test_session.refresh(run)
    return run


def _create(test_session, testset_run, best_criteria, **overrides):
    """Legt einen Befund mit sinnvollen Vorgaben an; overrides überschreiben einzeln."""
    kwargs = dict(
        testset_run_id=testset_run.id,
        iteration_id=42,
        concept_id=5,
        testset_id=7,
        indicator_config_id=13,
        spec_runner_version='4.0.0',
        goal_snapshot=None,
        best_criteria=best_criteria,
        planned_n_runs=4,
        planned_combos_per_run=25,
    )
    kwargs.update(overrides)
    return create_testset_run_finding(session=test_session, **kwargs)


def test_creates_finding_with_context_and_goal(
    test_session, testset_run, goal_snapshot, best_criteria,
):
    """Die Anlage schreibt Kontext und Soll als echte Spalten fort."""
    finding = _create(
        test_session, testset_run, best_criteria, goal_snapshot=goal_snapshot,
    )

    assert finding.testset_run_id == testset_run.id
    assert finding.iteration_id == 42
    assert finding.concept_id == 5
    assert finding.testset_id == 7
    assert finding.indicator_config_id == 13
    assert finding.spec_runner_version == '4.0.0'
    assert isinstance(finding.created_at, datetime)
    assert finding.goal_snapshot_json == goal_snapshot
    assert finding.goal_missing_reason is None
    assert finding.best_criteria_json == best_criteria
    assert finding.planned_n_runs == 4
    assert finding.planned_combos_per_run == 25
    assert finding.planned_combos_total == 100


def test_missing_goal_leaves_reason_and_does_not_raise(
    test_session, testset_run, best_criteria,
):
    """Konzept ohne Ziel: Soll bleibt leer, der Grund steht dabei — kein Fehler."""
    finding = _create(test_session, testset_run, best_criteria, goal_snapshot=None)

    assert finding.goal_snapshot_json is None
    assert finding.goal_missing_reason == GOAL_MISSING_REASON


def test_unavailable_grid_size_keeps_reason_instead_of_zero(
    test_session, testset_run, best_criteria,
):
    """Nicht ermittelbare Rastergröße bleibt leer mit Grund, nicht 0."""
    finding = _create(
        test_session, testset_run, best_criteria,
        planned_combos_per_run=None,
        planned_grid_reason='Rastergröße nicht ermittelbar: Testgrund',
    )

    assert finding.planned_combos_per_run is None
    assert finding.planned_combos_total is None
    assert finding.planned_grid_reason == 'Rastergröße nicht ermittelbar: Testgrund'


def test_goal_snapshot_is_decoupled_from_source(
    test_session, testset_run, goal_snapshot, best_criteria,
):
    """Eine spätere Änderung der Quelle ändert den bestehenden Befund nicht."""
    finding = _create(
        test_session, testset_run, best_criteria, goal_snapshot=goal_snapshot,
    )
    finding_id = finding.id

    # Quelle nachträglich verändern (so wie ein Edit am Konzept es täte)
    goal_snapshot['sharpe_min'] = 99
    goal_snapshot['nachtraeglich'] = True
    test_session.expire_all()

    reloaded = get_testset_run_finding(test_session, finding_id)
    assert reloaded.goal_snapshot_json == {'sharpe_min': 1.2, 'note': 'Beispielziel'}


@pytest.mark.parametrize(
    'field, new_value',
    [
        ('goal_snapshot_json', {'sharpe_min': 0.1}),
        ('best_criteria_json', ['max_return']),
        ('planned_combos_per_run', 1),
        ('planned_combos_total', 1),
        ('planned_n_runs', 1),
        ('iteration_id', 999),
        ('testset_id', 999),
        ('indicator_config_id', 999),
        ('spec_runner_version', '0.0.1'),
    ],
)
def test_phase1_fields_are_immutable(
    test_session, testset_run, goal_snapshot, best_criteria, field, new_value,
):
    """Jede Änderung an Kontext oder Soll wird mit sichtbarem Fehler abgewiesen."""
    finding = _create(
        test_session, testset_run, best_criteria, goal_snapshot=goal_snapshot,
    )

    setattr(finding, field, new_value)
    with pytest.raises(FindingImmutableError) as exc:
        test_session.commit()
    assert field in str(exc.value)

    test_session.rollback()
    assert getattr(get_testset_run_finding(test_session, finding.id), field) != new_value


def test_phase2_and_interpretation_stay_writable(
    test_session, testset_run, best_criteria,
):
    """Ist-Werte und Deutung bleiben schreibbar — der Schutz gilt nur für Phase 1."""
    finding = _create(test_session, testset_run, best_criteria)

    finding.scope_json = {'n_runs': 4}
    finding.candidates_json = {'max_return': {'sharpe': 1.4}}
    finding.robustness_json = {'dsr': 0.4, 'n': 100, 'sr0': 2.8}
    finding.benchmarks_json = {'buy_and_hold': 0.12}
    finding.warnings_json = {'trades_below_floor': True}
    finding.closed_at = datetime.now()
    finding.interpretation_text = 'Nur eine Deutung, keine Messung.'
    finding.interpretation_at = datetime.now()
    test_session.commit()

    reloaded = get_testset_run_finding(test_session, finding.id)
    assert reloaded.scope_json == {'n_runs': 4}
    assert reloaded.interpretation_text == 'Nur eine Deutung, keine Messung.'
    assert reloaded.closed_at is not None


def test_second_run_creates_second_finding(
    test_session, testset_run, goal_snapshot, best_criteria,
):
    """Ein erneuter Lauf legt einen zweiten Befund an, der erste bleibt unverändert."""
    first = _create(
        test_session, testset_run, best_criteria, goal_snapshot=goal_snapshot,
    )
    first_id = first.id
    second = _create(
        test_session, testset_run, best_criteria, goal_snapshot={'sharpe_min': 2.0},
    )

    assert second.id != first_id
    assert get_testset_run_finding(test_session, first_id).goal_snapshot_json == goal_snapshot
    assert test_session.query(TestSetRunFinding).count() == 2


def test_finding_survives_deletion_of_testset_run(
    test_session, testset_run, goal_snapshot, best_criteria,
):
    """Wird der Testset-Lauf gelöscht, bleibt der Befund mit seinem Kontext lesbar."""
    finding = _create(
        test_session, testset_run, best_criteria, goal_snapshot=goal_snapshot,
    )
    finding_id = finding.id

    test_session.delete(testset_run)
    test_session.commit()

    reloaded = get_testset_run_finding(test_session, finding_id)
    assert reloaded is not None
    assert reloaded.iteration_id == 42
    assert reloaded.testset_id == 7
    assert reloaded.goal_snapshot_json == goal_snapshot
    assert reloaded.created_at is not None


def test_schema_has_no_verdict_column():
    """Kein passed/score/rank/verdict im Schema — der Befund bewertet nicht."""
    columns = {c.name for c in TestSetRunFinding.__table__.columns}
    forbidden = {'passed', 'verdict', 'score', 'total_score', 'rank', 'rating', 'status'}
    assert not (columns & forbidden)


def test_payload_schema_has_no_manual_goal_input():
    """Das Start-Schema nimmt kein Soll entgegen — genau das wäre der Drift-Kanal."""
    fields = set(TestSetRunIn.model_fields)
    # GEÄNDERT: Ticket 102 — 'indicators' ist das inline übergebene Indikator-Raster,
    # kein Soll. Die Aussage des Tests bleibt: kein Feld trägt eine Zielvorgabe herein.
    assert fields == {'testset_id', 'iteration_id', 'indicator_config_id', 'indicators', 'metrics'}


# ============================================================================
# Verdrahtung: der Start-Endpunkt legt den Befund an
# (PostgreSQL-Test-DB; rq und create_backtest_run sind ersetzt, es wird nichts gerechnet)
# ============================================================================

# Stop-Sweep über drei Werte — zählbar ohne Indikator-Factory und damit ohne vbt.
_ROUTE_INDICATORS = {
    '_stops': {
        'tp_stop': {
            'type': 'arange', 'start': 0.01, 'stop': 0.031, 'step': 0.01,
            'dtype': 'float64',
        },
    },
}
_ROUTE_COMBOS_PER_RUN = 3


@pytest.fixture
def route_fixtures(session, db_engine, monkeypatch):
    """Legt Konzept, Iteration, IndicatorConfig, BacktestConfigs und Testset an.

    Ersetzt zugleich alles, was echte Infrastruktur bräuchte: rq (nicht im venv),
    die Redis-Verbindung und create_backtest_run. Der Endpunkt läuft dadurch bis
    zum Ende durch, ohne einen einzigen Backtest zu starten.

    Returns:
        Dict mit den IDs der angelegten Objekte.
    """
    concept = StrategyConcept(slug='befund-test', name='Befund-Test')
    session.add(concept)
    session.commit()
    iteration = StrategyIteration(concept_id=concept.id, version=1, type='generic')
    ind_config = IndicatorConfig(name='Befund-Test-IC', config_json=_ROUTE_INDICATORS)
    bt_configs = [
        BacktestConfig(
            name=f'Befund-Test-BC-{i}', symbol='BTCUSDT',
            start='2024-01-01', end='2024-12-31',
            ohlc_start='2023-12-01', ohlc_end='2025-01-01',
        )
        for i in range(2)
    ]
    session.add_all([iteration, ind_config, *bt_configs])
    session.commit()
    testset = TestSet(
        name='Befund-Test-TS',
        backtest_config_ids_json=[bc.id for bc in bt_configs],
    )
    session.add(testset)
    session.commit()

    fake_rq = types.ModuleType('rq')
    fake_rq.Queue = lambda *args, **kwargs: types.SimpleNamespace(
        enqueue=lambda *a, **kw: None,
    )
    monkeypatch.setitem(sys.modules, 'rq', fake_rq)
    monkeypatch.setattr(
        'services.api.redis_conn.get_redis_connection', lambda: None,
    )
    monkeypatch.setattr(
        'services.api.routes.api_testset_runs.create_backtest_run',
        lambda **kwargs: 1,
    )
    session_factory = sessionmaker(bind=db_engine)
    monkeypatch.setattr(
        'services.api.routes.api_testset_runs.get_session', session_factory,
    )

    return {
        'concept_id': concept.id,
        'iteration_id': iteration.id,
        'indicator_config_id': ind_config.id,
        'testset_id': testset.id,
    }


def test_start_endpoint_creates_finding_with_goal_snapshot(
    session, route_fixtures, goal_snapshot, best_criteria,
):
    """Ein gestarteter Lauf erzeugt sofort einen Befund mit Kontext und Soll."""
    concept = session.get(StrategyConcept, route_fixtures['concept_id'])
    concept.goal_json = goal_snapshot
    session.commit()

    response = start_testset_run(TestSetRunIn(
        testset_id=route_fixtures['testset_id'],
        iteration_id=route_fixtures['iteration_id'],
        indicator_config_id=route_fixtures['indicator_config_id'],
    ))
    assert response.status_code == 200

    finding = session.query(TestSetRunFinding).one()
    assert finding.iteration_id == route_fixtures['iteration_id']
    assert finding.concept_id == route_fixtures['concept_id']
    assert finding.testset_id == route_fixtures['testset_id']
    assert finding.indicator_config_id == route_fixtures['indicator_config_id']
    assert finding.testset_run_id is not None
    assert finding.spec_runner_version
    assert finding.goal_snapshot_json == goal_snapshot
    assert finding.goal_missing_reason is None
    assert finding.best_criteria_json == best_criteria
    assert finding.planned_n_runs == 2
    assert finding.planned_combos_per_run == _ROUTE_COMBOS_PER_RUN
    assert finding.planned_combos_total == _ROUTE_COMBOS_PER_RUN * 2
    # Der Befund entsteht, bevor gerechnet wird — der Lauf ist noch nicht fertig.
    assert finding.closed_at is None


def test_start_endpoint_without_goal_is_not_blocked(session, route_fixtures):
    """Konzept ohne Ziel: Befund mit leerem Soll und Grund, Start läuft durch."""
    response = start_testset_run(TestSetRunIn(
        testset_id=route_fixtures['testset_id'],
        iteration_id=route_fixtures['iteration_id'],
        indicator_config_id=route_fixtures['indicator_config_id'],
    ))
    assert response.status_code == 200

    finding = session.query(TestSetRunFinding).one()
    assert finding.goal_snapshot_json is None
    assert finding.goal_missing_reason == GOAL_MISSING_REASON


def test_start_endpoint_twice_creates_two_findings(session, route_fixtures):
    """Ein erneuter Lauf erzeugt einen zweiten Befund statt den ersten zu überschreiben."""
    payload = TestSetRunIn(
        testset_id=route_fixtures['testset_id'],
        iteration_id=route_fixtures['iteration_id'],
        indicator_config_id=route_fixtures['indicator_config_id'],
    )
    assert start_testset_run(payload).status_code == 200
    assert start_testset_run(payload).status_code == 200

    findings = (
        session.query(TestSetRunFinding)
        .order_by(TestSetRunFinding.id.asc())
        .all()
    )
    assert len(findings) == 2
    assert findings[0].testset_run_id != findings[1].testset_run_id

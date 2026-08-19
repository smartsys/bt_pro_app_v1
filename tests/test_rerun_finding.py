"""Tests für den Befund am Leaderboard-Rerun (direkter Weg).

Geprüft wird, was `finding_aggregation.py` an neuer Logik mitbringt — ohne den
schweren HTTP-Pfad `rerun_from_snapshot` selbst auszuführen (der rechnet echte
Strategien über vbt/OHLC, dafür gibt es in diesem Projekt bewusst keine Unit-Tests,
siehe `test_leaderboard_spec_json_snapshot.py`):

  - `resolve_iteration_for_rerun_finding` — löst die Iteration zuerst über die im
    Snapshot eingefrorene `iteration_id` (direkter Weg); nur wenn die
    fehlt oder ins Leere läuft, greift der Reserve-Weg über
    LeaderboardEntry.indicator_config_id -> IndicatorConfig.strategy_iteration_id
    -> StrategyIteration -> StrategyConcept. Jede Bruchstelle beider
    Wege bleibt sichtbar (WARNING-Log), bricht aber nichts ab.
  - `open_finding_for_testset_run` — die gemeinsame Phase-1-Implementierung, die
    jetzt sowohl der reguläre Startweg als auch der Rerun aufrufen.
  - Drift-Test: beide Startwege importieren dieselbe Funktion, keine zweite
    Phase-1-Implementierung.

Die reinen Logik-Tests laufen gegen SQLite (test_session), analog zu
tests/test_testset_run_finding_phase1.py.
"""

import logging

import pytest

from services.api.utils.finding_aggregation import (
    open_finding_for_testset_run,
    resolve_iteration_for_rerun_finding,
)
from user_data.utils.database.models import (
    IndicatorConfig,
    StrategyConcept,
    StrategyIteration,
    TestSetRunFinding,
)
from user_data.utils.database.repository_findings import GOAL_MISSING_REASON

# Stop-Sweep über drei Werte — zählbar ohne Indikator-Factory-Abhängigkeiten, analog
# zur Fixture in test_testset_run_finding_phase1.py.
_INDICATORS_JSON = {
    '_stops': {
        'tp_stop': {
            'type': 'arange', 'start': 0.01, 'stop': 0.031, 'step': 0.01,
            'dtype': 'float64',
        },
    },
}
_COMBOS_PER_RUN = 3


# ============================================================================
# resolve_iteration_for_rerun_finding
# ============================================================================

@pytest.fixture
def concept_with_goal(test_session) -> StrategyConcept:
    """Konzept mit gesetztem Entwicklungsziel."""
    concept = StrategyConcept(
        slug='rerun-test-konzept', name='Rerun-Test-Konzept',
        goal_json={'sharpe_min': 1.2},
    )
    test_session.add(concept)
    test_session.commit()
    test_session.refresh(concept)
    return concept


@pytest.fixture
def iteration_of_concept(test_session, concept_with_goal) -> StrategyIteration:
    """Iteration des Test-Konzepts."""
    iteration = StrategyIteration(concept_id=concept_with_goal.id, version=1, type='generic')
    test_session.add(iteration)
    test_session.commit()
    test_session.refresh(iteration)
    return iteration


@pytest.fixture
def indicator_config_linked(test_session, iteration_of_concept) -> IndicatorConfig:
    """IndicatorConfig mit loser Referenz auf die Iteration (wie beim Kopieren einer Iteration gesetzt)."""
    ic = IndicatorConfig(
        name='Rerun-Test-IC', config_json=_INDICATORS_JSON,
        strategy_iteration_id=iteration_of_concept.id,
    )
    test_session.add(ic)
    test_session.commit()
    test_session.refresh(ic)
    return ic


def test_resolves_iteration_concept_and_goal_snapshot(
    test_session, indicator_config_linked, iteration_of_concept, concept_with_goal,
):
    """Die volle Kette (IndicatorConfig -> Iteration -> Konzept) löst korrekt auf."""
    iteration_id, concept_id, goal_snapshot = resolve_iteration_for_rerun_finding(
        test_session, indicator_config_linked.id, entry_id=1,
    )

    assert iteration_id == iteration_of_concept.id
    assert concept_id == concept_with_goal.id
    assert goal_snapshot == {'sharpe_min': 1.2}


def test_missing_indicator_config_id_is_unresolvable(test_session, caplog):
    """Ohne indicator_config_id (z.B. Alt-Snapshot) bleibt die Iteration unauflösbar — sichtbar geloggt."""
    with caplog.at_level(logging.WARNING):
        result = resolve_iteration_for_rerun_finding(test_session, None, entry_id=42)

    assert result == (None, None, None)
    assert any(
        'Iteration nicht auflösbar' in r.message and 'Entry #42' in r.message
        for r in caplog.records
    )
    assert all(r.levelno == logging.WARNING for r in caplog.records if 'Iteration nicht auflösbar' in r.message)


def test_indicator_config_not_found_is_unresolvable(test_session, caplog):
    """Zeigt indicator_config_id auf keine existierende Zeile, bleibt die Iteration unauflösbar."""
    with caplog.at_level(logging.WARNING):
        result = resolve_iteration_for_rerun_finding(test_session, 999999, entry_id=7)

    assert result == (None, None, None)
    assert any('Iteration nicht auflösbar' in r.message for r in caplog.records)


def test_indicator_config_without_iteration_link_is_unresolvable(test_session, caplog):
    """IndicatorConfig ohne strategy_iteration_id (nie verknüpft) bleibt unauflösbar."""
    ic = IndicatorConfig(name='Unlinked-IC', config_json=_INDICATORS_JSON)
    test_session.add(ic)
    test_session.commit()
    test_session.refresh(ic)

    with caplog.at_level(logging.WARNING):
        result = resolve_iteration_for_rerun_finding(test_session, ic.id, entry_id=8)

    assert result == (None, None, None)
    assert any('Iteration nicht auflösbar' in r.message for r in caplog.records)


def test_dangling_iteration_reference_is_unresolvable(test_session, caplog):
    """strategy_iteration_id zeigt auf eine gelöschte Iteration — lose Referenz, kein Crash."""
    ic = IndicatorConfig(
        name='Dangling-IC', config_json=_INDICATORS_JSON, strategy_iteration_id=999999,
    )
    test_session.add(ic)
    test_session.commit()
    test_session.refresh(ic)

    with caplog.at_level(logging.WARNING):
        result = resolve_iteration_for_rerun_finding(test_session, ic.id, entry_id=9)

    assert result == (None, None, None)
    assert any('Iteration nicht auflösbar' in r.message for r in caplog.records)


def test_iteration_without_goal_resolves_with_empty_snapshot(test_session):
    """Konzept ohne goal_json: Iteration löst trotzdem auf, das Soll bleibt leer."""
    concept = StrategyConcept(slug='rerun-test-ohne-ziel', name='Ohne Ziel')
    test_session.add(concept)
    test_session.commit()
    iteration = StrategyIteration(concept_id=concept.id, version=1, type='generic')
    test_session.add(iteration)
    test_session.commit()
    ic = IndicatorConfig(
        name='Ohne-Ziel-IC', config_json=_INDICATORS_JSON,
        strategy_iteration_id=iteration.id,
    )
    test_session.add(ic)
    test_session.commit()
    test_session.refresh(ic)

    iteration_id, concept_id, goal_snapshot = resolve_iteration_for_rerun_finding(
        test_session, ic.id, entry_id=10,
    )

    assert iteration_id == iteration.id
    assert concept_id == concept.id
    assert goal_snapshot is None


def test_resolves_iteration_directly_from_snapshot_id(
    test_session, iteration_of_concept, concept_with_goal,
):
    """Direkter Weg: die eingefrorene iteration_id löst ohne IndicatorConfig auf."""
    iteration_id, concept_id, goal_snapshot = resolve_iteration_for_rerun_finding(
        test_session, None, entry_id=20, snapshot_iteration_id=iteration_of_concept.id,
    )

    assert iteration_id == iteration_of_concept.id
    assert concept_id == concept_with_goal.id
    assert goal_snapshot == {'sharpe_min': 1.2}


def test_falls_back_to_indicator_config_when_snapshot_iteration_is_dangling(
    test_session, indicator_config_linked, iteration_of_concept, concept_with_goal,
):
    """Reserve-Weg: zeigt die Snapshot-iteration_id ins Leere, greift der Config-Weg."""
    iteration_id, concept_id, goal_snapshot = resolve_iteration_for_rerun_finding(
        test_session, indicator_config_linked.id, entry_id=21,
        snapshot_iteration_id=999999,
    )

    assert iteration_id == iteration_of_concept.id
    assert concept_id == concept_with_goal.id
    assert goal_snapshot == {'sharpe_min': 1.2}


def test_both_resolution_paths_dead_is_unresolvable(test_session, caplog):
    """Weder Snapshot-iteration_id noch IndicatorConfig auflösbar — sichtbare Meldung, kein Crash."""
    with caplog.at_level(logging.WARNING):
        result = resolve_iteration_for_rerun_finding(
            test_session, 999999, entry_id=22, snapshot_iteration_id=999998,
        )

    assert result == (None, None, None)
    assert any(
        'Iteration nicht auflösbar' in r.message and 'Entry #22' in r.message
        for r in caplog.records
    )


# ============================================================================
# open_finding_for_testset_run — gemeinsame Phase-1-Implementierung
# ============================================================================

def test_open_finding_creates_finding_with_goal_and_counted_combos(test_session):
    """Legt einen Befund mit Soll-Schnappschuss und gezählter Rastergröße an."""
    finding = open_finding_for_testset_run(
        session=test_session,
        testset_run_id=101,
        iteration_id=5,
        concept_id=3,
        testset_id=7,
        indicator_config_id=13,
        indicators_json=_INDICATORS_JSON,
        spec_runner_version='4.0.0',
        goal_snapshot={'sharpe_min': 1.0},
        planned_n_runs=2,
    )

    assert finding.testset_run_id == 101
    assert finding.iteration_id == 5
    assert finding.concept_id == 3
    assert finding.testset_id == 7
    assert finding.indicator_config_id == 13
    assert finding.spec_runner_version == '4.0.0'
    assert finding.goal_snapshot_json == {'sharpe_min': 1.0}
    assert finding.goal_missing_reason is None
    assert finding.planned_n_runs == 2
    assert finding.planned_combos_per_run == _COMBOS_PER_RUN
    assert finding.planned_combos_total == _COMBOS_PER_RUN * 2


def test_open_finding_without_goal_sets_reason(test_session):
    """Kein Soll-Schnappschuss: goal_missing_reason trägt den Grund, kein Fehler."""
    finding = open_finding_for_testset_run(
        session=test_session,
        testset_run_id=102,
        iteration_id=5,
        concept_id=3,
        testset_id=7,
        indicator_config_id=13,
        indicators_json=_INDICATORS_JSON,
        spec_runner_version='4.0.0',
        goal_snapshot=None,
        planned_n_runs=1,
    )

    assert finding.goal_snapshot_json is None
    assert finding.goal_missing_reason == GOAL_MISSING_REASON


def test_open_finding_uses_same_best_criteria_as_direct_call(test_session):
    """Die Bestwert-Kriterien kommen aus derselben Single Source wie beim direkten Aufruf."""
    from services.api.utils.best_criteria_labels import BEST_CRITERIA_LABELS

    finding = open_finding_for_testset_run(
        session=test_session,
        testset_run_id=103,
        iteration_id=5,
        concept_id=3,
        testset_id=7,
        indicator_config_id=13,
        indicators_json=_INDICATORS_JSON,
        spec_runner_version='4.0.0',
        goal_snapshot=None,
        planned_n_runs=1,
    )

    assert finding.best_criteria_json == list(BEST_CRITERIA_LABELS.keys())


def test_open_finding_persists_via_test_session(test_session):
    """Der Befund ist über die übergebene Session lesbar — keine eigene Session im Hintergrund."""
    finding = open_finding_for_testset_run(
        session=test_session,
        testset_run_id=104,
        iteration_id=5,
        concept_id=3,
        testset_id=7,
        indicator_config_id=13,
        indicators_json=_INDICATORS_JSON,
        spec_runner_version='4.0.0',
        goal_snapshot=None,
        planned_n_runs=1,
    )

    reloaded = (
        test_session.query(TestSetRunFinding)
        .filter(TestSetRunFinding.id == finding.id)
        .one()
    )
    assert reloaded.testset_run_id == 104


# ============================================================================
# Drift-Test: keine zweite Phase-1-Implementierung
# ============================================================================

def test_both_start_paths_share_the_same_phase1_function():
    """start_testset_run und rerun_from_snapshot rufen dieselbe Funktion auf — kein Drift."""
    import services.api.routes.api_testset_runs as testset_runs_route

    assert testset_runs_route.open_finding_for_testset_run is open_finding_for_testset_run

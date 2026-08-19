"""Unit-Tests für Phase 2 des Befunds am Testset-Lauf.

Geprüft wird, was der Abschluss leistet:
  - Die fünf Ist-Gruppen werden aus dem gebaut, was die Läufe geschrieben haben
  - Die Rastergröße kommt aus n_combinations, nicht aus der Zahl der Results
  - Die vier Bestwert-Kandidaten stehen nebeneinander, ohne Rangfolge
  - Bänder und Trade-Floor entsprechen der kanonischen Bestwert-Definition
  - Die DSR steht nie ohne N und SR0
  - Fehlende Werte bleiben leer und tragen ihren Grund (N_eff, Benchmark-Linie,
    abgewählte Metrik-Gruppen)
  - Der Befund schließt genau einmal; ein zweiter Ist-Schreibvorgang wird abgewiesen
  - Die Deutung bleibt nach dem Schließen schreibbar

Die reinen Datensatz-Tests laufen gegen SQLite (test_session), die Aggregations-Tests
gegen die PostgreSQL-Test-DB (session/db_engine) — sie brauchen var_samp und
percentile_cont.
"""

import hashlib
import logging
import os
import sys
from datetime import datetime

import pytest
from sqlalchemy.orm import sessionmaker

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from services.api.utils.best_criteria_labels import BEST_CRITERIA_LABELS
from services.api.utils.best_criteria_selection import PF_MIN_TRADES
from services.api.utils.finding_aggregation import (
    BENCHMARK_LINE_MISSING_REASON,
    HOLDOUT_MISSING_REASON,
    build_ist_groups,
    build_warnings,
    close_finding_for_testset_run,
)
from services.api.utils.finding_robustness import N_EFF_MISSING_REASON
from user_data.utils.database.models import (
    BacktestParam,
    BacktestResult,
    BacktestRun,
    FindingImmutableError,
    TestSetRun,
    TestSetRunFinding,
)
from user_data.utils.database.repository_findings import (
    close_testset_run_finding,
    create_testset_run_finding,
    get_finding_for_testset_run,
    get_testset_run_finding,
)
from user_data.utils.metrics.deflated_sharpe import noise_floor_sr0

# Ein kleines Raster, dessen Sieger je Kriterium ein anderes Result ist — damit ein
# vertauschtes Kriterium sofort auffällt.
#   Spalten: param, total_return_pct, sharpe_ratio, win_rate_pct, profit_factor,
#            total_trades, max_drawdown_pct, deflated_sharpe_ratio
_GRID = (
    (1.0, 200.0, 0.80, 45.0, 9.0, 5, -10.0, 0.51),
    (2.0, 90.0, 1.50, 100.0, 3.0, 40, -20.0, 0.62),
    (3.0, 150.0, 1.45, 82.0, 2.5, 55, -25.0, 0.60),
    (4.0, 10.0, 0.50, 40.0, 1.2, 70, -30.0, 0.40),
    (5.0, -20.0, -0.30, 20.0, 0.7, 80, -40.0, 0.10),
)
# Rastergröße des Laufs — bewusst größer als die Zahl der angelegten Results, damit
# der Unterschied zwischen n_combinations und count(*) geprüft werden kann.
_N_COMBINATIONS = 9
_BENCHMARK_RETURN = 40.0


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def ist_groups() -> dict:
    """Die fünf Ist-Gruppen in minimaler Form (Inhalt hier nicht der Prüfgegenstand)."""
    return {
        'scope': {'n_runs': 2, 'n_eff': None, 'n_eff_reason': N_EFF_MISSING_REASON},
        'candidates': {'per_run': []},
        'robustness': {'dsr': [{'run_id': 1, 'n': 9, 'sr0': 1.13}]},
        'benchmarks': {'concept_benchmark_line': None},
        'warnings': {'items': [], 'not_evaluated': []},
    }


@pytest.fixture
def testset_run(test_session) -> TestSetRun:
    """Ein Testset-Lauf, an dem der Befund hängt (lose Referenz, kein FK)."""
    run = TestSetRun(
        testset_id=7,
        strategy_family='teststrategie',
        strategy_name='1',
        n_runs_total=2,
        indicators_config_json={},
        status='completed',
    )
    test_session.add(run)
    test_session.commit()
    test_session.refresh(run)
    return run


@pytest.fixture
def open_finding(test_session, testset_run) -> TestSetRunFinding:
    """Ein offener Befund aus Phase 1."""
    return create_testset_run_finding(
        session=test_session,
        testset_run_id=testset_run.id,
        iteration_id=42,
        concept_id=5,
        testset_id=7,
        indicator_config_id=13,
        spec_runner_version='4.0.0',
        goal_snapshot={'sharpe_min': 1.2},
        best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=2,
        planned_combos_per_run=_N_COMBINATIONS,
    )


def _add_run(session, testset_run_id: int, symbol: str, metrics_selection=None,
             offset: float = 0.0) -> BacktestRun:
    """Legt einen Backtest-Lauf mit dem Test-Raster an.

    Args:
        session: Aktive Session gegen die Test-DB.
        testset_run_id: Testset-Lauf, unter dem der Lauf hängt.
        symbol: Symbol des Laufs (ein Lauf = ein Symbol).
        metrics_selection: Metrik-Auswahl des Laufs (None = 'auto').
        offset: Additiver Versatz auf den Total Return, damit sich die Läufe in der
            Streuung über die Symbole unterscheiden.

    Returns:
        Der angelegte Lauf.
    """
    config: dict = {'symbols': [symbol]}
    if metrics_selection is not None:
        config['metrics'] = metrics_selection
    run = BacktestRun(
        strategy_family='teststrategie', strategy_name='1', symbol=symbol,
        exchange='binance', timeframe='4h',
        start_date=datetime(2020, 1, 1), end_date=datetime(2022, 1, 1),
        backtest_config_json=config, indicators_config_json={},
        n_combinations=_N_COMBINATIONS, ann_factor=2190.0,
        status='completed', testset_run_id=testset_run_id,
    )
    session.add(run)
    session.commit()

    for param, ret, sharpe, winrate, pf, trades, drawdown, dsr in _GRID:
        result = BacktestResult(
            run_id=run.id,
            params_hash=hashlib.md5(f'{run.id}-{param}'.encode()).hexdigest(),
            actual_params_json={'p': param},
            total_return_pct=ret + offset,
            benchmark_return_pct=_BENCHMARK_RETURN,
            sharpe_ratio=sharpe, win_rate_pct=winrate, profit_factor=pf,
            total_trades=trades, max_drawdown_pct=drawdown,
            deflated_sharpe_ratio=dsr, bar_count=4380, skew=0.1, kurtosis=3.2,
        )
        session.add(result)
        session.commit()
        session.add(BacktestParam(result_id=result.id, param_name='p', param_value=param))
        session.commit()
    return run


@pytest.fixture
def aggregated(session, db_engine):
    """Ein abgeschlossener Testset-Lauf mit zwei Läufen und den fertigen Ist-Gruppen."""
    testset_run = TestSetRun(
        testset_id=7, strategy_family='teststrategie', strategy_name='1',
        n_runs_total=2, indicators_config_json={}, status='completed',
    )
    session.add(testset_run)
    session.commit()
    _add_run(session, testset_run.id, 'BTCUSDT')
    _add_run(session, testset_run.id, 'ETHUSDT', offset=25.0)
    finding = create_testset_run_finding(
        session=session,
        testset_run_id=testset_run.id, iteration_id=42, concept_id=5, testset_id=7,
        indicator_config_id=13, spec_runner_version='4.0.0',
        goal_snapshot={'sharpe_min': 1.2},
        best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=2, planned_combos_per_run=_N_COMBINATIONS,
    )
    groups = build_ist_groups(db_engine, testset_run.id, finding)
    return {
        'testset_run_id': testset_run.id,
        'finding': finding,
        'groups': groups,
    }


# ============================================================================
# Schreibschutz: Phase 2 schließt genau einmal
# ============================================================================

def test_close_writes_ist_values_and_stamps_closed_at(
    test_session, open_finding, ist_groups,
):
    """Der Abschluss setzt alle fünf Ist-Gruppen und den Abschlusszeitpunkt."""
    closed = close_testset_run_finding(test_session, open_finding, **ist_groups)

    assert closed.closed_at is not None
    assert closed.scope_json == ist_groups['scope']
    assert closed.candidates_json == ist_groups['candidates']
    assert closed.robustness_json == ist_groups['robustness']
    assert closed.benchmarks_json == ist_groups['benchmarks']
    assert closed.warnings_json == ist_groups['warnings']
    # Vorgesehen, aber nicht befüllt: es gibt keinen markierten Holdout.
    assert closed.holdout_touched is None


def test_second_close_is_refused(test_session, open_finding, ist_groups):
    """Ein zweiter Ist-Schreibvorgang läuft mit sichtbarem Fehler auf."""
    close_testset_run_finding(test_session, open_finding, **ist_groups)
    first_scope = open_finding.scope_json

    changed = dict(ist_groups)
    changed['scope'] = {'n_runs': 99}
    with pytest.raises(FindingImmutableError) as exc:
        close_testset_run_finding(test_session, open_finding, **changed)
    assert 'geschlossen' in str(exc.value)

    test_session.expire_all()
    assert get_testset_run_finding(test_session, open_finding.id).scope_json == first_scope


@pytest.mark.parametrize(
    'field, new_value',
    [
        ('scope_json', {'n_runs': 99}),
        ('candidates_json', {'per_run': ['manipuliert']}),
        ('robustness_json', {'dsr': []}),
        ('benchmarks_json', {'concept_benchmark_line': 1.0}),
        ('warnings_json', {'items': []}),
        ('holdout_touched', True),
        ('closed_at', datetime(2030, 1, 1)),
    ],
)
def test_closed_finding_rejects_ist_field_change(
    test_session, open_finding, ist_groups, field, new_value,
):
    """Nach dem Schließen ist jedes Ist-Feld gesperrt — auch am ORM vorbei am Repository."""
    close_testset_run_finding(test_session, open_finding, **ist_groups)

    setattr(open_finding, field, new_value)
    with pytest.raises(FindingImmutableError) as exc:
        test_session.commit()
    assert field in str(exc.value)
    test_session.rollback()


def test_interpretation_stays_writable_after_close(
    test_session, open_finding, ist_groups,
):
    """Die Deutung wird nachträglich ergänzt, ohne die Zahlen zu berühren."""
    close_testset_run_finding(test_session, open_finding, **ist_groups)
    scope_before = open_finding.scope_json

    open_finding.interpretation_text = 'Deutung, keine Messung.'
    open_finding.interpretation_at = datetime.now()
    test_session.commit()

    reloaded = get_testset_run_finding(test_session, open_finding.id)
    assert reloaded.interpretation_text == 'Deutung, keine Messung.'
    assert reloaded.interpretation_at is not None
    assert reloaded.scope_json == scope_before


def test_get_finding_for_testset_run_returns_newest(
    test_session, testset_run, open_finding,
):
    """Bei mehreren Befunden am selben Lauf gewinnt der jüngste."""
    newer = create_testset_run_finding(
        session=test_session, testset_run_id=testset_run.id, iteration_id=42,
        concept_id=5, testset_id=7, indicator_config_id=13,
        spec_runner_version='4.0.0', goal_snapshot=None,
        best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=2, planned_combos_per_run=_N_COMBINATIONS,
    )
    found = get_finding_for_testset_run(test_session, testset_run.id)
    assert found.id == newer.id
    assert found.id != open_finding.id


def test_get_finding_for_testset_run_without_finding(test_session, testset_run):
    """Ohne Befund liefert die Suche None statt zu scheitern."""
    assert get_finding_for_testset_run(test_session, testset_run.id) is None


# ============================================================================
# Warnhinweise (reine Rechenlogik, ohne DB)
# ============================================================================

def test_trade_floor_warning_names_the_floor():
    """Ein Kandidat unter dem Trade-Floor erzeugt einen Warnhinweis mit Zahl und Floor."""
    per_run = [{
        'run_id': 1,
        'candidates': {
            'max_return': {'winner': {
                'result_id': 5, 'metrics': {'total_trades': 5},
            }},
        },
    }]
    result = build_warnings(per_run, {'dsr': []})

    floor_warnings = [w for w in result['items'] if w['code'] == 'trades_below_floor']
    assert len(floor_warnings) == 1
    assert floor_warnings[0]['total_trades'] == 5
    assert floor_warnings[0]['floor'] == PF_MIN_TRADES
    assert result['trade_floor'] == PF_MIN_TRADES


def test_grid_warning_when_noise_floor_beats_best_sharpe():
    """Liegt der beste Sharpe unter der Rauschlatte, steht das als Warnhinweis da."""
    robustness = {'dsr': [{
        'run_id': 1, 'n': 371943, 'sr0': 2.80, 'best_sharpe_ratio': 2.26,
    }]}
    result = build_warnings([], robustness)

    grid = [w for w in result['items'] if w['code'] == 'grid_raises_bar_above_result']
    assert len(grid) == 1
    assert grid[0]['n'] == 371943
    assert grid[0]['sr0'] == 2.80


def test_grid_warning_absent_when_result_beats_noise_floor():
    """Über der Latte gibt es keinen Warnhinweis — keine erfundene Beanstandung."""
    robustness = {'dsr': [{
        'run_id': 1, 'n': 9, 'sr0': 1.13, 'best_sharpe_ratio': 1.50,
    }]}
    assert build_warnings([], robustness)['items'] == []


def test_missing_values_are_listed_as_not_evaluated():
    """N_eff und Holdout stehen ausdrücklich als ungeprüft mit Grund da, statt zu fehlen."""
    not_evaluated = {
        entry['code']: entry['reason']
        for entry in build_warnings([], {'dsr': []})['not_evaluated']
    }
    assert not_evaluated['n_eff_low'] == N_EFF_MISSING_REASON
    assert not_evaluated['holdout_touched'] == HOLDOUT_MISSING_REASON


# ============================================================================
# Aggregation gegen die PostgreSQL-Test-DB
# ============================================================================

def test_scope_reports_grid_size_not_result_count(aggregated):
    """Die Rastergröße kommt aus n_combinations — count(*) der Results ist nicht N."""
    scope = aggregated['groups']['scope']

    assert scope['n_runs'] == 2
    assert scope['symbols'] == ['BTCUSDT', 'ETHUSDT']
    assert scope['n_symbols'] == 2
    assert scope['combos_total'] == 2 * _N_COMBINATIONS
    for entry in scope['runs']:
        assert entry['n_combinations'] == _N_COMBINATIONS
        assert entry['n_results'] == len(_GRID)
    # Beide Läufe teilen denselben Zeitraum — er steht genau einmal in der Liste.
    assert len(scope['periods']) == 1
    assert scope['periods'][0]['start'].startswith('2020-01-01')
    assert scope['periods'][0]['end'].startswith('2022-01-01')


def test_scope_leaves_n_eff_empty_with_reason(aggregated):
    """N_eff bleibt leer mit Grund — nicht 0 und nicht weggelassen."""
    scope = aggregated['groups']['scope']
    assert scope['n_eff'] is None
    assert scope['n_eff_reason'] == N_EFF_MISSING_REASON


def test_all_four_criteria_have_a_winner_without_ranking(aggregated):
    """Vier Kandidaten nebeneinander, in kanonischer Reihenfolge, ohne Gesamtsieger."""
    per_run = aggregated['groups']['candidates']['per_run']
    assert len(per_run) == 2
    for entry in per_run:
        assert list(entry['criteria'].keys()) == list(BEST_CRITERIA_LABELS.keys())
        for criterion in entry['criteria'].values():
            assert criterion['winner'] is not None
            assert criterion['reason'] is None
    # Kein Feld, das einen Gesamtsieger oder eine Note ausweisen würde.
    assert set(aggregated['groups']['candidates']) == {'hinweis', 'per_run'}


def test_criteria_follow_the_canonical_band_definition(aggregated):
    """Bänder und Trade-Floor entscheiden — nicht der blanke Höchstwert der Metrik."""
    criteria = aggregated['groups']['candidates']['per_run'][0]['criteria']

    # Max Total Return: das Result mit dem höchsten Return, ohne Trade-Floor.
    assert criteria['max_return']['winner']['metrics']['total_return_pct'] == 200.0
    # Win-Rate-Band: bestes Return im Band, nicht das Result mit der höchsten Win-Rate.
    assert criteria['winrate_band']['winner']['metrics']['win_rate_pct'] == 82.0
    assert criteria['winrate_band']['winner']['metrics']['total_return_pct'] == 150.0
    # Sharpe-Band: ebenso — bestes Return im Band, nicht der höchste Sharpe.
    assert criteria['sharpe_band']['winner']['metrics']['sharpe_ratio'] == 1.45
    # Profitfaktor: der höchste Wert mit mindestens 30 Trades (9.0 hat nur 5 Trades).
    assert criteria['pf_min30']['winner']['metrics']['profit_factor'] == 3.0
    assert criteria['pf_min30']['winner']['metrics']['total_trades'] == 40


def test_candidate_carries_all_six_metrics(aggregated):
    """Je Sieger stehen Sharpe, Return, Profitfaktor, Win-Rate, Trades und Drawdown."""
    winner = aggregated['groups']['candidates']['per_run'][0]['criteria']['max_return']['winner']
    assert set(winner['metrics']) == {
        'sharpe_ratio', 'total_return_pct', 'profit_factor', 'win_rate_pct',
        'total_trades', 'max_drawdown_pct',
    }
    assert all(value is not None for value in winner['metrics'].values())


def test_dsr_never_stands_without_n_and_sr0(aggregated):
    """Jede DSR-Angabe hängt an einem Objekt, das N und SR0 mitführt."""
    blocks = aggregated['groups']['robustness']['dsr']
    assert len(blocks) == 2
    for block in blocks:
        assert block['n'] == _N_COMBINATIONS
        assert block['sr0'] is not None
        assert block['sr0_reason'] is None
        assert block['best']['deflated_sharpe_ratio'] == 0.62
        assert {c['criterion'] for c in block['candidates']} == set(BEST_CRITERIA_LABELS)
        # Die DSR steht ausschließlich innerhalb dieses Objekts.
        for candidate in block['candidates']:
            assert candidate['deflated_sharpe_ratio'] is not None


def test_sr0_matches_the_shared_noise_floor_formula(aggregated, session):
    """SR0 kommt aus derselben Funktion, die auch in die DSR eingeht."""
    block = aggregated['groups']['robustness']['dsr'][0]
    expected = noise_floor_sr0(block['var_sharpe'], _N_COMBINATIONS)
    assert block['sr0'] == pytest.approx(expected)


def test_plateau_uses_one_grid_step_neighbourhood(aggregated):
    """Der Plateau-Score misst die Nachbarschaft der Sieger-Kombination."""
    plateau = aggregated['groups']['robustness']['plateau']
    assert len(plateau) == 2
    neighbourhoods = plateau[0]['neighborhoods']
    assert neighbourhoods
    for entry in neighbourhoods:
        assert entry['tolerance_steps'] == 1
        assert entry['summary']['n'] >= 1
        assert 'return_median' in entry['summary']


def test_symbol_dispersion_reports_spread_without_n_eff(aggregated):
    """Die Streuung über die Symbole steht da, N_eff bleibt leer mit Grund."""
    dispersion = aggregated['groups']['robustness']['symbol_dispersion']
    assert dispersion['n_symbols'] == 2
    assert dispersion['n_eff'] is None
    assert dispersion['n_eff_reason'] == N_EFF_MISSING_REASON
    # Der Versatz von 25 Punkten schlägt als Spanne zwischen den Symbolen durch.
    assert dispersion['spitzen_total_return_pct']['spanne'] == pytest.approx(25.0)


def test_benchmarks_compare_against_buy_and_hold(aggregated):
    """Buy-and-Hold steht je Lauf im selben Zeitraum neben dem besten Ergebnis."""
    benchmarks = aggregated['groups']['benchmarks']
    for entry in benchmarks['buy_and_hold']:
        assert entry['buy_and_hold_return_pct'] == _BENCHMARK_RETURN
        assert entry['buy_and_hold_reason'] is None
        assert entry['best_total_return_pct'] is not None
        assert entry['differenz_pct'] == pytest.approx(
            entry['best_total_return_pct'] - _BENCHMARK_RETURN,
        )


def test_concept_benchmark_line_is_empty_with_reason(aggregated):
    """Die Benchmark-Linie des Konzepts bleibt leer und sagt warum."""
    benchmarks = aggregated['groups']['benchmarks']
    assert benchmarks['concept_benchmark_line'] is None
    assert benchmarks['concept_benchmark_line_reason'] == BENCHMARK_LINE_MISSING_REASON


def test_goal_is_compared_without_being_evaluated(aggregated):
    """Das Soll steht dem Ist gegenüber — ohne Ableitung, ohne Bestanden-Aussage."""
    goal = aggregated['groups']['benchmarks']['goal']
    assert goal['soll'] == {'sharpe_min': 1.2}
    assert goal['soll_reason'] is None
    assert goal['ist_spanne_ueber_kandidaten']['sharpe_ratio']['max'] == 1.5
    assert 'bewertet' in goal['hinweis']


def test_trade_floor_warning_reaches_the_finding(aggregated):
    """Der Sieger mit 5 Trades erzeugt je Lauf einen Warnhinweis."""
    items = aggregated['groups']['warnings']['items']
    floor = [w for w in items if w['code'] == 'trades_below_floor']
    assert len(floor) == 2
    assert all(w['criterion'] == 'max_return' for w in floor)


def test_deselected_metric_group_leaves_reason_instead_of_zero(session, db_engine):
    """Abgewählte Metrik-Gruppen: betroffene Felder bleiben leer mit Grund."""
    testset_run = TestSetRun(
        testset_id=7, strategy_family='teststrategie', strategy_name='1',
        n_runs_total=1, indicators_config_json={}, status='completed',
    )
    session.add(testset_run)
    session.commit()
    # Nur die Gruppe 'drawdown' zusätzlich zu den Pflichtgruppen: 'trade_quality'
    # (Win-Rate, Profitfaktor) ist damit abgewählt.
    _add_run(session, testset_run.id, 'BTCUSDT', metrics_selection=['drawdown'])
    finding = create_testset_run_finding(
        session=session, testset_run_id=testset_run.id, iteration_id=42, concept_id=5,
        testset_id=7, indicator_config_id=13, spec_runner_version='4.0.0',
        goal_snapshot=None, best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=1, planned_combos_per_run=_N_COMBINATIONS,
    )

    groups = build_ist_groups(db_engine, testset_run.id, finding)
    criteria = groups['candidates']['per_run'][0]['criteria']

    for key in ('winrate_band', 'pf_min30'):
        assert criteria[key]['winner'] is None
        assert 'Metrik-Gruppe nicht gerechnet' in criteria[key]['reason']
    # Die übrigen Kriterien liefern weiterhin einen Sieger; nur seine Felder aus der
    # abgewählten Gruppe bleiben leer — nicht 0.
    winner = criteria['max_return']['winner']
    assert winner['metrics']['win_rate_pct'] is None
    assert winner['metrics']['profit_factor'] is None
    assert 'trade_quality' in winner['metrics_missing_reason']['win_rate_pct']
    assert winner['metrics']['max_drawdown_pct'] is not None
    assert groups['scope']['runs'][0]['metric_groups_skipped'] == [
        'benchmark', 'sqn_edge', 'tail_risk', 'trade_quality',
    ]


# ============================================================================
# Verdrahtung: beide Abschlusspfade rufen dieselbe Funktion
# ============================================================================

@pytest.fixture
def wired(monkeypatch, db_engine):
    """Verdrahtet den Abschluss-Einstieg auf die Test-DB statt auf die Arbeits-DB."""
    session_factory = sessionmaker(bind=db_engine)
    monkeypatch.setattr(
        'services.api.utils.finding_aggregation.get_session', session_factory,
    )
    monkeypatch.setattr(
        'services.api.utils.finding_aggregation.get_engine', lambda: db_engine,
    )


def test_close_entry_point_closes_the_finding(aggregated, wired, session):
    """Der Einstiegspunkt beider Abschlusspfade schließt den Befund vollständig."""
    finding_id = close_finding_for_testset_run(aggregated['testset_run_id'])
    assert finding_id == aggregated['finding'].id

    session.expire_all()
    closed = get_testset_run_finding(session, finding_id)
    assert closed.closed_at is not None
    assert closed.scope_json['n_runs'] == 2
    assert closed.candidates_json['per_run']
    assert closed.robustness_json['dsr']
    assert closed.benchmarks_json['buy_and_hold']
    assert closed.warnings_json['not_evaluated']


def test_close_entry_point_without_finding_does_not_fail(session, wired, caplog):
    """Ohne Befund läuft der Abschluss durch — rückwirkende Befunde sind Out of Scope."""
    caplog.set_level(logging.INFO, logger='services.api.utils.finding_aggregation')
    testset_run = TestSetRun(
        testset_id=7, strategy_family='teststrategie', strategy_name='1',
        n_runs_total=1, indicators_config_json={}, status='completed',
    )
    session.add(testset_run)
    session.commit()

    assert close_finding_for_testset_run(testset_run.id) is None
    assert 'kein Befund vorhanden' in caplog.text


def test_second_close_via_entry_point_is_logged_and_changes_nothing(
    aggregated, wired, session, caplog,
):
    """Ein zweiter Abschluss überschreibt nichts und wird als Fehler protokolliert."""
    finding_id = close_finding_for_testset_run(aggregated['testset_run_id'])
    session.expire_all()
    closed_at = get_testset_run_finding(session, finding_id).closed_at

    caplog.clear()
    assert close_finding_for_testset_run(aggregated['testset_run_id']) is None
    assert 'konnte nicht geschlossen werden' in caplog.text

    session.expire_all()
    assert get_testset_run_finding(session, finding_id).closed_at == closed_at

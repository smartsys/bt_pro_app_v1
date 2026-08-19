"""Tests der Walk-Forward-Ketten-Routen.

Die Endpunkt-Funktionen werden direkt aufgerufen (Projekt-Konvention, siehe
test_significance_api.py). Die Läufe entstehen über das echte
``create_backtest_run`` gegen die PostgreSQL-Test-DB (Port 5562) — nur so belegt
der Bestandstest, dass eine Kette wirklich keine Configs anlegt.

Geprüft wird:

* Anlegen schreibt den vollständigen Plan; ein Plan außerhalb der Datenabdeckung
  hinterlässt **keinen** Datensatz.
* Der IS-Lauf rechnet das **Anker-Raster** auf dem geplanten Fenster, der
  OOS-Lauf die eingefrorene Sieger-Kombination — beide mit ``parent_run_id`` auf
  den Anker und erhaltenem Vorlauf.
* Die Siegerwahl vollzieht das vorregistrierte Kriterium; ohne Kandidat über dem
  Trade-Floor gibt es einen ausgewiesenen Fold ohne Sieger statt eines Abbruchs.
* Fold-Anhänge, die vom Plan abweichen (Index oder Fenster), werden abgewiesen.
* Nach dem Abschluss weist jeder Schreibversuch ab.
* Während einer kompletten Kette entstehen keine Zeilen in ``backtest_configs``,
  ``indicator_configs`` und ``testsets``.
* Die Kette bleibt lesbar, nachdem Läufe und Results gelöscht wurden.
"""

import sys
import types
from uuid import uuid4

# rq ist nur im Worker-/App-Container installiert; für den Import des Routen-Moduls
# genügt ein Stub (Muster aus test_significance_api.py).
if 'rq' not in sys.modules:
    sys.modules['rq'] = types.ModuleType('rq')
if not hasattr(sys.modules['rq'], 'Queue'):
    sys.modules['rq'].Queue = object

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from services.api import walk_forward_chain_context as chain_context  # noqa: E402
from services.api.routes import api_walk_forward_chain_runs as run_routes  # noqa: E402
from services.api.routes import api_walk_forward_chains as routes  # noqa: E402
from services.api.routes.api_walk_forward_chain_runs import (  # noqa: E402
    FoldRunIn,
    OosRunIn,
    start_chain_is_run,
    start_chain_oos_run,
)
from services.api.routes.api_walk_forward_chains import (  # noqa: E402
    ChainCloseIn,
    ChainStartIn,
    FoldAppendIn,
    append_chain_fold,
    close_walk_forward_chain,
    get_walk_forward_chain_route,
    list_walk_forward_chains_route,
    start_walk_forward_chain,
)
from user_data.utils.database import repository as repo_module  # noqa: E402
from user_data.utils.database.models import (  # noqa: E402
    BacktestEquity,
    BacktestResult,
    BacktestRun,
    BacktestTrade,
    StrategyConcept,
    StrategyIteration,
    WalkForwardChain,
    WalkForwardChainImmutableError,
)

_ANCHOR_CONFIG = {
    'strategy_family': 'testkonzept',
    'strategy_name': 'v1',
    'symbols': ['BTCUSDT'],
    'exchange': 'binance',
    'timeframe': '4h',
    'start': '2020-01-01',
    'end': '2021-01-01',
    'ohlc_start': '2019-12-01',
    'ohlc_end': '2021-01-01',
    'portfolio': {'size': 100.0, 'size_type': 'value', 'init_cash': 100.0, 'fees': 0.001},
}

# Raster aus reinen Stop-Werten: zählbar ohne vectorbtpro-Indikatoren.
_ANCHOR_GRID = {'_stops': {'tp_stop': [0.02, 0.04, 0.06]}}

_WIDE_COVERAGE = {'BTCUSDT': ('2018-01-01T00:00:00', '2024-01-01T00:00:00')}


class _RecordingQueue:
    """Queue-Ersatz, der das Enqueue mitschreibt statt Redis zu brauchen."""

    calls: list = []

    def __init__(self, name, connection=None):
        self.name = name

    def enqueue(self, path, **kwargs):
        """Merkt sich Job-Pfad und Argumente."""
        _RecordingQueue.calls.append({'name': self.name, 'path': path, **kwargs})
        return None


@pytest.fixture
def wired(monkeypatch, session):
    """Verdrahtet Routen, Repository und Queue auf die Test-DB."""
    engine = session.get_bind()
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(routes, 'get_session', session_factory)
    monkeypatch.setattr(run_routes, 'get_session', session_factory)
    monkeypatch.setattr(chain_context, 'get_redis_connection', lambda: None)
    monkeypatch.setattr(chain_context, 'Queue', _RecordingQueue)
    monkeypatch.setattr(routes, 'ohlc_coverage', lambda *args, **kwargs: dict(_WIDE_COVERAGE))
    monkeypatch.setattr(repo_module, 'get_engine', lambda: engine)
    _RecordingQueue.calls = []
    return session


def _make_anchor(session, n_combinations: int = 3) -> BacktestRun:
    """Legt Konzept, Iteration und den Anker-Lauf an."""
    concept = StrategyConcept(slug='testkonzept', name='Testkonzept')
    session.add(concept)
    session.flush()
    iteration = StrategyIteration(
        concept_id=concept.id, version=1, version_name='v1', type='generic',
        spec_json={'indicators': {}, 'rules': {'entry': None, 'exit': None}},
    )
    session.add(iteration)
    session.flush()
    run = BacktestRun(
        strategy_family='testkonzept', strategy_name='v1',
        symbol='BTCUSDT', exchange='binance', timeframe='4h',
        start_date=__import__('datetime').datetime(2020, 1, 1),
        end_date=__import__('datetime').datetime(2021, 1, 1),
        backtest_config_json=dict(_ANCHOR_CONFIG),
        indicators_config_json=dict(_ANCHOR_GRID),
        n_combinations=n_combinations, status='completed',
        iteration_id=iteration.id, ann_factor=2190.0,
    )
    session.add(run)
    session.commit()
    return run


def _add_results(session, run_id: int, rows: list) -> list:
    """Legt Results eines Laufs an: (sharpe_ratio, total_trades, tp_stop)."""
    created = []
    for index, (sharpe, trades, tp_stop) in enumerate(rows):
        result = BacktestResult(
            run_id=run_id, params_hash=uuid4().hex,
            actual_params_json={'tp_stop': tp_stop},
            resolved_config_json={'_stops': {'tp_stop': tp_stop}},
            sharpe_ratio=sharpe, total_trades=trades,
            total_return_pct=sharpe * 10.0,
        )
        session.add(result)
        created.append(result)
    session.commit()
    return created


def _start_chain(session, anchor_id: int, folds: int = 2, trade_floor: int = 5) -> int:
    """Legt eine Kette über die Route an und gibt ihre ID zurück."""
    response = start_walk_forward_chain(ChainStartIn(
        anchor_run_id=anchor_id, folds=folds, oos_months=3,
        selection_metric='sharpe_ratio', selection_direction='max',
        trade_floor=trade_floor, metrics='kern',
    ))
    return response['data']['chain_id']


def _count(session, table: str) -> int:
    """Zeilenzahl einer Tabelle."""
    return int(session.execute(text(f'SELECT count(*) FROM {table}')).scalar())


# ---------------------------------------------------------------------------
# Anlegen und Plan-Validierung
# ---------------------------------------------------------------------------

def test_start_chain_writes_the_full_plan(wired):
    session = wired
    anchor = _make_anchor(session)

    response = start_walk_forward_chain(ChainStartIn(
        anchor_run_id=anchor.id, folds=3, oos_months=3,
        selection_metric='sharpe_ratio', trade_floor=30, metrics='kern',
    ))
    data = response['data']
    plan = data['chain']['plan_json']

    assert response['error'] is None
    assert data['chain']['status'] == 'running'
    assert plan['n_folds'] == 3
    assert len(plan['folds']) == 3
    assert plan['selection_metric'] == 'sharpe_ratio'
    assert plan['selection_direction'] == 'max'
    assert plan['trade_floor'] == 30
    assert plan['metrics_level'] == 'kern'
    assert plan['folds'][0]['is_window']['start'] == '2020-01-01'
    assert data['chain']['method_note']
    assert data['chain']['folds_json'] == []
    assert 'verdict' not in data['chain'] and 'passed' not in data['chain']


def test_unknown_selection_metric_is_rejected(wired):
    session = wired
    anchor = _make_anchor(session)

    with pytest.raises(HTTPException) as exc:
        start_walk_forward_chain(ChainStartIn(
            anchor_run_id=anchor.id, folds=2, oos_months=3,
            selection_metric='gefuehlte_guete',
        ))
    assert exc.value.status_code == 400
    assert _count(session, 'walk_forward_chains') == 0


def test_plan_beyond_data_coverage_creates_no_chain(wired, monkeypatch):
    session = wired
    anchor = _make_anchor(session)
    monkeypatch.setattr(
        routes, 'ohlc_coverage',
        lambda *args, **kwargs: {'BTCUSDT': ('2019-01-01T00:00:00', '2021-05-01T00:00:00')},
    )

    with pytest.raises(HTTPException) as exc:
        start_walk_forward_chain(ChainStartIn(
            anchor_run_id=anchor.id, folds=4, oos_months=3,
            selection_metric='sharpe_ratio',
        ))
    assert exc.value.status_code == 400
    assert '2022-01-01' in exc.value.detail
    assert _count(session, 'walk_forward_chains') == 0
    assert _RecordingQueue.calls == []


def test_anchor_without_iteration_is_rejected(wired):
    session = wired
    anchor = _make_anchor(session)
    anchor.iteration_id = None
    session.commit()

    with pytest.raises(HTTPException) as exc:
        start_walk_forward_chain(ChainStartIn(
            anchor_run_id=anchor.id, folds=2, oos_months=3,
            selection_metric='sharpe_ratio',
        ))
    assert exc.value.status_code == 400
    assert _count(session, 'walk_forward_chains') == 0


# ---------------------------------------------------------------------------
# Läufe der Kette
# ---------------------------------------------------------------------------

def test_is_run_computes_the_anchor_grid_on_the_planned_window(wired):
    session = wired
    anchor = _make_anchor(session)
    chain_id = _start_chain(session, anchor.id)

    response = start_chain_is_run(chain_id, FoldRunIn(fold_index=2))
    run_id = response['data']['run_id']
    run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()

    # Fold 2 rollt um die OOS-Länge nach vorn und behält die IS-Länge.
    assert response['data']['window']['start'] == '2020-03-31'
    assert response['data']['window']['end'] == '2021-04-01'
    assert run.parent_run_id == anchor.id
    assert run.iteration_id == anchor.iteration_id
    assert run.n_combinations == anchor.n_combinations
    assert run.indicators_config_json == _ANCHOR_GRID
    assert run.backtest_config_json['start'] == '2020-03-31'
    # Vorlauf von 31 Tagen bleibt erhalten.
    assert run.backtest_config_json['ohlc_start'] == '2020-02-29'
    assert run.backtest_config_json['metrics'] == 'kern'
    assert _RecordingQueue.calls[-1]['run_id'] == run_id


def test_oos_run_selects_the_winner_by_the_registered_criterion(wired):
    session = wired
    anchor = _make_anchor(session)
    chain_id = _start_chain(session, anchor.id)
    results = _add_results(session, anchor.id, [
        (1.2, 40, 0.02),
        (3.5, 2, 0.04),    # bester Sharpe, aber unter dem Trade-Floor
        (2.4, 40, 0.06),
    ])

    response = start_chain_oos_run(chain_id, OosRunIn(fold_index=1, is_run_id=anchor.id))
    data = response['data']
    run = session.query(BacktestRun).filter(BacktestRun.id == data['oos_run_id']).first()

    assert data['winner']['result_id'] == results[2].id
    assert data['winner']['selection_value'] == pytest.approx(2.4)
    assert data['winner']['actual_params'] == {'tp_stop': 0.06}
    assert data['no_winner_reason'] is None
    assert run.indicators_config_json == {'_stops': {'tp_stop': 0.06}}
    assert run.backtest_config_json['start'] == '2021-01-01'
    assert run.backtest_config_json['end'] == '2021-04-01'
    assert run.backtest_config_json['ohlc_start'] == '2020-12-01'
    assert run.parent_run_id == anchor.id
    assert run.parent_result_id == results[2].id


def test_oos_run_honours_the_registered_direction(wired):
    session = wired
    anchor = _make_anchor(session)
    start_walk_forward_chain(ChainStartIn(
        anchor_run_id=anchor.id, folds=2, oos_months=3,
        selection_metric='sharpe_ratio', selection_direction='min', trade_floor=5,
    ))
    chain_id = session.query(WalkForwardChain).first().id
    results = _add_results(session, anchor.id, [(1.2, 40, 0.02), (2.4, 40, 0.06)])

    response = start_chain_oos_run(chain_id, OosRunIn(fold_index=1, is_run_id=anchor.id))
    assert response['data']['winner']['result_id'] == results[0].id


def test_fold_without_candidate_over_the_trade_floor_reports_no_winner(wired):
    session = wired
    anchor = _make_anchor(session)
    chain_id = _start_chain(session, anchor.id, trade_floor=999)
    _add_results(session, anchor.id, [(1.2, 40, 0.02), (2.4, 40, 0.06)])
    runs_before = _count(session, 'backtest_runs')

    response = start_chain_oos_run(chain_id, OosRunIn(fold_index=1, is_run_id=anchor.id))
    data = response['data']

    assert data['winner'] is None
    assert data['oos_run_id'] is None
    assert 'Trade-Floor' in data['no_winner_reason']
    assert _count(session, 'backtest_runs') == runs_before


# ---------------------------------------------------------------------------
# Fold anhängen
# ---------------------------------------------------------------------------

def _append_fold(chain_id: int, fold_index: int, plan: dict, **kwargs) -> dict:
    """Hängt einen Fold anhand der Planfenster an."""
    planned = plan['folds'][fold_index - 1]
    payload = FoldAppendIn(
        fold_index=fold_index,
        is_window=planned['is_window'],
        oos_window=planned['oos_window'] if kwargs.get('oos_result_id') else None,
        **kwargs,
    )
    return append_chain_fold(chain_id, payload)


def test_fold_append_copies_the_oos_metrics_from_the_result(wired):
    session = wired
    anchor = _make_anchor(session)
    chain_id = _start_chain(session, anchor.id)
    plan = get_walk_forward_chain_route(chain_id)['data']['plan_json']
    result = _add_results(session, anchor.id, [(1.9, 42, 0.02)])[0]

    response = _append_fold(
        chain_id, 1, plan, is_run_id=anchor.id,
        winner={'result_id': result.id, 'selection_value': 2.4},
        oos_run_id=anchor.id, oos_result_id=result.id,
    )
    fold = response['data']['chain']['folds_json'][0]

    assert response['data']['folds_total'] == 1
    assert fold['oos_metrics']['sharpe_ratio'] == pytest.approx(1.9)
    assert fold['oos_metrics']['total_trades'] == 42
    assert fold['oos_metrics']['result_id'] == result.id
    assert fold['ann_factor'] == pytest.approx(2190.0)


def test_fold_append_rejects_a_wrong_index(wired):
    session = wired
    anchor = _make_anchor(session)
    chain_id = _start_chain(session, anchor.id)
    plan = get_walk_forward_chain_route(chain_id)['data']['plan_json']

    with pytest.raises(HTTPException) as exc:
        _append_fold(chain_id, 2, plan, is_run_id=anchor.id, no_winner_reason='kein Sieger')
    assert exc.value.status_code == 400
    assert 'Fold 1' in exc.value.detail


def test_fold_append_rejects_a_window_off_the_plan(wired):
    session = wired
    anchor = _make_anchor(session)
    chain_id = _start_chain(session, anchor.id)

    payload = FoldAppendIn(
        fold_index=1,
        is_window={'start': '2020-02-01', 'end': '2021-01-01'},
        is_run_id=anchor.id,
        no_winner_reason='kein Sieger',
    )
    with pytest.raises(HTTPException) as exc:
        append_chain_fold(chain_id, payload)
    assert exc.value.status_code == 400
    assert 'IS-Fenster' in exc.value.detail


def test_fold_without_winner_must_not_carry_an_oos_run(wired):
    session = wired
    anchor = _make_anchor(session)
    chain_id = _start_chain(session, anchor.id)
    plan = get_walk_forward_chain_route(chain_id)['data']['plan_json']

    with pytest.raises(HTTPException) as exc:
        _append_fold(chain_id, 1, plan, is_run_id=anchor.id, oos_run_id=anchor.id)
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Abschluss, Unveränderlichkeit und Aufräumen
# ---------------------------------------------------------------------------

def _full_chain(session, folds: int = 2, with_curve: bool = True) -> tuple:
    """Fährt eine vollständige Kette bis zum Abschluss und gibt (chain_id, ids) zurück."""
    anchor = _make_anchor(session)
    chain_id = _start_chain(session, anchor.id)
    plan = get_walk_forward_chain_route(chain_id)['data']['plan_json']
    result_ids = []

    for fold_index in range(1, folds + 1):
        result = _add_results(session, anchor.id, [(2.0 + fold_index, 40, 0.02)])[0]
        result_ids.append(result.id)
        if with_curve:
            base = __import__('datetime').datetime(2021, fold_index, 1)
            for offset, value in enumerate([100.0, 110.0, 99.0]):
                session.add(BacktestEquity(
                    result_id=result.id,
                    timestamp=base + __import__('datetime').timedelta(hours=4 * offset),
                    value=value,
                ))
            # Trades per SQL: das ORM-Modell trägt einen unbenannten Enum, den der
            # PostgreSQL-Dialekt beim INSERT nicht kompilieren kann.
            for exit_trade_id, pnl in ((1, 5.0), (2, -2.0)):
                session.execute(text(
                    'INSERT INTO backtest_result_trades '
                    '(result_id, exit_trade_id, direction, status, size, entry_index, '
                    ' avg_entry_price, pnl) '
                    "VALUES (:rid, :tid, 'Long', 'Closed', 1.0, :ts, 100.0, :pnl)"
                ), {'rid': result.id, 'tid': exit_trade_id, 'ts': base, 'pnl': pnl})
            session.commit()
        _append_fold(
            chain_id, fold_index, plan, is_run_id=anchor.id,
            winner={'result_id': result.id, 'selection_value': 2.0 + fold_index},
            oos_run_id=anchor.id, oos_result_id=result.id,
        )
    return chain_id, anchor.id, result_ids


def test_close_aggregates_server_side_and_seals_the_chain(wired):
    session = wired
    chain_id, _, _ = _full_chain(session)

    response = close_walk_forward_chain(chain_id, ChainCloseIn())
    chain = response['data']

    assert chain['status'] == 'completed'
    assert chain['completed_at'] is not None
    assert chain['aggregate_json']['folds_total'] == 2
    assert chain['aggregate_json']['folds_with_winner'] == 2
    assert chain['aggregate_json']['total_return_pct'] is not None
    assert chain['aggregate_json']['profit_factor'] == pytest.approx(10.0 / 4.0)
    assert len(chain['aggregate_json']['degradation']) == 2
    assert chain['method_note']
    assert 'verdict' not in chain['aggregate_json']


def test_completed_chain_rejects_every_further_write(wired):
    session = wired
    chain_id, anchor_id, _ = _full_chain(session, folds=1)
    close_walk_forward_chain(chain_id, ChainCloseIn())
    plan = get_walk_forward_chain_route(chain_id)['data']['plan_json']

    with pytest.raises(HTTPException) as exc:
        _append_fold(chain_id, 2, plan, is_run_id=anchor_id, no_winner_reason='zu spät')
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException):
        close_walk_forward_chain(chain_id, ChainCloseIn())

    chain = session.query(WalkForwardChain).filter(WalkForwardChain.id == chain_id).first()
    session.refresh(chain)
    chain.error_message = 'nachträglich'
    with pytest.raises(WalkForwardChainImmutableError):
        session.commit()
    session.rollback()


def test_failed_chain_keeps_reason_and_folds(wired):
    session = wired
    chain_id, _, _ = _full_chain(session, folds=1)

    response = close_walk_forward_chain(
        chain_id, ChainCloseIn(error_message='OOS-Lauf 42 abgebrochen'),
    )
    chain = response['data']

    assert chain['status'] == 'failed'
    assert chain['error_message'] == 'OOS-Lauf 42 abgebrochen'
    assert len(chain['folds_json']) == 1
    assert chain['aggregate_json'] is not None


def test_plan_stays_frozen_while_the_chain_runs(wired):
    session = wired
    anchor = _make_anchor(session)
    chain_id = _start_chain(session, anchor.id)

    chain = session.query(WalkForwardChain).filter(WalkForwardChain.id == chain_id).first()
    session.refresh(chain)
    chain.plan_json = {**chain.plan_json, 'trade_floor': 0}
    with pytest.raises(WalkForwardChainImmutableError):
        session.commit()
    session.rollback()


def test_a_complete_chain_creates_no_config_rows(wired):
    session = wired
    before = {
        table: _count(session, table)
        for table in ('backtest_configs', 'indicator_configs', 'testsets')
    }

    chain_id, anchor_id, _ = _full_chain(session, folds=2)
    start_chain_is_run(chain_id, FoldRunIn(fold_index=2))
    _add_results(session, anchor_id, [(1.0, 40, 0.02)])
    close_walk_forward_chain(chain_id, ChainCloseIn())

    after = {
        table: _count(session, table)
        for table in ('backtest_configs', 'indicator_configs', 'testsets')
    }
    assert before == after
    assert _count(session, 'walk_forward_chains') == 1


def test_chain_stays_readable_after_runs_and_results_are_deleted(wired):
    session = wired
    chain_id, anchor_id, result_ids = _full_chain(session, folds=2)
    close_walk_forward_chain(chain_id, ChainCloseIn())

    session.query(BacktestEquity).filter(BacktestEquity.result_id.in_(result_ids)).delete(
        synchronize_session=False,
    )
    session.query(BacktestTrade).filter(BacktestTrade.result_id.in_(result_ids)).delete(
        synchronize_session=False,
    )
    session.query(BacktestResult).filter(BacktestResult.id.in_(result_ids)).delete(
        synchronize_session=False,
    )
    session.query(BacktestRun).filter(BacktestRun.id == anchor_id).delete(
        synchronize_session=False,
    )
    session.commit()

    chain = get_walk_forward_chain_route(chain_id)['data']
    assert chain['plan_json']['n_folds'] == 2
    assert chain['folds_json'][0]['winner']['result_id'] == result_ids[0]
    assert chain['folds_json'][0]['oos_metrics']['sharpe_ratio'] is not None
    assert chain['aggregate_json']['total_return_pct'] is not None
    assert chain['config_snapshot_json']['symbol'] == 'BTCUSDT'


def test_history_is_chronological_and_scoped_by_iteration(wired):
    session = wired
    anchor = _make_anchor(session)
    first = _start_chain(session, anchor.id)
    second = _start_chain(session, anchor.id)

    response = list_walk_forward_chains_route(iteration_id=anchor.iteration_id)
    items = response['data']['items']

    assert [item['id'] for item in items] == [first, second]
    assert response['data']['total'] == 2
    assert list_walk_forward_chains_route(iteration_id=9999)['data']['items'] == []


def test_unknown_chain_gives_a_clean_404(wired):
    with pytest.raises(HTTPException) as exc:
        get_walk_forward_chain_route(4711)
    assert exc.value.status_code == 404

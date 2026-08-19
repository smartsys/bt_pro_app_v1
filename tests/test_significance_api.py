"""Tests der Signifikanztest-Routen.

Die Endpunkt-Funktionen werden direkt aufgerufen (Projekt-Konvention, siehe
test_testset_run_findings_api.py) — kein TestClient nötig. Geprüft wird:

* ``POST /api/backtest/results/{id}/significance`` mit ``method=bootstrap`` rechnet
  direkt und liefert Konfidenzbänder; ohne Trades kommt eine klare Fehlermeldung.
* ``method=permutation`` legt den Datensatz an, reiht den Job ein (Enqueue über den
  String-Pfad) und antwortet mit ``test_id`` und Status ``queued``.
* ``GET /api/significance-tests/{id}`` und ``GET /api/significance-tests?result_id=``
  liefern den Test bzw. die chronologische Historie.
* Ausgabe-Schema und Routen enthalten **kein** Bestanden-Feld und **keine**
  Sortierung nach p-Wert.
"""

import sys
import types
from datetime import datetime

# rq ist nur im Worker-/App-Container installiert; für den Import des Routen-Moduls
# genügt ein Stub (Muster aus test_backtest_run_single_get.py).
for _module_name in ('rq',):
    if _module_name not in sys.modules:
        sys.modules[_module_name] = types.ModuleType(_module_name)
sys.modules['rq'].Queue = object

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from services.api import significance_runner  # noqa: E402
from services.api.routes import api_significance  # noqa: E402
from services.api.routes.api_significance import (  # noqa: E402
    SignificanceStartIn,
    get_significance_test_route,
    list_significance_tests_route,
    start_significance_test,
)
from user_data.utils.database.models import (  # noqa: E402
    BacktestResult,
    BacktestRun,
    BacktestTrade,
    StrategyConcept,
    StrategyIteration,
)

_INDICATORS = {
    'fast_sma': {
        'indicator': 'custom:dwsFastSMA', 'tf': '4h', 'enabled': True,
        'source': 'close', 'length': 12, 'multiplier': 3,
    },
}

_RULES = {
    'entry': {'blocks': [{'conditions': [
        {'lhs': 'close', 'op': '>', 'rhs': 'indicator:fast_sma:result'},
    ]}]},
    'exit': None,
}

_CONFIG = {
    'symbols': ['BTCUSDT'], 'exchange': 'binance', 'timeframe': '4h',
    'start': '2020-01-05', 'end': '2020-04-01',
    'ohlc_start': '2020-01-01', 'ohlc_end': '2020-04-01',
    'import_path': 'user_data.strategies.generic.spec_runner.run_spec_strategy',
    'portfolio': {'size': 100.0, 'size_type': 'value', 'init_cash': 100.0, 'fees': 0.001},
}


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
def wired(monkeypatch, test_engine):
    """Verdrahtet Routen, Runner und Queue auf die Testumgebung."""
    session_factory = sessionmaker(bind=test_engine)
    monkeypatch.setattr(api_significance, 'get_session', session_factory)
    monkeypatch.setattr(significance_runner, 'get_session', session_factory)
    monkeypatch.setattr(api_significance, 'get_redis_connection', lambda: None)
    monkeypatch.setattr(api_significance, 'Queue', _RecordingQueue)
    _RecordingQueue.calls = []
    return session_factory


def _seed_candidate(session, n_trades: int = 0) -> int:
    """Legt Konzept, Iteration, Run, Result und optional Trades an.

    Args:
        session: Aktive Session.
        n_trades: Anzahl geschlossener Trades, die am Result hängen. 0 = keine
            Trades (der Bootstrap muss dann mit Hinweis abbrechen).

    Returns:
        Die Result-ID.
    """
    concept = StrategyConcept(slug='api-signifikanz', name='API-Signifikanz')
    session.add(concept)
    session.flush()
    iteration = StrategyIteration(
        concept_id=concept.id, version=1,
        spec_json={'indicators': _INDICATORS, 'rules': _RULES},
    )
    session.add(iteration)
    session.flush()
    run = BacktestRun(
        strategy_family='generic', strategy_name='api-signifikanz',
        symbol='BTCUSDT', exchange='binance', timeframe='4h',
        start_date=datetime(2020, 1, 5), end_date=datetime(2020, 4, 1),
        backtest_config_json=_CONFIG,
        indicators_config_json={**_INDICATORS, '_stops': {}},
        n_combinations=1, status='completed', iteration_id=iteration.id,
    )
    session.add(run)
    session.flush()
    result = BacktestResult(
        run_id=run.id, params_hash='api-signifikanz-hash', actual_params_json={},
        resolved_config_json=dict(_INDICATORS), iteration_id=iteration.id,
        sharpe_ratio=1.5, profit_factor=1.9, total_return_pct=42.0, total_trades=n_trades,
    )
    session.add(result)
    session.flush()
    for index in range(n_trades):
        session.add(BacktestTrade(
            result_id=result.id, exit_trade_id=index, direction='Long', status='Closed',
            size=1.0, entry_index=datetime(2020, 1, 6), avg_entry_price=100.0,
            return_pct=(2.5 if index % 3 else -1.5),
        ))
    session.commit()
    return result.id


# ---------------------------------------------------------------------------
# Bootstrap: rechnet direkt im Aufruf
# ---------------------------------------------------------------------------

def test_bootstrap_start_returns_completed_test_with_bands(wired):
    """Der Bootstrap-Aufruf antwortet mit fertigem Datensatz samt Konfidenzbändern."""
    session = wired()
    result_id = _seed_candidate(session, n_trades=40)
    session.close()

    response = start_significance_test(
        result_id, SignificanceStartIn(method='bootstrap', n=200, seed=7),
    )
    test = response['data']['test']
    assert response['error'] is None
    assert test['status'] == 'completed'
    assert test['method'] == 'bootstrap'
    assert test['n_iterations'] == 200 and test['seed'] == 7
    bands = test['summary_json']['bands']
    for key in ('mean_return_pct', 'median_return_pct', 'profit_factor'):
        assert set(bands[key]) >= {'p05', 'p50', 'p95'}
    assert 'p_value' not in test['summary_json'], 'Bootstrap liefert keinen p-Wert'
    assert test['summary_json']['share_pf_le_one'] is not None


def test_bootstrap_without_trades_fails_with_recompute_hint(wired):
    """Fehlen Trades, steht der Grund samt Recompute-Weg im Datensatz."""
    session = wired()
    result_id = _seed_candidate(session, n_trades=0)
    session.close()

    response = start_significance_test(
        result_id, SignificanceStartIn(method='bootstrap'),
    )
    test = response['data']['test']
    assert test['status'] == 'failed'
    assert 'backtest_result_trades' in test['error_message']
    assert 'Recompute' in test['error_message']


def test_bootstrap_uses_default_round_count_without_n(wired):
    """Ohne --n rechnet der Bootstrap mit 2000 Runden."""
    session = wired()
    result_id = _seed_candidate(session, n_trades=12)
    session.close()

    response = start_significance_test(result_id, SignificanceStartIn(method='bootstrap'))
    assert response['data']['test']['n_iterations'] == 2000


# ---------------------------------------------------------------------------
# Permutation: Datensatz anlegen und Job einreihen
# ---------------------------------------------------------------------------

def test_permutation_start_enqueues_job_by_string_path(wired):
    """Der Job wird über den String-Pfad eingereiht; die Antwort nennt die test_id."""
    session = wired()
    result_id = _seed_candidate(session, n_trades=0)
    session.close()

    response = start_significance_test(
        result_id, SignificanceStartIn(method='permutation', n=25, seed=3),
    )
    test = response['data']['test']
    assert test['status'] == 'queued'
    assert test['n_iterations'] == 25 and test['seed'] == 3
    assert response['data']['test_id'] == test['id']

    assert len(_RecordingQueue.calls) == 1
    call = _RecordingQueue.calls[0]
    assert call['path'] == 'services.api.worker_tasks.run_significance_permutation_job'
    assert call['test_id'] == test['id']
    assert call['job_timeout'] >= 3600, 'großzügiges Zeitlimit'


def test_permutation_start_freezes_candidate_context(wired):
    """Kombination und Config-Schnappschuss werden beim Anlegen eingefroren."""
    session = wired()
    result_id = _seed_candidate(session, n_trades=0)
    session.close()

    test = start_significance_test(
        result_id, SignificanceStartIn(method='permutation'),
    )['data']['test']
    assert test['params_json']['indicators']['fast_sma']['length'] == 12
    snapshot = test['config_snapshot_json']
    assert snapshot['symbol'] == 'BTCUSDT'
    assert snapshot['timeframe'] == '4h'
    assert snapshot['start'] == '2020-01-05'


def test_permutation_start_uses_default_series_count(wired):
    """Ohne --n rechnet der Permutationstest über 300 synthetische Reihen."""
    session = wired()
    result_id = _seed_candidate(session, n_trades=0)
    session.close()

    test = start_significance_test(
        result_id, SignificanceStartIn(method='permutation'),
    )['data']['test']
    assert test['n_iterations'] == 300


def test_metrics_selection_is_forwarded_to_the_job(wired):
    """Eine Metrik-Auswahl im Body landet unverändert als Job-Argument."""
    session = wired()
    result_id = _seed_candidate(session, n_trades=0)
    session.close()

    start_significance_test(
        result_id,
        SignificanceStartIn(method='permutation', metrics=['sharpe_ratio']),
    )
    assert _RecordingQueue.calls[0]['metrics'] == ['sharpe_ratio']


# ---------------------------------------------------------------------------
# Eingabe-Prüfung
# ---------------------------------------------------------------------------

def test_unknown_method_is_rejected(wired):
    """Eine unbekannte Methode wird abgewiesen statt still auf einen Default zu fallen."""
    session = wired()
    result_id = _seed_candidate(session)
    session.close()

    with pytest.raises(HTTPException) as excinfo:
        start_significance_test(result_id, SignificanceStartIn(method='monte-carlo'))
    assert excinfo.value.status_code == 400
    assert 'Unbekannte Methode' in excinfo.value.detail


def test_unknown_result_is_rejected_with_reason(wired):
    """Ein Result ohne Auflösung bricht mit lesbarem Grund ab."""
    wired()
    with pytest.raises(HTTPException) as excinfo:
        start_significance_test(999999, SignificanceStartIn(method='bootstrap'))
    assert excinfo.value.status_code == 400
    assert 'nicht gefunden' in excinfo.value.detail


def test_non_positive_n_is_rejected(wired):
    """n < 1 wird abgewiesen."""
    session = wired()
    result_id = _seed_candidate(session)
    session.close()

    with pytest.raises(HTTPException) as excinfo:
        start_significance_test(result_id, SignificanceStartIn(method='bootstrap', n=0))
    assert excinfo.value.status_code == 400


# ---------------------------------------------------------------------------
# Lese-Routen
# ---------------------------------------------------------------------------

def test_single_read_route_returns_the_test(wired):
    """GET /api/significance-tests/{id} liefert den Datensatz ohne Verdict-Feld."""
    session = wired()
    result_id = _seed_candidate(session, n_trades=15)
    session.close()

    test_id = start_significance_test(
        result_id, SignificanceStartIn(method='bootstrap', n=50),
    )['data']['test_id']

    payload = get_significance_test_route(test_id)['data']
    assert payload['id'] == test_id
    assert not {'passed', 'verdict', 'score'} & set(payload)


def test_single_read_route_404_for_unknown_id(wired):
    """Unbekannte Test-ID gibt 404."""
    wired()
    with pytest.raises(HTTPException) as excinfo:
        get_significance_test_route(4242)
    assert excinfo.value.status_code == 404


def test_history_is_chronological_and_offers_no_sorting(wired):
    """Die Historie liefert die Anlage-Reihenfolge; es gibt keinen Sortier-Parameter."""
    import inspect

    session = wired()
    result_id = _seed_candidate(session, n_trades=15)
    session.close()

    first = start_significance_test(
        result_id, SignificanceStartIn(method='bootstrap', n=50),
    )['data']['test_id']
    second = start_significance_test(
        result_id, SignificanceStartIn(method='permutation', n=10),
    )['data']['test_id']

    payload = list_significance_tests_route(result_id=result_id)['data']
    assert payload['total'] == 2
    assert [item['id'] for item in payload['items']] == [first, second]

    parameters = set(inspect.signature(list_significance_tests_route).parameters)
    assert parameters == {'result_id'}, 'kein sort_by, kein Filter-Parameter'


def test_history_of_a_result_without_tests_is_empty(wired):
    """Ohne Tests ist die Historie leer, nicht ein Fehler."""
    wired()
    payload = list_significance_tests_route(result_id=123456)['data']
    assert payload == {'items': [], 'total': 0}

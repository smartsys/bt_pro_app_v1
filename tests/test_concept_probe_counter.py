"""Tests für den Sondierungs-Zähler am Konzept (strategy_concepts.probe_count).

Der Zähler macht den Suchumfang sichtbar, der nicht im gespeicherten Raster
steht: die Lite-Sondierungen über POST /api/chart-playground/run-backtest-lite.
Geprüft wird die Mechanik über alle beteiligten Schichten:

- Repository: atomare Erhöhung, Startwert, Isolation je Konzept, unbekannte ID.
- Route: mit `concept_id` steigt der Zähler um genau 1 und die Antwort trägt den
  neuen Stand; ohne `concept_id` bleibt er unberührt; unbekanntes Konzept -> 404.
- Befund: der Umfang-der-Suche-Block trägt den Zählerstand; ohne Konzept-Bezug
  bleibt das Feld leer und trägt seinen Grund (nie eine erfundene 0).
- Toolbox: `--concept <id>` landet als `concept_id` im Request-Body; die
  Befund-Ausgabe zeigt den Stand und bleibt für Altbefunde ohne das Feld lesbar.

Bewertet wird der Zähler nirgends — kein Verdict, keine Schwelle, keine
Verrechnung in N oder DSR.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import text

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from user_data.utils.database.repository_strategies import (  # noqa: E402
    create_concept,
    increment_concept_probe_count,
)

_TOOLBOX_PATH = (
    _ROOT / ".claude" / "skills" / "ds-strategie-session" / "scripts" / "toolbox.py"
)


# ---------------------------------------------------------------------------
# Gemeinsame Fixtures / Payload
# ---------------------------------------------------------------------------

@pytest.fixture(scope='function')
def concept(session):
    """Test-Konzept mit Zählerstand 0."""
    return create_concept(
        session,
        slug='probe-counter-concept',
        name='Probe Counter',
        status='active',
        created_by='pytest',
    )


@pytest.fixture(scope="module")
def toolbox():
    """Lädt toolbox.py als Modul (Ordnername enthält Bindestriche)."""
    spec = importlib.util.spec_from_file_location("toolbox", _TOOLBOX_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["toolbox"] = module
    spec.loader.exec_module(module)
    return module


_LITE_PAYLOAD = {
    'indicators': {
        'fast_sma': {
            'indicator': 'dwsFastSMA',
            'tf': '4h',
            'src': 'close',
            'length': {'type': 'arange', 'start': 6, 'stop': 7, 'step': 1, 'dtype': 'int64'},
            'multiplier': {'type': 'arange', 'start': 6, 'stop': 7, 'step': 1, 'dtype': 'int64'},
        },
        '_stops': {
            'tp_stop': 0.3,
            'sl_stop': 0.15,
            'tsl_th': None,
            'tsl_stop': None,
            'td_stop': 8,
            'delta_format': 'percent',
            'time_delta_format': 'rows',
        },
    },
    'rules': {'entry': {'blocks': []}, 'exit': None},
    'portfolio': {
        'size': 100,
        'size_type': 'value',
        'init_cash': 100,
        'fees': 0.001,
        'stop_exit_price': None,
        'stop_order_type': None,
        'direction': 'longonly',
        'freq': None,
    },
    'data': {
        'exchange': 'binance',
        'symbols': ['BTCUSDT'],
        'timeframe': '4h',
        'start': '2022-01-01',
        'end': '2022-06-01',
        'ohlc_start': '2022-01-01',
        'ohlc_end': '2022-06-01',
    },
}


def _fake_strategy_results() -> dict:
    """Minimales Runner-Ergebnis (ein Mock-Portfolio) für die Route.

    Der Zeitindex ist echt, weil die Route das Portfolio über
    `slice_to_trading_window` auf das Handelsfenster schneidet und dort mit
    Zeitstempeln verglichen wird — ein reiner Mock-Index bricht dort ab.
    """
    pf = MagicMock()
    pf.wrapper.index = pd.date_range('2022-01-01', '2022-06-01', freq='4h', tz='UTC')
    pf.total_return = 0.1234
    pf.sharpe_ratio = 1.0
    pf.max_drawdown = 0.05
    pf.trades.records_readable = []
    return {
        'portfolios': pf,
        'indicators_results': {},
        'signals': {'entries': MagicMock(), 'exits': MagicMock()},
        'analysis_results_dict': None,
    }


def _probe_count(db_engine, concept_id: int) -> int:
    """Liest den Zählerstand direkt aus der Datenbank."""
    with db_engine.connect() as conn:
        return conn.execute(
            text('SELECT probe_count FROM strategy_concepts WHERE id = :id'),
            {'id': concept_id},
        ).scalar()


# ---------------------------------------------------------------------------
# Repository — die Zählmechanik selbst
# ---------------------------------------------------------------------------

def test_new_concept_starts_at_zero(concept):
    """Ein frisch angelegtes Konzept hat null Sondierungen (nicht NULL)."""
    assert concept.probe_count == 0


def test_each_increment_raises_counter_by_one(session, concept):
    """Jeder Aufruf erhöht den Zähler um genau 1 und liefert den neuen Stand."""
    assert [increment_concept_probe_count(session, concept.id) for _ in range(3)] == [1, 2, 3]


def test_counter_is_per_concept(session):
    """Zwei Konzepte zählen unabhängig voneinander."""
    c1 = create_concept(session, slug='probe-c1', name='C1', status='active')
    c2 = create_concept(session, slug='probe-c2', name='C2', status='active')

    increment_concept_probe_count(session, c1.id)
    increment_concept_probe_count(session, c1.id)

    assert increment_concept_probe_count(session, c2.id) == 1
    assert _probe_count(session.get_bind(), c1.id) == 2


def test_increment_on_unknown_concept_raises(session):
    """Unbekannte concept_id wird gemeldet, nicht still übergangen."""
    with pytest.raises(ValueError, match='nicht gefunden'):
        increment_concept_probe_count(session, 999999)


# ---------------------------------------------------------------------------
# Route — /run-backtest-lite zählt nur mit concept_id
# ---------------------------------------------------------------------------

def test_lite_call_with_concept_raises_counter(db_engine, session, concept):
    """Ein Lite-Aufruf mit concept_id erhöht den Zähler um genau 1."""
    from services.api.routes.api_chart_playground import RunBacktestIn, run_backtest_lite

    vorher = _probe_count(db_engine, concept.id)

    with patch('user_data.utils.ohlc.loader.load_ohlc_data', return_value=MagicMock()), \
         patch('user_data.strategies.generic.spec_runner.run_spec_strategy',
               return_value=_fake_strategy_results()):
        result = run_backtest_lite(RunBacktestIn(**_LITE_PAYLOAD, concept_id=concept.id))

    nachher = _probe_count(db_engine, concept.id)
    assert nachher == vorher + 1, f'Zähler ging von {vorher} auf {nachher}'
    assert result['data']['concept_probe_count'] == nachher


def test_lite_call_without_concept_leaves_counter(db_engine, session, concept):
    """Ohne concept_id bleibt der Zähler unverändert und das Feld leer."""
    from services.api.routes.api_chart_playground import RunBacktestIn, run_backtest_lite

    vorher = _probe_count(db_engine, concept.id)

    with patch('user_data.utils.ohlc.loader.load_ohlc_data', return_value=MagicMock()), \
         patch('user_data.strategies.generic.spec_runner.run_spec_strategy',
               return_value=_fake_strategy_results()):
        result = run_backtest_lite(RunBacktestIn(**_LITE_PAYLOAD))

    assert _probe_count(db_engine, concept.id) == vorher
    assert result['data']['concept_probe_count'] is None


def test_lite_call_with_unknown_concept_gives_404(session):
    """Ein unbekanntes Konzept endet als 404, statt ungezählt durchzulaufen."""
    from fastapi import HTTPException
    from services.api.routes.api_chart_playground import RunBacktestIn, run_backtest_lite

    with pytest.raises(HTTPException) as exc_info:
        run_backtest_lite(RunBacktestIn(**_LITE_PAYLOAD, concept_id=999999))

    assert exc_info.value.status_code == 404
    assert 'nicht gefunden' in exc_info.value.detail


# ---------------------------------------------------------------------------
# Befund — Zählerstand im Umfang-der-Suche-Block
# ---------------------------------------------------------------------------

def test_scope_carries_probe_count_of_concept(db_engine, session, concept):
    """Der Umfang-der-Suche-Block trägt den Zählerstand des Konzepts."""
    from services.api.utils.finding_aggregation import build_scope

    increment_concept_probe_count(session, concept.id)
    increment_concept_probe_count(session, concept.id)

    with db_engine.connect() as conn:
        scope = build_scope(conn, [], [], concept.id)

    assert scope['probe_count'] == 2
    assert scope['probe_count_reason'] is None
    # Der Zähler steht neben der Rastergröße, nicht in ihr.
    assert scope['combos_total'] == 0


def test_scope_without_concept_states_reason(db_engine, session):
    """Ohne Konzept-Bezug bleibt das Feld leer und trägt seinen Grund — keine 0."""
    from services.api.utils.finding_aggregation import build_scope

    with db_engine.connect() as conn:
        scope = build_scope(conn, [], [], None)

    assert scope['probe_count'] is None
    assert scope['probe_count_reason']


# ---------------------------------------------------------------------------
# Toolbox — --concept durchreichen und Befund-Ausgabe
# ---------------------------------------------------------------------------

def test_toolbox_concept_flag_reaches_request_body(toolbox, tmp_path):
    """--concept <id> landet als concept_id im Request-Body des Lite-Verbs."""
    spec_file = tmp_path / 'spec.json'
    spec_file.write_text('{"indicators": {}}', encoding='utf-8')

    with patch.object(toolbox, 'request', return_value={'data': {'total_return': 0.1}}) as mock_request:
        toolbox.playground_run_backtest_lite(['--file', str(spec_file), '--concept', '7'])

    body = mock_request.call_args[0][2]
    assert body['concept_id'] == 7


def test_toolbox_without_concept_flag_sends_no_concept_id(toolbox, tmp_path):
    """Ohne --concept bleibt der Body unverändert (kein concept_id)."""
    spec_file = tmp_path / 'spec.json'
    spec_file.write_text('{"indicators": {}}', encoding='utf-8')

    with patch.object(toolbox, 'request', return_value={'data': {'total_return': 0.1}}) as mock_request:
        toolbox.playground_run_backtest_lite(['--file', str(spec_file)])

    body = mock_request.call_args[0][2]
    assert 'concept_id' not in body


def test_toolbox_concept_flag_without_value_raises(toolbox, tmp_path):
    """--concept ohne Wert ist ein Fehler, kein still ignoriertes Flag."""
    spec_file = tmp_path / 'spec.json'
    spec_file.write_text('{"indicators": {}}', encoding='utf-8')

    with pytest.raises(ValueError, match='Konzept-ID'):
        toolbox.playground_run_backtest_lite(['--file', str(spec_file), '--concept'])


def _closed_finding(scope: dict) -> dict:
    """Minimaler geschlossener Befund für die Ausgabe-Prüfung."""
    return {
        'id': 1,
        'iteration_id': 2,
        'testset_id': 3,
        'testset_run_id': 4,
        'created_at': '2026-08-16T10:00:00',
        'closed_at': '2026-08-16T11:00:00',
        'best_criteria_json': [],
        'scope_json': scope,
        'candidates_json': {},
        'robustness_json': {},
        'benchmarks_json': {},
        'warnings_json': {},
    }


def test_befund_output_shows_probe_count(toolbox, capsys):
    """Die Befund-Ausgabe weist den Zählerstand neben der Rastergröße aus."""
    scope = {
        'n_runs': 1, 'n_runs_completed': 1, 'symbols': ['BTCUSDT'], 'combos_total': 96,
        'probe_count': 236, 'probe_count_reason': None, 'runs': [],
    }
    toolbox._print_befund(_closed_finding(scope))

    ausgabe = capsys.readouterr().out
    assert 'Kombinationen gesamt: 96' in ausgabe
    assert 'Lite-Sondierungen des Konzepts: 236' in ausgabe


def test_befund_output_stays_readable_without_probe_count(toolbox, capsys):
    """Ein Befund von vor der Änderung bleibt lesbar — die Zeile fehlt einfach."""
    scope = {
        'n_runs': 1, 'n_runs_completed': 1, 'symbols': ['BTCUSDT'], 'combos_total': 96,
        'runs': [],
    }
    toolbox._print_befund(_closed_finding(scope))

    ausgabe = capsys.readouterr().out
    assert 'Kombinationen gesamt: 96' in ausgabe
    assert 'Lite-Sondierungen' not in ausgabe

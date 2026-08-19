"""Tests für den Durchzug der drei Portfolio-Parameter durch alle Rechenpfade.

Es geht um ``slippage``, ``stop_exit_price`` und ``stop_order_type``:

- Der Result-Snapshot (``full_config_snapshot_json['backtest_config']``) trägt die
  drei Felder; ein Alt-Run ohne die Keys liefert ``None`` ("nicht gesetzt"), nicht ``0``.
- Der eingefrorene Testset-Snapshot (``testset_snapshot_json['configs']``), den der
  Leaderboard-Rerun konsumiert, trägt die drei Felder ebenfalls.
- Ein ungültiger Enum-Wert wird an beiden Eingabegrenzen (BacktestConfig speichern,
  Playground-Request) mit einer Meldung abgewiesen, die die gültigen Werte nennt.
  Ein gültiger Wert in abweichender Schreibweise wird dagegen akzeptiert und von VBT
  korrekt gemappt.

Die DB-gestützten Tests laufen gegen die PostgreSQL-Test-DB
(``VBT_TEST_DATABASE_URL``, Port 5562); ``session`` kommt aus ``tests/conftest.py``.
"""

import sys
import types

import pytest

# rq ist nur im Worker-Container installiert — für reine Tests stubben wir den Import
if 'rq' not in sys.modules:
    rq_stub = types.ModuleType('rq')
    rq_stub.Queue = object
    sys.modules['rq'] = rq_stub

import vectorbtpro as vbt  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from vectorbtpro.utils.enum_ import map_enum_fields  # noqa: E402

from services.api.routes.api_chart_playground import _check_portfolio_enums  # noqa: E402
from services.api.routes.api_config import BacktestConfigIn  # noqa: E402
from user_data.utils.database.models import (  # noqa: E402
    BacktestConfig,
    BacktestResult,
    BacktestRun,
    TestSet,
    TestSetRun,
)
from user_data.utils.database.repository import _build_full_config_snapshot  # noqa: E402
from user_data.utils.database.repository_testsets import (  # noqa: E402
    _build_leaderboard_entry_in_session,
)
from user_data.utils.portfolio_enums import (  # noqa: E402
    validate_stop_exit_price,
    validate_stop_order_type,
)


# ============================================================================
# Gemeinsame Testdaten
# ============================================================================

_INDICATORS_CONFIG = {
    'dwsvwma': {
        'indicator': 'custom:dwsVWMA',
        'enabled': True,
        'length': 16,
    },
    '_stops': {
        'td_stop': None,
        'tp_stop': 0.1,
        'sl_stop': 0.05,
        'tsl_stop': None,
        'tsl_th': None,
        'delta_format': 'percent',
        'time_delta_format': 'rows',
    },
}

_RULES = {'entry': {'blocks': []}, 'exit': None}


def _backtest_config_json(portfolio: dict) -> dict:
    """Baut ein backtest_config_json im Worker-Format mit gegebenem Portfolio-Block."""
    return {
        'strategy_family': 'generic',
        'strategy_name': 'test',
        'symbols': ['BTCUSDT'],
        'exchange': 'binance',
        'timeframe': '4h',
        'start': '2022-01-01',
        'end': '2023-01-01',
        'ohlc_start': '2021-12-01',
        'ohlc_end': '2023-01-01',
        'portfolio': portfolio,
    }


def _minimal_backtest_config_in(**overrides) -> dict:
    """Pflichtfelder für BacktestConfigIn, überschreibbar per Keyword."""
    payload = {
        'name': 'Enum-Test-Config',
        'start': '2022-01-01',
        'end': '2023-01-01',
        'ohlc_start': '2021-12-01',
        'ohlc_end': '2023-01-01',
    }
    payload.update(overrides)
    return payload


# ============================================================================
# Result-Snapshot
# ============================================================================

def test_result_snapshot_traegt_die_drei_portfolio_parameter():
    """Ein gesetzter Portfolio-Block landet vollständig im Result-Snapshot."""
    snapshot = _build_full_config_snapshot(
        backtest_config=_backtest_config_json({
            'size': 100.0,
            'size_type': 'value',
            'init_cash': 100.0,
            'fees': 0.001,
            'slippage': 0.002,
            'stop_exit_price': 'Close',
            'stop_order_type': 'Limit',
        }),
        indicators_config=_INDICATORS_CONFIG,
        actual_params={},
        rules=_RULES,
    )

    bc = snapshot['backtest_config']
    assert bc['slippage'] == 0.002
    assert bc['stop_exit_price'] == 'Close'
    assert bc['stop_order_type'] == 'Limit'


def test_result_snapshot_eines_alt_runs_meldet_nicht_gesetzt_statt_null():
    """Ein Run ohne die drei Keys liefert None — ausdrücklich nicht 0 bzw. ''."""
    snapshot = _build_full_config_snapshot(
        backtest_config=_backtest_config_json({
            'size': 100.0,
            'size_type': 'value',
            'init_cash': 100.0,
            'fees': 0.001,
        }),
        indicators_config=_INDICATORS_CONFIG,
        actual_params={},
        rules=_RULES,
    )

    bc = snapshot['backtest_config']
    for key in ('slippage', 'stop_exit_price', 'stop_order_type'):
        assert key in bc, f'Key {key} fehlt im Snapshot'
        assert bc[key] is None, f'{key} muss None ("nicht gesetzt") sein, ist {bc[key]!r}'
    # Absicherung gegen die eigentliche Verwechslungsgefahr
    assert bc['slippage'] != 0
    assert bc['stop_exit_price'] != ''


def test_result_snapshot_haelt_slippage_null_von_nicht_gesetzt_auseinander():
    """Ein ausdrücklich gesetztes slippage=0.0 ist etwas anderes als ein fehlender Key."""
    snapshot = _build_full_config_snapshot(
        backtest_config=_backtest_config_json({
            'size': 100.0,
            'size_type': 'value',
            'init_cash': 100.0,
            'fees': 0.001,
            'slippage': 0.0,
            'stop_exit_price': None,
            'stop_order_type': None,
        }),
        indicators_config=_INDICATORS_CONFIG,
        actual_params={},
        rules=_RULES,
    )

    assert snapshot['backtest_config']['slippage'] == 0.0
    assert snapshot['backtest_config']['slippage'] is not None


# ============================================================================
# Enum-Prüfung an der Eingabegrenze
# ============================================================================

def test_phantom_stop_exit_price_nennt_die_gueltigen_werte():
    """Ein Phantom-Wert liefert eine klare Meldung statt eines rohen KeyError."""
    with pytest.raises(ValueError) as exc:
        validate_stop_exit_price('CloseOrStop')

    message = str(exc.value)
    assert 'stop_exit_price' in message
    assert 'CloseOrStop' in message
    for valid in ('Stop', 'HardStop', 'Close'):
        assert valid in message


def test_phantom_stop_order_type_nennt_die_gueltigen_werte():
    """Auch der zweite Enum-Wert wird mit Nennung der gültigen Werte abgewiesen."""
    with pytest.raises(ValueError) as exc:
        validate_stop_order_type('Phantom')

    message = str(exc.value)
    assert 'stop_order_type' in message
    assert 'Market' in message and 'Limit' in message


@pytest.mark.parametrize('value,expected', [
    ('close', vbt.pf_enums.StopExitPrice.Close),
    ('CLOSE', vbt.pf_enums.StopExitPrice.Close),
    ('hard_stop', vbt.pf_enums.StopExitPrice.HardStop),
])
def test_gueltiger_stop_exit_price_in_abweichender_schreibweise_wird_gemappt(value, expected):
    """Abweichende Schreibweise wird durchgelassen und von VBT korrekt aufgelöst."""
    assert validate_stop_exit_price(value) == value
    assert map_enum_fields(value, vbt.pf_enums.StopExitPrice) == expected


def test_gueltiger_stop_order_type_in_abweichender_schreibweise_wird_gemappt():
    """Kleinschreibung beim Order-Typ wird akzeptiert und korrekt gemappt."""
    assert validate_stop_order_type('limit') == 'limit'
    assert map_enum_fields('limit', vbt.pf_enums.OrderType) == vbt.pf_enums.OrderType.Limit


@pytest.mark.parametrize('value', [None, '', '   '])
def test_leerer_enum_wert_bedeutet_vbt_default(value):
    """None und leere Eingaben gelten als 'nicht gesetzt' und werden zu None normalisiert."""
    assert validate_stop_exit_price(value) is None
    assert validate_stop_order_type(value) is None


def test_backtest_config_schema_weist_phantom_wert_ab():
    """Eingabegrenze 1: Das Speichern einer BacktestConfig lehnt den Phantom-Wert ab."""
    with pytest.raises(ValidationError) as exc:
        BacktestConfigIn(**_minimal_backtest_config_in(stop_exit_price='Price'))

    message = str(exc.value)
    assert 'Price' in message
    assert 'HardStop' in message


def test_backtest_config_schema_nimmt_gueltige_werte_und_slippage_an():
    """Gültige Werte (auch in abweichender Schreibweise) passieren das Schema unverändert."""
    data = BacktestConfigIn(**_minimal_backtest_config_in(
        slippage=0.002,
        stop_exit_price='close',
        stop_order_type='limit',
    ))

    assert data.slippage == 0.002
    assert data.stop_exit_price == 'close'
    assert data.stop_order_type == 'limit'


def test_backtest_config_schema_hat_slippage_default_null():
    """Ohne Angabe bleibt slippage 0.0 — kein stiller Verhaltenswechsel."""
    data = BacktestConfigIn(**_minimal_backtest_config_in())

    assert data.slippage == 0.0
    assert data.stop_exit_price is None
    assert data.stop_order_type is None


def test_playground_request_mit_phantom_wert_liefert_422():
    """Eingabegrenze 2: Der Playground-Portfolio-Block wird ebenfalls geprüft."""
    with pytest.raises(HTTPException) as exc:
        _check_portfolio_enums({
            'size': 100, 'size_type': 'value', 'init_cash': 100, 'fees': 0.001,
            'stop_exit_price': 'CloseOrStop', 'stop_order_type': None,
        })

    assert exc.value.status_code == 422
    assert 'CloseOrStop' in exc.value.detail
    assert 'HardStop' in exc.value.detail


def test_playground_request_mit_gueltiger_schreibweise_geht_durch():
    """Gegenprobe: 'close' wird im Playground nicht abgewiesen."""
    _check_portfolio_enums({
        'size': 100, 'size_type': 'value', 'init_cash': 100, 'fees': 0.001,
        'slippage': 0.002, 'stop_exit_price': 'close', 'stop_order_type': 'limit',
    })


# ============================================================================
# Eingefrorener Testset-Snapshot (Wurzel des Leaderboard-Reruns)
# ============================================================================

@pytest.fixture(scope='function')
def backtest_config_mit_portfolio_parametern(session):
    """BacktestConfig mit allen drei gesetzten Portfolio-Parametern."""
    config = BacktestConfig(
        name='Portfolio-Parameter-Config',
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start='2024-01-01',
        end='2024-12-31',
        ohlc_start='2023-12-01',
        ohlc_end='2025-01-01',
        slippage=0.002,
        stop_exit_price='Close',
        stop_order_type='Limit',
    )
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


@pytest.fixture(scope='function')
def testset_run_fuer_snapshot(session, backtest_config_mit_portfolio_parametern):
    """TestSet + TestSetRun + ein abgeschlossener BacktestRun mit einem Result."""
    testset = TestSet(
        name='Portfolio-Parameter-TestSet',
        backtest_config_ids_json=[backtest_config_mit_portfolio_parametern.id],
        leaderboard_enabled=True,
        created_by='test-portfolio-parameter',
    )
    session.add(testset)
    session.commit()
    session.refresh(testset)

    testset_run = TestSetRun(
        testset_id=testset.id,
        strategy_family='test-portfolio-parameter',
        strategy_name=1,
        n_runs_total=1,
        n_runs_completed=1,
        status='completed',
        indicators_config_json={'dwsvwma_length': 16},
        created_by='test-portfolio-parameter',
    )
    session.add(testset_run)
    session.commit()
    session.refresh(testset_run)

    backtest_run = BacktestRun(
        strategy_family='test-portfolio-parameter',
        strategy_name=1,
        symbol='BTCUSDT',
        exchange='binance',
        timeframe='4h',
        start_date='2024-01-01',
        end_date='2024-12-31',
        backtest_config_json={
            'strategy_family': 'test-portfolio-parameter',
            'strategy_name': 1,
            'backtest_config_id': backtest_config_mit_portfolio_parametern.id,
            'symbols': ['BTCUSDT'],
            'start': '2024-01-01',
            'end': '2024-12-31',
        },
        indicators_config_json={'dwsvwma_length': 16},
        n_combinations=1,
        status='completed',
        testset_run_id=testset_run.id,
        spec_runner_version='3.1.0',
    )
    session.add(backtest_run)
    session.commit()
    session.refresh(backtest_run)

    result = BacktestResult(
        run_id=backtest_run.id,
        params_hash=f'hash_{backtest_run.id}',
        actual_params_json={'dwsvwma_length': 16},
        total_return_pct=10.0,
        max_drawdown_pct=-5.0,
        sharpe_ratio=1.0,
    )
    session.add(result)
    session.commit()

    return testset_run


def test_testset_snapshot_traegt_die_drei_portfolio_parameter(session, testset_run_fuer_snapshot):
    """Der eingefrorene Config-Snapshot des Leaderboard-Eintrags trägt alle drei Felder.

    Ohne diese Werte liefert der Snapshot-Rerun dauerhaft None, egal wie der
    Recompute-Code aussieht — deshalb ist das die Wurzel und nicht der Recompute.
    """
    entry = _build_leaderboard_entry_in_session(session, testset_run_fuer_snapshot.id)

    assert entry is not None
    configs = entry.testset_snapshot_json['configs']
    assert len(configs) == 1

    snapshot_config = configs[0]
    assert snapshot_config['slippage'] == 0.002
    assert snapshot_config['stop_exit_price'] == 'Close'
    assert snapshot_config['stop_order_type'] == 'Limit'

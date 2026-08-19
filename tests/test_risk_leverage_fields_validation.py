"""Tests für die neuen Portfolio-Felder aus Ticket 104 (Teilaufgabe 1).

Es geht um ``size_type='risk_percent'``, ``risk_pct``, ``leverage`` und
``leverage_mode``:

- Ungültige Werte werden an der Eingabegrenze (BacktestConfig speichern,
  Playground-Request) mit einer Klartext-Meldung abgewiesen, nicht mit rohem
  Traceback (Muster: Ticket 59).
- ``leverage``/``leverage_mode`` werden jetzt IMMER an ``from_signals``
  durchgereicht — auch bei ``size_type='value'`` — und ändern dort nachweislich
  nichts am Rechenergebnis (VBTs eigener Default ist ``1.0``/``'lazy'``).
- ``size_type='risk_percent'`` ist konfigurierbar und persistiert; ohne
  Stopabstand (``sl_stop``) bricht der Lauf mit Klartext ab statt still eine
  falsche Größe zu rechnen. Die Rechnung selbst prüft
  ``test_risk_based_position_size.py``.
- Result-Snapshot und eingefrorener Testset-Snapshot tragen die drei neuen
  Felder (analog den drei Feldern aus Ticket 59).

Die DB-gestützten Tests laufen gegen die PostgreSQL-Test-DB
(``VBT_TEST_DATABASE_URL``, Port 5562); ``session`` kommt aus ``tests/conftest.py``.
"""

import sys
import types

import numpy as np
import pandas as pd
import pytest

# rq ist nur im Worker-Container installiert — für reine Tests stubben wir den Import
if 'rq' not in sys.modules:
    rq_stub = types.ModuleType('rq')
    rq_stub.Queue = object
    sys.modules['rq'] = rq_stub

import vectorbtpro as vbt  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from services.api.routes.api_chart_playground import _check_portfolio_enums  # noqa: E402
from services.api.routes.api_config import BacktestConfigIn  # noqa: E402
from user_data.strategies.generic.spec_runner import run_spec_strategy  # noqa: E402
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
    validate_leverage,
    validate_leverage_mode,
    validate_risk_pct,
    validate_size_type,
)


def _minimal_backtest_config_in(**overrides) -> dict:
    """Pflichtfelder für BacktestConfigIn, überschreibbar per Keyword."""
    payload = {
        'name': 'Risk-Leverage-Test-Config',
        'start': '2022-01-01',
        'end': '2023-01-01',
        'ohlc_start': '2021-12-01',
        'ohlc_end': '2023-01-01',
    }
    payload.update(overrides)
    return payload


# ============================================================================
# Validierung an der Eingabegrenze (user_data/utils/portfolio_enums.py)
# ============================================================================

def test_validate_size_type_akzeptiert_risk_percent():
    """'risk_percent' ist kein VBT-SizeType, aber ein gültiger App-Wert."""
    assert validate_size_type('risk_percent') == 'risk_percent'


@pytest.mark.parametrize('value', ['value', 'Value', 'PERCENT100', 'amount'])
def test_validate_size_type_akzeptiert_vbt_enum_werte_case_insensitiv(value):
    """Bestehende VBT-SizeType-Werte bleiben unabhängig von Groß-/Kleinschreibung gültig."""
    assert validate_size_type(value) == value


def test_validate_size_type_weist_phantom_wert_mit_klartext_ab():
    """Ein Tippfehler wird mit Meldung abgewiesen statt mit rohem KeyError."""
    with pytest.raises(ValueError) as exc:
        validate_size_type('risk_percentt')

    message = str(exc.value)
    assert 'risk_percentt' in message
    assert 'risk_percent' in message
    assert 'Value' in message


@pytest.mark.parametrize('value,expected', [
    ('Lazy', vbt.pf_enums.LeverageMode.Lazy),
    ('eager', vbt.pf_enums.LeverageMode.Eager),
    ('LAZYMULT', vbt.pf_enums.LeverageMode.LazyMult),
    ('eagerMult', vbt.pf_enums.LeverageMode.EagerMult),
])
def test_validate_leverage_mode_akzeptiert_alle_vier_werte_case_insensitiv(value, expected):
    """Alle vier LeverageMode-Werte werden unabhängig von der Schreibweise akzeptiert."""
    from vectorbtpro.utils.enum_ import map_enum_fields
    assert validate_leverage_mode(value) == value
    assert map_enum_fields(value, vbt.pf_enums.LeverageMode) == expected


@pytest.mark.parametrize('value', [None, '', '   '])
def test_validate_leverage_mode_normalisiert_leer_auf_lazy(value):
    """Anders als bei den Stop-Feldern ist leverage_mode NOT NULL — leer wird zu 'lazy'."""
    assert validate_leverage_mode(value) == 'lazy'


def test_validate_leverage_mode_weist_phantom_wert_mit_klartext_ab():
    """Ein ungültiger Hebelmodus liefert eine Meldung mit den vier gültigen Werten."""
    with pytest.raises(ValueError) as exc:
        validate_leverage_mode('turbo')

    message = str(exc.value)
    assert 'turbo' in message
    for valid in ('Lazy', 'Eager', 'LazyMult', 'EagerMult'):
        assert valid in message


@pytest.mark.parametrize('value', [0.0, -1.0, -0.001])
def test_validate_leverage_weist_nicht_positive_werte_ab(value):
    """leverage <= 0 ist nicht sinnvoll interpretierbar und wird abgewiesen."""
    with pytest.raises(ValueError) as exc:
        validate_leverage(value)
    assert 'leverage' in str(exc.value)


@pytest.mark.parametrize('value', [1.0, 0.01, 10.0, 100.0])
def test_validate_leverage_akzeptiert_positive_werte(value):
    """Positive Werte passieren unverändert."""
    assert validate_leverage(value) == value


def test_validate_risk_pct_weist_negativen_wert_ab():
    """Ein negativer Kontoanteil ergibt keinen Sinn und wird abgewiesen."""
    with pytest.raises(ValueError) as exc:
        validate_risk_pct(-0.1)
    assert 'risk_pct' in str(exc.value)


@pytest.mark.parametrize('value', [None, 0.0, 0.03, 1.0])
def test_validate_risk_pct_akzeptiert_none_und_nicht_negative_werte(value):
    """None ('nicht gesetzt') und nicht-negative Werte passieren unverändert."""
    assert validate_risk_pct(value) == value


# ============================================================================
# Eingabegrenze 1: BacktestConfig speichern (Pydantic-Schema)
# ============================================================================

def test_backtest_config_schema_hat_die_erwarteten_defaults():
    """Ohne Angabe: leverage=1.0, leverage_mode='lazy', risk_pct=None (VBT-Default)."""
    data = BacktestConfigIn(**_minimal_backtest_config_in())

    assert data.leverage == 1.0
    assert data.leverage_mode == 'lazy'
    assert data.risk_pct is None


def test_backtest_config_schema_nimmt_risk_percent_und_die_drei_felder_an():
    """Ein vollständig gesetzter Satz aller vier Felder passiert das Schema."""
    data = BacktestConfigIn(**_minimal_backtest_config_in(
        size_type='risk_percent', risk_pct=0.03, leverage=10.0, leverage_mode='eager',
    ))

    assert data.size_type == 'risk_percent'
    assert data.risk_pct == 0.03
    assert data.leverage == 10.0
    assert data.leverage_mode == 'eager'


def test_backtest_config_schema_weist_phantom_size_type_ab():
    """Eingabegrenze 1: ein ungültiger size_type wird mit Klartext abgewiesen."""
    with pytest.raises(ValidationError) as exc:
        BacktestConfigIn(**_minimal_backtest_config_in(size_type='risk_percentt'))
    assert 'risk_percentt' in str(exc.value)


def test_backtest_config_schema_weist_negativen_leverage_ab():
    """Eingabegrenze 1: leverage <= 0 wird mit Klartext abgewiesen."""
    with pytest.raises(ValidationError) as exc:
        BacktestConfigIn(**_minimal_backtest_config_in(leverage=-1.0))
    assert 'leverage' in str(exc.value)


def test_backtest_config_schema_weist_phantom_leverage_mode_ab():
    """Eingabegrenze 1: ein ungültiger Hebelmodus wird mit Klartext abgewiesen."""
    with pytest.raises(ValidationError) as exc:
        BacktestConfigIn(**_minimal_backtest_config_in(leverage_mode='turbo'))
    assert 'turbo' in str(exc.value)


def test_backtest_config_schema_weist_negativen_risk_pct_ab():
    """Eingabegrenze 1: ein negativer Kontoanteil wird mit Klartext abgewiesen."""
    with pytest.raises(ValidationError) as exc:
        BacktestConfigIn(**_minimal_backtest_config_in(risk_pct=-0.1))
    assert 'risk_pct' in str(exc.value)


# ============================================================================
# Eingabegrenze 2: Playground-Portfolio-Block
# ============================================================================

def test_playground_request_mit_phantom_size_type_liefert_422():
    """Eingabegrenze 2: size_type wird ebenfalls im Playground-Request geprüft."""
    with pytest.raises(HTTPException) as exc:
        _check_portfolio_enums({
            'size': 100, 'size_type': 'risk_percentt', 'init_cash': 100, 'fees': 0.001,
        })
    assert exc.value.status_code == 422
    assert 'risk_percentt' in exc.value.detail


def test_playground_request_mit_negativem_leverage_liefert_422():
    """Eingabegrenze 2: leverage <= 0 wird im Playground-Request geprüft."""
    with pytest.raises(HTTPException) as exc:
        _check_portfolio_enums({
            'size': 100, 'size_type': 'value', 'init_cash': 100, 'fees': 0.001,
            'leverage': -5.0,
        })
    assert exc.value.status_code == 422


def test_playground_request_mit_risk_percent_geht_durch():
    """Gegenprobe: ein vollständiger, gültiger risk_percent-Block passiert die Prüfung."""
    _check_portfolio_enums({
        'size': 100, 'size_type': 'risk_percent', 'init_cash': 100, 'fees': 0.001,
        'risk_pct': 0.03, 'leverage': 10.0, 'leverage_mode': 'eager',
    })


# ============================================================================
# Spec-Runner: risk_percent bricht bewusst ab, kein Platzhalter
# ============================================================================

def _make_synthetic_ohlc_data(n: int = 300, seed: int = 3):
    """Minimaler ohlc_data-Wrapper mit .get(key) — Muster aus test_combo_batching.py."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0, 0.01, size=n)
    close = 100.0 * np.exp(np.cumsum(returns))
    noise = rng.uniform(0.001, 0.005, size=n)
    high = close * (1 + noise)
    low = close * (1 - noise)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = rng.uniform(1000, 10000, size=n)
    idx = pd.date_range('2020-01-01', periods=n, freq='4h', tz='UTC')

    df = pd.DataFrame(
        {'Open': open_, 'High': high, 'Low': low, 'Close': close, 'Volume': volume},
        index=idx,
    )

    class _OhlcWrapper:
        def __init__(self, df_: pd.DataFrame) -> None:
            self._df = df_

        def get(self, key: str):
            return self._df[key]

    return _OhlcWrapper(df)


def _fastsma_indicators_json() -> dict:
    return {
        'fast_sma': {
            'indicator': 'custom:dwsFastSMA',
            'tf': '4h',
            'enabled': True,
            'source': 'close',
            'length': 10,
            'multiplier': 2,
        },
        '_stops': {
            'tp_stop': None, 'sl_stop': None, 'tsl_th': None, 'tsl_stop': None,
            'td_stop': None, 'delta_format': None, 'time_delta_format': None,
        },
    }


def _fastsma_rules_json() -> dict:
    return {
        'entry': {'blocks': [{'conditions': [
            {'lhs': 'close', 'op': '>', 'rhs': 'indicator:fast_sma:result'},
        ]}]},
        'exit': {'blocks': [{'conditions': [
            {'lhs': 'close', 'op': '<', 'rhs': 'indicator:fast_sma:result'},
        ]}]},
    }


def _fastsma_backtest_config(portfolio_overrides: dict) -> dict:
    portfolio = {
        'fees': 0.001, 'size': 100.0, 'init_cash': 100.0, 'size_type': 'value',
    }
    portfolio.update(portfolio_overrides)
    return {
        'start': '2020-01-01', 'end': '2020-12-31', 'timeframe': '4h',
        'portfolio': portfolio,
    }


def test_risk_percent_ohne_stopabstand_bricht_mit_klartext_ab():
    """Ohne ``sl_stop`` fehlt der Divisor der risikobasierten Größe.

    Der Lauf bricht dann mit Klartext ab, statt einen Ersatzwert einzusetzen.
    (Bis zur Umsetzung der Rechnung stand hier ein ``NotImplementedError``-Riegel;
    der ist mit Ticket 104, Teilaufgabe 2 durch die echte Rechnung ersetzt.)
    """
    ohlc_data = _make_synthetic_ohlc_data()
    indicators_json = _fastsma_indicators_json()
    rules_json = _fastsma_rules_json()
    backtest_config = _fastsma_backtest_config({
        'size_type': 'risk_percent', 'risk_pct': 0.03, 'leverage': 10.0,
    })

    with pytest.raises(ValueError) as exc:
        run_spec_strategy(ohlc_data, indicators_json, backtest_config, rules_json)

    message = str(exc.value)
    assert 'risk_percent' in message
    assert 'sl_stop' in message


def test_risk_percent_mit_stopabstand_rechnet_die_groesse_zur_laufzeit():
    """Mit gesetztem ``sl_stop`` rechnet der Lauf durch und meldet seine Größen.

    Gegenstück zum Test darüber: derselbe Aufbau, nur mit Stopabstand — dann
    entsteht kein Abbruch, sondern ein Lauf mit risikobasierten Ordergrößen und
    einer Selbstauskunft (``risk_sizing_report``).
    """
    ohlc_data = _make_synthetic_ohlc_data()
    indicators_json = _fastsma_indicators_json()
    indicators_json['_stops'] = {
        **indicators_json['_stops'], 'sl_stop': 0.02, 'delta_format': 'percent',
    }
    rules_json = _fastsma_rules_json()
    backtest_config = _fastsma_backtest_config({
        'size_type': 'risk_percent', 'risk_pct': 0.03, 'leverage': 10.0,
    })

    result = run_spec_strategy(ohlc_data, indicators_json, backtest_config, rules_json)
    report = result['risk_sizing_report']
    assert report is not None
    assert report['n_sized'] > 0


def test_leverage_und_leverage_mode_aendern_bei_size_type_value_nichts():
    """Keine Nebenwirkung: leverage/leverage_mode gehen jetzt immer an from_signals,
    aber ein Lauf mit fester Größe (size_type='value') liefert bit-genau dieselben
    Kennzahlen, ob die beiden Keys im portfolio-Block stehen oder ganz fehlen (der
    Vor-Ticket-104-Zustand, in dem from_signals sie nie bekam).
    """
    from user_data.utils.database.repository import _extract_metrics
    from user_data.utils.metrics.trading_window import slice_to_trading_window

    ohlc_data = _make_synthetic_ohlc_data()
    indicators_json = _fastsma_indicators_json()
    rules_json = _fastsma_rules_json()

    backtest_config_mit = _fastsma_backtest_config({'leverage': 1.0, 'leverage_mode': 'lazy'})
    backtest_config_ohne = _fastsma_backtest_config({})
    assert 'leverage' not in backtest_config_ohne['portfolio']
    assert 'leverage_mode' not in backtest_config_ohne['portfolio']

    result_mit = run_spec_strategy(ohlc_data, indicators_json, backtest_config_mit, rules_json)
    result_ohne = run_spec_strategy(ohlc_data, indicators_json, backtest_config_ohne, rules_json)

    pf_mit = slice_to_trading_window(result_mit['portfolios'], backtest_config_mit)
    pf_ohne = slice_to_trading_window(result_ohne['portfolios'], backtest_config_ohne)

    m_mit = _extract_metrics(pf_mit, pf_mit.wrapper.columns, backtest_config_mit)[0]
    m_ohne = _extract_metrics(pf_ohne, pf_ohne.wrapper.columns, backtest_config_ohne)[0]

    for key in ('total_return_pct', 'sharpe_ratio', 'total_trades', 'max_drawdown_pct', 'profit_factor'):
        assert m_mit[key] == m_ohne[key], f'{key}: {m_mit[key]!r} != {m_ohne[key]!r}'


# ============================================================================
# Result-Snapshot und eingefrorener Testset-Snapshot
# ============================================================================

_INDICATORS_CONFIG = {
    'dwsvwma': {'indicator': 'custom:dwsVWMA', 'enabled': True, 'length': 16},
    '_stops': {
        'td_stop': None, 'tp_stop': None, 'sl_stop': None, 'tsl_stop': None, 'tsl_th': None,
        'delta_format': 'percent', 'time_delta_format': 'rows',
    },
}
_RULES = {'entry': {'blocks': []}, 'exit': None}


def _backtest_config_json(portfolio: dict) -> dict:
    return {
        'strategy_family': 'generic', 'strategy_name': 'test', 'symbols': ['BTCUSDT'],
        'exchange': 'binance', 'timeframe': '4h', 'start': '2022-01-01', 'end': '2023-01-01',
        'ohlc_start': '2021-12-01', 'ohlc_end': '2023-01-01', 'portfolio': portfolio,
    }


def test_result_snapshot_traegt_risk_pct_leverage_leverage_mode():
    """Ein gesetzter risk_percent-Block landet vollständig im Result-Snapshot."""
    snapshot = _build_full_config_snapshot(
        backtest_config=_backtest_config_json({
            'size': 100.0, 'size_type': 'risk_percent', 'init_cash': 100.0, 'fees': 0.001,
            'risk_pct': 0.03, 'leverage': 10.0, 'leverage_mode': 'eager',
        }),
        indicators_config=_INDICATORS_CONFIG, actual_params={}, rules=_RULES,
    )

    bc = snapshot['backtest_config']
    assert bc['risk_pct'] == 0.03
    assert bc['leverage'] == 10.0
    assert bc['leverage_mode'] == 'eager'


def test_result_snapshot_eines_alt_runs_meldet_risk_pct_nicht_gesetzt():
    """Ein Run ohne die drei Keys liefert None ('nicht gesetzt'), nicht 0/'lazy'-erzwungen."""
    snapshot = _build_full_config_snapshot(
        backtest_config=_backtest_config_json({
            'size': 100.0, 'size_type': 'value', 'init_cash': 100.0, 'fees': 0.001,
        }),
        indicators_config=_INDICATORS_CONFIG, actual_params={}, rules=_RULES,
    )

    bc = snapshot['backtest_config']
    for key in ('risk_pct', 'leverage', 'leverage_mode'):
        assert key in bc
        assert bc[key] is None


@pytest.fixture(scope='function')
def backtest_config_mit_risk_leverage(session):
    """BacktestConfig mit gesetztem risk_percent-Block."""
    config = BacktestConfig(
        name='Risk-Leverage-Snapshot-Config', symbol='BTCUSDT', exchange='binance',
        timeframe='4h', start='2024-01-01', end='2024-12-31',
        ohlc_start='2023-12-01', ohlc_end='2025-01-01',
        size_type='risk_percent', risk_pct=0.03, leverage=10.0, leverage_mode='eager',
    )
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


@pytest.fixture(scope='function')
def testset_run_fuer_risk_leverage_snapshot(session, backtest_config_mit_risk_leverage):
    """TestSet + TestSetRun + ein abgeschlossener BacktestRun mit einem Result."""
    testset = TestSet(
        name='Risk-Leverage-TestSet',
        backtest_config_ids_json=[backtest_config_mit_risk_leverage.id],
        leaderboard_enabled=True, created_by='test-risk-leverage',
    )
    session.add(testset)
    session.commit()
    session.refresh(testset)

    testset_run = TestSetRun(
        testset_id=testset.id, strategy_family='test-risk-leverage', strategy_name=1,
        n_runs_total=1, n_runs_completed=1, status='completed',
        indicators_config_json={'dwsvwma_length': 16}, created_by='test-risk-leverage',
    )
    session.add(testset_run)
    session.commit()
    session.refresh(testset_run)

    backtest_run = BacktestRun(
        strategy_family='test-risk-leverage', strategy_name=1, symbol='BTCUSDT',
        exchange='binance', timeframe='4h', start_date='2024-01-01', end_date='2024-12-31',
        backtest_config_json={
            'strategy_family': 'test-risk-leverage', 'strategy_name': 1,
            'backtest_config_id': backtest_config_mit_risk_leverage.id,
            'symbols': ['BTCUSDT'], 'start': '2024-01-01', 'end': '2024-12-31',
        },
        indicators_config_json={'dwsvwma_length': 16}, n_combinations=1, status='completed',
        testset_run_id=testset_run.id, spec_runner_version='4.4.0',
    )
    session.add(backtest_run)
    session.commit()
    session.refresh(backtest_run)

    result = BacktestResult(
        run_id=backtest_run.id, params_hash=f'hash_{backtest_run.id}',
        actual_params_json={'dwsvwma_length': 16},
        total_return_pct=10.0, max_drawdown_pct=-5.0, sharpe_ratio=1.0,
    )
    session.add(result)
    session.commit()

    return testset_run


def test_testset_snapshot_traegt_risk_pct_leverage_leverage_mode(
    session, testset_run_fuer_risk_leverage_snapshot,
):
    """Der eingefrorene Config-Snapshot des Leaderboard-Eintrags trägt alle drei Felder.

    Ohne diese Werte liefert der Snapshot-Rerun dauerhaft None, egal wie der
    Recompute-Code aussieht — deshalb ist das die Wurzel und nicht der Recompute.
    """
    entry = _build_leaderboard_entry_in_session(session, testset_run_fuer_risk_leverage_snapshot.id)

    assert entry is not None
    configs = entry.testset_snapshot_json['configs']
    assert len(configs) == 1

    snapshot_config = configs[0]
    assert snapshot_config['risk_pct'] == 0.03
    assert snapshot_config['leverage'] == 10.0
    assert snapshot_config['leverage_mode'] == 'eager'

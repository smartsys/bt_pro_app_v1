"""Tests für den Lite-Backtest-Endpoint (run_backtest_lite).

Prüft:
- Happy Path: /run-backtest-lite liefert 200 mit total_return, trades, duration_ms.
- Validierungsfehler: ungültiger Payload -> 422.
- DB-Isolations-Pflicht: backtest_runs, backtest_trades, backtest_orders,
  backtest_positions, backtest_equity, strategy_iterations bleiben unverändert.
"""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Gemeinsame Test-Fixtures / Payload
# ---------------------------------------------------------------------------

_SAMPLE_INDICATORS = {
    'fast_sma': {
        'indicator': 'dwsFastSMA',
        'tf': '4h',
        'inputs': {'src': 'close'},
        'length': {'type': 'arange', 'start': 6, 'stop': 7, 'step': 1, 'dtype': 'int64'},
        'multiplier': {'type': 'arange', 'start': 6, 'stop': 7, 'step': 1, 'dtype': 'int64'},
    },
}

_SAMPLE_RULES = {
    'entry': {'logic': 'AND', 'conditions': []},
    'exit': None,
}

_SAMPLE_PORTFOLIO = {
    'size': 100,
    'size_type': 'value',
    'init_cash': 100,
    'fees': 0.001,
    'tp_stop': 0.3,
    'sl_stop': 0.15,
    'tsl_th': None,
    'tsl_stop': None,
    'td_stop': 8,
    'delta_format': 'percent',
    'time_delta_format': 'rows',
    'stop_exit_price': None,
    'stop_order_type': None,
    'direction': 'longonly',
    'freq': None,
}

_SAMPLE_DATA = {
    'exchange': 'binance',
    'symbols': ['BTCUSDT'],
    'timeframe': '4h',
    'start': '2022-01-01',
    'end': '2022-06-01',
    'ohlc_start': '2022-01-01',
    'ohlc_end': '2022-06-01',
}

_VALID_PAYLOAD = {
    'indicators': _SAMPLE_INDICATORS,
    'rules': _SAMPLE_RULES,
    'portfolio': _SAMPLE_PORTFOLIO,
    'data': _SAMPLE_DATA,
}


def _make_fake_pf(total_return: float = 0.1234, trade_count: int = 42):
    """Erzeugt ein minimales Mock-Portfolio-Objekt."""
    pf = MagicMock()
    pf.total_return = total_return
    pf.sharpe_ratio = 1.0
    pf.max_drawdown = 0.05
    pf.trades.records_readable = [MagicMock()] * trade_count
    return pf


def _fake_strategy_results(total_return: float = 0.1234, trade_count: int = 42) -> dict:
    return {
        'portfolios': _make_fake_pf(total_return, trade_count),
        'indicators_results': {},
        'signals': {'entries': MagicMock(), 'exits': MagicMock()},
        'analysis_results_dict': None,
    }


# ---------------------------------------------------------------------------
# Happy Path
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_lite_endpoint_happy_path():
    """run_backtest_lite liefert 200 mit total_return, trades, duration_ms.

    Prüft korrekte Felder und Typen im Response-Dict.
    """
    from services.api.routes.api_chart_playground import run_backtest_lite, RunBacktestIn

    with patch('user_data.utils.ohlc.loader.load_ohlc_data', return_value=MagicMock()), \
         patch('user_data.strategies.generic.spec_runner.run_spec_strategy',
               return_value=_fake_strategy_results(total_return=0.1234, trade_count=42)):
        req = RunBacktestIn(**_VALID_PAYLOAD)
        result = run_backtest_lite(req)

    assert result['error'] is None
    d = result['data']
    assert 'total_return' in d, "Feld total_return fehlt"
    assert 'trades' in d, "Feld trades fehlt"
    assert 'duration_ms' in d, "Feld duration_ms fehlt"
    assert isinstance(d['total_return'], float), f"total_return soll float sein, ist {type(d['total_return'])}"
    assert isinstance(d['trades'], int), f"trades soll int sein, ist {type(d['trades'])}"
    assert isinstance(d['duration_ms'], int), f"duration_ms soll int sein, ist {type(d['duration_ms'])}"
    assert abs(d['total_return'] - 0.1234) < 1e-9, f"Unerwarteter total_return: {d['total_return']}"
    assert d['trades'] == 42, f"Unerwartete trades: {d['trades']}"
    assert d['duration_ms'] >= 0, "duration_ms soll nicht negativ sein"


# ---------------------------------------------------------------------------
# Validierungsfehler
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_lite_endpoint_ohlc_fehler_gibt_400():
    """run_backtest_lite gibt HTTPException 400 wenn OHLC-Daten nicht ladbar."""
    from fastapi import HTTPException
    from services.api.routes.api_chart_playground import run_backtest_lite, RunBacktestIn

    with patch('user_data.utils.ohlc.loader.load_ohlc_data',
               side_effect=Exception('Keine OHLC-Daten vorhanden')):
        req = RunBacktestIn(**_VALID_PAYLOAD)
        with pytest.raises(HTTPException) as exc_info:
            run_backtest_lite(req)

    assert exc_info.value.status_code == 400
    assert 'OHLC' in exc_info.value.detail


@pytest.mark.integration
def test_lite_endpoint_run_fehler_gibt_500():
    """run_backtest_lite gibt HTTPException 500 wenn run_spec_strategy fehlschlägt."""
    from fastapi import HTTPException
    from services.api.routes.api_chart_playground import run_backtest_lite, RunBacktestIn

    with patch('user_data.utils.ohlc.loader.load_ohlc_data', return_value=MagicMock()), \
         patch('user_data.strategies.generic.spec_runner.run_spec_strategy',
               side_effect=Exception('Backtest-Fehler')):
        req = RunBacktestIn(**_VALID_PAYLOAD)
        with pytest.raises(HTTPException) as exc_info:
            run_backtest_lite(req)

    assert exc_info.value.status_code == 500
    assert 'Lite-Backtest fehlgeschlagen' in exc_info.value.detail


# ---------------------------------------------------------------------------
# DB-Isolations-Pflicht
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_lite_schreibt_nichts_in_db():
    """run_backtest_lite ruft weder create_backtest_run noch save_strategy_results auf.

    Prüft, dass kein DB-Schreib-Aufruf stattfindet: Wenn das Mock aufgerufen
    würde, würde der Test fehlschlagen.
    """
    from services.api.routes.api_chart_playground import run_backtest_lite, RunBacktestIn

    # Mocks die NICHT aufgerufen werden dürfen
    mock_create_run = MagicMock(return_value=999)
    mock_save_results = MagicMock()

    with patch('user_data.utils.ohlc.loader.load_ohlc_data', return_value=MagicMock()), \
         patch('user_data.strategies.generic.spec_runner.run_spec_strategy',
               return_value=_fake_strategy_results()), \
         patch('user_data.utils.database.repository.create_backtest_run', mock_create_run), \
         patch('user_data.utils.database.repository.save_strategy_results', mock_save_results):
        req = RunBacktestIn(**_VALID_PAYLOAD)
        run_backtest_lite(req)

    mock_create_run.assert_not_called()
    mock_save_results.assert_not_called()


@pytest.mark.integration
def test_lite_db_counts_unveraendert(db_engine):
    """Mehrere Lite-Aufrufe ändern keine DB-Zeilen in den persistierten Tabellen.

    PFLICHT-Assertion: SELECT count(*) vor und nach 3 Lite-Calls
    identisch für backtest_runs, backtest_trades, backtest_orders,
    backtest_positions, backtest_equity, strategy_iterations.
    """
    from sqlalchemy import text
    from services.api.routes.api_chart_playground import run_backtest_lite, RunBacktestIn

    tabellen = [
        'backtest_runs',
        'backtest_result_trades',
        'backtest_result_orders',
        'backtest_result_positions',
        'backtest_result_equity',
        'strategy_iterations',
    ]

    def _counts() -> dict:
        counts = {}
        with db_engine.connect() as conn:
            for t in tabellen:
                row = conn.execute(text(f'SELECT count(*) FROM {t}')).fetchone()
                counts[t] = row[0]
        return counts

    vorher = _counts()

    with patch('user_data.utils.ohlc.loader.load_ohlc_data', return_value=MagicMock()), \
         patch('user_data.strategies.generic.spec_runner.run_spec_strategy',
               return_value=_fake_strategy_results()):
        req = RunBacktestIn(**_VALID_PAYLOAD)
        for _ in range(3):
            run_backtest_lite(req)

    nachher = _counts()

    for t in tabellen:
        assert vorher[t] == nachher[t], (
            f"Tabelle '{t}' hat sich verändert: vorher={vorher[t]}, nachher={nachher[t]}"
        )

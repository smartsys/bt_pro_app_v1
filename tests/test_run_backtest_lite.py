"""Tests für den Lite-Backtest-Endpoint (run_backtest_lite).

Prüft:
- Happy Path: /run-backtest-lite liefert 200 mit total_return, trades,
  duration_ms, sharpe_ratio, position_coverage_pct und concept_probe_count.
- Validierungsfehler: ungültiger Payload -> 422.
- DB-Isolations-Pflicht: backtest_runs, backtest_trades, backtest_orders,
  backtest_positions, backtest_equity, strategy_iterations bleiben unverändert.

GEÄNDERT (Ticket 94): Kein 'integration'-Marker mehr — die Datei rechnet nicht
schwer und hat keine externe Abhängigkeit: `run_spec_strategy` und
`load_ohlc_data` sind gemockt, der einzige echte Nachbar ist die lokale
Test-DB über die 'db_engine'/'session'-Fixtures — genau wie in
`test_concept_probe_counter.py`, das dieselbe Route bereits ohne Marker
testet. Damit liefen diese Tests seit ihrer Einführung nie im Standardlauf
mit (`addopts = -m "not integration"` in pytest.ini deselektiert sie) und ihr
Mock-Portfolio verrottete unbemerkt.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Gemeinsame Test-Fixtures / Payload
# ---------------------------------------------------------------------------

# GEÄNDERT: Payload auf das echte Wire-Format gebracht (buildBacktestPayload):
# Flat-Spec (Inputs direkt am Top-Level, kein 'inputs'-Wrapper), Rules im
# Block-Format (DNF), Stops im Sonderschlüssel '_stops' statt im Portfolio.
# GEÄNDERT (Ticket 94): Eingabefeld 'source' statt 'src' — dwsFastSMA ist mit
# input_names=['source'] gebaut (user_data/utils/indicators/custom.py); 'src'
# war schlicht falsch und führte als Vorlage in die Irre (Fund aus Ticket 91).
_SAMPLE_INDICATORS = {
    'fast_sma': {
        'indicator': 'dwsFastSMA',
        'tf': '4h',
        'source': 'close',
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
}

_SAMPLE_RULES = {
    'entry': {'blocks': []},
    'exit': None,
}

_SAMPLE_PORTFOLIO = {
    'size': 100,
    'size_type': 'value',
    'init_cash': 100,
    'fees': 0.001,
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


def _make_fake_pf(
    total_return: float = 0.1234,
    trade_count: int = 42,
    sharpe_ratio: float = 1.0,
    position_coverage: float = 0.5,
) -> MagicMock:
    """Erzeugt ein Mock-Portfolio auf dem Stand der echten Route.

    GEÄNDERT (Ticket 94): Der Zeitindex ist ein echter, zeitzonenbewusster
    DatetimeIndex — die Route schneidet das Portfolio über
    `slice_to_trading_window` auf das Handelsfenster (start/end aus
    _SAMPLE_DATA) zu, das dort tz-aware Zeitstempel vergleicht; ein reiner
    MagicMock-Index bricht daran mit TypeError ab. `.loc[...]` liefert bewusst
    dasselbe Mock-Objekt zurück, damit die unten gesetzten Kennzahlen nach dem
    Zuschnitt erhalten bleiben (sonst wäre pf_window ein unabhängiger,
    unkonfigurierter Mock).
    """
    pf = MagicMock()
    pf.wrapper.index = pd.date_range('2022-01-01', '2022-06-01', freq='4h', tz='UTC')
    pf.loc.__getitem__.return_value = pf
    pf.total_return = total_return
    pf.sharpe_ratio = sharpe_ratio
    pf.max_drawdown = 0.05
    pf.total_market_return = 0.08
    pf.position_coverage = position_coverage
    pf.trades.records_readable = [MagicMock()] * trade_count
    pf.trades.count.return_value = trade_count
    pf.trades.status_open.count.return_value = 0
    pf.trades.status_closed.profit_factor = 1.5
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

def test_lite_endpoint_happy_path():
    """run_backtest_lite liefert 200 mit total_return, trades, duration_ms.

    Prüft korrekte Felder und Typen im Response-Dict — inklusive der mit den
    Tickets 90 und 92 hinzugekommenen Felder sharpe_ratio,
    position_coverage_pct und concept_probe_count (Ticket 94). Das
    Konzept-Zähler-Feld selbst — Erhöhung, Isolation je Konzept, 404 bei
    unbekannter ID — ist bereits vollständig in
    tests/test_concept_probe_counter.py abgedeckt; hier wird nur geprüft, dass
    die Route das Feld ohne concept_id sauber als None ausweist.
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
    assert 'sharpe_ratio' in d, "Feld sharpe_ratio fehlt"
    assert 'position_coverage_pct' in d, "Feld position_coverage_pct fehlt"
    assert 'concept_probe_count' in d, "Feld concept_probe_count fehlt"
    assert isinstance(d['total_return'], float), f"total_return soll float sein, ist {type(d['total_return'])}"
    assert isinstance(d['trades'], int), f"trades soll int sein, ist {type(d['trades'])}"
    assert isinstance(d['duration_ms'], int), f"duration_ms soll int sein, ist {type(d['duration_ms'])}"
    assert isinstance(d['sharpe_ratio'], float), f"sharpe_ratio soll float sein, ist {type(d['sharpe_ratio'])}"
    assert isinstance(d['position_coverage_pct'], float), (
        f"position_coverage_pct soll float sein, ist {type(d['position_coverage_pct'])}"
    )
    assert abs(d['total_return'] - 0.1234) < 1e-9, f"Unerwarteter total_return: {d['total_return']}"
    assert d['trades'] == 42, f"Unerwartete trades: {d['trades']}"
    assert d['duration_ms'] >= 0, "duration_ms soll nicht negativ sein"
    assert abs(d['sharpe_ratio'] - 1.0) < 1e-9, f"Unerwarteter sharpe_ratio: {d['sharpe_ratio']}"
    assert abs(d['position_coverage_pct'] - 50.0) < 1e-9, (
        f"Unerwarteter position_coverage_pct: {d['position_coverage_pct']}"
    )
    # Ohne concept_id im Payload zählt der Aufruf nicht mit — die Route
    # unterscheidet bewusst None (kein Konzept-Bezug) von 0 (Fund Ticket 92).
    assert d['concept_probe_count'] is None, (
        f"concept_probe_count soll ohne concept_id None sein, ist {d['concept_probe_count']}"
    )


# ---------------------------------------------------------------------------
# Validierungsfehler
# ---------------------------------------------------------------------------

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
    # GEÄNDERT: Der Endpunkt liefert bewusst den reinen Fehlertext — das Quell-Label
    # ("Schnellbacktest: ") setzt das Frontend-Banner. Assertion war veraltet.
    assert exc_info.value.detail == 'Backtest-Fehler'


# ---------------------------------------------------------------------------
# DB-Isolations-Pflicht
# ---------------------------------------------------------------------------

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

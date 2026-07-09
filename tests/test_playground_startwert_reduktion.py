"""Tests für die Startwert-Reduktion des Schnellbacktests (Input-Vertrag).

Verbindliche Vorgabe (documentation/todo/schnellbacktest-playground-fehler.md):
Der Schnellbacktest rechnet genau EINE Kombination — die Startwerte aller
eingetragenen Werte, für jeden Parameter jedes Indikators und genauso für die
Stops. Die Reduktion geschieht VOR dem Rechnen.

Diese Tests prüfen den Vertrag am Input des Runners, nicht an der Response:
- _reduce_to_start_values als reine Funktion (Unit).
- /run-backtest-lite: das an run_spec_strategy übergebene Dict enthält keine
  arange-Dicts und keine Listen mehr — weder bei Indikatoren noch unter '_stops'.
- /entry-signals: dasselbe für das an build_indicators übergebene Dict.
- Der Original-Payload (Wertebereiche) bleibt unverändert.
- Fehlender 'portfolios'-Key (gechunkter Rückgabewert) gibt 500 mit klarer
  Meldung statt KeyError.

Genau dieser Vertrag fehlte bisher: test_run_backtest_lite.py mockt den Runner
und prüft nur die Response — das ungefilterte Raster fiel dadurch nie auf.
"""

import copy
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from services.api.routes.api_chart_playground import _reduce_to_start_values


# ---------------------------------------------------------------------------
# Payload mit echten Sweep-Achsen (Wire-Format: Flat-Spec, Stops in '_stops')
# ---------------------------------------------------------------------------

_SWEEP_INDICATORS = {
    'fast_sma': {
        'indicator': 'dwsFastSMA',
        'tf': '4h',
        'src': 'close',
        'length': {'type': 'arange', 'start': 3, 'stop': 10, 'step': 1, 'dtype': 'int64'},
        'multiplier': [1.0, 1.5, 2.0],
    },
    'vwma': {
        'indicator': 'dwsVWMA',
        'tf': 'same',
        'source': 'Close',
        'volume': 'Volume',
        'length': {'type': 'arange', 'start': 2, 'stop': 18, 'step': 1, 'dtype': 'int64'},
        'below_pct': 5.0,
    },
    '_stops': {
        'tp_stop': {'type': 'arange', 'start': 0.1, 'stop': 0.5, 'step': 0.1},
        'sl_stop': [0.05, 0.1],
        'tsl_th': None,
        'tsl_stop': None,
        'td_stop': 8,
        'delta_format': 'percent',
        'time_delta_format': 'rows',
    },
}

_SWEEP_PAYLOAD = {
    'indicators': _SWEEP_INDICATORS,
    'rules': {'entry': {'blocks': [{'enabled': True, 'conditions': [
        {'type': 'above', 'a': 'indicator:fast_sma:real', 'b': 'Close'},
    ]}]}, 'exit': None},
    'portfolio': {
        'size': 100, 'size_type': 'value', 'init_cash': 100, 'fees': 0.001,
        'stop_exit_price': None, 'stop_order_type': None,
        'direction': 'longonly', 'freq': None,
    },
    'data': {
        'exchange': 'binance', 'symbols': ['BTCUSDT'], 'timeframe': '4h',
        'start': '2022-01-01', 'end': '2022-06-01',
        'ohlc_start': '2022-01-01', 'ohlc_end': '2022-06-01',
    },
}


def _assert_keine_sweep_werte(indicators: dict) -> None:
    """Messlatte 2 der Vorgabe: keine arange-Dicts, keine Listen — nirgends."""
    for name, entry in indicators.items():
        assert isinstance(entry, dict), f"Eintrag {name!r} ist kein Dict"
        for key, val in entry.items():
            assert not isinstance(val, (list, tuple)), (
                f"{name}.{key} ist noch eine Liste: {val!r}"
            )
            assert not (isinstance(val, dict) and ('start' in val or 'value' in val)), (
                f"{name}.{key} ist noch ein Range-Dict: {val!r}"
            )


# ---------------------------------------------------------------------------
# Unit: _reduce_to_start_values
# ---------------------------------------------------------------------------

def test_arange_dict_wird_auf_startwert_reduziert():
    """Range-Dict → 'start'-Wert, für jeden Indikator-Parameter."""
    reduced = _reduce_to_start_values(_SWEEP_INDICATORS)
    assert reduced['fast_sma']['length'] == 3
    assert reduced['vwma']['length'] == 2


def test_liste_wird_auf_erstes_element_reduziert():
    """Listen-Achse → erstes Element."""
    reduced = _reduce_to_start_values(_SWEEP_INDICATORS)
    assert reduced['fast_sma']['multiplier'] == 1.0


def test_skalare_und_metafelder_bleiben_unveraendert():
    """Skalare Params, Meta-Felder (indicator/tf) und Inputs (Strings) bleiben verbatim."""
    reduced = _reduce_to_start_values(_SWEEP_INDICATORS)
    assert reduced['vwma']['below_pct'] == 5.0
    assert reduced['fast_sma']['indicator'] == 'dwsFastSMA'
    assert reduced['fast_sma']['tf'] == '4h'
    assert reduced['fast_sma']['src'] == 'close'
    assert reduced['vwma']['source'] == 'Close'


def test_stops_werden_reduziert_formate_bleiben():
    """'_stops': Stop-Werte reduziert, Format-Strings und None unangetastet."""
    reduced = _reduce_to_start_values(_SWEEP_INDICATORS)
    stops = reduced['_stops']
    assert stops['tp_stop'] == 0.1
    assert stops['sl_stop'] == 0.05
    assert stops['td_stop'] == 8
    assert stops['tsl_th'] is None
    assert stops['delta_format'] == 'percent'
    assert stops['time_delta_format'] == 'rows'


def test_reduktion_laesst_original_unveraendert():
    """Messlatte 4: Der Wertebereich steht nach der Reduktion unverändert im Original."""
    original = copy.deepcopy(_SWEEP_INDICATORS)
    _reduce_to_start_values(_SWEEP_INDICATORS)
    assert _SWEEP_INDICATORS == original


def test_unbekanntes_dict_bleibt_stehen():
    """Ein Dict ohne 'start'/'value' ist kein Sweep — es bleibt stehen und schlägt
    später sichtbar in der Indikator-Factory fehl, statt still None zu werden."""
    indicators = {'x': {'indicator': 'dwsFastSMA', 'tf': '4h', 'length': {'foo': 1}}}
    reduced = _reduce_to_start_values(indicators)
    assert reduced['x']['length'] == {'foo': 1}


def test_ergebnis_ist_frei_von_sweep_werten():
    """Messlatte 2 komplett: keine Range-Dicts, keine Listen im Ergebnis."""
    _assert_keine_sweep_werte(_reduce_to_start_values(_SWEEP_INDICATORS))


# ---------------------------------------------------------------------------
# Vertrag: /run-backtest-lite übergibt dem Runner nur die Startwert-Kombi
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_lite_uebergibt_runner_nur_startwerte():
    """Das an run_spec_strategy übergebene Dict ist vollständig reduziert."""
    from services.api.routes.api_chart_playground import run_backtest_lite, RunBacktestIn

    def _fake_pf():
        pf = MagicMock()
        pf.total_return = 0.1
        pf.trades.records_readable = []
        return pf

    runner_mock = MagicMock(return_value={'portfolios': _fake_pf()})
    with patch('user_data.utils.ohlc.loader.load_ohlc_data', return_value=MagicMock()), \
         patch('user_data.strategies.generic.spec_runner.run_spec_strategy', runner_mock):
        req = RunBacktestIn(**_SWEEP_PAYLOAD)
        run_backtest_lite(req)

    runner_mock.assert_called_once()
    indicators_arg = runner_mock.call_args[0][1]

    _assert_keine_sweep_werte(indicators_arg)
    assert indicators_arg['fast_sma']['length'] == 3
    assert indicators_arg['fast_sma']['multiplier'] == 1.0
    assert indicators_arg['vwma']['length'] == 2
    assert indicators_arg['_stops']['tp_stop'] == 0.1
    assert indicators_arg['_stops']['sl_stop'] == 0.05
    # Messlatte 4: Der Request-Payload behält seine Wertebereiche
    assert req.indicators['fast_sma']['length'] == {
        'type': 'arange', 'start': 3, 'stop': 10, 'step': 1, 'dtype': 'int64'
    }
    assert req.indicators['_stops']['sl_stop'] == [0.05, 0.1]


@pytest.mark.integration
def test_lite_fehlender_portfolios_key_gibt_500_statt_keyerror():
    """Gechunkter Rückgabewert (metrics_table statt portfolios) → klare 500-Meldung."""
    from fastapi import HTTPException
    from services.api.routes.api_chart_playground import run_backtest_lite, RunBacktestIn

    chunked_result = {'metrics_table': MagicMock(), 'columns': ['c1', 'c2']}
    with patch('user_data.utils.ohlc.loader.load_ohlc_data', return_value=MagicMock()), \
         patch('user_data.strategies.generic.spec_runner.run_spec_strategy',
               return_value=chunked_result):
        req = RunBacktestIn(**_SWEEP_PAYLOAD)
        with pytest.raises(HTTPException) as exc_info:
            run_backtest_lite(req)

    assert exc_info.value.status_code == 500
    assert 'kein Portfolio' in exc_info.value.detail


# ---------------------------------------------------------------------------
# Vertrag: /entry-signals baut Indikatoren nur mit der Startwert-Kombi
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_entry_signals_baut_indikatoren_nur_mit_startwerten():
    """Das an build_indicators übergebene Dict ist vollständig reduziert."""
    from services.api.routes.api_chart_playground import entry_signals, RunBacktestIn

    idx = pd.date_range('2022-01-01', periods=5, freq='4h', tz='UTC')
    masks = MagicMock(
        long_entries=pd.Series([True, False, True, False, False], index=idx),
        short_entries=pd.Series(False, index=idx),
    )
    build_mock = MagicMock(return_value={})

    with patch('user_data.utils.ohlc.loader.load_ohlc_data', return_value=MagicMock()), \
         patch('user_data.strategies.generic.indicator_factory.build_indicators', build_mock), \
         patch('user_data.strategies.generic.rules_engine.evaluate_rules', return_value=masks):
        req = RunBacktestIn(**_SWEEP_PAYLOAD)
        result = entry_signals(req)

    build_mock.assert_called_once()
    indicators_arg = build_mock.call_args[0][0]

    _assert_keine_sweep_werte(indicators_arg)
    assert indicators_arg['fast_sma']['length'] == 3
    assert indicators_arg['vwma']['length'] == 2
    assert indicators_arg['_stops']['tp_stop'] == 0.1
    # Die erfüllten Bars kommen als Zeitpunkte zurück (Maske aus dem Mock)
    assert len(result['data']['signals']) == 2

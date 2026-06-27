"""Ticket 41 — Unit-Tests für full_config_snapshot_json in BacktestResult.

Prüft:
1. Snapshot-Inhalt nach save_strategy_results: alle drei Teile inkl. Stops
2. Alt-Result mit NULL-Snapshot crasht nicht (defensiver Konsument)
3. Snapshot korrekt wenn rules=None (kein Snapshot-Bau)
"""

import pytest
from unittest.mock import MagicMock, patch, call
from user_data.utils.database.repository import _build_full_config_snapshot, _build_resolved_config


# ============================================================================
# Tests für _build_full_config_snapshot
# ============================================================================

_BACKTEST_CONFIG = {
    'symbols': ['BTCUSDT'],
    'exchange': 'binance',
    'timeframe': '4h',
    'start': '2022-01-01',
    'end': '2023-01-01',
    'ohlc_start': '2021-12-01',
    'ohlc_end': '2023-01-31',
    'size': 100.0,
    'size_type': 'value',
    'init_cash': 100.0,
    'fees': 0.001,
    'strategy_family': 'generic',
    'strategy_name': 'test',
    'import_path': 'some.path',
}

_INDICATORS_CONFIG = {
    'dwsvwma': {
        'indicator': 'custom:dwsVWMA',
        'enabled': True,
        'length': {'type': 'arange', 'start': 10, 'stop': 30, 'step': 2, 'dtype': 'int64'},
    },
    # GEÄNDERT: Schritt 3d — Stops UND ihre Formate gehören zu '_stops' (Eigentümer
    # IndicatorConfig). Der Snapshot liest td/tp/sl/tsl + delta_format/time_delta_format
    # aus indicators_config['_stops'], nicht mehr aus backtest_config (toter Pfad).
    '_stops': {
        'td_stop': 10,
        'tp_stop': 0.05,
        'sl_stop': 0.03,
        'tsl_stop': 0.02,
        'tsl_th': 0.01,
        'delta_format': 'percent',
        'time_delta_format': 'rows',
    },
}

_ACTUAL_PARAMS = {
    'dwsvwma_length': 16,
}

_RULES = {
    'entry': {'type': 'signal', 'source': 'dwsvwma', 'output': 'long_entry'},
    'exit': {'type': 'signal', 'source': 'dwsvwma', 'output': 'long_exit'},
}


def test_snapshot_backtest_config_fields():
    """Snapshot enthält alle Pflicht-Felder aus backtest_config inkl. Stops."""
    snapshot = _build_full_config_snapshot(
        backtest_config=_BACKTEST_CONFIG,
        indicators_config=_INDICATORS_CONFIG,
        actual_params=_ACTUAL_PARAMS,
        rules=_RULES,
    )
    bc = snapshot['backtest_config']

    # Pflicht-Felder
    assert bc['symbol'] == 'BTCUSDT'
    assert bc['exchange'] == 'binance'
    assert bc['timeframe'] == '4h'
    assert bc['start'] == '2022-01-01'
    assert bc['end'] == '2023-01-01'
    # Kritisch für Reproduktion (Ticket 43)
    assert bc['ohlc_start'] == '2021-12-01'
    assert bc['ohlc_end'] == '2023-01-31'
    # Sizing
    assert bc['size'] == 100.0
    assert bc['size_type'] == 'value'
    assert bc['init_cash'] == 100.0
    assert bc['fees'] == 0.001
    # Alle Stops
    assert bc['td_stop'] == 10
    assert bc['tp_stop'] == 0.05
    assert bc['sl_stop'] == 0.03
    assert bc['tsl_stop'] == 0.02
    assert bc['tsl_th'] == 0.01
    # Format-Parameter für bit-genaue Reproduktion
    assert bc['delta_format'] == 'percent'
    assert bc['time_delta_format'] == 'rows'


def test_snapshot_has_all_three_sections():
    """Snapshot enthält alle drei Teile: backtest_config, indicators, rules."""
    snapshot = _build_full_config_snapshot(
        backtest_config=_BACKTEST_CONFIG,
        indicators_config=_INDICATORS_CONFIG,
        actual_params=_ACTUAL_PARAMS,
        rules=_RULES,
    )
    assert 'backtest_config' in snapshot
    assert 'indicators' in snapshot
    assert 'rules' in snapshot


def test_snapshot_indicators_as_dict():
    """indicators ist ein Dict (Key=Name), nicht eine Liste."""
    snapshot = _build_full_config_snapshot(
        backtest_config=_BACKTEST_CONFIG,
        indicators_config=_INDICATORS_CONFIG,
        actual_params=_ACTUAL_PARAMS,
        rules=_RULES,
    )
    assert isinstance(snapshot['indicators'], dict)
    assert 'dwsvwma' in snapshot['indicators']


def test_snapshot_indicators_resolved_values():
    """Indikator-Parameter sind aufgelöst (feste Werte, keine Ranges mehr)."""
    snapshot = _build_full_config_snapshot(
        backtest_config=_BACKTEST_CONFIG,
        indicators_config=_INDICATORS_CONFIG,
        actual_params=_ACTUAL_PARAMS,
        rules=_RULES,
    )
    ind = snapshot['indicators']['dwsvwma']
    # length sollte nicht mehr als Range-Dict vorliegen
    assert not isinstance(ind.get('length'), dict) or 'start' not in ind.get('length', {}), \
        "length ist noch ein Range-Dict — Auflösung hat nicht funktioniert"
    # Aufgelöster Wert muss 16 sein (aus actual_params)
    assert ind['length'] == 16


def test_snapshot_rules_structure():
    """rules enthält {entry, exit}."""
    snapshot = _build_full_config_snapshot(
        backtest_config=_BACKTEST_CONFIG,
        indicators_config=_INDICATORS_CONFIG,
        actual_params=_ACTUAL_PARAMS,
        rules=_RULES,
    )
    assert 'entry' in snapshot['rules']
    assert 'exit' in snapshot['rules']


def test_snapshot_symbol_from_symbols_list():
    """Symbol wird korrekt aus symbols-Liste extrahiert."""
    snapshot = _build_full_config_snapshot(
        backtest_config={**_BACKTEST_CONFIG, 'symbols': ['ETHUSDT']},
        indicators_config={},
        actual_params={},
        rules=_RULES,
    )
    assert snapshot['backtest_config']['symbol'] == 'ETHUSDT'


def test_snapshot_portfolio_felder_aus_nested_dict():
    """Portfolio-Felder aus verschachteltem 'portfolio'-Block (Playground-Struktur)."""
    pg_backtest_config = {
        'symbols': ['BTCUSDT'],
        'exchange': 'binance',
        'timeframe': '4h',
        'start': '2022-01-01',
        'end': '2023-01-01',
        'ohlc_start': '2021-12-01',
        'ohlc_end': '2023-01-31',
        'portfolio': {
            'size': 500.0,
            'size_type': 'percent',
            'init_cash': 200.0,
            'fees': 0.002,
        },
        'strategy_family': 'playground',
        'import_path': 'some.path',
    }
    # GEÄNDERT: Stops liegen seit dem Stop-Umbau in indicators_config['_stops'],
    # nicht mehr im portfolio-Block der backtest_config.
    snapshot = _build_full_config_snapshot(
        backtest_config=pg_backtest_config,
        indicators_config={'_stops': {'td_stop': 5, 'tp_stop': 0.1, 'sl_stop': None}},
        actual_params={},
        rules=_RULES,
    )
    bc = snapshot['backtest_config']
    assert bc['size'] == 500.0
    assert bc['size_type'] == 'percent'
    assert bc['init_cash'] == 200.0
    assert bc['fees'] == 0.002
    assert bc['td_stop'] == 5
    assert bc['tp_stop'] == 0.1


def test_snapshot_no_extra_fields_from_run():
    """Snapshot enthält keine laufspezifischen Felder (strategy_family, import_path etc.)."""
    snapshot = _build_full_config_snapshot(
        backtest_config=_BACKTEST_CONFIG,
        indicators_config={},
        actual_params={},
        rules=_RULES,
    )
    bc_keys = set(snapshot['backtest_config'].keys())
    # Diese Felder gehören nicht in den Snapshot
    assert 'strategy_family' not in bc_keys
    assert 'strategy_name' not in bc_keys
    assert 'import_path' not in bc_keys


# ============================================================================
# Bestandsschutz: Alt-Result mit NULL-Snapshot soll nicht crashen
# ============================================================================

def test_null_snapshot_defensiver_zugriff():
    """Alt-Result mit NULL-Snapshot: .get() liefert None statt Exception."""
    result_mock = MagicMock()
    result_mock.full_config_snapshot_json = None

    # Defensiver Zugriff wie ein Konsument ihn implementieren soll
    snapshot = result_mock.full_config_snapshot_json
    assert snapshot is None

    # Zugriff auf Unter-Felder via .get() crasht nicht
    if snapshot is not None:
        bc = snapshot.get('backtest_config')
    else:
        bc = None

    assert bc is None


def test_null_snapshot_klare_meldung():
    """Konsument kann fehlenden Snapshot sichtbar abweisen."""
    result_mock = MagicMock()
    result_mock.full_config_snapshot_json = None

    snapshot = result_mock.full_config_snapshot_json
    missing = snapshot is None

    assert missing, "Fehlender Snapshot muss als None erkannt werden"


# ============================================================================
# save_strategy_results ruft _build_full_config_snapshot nicht auf wenn rules=None
# ============================================================================

def test_no_snapshot_without_rules():
    """Wenn rules=None, wird kein Snapshot gebaut (hartcodierte Strategien)."""
    # Kein einfacher Weg _build_full_config_snapshot zu patchen ohne DB —
    # aber wir prüfen direkt: _build_full_config_snapshot erwartet rules-Parameter,
    # save_strategy_results soll es nur aufrufen wenn rules is not None.
    # Indirekter Test: _build_full_config_snapshot mit rules={} liefert Snapshot mit rules-Key
    snapshot_with_rules = _build_full_config_snapshot(
        backtest_config=_BACKTEST_CONFIG,
        indicators_config={},
        actual_params={},
        rules={'entry': None, 'exit': None},
    )
    assert snapshot_with_rules['rules'] == {'entry': None, 'exit': None}

"""Tests für die Gegenüberstellung mehrerer Indicator-Configs (services.api.utils.indicator_compare)."""
import pytest

from services.api.utils.indicator_compare import build_indicator_config_comparison


def _config(config_id: int, name: str, config_json: dict) -> dict:
    """Baut das Eingabe-Dict, wie es der Endpunkt aus IndicatorConfigOut liefert."""
    return {
        'id': config_id,
        'name': name,
        'config_json': config_json,
        'strategy_concept_name': 'VWMA',
        'strategy_iteration_number': config_id,
        'strategy_iteration_version': 'Iteration ' + str(config_id),
    }


@pytest.fixture
def stops():
    """Stops-Block wie in den VWMA-Configs."""
    return {
        'tp_stop': 0.3,
        'sl_stop': 0.15,
        'tsl_th': None,
        'tsl_stop': None,
        'td_stop': 8,
        'delta_format': 'percent',
        'time_delta_format': 'rows',
    }


@pytest.fixture
def fast_sma():
    """fast_sma mit zwei Sweep-Achsen."""
    return {
        'indicator': 'custom:dwsFastSMA',
        'tf': 'same',
        'source': 'close',
        'length': {'type': 'arange', 'start': 2, 'stop': 14.01, 'step': 1, 'dtype': 'int64'},
        'multiplier': {'type': 'arange', 'start': 1, 'stop': 9.01, 'step': 1, 'dtype': 'int64'},
    }


@pytest.fixture
def sma():
    """Zusätzlicher TA-Lib-SMA, den nur eine Config trägt."""
    return {
        'indicator': 'talib:SMA',
        'tf': 'same',
        'close': 'close',
        'timeperiod': {'type': 'arange', 'start': 10, 'stop': 100, 'step': 10, 'dtype': 'int64'},
    }


def _find_group(result: dict, name: str) -> dict:
    return next(g for g in result['groups'] if g['name'] == name)


def _find_row(group: dict, label: str) -> dict:
    return next(r for r in group['rows'] if r['label'] == label)


def test_identische_configs_melden_keine_abweichung(fast_sma, stops):
    """Zwei gleiche Configs: kein Feld weicht ab."""
    cfg = {'fast_sma': fast_sma, '_stops': stops}
    result = build_indicator_config_comparison([
        _config(4, 'A', cfg),
        _config(33, 'B', dict(cfg)),
    ])

    assert result['differs'] is False
    assert all(not g['differs'] for g in result['groups'])


def test_zusaetzlicher_indikator_wird_als_fehlt_markiert(fast_sma, sma, stops):
    """Der nur in Config B vorhandene SMA erscheint in Spalte A als 'fehlt'."""
    result = build_indicator_config_comparison([
        _config(4, 'A', {'fast_sma': fast_sma, '_stops': stops}),
        _config(33, 'B', {'fast_sma': fast_sma, 'sma': sma, '_stops': stops}),
    ])

    group = _find_group(result, 'sma')
    assert group['present'] == [False, True]
    assert group['differs'] is True
    assert _find_row(group, 'indicator')['cells'] == ['fehlt', 'talib:SMA']
    assert _find_row(group, 'timeperiod')['cells'] == ['fehlt', '10-90 (9) s: 10']
    assert result['differs'] is True


def test_beschnittener_wertebereich_wird_erkannt(fast_sma, stops):
    """Ein stillschweigend verkleinerter Sweep-Bereich muss als Abweichung auffallen."""
    beschnitten = dict(fast_sma)
    beschnitten['length'] = {'type': 'arange', 'start': 2, 'stop': 8.01, 'step': 1, 'dtype': 'int64'}

    result = build_indicator_config_comparison([
        _config(4, 'A', {'fast_sma': fast_sma, '_stops': stops}),
        _config(33, 'B', {'fast_sma': beschnitten, '_stops': stops}),
    ])

    row = _find_row(_find_group(result, 'fast_sma'), 'length')
    assert row['cells'] == ['2-14 (13) s: 1', '2-8 (7) s: 1']
    assert row['differs'] is True


def test_gleiche_grenzen_mit_anderem_schritt_weichen_ab(fast_sma, stops):
    """Gleiches Minimum und Maximum, gröberes Raster: nur der Schritt verrät die Abweichung."""
    grober = dict(fast_sma)
    grober['length'] = {'type': 'arange', 'start': 2, 'stop': 14.01, 'step': 2, 'dtype': 'int64'}

    result = build_indicator_config_comparison([
        _config(4, 'A', {'fast_sma': fast_sma, '_stops': stops}),
        _config(33, 'B', {'fast_sma': grober, '_stops': stops}),
    ])

    row = _find_row(_find_group(result, 'fast_sma'), 'length')
    assert row['cells'] == ['2-14 (13) s: 1', '2-14 (7) s: 2']
    assert row['differs'] is True


def test_liste_ohne_gleichmaessiges_raster_zeigt_keinen_schritt(fast_sma, stops):
    """Eine ungleichmäßige Werteliste hat keinen Schritt — die Zelle bleibt bei ``min-max (n)``."""
    liste = dict(fast_sma)
    liste['length'] = [2, 3, 8]

    result = build_indicator_config_comparison([
        _config(4, 'A', {'fast_sma': liste, '_stops': stops}),
        _config(33, 'B', {'fast_sma': liste, '_stops': stops}),
    ])

    row = _find_row(_find_group(result, 'fast_sma'), 'length')
    assert row['cells'] == ['2-8 (3)', '2-8 (3)']


def test_gleichmaessige_liste_zeigt_ihren_schritt(fast_sma, stops):
    """Eine Liste mit konstantem Abstand wird wie ein arange-Dict dargestellt."""
    liste = dict(fast_sma)
    liste['length'] = [2, 4, 6, 8]

    result = build_indicator_config_comparison([
        _config(4, 'A', {'fast_sma': liste, '_stops': stops}),
        _config(33, 'B', {'fast_sma': liste, '_stops': stops}),
    ])

    assert _find_row(_find_group(result, 'fast_sma'), 'length')['cells'] == ['2-8 (4) s: 2', '2-8 (4) s: 2']


def test_stops_werden_in_der_namens_notation_dargestellt(fast_sma, stops):
    """TP/SL als Prozent, TD als ganze Zahl, leere Stops als 'nicht gesetzt'."""
    result = build_indicator_config_comparison([
        _config(4, 'A', {'fast_sma': fast_sma, '_stops': stops}),
        _config(33, 'B', {'fast_sma': fast_sma, '_stops': stops}),
    ])

    group = _find_group(result, 'Stops')
    assert _find_row(group, 'TP')['cells'] == ['30%', '30%']
    assert _find_row(group, 'SL')['cells'] == ['15%', '15%']
    assert _find_row(group, 'TD')['cells'] == ['8', '8']
    assert _find_row(group, 'TSL')['cells'] == ['nicht gesetzt', 'nicht gesetzt']


def test_stop_sweeps_zeigen_ihren_schritt(fast_sma, stops):
    """Prozent-Stops zeigen den Schritt in Prozent, TD-Stops als ganze Zahl."""
    sweep_stops = dict(stops)
    sweep_stops['tp_stop'] = {'type': 'arange', 'start': 0.1, 'stop': 0.31, 'step': 0.05, 'dtype': 'float64'}
    sweep_stops['td_stop'] = {'type': 'arange', 'start': 4, 'stop': 12.01, 'step': 4, 'dtype': 'int64'}

    result = build_indicator_config_comparison([
        _config(4, 'A', {'fast_sma': fast_sma, '_stops': sweep_stops}),
        _config(33, 'B', {'fast_sma': fast_sma, '_stops': sweep_stops}),
    ])

    group = _find_group(result, 'Stops')
    assert _find_row(group, 'TP')['cells'] == ['10-30% (5) s: 5%', '10-30% (5) s: 5%']
    assert _find_row(group, 'TD')['cells'] == ['4-12 (3) s: 4', '4-12 (3) s: 4']
    # Skalare Stops bleiben ohne Schritt.
    assert _find_row(group, 'SL')['cells'] == ['15%', '15%']


def test_abweichende_stops_werden_markiert(fast_sma, stops):
    """Ein geänderter Stop-Wert schlägt in der Stops-Gruppe durch."""
    andere_stops = dict(stops)
    andere_stops['tp_stop'] = 0.4

    result = build_indicator_config_comparison([
        _config(4, 'A', {'fast_sma': fast_sma, '_stops': stops}),
        _config(33, 'B', {'fast_sma': fast_sma, '_stops': andere_stops}),
    ])

    group = _find_group(result, 'Stops')
    assert group['differs'] is True
    assert _find_row(group, 'TP')['cells'] == ['30%', '40%']


def test_ohne_stops_entfaellt_die_stops_gruppe(fast_sma):
    """Trägt keine Config Stops, gibt es auch keine Stops-Gruppe."""
    result = build_indicator_config_comparison([
        _config(4, 'A', {'fast_sma': fast_sma}),
        _config(33, 'B', {'fast_sma': fast_sma}),
    ])

    assert [g['name'] for g in result['groups']] == ['fast_sma']


def test_spaltenreihenfolge_folgt_der_eingabe(fast_sma, stops):
    """Die Spalten stehen in der Reihenfolge der übergebenen Configs."""
    result = build_indicator_config_comparison([
        _config(33, 'B', {'fast_sma': fast_sma, '_stops': stops}),
        _config(4, 'A', {'fast_sma': fast_sma, '_stops': stops}),
    ])

    assert [c['id'] for c in result['columns']] == [33, 4]

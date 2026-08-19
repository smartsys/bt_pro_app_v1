"""Tests für den App-Weg von Indikator-Referenz-Stops (Ticket 103, Teilaufgabe 3).

Der Rechenkern (Auflösung, Multi-Combo, Live/Ratsche) ist in
`tests/test_stop_indicator_reference.py` abgedeckt. Hier geht es um die Stellen,
über die der App-/Toolbox-Weg läuft und die vorher nicht mit einem Referenz-Dict
gerechnet hatten:

  1. Der Config-Name (`indicator_labels.build_indicator_config_name`) rechnet
     heute `v * 100` auf jeden gesetzten Stop-Wert — mit einem Referenz-Dict
     kracht das ohne den Fix.
  2. Der Preflight-Endpoint weist Referenz-Stops (Indikator, Faktor, Live,
     Ratsche) lesbar aus, statt sie stillschweigend zu ignorieren.
"""

import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# rq ist nur im Worker-Container installiert — für reine Tests stubben wir den Import
# (Konvention aus tests/test_preflight_endpoint.py).
if 'rq' not in sys.modules:
    rq_stub = types.ModuleType('rq')
    rq_stub.Queue = object
    sys.modules['rq'] = rq_stub

import pytest  # noqa: E402

from services.api.routes.api_chart_playground import (  # noqa: E402
    _preflight_stop_ref_summary,
)
from services.api.utils.indicator_labels import (  # noqa: E402
    build_indicator_config_description,
    build_indicator_config_labels,
    build_indicator_config_name,
)


def _atr_indicator_config() -> dict:
    return {
        'atr14': {
            'indicator': 'talib:ATR', 'tf': 'same',
            'high': 'high', 'low': 'low', 'close': 'close', 'timeperiod': 14,
        },
    }


class TestConfigNameWithReferenceStop:
    def test_name_enthaelt_indikator_und_faktor_statt_typeerror(self):
        cfg = {
            **_atr_indicator_config(),
            '_stops': {'sl_stop': {'ref': 'indicator:atr14:real', 'mult': 5.0}},
        }
        name = build_indicator_config_name(cfg, 'squeeze-bollinger-002', 28)
        assert 'SL 5 × atr14' in name

    def test_live_und_ratchet_erscheinen_im_namen(self):
        cfg = {
            **_atr_indicator_config(),
            '_stops': {
                'tsl_stop': {
                    'ref': 'indicator:atr14:real', 'mult': 2.5,
                    'live': True, 'ratchet': False,
                },
            },
        }
        name = build_indicator_config_name(cfg, None, None)
        assert 'TSL 2.5 × atr14 live, no-ratchet' in name

    def test_live_true_mit_default_ratchet_zeigt_kein_no_ratchet(self):
        cfg = {
            **_atr_indicator_config(),
            '_stops': {'tsl_stop': {'ref': 'indicator:atr14:real', 'mult': 2.5, 'live': True}},
        }
        name = build_indicator_config_name(cfg, None, None)
        assert 'live' in name
        assert 'no-ratchet' not in name

    def test_gemischte_stops_skalar_und_referenz_im_selben_namen(self):
        cfg = {
            **_atr_indicator_config(),
            '_stops': {
                'tp_stop': 0.30,
                'sl_stop': {'ref': 'indicator:atr14:real', 'mult': 5.0},
            },
        }
        name = build_indicator_config_name(cfg, None, None)
        assert 'TP 30%' in name
        assert 'SL 5 × atr14' in name

    def test_referenz_auf_td_stop_wird_nicht_als_prozent_gerechnet(self):
        """td_stop läuft über _fmt_td (ganze Zahl statt Prozent) — auch dort muss
        die Referenz VOR dem Zahlen-Pfad abgefangen werden."""
        cfg = {
            **_atr_indicator_config(),
            '_stops': {'td_stop': {'ref': 'indicator:atr14:real', 'mult': 3.0}},
        }
        name = build_indicator_config_name(cfg, None, None)
        assert 'TD 3 × atr14' in name

    def test_unbekanntes_feld_im_referenz_dict_bricht_sichtbar_ab(self):
        cfg = {
            **_atr_indicator_config(),
            '_stops': {'sl_stop': {'ref': 'indicator:atr14:real', 'unbekannt': 1}},
        }
        with pytest.raises(ValueError, match='unbekannte Felder'):
            build_indicator_config_name(cfg, None, None)

    def test_labels_und_description_bleiben_stop_frei_und_kombinierbar(self):
        """build_indicator_config_labels() ruft Name UND Beschreibung auf — die
        Beschreibung listet nur Indikatoren, keine Stops (unverändertes Verhalten)."""
        cfg = {
            **_atr_indicator_config(),
            '_stops': {'sl_stop': {'ref': 'indicator:atr14:real', 'mult': 5.0}},
        }
        labels = build_indicator_config_labels(cfg, 'konzept', 1)
        assert 'SL 5 × atr14' in labels['name']
        assert 'atr14: timeperiod 14' in labels['description']
        assert build_indicator_config_description(cfg) == labels['description']


class TestPreflightStopRefSummary:
    def test_leer_ohne_referenz_stops(self):
        cfg = {**_atr_indicator_config(), '_stops': {'sl_stop': 0.15}}
        assert _preflight_stop_ref_summary(cfg) == []

    def test_leer_ohne_stops_block(self):
        assert _preflight_stop_ref_summary({}) == []

    def test_weist_indikator_faktor_und_live_ratchet_aus(self):
        cfg = {
            **_atr_indicator_config(),
            '_stops': {
                'sl_stop': {'ref': 'indicator:atr14:real', 'mult': 5.0},
                'tsl_stop': {
                    'ref': 'indicator:atr14:real', 'mult': 2.5,
                    'live': True, 'ratchet': False,
                },
            },
        }
        summary = _preflight_stop_ref_summary(cfg)
        by_key = {row['stop_key']: row for row in summary}

        assert by_key['sl_stop']['indicator_id'] == 'atr14'
        assert by_key['sl_stop']['output'] == 'real'
        assert by_key['sl_stop']['mult'] == 5.0
        assert by_key['sl_stop']['live'] is False
        assert by_key['sl_stop']['ratchet'] is True  # Default, obwohl nicht gesetzt

        assert by_key['tsl_stop']['live'] is True
        assert by_key['tsl_stop']['ratchet'] is False

    def test_unbekanntes_referenz_feld_bricht_sichtbar_ab(self):
        cfg = {
            **_atr_indicator_config(),
            '_stops': {'sl_stop': {'ref': 'indicator:atr14:real', 'unbekannt': 1}},
        }
        with pytest.raises(ValueError, match='unbekannte Felder'):
            _preflight_stop_ref_summary(cfg)

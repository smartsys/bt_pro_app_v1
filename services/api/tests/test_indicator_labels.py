"""Tests für die Label-Notation der Indicator-Config (services.api.utils.indicator_labels)."""
import pytest

from services.api.utils.indicator_labels import (
    build_indicator_config_description,
    build_indicator_config_labels,
    build_indicator_config_name,
)


@pytest.fixture
def config_2018():
    """config_json wie Indicator-Config 2018 (Teststrategie): zwei Indikatoren mit Range-Parametern + Stops."""
    return {
        "teststrategie": {
            "tf": "4h",
            "length": {"step": 0.5, "stop": 18.01, "type": "arange", "dtype": "float64", "start": 2},
            "source": "indicator:fast_sma:result",
            "volume": "volume",
            "below_pct": {"step": 1, "stop": 17.01, "type": "arange", "dtype": "float64", "start": 1},
            "indicator": "custom:dwsVWMA",
        },
        "_stops": {
            "tsl_th": None,
            "sl_stop": 0.15,
            "td_stop": 8,
            "tp_stop": 0.05,
            "tsl_stop": None,
            "delta_format": "percent",
            "time_delta_format": "rows",
        },
        "fast_sma": {
            "tf": "4h",
            "length": {"step": 1, "stop": 14.01, "type": "arange", "dtype": "int64", "start": 2},
            "source": "close",
            "indicator": "custom:dwsFastSMA",
            "multiplier": {"step": 1, "stop": 9.01, "type": "arange", "dtype": "int64", "start": 1},
        },
    }


# --- Name ---

def test_name_konzept_und_iteration(config_2018):
    # 33 * 17 * 13 * 9 = 65637 Kombinationen; Stops wandern in den Titel
    assert build_indicator_config_name(config_2018, "Teststrategie", 2) == "Teststrategie-2-(65.637) TP 5% SL 15% TD 8, rows"


def test_name_konzept_ohne_iteration(config_2018):
    assert build_indicator_config_name(config_2018, "Teststrategie", None) == "Teststrategie-(65.637) TP 5% SL 15% TD 8, rows"


def test_name_ohne_konzept_nur_kombinationen(config_2018):
    assert build_indicator_config_name(config_2018, None, None) == "(65.637) TP 5% SL 15% TD 8, rows"


def test_name_konzept_schreibweise_verbatim(config_2018):
    # Konzept-Name wird 1:1 übernommen, nicht klein-/großgewandelt
    assert build_indicator_config_name(config_2018, "EmaAdx", 7).startswith("EmaAdx-7-(")


def test_name_stops_notation_mit_tsl_und_sweep():
    # TP als Sweep (Zähler), TSL mit delta_format, TD mit time_delta_format
    config = {
        "ind": {"indicator": "custom:x", "length": 5},
        "_stops": {
            "tp_stop": {"step": 0.1, "stop": 0.41, "type": "arange", "dtype": "float64", "start": 0.1},
            "sl_stop": 0.05,
            "tsl_th": 0.02, "tsl_stop": 0.01,
            "td_stop": 8,
            "delta_format": "percent", "time_delta_format": "rows",
        },
    }
    name = build_indicator_config_name(config, "VWMA", 26)
    assert name.startswith("VWMA-26-(")
    assert name.endswith("TP 10-40% (4) SL 5% TSL 2%/1%, percent TD 8, rows")


# --- Beschreibung (Indikatoren mit Werten/Wertebereichen) ---

def test_description_config_2018_indikatoren(config_2018):
    # Topologisch: fast_sma vor teststrategie (teststrategie.source chained von fast_sma);
    # Inputs (source/volume) und Stops bleiben außen vor, Ranges als min-max (n)
    assert build_indicator_config_description(config_2018) == (
        "fast_sma: length 2-14 (13), multiplier 1-9 (9); "
        "teststrategie: length 2-18 (33), below_pct 1-17 (17)"
    )


def test_description_skalar_indikator():
    # Feste Skalar-Parameter werden als Wert aufgeführt (keine Range)
    config = {"fast_sma": {"tf": "4h", "length": 12, "source": "close",
                           "indicator": "custom:dwsFastSMA", "multiplier": 9}}
    assert build_indicator_config_description(config) == "fast_sma: length 12, multiplier 9"


def test_description_leer_ohne_indikatoren():
    assert build_indicator_config_description({}) == ""


def test_description_deaktivierter_indikator_ausgelassen():
    # enabled=False fliegt aus der Auflistung
    config = {
        "fast_sma": {"indicator": "custom:dwsFastSMA", "length": 12, "multiplier": 9},
        "off_ind": {"indicator": "custom:dwsFastSMA", "length": 5, "multiplier": 2, "enabled": False},
    }
    assert build_indicator_config_description(config) == "fast_sma: length 12, multiplier 9"


# --- Kombiniert ---

def test_build_labels_kombiniert(config_2018):
    labels = build_indicator_config_labels(config_2018, "Teststrategie", 2)
    assert labels == {
        "name": "Teststrategie-2-(65.637) TP 5% SL 15% TD 8, rows",
        "description": ("fast_sma: length 2-14 (13), multiplier 1-9 (9); "
                        "teststrategie: length 2-18 (33), below_pct 1-17 (17)"),
    }

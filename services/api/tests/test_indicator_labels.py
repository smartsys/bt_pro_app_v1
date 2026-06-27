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
    # 33 * 17 * 13 * 9 = 65637 Kombinationen
    assert build_indicator_config_name(config_2018, "Teststrategie", 2) == "Teststrategie-2 - 65.637 Kombi. 5/15"


def test_name_konzept_ohne_iteration(config_2018):
    assert build_indicator_config_name(config_2018, "Teststrategie", None) == "Teststrategie - 65.637 Kombi. 5/15"


def test_name_ohne_konzept_kein_fuehrender_trenner(config_2018):
    assert build_indicator_config_name(config_2018, None, None) == "65.637 Kombi. 5/15"


def test_name_konzept_schreibweise_verbatim(config_2018):
    # Konzept-Name wird 1:1 übernommen, nicht klein-/großgewandelt
    assert build_indicator_config_name(config_2018, "EmaAdx", 7).startswith("EmaAdx-7")


# --- Beschreibung ---

def test_description_config_2018(config_2018):
    # kein percent (tsl_th null), rows weil td_stop gesetzt
    assert build_indicator_config_description(config_2018["_stops"]) == "TP 5%, SL 15%, TD 8, rows"


def test_description_alles_gesetzt():
    stops = {
        "tp_stop": 0.30, "sl_stop": 0.15, "tsl_th": 0.10, "tsl_stop": 0.05,
        "td_stop": 8, "delta_format": "percent", "time_delta_format": "rows",
    }
    assert build_indicator_config_description(stops) == "TP 30%, SL 15%, TSL 10%/5%, percent, TD 8, rows"


def test_description_nur_tsl_stop_kein_delta_format():
    stops = {"tp_stop": None, "sl_stop": None, "tsl_th": None, "tsl_stop": 0.05,
             "td_stop": None, "delta_format": "percent", "time_delta_format": "rows"}
    assert build_indicator_config_description(stops) == "TSL 5%"


def test_description_nur_tsl_th_zeigt_delta_format():
    stops = {"tsl_th": 0.10, "delta_format": "percent"}
    assert build_indicator_config_description(stops) == "TSL 10%, percent"


def test_description_nur_td_zeigt_time_delta_format():
    stops = {"td_stop": 12, "time_delta_format": "index"}
    assert build_indicator_config_description(stops) == "TD 12, index"


def test_description_alle_stops_null_leer():
    stops = {"tp_stop": None, "sl_stop": None, "tsl_th": None, "tsl_stop": None,
             "td_stop": None, "delta_format": "percent", "time_delta_format": "rows"}
    assert build_indicator_config_description(stops) == ""


def test_description_leerer_stops_block():
    assert build_indicator_config_description({}) == ""


# --- Kombiniert ---

def test_build_labels_kombiniert(config_2018):
    labels = build_indicator_config_labels(config_2018, "Teststrategie", 2)
    assert labels == {
        "name": "Teststrategie-2 - 65.637 Kombi. 5/15",
        "description": "TP 5%, SL 15%, TD 8, rows",
    }

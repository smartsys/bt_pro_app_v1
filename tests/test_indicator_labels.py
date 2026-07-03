"""Tests fuer die Label-Notation (services.api.utils.indicator_labels).

Deckt die drei _stops-Wertformen ab — Skalar, Sweep-Liste und arange-Dict —
fuer Name und Beschreibung. Kernfall: Sweep-Stops duerfen die Notation nicht
mehr zum Absturz bringen (frueher TypeError: float() argument ... not 'list'),
sondern erscheinen als kompakter Bereich ``min-max (n)``.
"""
import pytest

from services.api.utils.indicator_labels import (
    build_indicator_config_description,
    build_indicator_config_labels,
    build_indicator_config_name,
)


def _arange(start, stop, step, dtype="float"):
    """Kanonisches arange-Dict wie im Frontend/der Toolbox."""
    return {"type": "arange", "start": start, "stop": stop, "step": step, "dtype": dtype}


# --- Skalar: unveraendertes Verhalten ---------------------------------------

def test_description_scalar_percent_and_td():
    stops = {"tp_stop": 0.3, "sl_stop": 0.15, "td_stop": 8, "time_delta_format": "rows"}
    assert build_indicator_config_description(stops) == "TP 30%, SL 15%, TD 8, rows"


def test_description_empty_stops():
    assert build_indicator_config_description({}) == ""


# --- Sweep-Liste: fruehere Crash-Ursache ------------------------------------

def test_description_td_sweep_list_renders_range_with_count():
    # Nicht zusammenhaengende 35er-Liste (min 1, max 999) — der VWMA-v3-Fall.
    td_values = list(range(1, 31)) + [36, 42, 48, 60, 999]
    stops = {
        "tp_stop": 0.3,
        "sl_stop": 0.15,
        "tsl_th": None,
        "tsl_stop": None,
        "td_stop": td_values,
        "delta_format": "percent",
        "time_delta_format": "rows",
    }
    assert len(td_values) == 35
    # Akzeptanzkriterium Ticket/To-Do Bug 2
    assert build_indicator_config_description(stops) == "TP 30%, SL 15%, TD 1-999 (35), rows"


def test_description_percent_sweep_list_single_percent_sign():
    stops = {"tp_stop": [0.1, 0.2, 0.3, 0.4]}
    assert build_indicator_config_description(stops) == "TP 10-40% (4)"


# --- Sweep als arange-Dict: gleiche Darstellung wie Liste -------------------

def test_description_percent_sweep_arange_matches_list_format():
    stops = {"tp_stop": _arange(0.1, 0.4, 0.1)}
    # arange(0.1, 0.4, 0.1) -> 0.1, 0.2, 0.3, 0.4 (Stop inklusiv) => 4 Werte
    assert build_indicator_config_description(stops) == "TP 10-40% (4)"


def test_description_td_sweep_arange_integer_range():
    # arange ist stop-exklusiv: 1..5 step 1 -> [1, 2, 3, 4]
    stops = {"td_stop": _arange(1, 5, 1, dtype="int")}
    assert build_indicator_config_description(stops) == "TD 1-4 (4)"


# --- Name-Builder: kein Crash, Sweep als min-max ohne (n) -------------------

def test_name_scalar_stops_unchanged():
    cfg = {"_stops": {"tp_stop": 0.3, "sl_stop": 0.15, "delta_format": "percent"}}
    name = build_indicator_config_name(cfg, concept_name="teststrategie", iteration_number=1)
    assert name == "teststrategie-1 - 1 Kombi. 30/15"


def test_name_sweep_list_does_not_crash_and_shows_range():
    cfg = {
        "_stops": {
            "tp_stop": [0.1, 0.2, 0.3, 0.4],
            "sl_stop": 0.15,
            "delta_format": "percent",
        }
    }
    name = build_indicator_config_name(cfg, concept_name="teststrategie", iteration_number=1)
    # 4 Kombis (tp-Achse), tp als Bereich 10-40, sl skalar 15
    assert name == "teststrategie-1 - 4 Kombi. 10-40/15"


# --- labels()-Wrapper: Name + Beschreibung in einem Aufruf ------------------

def test_labels_wrapper_returns_both_fields():
    cfg = {"_stops": {"td_stop": [1, 2, 3], "time_delta_format": "rows"}}
    labels = build_indicator_config_labels(cfg, concept_name="teststrategie", iteration_number=1)
    assert labels["description"] == "TD 1-3 (3), rows"
    assert labels["name"].endswith("Kombi. /")  # kein tp/sl gesetzt


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

"""Utility: Notation für Name und Beschreibung einer Indicator-Config.

Einzige Wahrheit für die Label-Notation. Die Frontend-Buttons in
``indicator_config_edit.html`` erzeugen denselben Aufbau clientseitig;
serverseitig nutzt der Endpunkt ``POST /api/config/indicator/{id}/generate-labels``
diese Funktionen, damit die KI beim Anlegen per API korrekte Felder erhält,
ohne die Notation selbst kennen zu müssen.

Name:
  ``<Konzept>-<Iteration> - <Kombinationen> Kombi. <tp>/<sl>``
  Ohne Konzept entfällt der Kopf samt führendem Trenner; mit Konzept aber ohne
  Iteration entfällt nur die Iterationsnummer. tp/sl als Zahl (bei
  ``delta_format == "percent"`` ×100), ohne Prozentzeichen.

Beschreibung:
  Stops in Reihenfolge ``TP, SL, TSL (th/stop), delta_format, TD, time_delta_format``.
  Ein Stop erscheint nur, wenn gesetzt; ``delta_format`` nur bei gesetztem
  ``tsl_th``; ``time_delta_format`` nur bei gesetztem ``td_stop``; ``null`` wird
  weggelassen. TP/SL/TSL als Prozent (×100 mit ``%``), TD als ganze Zahl.
  Ohne gesetzte Stops bleibt die Beschreibung leer.

Sweep-Stops (Liste oder arange-Dict) erscheinen in der Beschreibung als
kompakter Bereich mit Anzahl ``min-max (n)`` — z. B. ``TD 1-999 (35)`` oder
``TP 10-40% (13)``. Im Namen (tp/sl) nur ``min-max`` ohne ``(n)``, weil die
Gesamt-Kombizahl dort schon im ``Kombi.``-Teil steht.
"""
from typing import Optional

from user_data.strategies.generic.indicator_factory import (
    count_total_combos,
    expand_stop_values,
    is_stop_sweep,
)


def _clean_num(value: float) -> str:
    """Auf 6 Nachkommastellen runden; ganze Zahlen ohne Dezimalteil ausgeben."""
    rounded = round(float(value), 6)
    if rounded == int(rounded):
        return str(int(rounded))
    return str(rounded)


def _format_de_thousands(n: int) -> str:
    """Ganzzahl mit Punkt als Tausendertrenner (wie toLocaleString('de-DE'))."""
    return f"{n:,}".replace(",", ".")


def _is_set(value) -> bool:
    return value is not None


def _sweep_bounds(value, stop_key: str) -> tuple:
    """Expandiert eine Sweep-Achse (Liste oder arange-Dict) zu (min, max, count).

    Nutzt den kanonischen Expander ``expand_stop_values`` (Single Source, dieselbe
    Mechanik wie der Motor), damit es keinen zweiten Sweep-Parser gibt. So werden
    Liste und arange-Dict identisch als Bereich dargestellt.
    """
    values = expand_stop_values(value, stop_key)
    return min(values), max(values), len(values)


def build_indicator_config_name(
    config_json: dict,
    concept_name: Optional[str] = None,
    iteration_number: Optional[int] = None,
) -> str:
    """Baut den Config-Namen nach Notation aus config_json + Konzept/Iteration."""
    stops = config_json.get("_stops") or {}
    is_percent = stops.get("delta_format") == "percent"
    total = count_total_combos(config_json)

    def fmt_stop(v, key) -> str:
        def one(x) -> str:
            return _clean_num(x * 100 if is_percent else x)
        if v is None:
            return ""
        # Sweep (Liste oder arange-Dict) als "min-max" — die Kombi-Zahl steht
        # bereits im "Kombi."-Teil, daher hier ohne (n)-Anhang.
        if is_stop_sweep(v):
            lo, hi, _ = _sweep_bounds(v, key)
            return one(lo) + "-" + one(hi)
        return one(v)

    tp = fmt_stop(stops.get("tp_stop"), "tp_stop")
    sl = fmt_stop(stops.get("sl_stop"), "sl_stop")

    head = ""
    if concept_name:
        head = str(concept_name)
        if iteration_number is not None and str(iteration_number) != "":
            head += "-" + str(iteration_number)

    combo_part = f"{_format_de_thousands(total)} Kombi. {tp}/{sl}"
    return f"{head} - {combo_part}" if head else combo_part


def build_indicator_config_description(stops: dict) -> str:
    """Baut die Beschreibung nach Notation aus dem _stops-Block."""
    if not stops:
        return ""

    # Sweep (Liste oder arange-Dict) als "min-max (n)" auflösen; Skalar unverändert.
    def pct(v, key) -> str:
        if is_stop_sweep(v):
            lo, hi, n = _sweep_bounds(v, key)
            return _clean_num(lo * 100) + "-" + _clean_num(hi * 100) + f"% ({n})"
        return _clean_num(v * 100) + "%"

    def td(v, key) -> str:
        if is_stop_sweep(v):
            lo, hi, n = _sweep_bounds(v, key)
            return _clean_num(lo) + "-" + _clean_num(hi) + f" ({n})"
        return _clean_num(v)

    parts = []
    if _is_set(stops.get("tp_stop")):
        parts.append("TP " + pct(stops["tp_stop"], "tp_stop"))
    if _is_set(stops.get("sl_stop")):
        parts.append("SL " + pct(stops["sl_stop"], "sl_stop"))

    tsl_parts = []
    if _is_set(stops.get("tsl_th")):
        tsl_parts.append(pct(stops["tsl_th"], "tsl_th"))
    if _is_set(stops.get("tsl_stop")):
        tsl_parts.append(pct(stops["tsl_stop"], "tsl_stop"))
    if tsl_parts:
        parts.append("TSL " + "/".join(tsl_parts))

    # delta_format gehört zu TSL: nur bei gesetztem tsl_th
    if _is_set(stops.get("tsl_th")) and stops.get("delta_format"):
        parts.append(stops["delta_format"])

    # TD als ganze Zahl; time_delta_format gehört zu TD
    if _is_set(stops.get("td_stop")):
        parts.append("TD " + td(stops["td_stop"], "td_stop"))
        if stops.get("time_delta_format"):
            parts.append(stops["time_delta_format"])

    return ", ".join(parts)


def build_indicator_config_labels(
    config_json: dict,
    concept_name: Optional[str] = None,
    iteration_number: Optional[int] = None,
) -> dict:
    """Erzeugt Name und Beschreibung in einem Aufruf."""
    config_json = config_json or {}
    stops = config_json.get("_stops") or {}
    return {
        "name": build_indicator_config_name(config_json, concept_name, iteration_number),
        "description": build_indicator_config_description(stops),
    }

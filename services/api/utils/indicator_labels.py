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
"""
from typing import Optional

from user_data.strategies.generic.indicator_factory import count_total_combos


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


def _is_range(value) -> bool:
    return isinstance(value, dict) and all(k in value for k in ("start", "stop", "step"))


def build_indicator_config_name(
    config_json: dict,
    concept_name: Optional[str] = None,
    iteration_number: Optional[int] = None,
) -> str:
    """Baut den Config-Namen nach Notation aus config_json + Konzept/Iteration."""
    stops = config_json.get("_stops") or {}
    is_percent = stops.get("delta_format") == "percent"
    total = count_total_combos(config_json)

    def fmt_stop(v) -> str:
        if v is None:
            return ""
        if _is_range(v):
            return fmt_stop(v["start"]) + "-" + fmt_stop(v["stop"])
        return _clean_num(v * 100 if is_percent else v)

    tp = fmt_stop(stops.get("tp_stop"))
    sl = fmt_stop(stops.get("sl_stop"))

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

    def pct(v) -> str:
        return _clean_num(v * 100) + "%"

    parts = []
    if _is_set(stops.get("tp_stop")):
        parts.append("TP " + pct(stops["tp_stop"]))
    if _is_set(stops.get("sl_stop")):
        parts.append("SL " + pct(stops["sl_stop"]))

    tsl_parts = []
    if _is_set(stops.get("tsl_th")):
        tsl_parts.append(pct(stops["tsl_th"]))
    if _is_set(stops.get("tsl_stop")):
        tsl_parts.append(pct(stops["tsl_stop"]))
    if tsl_parts:
        parts.append("TSL " + "/".join(tsl_parts))

    # delta_format gehört zu TSL: nur bei gesetztem tsl_th
    if _is_set(stops.get("tsl_th")) and stops.get("delta_format"):
        parts.append(stops["delta_format"])

    # TD als ganze Zahl; time_delta_format gehört zu TD
    if _is_set(stops.get("td_stop")):
        parts.append("TD " + _clean_num(stops["td_stop"]))
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

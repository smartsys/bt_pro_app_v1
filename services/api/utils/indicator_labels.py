"""Utility: Notation für Name und Beschreibung einer Indicator-Config.

Einzige Wahrheit für die Label-Notation. Das Frontend (``indicator_config_edit.html``)
rechnet nichts mehr selbst nach, sondern ruft ``POST /api/config/indicator/preview-labels``;
der speichernde Endpunkt und die Toolbox nutzen dieselben Funktionen, damit die KI beim
Anlegen per API korrekte Felder erhält, ohne die Notation selbst kennen zu müssen.

Name (selbsttragend — reicht allein zur Auswahl im Playground-Dropdown):
  ``<Konzept>-<Iteration>-(<Kombinationen>) <Stops>`` und optional ``: <Freitext>``.
  Ohne Konzept entfällt der Kopf (nur ``(<Kombinationen>)``); mit Konzept aber ohne
  Iteration entfällt nur die Iterationsnummer. Der Freitext hinter `` : `` ist rein
  manuell (User im Frontend, KI über den Skill) — der Generator baut ihn nicht.

  Stops im Namen: ``TP``, ``SL``, ``TSL`` (th/stop), ``TD`` in dieser Reihenfolge, mit
  Leerzeichen getrennt; das Format-Wort hängt per Komma an seinem Stop (``TSL 2%/1%, percent``,
  ``TD 8, rows``). TP/SL/TSL als Prozent (×100 mit ``%``), TD als ganze Zahl. Sweep-Achsen
  erscheinen als Bereich mit Anzahl ``min-max (n)`` — z. B. ``TP 10-40% (13)``.

Beschreibung:
  Auflistung der Indikatoren mit ihren Werten/Wertebereichen —
  ``<name>: <param> <wert>, <param> <min-max (n)>; <name2>: ...`` in topologischer
  Reihenfolge. Skalare als Wert, Sweep-Achsen (Range oder Liste) als ``min-max (n)``.
  Inputs (OHLC/Chains), Meta-Keys und Stops bleiben außen vor. Ein KI-/User-Freitext
  steht VOR der Auflistung, per `` | `` getrennt (``<Freitext> | <Auflistung>``);
  angehängt wird er im Frontend/Skill — nicht vom Generator.
"""
from typing import Optional

from user_data.strategies.generic.indicator_factory import (
    count_total_combos,
    describe_indicator_params,
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


def _fmt_pct(v, stop_key: str) -> str:
    """TP/SL/TSL-Wert als Prozent (×100 mit %); Sweep als ``min-max% (n)``."""
    if is_stop_sweep(v):
        lo, hi, n = _sweep_bounds(v, stop_key)
        return _clean_num(lo * 100) + "-" + _clean_num(hi * 100) + f"% ({n})"
    return _clean_num(v * 100) + "%"


def _fmt_td(v, stop_key: str) -> str:
    """TD-Wert als ganze Zahl; Sweep als ``min-max (n)`` (ohne Prozent)."""
    if is_stop_sweep(v):
        lo, hi, n = _sweep_bounds(v, stop_key)
        return _clean_num(lo) + "-" + _clean_num(hi) + f" ({n})"
    return _clean_num(v)


def _build_title_stops(stops: dict) -> str:
    """Baut die Stops-Notation für den Titel: Leerzeichen-getrennt, Format-Wort per Komma."""
    if not stops:
        return ""

    segments = []
    if _is_set(stops.get("tp_stop")):
        segments.append("TP " + _fmt_pct(stops["tp_stop"], "tp_stop"))
    if _is_set(stops.get("sl_stop")):
        segments.append("SL " + _fmt_pct(stops["sl_stop"], "sl_stop"))

    tsl_parts = []
    if _is_set(stops.get("tsl_th")):
        tsl_parts.append(_fmt_pct(stops["tsl_th"], "tsl_th"))
    if _is_set(stops.get("tsl_stop")):
        tsl_parts.append(_fmt_pct(stops["tsl_stop"], "tsl_stop"))
    if tsl_parts:
        seg = "TSL " + "/".join(tsl_parts)
        # delta_format gehört zu TSL: per Komma an das TSL-Segment, nur bei gesetztem tsl_th
        if _is_set(stops.get("tsl_th")) and stops.get("delta_format"):
            seg += ", " + stops["delta_format"]
        segments.append(seg)

    if _is_set(stops.get("td_stop")):
        seg = "TD " + _fmt_td(stops["td_stop"], "td_stop")
        # time_delta_format gehört zu TD: per Komma an das TD-Segment
        if stops.get("time_delta_format"):
            seg += ", " + stops["time_delta_format"]
        segments.append(seg)

    return " ".join(segments)


def build_indicator_config_name(
    config_json: dict,
    concept_name: Optional[str] = None,
    iteration_number: Optional[int] = None,
) -> str:
    """Baut den Config-Namen (fester Teil, ohne Freitext) nach Notation.

    Aufbau: ``<Konzept>-<Iteration>-(<Kombinationen>) <Stops>``. Ein manuell gepflegter
    ``: <Freitext>`` gehört nicht zum Generator — das Frontend/der Skill hängt ihn an.
    """
    config_json = config_json or {}
    stops = config_json.get("_stops") or {}
    total = count_total_combos(config_json)

    head = ""
    if concept_name:
        head = str(concept_name)
        if iteration_number is not None and str(iteration_number) != "":
            head += "-" + str(iteration_number)

    combos = _format_de_thousands(total)
    ident = f"{head}-({combos})" if head else f"({combos})"

    stops_str = _build_title_stops(stops)
    return f"{ident} {stops_str}" if stops_str else ident


def _fmt_scalar(value) -> str:
    """Einzelwert lesbar: Zahl über _clean_num, sonst roher String."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return _clean_num(value)
    return str(value)


def _fmt_param_axis(values: list) -> str:
    """Parameter-Achse: Skalar als Wert, Range/Liste als ``min-max (n)``."""
    if len(values) == 1:
        return _fmt_scalar(values[0])
    numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)
    if numeric:
        return f"{_clean_num(min(values))}-{_clean_num(max(values))} ({len(values)})"
    return f"{_fmt_scalar(values[0])}-{_fmt_scalar(values[-1])} ({len(values)})"


def build_indicator_config_description(config_json: dict) -> str:
    """Baut die Beschreibung: Indikatoren mit ihren Werten/Wertebereichen.

    Format: ``<name>: <param> <wert>, <param> <min-max (n)>; <name2>: ...`` in
    topologischer Reihenfolge. Ein KI-/User-Freitext wird separat per `` | `` angehängt
    (im Frontend/Skill) — der Generator baut ihn nicht.
    """
    config_json = config_json or {}
    parts = []
    for ind_id, params in describe_indicator_params(config_json):
        param_str = ", ".join(f"{key} {_fmt_param_axis(vals)}" for key, vals in params)
        parts.append(f"{ind_id}: {param_str}")
    return "; ".join(parts)


def build_indicator_config_labels(
    config_json: dict,
    concept_name: Optional[str] = None,
    iteration_number: Optional[int] = None,
) -> dict:
    """Erzeugt Name und Beschreibung in einem Aufruf."""
    config_json = config_json or {}
    return {
        "name": build_indicator_config_name(config_json, concept_name, iteration_number),
        "description": build_indicator_config_description(config_json),
    }

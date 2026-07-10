"""Utility: Gegenüberstellung mehrerer Indicator-Configs als Zeilen-Matrix.

Baut aus N ``config_json`` eine Tabelle, in der jede Config eine Spalte belegt und
gleiche Indikatoren untereinander stehen. Zweck ist der Blick-Vergleich zweier
Configs: Wurde beim Kopieren ein Wertebereich still beschnitten, ein Indikator
entfernt oder ein Stop verändert?

Formatierung delegiert vollständig an ``indicator_labels`` bzw. die Expander der
``indicator_factory`` — es gibt hier bewusst keine zweite Sweep-Mathematik. Ein
Wertebereich erscheint als ``min-max (n) s: schritt``, ein Skalar als Wert.

Der Schrittwert wird nur hier angehängt, nicht in ``indicator_labels``: Dort ist die
Notation die Single Source für Config-Namen und -Beschreibungen, die durch einen
zusätzlichen Schritt ihre Bedeutung ändern würden. Für den Vergleich ist der Schritt
dagegen wesentlich — zwei Bereiche mit gleichem Minimum und Maximum können sich allein
im Raster unterscheiden.

Anders als die Config-Beschreibung blendet der Vergleich nichts aus: Auch Inputs
(``close``, ``volume``), Quellen-Verkettungen (``source``), Meta-Keys (``indicator``,
``tf``, ``enabled``), deaktivierte Indikatoren und die Stops unter ``_stops`` sind
sichtbar. Ein Vergleich, der Felder verschweigt, kann seinen Zweck nicht erfüllen.
"""
from typing import Optional

from user_data.strategies.generic.indicator_factory import (
    _expand_range,
    _topological_order,
)

from services.api.utils.indicator_labels import (
    _clean_num,
    _fmt_param_axis,
    _fmt_pct,
    _fmt_scalar,
    _fmt_td,
)

# Sentinel für "Schlüssel in dieser Config nicht vorhanden" — abgegrenzt von einem
# vorhandenen Schlüssel mit Wert None (= bewusst nicht gesetzt, z.B. tsl_stop).
MISSING = None

_STOPS_KEY = '_stops'

# Anzeige-Reihenfolge und Beschriftung der Stop-Felder (Rest wird hinten angehängt).
_STOP_ORDER = [
    ('tp_stop', 'TP'),
    ('sl_stop', 'SL'),
    ('tsl_th', 'TSL Schwelle'),
    ('tsl_stop', 'TSL'),
    ('delta_format', 'Delta-Format'),
    ('td_stop', 'TD'),
    ('time_delta_format', 'Zeit-Delta-Format'),
]

# Stops, die als Prozent dargestellt werden (Rohwert 0.3 -> "30%").
_PCT_STOPS = {'tp_stop', 'sl_stop', 'tsl_th', 'tsl_stop'}

# Meta-Keys eines Indikators zuerst, danach die Parameter in Einfüge-Reihenfolge.
_INDICATOR_HEAD_KEYS = ['indicator', 'tf', 'enabled']


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _range_step(value) -> Optional[float]:
    """Schrittweite einer Sweep-Achse, oder ``None``, wenn es keine gibt.

    Beim arange-Dict steht der Schritt direkt drin. Eine Liste hat nur dann einen
    Schritt, wenn ihre numerischen Werte gleichmäßig verteilt sind — sonst gibt es
    schlicht keinen, und die Zelle bleibt bei ``min-max (n)``.
    """
    if isinstance(value, dict):
        step = value.get('step')
        return step if _is_number(step) else None

    if isinstance(value, (list, tuple)) and len(value) > 1 and all(_is_number(v) for v in value):
        steps = {round(b - a, 6) for a, b in zip(value, value[1:])}
        if len(steps) == 1:
            return steps.pop()

    return None


def _append_step(text: str, step_label: Optional[str]) -> str:
    """Hängt den Schritt an die Bereichs-Notation an: ``10-50 (5)`` -> ``10-50 (5) s: 10``.

    Skalare tragen keine ``(n)``-Klammer und bleiben unverändert.
    """
    if step_label is None or ' (' not in text:
        return text
    return f"{text} s: {step_label}"


def _format_value(value, ind_id: str, key: str) -> str:
    """Einen Config-Wert lesbar machen: Wertebereich als ``min-max (n) s: schritt``, sonst Skalar."""
    if value is None:
        return 'nicht gesetzt'
    if isinstance(value, bool):
        return 'ja' if value else 'nein'

    text = _fmt_param_axis(_expand_range(value, ind_id, key))
    step = _range_step(value)
    return _append_step(text, _clean_num(step) if step is not None else None)


def _format_stop(value, key: str) -> str:
    """Einen Stop-Wert in der Notation der Config-Namen darstellen, Sweeps mit Schritt."""
    if value is None:
        return 'nicht gesetzt'

    step = _range_step(value)
    if key in _PCT_STOPS:
        # Prozent-Stops werden ×100 angezeigt — der Schritt muss dieselbe Skala tragen.
        label = _clean_num(step * 100) + '%' if step is not None else None
        return _append_step(_fmt_pct(value, key), label)
    if key == 'td_stop':
        label = _clean_num(step) if step is not None else None
        return _append_step(_fmt_td(value, key), label)
    return _fmt_scalar(value)


def _ordered_indicator_ids(config_jsons: list) -> list:
    """Union aller Indikator-IDs, topologische Reihenfolge der ersten Nennung gewinnt."""
    ordered: list[str] = []
    for config_json in config_jsons:
        for ind_id in _topological_order(config_json or {}):
            if ind_id not in ordered:
                ordered.append(ind_id)
    return ordered


def _ordered_param_keys(entries: list) -> list:
    """Union der Schlüssel eines Indikators über alle Configs; Meta-Keys zuerst."""
    ordered = [k for k in _INDICATOR_HEAD_KEYS if any(k in e for e in entries)]
    for entry in entries:
        for key in entry:
            if key not in ordered:
                ordered.append(key)
    return ordered


def _build_row(label: str, cells: list) -> dict:
    """Eine Zeile bauen und markieren, ob die Zellen voneinander abweichen."""
    return {
        'label': label,
        'cells': cells,
        'differs': len(set(cells)) > 1,
    }


def _build_indicator_group(ind_id: str, config_jsons: list) -> dict:
    """Zeilengruppe für einen Indikator über alle Configs."""
    entries = [(cj or {}).get(ind_id) or {} for cj in config_jsons]
    present = [bool((cj or {}).get(ind_id)) for cj in config_jsons]

    rows = []
    for key in _ordered_param_keys(entries):
        cells = []
        for entry, is_present in zip(entries, present):
            if not is_present:
                cells.append('fehlt')
            elif key not in entry:
                cells.append('—')
            else:
                cells.append(_format_value(entry[key], ind_id, key))
        rows.append(_build_row(key, cells))

    return {
        'name': ind_id,
        'present': present,
        'differs': any(r['differs'] for r in rows) or len(set(present)) > 1,
        'rows': rows,
    }


def _build_stops_group(config_jsons: list) -> Optional[dict]:
    """Zeilengruppe für die Stops; ``None``, wenn keine Config Stops trägt."""
    stops = [(cj or {}).get(_STOPS_KEY) or {} for cj in config_jsons]
    if not any(stops):
        return None

    labels = dict(_STOP_ORDER)
    ordered = [k for k, _ in _STOP_ORDER if any(k in s for s in stops)]
    for entry in stops:
        for key in entry:
            if key not in ordered:
                ordered.append(key)

    rows = []
    for key in ordered:
        cells = [
            _format_stop(s[key], key) if key in s else '—'
            for s in stops
        ]
        rows.append(_build_row(labels.get(key, key), cells))

    return {
        'name': 'Stops',
        'present': [bool(s) for s in stops],
        'differs': any(r['differs'] for r in rows),
        'rows': rows,
    }


def build_indicator_config_comparison(configs: list) -> dict:
    """Stellt mehrere Indicator-Configs als Zeilen-Matrix gegenüber.

    Args:
        configs: Liste von Dicts mit mindestens ``id``, ``name`` und ``config_json``.
            Die Reihenfolge bestimmt die Spalten-Reihenfolge.

    Returns:
        Dict mit ``columns`` (je Config die Kopfdaten) und ``groups`` (je Indikator
        eine Zeilengruppe, die Stops als letzte Gruppe). Jede Zeile trägt ``differs``,
        jede Gruppe ebenfalls — damit das Frontend Abweichungen hervorheben kann.
    """
    config_jsons = [c.get('config_json') or {} for c in configs]

    groups = [
        _build_indicator_group(ind_id, config_jsons)
        for ind_id in _ordered_indicator_ids(config_jsons)
    ]
    stops_group = _build_stops_group(config_jsons)
    if stops_group:
        groups.append(stops_group)

    columns = [
        {
            'id': c.get('id'),
            'name': c.get('name'),
            'strategy_concept_name': c.get('strategy_concept_name'),
            'strategy_iteration_number': c.get('strategy_iteration_number'),
            'strategy_iteration_version': c.get('strategy_iteration_version'),
        }
        for c in configs
    ]

    return {
        'columns': columns,
        'groups': groups,
        'differs': any(g['differs'] for g in groups),
    }

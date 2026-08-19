"""Indikator-Referenzen als Stop-Wert.

Ein Stop-Feld in ``indicators_json['_stops']`` (``tp_stop``, ``sl_stop``, ``tsl_th``,
``tsl_stop``, ``td_stop``) nimmt neben Zahl, ``null`` und Range-Dict zusätzlich ein
Referenz-Dict::

    "sl_stop":  {"ref": "indicator:atr14:real", "mult": 5.0}
    "tsl_stop": {"ref": "indicator:atr14:real", "mult": 2.5, "live": true, "ratchet": true}

Damit wird der Stopabstand aus einer Zeitreihe bestimmt statt für alle Trades gleich.
``ref`` folgt exakt der Regel-Notation und wird über dieselbe Auflösung wie in den
Regeln aufgelöst (``rules_engine._resolve_ref``) — es gibt keinen zweiten Parser.

Der aufgelöste Wert geht unverändert (nur mit ``mult`` multipliziert) an
``from_signals``: keine implizite Umrechnung auf Prozent, keine Anpassung von
``delta_format``. Wer einen absoluten ATR-Abstand fährt, setzt ``delta_format``
selbst auf ``absolute``.

Eine Referenz ist KEINE Sweep-Achse: ein Referenz-Dict trägt keinen ``type``-Key und
wird deshalb von ``is_stop_sweep``/``count_stop_combos`` als ein Wert gezählt.
"""

from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

from user_data.strategies.generic.indicator_factory import STOP_PARAM_KEYS
from user_data.strategies.generic.rules_engine import _resolve_ref

# Felder, die im Referenz-Dict erlaubt sind. Alles andere ist ein Tippfehler und
# wird sichtbar abgewiesen, statt still ignoriert zu werden.
_ALLOWED_REF_FIELDS = frozenset({'ref', 'mult', 'live', 'ratchet'})

# Laufende Nachführung ist nur für den Anfangsstop und den nachgezogenen Stop
# sinnvoll. Ein nachgeführtes Kursziel bzw. eine nachgeführte Haltedauer hat keinen
# Anwendungsfall (Out of Scope im Ticket).
_LIVE_CAPABLE_KEYS = ('sl_stop', 'tsl_stop')


@dataclass(frozen=True)
class StopRefSpec:
    """Geparste Referenz-Notation eines Stop-Feldes.

    Attributes:
        stop_key: Name des Stop-Feldes ('sl_stop', 'tsl_stop', ...).
        ref: Referenz in Regel-Notation ('indicator:<id>:<output>').
        mult: Faktor auf die Zeitreihe (Default 1.0).
        live: True = der Abstand wird bei jeder Kerze neu gesetzt, solange die
            Position offen ist. False (Default) = der Abstand wird beim Einstieg
            festgelegt und gilt für diesen Trade (VBT-Verhalten).
        ratchet: Wirkt nur bei live=True. True (Default) = das Stop-Niveau darf sich
            nur zugunsten der Position bewegen. False = das Niveau folgt der Serie in
            beide Richtungen und kann sich wieder lockern.
    """

    stop_key: str
    ref: str
    mult: float
    live: bool
    ratchet: bool


@dataclass(frozen=True)
class ResolvedStopRef:
    """Zur Zeitreihe aufgelöste Referenz eines Stop-Feldes.

    Attributes:
        spec: Die geparste Notation (inkl. live/ratchet).
        series: Die aufgelöste Zeitreihe, bereits mit ``mult`` multipliziert.
            pandas-Objekt am Basis-Index; DataFrame, wenn der referenzierte Indikator
            eine Parameter-Achse trägt (Spalten-Level bereits instanz-eindeutig
            benannt), sonst Series. Warmup-Balken tragen NaN — VBT liest einen
            NaN-Stop als "kein Stop".
    """

    spec: StopRefSpec
    series: Any


def is_stop_ref(value: Any) -> bool:
    """True, wenn ein '_stops'-Wert ein Indikator-Referenz-Dict ist."""
    return isinstance(value, dict) and 'ref' in value


def parse_stop_ref(value: dict, stop_key: str) -> StopRefSpec:
    """Parst und validiert ein Referenz-Dict eines Stop-Feldes.

    Args:
        value: Das Referenz-Dict aus '_stops'.
        stop_key: Name des Stop-Feldes (für die Fehlermeldungen).

    Returns:
        Die geparste Notation.

    Raises:
        ValueError: Bei unbekannten Feldern, ungültiger Referenz-Notation, einem
            ``mult``, das keine Zahl ist, oder nicht-booleschen Schaltern.
    """
    unknown = sorted(set(value.keys()) - _ALLOWED_REF_FIELDS)
    if unknown:
        raise ValueError(
            f"Stop {stop_key!r}: unbekannte Felder im Referenz-Dict: {', '.join(unknown)}. "
            f"Erlaubt sind {sorted(_ALLOWED_REF_FIELDS)}."
        )

    ref = value.get('ref')
    if not isinstance(ref, str) or not ref.startswith('indicator:'):
        raise ValueError(
            f"Stop {stop_key!r}: 'ref' muss eine Indikator-Referenz der Form "
            f"'indicator:<id>:<output>' sein, gefunden: {ref!r}."
        )
    parts = ref.split(':')
    if len(parts) < 2 or not parts[1]:
        raise ValueError(
            f"Stop {stop_key!r}: ungültige Indikator-Referenz {ref!r} — es fehlt die "
            f"Indikator-ID ('indicator:<id>:<output>')."
        )

    mult = value.get('mult', 1.0)
    if isinstance(mult, bool) or not isinstance(mult, (int, float)):
        raise ValueError(
            f"Stop {stop_key!r}: 'mult' der Referenz {ref!r} muss eine Zahl sein, "
            f"gefunden: {mult!r} ({type(mult).__name__})."
        )

    live = value.get('live', False)
    if not isinstance(live, bool):
        raise ValueError(
            f"Stop {stop_key!r}: 'live' der Referenz {ref!r} muss ein Wahrheitswert "
            f"sein, gefunden: {live!r} ({type(live).__name__})."
        )
    if live and stop_key not in _LIVE_CAPABLE_KEYS:
        raise ValueError(
            f"Stop {stop_key!r}: 'live' ist nur für {list(_LIVE_CAPABLE_KEYS)} "
            f"vorgesehen — ein nachgeführtes Kursziel bzw. eine nachgeführte "
            f"Haltedauer gibt es nicht."
        )

    ratchet = value.get('ratchet', True)
    if not isinstance(ratchet, bool):
        raise ValueError(
            f"Stop {stop_key!r}: 'ratchet' der Referenz {ref!r} muss ein "
            f"Wahrheitswert sein, gefunden: {ratchet!r} ({type(ratchet).__name__})."
        )

    return StopRefSpec(
        stop_key=stop_key, ref=ref, mult=float(mult), live=live, ratchet=ratchet
    )


def parse_stop_refs(stops_cfg: Optional[dict]) -> dict[str, StopRefSpec]:
    """Parst alle Referenz-Dicts eines '_stops'-Blocks.

    Args:
        stops_cfg: Das '_stops'-Dict (darf fehlen/leer sein).

    Returns:
        Dict Stop-Feld -> geparste Notation; leer, wenn keine Referenz gesetzt ist.

    Raises:
        ValueError: Bei ungültiger Notation (siehe ``parse_stop_ref``).
    """
    if not stops_cfg:
        return {}
    return {
        key: parse_stop_ref(stops_cfg[key], key)
        for key in STOP_PARAM_KEYS
        if is_stop_ref(stops_cfg.get(key))
    }


def _assert_live_delta_format(
    specs: dict[str, StopRefSpec], delta_format: Any
) -> None:
    """Weist ``live: true`` in Verbindung mit ``delta_format: 'target'`` ab.

    Bei allen anderen Formaten ist der Stop-Wert ein Abstand (absolut oder
    prozentual), und genau darauf sind die Nachführung und die Ratsche definiert
    (Long: ``abstand = referenzpreis − niveau``). Bei ``target`` ist der Wert
    dagegen das Kursniveau selbst — eine Indikator-Serie als Abstand zu lesen
    ergäbe dort eine falsche Rechnung.

    Args:
        specs: Die geparsten Referenz-Notationen je Stop-Feld.
        delta_format: Der Wert aus '_stops' (VBT löst ihn case-insensitiv und
            ohne Unterstriche auf — hier gleich behandelt).

    Raises:
        ValueError: Wenn ein Feld mit ``live: true`` auf 'target' trifft.
    """
    if delta_format is None:
        return
    normalized = str(delta_format).strip().lower().replace('_', '')
    if normalized != 'target':
        return
    live_keys = sorted(key for key, spec in specs.items() if spec.live)
    if not live_keys:
        return
    raise ValueError(
        f"Stop {live_keys[0]!r}: '\"live\": true' verträgt sich nicht mit "
        f"delta_format {delta_format!r}. Bei 'target' ist der Stop-Wert ein "
        f"Kursniveau statt eines Abstands — die laufende Nachführung und die "
        f"Ratsche sind auf Abstände definiert. Für einen nachgeführten Abstand "
        f"delta_format 'absolute', 'percent' oder 'percent100' setzen."
    )


def resolve_stop_refs(
    stops_cfg: Optional[dict],
    ohlc_data: Any,
    indicators: dict,
) -> dict[str, ResolvedStopRef]:
    """Löst die Referenz-Stops nach ``build_indicators`` zu Zeitreihen auf.

    Args:
        stops_cfg: Das '_stops'-Dict (darf fehlen/leer sein).
        ohlc_data: vbt.Data-Objekt (nur für die gemeinsame Auflösung durchgereicht).
        indicators: Die von ``build_indicators`` gebauten Indikator-Instanzen.

    Returns:
        Dict Stop-Feld -> aufgelöste Referenz (Serie bereits mit ``mult`` skaliert).

    Raises:
        ValueError: Bei unbekanntem Indikator, unbekanntem Output, einer Referenz,
            die keine Zeitreihe liefert, oder bei ``live: true`` zusammen mit
            ``delta_format: 'target'``. Kein Zurückfallen auf einen Default.
    """
    specs = parse_stop_refs(stops_cfg)
    _assert_live_delta_format(specs, (stops_cfg or {}).get('delta_format'))
    resolved: dict[str, ResolvedStopRef] = {}
    for stop_key, spec in specs.items():
        try:
            series = _resolve_ref(spec.ref, ohlc_data, indicators)
        except Exception as exc:
            # Breit gefangen: ein unbekannter Output schlägt in der gemeinsamen
            # Auflösung als AttributeError durch (getattr auf die Instanz), ein
            # unbekannter Indikator als ValueError. Beides muss dieselbe Klartext-
            # Meldung mit Stop-Feld und Referenz ergeben.
            raise ValueError(
                f"Stop {stop_key!r}: Referenz {spec.ref!r} nicht auflösbar — {exc}"
            ) from exc

        if not isinstance(series, (pd.Series, pd.DataFrame)):
            raise ValueError(
                f"Stop {stop_key!r}: Referenz {spec.ref!r} liefert keine Zeitreihe, "
                f"sondern {type(series).__name__}."
            )

        resolved[stop_key] = ResolvedStopRef(spec=spec, series=series * spec.mult)
    return resolved

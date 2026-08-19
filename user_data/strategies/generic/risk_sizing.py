"""Risikobasierte Positionsgröße (``size_type = 'risk_percent'``).

Statt einer festen Ordergröße bemisst sich die Position nach dem Risiko::

    groesse = (kontowert * risk_pct) / stopabstand

Der Kontowert ist der laufende Wert der jeweiligen Portfolio-Spalte am
Einstiegsbalken (``c.last_value[c.group]`` im ``FSSignalContext``), der
Stopabstand kommt aus ``sl_stop`` — als Skalar oder als Indikator-Referenz
(Ticket 103, ``stop_refs.py``). Der Verlust bis zum Stop ist damit
``groesse * stopabstand = kontowert * risk_pct``, unabhängig vom Kurs.

Umsetzung: Die Signal-Funktion schreibt die Größe im Einstiegsbalken in ein
``size``-Array, das zugleich als ``size``-Argument an ``from_signals`` geht
(``size_type='amount'``). Das wirkt, weil VBT das übergebene Array beim
Broadcast nicht kopiert, solange sich seine Form nicht ändert — der
``signal_func_nb``-Aufruf steht in ``from_signal_func_nb`` vor allen
Lesestellen von ``size_``.

Grenzen, die hier bewusst als Abbruch statt als stille Näherung enden:

- **Stop-Sweep.** Eine ``vbt.Param``-Stop-Achse legt VBT erst nach dem
  Broadcast gegen die Kursreihe über die Spalten. Das ``size``-Array wird dabei
  vervielfältigt (kopiert), Schreibzugriffe der Signal-Funktion gingen ins Leere
  und die Spaltenzahl passte nicht mehr. Am Container gemessen (2026-08-19).
- **``from_ago``.** ``from_signals`` liest die Größe an ``size_arr[i - from_ago]``
  statt an ``size_arr[i]`` — es entstünde eine Order mit falscher Größe, ohne
  Fehlermeldung.
- **Kein ``sl_stop``.** Ohne Stopabstand ist der Divisor undefiniert.
- **``delta_format: 'target'``.** Dort ist der Stop-Wert ein Kursniveau, kein
  Abstand.

Ohne Kreditlinie (``leverage = 1``) kürzt VBT eine zu große Order still auf das
verfügbare Geld — aus der variablen Größe wird wieder eine konstante, und die
Kennzahlen messen etwas anderes als die Strategie. ``summarize_truncation``
vergleicht deshalb nach dem Lauf die gewünschte gegen die ausgeführte Größe und
liefert eine Klartext-Meldung.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import vectorbtpro as vbt
from vectorbtpro.utils.enum_ import map_enum_fields

# VBT-Default, wenn '_stops' kein 'delta_format' trägt (vectorbtpro/_settings.py).
_DEFAULT_DELTA_FORMAT = 'percent'

# Delta-Format-Codes direkt aus der installierten VBT-Version (kein Duplikat).
DELTA_FORMAT_ABSOLUTE = int(vbt.pf_enums.DeltaFormat.Absolute)
DELTA_FORMAT_PERCENT = int(vbt.pf_enums.DeltaFormat.Percent)
DELTA_FORMAT_PERCENT100 = int(vbt.pf_enums.DeltaFormat.Percent100)
DELTA_FORMAT_TARGET = int(vbt.pf_enums.DeltaFormat.Target)

# App-Notation für die risikobasierte Größe (kein VBT-SizeType).
RISK_PERCENT_SIZE_TYPE = 'risk_percent'


@dataclass
class RiskSizingSpec:
    """Alles, was der Lauf für die risikobasierte Größe braucht.

    Attributes:
        risk_pct: Kontoanteil je Trade als Bruchteil (0.03 = 3 %).
        delta_format_code: Aufgelöstes ``delta_format`` des '_stops'-Blocks als
            VBT-Code — bestimmt, wie aus dem ``sl_stop``-Wert ein Preisabstand
            wird (wie in ``_apply_live_stop_nb``).
        sl_scalar: Der skalare ``sl_stop``-Wert, wenn kein Referenz-Stop gesetzt
            ist; sonst ``None`` (dann liefert die Referenz-Serie den Wert).
        desired_size: Wird von ``evaluate_rules_native`` gefüllt: das
            ``size``-Array (n_bars, n_total), das die Signal-Funktion beschrieben
            hat. Nicht gesetzte Balken tragen ``inf`` (VBT-Default „alles"),
            Einstiege ohne bestimmbaren Stopabstand ``NaN`` (keine Order).
    """

    risk_pct: float
    delta_format_code: int
    sl_scalar: Optional[float] = None
    desired_size: Optional[np.ndarray] = field(default=None, repr=False)


def is_risk_percent(size_type: Any) -> bool:
    """True, wenn der ``size_type`` die risikobasierte Größe verlangt."""
    return isinstance(size_type, str) and size_type.strip().lower() == RISK_PERCENT_SIZE_TYPE


def resolve_delta_format_code(delta_format: Any) -> int:
    """Löst das ``delta_format`` eines '_stops'-Blocks zum VBT-Code auf.

    Args:
        delta_format: Der Wert aus '_stops' (``None`` = VBT-Default 'percent').

    Returns:
        Der VBT-Code (Absolute/Percent/Percent100/Target).

    Raises:
        ValueError: Wenn VBT den Wert nicht auflösen kann.
    """
    value = delta_format if delta_format is not None else _DEFAULT_DELTA_FORMAT
    try:
        return int(map_enum_fields(value, vbt.pf_enums.DeltaFormat))
    except KeyError:
        raise ValueError(
            f"Ungültiges delta_format {delta_format!r} im '_stops'-Block. "
            f"Gültig sind: {', '.join(vbt.pf_enums.DeltaFormat._fields)}."
        ) from None


def build_risk_sizing_spec(
    pf_cfg: dict,
    stops_cfg: Optional[dict],
    stops_swept: bool,
) -> Optional[RiskSizingSpec]:
    """Prüft die Konfiguration und baut die Spezifikation der risikobasierten Größe.

    Args:
        pf_cfg: Der 'portfolio'-Block der BacktestConfig.
        stops_cfg: Der '_stops'-Block der Indikator-Config.
        stops_swept: True, wenn mindestens ein Stop-Feld eine Sweep-Achse trägt.

    Returns:
        Die Spezifikation, oder ``None`` wenn ``size_type`` nicht
        ``'risk_percent'`` ist (dann bleibt der Lauf unverändert).

    Raises:
        ValueError: Bei fehlendem/ungültigem ``risk_pct``, fehlendem ``sl_stop``,
            ``delta_format: 'target'``, einem Stop-Sweep oder ``from_ago != 0``.
            Jede Meldung nennt die Stelle, an der es hängt.
    """
    if not is_risk_percent(pf_cfg.get('size_type')):
        return None

    risk_pct = pf_cfg.get('risk_pct')
    if risk_pct is None or float(risk_pct) <= 0.0:
        raise ValueError(
            "size_type='risk_percent' braucht ein positives 'risk_pct' im "
            "portfolio-Block der BacktestConfig (Bruchteil, 0.03 = 3 % Kontorisiko "
            f"je Trade). Gefunden: {risk_pct!r}."
        )

    # GEÄNDERT: Ticket 104, Anforderung 4 — 'from_ago' verriegeln statt
    # vorbauen. from_signals liest die Größe an size_arr[i - from_ago], die
    # Signal-Funktion schreibt sie an size_arr[i]: es entstünde eine Order mit
    # falscher Größe, ohne Fehlermeldung (am Container gemessen, Ticket 104
    # Messung 7).
    from_ago = pf_cfg.get('from_ago')
    if from_ago is not None and int(from_ago) != 0:
        raise ValueError(
            f"size_type='risk_percent' verträgt sich nicht mit from_ago={from_ago!r}. "
            "from_signals liest die Ordergröße an size_arr[i - from_ago], die "
            "Signal-Funktion schreibt sie an size_arr[i] — die Order bekäme still "
            "die falsche Größe. Anzupassende Stelle, falls from_ago einmal "
            "gebraucht wird: rules_engine._state_exit_signal_func_nb (Schreibstelle "
            "des size-Arrays) zusammen mit risk_sizing.build_risk_sizing_spec "
            "(dieser Riegel)."
        )

    stops = stops_cfg or {}
    sl_stop = stops.get('sl_stop')
    if sl_stop is None:
        raise ValueError(
            "size_type='risk_percent' braucht einen Stopabstand als Divisor, aber "
            "'sl_stop' ist im '_stops'-Block der Indikator-Config nicht gesetzt. "
            "Ohne ihn ist die Rechnung (Kontowert x risk_pct / Stopabstand) "
            "undefiniert — es wird kein Ersatzwert eingesetzt."
        )

    delta_format_code = resolve_delta_format_code(stops.get('delta_format'))
    if delta_format_code == DELTA_FORMAT_TARGET:
        raise ValueError(
            "size_type='risk_percent' verträgt sich nicht mit delta_format "
            "'target': dort ist der Stop-Wert ein Kursniveau statt eines Abstands, "
            "aus dem sich die Positionsgröße ergäbe. Für die risikobasierte Größe "
            "delta_format 'absolute', 'percent' oder 'percent100' setzen."
        )

    # GEÄNDERT: Ticket 104 — Stop-Sweep und risikobasierte Größe schließen
    # sich aus. VBT broadcastet 'size' zuerst gegen die Kursreihe und legt die
    # vbt.Param-Achse danach darüber; dabei wird das Array vervielfältigt, die
    # Schreibzugriffe der Signal-Funktion landen in der Kopie und wirken nicht
    # (am Container gemessen, 2026-08-19). Ein stiller Lauf mit fester Größe
    # wäre die schlechteste aller Antworten.
    if stops_swept:
        raise ValueError(
            "size_type='risk_percent' verträgt sich nicht mit einem Stop-Sweep "
            "(Range/Liste in '_stops'). VBT legt die Sweep-Achse erst nach dem "
            "Broadcast über die Spalten und vervielfältigt dabei das size-Array — "
            "die zur Laufzeit gerechnete Größe würde verworfen, ohne dass es "
            "auffiele. Entweder die Stops als feste Werte bzw. Indikator-Referenz "
            "setzen oder mit size_type='value'/'percent100' rechnen."
        )

    sl_scalar = None
    if not isinstance(sl_stop, dict):
        sl_scalar = float(sl_stop)
        if not np.isfinite(sl_scalar) or sl_scalar <= 0.0:
            raise ValueError(
                f"size_type='risk_percent': 'sl_stop' muss ein positiver "
                f"Stopabstand sein, gefunden: {sl_stop!r}."
            )

    return RiskSizingSpec(
        risk_pct=float(risk_pct),
        delta_format_code=delta_format_code,
        sl_scalar=sl_scalar,
    )


def summarize_truncation(portfolio: Any, desired_size: Optional[np.ndarray]) -> dict:
    """Vergleicht die gewünschte mit der ausgeführten Ordergröße.

    Ticket 104, Anforderung 3: Ohne Kreditlinie kürzt VBT eine zu große Order
    still auf das verfügbare Geld. Die Kennzahlen sehen dann plausibel aus,
    messen aber eine konstante statt einer risikobasierten Größe. Der Abgleich
    läuft über die Order-Records: an jedem Balken, an dem die Signal-Funktion
    eine Größe geschrieben hat, wird die ausgeführte Größe dagegen gehalten.

    Eine Umkehr-Order (``upon_opposite_entry='Reverse'``) ist größer als die
    gewünschte Größe (sie schließt zusätzlich die Gegenposition) und kann den
    Befund deshalb nicht auslösen — gemeldet wird ausschließlich die
    Unterschreitung.

    Args:
        portfolio: Das fertige ``vbt.Portfolio``.
        desired_size: Das von der Signal-Funktion beschriebene size-Array
            (n_bars, n_total) oder ``None`` (dann ist der Bericht leer).

    Returns:
        Dict mit 'n_sized' (Einstiege mit gerechneter Größe), 'n_unsized'
        (Einstiege ohne bestimmbaren Stopabstand), 'n_truncated' (gekürzte
        Orders), 'max_shortfall_pct' (größte Kürzung in Prozent) und 'note'
        (Klartext-Meldung oder ``None``, wenn nichts zu melden ist).
    """
    empty = {
        'n_sized': 0,
        'n_unsized': 0,
        'n_truncated': 0,
        'max_shortfall_pct': 0.0,
        'note': None,
    }
    if desired_size is None:
        return empty

    finite = np.isfinite(desired_size)
    n_sized = int(np.count_nonzero(finite))
    n_unsized = int(np.count_nonzero(np.isnan(desired_size)))

    # ``Records.values`` ist das strukturierte numpy-Array der Order-Records
    # (``Records.records`` wäre ein DataFrame). Der Abgleich läuft vektorisiert.
    records = portfolio.orders.values
    n_bars, n_cols = desired_size.shape
    n_truncated = 0
    max_shortfall = 0.0
    if len(records):
        order_col = records['col'].astype(np.int64)
        order_idx = records['idx'].astype(np.int64)
        order_size = records['size'].astype(np.float64)
        in_range = (order_col < n_cols) & (order_idx < n_bars)
        order_col = order_col[in_range]
        order_idx = order_idx[in_range]
        order_size = order_size[in_range]
        wanted = desired_size[order_idx, order_col]
        comparable = np.isfinite(wanted) & (wanted > 0.0)
        short = comparable & (order_size < wanted * (1.0 - 1e-9))
        n_truncated = int(np.count_nonzero(short))
        if n_truncated:
            shortfalls = (wanted[short] - order_size[short]) / wanted[short] * 100.0
            max_shortfall = float(np.max(shortfalls))

    note = None
    parts: list[str] = []
    if n_truncated:
        parts.append(
            f"{n_truncated} von {n_sized} risikobasierten Orders wurden von VBT auf "
            f"das verfügbare Geld gekürzt (größte Kürzung {max_shortfall:.1f} %). "
            f"Die Risikoregel greift insoweit nicht — die Kennzahlen messen eine "
            f"kleinere, faktisch begrenzte Position. Abhilfe: 'leverage' im "
            f"portfolio-Block erhöhen (Bedarf ~ risk_pct / Stopabstand-in-Prozent)."
        )
    if n_unsized:
        parts.append(
            f"{n_unsized} Einstiegsbalken hatten keinen bestimmbaren Stopabstand "
            f"(Vorlauf des Referenz-Indikators) und wurden nicht gehandelt."
        )
    if parts:
        note = ' '.join(parts)

    return {
        'n_sized': n_sized,
        'n_unsized': n_unsized,
        'n_truncated': n_truncated,
        'max_shortfall_pct': float(max_shortfall),
        'note': note,
    }


def merge_reports(reports: list[dict]) -> dict:
    """Fasst die Berichte mehrerer Chunks zu einem Lauf-Bericht zusammen.

    Args:
        reports: Die Einzelberichte aus ``summarize_truncation``.

    Returns:
        Ein Bericht im selben Format; 'note' wird aus den Summen neu formuliert,
        damit sie den ganzen Lauf beschreibt statt den letzten Chunk.
    """
    merged = {
        'n_sized': sum(int(r.get('n_sized') or 0) for r in reports),
        'n_unsized': sum(int(r.get('n_unsized') or 0) for r in reports),
        'n_truncated': sum(int(r.get('n_truncated') or 0) for r in reports),
        'max_shortfall_pct': max(
            [float(r.get('max_shortfall_pct') or 0.0) for r in reports], default=0.0
        ),
        'note': None,
    }
    parts: list[str] = []
    if merged['n_truncated']:
        parts.append(
            f"{merged['n_truncated']} von {merged['n_sized']} risikobasierten Orders "
            f"wurden von VBT auf das verfügbare Geld gekürzt (größte Kürzung "
            f"{merged['max_shortfall_pct']:.1f} %). Die Risikoregel greift insoweit "
            f"nicht — die Kennzahlen messen eine kleinere, faktisch begrenzte "
            f"Position. Abhilfe: 'leverage' im portfolio-Block erhöhen (Bedarf ~ "
            f"risk_pct / Stopabstand-in-Prozent)."
        )
    if merged['n_unsized']:
        parts.append(
            f"{merged['n_unsized']} Einstiegsbalken hatten keinen bestimmbaren "
            f"Stopabstand (Vorlauf des Referenz-Indikators) und wurden nicht "
            f"gehandelt."
        )
    if parts:
        merged['note'] = ' '.join(parts)
    return merged

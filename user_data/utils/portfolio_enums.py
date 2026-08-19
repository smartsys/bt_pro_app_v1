"""Gültige Portfolio-Enum-Werte gegen die installierte VBT-Version prüfen.

Die BacktestConfig hält ``stop_exit_price`` und ``stop_order_type`` als freie
Zeichenketten und reicht sie unverändert an ``Portfolio.from_signals`` durch.
VBT löst sie dort selbst auf — case-insensitiv und unter Ignorieren von
Unterstrichen (``map_enum_fields``) — und bricht bei einem unbekannten Wert mit
``KeyError`` ab.

Damit dieser Abbruch nicht als roher Traceback beim Nutzer landet, prüfen die
Eingabegrenzen (BacktestConfig speichern, Playground-Request) den Wert vorab mit
**genau demselben** VBT-Resolver und ersetzen den ``KeyError`` durch eine
Meldung, die die gültigen Werte nennt. Es wird also keine eigene Auflösung
nachgebaut — die Entscheidung trifft weiterhin VBT, hier fällt nur die
Fehlermeldung verständlich aus.

``None`` und der leere String bedeuten „nicht gesetzt" (VBT-Default) und werden
zu ``None`` normalisiert.
"""

from typing import Optional, Tuple

import vectorbtpro as vbt
from vectorbtpro.utils.enum_ import map_enum_fields

# Gültige Werte, direkt aus der installierten VBT-Version gelesen (kein
# handgepflegtes Duplikat). Stand vbt 2026.3.1:
# StopExitPrice = Stop(-1), HardStop(-2), Close(-3) · OrderType = Market(0), Limit(1)
STOP_EXIT_PRICE_VALUES: Tuple[str, ...] = tuple(vbt.pf_enums.StopExitPrice._fields)
STOP_ORDER_TYPE_VALUES: Tuple[str, ...] = tuple(vbt.pf_enums.OrderType._fields)

# GEÄNDERT: Ticket 104 — 'risk_percent' ist KEIN VBT-SizeType, sondern eine
# App-Notation für risikobasierte Positionsgröße. Der Spec-Runner rechnet die
# Größe zur Laufzeit und schickt VBT stattdessen 'amount'
# (user_data/strategies/generic/risk_sizing.py); an der Eingabegrenze zählt sie
# als gültiger size_type-Wert.
RISK_PERCENT_SIZE_TYPE = 'risk_percent'

# Stand vbt 2026.3.1: SizeType = Amount, Value, Percent, Percent100,
# ValuePercent, ValuePercent100, TargetAmount, TargetValue, TargetPercent,
# TargetPercent100 · LeverageMode = Lazy, Eager, LazyMult, EagerMult.
SIZE_TYPE_VALUES: Tuple[str, ...] = tuple(vbt.pf_enums.SizeType._fields) + (RISK_PERCENT_SIZE_TYPE,)
LEVERAGE_MODE_VALUES: Tuple[str, ...] = tuple(vbt.pf_enums.LeverageMode._fields)


def _validate_enum_value(value: Optional[str], field_name: str, enum_tuple, valid: Tuple[str, ...]) -> Optional[str]:
    """Prüft einen Enum-String mit VBTs eigenem Resolver und gibt ihn roh zurück.

    Args:
        value: Der zu prüfende Wert (``None``/leer = nicht gesetzt).
        field_name: Feldname für die Fehlermeldung.
        enum_tuple: Das VBT-Enum-NamedTuple (z.B. ``vbt.pf_enums.StopExitPrice``).
        valid: Die gültigen Feldnamen für die Fehlermeldung.

    Returns:
        Den unveränderten Wert, oder ``None`` wenn nicht gesetzt.

    Raises:
        ValueError: Wenn VBT den Wert nicht auflösen kann.
    """
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        map_enum_fields(value, enum_tuple)
    except KeyError:
        raise ValueError(
            f"Ungültiger Wert für {field_name}: {value!r}. "
            f"Gültig sind (Groß-/Kleinschreibung egal): {', '.join(valid)} "
            f"— oder leer für den VBT-Default."
        ) from None
    return value


def validate_stop_exit_price(value: Optional[str]) -> Optional[str]:
    """Prüft ``stop_exit_price`` gegen ``vbt.pf_enums.StopExitPrice``.

    Args:
        value: Der zu prüfende Wert (``None``/leer = VBT-Default).

    Returns:
        Den unveränderten Wert, oder ``None`` wenn nicht gesetzt.

    Raises:
        ValueError: Wenn VBT den Wert nicht auflösen kann.
    """
    return _validate_enum_value(
        value, 'stop_exit_price', vbt.pf_enums.StopExitPrice, STOP_EXIT_PRICE_VALUES
    )


def validate_stop_order_type(value: Optional[str]) -> Optional[str]:
    """Prüft ``stop_order_type`` gegen ``vbt.pf_enums.OrderType``.

    Args:
        value: Der zu prüfende Wert (``None``/leer = VBT-Default).

    Returns:
        Den unveränderten Wert, oder ``None`` wenn nicht gesetzt.

    Raises:
        ValueError: Wenn VBT den Wert nicht auflösen kann.
    """
    return _validate_enum_value(
        value, 'stop_order_type', vbt.pf_enums.OrderType, STOP_ORDER_TYPE_VALUES
    )


def validate_size_type(value: str) -> str:
    """Prüft ``size_type`` gegen ``vbt.pf_enums.SizeType`` plus den App-Sonderwert.

    ``risk_percent`` ist kein VBT-``SizeType``, sondern eine App-Notation für
    risikobasierte Positionsgröße (Ticket 104) — der Spec-Runner behandelt sie
    gesondert, bevor der Wert an ``from_signals`` geht.

    Args:
        value: Der zu prüfende Wert (NOT NULL — ``size_type`` kennt keinen
            „nicht gesetzt"-Zustand).

    Returns:
        Den unveränderten Wert.

    Raises:
        ValueError: Wenn VBT den Wert nicht auflösen kann und es nicht der
            App-Sonderwert ``risk_percent`` ist.
    """
    if isinstance(value, str) and value.strip().lower() == RISK_PERCENT_SIZE_TYPE:
        return value
    try:
        map_enum_fields(value, vbt.pf_enums.SizeType)
    except KeyError:
        raise ValueError(
            f"Ungültiger Wert für size_type: {value!r}. "
            f"Gültig sind (Groß-/Kleinschreibung egal): {', '.join(SIZE_TYPE_VALUES)}."
        ) from None
    return value


def validate_leverage_mode(value: Optional[str]) -> str:
    """Prüft ``leverage_mode`` gegen ``vbt.pf_enums.LeverageMode``.

    Anders als die beiden Stop-Ausführungsfelder ist ``leverage_mode`` NOT
    NULL (geht immer an ``from_signals``) — ein leerer Wert wird auf VBTs
    eigenen Default ``lazy`` normalisiert statt ``None`` zu bleiben.

    Args:
        value: Der zu prüfende Wert. Leer/``None`` -> Default ``lazy``.

    Returns:
        Den unveränderten (oder auf ``lazy`` normalisierten) Wert.

    Raises:
        ValueError: Wenn VBT den Wert nicht auflösen kann.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return 'lazy'
    try:
        map_enum_fields(value, vbt.pf_enums.LeverageMode)
    except KeyError:
        raise ValueError(
            f"Ungültiger Wert für leverage_mode: {value!r}. "
            f"Gültig sind (Groß-/Kleinschreibung egal): {', '.join(LEVERAGE_MODE_VALUES)}."
        ) from None
    return value


def validate_leverage(value: float) -> float:
    """Prüft ``leverage`` auf einen positiven Wert.

    VBT interpretiert ``leverage`` als Multiplikator auf das verfügbare
    Kapital; ein Wert <= 0 ist nicht sinnvoll interpretierbar und wird an der
    Eingabegrenze abgewiesen statt VBT einen stillen Fehlwert rechnen zu
    lassen.

    Args:
        value: Der zu prüfende Wert.

    Returns:
        Den unveränderten Wert.

    Raises:
        ValueError: Wenn der Wert nicht positiv ist.
    """
    if value is None or value <= 0:
        raise ValueError(f"Ungültiger Wert für leverage: {value!r}. Muss > 0 sein.")
    return value


def validate_risk_pct(value: Optional[float]) -> Optional[float]:
    """Prüft ``risk_pct`` auf einen nicht-negativen Wert.

    ``None`` bedeutet „nicht gesetzt" — der Wert ist ohnehin nur bei
    ``size_type = 'risk_percent'`` wirksam (Ticket 104).

    Args:
        value: Der zu prüfende Wert, oder ``None``.

    Returns:
        Den unveränderten Wert.

    Raises:
        ValueError: Wenn der Wert gesetzt und negativ ist.
    """
    if value is None:
        return None
    if value < 0:
        raise ValueError(f"Ungültiger Wert für risk_pct: {value!r}. Darf nicht negativ sein.")
    return value


def validate_portfolio_enums(portfolio: dict) -> None:
    """Prüft die Enum-/Wertebereichs-Felder eines ``portfolio``-Blocks.

    Args:
        portfolio: Der Portfolio-Block (z.B. aus einem Playground-Request).

    Raises:
        ValueError: Wenn einer der Werte ungültig ist.
    """
    validate_stop_exit_price(portfolio.get('stop_exit_price'))
    validate_stop_order_type(portfolio.get('stop_order_type'))
    # GEÄNDERT: Ticket 104 — size_type (inkl. App-Sonderwert 'risk_percent'),
    # risk_pct, leverage und leverage_mode ebenfalls an der Eingabegrenze prüfen.
    if portfolio.get('size_type') is not None:
        validate_size_type(portfolio.get('size_type'))
    validate_risk_pct(portfolio.get('risk_pct'))
    if portfolio.get('leverage') is not None:
        validate_leverage(portfolio.get('leverage'))
    if portfolio.get('leverage_mode') is not None:
        validate_leverage_mode(portfolio.get('leverage_mode'))

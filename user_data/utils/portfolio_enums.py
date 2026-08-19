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


def validate_portfolio_enums(portfolio: dict) -> None:
    """Prüft die beiden Stop-Enum-Felder eines ``portfolio``-Blocks.

    Args:
        portfolio: Der Portfolio-Block (z.B. aus einem Playground-Request).

    Raises:
        ValueError: Wenn einer der beiden Werte ungültig ist.
    """
    validate_stop_exit_price(portfolio.get('stop_exit_price'))
    validate_stop_order_type(portfolio.get('stop_order_type'))

"""Handelsfenster einer BacktestConfig und Zuschnitt des Portfolios darauf.

Alle Kennzahlen eines Results beziehen sich ausschließlich auf das
Handelsfenster `start`–`end` der BacktestConfig. Der Vorlauf
(`ohlc_start`–`ohlc_end`) existiert allein, damit die Indikatoren aufgewärmt
sind, und geht in keine Kennzahl ein.

Warum ein eigenes Modul: Der Zuschnitt wird an sechs Stellen gebraucht
(gechunkter Lauf, ungechunkter Lauf, Einzel-Kombination, Recompute,
Full-Metriken, Playground-Schnellbacktest). Er steht deshalb genau einmal hier
und nicht sechsmal kopiert. Das Modul braucht nur pandas — kein vectorbtpro,
keine Datenbank —, damit es aus dem Runner, dem DB-Repository und den
API-Routen gleichermaßen importierbar bleibt.
"""

from typing import Any, Optional, Tuple

import pandas as pd


def build_trading_window(backtest_config: dict) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """Bildet die beiden Grenzen des Handelsfensters aus der BacktestConfig.

    Einzige Bildungsvorschrift im System: `pd.Timestamp(..., tz='UTC')` auf
    `backtest_config['start']` und `['end']`. Der Spec-Runner übergibt exakt
    diese beiden Werte als Datumsmaske an die Rules-Engine
    (`rules_engine.evaluate_rules_native`, Maske `idx >= start` und
    `idx <= end`) — der Zuschnitt der Kennzahlen muss dieselben Grenzen
    verwenden, sonst driften Signalfenster und Messfenster auseinander.

    Beide Grenzen sind inklusiv. Ein `end` ohne Uhrzeit ist damit Mitternacht
    des genannten Tages: Der letzte gemessene Balken ist `end 00:00`, spätere
    Intraday-Balken desselben Tages liegen außerhalb. Das ist bewusst dieselbe
    Auslegung wie in der bestehenden Entry-Maske — nicht enger und nicht
    weiter.

    Args:
        backtest_config: BacktestConfig-Dict mit den Schlüsseln 'start' und 'end'.

    Returns:
        Tupel (start, end) als tz-bewusste UTC-Zeitstempel.

    Raises:
        ValueError: Wenn 'start' oder 'end' fehlt, leer ist oder nicht als
            Zeitstempel lesbar ist.
    """
    if not isinstance(backtest_config, dict):
        raise ValueError(
            "Handelsfenster nicht bestimmbar: backtest_config fehlt oder ist kein Dict. "
            "Kennzahlen dürfen nicht über den Vorlauf gerechnet werden."
        )

    missing = [key for key in ('start', 'end') if not backtest_config.get(key)]
    if missing:
        raise ValueError(
            "Handelsfenster nicht bestimmbar: fehlende Felder in der BacktestConfig — "
            + ", ".join(missing)
            + ". Kennzahlen dürfen nicht über den Vorlauf gerechnet werden."
        )

    try:
        start = pd.Timestamp(backtest_config['start'], tz='UTC')
        end = pd.Timestamp(backtest_config['end'], tz='UTC')
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Handelsfenster nicht bestimmbar: 'start'/'end' der BacktestConfig sind keine "
            f"lesbaren Zeitstempel ({backtest_config.get('start')!r} / "
            f"{backtest_config.get('end')!r}) — {exc}"
        ) from exc

    if start > end:
        raise ValueError(
            f"Handelsfenster ungültig: start ({start}) liegt hinter end ({end})."
        )
    return start, end


def slice_to_trading_window(portfolios: Any, backtest_config: dict) -> Any:
    """Schneidet ein fertiges Portfolio auf das Handelsfenster zu.

    Am vbt-Kernel geprüft: `pf.loc[start:end]` erhält den vollständigen
    Spalten-Index (Multi-Kombination überlebt), lässt `total_return`
    unverändert (im Vorlauf liegt kein Trade, das Startvermögen ist dort
    konstant `init_cash`) und rechnet die zeitraumbezogenen Größen —
    Buy-and-Hold-Vergleichsmaßstab, Sharpe, annualisierte Kennzahlen — auf dem
    Fenster neu. Eine Neusimulation ist dafür nicht nötig.

    Eine Position, die über `end` hinausläuft, wird zur Fenstergrenze
    marktbewertet und erscheint als offener Trade. Wie die Kennzahlen damit
    umgehen, steht in den Docstrings der Extraktionsfunktionen in
    `user_data/utils/database/repository.py`.

    Args:
        portfolios: Fertiges vbt-Portfolio (Einzel- oder Multi-Kombination).
        backtest_config: BacktestConfig-Dict mit 'start' und 'end'.

    Returns:
        Auf das Handelsfenster zugeschnittenes Portfolio.

    Raises:
        ValueError: Wenn das Handelsfenster nicht bestimmbar ist oder kein
            einziger geladener Balken darin liegt.
    """
    start, end = build_trading_window(backtest_config)
    index = portfolios.wrapper.index
    # Ohne diesen Guard läuft vbt beim leeren Schnitt in einen IndexError tief in
    # der Wrapper-Indizierung. Ein Fenster ohne Balken ist ein Fehlzustand
    # (falscher Zeitraum, fehlende OHLCV-Daten) und wird als solcher gemeldet.
    if not ((index >= start) & (index <= end)).any():
        raise ValueError(
            f"Handelsfenster {start.date()}..{end.date()} enthält keinen einzigen "
            f"geladenen Balken (geladen: {index[0]}..{index[-1]}). "
            "Kennzahlen sind darauf nicht berechenbar — Zeitraum oder OHLCV-Daten prüfen."
        )
    return portfolios.loc[start:end]


def count_open_trades(portfolios: Any) -> Optional[Any]:
    """Zählt die am Ende des übergebenen Portfolios offenen Positionen.

    Auf einem bereits zugeschnittenen Portfolio ist das die Anzahl der
    Positionen, die über das Handelsfenster hinauslaufen und deshalb nur
    marktbewertet — nicht realisiert — in die Kennzahlen eingehen.

    Args:
        portfolios: Portfolio (Einzel- oder Multi-Kombination).

    Returns:
        Skalar bei einer Kombination, Series über die Kombinationen sonst.
    """
    return portfolios.trades.status_open.count()

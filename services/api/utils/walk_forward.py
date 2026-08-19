"""Zeitfenster-Logik für den Walk-Forward.

Reine Datumsrechnung ohne FastAPI-, Queue- oder DB-Abhängigkeiten, damit sie
eigenständig testbar bleibt.
"""

import copy
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

DATE_FORMAT = '%Y-%m-%d'


def shift_backtest_window(backtest_config: dict, months: int) -> dict:
    """Verschiebt das Zeitfenster einer BacktestConfig um `months` nach vorn.

    Der neue Zeitraum beginnt am bisherigen Ende. Der Indikator-Vorlauf (der Abstand
    zwischen `ohlc_start` und `start`) bleibt dabei erhalten.

    Args:
        backtest_config: Bestehende Config mit start, end und optional ohlc_start.
        months: Länge des neuen Fensters in Monaten.

    Returns:
        Neues Config-Dict mit verschobenem start/end/ohlc_start/ohlc_end. Die
        übergebene Config bleibt unverändert.
    """
    shifted = copy.deepcopy(backtest_config)

    # GEÄNDERT: Vorlauf aus den ALTEN Werten berechnen, bevor start/end überschrieben
    # werden. Vorher wurde der alte Start erst gelesen, nachdem er bereits überschrieben
    # war — der "Vorlauf" wuchs dadurch auf die gesamte bisherige Historie an.
    old_start = datetime.strptime(shifted['start'], DATE_FORMAT)
    old_ohlc_start = datetime.strptime(shifted.get('ohlc_start') or shifted['start'], DATE_FORMAT)
    vorlauf = old_start - old_ohlc_start

    new_start = datetime.strptime(shifted['end'], DATE_FORMAT)
    new_end = new_start + relativedelta(months=months)

    shifted['start'] = new_start.strftime(DATE_FORMAT)
    shifted['end'] = new_end.strftime(DATE_FORMAT)
    shifted['ohlc_start'] = (new_start - vorlauf).strftime(DATE_FORMAT)
    shifted['ohlc_end'] = new_end.strftime(DATE_FORMAT)

    return shifted


def warmup_span(backtest_config: dict) -> timedelta:
    """Liest den Indikator-Vorlauf einer BacktestConfig (Abstand ohlc_start → start).

    Args:
        backtest_config: Config mit `start` und optional `ohlc_start`.

    Returns:
        Der Vorlauf als Zeitspanne. Ohne `ohlc_start` ist er null.
    """
    start = datetime.strptime(backtest_config['start'], DATE_FORMAT)
    ohlc_start = datetime.strptime(
        backtest_config.get('ohlc_start') or backtest_config['start'], DATE_FORMAT,
    )
    return start - ohlc_start


def set_backtest_window(backtest_config: dict, start: str, end: str) -> dict:
    """Setzt ein explizites Handelsfenster; der Indikator-Vorlauf bleibt erhalten.

    Gegenstück zu :func:`shift_backtest_window` für die Fold-Kette:
    dort sind die Fenstergrenzen aus dem Plan vorgegeben und dürfen nicht aus einer
    Monatslänge hergeleitet werden — sonst driftet der gerechnete Lauf vom
    vorregistrierten Fenster ab.

    Args:
        backtest_config: Bestehende Config mit start, end und optional ohlc_start.
        start: Neuer Handelsbeginn im Format YYYY-MM-DD.
        end: Neues Handelsende im Format YYYY-MM-DD.

    Returns:
        Neues Config-Dict mit gesetztem start/end/ohlc_start/ohlc_end. Die
        übergebene Config bleibt unverändert.

    Raises:
        ValueError: Wenn `end` nicht nach `start` liegt.
    """
    windowed = copy.deepcopy(backtest_config)

    vorlauf = warmup_span(windowed)

    new_start = datetime.strptime(start, DATE_FORMAT)
    new_end = datetime.strptime(end, DATE_FORMAT)
    if new_end <= new_start:
        raise ValueError(f'Fensterende {end} liegt nicht nach dem Fensterbeginn {start}.')

    windowed['start'] = new_start.strftime(DATE_FORMAT)
    windowed['end'] = new_end.strftime(DATE_FORMAT)
    windowed['ohlc_start'] = (new_start - vorlauf).strftime(DATE_FORMAT)
    windowed['ohlc_end'] = new_end.strftime(DATE_FORMAT)

    return windowed

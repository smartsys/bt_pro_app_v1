"""Tests für die Date-Window-Maske des Entry-Hintergrunds (_apply_entry_date_window).

Befund 7: Der grüne Entry-Hintergrund im Chart-Playground darf nur Bars im
Handelsfenster [start, end] markieren — genau wie der Motor die Entries maskiert.
Bars im Warmup-Bereich (vor start) und nach end dürfen nicht als Signal erscheinen,
obwohl das geladene OHLC-Fenster (ohlc_start..ohlc_end) weiter reicht.

Reiner Unit-Test: der Helper braucht nur pandas, kein OHLC und keine DB.
"""

import pandas as pd

from services.api.routes.api_chart_playground import _apply_entry_date_window


def _full_true_mask() -> pd.Series:
    """Entry-Maske mit stündlichem Index, an jeder Kerze True (inkl. Warmup + Nachlauf)."""
    idx = pd.date_range('2024-01-01', periods=10, freq='h', tz='UTC')
    return pd.Series(True, index=idx)


def test_warmup_bars_vor_start_fallen_raus():
    """Bars vor start werden auf False gesetzt."""
    mask = _full_true_mask()
    start = '2024-01-01 03:00:00'
    result = _apply_entry_date_window(mask, start, None)

    idx = mask.index
    # Vor start: alles False
    assert not result[idx < pd.Timestamp(start, tz='UTC')].any()
    # Ab start (inklusiv): unveraendert True
    assert result[idx >= pd.Timestamp(start, tz='UTC')].all()


def test_bars_nach_end_fallen_raus():
    """Bars nach end werden auf False gesetzt (end ist inklusiv)."""
    mask = _full_true_mask()
    end = '2024-01-01 06:00:00'
    result = _apply_entry_date_window(mask, None, end)

    idx = mask.index
    # Bis end (inklusiv): True
    assert result[idx <= pd.Timestamp(end, tz='UTC')].all()
    # Nach end: alles False
    assert not result[idx > pd.Timestamp(end, tz='UTC')].any()


def test_bars_innerhalb_bleiben_erhalten():
    """Nur das Fenster [start, end] bleibt True, beide Grenzen inklusiv."""
    mask = _full_true_mask()
    start = '2024-01-01 03:00:00'
    end = '2024-01-01 06:00:00'
    result = _apply_entry_date_window(mask, start, end)

    idx = mask.index
    inside = (idx >= pd.Timestamp(start, tz='UTC')) & (idx <= pd.Timestamp(end, tz='UTC'))
    assert result[inside].all()
    assert not result[~inside].any()
    # Genau 4 Kerzen im Fenster (03,04,05,06 Uhr)
    assert int(result.sum()) == 4


def test_ohne_grenzen_unveraendert():
    """Fehlen start und end, bleibt die Maske identisch (kein Masking)."""
    mask = _full_true_mask()
    result = _apply_entry_date_window(mask, None, None)
    assert result.equals(mask)


def test_selektive_maske_wird_nur_beschnitten_nie_erweitert():
    """Eine bereits False-Kerze innerhalb des Fensters bleibt False (nur UND-Verknuepfung)."""
    mask = _full_true_mask()
    # Kerze um 04:00 Uhr manuell auf False — darf durch das Masking nicht wieder True werden
    mask.loc[pd.Timestamp('2024-01-01 04:00:00', tz='UTC')] = False
    result = _apply_entry_date_window(mask, '2024-01-01 03:00:00', '2024-01-01 06:00:00')
    assert not bool(result.loc[pd.Timestamp('2024-01-01 04:00:00', tz='UTC')])
    # Die anderen Fenster-Kerzen (03,05,06) bleiben True
    assert int(result.sum()) == 3

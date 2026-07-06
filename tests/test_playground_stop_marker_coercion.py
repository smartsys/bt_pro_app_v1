"""Tests für die Stop-Auflösung der Trade-Marker (_coerce_param auf tp/sl_stop).

Befund 8: Die TP/SL-Preislinie der Trade-Marker im Schnellbacktest braucht einen
einzelnen Stop-Wert. Ein sweep-förmiger Stop (Range-Dict oder Liste, z.B.
tp_stop: [0.02, 0.04]) rutschte am alten dict-only-Check vorbei; float(list) warf
im Trade-Loop einen TypeError, und das per-Trade-except verwarf still jeden Trade —
Badge meldete Trades, Chart zeigte null Marker, ohne Fehlermeldung.

Fix: Beide Stops laufen jetzt durch _coerce_param — Liste → erstes Element,
Range-Dict → Startwert, Skalar bleibt. Das entspricht dem, was der Lite-Backtest
tatsaechlich rechnet (immer Kombi 1 = Startwert), sodass die Marker-Linie zur
Berechnung passt.

Reiner Unit-Test: der Helper braucht keine Abhaengigkeiten.
"""

from services.api.routes.api_chart_playground import _coerce_param


def test_skalarer_stop_bleibt_erhalten():
    """Ein echter Stop-Wert wird unveraendert durchgereicht."""
    assert _coerce_param(0.02) == 0.02


def test_liste_wird_auf_erstes_element_aufgeloest():
    """Listen-Stop (Kern von Befund 8) → erstes Element, kein float()-Crash."""
    assert _coerce_param([0.02, 0.04]) == 0.02


def test_leere_liste_wird_none():
    """Leere Liste hat keinen ersten Wert → None (keine Preislinie)."""
    assert _coerce_param([]) is None


def test_range_dict_wird_auf_startwert_aufgeloest():
    """Range-Dict (Sweep-Achse) → Startwert, konsistent zur Lite-Berechnung."""
    assert _coerce_param({'type': 'arange', 'start': 0.02, 'stop': 0.06, 'step': 0.02}) == 0.02


def test_none_bleibt_none():
    """Kein Stop gesetzt → None."""
    assert _coerce_param(None) is None

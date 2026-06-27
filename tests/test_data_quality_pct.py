"""Tests für die Datenqualitäts-Kennzahl (_quality_pct) des Daten-Endpoints.

Qualität = vorhandene Kerzen / im Zeitraum erwartete Kerzen. Erwartete Kerzen =
Intervalle zwischen erster und letzter Kerze + 1.
"""

import sys
import types

import pandas as pd

# rq ist nur im Worker-Container installiert — für reine Tests stubben wir den Import
if 'rq' not in sys.modules:
    rq_stub = types.ModuleType('rq')
    rq_stub.Queue = object
    sys.modules['rq'] = rq_stub

from services.api.routes.api_config import _quality_pct  # noqa: E402

# 1d-Intervall in Sekunden (Standard-Timeframe für die Tests).
_DAY = 86400


def test_lueckenlos_ergibt_100_prozent():
    """Zehn Tageskerzen über genau neun Tagesabstände -> 100 %."""
    first = pd.Timestamp("2020-01-01")
    last = pd.Timestamp("2020-01-10")  # 9 Intervalle -> 10 erwartete Kerzen
    assert _quality_pct(first, last, nrows=10, tf_seconds=_DAY) == 100.0


def test_fehlende_kerze_druckt_unter_100():
    """Eine fehlende Kerze im selben Zeitraum -> 9/10 = 90 %."""
    first = pd.Timestamp("2020-01-01")
    last = pd.Timestamp("2020-01-10")
    assert _quality_pct(first, last, nrows=9, tf_seconds=_DAY) == 90.0


def test_mehr_bars_als_erwartet_wird_auf_100_gedeckelt():
    """Mehr Kerzen als erwartet (z.B. Duplikate) werden auf 100 % begrenzt."""
    first = pd.Timestamp("2020-01-01")
    last = pd.Timestamp("2020-01-10")
    assert _quality_pct(first, last, nrows=15, tf_seconds=_DAY) == 100.0


def test_unbekannter_timeframe_ergibt_none():
    """Ohne bekanntes Intervall ist die Qualität nicht bestimmbar."""
    first = pd.Timestamp("2020-01-01")
    last = pd.Timestamp("2020-01-10")
    assert _quality_pct(first, last, nrows=10, tf_seconds=None) is None


def test_endzeit_vor_startzeit_ergibt_none():
    """Negative Zeitspanne ist ungültig -> None."""
    first = pd.Timestamp("2020-01-10")
    last = pd.Timestamp("2020-01-01")
    assert _quality_pct(first, last, nrows=10, tf_seconds=_DAY) is None


def test_einzelne_kerze_ergibt_100_prozent():
    """Erste = letzte Kerze: ein Intervall erwartet, eine vorhanden -> 100 %."""
    ts = pd.Timestamp("2020-01-01")
    assert _quality_pct(ts, ts, nrows=1, tf_seconds=_DAY) == 100.0

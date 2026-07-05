"""Tests für die zeitraum-bezogene Datenqualität einer Backtest-Config.

_config_range_quality misst die Vollständigkeit der OHLC-Daten im eingestellten
Config-Zeitraum [ohlc_start, ohlc_end]: vorhandene Kerzen im Bereich geteilt durch
die laut Timeframe erwarteten Kerzen. Anders als die Gesamtqualität erfasst das auch
fehlende Ränder (Daten beginnen später oder enden früher als der Config-Zeitraum).
"""

import sys
import types

import pandas as pd

# rq ist nur im Worker-Container installiert — für reine Tests stubben wir den Import
if 'rq' not in sys.modules:
    rq_stub = types.ModuleType('rq')
    rq_stub.Queue = object
    sys.modules['rq'] = rq_stub

from services.api.routes.api_config import _config_range_quality  # noqa: E402

# 1d-Intervall in Sekunden (Standard-Timeframe für die Tests).
_DAY = 86400


def _idx(start: str, end: str) -> pd.DatetimeIndex:
    """UTC-Zeit-Index mit Tageskerzen von start bis end (beide inklusive)."""
    return pd.date_range(start, end, freq='D', tz='UTC')


def test_zeitraum_voll_abgedeckt_ergibt_100_prozent():
    """Daten decken den Config-Zeitraum lückenlos ab -> 100 %."""
    idx = _idx('2020-01-01', '2020-01-10')  # 10 Tageskerzen
    assert _config_range_quality(idx, '2020-01-01', '2020-01-10', _DAY) == 100.0


def test_fehlender_rand_vorne_druckt_unter_100():
    """Daten beginnen später als ohlc_start -> fehlender Vorlauf senkt die Qualität."""
    idx = _idx('2020-01-05', '2020-01-10')  # nur 6 der 10 erwarteten Kerzen
    assert _config_range_quality(idx, '2020-01-01', '2020-01-10', _DAY) == 60.0


def test_enger_zeitraum_innerhalb_der_daten_ergibt_100_prozent():
    """Config-Zeitraum liegt vollständig innerhalb der vorhandenen Daten -> 100 %."""
    idx = _idx('2020-01-01', '2020-01-31')
    assert _config_range_quality(idx, '2020-01-10', '2020-01-20', _DAY) == 100.0


def test_keine_daten_ergibt_0_prozent():
    """Ohne Daten (idx None) bei gültigem Zeitraum -> 0 Kerzen im Bereich -> 0 %."""
    assert _config_range_quality(None, '2020-01-01', '2020-01-10', _DAY) == 0.0


def test_unbekannter_timeframe_ergibt_none():
    """Ohne bekanntes Intervall ist die Qualität nicht bestimmbar -> None."""
    idx = _idx('2020-01-01', '2020-01-10')
    assert _config_range_quality(idx, '2020-01-01', '2020-01-10', None) is None


def test_fehlender_zeitraum_ergibt_none():
    """Fehlt eine Zeitraumgrenze, ist die Kennzahl nicht bestimmbar -> None."""
    idx = _idx('2020-01-01', '2020-01-10')
    assert _config_range_quality(idx, None, '2020-01-10', _DAY) is None
    assert _config_range_quality(idx, '2020-01-01', None, _DAY) is None


def test_endzeit_vor_startzeit_ergibt_none():
    """Negative Zeitspanne ist ungültig -> None."""
    idx = _idx('2020-01-01', '2020-01-10')
    assert _config_range_quality(idx, '2020-01-10', '2020-01-01', _DAY) is None

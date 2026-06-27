"""Tests für OHLC-Download-Jobs: Intervall-Schätzung, Fortschritts-Hook und
das Zerlegen einer Symbol-Liste in Einzel-Jobs.

Reine Funktionen (_expected_intervals, _TF_SECONDS, Fortschritts-Hook) laufen
ohne DB. Der Split-Test der Download-API nutzt die PostgreSQL-Test-DB
(VBT_TEST_DATABASE_URL, Port 5562) und mockt das Einreihen in die Redis-Queue.
"""

import sys
import types

import pandas as pd
import pytest

from services.api import worker_tasks as wt


def _ensure_stub(name: str, **attrs) -> None:
    """Registriert ein Minimal-Stub-Modul, falls die echte Lib im venv fehlt."""
    if name not in sys.modules:
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module


# rq/redis sind reine Worker-/Container-Deps und im Projekt-venv nicht installiert.
# Für den Import von api_config genügen Stubs — die Queue wird im Test gemockt.
_ensure_stub('rq', Queue=object)
_ensure_stub('redis', Redis=object)


# ============================================================================
# _expected_intervals — Vorab-Schätzung der zu ladenden Bars
# ============================================================================

def test_expected_intervals_zaehlt_ganze_bars():
    """5m über genau eine Stunde -> 12 Intervalle."""
    start = pd.Timestamp('2024-01-01 00:00:00', tz='utc')
    end = pd.Timestamp('2024-01-01 01:00:00', tz='utc')
    assert wt._expected_intervals(start, end, 300) == 12


def test_expected_intervals_tagespuffer_5m():
    """5m über einen Tag -> 288 Intervalle."""
    start = pd.Timestamp('2024-01-01 00:00:00', tz='utc')
    end = start + pd.Timedelta(days=1)
    assert wt._expected_intervals(start, end, wt._TF_SECONDS['5m']) == 288


def test_expected_intervals_negativ_und_none_sind_null():
    """Ende vor Start, fehlende Werte oder unbekannter TF -> 0."""
    start = pd.Timestamp('2024-01-02', tz='utc')
    end = pd.Timestamp('2024-01-01', tz='utc')
    assert wt._expected_intervals(start, end, 300) == 0
    assert wt._expected_intervals(None, end, 300) == 0
    assert wt._expected_intervals(start, None, 300) == 0
    assert wt._expected_intervals(start, end, None) == 0


def test_tf_seconds_deckt_alle_form_timeframes():
    """Alle im Download-Formular angebotenen Timeframes haben eine Sekunden-Angabe."""
    form_tfs = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d']
    for tf in form_tfs:
        assert tf in wt._TF_SECONDS and wt._TF_SECONDS[tf] > 0


# ============================================================================
# Fortschritts-Hook — zählt Binance-Chunks und meldet chunks * limit
# ============================================================================

def test_progress_hook_zaehlt_nur_binance_chunks():
    """Pro update() der 'binance'-Leiste wird chunks*limit gemeldet; andere bar_ids
    werden ignoriert. Der Download-Pfad selbst wird nicht verändert."""
    from vectorbtpro.utils.pbar import ProgressBar

    wt._install_binance_progress_hook()
    got: list = []
    wt._progress_ctx.clear()
    wt._progress_ctx.update({'chunks': 0, 'limit': 1000, 'report': got.append})
    try:
        # show_progress=False: interne Leiste deaktiviert, der Hook zählt trotzdem mit.
        pb = ProgressBar(show_progress=False, bar_id='binance')
        pb.update()
        pb.update()
        pb.update()
        assert got == [1000, 2000, 3000]

        # Andere Leiste darf nicht mitzählen.
        got.clear()
        other = ProgressBar(show_progress=False, bar_id='recompute')
        other.update()
        assert got == []
    finally:
        wt._progress_ctx.clear()


def test_progress_hook_ohne_aktiven_job_ist_no_op():
    """Ohne gesetzten report-Callback bleibt update() ein reiner Durchlauf."""
    from vectorbtpro.utils.pbar import ProgressBar

    wt._install_binance_progress_hook()
    wt._progress_ctx.clear()
    pb = ProgressBar(show_progress=False, bar_id='binance')
    # Darf nicht werfen und nichts melden (kein report registriert).
    pb.update()


# ============================================================================
# Download-API — zerlegt Symbol-Liste in Einzel-Jobs (ein Symbol je Job)
# ============================================================================

def test_download_endpoint_legt_einen_job_je_symbol_an(db_engine):
    """POST /data/download mit 3 Symbolen erzeugt 3 Jobs mit je einem Symbol."""
    from unittest.mock import patch
    from sqlalchemy.orm import sessionmaker

    from user_data.utils.database.models import OhlcDownloadJob

    Session = sessionmaker(bind=db_engine)
    route_session = Session()

    from services.api.routes.api_config import create_download_job, OhlcDownloadIn

    payload = OhlcDownloadIn(
        exchange='binance',
        timeframe='5m',
        symbols=['BTCUSDT', 'ETHUSDT', 'btcusdt', 'FETUSDT'],  # Duplikat (Casing) raus
        start_date='2024-01-01',
        end_date=None,
    )
    with patch('services.api.routes.api_config.get_session', return_value=route_session), \
         patch('services.api.routes.api_config._enqueue_ohlc_job', return_value='rq-fake'):
        result = create_download_job(payload)

    assert result['error'] is None
    assert result['data']['count'] == 3  # Duplikat entfernt

    check = Session()
    try:
        jobs = check.query(OhlcDownloadJob).order_by(OhlcDownloadJob.id).all()
        assert len(jobs) == 3
        symbols = sorted(j.symbols[0] for j in jobs)
        assert symbols == ['BTCUSDT', 'ETHUSDT', 'FETUSDT']
        for j in jobs:
            assert len(j.symbols) == 1
            assert j.job_type == 'download'
            assert j.timeframe == '5m'
            assert j.status == 'queued'
            assert j.rq_job_id == 'rq-fake'
    finally:
        check.close()
        route_session.close()

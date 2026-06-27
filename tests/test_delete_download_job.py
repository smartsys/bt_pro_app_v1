"""Tests für das Löschen/Abbrechen von OHLC-Download-Jobs (delete_download_job).

Prüft die Status-Verzweigung:
- 'completed'/'failed': nur DB-Zeile entfernen, kein RQ-Eingriff.
- 'queued': wartenden RQ-Job stornieren (RqJob.fetch(...).cancel()).
- 'running': laufenden RQ-Job hart stoppen (send_stop_job_command).
- unbekannte ID: 404.

Nutzt die PostgreSQL-Test-DB (db_engine-Fixture). rq/redis sind Worker-/Container-Deps
und im venv nicht installiert — sie werden gestubbt, die RQ-Aufrufe gemockt.
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# rq + redis als Minimal-Stubs registrieren (für den Import von api_config)
if 'rq' not in sys.modules:
    rq_stub = types.ModuleType('rq')
    rq_stub.Queue = object
    sys.modules['rq'] = rq_stub
if 'redis' not in sys.modules:
    redis_stub = types.ModuleType('redis')
    redis_stub.Redis = object
    sys.modules['redis'] = redis_stub

from sqlalchemy.orm import sessionmaker  # noqa: E402

from services.api.routes import api_config as api_config_module  # noqa: E402
from user_data.utils.database.models import OhlcDownloadJob  # noqa: E402


def _make_job(session, status: str, rq_job_id='rq-fake') -> int:
    """Legt einen OHLC-Job mit gegebenem Status an und liefert dessen ID."""
    job = OhlcDownloadJob(
        job_type='download',
        exchange='binance',
        timeframe='5m',
        symbols=['BTCUSDT'],
        status=status,
        rq_job_id=rq_job_id,
    )
    session.add(job)
    session.commit()
    return job.id


def _call_delete(job_id, route_session):
    """Ruft delete_download_job mit gestubbten rq-Submodulen auf und gibt
    (result, send_stop_mock, job_fetch_mock) zurück."""
    cmd_mod = types.ModuleType('rq.command')
    cmd_mod.send_stop_job_command = MagicMock()
    job_mod = types.ModuleType('rq.job')
    job_mod.Job = MagicMock()
    with patch.dict(sys.modules, {'rq.command': cmd_mod, 'rq.job': job_mod}), \
         patch.object(api_config_module, 'get_session', return_value=route_session), \
         patch.object(api_config_module, 'get_redis_connection', return_value=object()):
        result = api_config_module.delete_download_job(job_id)
    return result, cmd_mod.send_stop_job_command, job_mod.Job.fetch


def test_completed_job_wird_ohne_rq_eingriff_geloescht(db_engine):
    Session = sessionmaker(bind=db_engine)
    job_id = _make_job(Session(), 'completed')

    result, send_stop, job_fetch = _call_delete(job_id, Session())

    assert result['error'] is None
    assert result['data']['deleted'] == job_id
    assert not send_stop.called
    assert not job_fetch.called
    assert Session().query(OhlcDownloadJob).filter_by(id=job_id).first() is None


def test_queued_job_wird_storniert_und_geloescht(db_engine):
    Session = sessionmaker(bind=db_engine)
    job_id = _make_job(Session(), 'queued')

    result, send_stop, job_fetch = _call_delete(job_id, Session())

    assert result['data']['deleted'] == job_id
    assert job_fetch.called          # RqJob.fetch(...) -> .cancel()
    assert not send_stop.called
    assert Session().query(OhlcDownloadJob).filter_by(id=job_id).first() is None


def test_running_job_wird_hart_gestoppt_und_geloescht(db_engine):
    Session = sessionmaker(bind=db_engine)
    job_id = _make_job(Session(), 'running')

    result, send_stop, job_fetch = _call_delete(job_id, Session())

    assert result['data']['deleted'] == job_id
    assert send_stop.called           # send_stop_job_command(redis, rq_job_id)
    assert not job_fetch.called
    assert Session().query(OhlcDownloadJob).filter_by(id=job_id).first() is None


def test_unbekannte_id_ergibt_404(db_engine):
    Session = sessionmaker(bind=db_engine)

    result, send_stop, job_fetch = _call_delete(999999, Session())

    # delete_download_job gibt bei fehlendem Job eine JSONResponse mit 404 zurück.
    assert getattr(result, 'status_code', None) == 404
    assert not send_stop.called
    assert not job_fetch.called

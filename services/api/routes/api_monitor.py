"""API für die Queue-/Job-Übersicht (Monitoring).

GET /api/monitor/overview — Live-Zustand aller RQ-Queues und Worker (aus Redis)
                            plus Status-Zusammenfassung und aktive Jobs (aus der DB).

Diese Maske bündelt, was bisher über drei getrennte Domänen-Listen verteilt war
(Backtest-Runs, OHLC-Jobs, Reindex-Läufe), und ergänzt die Live-Sicht auf Redis.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import func

from services.api.redis_conn import (
    get_redis_connection,
    BACKTEST_QUEUE_NAME,
    RECOMPUTE_QUEUE_NAME,
    OHLC_DOWNLOAD_QUEUE_NAME,
)
from user_data.utils.database.db import get_session
from user_data.utils.database.models import (
    BacktestRun,
    BacktestJob,
    OhlcDownloadJob,
    TestSetRun,
    VaultReindexRun,
)

router = APIRouter(prefix='/api/monitor', tags=['monitor'])

# Queues in Prioritätsreihenfolge (identisch zum Worker-Entrypoint).
QUEUE_NAMES = [BACKTEST_QUEUE_NAME, RECOMPUTE_QUEUE_NAME, OHLC_DOWNLOAD_QUEUE_NAME]

# Als aktiv (offen) gelten diese Status — quer über alle Job-Tabellen.
ACTIVE_STATES = ('queued', 'running')


def _iso(dt) -> str | None:
    """Wandelt ein datetime in ISO-String oder None."""
    return dt.isoformat() if dt else None


def _collect_redis_state() -> dict:
    """Liest Queue-Längen, Registries und aktive Worker aus Redis.

    Returns:
        Dict mit Schlüsseln 'queues', 'workers' und 'available'. Bei nicht
        erreichbarem Redis ist 'available' False und 'error' gesetzt.
    """
    from rq import Queue, Worker
    from rq.registry import (
        StartedJobRegistry,
        FailedJobRegistry,
        FinishedJobRegistry,
        DeferredJobRegistry,
    )

    conn = get_redis_connection()
    conn.ping()

    queues = []
    for name in QUEUE_NAMES:
        q = Queue(name, connection=conn)
        queues.append({
            'name': name,
            'queued': q.count,
            'started': StartedJobRegistry(name, connection=conn).count,
            'failed': FailedJobRegistry(name, connection=conn).count,
            'finished': FinishedJobRegistry(name, connection=conn).count,
            'deferred': DeferredJobRegistry(name, connection=conn).count,
        })

    workers = []
    for w in Worker.all(connection=conn):
        current = w.get_current_job()
        workers.append({
            'name': w.name,
            'state': w.get_state(),
            'queues': w.queue_names(),
            'current_job': current.func_name if current else None,
            'successful_jobs': w.successful_job_count,
            'failed_jobs': w.failed_job_count,
            'last_heartbeat': _iso(w.last_heartbeat),
        })

    return {'available': True, 'queues': queues, 'workers': workers}


def _status_counts(session, model) -> dict:
    """Zählt die Datensätze einer Job-Tabelle gruppiert nach Status (SQL GROUP BY).

    Aggregiert in der DB, damit der Abruf auch bei grossen Tabellen und kurzem
    Auto-Update-Intervall leicht bleibt.
    """
    rows = session.query(model.status, func.count()).group_by(model.status).all()
    return {status: count for status, count in rows}


def _active_backtest_runs(session) -> list:
    """Offene Backtest-Runs als vereinheitlichte Job-Zeilen."""
    rows = (
        session.query(BacktestRun)
        .filter(BacktestRun.status.in_(ACTIVE_STATES))
        .order_by(BacktestRun.created_at.desc())
        .all()
    )
    items = []
    for r in rows:
        progress = None
        if r.current_chunk is not None and r.total_chunks:
            progress = f'Chunk {r.current_chunk}/{r.total_chunks}'
        items.append({
            'type': 'backtest_run',
            'type_label': 'Backtest-Run',
            'queue': BACKTEST_QUEUE_NAME,
            'id': r.id,
            'label': f'{r.strategy_name} · {r.symbol} {r.timeframe}',
            'status': r.status,
            'progress': progress,
            'rq_job_id': None,
            'error_message': r.error_message,
            'created_at': _iso(r.created_at),
            'started_at': _iso(r.started_at),
            'detail_url': f'/backtest/runs/{r.id}',
        })
    return items


def _active_backtest_jobs(session) -> list:
    """Offene Recompute-Jobs als vereinheitlichte Job-Zeilen."""
    rows = (
        session.query(BacktestJob)
        .filter(BacktestJob.status.in_(ACTIVE_STATES))
        .order_by(BacktestJob.created_at.desc())
        .all()
    )
    return [{
        'type': 'backtest_job',
        'type_label': 'Recompute',
        'queue': RECOMPUTE_QUEUE_NAME,
        'id': r.id,
        'label': f'Result {r.result_id} (Run {r.run_id})',
        'status': r.status,
        'progress': f'Neustart {r.retry_count}' if r.retry_count else None,
        'rq_job_id': r.rq_job_id,
        'error_message': r.error_message,
        'created_at': _iso(r.created_at),
        'started_at': _iso(r.started_at),
        'detail_url': None,
    } for r in rows]


def _active_ohlc_jobs(session) -> list:
    """Offene OHLC-Download-Jobs als vereinheitlichte Job-Zeilen."""
    rows = (
        session.query(OhlcDownloadJob)
        .filter(OhlcDownloadJob.status.in_(ACTIVE_STATES))
        .order_by(OhlcDownloadJob.created_at.desc())
        .all()
    )
    items = []
    for r in rows:
        progress = None
        if r.intervals_done is not None and r.intervals_total:
            progress = f'{r.intervals_done}/{r.intervals_total} Bars'
        items.append({
            'type': 'ohlc_download_job',
            'type_label': 'OHLC-Download',
            'queue': OHLC_DOWNLOAD_QUEUE_NAME,
            'id': r.id,
            'label': f'{r.job_type} {r.exchange} {r.timeframe}',
            'status': r.status,
            'progress': progress,
            'rq_job_id': r.rq_job_id,
            'error_message': r.message,
            'created_at': _iso(r.created_at),
            'started_at': _iso(r.started_at),
            'detail_url': '/config/data',
        })
    return items


def _active_testset_runs(session) -> list:
    """Offene TestSet-Läufe als vereinheitlichte Job-Zeilen."""
    rows = (
        session.query(TestSetRun)
        .filter(TestSetRun.status.in_(ACTIVE_STATES))
        .order_by(TestSetRun.created_at.desc())
        .all()
    )
    return [{
        'type': 'testset_run',
        'type_label': 'TestSet-Lauf',
        'queue': BACKTEST_QUEUE_NAME,
        'id': r.id,
        'label': f'TestSet {r.testset_id} · {r.strategy_name}',
        'status': r.status,
        'progress': f'{r.n_runs_completed}/{r.n_runs_total} Runs',
        'rq_job_id': None,
        'error_message': None,
        'created_at': _iso(r.created_at),
        'started_at': None,
        'detail_url': None,
    } for r in rows]


def _active_reindex_runs(session) -> list:
    """Offene Vault-Reindex-Läufe als vereinheitlichte Job-Zeilen."""
    rows = (
        session.query(VaultReindexRun)
        .filter(VaultReindexRun.status.in_(ACTIVE_STATES))
        .order_by(VaultReindexRun.created_at.desc())
        .all()
    )
    return [{
        'type': 'vault_reindex_run',
        'type_label': 'Vault-Reindex',
        'queue': RECOMPUTE_QUEUE_NAME,
        'id': r.id,
        'label': f'{r.scope} {r.target_path or ""}'.strip(),
        'status': r.status,
        'progress': None,
        'rq_job_id': r.job_id,
        'error_message': r.error_message,
        'created_at': _iso(r.created_at),
        'started_at': _iso(r.started_at),
        'detail_url': f'/knowledge/runs/{r.id}',
    } for r in rows]


@router.get('/overview')
def monitor_overview():
    """Gesamtübersicht: Live-Queues/Worker aus Redis plus DB-Job-Status.

    Returns:
        JSON mit 'redis' (Queues + Worker), 'db_summary' (Statuszählung je
        Tabelle) und 'active_jobs' (alle offenen Jobs quer über die Tabellen).
    """
    # Redis-Teil defensiv: fällt Redis aus, bleibt die DB-Sicht trotzdem nutzbar.
    try:
        redis_state = _collect_redis_state()
    except Exception as exc:
        redis_state = {'available': False, 'error': str(exc), 'queues': [], 'workers': []}

    with get_session() as session:
        db_summary = {
            'backtest_runs': _status_counts(session, BacktestRun),
            'backtest_jobs': _status_counts(session, BacktestJob),
            'ohlc_download_jobs': _status_counts(session, OhlcDownloadJob),
            'testset_runs': _status_counts(session, TestSetRun),
            'vault_reindex_runs': _status_counts(session, VaultReindexRun),
        }
        active_jobs = (
            _active_backtest_runs(session)
            + _active_backtest_jobs(session)
            + _active_ohlc_jobs(session)
            + _active_testset_runs(session)
            + _active_reindex_runs(session)
        )

    return {
        'data': {
            'redis': redis_state,
            'db_summary': db_summary,
            'active_jobs': active_jobs,
        },
        'error': None,
    }


@router.delete('/failed')
def reset_failed_jobs():
    """Leert die RQ-Failed-Registries aller Queues.

    Entfernt die fehlgeschlagenen Jobs endgültig aus Redis (inklusive Job-Hash).
    Setzt die 'Fehlgeschlagen'-Zähler der Queue-Karten auf 0.

    Returns:
        JSON mit Anzahl entfernter Einträge je Queue, oder Fehler wenn Redis
        nicht erreichbar ist.
    """
    try:
        from rq.registry import FailedJobRegistry

        conn = get_redis_connection()
        conn.ping()

        per_queue: dict = {}
        total = 0
        for name in QUEUE_NAMES:
            reg = FailedJobRegistry(name, connection=conn)
            job_ids = reg.get_job_ids()
            for job_id in job_ids:
                # delete_job=True entfernt zusätzlich den Job-Hash, nicht nur den
                # Registry-Eintrag — sonst bleiben verwaiste Job-Daten in Redis.
                reg.remove(job_id, delete_job=True)
            per_queue[name] = len(job_ids)
            total += len(job_ids)

        return {'data': {'removed_total': total, 'per_queue': per_queue}, 'error': None}
    except Exception as exc:
        return JSONResponse(
            {'data': None, 'error': f'Zurücksetzen fehlgeschlagen: {exc}'},
            status_code=500,
        )

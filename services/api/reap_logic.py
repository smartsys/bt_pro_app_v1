"""Reine Entscheidungslogik des Reapers (services/api/reap_stale_jobs.py).

Bewusst ohne rq/redis/DB-Abhaengigkeiten, damit sie ohne Container und ohne
externe Dienste testbar ist. Der Reaper selbst kuemmert sich um Redis-Zugriff,
DB-Updates und Re-Enqueue; hier steckt nur die Frage: was ist mit einem Job zu
tun?
"""

from datetime import datetime, timedelta

# Insgesamt erlaubte Startversuche (Original + automatische Neustarts).
MAX_STARTS: int = 3
# Job-Timeout beim Einreihen (siehe start_recompute_jobs) plus Puffer. Ein
# 'running'-Job, dessen started_at aelter ist, gilt als tot (RQ haette ihn
# langst beim Timeout abgebrochen).
JOB_TIMEOUT_SECONDS: int = 600
STALE_RUNNING_SECONDS: int = JOB_TIMEOUT_SECONDS + 300


def is_stale(status: str, alive: bool, started_at: datetime | None, now: datetime) -> bool:
    """Prüft, ob ein queued/running Job verwaist ist.

    Args:
        status: Aktueller Job-Status ('queued' oder 'running').
        alive: Ob der zugehoerige RQ-Job noch in Redis existiert.
        started_at: Zeitpunkt des Verarbeitungsstarts (nur bei running relevant).
        now: Aktuelle Zeit (naive, gleiche Zeitzone wie started_at).

    Returns:
        True, wenn der Job als verwaist gilt.
    """
    if status == 'running':
        too_old = started_at is not None and started_at < now - timedelta(seconds=STALE_RUNNING_SECONDS)
        return (not alive) or too_old
    # queued: nur verwaist, wenn Redis den Job verloren hat
    return not alive


def classify_job(
    status: str,
    alive: bool,
    started_at: datetime | None,
    now: datetime,
    retry_count: int,
) -> str:
    """Entscheidet, wie mit einem Job zu verfahren ist.

    Returns:
        'skip'  - Job ist gesund, nicht anfassen.
        'retry' - Job ist verwaist und darf neu gestartet werden.
        'fail'  - Job ist verwaist und hat die erlaubten Startversuche erschoepft.
    """
    if not is_stale(status, alive, started_at, now):
        return 'skip'
    starts_so_far = retry_count + 1  # inkl. Original-Start
    return 'retry' if starts_so_far < MAX_STARTS else 'fail'

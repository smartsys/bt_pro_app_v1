"""Reine Entscheidungslogik des Run-Reapers (services/api/reap_stale_runs.py).

Bewusst ohne rq/redis/DB-Abhängigkeiten, damit sie ohne Container und ohne
externe Dienste testbar ist. Übersetzt den RQ-Zustand eines toten Jobs in eine
lesbare Abbruch-Begründung für backtest_runs.error_message (Ticket 69).

RQ erkennt einen hart beendeten Work-Horse (OOM-Killer, kill -9) selbst: der
überlebende Worker-Prozess ruft handle_job_failure() auf und schreibt einen
festen exc_string der Form 'Work-horse terminated unexpectedly; waitpid
returned <val> (signal <n>); ' in job.exc_info (siehe
rq/worker/worker_classes.py, monitor_work_horse()). Signal 9 (SIGKILL) ist
das Signal, mit dem sowohl der OOM-Killer als auch ein manuelles 'kill -9'
den Work-Horse beendet — die beiden sind auf dieser Ebene nicht
unterscheidbar, deshalb 'mutmaßlich'.
"""

import re

WORK_HORSE_MARKER: str = 'Work-horse terminated unexpectedly'
OOM_SIGNAL: int = 9  # SIGKILL

_SIGNAL_RE = re.compile(r'\(signal (\d+)\)')


def build_abort_reason(exc_info: str | None) -> str:
    """Übersetzt den RQ-Zustand eines toten Jobs in eine lesbare Abbruch-Begründung.

    Args:
        exc_info: exc_info-Text des Jobs aus der FailedJobRegistry, oder None,
            wenn zur run_id in Redis gar kein Job mehr auffindbar ist (Job
            verschwunden, z.B. abgelaufene TTL oder Altbestand von vor der
            Einführung dieser Erkennung).

    Returns:
        Lesbarer deutscher Text für backtest_runs.error_message. Unterscheidet
        Speicher-Abbruch (Signal 9) von sonstigem Work-Horse-Absturz und von
        einem regulären Fehler außerhalb des eigenen try/except von
        run_backtest_job (z.B. Konfigurationsfehler vor dem Statuswechsel auf
        'running').
    """
    if not exc_info:
        return (
            "Lauf abgebrochen: RQ-Job zu diesem Run nicht mehr auffindbar "
            "(Worker-Prozess vermutlich beendet, Ursache unbekannt)."
        )

    if WORK_HORSE_MARKER in exc_info:
        match = _SIGNAL_RE.search(exc_info)
        if match is None:
            return (
                "Lauf abgebrochen: Worker-Prozess unerwartet beendet "
                "(kein Signal erkennbar)."
            )
        signal = int(match.group(1))
        if signal == OOM_SIGNAL:
            return (
                "Lauf abgebrochen: Worker-Prozess vom Betriebssystem beendet "
                "(Signal 9 / SIGKILL, mutmaßlich Speichermangel/OOM)."
            )
        return f"Lauf abgebrochen: Worker-Prozess unerwartet beendet (Signal {signal})."

    # Regulärer Fehler außerhalb des eigenen try/except von run_backtest_job —
    # die letzte Zeile der Traceback trägt üblicherweise die Exception-Meldung.
    lines = exc_info.strip().splitlines()
    last_line = lines[-1] if lines else exc_info
    return f"Lauf abgebrochen mit Fehler: {last_line[:500]}"

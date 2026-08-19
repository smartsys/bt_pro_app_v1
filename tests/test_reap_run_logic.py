"""Tests für die reine Entscheidungslogik des Run-Reapers (services/api/reap_run_logic.py).

Deckt die Übersetzung eines toten RQ-Jobs in eine lesbare Abbruch-Begründung ab
(Ticket 69). Keine DB, kein Redis — reine Logik mit festen exc_info-Texten.
"""

from services.api.reap_run_logic import build_abort_reason


def test_work_horse_mit_signal_9_gilt_als_speicher_abbruch():
    exc_info = 'Work-horse terminated unexpectedly; waitpid returned -9 (signal 9); '
    reason = build_abort_reason(exc_info)
    assert 'Speichermangel' in reason or 'OOM' in reason
    assert 'Signal 9' in reason


def test_work_horse_mit_anderem_signal_ist_kein_speicher_abbruch():
    exc_info = 'Work-horse terminated unexpectedly; waitpid returned -11 (signal 11); '
    reason = build_abort_reason(exc_info)
    assert 'Signal 11' in reason
    assert 'Speichermangel' not in reason
    assert 'OOM' not in reason


def test_work_horse_ohne_erkennbares_signal():
    exc_info = 'Work-horse terminated unexpectedly; waitpid returned 1; '
    reason = build_abort_reason(exc_info)
    assert 'kein Signal erkennbar' in reason


def test_regulaerer_fehler_wird_von_speicher_abbruch_unterschieden():
    exc_info = (
        'Traceback (most recent call last):\n'
        '  File "worker_tasks.py", line 1, in run_backtest_job\n'
        'ValueError: iteration_id fehlt'
    )
    reason = build_abort_reason(exc_info)
    assert 'Speichermangel' not in reason
    assert 'OOM' not in reason
    assert 'Work-Horse' not in reason
    assert 'ValueError: iteration_id fehlt' in reason


def test_job_verschwunden_liefert_eigene_begruendung():
    reason = build_abort_reason(None)
    assert 'nicht mehr auffindbar' in reason
    assert 'Ursache unbekannt' in reason


def test_leerer_exc_info_string_wird_wie_verschwunden_behandelt():
    reason = build_abort_reason('')
    assert 'nicht mehr auffindbar' in reason

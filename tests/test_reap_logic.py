"""Tests für die reine Entscheidungslogik des Reapers (services/api/reap_logic.py).

Deckt die Verwaisungs-Erkennung (is_stale) und die Klassifizierung inklusive der
Startversuch-Zaehlung (classify_job) ab. Keine DB, kein Redis - reine Logik mit
festen Zeitpunkten.
"""

from datetime import datetime, timedelta

import pytest

from services.api.reap_logic import (
    classify_job,
    is_stale,
    MAX_STARTS,
    STALE_RUNNING_SECONDS,
)

# Fester Bezugszeitpunkt fuer alle Tests (deterministisch).
NOW = datetime(2026, 7, 1, 12, 0, 0)
FRESH = NOW - timedelta(seconds=10)                        # gerade erst gestartet
OLD = NOW - timedelta(seconds=STALE_RUNNING_SECONDS + 60)  # jenseits des Timeouts


# ---------------------------------------------------------------------------
# is_stale
# ---------------------------------------------------------------------------

def test_running_lebendig_und_frisch_ist_nicht_stale():
    assert is_stale('running', alive=True, started_at=FRESH, now=NOW) is False


def test_running_ohne_lebenden_rq_job_ist_stale():
    assert is_stale('running', alive=False, started_at=FRESH, now=NOW) is True


def test_running_zu_alt_ist_stale_trotz_lebendem_rq_job():
    assert is_stale('running', alive=True, started_at=OLD, now=NOW) is True


def test_running_ohne_started_at_und_lebendig_ist_nicht_stale():
    # Kein Timeout-Kriterium ohne started_at; lebendiger Job -> nicht stale.
    assert is_stale('running', alive=True, started_at=None, now=NOW) is False


def test_queued_lebendig_ist_nicht_stale():
    assert is_stale('queued', alive=True, started_at=None, now=NOW) is False


def test_queued_ohne_lebenden_rq_job_ist_stale():
    assert is_stale('queued', alive=False, started_at=None, now=NOW) is True


# ---------------------------------------------------------------------------
# classify_job
# ---------------------------------------------------------------------------

def test_gesunder_job_wird_uebersprungen():
    assert classify_job('running', True, FRESH, NOW, retry_count=0) == 'skip'


def test_verwaister_job_erster_neustart():
    # Original-Start (retry_count=0) verwaist -> Neustart erlaubt.
    assert classify_job('running', False, FRESH, NOW, retry_count=0) == 'retry'


def test_verwaister_job_zweiter_neustart():
    # Nach einem Neustart (retry_count=1) verwaist -> noch ein Neustart erlaubt.
    assert classify_job('queued', False, None, NOW, retry_count=1) == 'retry'


def test_verwaister_job_nach_drei_starts_failt():
    # retry_count=2 bedeutet: 3 Starts absolviert (Original + 2 Neustarts) -> fail.
    assert classify_job('running', False, OLD, NOW, retry_count=2) == 'fail'


def test_gesunder_job_failt_nicht_trotz_hohem_retry_count():
    # Ein gesunder Job wird nie angefasst, egal wie hoch retry_count ist.
    assert classify_job('running', True, FRESH, NOW, retry_count=2) == 'skip'


def test_genau_max_starts_grenze():
    # Sicherstellen, dass die Grenze bei MAX_STARTS liegt: der letzte erlaubte
    # Neustart ist bei retry_count = MAX_STARTS - 2, danach fail.
    assert classify_job('queued', False, None, NOW, retry_count=MAX_STARTS - 2) == 'retry'
    assert classify_job('queued', False, None, NOW, retry_count=MAX_STARTS - 1) == 'fail'

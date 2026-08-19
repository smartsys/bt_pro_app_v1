"""Tests der `metrics`-Parameter-Validierung an den beiden Run-Start-Endpunkten
(Anforderung 2).

Zwei Strategien, je nach Endpunkt:

- `/api/testset-runs` (api_testset_runs.py) importiert `rq` nur lazy innerhalb der
  Funktion — die Route-Funktion lässt sich direkt aufrufen (wie in
  test_testset_runs_api.py), ohne den laufenden Container zu brauchen.
- `/api/backtest/start` (api_backtest.py) importiert `rq` am Modulanfang; `rq` ist im
  lokalen Windows-venv nicht installiert (nur im API-Container). Diese Route wird
  deshalb über HTTP gegen den laufenden Container getestet (Muster aus
  test_strategy_results_columns.py) und übersprungen, wenn der Container nicht
  erreichbar ist.

Beide Wege belegen dasselbe Verhalten: ein unbekannter Gruppen-Key/Stufenname wird vor
jedem DB-Zugriff mit HTTP 400 abgelehnt.
"""

import json
import os

import pytest
import requests

from services.api.routes.api_testset_runs import TestSetRunIn, start_testset_run

# GEÄNDERT (Nachtrag): Adresse der laufenden App aus der Umgebung. Im
# Test-Container ist 'localhost' der Container selbst — dort gilt der Dienstname
# (http://app:8000), vom Host aus der gemappte Port.
BASE_URL = os.getenv('APP_BASE_URL', 'http://localhost:5570')


def _container_available() -> bool:
    try:
        r = requests.get(BASE_URL + '/api/strategy/concepts', timeout=3)
        return r.status_code == 200
    except Exception:
        return False


# ============================================================================
# /api/testset-runs — Route-Funktion direkt (kein rq-Import nötig)
# ============================================================================

def test_start_testset_run_rejects_unknown_metrics_group_before_any_db_access():
    """POST /api/testset-runs mit unbekanntem Gruppen-Key -> 400, kein DB-Zugriff.

    testset_id=0 würde ohne die Prüfung eine DB-Abfrage auslösen und mit
    einem 'nicht gefunden'-Fehler enden — die Prüfung muss also VOR dem ersten
    get_session()-Aufruf greifen.
    """
    payload = TestSetRunIn(
        testset_id=0,
        iteration_id=0,
        indicator_config_id=0,
        metrics=['gibtsnicht'],
    )
    result = start_testset_run(payload)
    assert result.status_code == 400
    body = json.loads(result.body)
    assert 'Unbekannte Metrik-Gruppe' in body['error']


def test_start_testset_run_rejects_unknown_metrics_stage_before_any_db_access():
    """Ebenso für eine unbekannte Stufe (Zeichenkette statt Liste)."""
    payload = TestSetRunIn(
        testset_id=0,
        iteration_id=0,
        indicator_config_id=0,
        metrics='mittel',
    )
    result = start_testset_run(payload)
    assert result.status_code == 400
    body = json.loads(result.body)
    assert 'Unbekannte Metrik-Auswahl' in body['error']


def test_start_testset_run_with_known_stage_passes_validation():
    """Ein gültiger Stufenname löst die Metrik-Prüfung nicht mehr aus — der Fehler
    danach ('TestSet nicht gefunden') beweist, dass die Route weitergelaufen ist."""
    payload = TestSetRunIn(
        testset_id=0,
        iteration_id=0,
        indicator_config_id=0,
        metrics='kern',
    )
    result = start_testset_run(payload)
    assert result.status_code == 400
    body = json.loads(result.body)
    assert 'Metrik' not in body['error']
    assert 'nicht gefunden' in body['error'].lower()


# ============================================================================
# /api/backtest/start — HTTP gegen den laufenden Container (rq nicht im lokalen venv)
# ============================================================================

@pytest.mark.integration  # spricht mit der laufenden App auf der Arbeits-DB
@pytest.mark.skipif(not _container_available(), reason=f'App nicht erreichbar ({BASE_URL})')
def test_backtest_start_rejects_unknown_metrics_group_via_http():
    """POST /api/backtest/start mit unbekanntem Gruppen-Key -> 400 über den echten Endpunkt."""
    r = requests.post(f'{BASE_URL}/api/backtest/start', json={
        'backtest_config_id': 1,
        'indicator_config_id': 1,
        'iteration_id': 1,
        'metrics': ['gibtsnicht'],
    }, timeout=10)
    assert r.status_code == 400, f'Erwarte 400, bekam {r.status_code}: {r.text}'
    assert 'Unbekannte Metrik-Gruppe' in r.json()['error']


@pytest.mark.integration  # spricht mit der laufenden App auf der Arbeits-DB
@pytest.mark.skipif(not _container_available(), reason=f'App nicht erreichbar ({BASE_URL})')
def test_backtest_start_rejects_unknown_metrics_stage_via_http():
    """POST /api/backtest/start mit unbekannter Stufe -> 400 über den echten Endpunkt."""
    r = requests.post(f'{BASE_URL}/api/backtest/start', json={
        'backtest_config_id': 1,
        'indicator_config_id': 1,
        'iteration_id': 1,
        'metrics': 'mittel',
    }, timeout=10)
    assert r.status_code == 400, f'Erwarte 400, bekam {r.status_code}: {r.text}'
    assert 'Unbekannte Metrik-Auswahl' in r.json()['error']

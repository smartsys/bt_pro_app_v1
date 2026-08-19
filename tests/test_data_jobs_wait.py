"""Tests für die --wait-Bilanz von data-update/data-download.

Prüft die geteilte Funktion `_data_jobs_wait` aus
`.claude/skills/ds-strategie-session/scripts/toolbox.py` sowie ihre Anbindung in
`data_update` und `data_download` — ohne Netzwerk-Zugriff: `fetch`/`post`/
`time.sleep`/`time.monotonic` werden gemockt (gleiches Muster wie
tests/test_run_wait.py, da die Toolbox ein stdlib-only CLI-Skript ist).
"""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_TOOLBOX_PATH = (
    Path(__file__).resolve().parent.parent
    / ".claude" / "skills" / "ds-strategie-session" / "scripts" / "toolbox.py"
)


def _load_toolbox():
    """Lädt toolbox.py als Modul (Ordnername enthält Bindestriche -> kein Package-Import)."""
    spec = importlib.util.spec_from_file_location("toolbox", _TOOLBOX_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["toolbox"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def toolbox():
    return _load_toolbox()


_CREATED = [
    {"id": 1, "symbol": "BTCUSDT", "rq_job_id": "rq-1"},
    {"id": 2, "symbol": "ETHUSDT", "rq_job_id": "rq-2"},
]


def test_data_jobs_wait_alle_erfolgreich_gibt_null_zurueck(toolbox, capsys):
    """Beide Jobs 'completed': Bilanz nennt 2 gesamt/2 erfolgreich/0 fehlgeschlagen, rc 0."""
    jobs = {
        1: {"id": 1, "status": "completed", "message": "Update abgeschlossen"},
        2: {"id": 2, "status": "completed", "message": "Update abgeschlossen"},
    }

    def fake_fetch(path, timeout=None):
        assert "/api/config/data/jobs" in path
        return {"data": {"items": list(jobs.values())}}

    with patch.object(toolbox, "fetch", side_effect=fake_fetch), \
         patch("time.sleep"):
        rc = toolbox._data_jobs_wait(_CREATED, timeout=60)

    assert rc == 0
    out = capsys.readouterr().out
    assert "2 gesamt, 2 erfolgreich, 0 fehlgeschlagen" in out


def test_data_jobs_wait_fehlschlag_erscheint_namentlich_mit_grund(toolbox, capsys):
    """Ein 'failed' Job: Bilanz nennt genau dieses Symbol mit seinem Grund, rc 1."""
    jobs = {
        1: {"id": 1, "status": "completed", "message": "Update abgeschlossen"},
        2: {"id": 2, "status": "failed", "message": "ETHUSDT: nicht in Datei"},
    }

    def fake_fetch(path, timeout=None):
        return {"data": {"items": list(jobs.values())}}

    with patch.object(toolbox, "fetch", side_effect=fake_fetch), \
         patch("time.sleep"):
        rc = toolbox._data_jobs_wait(_CREATED, timeout=60)

    assert rc == 1
    out = capsys.readouterr().out
    assert "2 gesamt, 1 erfolgreich, 1 fehlgeschlagen" in out
    assert "ETHUSDT" in out
    assert "nicht in Datei" in out


def test_data_jobs_wait_timeout_meldet_noch_offene_symbole(toolbox, capsys):
    """Bleiben Jobs dauerhaft 'running': TIMEOUT (rc=2), offene Symbole werden genannt."""
    jobs = {
        1: {"id": 1, "status": "completed", "message": "OK"},
        2: {"id": 2, "status": "running", "message": None},
    }

    def fake_fetch(path, timeout=None):
        return {"data": {"items": list(jobs.values())}}

    # time.monotonic(): t0=0, erste Prüfung 0 (kein Timeout bei --timeout 5), zweite 200 (> 5).
    with patch.object(toolbox, "fetch", side_effect=fake_fetch), \
         patch("time.sleep"), \
         patch("time.monotonic", side_effect=[0, 0, 200, 200]):
        rc = toolbox._data_jobs_wait(_CREATED, timeout=5)

    assert rc == 2
    out = capsys.readouterr().out
    assert "TIMEOUT" in out
    assert "ETHUSDT" in out


def test_data_update_ohne_wait_bleibt_asynchron(toolbox, capsys):
    """Ohne --wait: nur die Anlege-Antwort wird gedruckt, kein Polling (fetch bleibt ungenutzt)."""
    with patch.object(toolbox, "post", return_value={"data": {"id": 1, "jobs": _CREATED}}) as post_mock, \
         patch.object(toolbox, "fetch") as fetch_mock:
        rc = toolbox.data_update(["--timeframe", "4h"])

    assert rc == 0
    post_mock.assert_called_once()
    fetch_mock.assert_not_called()
    out = capsys.readouterr().out
    assert "2 Job(s) angelegt" in out


def test_data_update_mit_wait_ruft_die_geteilte_bilanz_ab(toolbox, capsys):
    """--wait bei data-update pollt und druckt die Bilanz."""
    jobs = {
        1: {"id": 1, "status": "completed", "message": "OK"},
        2: {"id": 2, "status": "completed", "message": "OK"},
    }

    with patch.object(toolbox, "post", return_value={"data": {"id": 1, "jobs": _CREATED}}), \
         patch.object(toolbox, "fetch", side_effect=lambda path, timeout=None: {"data": {"items": list(jobs.values())}}), \
         patch("time.sleep"):
        rc = toolbox.data_update(["--timeframe", "4h", "--wait"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "2 gesamt, 2 erfolgreich, 0 fehlgeschlagen" in out


def test_data_download_teilt_dieselbe_bilanz_funktion_wie_data_update(toolbox, capsys, tmp_path):
    """data-download --wait liefert dieselbe Bilanz-Ausgabe wie data-update --wait
    (Code-Beleg für die geteilte Funktion, nicht nur gleiches Verhalten per Zufall)."""
    payload_file = tmp_path / "download.json"
    payload_file.write_text(json.dumps({
        "exchange": "binance", "timeframe": "4h", "symbols": ["BTCUSDT", "ETHUSDT"],
    }), encoding="utf-8")

    jobs = {
        1: {"id": 1, "status": "completed", "message": "OK"},
        2: {"id": 2, "status": "failed", "message": "SYMBOLXYZ: ungültiges Symbol"},
    }
    created = [
        {"id": 1, "symbol": "BTCUSDT", "rq_job_id": "rq-1"},
        {"id": 2, "symbol": "SYMBOLXYZ", "rq_job_id": "rq-2"},
    ]

    with patch.object(toolbox, "post", return_value={"data": {"id": 1, "jobs": created}}), \
         patch.object(toolbox, "fetch", side_effect=lambda path, timeout=None: {"data": {"items": list(jobs.values())}}), \
         patch("time.sleep"):
        rc = toolbox.data_download(["--file", str(payload_file), "--wait"])

    assert rc == 1
    out = capsys.readouterr().out
    assert "SYMBOLXYZ" in out
    assert "ungültiges Symbol" in out
    # Beweis, dass beide Verben denselben Bilanz-Codepfad nutzen (keine Kopie): der
    # Bytecode beider Handler referenziert dieselbe Funktion `_data_jobs_wait`.
    assert "_data_jobs_wait" in toolbox.data_update.__code__.co_names
    assert "_data_jobs_wait" in toolbox.data_download.__code__.co_names

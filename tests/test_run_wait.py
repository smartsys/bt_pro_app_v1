"""Tests für das aktive Warten auf ein Lauf-Ende (Ticket 60, Anforderung 6).

Prüft die reine Funktion `run_wait` aus
`.claude/skills/ds-strategie-session/scripts/toolbox.py` — ohne Netzwerk-Zugriff:
`fetch`/`time.sleep`/`time.monotonic` werden gemockt, da die Toolbox ein
stdlib-only CLI-Skript ist (keine DB, kein echter HTTP-Call in Unit-Tests).
"""

import importlib.util
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


def test_run_wait_ohne_selektor_wirft_value_error(toolbox):
    """Weder --run noch --testset-run angegeben: klarer Fehler statt stillem Nichtstun."""
    with pytest.raises(ValueError):
        toolbox.run_wait([])


def test_run_wait_erfolgreicher_run_meldet_dauer_und_results(toolbox, capsys):
    """Ein sofort 'completed' gemeldeter Run: Status, Dauer und Result-Zahl in der Ausgabe."""
    run_row = {
        "id": 1812, "status": "completed",
        "started_at": "2026-08-13T10:00:00", "completed_at": "2026-08-13T10:01:30",
        "error_message": None,
    }

    # GEÄNDERT: Ticket 70/C — --run pollt über den Einzel-GET (/runs/{id}, Antwort
    # ist das Run-Objekt direkt), nicht mehr über die Liste (items-Wrapper).
    def fake_fetch(path, timeout=None):
        if "results?limit=1" in path:
            return {"data": {"total": 25}}
        return {"data": run_row}

    with patch.object(toolbox, "fetch", side_effect=fake_fetch), \
         patch("time.sleep"):
        rc = toolbox.run_wait(["--run", "1812", "--timeout", "60"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "run:1812" in out
    assert "completed" in out
    assert "90.0s" in out, f"Dauer (10:00:00 -> 10:01:30 = 90s) fehlt in: {out}"
    assert "25 Results" in out


def test_run_wait_fehlgeschlagener_run_meldet_fehlermeldung(toolbox, capsys):
    """Ein 'failed' gemeldeter Run: Fehlermeldung erscheint in der Ausgabe, rc bleibt 0
    (run-wait selbst hat sein Ziel erreicht — den Endzustand zu berichten)."""
    run_row = {
        "id": 500, "status": "failed",
        "started_at": "2026-08-13T10:00:00", "completed_at": "2026-08-13T10:00:01",
        "error_message": "OHLC-Daten laden fehlgeschlagen: No object named ZZZ in the file",
    }

    # GEÄNDERT: Ticket 70/C — --run pollt über den Einzel-GET (/runs/{id}, Antwort
    # ist das Run-Objekt direkt), nicht mehr über die Liste (items-Wrapper).
    def fake_fetch(path, timeout=None):
        if "results?limit=1" in path:
            return {"data": {"total": 0}}
        return {"data": run_row}

    with patch.object(toolbox, "fetch", side_effect=fake_fetch), \
         patch("time.sleep"):
        rc = toolbox.run_wait(["--run", "500", "--timeout", "60"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "failed" in out
    assert "ZZZ" in out
    assert "0 Results" in out


def test_run_wait_timeout_wird_als_timeout_gemeldet_nicht_als_fehlschlag(toolbox, capsys):
    """Bleibt ein Run dauerhaft 'running', meldet run-wait TIMEOUT (rc=2) — nicht 'failed'."""
    run_row = {"id": 999, "status": "running", "started_at": None, "completed_at": None, "error_message": None}

    # time.monotonic(): t0=0, erste Schleifenprüfung 0 (noch kein Timeout bei --timeout 5),
    # zweite Schleifenprüfung 200 (> 5 -> Timeout).
    # GEÄNDERT: Ticket 70/C — --run pollt über den Einzel-GET, Antwort ist das
    # Run-Objekt direkt (kein items-Wrapper).
    with patch.object(toolbox, "fetch", return_value={"data": run_row}), \
         patch("time.sleep"), \
         patch("time.monotonic", side_effect=[0, 0, 200, 200]):
        rc = toolbox.run_wait(["--run", "999", "--timeout", "5"])

    assert rc == 2, "Timeout muss einen eigenen Rückgabecode haben (kein Fehlschlag der Runs)"
    out = capsys.readouterr().out
    assert "TIMEOUT" in out
    assert "failed" not in out.lower()


def test_run_wait_testset_run_ohne_treffer_meldet_das(toolbox, capsys):
    """--testset-run ohne zugehörige Runs: klare Meldung statt leerer Erfolgsmeldung."""
    with patch.object(toolbox, "fetch", return_value={"data": {"items": []}}):
        rc = toolbox.run_wait(["--testset-run", "42"])

    assert rc == 1
    out = capsys.readouterr().out
    assert "testset-run:42" in out
    assert "keine Runs" in out

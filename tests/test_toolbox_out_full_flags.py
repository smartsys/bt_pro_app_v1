"""Tests für `--out`/`--full` an den Lese-Verben (GET) der TABLE_VERBS-Tabelle (Ticket 73).

Prüft `_run_table_verb` aus
`.claude/skills/ds-strategie-session/scripts/toolbox.py` — ohne Netzwerk-Zugriff
(`request` wird gemockt), da die Toolbox ein stdlib-only CLI-Skript ist. Bisher gab es
`--out`/`--full` nur am generischen `api`-Verb; dieser Test belegt dieselbe Semantik an
den TABLE_VERBS-Lese-Verben (Kappung, volle Datei, gegenseitiger Ausschluss, kein Leck
in den Query-String).
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


@pytest.fixture
def isolated_out_dir(toolbox, tmp_path, monkeypatch):
    """Lenkt OUT_DIR auf ein Test-Verzeichnis um — nie den echten Temp-Ordner anfassen."""
    out_dir = tmp_path / "bt-toolbox-out"
    monkeypatch.setattr(toolbox, "OUT_DIR", out_dir)
    return out_dir


# Große Antwort (> 4000 Zeichen als JSON) — run-results liefert genau so eine Liste.
_LARGE_PAYLOAD = {
    "items": [
        {"result_id": i, "symbol": "BTCUSDT", "timeframe": "4h",
         "total_return_pct": float(i), "sharpe_ratio": 1.23, "profit_factor": 1.5,
         "win_rate_pct": 55.5, "total_trades": 42, "max_drawdown_pct": -12.3}
        for i in range(60)
    ],
    "total": 60,
}
_LARGE_RESPONSE = {"data": _LARGE_PAYLOAD, "error": None}


def test_get_verb_truncates_without_flag(toolbox, capsys):
    """Ohne Flag bleibt die bestehende 4000-Zeichen-Kappung von _print_data aktiv."""
    spec = toolbox.TABLE_VERBS["run-results"]
    with patch.object(toolbox, "request", return_value=_LARGE_RESPONSE):
        rc = toolbox._run_table_verb("run-results", spec, ["1812"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "gekürzt: 4000 von" in out
    assert "--full oder --out <datei>" in out


def test_get_verb_full_flag_prints_untruncated(toolbox, capsys):
    """--full druckt die vollständige, unverkürzte Antwort auf stdout."""
    spec = toolbox.TABLE_VERBS["run-results"]
    with patch.object(toolbox, "request", return_value=_LARGE_RESPONSE):
        rc = toolbox._run_table_verb("run-results", spec, ["1812", "--full"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "gekürzt" not in out
    full_json = json.dumps(_LARGE_PAYLOAD, ensure_ascii=False, indent=2)
    assert full_json in out


def test_get_verb_out_flag_writes_full_file(toolbox, capsys, isolated_out_dir):
    """--out schreibt die vollständige Antwort in eine Datei, Konsole nur Pfad + Zeichenzahl."""
    spec = toolbox.TABLE_VERBS["run-results"]
    with patch.object(toolbox, "request", return_value=_LARGE_RESPONSE):
        rc = toolbox._run_table_verb("run-results", spec, ["1812", "--out"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "gekürzt" not in out
    assert "vollständiges JSON geschrieben" in out

    written_files = list(isolated_out_dir.glob("*.json"))
    assert len(written_files) == 1
    content = written_files[0].read_text(encoding="utf-8")
    assert json.loads(content) == _LARGE_PAYLOAD
    assert str(written_files[0]) in out
    assert str(len(content)) in out


def test_out_and_full_together_raises(toolbox):
    """--out und --full zusammen sind ein Fehler (gleiche Formulierung wie beim api-Verb)."""
    spec = toolbox.TABLE_VERBS["run-results"]
    with patch.object(toolbox, "request", return_value=_LARGE_RESPONSE):
        with pytest.raises(ValueError, match="--out und --full schließen sich aus"):
            toolbox._run_table_verb("run-results", spec, ["1812", "--out", "--full"])


def test_out_flag_not_leaked_into_query_string(toolbox, isolated_out_dir):
    """--out darf bei use_query=True-Verben nicht als Query-Parameter landen."""
    spec = toolbox.TABLE_VERBS["run-results"]
    assert spec[4] is True  # use_query — sonst würde dieser Test nichts prüfen
    with patch.object(toolbox, "request", return_value=_LARGE_RESPONSE) as mock_request:
        toolbox._run_table_verb("run-results", spec, ["1812", "--out"])

    called_path = mock_request.call_args[0][1]
    assert "out=" not in called_path
    assert "full=" not in called_path


def test_full_flag_not_leaked_into_query_string(toolbox):
    """Gegenprobe mit --full statt --out — ebenfalls kein Query-Leck."""
    spec = toolbox.TABLE_VERBS["run-results"]
    with patch.object(toolbox, "request", return_value=_LARGE_RESPONSE) as mock_request:
        toolbox._run_table_verb("run-results", spec, ["1812", "--full"])

    called_path = mock_request.call_args[0][1]
    assert "out=" not in called_path
    assert "full=" not in called_path


def test_out_flag_on_write_verb_raises(toolbox):
    """--out/--full gibt es nur bei Lese-Verben (GET) — bei Schreib-Verben ein Fehler,
    kein stilles Verschlucken.

    GEÄNDERT: Ticket 89 — result-favorite ist kein TABLE_VERBS-Eintrag mehr (jetzt
    eigenes, idempotent setzendes SINGLE_VERB); indicator-config-generate-labels bleibt
    als Schreib-Verb-Beispiel in TABLE_VERBS.
    """
    spec = toolbox.TABLE_VERBS["indicator-config-generate-labels"]
    assert spec[0] != "GET"
    with pytest.raises(ValueError, match="--out/--full gibt es nur bei Lese-Verben"):
        toolbox._run_table_verb("indicator-config-generate-labels", spec, ["1", "--out"])

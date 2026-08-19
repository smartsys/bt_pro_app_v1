"""Tests für `--out`/`--full` an den `--json`-Verben aus `_maybe_json` (Ticket 77/C).

Fundfall (werkzeug-luecken.md, 14.08.2026): `result-list --run <id> --json --out
datei.json` schrieb keine Datei — `--out` wurde von `_maybe_json` schlicht ignoriert,
das JSON lief unabhängig von der Item-Zahl auf stdout. Bei großen Treffermengen ist
das dann nicht mehr sicher vollständig parsebar.

Prüft `_maybe_json` direkt sowie exemplarisch `result_list` aus
`.claude/skills/ds-strategie-session/scripts/toolbox.py` — ohne Netzwerk-Zugriff
(`fetch` wird gemockt), da die Toolbox ein stdlib-only CLI-Skript ist.
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


# > 4000 Zeichen als JSON (result-list-Item-Form) — der Fall aus dem Fundeintrag.
_MANY_RESULT_ITEMS = [
    {"id": i, "run_id": 608, "symbol": "BTCUSDT", "total_return_pct": float(i),
     "sharpe_ratio": 1.23, "max_drawdown_pct": -12.3, "profit_factor": 1.5,
     "win_rate_pct": 55.5, "total_trades": 42, "open_trades": 0}
    for i in range(120)
]
_LARGE_PAYLOAD = {"total": len(_MANY_RESULT_ITEMS), "items": _MANY_RESULT_ITEMS}


def test_maybe_json_without_out_keeps_full_json_on_stdout(toolbox, capsys):
    """Ohne --out bleibt das bisherige Verhalten: volles, parsebares JSON auf stdout."""
    flags = {"json": True}
    handled = toolbox._maybe_json(flags, _LARGE_PAYLOAD, "result-list")

    assert handled is True
    out = capsys.readouterr().out
    assert len(out) > 4000
    parsed = json.loads(out)
    assert parsed == _LARGE_PAYLOAD


def test_maybe_json_out_flag_writes_full_file(toolbox, capsys, isolated_out_dir):
    """--out schreibt das vollständige JSON in eine Datei, Konsole nur Pfad + Zeichenzahl."""
    flags = {"json": True, "out": True}
    handled = toolbox._maybe_json(flags, _LARGE_PAYLOAD, "result-list")

    assert handled is True
    out = capsys.readouterr().out
    assert "vollständiges JSON geschrieben" in out

    written_files = list(isolated_out_dir.glob("*.json"))
    assert len(written_files) == 1
    content = written_files[0].read_text(encoding="utf-8")
    assert len(content) > 4000
    parsed = json.loads(content)
    assert parsed == _LARGE_PAYLOAD
    assert len(parsed["items"]) == len(_MANY_RESULT_ITEMS)


def test_maybe_json_out_and_full_together_raises(toolbox):
    """--out und --full schließen sich aus (gleiche Formulierung wie beim api-Verb)."""
    flags = {"json": True, "out": True, "full": True}
    with pytest.raises(ValueError, match="--out und --full schließen sich aus"):
        toolbox._maybe_json(flags, _LARGE_PAYLOAD, "result-list")


def test_maybe_json_without_json_flag_is_a_noop(toolbox, capsys):
    """Ohne --json bleibt _maybe_json untätig — der Markdown-Pfad des Verbs übernimmt."""
    handled = toolbox._maybe_json({}, _LARGE_PAYLOAD, "result-list")
    assert handled is False
    assert capsys.readouterr().out == ""


def test_result_list_json_out_writes_full_file_readable_via_json_load(toolbox, capsys, isolated_out_dir):
    """Abnahmefall wörtlich: result-list --run <id> --json --out x.json erzeugt eine
    Datei, die per json.load vollständig lesbar ist und alle Items enthält (>4000
    Zeichen im Testfall)."""
    with patch.object(toolbox, "fetch", return_value={"data": {"items": _MANY_RESULT_ITEMS}}):
        rc = toolbox.result_list(["--run", "608", "--json", "--out", "x.json"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "vollständiges JSON geschrieben" in out

    written = isolated_out_dir / "x.json"
    assert written.is_file()
    with open(written, "r", encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert loaded["total"] == len(_MANY_RESULT_ITEMS)
    assert len(loaded["items"]) == len(_MANY_RESULT_ITEMS)
    assert len(written.read_text(encoding="utf-8")) > 4000


def test_result_list_out_and_full_together_raises(toolbox):
    """Gegenseitiger Ausschluss --out/--full greift auch über den Verb-Aufruf."""
    with patch.object(toolbox, "fetch", return_value={"data": {"items": []}}):
        with pytest.raises(ValueError, match="--out und --full schließen sich aus"):
            toolbox.result_list(["--run", "608", "--json", "--out", "--full"])


def test_result_list_without_out_keeps_stdout_behavior(toolbox, capsys):
    """Ohne --out bleibt das bisherige stdout-Verhalten (Ticket 77/C, Testanforderung)."""
    with patch.object(toolbox, "fetch", return_value={"data": {"items": _MANY_RESULT_ITEMS}}):
        rc = toolbox.result_list(["--run", "608", "--json"])

    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert len(parsed["items"]) == len(_MANY_RESULT_ITEMS)


def test_run_top_results_out_flag_now_reaches_maybe_json(toolbox, capsys, isolated_out_dir):
    """Regression: run-top-results/run-best bauten flags früher manuell als {'json': ..}
    und verschluckten --out dabei stillschweigend (Ticket 77/C betrifft auch diese
    beiden, da sie über _strip_json_flag liefen statt über _parse_flags)."""
    response = {"results": _MANY_RESULT_ITEMS}
    with patch.object(toolbox, "fetch", return_value=response):
        rc = toolbox.run_top_results(["1812", "sharpe_ratio", "20", "desc", "--json", "--out"])

    assert rc == 0
    written_files = list(isolated_out_dir.glob("*.json"))
    assert len(written_files) == 1
    parsed = json.loads(written_files[0].read_text(encoding="utf-8"))
    assert len(parsed["items"]) == len(_MANY_RESULT_ITEMS)

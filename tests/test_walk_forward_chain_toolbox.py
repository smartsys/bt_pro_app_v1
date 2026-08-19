"""Tests der Toolbox-Verben zur Walk-Forward-Fold-Kette (Anforderung 3).

Geprüft werden `walk_forward_chain_start`, `walk_forward_chain_read`,
`walk_forward_chain_list` und die Ausgabe-Helfer aus
`.claude/skills/ds-strategie-session/scripts/toolbox.py` — ohne Netzwerk-Zugriff
(`fetch`/`post`/`run_wait` werden ersetzt), da die Toolbox ein stdlib-only
CLI-Skript ist. Die Server-Logik steht in tests/test_walk_forward_chain_api.py.

Kernregeln der Ausgabe: **das Aggregat erscheint nie ohne seine Fold-Tabelle**,
je Fold steht der IS-Wert **neben** dem OOS-Wert, und die Toolbox rechnet die
Aggregation **nicht nach** — sie zeigt, was der Server gerechnet hat.

Kernregeln der Orchestrierung: Fold 1 rechnet nicht doppelt, wenn sein IS-Fenster
das Anker-Fenster ist; ein Fold ohne Sieger wird angehängt und die Kette läuft
weiter; ein abgebrochener Lauf schließt die Kette als `failed` mit Grund.
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


_PLAN = {
    "n_folds": 2,
    "is_months": None,
    "oos_months": 3,
    "warmup_days": 31,
    "selection_metric": "sharpe_ratio",
    "selection_direction": "max",
    "trade_floor": 20,
    "metrics_level": None,
    "anchor_window": {
        "start": "2020-01-01", "end": "2022-01-01",
        "ohlc_start": "2019-12-01", "ohlc_end": "2022-01-01",
    },
    "folds": [
        {
            "fold_index": 1,
            "is_window": {"start": "2020-01-01", "end": "2022-01-01"},
            "oos_window": {"start": "2022-01-01", "end": "2022-04-01"},
        },
        {
            "fold_index": 2,
            "is_window": {"start": "2020-03-31", "end": "2022-04-01"},
            "oos_window": {"start": "2022-04-01", "end": "2022-07-01"},
        },
    ],
    "required_span": {"ohlc_start": "2019-12-01", "end": "2022-07-01"},
}


def _winner(result_id: int, value: float) -> dict:
    """Baut einen Sieger-Block, wie ihn die oos-run-Route liefert."""
    return {
        "result_id": result_id,
        "run_id": 618,
        "actual_params": {"vwma_length": 20, "atr_mult": 2.5},
        "resolved_config": {"vwma": {"length": 20}},
        "full_config_snapshot": {"indicators": {}},
        "selection_metric": "sharpe_ratio",
        "selection_value": value,
        "is_metrics": {"sharpe_ratio": value, "total_trades": 176},
    }


def _fold_block(fold_index: int, is_value=None, oos_value=None, reason=None) -> dict:
    """Baut einen angehängten Fold-Block, wie ihn die API zurückgibt."""
    planned = _PLAN["folds"][fold_index - 1]
    if reason is not None:
        return {
            "fold_index": fold_index, "is_window": planned["is_window"],
            "is_run_id": 618, "winner": None, "no_winner_reason": reason,
            "oos_window": None, "oos_run_id": None, "oos_result_id": None,
            "oos_metrics": None, "ann_factor": None,
        }
    return {
        "fold_index": fold_index,
        "is_window": planned["is_window"],
        "is_run_id": 618,
        "winner": _winner(7924049, is_value),
        "no_winner_reason": None,
        "oos_window": planned["oos_window"],
        "oos_run_id": 662,
        "oos_result_id": 7924128,
        "oos_metrics": {
            "sharpe_ratio": oos_value, "total_return_pct": -9.24, "total_trades": 12,
        },
        "ann_factor": 2190.0,
    }


_AGGREGATE = {
    "total_return_pct": -78.39, "sharpe_ratio": -0.9705, "max_drawdown_pct": -85.68,
    "bar_count": 1635, "ann_factor": 2190.0, "profit_factor": 1.42,
    "total_trades": 24, "closed_trades": 21, "open_trades": 3,
    "gross_profit": 100.0, "gross_loss": 70.0, "selection_metric": "sharpe_ratio",
    "folds_total": 2, "folds_with_winner": 2, "folds_without_winner": 0,
    "folds_in_curve": 2, "profitable_folds": 1, "profitable_folds_pct": 50.0,
    "degradation": [], "notes": [],
}


def _chain(folds=None, aggregate=None, status="completed") -> dict:
    """Baut eine serialisierte Kette, wie sie die API liefert."""
    return {
        "id": 2, "anchor_run_id": 618, "iteration_id": 20, "concept_id": 10,
        "config_snapshot_json": {
            "symbol": "FETUSDT", "exchange": "binance", "timeframe": "4h",
        },
        "plan_json": _PLAN,
        "folds_json": folds if folds is not None else [
            _fold_block(1, is_value=1.1361, oos_value=0.4461),
            _fold_block(2, is_value=1.4269, oos_value=-4.0502),
        ],
        "aggregate_json": aggregate if aggregate is not None else _AGGREGATE,
        "method_note": "Die Gesamtbewertung entsteht aus den balkengenauen Kapitalkurven "
                       "der Testfenster-Läufe. Kein Signal-Splice. Kein Verdict.",
        "status": status, "error_message": None,
        "created_at": "2026-08-15T11:46:43", "completed_at": "2026-08-15T11:52:40",
    }


# ---------------------------------------------------------------------------
# Ausgabe: Aggregat nie ohne Fold-Tabelle, IS-Wert neben OOS-Wert
# ---------------------------------------------------------------------------

def test_fold_row_shows_the_is_value_next_to_the_oos_value(toolbox, capsys):
    """Je Fold stehen IS- und OOS-Wert des Kriteriums in derselben Zeile."""
    toolbox._print_walk_forward_chain(_chain())
    out = capsys.readouterr().out

    header = next(line for line in out.splitlines() if line.startswith("| Fold | IS-Fenster |"))
    assert "IS-sharpe_ratio" in header
    assert "OOS-sharpe_ratio" in header
    assert header.index("IS-sharpe_ratio") < header.index("OOS-sharpe_ratio")

    row = next(line for line in out.splitlines() if line.startswith("| 1 |") and "result" in line)
    assert "1.1361" in row, "IS-Wert steht in der Zeile"
    assert "0.4461" in row, "OOS-Wert steht in derselben Zeile"


def test_aggregate_never_appears_before_the_fold_table(toolbox, capsys):
    """Die Fold-Tabelle steht immer vor dem Gesamtblock."""
    toolbox._print_walk_forward_chain(_chain())
    out = capsys.readouterr().out
    assert out.index("### Folds") < out.index("### Gesamt")
    assert "-78.39" in out


def test_chain_without_folds_shows_no_aggregate_at_all(toolbox, capsys):
    """Ohne Fold-Blöcke wird auch kein Aggregat ausgegeben — es wäre nicht einordbar."""
    toolbox._print_walk_forward_chain(_chain(folds=[], aggregate=_AGGREGATE))
    out = capsys.readouterr().out
    assert "keine Fold-Blöcke vorhanden" in out
    assert "### Gesamt" not in out
    assert "-78.39" not in out, "kein Aggregat ohne seine Fold-Tabelle"
    assert "Methodenhinweis" in out


def test_output_carries_the_method_note_and_the_criterion(toolbox, capsys):
    """Methodenhinweis und vorregistriertes Kriterium erscheinen in der Ausgabe."""
    toolbox._print_walk_forward_chain(_chain())
    out = capsys.readouterr().out
    assert "Kein Signal-Splice" in out
    assert "**sharpe_ratio** (max)" in out
    assert "Trade-Floor 20" in out


def test_output_contains_no_verdict_wording(toolbox, capsys):
    """Kein Bestanden-/Urteils-Vokabular — die Kette misst, sie urteilt nicht."""
    toolbox._print_walk_forward_chain(_chain())
    out = capsys.readouterr().out.lower()
    for forbidden in ("bestanden", "passed", "ampel", "score"):
        assert forbidden not in out
    # 'Verdict' kommt genau einmal vor: im Methodenhinweis, der seine Abwesenheit feststellt.
    assert "kein verdict" in out


def test_fold_without_winner_is_shown_with_its_reason(toolbox, capsys):
    """Ein Fold ohne Sieger erscheint samt Grund statt weggefiltert zu werden."""
    folds = [
        _fold_block(1, reason="Kein Kandidat erfüllt den Trade-Floor (999999 Trades)."),
        _fold_block(2, is_value=1.4269, oos_value=-4.0502),
    ]
    toolbox._print_walk_forward_chain(_chain(folds=folds))
    out = capsys.readouterr().out
    assert "kein Sieger" in out
    assert "999999" in out
    assert "entfällt" in out, "das Testfenster entfällt sichtbar"


def test_toolbox_shows_the_server_aggregate_verbatim(toolbox, capsys):
    """Die Toolbox rechnet nichts nach: sie zeigt genau die Server-Zahlen.

    Belegt mit einem Aggregat, das zu den Fold-Werten bewusst nicht passt — eine
    zweite Rechnung in der Toolbox würde hier andere Zahlen ausgeben.
    """
    aggregate = {**_AGGREGATE, "total_return_pct": 12345.67, "bar_count": 7}
    toolbox._print_walk_forward_chain(_chain(aggregate=aggregate))
    out = capsys.readouterr().out
    assert "12345.67 %" in out
    assert "Balken: 7" in out


# ---------------------------------------------------------------------------
# walk-forward-chain-start — Orchestrierung
# ---------------------------------------------------------------------------

class _ChainServer:
    """Minimaler Server-Doppelgänger für die Ketten-Endpunkte.

    Hält die angehängten Folds fest, damit die Tests prüfen können, was die
    Orchestrierung geschickt hat — und ob sie die Kette am Ende schließt.
    """

    def __init__(self, plan=None, winners=None, run_status="completed"):
        self.plan = plan or _PLAN
        self.winners = winners if winners is not None else {1: 1.1361, 2: 1.4269}
        self.run_status = run_status
        self.calls = []
        self.appended = []
        self.closed_with = "nicht geschlossen"
        self.next_run_id = 700

    def post(self, path, body=None, timeout=None):
        self.calls.append((path, body))
        if path.endswith("/close"):
            self.closed_with = (body or {}).get("error_message")
            return {"data": _chain(folds=self.appended)}
        if path.endswith("/folds"):
            self.appended.append(body)
            return {"data": {"chain_id": 2, "fold_index": body["fold_index"],
                             "folds_total": len(self.appended), "chain": {}}}
        if path.endswith("/is-run"):
            self.next_run_id += 1
            fold = self.plan["folds"][body["fold_index"] - 1]
            return {"data": {"chain_id": 2, "fold_index": body["fold_index"],
                             "run_id": self.next_run_id, "window": fold["is_window"]}}
        if path.endswith("/oos-run"):
            fold_index = body["fold_index"]
            fold = self.plan["folds"][fold_index - 1]
            value = self.winners.get(fold_index)
            if value is None:
                return {"data": {
                    "chain_id": 2, "fold_index": fold_index, "is_run_id": body["is_run_id"],
                    "winner": None, "no_winner_reason": "Kein Kandidat über dem Trade-Floor.",
                    "oos_run_id": None, "oos_window": fold["oos_window"],
                }}
            self.next_run_id += 1
            return {"data": {
                "chain_id": 2, "fold_index": fold_index, "is_run_id": body["is_run_id"],
                "winner": _winner(7924049, value), "no_winner_reason": None,
                "oos_run_id": self.next_run_id, "oos_window": fold["oos_window"],
            }}
        # Kette anlegen
        return {"data": {"chain_id": 2, "chain": _chain(folds=[], aggregate=None,
                                                        status="running")}}

    def fetch(self, path, timeout=None):
        if "/chart-data" in path:
            return {"equity": [{"time": 1, "value": 100.0}], "indicators": {}}
        if path.endswith("/results?limit=1"):
            return {"data": {"items": [{"id": 7924128}], "total": 1}}
        return {"data": {"id": 1, "status": self.run_status, "error_message": "Motor-Fehler"}}


def _run_chain(toolbox, server, args, run_wait_code=0):
    """Fährt walk_forward_chain_start gegen den Server-Doppelgänger."""
    with patch.object(toolbox, "post", server.post), \
         patch.object(toolbox, "fetch", server.fetch), \
         patch.object(toolbox, "run_wait", lambda _a: run_wait_code):
        return toolbox.walk_forward_chain_start(args)


_ARGS = ["--run", "618", "--folds", "2", "--oos-monate", "3",
         "--selection-metric", "sharpe_ratio", "--trade-floor", "20"]


def test_start_sends_the_full_preregistration_in_one_call(toolbox, capsys):
    """Fold-Zahl, Fensterlängen und Kriterium gehen in einem Aufruf raus."""
    server = _ChainServer()
    rc = _run_chain(toolbox, server, _ARGS + ["--is-monate", "12", "--metrics", "kern"])
    capsys.readouterr()
    assert rc == 0
    path, body = server.calls[0]
    assert path == "/api/backtest/walk-forward-chains"
    assert body == {
        "anchor_run_id": 618, "folds": 2, "oos_months": 3,
        "selection_metric": "sharpe_ratio", "selection_direction": "max",
        "trade_floor": 20, "is_months": 12, "metrics": "kern",
    }


def test_start_defaults_direction_to_max_and_floor_to_zero(toolbox, capsys):
    """Ohne Angabe gilt Richtung 'max' und Trade-Floor 0 — der Server bekommt beides explizit."""
    server = _ChainServer()
    _run_chain(toolbox, server, ["--run", "618", "--folds", "2", "--oos-monate", "3",
                                 "--selection-metric", "sharpe_ratio"])
    capsys.readouterr()
    body = server.calls[0][1]
    assert body["selection_direction"] == "max"
    assert body["trade_floor"] == 0
    assert "is_months" not in body


def test_start_requires_run_folds_metric_and_oos_length(toolbox):
    """Fehlt eine Pflichtangabe, bricht das Verb ab, bevor etwas angelegt wird."""
    for missing, args in (
        ("--run", ["--folds", "2", "--oos-monate", "3", "--selection-metric", "x"]),
        ("--folds", ["--run", "1", "--oos-monate", "3", "--selection-metric", "x"]),
        ("--oos-monate", ["--run", "1", "--folds", "2", "--selection-metric", "x"]),
        ("--selection-metric", ["--run", "1", "--folds", "2", "--oos-monate", "3"]),
    ):
        with pytest.raises(ValueError, match=missing):
            toolbox.walk_forward_chain_start(args)


def test_fold_one_reuses_the_anchor_run_instead_of_computing_it_again(toolbox, capsys):
    """Ist das IS-Fenster von Fold 1 das Anker-Fenster, wird kein zweiter IS-Lauf gestartet."""
    server = _ChainServer()
    rc = _run_chain(toolbox, server, _ARGS)
    out = capsys.readouterr().out
    assert rc == 0
    is_runs = [body["fold_index"] for path, body in server.calls if path.endswith("/is-run")]
    assert is_runs == [2], "nur Fold 2 braucht einen eigenen IS-Lauf"
    assert server.appended[0]["is_run_id"] == 618, "Fold 1 hängt am Anker-Lauf"
    assert "kein Doppelrechnen" in out


def test_own_is_run_when_the_plan_carries_its_own_is_length(toolbox, capsys):
    """Mit eigener IS-Länge weicht Fold 1 vom Anker-Fenster ab und bekommt einen IS-Lauf."""
    plan = json.loads(json.dumps(_PLAN))
    plan["is_months"] = 12
    plan["folds"][0]["is_window"] = {"start": "2021-01-01", "end": "2022-01-01"}
    server = _ChainServer(plan=plan)

    def _post(path, body=None, timeout=None):
        if path == "/api/backtest/walk-forward-chains":
            server.calls.append((path, body))
            return {"data": {"chain_id": 2,
                             "chain": {**_chain(folds=[], status="running"),
                                       "plan_json": plan, "aggregate_json": None}}}
        return _ChainServer.post(server, path, body, timeout)

    with patch.object(toolbox, "post", _post), \
         patch.object(toolbox, "fetch", server.fetch), \
         patch.object(toolbox, "run_wait", lambda _a: 0):
        rc = toolbox.walk_forward_chain_start(_ARGS + ["--is-monate", "12"])
    capsys.readouterr()
    assert rc == 0
    is_runs = [body["fold_index"] for path, body in server.calls if path.endswith("/is-run")]
    assert is_runs == [1, 2]


def test_fold_without_winner_is_appended_and_the_chain_continues(toolbox, capsys):
    """Kein Kandidat über dem Trade-Floor: Fold wird ausgewiesen, kein OOS-Lauf, kein Abbruch."""
    server = _ChainServer(winners={1: None, 2: 1.4269})
    rc = _run_chain(toolbox, server, _ARGS)
    out = capsys.readouterr().out
    assert rc == 0
    assert server.appended[0]["no_winner_reason"] == "Kein Kandidat über dem Trade-Floor."
    assert "oos_run_id" not in server.appended[0]
    assert len(server.appended) == 2, "die Kette läuft nach dem Fold ohne Sieger weiter"
    assert server.closed_with is None, "sauberer Abschluss, kein failed"
    assert "Kein Sieger" in out


def test_failed_run_closes_the_chain_as_failed_with_a_reason(toolbox, capsys):
    """Ein fehlgeschlagener Lauf schließt die Kette mit Grund — kein stilles Hängenbleiben."""
    server = _ChainServer(run_status="failed")
    rc = _run_chain(toolbox, server, _ARGS)
    out = capsys.readouterr().out
    assert rc == 1
    assert server.closed_with is not None
    assert "Motor-Fehler" in server.closed_with
    assert "Abbruch" in out


def test_timeout_closes_the_chain_and_exits_with_code_two(toolbox, capsys):
    """Der Timeout meldet sich als Timeout (Exit 2) und schließt die Kette trotzdem."""
    server = _ChainServer()
    rc = _run_chain(toolbox, server, _ARGS, run_wait_code=2)
    capsys.readouterr()
    assert rc == 2
    assert "Timeout" in (server.closed_with or "")


def test_start_recomputes_the_oos_curve_before_appending_the_fold(toolbox, capsys):
    """Vor dem Anhängen wird die Kapitalkurve nachgerechnet — Grundlage der Aggregation."""
    server = _ChainServer()
    seen = []
    original_fetch = server.fetch

    def _fetch(path, timeout=None):
        seen.append(path)
        return original_fetch(path, timeout)

    with patch.object(toolbox, "post", server.post), \
         patch.object(toolbox, "fetch", _fetch), \
         patch.object(toolbox, "run_wait", lambda _a: 0):
        rc = toolbox.walk_forward_chain_start(_ARGS)
    capsys.readouterr()
    assert rc == 0
    assert any("/chart-data" in path for path in seen)
    assert server.appended[0]["oos_result_id"] == 7924128


# ---------------------------------------------------------------------------
# walk-forward-chain / walk-forward-chain-list
# ---------------------------------------------------------------------------

def test_read_verb_fetches_by_id(toolbox, capsys):
    """`walk-forward-chain --id` liest genau diese Kette."""
    with patch.object(toolbox, "fetch", lambda path, timeout=None: {"data": _chain()}):
        rc = toolbox.walk_forward_chain_read(["--id", "2"])
    assert rc == 0
    assert "Walk-Forward-Kette 2" in capsys.readouterr().out


def test_read_verb_requires_id(toolbox):
    """Ohne --id bricht das Verb ab."""
    with pytest.raises(ValueError, match="--id"):
        toolbox.walk_forward_chain_read([])


def test_read_verb_supports_json_output(toolbox, capsys):
    """--json gibt die rohen Daten aus (für Folge-Analysen)."""
    with patch.object(toolbox, "fetch", lambda path, timeout=None: {"data": _chain()}):
        toolbox.walk_forward_chain_read(["--id", "2", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == 2


def test_list_keeps_server_order_and_shows_no_metrics(toolbox, capsys):
    """Die Historie bleibt chronologisch und zeigt keine Kennzahlen (keine Bestenliste)."""
    items = [{**_chain(), "id": 1}, {**_chain(), "id": 2}, {**_chain(), "id": 3}]
    with patch.object(toolbox, "fetch",
                      lambda path, timeout=None: {"data": {"items": items, "total": 3}}):
        rc = toolbox.walk_forward_chain_list([])
    assert rc == 0
    out = capsys.readouterr().out
    positions = [out.index(f"| {i} | 2026-08-15") for i in (1, 2, 3)]
    assert positions == sorted(positions)
    assert "chronologisch" in out
    assert "-78.39" not in out, "kein Aggregat ohne Fold-Tabelle"


def test_list_scopes_to_an_iteration(toolbox, capsys):
    """--iteration schränkt die Historie serverseitig ein."""
    seen = []

    def _fetch(path, timeout=None):
        seen.append(path)
        return {"data": {"items": [], "total": 0}}

    with patch.object(toolbox, "fetch", _fetch):
        rc = toolbox.walk_forward_chain_list(["--iteration", "20"])
    assert rc == 0
    assert seen == ["/api/walk-forward-chains?iteration_id=20"]
    assert "keine Ketten vorhanden" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Verdrahtung
# ---------------------------------------------------------------------------

def test_verbs_are_registered_and_documented(toolbox):
    """Die drei Verben sind aufrufbar und im --help-Docstring beschrieben."""
    for verb, handler in (
        ("walk-forward-chain-start", toolbox.walk_forward_chain_start),
        ("walk-forward-chain", toolbox.walk_forward_chain_read),
        ("walk-forward-chain-list", toolbox.walk_forward_chain_list),
    ):
        assert toolbox.SINGLE_VERBS[verb] is handler
        assert verb in toolbox.__doc__


def test_help_text_states_the_aggregate_rule(toolbox):
    """Der Docstring nennt die Regel, dass das Aggregat nie ohne Fold-Tabelle zitiert wird."""
    assert "NIE ohne seine Fold-Tabelle" in toolbox.__doc__
    assert "Messwerkzeug, kein Ertragsbringer" in toolbox.__doc__

#!/usr/bin/env python3
"""Objekt-Toolbox für bt_pro_app_v1.

Nimmt eine Liste aus URLs und/oder `<bereich>:<wert>`-Strings und druckt ein
kompaktes Markdown-Briefing der referenzierten Objekte. Spart pro LLM-Session
mehrere Einzel-Curls und deckt jede briefbare API-Route ab.

Namens-Konvention: Funktionen heißen `<bereich>_<aktion>` (z.B. `iteration_read`,
`backtest_config_copy`). Aktionen: read, list, create, copy, start. Keine Jargon-Begriffe.

Jede Maßnahme ist ein einzelnes Werkzeug, einzeln aufrufbar. Es gibt keine
vorgegebene Reihenfolge. Vollständige Werkzeug-Liste mit je einem Satz:
documentation/project/handbuch.md (Abschnitt "Toolbox-Werkzeuge").

Wichtig zum Leaderboard: Ein Testset-Lauf erzeugt NICHT automatisch einen Leaderboard-
Eintrag. Das passiert nur, wenn das Testset 'leaderboard_enabled=True' gesetzt hat
(Opt-in, Default False). Sinn: Viele Testsets dienen nur dem Testen über mehrere Symbole/
kurze Zeiträume; ins Leaderboard gehören bewusst nur wenige, über lange Zeiträume
vergleichbare Läufe. Ein leeres Leaderboard ist also KEIN Beleg dafür, dass kein
Testset-Lauf stattfand.

Beispiele (Lesen — Default, kein Verb):
  python3 toolbox.py http://localhost:5570/config/strategy-concepts/1/iterations/26/edit \\
                       http://localhost:5570/config/backtest/553 \\
                       http://localhost:5570/config/indicator/1970

  python3 toolbox.py iteration:26 indicator-config:1970 backtest-config:552 result:2635737 run:1753
  python3 toolbox.py concept:1 strategy-config:12 testset:4 leaderboard:88
  python3 toolbox.py knowledge:"teststrategie exit logik" vault:30_Trading/strategies

Kopieren (Schreib-Aktion — erzeugt neue Objekte, Originale bleiben unverändert):
  python3 toolbox.py copy iteration:2
  python3 toolbox.py copy backtest-config:553 indicator-config:1970
  Kopierbar: iteration, backtest-config, indicator-config.

IndicatorConfig aus Result erstellen (Schreib-Aktion):
  python3 toolbox.py create-indicator-config result:2706026:Sharpe
  python3 toolbox.py create-indicator-config result:2755455:Return result:2734638:PF
  Erstellt aus den Gewinner-Parametern eines Results eine Single-Point-IndicatorConfig
  (Range -> Skalar) nach Konvention `<KONZEPT> <version> / <Segment> / <ResultID>`.
  Segment ist optional (Return/Sharpe/PF/WinR90); Trenner ':' oder '/'.
  Nur Results sind als Quelle zulässig. Für die Vergleichsmessung via Testset.

Listen-Reads (kompaktes Markdown, eigene Verben):
  python3 toolbox.py concept-list
  python3 toolbox.py iteration-list 1            # optional: concept_id
  python3 toolbox.py backtest-config-list
  python3 toolbox.py indicator-config-list 1 41  # optional: concept_id iteration_id
  python3 toolbox.py result-list --run 1812 --limit 20   # optional: --symbol --timeframe
  python3 toolbox.py run-list --strategy vwma --version 1 # Runs zu Strategie+Version, nach Testset gruppiert
                                                          #   alt: --iteration <id> | --testset-run <id>
  python3 toolbox.py testset-list
  python3 toolbox.py leaderboard-list 293        # optional: testset_id
  python3 toolbox.py symbol-list binance 4h      # exchange timeframe (Pflicht)
  python3 toolbox.py run-parameter-ranking 1812 sharpe_ratio   # run_id [metric]
  python3 toolbox.py run-top-results 1812 sharpe_ratio 20 desc # run_id [metric] [limit] [direction]
  python3 toolbox.py run-best 1812 profit_factor 30 1         # run_id metrik [min_trades=30] [limit=1] — bester Metrik-Wert mit >= min_trades Trades
  python3 toolbox.py run-bestwerte --run 1812                 # vier feste Bestwerte je Run ziehen + als Doku-Favorit (roter Stern) markieren (idempotent)
                                                              #   mehrere Runs: --strategy vwma [--version 1] | --iteration <id> | --testset-run <id>
  python3 toolbox.py run-favorites-reset --testset-run 6      # Favoriten einer Run-Menge zuruecksetzen; ohne Flag beide Sterne, sonst --doc (rot) und/oder --user (gelb)
                                                              #   Selektoren wie run-bestwerte: --run | --strategy [--version] | --iteration | --testset-run
  python3 toolbox.py playground-indicators                    # Gruppen-Übersicht (Name + Anzahl), kein voller Dump
  python3 toolbox.py playground-indicators --group talib      # nur diese Gruppe, kompakt: id/inputs/params/outputs
  python3 toolbox.py playground-indicators --search ema       # case-insensitiv über id/name, --group kombinierbar

Anlegen (create — Schreib-Aktion). Komplexe Payloads per --file als JSON-Datei.
KEIN stiller Konverter, kein Fallback: spec_json/config_json wird unverändert
durchgereicht und scheitert beim Lauf laut, wenn falsch geformt.
  python3 toolbox.py concept-create --slug teststrategie --name "Teststrategie" [--category ... --description ... --status active]
  python3 toolbox.py iteration-create --concept 1 --file spec.json [--name "v5" --type generic --description ... --parent 41]
        --file = das spec_json (Flat-Dict indicators + DNF-rules). type=hardcoded braucht --import-path.
  python3 toolbox.py indicator-config-create --file config.json [--concept 1 --iteration 41 --name "..." --description ...]
        --file = das config_json (Parameter-Raster, arange je Indikator).
        Ohne --name: Standard-Titel (und Beschreibung) nach Notation über den Server (preview-labels).
        Mit --name: individueller Name, verbatim. --description überschreibt die Auto-Beschreibung.
  python3 toolbox.py backtest-config-create --file backtest.json
        --file = der volle Body (Pflicht: name, start, end, ohlc_start, ohlc_end; Defaults: symbol BTCUSDT, exchange binance, timeframe 4h, size 100, size_type value, init_cash 100, fees 0.001).
  python3 toolbox.py testset-create --name "OoS 22/23" --configs 552,553,554 [--description ...]

Ausführen (start — Schreib-Aktion, ID-basiert):
  python3 toolbox.py backtest-run-start --backtest-config 552 --indicator-config 1970 --iteration 41
  python3 toolbox.py testset-run-start --testset 293 --iteration 41 --indicator-config 1973
  python3 toolbox.py walk-forward-start --result 2706026 --months 6

Ändern (PUT, voller Body per --file): <bereich>-update --id <n> --file body.json
  concept-update · iteration-update · backtest-config-update · indicator-config-update ·
  strategy-config-update · testset-update · playground-setup-update

Löschen (DELETE): <bereich>-delete <id>   (concept/iteration zusätzlich: --force --delete_vault)
  concept-delete · iteration-delete · backtest-config-delete · indicator-config-delete ·
  strategy-config-delete · result-delete · run-delete · testset-delete · leaderboard-delete ·
  playground-setup-delete · knowledge-reset
  Sammellöschen: <bereich>-bulk-delete --ids 1,2,3 (indicator-config/result/run/playground-setup)
  Alle (außer Favoriten): result-delete-all · run-delete-all

Aktionen (POST): iteration-favorite/iteration-doc-favorite/result-favorite/result-doc-favorite <id> ·
  concept-vault-create/iteration-vault-create <id> · run-restart <id> · run-remarks <id> --text "..." ·
  result-full-metrics <id> · run-analyse-start/stop/reset <id>

Weitere Anlegen (POST, --file): strategy-config-create · data-download ·
  playground-setup-create/compute/run-backtest/run-backtest-lite · knowledge-reindex
  data-update --timeframe 4h · data-delete-symbol --timeframe 4h --symbol FETUSDT

Weitere Listen/Reads: strategy-config-list · data-files-list · data-jobs-list · filters-list ·
  run-results/run-summary/run-distribution/run-equity-overview/run-heatmap/run-analyse-progress <id> ·
  result-stats/result-trades/result-orders/result-positions/result-ohlcv/result-chart-data/result-metrics-level <id> ·
  knowledge-runs-list · knowledge-run <id> · knowledge-stats ·
  playground-sources/playground-ohlcv/playground-setup-list

Generischer Direktzugriff auf JEDE (auch künftige) Route:
  python3 toolbox.py api GET /api/backtest/runs
  python3 toolbox.py api POST /api/testsets --file body.json
  python3 toolbox.py api DELETE /api/backtest/runs/1234

Unterstützte Bereiche:
  ID-basiert:
    concept             — Strategie-Konzept
    iteration           — Iteration
    indicator-config    — Indicator-Config
    backtest-config     — Backtest-Config
    strategy-config     — Strategy-Config (hardcoded/generic, Legacy)
    result              — Backtest-Result (Stats)
    run                 — Backtest-Run (Listen-Filter, kein Einzel-GET)
    testset             — Testset
    leaderboard         — Leaderboard-Eintrag (Drilldown)
    playground-setup    — Chart-Playground-Setup
  String-basiert:
    knowledge           — semantische Vektorsuche im Vault-Index
    vault               — indizierte Vault-Dateien (Pfad-Substring)
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
import urllib.error

# Basis-URL des FastAPI-Backends. Default lokal; per Env VBT_APP_BASE_URL überschreibbar.
BASE = os.environ.get("VBT_APP_BASE_URL", "http://localhost:5570").rstrip("/")
TIMEOUT = 10
# Maximale Run-Liste, die für den Run-Filter geladen wird (kein Einzel-GET vorhanden)
RUN_LIST_LIMIT = 500

URL_PATTERNS = [
    (re.compile(r"/config/strategy-concepts/\d+/iterations/(\d+)"), "iteration"),
    (re.compile(r"/strategy/iterations/(\d+)"), "iteration"),
    (re.compile(r"/config/backtest/(\d+)"), "backtest-config"),
    (re.compile(r"/config/indicator/(\d+)"), "indicator-config"),
    (re.compile(r"/config/playground/(\d+)"), "playground-setup"),
    (re.compile(r"/backtest/results/(\d+)"), "result"),
    (re.compile(r"/backtest/runs/(\d+)"), "run"),
    (re.compile(r"/testsets/(\d+)"), "testset"),
]

# Gültige Bereiche (kanonisch, keine Kurz-Aliasse). Reihenfolge = Doku-Reihenfolge.
VALID_TYPES = {
    "concept",
    "iteration",
    "indicator-config",
    "backtest-config",
    "strategy-config",
    "result",
    "run",
    "testset",
    "leaderboard",
    "playground-setup",
    "knowledge",
    "vault",
}

# Bereiche, deren Wert ein String ist (Query/Pfad) statt einer Integer-ID
STRING_TYPES = {"knowledge", "vault"}


def parse_arg(arg: str):
    """Liefert (typ, wert) oder (None, None). wert ist int (ID-Typen) oder str (String-Typen)."""
    if arg.startswith("http"):
        for pat, t in URL_PATTERNS:
            m = pat.search(arg)
            if m:
                return t, int(m.group(1))
        return None, None
    if ":" in arg:
        t, val = arg.split(":", 1)
        t = t.lower()
        if t not in VALID_TYPES:
            return None, None
        if t in STRING_TYPES:
            return t, val.strip()
        if val.isdigit():
            return t, int(val)
    return None, None


def fetch(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=TIMEOUT) as r:
        return json.loads(r.read())


def post(path: str, body: dict = None) -> dict:
    """POST mit optionalem JSON-Body. Gibt die geparste Antwort zurück."""
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def request(method: str, path: str, body: dict = None) -> dict:
    """Beliebige HTTP-Methode mit optionalem JSON-Body. Leere Antwort -> {}."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method.upper(), headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def num(v, fmt: str = "{:.2f}", dash: str = "—") -> str:
    """None-sichere Zahlenformatierung."""
    return fmt.format(v) if isinstance(v, (int, float)) else dash


def fmt_cond(c: dict) -> str:
    lhs = c.get("lhs"); op = c.get("op"); rhs = c.get("rhs")
    lhs_s = c.get("lhs_shift", 0); rhs_s = c.get("rhs_shift", 0)
    parts = [str(lhs)]
    if lhs_s: parts.append(f".shift({lhs_s})")
    parts.append(f" {op} {rhs}")
    if rhs_s: parts.append(f" (rhs.shift({rhs_s}))")
    return "".join(parts)


def render_spec(spec: dict) -> None:
    """Druckt Indikatoren und Entry/Exit-Rules aus einem spec_json/strategy_config_json."""
    inds = spec.get("indicators", {})
    if inds:
        print("- Indikatoren:")
        for name, p in inds.items():
            params = ", ".join(f"{k}={v}" for k, v in p.items() if k not in ("enabled", "tf", "indicator"))
            # GEAENDERT: Ticket 48 — deaktivierte Indikatoren (enabled: false) markieren
            tag = "" if p.get("enabled", True) else " [deaktiviert]"
            print(f"  - **{name}** ({p.get('indicator')}){tag}: {params}")
    rules = spec.get("rules", {})
    # GEAENDERT: Ticket 48 — Block-Format (DNF) statt Alt-Format {logic, conditions};
    # Blöcke sind ODER-verknüpft, Short- und deaktivierte Blöcke (enabled: false) werden markiert.
    for kind in ("entry", "exit"):
        r = rules.get(kind) or {}
        blocks = r.get("blocks") or []
        if not blocks:
            continue
        print(f"- {kind.capitalize()}-Rules (Blöcke ODER-verknüpft):")
        for n, b in enumerate(blocks, 1):
            tags = []
            if b.get("is_short"):
                tags.append("SHORT")
            if not b.get("enabled", True):
                tags.append("deaktiviert")
            suffix = f" [{', '.join(tags)}]" if tags else ""
            conds = b.get("conditions", [])
            cond_txt = " UND ".join(fmt_cond(c) for c in conds) if conds else "(leer)"
            print(f"  - Block {n}{suffix}: `{cond_txt}`")


# ---------------------------------------------------------------------------
# Lese-Handler (read). Nehmen eine ID, rufen die passende API-Route und drucken
# ein eingedampftes Markdown-Briefing. Funktionsname: <bereich>_read.
# ---------------------------------------------------------------------------

def concept_read(i: int) -> None:
    d = fetch(f"/api/strategy/concepts/{i}")["data"]
    print(f"## Concept {i} — {d.get('name')} ({d.get('slug')})")
    print(f"- Status: {d.get('status')} · Kategorie: {d.get('category') or '—'} · Vault: {d.get('vault_exists')}")
    if d.get("description"):
        print(f"- {d['description']}")
    print()


def iteration_read(i: int) -> None:
    d = fetch(f"/api/strategy/iterations/{i}")["data"]
    name = d.get("version_name") or d.get("version")
    print(f"## Iteration {i} — {name}")
    print(f"- Concept-ID: {d.get('concept_id')} · Typ: {d.get('type')} · Status: {d.get('status')} · Vault: {d.get('vault_exists')}")
    if d.get("description"):
        print(f"- {d['description']}")
    render_spec(d.get("spec_json") or {})
    print()


def indicator_config_read(i: int) -> None:
    d = fetch(f"/api/config/indicator/{i}")["data"]
    print(f"## Indicator-Config {i} — {d.get('name')}")
    print(f"- Strategie: {d.get('strategy_concept_name')} · Iter: {d.get('strategy_iteration_version')} (id {d.get('strategy_iteration_id')})")
    if d.get("description"):
        print(f"- {d['description']}")
    for name, p in (d.get("config_json") or {}).items():
        params = ", ".join(f"{k}={v}" for k, v in p.items() if k not in ("enabled", "tf", "indicator"))
        # GEAENDERT: Ticket 48 — deaktivierte Indikatoren (enabled: false) markieren
        tag = "" if p.get("enabled", True) else " [deaktiviert]"
        print(f"  - **{name}** ({p.get('indicator')}){tag}: {params}")
    print()


def backtest_config_read(i: int) -> None:
    d = fetch(f"/api/config/backtest/{i}")["data"]
    print(f"## Backtest-Config {i} — {d.get('name')}")
    if d.get("description"):
        print(f"- {d['description']}")
    print(f"- {d['symbol']} {d['timeframe']} · {d['start']} → {d['end']} · exchange {d.get('exchange')}")
    print(f"- Sizing: {d['size']} {d['size_type']}, init_cash {d['init_cash']}, fees {d['fees']}")
    print(f"- Stops: td={d['td_stop']} tp={d['tp_stop']} sl={d['sl_stop']} tsl={d['tsl_stop']} (tsl_th={d['tsl_th']})")
    print()


def strategy_config_read(i: int) -> None:
    d = fetch(f"/api/config/strategy/{i}")["data"]
    print(f"## Strategy-Config {i} — {d.get('name')}")
    if d.get("description"):
        print(f"- {d['description']}")
    print(f"- Familie: {d.get('strategy_family')} · Name: {d.get('strategy_name')} · Typ: {d.get('type')}")
    if d.get("import_path"):
        print(f"- Import: `{d['import_path']}`")
    cfg = d.get("strategy_config_json")
    if cfg:
        render_spec(cfg)
    print()


def result_read(i: int) -> None:
    s = fetch(f"/api/backtest/results/{i}/stats")["stats"]
    print(f"## Result {i}")
    print(f"- Return: {num(s.get('Total Return [%]'))}% (Benchmark {num(s.get('Benchmark Return [%]'))}%)")
    print(f"- Sharpe {num(s.get('Sharpe Ratio'))} / Sortino {num(s.get('Sortino Ratio'))} / Calmar {num(s.get('Calmar Ratio'))}")
    print(f"- Max DD {num(s.get('Max Drawdown [%]'))}% (Dauer {s.get('Max Drawdown Duration')})")
    print(f"- Trades: {s.get('Total Trades')} · Win-Rate {num(s.get('Win Rate [%]'))}% · Profit-Factor {num(s.get('Profit Factor'))}")
    print(f"- Value: {s.get('Start Value')} → {num(s.get('End Value'))}")
    print()


def run_read(i: int) -> None:
    d = fetch(f"/api/backtest/runs?limit={RUN_LIST_LIMIT}")["data"]["items"]
    r = next((x for x in d if x.get("id") == i), None)
    if not r:
        print(f"## Run {i} — nicht in den letzten {RUN_LIST_LIMIT} Runs gefunden\n")
        return
    # Sprechendes Label: Strategie+Version statt nackter ID (strategy_family=Slug,
    # strategy_name=Versionsnummer). Testset-Zugehoerigkeit, falls der Run aus einem
    # TestSet-Lauf stammt.
    fam = (r.get("strategy_family") or "").upper()
    ver = r.get("strategy_name")
    label = f"{fam} v{ver}" if fam else f"Run {i}"
    print(f"## Run {i} — {label} · {r.get('symbol')} {r.get('timeframe')}")
    print(f"- Status: {r.get('status')} · {r.get('n_combinations')} Kombinationen")
    if r.get("testset_name"):
        ts = f"testset:{r.get('testset_id')}"
        if r.get("testset_run_id"):
            ts += f" · testset-run:{r.get('testset_run_id')}"
        print(f"- Testset: {r.get('testset_name')} ({ts})")
    print(f"- Zeitraum: {str(r.get('start_date', ''))[:10]} → {str(r.get('end_date', ''))[:10]}")
    # Aggregat-Kennzahlen aus der Analyse (falls berechnet)
    try:
        summ = fetch(f"/api/backtest/runs/{i}/analyse/summary")
        print(f"- Analyse: {summ.get('total_results')} Results · {summ.get('profitable_count')} profitabel · "
              f"avg Return {num(summ.get('avg_return'))} / avg Sharpe {num(summ.get('avg_sharpe'))} / max Sharpe {num(summ.get('max_sharpe'))}")
    except Exception:
        pass
    # Verlinkte Results
    try:
        results = fetch(f"/api/backtest/runs/{i}/results")["data"]["items"]
        if results:
            ids = ", ".join(str(x["id"]) for x in results[:5])
            print(f"- Result-IDs: {ids}{' ...' if len(results) > 5 else ''}")
    except Exception:
        pass
    print()


def testset_read(i: int) -> None:
    d = fetch(f"/api/testsets/{i}")["data"]
    print(f"## Testset {i} — {d.get('name')}")
    if d.get("description"):
        print(f"- {d['description']}")
    ids = d.get("backtest_config_ids") or []
    shown = ", ".join(str(x) for x in ids[:10])
    print(f"- {len(ids)} Backtest-Configs: {shown}{' ...' if len(ids) > 10 else ''}")
    if d.get("created_by"):
        print(f"- Erstellt von: {d['created_by']}")
    print()


def leaderboard_read(i: int) -> None:
    d = fetch(f"/api/leaderboard/{i}/drilldown")["data"]
    print(f"## Leaderboard-Eintrag {i}")
    if d.get("executive_summary"):
        print(f"- {d['executive_summary']}")
    results = d.get("results") or []
    print(f"- {len(results)} Configs:")
    for r in results[:10]:
        if r.get("missing"):
            print(f"  - #{r.get('position')}: (Result fehlt)")
            continue
        print(f"  - #{r.get('position')} result:{r.get('result_id')} {r.get('symbol') or ''} — "
              f"Ret {num(r.get('total_return_pct'))}% / Sharpe {num(r.get('sharpe_ratio'))} / "
              f"DD {num(r.get('max_drawdown_pct'))}% / {r.get('n_trades')} Trades")
    print()


def playground_setup_read(i: int) -> None:
    d = fetch(f"/api/chart-playground/setups/{i}")["data"]
    print(f"## Playground-Setup {i} — {d.get('name')}")
    if d.get("description"):
        print(f"- {d['description']}")
    print()


def knowledge_search(query: str) -> None:
    qs = urllib.parse.urlencode({"q": query, "k": 5})
    d = fetch(f"/api/knowledge/search?{qs}")
    results = d.get("results") or []
    print(f"## Knowledge-Suche — \"{query}\" ({len(results)} Treffer)")
    for r in results:
        print(f"- **{r.get('vault_path')}** (Chunk #{r.get('chunk_index')}, sim {num(r.get('similarity'), '{:.3f}')})")
        if r.get("heading_path"):
            print(f"  - {r['heading_path']}")
        content = (r.get("content") or "").strip().replace("\n", " ")
        if len(content) > 300:
            content = content[:300] + "…"
        if content:
            print(f"  - {content}")
    print()


def vault_list(path: str) -> None:
    qs = urllib.parse.urlencode({"q": path, "limit": 20})
    d = fetch(f"/api/knowledge/files?{qs}")
    files = d.get("files") or []
    print(f"## Vault-Dateien — Filter \"{path}\" ({d.get('total', len(files))} gesamt)")
    for f in files[:20]:
        tags = ", ".join(f.get("tags") or [])
        print(f"- **{f.get('vault_path')}** — {f.get('chunk_count')} Chunks · Tags: {tags or '—'}")
    print()


# ---------------------------------------------------------------------------
# Kopier-Handler (copy). Erzeugen jeweils ein neues Objekt und lassen das
# Original unverändert. Funktionsname: <bereich>_copy.
# ---------------------------------------------------------------------------

def backtest_config_copy(i: int) -> None:
    d = post(f"/api/config/backtest/{i}/copy")["data"]
    print(f"## Kopiert: Backtest-Config {i} -> **{d['id']}** ({d.get('name')})\n")


def indicator_config_copy(i: int) -> None:
    d = post(f"/api/config/indicator/{i}/copy")["data"]
    print(f"## Kopiert: Indicator-Config {i} -> **{d['id']}** ({d.get('name')})\n")


def iteration_copy(i: int) -> None:
    d = post(f"/api/strategy/iterations/{i}/copy")["data"]
    name = d.get("version_name") or d.get("version")
    print(f"## Kopiert: Iteration {i} -> **{d['id']}** ({name}, Concept {d.get('concept_id')})\n")


COPY_HANDLERS = {
    "iteration": iteration_copy,
    "backtest-config": backtest_config_copy,
    "indicator-config": indicator_config_copy,
}


# ---------------------------------------------------------------------------
# Erstell-Handler: IndicatorConfig aus einem Result erstellen. Friert die
# Gewinner-Parameter fest (Range -> Skalar) und legt eine Single-Point-Config
# an. Eigener Parser, weil das Segment-Label (Return/Sharpe/PF/WinR90) kein
# numerischer Wert ist.
# ---------------------------------------------------------------------------

def _parse_result_segment_arg(a: str):
    """Arg -> (result_id:str, segment:str|None).

    Akzeptierte Formen: `result:2706026`, `result:2706026:Sharpe`, `2706026`,
    `2706026/Sharpe`. Trenner ':' oder '/'. Gibt (None, None) bei ungültig.
    """
    s = a.strip()
    low = s.lower()
    if low.startswith("result:"):
        s = s[len("result:"):]
    s = s.replace("/", ":")
    parts = s.split(":", 1)
    rid = parts[0].strip()
    seg = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    if not rid.isdigit():
        return None, None
    return rid, seg


def indicator_config_create_from_result(rid: str, segment) -> None:
    body = {"segment": segment} if segment else None
    d = post(f"/api/config/indicator/from-result/{rid}", body)["data"]
    print(f"## Erstellt: IndicatorConfig **{d['id']}** ({d.get('name')}) aus Result {rid}\n")


# ---------------------------------------------------------------------------
# Flag-Parser für Create-/Start-Verben. Liest `--key value` und `--key=value`
# in ein Dict. Positionsargumente landen unter "_positional".
# ---------------------------------------------------------------------------

def _parse_flags(tokens: list) -> dict:
    """Parst `--key value` / `--key=value` in ein Dict. Rest -> _positional."""
    flags: dict = {}
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("--"):
            key = t[2:]
            if "=" in key:
                k, v = key.split("=", 1)
                flags[k] = v
                i += 1
            elif i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                flags[key] = tokens[i + 1]
                i += 2
            else:
                flags[key] = True
                i += 1
        else:
            flags.setdefault("_positional", []).append(t)
            i += 1
    return flags


def _require(flags: dict, key: str, verb: str):
    """Holt einen Pflicht-Flag-Wert oder wirft ValueError."""
    val = flags.get(key)
    if not val or val is True:
        raise ValueError(f"--{key} fehlt (z.B. {verb} --{key} <wert>)")
    return val


def _read_json_file(path: str):
    """Lädt eine JSON-Datei. Wirft bei Fehler — kein stiller Fallback."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Listen-Reads (list). Drucken eine kompakte Markdown-Liste briefbarer Objekte.
# Funktionsname: <bereich>_list. Argumente positionsbasiert (optional/erforderlich
# je Verb), result_list nutzt Flags.
# ---------------------------------------------------------------------------

def concept_list(args: list) -> int:
    items = fetch("/api/strategy/concepts")["data"]["items"]
    print(f"## Konzepte ({len(items)})")
    for c in items:
        print(f"- concept:{c['id']} **{c.get('name')}** ({c.get('slug')}) · {c.get('status')} · Iter-Zähler {c.get('iteration_counter')}")
    print()
    return 0


def iteration_list(args: list) -> int:
    qs = f"?concept_id={int(args[0])}" if args else ""
    items = fetch(f"/api/strategy/iterations{qs}")["data"]["items"]
    print(f"## Iterationen ({len(items)})")
    for it in items:
        nm = it.get("version_name") or ""
        print(f"- iteration:{it['id']} v{it.get('version')} {nm} · Concept {it.get('concept_id')} · {it.get('type')} · {it.get('status')}")
    print()
    return 0


def backtest_config_list(args: list) -> int:
    items = fetch("/api/config/backtest")["data"]
    print(f"## Backtest-Configs ({len(items)})")
    for c in items:
        print(f"- backtest-config:{c['id']} **{c.get('name')}** · {c.get('symbol')} {c.get('timeframe')} · {c.get('start')} -> {c.get('end')}")
    print()
    return 0


def indicator_config_list(args: list) -> int:
    parts = []
    if len(args) >= 1:
        parts.append(f"concept_id={int(args[0])}")
    if len(args) >= 2:
        parts.append(f"iteration_id={int(args[1])}")
    q = ("?" + "&".join(parts)) if parts else ""
    items = fetch(f"/api/config/indicator{q}")["data"]
    print(f"## Indicator-Configs ({len(items)})")
    for c in items:
        print(f"- indicator-config:{c['id']} **{c.get('name')}** · Concept {c.get('strategy_concept_id')} Iter {c.get('strategy_iteration_id')}")
    print()
    return 0


def result_list(args: list) -> int:
    f = _parse_flags(args)
    params = {"limit": f.get("limit", 20)}
    if f.get("run"):
        params["run_id"] = f["run"]
    if f.get("symbol"):
        params["symbol"] = f["symbol"]
    if f.get("timeframe"):
        params["timeframe"] = f["timeframe"]
    items = fetch(f"/api/backtest/results?{urllib.parse.urlencode(params)}")["data"]["items"]
    print(f"## Results ({len(items)})")
    for r in items:
        print(f"- result:{r['id']} run:{r.get('run_id')} {r.get('symbol')} — "
              f"Ret {num(r.get('total_return_pct'))}% / Sharpe {num(r.get('sharpe_ratio'))} / "
              f"DD {num(r.get('max_drawdown_pct'))}% / {r.get('total_trades')} Trades")
    print()
    return 0


def run_list(args: list) -> int:
    """Runs zu einer Strategie+Version (oder Iteration / TestSet-Lauf), nach Testset gruppiert.

    Flags: --strategy <slug> [--version <n>] | --iteration <id> | --testset-run <id> [--limit <n>]
    Die API loest (Slug, Version) serverseitig zu iteration_ids auf — der Aufrufer
    denkt in Strategie+Version, nicht in Datensatz-IDs.
    """
    f = _parse_flags(args)
    params: dict = {"limit": f.get("limit", 10000)}
    if f.get("strategy"):
        params["strategy"] = f["strategy"]
    if f.get("version"):
        params["version"] = f["version"]
    if f.get("iteration"):
        params["iteration_id"] = f["iteration"]
    if f.get("testset-run"):
        params["testset_run_id"] = f["testset-run"]
    items = fetch(f"/api/backtest/runs?{urllib.parse.urlencode(params)}")["data"]["items"]

    scope = []
    if f.get("strategy"):
        scope.append(str(f["strategy"]).upper() + (f" v{f['version']}" if f.get("version") else ""))
    if f.get("iteration"):
        scope.append(f"iteration:{f['iteration']}")
    if f.get("testset-run"):
        scope.append(f"testset-run:{f['testset-run']}")
    print(f"## Runs — {' · '.join(scope) if scope else 'alle'} ({len(items)})")
    if not items:
        print("- (keine)\n")
        return 0

    # Nach Testset-Lauf (testset_run_id = Auftrags-ID) gruppieren: ein Testset-Lauf
    # umfasst alle Symbol-Runs eines Auftrags. So ist sichtbar, welche Runs als ein
    # Auftrag zusammengehören — und die ID ist direkt als --testset-run-Selektor nutzbar.
    # Einzel-Backtests ohne Testset-Lauf kommen in eine eigene Gruppe.
    groups: dict = {}
    for r in items:
        groups.setdefault(r.get("testset_run_id"), []).append(r)
    # Auftrags-Gruppen zuerst (nach ID), Einzel-Backtests (None) ans Ende.
    for gkey in sorted(groups, key=lambda k: (k is None, k or 0)):
        rs = sorted(groups[gkey], key=lambda x: x["id"])
        if gkey is None:
            print("\n### Einzel-Backtests (kein Testset-Lauf)")
        else:
            name = rs[0].get("testset_name") or "Testset-Lauf"
            tsid = rs[0].get("testset_id")
            ts = f"testset:{tsid} · " if tsid else ""
            print(f"\n### {name} ({ts}testset-run:{gkey})")
        for r in rs:
            print(f"- run:{r['id']} · {r.get('symbol')} {r.get('timeframe')} · {r.get('status')} · "
                  f"{r.get('n_combinations')} Kombinationen · "
                  f"{str(r.get('start_date', ''))[:10]}→{str(r.get('end_date', ''))[:10]}")
    print()
    return 0


def testset_list(args: list) -> int:
    items = fetch("/api/testsets")["data"]
    print(f"## Testsets ({len(items)})")
    for t in items:
        n = len(t.get("backtest_config_ids") or [])
        print(f"- testset:{t['id']} **{t.get('name')}** · {n} Backtest-Configs")
    print()
    return 0


def leaderboard_list(args: list) -> int:
    qs = f"?testset_id={int(args[0])}" if args else ""
    items = fetch(f"/api/leaderboard{qs}")["data"]["items"]
    print(f"## Leaderboard ({len(items)})")
    for e in items:
        print(f"- leaderboard:{e['id']} {e.get('testset_name') or ''} {e.get('strategy_family')} {e.get('strategy_name')} — "
              f"Ø Ret {num(e.get('total_return_avg'))}% / Sharpe {num(e.get('sharpe_avg'))} / "
              f"{e.get('configs_win')}W-{e.get('configs_loss')}L")
    print()
    return 0


def symbol_list(args: list) -> int:
    if len(args) < 2:
        raise ValueError("symbol-list braucht <exchange> <timeframe> (z.B. symbol-list binance 4h)")
    exchange, timeframe = args[0], args[1]
    qs = urllib.parse.urlencode({"exchange": exchange, "timeframe": timeframe})
    d = fetch(f"/api/config/symbols?{qs}")["data"]
    syms = d.get("symbols") or []
    print(f"## Symbole {exchange}/{timeframe} ({len(syms)}) — Datei {d.get('file')}, vorhanden {d.get('exists')}")
    if syms:
        print(", ".join(syms))
    print()
    return 0


def _filter_indicators(groups: list, group_filter: str = None, search: str = "") -> list:
    """Filtert die Indikator-Gruppen des Katalogs nach Gruppe und/oder Suchtext.

    Reine Funktion (kein Netzwerk-Zugriff) — testbar ohne laufenden Server.

    Args:
        groups: Liste der Gruppen-Objekte (`{"name": ..., "indicators": [...]}`),
            wie von `GET /api/chart-playground/indicators` geliefert.
        group_filter: Falls gesetzt, nur Indikatoren dieser Gruppe (exakter Name-Match).
        search: Case-insensitiver Substring-Filter über `id` und `name`. Leerer
            String = kein Filter.

    Returns:
        Liste der passenden Indikator-Objekte über alle betroffenen Gruppen hinweg.
    """
    search = (search or "").lower()
    matches = []
    for g in groups:
        if group_filter and g["name"] != group_filter:
            continue
        for ind in g["indicators"]:
            if search and search not in ind["id"].lower() and search not in ind["name"].lower():
                continue
            matches.append(ind)
    return matches


def _format_indicator_line(ind: dict) -> str:
    """Formatiert einen Indikator als kompakte Markdown-Zeile (id/inputs/params/outputs).

    Args:
        ind: Indikator-Objekt aus dem Katalog (`id`, `inputs`, `params`, `outputs`).

    Returns:
        Eine einzelne Markdown-Bullet-Zeile ohne Defaults-Ballast.
    """
    params = ", ".join(p["name"] for p in ind.get("params", []))
    return (f"- **{ind['id']}** — inputs: {', '.join(ind.get('inputs', [])) or '—'} | "
            f"params: {params or '—'} | outputs: {', '.join(ind.get('outputs', [])) or '—'}")


def playground_indicators_list(args: list) -> int:
    """Indikator-Katalog des Chart-Playgrounds — gefiltert statt voll gedumpt.

    Ohne Filter: kompakte Gruppen-Übersicht (Name + Anzahl je Gruppe).
    Mit --group <name>: nur diese Gruppe (z.B. talib, vbt, custom, ta, wqa101).
    Mit --search <substring>: case-insensitiv über id/name gefiltert (z.B. "ema").
    Beide Flags kombinierbar. Bei Treffern: eine Zeile je Indikator mit
    id/inputs/params(Namen)/outputs — kein voller JSON-Dump mit Defaults.
    """
    f = _parse_flags(args)
    group_filter = f.get("group")
    search = f.get("search") or ""
    groups = fetch("/api/chart-playground/indicators")["data"]["groups"]

    if not group_filter and not search:
        total = sum(len(g["indicators"]) for g in groups)
        print(f"## Indikator-Katalog ({total} gesamt)")
        for g in groups:
            print(f"- {g['name']}: {len(g['indicators'])}")
        print("\nFilter: --group <name> und/oder --search <substring>\n")
        return 0

    matches = _filter_indicators(groups, group_filter, search)
    label = " / ".join(
        p for p in (f"Gruppe {group_filter}" if group_filter else None,
                    f"Suche '{search}'" if search else None) if p
    )
    print(f"## Indikator-Katalog — {label} ({len(matches)} Treffer)")
    for ind in matches:
        print(_format_indicator_line(ind))
    print()
    return 0


def run_parameter_ranking(args: list) -> int:
    if not args:
        raise ValueError("run-parameter-ranking braucht <run_id> [metric]")
    run_id = int(args[0])
    metric = args[1] if len(args) > 1 else "sharpe_ratio"
    d = fetch(f"/api/backtest/runs/{run_id}/analyse/parameter-ranking?metric={urllib.parse.quote(metric)}")
    print(f"## Parameter-Ranking Run {run_id} — {d.get('metric_label', metric)}")
    for pname, vals in (d.get("parameters") or {}).items():
        print(f"- **{pname}**:")
        for v in vals[:10]:
            print(f"  - {v.get('value')}: Ø {num(v.get('avg'), '{:.4f}')} "
                  f"(min {num(v.get('min'), '{:.4f}')} / max {num(v.get('max'), '{:.4f}')}, n {v.get('count')})")
    print()
    return 0


def run_top_results(args: list) -> int:
    if not args:
        raise ValueError("run-top-results braucht <run_id> [metric] [limit] [direction]")
    run_id = int(args[0])
    metric = args[1] if len(args) > 1 else "sharpe_ratio"
    limit = args[2] if len(args) > 2 else "20"
    direction = args[3] if len(args) > 3 else "desc"
    qs = urllib.parse.urlencode({"metric": metric, "limit": limit, "direction": direction})
    d = fetch(f"/api/backtest/runs/{run_id}/analyse/top-results?{qs}")
    results = d.get("results") or []
    print(f"## Top-Results Run {run_id} — {d.get('metric_label', metric)} {direction} ({len(results)})")
    for r in results:
        params = r.get("actual_params") or {}
        pstr = ", ".join(f"{k}={v}" for k, v in params.items()) if isinstance(params, dict) else ""
        print(f"- result:{r['id']} — Ret {num(r.get('total_return_pct'))}% / WinR {num(r.get('win_rate_pct'))}% / "
              f"Sharpe {num(r.get('sharpe_ratio'))} / DD {num(r.get('max_drawdown_pct'))}% / "
              f"PF {num(r.get('profit_factor'))} / {r.get('total_trades')} Trades")
        if pstr:
            print(f"  - {pstr}")
    print()
    return 0


# Spalten-Index im /results/dt-Endpoint (Sortier-Parameter order[0][column])
_DT_SORT_IDX = {
    "sharpe_ratio": 13, "max_drawdown_pct": 15, "total_trades": 16,
    "win_rate_pct": 17, "profit_factor": 18, "total_return_pct": 19,
}
_METRIC_LABEL = {
    "total_return_pct": "Total Return", "win_rate_pct": "Win Rate",
    "sharpe_ratio": "Sharpe", "profit_factor": "Profit Factor",
    "max_drawdown_pct": "Max Drawdown", "total_trades": "Trades",
}


def run_best(args: list) -> int:
    """Bester Result eines Runs nach <metrik>, gefiltert auf >= min_trades.

    Einfaches Regelwerk gegen Low-Trade-Flukes: erst alle Results mit
    mindestens <min_trades> Trades, davon der höchste Wert der Metrik.
    Filter (total_trades_min) + Sortierung laufen serverseitig über
    /api/backtest/results/dt. Default-Floor 30 Trades.
    """
    if len(args) < 2:
        raise ValueError("run-best braucht <run_id> <metrik> [min_trades=30] [limit=1]")
    run_id = int(args[0])
    metric = args[1]
    if metric not in _DT_SORT_IDX:
        raise ValueError(f"Unbekannte Metrik {metric!r}. Erlaubt: {', '.join(_DT_SORT_IDX)}")
    min_trades = int(args[2]) if len(args) > 2 else 30
    limit = int(args[3]) if len(args) > 3 else 1
    qs = urllib.parse.urlencode({
        "run_id": run_id, "total_trades_min": min_trades,
        "order[0][column]": _DT_SORT_IDX[metric], "order[0][dir]": "desc",
        "start": 0, "length": limit, "draw": 1,
    })
    dd = fetch(f"/api/backtest/results/dt?{qs}")
    rows = dd.get("data") or []
    n = dd.get("recordsFiltered")
    print(f"## Best Run {run_id} — {_METRIC_LABEL[metric]} desc, min {min_trades} Trades "
          f"({n} Results >= {min_trades} Trades), Top {limit}")
    for r in rows:
        params = r.get("actual_params") or {}
        pstr = ", ".join(f"{k}={v}" for k, v in params.items()) if isinstance(params, dict) else ""
        print(f"- result:{r['id']} — Ret {num(r.get('total_return_pct'))}% / WinR {num(r.get('win_rate_pct'))}% / "
              f"Sharpe {num(r.get('sharpe_ratio'))} / DD {num(r.get('max_drawdown_pct'))}% / "
              f"PF {num(r.get('profit_factor'))} / {r.get('total_trades')} Trades")
        if pstr:
            print(f"  - {pstr}")
    print()
    return 0


# ---------------------------------------------------------------------------
# Bestwerte (bestwerte). EIN Verb, das die kanonische 4er-Definition aus
# multiparameter-lauf.md ausführbar kapselt — damit sie nicht je Aufruf von Hand
# falsch zusammengesetzt wird — und die Gewinner als Doku-Favorit (roter Stern)
# markiert. Die Definitionswerte (Band 20% vom Höchstwert, PF-Floor 30 Trades) sind
# bewusst fest verdrahtet, NICHT parametrisierbar: das Verb IST die Definition.
# ---------------------------------------------------------------------------

# Feste Definitionswerte der vier Bestwerte (multiparameter-lauf.md Schritt 5).
# Oberes Band für Krit 2 (Win-Rate) und Krit 3 (Sharpe) — Anteil vom jeweiligen
# Höchstwert, innerhalb des Bands wird nach Total Return gekürt. Die beiden Bänder
# sind BEWUSST unterschiedlich breit: das Sharpe-Band ist mit 10 Prozent enger als
# das Win-Rate-Band (20 Prozent), damit der Sharpe-Band-Sieger seltener mit dem
# Max-Total-Return-Bestwert zusammenfällt (mehr distinkte Doku-Favoriten je Run).
_WINRATE_BAND_FRACTION = 0.20
_SHARPE_BAND_FRACTION = 0.10
_PF_MIN_TRADES = 30


def _dt_query(run_id: int, order_idx: int, *, win_rate_pct_min=None,
              sharpe_ratio_min=None, total_trades_min=None, length: int = 1) -> tuple:
    """Top-<length> Results eines Runs nach Spalte <order_idx> absteigend.

    Geteilte Low-Level-Abfrage über /api/backtest/results/dt für die vier
    Bestwerte (Spalten-Indizes in _DT_SORT_IDX). Optionale serverseitige Filter
    win_rate_pct_min / sharpe_ratio_min / total_trades_min. Gibt (rows, recordsFiltered) zurück.
    """
    params = {
        "run_id": run_id,
        "order[0][column]": order_idx, "order[0][dir]": "desc",
        "start": 0, "length": length, "draw": 1,
    }
    if win_rate_pct_min is not None:
        params["win_rate_pct_min"] = win_rate_pct_min
    if sharpe_ratio_min is not None:
        params["sharpe_ratio_min"] = sharpe_ratio_min
    if total_trades_min is not None:
        params["total_trades_min"] = total_trades_min
    dd = fetch(f"/api/backtest/results/dt?{urllib.parse.urlencode(params)}")
    return dd.get("data") or [], dd.get("recordsFiltered")


def _band_best_return(run_id: int, metric_key: str, filter_param: str, fraction: float) -> tuple:
    """Bestes Total Return im oberen <metric>-Band eines Runs als (result|None, info).

    Gemeinsame Mechanik für Krit 2 (Win-Rate-Band) und Krit 3 (Sharpe-Band): nimmt
    den Höchstwert der Metrik im Run, zieht den Bandanteil <fraction> vom Höchstwert
    ab und wählt aus allen Results im Band [max - fraction, max] das mit dem
    höchsten Total Return. So kann ein Low-Trade-Fluke (hoher Sharpe/100% Win-Rate
    bei 2 Trades) den Bestwert nicht mehr direkt kapern — im Band gewinnt der echte
    Return. Der Abzug nutzt abs(), damit das Band auch bei durchweg negativem
    Höchstwert (z.B. negativer Sharpe) korrekt unterhalb des Maximums liegt.
    """
    top_rows, _ = _dt_query(run_id, _DT_SORT_IDX[metric_key])
    if not top_rows or top_rows[0].get(metric_key) is None:
        return None, f"keine {_METRIC_LABEL[metric_key]}-Results"
    max_val = top_rows[0][metric_key]
    threshold = max_val - abs(max_val) * fraction
    band_rows, n_band = _dt_query(run_id, _DT_SORT_IDX["total_return_pct"],
                                  **{filter_param: threshold})
    info = f"Band {num(threshold)}..{num(max_val)} ({n_band} im Band)"
    return (band_rows[0] if band_rows else None), info


def _bestwerte_for_run(run_id: int) -> list:
    """Die vier kanonischen Bestwerte eines Runs als Liste (label, result|None, info).

    1) Max Total Return (kein Trade-Floor)
    2) Bestes Total Return im oberen Win-Rate-Band (höchste Win-Rate minus 20% vom Höchstwert)
    3) Bestes Total Return im oberen Sharpe-Band (höchster Sharpe minus 10% vom Höchstwert)
    4) Max Profitfaktor mit mindestens 30 Trades
    """
    out = []
    # 1) Max Total Return
    rows, _ = _dt_query(run_id, _DT_SORT_IDX["total_return_pct"])
    out.append(("Max Total Return", rows[0] if rows else None, ""))
    # 2) Win-Rate-Band -> bestes Total Return (Band 20%)
    res2, info2 = _band_best_return(run_id, "win_rate_pct", "win_rate_pct_min", _WINRATE_BAND_FRACTION)
    out.append(("Bestes Return im Win-Rate-Band", res2, info2))
    # 3) Sharpe-Band -> bestes Total Return (Band 10% — enger als Win-Rate)
    res3, info3 = _band_best_return(run_id, "sharpe_ratio", "sharpe_ratio_min", _SHARPE_BAND_FRACTION)
    out.append(("Bestes Return im Sharpe-Band", res3, info3))
    # 4) Max Profitfaktor mit >= 30 Trades
    rows, n = _dt_query(run_id, _DT_SORT_IDX["profit_factor"], total_trades_min=_PF_MIN_TRADES)
    out.append((f"Max Profitfaktor (>= {_PF_MIN_TRADES} Trades)",
                rows[0] if rows else None, f"{n} mit >= {_PF_MIN_TRADES} Trades"))
    return out


def _fmt_result_line(r: dict) -> str:
    """Eine Result-Zeile mit Kennzahlen + actual_params (gleiches Format wie run-best)."""
    params = r.get("actual_params") or {}
    pstr = ", ".join(f"{k}={v}" for k, v in params.items()) if isinstance(params, dict) else ""
    line = (f"result:{r['id']} — Ret {num(r.get('total_return_pct'))}% / WinR {num(r.get('win_rate_pct'))}% / "
            f"Sharpe {num(r.get('sharpe_ratio'))} / DD {num(r.get('max_drawdown_pct'))}% / "
            f"PF {num(r.get('profit_factor'))} / {r.get('total_trades')} Trades")
    return line + (f"  ·  {pstr}" if pstr else "")


def _resolve_runs(f: dict, verb: str) -> tuple:
    """Loest die Run-Auswahl aus den Selektor-Flags auf -> (runs, scope).

    Geteilt von run-bestwerte und run-favorites-reset. Genau ein Selektor:
    --run <id> | --strategy <slug> [--version <n>] | --iteration <id> | --testset-run <id>.
    Liefert die Run-Dicts (wie /api/backtest/runs) und einen lesbaren Scope-String.
    """
    if f.get("run"):
        return [{"id": int(f["run"])}], f"run:{f['run']}"
    params: dict = {"limit": f.get("limit", 10000)}
    if f.get("strategy"):
        params["strategy"] = f["strategy"]
    if f.get("version"):
        params["version"] = f["version"]
    if f.get("iteration"):
        params["iteration_id"] = f["iteration"]
    if f.get("testset-run"):
        params["testset_run_id"] = f["testset-run"]
    if len(params) == 1:
        raise ValueError(f"{verb} braucht einen Selektor: --run | --strategy [--version] | --iteration | --testset-run")
    runs = fetch(f"/api/backtest/runs?{urllib.parse.urlencode(params)}")["data"]["items"]
    sc = []
    if f.get("strategy"):
        sc.append(str(f["strategy"]).upper() + (f" v{f['version']}" if f.get("version") else ""))
    if f.get("iteration"):
        sc.append(f"iteration:{f['iteration']}")
    if f.get("testset-run"):
        sc.append(f"testset-run:{f['testset-run']}")
    return runs, (" · ".join(sc) if sc else "alle")


def run_bestwerte(args: list) -> int:
    """Vier feste Bestwerte je Run ziehen UND als Doku-Favorit (roter Stern) markieren.

    Flags: --run <id> | --strategy <slug> [--version <n>] | --iteration <id> | --testset-run <id> [--limit <n>]
    Kapselt die kanonische 4er-Definition aus multiparameter-lauf.md (max Total
    Return · bestes Return im oberen Win-Rate-Band [Max-WinR - 20% vom Höchstwert] · bestes
    Return im oberen Sharpe-Band [Max-Sharpe - 10% vom Höchstwert] · max Profitfaktor mit
    >= 30 Trades), damit sie nicht von Hand falsch
    zusammengesetzt werden kann. Mehrere Runs über die gleiche Auflösung wie
    run-list (Strategie+Version / Iteration / TestSet-Lauf).

    Markiert idempotent: Ein Gewinner-Result, das den roten Stern schon trägt
    (oder ihn in diesem Lauf als Mehrfach-Sieger bereits bekommen hat), wird NICHT
    erneut getoggelt — der doc_favorite-Endpunkt ist ein Toggle.
    """
    f = _parse_flags(args)
    runs, scope = _resolve_runs(f, "run-bestwerte")

    print(f"## Bestwerte — {scope} ({len(runs)} Run(s)) — vier feste Kriterien, rote Doku-Favoriten")
    if not runs:
        print("- (keine Runs)\n")
        return 0

    now_on: set = set()   # Result-IDs, die nach diesem Lauf den roten Stern tragen
    newly: set = set()    # davon: in diesem Lauf neu gesetzt
    for run in sorted(runs, key=lambda x: x["id"]):
        rid = run["id"]
        meta = []
        if run.get("symbol"):
            meta.append(f"{run['symbol']} {run.get('timeframe', '')}".strip())
        if run.get("testset_name"):
            tn = run["testset_name"]
            if run.get("testset_run_id"):
                tn += f" (testset-run:{run['testset_run_id']})"
            meta.append(tn)
        print(f"\n### run:{rid}{(' · ' + ' · '.join(meta)) if meta else ''}")
        for label, res, info in _bestwerte_for_run(rid):
            suffix = f" — {info}" if info else ""
            if not res:
                print(f"- **{label}**{suffix}: kein Result")
                continue
            print(f"- **{label}**{suffix}")
            print(f"  - {_fmt_result_line(res)}")
            res_id = res["id"]
            if res_id in now_on or res.get("is_doc_favorite"):
                now_on.add(res_id)
                print("  - roter Stern: bereits gesetzt")
            else:
                post(f"/api/backtest/results/{res_id}/doc_favorite")
                now_on.add(res_id)
                newly.add(res_id)
                print("  - roter Stern: gesetzt")

    already = len(now_on) - len(newly)
    print(f"\n**{len(now_on)} Results sind rote Doku-Favoriten** — {len(newly)} neu gesetzt, {already} bereits zuvor markiert.")
    if newly:
        print(f"Neu: {', '.join(f'result:{i}' for i in sorted(newly))}")
    print()
    return 0


# Favoriten-Reset. Raeumt die Favoriten einer ganzen Run-Menge ab: roter Doku-Stern
# (is_doc_favorite) UND/ODER gelber User-Stern (is_favorite). Beide Endpunkte sind
# Toggles -> erst markierte Results auslesen, dann gezielt zuruecktoggeln (kein
# Blind-Toggle, der ungesetzte Sterne anschalten wuerde).
_FAV_KINDS = {
    # flag -> (dt-Spaltenindex [Favoriten sortieren zuerst], Result-Feld, Endpunkt-Suffix, Label)
    "doc": (2, "is_doc_favorite", "doc_favorite", "roter Stern (Doku)"),
    "user": (1, "is_favorite", "favorite", "gelber Stern (User)"),
}


def run_favorites_reset(args: list) -> int:
    """Favoriten einer Run-Menge zuruecksetzen (roter Doku-Stern und/oder gelber User-Stern).

    Flags: --run <id> | --strategy <slug> [--version <n>] | --iteration <id> | --testset-run <id>
           [--doc] [--user]
    Ohne --doc/--user werden BEIDE Favoriten-Arten abgeraeumt ("ganzer Run reset").
    Mit genau einem der beiden Flags nur diese Art. Run-Aufloesung identisch zu run-bestwerte.

    Liest je Run die aktuell markierten Results aus (dt-Endpunkt, Favoriten zuerst
    sortiert) und toggelt jeden gesetzten Stern einzeln aus. Idempotent: ein bereits
    sternloses Result wird nicht angefasst.
    """
    f = _parse_flags(args)
    kinds = [k for k in ("doc", "user") if f.get(k)] or ["doc", "user"]
    runs, scope = _resolve_runs(f, "run-favorites-reset")

    kind_labels = ", ".join(_FAV_KINDS[k][3] for k in kinds)
    print(f"## Favoriten-Reset — {scope} ({len(runs)} Run(s)) — {kind_labels}")
    if not runs:
        print("- (keine Runs)\n")
        return 0

    removed_total = 0
    for run in sorted(runs, key=lambda x: x["id"]):
        rid = run["id"]
        for kind in kinds:
            col_idx, field, suffix, label = _FAV_KINDS[kind]
            # Favoriten sortieren zuerst -> length deckt jede realistische Favoriten-Zahl je Run ab
            rows, _ = _dt_query(rid, col_idx, length=200)
            marked = [r["id"] for r in rows if r.get(field)]
            for res_id in marked:
                post(f"/api/backtest/results/{res_id}/{suffix}")   # Toggle aus
            removed_total += len(marked)
            ids = ", ".join(f"result:{i}" for i in marked) if marked else "—"
            print(f"- run:{rid} · {label}: {len(marked)} entfernt ({ids})")

    print(f"\n**{removed_total} Favoriten-Markierungen entfernt.**\n")
    return 0


# ---------------------------------------------------------------------------
# Anlegen (create). Erzeugen jeweils ein neues Objekt per POST. Komplexe
# Payloads (spec_json, config_json, volle Backtest-Config) per --file als
# JSON-Datei. KEIN stiller Konverter, kein Fallback: das spec_json/config_json
# wird unverändert durchgereicht und scheitert beim Lauf laut, wenn falsch
# geformt. Funktionsname: <bereich>_create.
# ---------------------------------------------------------------------------

def concept_create(args: list) -> int:
    f = _parse_flags(args)
    body = {"slug": _require(f, "slug", "concept-create"), "name": _require(f, "name", "concept-create")}
    for key in ("category", "description", "status"):
        if f.get(key):
            body[key] = f[key]
    d = post("/api/strategy/concepts", body)["data"]
    print(f"## Erstellt: Concept **{d['id']}** ({d.get('name')}, {d.get('slug')})\n")
    return 0


def iteration_create(args: list) -> int:
    f = _parse_flags(args)
    concept_id = int(_require(f, "concept", "iteration-create"))
    spec = _read_json_file(_require(f, "file", "iteration-create"))
    body = {"concept_id": concept_id, "spec_json": spec, "type": f.get("type", "generic")}
    if f.get("name"):
        body["version_name"] = f["name"]
    if f.get("import-path"):
        body["import_path"] = f["import-path"]
    if f.get("parent"):
        body["parent_iteration_id"] = int(f["parent"])
    if f.get("description"):
        body["description"] = f["description"]
    d = post("/api/strategy/iterations", body)["data"]
    nm = d.get("version_name") or ""
    print(f"## Erstellt: Iteration **{d['id']}** (v{d.get('version')} {nm}, Concept {d.get('concept_id')})\n")
    return 0


def _preview_labels(config_json: dict, concept_id, iteration_id) -> dict:
    """Standard-Labels (Name + Beschreibung) über den Server-Endpunkt berechnen.

    Nutzt dieselbe zustandslose Route wie die Frontend-Buttons
    (/api/config/indicator/preview-labels) — einzige Notations-Wahrheit ist
    services/api/utils/indicator_labels.py. Konzeptname und Iterations-Nummer werden
    aus den verknüpften IDs aufgelöst; ohne Verknüpfung entfällt der jeweilige Teil.
    """
    concept_name = None
    iteration_number = None
    if iteration_id:
        it = fetch(f"/api/strategy/iterations/{iteration_id}")["data"]
        iteration_number = it.get("version")
        if not concept_id:
            concept_id = it.get("concept_id")
    if concept_id:
        concept_name = fetch(f"/api/strategy/concepts/{concept_id}")["data"].get("name")
    body = {
        "config_json": config_json,
        "concept_name": concept_name,
        "iteration_number": iteration_number,
    }
    return post("/api/config/indicator/preview-labels", body)["data"]


def indicator_config_create(args: list) -> int:
    f = _parse_flags(args)
    config_json = _read_json_file(_require(f, "file", "indicator-config-create"))
    concept_id = int(f["concept"]) if f.get("concept") else None
    iteration_id = int(f["iteration"]) if f.get("iteration") else None
    name = f.get("name") if f.get("name") and f.get("name") is not True else None
    description = f.get("description") if f.get("description") and f.get("description") is not True else None
    # Ohne --name: Standard-Titel (und, falls keine --description, Standard-Beschreibung)
    # nach Notation über den Server erzeugen. Mit --name: individuell, verbatim.
    if name is None:
        labels = _preview_labels(config_json, concept_id, iteration_id)
        name = labels.get("name")
        if description is None:
            description = labels.get("description")
    body = {"name": name, "config_json": config_json}
    if concept_id:
        body["strategy_concept_id"] = concept_id
    if iteration_id:
        body["strategy_iteration_id"] = iteration_id
    if description:
        body["description"] = description
    d = post("/api/config/indicator", body)["data"]
    print(f"## Erstellt: Indicator-Config **{d['id']}** ({d.get('name')})\n")
    return 0


def backtest_config_create(args: list) -> int:
    f = _parse_flags(args)
    body = _read_json_file(_require(f, "file", "backtest-config-create"))
    d = post("/api/config/backtest", body)["data"]
    print(f"## Erstellt: Backtest-Config **{d['id']}** ({d.get('name')})\n")
    return 0


def testset_create(args: list) -> int:
    f = _parse_flags(args)
    name = _require(f, "name", "testset-create")
    raw = _require(f, "configs", "testset-create")
    ids = [int(x) for x in str(raw).split(",") if x.strip()]
    body = {"name": name, "backtest_config_ids": ids}
    if f.get("description"):
        body["description"] = f["description"]
    d = post("/api/testsets", body)["data"]
    print(f"## Erstellt: Testset **{d['id']}** ({d.get('name')}, {len(ids)} Backtest-Configs)\n")
    return 0


# ---------------------------------------------------------------------------
# Ausführen (start). Stoßen einen Lauf an. ID-basiert, keine Payload-Datei.
# Funktionsname: <bereich>_start.
# ---------------------------------------------------------------------------

def backtest_run_start(args: list) -> int:
    f = _parse_flags(args)
    body = {
        "backtest_config_id": int(_require(f, "backtest-config", "backtest-run-start")),
        "indicator_config_id": int(_require(f, "indicator-config", "backtest-run-start")),
        "iteration_id": int(_require(f, "iteration", "backtest-run-start")),
    }
    d = post("/api/backtest/start", body)["data"]
    print(f"## Gestartet: Backtest-Run **{d['run_id']}** "
          f"(backtest-config {body['backtest_config_id']}, indicator-config {body['indicator_config_id']}, iteration {body['iteration_id']})\n")
    return 0


def testset_run_start(args: list) -> int:
    f = _parse_flags(args)
    body = {
        "testset_id": int(_require(f, "testset", "testset-run-start")),
        "iteration_id": int(_require(f, "iteration", "testset-run-start")),
        "indicator_config_id": int(_require(f, "indicator-config", "testset-run-start")),
    }
    d = post("/api/testset-runs", body)["data"]
    run_ids = d.get("run_ids", [])
    print(f"## Gestartet: Testset-Run **{d['testset_run_id']}** — {len(run_ids)} Runs "
          f"({', '.join(str(x) for x in run_ids)})\n")
    return 0


# ---------------------------------------------------------------------------
# Ändern / Löschen / Aktionen / restliche Reads. Damit deckt die Toolbox JEDE
# operative API-Route ab. Einfache Fälle laufen über eine deklarative Tabelle
# (TABLE_VERBS) mit generischem Executor; Bodies aus mehreren Skalar-Flags haben
# eigene kleine Handler. Der generische `api`-Befehl erreicht zusätzlich jede
# beliebige (auch künftige) Route direkt.
# ---------------------------------------------------------------------------

def _print_data(verb: str, resp) -> None:
    """Druckt die Antwort einer Route als kompakten JSON-Block.

    Kürzt sehr lange Antworten auf 4000 Zeichen, weist die Kürzung dabei aber
    immer sichtbar mit Original-Größe aus — nie stilles Abschneiden.
    """
    payload = resp.get("data", resp) if isinstance(resp, dict) else resp
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(f"## {verb}")
    print("```json")
    if len(text) > 4000:
        print(text[:4000])
        print(f"[gekürzt: 4000 von {len(text)} Zeichen — Filter nutzen]")
    else:
        print(text)
    print("```\n")


def _run_table_verb(verb: str, spec: tuple, args: list) -> int:
    """Generischer Executor für TABLE_VERBS.

    spec = (method, path_template, n_path_args, body_mode, use_query)
      - path_template nutzt '{}' für (max. 1) Pfad-Argument (aus --id oder erstem Positional)
      - body_mode: None | 'file' (--file = JSON-Body) | 'ids' (--ids 1,2,3 -> {ids:[...]})
      - use_query: True -> übrige --flags werden als Query-String angehängt
    """
    method, path_tmpl, n_path, body_mode, use_query = spec
    f = _parse_flags(args)
    pos = f.get("_positional", [])
    fmt_args = []
    if n_path:
        val = f.get("id")
        if val is None and pos:
            val = pos[0]
        if val is None:
            raise ValueError(f"{verb}: ID fehlt (--id <n> oder als erstes Argument)")
        fmt_args.append(val)
    path = path_tmpl.format(*fmt_args)

    if use_query:
        q = {}
        for k, v in f.items():
            if k in ("file", "id", "ids", "_positional"):
                continue
            q[k] = "true" if v is True else v
        if q:
            path += ("&" if "?" in path else "?") + urllib.parse.urlencode(q)

    body = None
    if body_mode == "file":
        body = _read_json_file(_require(f, "file", verb))
    elif body_mode == "ids":
        raw = f.get("ids") or (pos[0] if pos else None)
        if not raw:
            raise ValueError(f"{verb}: --ids 1,2,3 fehlt")
        body = {"ids": [int(x) for x in str(raw).split(",") if x.strip()]}

    resp = request(method, path, body)
    if method == "GET":
        _print_data(verb, resp)
    else:
        payload = resp.get("data", resp) if isinstance(resp, dict) else resp
        print(f"## {verb}: OK — {json.dumps(payload, ensure_ascii=False)[:300]}\n")
    return 0


def api_call(args: list) -> int:
    """Generischer Direktaufruf: api <METHOD> <pfad> [--file body.json].

    Erreicht JEDE Route — auch solche ohne eigenes Verb und künftige.
    """
    if len(args) < 2:
        raise ValueError("api braucht <METHOD> <pfad> (z.B. api GET /api/backtest/runs)")
    method = args[0].upper()
    path = args[1]
    if not path.startswith("/"):
        path = "/" + path
    f = _parse_flags(args[2:])
    body = _read_json_file(f["file"]) if f.get("file") else None
    resp = request(method, path, body)
    _print_data(f"api {method} {path}", resp)
    return 0


# Flag-Body-Handler: Bodies aus mehreren Skalar-Flags (kein --file).

def walk_forward_start(args: list) -> int:
    f = _parse_flags(args)
    body = {"result_id": int(_require(f, "result", "walk-forward-start"))}
    if f.get("months"):
        body["months"] = int(f["months"])
    if f.get("metric"):
        body["metric"] = f["metric"]
    d = post("/api/backtest/walk-forward", body)["data"]
    print(f"## Gestartet: Walk-Forward-Run **{d['run_id']}** "
          f"(aus Result {d.get('parent_result_id')}, {d.get('start')} → {d.get('end')})\n")
    return 0


def run_remarks_set(args: list) -> int:
    f = _parse_flags(args)
    pos = f.get("_positional", [])
    rid = f.get("id") or (pos[0] if pos else None)
    if not rid:
        raise ValueError("run-remarks: ID fehlt (--id <n> oder erstes Argument)")
    text = _require(f, "text", "run-remarks")
    request("PUT", f"/api/backtest/runs/{int(rid)}/remarks", {"remarks": text})
    print(f"## run-remarks: OK — Run {int(rid)} Bemerkung gesetzt\n")
    return 0


def data_update(args: list) -> int:
    f = _parse_flags(args)
    body = {"exchange": f.get("exchange", "binance"), "timeframe": _require(f, "timeframe", "data-update")}
    d = post("/api/config/data/update", body)["data"]
    print(f"## data-update: OK — Job {d.get('id')} (rq {d.get('rq_job_id')})\n")
    return 0


def data_delete_symbol(args: list) -> int:
    f = _parse_flags(args)
    body = {
        "exchange": f.get("exchange", "binance"),
        "timeframe": _require(f, "timeframe", "data-delete-symbol"),
        "symbol": _require(f, "symbol", "data-delete-symbol"),
    }
    d = request("POST", "/api/config/data/delete-symbol", body).get("data", {})
    print(f"## data-delete-symbol: OK — {d}\n")
    return 0


# Deklarative Tabelle: verb -> (METHOD, pfad_template, n_pfad_args, body_mode, use_query)
TABLE_VERBS = {
    # Ändern (PUT, voller Body per --file)
    "concept-update": ("PUT", "/api/strategy/concepts/{}", 1, "file", False),
    "iteration-update": ("PUT", "/api/strategy/iterations/{}", 1, "file", False),
    "backtest-config-update": ("PUT", "/api/config/backtest/{}", 1, "file", False),
    "indicator-config-update": ("PUT", "/api/config/indicator/{}", 1, "file", False),
    "strategy-config-update": ("PUT", "/api/config/strategy/{}", 1, "file", False),
    "testset-update": ("PUT", "/api/testsets/{}", 1, "file", False),
    "playground-setup-update": ("PUT", "/api/chart-playground/setups/{}", 1, "file", False),
    # Löschen (DELETE). concept/iteration unterstützen --force und --delete_vault.
    "concept-delete": ("DELETE", "/api/strategy/concepts/{}", 1, None, True),
    "iteration-delete": ("DELETE", "/api/strategy/iterations/{}", 1, None, True),
    "backtest-config-delete": ("DELETE", "/api/config/backtest/{}", 1, None, False),
    "indicator-config-delete": ("DELETE", "/api/config/indicator/{}", 1, None, False),
    "strategy-config-delete": ("DELETE", "/api/config/strategy/{}", 1, None, False),
    "result-delete": ("DELETE", "/api/backtest/results/{}", 1, None, False),
    "result-delete-all": ("DELETE", "/api/backtest/results", 0, None, False),
    "run-delete": ("DELETE", "/api/backtest/runs/{}", 1, None, False),
    "run-delete-all": ("DELETE", "/api/backtest/runs", 0, None, False),
    "testset-delete": ("DELETE", "/api/testsets/{}", 1, None, False),
    "leaderboard-delete": ("DELETE", "/api/leaderboard/{}", 1, None, False),
    "playground-setup-delete": ("DELETE", "/api/chart-playground/setups/{}", 1, None, False),
    "knowledge-reset": ("DELETE", "/api/knowledge/reset", 0, None, False),
    # Sammellöschen (POST, --ids 1,2,3)
    "indicator-config-bulk-delete": ("POST", "/api/config/indicator/bulk-delete", 0, "ids", False),
    "result-bulk-delete": ("POST", "/api/backtest/results/bulk-delete", 0, "ids", False),
    "run-bulk-delete": ("POST", "/api/backtest/runs/bulk-delete", 0, "ids", False),
    "playground-setup-bulk-delete": ("POST", "/api/chart-playground/setups/bulk-delete", 0, "ids", False),
    # Aktionen / Toggles (POST, kein Body)
    "indicator-config-generate-labels": ("POST", "/api/config/indicator/{}/generate-labels", 1, None, False),
    "iteration-favorite": ("POST", "/api/strategy/iterations/{}/favorite", 1, None, False),
    "iteration-doc-favorite": ("POST", "/api/strategy/iterations/{}/doc_favorite", 1, None, False),
    "result-favorite": ("POST", "/api/backtest/results/{}/favorite", 1, None, False),
    "result-doc-favorite": ("POST", "/api/backtest/results/{}/doc_favorite", 1, None, False),
    "concept-vault-create": ("POST", "/api/strategy/concepts/{}/vault-create", 1, None, False),
    "iteration-vault-create": ("POST", "/api/strategy/iterations/{}/vault-create", 1, None, False),
    "run-restart": ("POST", "/api/backtest/runs/{}/restart", 1, None, False),
    "result-full-metrics": ("POST", "/api/backtest/results/{}/full-metrics", 1, None, False),
    "run-analyse-start": ("POST", "/api/backtest/runs/{}/analyse/start", 1, None, False),
    "run-analyse-stop": ("POST", "/api/backtest/runs/{}/analyse/stop", 1, None, False),
    "run-analyse-reset": ("POST", "/api/backtest/runs/{}/analyse/reset", 1, None, False),
    "playground-setup-from-result": ("POST", "/api/chart-playground/setups/from-result/{}", 1, None, False),
    # Anlegen (POST, voller Body per --file)
    "strategy-config-create": ("POST", "/api/config/strategy", 0, "file", False),
    "data-download": ("POST", "/api/config/data/download", 0, "file", False),
    "playground-setup-create": ("POST", "/api/chart-playground/setups", 0, "file", False),
    "playground-compute": ("POST", "/api/chart-playground/compute", 0, "file", False),
    "playground-run-backtest": ("POST", "/api/chart-playground/run-backtest", 0, "file", False),
    "playground-run-backtest-lite": ("POST", "/api/chart-playground/run-backtest-lite", 0, "file", False),
    "knowledge-reindex": ("POST", "/api/knowledge/reindex", 0, None, False),
    # Lesen (GET)
    "strategy-config-list": ("GET", "/api/config/strategy", 0, None, False),
    "data-files-list": ("GET", "/api/config/data/files", 0, None, False),
    "data-jobs-list": ("GET", "/api/config/data/jobs", 0, None, True),
    "filters-list": ("GET", "/api/backtest/filters", 0, None, False),
    "run-results": ("GET", "/api/backtest/runs/{}/results", 1, None, True),
    "result-stats": ("GET", "/api/backtest/results/{}/stats", 1, None, False),
    "result-trades": ("GET", "/api/backtest/results/{}/trades", 1, None, False),
    "result-orders": ("GET", "/api/backtest/results/{}/orders", 1, None, False),
    "result-positions": ("GET", "/api/backtest/results/{}/positions", 1, None, False),
    "result-ohlcv": ("GET", "/api/backtest/results/{}/ohlcv", 1, None, False),
    "result-chart-data": ("GET", "/api/backtest/results/{}/chart-data", 1, None, False),
    "result-metrics-level": ("GET", "/api/backtest/results/{}/metrics-level", 1, None, False),
    "run-summary": ("GET", "/api/backtest/runs/{}/analyse/summary", 1, None, False),
    "run-distribution": ("GET", "/api/backtest/runs/{}/analyse/distribution", 1, None, False),
    "run-equity-overview": ("GET", "/api/backtest/runs/{}/analyse/equity-overview", 1, None, True),
    "run-heatmap": ("GET", "/api/backtest/runs/{}/analyse/heatmap", 1, None, True),
    "run-analyse-progress": ("GET", "/api/backtest/runs/{}/analyse/progress", 1, None, False),
    "knowledge-runs-list": ("GET", "/api/knowledge/runs", 0, None, False),
    "knowledge-run": ("GET", "/api/knowledge/runs/{}", 1, None, False),
    "knowledge-stats": ("GET", "/api/knowledge/stats", 0, None, False),
    "playground-sources": ("GET", "/api/chart-playground/sources", 0, None, False),
    "playground-ohlcv": ("GET", "/api/chart-playground/ohlcv", 0, None, True),
    "playground-setup-list": ("GET", "/api/chart-playground/setups", 0, None, False),
}


# Einzel-Verben mit eigener Argument-Form (Liste/Create/Start). Erstes CLI-Argument.
SINGLE_VERBS = {
    "api": api_call,
    "walk-forward-start": walk_forward_start,
    "run-remarks": run_remarks_set,
    "data-update": data_update,
    "data-delete-symbol": data_delete_symbol,
    "concept-list": concept_list,
    "iteration-list": iteration_list,
    "backtest-config-list": backtest_config_list,
    "indicator-config-list": indicator_config_list,
    "result-list": result_list,
    "run-list": run_list,
    "testset-list": testset_list,
    "leaderboard-list": leaderboard_list,
    "symbol-list": symbol_list,
    "playground-indicators": playground_indicators_list,
    "run-parameter-ranking": run_parameter_ranking,
    "run-top-results": run_top_results,
    "run-best": run_best,
    "run-bestwerte": run_bestwerte,
    "run-favorites-reset": run_favorites_reset,
    "concept-create": concept_create,
    "iteration-create": iteration_create,
    "indicator-config-create": indicator_config_create,
    "backtest-config-create": backtest_config_create,
    "testset-create": testset_create,
    "backtest-run-start": backtest_run_start,
    "testset-run-start": testset_run_start,
}


HANDLERS = {
    "concept": concept_read,
    "iteration": iteration_read,
    "indicator-config": indicator_config_read,
    "backtest-config": backtest_config_read,
    "strategy-config": strategy_config_read,
    "result": result_read,
    "run": run_read,
    "testset": testset_read,
    "leaderboard": leaderboard_read,
    "playground-setup": playground_setup_read,
    "knowledge": knowledge_search,
    "vault": vault_list,
}


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    # Einzel-Verben (Liste/Create/Start): erstes Argument ist das Verb, jedes Verb
    # parst seine eigene Argument-Form. Zentrale Fehlerbehandlung inkl. Server-Body.
    verb = args[0].lower()
    if verb in SINGLE_VERBS:
        try:
            return SINGLE_VERBS[verb](args[1:])
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            print(f"## {verb} — HTTP {e.code} {e.reason}\n{body}\n")
            return 1
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
            print(f"## {verb} — {e}\n")
            return 1
        except Exception as e:
            print(f"## {verb} — Fehler: {e}\n")
            return 1

    # Tabellen-Verben (Ändern/Löschen/Aktionen/restliche Reads): generischer Executor.
    if verb in TABLE_VERBS:
        try:
            return _run_table_verb(verb, TABLE_VERBS[verb], args[1:])
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            print(f"## {verb} — HTTP {e.code} {e.reason}\n{body}\n")
            return 1
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
            print(f"## {verb} — {e}\n")
            return 1
        except Exception as e:
            print(f"## {verb} — Fehler: {e}\n")
            return 1

    # Verb-Modi: erstes Argument ist "copy" oder "create-indicator-config", Rest sind Ziel-IDs
    mode = "read"
    if args[0].lower() == "copy":
        mode = "copy"
        args = args[1:]
        if not args:
            print("## copy: keine Ziel-IDs angegeben (z.B. `copy iteration:2 backtest-config:553`)\n")
            return 2
    elif args[0].lower() == "create-indicator-config":
        mode = "create-indicator-config"
        args = args[1:]
        if not args:
            print("## create-indicator-config: keine Result-IDs angegeben (z.B. `create-indicator-config result:2706026:Sharpe`)\n")
            return 2
    if mode == "copy":
        print(f"# Kopier-Aktion (Ziel: {BASE})\n")
    elif mode == "create-indicator-config":
        print(f"# IndicatorConfig aus Result erstellen (Ziel: {BASE})\n")
    else:
        print(f"# Briefing (Quelle: {BASE})\n")
    rc = 0
    for a in args:
        if mode == "create-indicator-config":
            rid, seg = _parse_result_segment_arg(a)
            if not rid:
                print(f"## Konnte nicht parsen: `{a}` (erwartet result:ID oder result:ID:Segment)\n")
                rc = 1
                continue
            try:
                indicator_config_create_from_result(rid, seg)
            except urllib.error.HTTPError as e:
                print(f"## result:{rid} — HTTP {e.code} {e.reason}\n")
                rc = 1
            except Exception as e:
                print(f"## result:{rid} — Fehler: {e}\n")
                rc = 1
            continue
        t, val = parse_arg(a)
        if not t:
            print(f"## Konnte nicht parsen: `{a}`\n")
            rc = 1
            continue
        if mode == "copy":
            handler = COPY_HANDLERS.get(t)
            if not handler:
                print(f"## copy {t}:{val} — nicht kopierbar (kein Copy-Endpoint; kopierbar: iteration, backtest-config, indicator-config)\n")
                rc = 1
                continue
        else:
            handler = HANDLERS[t]
        try:
            handler(val)
        except urllib.error.HTTPError as e:
            print(f"## {t}:{val} — HTTP {e.code} {e.reason}\n")
            rc = 1
        except Exception as e:
            print(f"## {t}:{val} — Fehler: {e}\n")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())

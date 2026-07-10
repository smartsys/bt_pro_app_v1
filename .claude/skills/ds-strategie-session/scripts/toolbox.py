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
  python3 toolbox.py run-favorites-list --testset-run 6       # markierte Favoriten-Results ausgeben (reiner Read); Selektoren/Flags wie run-favorites-reset
  python3 toolbox.py result-lookup --run 1812 --params "vwma_length=20,atr_mult=2.5"    # Result(s) per Parameter-Werten nachschlagen (Subset, serverseitig)
                                                              #   [--tolerance 1] = skalare Nachbarschaft (±t je Parameter) | [--tolerance-steps 1] = ±N Raster-Schritte je Achse, [--limit 20]
                                                              #   [--summary] = Plateau-Score (Median/Mittel/Streuung/Anteil profitabel) statt Trefferliste
  python3 toolbox.py result-query --run 1812 --where "sharpe_ratio>=1.5,total_trades>=100"  # kombinierte Metrik-Filter (nur >= und <=, UND-verknüpft)
                                                              #   [--sort <metrik>] [--direction asc|desc] [--limit 20]; Metriken: total_return_pct,
                                                              #   win_rate_pct, sharpe_ratio, profit_factor, max_drawdown_pct, total_trades
  python3 toolbox.py kreuztest --from-run 10 --to-run 11      # Bestwerte (rote Doku-Favoriten) aus Run A in Run B nachschlagen, Vergleichstabelle
                                                              #   [--user] = gelbe Sterne zusätzlich, [--tolerance <t> | --tolerance-steps <N>] wie result-lookup
  python3 toolbox.py kreuztest --from-testset-run 2 --to-testset-run 3  # ganze Testset-Läufe: Runs werden per Symbol+Timeframe gepaart (Walk-Forward)
  python3 toolbox.py combo-trace --testset-run 3 --params "vwma_length=2,…"  # eine Kombination über eine Run-Menge verfolgen (1:N); Selektoren wie
                                                              #   run-bestwerte (--run | --strategy [--version] | --iteration | --testset-run)
  --json (bei result-list, run-top-results, run-best, run-favorites-list, result-lookup,
          result-query, kreuztest, combo-trace): rohe Items als JSON statt Markdown — für Folge-Analysen
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
  python3 toolbox.py indicator-config-set --id 4 [--concept 2 --iteration 2 --name "..." --description "..."]
        Teil-Update (PATCH): schreibt NUR die gesetzten Felder; config_json/_stops bleiben unangetastet.
        Kernfall: bestehende Config nachträglich einem Konzept/einer Iteration zuweisen.
  python3 toolbox.py indicator-config-labels --id 4 [--name-freetext "..." --desc-freetext "..." --save]
        Standard-Notation erzeugen (preview-labels), optional Freitext setzen (Titel: `<Notation> : <Freitext>`,
        Beschreibung: `<Freitext> | <Auflistung>`), mit --save via PATCH nur Name/Beschreibung zurückschreiben.
        Ohne --save nur Vorschau. Freitext ausschreiben, keine kryptischen Kürzel.
  python3 toolbox.py backtest-config-create --file backtest.json
        --file = der volle Body (Pflicht: name, start, end, ohlc_start, ohlc_end; Defaults: symbol BTCUSDT, exchange binance, timeframe 4h, size 100, size_type value, init_cash 100, fees 0.001).
  python3 toolbox.py testset-create --name "OoS 22/23" --configs 552,553,554 [--description ...]

Ausführen (start — Schreib-Aktion, ID-basiert):
  python3 toolbox.py backtest-run-start --backtest-config 552 --indicator-config 1970 --iteration 41
  python3 toolbox.py testset-run-start --testset 293 --iteration 41 --indicator-config 1973
  python3 toolbox.py walk-forward-start --result 2706026 --months 6

Gezielt bearbeiten (Schreib-Aktion — GET, EINEN Teil ändern, zurückschreiben; der Rest
bleibt bit-genau). Für den Alltagsfall "kopieren und einen Indikator/eine Regel/ein Feld
ergänzen" — KEIN kompletter Body nötig:
  Felder (Meta/flach):
    concept-set --id N [--name --slug --category --description --status]
    iteration-set --id N [--version-name --description --status]
    backtest-config-set --id N [--symbol --exchange --timeframe --start --end --ohlc-start
                                --ohlc-end --size --size-type --init-cash --fees --name --description]
  Indikatoren (spec_json.indicators bzw. config_json):
    iteration-indicator-set --id N --name <key> --file frag.json [--replace]
    iteration-indicator-remove --id N --name <key>
    indicator-config-indicator-set --id N --name <key> --file frag.json [--replace]
    indicator-config-indicator-remove --id N --name <key>
        frag.json = ein Indikator-Block, z.B. {"indicator":"talib:SMA","tf":"4h","close":"close","timeperiod":50}.
        Existiert der Key, wird gemergt: nur die genannten Parameter ändern sich, der Rest
        des Blocks bleibt bit-genau. Einzelnen Wert ändern: --file {"timeperiod":50}.
        --replace ersetzt den Block komplett (alles Nicht-Genannte fällt weg).
        In der Config dürfen Param-Werte arange-Ranges sein (Multiparameter): "timeperiod":{"type":"arange",...}.
  Stops (config_json._stops, einzeln):
    indicator-config-stops-set --id N [--tp --sl --td --tsl --tsl-th --delta-format --time-delta-format]
        Zahlen/null werden gecastet, Format-Felder bleiben String; nicht genannte Stops bleiben.
  Regeln (spec_json.rules):
    iteration-condition-add --id N [--exit] [--block K | --new-block [--short]] --file cond.json
    iteration-condition-remove --id N [--exit] --block K [--index J | --remove-block]
        cond.json = eine Bedingung, z.B. {"op":">","lhs":"close","rhs":"indicator:sma:real"} (opt. lhs_shift/rhs_shift).
        Ohne --block hängt condition-add an Block 1 (UND-verknüpft); --new-block macht einen ODER-Block.

Ändern (PUT, voller Body per --file): <bereich>-update --id <n> --file body.json
  Voll-Replace für den ganzen Body. Für gezielte Teiländerungen die "Gezielt bearbeiten"-Verben
  oben nehmen. Braucht man doch den rohen Ist-Body: `api GET <route>` (roher JSON-Dump), editieren,
  per <bereich>-update --file zurück.
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
import statistics
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
            # GEÄNDERT: tf nicht mehr filtern — der Rechen-Timeframe ist laufzeit-wirksam
            # (fehlt er beim Zurückschreiben, bricht der Lauf mit ValueError ab)
            params = ", ".join(f"{k}={v}" for k, v in p.items() if k not in ("enabled", "indicator"))
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
        # GEÄNDERT: tf nicht mehr filtern — der Rechen-Timeframe ist laufzeit-wirksam
        # (fehlt er beim Zurückschreiben, bricht der Lauf mit ValueError ab)
        params = ", ".join(f"{k}={v}" for k, v in p.items() if k not in ("enabled", "indicator"))
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


def _maybe_json(flags: dict, payload) -> bool:
    """Gibt bei --json das rohe Payload als JSON aus und meldet True (Verb ist fertig).

    Maschinenlesbarer Ausgabe-Modus für Folge-Analysen — statt die formatierten
    Markdown-Zeilen zurückzuparsen, bekommt der Aufrufer die Items direkt.
    """
    if not flags.get("json"):
        return False
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return True


def _strip_json_flag(args: list) -> tuple:
    """Zieht --json aus positionalen Argument-Listen heraus -> (args_ohne_flag, json_an)."""
    return [a for a in args if a != "--json"], "--json" in args


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
    if _maybe_json(f, {"total": len(items), "items": items}):
        return 0
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
    args, json_out = _strip_json_flag(args)
    if not args:
        raise ValueError("run-top-results braucht <run_id> [metric] [limit] [direction] [--json]")
    run_id = int(args[0])
    metric = args[1] if len(args) > 1 else "sharpe_ratio"
    limit = args[2] if len(args) > 2 else "20"
    direction = args[3] if len(args) > 3 else "desc"
    qs = urllib.parse.urlencode({"metric": metric, "limit": limit, "direction": direction})
    d = fetch(f"/api/backtest/runs/{run_id}/analyse/top-results?{qs}")
    results = d.get("results") or []
    if _maybe_json({"json": json_out}, {"total": len(results), "items": results}):
        return 0
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
    # GEAENDERT: ToDo 10 — alle Indizes +1 (neue Bestwert-Badge-Spalte an Index 3 im /results/dt)
    "sharpe_ratio": 14, "max_drawdown_pct": 16, "total_trades": 17,
    "win_rate_pct": 18, "profit_factor": 19, "total_return_pct": 20,
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
    args, json_out = _strip_json_flag(args)
    if len(args) < 2:
        raise ValueError("run-best braucht <run_id> <metrik> [min_trades=30] [limit=1] [--json]")
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
    if _maybe_json({"json": json_out}, {"total": n, "items": rows}):
        return 0
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


def result_query(args: list) -> int:
    """Results eines Runs mit kombinierten Metrik-Filtern abfragen.

    Flags: --run <id> --where "sharpe_ratio>=1.5,total_trades>=100,max_drawdown_pct>=-40"
           [--sort <metrik>] [--direction asc|desc] [--limit <n=20>] [--json]
    Bedingungen nur >= und <=, UND-verknüpft — sie werden 1:1 auf die
    serverseitigen _min/_max-Filter des dt-Endpunkts abgebildet. Erlaubte
    Metriken: die Keys aus _DT_SORT_IDX (total_return_pct, win_rate_pct,
    sharpe_ratio, profit_factor, max_drawdown_pct, total_trades).
    """
    f = _parse_flags(args)
    run_id = int(_require(f, "run", "result-query"))
    raw = _require(f, "where", "result-query")
    sort = f.get("sort", "total_return_pct")
    if sort not in _DT_SORT_IDX:
        raise ValueError(f"Unbekannte Sortier-Metrik {sort!r}. Erlaubt: {', '.join(_DT_SORT_IDX)}")
    direction = f.get("direction", "desc")
    if direction not in ("asc", "desc"):
        raise ValueError("--direction erlaubt nur asc|desc")
    limit = int(f.get("limit", 20))

    params = {
        "run_id": run_id,
        "order[0][column]": _DT_SORT_IDX[sort], "order[0][dir]": direction,
        "start": 0, "length": limit, "draw": 1,
    }
    conds = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\w+)\s*(>=|<=)\s*(-?\d+(?:\.\d+)?)$", part)
        if not m:
            raise ValueError(f"--where erwartet <metrik>>=<wert> oder <metrik><=<wert>, bekommen: {part!r}")
        metric, op, val = m.groups()
        if metric not in _DT_SORT_IDX:
            raise ValueError(f"Unbekannte Metrik {metric!r}. Erlaubt: {', '.join(_DT_SORT_IDX)}")
        params[f"{metric}_{'min' if op == '>=' else 'max'}"] = val
        conds.append(part)
    if not conds:
        raise ValueError("--where ist leer")

    dd = fetch(f"/api/backtest/results/dt?{urllib.parse.urlencode(params)}")
    rows = dd.get("data") or []
    n = dd.get("recordsFiltered")
    if _maybe_json(f, {"total": n, "items": rows}):
        return 0
    print(f"## Result-Query Run {run_id} — {' UND '.join(conds)} — Sortierung {sort} {direction} ({n} Treffer, Top {limit})")
    if not rows:
        print("- (keine Treffer)")
    for r in rows:
        print(f"- {_fmt_result_line(r)}")
    print()
    return 0


# ---------------------------------------------------------------------------
# Result-Lookup per Parameter-Werten (result-lookup) + Kreuz-Test (kreuztest).
# Serverseitig über GET /api/backtest/runs/{id}/results/lookup — exakter Lookup
# einer Kombination oder Nachbarschafts-Modus (±tolerance je Parameter,
# Plateau-Prüfung). kreuztest schlägt die markierten Bestwerte aus Run A in
# Run B nach und stellt die Metriken gegenüber.
# ---------------------------------------------------------------------------

def _parse_params_flag(raw: str) -> dict:
    """Zerlegt --params "key=wert,key2=wert2" in ein Dict (Werte verbatim als Strings)."""
    wanted: dict = {}
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"--params erwartet key=wert-Paare (Komma-getrennt), bekommen: {part!r}")
        k, v = part.split("=", 1)
        wanted[k.strip()] = v.strip()
    if not wanted:
        raise ValueError("--params ist leer")
    return wanted


def _lookup(run_id: int, params: dict, tolerance=None, limit=None, tolerance_steps=None) -> dict:
    """Ruft die Lookup-Route auf und gibt deren data-Block (items/total) zurück."""
    qp = dict(params)
    if tolerance is not None:
        qp["tolerance"] = tolerance
    if tolerance_steps is not None:
        qp["tolerance_steps"] = tolerance_steps
    if limit is not None:
        qp["limit"] = limit
    return fetch(f"/api/backtest/runs/{run_id}/results/lookup?{urllib.parse.urlencode(qp)}")["data"]


def _tolerance_kwargs(f: dict) -> dict:
    """Liest --tolerance / --tolerance-steps in _lookup-kwargs (schließen sich aus)."""
    tol = f.get("tolerance")
    steps = f.get("tolerance-steps")
    if tol and steps:
        raise ValueError("--tolerance und --tolerance-steps schließen sich aus — nur eins angeben")
    kwargs: dict = {}
    if tol:
        kwargs["tolerance"] = tol
    if steps:
        kwargs["tolerance_steps"] = steps
    return kwargs


def _tolerance_label(f: dict) -> str:
    """Einheitlicher Toleranz-Zusatz für die Markdown-Überschriften."""
    if f.get("tolerance-steps"):
        return f" · Toleranz ±{f['tolerance-steps']} Schritt(e)"
    if f.get("tolerance"):
        return f" · Toleranz ±{f['tolerance']}"
    return ""


def _neighborhood_summary(items: list) -> dict:
    """Verdichtet eine Nachbarschafts-Treffermenge zum Plateau-Score.

    Beantwortet „Plateau oder Nadel?" in wenigen Kennzahlen statt N Zeilen:
    Median/Mittel/Streuung des Total Return, Anteil profitabel, Bester/Schlechtester.
    """
    rets = [(r["total_return_pct"], r["id"]) for r in items
            if isinstance(r.get("total_return_pct"), (int, float))]
    if not rets:
        return {"n": len(items), "n_mit_return": 0}
    values = [v for v, _ in rets]
    best = max(rets)
    worst = min(rets)
    return {
        "n": len(items),
        "n_mit_return": len(values),
        "anteil_profitabel_pct": round(100.0 * sum(1 for v in values if v > 0) / len(values), 1),
        "return_median": round(statistics.median(values), 2),
        "return_mittel": round(statistics.fmean(values), 2),
        "return_streuung": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
        "return_bester": {"result_id": best[1], "total_return_pct": round(best[0], 2)},
        "return_schlechtester": {"result_id": worst[1], "total_return_pct": round(worst[0], 2)},
    }


def result_lookup(args: list) -> int:
    """Results eines Runs per Parameter-Werten nachschlagen (serverseitig).

    Flags: --run <id> --params "key=wert,key2=wert2"
           [--tolerance <t> | --tolerance-steps <N>] [--limit <n=20>] [--summary] [--json]
    Ohne Toleranz exakter Lookup der einen Kombination; mit --tolerance alle
    Results, deren Parameter je ±t (skalar) um die Zielwerte liegen; mit
    --tolerance-steps N je Parameter ±N Raster-Schritte (Schrittweite aus dem
    Run abgeleitet — bildet die echte ±N-Schritt-Nachbarschaft auch bei
    ungleichen Schrittweiten je Achse). Subset: nur die angegebenen Keys müssen
    passen. Unbekannte Parameter-Namen meldet der Server mit den vorhandenen
    Namen des Runs. --summary verdichtet die Nachbarschaft zum Plateau-Score
    (holt dafür die volle Treffermenge, --limit spielt dann keine Rolle).
    """
    f = _parse_flags(args)
    run_id = int(_require(f, "run", "result-lookup"))
    wanted = _parse_params_flag(_require(f, "params", "result-lookup"))
    pstr = ", ".join(f"{k}={v}" for k, v in wanted.items())
    tkw = _tolerance_kwargs(f)
    tol = _tolerance_label(f)

    if f.get("summary"):
        d = _lookup(run_id, wanted, limit=100000, **tkw)
        items = d.get("items") or []
        summ = _neighborhood_summary(items)
        if _maybe_json(f, summ):
            return 0
        print(f"## Plateau-Score Run {run_id} — {pstr}{tol}")
        if not items:
            print("- (keine Treffer)\n")
            return 0
        print(f"- Nachbarschaft: {summ['n']} Results · {summ['anteil_profitabel_pct']}% profitabel")
        print(f"- Total Return: Median {num(summ['return_median'])}% · Mittel {num(summ['return_mittel'])}% · "
              f"Streuung {num(summ['return_streuung'])}")
        print(f"- Bester: result:{summ['return_bester']['result_id']} ({num(summ['return_bester']['total_return_pct'])}%) · "
              f"Schlechtester: result:{summ['return_schlechtester']['result_id']} "
              f"({num(summ['return_schlechtester']['total_return_pct'])}%)")
        print()
        return 0

    out_limit = int(f.get("limit", 20))
    d = _lookup(run_id, wanted, limit=out_limit, **tkw)
    items = d.get("items") or []
    total = d.get("total") or 0
    if _maybe_json(f, {"total": total, "items": items}):
        return 0

    print(f"## Result-Lookup Run {run_id} — {pstr}{tol} ({total} Treffer)")
    if not items:
        print("- (keine Treffer)")
    for r in items:
        print(f"- {_fmt_result_line(r)}")
    if total > len(items):
        print(f"- … {total - len(items)} weitere Treffer (--limit erhöhen)")
    print()
    return 0


def _favorite_results(run_id: int, kinds: list) -> list:
    """Markierte Favoriten-Results eines Runs (dedupliziert über die Sterne-Arten)."""
    favorites: list = []
    seen: set = set()
    for kind in kinds:
        col_idx, field, _suffix, _label = _FAV_KINDS[kind]
        rows, _ = _dt_query(run_id, col_idx, length=200)
        for r in rows:
            if r.get(field) and r["id"] not in seen:
                seen.add(r["id"])
                favorites.append(r)
    return favorites


def _kreuztest_rows(run_a: int, run_b: int, kinds: list, tol_kwargs: dict) -> list:
    """Vergleichszeilen eines Run-Paars: je Favorit aus A das Gegenstück aus B (oder None)."""
    rows = []
    for a in sorted(_favorite_results(run_a, kinds), key=lambda x: x["id"]):
        num_params = {k: v for k, v in (a.get("actual_params") or {}).items()
                      if isinstance(v, (int, float)) and not isinstance(v, bool)}
        b = None
        if num_params:
            items = _lookup(run_b, num_params, limit=1, **tol_kwargs).get("items") or []
            b = items[0] if items else None
        rows.append({"params": num_params, "a": a, "b": b})
    return rows


def _print_kreuztest_table(rows: list) -> None:
    """Markdown-Vergleichstabelle für die Zeilen eines Run-Paars."""
    print("| Params | Result A→B | Ret % | Sharpe | PF | WinR % | Trades |")
    print("|---|---|---|---|---|---|---|")
    for row in rows:
        a, b = row["a"], row["b"]

        def pair(key: str) -> str:
            return f"{num(a.get(key))} → {num(b.get(key)) if b else '—'}"

        pstr = ", ".join(f"{k}={v}" for k, v in row["params"].items()) or "(keine numerischen Params)"
        ab = f"{a['id']} → {b['id'] if b else 'nicht gefunden'}"
        print(f"| {pstr} | {ab} | {pair('total_return_pct')} | {pair('sharpe_ratio')} | "
              f"{pair('profit_factor')} | {pair('win_rate_pct')} | "
              f"{a.get('total_trades')} → {b.get('total_trades') if b else '—'} |")


def kreuztest(args: list) -> int:
    """Markierte Bestwerte aus Run/Testset-Lauf A in B nachschlagen (Vergleichstabelle).

    Flags: --from-run <A> --to-run <B>                        (Einzel-Paar)
       oder --from-testset-run <A> --to-testset-run <B>       (ganze Fenster/Testsets,
            Runs werden per Symbol+Timeframe gepaart — BTC-Run zu BTC-Run usw.)
       dazu [--user] [--tolerance <t> | --tolerance-steps <N>] [--json]
    Quelle sind die roten Doku-Favoriten (Bestwerte) der A-Seite; --user nimmt
    zusätzlich die gelben User-Sterne. Je Kombination wird das Result mit
    denselben Parameterwerten auf der B-Seite nachgeschlagen (nur numerische
    Parameter; run-gebundene Keys wie symbol bleiben außen vor). Mit
    --tolerance (skalar) oder --tolerance-steps (±N Raster-Schritte je
    Parameter) zählt bei mehreren Nachbarschafts-Treffern der beste Total Return.
    """
    f = _parse_flags(args)
    kinds = ["doc"] + (["user"] if f.get("user") else [])
    tol_kwargs = _tolerance_kwargs(f)
    label = "rote Doku-Favoriten" + (" + gelbe User-Sterne" if f.get("user") else "")
    tol = _tolerance_label(f)

    # Paar-Auflösung: Einzel-Paar oder Testset-Lauf gegen Testset-Lauf.
    unmatched: list = []
    if f.get("from-testset-run") or f.get("to-testset-run"):
        ts_a = int(_require(f, "from-testset-run", "kreuztest"))
        ts_b = int(_require(f, "to-testset-run", "kreuztest"))
        runs_a = fetch(f"/api/backtest/runs?testset_run_id={ts_a}&limit=10000")["data"]["items"]
        runs_b = fetch(f"/api/backtest/runs?testset_run_id={ts_b}&limit=10000")["data"]["items"]
        by_key_b = {(r.get("symbol"), r.get("timeframe")): r for r in runs_b}
        pairs = []
        for ra in sorted(runs_a, key=lambda x: x["id"]):
            key = (ra.get("symbol"), ra.get("timeframe"))
            rb = by_key_b.pop(key, None)
            if rb is None:
                unmatched.append(f"run:{ra['id']} ({key[0]} {key[1]}) ohne Gegenstück in testset-run:{ts_b}")
            else:
                pairs.append((ra["id"], rb["id"], f"{key[0]} {key[1]}"))
        unmatched += [f"run:{r['id']} ({k[0]} {k[1]}) ohne Gegenstück in testset-run:{ts_a}"
                      for k, r in by_key_b.items()]
        scope = f"testset-run:{ts_a} → testset-run:{ts_b}"
    else:
        run_a = int(_require(f, "from-run", "kreuztest"))
        run_b = int(_require(f, "to-run", "kreuztest"))
        pairs = [(run_a, run_b, "")]
        scope = f"run:{run_a} → run:{run_b}"

    results = [{"run_a": a, "run_b": b, "match": m, "rows": _kreuztest_rows(a, b, kinds, tol_kwargs)}
               for a, b, m in pairs]
    if _maybe_json(f, {"scope": scope, "pairs": results, "unmatched": unmatched}):
        return 0

    print(f"## Kreuz-Test {scope} — {label}{tol} ({len(pairs)} Paar(e))")
    for entry in results:
        suffix = f" ({entry['match']})" if entry["match"] else ""
        print(f"\n### run:{entry['run_a']} → run:{entry['run_b']}{suffix} — {len(entry['rows'])} Kombination(en)")
        if not entry["rows"]:
            print("- (keine markierten Results auf der A-Seite)")
            continue
        _print_kreuztest_table(entry["rows"])
    for line in unmatched:
        print(f"- OHNE PAAR: {line}")
    print()
    return 0


def combo_trace(args: list) -> int:
    """Eine Parameterkombination über eine Run-Menge verfolgen (1:N-Kreuz-Test).

    Flags: --params "key=wert,key2=wert2" + Selektor wie run-bestwerte
           (--run <id> | --strategy <slug> [--version <n>] | --iteration <id> |
            --testset-run <id>)   [--tolerance <t> | --tolerance-steps <N>] [--limit <n=200>] [--json]
    Schlägt die Kombination in jedem Run des Scopes nach (serverseitig über
    /api/backtest/results/lookup) und listet je Treffer Run-Kontext
    (Symbol/Timeframe) plus Kennzahlen. Runs ohne Treffer werden ausgewiesen.
    Im Schritt-Modus (--tolerance-steps) wird die Schrittweite je Run einzeln
    abgeleitet (Raster können differieren).
    """
    f = _parse_flags(args)
    wanted = _parse_params_flag(_require(f, "params", "combo-trace"))
    tkw = _tolerance_kwargs(f)
    runs, scope = _resolve_runs(f, "combo-trace")
    if not runs:
        print(f"## Kombinations-Verfolgung — {scope}\n- (keine Runs)\n")
        return 0
    run_ids = sorted(r["id"] for r in runs)

    qp = dict(wanted)
    qp["run_ids"] = ",".join(str(i) for i in run_ids)
    if "tolerance" in tkw:
        qp["tolerance"] = tkw["tolerance"]
    if "tolerance_steps" in tkw:
        qp["tolerance_steps"] = tkw["tolerance_steps"]
    qp["limit"] = f.get("limit", 200)
    d = fetch(f"/api/backtest/results/lookup?{urllib.parse.urlencode(qp)}")["data"]
    items = d.get("items") or []
    total = d.get("total") or 0
    if _maybe_json(f, {"scope": scope, "run_ids": run_ids, "total": total, "items": items}):
        return 0

    pstr = ", ".join(f"{k}={v}" for k, v in wanted.items())
    tol = _tolerance_label(f)
    print(f"## Kombinations-Verfolgung — {scope} ({len(run_ids)} Run(s)) — {pstr}{tol} ({total} Treffer)")
    hit_runs = set()
    for r in items:
        hit_runs.add(r["run_id"])
        print(f"- run:{r['run_id']} {r.get('symbol')} {r.get('timeframe')} — {_fmt_result_line(r)}")
    if total > len(items):
        print(f"- … {total - len(items)} weitere Treffer (--limit erhöhen)")
    missing = [i for i in run_ids if i not in hit_runs]
    if missing:
        print(f"- OHNE TREFFER: {', '.join(f'run:{i}' for i in missing)}")
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


# Stabile Bestwert-Keys in kanonischer Reihenfolge — parallel zu den vier Einträgen von
# _bestwerte_for_run. Single Source des Klartext-Labels ist der Server
# (services/api/utils/best_criteria_labels.py); hier stehen NUR die Keys.
_BESTWERTE_KEYS = ["max_return", "winrate_band", "sharpe_band", "pf_min30"]


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
    # GEAENDERT: ToDo 10 — gewonnene Bestwert-Kriterien anhaengen. Der Server liefert
    # Badge-Objekte {short, long}; fuer die Text-Ausgabe die Langform verwenden.
    crit = r.get("best_criteria") or []
    labels = [c.get("long") if isinstance(c, dict) else c for c in crit]
    crit_str = f"  ·  Bestwert: {', '.join(labels)}" if labels else ""
    return line + (f"  ·  {pstr}" if pstr else "") + crit_str


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
        # GEAENDERT: ToDo 10 — pro Sieger-Result die gewonnenen Kriterium-Keys sammeln
        # (ein Result kann mehrere Kriterien gleichzeitig gewinnen) und den roten Stern
        # samt Keys idempotent ueber den mark-Endpunkt setzen (kein Toggle, ueberschreibt
        # die Keys auch bei bereits gesetztem Stern).
        run_keys: dict = {}       # res_id -> [keys] (geordnet, dedup)
        was_starred: dict = {}    # res_id -> war vor diesem Lauf schon roter Favorit?
        for idx, (label, res, info) in enumerate(_bestwerte_for_run(rid)):
            suffix = f" — {info}" if info else ""
            if not res:
                print(f"- **{label}**{suffix}: kein Result")
                continue
            print(f"- **{label}**{suffix}")
            print(f"  - {_fmt_result_line(res)}")
            res_id = res["id"]
            key = _BESTWERTE_KEYS[idx]
            keys = run_keys.setdefault(res_id, [])
            if key not in keys:
                keys.append(key)
            was_starred[res_id] = bool(res.get("is_doc_favorite"))
        # Markieren: pro Result einmal, mit allen gewonnenen Keys
        for res_id, keys in run_keys.items():
            post(f"/api/backtest/results/{res_id}/doc_favorite/mark", {"criteria": keys})
            now_on.add(res_id)
            if not was_starred.get(res_id):
                newly.add(res_id)
            state = "gesetzt" if not was_starred.get(res_id) else "aktualisiert"
            print(f"- result:{res_id} — roter Stern {state} (Kriterien: {', '.join(keys)})")

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


def run_favorites_list(args: list) -> int:
    """Aktuell markierte Favoriten-Results einer Run-Menge ausgeben (reiner Read).

    Flags wie run-favorites-reset: --run <id> | --strategy <slug> [--version <n>] |
           --iteration <id> | --testset-run <id>   [--doc] [--user]
    Ohne --doc/--user werden BEIDE Favoriten-Arten gelistet. Nutzt denselben
    dt-Abruf wie der Reset (Favoriten zuerst sortiert), ändert aber nichts.
    """
    f = _parse_flags(args)
    kinds = [k for k in ("doc", "user") if f.get(k)] or ["doc", "user"]
    runs, scope = _resolve_runs(f, "run-favorites-list")

    # Erst einsammeln (auch für --json), dann ausgeben.
    collected: list = []
    for run in sorted(runs, key=lambda x: x["id"]):
        rid = run["id"]
        for kind in kinds:
            col_idx, field, _suffix, label = _FAV_KINDS[kind]
            # Favoriten sortieren zuerst -> length deckt jede realistische Favoriten-Zahl je Run ab
            rows, _ = _dt_query(rid, col_idx, length=200)
            marked = [r for r in rows if r.get(field)]
            collected.append({"run_id": rid, "kind": kind, "label": label, "results": marked})
    if _maybe_json(f, {"scope": scope, "groups": collected}):
        return 0

    kind_labels = ", ".join(_FAV_KINDS[k][3] for k in kinds)
    print(f"## Favoriten — {scope} ({len(runs)} Run(s)) — {kind_labels}")
    if not runs:
        print("- (keine Runs)\n")
        return 0

    found_total = 0
    for group in collected:
        found_total += len(group["results"])
        print(f"- run:{group['run_id']} · {group['label']}: {len(group['results'])}")
        for r in group["results"]:
            print(f"  - {_fmt_result_line(r)}")

    print(f"\n**{found_total} Favoriten-Markierungen gefunden.**\n")
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


def indicator_config_set(args: list) -> int:
    """Bestehende Indicator-Config gezielt aktualisieren (nur die gesetzten Felder).

    Flags: --id <n> (oder erstes Positional) und mindestens eines von
      --concept <n> · --iteration <n> · --name "..." · --description "..."
    Nutzt PATCH /api/config/indicator/{id} (Teil-Update): config_json, _stops und
    alle nicht übergebenen Felder bleiben bit-genau unangetastet. Kernfall:
    nachträgliche Konzept-/Iterations-Verknüpfung einer Config.
    """
    f = _parse_flags(args)
    pos = f.get("_positional", [])
    cid = f.get("id") or (pos[0] if pos else None)
    if not cid:
        raise ValueError("indicator-config-set: ID fehlt (--id <n> oder erstes Argument)")
    body: dict = {}
    if f.get("concept"):
        body["strategy_concept_id"] = int(f["concept"])
    if f.get("iteration"):
        body["strategy_iteration_id"] = int(f["iteration"])
    if f.get("name") and f.get("name") is not True:
        body["name"] = f["name"]
    if f.get("description") and f.get("description") is not True:
        body["description"] = f["description"]
    if not body:
        raise ValueError("indicator-config-set: mindestens ein Feld nötig (--concept | --iteration | --name | --description)")
    d = request("PATCH", f"/api/config/indicator/{int(cid)}", body)["data"]
    print(f"## indicator-config-set: OK — Config {d['id']} aktualisiert "
          f"(Concept {d.get('strategy_concept_id')} · Iter {d.get('strategy_iteration_id')} · {d.get('name')})\n")
    return 0


def indicator_config_labels(args: list) -> int:
    """Standard-Notation einer Config erzeugen, optional um Freitext erweitern, optional speichern.

    Flags: --id <n> (oder erstes Positional)
           [--name-freetext "..."]  kurze lesbare Kennung, hängt hinten per " : " an den Titel
           [--desc-freetext "..."]  Freitext, steht VOR der Auflistung: "<Freitext> | <Auflistung>"
           [--save]                 Ergebnis via PATCH zurückschreiben
    Bildet den Frontend-Flow nach: dieselbe zustandslose Route
    (/api/config/indicator/preview-labels, einzige Notations-Wahrheit) liefert Name +
    Indikator-Auflistung; der KI-Freitext wird an die richtige Stelle gesetzt und getrennt
    gespeichert. Freitext immer ausschreiben, keine kryptischen Kürzel. Ohne --save nur Anzeige.
    """
    f = _parse_flags(args)
    pos = f.get("_positional", [])
    cid = f.get("id") or (pos[0] if pos else None)
    if not cid:
        raise ValueError("indicator-config-labels: ID fehlt (--id <n> oder erstes Argument)")
    d = fetch(f"/api/config/indicator/{int(cid)}")["data"]
    labels = _preview_labels(d.get("config_json") or {},
                             d.get("strategy_concept_id"), d.get("strategy_iteration_id"))
    name = labels.get("name") or ""
    description = labels.get("description") or ""
    name_freetext = f.get("name-freetext")
    desc_freetext = f.get("desc-freetext")
    # Titel-Freitext hängt hinten per " : " (kurze, lesbare Kennung: Symbol + Regime)
    if name_freetext and name_freetext is not True:
        name = f"{name} : {name_freetext}"
    # Beschreibungs-Freitext steht VOR der Auflistung, per " | " getrennt
    if desc_freetext and desc_freetext is not True:
        description = f"{desc_freetext} | {description}"

    print(f"## indicator-config-labels — Config {int(cid)}")
    print(f"- Name: {name}")
    print(f"- Beschreibung: {description}")
    if f.get("save"):
        upd = request("PATCH", f"/api/config/indicator/{int(cid)}",
                      {"name": name, "description": description})["data"]
        print(f"- gespeichert (PATCH): Config {upd['id']}")
    else:
        print("- nur Vorschau (kein --save) — mit --save zurückschreiben")
    print()
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


# ---------------------------------------------------------------------------
# Bearbeitungs-Verben (add/remove/change). Gemeinsames Muster: das aktuelle
# Objekt per GET holen, gezielt EINEN Teil aendern (ein Feld, einen Indikator,
# einen Stop, eine Regel-Bedingung) und zurueckschreiben. So muss nie der ganze
# Body von Hand neu gebaut werden. Server-PUTs sind teils partiell (concept,
# iteration), teils Voll-Replace (backtest-config) — der jeweilige Helfer kennt
# das und macht das Richtige.
# ---------------------------------------------------------------------------

def _require_id(f: dict, verb: str) -> int:
    """ID aus --id oder erstem Positional. Wirft, wenn keine da ist."""
    pos = f.get("_positional", [])
    val = f.get("id") or (pos[0] if pos else None)
    if val is None or val is True:
        raise ValueError(f"{verb}: ID fehlt (--id <n> oder als erstes Argument)")
    return int(val)


def _coerce_scalar(v: str):
    """String-Flagwert -> passender JSON-Typ. 'null'->None, 'true'/'false'->bool,
    ganze Zahl->int, Dezimal->float, sonst String. Fuer Feld-/Stop-Werte, deren
    Typ am CLI nicht explizit angegeben wird."""
    if v is True:
        return True
    s = str(v).strip()
    low = s.lower()
    if low in ("null", "none"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _iteration_get_spec(iid: int) -> dict:
    """spec_json einer Iteration holen (leeres Dict wenn None)."""
    return fetch(f"/api/strategy/iterations/{iid}")["data"].get("spec_json") or {}


def _iteration_put_spec(iid: int, spec: dict) -> dict:
    """spec_json partiell zurueckschreiben (nur dieses Feld, PUT ist exclude_unset)."""
    return request("PUT", f"/api/strategy/iterations/{iid}", {"spec_json": spec})["data"]


def _indicator_config_get_json(cid: int) -> dict:
    """config_json einer IndicatorConfig holen (leeres Dict wenn None)."""
    return fetch(f"/api/config/indicator/{cid}")["data"].get("config_json") or {}


def _indicator_config_patch_json(cid: int, cfg: dict) -> dict:
    """config_json per PATCH zurueckschreiben (Teil-Update, Rest der Config bleibt)."""
    return request("PATCH", f"/api/config/indicator/{cid}", {"config_json": cfg})["data"]


# --- Feld-set (Meta/flache Felder) ---

def concept_set(args: list) -> int:
    """concept-set --id N [--name ... --slug ... --category ... --description ... --status ...]

    Partieller PUT: nur gesetzte Felder werden geschrieben (Server: exclude_none).
    """
    f = _parse_flags(args)
    cid = _require_id(f, "concept-set")
    body = {k: f[k] for k in ("name", "slug", "category", "description", "status") if k in f and f[k] is not True}
    if not body:
        raise ValueError("concept-set: mindestens ein Feld noetig (--name | --slug | --category | --description | --status)")
    d = request("PUT", f"/api/strategy/concepts/{cid}", body)["data"]
    print(f"## concept-set: OK — Konzept {d['id']} ({d.get('name')}) aktualisiert: {', '.join(body)}\n")
    return 0


def iteration_set(args: list) -> int:
    """iteration-set --id N [--version-name ... --description ... --status ...]

    Partieller PUT (Server: exclude_unset). Nur Meta-Felder — Indikatoren/Regeln
    laufen ueber die iteration-indicator-*/iteration-condition-*-Verben.
    """
    f = _parse_flags(args)
    iid = _require_id(f, "iteration-set")
    mapping = {"version-name": "version_name", "description": "description", "status": "status"}
    body = {dst: f[src] for src, dst in mapping.items() if src in f and f[src] is not True}
    if not body:
        raise ValueError("iteration-set: mindestens ein Feld noetig (--version-name | --description | --status)")
    d = request("PUT", f"/api/strategy/iterations/{iid}", body)["data"]
    name = d.get("version_name") or d.get("version")
    print(f"## iteration-set: OK — Iteration {d['id']} ({name}) aktualisiert: {', '.join(body)}\n")
    return 0


# Editierbare Felder der BacktestConfig (Voll-Replace-PUT -> GET, mergen, zurueck).
_BACKTEST_FIELDS = (
    "name", "description", "symbol", "exchange", "timeframe", "start", "end",
    "ohlc_start", "ohlc_end", "size", "size_type", "init_cash", "fees",
)
# Kurz-Flags -> Feldname; numerische Felder werden gecastet.
_BACKTEST_NUMERIC = {"size": float, "init_cash": float, "fees": float}


def backtest_config_set(args: list) -> int:
    """backtest-config-set --id N [--symbol ... --timeframe ... --fees ... --size ... --start ... --end ... --name ... ]

    BacktestConfig-PUT ist Voll-Replace: aktuelle Config holen, gesetzte Felder
    drueberlegen, kompletten Body zurueckschreiben. Stops liegen NICHT hier
    (die stecken in der IndicatorConfig unter _stops).
    """
    f = _parse_flags(args)
    cid = _require_id(f, "backtest-config-set")
    # Flag-Wert holen: akzeptiert Feldnamen in Unterstrich- ODER Bindestrich-Form
    # (--ohlc-start == ohlc_start), da _parse_flags die Bindestriche im Key belaesst.
    def _flag(field):
        for key in (field, field.replace("_", "-")):
            if key in f and f[key] is not True:
                return f[key]
        return None
    changed = {k for k in _BACKTEST_FIELDS if _flag(k) is not None}
    if not changed:
        opts = " | ".join("--" + x.replace("_", "-") for x in _BACKTEST_FIELDS)
        raise ValueError(f"backtest-config-set: mindestens ein Feld noetig ({opts})")
    cur = fetch(f"/api/config/backtest/{cid}")["data"]
    body = {k: cur.get(k) for k in _BACKTEST_FIELDS}
    for k in changed:
        v = _flag(k)
        body[k] = _BACKTEST_NUMERIC[k](v) if k in _BACKTEST_NUMERIC else v
    d = request("PUT", f"/api/config/backtest/{cid}", body)["data"]
    print(f"## backtest-config-set: OK — Backtest-Config {d['id']} ({d.get('name')}) aktualisiert: {', '.join(sorted(changed))}\n")
    return 0


# --- Indikatoren (dict-Sammlung) ---

def _merge_indicator_block(coll: dict, name: str, frag: dict, replace: bool) -> tuple:
    """Schreibt frag in coll[name] — als Merge (Default) oder Vollersatz (replace).

    Merge aktualisiert nur die im Fragment genannten Parameter; alles andere im
    bestehenden Block bleibt unangetastet. Damit verliert ein unvollstaendiges
    Fragment keine laufzeit-wirksamen Felder (z.B. tf, dessen Fehlen den Lauf mit
    ValueError abbricht). Neue Keys werden schlicht eingefuegt.

    Returns:
        (verb, block): verb beschreibt die Aktion fuer die Ausgabe, block ist der
        geschriebene Indikator-Block.
    """
    if name not in coll:
        coll[name] = frag
        return "hinzugefuegt", frag
    if replace:
        coll[name] = frag
        return "ersetzt", frag
    block = dict(coll[name])
    block.update(frag)
    coll[name] = block
    geaendert = ", ".join(sorted(frag))
    return f"aktualisiert ({geaendert})", block


def iteration_indicator_set(args: list) -> int:
    """iteration-indicator-set --id N --name <key> --file frag.json [--replace]

    Schreibt einen Indikator nach spec_json.indicators[key]. Existiert der Key,
    werden nur die im Fragment genannten Parameter aktualisiert, der Rest des
    Blocks bleibt bit-genau (Merge, wie indicator-config-stops-set). Mit --replace
    wird der Block komplett ersetzt. frag.json ist der Indikator-Block bzw. der zu
    aendernde Ausschnitt, z.B. {"timeperiod": 50} oder ein voller Block.
    """
    f = _parse_flags(args)
    iid = _require_id(f, "iteration-indicator-set")
    name = _require(f, "name", "iteration-indicator-set")
    frag = _read_json_file(_require(f, "file", "iteration-indicator-set"))
    spec = _iteration_get_spec(iid)
    inds = spec.setdefault("indicators", {})
    # GEÄNDERT: Merge statt Vollersatz — ein unvollstaendiges Fragment darf keine
    # bestehenden Parameter (z.B. tf) still verlieren. --replace erzwingt Vollersatz.
    verb, block = _merge_indicator_block(inds, name, frag, bool(f.get("replace")))
    _iteration_put_spec(iid, spec)
    print(f"## iteration-indicator-set: OK — Iteration {iid}: Indikator '{name}' {verb} ({block.get('indicator')})\n")
    return 0


def iteration_indicator_remove(args: list) -> int:
    """iteration-indicator-remove --id N --name <key>

    Entfernt einen Indikator aus spec_json.indicators. Warnt, wenn Regeln ihn
    noch referenzieren (indicator:<key>:...), bricht aber nicht ab.
    """
    f = _parse_flags(args)
    iid = _require_id(f, "iteration-indicator-remove")
    name = _require(f, "name", "iteration-indicator-remove")
    spec = _iteration_get_spec(iid)
    inds = spec.get("indicators", {})
    if name not in inds:
        raise ValueError(f"iteration-indicator-remove: Indikator '{name}' nicht vorhanden (da: {', '.join(inds) or '—'})")
    del inds[name]
    _iteration_put_spec(iid, spec)
    ref = f"indicator:{name}:"
    still = ref in json.dumps(spec.get("rules", {}))
    warn = f"  WARNUNG: Regeln referenzieren '{name}' noch ({ref}...)\n" if still else ""
    print(f"## iteration-indicator-remove: OK — Iteration {iid}: Indikator '{name}' entfernt\n{warn}")
    return 0


def indicator_config_indicator_set(args: list) -> int:
    """indicator-config-indicator-set --id N --name <key> --file frag.json [--replace]

    Schreibt einen Indikator nach config_json[key]. Existiert der Key, werden nur
    die im Fragment genannten Parameter aktualisiert, der Rest des Blocks bleibt
    bit-genau (Merge); --replace ersetzt den Block komplett. frag.json ist der
    Parameter-Block bzw. der zu aendernde Ausschnitt (Werte skalar ODER als
    arange-Range fuer Multiparameter), z.B. {"indicator": "talib:SMA", "tf": "same",
    "close": "close", "timeperiod": {"type":"arange","start":20,"stop":101,"step":10,"dtype":"int64"}}.
    """
    f = _parse_flags(args)
    cid = _require_id(f, "indicator-config-indicator-set")
    name = _require(f, "name", "indicator-config-indicator-set")
    if name == "_stops":
        raise ValueError("indicator-config-indicator-set: '_stops' ist reserviert — nutze indicator-config-stops-set")
    frag = _read_json_file(_require(f, "file", "indicator-config-indicator-set"))
    cfg = _indicator_config_get_json(cid)
    # GEÄNDERT: Merge statt Vollersatz — siehe _merge_indicator_block
    verb, block = _merge_indicator_block(cfg, name, frag, bool(f.get("replace")))
    _indicator_config_patch_json(cid, cfg)
    print(f"## indicator-config-indicator-set: OK — Config {cid}: Indikator '{name}' {verb} ({block.get('indicator')})\n")
    return 0


def indicator_config_indicator_remove(args: list) -> int:
    """indicator-config-indicator-remove --id N --name <key>

    Entfernt einen Indikator aus config_json. '_stops' ist geschuetzt.
    """
    f = _parse_flags(args)
    cid = _require_id(f, "indicator-config-indicator-remove")
    name = _require(f, "name", "indicator-config-indicator-remove")
    if name == "_stops":
        raise ValueError("indicator-config-indicator-remove: '_stops' nicht ueber dieses Verb entfernen")
    cfg = _indicator_config_get_json(cid)
    if name not in cfg:
        keys = [k for k in cfg if k != "_stops"]
        raise ValueError(f"indicator-config-indicator-remove: Indikator '{name}' nicht vorhanden (da: {', '.join(keys) or '—'})")
    del cfg[name]
    _indicator_config_patch_json(cid, cfg)
    print(f"## indicator-config-indicator-remove: OK — Config {cid}: Indikator '{name}' entfernt\n")
    return 0


# --- Stops (config_json._stops) ---

# Kurz-Flag -> _stops-Feld. Werte gecastet (null/Zahl); Formate bleiben String.
_STOP_FLAGS = {
    "tp": "tp_stop", "sl": "sl_stop", "td": "td_stop", "tsl": "tsl_stop",
    "tsl-th": "tsl_th", "delta-format": "delta_format", "time-delta-format": "time_delta_format",
}
_STOP_STRING_FIELDS = {"delta_format", "time_delta_format"}


def indicator_config_stops_set(args: list) -> int:
    """indicator-config-stops-set --id N [--tp .. --sl .. --td .. --tsl .. --tsl-th .. --delta-format .. --time-delta-format ..]

    Setzt einzelne Werte in config_json._stops; nicht genannte Stops bleiben.
    Zahlen/null werden gecastet, die Format-Felder bleiben String. 'null' loescht
    einen Stop-Wert (setzt ihn auf None).
    """
    f = _parse_flags(args)
    cid = _require_id(f, "indicator-config-stops-set")
    changed = {flag: dst for flag, dst in _STOP_FLAGS.items() if flag in f}
    if not changed:
        raise ValueError(f"indicator-config-stops-set: mindestens ein Stop noetig ({' | '.join('--' + x for x in _STOP_FLAGS)})")
    cfg = _indicator_config_get_json(cid)
    stops = cfg.setdefault("_stops", {})
    for flag, dst in changed.items():
        v = f[flag]
        stops[dst] = str(v) if dst in _STOP_STRING_FIELDS else _coerce_scalar(v)
    _indicator_config_patch_json(cid, cfg)
    print(f"## indicator-config-stops-set: OK — Config {cid}: _stops aktualisiert ({', '.join(changed[k] for k in changed)})\n")
    return 0


# --- Regeln (spec_json.rules) ---

def _rules_side(spec: dict, exit_side: bool) -> tuple:
    """Liefert (rules_dict, side_key). Legt rules/entry|exit-Geruest an, falls fehlt."""
    rules = spec.setdefault("rules", {})
    side = "exit" if exit_side else "entry"
    if not isinstance(rules.get(side), dict):
        rules[side] = {"blocks": []}
    rules[side].setdefault("blocks", [])
    return rules, side


def iteration_condition_add(args: list) -> int:
    """iteration-condition-add --id N [--exit] [--block K | --new-block [--short]] --file cond.json

    Haengt eine Bedingung an einen Regel-Block. Ohne --block: Block 1 (erster).
    --new-block legt einen neuen ODER-Block an (--short markiert ihn als Short).
    cond.json ist ein Bedingungs-Dict, z.B.
    {"op": ">", "lhs": "close", "rhs": "indicator:sma:real"} (optional lhs_shift/rhs_shift).
    """
    f = _parse_flags(args)
    iid = _require_id(f, "iteration-condition-add")
    cond = _read_json_file(_require(f, "file", "iteration-condition-add"))
    exit_side = bool(f.get("exit"))
    spec = _iteration_get_spec(iid)
    rules, side = _rules_side(spec, exit_side)
    blocks = rules[side]["blocks"]
    if f.get("new-block"):
        new_block = {"conditions": [cond]}
        if f.get("short"):
            new_block["is_short"] = True
        blocks.append(new_block)
        pos = len(blocks)
    else:
        if not blocks:
            blocks.append({"conditions": []})
        idx = int(f["block"]) - 1 if f.get("block") and f["block"] is not True else 0
        if idx < 0 or idx >= len(blocks):
            raise ValueError(f"iteration-condition-add: Block {idx + 1} existiert nicht ({len(blocks)} Bloecke)")
        blocks[idx].setdefault("conditions", []).append(cond)
        pos = idx + 1
    _iteration_put_spec(iid, spec)
    print(f"## iteration-condition-add: OK — Iteration {iid}: Bedingung in {side}-Block {pos} ({fmt_cond(cond)})\n")
    return 0


def iteration_condition_remove(args: list) -> int:
    """iteration-condition-remove --id N [--exit] --block K [--index J | --remove-block]

    Entfernt eine Bedingung (--index J, 1-basiert) aus einem Block, oder mit
    --remove-block den ganzen Block. Ohne --index und ohne --remove-block: Fehler.
    """
    f = _parse_flags(args)
    iid = _require_id(f, "iteration-condition-remove")
    exit_side = bool(f.get("exit"))
    if not f.get("block") or f["block"] is True:
        raise ValueError("iteration-condition-remove: --block K noetig")
    bidx = int(f["block"]) - 1
    spec = _iteration_get_spec(iid)
    rules = spec.get("rules", {})
    side = "exit" if exit_side else "entry"
    blocks = (rules.get(side) or {}).get("blocks") or []
    if bidx < 0 or bidx >= len(blocks):
        raise ValueError(f"iteration-condition-remove: {side}-Block {bidx + 1} existiert nicht ({len(blocks)} Bloecke)")
    if f.get("remove-block"):
        blocks.pop(bidx)
        _iteration_put_spec(iid, spec)
        print(f"## iteration-condition-remove: OK — Iteration {iid}: {side}-Block {bidx + 1} entfernt ({len(blocks)} verbleiben)\n")
        return 0
    if not f.get("index") or f["index"] is True:
        raise ValueError("iteration-condition-remove: --index J (1-basiert) oder --remove-block noetig")
    cidx = int(f["index"]) - 1
    conds = blocks[bidx].get("conditions") or []
    if cidx < 0 or cidx >= len(conds):
        raise ValueError(f"iteration-condition-remove: Bedingung {cidx + 1} in Block {bidx + 1} existiert nicht ({len(conds)} Bedingungen)")
    removed = conds.pop(cidx)
    _iteration_put_spec(iid, spec)
    print(f"## iteration-condition-remove: OK — Iteration {iid}: Bedingung {cidx + 1} aus {side}-Block {bidx + 1} entfernt ({fmt_cond(removed)})\n")
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
    "run-favorites-list": run_favorites_list,
    "result-lookup": result_lookup,
    "result-query": result_query,
    "kreuztest": kreuztest,
    "combo-trace": combo_trace,
    "concept-create": concept_create,
    "iteration-create": iteration_create,
    "indicator-config-create": indicator_config_create,
    "indicator-config-set": indicator_config_set,
    "indicator-config-labels": indicator_config_labels,
    # Bearbeitungs-Verben (add/remove/change): GET -> gezielt aendern -> zurueckschreiben
    "concept-set": concept_set,
    "iteration-set": iteration_set,
    "backtest-config-set": backtest_config_set,
    "iteration-indicator-set": iteration_indicator_set,
    "iteration-indicator-remove": iteration_indicator_remove,
    "indicator-config-indicator-set": indicator_config_indicator_set,
    "indicator-config-indicator-remove": indicator_config_indicator_remove,
    "indicator-config-stops-set": indicator_config_stops_set,
    "iteration-condition-add": iteration_condition_add,
    "iteration-condition-remove": iteration_condition_remove,
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

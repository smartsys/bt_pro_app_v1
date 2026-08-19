"""Anlage und Abschluss des Befunds je Testset-Lauf (Ticket 56, Ticket 72).

``open_finding_for_testset_run`` ist Phase 1 (Kontext + Soll beim Start) — die einzige
Implementierung, die sowohl der reguläre Startweg (``api_testset_runs.start_testset_run``)
als auch der Leaderboard-Rerun (``api_leaderboard.rerun_from_snapshot``) aufrufen (Ticket 72).

Der Rest der Datei ist Phase 2: Die Ist-Werte werden ausschließlich aus dem gelesen, was
die Läufe ohnehin geschrieben haben — es wird nichts nachgerechnet und **kein** Recompute
angestoßen. Wurde eine Metrik-Gruppe abgewählt (Ticket 68), bleibt das betroffene Feld
leer und trägt seinen Grund; es wird nie mit 0 gefüllt.

Eine Ausnahme von „nur aus den Läufen" ist der Sondierungs-Zähler des Konzepts
(``strategy_concepts.probe_count``, Ticket 92): Er steht im Umfang-der-Suche-Block neben
der Rastergröße, weil die Lite-Sondierungen nichts in die Datenbank schreiben und sonst
unsichtbar blieben. Auch er wird nur ausgewiesen — nicht in ``combos_total``, nicht in
``N`` und nicht in die DSR eingerechnet.

**Kein Verdict.** Es entsteht keine Gesamtnote, kein Score und keine Rangfolge. Die
Kandidaten stehen nebeneinander, die Reihenfolge ist die kanonische Kriterien-Reihenfolge
und die Lauf-Reihenfolge — nicht die Güte.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from services.api.utils.best_criteria_labels import BEST_CRITERIA_LABELS
from services.api.utils.best_criteria_selection import (
    CANDIDATE_METRIC_FIELDS,
    PF_MIN_TRADES,
    select_best_candidates,
)
from services.api.utils.finding_robustness import (
    N_EFF_MISSING_REASON,
    build_dsr_block,
    build_plateau_block,
    build_symbol_dispersion,
)
from user_data.strategies.generic.indicator_factory import describe_combos
from user_data.utils.database.db import get_engine, get_session
from user_data.utils.database.models import (
    IndicatorConfig,
    StrategyConcept,
    StrategyIteration,
    TestSetRunFinding,
)
from user_data.utils.database.repository_findings import (
    close_testset_run_finding,
    create_testset_run_finding,
    get_finding_for_testset_run,
)
from user_data.utils.metrics.metric_sets import ALL_GROUPS, resolve_metric_groups

logger = logging.getLogger(__name__)

# Die Benchmark-Linie des Konzepts lebt bisher als Prosa in der Vault-Dokumentation.
# Eine maschinenlesbare Quelle dafür zu schaffen ist ausdrücklich nicht Teil von
# Ticket 56 — der Anker bleibt deshalb leer und sagt warum.
BENCHMARK_LINE_MISSING_REASON = 'keine maschinenlesbare Benchmark-Linie vorhanden'

# Es gibt keinen markierten Holdout-Zeitraum (Ticket 56, Out of Scope). Das Warnfeld ist
# vorgesehen, bleibt aber leer statt False — „nicht berührt" wäre eine Aussage, die
# niemand geprüft hat.
HOLDOUT_MISSING_REASON = (
    'kein markierter Holdout-Zeitraum vorhanden (Ticket 56, Out of Scope)'
)


def _load_runs(conn: Connection, testset_run_id: int) -> List[Any]:
    """Lädt die Backtest-Läufe eines Testset-Laufs in stabiler Reihenfolge."""
    return conn.execute(
        text(
            'SELECT id, symbol, exchange, timeframe, start_date, end_date, '
            'n_combinations, ann_factor, status, backtest_config_json '
            'FROM backtest_runs WHERE testset_run_id = :tid ORDER BY id'
        ),
        {'tid': testset_run_id},
    ).fetchall()


def _active_groups(run: Any) -> tuple:
    """Ermittelt die gerechneten Metrik-Gruppen eines Laufs und die Roh-Auswahl.

    Args:
        run: Zeile aus `backtest_runs`.

    Returns:
        Tupel aus Gruppen-Menge und Roh-Auswahl (`backtest_config_json['metrics']`).
    """
    selection = (run.backtest_config_json or {}).get('metrics')
    try:
        groups = resolve_metric_groups(selection, n_combinations=int(run.n_combinations or 0))
    except ValueError as exc:
        # Eine unbekannte Auswahl am Alt-Datensatz wird sichtbar gemacht, nicht
        # stillschweigend zu „alles gerechnet" umgedeutet.
        logger.error(
            '[BEFUND] Lauf %d trägt eine unlesbare Metrik-Auswahl (%r): %s',
            run.id, selection, exc,
        )
        raise
    return groups, selection


def _read_concept_probe_count(conn: Connection, concept_id: Optional[int]) -> Dict[str, Any]:
    """Liest den Sondierungs-Zähler des Konzepts für den Befund (Ticket 92).

    Der Zähler steht im Befund neben der Rastergröße, weil `N` nur die
    gespeicherten Läufe kennt: Lite-Sondierungen schreiben nichts in die
    Datenbank und blieben sonst unsichtbar. Reiner Ausweis — der Wert fließt in
    keine Schwelle und in keine DSR-Rechnung ein.

    Leere Felder tragen ihren Grund (Befund-Konvention), statt 0 zu behaupten:
    ein Befund ohne Konzept-Bezug hat keinen Zähler, nicht den Stand null.

    Args:
        conn: Offene SQLAlchemy-Verbindung.
        concept_id: Konzept des Befunds oder None.

    Returns:
        Dict mit `probe_count` (int oder None) und `probe_count_reason`
        (Grund oder None) sowie einem erklärenden Hinweis.
    """
    hinweis = (
        'probe_count zählt die Lite-Sondierungen des Konzepts (Aufrufe von '
        '/run-backtest-lite mit concept_id). Diese Läufe stehen NICHT in '
        'combos_total und sind nicht in N oder der DSR verrechnet — der Wert '
        'ist ein Ausweis des tatsächlichen Suchumfangs, keine Bewertung.'
    )
    if concept_id is None:
        return {
            'probe_count': None,
            'probe_count_reason': 'Befund ohne Konzept-Bezug (concept_id nicht gesetzt)',
            'probe_count_hinweis': hinweis,
        }
    value = conn.execute(
        text('SELECT probe_count FROM strategy_concepts WHERE id = :concept_id'),
        {'concept_id': concept_id},
    ).scalar()
    if value is None:
        return {
            'probe_count': None,
            'probe_count_reason': f'Konzept {concept_id} nicht gefunden (gelöscht?)',
            'probe_count_hinweis': hinweis,
        }
    return {
        'probe_count': int(value),
        'probe_count_reason': None,
        'probe_count_hinweis': hinweis,
    }


def build_scope(
    conn: Connection, runs: List[Any], per_run: List[Dict[str, Any]],
    concept_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Umfang der Suche: Läufe, Symbole, Zeiträume, Kombinationen, Sondierungen.

    `n_combinations` ist die tatsächlich gelaufene Rastergröße; die Zahl der
    vorliegenden Results steht daneben und ist **nicht** dasselbe — Läufe werden auf
    ihre Doku-Favoriten ausgedünnt.

    GEÄNDERT: Ticket 92 — dazu kommt `probe_count`, der Sondierungs-Zähler des
    Konzepts (siehe `_read_concept_probe_count`). Er steht neben der Rastergröße
    und wird nicht in sie eingerechnet.

    Args:
        conn: Offene SQLAlchemy-Verbindung.
        runs: Zeilen aus `backtest_runs`.
        per_run: Bereits ermittelte Zusatzangaben je Lauf (Metrik-Gruppen).
        concept_id: Konzept des Befunds (für den Sondierungs-Zähler); None, wenn
            der Befund keinen Konzept-Bezug trägt.

    Returns:
        Die Gruppe „Umfang der Suche" des Befunds.
    """
    entries: List[Dict[str, Any]] = []
    for run, extra in zip(runs, per_run):
        n_results = conn.execute(
            text('SELECT COUNT(*) FROM backtest_results WHERE run_id = :run_id'),
            {'run_id': run.id},
        ).scalar()
        entries.append({
            'run_id': run.id,
            'symbol': run.symbol,
            'exchange': run.exchange,
            'timeframe': run.timeframe,
            'start': run.start_date.isoformat() if run.start_date else None,
            'end': run.end_date.isoformat() if run.end_date else None,
            'status': run.status,
            'n_combinations': int(run.n_combinations or 0),
            'n_results': int(n_results or 0),
            'metrics_selection': extra['metrics_selection'],
            'metric_groups_skipped': sorted(ALL_GROUPS - extra['active_groups']),
        })

    periods = sorted({(e['start'], e['end']) for e in entries})
    return {
        'n_runs': len(entries),
        'n_runs_completed': sum(1 for e in entries if e['status'] == 'completed'),
        'n_runs_not_completed': sum(1 for e in entries if e['status'] != 'completed'),
        'symbols': sorted({e['symbol'] for e in entries}),
        'n_symbols': len({e['symbol'] for e in entries}),
        'n_eff': None,
        'n_eff_reason': N_EFF_MISSING_REASON,
        'periods': [{'start': start, 'end': end} for start, end in periods],
        'combos_total': sum(e['n_combinations'] for e in entries),
        'combos_note': (
            'combos_total ist die Summe von backtest_runs.n_combinations — nicht die '
            'Summe der vorliegenden Results (n_results)'
        ),
        **_read_concept_probe_count(conn, concept_id),
        'runs': entries,
    }


def build_benchmarks(
    conn: Connection, runs: List[Any], per_run: List[Dict[str, Any]],
    goal_snapshot: Optional[dict], goal_missing_reason: Optional[str],
) -> Dict[str, Any]:
    """Vergleichsanker: Buy-and-Hold, Benchmark-Linie des Konzepts, Ist gegen Soll.

    Buy-and-Hold kommt aus `benchmark_return_pct` — derselbe Zeitraum, dieselben
    Kosten-Annahmen, gerechnet vom selben Portfolio. Die Benchmark-Linie des Konzepts
    bleibt leer mit Grund. Das Ist-gegen-Soll stellt den Ziel-Schnappschuss den
    erreichten Werten gegenüber, **ohne** ihn auszuwerten: `goal_json` hat bewusst kein
    festes Schema (Ticket 66), eine automatische Zuordnung wäre geraten.

    Args:
        conn: Offene SQLAlchemy-Verbindung.
        runs: Zeilen aus `backtest_runs`.
        per_run: Zusatzangaben je Lauf inklusive der Kandidaten.
        goal_snapshot: Ziel-Schnappschuss aus Phase 1.
        goal_missing_reason: Grund, wenn kein Ziel hinterlegt war.

    Returns:
        Die Gruppe „Vergleichsanker" des Befunds.
    """
    buy_and_hold: List[Dict[str, Any]] = []
    for run, extra in zip(runs, per_run):
        row = conn.execute(
            text(
                'SELECT MIN(benchmark_return_pct) AS lo, MAX(benchmark_return_pct) AS hi, '
                'MAX(total_return_pct) AS best FROM backtest_results WHERE run_id = :run_id'
            ),
            {'run_id': run.id},
        ).fetchone()
        entry: Dict[str, Any] = {
            'run_id': run.id,
            'symbol': run.symbol,
            'start': run.start_date.isoformat() if run.start_date else None,
            'end': run.end_date.isoformat() if run.end_date else None,
            'buy_and_hold_return_pct': None,
            'buy_and_hold_reason': None,
            'best_total_return_pct': None if row.best is None else float(row.best),
            'differenz_pct': None,
        }
        if row.hi is None:
            entry['buy_and_hold_reason'] = (
                'kein Result trägt benchmark_return_pct in diesem Lauf'
            )
        else:
            entry['buy_and_hold_return_pct'] = float(row.hi)
            entry['buy_and_hold_spanne'] = [float(row.lo), float(row.hi)]
            if entry['best_total_return_pct'] is not None:
                entry['differenz_pct'] = round(
                    entry['best_total_return_pct'] - float(row.hi), 4,
                )
        buy_and_hold.append(entry)

    ist: Dict[str, Any] = {}
    for field in CANDIDATE_METRIC_FIELDS:
        values = [
            entry['winner']['metrics'][field]
            for extra in per_run
            for entry in extra['candidates'].values()
            if entry.get('winner') and entry['winner']['metrics'].get(field) is not None
        ]
        ist[field] = (
            {'min': min(values), 'max': max(values)} if values else None
        )

    return {
        'buy_and_hold': buy_and_hold,
        'concept_benchmark_line': None,
        'concept_benchmark_line_reason': BENCHMARK_LINE_MISSING_REASON,
        'goal': {
            'soll': goal_snapshot,
            'soll_reason': goal_missing_reason,
            'ist_spanne_ueber_kandidaten': ist,
            'hinweis': (
                'Gegenüberstellung ohne Auswertung: goal_json hat bewusst kein festes '
                'Schema (Ticket 66). Es wird nichts abgeleitet, nichts bewertet und '
                'nichts als bestanden oder durchgefallen markiert.'
            ),
        },
    }


def build_warnings(
    per_run: List[Dict[str, Any]], robustness: Dict[str, Any],
) -> Dict[str, Any]:
    """Warnhinweise: Trade-Floor, Rastergröße gegen Zugewinn, N_eff, Holdout.

    Zwei Hinweise lassen sich heute nicht bilden und stehen deshalb ausdrücklich als
    „nicht geprüft" mit Grund in der Ausgabe, statt zu fehlen: `N_eff` ist am Testset
    nicht ausgewiesen und einen markierten Holdout gibt es nicht.

    Args:
        per_run: Zusatzangaben je Lauf inklusive der Kandidaten.
        robustness: Bereits gebaute Robustheits-Gruppe (liefert `N` und `SR0`).

    Returns:
        Die Gruppe „Warnhinweise" des Befunds.
    """
    items: List[Dict[str, Any]] = []

    for extra in per_run:
        for key, entry in extra['candidates'].items():
            winner = entry.get('winner')
            if not winner:
                continue
            trades = winner['metrics'].get('total_trades')
            if trades is not None and trades < PF_MIN_TRADES:
                items.append({
                    'code': 'trades_below_floor',
                    'run_id': extra['run_id'],
                    'criterion': key,
                    'result_id': winner['result_id'],
                    'total_trades': trades,
                    'floor': PF_MIN_TRADES,
                    'text': (
                        f'Kandidat des Kriteriums "{key}" in Lauf {extra["run_id"]} hat '
                        f'{trades} Trades und liegt damit unter dem Trade-Floor von '
                        f'{PF_MIN_TRADES}. Kennzahlen aus so wenigen Trades sind '
                        f'Artefakte, keine Aussage über die Kombination.'
                    ),
                })

    for block in robustness['dsr']:
        sr0 = block.get('sr0')
        best_sharpe = block.get('best_sharpe_ratio')
        if sr0 is None or best_sharpe is None:
            continue
        if best_sharpe <= sr0:
            items.append({
                'code': 'grid_raises_bar_above_result',
                'run_id': block['run_id'],
                'n': block['n'],
                'sr0': sr0,
                'best_sharpe_ratio': best_sharpe,
                'text': (
                    f'Lauf {block["run_id"]}: das Raster aus {block["n"]} Kombinationen '
                    f'hebt die Rauschlatte auf SR0 = {sr0:.4f}, der beste erreichte '
                    f'Sharpe liegt mit {best_sharpe:.4f} darunter. Der Zugewinn durch '
                    f'die Rastergröße geht vollständig in die Latte.'
                ),
            })

    return {
        'trade_floor': PF_MIN_TRADES,
        'items': items,
        'not_evaluated': [
            {'code': 'n_eff_low', 'reason': N_EFF_MISSING_REASON},
            {'code': 'holdout_touched', 'reason': HOLDOUT_MISSING_REASON},
        ],
    }


def build_ist_groups(engine: Engine, testset_run_id: int, finding) -> Dict[str, Any]:
    """Baut die fünf Ist-Gruppen eines Testset-Laufs.

    Args:
        engine: Engine der Arbeits-DB.
        testset_run_id: Abgeschlossener Testset-Lauf.
        finding: Der zugehörige Befund (liefert den Ziel-Schnappschuss aus Phase 1).

    Returns:
        Dict mit `scope`, `candidates`, `robustness`, `benchmarks` und `warnings`.

    Raises:
        ValueError: Wenn der Testset-Lauf keine Backtest-Läufe trägt — dann gäbe es
            nichts zu befunden, und ein leerer Befund wäre irreführend.
    """
    with engine.connect() as conn:
        runs = _load_runs(conn, testset_run_id)
        if not runs:
            raise ValueError(
                f'Testset-Lauf {testset_run_id} trägt keine Backtest-Läufe — '
                f'es gibt nichts zu befunden.'
            )

        per_run: List[Dict[str, Any]] = []
        for run in runs:
            groups, selection = _active_groups(run)
            candidates = select_best_candidates(conn, run.id, groups, selection)
            per_run.append({
                'run_id': run.id,
                'symbol': run.symbol,
                'active_groups': groups,
                'metrics_selection': selection,
                'candidates': candidates,
            })

        # GEÄNDERT: Ticket 92 — der Sondierungs-Zähler hängt am Konzept des Befunds
        scope = build_scope(conn, runs, per_run, finding.concept_id)

        dsr_blocks: List[Dict[str, Any]] = []
        for run, extra in zip(runs, per_run):
            block = build_dsr_block(conn, run, extra['candidates'])
            best_sharpe = conn.execute(
                text(
                    'SELECT MAX(sharpe_ratio) FROM backtest_results WHERE run_id = :run_id'
                ),
                {'run_id': run.id},
            ).scalar()
            block['best_sharpe_ratio'] = None if best_sharpe is None else float(best_sharpe)
            dsr_blocks.append(block)

        robustness: Dict[str, Any] = {
            'dsr': dsr_blocks,
            'dsr_hinweis': (
                'Die Deflated Sharpe Ratio steht hier immer zusammen mit der '
                'Rastergröße N und der Rauschlatte SR0 — allein ist sie nicht lesbar.'
            ),
            'plateau': [],
            'symbol_dispersion': build_symbol_dispersion(conn, per_run),
        }
        candidates_group = {
            'hinweis': (
                'Mehrere Kandidaten nebeneinander, kein Gesamtsieger und keine '
                'Rangfolge. Die Reihenfolge ist die kanonische Kriterien-Reihenfolge.'
            ),
            'per_run': [
                {
                    'run_id': extra['run_id'],
                    'symbol': extra['symbol'],
                    'criteria': extra['candidates'],
                }
                for extra in per_run
            ],
        }
        benchmarks = build_benchmarks(
            conn, runs, per_run,
            finding.goal_snapshot_json, finding.goal_missing_reason,
        )

    # Der Plateau-Score läuft über die vorhandene Serverlogik, die eine eigene
    # Verbindung aufmacht — deshalb außerhalb des connect()-Blocks.
    for extra in per_run:
        robustness['plateau'].append({
            'run_id': extra['run_id'],
            'symbol': extra['symbol'],
            'neighborhoods': build_plateau_block(
                engine, extra['run_id'], extra['candidates'],
            ),
        })

    warnings = build_warnings(per_run, robustness)
    return {
        'scope': scope,
        'candidates': candidates_group,
        'robustness': robustness,
        'benchmarks': benchmarks,
        'warnings': warnings,
    }


def _resolve_iteration_context(
    session: Session, iteration_id: int,
) -> Optional[Tuple[int, Optional[int], Optional[Dict[str, Any]]]]:
    """Löst Konzept und Soll-Schnappschuss zu einer bekannten Iterations-ID auf.

    Args:
        session: Aktive SQLAlchemy-Session.
        iteration_id: Zu prüfende ``StrategyIteration.id``.

    Returns:
        Tupel ``(iteration_id, concept_id, goal_snapshot)`` oder None, wenn die
        Iteration nicht existiert (lose Referenz, Zielobjekt gelöscht).
    """
    iteration_row = (
        session.query(StrategyIteration)
        .filter(StrategyIteration.id == iteration_id)
        .first()
    )
    if iteration_row is None:
        return None
    goal_snapshot: Optional[Dict[str, Any]] = None
    concept_row = (
        session.query(StrategyConcept)
        .filter(StrategyConcept.id == iteration_row.concept_id)
        .first()
    )
    if concept_row is not None:
        goal_snapshot = concept_row.goal_json
    return iteration_row.id, iteration_row.concept_id, goal_snapshot


def resolve_iteration_for_rerun_finding(
    session: Session,
    indicator_config_id: Optional[int],
    entry_id: int,
    snapshot_iteration_id: Optional[int] = None,
) -> Tuple[Optional[int], Optional[int], Optional[Dict[str, Any]]]:
    """Löst die Iteration für den Rerun-Befund auf (Ticket 72, direkter Weg Ticket 101).

    Zwei Wege, in dieser Reihenfolge:

    1. **Direkter Weg (Ticket 101):** Steht ``iteration_id`` im
       ``strategy_snapshot_json`` des Eintrags (vom Builder eingefroren,
       ``repository_testsets.build_leaderboard_entry_for_testset_run``), wird sie
       direkt gegen ``StrategyIteration`` aufgelöst — die IndicatorConfig wird dafür
       nicht gebraucht.
    2. **Reserve-Weg (Ticket 72):** Nur wenn der direkte Weg fehlt oder ins Leere
       läuft, greift der Umweg über ``LeaderboardEntry.indicator_config_id`` ->
       ``IndicatorConfig.strategy_iteration_id`` -> ``StrategyIteration``. Bleibt für
       Alt-Einträge ohne eingefrorene ``iteration_id`` erhalten.

    Bricht auch der zweite Weg ab — keine Referenz gesetzt, Zielobjekt gelöscht — wird
    das sichtbar geloggt (WARNING) statt still übersprungen; der Rerun selbst darf
    daran nicht scheitern (Projekt-Prinzip „Altlasten sichtbar machen").

    Args:
        session: Aktive SQLAlchemy-Session.
        indicator_config_id: ``LeaderboardEntry.indicator_config_id`` (lose Referenz,
            kann None sein) — Reserve-Weg.
        entry_id: ID des LeaderboardEntry, nur für die Log-Meldung.
        snapshot_iteration_id: ``iteration_id`` aus ``strategy_snapshot_json`` (lose
            Referenz, kann None sein für Alt-Einträge) — direkter Weg, hat Vorrang.

    Returns:
        Tupel ``(iteration_id, concept_id, goal_snapshot)``. ``iteration_id`` ist None,
        wenn keiner der beiden Wege auflösbar war — dann sind auch die anderen beiden
        Werte None.
    """
    if snapshot_iteration_id is not None:
        resolved = _resolve_iteration_context(session, snapshot_iteration_id)
        if resolved is not None:
            return resolved

    if indicator_config_id is not None:
        ind_config_row = (
            session.query(IndicatorConfig)
            .filter(IndicatorConfig.id == indicator_config_id)
            .first()
        )
        if ind_config_row is not None and ind_config_row.strategy_iteration_id is not None:
            resolved = _resolve_iteration_context(
                session, ind_config_row.strategy_iteration_id,
            )
            if resolved is not None:
                return resolved

    logger.warning(
        '[BEFUND] Rerun von Entry #%d: Iteration nicht auflösbar '
        '(snapshot_iteration_id=%s, indicator_config_id=%s) — es entsteht kein '
        'Befund für diesen Lauf.',
        entry_id, snapshot_iteration_id, indicator_config_id,
    )
    return None, None, None


def open_finding_for_testset_run(
    session: Session,
    testset_run_id: int,
    iteration_id: int,
    concept_id: Optional[int],
    testset_id: int,
    indicator_config_id: Optional[int],
    indicators_json: Dict[str, Any],
    spec_runner_version: Optional[str],
    goal_snapshot: Optional[Dict[str, Any]],
    planned_n_runs: int,
) -> TestSetRunFinding:
    """Legt den Befund eines startenden Testset-Laufs an (Phase 1, Ticket 56/72).

    Einzige Phase-1-Implementierung: wird vom regulären Startweg
    (``api_testset_runs.start_testset_run``) und vom Leaderboard-Rerun
    (``api_leaderboard.rerun_from_snapshot``) aufgerufen, damit beide Startwege
    denselben Kontext- und Soll-Aufbau durchlaufen statt ihn zu duplizieren.

    Zählt die geplante Rastergröße über die einzige Zähl-Wahrheit
    (``describe_combos``); scheitert die Zählung, bleibt der Wert NULL mit
    hinterlegtem Grund statt einer 0. Das Soll ist ein Schnappschuss aus
    ``concept.goal_json`` — die Kopie und die ``goal_missing_reason``-Logik
    übernimmt ``create_testset_run_finding``.

    Args:
        session: Aktive SQLAlchemy-Session, vom Aufrufer verwaltet.
        testset_run_id: Lose Referenz auf testset_runs.id.
        iteration_id: Iteration, für die der Lauf gestartet wurde.
        concept_id: Konzept der Iteration — Herkunft des Ziel-Schnappschusses.
        testset_id: Testset, über das gelaufen wird.
        indicator_config_id: Verwendete Indikator-Konfiguration (lose Referenz).
        indicators_json: Indikator-Konfiguration, aus der die Rastergröße gezählt wird.
        spec_runner_version: Version des Spec-Runners zum Startzeitpunkt.
        goal_snapshot: Inhalt von ``concept.goal_json`` oder None.
        planned_n_runs: Anzahl der geplanten Backtest-Runs (ein Lauf, kein Sweep über N).

    Returns:
        Der neu angelegte Befund.
    """
    planned_combos_per_run: Optional[int] = None
    planned_grid_reason: Optional[str] = None
    try:
        planned_combos_per_run = describe_combos(indicators_json)['total']
    except ValueError as exc:
        planned_grid_reason = f'Rastergröße nicht ermittelbar: {exc}'

    return create_testset_run_finding(
        session=session,
        testset_run_id=testset_run_id,
        iteration_id=iteration_id,
        concept_id=concept_id,
        testset_id=testset_id,
        indicator_config_id=indicator_config_id,
        spec_runner_version=spec_runner_version,
        goal_snapshot=goal_snapshot,
        best_criteria=list(BEST_CRITERIA_LABELS.keys()),
        planned_n_runs=planned_n_runs,
        planned_combos_per_run=planned_combos_per_run,
        planned_grid_reason=planned_grid_reason,
    )


def close_finding_for_testset_run(testset_run_id: int) -> Optional[int]:
    """Schließt den Befund eines abgeschlossenen Testset-Laufs (Phase 2).

    Wird von beiden Abschlusspfaden aufgerufen — dem regulären Worker-Weg und dem
    Rerun aus dem Leaderboard-Snapshot. Existiert kein Befund (etwa für Läufe, die vor
    Ticket 56 gestartet wurden, oder für einen Snapshot-Rerun ohne Iteration), ist das
    kein Fehler: rückwirkende Befunde sind ausdrücklich Out of Scope.

    Fehler beim Schreiben reißen den Lauf-Abschluss nicht ab, werden aber als Fehler
    protokolliert — auch der Versuch, einen bereits geschlossenen Befund erneut zu
    beschreiben.

    Args:
        testset_run_id: ID des abgeschlossenen Testset-Laufs.

    Returns:
        ID des geschlossenen Befunds oder None, wenn keiner geschlossen wurde.
    """
    session = get_session()
    try:
        finding = get_finding_for_testset_run(session, testset_run_id)
        if finding is None:
            logger.info(
                '[BEFUND] Testset-Lauf %d: kein Befund vorhanden — nichts zu schließen '
                '(rückwirkende Befunde sind Out of Scope).',
                testset_run_id,
            )
            return None
        groups = build_ist_groups(get_engine(), testset_run_id, finding)
        close_testset_run_finding(session, finding, **groups)
        logger.info(
            '[BEFUND] Befund %d geschlossen (Testset-Lauf %d, %d Läufe, %d Warnhinweise).',
            finding.id, testset_run_id, groups['scope']['n_runs'],
            len(groups['warnings']['items']),
        )
        return finding.id
    except Exception as exc:
        session.rollback()
        logger.error(
            '[BEFUND] Befund für Testset-Lauf %d konnte nicht geschlossen werden: %s',
            testset_run_id, exc, exc_info=True,
        )
        return None
    finally:
        session.close()

"""Kandidat auflösen und nachrechnen — Grundlage der Signifikanztests (Ticket 79).

Ein Kandidat ist ein Result: Iteration × eingefrorene Parameterkombination ×
BacktestConfig. Dieses Modul beantwortet genau zwei Fragen:

1. **Womit rechnet man diesen Kandidaten nach?** (:func:`resolve_candidate`) —
   derselbe Auflösungsweg wie ``start_walk_forward``: BacktestConfig aus dem Run,
   eingefrorene Kombination aus ``result.resolved_config_json``, Regeln aus
   ``iteration.spec_json['rules']``. Die Stops kommen aus derselben
   Bildungsvorschrift wie der Result-Schnappschuss
   (``_build_full_config_snapshot``) — ein gesweepter Stop steht dort schon als
   Skalar der jeweiligen Kombination.
2. **Rechnet der Nachlauf dasselbe wie der bewertete Lauf?**
   (:func:`verify_reference_run`) — die Selbstprüfung. Sie ist der Grund, warum
   einem p-Wert überhaupt zu glauben ist: ohne sie könnte der Test unbemerkt eine
   andere Kombination, ein anderes Fenster oder andere Stops messen.

Gerechnet wird **save-frei** (:func:`single_combination_metrics`) nach dem Muster
von ``/run-backtest-lite``: ``run_spec_strategy`` direkt, Kennzahlen über
``_extract_metrics``. Es entsteht kein Run, kein Result und keine Detail-Zeile.

Das Modul schreibt nichts und kennt den ``significance_tests``-Datensatz nicht —
das macht der :mod:`services.api.significance_runner`.
"""

import copy
import math
from typing import Any, Dict, List, Optional, Sequence

from user_data.utils.analysis.significance import DEFAULT_PERMUTATION_METRICS
from user_data.utils.database.models import BacktestResult, BacktestRun, BacktestTrade
from user_data.utils.database.repository import (
    _build_full_config_snapshot,
    _extract_metrics,
)
from user_data.utils.metrics.metric_sets import (
    ALL_METRIC_FIELDS,
    METRIC_GROUPS,
    normalize_groups,
)
from user_data.strategies.generic.indicator_factory import STOP_PARAM_KEYS

# Relative Toleranz der Selbstprüfung. Bewusst eng: Referenzlauf und Result rechnen
# denselben Code über dieselben Daten, es darf nur Gleitkomma-Rauschen abweichen.
REFERENCE_TOLERANCE: float = 1e-9

# Feld, an dem „dieser Lauf hat gar nicht gehandelt" abgelesen wird.
TRADE_COUNT_FIELD: str = 'total_trades'


def json_safe(value: Any) -> Any:
    """Ersetzt nicht-endliche Zahlen rekursiv durch None (JSONB-taugliche Form).

    ``NaN``/``Infinity`` sind kein gültiges JSON und werden von JSONB abgewiesen.
    Ein NaN-Profitfaktor (Lauf ohne geschlossene Trades) muss aber erhalten
    bleiben — als ausdrückliches None, nicht als 0.

    Args:
        value: Beliebige Struktur aus Dicts, Listen und Skalaren.

    Returns:
        Dieselbe Struktur mit None an allen nicht-endlichen Zahl-Positionen.
    """
    if isinstance(value, dict):
        return {key: json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(val) for val in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            return None
        return value if isinstance(value, int) else number
    return value


def groups_for_metrics(metrics: Sequence[str]) -> frozenset:
    """Bestimmt die zu rechnenden Kennzahl-Gruppen für eine Metrik-Auswahl.

    Nur die Gruppen der angefragten Metriken werden gerechnet (plus die
    Pflichtgruppen) — der Sinn der Gruppen-Auswahl ist gesparte Rechenzeit, und bei
    N Läufen zählt sie N-fach.

    Args:
        metrics: Namen der Kennzahl-Felder (Spalten von ``backtest_results``).

    Returns:
        Menge der zu rechnenden Gruppen.

    Raises:
        ValueError: Bei einem unbekannten Kennzahl-Feld — geraten wird nicht.
    """
    unknown = [metric for metric in metrics if metric not in ALL_METRIC_FIELDS]
    if unknown:
        raise ValueError(
            f"Unbekannte Kennzahl(en): {', '.join(unknown)}. Zulässig sind die "
            f"Kennzahl-Felder aus metric_sets.py, z.B. "
            f"{', '.join(DEFAULT_PERMUTATION_METRICS)}."
        )
    needed = {
        group for group, fields in METRIC_GROUPS.items()
        if any(metric in fields for metric in metrics)
    }
    return normalize_groups(needed)


def resolve_candidate(session, result_id: int) -> Dict[str, Any]:
    """Löst einen Kandidaten (Result) zu allem auf, was ein Nachlauf braucht.

    Args:
        session: Aktive SQLAlchemy-Session.
        result_id: ID des Results.

    Returns:
        Dict mit ``run_id``, ``iteration_id``, ``backtest_config`` (rechenfertig,
        Chunking deaktiviert), ``indicators`` (eingefrorene Kombination inkl.
        ``_stops``), ``rules``, ``actual_params``, ``config_snapshot`` und
        ``stored_metrics`` (alle Kennzahl-Felder des Results).

    Raises:
        ValueError: Wenn Result, Run, Iteration, Regeln oder die eingefrorene
            Kombination fehlen. Jede Lücke bricht sichtbar ab.
    """
    result = session.query(BacktestResult).filter(BacktestResult.id == result_id).first()
    if result is None:
        raise ValueError(f'Result {result_id} nicht gefunden.')
    run = session.query(BacktestRun).filter(BacktestRun.id == result.run_id).first()
    if run is None:
        raise ValueError(
            f'Run {result.run_id} zu Result {result_id} nicht gefunden — der Lauf '
            f'wurde aufgeräumt, damit ist der Kandidat nicht mehr nachrechenbar.'
        )
    if not result.resolved_config_json:
        raise ValueError(
            f'Result {result_id} hat keine resolved_config_json — ohne die '
            f'eingefrorene Kombination gibt es nichts nachzurechnen.'
        )
    if run.iteration_id is None or run.iteration is None:
        raise ValueError(
            f'Run {run.id}: iteration_id fehlt. Die Regeln kommen ausschließlich aus '
            f'iteration.spec_json.'
        )
    rules = (run.iteration.spec_json or {}).get('rules')
    if rules is None:
        raise ValueError(f"Iteration {run.iteration_id}: spec_json enthält keinen 'rules'-Key.")

    backtest_config = copy.deepcopy(dict(run.backtest_config_json))
    # Genau eine Kombination: Chunking abschalten, damit der Runner ein Portfolio
    # zurückgibt (kein metrics_table) — identisch zum Recompute-Pfad.
    backtest_config['_disable_chunked'] = True

    snapshot = _build_full_config_snapshot(
        backtest_config=dict(run.backtest_config_json),
        indicators_config=dict(run.indicators_config_json),
        actual_params=dict(result.actual_params_json or {}),
        rules=rules,
    )
    indicators = copy.deepcopy(dict(result.resolved_config_json))
    indicators['_stops'] = {
        **{key: snapshot['backtest_config'].get(key) for key in STOP_PARAM_KEYS},
        'delta_format': snapshot['backtest_config'].get('delta_format'),
        'time_delta_format': snapshot['backtest_config'].get('time_delta_format'),
    }

    stored_metrics = {field: getattr(result, field, None) for field in ALL_METRIC_FIELDS}

    return {
        'run_id': run.id,
        'iteration_id': run.iteration_id,
        'backtest_config': backtest_config,
        'indicators': indicators,
        'rules': rules,
        'actual_params': dict(result.actual_params_json or {}),
        'config_snapshot': snapshot['backtest_config'],
        'stored_metrics': stored_metrics,
    }


def single_combination_metrics(
    ohlc_data: Any,
    candidate: Dict[str, Any],
    groups: frozenset,
) -> Dict[str, Any]:
    """Rechnet genau eine Kombination durch und liefert ihre Kennzahlen.

    Save-freier Weg wie ``/run-backtest-lite``: ``run_spec_strategy`` direkt, danach
    ``_extract_metrics`` — die einzige Kennzahl-Funktion des Systems. Es entsteht
    kein Run, kein Result und keine Detail-Zeile.

    Args:
        ohlc_data: Echte oder synthetische Preisreihe (``vbt.Data``).
        candidate: Auflösung aus :func:`resolve_candidate`.
        groups: Zu rechnende Kennzahl-Gruppen.

    Returns:
        Kennzahl-Dict der einen Kombination.

    Raises:
        ValueError: Wenn der Runner kein Portfolio liefert oder mehr als eine
            Kombination herauskommt (dann war die Kombination nicht eingefroren).
    """
    from user_data.strategies.generic.spec_runner import run_spec_strategy

    strategy_results = run_spec_strategy(
        ohlc_data,
        candidate['indicators'],
        candidate['backtest_config'],
        candidate['rules'],
    )
    portfolios = strategy_results.get('portfolios')
    if portfolios is None:
        raise ValueError(
            'Der Spec-Runner lieferte kein Portfolio — erwartet wird genau eine '
            'Kombination (gechunkte Läufe geben stattdessen metrics_table zurück).'
        )
    columns = portfolios.wrapper.columns
    if len(columns) != 1:
        raise ValueError(
            f'Der Lauf ergab {len(columns)} Kombinationen, erwartet wird genau eine. '
            f'Die eingefrorene Kombination des Results enthält offenbar noch eine '
            f'Sweep-Achse.'
        )
    return _extract_metrics(portfolios, columns, candidate['backtest_config'], groups)[0]


def _values_match(stored: Optional[float], reference: Optional[float]) -> bool:
    """Vergleicht zwei Kennzahlen mit relativer Toleranz.

    Args:
        stored: Am Result gespeicherter Wert.
        reference: Wert des Referenzlaufs.

    Returns:
        True, wenn beide Werte innerhalb von REFERENCE_TOLERANCE übereinstimmen.
        Zwei nicht-endliche Werte gelten als übereinstimmend; einer allein nicht.
    """
    stored_finite = stored is not None and math.isfinite(float(stored))
    reference_finite = reference is not None and math.isfinite(float(reference))
    if not stored_finite or not reference_finite:
        return stored_finite == reference_finite
    left, right = float(stored), float(reference)
    return abs(left - right) <= REFERENCE_TOLERANCE * max(abs(left), abs(right), 1e-300)


def verify_reference_run(
    stored_metrics: Dict[str, Any],
    reference_metrics: Dict[str, Any],
    metrics: Sequence[str],
) -> Dict[str, Any]:
    """Prüft, ob der Referenzlauf die gespeicherten Kennzahlen reproduziert.

    Verglichen wird jede angefragte Metrik, die am Result **einen Wert hat**. Eine
    am Result nicht gespeicherte Metrik (etwa weil der Lauf mit reduzierter
    Kennzahl-Auswahl lief, oder weil es keinen geschlossenen Trade gab) lässt sich
    nicht vergleichen; sie wird als ungeprüft **ausgewiesen**, nicht stillschweigend
    übergangen.

    Args:
        stored_metrics: Kennzahlen des Results.
        reference_metrics: Kennzahlen des Referenzlaufs auf der echten Reihe.
        metrics: Angefragte Metriken.

    Returns:
        Prüfbericht mit ``tolerance``, ``compared`` (je Metrik gespeicherter und
        gerechneter Wert) und ``unchecked`` (Metrik plus Grund).

    Raises:
        ValueError: Wenn eine Metrik abweicht oder keine einzige prüfbar war.
    """
    compared: Dict[str, Any] = {}
    unchecked: Dict[str, str] = {}
    mismatches: List[str] = []

    for metric in metrics:
        stored = stored_metrics.get(metric)
        reference = reference_metrics.get(metric)
        if stored is None:
            unchecked[metric] = (
                'am Result nicht gespeichert (NULL) — kein Vergleich möglich; der '
                f'Referenzlauf ergab {reference!r}'
            )
            continue
        matches = _values_match(stored, reference)
        compared[metric] = {
            'stored': json_safe(stored),
            'reference': json_safe(reference),
            'matches': matches,
        }
        if not matches:
            mismatches.append(f'{metric}: Result {stored!r} vs. Referenzlauf {reference!r}')

    if mismatches:
        raise ValueError(
            'Selbstprüfung fehlgeschlagen: der Referenzlauf auf der echten Reihe '
            'reproduziert die am Result gespeicherten Kennzahlen nicht (relative '
            f'Toleranz {REFERENCE_TOLERANCE}). Abweichungen: {"; ".join(mismatches)}. '
            'Der Test würde damit etwas anderes messen als das bewertete Result und '
            'bricht deshalb ab.'
        )
    if not compared:
        raise ValueError(
            'Selbstprüfung nicht durchführbar: keine der angefragten Kennzahlen ist '
            f'am Result gespeichert ({", ".join(metrics)}). Ohne mindestens eine '
            'vergleichbare Zahl ist nicht belegbar, dass der Referenzlauf dasselbe '
            'misst wie das bewertete Result.'
        )

    return {
        'tolerance': REFERENCE_TOLERANCE,
        'compared': compared,
        'unchecked': unchecked,
    }


def load_trade_returns(session, result_id: int) -> List[float]:
    """Liest die Renditen der **geschlossenen** Trades eines Results.

    Offene Trades (am Fensterende marktbewertet) bleiben außen vor — ein
    unrealisierter Buchgewinn ist kein Ergebnis. Das ist dieselbe Grundgesamtheit,
    über die auch ``profit_factor`` und ``win_rate_pct`` rechnen.

    Args:
        session: Aktive SQLAlchemy-Session.
        result_id: ID des Results.

    Returns:
        Liste der ``return_pct``-Werte in Prozent.
    """
    rows = (
        session.query(BacktestTrade.return_pct)
        .filter(BacktestTrade.result_id == result_id, BacktestTrade.status == 'Closed')
        .order_by(BacktestTrade.exit_trade_id.asc())
        .all()
    )
    return [row[0] for row in rows if row[0] is not None]

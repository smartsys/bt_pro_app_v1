"""Ausführung der Signifikanztests eines Kandidaten.

Zwei Rechenwege, beide **ohne jedes Schreiben in ``backtest_results`` oder
``backtest_runs``** — geschrieben wird ausschließlich der eigene Datensatz in
``significance_tests``:

* :func:`run_permutation_test` — Referenzlauf auf der echten Reihe (Selbstprüfung),
  danach N Läufe auf synthetischen Reihen (Seeds ``seed + i``). Vorbild für den
  save-freien Rechenweg ist ``/run-backtest-lite``: ``run_spec_strategy`` wird direkt
  aufgerufen, es gibt kein ``create_backtest_run`` und kein
  ``save_strategy_results``. Deshalb entfällt auch jeder Aufräumschritt.
* :func:`run_bootstrap_test` — Resampling der gespeicherten Trade-Renditen. Kein
  Backtest, kein Recompute.

**Die Selbstprüfung kommt zuerst.** Der Referenzlauf auf der echten Reihe muss die
am Result gespeicherten Kennzahlen reproduzieren (relative Toleranz 1e-9). Weichen
sie ab, bricht der Test sichtbar ab — dann misst er etwas anderes als das bewertete
Result, und ein p-Wert dazu wäre irreführend. Kein stilles Weiterrechnen.

Auflösung des Kandidaten, save-freie Messung und Selbstprüfung liegen in
:mod:`services.api.significance_candidate`; die Rechenkerne (p-Wert, Bootstrap) in
:mod:`user_data.utils.analysis.significance`. Dieses Modul verbindet beides mit dem
Datensatz-Lebenslauf (running -> completed/failed).
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from services.api.significance_candidate import (
    TRADE_COUNT_FIELD,
    groups_for_metrics,
    json_safe,
    load_trade_returns,
    resolve_candidate,
    single_combination_metrics,
    verify_reference_run,
)
from user_data.utils.analysis.significance import (
    DEFAULT_BOOTSTRAP_ROUNDS,
    DEFAULT_PERMUTATION_METRICS,
    bootstrap_trade_returns,
    build_permutation_summary,
)
from user_data.utils.database.db import get_session
from user_data.utils.database.repository_significance import (
    complete_significance_test,
    fail_significance_test,
    get_significance_test,
    mark_significance_test_running,
)

logger = logging.getLogger(__name__)


def run_permutation_test(
    test_id: int,
    metrics: Optional[Sequence[str]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> bool:
    """Rechnet den Monte-Carlo-Permutationstest eines Signifikanztest-Datensatzes.

    Ablauf: Kandidat auflösen, echte Reihe laden, Referenzlauf samt Selbstprüfung,
    dann N Läufe auf synthetischen Reihen. Geschrieben wird ausschließlich der
    ``significance_tests``-Datensatz.

    Args:
        test_id: ID des vorbereiteten Signifikanztests.
        metrics: Auszuwertende Kennzahlen. None nimmt
            ``DEFAULT_PERMUTATION_METRICS``.
        progress_callback: Optionaler Callback (step, total) je fertiger Reihe.

    Returns:
        True bei Abschluss mit Ergebnis, False bei sichtbar festgeschriebenem Fehler.
    """
    from user_data.utils.analysis.synthetic_series import iter_synthetic_data
    from user_data.utils.ohlc.loader import load_ohlc_data

    metric_names: Tuple[str, ...] = tuple(metrics or DEFAULT_PERMUTATION_METRICS)
    started = time.monotonic()

    session = get_session()
    try:
        test = get_significance_test(session, test_id)
        if test is None:
            logger.error('[SIGNIFIKANZ] Test %s nicht gefunden.', test_id)
            return False
        n_series, seed, result_id = test.n_iterations, test.seed, test.result_id
        mark_significance_test_running(session, test_id)

        try:
            groups = groups_for_metrics(metric_names)
            candidate = resolve_candidate(session, result_id)
            ohlc_data = load_ohlc_data(candidate['backtest_config'])

            # Selbstprüfung zuerst — vor jedem synthetischen Lauf.
            reference_metrics = single_combination_metrics(ohlc_data, candidate, groups)
            reference_check = verify_reference_run(
                candidate['stored_metrics'], reference_metrics, metric_names,
            )
            logger.info(
                '[SIGNIFIKANZ] Test %d: Referenzlauf reproduziert das Result '
                '(%d Kennzahlen verglichen).',
                test_id, len(reference_check['compared']),
            )

            distributions: Dict[str, List[Any]] = {metric: [] for metric in metric_names}
            n_no_trade_runs = 0
            for step, (_used_seed, synthetic_data) in enumerate(
                iter_synthetic_data(ohlc_data, n_series=n_series, seed=seed), start=1,
            ):
                synthetic_metrics = single_combination_metrics(
                    synthetic_data, candidate, groups,
                )
                for metric in metric_names:
                    distributions[metric].append(json_safe(synthetic_metrics.get(metric)))
                if not synthetic_metrics.get(TRADE_COUNT_FIELD):
                    n_no_trade_runs += 1
                if progress_callback is not None:
                    progress_callback(step, n_series)

            real_values = {metric: reference_metrics.get(metric) for metric in metric_names}
            summary = build_permutation_summary(
                real_values=real_values,
                distributions=distributions,
                n_no_trade_runs=n_no_trade_runs,
                n_runs=n_series,
            )
            summary['metric_names'] = list(metric_names)
            summary['reference_check'] = reference_check
            summary['metric_groups'] = sorted(groups)

            complete_significance_test(
                session=session,
                test_id=test_id,
                real_values=json_safe(real_values),
                distributions=json_safe(distributions),
                summary=json_safe(summary),
                duration_seconds=time.monotonic() - started,
            )
            return True
        except Exception as exc:
            fail_significance_test(
                session=session,
                test_id=test_id,
                error_message=str(exc),
                duration_seconds=time.monotonic() - started,
            )
            logger.error(
                '[SIGNIFIKANZ] Test %d (permutation) fehlgeschlagen: %s',
                test_id, exc, exc_info=True,
            )
            return False
    finally:
        session.close()


def run_bootstrap_test(test_id: int) -> bool:
    """Rechnet den Trade-Level-Bootstrap eines Signifikanztest-Datensatzes.

    Läuft synchron (Sekundenbruchteile) und braucht keinen Backtest: die Trades
    liegen bereits in ``backtest_result_trades``. Fehlen sie, bricht der Test mit
    Hinweis auf den Recompute-Weg ab — **kein** automatischer Recompute.

    Args:
        test_id: ID des vorbereiteten Signifikanztests.

    Returns:
        True bei Abschluss mit Ergebnis, False bei sichtbar festgeschriebenem Fehler.
    """
    started = time.monotonic()
    session = get_session()
    try:
        test = get_significance_test(session, test_id)
        if test is None:
            logger.error('[SIGNIFIKANZ] Test %s nicht gefunden.', test_id)
            return False
        n_rounds, seed, result_id = test.n_iterations, test.seed, test.result_id
        try:
            returns = load_trade_returns(session, result_id)
            outcome = bootstrap_trade_returns(
                returns, n_rounds=n_rounds or DEFAULT_BOOTSTRAP_ROUNDS, seed=seed,
            )
            complete_significance_test(
                session=session,
                test_id=test_id,
                real_values=json_safe(outcome['observed']),
                # Der Bootstrap zieht keine Null-Verteilung — die volle Werteliste
                # sind hier die Eingangs-Trade-Renditen, aus denen alles folgt.
                distributions=json_safe({'trade_return_pct': returns}),
                summary=json_safe(outcome),
                duration_seconds=time.monotonic() - started,
            )
            return True
        except Exception as exc:
            fail_significance_test(
                session=session,
                test_id=test_id,
                error_message=str(exc),
                duration_seconds=time.monotonic() - started,
            )
            logger.error(
                '[SIGNIFIKANZ] Test %d (bootstrap) fehlgeschlagen: %s', test_id, exc,
            )
            return False
    finally:
        session.close()

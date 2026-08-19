"""Repository-Funktionen für den Signifikanztest je Kandidat (Ticket 79).

Der Datensatz entsteht beim Start (Kontext, Methode, N, Seed) und wird genau
einmal abgeschlossen — mit Ergebnis (``completed``) oder mit Fehlermeldung
(``failed``). Danach ist er unveränderlich; durchgesetzt wird das vom ORM-Wächter
an :class:`~user_data.utils.database.models.SignificanceTest`, nicht von einer
Konvention in diesem Docstring.

Es gibt bewusst **keine** Update- und keine Delete-Funktion: ein neuer Test
erzeugt einen neuen Datensatz. Und **keine** Sortierung nach p-Wert — die
Historie ist ausnahmslos chronologisch, damit aus dem Bericht keine
Filter-Einladung wird.
"""

import copy
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from user_data.utils.database.models import (
    SIGNIFICANCE_METHODS,
    SignificanceTest,
)

logger = logging.getLogger(__name__)


def create_significance_test(
    session: Session,
    result_id: int,
    run_id: Optional[int],
    iteration_id: Optional[int],
    method: str,
    n_iterations: int,
    seed: int,
    params: Optional[Dict[str, Any]] = None,
    config_snapshot: Optional[Dict[str, Any]] = None,
    status: str = 'queued',
) -> SignificanceTest:
    """Legt den Datensatz eines Signifikanztests an.

    Kontext-Angaben werden tief kopiert: eine spätere Änderung am Result oder Run
    darf einen bereits angelegten Test nicht mehr berühren.

    Args:
        session: Aktive SQLAlchemy-Session.
        result_id: Lose Referenz auf backtest_results.id (kein FK).
        run_id: Lose Referenz auf backtest_runs.id.
        iteration_id: Lose Referenz auf strategy_iterations.id.
        method: 'permutation' oder 'bootstrap'.
        n_iterations: Anzahl synthetischer Reihen bzw. Bootstrap-Runden.
        seed: Startwert des Zufallsgenerators.
        params: Eingefrorene Parameterkombination des Kandidaten.
        config_snapshot: Symbol, Timeframe, Zeitraum, Portfolio-Kern.
        status: Startstatus ('queued' für den Job-Pfad, 'running' für den
            synchronen Pfad).

    Returns:
        Der neu angelegte Signifikanztest.

    Raises:
        ValueError: Bei unbekannter Methode oder n_iterations < 1.
    """
    if method not in SIGNIFICANCE_METHODS:
        raise ValueError(
            f"Unbekannte Methode '{method}'. Zulässig: {', '.join(SIGNIFICANCE_METHODS)}."
        )
    if n_iterations < 1:
        raise ValueError(f'n_iterations muss >= 1 sein, ist {n_iterations}')

    test = SignificanceTest(
        result_id=result_id,
        run_id=run_id,
        iteration_id=iteration_id,
        params_json=copy.deepcopy(params) if params else None,
        config_snapshot_json=copy.deepcopy(config_snapshot) if config_snapshot else None,
        method=method,
        n_iterations=n_iterations,
        seed=seed,
        status=status,
    )
    session.add(test)
    session.commit()
    session.refresh(test)
    logger.info(
        '[SIGNIFIKANZ] Test %d angelegt (Methode %s, Result %d, N=%d, Seed=%d, Status %s).',
        test.id, method, result_id, n_iterations, seed, status,
    )
    return test


def get_significance_test(
    session: Session, test_id: int,
) -> Optional[SignificanceTest]:
    """Gibt einen einzelnen Signifikanztest zurück oder None.

    Args:
        session: Aktive SQLAlchemy-Session.
        test_id: Primärschlüssel des Tests.

    Returns:
        Der Test oder None.
    """
    return (
        session.query(SignificanceTest)
        .filter(SignificanceTest.id == test_id)
        .first()
    )


def list_significance_tests_for_result(
    session: Session, result_id: int,
) -> List[SignificanceTest]:
    """Historie aller Signifikanztests eines Results — chronologisch.

    Sortiert ausschließlich nach Anlagezeitpunkt (und id als Tiebreaker). Es gibt
    bewusst keine Sortierung nach p-Wert: sonst würde die Historie zur
    Bestenliste, und der Test ist ein Bericht, kein Filter.

    Args:
        session: Aktive SQLAlchemy-Session.
        result_id: Lose Referenz auf backtest_results.id.

    Returns:
        Liste der Tests, ältester zuerst.
    """
    return (
        session.query(SignificanceTest)
        .filter(SignificanceTest.result_id == result_id)
        .order_by(SignificanceTest.created_at.asc(), SignificanceTest.id.asc())
        .all()
    )


def mark_significance_test_running(session: Session, test_id: int) -> None:
    """Setzt einen Test auf 'running' (Job hat ihn aufgegriffen).

    Args:
        session: Aktive SQLAlchemy-Session.
        test_id: Primärschlüssel des Tests.

    Raises:
        ValueError: Wenn der Test nicht existiert.
    """
    test = get_significance_test(session, test_id)
    if test is None:
        raise ValueError(f'Signifikanztest {test_id} nicht gefunden.')
    test.status = 'running'
    session.commit()


def complete_significance_test(
    session: Session,
    test_id: int,
    real_values: Dict[str, Any],
    distributions: Dict[str, Any],
    summary: Dict[str, Any],
    duration_seconds: float,
) -> SignificanceTest:
    """Schließt einen Test mit Ergebnis ab (Status 'completed').

    Ergebnis und Endstatus werden in **einem** Flush geschrieben: für diesen
    Schreibvorgang war der Test noch offen, der Wächter greift also noch nicht.
    Jeder weitere Versuch trifft den Endzustand und läuft auf.

    Args:
        session: Aktive SQLAlchemy-Session.
        test_id: Primärschlüssel des Tests.
        real_values: Echter Wert je Metrik (bzw. beobachtete Kennzahlen).
        distributions: Vollständige Wertelisten der Null-Verteilung je Metrik.
        summary: Kennwerte und p-Werte bzw. Konfidenzbänder.
        duration_seconds: Laufzeit des Tests.

    Returns:
        Der abgeschlossene Test.

    Raises:
        ValueError: Wenn der Test nicht existiert.
        SignificanceTestImmutableError: Wenn der Test bereits abgeschlossen war.
    """
    test = get_significance_test(session, test_id)
    if test is None:
        raise ValueError(f'Signifikanztest {test_id} nicht gefunden.')
    test.real_values_json = real_values
    test.distribution_json = distributions
    test.summary_json = summary
    test.duration_seconds = float(duration_seconds)
    test.error_message = None
    test.status = 'completed'
    session.commit()
    session.refresh(test)
    logger.info(
        '[SIGNIFIKANZ] Test %d abgeschlossen (%s, %.1fs).',
        test.id, test.method, test.duration_seconds,
    )
    return test


def fail_significance_test(
    session: Session,
    test_id: int,
    error_message: str,
    duration_seconds: Optional[float] = None,
) -> SignificanceTest:
    """Schließt einen Test mit sichtbarer Fehlermeldung ab (Status 'failed').

    Der Fehler wird als Endzustand festgeschrieben, nicht geschluckt: ein
    gescheiterter Test ist ein Ergebnis, das lesbar bleiben muss (etwa die
    fehlgeschlagene Selbstprüfung des Referenzlaufs).

    Args:
        session: Aktive SQLAlchemy-Session.
        test_id: Primärschlüssel des Tests.
        error_message: Klartext des Fehlers.
        duration_seconds: Bis zum Abbruch verbrauchte Zeit, falls bekannt.

    Returns:
        Der abgebrochene Test.

    Raises:
        ValueError: Wenn der Test nicht existiert.
        SignificanceTestImmutableError: Wenn der Test bereits abgeschlossen war.
    """
    test = get_significance_test(session, test_id)
    if test is None:
        raise ValueError(f'Signifikanztest {test_id} nicht gefunden.')
    test.error_message = str(error_message)[:4000]
    if duration_seconds is not None:
        test.duration_seconds = float(duration_seconds)
    test.status = 'failed'
    session.commit()
    session.refresh(test)
    logger.error(
        '[SIGNIFIKANZ] Test %d fehlgeschlagen (%s): %s',
        test.id, test.method, test.error_message,
    )
    return test


def significance_test_to_dict(test: SignificanceTest) -> Dict[str, Any]:
    """Serialisiert einen Signifikanztest für die API-Antwort.

    Enthält bewusst **kein** Verdict-Feld: kein ``passed``, kein Score, keine
    Ampel. Der p-Wert steht innerhalb von ``summary_json`` immer zusammen mit den
    Kennwerten seiner Null-Verteilung.

    Args:
        test: Die ORM-Instanz.

    Returns:
        JSON-serialisierbares Dict.
    """
    created_at: Optional[datetime] = test.created_at
    return {
        'id': test.id,
        'result_id': test.result_id,
        'run_id': test.run_id,
        'iteration_id': test.iteration_id,
        'params_json': test.params_json,
        'config_snapshot_json': test.config_snapshot_json,
        'method': test.method,
        'n_iterations': test.n_iterations,
        'seed': test.seed,
        'status': test.status,
        'error_message': test.error_message,
        'created_at': created_at.isoformat() if created_at else None,
        'duration_seconds': test.duration_seconds,
        'real_values_json': test.real_values_json,
        'distribution_json': test.distribution_json,
        'summary_json': test.summary_json,
    }

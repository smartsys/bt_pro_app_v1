"""API-Endpunkte für den Signifikanztest je Kandidat

POST /api/backtest/results/{result_id}/significance — Test anlegen und starten
GET  /api/significance-tests/{test_id}              — ein Test
GET  /api/significance-tests?result_id=…            — Historie eines Results

Zwei Methoden, ein Datensatz-Typ:

* ``permutation`` — Monte-Carlo-Permutationstest über N synthetische Preisreihen.
  Läuft als RQ-Hintergrund-Job (Minuten), der Endpunkt gibt sofort die ``test_id``
  zurück.
* ``bootstrap`` — Resampling der gespeicherten Trade-Renditen. Rechnet direkt im
  Aufruf (Sekundenbruchteile) und antwortet mit dem fertigen Ergebnis.

**Kein Verdict, keine Güte-Sortierung.** Die Historie liefert ausnahmslos die
chronologische Reihenfolge — es gibt kein ``sort_by``, keinen „nur signifikante"-
Filter und kein ``passed``-Feld. Es gibt ebenso **keine** Update- und keine
Delete-Route: ein abgeschlossener Test ist unveränderlich, ein erneuter Test
erzeugt einen neuen Datensatz.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from rq import Queue

from services.api.redis_conn import (
    BACKTEST_QUEUE_NAME,
    get_redis_connection,
)
from user_data.utils.analysis.significance import (
    DEFAULT_BOOTSTRAP_ROUNDS,
    DEFAULT_PERMUTATION_METRICS,
)
from user_data.utils.database.db import get_session
from user_data.utils.database.models import SIGNIFICANCE_METHODS
from user_data.utils.database.repository_significance import (
    create_significance_test,
    get_significance_test,
    list_significance_tests_for_result,
    significance_test_to_dict,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=['significance'])

# Standard-Anzahl synthetischer Reihen des Permutationstests.
DEFAULT_PERMUTATION_SERIES: int = 300

# Zeitlimit des Permutations-Jobs. Großzügig: 300 Reihen liegen bei wenigen Minuten,
# ein langer Zeitraum mit vielen Indikatoren kann aber deutlich darüber landen. Ein
# zu enges Limit würde den Lauf mitten im Raster abschneiden.
SIGNIFICANCE_JOB_TIMEOUT: int = 24 * 3600


class SignificanceStartIn(BaseModel):
    """Eingabe-Schema zum Starten eines Signifikanztests."""
    method: str = Field(description="'permutation' oder 'bootstrap'")
    n: Optional[int] = Field(
        default=None,
        description=(
            'Anzahl synthetischer Reihen (permutation, Default 300) bzw. '
            'Bootstrap-Runden (bootstrap, Default 2000).'
        ),
    )
    seed: int = Field(default=42, description='Startwert des Zufallsgenerators.')
    metrics: Optional[List[str]] = Field(
        default=None,
        description=(
            'Auszuwertende Kennzahl-Felder (nur permutation). Default: '
            f"{', '.join(DEFAULT_PERMUTATION_METRICS)}."
        ),
    )


def _default_iterations(method: str, requested: Optional[int]) -> int:
    """Bestimmt die Iterationszahl je Methode.

    Args:
        method: 'permutation' oder 'bootstrap'.
        requested: Vom Aufrufer gewünschter Wert oder None.

    Returns:
        Zu verwendende Iterationszahl.

    Raises:
        HTTPException: Bei einem Wert kleiner als 1.
    """
    if requested is None:
        return (
            DEFAULT_PERMUTATION_SERIES if method == 'permutation'
            else DEFAULT_BOOTSTRAP_ROUNDS
        )
    if requested < 1:
        raise HTTPException(status_code=400, detail=f'n muss >= 1 sein, ist {requested}.')
    return requested


@router.post('/api/backtest/results/{result_id}/significance')
def start_significance_test(result_id: int, payload: SignificanceStartIn):
    """Legt einen Signifikanztest an und startet ihn.

    ``permutation`` wird als Hintergrund-Job eingereiht (Enqueue über den
    String-Pfad, wie alle Jobs des Projekts) und die Antwort enthält die
    ``test_id`` samt Status ``queued``. ``bootstrap`` rechnet direkt und antwortet
    mit dem fertigen Datensatz.

    Der Kontext (eingefrorene Kombination, Config-Schnappschuss) wird schon beim
    Anlegen eingefroren — damit bleibt auch ein gescheiterter Test deutbar.
    """
    from services.api.significance_candidate import resolve_candidate
    from services.api.significance_runner import run_bootstrap_test

    if payload.method not in SIGNIFICANCE_METHODS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unbekannte Methode '{payload.method}'. Zulässig: "
                f"{', '.join(SIGNIFICANCE_METHODS)}."
            ),
        )
    n_iterations = _default_iterations(payload.method, payload.n)

    session = get_session()
    try:
        try:
            candidate = resolve_candidate(session, result_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        test = create_significance_test(
            session=session,
            result_id=result_id,
            run_id=candidate['run_id'],
            iteration_id=candidate['iteration_id'],
            method=payload.method,
            n_iterations=n_iterations,
            seed=payload.seed,
            params={
                'actual_params': candidate['actual_params'],
                'indicators': candidate['indicators'],
            },
            config_snapshot=candidate['config_snapshot'],
            status='queued' if payload.method == 'permutation' else 'running',
        )
        test_id = test.id
    finally:
        session.close()

    if payload.method == 'permutation':
        queue = Queue(BACKTEST_QUEUE_NAME, connection=get_redis_connection())
        queue.enqueue(
            'services.api.worker_tasks.run_significance_permutation_job',
            test_id=test_id,
            metrics=list(payload.metrics) if payload.metrics else None,
            job_timeout=SIGNIFICANCE_JOB_TIMEOUT,
        )
        logger.info(
            '[SIGNIFIKANZ] Permutationstest %d eingereiht (Result %d, N=%d, Seed=%d).',
            test_id, result_id, n_iterations, payload.seed,
        )
    else:
        run_bootstrap_test(test_id)

    session = get_session()
    try:
        test = get_significance_test(session, test_id)
        return {
            'data': {'test_id': test_id, 'test': significance_test_to_dict(test)},
            'error': None,
        }
    finally:
        session.close()


@router.get('/api/significance-tests/{test_id}')
def get_significance_test_route(test_id: int):
    """Ein einzelner Signifikanztest — bleibt lesbar, auch wenn Result und Run
    längst aufgeräumt wurden (lose Referenzen, siehe Modell-Docstring)."""
    session = get_session()
    try:
        test = get_significance_test(session, test_id)
        if test is None:
            raise HTTPException(
                status_code=404, detail=f'Signifikanztest {test_id} nicht gefunden.',
            )
        return {'data': significance_test_to_dict(test), 'error': None}
    finally:
        session.close()


@router.get('/api/significance-tests')
def list_significance_tests_route(
    result_id: int = Query(description='Result, dessen Test-Historie geliefert wird.'),
):
    """Test-Historie eines Results — chronologisch, ohne Sortier- oder Filteroption.

    Bewusst keine Sortierung nach p-Wert: sonst würde die Historie zur Bestenliste,
    und der Test ist ein Bericht, kein Filter.
    """
    session = get_session()
    try:
        tests = list_significance_tests_for_result(session, result_id)
        items = [significance_test_to_dict(test) for test in tests]
        return {'data': {'items': items, 'total': len(items)}, 'error': None}
    finally:
        session.close()

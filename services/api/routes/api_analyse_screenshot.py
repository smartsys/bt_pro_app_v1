"""
Analyse-Screenshot (Ticket 100)

GET /api/backtest/runs/{run_id}/analyse/screenshot — Vollseiten-PNG der Analyse-Seite.

Die Route baut aus den Parametern die Analyse-URL (dieselben Query-Parameter, die die Seite
seit Ticket 99 liest), lässt den Renderer-Dienst die echte Seite fotografieren und gibt das
PNG als ``image/png`` zurück. Fehler des Renderers — Zeitüberschreitung oder ein von der
Seite gemeldeter Grund (``window.__analyseError``) — werden als Fehlerantwort mit
Klartext-Grund durchgereicht, nie als leeres oder halbes Bild.

Die Sollwerte des Screenshot-Standards stehen hier als Vorgabewerte im Code statt in Prosa:
Vollseite, mindestens 1920 breit, beide Aggregationen ``avg``, beide Slider leer, Metrik
``total_return_pct``. Abweichen kann nur, wer sie ausdrücklich als Parameter setzt.
"""

import os
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from user_data.utils.database.db import get_session
from user_data.utils.database.models import BacktestResult, BacktestRun

router = APIRouter(prefix='/api/backtest', tags=['analyse-screenshot'])

# --- Sollwerte des Screenshot-Standards (Single Source, siehe Modul-Docstring) ---------
# Fenstermaße: Unter 1920 Breite rutscht die zweite Heatmap unter die erste und das Bild
# ist für den Vergleich über Iterationen unbrauchbar.
STANDARD_WIDTH = 1920
STANDARD_HEIGHT = 1080
# Average statt Max, weil die Doku robuste Zonen zeigen soll (Plateau-Denken) — Max zeigt
# überfittete Einzelpunkt-Nadeln. Der Seiten-Default ist ausdrücklich 'max'.
STANDARD_AGG = 'avg'
# Beide Slider leer: Die Seite belegt heatmap2-z ab fünf bekannten Parametern automatisch
# vor; wer nur Heatmap 1 zurücksetzt, fotografiert eine gefilterte zweite Heatmap.
STANDARD_SLIDER = ''
# Referenzschuss auf Total Return %; die Zielkennzahl kommt als zusätzlicher Schuss.
STANDARD_METRIC = 'total_return_pct'
# Vollseite — sonst fehlen Verteilung und zweite Heatmap.
STANDARD_FULL_PAGE = True
# Obergrenze fürs Warten auf window.__analyseReady.
STANDARD_TIMEOUT_MS = 90000

# Die Tabs „Übersicht" und „Heatmaps" sind in analyse.html bereits die aktiven Reiter
# (class="nav-link active"); die 3D-Ansicht liegt in einem inaktiven, ausgeblendeten
# Tab-Bereich und kommt damit nicht mit aufs Bild. Es gibt dafür keinen URL-Parameter
# und es braucht keinen.


def _resolve_metric(metric: str) -> str:
    """Fällt bei leerem oder Whitespace-only ``metric`` auf den Standardwert zurück.

    Ein leerer Query-Parameter (``metric=``) ist ein gesetzter leerer String — der
    Query-Default greift nur, wenn der Parameter ganz fehlt. Ohne diese Normalisierung
    landet der leere Wert unverändert in der Analyse-URL, die Seite meldet „Unbekannte
    Metrik: " und die Route scheitert erst nach dem Renderer-Lauf mit HTTP 502. Gilt
    ausschließlich für ``metric`` — ``z`` (kein Slider) hat dieselbe Leer-Semantik nicht
    und darf nicht über diese Funktion laufen.
    """
    return metric.strip() or STANDARD_METRIC


def _renderer_base_url() -> str:
    """Adresse des Renderer-Dienstes im internen Netz."""
    return os.environ.get('RENDERER_BASE_URL', 'http://renderer:8080').rstrip('/')


def _app_internal_base_url() -> str:
    """Adresse, unter der der Renderer die Analyse-Seite erreicht."""
    return os.environ.get('APP_INTERNAL_BASE_URL', 'http://app:8000').rstrip('/')


def build_analyse_url(
    run_id: int,
    x: str,
    y: str,
    agg: str,
    metric: str,
    z: str,
    x2: Optional[str],
    y2: Optional[str],
    agg2: Optional[str],
    z2: Optional[str],
) -> str:
    """Baut die Analyse-URL mit allen Sollwerten ausdrücklich ausgeschrieben.

    Die Seite würde x2/y2/agg2/z2 ohne eigenen Wert auf die Basis-Werte zurückfallen
    lassen; die Route schreibt sie trotzdem aus, damit im Bild nachvollziehbar ist,
    womit fotografiert wurde.

    Args:
        run_id: ID des Runs.
        x: Waagerechte Achse von Heatmap 1.
        y: Senkrechte Achse von Heatmap 1.
        agg: Aggregation von Heatmap 1 ('avg' oder 'max').
        metric: Aktive Metrik der Seite.
        z: Slider-Parameter von Heatmap 1 ('' = kein Slider).
        x2: Waagerechte Achse von Heatmap 2 (None = wie x).
        y2: Senkrechte Achse von Heatmap 2 (None = wie y).
        agg2: Aggregation von Heatmap 2 (None = wie agg).
        z2: Slider-Parameter von Heatmap 2 (None = wie z).

    Returns:
        Vollständige Adresse der Analyse-Seite inklusive Query-Parametern.
    """
    params = {
        'x': x,
        'y': y,
        'agg': agg,
        'z': z,
        'metric': metric,
        'x2': x2 if x2 is not None else x,
        'y2': y2 if y2 is not None else y,
        'agg2': agg2 if agg2 is not None else agg,
        'z2': z2 if z2 is not None else z,
    }
    return f'{_app_internal_base_url()}/backtest/runs/{run_id}/analyse?{urlencode(params)}'


@router.get(
    '/runs/{run_id}/analyse/screenshot',
    responses={200: {'content': {'image/png': {}}, 'description': 'Vollseiten-PNG der Analyse-Seite'}},
)
async def get_analyse_screenshot(
    run_id: int,
    x: str = Query(..., description='Waagerechte Achse der Heatmaps (Parametername)'),
    y: str = Query(..., description='Senkrechte Achse der Heatmaps (Parametername)'),
    agg: str = Query(STANDARD_AGG, pattern='^(avg|max)$', description='Aggregation Heatmap 1'),
    metric: str = Query(STANDARD_METRIC, description='Aktive Metrik der Seite'),
    z: str = Query(STANDARD_SLIDER, description='Slider-Parameter Heatmap 1, leer = kein Slider'),
    x2: Optional[str] = Query(None, description='Waagerechte Achse Heatmap 2 (ohne Wert wie x)'),
    y2: Optional[str] = Query(None, description='Senkrechte Achse Heatmap 2 (ohne Wert wie y)'),
    agg2: Optional[str] = Query(None, pattern='^(avg|max)$', description='Aggregation Heatmap 2 (ohne Wert wie agg)'),
    z2: Optional[str] = Query(None, description='Slider-Parameter Heatmap 2 (ohne Wert wie z)'),
    width: int = Query(STANDARD_WIDTH, ge=STANDARD_WIDTH, le=8000, description='Fensterbreite, mindestens 1920'),
    height: int = Query(STANDARD_HEIGHT, ge=400, le=8000, description='Fensterhöhe'),
    full_page: bool = Query(STANDARD_FULL_PAGE, description='Vollseiten-Aufnahme'),
    timeout_ms: int = Query(STANDARD_TIMEOUT_MS, ge=1000, le=600000, description='Obergrenze in Millisekunden'),
) -> Response:
    """Fotografiert die Analyse-Seite eines Runs und liefert das PNG.

    Args:
        run_id: ID des Runs.
        x, y, agg, metric, z: Ansicht von Heatmap 1 und Metrik der Seite.
        x2, y2, agg2, z2: Abweichende Ansicht für Heatmap 2, sonst wie Heatmap 1.
        width, height: Fenstermaße, Vorgabe 1920x1080.
        full_page: Vollseiten-Aufnahme statt sichtbarem Ausschnitt.
        timeout_ms: Obergrenze fürs Warten auf das Fertig-Signal der Seite.

    Returns:
        Das PNG als ``image/png``-Antwort.

    Raises:
        HTTPException: Run unbekannt (404), Run ohne Results (409), Renderer nicht
            erreichbar (503) oder Aufnahme gescheitert (502) — jeweils mit Klartext-Grund.
    """
    # Vorprüfung im App-Container: Ein unbekannter Run oder ein Run ohne Result-Bestand
    # ergäbe sonst ein Bild, das wie ein kaputter Lauf aussieht.
    session = get_session()
    try:
        run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail=f'Run {run_id} nicht gefunden.')
        result_count = session.query(BacktestResult).filter(
            BacktestResult.run_id == run_id
        ).count()
    finally:
        session.close()

    if result_count == 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f'Run {run_id} hat keine Results — die Analyse-Seite rechnet aus dem vollen '
                f'Result-Satz und bliebe leer. Screenshot vor dem Ergebnis-Purge aufnehmen.'
            ),
        )

    analyse_url = build_analyse_url(run_id, x, y, agg, _resolve_metric(metric), z, x2, y2, agg2, z2)
    render_params = {
        'url': analyse_url,
        'width': width,
        'height': height,
        'full_page': str(full_page).lower(),
        'timeout_ms': timeout_ms,
    }

    # Der Renderer wartet selbst bis timeout_ms; der HTTP-Aufruf braucht etwas Luft darüber.
    http_timeout = timeout_ms / 1000.0 + 30.0
    try:
        async with httpx.AsyncClient(timeout=http_timeout) as client:
            response = await client.get(f'{_renderer_base_url()}/render', params=render_params)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail=f'Renderer-Dienst nicht erreichbar ({_renderer_base_url()}): {exc}',
        ) from exc

    if response.status_code != 200:
        reason = _extract_renderer_reason(response)
        raise HTTPException(
            status_code=502,
            detail=f'Screenshot fehlgeschlagen: {reason} (Analyse-URL: {analyse_url})',
        )

    if response.headers.get('content-type', '').split(';')[0].strip() != 'image/png':
        raise HTTPException(
            status_code=502,
            detail='Renderer lieferte kein PNG — Aufnahme verworfen statt halbes Bild zurückzugeben.',
        )

    return Response(
        content=response.content,
        media_type='image/png',
        headers={'Cache-Control': 'no-store'},
    )


def _extract_renderer_reason(response: httpx.Response) -> str:
    """Zieht den Klartext-Grund aus der Fehlerantwort des Renderers."""
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or f'HTTP {response.status_code} ohne Begründung'
    if isinstance(payload, dict):
        for key in ('error', 'detail', 'message'):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    return f'HTTP {response.status_code}: {payload}'

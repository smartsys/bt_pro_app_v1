"""HTML-Seiten für Vault-Wissens-Index (Ticket 29, Ticket 30)

GET /knowledge               — Dashboard: Index- und Lauf-Statistiken (Ticket 30)
GET /knowledge/runs          — Reindex-Verlauf Übersicht
GET /knowledge/runs/{id}     — Reindex-Run Detail
GET /knowledge/files         — Indizierte Dateien
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from user_data.utils.database.db import get_session
from user_data.utils.database.models import VaultReindexRun

router = APIRouter(prefix='/knowledge', tags=['knowledge-views'])


# GEÄNDERT: Ticket 30 — Dashboard-Seite als Einstiegspunkt
@router.get('', response_class=HTMLResponse)
def knowledge_dashboard_page(request: Request) -> HTMLResponse:
    """Wissens-Index Dashboard (Übersicht über Index und Lauf-Statistiken)."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='knowledge/dashboard.html',
        context={'active_nav': 'knowledge_dashboard'},
    )


@router.get('/runs', response_class=HTMLResponse)
def knowledge_runs_page(request: Request) -> HTMLResponse:
    """Reindex-Verlauf Übersicht."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='knowledge/runs.html',
        context={'active_nav': 'knowledge_runs'},
    )


@router.get('/runs/{run_id}', response_class=HTMLResponse)
def knowledge_run_detail_page(request: Request, run_id: int) -> HTMLResponse:
    """Reindex-Run Detail-Seite.

    Args:
        run_id: DB-ID des VaultReindexRun-Eintrags.

    Returns:
        HTML-Seite mit Run-Details oder 404 wenn nicht gefunden.
    """
    with get_session() as session:
        run = session.query(VaultReindexRun).filter(VaultReindexRun.id == run_id).first()
        if run is None:
            return HTMLResponse('<h1>Reindex-Run nicht gefunden</h1>', status_code=404)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='knowledge/run_detail.html',
        context={'active_nav': 'knowledge_runs', 'run_id': run_id},
    )


@router.get('/files', response_class=HTMLResponse)
def knowledge_files_page(request: Request) -> HTMLResponse:
    """Indizierte Dateien Übersicht."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='knowledge/files.html',
        context={'active_nav': 'knowledge_files'},
    )

"""HTML-Seite für die Queue-/Job-Übersicht (Monitoring).

GET /monitor — Übersicht über RQ-Queues, Worker und offene Jobs.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix='/monitor', tags=['monitor-views'])


@router.get('', response_class=HTMLResponse)
def monitor_page(request: Request) -> HTMLResponse:
    """Queue-/Job-Übersicht (Live-Queues, Worker und offene Jobs)."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='monitor/overview.html',
        context={'active_nav': 'monitor'},
    )

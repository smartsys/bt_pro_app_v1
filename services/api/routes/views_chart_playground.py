"""
HTML-View für Chart Playground.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse


router = APIRouter(tags=['views-chart-playground'])


@router.get('/chart-playground', response_class=HTMLResponse)
def chart_playground_page(request: Request) -> HTMLResponse:
    """Chart-Playground-Seite für Strategie-Entwicklung ohne Backtest."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='chart_playground/index.html',
        context={'active_nav': 'chart_playground'},
    )

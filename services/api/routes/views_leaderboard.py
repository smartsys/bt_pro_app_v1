"""
HTML-Seite für das Leaderboard

GET /leaderboard — Leaderboard-Übersicht mit TestSet-Dropdown und DataTable
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from user_data.utils.database.db import get_session
from user_data.utils.database.models import TestSet

router = APIRouter(prefix='/leaderboard', tags=['leaderboard-views'])


@router.get('', response_class=HTMLResponse)
def leaderboard_page(request: Request) -> HTMLResponse:
    """Leaderboard-Seite — TestSet-Dropdown + DataTable lädt per AJAX."""
    session = get_session()
    try:
        testsets = (
            session.query(TestSet)
            .order_by(TestSet.name)
            .all()
        )
        testsets_data = [
            {'id': ts.id, 'name': ts.name}
            for ts in testsets
        ]
    finally:
        session.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='leaderboard/index.html',
        context={
            'active_nav': 'leaderboard',
            'testsets': testsets_data,
        },
    )

"""
HTML-Seiten für TestSets

GET /testsets          — TestSets Übersicht
GET /testsets/new      — Neues TestSet anlegen (gleiche Maske wie Bearbeiten)
GET /testsets/{id}     — TestSet Detail/Bearbeiten
"""
# GEÄNDERT: Ticket 13 — Naming-Cleanup auf views_testsets / Prefix /testsets

from typing import Any, Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from user_data.utils.database.db import get_session
from user_data.utils.database.models import BacktestConfig
from user_data.utils.database.repository_testsets import get_testset

router = APIRouter(prefix='/testsets', tags=['testsets-views'])


def _load_configs_data(session: Session) -> List[Dict[str, Any]]:
    """Lädt alle BacktestConfigs für die Config-Auswahl im TestSet-Formular."""
    all_configs = (
        session.query(BacktestConfig)
        .order_by(BacktestConfig.name)
        .all()
    )
    return [
        {'id': c.id, 'name': c.name, 'symbol': c.symbol, 'timeframe': c.timeframe}
        for c in all_configs
    ]


@router.get('', response_class=HTMLResponse)
def testsets_page(request: Request) -> HTMLResponse:
    """TestSets Übersicht — DataTable lädt per AJAX."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='testsets/list.html',
        context={'active_nav': 'testsets'},
    )


@router.get('/new', response_class=HTMLResponse)
def testset_new_page(request: Request) -> HTMLResponse:
    """Neues TestSet anlegen — gleiche Maske wie Bearbeiten, ohne vorgeladene Daten."""
    session = get_session()
    try:
        configs_data = _load_configs_data(session)
    finally:
        session.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='testsets/detail.html',
        context={
            'active_nav': 'testsets',
            'testset': None,
            'all_configs': configs_data,
        },
    )


@router.get('/{testset_id}', response_class=HTMLResponse)
def testset_detail_page(request: Request, testset_id: int) -> HTMLResponse:
    """TestSet Detail-Ansicht mit Bearbeiten-Formular."""
    session = get_session()
    try:
        ts = get_testset(session, testset_id)
        if ts is None:
            return HTMLResponse('<h1>TestSet nicht gefunden</h1>', status_code=404)

        configs_data = _load_configs_data(session)

        ts_data = {
            'id': ts.id,
            'name': ts.name,
            'description': ts.description,
            # GEÄNDERT: Ticket 15 Code-Sweep — _json-Suffix
            'backtest_config_ids': ts.backtest_config_ids_json,
            'leaderboard_enabled': ts.leaderboard_enabled,
            'created_at': ts.created_at.strftime('%Y-%m-%d %H:%M') if ts.created_at else '',
            'created_by': ts.created_by,
        }
    finally:
        session.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='testsets/detail.html',
        context={
            'active_nav': 'testsets',
            'testset': ts_data,
            'all_configs': configs_data,
        },
    )

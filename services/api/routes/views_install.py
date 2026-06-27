"""Onboarding-/Installations-Seite (/install)

GET /install — Übersicht über die mit der Grundausstattung installierten Objekte
               (DB-Check) plus Aktion, die die nötigen OHLC-Download-Jobs anlegt.

Gedacht als erster Aufruf nach install.sh: zeigt dem neuen Nutzer, was bereits
da ist, und lässt ihn die Kursdaten für die mitgelieferten Test-Sets laden.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from user_data.utils.database.db import get_session
from user_data.utils.database.models import (
    BacktestConfig,
    IndicatorConfig,
    StrategyConcept,
    StrategyIteration,
    TestSet,
)

router = APIRouter(tags=['install-views'])


@router.get('/install', response_class=HTMLResponse)
def install_page(request: Request) -> HTMLResponse:
    """Installations-Übersicht: zeigt, was die Grundausstattung mitgebracht hat."""
    with get_session() as session:
        counts = {
            'backtest_configs': session.query(BacktestConfig).count(),
            'testsets': session.query(TestSet).count(),
            'strategy_concepts': session.query(StrategyConcept).count(),
            'strategy_iterations': session.query(StrategyIteration).count(),
            'indicator_configs': session.query(IndicatorConfig).count(),
        }
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='install/dashboard.html',
        context={'active_nav': 'install', 'counts': counts},
    )

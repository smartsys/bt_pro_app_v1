"""
FastAPI App

Hauptanwendung: JSON-API + HTML-Seiten für Backtest-Ergebnisse.
Nutzt bestehende DB-Schicht aus user_data.utils.database.
"""

import os
import sys
from pathlib import Path

# Projekt-Root für user_data Imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

import logging


# Polling-Requests aus Uvicorn-Logs filtern (DataTables, Auto-Update)
class QuietAccessFilter(logging.Filter):
    """Filtert häufige Polling-Requests aus dem Access-Log."""
    _quiet_paths = ['/api/backtest/results/dt', '/api/backtest/runs?', '/api/backtest/runs/']

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(p in msg for p in self._quiet_paths)


logging.getLogger('uvicorn.access').addFilter(QuietAccessFilter())

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from services.api.routes.api_backtest import router as api_router
from services.api.routes.api_config import router as api_config_router
from services.api.routes.api_chart_playground import router as api_chart_playground_router
# GEÄNDERT: Ticket 13 — Naming-Cleanup auf api_testsets / views_testsets
from services.api.routes.api_testsets import router as testsets_router
# GEÄNDERT: TestSet-Runs API-Router (Ticket 05)
from services.api.routes.api_testset_runs import router as api_testset_runs_router
from services.api.routes.views_backtest import router as views_router
from services.api.routes.views_config import router as views_config_router
from services.api.routes.views_chart_playground import router as views_chart_playground_router
from services.api.routes.views_testsets import router as views_testsets_router
# GEÄNDERT: Leaderboard-Router (Ticket 07)
from services.api.routes.api_leaderboard import router as api_leaderboard_router
from services.api.routes.views_leaderboard import router as views_leaderboard_router
# GEÄNDERT: Strategie-Konzepte und Iterationen (Ticket 09)
from services.api.routes.api_strategy import router as api_strategy_router
# GEÄNDERT: Ticket 26 — Vault-Wissenssuche und Reindex-Endpoints
from services.api.routes.api_knowledge import router as api_knowledge_router
# GEÄNDERT: Ticket 29 — Knowledge-Frontend-Views
from services.api.routes.views_knowledge import router as views_knowledge_router
# Onboarding-/Installations-Seite (/install)
from services.api.routes.views_install import router as views_install_router
# Queue-/Job-Übersicht (Monitoring)
from services.api.routes.api_monitor import router as api_monitor_router
from services.api.routes.views_monitor import router as views_monitor_router

app = FastAPI(title="BT Pro App", version="1.0.0", debug=True)

# Static Files
FRONTEND_DIR = PROJECT_ROOT / 'services' / 'frontend'
app.mount('/static', StaticFiles(directory=str(FRONTEND_DIR / 'static')), name='static')

# Jinja2 Templates
templates = Jinja2Templates(directory=str(FRONTEND_DIR / 'templates'))
templates.env.globals['APP_VERSION'] = os.getenv('APP_VERSION', '0.0.0')
templates.env.globals['STATIC_TS'] = str(int(__import__('time').time()))
app.state.templates = templates

# Router einbinden
app.include_router(api_router)
app.include_router(api_config_router)
app.include_router(api_chart_playground_router)
# GEÄNDERT: Ticket 13 — Naming-Cleanup auf testsets_router
app.include_router(testsets_router)
# GEÄNDERT: TestSet-Runs Router einbinden (Ticket 05)
app.include_router(api_testset_runs_router)
app.include_router(views_router)
app.include_router(views_config_router)
app.include_router(views_chart_playground_router)
# GEÄNDERT: Ticket 13 — Naming-Cleanup auf views_testsets_router
app.include_router(views_testsets_router)
# GEÄNDERT: Leaderboard-Router einbinden (Ticket 07)
app.include_router(api_leaderboard_router)
app.include_router(views_leaderboard_router)
# GEÄNDERT: Strategie-Router einbinden (Ticket 09)
app.include_router(api_strategy_router)
# GEÄNDERT: Ticket 26 — Knowledge-Router einbinden
app.include_router(api_knowledge_router)
# GEÄNDERT: Ticket 29 — Knowledge-Views-Router einbinden
app.include_router(views_knowledge_router)
# Onboarding-/Installations-Seite einbinden
app.include_router(views_install_router)
# Queue-/Job-Übersicht (Monitoring) einbinden
app.include_router(api_monitor_router)
app.include_router(views_monitor_router)


@app.get('/')
def root():
    """Redirect zur Runs-Übersicht."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url='/backtest/runs')

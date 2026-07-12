"""
HTML-Seiten + Aktionen für DB-Snapshot Export/Import.

GET  /config/seed/export           — Export-Seite (Speichern-Button + Download)
POST /config/seed/export           — Snapshot im Ordner speichern
GET  /config/seed/export/download  — frischen Dump als Download ausliefern
GET  /config/seed/import           — Import-Seite (gespeicherten Snapshot + Button)
POST /config/seed/import           — Import anstoßen (läuft im Hintergrund)
GET  /config/seed/import/status    — Fortschritt des Imports (für die Anzeige)

Der eigentliche Dump/Restore steckt in services.api.seed_service (pg_dump/
pg_restore per TCP, Ablage in db_snapshot/data/, kein Stack-Neustart).
"""

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.background import BackgroundTask

from services.api.seed_service import (
    export_temp_dump,
    export_to_store,
    import_status,
    snapshot_filename,
    start_import,
    stored_snapshot_info,
)


router = APIRouter(prefix='/config', tags=['seed-views'])


@router.get('/seed/export', response_class=HTMLResponse)
def seed_export_page(request: Request) -> HTMLResponse:
    """Export-Seite: Snapshot speichern (im Ordner) oder herunterladen."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='config/seed_export.html',
        context={
            'active_nav': 'config_seed_export',
            'result': None,
            'snapshot': stored_snapshot_info(),
        },
    )


@router.post('/seed/export', response_class=HTMLResponse)
def seed_export_action(request: Request) -> HTMLResponse:
    """Speichert einen Snapshot im Ordner db_snapshot/data/ (wie das CLI-Skript)."""
    templates = request.app.state.templates
    try:
        dated = export_to_store()
        result = {
            'ok': True,
            'message': f'Snapshot gespeichert: {dated.name} '
                       f'(auch als seed.dump für den Import).',
        }
    except Exception as exc:  # noqa: BLE001 — Fehler sichtbar auf der Seite melden
        result = {'ok': False, 'message': f'Export fehlgeschlagen: {exc}'}
    return templates.TemplateResponse(
        request=request,
        name='config/seed_export.html',
        context={
            'active_nav': 'config_seed_export',
            'result': result,
            'snapshot': stored_snapshot_info(),
        },
    )


@router.get('/seed/export/download')
def seed_export_download():
    """Erzeugt einen frischen Dump und liefert ihn als Datei-Download aus."""
    path = export_temp_dump()
    return FileResponse(
        path=str(path),
        media_type='application/octet-stream',
        filename=snapshot_filename(),
        background=BackgroundTask(lambda: path.unlink(missing_ok=True)),
    )


@router.get('/seed/import', response_class=HTMLResponse)
def seed_import_page(request: Request) -> HTMLResponse:
    """Import-Seite: zeigt den gespeicherten Snapshot und den Import-Button."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name='config/seed_import.html',
        context={
            'active_nav': 'config_seed_import',
            'snapshot': stored_snapshot_info(),
        },
    )


@router.post('/seed/import')
def seed_import_action() -> JSONResponse:
    """Stößt den Import an (läuft im Hintergrund) und kehrt sofort zurück.

    Den Fortschritt holt die Seite über ``/config/seed/import/status``.
    """
    try:
        start_import()
    except Exception as exc:  # noqa: BLE001 — Fehler sichtbar auf der Seite melden
        return JSONResponse(
            status_code=409,
            content={'started': False, 'message': f'Import fehlgeschlagen: {exc}'},
        )
    return JSONResponse(status_code=202, content={'started': True})


@router.get('/seed/import/status')
def seed_import_status() -> JSONResponse:
    """Aktueller Stand des laufenden bzw. zuletzt gelaufenen Imports."""
    return JSONResponse(content=import_status())

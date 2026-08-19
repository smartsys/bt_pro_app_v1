"""
Renderer-Dienst — „URL rein, PNG raus".

Fotografiert die echte Seite mit einem langlebigen Chromium (Playwright). Je Anfrage
entsteht ein frischer Tab, der danach wieder geschlossen wird; der Browser-Prozess selbst
bleibt bestehen, weil Start und Stopp je Bild sonst ein bis zwei Sekunden kosten. Ein
Leerlauf-Timeout beendet ihn, wenn eine Weile niemand mehr fotografiert hat.

Gewartet wird ausschließlich auf ein Fertig-Signal der Seite (Vorgabe:
``window.__analyseReady``). Läuft es in den Timeout, ist das ein Fehler mit Grund — es gibt
bewusst keinen Rückfall auf eine feste Wartezeit.

Schnittstelle:
    GET /health   — Zustand des Dienstes und des Browsers (aktualisiert den Leerlauf NICHT)
    GET /render   — URL fotografieren, liefert image/png oder eine JSON-Fehlerantwort
"""

import asyncio
import logging
import os
import time
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, Response
from playwright.async_api import (
    Browser,
    Playwright,
    async_playwright,
)
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [renderer] %(message)s',
)
logger = logging.getLogger('renderer')

# Leerlauf-Timeout in Sekunden: so lange darf der Browser ohne Anfrage bestehen bleiben.
# Zum Prüfen bewusst kurz konfigurierbar (Compose-Umgebungsvariable).
IDLE_TIMEOUT_SECONDS: float = float(os.environ.get('RENDERER_IDLE_TIMEOUT_SECONDS', '300'))
# Takt, in dem der Leerlauf-Wächter nachsieht.
IDLE_CHECK_INTERVAL_SECONDS: float = float(os.environ.get('RENDERER_IDLE_CHECK_INTERVAL_SECONDS', '5'))
# Vorgabe für die Gesamt-Wartezeit einer Aufnahme.
DEFAULT_TIMEOUT_MS: int = int(os.environ.get('RENDERER_DEFAULT_TIMEOUT_MS', '90000'))

# Vorgabe-Ausdrücke für die Analyse-Seite. Der Aufrufer kann sie ersetzen,
# damit der Dienst nicht auf genau eine Seite festgenagelt ist.
DEFAULT_READY_EXPR = 'window.__analyseReady === true'
DEFAULT_ERROR_EXPR = 'window.__analyseError'


class RenderError(Exception):
    """Aufnahme ist endgültig gescheitert — die Meldung ist der Klartext-Grund."""


class BrowserPool:
    """Hält genau einen langlebigen Chromium-Prozess und gibt je Aufnahme einen Tab aus."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self.started_at: Optional[float] = None
        self.last_used_at: Optional[float] = None
        self.rendered_pages: int = 0
        self.browser_starts: int = 0
        # Zahl der gerade laufenden Aufnahmen — der Leerlauf-Wächter darf einen
        # beschäftigten Browser nicht unter den Füßen wegziehen.
        self.active_renders: int = 0

    @property
    def running(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    async def get_browser(self) -> Browser:
        """Liefert den laufenden Browser, startet ihn beim ersten Mal (und nach Leerlauf)."""
        async with self._lock:
            if self._browser is not None and not self._browser.is_connected():
                logger.warning('Browser-Verbindung verloren — wird neu gestartet.')
                await self._close_locked()
            if self._browser is None:
                if self._playwright is None:
                    self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        # Im Container gibt es keinen Benutzer-Namensraum für die Sandbox.
                        '--no-sandbox',
                        # /dev/shm ist im Container klein; sonst stirbt Chromium bei großen Seiten.
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                    ],
                )
                self.started_at = time.time()
                self.browser_starts += 1
                logger.info(
                    'Chromium gestartet (Start Nr. %d, Leerlauf-Timeout %.0f s).',
                    self.browser_starts,
                    IDLE_TIMEOUT_SECONDS,
                )
            return self._browser

    async def _close_locked(self) -> None:
        """Browser schließen — Aufrufer hält bereits die Sperre."""
        if self._browser is not None:
            try:
                await self._browser.close()
            except PlaywrightError as exc:
                logger.warning('Browser liess sich nicht sauber schliessen: %s', exc)
            self._browser = None
            self.started_at = None

    async def close_if_idle(self) -> bool:
        """Beendet den Browser, wenn er lange genug unbenutzt ist. True = beendet."""
        if not self.running or self.active_renders > 0 or self.last_used_at is None:
            return False
        idle_for = time.time() - self.last_used_at
        if idle_for < IDLE_TIMEOUT_SECONDS:
            return False
        async with self._lock:
            # Zustand nach dem Warten auf die Sperre erneut prüfen.
            if self._browser is None or self.active_renders > 0:
                return False
            logger.info('Leerlauf von %.0f s erreicht — Chromium wird beendet.', idle_for)
            await self._close_locked()
            return True

    async def shutdown(self) -> None:
        async with self._lock:
            await self._close_locked()
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None


pool = BrowserPool()


async def _idle_watchdog() -> None:
    """Hintergrund-Wächter: beendet den Browser nach dem Leerlauf-Timeout."""
    while True:
        try:
            await asyncio.sleep(IDLE_CHECK_INTERVAL_SECONDS)
            await pool.close_if_idle()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover — Wächter darf nie sterben
            logger.exception('Leerlauf-Wächter hat sich verschluckt: %s', exc)


async def take_screenshot(
    url: str,
    width: int,
    height: int,
    full_page: bool,
    ready_expr: str,
    error_expr: str,
    timeout_ms: int,
) -> bytes:
    """Fotografiert eine Seite und gibt die PNG-Bytes zurück.

    Args:
        url: Vollständige Adresse der Seite (interner Container-Name).
        width: Fensterbreite in Pixeln.
        height: Fensterhöhe in Pixeln.
        full_page: True = Vollseiten-Aufnahme statt nur des sichtbaren Ausschnitts.
        ready_expr: JavaScript-Ausdruck, der wahr wird, sobald die Seite fertig ist.
        error_expr: JavaScript-Ausdruck, der im Fehlerfall einen Klartext-Grund liefert.
        timeout_ms: Obergrenze für Laden und Warten auf das Fertig-Signal.

    Returns:
        Die PNG-Bytes der Aufnahme.

    Raises:
        RenderError: Laden gescheitert, Seite meldet einen Fehler oder Timeout.
    """
    browser = await pool.get_browser()
    pool.active_renders += 1
    started = time.monotonic()
    context = None
    try:
        context = await browser.new_context(
            viewport={'width': width, 'height': height},
            device_scale_factor=1,
        )
        page = await context.new_page()
        try:
            response = await page.goto(url, wait_until='domcontentloaded', timeout=timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise RenderError(f'Seite konnte nicht geladen werden (Timeout nach {timeout_ms} ms): {url}') from exc
        except PlaywrightError as exc:
            raise RenderError(f'Seite konnte nicht geladen werden: {url} — {exc}') from exc

        if response is not None and response.status >= 400:
            raise RenderError(f'Seite antwortete mit HTTP {response.status}: {url}')

        # Auf genau ein Signal warten: fertig ODER Klartext-Fehler der Seite.
        # Kein Rückfall auf eine feste Wartezeit — genau die soll der serverseitige Weg abschaffen.
        wait_expr = f"() => (({ready_expr}) === true) || (typeof ({error_expr}) === 'string')"
        timed_out = False
        try:
            await page.wait_for_function(wait_expr, timeout=timeout_ms)
        except PlaywrightTimeoutError:
            timed_out = True

        page_error = await page.evaluate(f'() => (({error_expr}) || null)')
        if isinstance(page_error, str) and page_error:
            raise RenderError(f'Die Seite meldet einen Fehler: {page_error}')
        if timed_out:
            raise RenderError(
                f'Zeitüberschreitung nach {timeout_ms} ms: Die Seite hat kein Fertig-Signal '
                f'gesetzt ({ready_expr}) und auch keinen Fehler gemeldet.'
            )

        png = await page.screenshot(full_page=full_page, type='png')
        pool.rendered_pages += 1
        logger.info(
            'Aufnahme fertig in %.2f s (%d Bytes, %dx%d, full_page=%s): %s',
            time.monotonic() - started, len(png), width, height, full_page, url,
        )
        return png
    finally:
        if context is not None:
            try:
                await context.close()
            except PlaywrightError as exc:
                logger.warning('Tab liess sich nicht schliessen: %s', exc)
        pool.active_renders -= 1
        # Erst nach dem Ende der Aufnahme zählt der Leerlauf.
        pool.last_used_at = time.time()


app = FastAPI(title='BT Pro Renderer', docs_url=None, redoc_url=None)


@app.on_event('startup')
async def _startup() -> None:
    app.state.watchdog = asyncio.create_task(_idle_watchdog())
    logger.info(
        'Renderer bereit (Leerlauf-Timeout %.0f s, Prüftakt %.0f s, Vorgabe-Timeout %d ms).',
        IDLE_TIMEOUT_SECONDS, IDLE_CHECK_INTERVAL_SECONDS, DEFAULT_TIMEOUT_MS,
    )


@app.on_event('shutdown')
async def _shutdown() -> None:
    task = getattr(app.state, 'watchdog', None)
    if task is not None:
        task.cancel()
    await pool.shutdown()


@app.get('/health')
async def health() -> dict:
    """Zustandsauskunft. Aktualisiert den Leerlauf ausdrücklich NICHT."""
    now = time.time()
    return {
        'status': 'ok',
        'browser_running': pool.running,
        'browser_starts': pool.browser_starts,
        'browser_uptime_seconds': round(now - pool.started_at, 1) if pool.started_at else None,
        'idle_seconds': round(now - pool.last_used_at, 1) if pool.last_used_at else None,
        'idle_timeout_seconds': IDLE_TIMEOUT_SECONDS,
        'rendered_pages': pool.rendered_pages,
        'active_renders': pool.active_renders,
    }


@app.get('/render')
async def render(
    url: str = Query(..., description='Vollständige Adresse der zu fotografierenden Seite'),
    width: int = Query(1920, ge=320, le=8000, description='Fensterbreite in Pixeln'),
    height: int = Query(1080, ge=240, le=8000, description='Fensterhöhe in Pixeln'),
    full_page: bool = Query(True, description='Vollseiten-Aufnahme statt sichtbarem Ausschnitt'),
    ready_expr: str = Query(DEFAULT_READY_EXPR, description='JS-Ausdruck, der das Fertig-Signal prüft'),
    error_expr: str = Query(DEFAULT_ERROR_EXPR, description='JS-Ausdruck mit dem Klartext-Fehler der Seite'),
    timeout_ms: int = Query(DEFAULT_TIMEOUT_MS, ge=1000, le=600000, description='Obergrenze in Millisekunden'),
) -> Response:
    """Fotografiert die Seite und liefert das PNG — oder eine Fehlerantwort mit Klartext."""
    try:
        png = await take_screenshot(
            url=url,
            width=width,
            height=height,
            full_page=full_page,
            ready_expr=ready_expr,
            error_expr=error_expr,
            timeout_ms=timeout_ms,
        )
    except RenderError as exc:
        logger.warning('Aufnahme gescheitert: %s', exc)
        return JSONResponse(status_code=422, content={'error': str(exc)})
    except PlaywrightError as exc:
        logger.exception('Browser-Fehler bei der Aufnahme.')
        return JSONResponse(status_code=500, content={'error': f'Browser-Fehler: {exc}'})
    return Response(content=png, media_type='image/png')

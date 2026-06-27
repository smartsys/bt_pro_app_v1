"""
Worker-Tasks — RQ-Aufgaben für Hintergrund-Jobs

Jede Task-Funktion wird vom RQ-Worker aufgerufen.
- run_recompute_job: Equity-Recompute für einzelne Results
- run_backtest_job: Kompletten Backtest starten (Strategie ausführen + DB speichern)
"""

import inspect
import logging
from datetime import datetime

import pandas as pd

from user_data.utils.database.db import get_session
from user_data.utils.database.models import BacktestJob
from services.api.recompute import recompute_single_result

logger = logging.getLogger(__name__)


def run_recompute_job(job_id: int, result_id: int) -> bool:
    """Führt recompute_single_result aus und aktualisiert den Job-Status in der DB.

    Args:
        job_id: ID des BacktestJob-Eintrags
        result_id: ID des BacktestResult

    Returns:
        True wenn erfolgreich
    """
    session = get_session()
    try:
        # Status auf running setzen
        job = session.query(BacktestJob).filter(BacktestJob.id == job_id).first()
        if not job:
            logger.error(f"[WORKER] Job {job_id} nicht gefunden")
            return False
        job.status = 'running'
        job.started_at = datetime.now()
        session.commit()
    finally:
        session.close()

    # Recompute ausführen (sync=True: kein Background-Thread)
    try:
        success = recompute_single_result(result_id, sync=True)
        status = 'completed' if success else 'failed'
        error_msg = None if success else 'recompute_single_result gab False zurück'
    except Exception as e:
        status = 'failed'
        error_msg = str(e)[:2000]
        logger.error(f"[WORKER] Job {job_id} / Result {result_id} fehlgeschlagen: {e}")

    # Status aktualisieren
    session = get_session()
    try:
        job = session.query(BacktestJob).filter(BacktestJob.id == job_id).first()
        if job:
            job.status = status
            job.error_message = error_msg
            job.completed_at = datetime.now()
            session.commit()
    finally:
        session.close()

    return status == 'completed'


def run_full_metrics_job(result_id: int) -> bool:
    """Berechnet die langsamen Full-Metriken für ein einzelnes Result.

    Stufe 3: tail_ratio, VaR, CVaR, alpha, beta, information_ratio etc.
    Wird als Hintergrund-Job in der Recompute-Queue ausgeführt.

    Args:
        result_id: ID des BacktestResult

    Returns:
        True wenn erfolgreich
    """
    from services.api.recompute import compute_full_metrics
    try:
        success = compute_full_metrics(result_id)
        if success:
            logger.info(f"[WORKER] Full-Metriken für Result {result_id} berechnet")
        else:
            logger.error(f"[WORKER] Full-Metriken für Result {result_id} fehlgeschlagen")
        return success
    except Exception as e:
        logger.error(f"[WORKER] Full-Metriken für Result {result_id} Fehler: {e}")
        return False


def run_backtest_job(run_id: int) -> bool:
    """Führt einen kompletten Backtest aus: OHLC laden, Strategie ausführen, Ergebnisse speichern.

    Der BacktestRun wurde bereits vom API-Endpoint angelegt (sofort sichtbar in /runs).
    Liest backtest_config und indicators_config aus dem Run-Eintrag in der DB.

    Args:
        run_id: ID des bereits angelegten BacktestRun

    Returns:
        True wenn erfolgreich
    """
    from services.api.recompute import load_strategy_function
    from user_data.utils.database.repository import (
        save_strategy_results,
        update_backtest_run_status,
        update_backtest_run_progress,
    )
    from user_data.utils.database.models import BacktestRun
    from user_data.utils.ohlc.loader import load_ohlc_data
    # GEÄNDERT: Spec-Runner-Version für Reproduzierbarkeit (Ticket 01)
    from user_data.strategies.generic.spec_runner import VERSION as _spec_runner_version
    from sqlalchemy import text

    # Configs aus dem Run laden
    session = get_session()
    try:
        run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
        if not run:
            logger.error(f"[BACKTEST] Run #{run_id} nicht gefunden")
            return False
        # GEÄNDERT: Ticket 15 — _json-Suffix
        backtest_config_json = dict(run.backtest_config_json)
        indicators_json = dict(run.indicators_config_json)
        # testset_run_id für Increment-Logik merken (Ticket 05)
        testset_run_id = run.testset_run_id
        # GEÄNDERT: Ticket 21 — _rules-Fallback entfernt. Rules kommen ausschließlich aus iteration.spec_json.
        if run.iteration_id is None or run.iteration is None:
            raise ValueError(
                f"[BACKTEST] Run #{run_id}: iteration_id fehlt. "
                "Jeder Run muss eine Iteration mit spec_json haben."
            )
        iteration_spec = run.iteration.spec_json or {}
        rules_json = iteration_spec.get('rules')
        if rules_json is None:
            raise ValueError(
                f"[BACKTEST] Run #{run_id}: iteration.spec_json enthält keinen 'rules'-Key."
            )
    finally:
        session.close()

    # GEÄNDERT: Status auf 'running' setzen — Job wird jetzt tatsächlich ausgeführt
    update_backtest_run_status(run_id, status='running')

    logger.info(f"[BACKTEST] Start: {backtest_config_json['symbols'][0]} "
                f"{backtest_config_json['exchange']} {backtest_config_json['timeframe']} (Run #{run_id})")

    run_status = 'failed'
    try:
        # OHLC-Daten laden
        ohlc_data = load_ohlc_data(backtest_config_json)

        # Strategie-Funktion dynamisch laden und ausführen
        # GEÄNDERT: Ticket 12 — rules_json explizit übergeben (kein _rules-Key mehr)
        # GEÄNDERT: rules_json nur übergeben, wenn die Funktion es akzeptiert
        # (handgeschriebene Strategien haben keinen rules_json-Parameter)
        strategy_fn = load_strategy_function(backtest_config_json['import_path'])
        strategy_kwargs = {
            'indicators_json': indicators_json,
            'backtest_config_json': backtest_config_json,
        }
        strategy_params = inspect.signature(strategy_fn).parameters
        if 'rules_json' in strategy_params:
            strategy_kwargs['rules_json'] = rules_json
        # GEÄNDERT: Chunk-Fortschritt — Callback injizieren, der pro Chunk den DB-Stand
        # aktualisiert. Nur für Strategie-Funktionen, die den Parameter akzeptieren
        # (Spec-Runner); Hardcoded-Legacy-Strategien ohne den Parameter bleiben unberührt.
        if 'progress_callback' in strategy_params:
            strategy_kwargs['progress_callback'] = (
                lambda current_chunk, total_chunks: update_backtest_run_progress(
                    run_id, current_chunk, total_chunks
                )
            )
        strategy_results = strategy_fn(ohlc_data, **strategy_kwargs)

        # Ergebnisse in DB speichern
        # GEÄNDERT: Spec-Runner-Version mitschreiben (Ticket 01)
        # GEÄNDERT: Ticket 41 — rules und backtest_config für vollständigen Snapshot durchreichen
        n_results = save_strategy_results(
            run_id=run_id,
            strategy_results=strategy_results,
            spec_runner_version=_spec_runner_version,
            rules=rules_json,
            backtest_config=backtest_config_json,
        )

        logger.info(f"[BACKTEST] Fertig: {n_results} Kombinationen gespeichert (Run #{run_id})")
        run_status = 'completed'

    except Exception as e:
        update_backtest_run_status(run_id, status='failed', error_message=str(e))
        logger.error(f"[BACKTEST] Run #{run_id} fehlgeschlagen: {e}", exc_info=True)

    # GEÄNDERT: Atomares Increment für TestSet-Runs (Ticket 05)
    if testset_run_id is not None:
        _increment_testset_run(testset_run_id, run_status)

    return run_status == 'completed'


# GEÄNDERT: Sekunden je Timeframe für die deterministische Vorab-Schätzung der
# zu ladenden Intervalle (Bars). Bewusst explizit statt pd.Timedelta-Parsing, weil
# 'm' dort mehrdeutig (Monat vs. Minute) interpretiert werden kann.
_TF_SECONDS: dict = {
    '1m': 60, '5m': 300, '15m': 900, '30m': 1800,
    '1h': 3600, '2h': 7200, '4h': 14400, '6h': 21600,
    '12h': 43200, '1d': 86400, '1w': 604800,
}

# GEÄNDERT: Fortschritts-Hook-Status. Pro Worker-Child eigen (RQ forkt je Job),
# daher kein Leck zwischen parallelen Jobs.
_progress_ctx: dict = {}
_progress_hook_installed: bool = False


def _expected_intervals(start_ts, end_ts, tf_seconds) -> int:
    """Schätzt die Anzahl der Intervalle (Bars) zwischen zwei Zeitpunkten.

    Args:
        start_ts: tz-bewusster Startzeitpunkt (oder None).
        end_ts: tz-bewusster Endzeitpunkt (oder None).
        tf_seconds: Sekunden je Bar des Timeframes (oder None/0).

    Returns:
        Anzahl erwarteter Bars, mindestens 0.
    """
    if start_ts is None or end_ts is None or not tf_seconds:
        return 0
    secs = (end_ts - start_ts).total_seconds()
    if secs <= 0:
        return 0
    return int(secs // tf_seconds)


def _install_binance_progress_hook() -> None:
    """Klinkt sich einmalig je Prozess in vbts ProgressBar ein.

    Wir ändern die Download-Logik NICHT, sondern zählen nur die Chunk-Updates der
    Binance-Fortschrittsleiste (bar_id 'binance') mit und melden den Stand über den
    aktiven Callback in `_progress_ctx`. Fällt der Hook aus, läuft der Download
    unverändert weiter — nur die Live-Zahl bleibt dann stehen (per try/except
    abgesichert).
    """
    global _progress_hook_installed
    if _progress_hook_installed:
        return
    from vectorbtpro.utils.pbar import ProgressBar

    _orig_update = ProgressBar.update

    def _patched_update(self, n: int = 1) -> None:
        _orig_update(self, n=n)
        try:
            ctx = _progress_ctx
            report = ctx.get('report')
            if report is not None and getattr(self, 'bar_id', None) == 'binance':
                ctx['chunks'] = ctx.get('chunks', 0) + 1
                report(ctx['chunks'] * ctx['limit'])
        except Exception:
            pass

    ProgressBar.update = _patched_update
    _progress_hook_installed = True


def run_ohlc_download_job(job_id: int) -> bool:
    """Lädt OHLC-Daten via vbt.BinanceData.pull und schreibt sie in die HDF5-Datei.

    job_type 'download': neue Datei anlegen (oder Symbole ergänzen)
    job_type 'update':   bestehende Datei per .update() fortschreiben

    Jeder Job trägt im Regelfall genau ein Symbol (die API zerlegt Mehrfach-Eingaben
    in Einzel-Jobs). Der Worker schätzt vorab die zu ladenden Intervalle und meldet
    den Fortschritt live in die DB (intervals_total/intervals_done).

    Args:
        job_id: ID des OhlcDownloadJob

    Returns:
        True wenn erfolgreich
    """
    import os
    import vectorbtpro as vbt

    from user_data.config import Config
    from user_data.utils.database.models import OhlcDownloadJob

    # Job laden
    session = get_session()
    try:
        job = session.query(OhlcDownloadJob).filter(OhlcDownloadJob.id == job_id).first()
        if not job:
            logger.error(f"[OHLC-DL] Job {job_id} nicht gefunden")
            return False
        job_type = job.job_type
        exchange = job.exchange
        timeframe = job.timeframe
        symbols = list(dict.fromkeys(job.symbols))
        start_date = job.start_date
        job_end_date = job.end_date
        job.status = 'running'
        job.started_at = datetime.now()
        session.commit()
    finally:
        session.close()

    datafile = os.path.join(Config.DATA_PATH, f'ohlcv_{timeframe}_{exchange}.h5')
    logger.info(f"[OHLC-DL] Job #{job_id} {job_type} {exchange}/{timeframe} symbols={symbols} -> {datafile}")

    # GEÄNDERT: Binance-Schonung env-konfigurierbar. Einmal je Job-Child in die
    # vbt-Settings schreiben, damit pull UND update denselben delay/limit nutzen.
    # show_progress aus, damit keine tqdm-Zeilen in die Worker-Logs laufen — der
    # Fortschritts-Hook zählt die Chunk-Updates trotzdem mit.
    fetch_delay = float(os.getenv('OHLC_FETCH_DELAY', '1.5'))
    fetch_limit = int(os.getenv('OHLC_FETCH_LIMIT', '1000'))
    vbt.settings['data']['custom']['binance']['delay'] = fetch_delay
    vbt.settings['data']['custom']['binance']['limit'] = fetch_limit
    vbt.settings['data']['custom']['binance']['show_progress'] = False

    tf_seconds = _TF_SECONDS.get(timeframe)
    _install_binance_progress_hook()

    def _write_progress(total=None, done=None) -> None:
        """Schreibt total/done in die Job-Zeile (eigene Kurz-Session, fehlertolerant)."""
        s = get_session()
        try:
            j = s.query(OhlcDownloadJob).filter(OhlcDownloadJob.id == job_id).first()
            if j:
                if total is not None:
                    j.intervals_total = int(total)
                if done is not None:
                    cap = j.intervals_total if j.intervals_total is not None else done
                    j.intervals_done = int(min(done, cap))
                s.commit()
        except Exception:
            s.rollback()
        finally:
            s.close()

    # GEÄNDERT: Tatsächlich resultierender Datenbereich (min Start / max Ende über alle
    # erfolgreich verarbeiteten Symbole). Wird zurückgeschrieben, damit der Job den
    # echten Range zeigt statt des relativen Platzhalters "now UTC" / leerem Start.
    resolved_start = None
    resolved_end = None
    data_ranges: list[tuple] = []

    def _parse_end() -> "pd.Timestamp":
        """Enddatum des Jobs als tz-bewusster Timestamp; leer/'now UTC' -> jetzt."""
        if job_end_date and job_end_date != 'now UTC':
            try:
                return pd.Timestamp(job_end_date, tz='utc')
            except Exception:
                pass
        return pd.Timestamp.now(tz='utc')

    try:
        now_end = _parse_end()
        # Planung: pro Symbol Start/Ende und erwartete Intervalle bestimmen.
        # plan-Eintrag: (symbol, start_ts, end_ts, n_intervals, skip_reason|None)
        plan: list[tuple] = []
        if job_type == 'update':
            if not os.path.exists(datafile):
                raise FileNotFoundError(f'Datei nicht gefunden: {datafile}')
            with pd.HDFStore(datafile, mode='r') as store:
                file_keys = set(k.lstrip('/') for k in store.keys())
            for sym in symbols:
                if sym not in file_keys:
                    plan.append((sym, None, None, 0, f'{sym}: nicht in Datei'))
                    continue
                d0 = vbt.BinanceData.from_hdf(
                    sym, paths=datafile, match_paths=False,
                    fetch_kwargs=dict(timeframe=timeframe),
                )
                idx = d0.index
                if len(idx):
                    # GEÄNDERT: Start = ein Tag vor dem letzten Bar (Nutzer-Vorgabe),
                    # geclamped auf den ersten Bar. Der Tages-Puffer deckt einen evtl.
                    # unvollständigen letzten Bar mit ab; update() merged per Index.
                    start_ts = max(idx[-1] - pd.Timedelta(days=1), idx[0])
                else:
                    start_ts = None
                n = _expected_intervals(start_ts, now_end, tf_seconds)
                plan.append((sym, start_ts, now_end, n, None))
        else:
            start_ts = None
            if start_date:
                try:
                    start_ts = pd.Timestamp(start_date, tz='utc')
                except Exception:
                    start_ts = None
            for sym in symbols:
                n = _expected_intervals(start_ts, now_end, tf_seconds)
                plan.append((sym, start_ts, now_end, n, None))

        intervals_total = sum(p[3] for p in plan)
        _write_progress(total=intervals_total, done=0)

        loaded: list[str] = []
        errors: list[str] = []
        base_done = 0
        for sym, sym_start, sym_end, n, skip in plan:
            if skip:
                errors.append(skip)
                logger.warning(f"[OHLC-DL] Job #{job_id} übersprungen: {skip}")
                continue
            # Live-Reporting für genau dieses Symbol: Basis = bereits fertige Symbole,
            # gedeckelt auf base_done + n, damit der Zähler nicht überläuft.
            _progress_ctx.clear()
            _progress_ctx.update({
                'chunks': 0,
                'limit': fetch_limit,
                'report': (lambda b, base=base_done, cap=base_done + n:
                           _write_progress(done=min(base + b, cap))),
            })
            try:
                if job_type == 'update':
                    d = vbt.BinanceData.from_hdf(
                        sym, paths=datafile, match_paths=False,
                        fetch_kwargs=dict(timeframe=timeframe),
                    )
                    if sym_start is not None:
                        d = d.update(start=sym_start, end='now UTC')
                    else:
                        d = d.update(end='now UTC')
                    d.to_hdf(datafile)
                    logger.info(f"[OHLC-DL] Job #{job_id} updated: {sym}")
                else:
                    d = vbt.BinanceData.pull(
                        sym, start=start_date, end=job_end_date or 'now UTC',
                        timeframe=timeframe,
                    )
                    d.to_hdf(datafile)
                    logger.info(f"[OHLC-DL] Job #{job_id} geladen: {sym}")
                loaded.append(sym)
                idx = d.index
                if len(idx):
                    data_ranges.append((idx[0], idx[-1]))
                base_done += n
            except Exception as sym_exc:
                errors.append(f'{sym}: {sym_exc}')
                logger.warning(f"[OHLC-DL] Job #{job_id} Symbol {sym} fehlgeschlagen: {sym_exc}")
            finally:
                _progress_ctx.clear()
                _write_progress(done=base_done)

        if not loaded:
            raise RuntimeError(f'Kein Symbol erfolgreich verarbeitet. Fehler: {errors}')
        if data_ranges:
            resolved_start = min(r[0] for r in data_ranges)
            resolved_end = max(r[1] for r in data_ranges)
        verb = 'Update' if job_type == 'update' else 'Download'
        # Angezeigte Meldung ohne Dateiname (nicht benötigt); Dateiname bleibt nur im Log.
        msg_parts = [f'{verb} abgeschlossen für {loaded}']
        if errors:
            msg_parts.append(f'Fehler: {errors}')
        message = ' | '.join(msg_parts)

        status = 'completed'
        logger.info(f"[OHLC-DL] Job #{job_id} {status} ({os.path.basename(datafile)}): {message}")
    except Exception as exc:
        status = 'failed'
        message = str(exc)[:2000]
        logger.error(f"[OHLC-DL] Job #{job_id} fehlgeschlagen: {exc}", exc_info=True)

    session = get_session()
    try:
        job = session.query(OhlcDownloadJob).filter(OhlcDownloadJob.id == job_id).first()
        if job:
            job.status = status
            job.message = message
            job.completed_at = datetime.now()
            # GEÄNDERT: echten Datenbereich speichern, damit der Job-Range den tatsächlichen
            # Start und das aktualisierte Enddatum zeigt (statt leerem Start / "now UTC").
            if status == 'completed' and resolved_start is not None:
                job.start_date = resolved_start.strftime('%Y-%m-%d')
                job.end_date = resolved_end.strftime('%Y-%m-%d')
            session.commit()
    finally:
        session.close()

    return status == 'completed'


def _delete_all_non_favorites() -> dict:
    """Löscht alle non-favorisierten Results (+Details) und verwaiste Runs.

    Gemeinsame Kernlogik der beiden 'Alle löschen'-Jobs (Results und Runs). Schützt
    beide Stern-Markierungen (is_favorite=0 UND is_doc_favorite=0) und meldet den
    Fortschritt ins RQ-Job-Meta (vom delete-status-Endpoint gelesen).

    Returns:
        dict mit Anzahl gelöschter Results und Runs.
    """
    # Lazy-Import, um den Worker-Start nicht an den schweren Router zu koppeln
    from rq import get_current_job
    from sqlalchemy import text

    rq_job = get_current_job()

    def _report(done: int, total: int) -> None:
        """Schreibt den Lösch-Fortschritt ins RQ-Job-Meta (vom Status-Endpoint gelesen)."""
        if rq_job is None:
            return
        pct = round(done / total * 100) if total else 100
        rq_job.meta['progress'] = {'step': done, 'total': total, 'pct': pct,
                                   'label': f'{done}/{total} Results gelöscht'}
        rq_job.save_meta()

    # Detail-Tabellen mit losem Fremdschlüssel result_id (INT, kein FK-Constraint)
    detail_tables = ['backtest_result_indicators', 'backtest_result_equity',
                     'backtest_result_trades', 'backtest_result_orders',
                     'backtest_result_positions', 'backtest_result_params']
    # Alle Tabellen, die der Lauf leert (in einem TRUNCATE-Schwung)
    all_tables = ['backtest_results', 'backtest_runs', 'backtest_jobs'] + detail_tables

    session = get_session()
    try:
        total_before = session.execute(text("SELECT count(*) FROM backtest_results")).scalar() or 0
        runs_before = session.execute(text("SELECT count(*) FROM backtest_runs")).scalar() or 0
        _report(0, total_before)

        # Favoriten-Result-IDs bestimmen (beide Stern-Markierungen schützen)
        keep_ids = [row[0] for row in session.execute(text(
            "SELECT id FROM backtest_results WHERE is_favorite = 1 OR is_doc_favorite = 1"
        )).fetchall()]

        if not keep_ids:
            # Kein Favorit -> alle Tabellen komplett leeren (schnellster Weg, eine Sperre)
            session.execute(text("TRUNCATE TABLE " + ", ".join(all_tables)))
            session.commit()
            deleted_results = total_before
            deleted_runs = runs_before
        else:
            # IDs aus der DB sind reine Integer -> sicheres Inlining (analog _delete_result_details)
            ids_csv = ",".join(str(i) for i in keep_ids)

            # Phase A: Favoriten-Zeilen in Temp-Tabellen sichern. Muss VOR dem TRUNCATE
            # passieren, da die zu erhaltenden Runs aus den Favoriten-Results abgeleitet
            # werden. ON COMMIT DROP raeumt die Temp-Tabellen beim Commit selbst auf.
            session.execute(text(
                f"CREATE TEMP TABLE _keep_results ON COMMIT DROP AS "
                f"SELECT * FROM backtest_results WHERE id IN ({ids_csv})"))
            session.execute(text(
                f"CREATE TEMP TABLE _keep_runs ON COMMIT DROP AS "
                f"SELECT * FROM backtest_runs WHERE id IN "
                f"(SELECT DISTINCT run_id FROM backtest_results WHERE id IN ({ids_csv}))"))
            # backtest_jobs: Jobs eines Favoriten-Results und ungebundene Jobs (result_id NULL)
            # bleiben erhalten -- identisch zur bisherigen Per-Result-Loeschsemantik.
            session.execute(text(
                f"CREATE TEMP TABLE _keep_backtest_jobs ON COMMIT DROP AS "
                f"SELECT * FROM backtest_jobs WHERE result_id IS NULL OR result_id IN ({ids_csv})"))
            for tbl in detail_tables:
                session.execute(text(
                    f"CREATE TEMP TABLE _keep_{tbl} ON COMMIT DROP AS "
                    f"SELECT * FROM {tbl} WHERE result_id IN ({ids_csv})"))

            # Phase B: alle betroffenen Tabellen in einem Schwung leeren (keine Index-Pflege,
            # keine toten Tupel, sofortige Platzfreigabe -- auch auf den Hypertables)
            session.execute(text("TRUNCATE TABLE " + ", ".join(all_tables)))

            # Phase C: gesicherte Favoriten-Zeilen zurueckschreiben
            session.execute(text("INSERT INTO backtest_results SELECT * FROM _keep_results"))
            session.execute(text("INSERT INTO backtest_runs SELECT * FROM _keep_runs"))
            session.execute(text("INSERT INTO backtest_jobs SELECT * FROM _keep_backtest_jobs"))
            for tbl in detail_tables:
                session.execute(text(f"INSERT INTO {tbl} SELECT * FROM _keep_{tbl}"))

            session.commit()
            kept_runs = session.execute(text("SELECT count(*) FROM backtest_runs")).scalar() or 0
            deleted_results = total_before - len(keep_ids)
            deleted_runs = runs_before - kept_runs

        _report(total_before, total_before)
        logger.info(f"[DELETE-ALL] {deleted_results} Results, {deleted_runs} verwaiste Runs "
                    f"geloescht (TRUNCATE-Pfad, {len(keep_ids)} Favoriten erhalten)")
        return {'deleted_results': deleted_results, 'deleted_runs': deleted_runs}
    finally:
        session.close()


def delete_all_results_job() -> dict:
    """Löscht alle Results außer Favoriten inkl. Detail-Daten und verwaister Runs.

    Läuft als RQ-Hintergrund-Job, damit der "Alle löschen"-Klick die UI nicht
    minutenlang blockiert (Löschen über TimescaleDB-Hypertables ist teuer). Der
    Status wird über RQ/Redis verfolgt, nicht über einen DB-Job-Eintrag.

    Returns:
        dict mit Anzahl gelöschter Results und Runs (RQ legt den Rückgabewert als
        Job-Result ab; das Frontend zeigt ihn nach Abschluss an).
    """
    return _delete_all_non_favorites()


def delete_all_runs_job() -> dict:
    """Wie delete_all_results_job, stoppt zusätzlich laufende Backtest-Berechnungen.

    Spiegelt den vormals synchronen DELETE /runs-Pfad: gleiche Löschmenge (non-fav
    Results + verwaiste Runs), danach _stop_run_jobs(None), damit zu gelöschten Runs
    keine Berechnung sinnlos weiterrechnet. _stop_run_jobs greift nur echte
    run_backtest_job-Berechnungen ab — dieser Lösch-Job stoppt sich also nicht selbst.

    Returns:
        dict mit Anzahl gelöschter Results und Runs.
    """
    from services.api.routes.api_backtest import _stop_run_jobs
    result = _delete_all_non_favorites()
    _stop_run_jobs(None)
    return result


def _increment_testset_run(testset_run_id: int, run_status: str) -> None:
    """Inkrementiert n_runs_completed atomar via SQL und setzt ggf. den Gesamt-Status.

    Kein ORM-Read-Modify-Write — atomar via UPDATE ... SET n = n + 1,
    damit parallel laufende Worker sich nicht gegenseitig überschreiben.

    Args:
        testset_run_id: ID des TestSetRun-Datensatzes.
        run_status: 'completed' oder 'failed' — bestimmt Folge-Logik.
    """
    from user_data.utils.database.db import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.begin() as conn:
        # Atomar inkrementieren
        conn.execute(
            text(
                "UPDATE testset_runs "
                "SET n_runs_completed = n_runs_completed + 1 "
                "WHERE id = :tid"
            ),
            {'tid': testset_run_id},
        )

        if run_status == 'failed':
            # Status nur auf 'failed' setzen, wenn noch kein Endzustand erreicht
            conn.execute(
                text(
                    "UPDATE testset_runs "
                    "SET status = 'failed' "
                    "WHERE id = :tid AND status NOT IN ('completed', 'failed')"
                ),
                {'tid': testset_run_id},
            )
            logger.info('[TESTSET-RUN] TestSetRun #%d: Run fehlgeschlagen -> status=failed', testset_run_id)

        elif run_status == 'completed':
            # Nach Increment prüfen ob alle Runs abgeschlossen sind
            row = conn.execute(
                text(
                    "SELECT n_runs_completed, n_runs_total, status "
                    "FROM testset_runs WHERE id = :tid"
                ),
                {'tid': testset_run_id},
            ).fetchone()

            if row and row.n_runs_completed >= row.n_runs_total and row.status not in ('completed', 'failed'):
                conn.execute(
                    text(
                        "UPDATE testset_runs "
                        "SET status = 'completed', completed_at = NOW() "
                        "WHERE id = :tid AND status NOT IN ('completed', 'failed')"
                    ),
                    {'tid': testset_run_id},
                )
                logger.info(
                    '[TESTSET-RUN] TestSetRun #%d abgeschlossen (%d/%d Runs)',
                    testset_run_id, row.n_runs_completed, row.n_runs_total,
                )
                # GEÄNDERT: Aggregat-Trigger (Ticket 06) — direkter Aufruf im Worker-Prozess
                _trigger_leaderboard_aggregation(testset_run_id)


def _trigger_leaderboard_aggregation(testset_run_id: int) -> None:
    """Löst die Aggregat-Berechnung für einen abgeschlossenen TestSetRun aus.

    Wird direkt nach dem Status-Update auf 'completed' aufgerufen (kein zweiter Queue-Job).
    Exceptions werden nur geloggt — der Worker-Prozess wird nicht abgerissen.

    Args:
        testset_run_id: ID des abgeschlossenen TestSetRun.
    """
    from user_data.utils.database.repository_testsets import build_leaderboard_entry_for_testset_run

    try:
        entry = build_leaderboard_entry_for_testset_run(testset_run_id)
        if entry is not None:
            logger.info(
                '[TESTSET-RUN] LeaderboardEntry #%d für TestSetRun #%d angelegt.',
                entry.id, testset_run_id,
            )
        else:
            logger.info(
                '[TESTSET-RUN] Aggregat für TestSetRun #%d: No-Op (bereits vorhanden oder nicht gefunden).',
                testset_run_id,
            )
    except Exception as exc:
        logger.error(
            '[TESTSET-RUN] Aggregat-Trigger für TestSetRun #%d fehlgeschlagen: %s',
            testset_run_id, exc, exc_info=True,
        )


def reindex_vault_chunk_job(
    target_path: str | None = None,
    trigger: str = "api",
    run_db_id: int | None = None,
) -> dict:
    """Führt einen inkrementellen Vault-Reindex aus und schreibt Chunks in vault_chunks.

    Wird periodisch alle 5 Minuten vom scheduler-Container eingereiht sowie manuell
    per API-Endpoint (Ticket 26) triggerbar. Protokolliert Lifecycle in vault_reindex_runs
    (Ticket 28).

    Args:
        target_path: Relativer Pfad ab vault_root, z.B. 'strategies/teststrategie/status.md'.
                     None = ganzer Vault.
        trigger: Herkunft des Jobs — 'api', 'scheduler' oder 'cli'.
        run_db_id: ID des bereits angelegten VaultReindexRun-Eintrags (Pre-Insert durch
                   den Endpoint). Falls None, wird der Eintrag via rq.get_current_job()
                   nachgeschlagen oder neu angelegt.

    Returns:
        Ergebnis-Dict mit files_scanned, files_reindexed, files_deleted, chunks_written,
        duration_seconds.
    """
    import os
    from pathlib import Path
    from services.vbt.knowledge.indexer import reindex
    from user_data.utils.database.models import VaultReindexRun

    # GEÄNDERT: Ticket 28 — Job-ID aus rq-Kontext ermitteln
    _job_id: str | None = None
    try:
        from rq import get_current_job as _get_current_job  # noqa: PLC0415
        _rq_job = _get_current_job()
        if _rq_job:
            _job_id = str(_rq_job.id)
    except Exception:
        pass

    scope = 'single-file' if target_path else 'full'

    # GEÄNDERT: Ticket 28 — Run-Eintrag auf 'running' setzen
    session = get_session()
    try:
        run_entry: VaultReindexRun | None = None
        if run_db_id is not None:
            run_entry = session.query(VaultReindexRun).filter(
                VaultReindexRun.id == run_db_id
            ).first()
        elif _job_id is not None:
            run_entry = session.query(VaultReindexRun).filter(
                VaultReindexRun.job_id == _job_id
            ).first()

        if run_entry is None and _job_id is not None:
            # Fallback: neuen Eintrag anlegen (z.B. bei Scheduler ohne Pre-Insert)
            run_entry = VaultReindexRun(
                job_id=_job_id,
                scope=scope,
                target_path=target_path,
                trigger=trigger,
                status='running',
                started_at=datetime.now(),
            )
            session.add(run_entry)
            session.flush()
        elif run_entry is not None:
            run_entry.status = 'running'
            run_entry.started_at = datetime.now()

        session.commit()
        run_db_id = run_entry.id if run_entry else None
    finally:
        session.close()

    vault_root = Path(os.environ.get("VAULT_ROOT", "/obsidian_vault"))
    target: Path | None = None
    if target_path:
        target = vault_root / target_path

    try:
        result = reindex(vault_root=vault_root, target_path=target)
        logger.info("[VAULT-JOB] Reindex-Ergebnis: %s", result)
    except Exception as exc:
        # GEÄNDERT: Ticket 28 — Fehler in DB schreiben, dann Exception weiterwerfen
        if run_db_id is not None:
            session = get_session()
            try:
                run_entry = session.query(VaultReindexRun).filter(
                    VaultReindexRun.id == run_db_id
                ).first()
                if run_entry:
                    run_entry.status = 'failed'
                    run_entry.finished_at = datetime.now()
                    if run_entry.started_at:
                        run_entry.duration_seconds = (
                            run_entry.finished_at - run_entry.started_at
                        ).total_seconds()
                    run_entry.error_message = str(exc)
                    session.commit()
            finally:
                session.close()
        raise

    # GEÄNDERT: Ticket 28 — Erfolg in DB schreiben
    if run_db_id is not None:
        session = get_session()
        try:
            run_entry = session.query(VaultReindexRun).filter(
                VaultReindexRun.id == run_db_id
            ).first()
            if run_entry:
                run_entry.status = 'success'
                run_entry.finished_at = datetime.now()
                if run_entry.started_at:
                    run_entry.duration_seconds = (
                        run_entry.finished_at - run_entry.started_at
                    ).total_seconds()
                run_entry.files_scanned = result.get('files_scanned')
                run_entry.files_reindexed = result.get('files_reindexed')
                run_entry.files_deleted = result.get('files_deleted')
                run_entry.chunks_written = result.get('chunks_written')
                # GEÄNDERT: Ticket 34 — reindexierte und gelöschte Pfade als JSONB speichern
                run_entry.files_changed = {
                    'reindexed': result.get('reindexed_paths', []),
                    'deleted': result.get('deleted_paths', []),
                }
                session.commit()
        finally:
            session.close()

    return result

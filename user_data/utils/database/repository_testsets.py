"""
Repository-Funktionen für TestSets, TestSetRuns und LeaderboardEntries

Isolierter Themenbereich für TestSet-Verwaltung (Tickets 02-07).
Enthält CRUD-Operationen für TestSets sowie
TestSetRun- und LeaderboardEntry-Operationen sowie
Aggregat-Berechnung.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from user_data.utils.database.models import (
    BacktestConfig,
    BacktestResult,
    BacktestRun,
    LeaderboardEntry,
    StrategyIteration,
    TestSet,
    TestSetRun,
)

logger = logging.getLogger(__name__)


# GEÄNDERT: eigener Fehlertyp für den Lösch-Konflikt am TestSet.
# GEÄNDERT: Der Fehler ist keine endgültige Ablehnung mehr, sondern der Anlass für
# eine Rückfrage: Er meldet, was am TestSet noch dranhängt, damit die Oberfläche
# den Löschwunsch bestätigen lassen kann (Löschen dann mit force=True).
class TestSetRunsBlockingError(Exception):
    """Am TestSet hängen noch Testset-Läufe — Löschen erst nach Bestätigung.

    Attributes:
        blocking_testset_runs: Anzahl der Testset-Läufe, die am TestSet hängen.
        blocking_backtest_runs: Anzahl der an diesen Läufen hängenden Backtest-Runs.
    """

    def __init__(self, blocking_testset_runs: int, blocking_backtest_runs: int) -> None:
        self.blocking_testset_runs = blocking_testset_runs
        self.blocking_backtest_runs = blocking_backtest_runs
        super().__init__(
            f'{blocking_testset_runs} Testset-Läufe mit insgesamt '
            f'{blocking_backtest_runs} Backtest-Runs hängen noch am TestSet.'
        )


def _validate_backtest_config_ids(session: Session, backtest_config_ids: List[int]) -> None:
    """Prüft, ob alle übergebenen backtest_config_ids in der DB existieren.

    Args:
        session: Aktive SQLAlchemy-Session.
        backtest_config_ids: Liste der zu prüfenden IDs.

    Raises:
        ValueError: Wenn eine oder mehr IDs nicht in backtest_configs existieren.
    """
    if not backtest_config_ids:
        return

    existing_ids = {
        row[0]
        for row in session.query(BacktestConfig.id)
        .filter(BacktestConfig.id.in_(backtest_config_ids))
        .all()
    }
    missing = [id_ for id_ in backtest_config_ids if id_ not in existing_ids]
    if missing:
        raise ValueError(
            f"Folgende backtest_config_ids existieren nicht: {missing}"
        )


# GEÄNDERT: Naming-Cleanup auf testset-Funktionsnamen

def create_testset(
    session: Session,
    name: str,
    backtest_config_ids: List[int],
    description: Optional[str] = None,
    created_by: Optional[str] = None,
    leaderboard_enabled: bool = False,
) -> TestSet:
    """Legt ein neues TestSet an.

    Args:
        session: Aktive SQLAlchemy-Session.
        name: Eindeutiger Name des TestSets.
        backtest_config_ids: Liste von backtest_configs.id (muss existieren).
        description: Optionale Beschreibung.
        created_by: Optionaler Ersteller-Name.
        leaderboard_enabled: Opt-in-Schalter für Leaderboard-Einträge (Default False).

    Returns:
        Das neu angelegte TestSet.

    Raises:
        ValueError: Wenn backtest_config_ids nicht-existierende IDs enthalten.
    """
    _validate_backtest_config_ids(session, backtest_config_ids)
    testset = TestSet(
        name=name,
        description=description,
        # GEÄNDERT: _json-Suffix
        backtest_config_ids_json=backtest_config_ids,
        leaderboard_enabled=leaderboard_enabled,
        created_by=created_by,
    )
    session.add(testset)
    session.commit()
    session.refresh(testset)
    logger.info("TestSet '%s' (ID %d) angelegt.", name, testset.id)
    return testset


def get_testset(session: Session, testset_id: int) -> Optional[TestSet]:
    """Gibt ein einzelnes TestSet zurück oder None.

    Args:
        session: Aktive SQLAlchemy-Session.
        testset_id: Primärschlüssel des TestSets.

    Returns:
        TestSet oder None.
    """
    return session.query(TestSet).filter(TestSet.id == testset_id).first()


def list_testsets(session: Session) -> List[TestSet]:
    """Gibt alle TestSets zurück — Favoriten zuerst, dann alphabetisch nach Name.

    Args:
        session: Aktive SQLAlchemy-Session.

    Returns:
        Liste aller TestSets.
    """
    # GEÄNDERT: Favoriten-Stern zuerst, danach die bisherige Namens-Sortierung
    return session.query(TestSet).order_by(TestSet.is_favorite.desc(), TestSet.name).all()


def toggle_testset_favorite(session: Session, testset_id: int) -> Optional[TestSet]:
    """Schaltet den Favoriten-Stern eines TestSets um.

    Args:
        session: Aktive SQLAlchemy-Session.
        testset_id: Primärschlüssel des TestSets.

    Returns:
        Das aktualisierte TestSet oder None wenn nicht gefunden.
    """
    testset = session.query(TestSet).filter(TestSet.id == testset_id).first()
    if testset is None:
        return None
    testset.is_favorite = 0 if testset.is_favorite else 1
    session.commit()
    session.refresh(testset)
    logger.info("TestSet ID %d: is_favorite -> %d.", testset_id, testset.is_favorite)
    return testset


def update_testset(
    session: Session,
    testset_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    backtest_config_ids: Optional[List[int]] = None,
    created_by: Optional[str] = None,
    leaderboard_enabled: Optional[bool] = None,
) -> Optional[TestSet]:
    """Aktualisiert ein bestehendes TestSet.

    Args:
        session: Aktive SQLAlchemy-Session.
        testset_id: Primärschlüssel des TestSets.
        name: Neuer Name (optional).
        description: Neue Beschreibung (optional).
        backtest_config_ids: Neue ID-Liste (optional, wird validiert).
        created_by: Neuer Ersteller (optional).
        leaderboard_enabled: Neuer Wert des Opt-in-Schalters (optional).

    Returns:
        Aktualisiertes TestSet oder None wenn nicht gefunden.

    Raises:
        ValueError: Wenn backtest_config_ids nicht-existierende IDs enthalten.
    """
    testset = session.query(TestSet).filter(TestSet.id == testset_id).first()
    if testset is None:
        return None

    if backtest_config_ids is not None:
        _validate_backtest_config_ids(session, backtest_config_ids)
        # GEÄNDERT: _json-Suffix
        testset.backtest_config_ids_json = backtest_config_ids

    if name is not None:
        testset.name = name
    if description is not None:
        testset.description = description
    if created_by is not None:
        testset.created_by = created_by
    if leaderboard_enabled is not None:
        testset.leaderboard_enabled = leaderboard_enabled

    session.commit()
    session.refresh(testset)
    logger.info("TestSet ID %d aktualisiert.", testset_id)
    return testset


def delete_testset(session: Session, testset_id: int, force: bool = False) -> Optional[bool]:
    """Löscht ausschließlich das TestSet selbst — alles Nachgelagerte bleibt stehen.

    GEÄNDERT: fing eine Fremdschlüsselverletzung ab (roher HTTP-500),
    weil testset_runs.testset_id damals per Fremdschlüssel auf testsets.id zeigte.
    GEÄNDERT: der Fremdschlüssel wurde per Migration entfernt
    (0019_drop_testset_runs_fk); testset_runs.testset_id ist seitdem auch in der
    Datenbank eine lose Referenz. Die Prüfung blieb dabei als harte Ablehnung stehen.
    GEÄNDERT: Aus der Ablehnung wird eine Rückfrage. Ein TestSet ist nur die
    Zusammenstellung von Backtest-Configs — es zu löschen heißt nicht, die damit
    erzeugten Daten zu löschen:

    - Hängen Testset-Läufe am TestSet, wird ohne ``force`` nichts gelöscht und
      TestSetRunsBlockingError mit den Anzahlen geworfen. Die Oberfläche nutzt das,
      um den Löschwunsch bestätigen zu lassen.
    - Mit ``force=True`` wird nur die TestSet-Zeile entfernt. Testset-Läufe,
      Backtest-Runs und deren Results bleiben unverändert bestehen; ihre
      ``testset_id`` zeigt danach auf ein nicht mehr vorhandenes TestSet.

    Args:
        session: Aktive SQLAlchemy-Session.
        testset_id: Primärschlüssel des TestSets.
        force: True überspringt die Rückfrage und löscht das TestSet direkt.

    Returns:
        True wenn gelöscht, oder None wenn das TestSet nicht existiert.

    Raises:
        TestSetRunsBlockingError: Wenn ohne ``force`` noch Testset-Läufe dranhängen.
    """
    testset = session.query(TestSet).filter(TestSet.id == testset_id).first()
    if testset is None:
        return None

    if not force:
        testset_run_ids = [
            row[0] for row in session.query(TestSetRun.id)
            .filter(TestSetRun.testset_id == testset_id).all()
        ]
        if testset_run_ids:
            backtest_run_count = (
                session.query(BacktestRun.id)
                .filter(BacktestRun.testset_run_id.in_(testset_run_ids))
                .count()
            )
            raise TestSetRunsBlockingError(len(testset_run_ids), backtest_run_count)

    session.delete(testset)
    session.commit()
    logger.info("TestSet ID %d gelöscht (Testset-Läufe und Runs bleiben bestehen).", testset_id)
    return True


# GEÄNDERT: Waisen-Schutz beim Löschen von Backtest-Runs.
def purge_empty_testset_runs(session: Session, testset_run_ids: Iterable[Optional[int]]) -> int:
    """Entfernt die Testset-Läufe aus der Liste, auf die kein Backtest-Run mehr zeigt.

    Wird von allen Lösch-Pfaden für Backtest-Runs aufgerufen, damit kein Testset-Lauf
    ohne die Runs zurückbleibt, aus denen er bestand. Läuft in der Session des Aufrufers
    (kein eigener Commit), damit Run-Löschung und Aufräumen dieselbe Transaktion teilen.

    Args:
        session: Aktive SQLAlchemy-Session — die Run-Löschungen müssen darin bereits
            ausgeführt (nicht zwingend committet) sein.
        testset_run_ids: IDs der Testset-Läufe, die von der Löschung betroffen waren.

    Returns:
        Anzahl der entfernten Testset-Läufe.
    """
    ids = {int(tid) for tid in testset_run_ids if tid is not None}
    if not ids:
        return 0

    still_used = {
        row[0] for row in session.query(BacktestRun.testset_run_id)
        .filter(BacktestRun.testset_run_id.in_(ids)).distinct().all()
    }
    empty_ids = sorted(ids - still_used)
    if not empty_ids:
        return 0

    deleted = (
        session.query(TestSetRun)
        .filter(TestSetRun.id.in_(empty_ids))
        .delete(synchronize_session=False)
    )
    logger.info("Verwaiste Testset-Läufe entfernt: %s", empty_ids)
    return deleted


# ============================================================================
# TestSetRun
# ============================================================================

def create_testset_run(
    session: Session,
    testset_id: int,
    strategy_family: str,
    strategy_name: str,
    n_runs_total: int,
    indicators_config_json: Optional[Dict[str, Any]] = None,
    triggered_by: Optional[str] = None,
    created_by: Optional[str] = None,
    status: str = 'queued',
) -> TestSetRun:
    """Legt einen neuen TestSetRun an.

    GEÄNDERT: indicators_config_json direkt (kein indicator_config_id FK mehr).

    Args:
        session: Aktive SQLAlchemy-Session.
        testset_id: Lose Referenz auf testsets.id (kein FK).
        strategy_family: Strategie-Familie (z.B. "teststrategie").
        strategy_name: Strategie-Name (z.B. "teststrategie_v1").
        n_runs_total: Gesamtanzahl der geplanten Runs.
        indicators_config_json: Optionale Indikator-Konfiguration als JSON-Dict.
        triggered_by: Herkunft des Triggers (z.B. "user:tom").
        created_by: Optionaler Ersteller-Name.
        status: Anfangsstatus (Standard: 'queued').

    Returns:
        Der neu angelegte TestSetRun.
    """
    run = TestSetRun(
        testset_id=testset_id,
        strategy_family=strategy_family,
        strategy_name=strategy_name,
        n_runs_total=n_runs_total,
        # GEÄNDERT: JSON inline statt FK
        indicators_config_json=indicators_config_json or {},
        triggered_by=triggered_by,
        created_by=created_by,
        status=status,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    logger.info("TestSetRun ID %d (TestSet %d) angelegt.", run.id, testset_id)
    return run


def get_testset_run(session: Session, testset_run_id: int) -> Optional[TestSetRun]:
    """Gibt einen einzelnen TestSetRun zurück oder None.

    Args:
        session: Aktive SQLAlchemy-Session.
        testset_run_id: Primärschlüssel des TestSetRuns.

    Returns:
        TestSetRun oder None.
    """
    return session.query(TestSetRun).filter(TestSetRun.id == testset_run_id).first()


def update_testset_run_status(
    session: Session,
    testset_run_id: int,
    status: str,
    n_runs_completed: Optional[int] = None,
    completed_at: Optional[datetime] = None,
) -> Optional[TestSetRun]:
    """Aktualisiert Status, Fortschritt und Abschlusszeit eines TestSetRuns.

    Args:
        session: Aktive SQLAlchemy-Session.
        testset_run_id: Primärschlüssel des TestSetRuns.
        status: Neuer Status (queued|running|completed|failed).
        n_runs_completed: Anzahl abgeschlossener Runs (optional).
        completed_at: Abschluss-Timestamp (optional).

    Returns:
        Aktualisierter TestSetRun oder None wenn nicht gefunden.
    """
    run = session.query(TestSetRun).filter(TestSetRun.id == testset_run_id).first()
    if run is None:
        return None

    run.status = status
    if n_runs_completed is not None:
        run.n_runs_completed = n_runs_completed
    if completed_at is not None:
        run.completed_at = completed_at

    session.commit()
    session.refresh(run)
    logger.info("TestSetRun ID %d: Status -> '%s'.", testset_run_id, status)
    return run


# ============================================================================
# LeaderboardEntry
# ============================================================================

def create_leaderboard_entry(
    session: Session,
    testset_id: int,
    strategy_family: str,
    strategy_name: str,
    configs_total: int,
    testset_snapshot: Dict[str, Any],
    strategy_snapshot: Dict[str, Any],
    winning_result_ids: List[Any],
    testset_run_id: Optional[int] = None,
    indicator_config_id: Optional[int] = None,
    spec_runner_version: Optional[str] = None,
    indicator_config_snapshot: Optional[Dict[str, Any]] = None,
    hint: Optional[str] = None,
    executive_summary: Optional[str] = None,
    mini_report: Optional[str] = None,
) -> LeaderboardEntry:
    """Legt einen neuen LeaderboardEntry mit Snapshots an.

    Aggregate (total_return_avg, max_drawdown_avg etc.) sind nullable und
    werden befüllt. configs_passed und filter_breached sind
    ebenfalls nullable, solange kein Goal-Filter definiert ist.

    Args:
        session: Aktive SQLAlchemy-Session.
        testset_id: TestSet-ID (nur Lookup, keine FK).
        strategy_family: Strategie-Familie.
        strategy_name: Strategie-Name.
        configs_total: Gesamtanzahl der evaluierten Konfigurationen.
        testset_snapshot: Vollständiger Snapshot des TestSets (SoT).
        strategy_snapshot: Strategie-Identifikations-Snapshot (SoT).
        winning_result_ids: Liste der Sweep-Sieger-result_ids.
        testset_run_id: Optionale FK auf testset_runs.id (für Idempotenz).
        indicator_config_id: Optionale Indikator-Config-ID.
        spec_runner_version: Optionale Spec-Runner-Version.
        indicator_config_snapshot: Optionaler Snapshot der Indikator-Config.
        hint: Optionaler Hinweis-Text.
        executive_summary: Optionale Zusammenfassung.
        mini_report: Optionaler Kurzbericht.

    Returns:
        Der neu angelegte LeaderboardEntry.
    """
    entry = LeaderboardEntry(
        testset_id=testset_id,
        testset_run_id=testset_run_id,
        strategy_family=strategy_family,
        strategy_name=strategy_name,
        indicator_config_id=indicator_config_id,
        spec_runner_version=spec_runner_version,
        configs_total=configs_total,
        # GEÄNDERT: _json-Suffix
        testset_snapshot_json=testset_snapshot,
        indicator_config_snapshot_json=indicator_config_snapshot,
        strategy_snapshot_json=strategy_snapshot,
        winning_result_ids_json=winning_result_ids,
        hint=hint,
        executive_summary=executive_summary,
        mini_report=mini_report,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    logger.info("LeaderboardEntry ID %d (TestSet %d) angelegt.", entry.id, testset_id)
    return entry


def get_leaderboard_entry(session: Session, entry_id: int) -> Optional[LeaderboardEntry]:
    """Gibt einen einzelnen LeaderboardEntry zurück oder None.

    Args:
        session: Aktive SQLAlchemy-Session.
        entry_id: Primärschlüssel des LeaderboardEntry.

    Returns:
        LeaderboardEntry oder None.
    """
    return session.query(LeaderboardEntry).filter(LeaderboardEntry.id == entry_id).first()


def list_leaderboard_entries_for_testset(
    session: Session,
    testset_id: int,
) -> List[LeaderboardEntry]:
    """Gibt alle LeaderboardEntries für ein TestSet, sortiert nach total_return_avg DESC.

    Einträge ohne Aggregate (total_return_avg IS NULL) erscheinen am Ende.

    Args:
        session: Aktive SQLAlchemy-Session.
        testset_id: TestSet-ID als Lookup.

    Returns:
        Liste der LeaderboardEntries, sortiert nach total_return_avg DESC (NULLs zuletzt).
    """
    return (
        session.query(LeaderboardEntry)
        .filter(LeaderboardEntry.testset_id == testset_id)
        .order_by(LeaderboardEntry.total_return_avg.desc().nulls_last())
        .all()
    )


def list_leaderboard_entries_with_triggered_by(
    session: Session,
    testset_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Gibt LeaderboardEntries mit triggered_by via LEFT JOIN.

    Da testset_runs nach einem Cleanup gelöscht sein kann, wird triggered_by
    per LEFT JOIN aus testset_runs geholt — NULL wenn Run nicht mehr existiert.
    Sortierung: total_return_avg DESC NULLS LAST.

    Args:
        session: Aktive SQLAlchemy-Session.
        testset_id: Optionale TestSet-ID. Ohne Angabe werden alle Einträge geliefert.

    Returns:
        Liste von Dicts mit allen Entry-Feldern plus triggered_by (oder None).
    """
    query = (
        session.query(LeaderboardEntry, TestSetRun.triggered_by)
        .outerjoin(TestSetRun, LeaderboardEntry.testset_run_id == TestSetRun.id)
    )
    if testset_id is not None:
        query = query.filter(LeaderboardEntry.testset_id == testset_id)
    rows = query.order_by(LeaderboardEntry.total_return_avg.desc().nulls_last()).all()
    result = []
    for entry, triggered_by in rows:
        result.append({
            'entry': entry,
            'triggered_by': triggered_by,
        })
    return result


# ============================================================================
# Aggregat-Berechnung
# ============================================================================

def build_leaderboard_entry_for_testset_run(
    testset_run_id: int,
) -> Optional[LeaderboardEntry]:
    """Berechnet Aggregate aus allen BacktestRuns eines TestSetRuns und schreibt einen LeaderboardEntry.

    Wird direkt im Worker-Prozess nach Abschluss aller Runs aufgerufen (kein zweiter Queue-Job).
    Idempotenz: Bei UNIQUE-Verletzung (testset_run_id bereits vorhanden) wird None zurückgegeben.

    Ablauf:
    1. TestSetRun + TestSet + BacktestConfigs + IndicatorConfig laden.
    2. Für jeden BacktestRun (in Reihenfolge der backtest_config_ids) den Sweep-Sieger ermitteln.
    3. Aggregate aus den nicht-leeren Siegern berechnen.
    4. Snapshots bauen und LeaderboardEntry persistieren.

    Ist das TestSet gelöscht, seine Läufe aber stehengeblieben (siehe delete_testset),
    tritt der letzte bekannte testset_snapshot_json aus dem Leaderboard an seine Stelle.
    Ohne einen solchen Snapshot entsteht kein Eintrag.

    Args:
        testset_run_id: Primärschlüssel des TestSetRun.

    Returns:
        Der neu angelegte LeaderboardEntry oder None bei Idempotenz-Fall / fehlendem TestSetRun.
    """
    from user_data.utils.database.db import get_session

    session = get_session()
    try:
        return _build_leaderboard_entry_in_session(session, testset_run_id)
    finally:
        session.close()


def _load_last_testset_snapshot(session: Session, testset_id: int) -> Optional[Dict[str, Any]]:
    """Holt den jüngsten testset_snapshot_json aus dem Leaderboard zu einem TestSet.

    Dient als Ersatzquelle, wenn die TestSet-Zeile gelöscht wurde, ihre Läufe aber
    bestehen geblieben sind. Verwertbar ist der Snapshot nur mit Config-Liste — ohne
    sie liesse sich weder die Positions-Reihenfolge noch der Sieger je Position
    bestimmen.

    Args:
        session: Aktive SQLAlchemy-Session.
        testset_id: ID des (gelöschten) TestSets.

    Returns:
        Der Snapshot als Dict, oder None wenn keiner mit Config-Liste existiert.
    """
    rows = (
        session.query(LeaderboardEntry.testset_snapshot_json)
        .filter(LeaderboardEntry.testset_id == testset_id)
        .order_by(LeaderboardEntry.id.desc())
        .all()
    )
    for (snapshot,) in rows:
        if snapshot and snapshot.get('backtest_config_ids_json'):
            return dict(snapshot)
    return None


def _build_leaderboard_entry_in_session(
    session: Session,
    testset_run_id: int,
) -> Optional[LeaderboardEntry]:
    """Interne Implementierung von build_leaderboard_entry_for_testset_run mit gegebener Session.

    Trennung ermöglicht Tests mit kontrollierter Test-Session (Rollback-Isolation).

    Args:
        session: Aktive SQLAlchemy-Session.
        testset_run_id: Primärschlüssel des TestSetRun.

    Returns:
        Der neu angelegte LeaderboardEntry oder None.
    """
    # --- TestSetRun laden ---
    testset_run = session.query(TestSetRun).filter(TestSetRun.id == testset_run_id).first()
    if testset_run is None:
        logger.warning('build_leaderboard_entry: TestSetRun #%d nicht gefunden.', testset_run_id)
        return None

    # --- TestSet laden ---
    testset = session.query(TestSet).filter(TestSet.id == testset_run.testset_id).first()

    # GEÄNDERT: Ein gelöschtes TestSet lässt seine Läufe bewusst stehen (siehe
    # delete_testset). Damit diese Läufe trotzdem im Leaderboard landen, tritt der
    # letzte bekannte testset_snapshot_json an die Stelle der TestSet-Zeile — dasselbe
    # Muster, mit dem die Leaderboard-Liste ihre Namen auflöst. Vorher endete der Lauf
    # hier ohne Eintrag und der Snapshot-Rerun quittierte das mit HTTP 500.
    fallback_snapshot: Optional[Dict[str, Any]] = None
    if testset is None:
        fallback_snapshot = _load_last_testset_snapshot(session, testset_run.testset_id)
        if fallback_snapshot is None:
            logger.warning(
                'build_leaderboard_entry: TestSet #%d gelöscht und kein früherer Snapshot '
                'vorhanden (TestSetRun #%d) — kein Leaderboard-Eintrag.',
                testset_run.testset_id, testset_run_id,
            )
            return None
        logger.info(
            'build_leaderboard_entry: TestSet #%d gelöscht — Snapshot des letzten '
            'Leaderboard-Eintrags wird verwendet (TestSetRun #%d).',
            testset_run.testset_id, testset_run_id,
        )

    if testset is not None:
        testset_name: Optional[str] = testset.name
        testset_description: Optional[str] = testset.description
        # GEÄNDERT: _json-Suffix
        config_ids: List[int] = list(testset.backtest_config_ids_json or [])
        leaderboard_enabled = bool(testset.leaderboard_enabled)
        snapshot_configs: Dict[int, Dict[str, Any]] = {}
    else:
        testset_name = fallback_snapshot.get('name')
        testset_description = fallback_snapshot.get('description')
        config_ids = [int(cid) for cid in (fallback_snapshot.get('backtest_config_ids_json') or [])]
        # Der Snapshot existiert nur, weil das TestSet damals im Leaderboard geführt
        # wurde — der Opt-in-Schalter stand also auf True und ist nicht mehr abfragbar.
        leaderboard_enabled = True
        snapshot_configs = {
            int(cfg['id']): cfg
            for cfg in (fallback_snapshot.get('configs') or [])
            if cfg.get('id') is not None
        }

    # GEÄNDERT: Opt-in-Schalter — nur bei aktiviertem leaderboard_enabled wird ein
    # LeaderboardEntry erstellt. Andernfalls bewusst überspringen (kein Fehler).
    if not leaderboard_enabled:
        logger.info(
            'build_leaderboard_entry: TestSet #%d hat leaderboard_enabled=False '
            '(TestSetRun #%d) — kein Leaderboard-Eintrag.',
            testset_run.testset_id, testset_run_id,
        )
        return None

    # --- BacktestConfigs in Reihenfolge der backtest_config_ids_json laden ---
    configs_by_id: Dict[int, BacktestConfig] = {}
    if config_ids:
        rows = session.query(BacktestConfig).filter(BacktestConfig.id.in_(config_ids)).all()
        configs_by_id = {c.id: c for c in rows}

    # GEÄNDERT: indicators_config_json direkt aus testset_run lesen (kein FK mehr)
    indicators_config_json_snapshot: Optional[Dict[str, Any]] = testset_run.indicators_config_json or None

    # --- BacktestRuns für diesen TestSetRun in Reihenfolge der config_ids ermitteln ---
    # Jeder BacktestRun ist einer BacktestConfig zugeordnet — über backtest_config JSON-Feld.
    # Wir laden alle zugehörigen Runs und ordnen sie den config_ids zu.
    all_runs: List[BacktestRun] = (
        session.query(BacktestRun)
        .filter(BacktestRun.testset_run_id == testset_run_id)
        .all()
    )

    # Herkunfts-Referenz auf die verwendete IndicatorConfig: alle BacktestRuns eines
    # TestSet-Runs teilen dieselbe indicator_config_id. ID statt Name speichern, damit
    # ein späteres Umbenennen der Config den Join nicht bricht.
    source_indicator_config_id: Optional[int] = next(
        (run.indicator_config_id for run in all_runs if run.indicator_config_id is not None),
        None,
    )

    # Mapping: backtest_config_id -> BacktestRun
    # Die BacktestConfig-ID liegt im JSON-Feld backtest_config_json['backtest_config_id']
    # GEÄNDERT: _json-Suffix
    runs_by_config_id: Dict[int, BacktestRun] = {}
    for run in all_runs:
        bc_json = run.backtest_config_json or {}
        bc_id = bc_json.get('backtest_config_id')
        if bc_id is not None:
            runs_by_config_id[int(bc_id)] = run

    # --- Pro Position (Reihenfolge der config_ids) Sweep-Sieger ermitteln ---
    winning_result_ids: List[Any] = []
    winners: List[BacktestResult] = []
    empty_run_count = 0

    for config_id in config_ids:
        run = runs_by_config_id.get(config_id)
        if run is None:
            # Kein Run für diese Config -> null an dieser Position
            winning_result_ids.append(None)
            empty_run_count += 1
            continue

        winner: Optional[BacktestResult] = (
            session.query(BacktestResult)
            .filter(BacktestResult.run_id == run.id)
            .order_by(BacktestResult.total_return_pct.desc())
            .first()
        )
        if winner is None:
            winning_result_ids.append(None)
            empty_run_count += 1
        else:
            winning_result_ids.append(winner.id)
            winners.append(winner)

    configs_total = len(config_ids)

    # --- Aggregate aus nicht-leeren Siegern ---
    total_return_avg: Optional[float] = None
    total_return_sum: Optional[float] = None
    max_drawdown_avg: Optional[float] = None
    sharpe_avg: Optional[float] = None

    if winners:
        returns = [w.total_return_pct for w in winners if w.total_return_pct is not None]
        drawdowns = [w.max_drawdown_pct for w in winners if w.max_drawdown_pct is not None]
        sharpes = [w.sharpe_ratio for w in winners if w.sharpe_ratio is not None]

        if returns:
            total_return_avg = sum(returns) / len(returns)
            total_return_sum = sum(returns)
        if drawdowns:
            max_drawdown_avg = sum(drawdowns) / len(drawdowns)
        if sharpes:
            sharpe_avg = sum(sharpes) / len(sharpes)

    # --- Hint bei leeren Runs ---
    hint: Optional[str] = None
    if empty_run_count > 0:
        hint = f'{empty_run_count} von {configs_total} Runs hatten keine Results'

    # --- spec_runner_version aus einem der Runs oder aus TestSetRun ermitteln ---
    spec_runner_version: Optional[str] = None
    for run in all_runs:
        if run.spec_runner_version:
            spec_runner_version = run.spec_runner_version
            break

    # --- Snapshots bauen ---

    # testset_snapshot_json: TestSet-Zeile + referenzierte BacktestConfig-Inhalte
    # GEÄNDERT: _json-Suffix im Snapshot-Key
    # GEÄNDERT: Fehlt eine BacktestConfig in der Datenbank, wird ihr Eintrag aus dem
    # vorherigen Snapshot übernommen (nur im Fallback-Fall belegt) — sonst verlöre der
    # Rerun mit jedem Durchlauf mehr Config-Inhalte.
    def _config_snapshot(config_id: int) -> Optional[Dict[str, Any]]:
        """Baut den Snapshot-Eintrag einer BacktestConfig aus DB oder Vorgänger-Snapshot."""
        c = configs_by_id.get(config_id)
        if c is None:
            return snapshot_configs.get(config_id)
        return {
            'id': c.id,
            'name': c.name,
            'symbol': c.symbol,
            'exchange': c.exchange,
            'timeframe': c.timeframe,
            'start': c.start,
            'end': c.end,
            'ohlc_start': c.ohlc_start,
            'ohlc_end': c.ohlc_end,
            'size': c.size,
            'size_type': c.size_type,
            'init_cash': c.init_cash,
            'fees': c.fees,
            # GEÄNDERT: die drei Portfolio-Parameter mit einfrieren.
            # Dieser Snapshot ist die Quelle des Leaderboard-Reruns: fehlt ein Feld
            # hier, liefert der Rerun dauerhaft None, egal was der Recompute-Code tut.
            'slippage': c.slippage,
            'stop_exit_price': c.stop_exit_price,
            'stop_order_type': c.stop_order_type,
            # GEÄNDERT: Schritt 3d — Stop-Formate gehören nicht mehr in den
            # Config-Snapshot; sie reisen in indicator_config_snapshot_json
            # ['config_json']['_stops'] mit.
        }

    testset_snapshot: Dict[str, Any] = {
        'id': testset_run.testset_id,
        'name': testset_name,
        'description': testset_description,
        'backtest_config_ids_json': config_ids,
        'configs': [
            snap for cid in config_ids
            if (snap := _config_snapshot(cid)) is not None
        ],
    }

    # indicator_config_snapshot_json: Snapshot der Indikator-Config
    # GEÄNDERT: direkt aus testset_run.indicators_config_json (kein FK mehr)
    indicator_config_snapshot: Optional[Dict[str, Any]] = None
    if indicators_config_json_snapshot:
        indicator_config_snapshot = {
            'config_json': indicators_config_json_snapshot,
        }

    # GEÄNDERT: spec_json aus StrategyIteration via einzigen Lookup einbetten
    # Alle BacktestRuns eines TestSetRuns teilen dieselbe iteration_id (gesetzt in api_testset_runs.py).
    # Kein FK gesetzt — lose/löschfest, konsistent mit indicator_config_id.
    iteration_spec_json: Optional[Dict[str, Any]] = None
    source_iteration_id: Optional[int] = next(
        (run.iteration_id for run in all_runs if run.iteration_id is not None),
        None,
    )
    if source_iteration_id is not None:
        iteration_row = (
            session.query(StrategyIteration.spec_json)
            .filter(StrategyIteration.id == source_iteration_id)
            .one_or_none()
        )
        if iteration_row is not None and iteration_row.spec_json is not None:
            iteration_spec_json = dict(iteration_row.spec_json)

    # strategy_snapshot_json: Grunddaten + eingebettetes spec_json für Reproduzierbarkeit
    # GEÄNDERT: _json-Suffix im Snapshot-Key
    strategy_snapshot: Dict[str, Any] = {
        'strategy_family': testset_run.strategy_family,
        'strategy_name': testset_run.strategy_name,
        'spec_runner_version': spec_runner_version,
    }
    if iteration_spec_json is not None:
        strategy_snapshot['spec_json'] = iteration_spec_json
    # GEÄNDERT: iteration_id mit einfrieren, damit der Rerun-Befund sie
    # direkt aus dem Schnappschuss lesen kann statt über die IndicatorConfig zu gehen.
    # Bewusst als Schnappschuss-Key, keine neue Spalte (siehe Ticket-Anforderung 1).
    if source_iteration_id is not None:
        strategy_snapshot['iteration_id'] = source_iteration_id

    # --- Idempotenz-Check vor Insert (verhindert IntegrityError in Test-Session) ---
    existing = (
        session.query(LeaderboardEntry)
        .filter(LeaderboardEntry.testset_run_id == testset_run_id)
        .first()
    )
    if existing is not None:
        logger.info(
            'build_leaderboard_entry: TestSetRun #%d bereits vorhanden (Idempotenz). No-Op.',
            testset_run_id,
        )
        return None

    # --- LeaderboardEntry persistieren ---
    entry = LeaderboardEntry(
        testset_id=testset_run.testset_id,
        testset_run_id=testset_run_id,
        strategy_family=testset_run.strategy_family,
        strategy_name=testset_run.strategy_name,
        # indicator_config_id als lose Referenz ohne FK (kein Lösch-Block für die Config);
        # befüllt aus den BacktestRuns des TestSet-Runs, NULL wenn keiner eine Config-ID trägt
        indicator_config_id=source_indicator_config_id,
        spec_runner_version=spec_runner_version,
        configs_total=configs_total,
        total_return_avg=total_return_avg,
        total_return_sum=total_return_sum,
        max_drawdown_avg=max_drawdown_avg,
        sharpe_avg=sharpe_avg,
        configs_passed=None,
        filter_breached=None,
        # GEÄNDERT: _json-Suffix
        testset_snapshot_json=testset_snapshot,
        indicator_config_snapshot_json=indicator_config_snapshot,
        strategy_snapshot_json=strategy_snapshot,
        winning_result_ids_json=winning_result_ids,
        hint=hint,
    )
    session.add(entry)

    try:
        session.commit()
        session.refresh(entry)
        logger.info(
            'LeaderboardEntry #%d für TestSetRun #%d angelegt (configs_total=%d, leere Runs=%d).',
            entry.id, testset_run_id, configs_total, empty_run_count,
        )
        return entry
    except IntegrityError:
        # Race-Condition-Fallback: Gleichzeitiger zweiter Trigger -> No-Op
        session.rollback()
        logger.info(
            'build_leaderboard_entry: TestSetRun #%d UNIQUE-Verletzung (Race-Condition). No-Op.',
            testset_run_id,
        )
        return None

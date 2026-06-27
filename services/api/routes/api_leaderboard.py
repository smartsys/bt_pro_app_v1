"""
API-Endpoints für das Leaderboard

GET /api/leaderboard?testset_id=<int>    — LeaderboardEntries; ohne testset_id alle Einträge
GET /api/leaderboard/<entry_id>/drilldown — Drill-Down: Pro-Config-Results + Report
POST /api/leaderboard/<entry_id>/rerun   — Lauf aus Snapshot allein reproduzieren (Ticket 40)
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Integer, func

logger = logging.getLogger(__name__)

from user_data.utils.database.db import get_session
from user_data.utils.database.models import BacktestResult, BacktestRun, IndicatorConfig, LeaderboardEntry, StrategyConcept, StrategyIteration
from user_data.utils.database.repository_testsets import (
    get_leaderboard_entry,
    list_leaderboard_entries_with_triggered_by,
)

router = APIRouter(prefix='/api/leaderboard', tags=['leaderboard'])


def _compute_span_days(intervals: List[Tuple[datetime, datetime]]) -> Tuple[Optional[float], bool]:
    """Berechnet die Tage der Intervall-Union und erkennt Überschneidungen.

    Returns (union_days, has_overlap). union_days ist None, wenn keine
    gültigen Intervalle vorliegen.
    """
    valid = [(s, e) for s, e in intervals if s is not None and e is not None and e > s]
    if not valid:
        return None, False
    # Identische Zeiträume (gleiches Symbol, gleicher Window) sind kein Overlap,
    # sondern der Normalfall bei TestSets. Erst deduplizieren, dann prüfen.
    unique = sorted(set(valid), key=lambda iv: iv[0])
    naive_seconds = sum((e - s).total_seconds() for s, e in unique)
    merged: List[List[datetime]] = [[unique[0][0], unique[0][1]]]
    for s, e in unique[1:]:
        if s < merged[-1][1]:
            if e > merged[-1][1]:
                merged[-1][1] = e
        else:
            merged.append([s, e])
    union_seconds = sum((e - s).total_seconds() for s, e in merged)
    union_days = union_seconds / 86400.0
    has_overlap = naive_seconds > union_seconds + 1.0  # 1s Toleranz
    return union_days, has_overlap


# --- Pydantic Schemas ---

class LeaderboardEntryOut(BaseModel):
    """Ausgabe-Schema für einen LeaderboardEntry inkl. triggered_by."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    testset_run_id: Optional[int]
    testset_name: Optional[str] = None
    strategy_family: str
    strategy_name: str
    indicator_config_id: Optional[int]
    indicator_config_name: Optional[str] = None
    indicators: Optional[Dict[str, Dict[str, Any]]] = None
    spec_runner_version: Optional[str]
    configs_total: int
    configs_passed: Optional[int]
    total_return_avg: Optional[float]
    total_return_sum: Optional[float]
    max_drawdown_avg: Optional[float]
    sharpe_avg: Optional[float]
    profit_factor_avg: Optional[float] = None
    configs_win: Optional[int] = None
    configs_loss: Optional[int] = None
    iteration_description: Optional[str] = None
    span_days: Optional[float] = None
    has_overlap: bool = False
    return_per_day_pct: Optional[float] = None
    filter_breached: Optional[bool]
    hint: Optional[str]
    executive_summary: Optional[str]
    mini_report: Optional[str]
    created_at: datetime
    triggered_by: Optional[str] = None


class DrilldownResultItem(BaseModel):
    """Ein Result-Eintrag im Drill-Down (eine Config-Position)."""
    position: int
    missing: bool = False
    result_id: Optional[int] = None
    symbol: Optional[str] = None
    start_index: Optional[str] = None
    end_index: Optional[str] = None
    total_return_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    n_trades: Optional[int] = None
    win_rate_pct: Optional[float] = None
    profit_factor: Optional[float] = None


class DrilldownOut(BaseModel):
    """Ausgabe-Schema für den Drill-Down-Endpunkt."""
    entry_id: int
    executive_summary: Optional[str]
    mini_report: Optional[str]
    results: List[DrilldownResultItem]


# --- Endpoints ---

@router.get('')
def list_leaderboard(testset_id: Optional[int] = None):
    """LeaderboardEntries, default-sortiert nach total_return_avg DESC.

    Ohne testset_id werden alle Einträge geliefert, sonst nur die des Test-Sets.
    """
    session = get_session()
    try:
        rows = list_leaderboard_entries_with_triggered_by(session, testset_id)

        # GEÄNDERT: Iteration-Description batched laden via (concept.slug, iteration.version)
        family_version_pairs = {
            (row['entry'].strategy_family, row['entry'].strategy_name) for row in rows
        }
        iteration_descriptions: Dict[tuple, Optional[str]] = {}
        if family_version_pairs:
            iter_rows = (
                session.query(StrategyConcept.slug, StrategyIteration.version, StrategyIteration.description)
                .join(StrategyIteration, StrategyIteration.concept_id == StrategyConcept.id)
                .all()
            )
            for slug, version, desc in iter_rows:
                if (slug, version) in family_version_pairs:
                    iteration_descriptions[(slug, version)] = desc

        # IndicatorConfig-Namen batched laden (Snapshot speichert nur config_json, keinen Namen)
        config_ids = {row['entry'].indicator_config_id for row in rows if row['entry'].indicator_config_id is not None}
        indicator_config_names: Dict[int, str] = {}
        if config_ids:
            for cfg_id, cfg_name in (
                session.query(IndicatorConfig.id, IndicatorConfig.name)
                .filter(IndicatorConfig.id.in_(config_ids))
                .all()
            ):
                indicator_config_names[cfg_id] = cfg_name

        items = []
        for row in rows:
            entry: LeaderboardEntry = row['entry']
            triggered_by: Optional[str] = row['triggered_by']

            # Aggregation aus BacktestResult für Win/Loss-Counts und Profit-Faktor-Durchschnitt
            result_ids: List[Any] = [rid for rid in (entry.winning_result_ids_json or []) if rid is not None]
            configs_win: Optional[int] = None
            configs_loss: Optional[int] = None
            profit_factor_avg: Optional[float] = None
            span_days: Optional[float] = None
            has_overlap: bool = False
            return_per_day_pct: Optional[float] = None
            if result_ids:
                agg = (
                    session.query(
                        func.sum((BacktestResult.total_return_pct > 0).cast(Integer)).label('wins'),
                        func.sum((BacktestResult.total_return_pct <= 0).cast(Integer)).label('losses'),
                        func.avg(BacktestResult.profit_factor).label('pf_avg'),
                    )
                    .filter(BacktestResult.id.in_(result_ids))
                    .one()
                )
                configs_win = int(agg.wins) if agg.wins is not None else 0
                configs_loss = int(agg.losses) if agg.losses is not None else 0
                profit_factor_avg = float(agg.pf_avg) if agg.pf_avg is not None else None

                # GEÄNDERT: Tage-Union über Winning-Results + Return/Tag
                # Fallback: wenn start_index/end_index am Result NULL sind (nur Chart-Stufe
                # füllt diese), nutze die start_date/end_date des zugehörigen BacktestRun.
                intervals = (
                    session.query(
                        BacktestResult.start_index,
                        BacktestResult.end_index,
                        BacktestRun.start_date,
                        BacktestRun.end_date,
                    )
                    .join(BacktestRun, BacktestRun.id == BacktestResult.run_id)
                    .filter(BacktestResult.id.in_(result_ids))
                    .all()
                )
                merged_intervals = [
                    (s if s is not None else rs, e if e is not None else re)
                    for s, e, rs, re in intervals
                ]
                span_days, has_overlap = _compute_span_days(merged_intervals)
                if span_days and span_days > 0 and entry.total_return_sum is not None:
                    return_per_day_pct = float(entry.total_return_sum) / span_days

            # Indikatoren generisch aus indicator_config_snapshot_json.config_json extrahieren
            indicators: Optional[Dict[str, Dict[str, Any]]] = None
            snap = entry.indicator_config_snapshot_json or {}
            if isinstance(snap, dict):
                cfg = snap.get('config_json')
                if isinstance(cfg, dict) and cfg:
                    indicators = {k: v for k, v in cfg.items() if isinstance(v, dict)}

            # TestSet-Name aus Snapshot (Source of Truth nach Cleanup)
            testset_snap = entry.testset_snapshot_json or {}
            testset_name: Optional[str] = testset_snap.get('name') if isinstance(testset_snap, dict) else None

            out = LeaderboardEntryOut(
                id=entry.id,
                testset_run_id=entry.testset_run_id,
                testset_name=testset_name,
                strategy_family=entry.strategy_family,
                strategy_name=entry.strategy_name,
                indicator_config_id=entry.indicator_config_id,
                indicator_config_name=indicator_config_names.get(entry.indicator_config_id),
                indicators=indicators,
                spec_runner_version=entry.spec_runner_version,
                configs_total=entry.configs_total,
                configs_passed=entry.configs_passed,
                total_return_avg=float(entry.total_return_avg) if entry.total_return_avg is not None else None,
                total_return_sum=float(entry.total_return_sum) if entry.total_return_sum is not None else None,
                max_drawdown_avg=float(entry.max_drawdown_avg) if entry.max_drawdown_avg is not None else None,
                sharpe_avg=float(entry.sharpe_avg) if entry.sharpe_avg is not None else None,
                profit_factor_avg=profit_factor_avg,
                configs_win=configs_win,
                configs_loss=configs_loss,
                iteration_description=iteration_descriptions.get((entry.strategy_family, entry.strategy_name)),
                span_days=span_days,
                has_overlap=has_overlap,
                return_per_day_pct=return_per_day_pct,
                filter_breached=entry.filter_breached,
                hint=entry.hint,
                executive_summary=entry.executive_summary,
                mini_report=entry.mini_report,
                created_at=entry.created_at,
                triggered_by=triggered_by,
            )
            items.append(out.model_dump(mode='json'))
        return {'data': {'items': items, 'total': len(items)}, 'error': None}
    finally:
        session.close()


@router.delete('/{entry_id}')
def delete_leaderboard_entry(entry_id: int):
    """Löscht einen LeaderboardEntry."""
    session = get_session()
    try:
        entry = get_leaderboard_entry(session, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f'LeaderboardEntry {entry_id} nicht gefunden.')
        session.delete(entry)
        session.commit()
        return {'data': {'deleted_id': entry_id}, 'error': None}
    finally:
        session.close()


@router.get('/{entry_id}/drilldown')
def drilldown_leaderboard(entry_id: int):
    """Drill-Down für einen LeaderboardEntry: Pro-Config-Results + executive_summary + mini_report."""
    session = get_session()
    try:
        entry = get_leaderboard_entry(session, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f'LeaderboardEntry {entry_id} nicht gefunden.')

        # GEÄNDERT: Ticket 15 — _json-Suffix
        winning_ids: List[Any] = entry.winning_result_ids_json or []
        results: List[DrilldownResultItem] = []

        for i, result_id in enumerate(winning_ids):
            if result_id is None:
                results.append(DrilldownResultItem(position=i, missing=True))
                continue

            br: Optional[BacktestResult] = (
                session.query(BacktestResult)
                .filter(BacktestResult.id == result_id)
                .first()
            )
            if br is None:
                results.append(DrilldownResultItem(position=i, missing=True, result_id=result_id))
                continue

            # Symbol aus actual_params_json lesen (gespeichertes JSON)
            # GEÄNDERT: Ticket 15 — _json-Suffix
            symbol: Optional[str] = None
            if br.actual_params_json and isinstance(br.actual_params_json, dict):
                symbol = br.actual_params_json.get('symbol')

            start_str: Optional[str] = br.start_index.isoformat() if br.start_index else None
            end_str: Optional[str] = br.end_index.isoformat() if br.end_index else None

            results.append(DrilldownResultItem(
                position=i,
                missing=False,
                result_id=br.id,
                symbol=symbol,
                start_index=start_str,
                end_index=end_str,
                total_return_pct=br.total_return_pct,
                max_drawdown_pct=br.max_drawdown_pct,
                sharpe_ratio=br.sharpe_ratio,
                n_trades=br.total_trades,
                win_rate_pct=br.win_rate_pct,
                profit_factor=br.profit_factor,
            ))

        out = DrilldownOut(
            entry_id=entry.id,
            executive_summary=entry.executive_summary,
            mini_report=entry.mini_report,
            results=results,
        )
        return {'data': out.model_dump(mode='json'), 'error': None}
    finally:
        session.close()


# GEÄNDERT: Ticket 40 — Snapshot-basierter Rerun-Endpunkt

class RerunOut(BaseModel):
    """Ausgabe-Schema für einen Snapshot-Rerun."""
    source_entry_id: int
    new_entry_id: int
    configs_total: int
    total_return_avg: Optional[float]
    original_total_return_avg: Optional[float]
    bit_exact_match: Optional[bool]


@router.post('/{entry_id}/rerun')
def rerun_from_snapshot(entry_id: int):
    """Reproduziert einen Leaderboard-Lauf ausschließlich aus dem gespeicherten Snapshot.

    Liest Backtest-Configs aus testset_snapshot_json['configs'], die Strategie-Anleitung
    aus strategy_snapshot_json['spec_json'] und das Indikator-Raster aus
    indicator_config_snapshot_json. Kein Zugriff auf backtest_configs, strategy_iterations
    oder backtest_results der Originaldaten nötig.

    Bestandsschutz: Fehlt spec_json im strategy_snapshot, wird der Versuch klar abgelehnt.
    """
    from decimal import Decimal

    from user_data.strategies.generic.spec_runner import (
        SPEC_RUNNER_IMPORT_PATH,
        VERSION as _spec_runner_version,
        run_spec_strategy,
    )
    from user_data.utils.database.models import TestSetRun
    from user_data.utils.database.repository import (
        create_backtest_run,
        save_strategy_results,
        update_backtest_run_status,
    )
    from user_data.utils.database.repository_testsets import (
        build_leaderboard_entry_for_testset_run,
        create_testset_run,
    )
    from user_data.utils.ohlc.loader import load_ohlc_data

    session = get_session()
    try:
        entry = get_leaderboard_entry(session, entry_id)
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=f'LeaderboardEntry {entry_id} nicht gefunden.',
            )

        # --- Snapshot-Daten extrahieren ---
        strategy_snap: Dict[str, Any] = entry.strategy_snapshot_json or {}
        testset_snap: Dict[str, Any] = entry.testset_snapshot_json or {}
        indicator_snap: Dict[str, Any] = entry.indicator_config_snapshot_json or {}

        # Bestandsschutz: spec_json muss im Snapshot vorhanden sein
        spec_json: Optional[Dict[str, Any]] = strategy_snap.get('spec_json')
        if spec_json is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f'LeaderboardEntry {entry_id} enthält kein eingebettetes spec_json im '
                    'strategy_snapshot. Dieser Eintrag wurde vor Ticket 40 angelegt und '
                    'kann nicht aus dem Snapshot allein reproduziert werden.'
                ),
            )

        rules_json: Optional[Dict[str, Any]] = spec_json.get('rules')
        if rules_json is None:
            raise HTTPException(
                status_code=422,
                detail=f'spec_json in LeaderboardEntry {entry_id} enthält keinen rules-Key.',
            )

        indicators_json: Dict[str, Any] = indicator_snap.get('config_json') or {}
        if not indicators_json:
            raise HTTPException(
                status_code=422,
                detail=f'indicator_config_snapshot in LeaderboardEntry {entry_id} ist leer.',
            )

        configs: List[Dict[str, Any]] = testset_snap.get('configs') or []
        if not configs:
            raise HTTPException(
                status_code=422,
                detail=f'testset_snapshot in LeaderboardEntry {entry_id} enthält keine configs.',
            )

        strategy_family: str = strategy_snap.get('strategy_family', 'snapshot-rerun')
        strategy_name: str = strategy_snap.get('strategy_name', 'rerun')
        original_return_avg: Optional[float] = (
            float(entry.total_return_avg) if entry.total_return_avg is not None else None
        )
        testset_id: int = testset_snap.get('id', entry.testset_id)

    finally:
        session.close()

    # --- Neuen TestSetRun anlegen ---
    session = get_session()
    try:
        testset_run = create_testset_run(
            session=session,
            testset_id=testset_id,
            strategy_family=strategy_family,
            strategy_name=strategy_name,
            n_runs_total=len(configs),
            indicators_config_json=indicators_json,
            triggered_by=f'snapshot-rerun:{entry_id}',
            status='queued',
        )
        testset_run_id: int = testset_run.id
    finally:
        session.close()

    # --- Pro Config synchron ausführen ---
    run_ids: List[int] = []
    for cfg in configs:
        backtest_config_json: Dict[str, Any] = {
            'strategy_family': strategy_family,
            'strategy_name': strategy_name,
            'import_path': SPEC_RUNNER_IMPORT_PATH,
            'backtest_config_id': cfg.get('id'),
            'symbols': [cfg['symbol']],
            'start': cfg['start'],
            'end': cfg['end'],
            'ohlc_start': cfg.get('ohlc_start', cfg['start']),
            'ohlc_end': cfg.get('ohlc_end', cfg['end']),
            'exchange': cfg['exchange'],
            'timeframe': cfg['timeframe'],
            'portfolio': {
                'size': cfg.get('size'),
                'size_type': cfg.get('size_type'),
                'init_cash': cfg.get('init_cash'),
                'fees': cfg.get('fees'),
                # GEÄNDERT: Schritt 3d — Stop-Formate kommen über '_stops'
                # (indicators_json), nicht mehr aus dem Config-portfolio-Block.
            },
        }

        # GEÄNDERT: Schritt 3c — Stops stammen aus dem Indikator-Snapshot
        # (indicators_json['_stops']), nicht mehr aus dem portfolio-Block der Config.
        # Alt-Entries ohne '_stops' wurden in Migration 0003 entfernt (nicht reproduzierbar).
        run_indicators_json = dict(indicators_json)

        run_id = create_backtest_run(
            backtest_config=backtest_config_json,
            indicators_config=run_indicators_json,
            spec_runner_version=_spec_runner_version,
            testset_run_id=testset_run_id,
            iteration_id=None,
        )
        run_ids.append(run_id)

        try:
            update_backtest_run_status(run_id, status='running')
            ohlc_data = load_ohlc_data(backtest_config_json)
            strategy_results = run_spec_strategy(
                ohlc_data,
                indicators_json=run_indicators_json,
                backtest_config_json=backtest_config_json,
                rules_json=rules_json,
            )
            save_strategy_results(
                run_id=run_id,
                strategy_results=strategy_results,
                spec_runner_version=_spec_runner_version,
                rules=rules_json,
                backtest_config=backtest_config_json,
            )
            update_backtest_run_status(run_id, status='completed')
        except Exception as exc:
            update_backtest_run_status(run_id, status='failed', error_message=str(exc))
            logger.error(
                '[RERUN] Run #%d (Entry #%d, Config %s) fehlgeschlagen: %s',
                run_id, entry_id, cfg.get('symbol'), exc, exc_info=True,
            )

    # --- TestSetRun auf completed setzen und LeaderboardEntry erzeugen ---
    from user_data.utils.database.db import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE testset_runs "
                "SET status = 'completed', n_runs_completed = :n, completed_at = NOW() "
                "WHERE id = :tid"
            ),
            {'n': len(configs), 'tid': testset_run_id},
        )

    new_entry = build_leaderboard_entry_for_testset_run(testset_run_id)
    if new_entry is None:
        raise HTTPException(
            status_code=500,
            detail=f'LeaderboardEntry nach Rerun (TestSetRun #{testset_run_id}) konnte nicht angelegt werden.',
        )

    # GEÄNDERT: Ticket 40 — spec_json aus dem Quell-Entry in den neuen Entry einbetten.
    # Da der Rerun ohne iteration_id läuft (transient, kein FK), wird spec_json nicht
    # automatisch eingebettet. Wir übertragen es direkt aus dem Quell-Snapshot.
    if spec_json is not None:
        session = get_session()
        try:
            fresh_entry = session.query(LeaderboardEntry).filter(
                LeaderboardEntry.id == new_entry.id
            ).first()
            if fresh_entry is not None:
                snap = dict(fresh_entry.strategy_snapshot_json or {})
                snap['spec_json'] = spec_json
                fresh_entry.strategy_snapshot_json = snap
                session.commit()
        finally:
            session.close()

    new_return_avg: Optional[float] = (
        float(new_entry.total_return_avg) if new_entry.total_return_avg is not None else None
    )

    # Bit-genaue Verifikation: Werte als Decimal vergleichen (4 Nachkommastellen)
    bit_exact: Optional[bool] = None
    if original_return_avg is not None and new_return_avg is not None:
        bit_exact = abs(original_return_avg - new_return_avg) < 1e-6

    logger.info(
        '[RERUN] Entry #%d -> neuer Entry #%d: original=%.4f, neu=%.4f, bit_exact=%s',
        entry_id, new_entry.id,
        original_return_avg or 0.0, new_return_avg or 0.0, bit_exact,
    )

    out = RerunOut(
        source_entry_id=entry_id,
        new_entry_id=new_entry.id,
        configs_total=len(configs),
        total_return_avg=new_return_avg,
        original_total_return_avg=original_return_avg,
        bit_exact_match=bit_exact,
    )
    return {'data': out.model_dump(mode='json'), 'error': None}

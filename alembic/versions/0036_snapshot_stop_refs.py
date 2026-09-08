"""Referenz-Stops in bestehende Result-Snapshots zurückschreiben

`_build_full_config_snapshot` (repository.py) hat jedes Dict im `_stops`-Block als
Sweep-Range gelesen und im Snapshot auf NULL gesetzt. Ein Referenz-Stop
(`{"ref": "indicator:atr_stop:real", "mult": 5.0}`, siehe `stop_refs.py`) ist aber
keine Sweep-Achse: er bleibt zur Laufzeit ein Dict und erscheint nie in
`actual_params`. Results solcher Läufe trugen deshalb einen Snapshot ganz ohne
Stopabstand — sichtbar wurde das im Chart-Playground, wo der Schnellbacktest bei
`size_type='risk_percent'` den fehlenden `sl_stop` meldete.

Der Fehler in der Snapshot-Erzeugung ist behoben; diese Migration repariert die
bereits geschriebenen Snapshots. Quelle ist der Lauf selbst
(`backtest_runs.indicators_config_json['_stops']`) — dort stehen die Referenzen
unverändert. Übernommen wird ein Referenz-Stop nur dort, wo der Snapshot für
dasselbe Feld NULL trägt; per-Result aufgelöste Sweep-Werte bleiben unangetastet.

`backtest_runs` und `backtest_results` sind keine Baseline-Tabellen; der
Daten-Load `0021_seed_baseline_data_v3` muss deshalb nicht umziehen.

Revision ID: 0036_snapshot_stop_refs
Revises: 0035_bc_risk_leverage
Create Date: 2026-09-08
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0036_snapshot_stop_refs'
down_revision: Union[str, Sequence[str], None] = '0035_bc_risk_leverage'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Die fünf Stop-Felder, die ein Referenz-Dict tragen können (STOP_PARAM_KEYS).
STOP_KEYS = ('td_stop', 'tp_stop', 'sl_stop', 'tsl_stop', 'tsl_th')


def _as_dict(value):
    """JSON-Spalten kommen je nach Treiber als dict oder als Text zurück."""
    if isinstance(value, str):
        return json.loads(value)
    return value


def upgrade() -> None:
    """Trägt die Referenz-Stops des Laufs in die Snapshots seiner Results nach."""
    conn = op.get_bind()

    # Läufe mit mindestens einem Referenz-Stop (Dict mit 'ref') im '_stops'-Block.
    runs = conn.execute(sa.text(
        "SELECT id, indicators_config_json FROM backtest_runs "
        "WHERE indicators_config_json IS NOT NULL "
        "AND EXISTS (SELECT 1 FROM jsonb_each("
        "    COALESCE(indicators_config_json::jsonb -> '_stops', '{}'::jsonb)) e "
        "  WHERE jsonb_typeof(e.value) = 'object' AND e.value ? 'ref')"
    )).fetchall()

    for run_id, indicators_config in runs:
        stops = (_as_dict(indicators_config) or {}).get('_stops') or {}
        refs = {
            key: stops[key] for key in STOP_KEYS
            if isinstance(stops.get(key), dict) and 'ref' in stops[key]
        }
        if not refs:
            continue

        results = conn.execute(sa.text(
            "SELECT id, full_config_snapshot_json FROM backtest_results "
            "WHERE run_id = :run_id AND full_config_snapshot_json IS NOT NULL"
        ), {'run_id': run_id}).fetchall()

        for result_id, snapshot_raw in results:
            snapshot = _as_dict(snapshot_raw) or {}
            backtest_config = snapshot.get('backtest_config')
            if not isinstance(backtest_config, dict):
                continue
            # Nur leere Felder füllen — ein per Result aufgelöster Sweep-Wert bleibt stehen.
            changed = False
            for key, ref in refs.items():
                if backtest_config.get(key) is None:
                    backtest_config[key] = ref
                    changed = True
            if not changed:
                continue
            conn.execute(sa.text(
                "UPDATE backtest_results SET full_config_snapshot_json = CAST(:snapshot AS json) "
                "WHERE id = :result_id"
            ), {'snapshot': json.dumps(snapshot), 'result_id': result_id})


def downgrade() -> None:
    """Kein Rückbau.

    Die nachgetragenen Referenzen wieder auf NULL zu setzen hieße, den Defekt
    absichtlich zurückzuholen — ein Result stünde erneut ohne seine Stops da.
    """
    pass

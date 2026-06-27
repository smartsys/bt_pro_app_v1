"""move stop formats (delta_format/time_delta_format) into _stops meta key

Schritt 3d des Stop-Umbaus: Verlagert die zwei Stop-FORMAT-Parameter
delta_format (Prozent/Absolut für tp/sl/tsl) und time_delta_format (rows/Index
für td) genauso wie zuvor die 5 Stop-Werte in den Meta-Key
indicators_config_json['_stops'] und entfernt die zugehörigen Spalten aus
backtest_configs.

Die Formate interpretieren die Stops, gehören also zu '_stops' (Eigentümer =
IndicatorConfig). '_stops' existiert seit Migration 0002 in jedem Run-Snapshot;
hier kommen die zwei Format-Keys flach neben die Stop-Werte (NICHT in
STOP_PARAM_KEYS — sie sind nicht sweepbar).

upgrade():
  1. Backfill — für jeden backtest_runs-Eintrag die zwei Format-Keys in
     indicators_config_json['_stops'] schreiben, gelesen aus
     backtest_config_json['portfolio']. Idempotent: ein Format-Key wird nur
     gesetzt, wo er in '_stops' noch fehlt.
  2. Drop — die zwei Spalten delta_format/time_delta_format aus backtest_configs.

Backfill liest JSON (nicht die Spalten), daher ist die Reihenfolge unkritisch;
Backfill-vor-Drop bleibt für Klarheit.

Revision ID: 0004_move_stop_formats_to_stops
Revises: 0003_drop_stop_columns
Create Date: 2026-06-18
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0004_move_stop_formats_to_stops'
down_revision: Union[str, Sequence[str], None] = '0003_drop_stop_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Die zwei Stop-Format-Keys (flach in '_stops', neben den Stop-Werten).
FORMAT_KEYS = ('delta_format', 'time_delta_format')


def _as_dict(value) -> dict:
    """Normalisiert einen jsonb-Spaltenwert zu einem dict (dict durchreichen, str parsen)."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, (str, bytes, bytearray)):
        return json.loads(value)
    raise TypeError(
        f"Unerwarteter JSON-Spaltentyp {type(value).__name__} — "
        f"erwartet dict oder str/bytes."
    )


def upgrade() -> None:
    """Backfillt die Formate in '_stops' und droppt die zwei Format-Spalten."""
    conn = op.get_bind()

    # --- 1. Backfill: Formate aus backtest_config_json['portfolio'] in '_stops' ---
    rows = conn.execute(
        sa.text(
            "SELECT id, backtest_config_json, indicators_config_json "
            "FROM backtest_runs"
        )
    ).fetchall()

    updated = 0
    for run_id, backtest_config_json, indicators_config_json in rows:
        backtest_config = _as_dict(backtest_config_json)
        indicators_config = _as_dict(indicators_config_json)

        # '_stops' existiert seit Migration 0002 immer; defensiv trotzdem absichern.
        stops = indicators_config.get('_stops')
        if not isinstance(stops, dict):
            stops = {}

        portfolio = backtest_config.get('portfolio') or {}

        # Idempotenz: einen Format-Key nur setzen, wo er in '_stops' noch fehlt.
        changed = False
        for key in FORMAT_KEYS:
            if key not in stops:
                stops[key] = portfolio.get(key)
                changed = True

        if not changed:
            continue

        indicators_config['_stops'] = stops
        conn.execute(
            sa.text(
                "UPDATE backtest_runs SET indicators_config_json = "
                "CAST(:payload AS jsonb) WHERE id = :run_id"
            ),
            {'payload': json.dumps(indicators_config), 'run_id': run_id},
        )
        updated += 1

    print(f"[move stop formats] {updated} von {len(rows)} Runs aktualisiert "
          f"(übersprungen: {len(rows) - updated} mit bereits vorhandenen Format-Keys in '_stops').")

    # --- 2. Drop: die zwei Format-Spalten ---
    for col in FORMAT_KEYS:
        op.drop_column('backtest_configs', col)
    print(f"[move stop formats] {len(FORMAT_KEYS)} Format-Spalten aus backtest_configs entfernt.")


def downgrade() -> None:
    """Stellt die zwei Format-Spalten als nullable wieder her (Schema reversibel).

    Die Daten sind NICHT wiederherstellbar — die alten Format-Werte wurden beim
    Drop verworfen; die Spalten kommen leer (NULL) zurück. Das Backfill in
    '_stops' wird bewusst NICHT rückgängig gemacht (No-op): welche Runs die
    Format-Keys bereits vor der Migration trugen und welche sie erst durch
    upgrade() bekamen, ist nachträglich nicht unterscheidbar.
    """
    op.add_column('backtest_configs', sa.Column('delta_format', sa.String(length=20), nullable=True))
    op.add_column('backtest_configs', sa.Column('time_delta_format', sa.String(length=20), nullable=True))

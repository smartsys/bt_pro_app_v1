"""backfill _stops meta key

Schritt 3a des Stop-Umbaus: Schreibt für jeden Run in backtest_runs den
reservierten Meta-Key '_stops' in die Spalte indicators_config_json — abgeleitet
aus dem eigenen, eingefrorenen backtest_config_json desselben Runs (Sub-Dict
'portfolio'). So tragen bestehende Run-Snapshots ihre Stops im neuen Format,
bevor später (Schritt 3b/3c) der alte Lesepfad und die DB-Spalten entfernt werden.

Reine Daten-Migration: KEINE Schema-Änderung, KEIN Spalten-Drop, KEIN Lesepfad-Eingriff.

Die abgeleitete '_stops'-Form ist bit-genau identisch zu dem, was der Spec-Runner-
Helfer `stops_from_portfolio` (user_data/strategies/generic/indicator_factory.py)
erzeugt: ein Skalar-Dict mit genau den Keys aus STOP_PARAM_KEYS in fester Reihenfolge,
fehlende Stops als None. Der Helfer wird hier NICHT importiert, weil sein Modul
vectorbtpro zieht (im Migrations-Tooling-Python nicht installiert). Die Logik ist
trivial und wird bewusst inline gespiegelt — Single Source der Form bleibt der Helfer.

Idempotent: '_stops' wird nur gesetzt, wo es noch nicht existiert.

Revision ID: 0002_backfill_stops_meta_key
Revises: 0001_baseline_squash
Create Date: 2026-06-18
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0002_backfill_stops_meta_key'
down_revision: Union[str, Sequence[str], None] = '0001_baseline_squash'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Spiegelung von STOP_PARAM_KEYS (Single Source: indicator_factory.STOP_PARAM_KEYS).
# Reihenfolge und Keys müssen exakt zu stops_from_portfolio passen.
STOP_PARAM_KEYS = ('tp_stop', 'sl_stop', 'tsl_th', 'tsl_stop', 'td_stop')


def _stops_from_portfolio(portfolio_cfg: dict) -> dict:
    """Spiegelt stops_from_portfolio: Skalar-Dict mit allen Stop-Keys, fehlende als None."""
    return {key: portfolio_cfg.get(key) for key in STOP_PARAM_KEYS}


def upgrade() -> None:
    """Setzt indicators_config_json['_stops'] je Run aus dessen backtest_config_json['portfolio']."""
    conn = op.get_bind()

    rows = conn.execute(
        sa.text(
            "SELECT id, backtest_config_json, indicators_config_json "
            "FROM backtest_runs"
        )
    ).fetchall()

    updated = 0
    for run_id, backtest_config_json, indicators_config_json in rows:
        # JSON sauber laden — die Spalten sind jsonb, der Treiber liefert sie
        # je nach Pfad als dict oder als str. Beide Fälle abdecken.
        backtest_config = _as_dict(backtest_config_json)
        indicators_config = _as_dict(indicators_config_json)

        # Idempotenz: bereits vorhandenen '_stops'-Key niemals überschreiben.
        if '_stops' in indicators_config:
            continue

        portfolio = backtest_config.get('portfolio') or {}
        indicators_config['_stops'] = _stops_from_portfolio(portfolio)

        conn.execute(
            sa.text(
                "UPDATE backtest_runs SET indicators_config_json = "
                "CAST(:payload AS jsonb) WHERE id = :run_id"
            ),
            {'payload': json.dumps(indicators_config), 'run_id': run_id},
        )
        updated += 1

    print(f"[backfill _stops] {updated} von {len(rows)} Runs aktualisiert "
          f"(übersprungen: {len(rows) - updated} mit bereits vorhandenem '_stops').")


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


def downgrade() -> None:
    # No-op: Das Daten-Backfill ist nicht sauber reversibel. Welche Runs bereits
    # vor der Migration ein '_stops' trugen (und daher übersprungen wurden) und
    # welche es erst durch upgrade() bekamen, ist nachträglich nicht unterscheidbar.
    # Ein pauschales Löschen von '_stops' würde vorbestehende Daten zerstören —
    # daher bewusst kein Reverse.
    pass

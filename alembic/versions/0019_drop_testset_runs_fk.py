"""testset_runs.testset_id — Fremdschlüssel entfernen (lose Kopplung)

`models.py` behauptet seit der Umstellung „kein FK mehr" für
testset_runs.testset_id (lose Referenz wie LeaderboardEntry.testset_id, Snapshot
ist Source of Truth). Die Datenbank widersprach dem bisher: `0001_baseline.sql`
hatte `fk_testset_runs_testset_id` tatsächlich angelegt — ein Überbleibsel, das
laut eigenem Schema-Entwurf nie vorsah ("nur als Lookup, keine FK").
Diese Drift war die Ursache des HTTP-500.

Der User hat entschieden (12.08.2026): Der Fremdschlüssel fällt weg. Architektur-
Prinzip: Testset-Läufe müssen einzeln lauffähig bleiben, auch wenn ihr TestSet
gelöscht wurde — testset_id bleibt ein reiner Lookup-Wert, keine harte Kopplung.
Die übrigen fünf Fremdschlüssel der App (Konzept -> Iteration -> Run -> Result)
sind davon nicht betroffen und bleiben unangetastet.

Revision ID: 0019_drop_testset_runs_fk
Revises: 0018_result_open_trades
Create Date: 2026-08-12
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0019_drop_testset_runs_fk'
down_revision: Union[str, Sequence[str], None] = '0018_result_open_trades'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Entfernt fk_testset_runs_testset_id — testset_id bleibt lose Referenz."""
    op.drop_constraint(
        'fk_testset_runs_testset_id', 'testset_runs', type_='foreignkey',
    )


def downgrade() -> None:
    """Stellt den Fremdschlüssel wieder her (Rollback-Pfad)."""
    op.create_foreign_key(
        'fk_testset_runs_testset_id', 'testset_runs', 'testsets',
        local_cols=['testset_id'], remote_cols=['id'],
    )

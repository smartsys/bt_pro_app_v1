"""seed grundausstattung am neuen ende der schema-kette (v3)

Übernimmt den Grundausstattungs-Load von ``0009_seed_baseline_data_at_end``
(dort jetzt No-op, siehe dortiger Docstring) ans neue Kettenende. Lädt die
neutrale Grundausstattung, die jede Neuinstallation von Anfang an mitbringen
soll: alle ``backtest_configs`` (inkl. der in Ticket 59 ergänzten Spalten
``slippage``/``stop_exit_price``/``stop_order_type``), alle ``testsets`` sowie
die Demo-Strategie (``strategy_concepts`` id 1 "teststrategie",
``strategy_iterations`` id 1, ``indicator_configs`` id 1+2). Keine privaten
Strategien, Runs oder Leaderboard-Einträge.

Grund (Ticket 59): ``0020_bc_portfolio_params`` fügt drei Spalten zu
``backtest_configs`` hinzu - einer Baseline-Tabelle. Der Load muss am ECHTEN
Ende der Schema-Kette laufen, damit das SQL alle Spalten trägt.

Herkunft des SQL-Dumps (``0021_baseline_data_v3.sql``): Der Arbeits-DB-Stand
von ``backtest_configs``/``testsets`` (896 bzw. 16 Zeilen, Inhalt geprüft)
entspricht exakt dem bisherigen ``0009_baseline_data.sql`` - keine privaten
oder experimentellen Zeilen wurden seit dem Einfrieren ergänzt. Statt eines
kompletten Neu-Dumps (der die dort zusätzlich eingefrorenen
``indicator_configs``/``strategy_concepts``/``strategy_iterations``-Zeilen der
Demo-Strategie verloren hätte, weil ein regulärer Dump nur
``backtest_configs``/``testsets`` zieht) wurde ``0009_baseline_data.sql``
unverändert übernommen und in jeder ``backtest_configs``-INSERT-Zeile um die
drei neuen Spalten mit den Default-Werten ``0`` (slippage), ``NULL``
(stop_exit_price), ``NULL`` (stop_order_type) ergänzt (896 Zeilen, geprüft
per Skript-Diff). Alle anderen Tabellen im Dump sind byte-identisch zum
Vorgänger.

Idempotenz: Es wird nur in eine leere DB eingefügt. Bestehende DBs (die die
Daten über 0006, 0009 oder anderweitig bereits haben) überspringen den Insert
sichtbar - so entsteht kein PK-Konflikt.

Revisionsname bewusst gekürzt: ``0021_seed_baseline_data_at_end_v3`` (34
Zeichen, analog zum Präzedenzfall-Namen) überschreitet die Spaltenbreite
``alembic_version.version_num`` (``VARCHAR(32)``, siehe ``0001_baseline.sql``)
- ein erster Upgrade-Versuch brach am finalen `UPDATE alembic_version` mit
``StringDataRightTruncation`` ab (DDL rollte transaktional vollständig
zurück, kein Datenverlust). Daher ``..._v3`` ohne ``_at_end`` (26 Zeichen).

Revision ID: 0021_seed_baseline_data_v3
Revises: 0020_bc_portfolio_params
Create Date: 2026-08-12
"""
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0021_seed_baseline_data_v3'
down_revision: Union[str, Sequence[str], None] = '0020_bc_portfolio_params'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SQL_DIR = Path(__file__).parent / '_sql'


def upgrade() -> None:
    """Lädt die Grundausstattung - nur in eine leere DB."""
    conn = op.get_bind()
    bc_count = conn.execute(sa.text('SELECT count(*) FROM backtest_configs')).scalar() or 0
    ts_count = conn.execute(sa.text('SELECT count(*) FROM testsets')).scalar() or 0
    if bc_count or ts_count:
        # Sichtbar überspringen statt still scheitern (kein PK-Konflikt auf
        # bestehenden DBs, die die Daten schon haben).
        print(
            f'0021_seed_baseline_data_v3: Grundausstattung übersprungen - Tabellen '
            f'nicht leer (backtest_configs={bc_count}, testsets={ts_count}).'
        )
        return
    data_sql = (_SQL_DIR / '0021_baseline_data_v3.sql').read_text(encoding='utf-8')
    op.execute(data_sql)


def downgrade() -> None:
    # Bewusst no-op: Aus dem Seed eingefügte Zeilen sind nachträglich nicht von
    # echten Nutzerdaten unterscheidbar - ein DELETE würde fremde Daten treffen.
    pass

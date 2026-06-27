"""Tests für services/api/utils/strategy_io.py — Export/Import von Strategie-Objekten.

Round-Trip je Objekttyp (Konzept, Iteration, IndicatorConfig): exportieren in
einen Temp-Ordner, Datei wieder einlesen, importieren und Felder vergleichen.
IDs werden beim Import neu vergeben — geprüft wird inhaltliche Gleichheit.

Verwendet die zentrale PostgreSQL-``session``-Fixture aus tests/conftest.py
(Test-DB Port 5562). Der Backup-Ordner wird per STRATEGY_BACKUP_DIR auf tmp_path
umgeleitet, damit kein echter Repo-Ordner beschrieben wird.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from services.api.utils import strategy_io
from user_data.utils.database.models import IndicatorConfig
from user_data.utils.database.repository_strategies import (
    create_concept,
    create_iteration,
    next_iteration_version,
)


@pytest.fixture(autouse=True)
def _redirect_backup_dir(tmp_path, monkeypatch):
    """Lenkt den Export-Ordner für jeden Test auf ein isoliertes Temp-Verzeichnis."""
    monkeypatch.setenv('STRATEGY_BACKUP_DIR', str(tmp_path))
    return tmp_path


def _make_concept(session, slug='io-test', name='IO Test'):
    return create_concept(session, slug=slug, name=name, category='unit',
                          description='Beschreibung', status='active')


def _make_iteration(session, concept_id, version_name='v1'):
    spec = {'indicators': {'vwma': {'indicator': 'vwma', 'length': 20}},
            'rules': {'entry': {'blocks': [{'conditions': []}]}, 'exit': None}}
    return create_iteration(
        session, concept_id=concept_id,
        version=next_iteration_version(session, concept_id),
        version_name=version_name, spec_json=spec, spec_hash='abc123',
        type='generic', status='active', description='erste Iteration',
    )


# ---------------------------------------------------------------------------
# Konzept
# ---------------------------------------------------------------------------

def test_export_concept_writes_file(session, tmp_path):
    concept = _make_concept(session)
    path = strategy_io.export_concept(session, concept.id)
    assert path == tmp_path / 'io-test' / 'concept.json'
    assert path.is_file()
    payload = json.loads(path.read_text(encoding='utf-8'))
    assert payload['kind'] == 'strategy_concept'
    assert payload['concept']['slug'] == 'io-test'
    assert payload['concept']['name'] == 'IO Test'


def test_import_concept_creates_new(session):
    payload = {'concept': {'slug': 'fresh-slug', 'name': 'Frisch',
                           'category': 'cat', 'description': 'd', 'status': 'active'}}
    concept, action = strategy_io.import_concept(session, payload)
    assert action == 'created'
    assert concept.id is not None
    assert concept.slug == 'fresh-slug'
    assert concept.name == 'Frisch'


def test_import_concept_updates_existing(session):
    _make_concept(session, slug='dup', name='Alt')
    payload = {'concept': {'slug': 'dup', 'name': 'Neu', 'status': 'active'}}
    concept, action = strategy_io.import_concept(session, payload)
    assert action == 'updated'
    assert concept.name == 'Neu'


def test_import_concept_rejects_invalid(session):
    with pytest.raises(ValueError):
        strategy_io.import_concept(session, {'concept': {'name': 'ohne slug'}})


# ---------------------------------------------------------------------------
# Iteration
# ---------------------------------------------------------------------------

def test_iteration_roundtrip(session):
    concept = _make_concept(session)
    original = _make_iteration(session, concept.id)
    path = strategy_io.export_iteration(session, original.id)
    assert path.is_file()
    payload = json.loads(path.read_text(encoding='utf-8'))

    imported = strategy_io.import_iteration(session, concept.id, payload)
    assert imported.id != original.id
    assert imported.version != original.version  # frische Nummer pro Konzept
    assert imported.spec_json == original.spec_json
    assert imported.spec_hash == original.spec_hash
    assert imported.type == original.type
    assert imported.parent_iteration_id is None


def test_import_iteration_rejects_unknown_concept(session):
    with pytest.raises(ValueError):
        strategy_io.import_iteration(session, 999999, {'iteration': {}})


# ---------------------------------------------------------------------------
# IndicatorConfig
# ---------------------------------------------------------------------------

def test_indicator_config_roundtrip(session):
    concept = _make_concept(session)
    iteration = _make_iteration(session, concept.id)
    config = IndicatorConfig(name='Sweep A', description='desc',
                             config_json={'vwma': {'length': [10, 20]}, '_stops': {}},
                             is_default=0, strategy_concept_id=concept.id,
                             strategy_iteration_id=iteration.id)
    session.add(config)
    session.commit()
    session.refresh(config)

    path = strategy_io.export_indicator_config(session, config.id)
    assert path.is_file()
    payload = json.loads(path.read_text(encoding='utf-8'))
    assert payload['indicator_config']['name'] == 'Sweep A'

    imported = strategy_io.import_indicator_config(
        session, payload, strategy_iteration_id=iteration.id)
    assert imported.id != config.id
    assert imported.name == 'Sweep A'
    assert imported.config_json == config.config_json
    assert imported.strategy_iteration_id == iteration.id


def test_import_indicator_config_rejects_invalid(session):
    with pytest.raises(ValueError):
        strategy_io.import_indicator_config(session, {'indicator_config': {'name': 'x'}})

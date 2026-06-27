"""Ticket 22 — IndicatorConfig: lose Verknüpfung Concept/Iteration + 3-Bucket-Sortierung.

Verifiziert:
- IndicatorConfig akzeptiert strategy_concept_id und strategy_iteration_id (Integer, nullable, kein FK).
- GET /api/config/indicator sortiert nach Buckets, wenn concept_id/iteration_id Query-Params gesetzt sind:
  1) exakter Match (concept + iteration), 2) nur Concept-Match, 3) Rest.
- Innerhalb Bucket: is_default DESC, Iterations-Version DESC, name ASC.
- Read-Only-Lookups (strategy_concept_name, strategy_iteration_version) werden befüllt;
  zeigen NULL bei gelöschten/nicht existierenden Zielen (lose Kopplung).
- Ohne Query-Params: Fallback-Sortierung is_default DESC, name.
"""

import sys
import types
from datetime import datetime, timedelta

import pytest

# rq ist nur im Worker-Container installiert — für reine Tests stubben wir den Import
if 'rq' not in sys.modules:
    rq_stub = types.ModuleType('rq')
    rq_stub.Queue = object  # nicht aufgerufen in den getesteten Pfaden
    sys.modules['rq'] = rq_stub

from services.api.routes import api_config as api_config_module  # noqa: E402
from user_data.utils.database.models import (  # noqa: E402
    IndicatorConfig,
    StrategyConcept,
    StrategyIteration,
)


@pytest.fixture
def seeded_session(test_session, monkeypatch):
    """Befüllt eine SQLite-Session mit 2 Concepts, 3 Iterationen, 5 IndicatorConfigs."""
    # Concepts
    c1 = StrategyConcept(id=1, slug='teststrategie', name='Teststrategie-Konzept', status='active')
    c2 = StrategyConcept(id=2, slug='pullback', name='Pullback-Konzept', status='active')
    test_session.add_all([c1, c2])

    # Iterationen
    i11 = StrategyIteration(id=11, concept_id=1, version=1, type='generic')
    i12 = StrategyIteration(id=12, concept_id=1, version=2, type='generic')
    i21 = StrategyIteration(id=21, concept_id=2, version=1, type='generic')
    test_session.add_all([i11, i12, i21])
    test_session.commit()

    # IndicatorConfigs — fünf Einträge mit unterschiedlicher Verknüpfung
    base = datetime(2026, 1, 1, 12, 0, 0)
    cfgs = [
        # Exakter Match (concept=1, iter=11)
        IndicatorConfig(name='A_exact', config_json={}, is_default=0,
                        strategy_concept_id=1, strategy_iteration_id=11,
                        created_at=base + timedelta(days=1)),
        # Nur Concept-Match (concept=1, iter=12)
        IndicatorConfig(name='B_concept_only', config_json={}, is_default=0,
                        strategy_concept_id=1, strategy_iteration_id=12,
                        created_at=base + timedelta(days=2)),
        # Concept-Match aber default-flag
        IndicatorConfig(name='C_concept_default', config_json={}, is_default=1,
                        strategy_concept_id=1, strategy_iteration_id=None,
                        created_at=base + timedelta(days=3)),
        # Anderes Concept (Rest)
        IndicatorConfig(name='D_other', config_json={}, is_default=0,
                        strategy_concept_id=2, strategy_iteration_id=21,
                        created_at=base + timedelta(days=4)),
        # Gar keine Verknüpfung (Rest, jüngster)
        IndicatorConfig(name='E_no_link', config_json={}, is_default=0,
                        strategy_concept_id=None, strategy_iteration_id=None,
                        created_at=base + timedelta(days=5)),
    ]
    test_session.add_all(cfgs)
    test_session.commit()

    # get_session-Monkeypatch: api_config liest Session via get_session()
    monkeypatch.setattr(api_config_module, 'get_session', lambda: test_session)
    return test_session


def test_indicator_config_columns_exist(test_session):
    """Smoke-Test: strategy_concept_id und strategy_iteration_id sind nullable Integer-Spalten."""
    ic = IndicatorConfig(
        name='Smoke',
        config_json={},
        is_default=0,
        strategy_concept_id=None,
        strategy_iteration_id=None,
    )
    test_session.add(ic)
    test_session.commit()
    test_session.refresh(ic)
    assert ic.strategy_concept_id is None
    assert ic.strategy_iteration_id is None


def test_list_without_params_uses_fallback_sort(seeded_session):
    """Ohne Query-Params: is_default DESC, Iterations-Version DESC, name ASC."""
    resp = api_config_module.list_indicator_configs(concept_id=None, iteration_id=None)
    names = [item['name'] for item in resp['data']]
    # C_concept_default (is_default=1) zuerst. Danach Iterations-Version DESC:
    # B(v2) vor A(v1)/D(v1) — bei gleicher Version name ASC (A vor D) — dann E(v0).
    assert names[0] == 'C_concept_default'
    assert names[1:] == ['B_concept_only', 'A_exact', 'D_other', 'E_no_link']


def test_list_with_concept_only_sorts_concept_match_first(seeded_session):
    """concept_id=1 ohne iteration_id: alle concept=1 zuerst (innerhalb is_default+timestamp), Rest danach."""
    resp = api_config_module.list_indicator_configs(concept_id=1, iteration_id=None)
    names = [item['name'] for item in resp['data']]
    # Erste drei: alle mit concept=1 (C ist default -> zuerst, dann B vor A nach updated/created DESC)
    assert set(names[:3]) == {'A_exact', 'B_concept_only', 'C_concept_default'}
    assert names[0] == 'C_concept_default'  # is_default
    # Rest: D, E
    assert set(names[3:]) == {'D_other', 'E_no_link'}


def test_list_with_concept_and_iteration_three_buckets(seeded_session):
    """concept_id=1, iteration_id=11: A_exact zuerst, dann B+C (concept-only), dann Rest."""
    resp = api_config_module.list_indicator_configs(concept_id=1, iteration_id=11)
    names = [item['name'] for item in resp['data']]
    # Bucket 0 (exakt): nur A
    assert names[0] == 'A_exact'
    # Bucket 1 (concept-only): C (default) zuerst, dann B
    assert names[1] == 'C_concept_default'
    assert names[2] == 'B_concept_only'
    # Bucket 2 (Rest): Iterations-Version DESC -> D (iter=21, v1) vor E (kein iter, v0)
    assert names[3] == 'D_other'
    assert names[4] == 'E_no_link'


def test_lookup_fields_populated_and_null_safe(seeded_session):
    """strategy_concept_name/iteration_version werden gesetzt; NULL bei fehlender Verknüpfung."""
    resp = api_config_module.list_indicator_configs(concept_id=None, iteration_id=None)
    by_name = {item['name']: item for item in resp['data']}
    assert by_name['A_exact']['strategy_concept_name'] == 'Teststrategie-Konzept'
    # GEÄNDERT: version ist eine Integer-Nummer (Iteration 11 hat version=1)
    assert by_name['A_exact']['strategy_iteration_version'] == 1
    assert by_name['C_concept_default']['strategy_concept_name'] == 'Teststrategie-Konzept'
    assert by_name['C_concept_default']['strategy_iteration_version'] is None
    assert by_name['E_no_link']['strategy_concept_name'] is None
    assert by_name['E_no_link']['strategy_iteration_version'] is None


def test_lookup_field_null_for_deleted_target(seeded_session):
    """Lose Kopplung: ID auf nicht existierendes Concept -> name=None, kein Fehler."""
    # Neue Config mit unbekannter concept_id
    orphan = IndicatorConfig(
        name='Z_orphan',
        config_json={},
        is_default=0,
        strategy_concept_id=9999,
        strategy_iteration_id=9999,
    )
    seeded_session.add(orphan)
    seeded_session.commit()
    resp = api_config_module.list_indicator_configs(concept_id=None, iteration_id=None)
    orph = next(item for item in resp['data'] if item['name'] == 'Z_orphan')
    assert orph['strategy_concept_id'] == 9999
    assert orph['strategy_concept_name'] is None
    assert orph['strategy_iteration_version'] is None

"""Indicator-Config Teil-Update (PATCH) — nur gesetzte Felder werden geschrieben.

Verifiziert services/api/routes/api_config.py:patch_indicator_config:
- nachträgliche Konzept-/Iterations-Verknüpfung lässt config_json/name/description/is_default
  bit-genau unangetastet (Kernfall ToDo 9)
- gezieltes Setzen von name/description ohne vollen Body
- leerer Body -> 400
- unbekannte Config -> 404
- exklusives is_default bleibt beim Setzen exklusiv
"""

import sys
import types

# rq nur im Worker-Container vorhanden — für Tests stubben
if 'rq' not in sys.modules:
    rq_stub = types.ModuleType('rq')
    rq_stub.Queue = object
    sys.modules['rq'] = rq_stub

from sqlalchemy.orm import sessionmaker  # noqa: E402

from services.api.routes import api_config as api_config_module  # noqa: E402
from services.api.routes.api_config import IndicatorConfigIn, IndicatorConfigPatch  # noqa: E402
from user_data.utils.database.models import IndicatorConfig  # noqa: E402


_CONFIG_JSON = {
    "vwma": {
        "indicator": "vwma", "enabled": True, "tf": "same",
        "vwma_length": {"type": "arange", "start": 5, "stop": 20, "step": 1, "dtype": "int"},
    },
    "_stops": {"tp_stop": 0.3, "sl_stop": 0.15},
}


def _create(session_factory, monkeypatch, name="Cfg", config_json=None, is_default=0):
    monkeypatch.setattr(api_config_module, 'get_session', lambda: session_factory())
    data = IndicatorConfigIn(name=name, config_json=config_json or _CONFIG_JSON, is_default=is_default)
    return api_config_module.create_indicator_config(data)['data']


def test_patch_verknuepfung_laesst_rest_unangetastet(test_engine, monkeypatch):
    """Nachträgliche Concept/Iteration-Verknüpfung ändert config_json/name/desc/is_default nicht."""
    Session = sessionmaker(bind=test_engine)
    created = _create(Session, monkeypatch, name="VWMA-Raster")
    cid = created['id']

    resp = api_config_module.patch_indicator_config(
        cid, IndicatorConfigPatch(strategy_concept_id=2, strategy_iteration_id=7)
    )
    assert resp['error'] is None
    data = resp['data']
    assert data['strategy_concept_id'] == 2
    assert data['strategy_iteration_id'] == 7
    # Bit-genau unverändert
    assert data['config_json'] == _CONFIG_JSON
    assert data['name'] == "VWMA-Raster"
    assert data['description'] is None
    assert data['is_default'] == 0


def test_patch_setzt_nur_name_und_description(test_engine, monkeypatch):
    """Gezieltes Setzen von name/description berührt config_json nicht."""
    Session = sessionmaker(bind=test_engine)
    created = _create(Session, monkeypatch, name="Alt")
    cid = created['id']

    resp = api_config_module.patch_indicator_config(
        cid, IndicatorConfigPatch(name="Neu — Zusatz", description="Beschreibung")
    )
    data = resp['data']
    assert data['name'] == "Neu — Zusatz"
    assert data['description'] == "Beschreibung"
    assert data['config_json'] == _CONFIG_JSON


def test_patch_leerer_body_400(test_engine, monkeypatch):
    """PATCH ohne gesetzte Felder liefert 400 (kein stiller No-op)."""
    Session = sessionmaker(bind=test_engine)
    created = _create(Session, monkeypatch, name="X")
    resp = api_config_module.patch_indicator_config(created['id'], IndicatorConfigPatch())
    assert resp.status_code == 400


def test_patch_unbekannte_config_404(test_engine, monkeypatch):
    """PATCH auf nicht existierende Config liefert 404."""
    Session = sessionmaker(bind=test_engine)
    monkeypatch.setattr(api_config_module, 'get_session', lambda: Session())
    resp = api_config_module.patch_indicator_config(999999, IndicatorConfigPatch(name="X"))
    assert resp.status_code == 404


def test_patch_is_default_bleibt_exklusiv(test_engine, monkeypatch):
    """Wird is_default per PATCH auf 1 gesetzt, verlieren andere Configs ihr Flag."""
    Session = sessionmaker(bind=test_engine)
    a = _create(Session, monkeypatch, name="A", is_default=1)
    b = _create(Session, monkeypatch, name="B", is_default=0)

    api_config_module.patch_indicator_config(b['id'], IndicatorConfigPatch(is_default=1))

    s = Session()
    try:
        rows = {c.id: c.is_default for c in s.query(IndicatorConfig).all()}
    finally:
        s.close()
    assert rows[b['id']] == 1
    assert rows[a['id']] == 0

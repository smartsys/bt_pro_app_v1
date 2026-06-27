"""Backtest-Config Favoriten-Stern (ersetzt das frühere exklusive Default-Flag).

Verifiziert:
- toggle_backtest_config_favorite: schaltet is_favorite an und wieder aus
- toggle_backtest_config_favorite: 404 bei unbekannter Config
- create_config: legt Config immer mit is_favorite=0 an (nicht-exklusiv, kein Flag im Input)
- create_config: mehrere Favoriten möglich (kein Zurücksetzen anderer beim Anlegen)
- update_config: lässt is_favorite unangetastet (Markierung nur über Toggle)
"""

import sys
import types

import pytest

# rq ist nur im Worker-Container installiert — für reine Tests stubben wir den Import
if 'rq' not in sys.modules:
    rq_stub = types.ModuleType('rq')
    rq_stub.Queue = object
    sys.modules['rq'] = rq_stub

from sqlalchemy.orm import sessionmaker  # noqa: E402

from services.api.routes import api_config as api_config_module  # noqa: E402
from services.api.routes.api_config import BacktestConfigIn  # noqa: E402
from user_data.utils.database.models import BacktestConfig  # noqa: E402


def _make_config_in(name: str) -> BacktestConfigIn:
    """Minimal gültiges Eingabe-Schema für eine Backtest-Config."""
    return BacktestConfigIn(
        name=name,
        start='2023-01-01',
        end='2024-01-01',
        ohlc_start='2023-01-01',
        ohlc_end='2024-01-01',
    )


def test_backtest_config_in_kennt_kein_default_flag():
    """Das Eingabe-Schema hat kein is_default/is_favorite-Feld mehr."""
    assert 'is_default' not in BacktestConfigIn.model_fields
    assert 'is_favorite' not in BacktestConfigIn.model_fields


def test_create_config_immer_kein_favorit(test_engine, monkeypatch):
    """Neu angelegte Config ist nie Favorit (Default 0)."""
    Session = sessionmaker(bind=test_engine)
    monkeypatch.setattr(api_config_module, 'get_session', lambda: Session())

    resp = api_config_module.create_config(_make_config_in('A'))
    assert resp['error'] is None
    assert resp['data']['is_favorite'] == 0


def test_toggle_schaltet_an_und_aus(test_engine, monkeypatch):
    """Toggle setzt is_favorite auf 1 und beim zweiten Aufruf zurück auf 0."""
    Session = sessionmaker(bind=test_engine)
    monkeypatch.setattr(api_config_module, 'get_session', lambda: Session())

    created = api_config_module.create_config(_make_config_in('A'))['data']
    config_id = created['id']

    on = api_config_module.toggle_backtest_config_favorite(config_id)
    assert on['error'] is None
    assert on['data']['is_favorite'] is True

    off = api_config_module.toggle_backtest_config_favorite(config_id)
    assert off['data']['is_favorite'] is False

    # Datenbankprüfung
    s = Session()
    saved = s.query(BacktestConfig).filter(BacktestConfig.id == config_id).first()
    assert saved.is_favorite == 0
    s.close()


def test_toggle_404_bei_unbekannter_config(test_engine, monkeypatch):
    """Toggle auf nicht existierende Config liefert 404."""
    Session = sessionmaker(bind=test_engine)
    monkeypatch.setattr(api_config_module, 'get_session', lambda: Session())

    resp = api_config_module.toggle_backtest_config_favorite(99999)
    assert resp.status_code == 404


def test_mehrere_favoriten_moeglich(test_engine, monkeypatch):
    """Anlegen setzt keine anderen Favoriten zurück — mehrere Favoriten erlaubt."""
    Session = sessionmaker(bind=test_engine)
    monkeypatch.setattr(api_config_module, 'get_session', lambda: Session())

    a = api_config_module.create_config(_make_config_in('A'))['data']
    b = api_config_module.create_config(_make_config_in('B'))['data']
    api_config_module.toggle_backtest_config_favorite(a['id'])
    api_config_module.toggle_backtest_config_favorite(b['id'])

    s = Session()
    favorites = s.query(BacktestConfig).filter(BacktestConfig.is_favorite == 1).count()
    assert favorites == 2
    s.close()


def test_update_laesst_favorit_unberuehrt(test_engine, monkeypatch):
    """Speichern (PUT) ändert is_favorite nicht — Markierung nur über Toggle."""
    Session = sessionmaker(bind=test_engine)
    monkeypatch.setattr(api_config_module, 'get_session', lambda: Session())

    created = api_config_module.create_config(_make_config_in('A'))['data']
    config_id = created['id']
    api_config_module.toggle_backtest_config_favorite(config_id)  # jetzt Favorit

    updated = api_config_module.update_config(config_id, _make_config_in('A umbenannt'))
    assert updated['error'] is None
    assert updated['data']['name'] == 'A umbenannt'
    assert updated['data']['is_favorite'] == 1

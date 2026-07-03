"""Doku-Favorit + gewonnene Bestwert-Kriterien (roter Stern, ToDo 10).

Verifiziert services/api/routes/api_backtest.py:
- mark_doc_favorite_criteria: setzt roten Stern + best_criteria_json (idempotent), überschreibt
  Keys auch bei bereits gesetztem Stern, dedupliziert
- unbekannter Key -> 400, unbekanntes Result -> 404
- toggle_doc_favorite: beim Ausschalten werden die Kriterien mit-geleert (Kopplung)
"""

import json
import sys
import types

# rq-Familie stubben (nur im Worker-Container installiert), damit api_backtest importierbar ist
for _m in ('rq', 'rq.job', 'rq.registry', 'rq.command'):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)
sys.modules['rq'].Queue = object
sys.modules['rq.job'].Job = object
sys.modules['rq.registry'].StartedJobRegistry = object
sys.modules['rq.command'].send_stop_job_command = lambda *a, **k: None

from sqlalchemy.orm import sessionmaker  # noqa: E402

from services.api.routes import api_backtest as api_backtest_module  # noqa: E402
from user_data.utils.database.models import BacktestResult  # noqa: E402


def _decode(resp) -> dict:
    """JSONResponse-Body als Dict."""
    return json.loads(resp.body)


def _make_result(session, run_id=1, doc_fav=0, criteria=None) -> int:
    """Minimales BacktestResult in die Test-DB schreiben, gibt die id zurück."""
    r = BacktestResult(
        run_id=run_id,
        params_hash='abc',
        actual_params_json={'x': 1},
        is_doc_favorite=doc_fav,
        best_criteria_json=criteria,
    )
    session.add(r)
    session.commit()
    rid = r.id
    return rid


def test_mark_setzt_stern_und_kriterien(test_engine, monkeypatch):
    """mark setzt is_doc_favorite=1 und schreibt die Keys."""
    Session = sessionmaker(bind=test_engine)
    s = Session()
    rid = _make_result(s)
    s.close()
    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())

    resp = api_backtest_module.mark_doc_favorite_criteria(rid, {'criteria': ['max_return', 'sharpe_band']})
    body = _decode(resp)
    assert body['is_doc_favorite'] is True
    assert body['best_criteria'] == ['max_return', 'sharpe_band']

    s = Session()
    saved = s.get(BacktestResult, rid)
    assert saved.is_doc_favorite == 1
    assert saved.best_criteria_json == ['max_return', 'sharpe_band']
    s.close()


def test_mark_ueberschreibt_und_dedupliziert(test_engine, monkeypatch):
    """mark überschreibt bestehende Keys auch bei gesetztem Stern und entfernt Duplikate."""
    Session = sessionmaker(bind=test_engine)
    s = Session()
    rid = _make_result(s, doc_fav=1, criteria=['max_return'])
    s.close()
    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())

    api_backtest_module.mark_doc_favorite_criteria(rid, {'criteria': ['pf_min30', 'pf_min30']})
    s = Session()
    saved = s.get(BacktestResult, rid)
    assert saved.best_criteria_json == ['pf_min30']
    assert saved.is_doc_favorite == 1
    s.close()


def test_mark_unbekannter_key_400(test_engine, monkeypatch):
    """Unbekannter Kriterium-Key liefert 400."""
    Session = sessionmaker(bind=test_engine)
    s = Session()
    rid = _make_result(s)
    s.close()
    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())
    resp = api_backtest_module.mark_doc_favorite_criteria(rid, {'criteria': ['quatsch']})
    assert resp.status_code == 400


def test_mark_unbekanntes_result_404(test_engine, monkeypatch):
    """mark auf nicht existierendes Result liefert 404 (HTTPException)."""
    import pytest
    from fastapi import HTTPException
    Session = sessionmaker(bind=test_engine)
    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())
    with pytest.raises(HTTPException) as exc:
        api_backtest_module.mark_doc_favorite_criteria(999999, {'criteria': ['max_return']})
    assert exc.value.status_code == 404


def test_toggle_off_leert_kriterien(test_engine, monkeypatch):
    """toggle_doc_favorite schaltet den Stern aus UND leert best_criteria_json (Kopplung)."""
    Session = sessionmaker(bind=test_engine)
    s = Session()
    rid = _make_result(s, doc_fav=1, criteria=['max_return', 'sharpe_band'])
    s.close()
    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())

    resp = api_backtest_module.toggle_doc_favorite(rid)
    assert _decode(resp)['is_doc_favorite'] is False

    s = Session()
    saved = s.get(BacktestResult, rid)
    assert saved.is_doc_favorite == 0
    assert saved.best_criteria_json is None
    s.close()

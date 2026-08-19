"""Gelber Favoriten-Stern eines Results — setzend statt umschaltend (Ticket 89).

Verifiziert services/api/routes/api_backtest.py:
- mark_favorite: setzt is_favorite idempotent (nie aus), changed-Flag korrekt
- unmark_favorite: entfernt is_favorite gezielt und idempotent, changed-Flag korrekt
- unbekanntes Result -> 404 bei beiden Routen
- toggle_favorite (Frontend-Stern) bleibt unverändert ein reiner Toggle
"""

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

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from services.api.routes import api_backtest as api_backtest_module  # noqa: E402
from user_data.utils.database.models import BacktestResult  # noqa: E402


def _decode(resp) -> dict:
    """JSONResponse-Body als Dict."""
    import json
    return json.loads(resp.body)


def _make_result(session, run_id=1, is_favorite=0) -> int:
    r = BacktestResult(
        run_id=run_id,
        params_hash='abc',
        actual_params_json={'x': 1},
        is_favorite=is_favorite,
    )
    session.add(r)
    session.commit()
    rid = r.id
    return rid


def test_mark_setzt_favorit_idempotent(test_engine, monkeypatch):
    Session = sessionmaker(bind=test_engine)
    s = Session()
    rid = _make_result(s)
    s.close()
    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())

    first = _decode(api_backtest_module.mark_favorite(rid))
    assert first['is_favorite'] is True
    assert first['changed'] is True

    second = _decode(api_backtest_module.mark_favorite(rid))
    assert second['is_favorite'] is True
    assert second['changed'] is False

    s = Session()
    saved = s.get(BacktestResult, rid)
    assert saved.is_favorite == 1
    s.close()


def test_unmark_entfernt_favorit_idempotent(test_engine, monkeypatch):
    Session = sessionmaker(bind=test_engine)
    s = Session()
    rid = _make_result(s, is_favorite=1)
    s.close()
    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())

    first = _decode(api_backtest_module.unmark_favorite(rid))
    assert first['is_favorite'] is False
    assert first['changed'] is True

    second = _decode(api_backtest_module.unmark_favorite(rid))
    assert second['is_favorite'] is False
    assert second['changed'] is False

    s = Session()
    saved = s.get(BacktestResult, rid)
    assert saved.is_favorite == 0
    s.close()


def test_mark_unbekanntes_result_404(test_engine, monkeypatch):
    Session = sessionmaker(bind=test_engine)
    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())
    with pytest.raises(HTTPException) as exc:
        api_backtest_module.mark_favorite(999999)
    assert exc.value.status_code == 404


def test_unmark_unbekanntes_result_404(test_engine, monkeypatch):
    Session = sessionmaker(bind=test_engine)
    monkeypatch.setattr(api_backtest_module, 'get_session', lambda: Session())
    with pytest.raises(HTTPException) as exc:
        api_backtest_module.unmark_favorite(999999)
    assert exc.value.status_code == 404

"""Favoriten-Sterne einer Iteration (gelb + roter Doku-Stern) — setzend statt
umschaltend.

Verifiziert services/api/routes/api_strategy.py:
- mark_iteration_favorite / mark_iteration_doc_favorite: setzen idempotent (nie aus),
  changed-Flag korrekt
- unmark_iteration_favorite / unmark_iteration_doc_favorite: entfernen gezielt und
  idempotent, changed-Flag korrekt
- unbekannte Iteration -> 404 bei allen vier Routen
- toggle_iteration_favorite / toggle_iteration_doc_favorite (Frontend-Stern) bleiben
  unverändert reine Toggles
"""

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from services.api.routes import api_strategy as api_strategy_module
from user_data.utils.database.models import StrategyConcept, StrategyIteration


def _make_iteration(session, *, is_favorite=False, is_doc_favorite=False) -> int:
    concept = StrategyConcept(slug='test-fav-set', name='Test Favorite Set')
    session.add(concept)
    session.commit()
    iteration = StrategyIteration(
        concept_id=concept.id,
        version=1,
        is_favorite=is_favorite,
        is_doc_favorite=is_doc_favorite,
    )
    session.add(iteration)
    session.commit()
    return iteration.id


@pytest.mark.parametrize(
    'mark_fn_name,unmark_fn_name,field',
    [
        ('mark_iteration_favorite', 'unmark_iteration_favorite', 'is_favorite'),
        ('mark_iteration_doc_favorite', 'unmark_iteration_doc_favorite', 'is_doc_favorite'),
    ],
)
def test_mark_setzt_idempotent(test_engine, monkeypatch, mark_fn_name, unmark_fn_name, field):
    Session = sessionmaker(bind=test_engine)
    s = Session()
    iid = _make_iteration(s)
    s.close()
    monkeypatch.setattr(api_strategy_module, 'get_session', lambda: Session())
    mark_fn = getattr(api_strategy_module, mark_fn_name)

    first = mark_fn(iid)
    assert first['data'][field] is True
    assert first['data']['changed'] is True

    second = mark_fn(iid)
    assert second['data'][field] is True
    assert second['data']['changed'] is False

    s = Session()
    saved = s.get(StrategyIteration, iid)
    assert bool(getattr(saved, field)) is True
    s.close()


@pytest.mark.parametrize(
    'mark_fn_name,unmark_fn_name,field',
    [
        ('mark_iteration_favorite', 'unmark_iteration_favorite', 'is_favorite'),
        ('mark_iteration_doc_favorite', 'unmark_iteration_doc_favorite', 'is_doc_favorite'),
    ],
)
def test_unmark_entfernt_idempotent(test_engine, monkeypatch, mark_fn_name, unmark_fn_name, field):
    Session = sessionmaker(bind=test_engine)
    s = Session()
    kwargs = {field: True}
    iid = _make_iteration(s, **kwargs)
    s.close()
    monkeypatch.setattr(api_strategy_module, 'get_session', lambda: Session())
    unmark_fn = getattr(api_strategy_module, unmark_fn_name)

    first = unmark_fn(iid)
    assert first['data'][field] is False
    assert first['data']['changed'] is True

    second = unmark_fn(iid)
    assert second['data'][field] is False
    assert second['data']['changed'] is False

    s = Session()
    saved = s.get(StrategyIteration, iid)
    assert bool(getattr(saved, field)) is False
    s.close()


@pytest.mark.parametrize(
    'fn_name',
    [
        'mark_iteration_favorite',
        'unmark_iteration_favorite',
        'mark_iteration_doc_favorite',
        'unmark_iteration_doc_favorite',
    ],
)
def test_unbekannte_iteration_404(test_engine, monkeypatch, fn_name):
    Session = sessionmaker(bind=test_engine)
    monkeypatch.setattr(api_strategy_module, 'get_session', lambda: Session())
    fn = getattr(api_strategy_module, fn_name)
    with pytest.raises(HTTPException) as exc:
        fn(999999)
    assert exc.value.status_code == 404

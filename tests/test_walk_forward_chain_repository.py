"""Tests des Ketten-Repositories und der ORM-Wächter (Ticket 82).

Der Schutz sitzt am ORM-Mapper und gilt damit für jeden Schreibweg über eine
Session — nicht nur für die Repository-Funktionen. Geprüft wird:

* Folds wachsen streng append-only; ein bereits angehängter Fold lässt sich
  weder umschreiben noch entfernen.
* Plan und Kontext sind ab der Anlage unveränderlich (Vorregistrierung).
* Nach ``completed``/``failed`` weist jede Änderung ab.
* Fold-Anhänge mit falschem Index oder abweichendem Fenster laufen auf.
"""

import pytest

from user_data.utils.database.models import (
    WalkForwardChain,
    WalkForwardChainImmutableError,
)
from user_data.utils.database.repository_walk_forward_chains import (
    WalkForwardPlanMismatchError,
    append_walk_forward_fold,
    complete_walk_forward_chain,
    create_walk_forward_chain,
    fail_walk_forward_chain,
    get_walk_forward_chain,
    list_walk_forward_chains,
    walk_forward_chain_to_dict,
)

_PLAN = {
    'n_folds': 2,
    'oos_months': 3,
    'selection_metric': 'sharpe_ratio',
    'selection_direction': 'max',
    'trade_floor': 5,
    'folds': [
        {
            'fold_index': 1,
            'is_window': {'start': '2020-01-01', 'end': '2021-01-01'},
            'oos_window': {'start': '2021-01-01', 'end': '2021-04-01'},
        },
        {
            'fold_index': 2,
            'is_window': {'start': '2020-03-31', 'end': '2021-04-01'},
            'oos_window': {'start': '2021-04-01', 'end': '2021-07-01'},
        },
    ],
}


def _fold(fold_index: int, with_winner: bool = True) -> dict:
    """Baut einen planungskonformen Fold-Block."""
    planned = _PLAN['folds'][fold_index - 1]
    fold = {
        'fold_index': fold_index,
        'is_window': dict(planned['is_window']),
        'is_run_id': 100 + fold_index,
        'winner': None,
        'no_winner_reason': 'Kein Kandidat über dem Trade-Floor.',
        'oos_window': None,
        'oos_run_id': None,
        'oos_result_id': None,
        'oos_metrics': None,
        'ann_factor': None,
    }
    if with_winner:
        fold.update({
            'winner': {'result_id': 200 + fold_index, 'selection_value': 2.0},
            'no_winner_reason': None,
            'oos_window': dict(planned['oos_window']),
            'oos_run_id': 300 + fold_index,
            'oos_result_id': 400 + fold_index,
        })
    return fold


@pytest.fixture
def chain(test_session):
    """Legt eine laufende Kette an."""
    return create_walk_forward_chain(
        session=test_session, anchor_run_id=7, plan=_PLAN,
        iteration_id=3, concept_id=1,
        config_snapshot={'symbol': 'BTCUSDT'}, method_note='Hinweis',
    )


def test_create_requires_fold_windows(test_session):
    with pytest.raises(ValueError):
        create_walk_forward_chain(
            session=test_session, anchor_run_id=1, plan={'n_folds': 0, 'folds': []},
        )


def test_create_deep_copies_the_plan(test_session):
    plan = {'n_folds': 1, 'folds': [{'fold_index': 1, 'is_window': {}, 'oos_window': {}}]}
    created = create_walk_forward_chain(
        session=test_session, anchor_run_id=1, plan=plan,
    )
    plan['n_folds'] = 99
    assert get_walk_forward_chain(test_session, created.id).plan_json['n_folds'] == 1


def test_folds_are_appended_in_order(test_session, chain):
    append_walk_forward_fold(test_session, chain.id, _fold(1))
    updated = append_walk_forward_fold(test_session, chain.id, _fold(2, with_winner=False))

    assert [fold['fold_index'] for fold in updated.folds_json] == [1, 2]
    assert updated.folds_json[1]['winner'] is None
    assert 'Trade-Floor' in updated.folds_json[1]['no_winner_reason']


def test_wrong_fold_index_is_rejected(test_session, chain):
    with pytest.raises(WalkForwardPlanMismatchError, match='Fold 1'):
        append_walk_forward_fold(test_session, chain.id, _fold(2))


def test_window_off_the_plan_is_rejected(test_session, chain):
    fold = _fold(1)
    fold['is_window']['end'] = '2021-02-01'
    with pytest.raises(WalkForwardPlanMismatchError, match='IS-Fenster'):
        append_walk_forward_fold(test_session, chain.id, fold)


def test_oos_window_off_the_plan_is_rejected(test_session, chain):
    fold = _fold(1)
    fold['oos_window']['end'] = '2021-05-01'
    with pytest.raises(WalkForwardPlanMismatchError, match='OOS-Fenster'):
        append_walk_forward_fold(test_session, chain.id, fold)


def test_existing_folds_cannot_be_rewritten(test_session, chain):
    append_walk_forward_fold(test_session, chain.id, _fold(1))

    stored = get_walk_forward_chain(test_session, chain.id)
    rewritten = [dict(stored.folds_json[0], oos_result_id=999)]
    stored.folds_json = rewritten
    with pytest.raises(WalkForwardChainImmutableError, match='unveränderlich'):
        test_session.commit()
    test_session.rollback()


def test_folds_cannot_be_removed(test_session, chain):
    append_walk_forward_fold(test_session, chain.id, _fold(1))

    stored = get_walk_forward_chain(test_session, chain.id)
    stored.folds_json = []
    with pytest.raises(WalkForwardChainImmutableError):
        test_session.commit()
    test_session.rollback()


def test_plan_and_context_are_frozen(test_session, chain):
    stored = get_walk_forward_chain(test_session, chain.id)
    stored.anchor_run_id = 42
    with pytest.raises(WalkForwardChainImmutableError, match='Vorregistrierung'):
        test_session.commit()
    test_session.rollback()


def test_completed_chain_is_immutable(test_session, chain):
    append_walk_forward_fold(test_session, chain.id, _fold(1))
    complete_walk_forward_chain(test_session, chain.id, {'folds_with_winner': 1})

    with pytest.raises(ValueError, match='abgeschlossen'):
        append_walk_forward_fold(test_session, chain.id, _fold(2))

    stored = get_walk_forward_chain(test_session, chain.id)
    stored.method_note = 'anders'
    with pytest.raises(WalkForwardChainImmutableError):
        test_session.commit()
    test_session.rollback()


def test_failed_chain_is_immutable_and_keeps_its_reason(test_session, chain):
    fail_walk_forward_chain(test_session, chain.id, 'Lauf 5 abgebrochen')

    stored = get_walk_forward_chain(test_session, chain.id)
    assert stored.status == 'failed'
    assert stored.error_message == 'Lauf 5 abgebrochen'

    stored.status = 'completed'
    with pytest.raises(WalkForwardChainImmutableError):
        test_session.commit()
    test_session.rollback()


def test_history_is_chronological(test_session):
    first = create_walk_forward_chain(test_session, 1, _PLAN, iteration_id=3)
    second = create_walk_forward_chain(test_session, 2, _PLAN, iteration_id=3)
    other = create_walk_forward_chain(test_session, 3, _PLAN, iteration_id=4)

    ids = [chain.id for chain in list_walk_forward_chains(test_session, iteration_id=3)]
    assert ids == [first.id, second.id]
    assert [c.id for c in list_walk_forward_chains(test_session)] == [
        first.id, second.id, other.id,
    ]


def test_serialisation_carries_no_verdict(test_session, chain):
    data = walk_forward_chain_to_dict(chain)

    assert set(data) == {
        'id', 'anchor_run_id', 'iteration_id', 'concept_id', 'config_snapshot_json',
        'plan_json', 'folds_json', 'aggregate_json', 'method_note', 'status',
        'error_message', 'created_at', 'completed_at',
    }
    assert data['folds_json'] == []
    assert isinstance(chain, WalkForwardChain)

"""Tests der Metrik-Auswahl-Durchreichung beim Run-Start (Anforderung 2+4).

`create_backtest_run` ist die einzige Stelle, an der eine `metrics`-Rohangabe
('kern'/'voll'/'auto'/Liste/None) zur konkreten Gruppenmenge aufgelöst wird — hier ist
`n_combinations` für Einzel- und Multiparameterlauf exakt dieselbe Zahl, die später als
`backtest_runs.n_combinations` steht. Geprüft wird:

- Ein unbekannter Gruppen-Key/Stufenname wird abgewiesen, BEVOR ein BacktestRun-Datensatz
  entsteht (kein Run wird erzeugt).
- Explizite Auswahl landet roh unter 'metrics' und aufgelöst unter 'metrics_resolved' im
  backtest_config_json; 'metrics_auto_note' bleibt dabei unbenutzt.
- 'auto' unterhalb der (testweise klein gestellten) Schwelle rechnet voll, ohne Notiz;
  ab der Schwelle nur noch 'kern', mit einer Notiz, die Rastergröße und Schwelle nennt.
- Zwei unterschiedlich geformte Raster gleicher Kombinationszahl lösen identisch auf —
  die Auflösung hängt nur an n_combinations, nicht am Weg dorthin (Einzel- vs.
  Multiparameterlauf-Unabhängigkeit, Erbe).
- `assess_run_usability` hängt eine übergebene Metrik-Notiz an die sonst berechnete
  Note an, statt sie zu ersetzen; ohne Notiz bleibt die Note unverändert.

Tests laufen gegen die echte PostgreSQL-Test-DB (VBT_TEST_DATABASE_URL, Port 5562).
db_engine und session kommen aus tests/conftest.py.
"""

import pytest
from sqlalchemy import text

from user_data.utils.metrics.metric_sets import (
    ALL_GROUPS,
    CORE_GROUPS,
    REQUIRED_GROUPS,
)

_BACKTEST_CONFIG: dict = {
    'strategy_family': 'test_family',
    'strategy_name': 'test_strategy',
    'symbols': ['BTCUSDT'],
    'exchange': 'binance',
    'timeframe': '4h',
    'start': '2024-01-01',
    'end': '2024-12-31',
}


def _config(**metrics_kwargs) -> dict:
    """Minimale BacktestConfig, optional mit 'metrics'-Angabe."""
    cfg = dict(_BACKTEST_CONFIG)
    cfg.update(metrics_kwargs)
    return cfg


def _stop_sweep_indicators(n: int, key: str = 'tp_stop') -> dict:
    """indicators_config mit genau n Kombinationen über einen Stop-Sweep.

    Kein Indikator, keine vbt-Abhängigkeit: count_total_combos zählt allein über
    '_stops' (count_stop_combos). key wählbar, um zwei verschieden geformte Raster
    mit derselben Kombinationszahl zu erzeugen.
    """
    return {'_stops': {key: list(range(1, n + 1))}}


@pytest.fixture()
def repo(monkeypatch, session):
    """Verdrahtet das Repository mit der Test-DB."""
    import user_data.utils.database.repository as repo_module

    monkeypatch.setattr(repo_module, 'get_engine', lambda: session.get_bind())
    return repo_module


def _run_row(session, run_id: int):
    return session.execute(
        text('SELECT backtest_config_json FROM backtest_runs WHERE id = :id'),
        {'id': run_id},
    ).fetchone()


def test_unknown_group_key_is_rejected_before_any_run_row_is_created(repo, session):
    """Ein unbekannter Gruppen-Key bricht ab — es entsteht kein BacktestRun-Datensatz."""
    n_before = session.execute(text('SELECT count(*) FROM backtest_runs')).scalar()

    with pytest.raises(ValueError, match='Unbekannte Metrik-Gruppe'):
        repo.create_backtest_run(
            backtest_config=_config(metrics=['gibtsnicht']),
            indicators_config=_stop_sweep_indicators(3),
        )
    session.rollback()

    n_after = session.execute(text('SELECT count(*) FROM backtest_runs')).scalar()
    assert n_after == n_before


def test_unknown_stage_name_is_rejected_before_any_run_row_is_created(repo, session):
    """Ebenso für eine unbekannte Stufe (Zeichenkette statt Liste)."""
    n_before = session.execute(text('SELECT count(*) FROM backtest_runs')).scalar()

    with pytest.raises(ValueError, match='Unbekannte Metrik-Auswahl'):
        repo.create_backtest_run(
            backtest_config=_config(metrics='mittel'),
            indicators_config=_stop_sweep_indicators(3),
        )
    session.rollback()

    n_after = session.execute(text('SELECT count(*) FROM backtest_runs')).scalar()
    assert n_after == n_before


def test_explicit_selection_is_stored_raw_and_resolved(repo, session):
    """Explizite Auswahl steht roh unter 'metrics', aufgelöst unter 'metrics_resolved'."""
    run_id = repo.create_backtest_run(
        backtest_config=_config(metrics='kern'),
        indicators_config=_stop_sweep_indicators(3),
    )
    session.rollback()

    row = _run_row(session, run_id)
    bc = row.backtest_config_json
    assert bc['metrics'] == 'kern'
    assert set(bc['metrics_resolved']) == CORE_GROUPS
    assert 'metrics_auto_note' not in bc


def test_explicit_group_list_adds_to_mandatory_groups(repo, session):
    """Eine explizite Liste ergänzt die Pflichtgruppen, roh und aufgelöst konsistent."""
    run_id = repo.create_backtest_run(
        backtest_config=_config(metrics=['drawdown']),
        indicators_config=_stop_sweep_indicators(2),
    )
    session.rollback()

    bc = _run_row(session, run_id).backtest_config_json
    assert bc['metrics'] == ['drawdown']
    assert set(bc['metrics_resolved']) == REQUIRED_GROUPS | {'drawdown'}
    assert 'metrics_auto_note' not in bc


def test_auto_below_threshold_resolves_to_full_without_note(repo, session, monkeypatch):
    """'auto' unterhalb der Schwelle rechnet voll — keine Notiz."""
    import user_data.utils.metrics.metric_sets as metric_sets
    monkeypatch.setattr(metric_sets, 'AUTO_FULL_COMBINATION_THRESHOLD', 5)

    run_id = repo.create_backtest_run(
        backtest_config=_config(),  # kein 'metrics' -> auto
        indicators_config=_stop_sweep_indicators(4),  # 4 < 5
    )
    session.rollback()

    bc = _run_row(session, run_id).backtest_config_json
    assert 'metrics' not in bc
    assert set(bc['metrics_resolved']) == ALL_GROUPS
    assert 'metrics_auto_note' not in bc


def test_auto_at_threshold_resolves_to_core_and_writes_note(repo, session, monkeypatch):
    """'auto' ab der Schwelle rechnet nur noch 'kern' — mit Notiz."""
    import user_data.utils.metrics.metric_sets as metric_sets
    monkeypatch.setattr(metric_sets, 'AUTO_FULL_COMBINATION_THRESHOLD', 4)

    run_id = repo.create_backtest_run(
        backtest_config=_config(metrics='auto'),
        indicators_config=_stop_sweep_indicators(4),  # 4 >= 4
    )
    session.rollback()

    bc = _run_row(session, run_id).backtest_config_json
    assert set(bc['metrics_resolved']) == CORE_GROUPS
    note = bc['metrics_auto_note']
    assert '4' in note  # Rastergröße UND Schwelle sind hier zufällig beide 4
    assert 'tail_ratio' in note and 'value_at_risk' in note and 'cond_value_at_risk' in note


def test_identical_grid_size_gives_identical_resolution_regardless_of_shape(repo, session, monkeypatch):
    """Zwei verschieden geformte Raster gleicher Kombinationszahl lösen identisch auf.

    Steht für die Ticket-Anforderung, dass Einzel- und Multiparameterlauf gleicher
    Rastergröße und Auswahl sich identisch verhalten: die Auflösung hängt hier
    ausschließlich an n_combinations (via count_total_combos), nicht am Weg dorthin.
    """
    import user_data.utils.metrics.metric_sets as metric_sets
    monkeypatch.setattr(metric_sets, 'AUTO_FULL_COMBINATION_THRESHOLD', 6)

    run_id_a = repo.create_backtest_run(
        backtest_config=_config(),
        indicators_config=_stop_sweep_indicators(6, key='tp_stop'),
    )
    run_id_b = repo.create_backtest_run(
        backtest_config=_config(),
        indicators_config=_stop_sweep_indicators(6, key='sl_stop'),
    )
    session.rollback()

    bc_a = _run_row(session, run_id_a).backtest_config_json
    bc_b = _run_row(session, run_id_b).backtest_config_json
    assert bc_a['metrics_resolved'] == bc_b['metrics_resolved']
    # Die Notiz hängt nur an n_combinations/Schwelle, nicht an der Rasterform (tp_stop
    # vs. sl_stop) — beide Läufe erzeugen denselben Text.
    assert bc_a['metrics_auto_note'] == bc_b['metrics_auto_note']
    assert set(bc_a['metrics_resolved']) == CORE_GROUPS


def test_stale_metrics_auto_note_from_a_copied_config_is_cleared(repo, session, monkeypatch):
    """Walk-Forward/Leaderboard-Reruns kopieren backtest_config_json 1:1 vom Eltern-Run
    (siehe api_backtest.py:start_walk_forward) — inklusive einer dort gesetzten
    'metrics_auto_note'. Liegt der neue Lauf diesmal unter der Schwelle, darf die alte
    Notiz nicht stehen bleiben, obwohl gar nicht gekürzt wurde.
    """
    import user_data.utils.metrics.metric_sets as metric_sets
    monkeypatch.setattr(metric_sets, 'AUTO_FULL_COMBINATION_THRESHOLD', 100)

    # Simuliert eine 1:1-Kopie von backtest_config_json eines Eltern-Runs, der gekürzt hatte.
    stale_config = _config()
    stale_config['metrics_auto_note'] = 'Metrik-Auswahl auto: 500 Kombinationen ≥ Schwelle 100 — veraltet.'

    run_id = repo.create_backtest_run(
        backtest_config=stale_config,
        indicators_config=_stop_sweep_indicators(3),  # 3 < 100 -> diesmal keine Kürzung
    )
    session.rollback()

    bc = _run_row(session, run_id).backtest_config_json
    assert set(bc['metrics_resolved']) == ALL_GROUPS
    assert 'metrics_auto_note' not in bc


def test_assess_run_usability_appends_metrics_note_without_replacing_base_note(repo, session):
    """Eine übergebene Metrik-Notiz hängt an, ersetzt nicht die Verwertbarkeits-Note."""
    run_id = repo.create_backtest_run(
        backtest_config=_config(),
        indicators_config=_stop_sweep_indicators(1),
    )
    session.rollback()
    # Mindestens ein Result mit einem Trade, sonst greift der 'no_signals'-Zweig.
    session.execute(text(
        "INSERT INTO backtest_results (run_id, params_hash, actual_params_json, "
        "resolved_config_json, total_trades) VALUES (:run_id, 'hash-1', '{}', '{}', 3)"
    ), {'run_id': run_id})
    session.commit()

    verdict = repo.assess_run_usability(run_id, warmup=None, metrics_note='Zusatz-Hinweis.')
    session.rollback()

    assert verdict['usability'] == 'usable'
    assert verdict['note'].startswith('Verwertbar:')
    assert verdict['note'].endswith('Zusatz-Hinweis.')

    row = session.execute(
        text('SELECT usability_note FROM backtest_runs WHERE id = :id'), {'id': run_id}
    ).fetchone()
    assert row.usability_note == verdict['note']


def test_assess_run_usability_note_unchanged_without_metrics_note(repo, session):
    """Ohne Metrik-Notiz bleibt usability_note ausschließlich die Verwertbarkeits-Note."""
    run_id = repo.create_backtest_run(
        backtest_config=_config(metrics='voll'),
        indicators_config=_stop_sweep_indicators(1),
    )
    session.rollback()
    session.execute(text(
        "INSERT INTO backtest_results (run_id, params_hash, actual_params_json, "
        "resolved_config_json, total_trades) VALUES (:run_id, 'hash-1', '{}', '{}', 3)"
    ), {'run_id': run_id})
    session.commit()

    verdict = repo.assess_run_usability(run_id, warmup=None)
    session.rollback()

    assert verdict['note'] == 'Verwertbar: 1 Kombinationen, 3 Trades insgesamt.'


def test_shortened_auto_run_states_reason_and_grid_size_in_usability_note(
    repo, session, monkeypatch
):
    """Die ganze Kette: 'auto' kürzt -> usability_note nennt Grund UND Rastergröße.

    Bisher waren die beiden Hälften getrennt geprüft (Notiz-Text im
    backtest_config_json, Anhängen in assess_run_usability). Hier läuft der Weg zusammen,
    den der Worker geht (`worker_tasks.run_backtest_job`: Notiz aus
    `backtest_config_json['metrics_auto_note']` in `assess_run_usability`), und die
    Rastergröße ist bewusst von der Schwelle verschieden — sonst belegt ein Treffer im
    Text nicht, dass beide Zahlen darin stehen.
    """
    import user_data.utils.metrics.metric_sets as metric_sets
    monkeypatch.setattr(metric_sets, 'AUTO_FULL_COMBINATION_THRESHOLD', 5)

    run_id = repo.create_backtest_run(
        backtest_config=_config(),  # kein 'metrics' -> auto
        indicators_config=_stop_sweep_indicators(12),  # 12 >= 5 -> Kürzung
    )
    session.rollback()
    session.execute(text(
        "INSERT INTO backtest_results (run_id, params_hash, actual_params_json, "
        "resolved_config_json, total_trades) VALUES (:run_id, 'hash-1', '{}', '{}', 7)"
    ), {'run_id': run_id})
    session.commit()

    bc = _run_row(session, run_id).backtest_config_json
    assert set(bc['metrics_resolved']) == CORE_GROUPS

    repo.assess_run_usability(
        run_id, warmup=None, metrics_note=bc.get('metrics_auto_note')
    )
    session.rollback()

    note = session.execute(
        text('SELECT usability_note FROM backtest_runs WHERE id = :id'), {'id': run_id}
    ).fetchone().usability_note

    # Verwertbarkeits-Bewertung bleibt vorne, die Metrik-Selbstauskunft hängt an.
    assert note.startswith('Verwertbar: 1 Kombinationen, 7 Trades insgesamt.')
    assert '12 Kombinationen' in note      # Rastergröße
    assert 'Schwelle 5' in note            # Grund: Rastergröße >= Schwelle
    assert 'tail_risk übersprungen' in note
    for field in ('tail_ratio', 'value_at_risk', 'cond_value_at_risk'):
        assert field in note

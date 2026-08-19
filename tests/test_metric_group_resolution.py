"""Tests der Metrik-Gruppen-Auflösung (`user_data/utils/metrics/metric_sets.py`).

Die Gruppen-Zuordnung ist die einzige Quelle für die Frage „welche Kennzahl gehört
wohin". Geprüft wird hier das Verhalten, auf das sich Runner und Persistenz
verlassen:

- Die Stufen `kern`/`voll` lösen zu festen Gruppenmengen auf.
- Pflichtgruppen sind in **keiner** Aufruf-Form abwählbar — auch nicht über eine
  leere Liste.
- Ein unbekannter Gruppen-Key oder eine unbekannte Stufe führt zum Fehler, nicht zu
  stillem Übergehen.
- Die Feldliste deckt genau die 46 Kennzahl-Spalten von BacktestResult ab.
"""

import pytest

from user_data.utils.database.models import BacktestResult
from user_data.utils.metrics.metric_sets import (
    ALL_GROUPS,
    ALL_METRIC_FIELDS,
    AUTO_FULL_COMBINATION_THRESHOLD,
    CORE_GROUPS,
    METRIC_GROUPS,
    OPTIONAL_GROUPS,
    REQUIRED_GROUPS,
    STAGE_AUTO,
    STAGE_CORE,
    STAGE_FULL,
    fields_for_groups,
    normalize_groups,
    resolve_metric_groups,
    skipped_fields,
)

# Spalten von BacktestResult, die keine Kennzahl aus _extract_metrics sind.
_NON_METRIC_COLUMNS = {
    'id', 'run_id', 'params_hash', 'actual_params_json', 'resolved_config_json',
    'deflated_sharpe_ratio', 'spec_runner_version', 'is_favorite', 'is_doc_favorite',
    'best_criteria_json', 'iteration_id', 'full_config_snapshot_json',
    'created_at', 'updated_at',
}


def test_field_list_covers_every_metric_column_of_the_result_table():
    """Die Gruppen decken genau die Kennzahl-Spalten von BacktestResult ab.

    Fällt der Test, ist eine Spalte hinzugekommen, ohne dass sie einer Gruppe
    zugeordnet wurde — dann schriebe die Persistenz sie nicht mehr mit.
    """
    table_columns = {column.name for column in BacktestResult.__table__.columns}
    metric_columns = table_columns - _NON_METRIC_COLUMNS

    assert set(ALL_METRIC_FIELDS) == metric_columns
    assert len(ALL_METRIC_FIELDS) == 46
    assert len(set(ALL_METRIC_FIELDS)) == 46, 'Ein Feld steht in zwei Gruppen'


def test_required_groups_are_exactly_the_five_mandatory_ones():
    """Pflicht sind die fünf Gruppen, die den DSR-Nachlauf und das Basisergebnis tragen."""
    assert REQUIRED_GROUPS == {'scope', 'returns', 'trades', 'risk_ratios', 'moments'}
    assert OPTIONAL_GROUPS == ALL_GROUPS - REQUIRED_GROUPS
    assert set(METRIC_GROUPS) == ALL_GROUPS


def test_deflated_sharpe_inputs_are_covered_by_required_groups():
    """Die vier Eingänge des DSR-Nachlaufs stehen in Pflichtgruppen.

    `_calculate_deflated_sharpe` liest `sharpe_ratio`, `skew`, `kurtosis` und
    `bar_count` aus der Datenbank. Wären sie abwählbar, fiele die Deflated Sharpe
    Ratio bei schmaler Auswahl aus.
    """
    required_fields = fields_for_groups([])
    for field in ('sharpe_ratio', 'skew', 'kurtosis', 'bar_count'):
        assert field in required_fields


def test_stage_voll_selects_every_group():
    """`voll` rechnet alles."""
    assert resolve_metric_groups(STAGE_FULL) == ALL_GROUPS
    assert set(fields_for_groups(resolve_metric_groups(STAGE_FULL))) == set(ALL_METRIC_FIELDS)
    assert skipped_fields(resolve_metric_groups(STAGE_FULL)) == ()


def test_stage_kern_drops_only_the_three_expensive_metrics():
    """`kern` ist „alles außer `tail_risk`" — und sonst nichts."""
    groups = resolve_metric_groups(STAGE_CORE)

    assert groups == CORE_GROUPS
    assert groups == ALL_GROUPS - {'tail_risk'}
    assert skipped_fields(groups) == ('tail_ratio', 'value_at_risk', 'cond_value_at_risk')


def test_group_list_adds_the_chosen_groups_to_the_mandatory_ones():
    """Eine Liste benennt zusätzlich zu den Pflichtgruppen zu rechnende Gruppen."""
    groups = resolve_metric_groups(['tail_risk', 'drawdown'])

    assert groups == REQUIRED_GROUPS | {'tail_risk', 'drawdown'}
    assert 'trade_quality' not in groups
    assert 'sqn' in skipped_fields(groups)


def test_empty_group_list_still_computes_the_mandatory_groups():
    """Die leere Liste heißt „nur Pflichtgruppen", nicht „gar nichts"."""
    groups = resolve_metric_groups([])

    assert groups == REQUIRED_GROUPS
    assert set(skipped_fields(groups)) == set(ALL_METRIC_FIELDS) - set(fields_for_groups([]))


def test_mandatory_groups_cannot_be_switched_off_in_any_call_form():
    """Keine Aufruf-Form entfernt eine Pflichtgruppe."""
    for selection in (STAGE_CORE, STAGE_FULL, [], ['tail_risk'], list(OPTIONAL_GROUPS)):
        assert REQUIRED_GROUPS <= resolve_metric_groups(selection)


def test_listing_a_mandatory_group_is_allowed_and_changes_nothing():
    """Eine Pflichtgruppe in der Liste ist kein Fehler — sie ist ohnehin dabei.

    Damit ist die Auflösung wiederholbar: eine bereits aufgelöste Gruppenmenge darf
    erneut durch resolve_metric_groups laufen, ohne sich zu verändern.
    """
    once = resolve_metric_groups(['drawdown'])
    twice = resolve_metric_groups(sorted(once))

    assert once == twice


def test_unknown_group_key_raises():
    """Ein unbekannter Gruppen-Key wird abgewiesen, nicht still ignoriert."""
    with pytest.raises(ValueError, match='Unbekannte Metrik-Gruppe'):
        resolve_metric_groups(['drawdown', 'gibtsnicht'])

    with pytest.raises(ValueError, match='Unbekannte Metrik-Gruppe'):
        normalize_groups({'gibtsnicht'})

    with pytest.raises(ValueError, match='Unbekannte Metrik-Gruppe'):
        fields_for_groups(['gibtsnicht'])


def test_unknown_stage_raises():
    """Eine unbekannte Stufe wird abgewiesen."""
    with pytest.raises(ValueError, match='Unbekannte Metrik-Auswahl'):
        resolve_metric_groups('halb')

    # Auch die Schreibweise ist verbindlich — kein tolerantes Umbiegen.
    with pytest.raises(ValueError, match='Unbekannte Metrik-Auswahl'):
        resolve_metric_groups('KERN')


def test_stage_name_passed_as_group_list_raises():
    """Eine Stufe gehört nicht in die Gruppen-Liste; die Zeichenkette wird nicht zerlegt."""
    with pytest.raises(ValueError, match='Zeichenkette'):
        normalize_groups(STAGE_CORE)


def test_auto_computes_everything_below_the_threshold():
    """Unterhalb der Schwelle rechnet `auto` voll."""
    assert resolve_metric_groups(STAGE_AUTO, AUTO_FULL_COMBINATION_THRESHOLD - 1) == ALL_GROUPS
    assert resolve_metric_groups(None, 1) == ALL_GROUPS


def test_auto_drops_tail_risk_from_the_threshold_on():
    """Ab der Schwelle rechnet `auto` nur noch `kern`."""
    assert resolve_metric_groups(STAGE_AUTO, AUTO_FULL_COMBINATION_THRESHOLD) == CORE_GROUPS
    assert resolve_metric_groups(
        STAGE_AUTO, AUTO_FULL_COMBINATION_THRESHOLD * 10
    ) == CORE_GROUPS


def test_auto_without_grid_size_raises():
    """`auto` ohne Rastergröße ist nicht entscheidbar — es wird nicht geraten."""
    with pytest.raises(ValueError, match='Rastergröße'):
        resolve_metric_groups(STAGE_AUTO)

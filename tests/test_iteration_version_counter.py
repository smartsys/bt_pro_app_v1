"""Tests für next_iteration_version — fortlaufende Iterations-Nummern pro Konzept.

Prüft:
- Fortlaufende Vergabe ab 1 pro Konzept (jeder Aufruf zählt den High-Water-Mark hoch).
- Zähler ist pro Konzept isoliert.
- High-Water-Mark: Nach Löschen der höchsten Iteration wird ihre Nummer NICHT
  wiederverwendet — der Zähler sinkt nie.

Nutzt die PostgreSQL-Test-DB (session-Fixture aus conftest.py), weil
next_iteration_version ein atomares UPDATE ... RETURNING verwendet.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from user_data.utils.database.repository_strategies import (
    create_concept,
    create_iteration,
    delete_iteration,
    next_iteration_version,
)


@pytest.fixture(scope='function')
def concept(session):
    """Test-Konzept mit Startzähler 0."""
    return create_concept(
        session,
        slug='counter-test-concept',
        name='Counter Test',
        status='active',
        created_by='pytest',
    )


def test_first_version_is_one(session, concept):
    """Erster Aufruf liefert 1 (Zähler-Startwert 0 + 1)."""
    assert next_iteration_version(session, concept.id) == 1


def test_sequential_versions(session, concept):
    """Aufeinanderfolgende Aufrufe liefern 1, 2, 3, ..."""
    assigned = [next_iteration_version(session, concept.id) for _ in range(5)]
    assert assigned == [1, 2, 3, 4, 5]


def test_counter_is_per_concept(session):
    """Zwei Konzepte zählen unabhängig voneinander ab 1."""
    c1 = create_concept(session, slug='counter-c1', name='C1', status='active')
    c2 = create_concept(session, slug='counter-c2', name='C2', status='active')

    assert next_iteration_version(session, c1.id) == 1
    assert next_iteration_version(session, c1.id) == 2
    # c2 startet unbeeinflusst von c1 bei 1
    assert next_iteration_version(session, c2.id) == 1


def test_high_water_mark_no_reuse_after_delete(session, concept):
    """Nach Löschen der höchsten Iteration wird die Nummer NICHT wiederverwendet."""
    v1 = next_iteration_version(session, concept.id)
    v2 = next_iteration_version(session, concept.id)
    assert (v1, v2) == (1, 2)

    it1 = create_iteration(session, concept_id=concept.id, version=v1, status='active')
    it2 = create_iteration(session, concept_id=concept.id, version=v2, status='active')

    # Höchste Iteration (Version 2) löschen
    assert delete_iteration(session, it2.id) is True

    # Nächste Nummer ist 3 — die freigewordene 2 wird NICHT recycelt
    assert next_iteration_version(session, concept.id) == 3


def test_unknown_concept_raises(session):
    """Unbekannte concept_id wirft ValueError."""
    with pytest.raises(ValueError, match='nicht gefunden'):
        next_iteration_version(session, 999999)

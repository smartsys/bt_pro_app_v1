"""Tests für Vault-Pfade und Notiz-Inhalte (services.api.utils.obsidian_paths/-notes)."""
import pytest

from services.api.utils.obsidian_notes import (
    build_concept_note,
    build_iteration_note,
    build_status_note,
)
from services.api.utils.obsidian_paths import (
    concept_dir,
    concept_md_path,
    iteration_md_path,
    strategies_base_rel,
)


@pytest.fixture
def vault(monkeypatch, tmp_path):
    """Setzt OBSIDIAN_VAULT_PATH auf ein temporäres Verzeichnis."""
    monkeypatch.setenv('OBSIDIAN_VAULT_PATH', str(tmp_path))
    return tmp_path


def parse_frontmatter(md: str) -> dict:
    """Liest die flachen Top-Level-Schlüssel des YAML-Frontmatter.

    Verschachtelte Blöcke (z.B. metrics) werden übersprungen.

    Args:
        md: Vollständiger Markdown-Inhalt mit Frontmatter.

    Returns:
        Dict der Top-Level-Schlüssel auf ihre Rohwerte (Strings).
    """
    assert md.startswith('---\n')
    body = md.split('---\n', 2)[1]
    result = {}
    for line in body.splitlines():
        if not line or line.startswith((' ', '#')):
            continue
        key, _, value = line.partition(':')
        result[key.strip()] = value.strip()
    return result


class TestVaultPaths:
    """Pfad-Ableitung folgt der Vault-Konvention 30_Trading/strategies/<slug>/vbt."""

    def test_strategies_basis_ohne_welten_segment(self):
        assert strategies_base_rel() == '30_Trading/strategies'

    def test_konzept_ordner_liegt_ueber_der_welt(self, vault):
        assert concept_dir('vwma') == vault / '30_Trading' / 'strategies' / 'vwma'

    def test_concept_md_heisst_slug_concept(self, vault):
        assert concept_md_path('vwma').name == 'vwma-concept.md'

    def test_iteration_md_liegt_im_versions_ordner_der_welt(self, vault):
        path = iteration_md_path('vwma', 9)
        assert path == concept_dir('vwma') / 'vbt' / 'iterations' / '9' / 'vwma-9.md'


class TestConceptNote:
    """Konzept-Notiz folgt _templates/strategy-concept.md."""

    def test_frontmatter_schluessel_entsprechen_template(self):
        fm = parse_frontmatter(build_concept_note('vwma', 'VWMA', today='2026-08-03'))
        assert fm['type'] == 'strategy-concept'
        assert fm['slug'] == 'vwma'
        assert fm['status'] == 'idea'
        assert fm['created'] == '2026-08-03'
        assert fm['updated'] == '2026-08-03'
        assert fm['tags'] == '[trading]'

    def test_kein_veraltetes_concept_id_feld(self):
        fm = parse_frontmatter(build_concept_note('vwma', 'VWMA'))
        assert 'concept_id' not in fm
        assert 'created_at' not in fm

    def test_body_enthaelt_template_abschnitte(self):
        md = build_concept_note('vwma', 'VWMA')
        for heading in ('# VWMA — Konzept', '## Mechanik', '## Hypothetischer Edge', '## Ziel-Regime'):
            assert heading in md


class TestStatusNote:
    """status.md folgt _templates/status.md."""

    def test_frontmatter_und_verweis_auf_konzept(self):
        md = build_status_note('vwma', 'VWMA', today='2026-08-03')
        fm = parse_frontmatter(md)
        assert fm['type'] == 'strategy-status'
        assert fm['strategy'] == 'vwma'
        assert fm['updated'] == '2026-08-03'
        assert '[[vwma-concept]]' in md

    def test_body_enthaelt_pflicht_abschnitte(self):
        md = build_status_note('vwma', 'VWMA')
        for heading in ('## Aktueller Stand', '## Beste Iteration', '## Backlog', '## Nicht anfassen'):
            assert heading in md


class TestIterationNote:
    """Iterations-Notiz folgt _templates/iteration.md."""

    def test_frontmatter_befuellt_db_felder(self):
        md = build_iteration_note(
            slug='vwma',
            version=9,
            version_name='Einfacher Pullback Crossover',
            iteration_id=12,
            concept_id=2,
            parent_iteration_id=10,
            parent_version=7,
            today='2026-08-03',
        )
        fm = parse_frontmatter(md)
        assert fm['type'] == 'strategy-iteration'
        assert fm['iteration_id'] == '12'
        assert fm['concept_id'] == '2'
        assert fm['concept_slug'] == 'vwma'
        assert fm['version'] == '9'
        assert fm['version_name'] == '"Einfacher Pullback Crossover"'
        assert fm['parent_iteration_id'] == '10'
        assert fm['status'] == 'defined'
        assert fm['workflow_state'] == 'drafted'
        assert fm['created_at'] == '2026-08-03'
        assert fm['updated'] == '2026-08-03'

    def test_keine_template_fremden_felder(self):
        md = build_iteration_note(
            slug='vwma', version=9, version_name=None, iteration_id=12,
            concept_id=2, parent_iteration_id=None, parent_version=None,
        )
        fm = parse_frontmatter(md)
        assert 'iteration' not in fm
        assert 'archetype' not in fm

    def test_ohne_parent_ist_basis_eine_baseline(self):
        md = build_iteration_note(
            slug='vwma', version=1, version_name=None, iteration_id=1,
            concept_id=2, parent_iteration_id=None, parent_version=None,
        )
        fm = parse_frontmatter(md)
        assert fm['parent_iteration_id'] == 'null'
        assert fm['version_name'] == '""'
        assert '_keine (Baseline)_' in md

    def test_mit_parent_wird_wikilink_gesetzt(self):
        md = build_iteration_note(
            slug='vwma', version=9, version_name=None, iteration_id=12,
            concept_id=2, parent_iteration_id=10, parent_version=7,
        )
        assert '[[vwma-7]]' in md

    def test_titel_nutzt_version_und_label(self):
        md = build_iteration_note(
            slug='vwma', version=9, version_name='Crossover', iteration_id=12,
            concept_id=2, parent_iteration_id=None, parent_version=None,
        )
        assert '# 9 — Crossover' in md

    def test_version_name_mit_anfuehrungszeichen_wird_escaped(self):
        md = build_iteration_note(
            slug='vwma', version=9, version_name='Test "A"', iteration_id=12,
            concept_id=2, parent_iteration_id=None, parent_version=None,
        )
        assert 'version_name: "Test \\"A\\""' in md

    def test_body_enthaelt_template_abschnitte(self):
        md = build_iteration_note(
            slug='vwma', version=9, version_name=None, iteration_id=12,
            concept_id=2, parent_iteration_id=None, parent_version=None,
        )
        for heading in ('## Hypothese', '## Setup', '## Run-Journal', '## Ergebnisse', '## Verdict'):
            assert heading in md

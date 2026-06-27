"""Tests für Ticket 16 — Obsidian-Pfad-Konvention deterministisch + vault-create Endpoints.

Abdeckung:
- obsidian_paths.py: normalize_slug, normalize_version, alle Pfad-Funktionen
- vault-create Konzept-Endpoint: Erst-Anlage, Idempotenz
- vault-create Iterations-Endpoint: Erst-Anlage, Idempotenz
- Frontmatter-Korrektheit

Tests laufen gegen SQLite (test_session aus conftest.py) + pytest tmp_path für Filesystem.
Kein Live-Container nötig.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from services.api.utils.obsidian_paths import (
    concept_dir,
    concept_md_path,
    iteration_dir,
    iteration_md_path,
    normalize_slug,
    normalize_version,
    vault_root,
)
from user_data.utils.database.repository_strategies import create_concept, create_iteration


# ============================================================================
# Unit-Tests: obsidian_paths.py
# ============================================================================

class TestNormalizeSlug:
    """Tests für normalize_slug."""

    def test_already_normalized(self):
        assert normalize_slug('teststrategie-dws') == 'teststrategie-dws'

    def test_uppercase(self):
        assert normalize_slug('TESTSTRATEGIE-DWS') == 'teststrategie-dws'

    def test_spaces_to_dashes(self):
        assert normalize_slug('TESTSTRATEGIE DWS') == 'teststrategie-dws'

    def test_underscores_to_dashes(self):
        assert normalize_slug('teststrategie_dws') == 'teststrategie-dws'

    def test_mixed(self):
        assert normalize_slug('TESTSTRATEGIE_DWS Test') == 'teststrategie-dws-test'

    def test_multiple_dashes_collapsed(self):
        assert normalize_slug('teststrategie--dws') == 'teststrategie-dws'

    def test_leading_trailing_stripped(self):
        assert normalize_slug('  -teststrategie-dws- ') == 'teststrategie-dws'

    def test_special_chars_removed(self):
        assert normalize_slug('teststrategie#dws!') == 'teststrategiedws'

    def test_numbers_kept(self):
        assert normalize_slug('strategy-01') == 'strategy-01'


class TestNormalizeVersion:
    """Tests für normalize_version."""

    def test_already_normalized(self):
        assert normalize_version('v2.0') == 'v2.0'

    def test_uppercase(self):
        assert normalize_version('V2.0') == 'v2.0'

    def test_spaces_to_dashes(self):
        assert normalize_version('v2 0') == 'v2-0'

    def test_underscores_kept(self):
        assert normalize_version('dyn-v0.31o_robustness-bestvariante') == 'dyn-v0.31o_robustness-bestvariante'

    def test_dots_kept(self):
        assert normalize_version('v0.31') == 'v0.31'

    def test_special_chars_removed(self):
        assert normalize_version('v2.0!#') == 'v2.0'


class TestPathFunctions:
    """Tests für Pfad-Ableitungsfunktionen."""

    def test_concept_dir(self, tmp_path):
        with patch.dict(os.environ, {'OBSIDIAN_VAULT_PATH': str(tmp_path)}):
            result = concept_dir('teststrategie-dws')
            assert result == tmp_path / '30_Trading' / 'strategies' / 'teststrategie-dws'

    def test_concept_md_path(self, tmp_path):
        with patch.dict(os.environ, {'OBSIDIAN_VAULT_PATH': str(tmp_path)}):
            result = concept_md_path('teststrategie-dws')
            assert result == tmp_path / '30_Trading' / 'strategies' / 'teststrategie-dws' / 'teststrategie-dws-concept.md'

    def test_iteration_dir(self, tmp_path):
        with patch.dict(os.environ, {'OBSIDIAN_VAULT_PATH': str(tmp_path)}):
            result = iteration_dir('teststrategie-dws', 'v2.0')
            assert result == tmp_path / '30_Trading' / 'strategies' / 'teststrategie-dws' / 'iterations' / 'v2.0'

    def test_iteration_md_path(self, tmp_path):
        with patch.dict(os.environ, {'OBSIDIAN_VAULT_PATH': str(tmp_path)}):
            result = iteration_md_path('teststrategie-dws', 'v2.0')
            # Dateiname-Konvention: {slug}-{version}.md (sprechender Name mit Slug-Präfix)
            assert result == (
                tmp_path / '30_Trading' / 'strategies' / 'teststrategie-dws' / 'iterations' / 'v2.0' / 'teststrategie-dws-v2.0.md'
            )

    def test_iteration_md_path_complex_version(self, tmp_path):
        """Komplexe Version mit Punkten und Unterstrichen."""
        with patch.dict(os.environ, {'OBSIDIAN_VAULT_PATH': str(tmp_path)}):
            version = 'dyn-v0.31o_robustness-bestvariante'
            result = iteration_md_path('teststrategie-dws', version)
            assert result == (
                tmp_path / '30_Trading' / 'strategies' / 'teststrategie-dws' / 'iterations' / version / f'teststrategie-dws-{version}.md'
            )

    def test_vault_root_default(self):
        """Standard-Vault-Root wenn OBSIDIAN_VAULT_PATH nicht gesetzt."""
        env = {k: v for k, v in os.environ.items() if k != 'OBSIDIAN_VAULT_PATH'}
        with patch.dict(os.environ, env, clear=True):
            result = vault_root()
            assert result == Path('/obsidian_vault')

    def test_vault_root_from_env(self, tmp_path):
        with patch.dict(os.environ, {'OBSIDIAN_VAULT_PATH': str(tmp_path)}):
            result = vault_root()
            assert result == tmp_path


# ============================================================================
# API-Tests: vault-create Endpoints (gegen SQLite + tmp_path)
# ============================================================================

@pytest.fixture
def strategy_client(tmp_path, monkeypatch):
    """FastAPI TestClient mit nur dem strategy-Router, File-basierter SQLite-DB und gemocktem Vault-Root.

    Nutzt minimale Test-App ohne rq/redis-Abhängigkeiten (analog zu test_api_strategy.py).
    File-basierte SQLite-DB (nicht In-Memory) damit TestClient (separater Thread) die Daten sieht.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient as _TC
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import user_data.utils.database.db as db_module
    from user_data.utils.database.models import Base

    monkeypatch.setenv('OBSIDIAN_VAULT_PATH', str(tmp_path))

    # File-basierte SQLite-DB mit eindeutigem Pfad pro Fixture-Instanz
    import uuid
    db_file = tmp_path / f'test_t16_{uuid.uuid4().hex[:8]}.db'
    db_url = f'sqlite:///{db_file}'
    engine = create_engine(
        db_url,
        connect_args={'check_same_thread': False},
        echo=False,
    )
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, autoflush=True)

    def mock_get_session():
        return SessionFactory()

    # Modul-Level-Import in api_strategy patchen (nicht db_module — die Kopie dort ist lokal)
    import services.api.routes.api_strategy as api_strategy_module
    monkeypatch.setattr(api_strategy_module, 'get_session', mock_get_session)

    from services.api.routes.api_strategy import router as strategy_router
    test_app = FastAPI()
    test_app.include_router(strategy_router)

    with _TC(test_app) as client:
        yield client

    engine.dispose()


@pytest.fixture
def sample_concept(strategy_client):
    """Test-Konzept via API anlegen."""
    response = strategy_client.post('/api/strategy/concepts', json={
        'slug': 'test-slug-16',
        'name': 'Test Strategie 16',
        'status': 'active',
    })
    assert response.status_code == 200, response.text
    return response.json()['data']


@pytest.fixture
def sample_iteration(strategy_client, sample_concept):
    """Test-Iteration via API anlegen.

    version wird server-seitig als fortlaufende Integer-Nummer vergeben (erste = 1).
    """
    response = strategy_client.post('/api/strategy/iterations', json={
        'concept_id': sample_concept['id'],
        'type': 'generic',
        'status': 'active',
    })
    assert response.status_code == 200, response.text
    return response.json()['data']


class TestConceptVaultCreate:
    """Tests für POST /api/strategy/concepts/{id}/vault-create."""

    def test_create_new(self, strategy_client, tmp_path, sample_concept):
        """Erst-Anlage legt Datei mit Frontmatter an."""
        response = strategy_client.post(f'/api/strategy/concepts/{sample_concept["id"]}/vault-create')
        assert response.status_code == 200
        data = response.json()
        assert data['error'] is None
        assert data['data']['created'] is True
        assert data['data']['exists'] is True

        # Datei tatsächlich vorhanden
        md_path = tmp_path / '30_Trading' / 'strategies' / 'test-slug-16' / 'test-slug-16-concept.md'
        assert md_path.exists()

        # Frontmatter korrekt
        content = md_path.read_text(encoding='utf-8')
        assert 'type: strategy-concept' in content
        assert f'concept_id: {sample_concept["id"]}' in content
        assert 'slug: test-slug-16' in content
        assert 'name: Test Strategie 16' in content

    def test_idempotent_second_call(self, strategy_client, tmp_path, sample_concept):
        """Zweiter Aufruf gibt created: false, exists: true zurück ohne Datei zu überschreiben."""
        # Erster Call
        strategy_client.post(f'/api/strategy/concepts/{sample_concept["id"]}/vault-create')

        # Datei manuell ändern um sicherzustellen, dass sie nicht überschrieben wird
        md_path = tmp_path / '30_Trading' / 'strategies' / 'test-slug-16' / 'test-slug-16-concept.md'
        md_path.write_text('# Eigener Inhalt\n', encoding='utf-8')

        # Zweiter Call
        response = strategy_client.post(f'/api/strategy/concepts/{sample_concept["id"]}/vault-create')
        assert response.status_code == 200
        data = response.json()
        assert data['data']['created'] is False
        assert data['data']['exists'] is True

        # Datei unverändert
        assert md_path.read_text(encoding='utf-8') == '# Eigener Inhalt\n'

    def test_not_found(self, strategy_client, tmp_path):
        """404 für unbekannte Konzept-ID."""
        response = strategy_client.post('/api/strategy/concepts/99999/vault-create')
        assert response.status_code == 404


class TestIterationVaultCreate:
    """Tests für POST /api/strategy/iterations/{id}/vault-create."""

    def test_create_new(self, strategy_client, tmp_path, sample_iteration, sample_concept):
        """Erst-Anlage legt Ordner + Datei mit Frontmatter an."""
        response = strategy_client.post(f'/api/strategy/iterations/{sample_iteration["id"]}/vault-create')
        assert response.status_code == 200
        data = response.json()
        assert data['error'] is None
        assert data['data']['created'] is True
        assert data['data']['exists'] is True

        # GEÄNDERT: version ist eine Integer-Nummer (erste Iteration = 1).
        # Pfad-Schema gemäß obsidian_paths.iteration_md_path: iterations/{version}/{slug}-{version}.md
        version = sample_iteration['version']
        it_path = (
            tmp_path / '30_Trading' / 'strategies' / 'test-slug-16'
            / 'iterations' / str(version) / f'test-slug-16-{version}.md'
        )
        assert it_path.exists()

        # Frontmatter korrekt
        content = it_path.read_text(encoding='utf-8')
        assert 'type: strategy-iteration' in content
        assert f'iteration_id: {sample_iteration["id"]}' in content
        assert f'concept_id: {sample_concept["id"]}' in content
        assert 'concept_slug: test-slug-16' in content
        assert f'version: {version}' in content

        # result.md NICHT vorhanden
        result_path = (
            tmp_path / '30_Trading' / 'strategies' / 'test-slug-16'
            / 'iterations' / str(version) / 'result.md'
        )
        assert not result_path.exists()

    def test_idempotent_second_call(self, strategy_client, tmp_path, sample_iteration):
        """Zweiter Aufruf gibt created: false, exists: true zurück."""
        strategy_client.post(f'/api/strategy/iterations/{sample_iteration["id"]}/vault-create')

        response = strategy_client.post(f'/api/strategy/iterations/{sample_iteration["id"]}/vault-create')
        assert response.status_code == 200
        data = response.json()
        assert data['data']['created'] is False
        assert data['data']['exists'] is True

    def test_not_found(self, strategy_client, tmp_path):
        """404 für unbekannte Iterations-ID."""
        response = strategy_client.post('/api/strategy/iterations/99999/vault-create')
        assert response.status_code == 404


# ============================================================================
# Tests: vault_exists in GET-Responses
# ============================================================================

class TestVaultExistsInGetResponses:
    """vault_exists-Feld in GET-Responses prüfen."""

    def test_concept_list_has_vault_exists(self, strategy_client, sample_concept):
        """GET /api/strategy/concepts liefert vault_exists als bool."""
        response = strategy_client.get('/api/strategy/concepts')
        assert response.status_code == 200
        items = response.json()['data']['items']
        assert len(items) > 0
        item = next(i for i in items if i['id'] == sample_concept['id'])
        assert isinstance(item['vault_exists'], bool)

    def test_concept_detail_has_vault_exists(self, strategy_client, sample_concept):
        """GET /api/strategy/concepts/{id} liefert vault_exists als bool."""
        response = strategy_client.get(f'/api/strategy/concepts/{sample_concept["id"]}')
        assert response.status_code == 200
        assert isinstance(response.json()['data']['vault_exists'], bool)

    def test_iteration_list_has_vault_exists(self, strategy_client, sample_iteration):
        """GET /api/strategy/iterations liefert vault_exists als bool."""
        response = strategy_client.get('/api/strategy/iterations')
        assert response.status_code == 200
        items = response.json()['data']['items']
        assert len(items) > 0
        item = next(i for i in items if i['id'] == sample_iteration['id'])
        assert isinstance(item['vault_exists'], bool)

    def test_iteration_detail_has_vault_exists(self, strategy_client, sample_iteration):
        """GET /api/strategy/iterations/{id} liefert vault_exists als bool."""
        response = strategy_client.get(f'/api/strategy/iterations/{sample_iteration["id"]}')
        assert response.status_code == 200
        assert isinstance(response.json()['data']['vault_exists'], bool)


# ============================================================================
# Tests: Slug-Normalisierung bei Create/Update
# ============================================================================

class TestSlugNormalization:
    """Slug-Auto-Normalisierung beim Speichern."""

    def test_create_normalizes_slug(self, strategy_client):
        """POST /api/strategy/concepts normalisiert den Slug."""
        response = strategy_client.post('/api/strategy/concepts', json={
            'slug': 'TESTSTRATEGIE_Test',
            'name': 'Test',
            'status': 'active',
        })
        assert response.status_code == 200
        assert response.json()['data']['slug'] == 'teststrategie-test'

    def test_update_normalizes_slug(self, strategy_client, sample_concept):
        """PUT /api/strategy/concepts/{id} normalisiert den Slug."""
        response = strategy_client.put(f'/api/strategy/concepts/{sample_concept["id"]}', json={
            'slug': 'TESTSTRATEGIE Updated',
        })
        assert response.status_code == 200
        assert response.json()['data']['slug'] == 'teststrategie-updated'


# ============================================================================
# Hilfsfunktion
# ============================================================================

def monkeypatch_vault(tmp_path: Path) -> None:
    """Setzt OBSIDIAN_VAULT_PATH für den aktuellen Prozess."""
    os.environ['OBSIDIAN_VAULT_PATH'] = str(tmp_path)
    # obsidian_paths Modul-Cache aktualisieren
    import importlib
    import services.api.utils.obsidian_paths as op_module
    importlib.reload(op_module)

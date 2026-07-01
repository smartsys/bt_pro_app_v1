"""Pytest-Konfiguration für services/api/tests.

Leitet alle Fixtures aus dem Root-conftest (tests/conftest.py) weiter
und stellt einen FastAPI-TestClient für den Knowledge-Router bereit.

Setzt POSTGRES_PORT auf den Test-DB-Port (5562), damit get_session()
in den Route-Handlers die Test-DB nutzt statt der Prod-DB.
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest
from dotenv import load_dotenv

# Projekt-Root für alle Importe
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

# .env laden damit VBT_TEST_DATABASE_URL verfügbar ist
load_dotenv(_ROOT / '.env')

# Test-DB-Port aus VBT_TEST_DATABASE_URL extrahieren und setzen,
# damit user_data.utils.database.db.get_session() die Test-DB nutzt.
_test_url = os.getenv('VBT_TEST_DATABASE_URL', '')
if _test_url:
    _parsed = urlparse(_test_url)
    if _parsed.port:
        os.environ['POSTGRES_PORT'] = str(_parsed.port)
    if _parsed.hostname:
        os.environ['POSTGRES_SERVER'] = _parsed.hostname

# Hinweis: Die db_engine/session-Fixtures aus tests/conftest.py werden über die
# Top-Level-conftest.py (Projekt-Root) als Plugin geladen — pytest_plugins darf
# nur dort stehen, nicht in dieser Unterverzeichnis-conftest.

"""Top-Level-pytest-Konfiguration (Projekt-Root).

Registriert die zentralen Fixtures aus tests/conftest.py als Plugin, damit sie
in allen Test-Verzeichnissen verfügbar sind — insbesondere in services/api/tests/,
das nicht unterhalb von tests/ liegt und die DB-/Session-Fixtures sonst nicht sähe.

pytest erlaubt die Variable pytest_plugins ausschliesslich in der Top-Level-conftest
am rootdir (seit pytest 7 harter Fehler in Unterverzeichnissen).
"""

pytest_plugins = ['tests.conftest']

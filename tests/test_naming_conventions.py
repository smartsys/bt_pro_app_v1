"""Namenskonventions-Test: Stellt sicher, dass veraltete test_set-Bezeichner
nicht mehr im aktiven Code vorkommen.

Ticket 13: Nach dem Naming-Cleanup darf 'test_set' (mit Unterstrich) nicht mehr
als DB-Spaltenname, ORM-Attribut, API-Parameter oder Variablenname in
services/ und user_data/ auftauchen.

Dieser Test schlägt fehl, sobald eine der verbotenen Zeichenketten im Quellcode
auftaucht.
"""

import os
import re
from pathlib import Path

# Wurzel des Projekts, relativ zu dieser Test-Datei
_PROJECT_ROOT = Path(__file__).parent.parent

# Zu prüfende Verzeichnisse
_SCAN_DIRS = [
    _PROJECT_ROOT / 'services',
    _PROJECT_ROOT / 'user_data',
]

# Dateierweiterungen die geprüft werden
_EXTENSIONS = {'.py', '.html', '.js', '.json'}

# Muster die in aktivem Code NICHT vorkommen dürfen
# (Kommentarzeilen werden herausgefiltert)
_FORBIDDEN_PATTERNS = [
    # DB-Spaltennamen / ORM-Attribute
    r'\btest_set_id\b',
    # Alter Tabellenname in SQL-Strings
    r"'test_sets'",
    r'"test_sets"',
    r'\bINTO test_sets\b',
    r'\bFROM test_sets\b',
    # Alte Klasse/Tabelle in Nicht-Kommentar-Kontext — ORM-Verwendung
    # (Den Klassenimport TestSet selbst erlauben wir, nur test_sets als Tabellenstring)
]

# Kommentarzeilen-Muster (Zeilen die mit # beginnen oder nur HTML/JS-Kommentare sind)
_COMMENT_LINE_RE = re.compile(
    r'^\s*(?:#|//|<!--|\*)',
)

# GEÄNDERT: Ticket 13 — Namenskonventions-Test neu erstellt


def _iter_source_files():
    """Iteriert über alle relevanten Quelldateien in den Scan-Verzeichnissen."""
    for scan_dir in _SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for path in scan_dir.rglob('*'):
            if path.suffix in _EXTENSIONS and '__pycache__' not in str(path):
                yield path


def _get_active_code_lines(filepath: Path):
    """Gibt (Zeilennummer, Zeileninhalt)-Tupel für nicht-leere Nicht-Kommentar-Zeilen zurück.

    Filtert:
    - Reine Kommentarzeilen (# / // / <!-- / *)
    - Zeilen die 'GEÄNDERT:' enthalten (Migrations-Kommentare)
    """
    try:
        lines = filepath.read_text(encoding='utf-8', errors='replace').splitlines()
    except Exception:
        return

    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        # Kommentarzeile überspringen
        if _COMMENT_LINE_RE.match(stripped):
            continue
        # Migrations-Kommentare überspringen
        if 'GEÄNDERT:' in line:
            continue
        yield lineno, line


def test_no_forbidden_test_set_patterns():
    """Kein verbotener test_set-Bezeichner in aktivem Code."""
    violations = []

    forbidden_res = [re.compile(pattern, re.IGNORECASE) for pattern in _FORBIDDEN_PATTERNS]

    for filepath in _iter_source_files():
        for lineno, line in _get_active_code_lines(filepath):
            for pattern_re in forbidden_res:
                if pattern_re.search(line):
                    rel_path = filepath.relative_to(_PROJECT_ROOT)
                    violations.append(
                        f'{rel_path}:{lineno}: {line.strip()}'
                    )
                    break  # Pro Zeile nur einmal melden

    assert violations == [], (
        f'{len(violations)} verbotene test_set-Bezeichner gefunden:\n'
        + '\n'.join(violations)
    )

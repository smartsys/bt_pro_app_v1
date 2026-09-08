"""Beschreibungstexte der Indikatoren aus ihren Docstrings.

Der Chart-Playground zeigt zu jedem Indikator ein Info-Fenster: was er tut, welche
Eingaben er braucht, was jeder Parameter bewirkt und was er ausgibt. Diese Texte
kommen aus dem Quelltext selbst — es gibt keine zweite, gepflegte Textsammlung, die
irgendwann von der Wirklichkeit abweichen könnte.

Drei Quellen, in dieser Reihenfolge:

1. **Erklärtexte** aus ``user_data/utils/indicators/erklaerungen.py`` — für die eigenen
   Indikatoren. Sie sind für den Anwender geschrieben: was man im Chart sieht und was ein
   Parameter praktisch bewirkt.
2. **Docstring der Rechenfunktion** (``factory.apply_func``) — Rückfall für eigene
   Indikatoren ohne Erklärtext. Deutsch, aber aus Entwicklersicht geschrieben.
3. **Docstring der Klasse** — für Bibliotheks-Indikatoren (``talib:...``, ``vbt:...``).
   Deren ``apply_func`` beschreibt nur die technische Weiterreichung der Arrays und taugt
   nicht als Erklärung.
"""

import inspect
import re
from typing import Any, Optional

try:
    from user_data.utils.indicators.erklaerungen import INDICATOR_EXPLANATIONS
except Exception:  # Erklärtexte sind optional — ohne sie greift der Docstring-Rückfall.
    INDICATOR_EXPLANATIONS = {}

# Abschnittsüberschriften eines Google-Style-Docstrings.
_SECTION_PATTERN = re.compile(r'^(Args|Arguments|Returns|Yields|Raises|Note|Notes|Example|Examples):\s*$')

# Ein Eintrag im Args-Abschnitt: "    name (typ): Text" oder "    name: Text".
_ARG_PATTERN = re.compile(r'^(\w+)\s*(?:\([^)]*\))?\s*:\s*(.*)$')


def _clean(text: Optional[str]) -> str:
    """Docstring einrücken-bereinigen und Rand-Leerzeichen entfernen.

    Args:
        text: Roher Docstring oder None.

    Returns:
        Bereinigter Text, leer wenn nichts vorhanden war.
    """
    if not text:
        return ''
    return inspect.cleandoc(text).strip()


def _split_sections(doc: str) -> dict[str, list[str]]:
    """Zerlegt einen Google-Style-Docstring in seine Abschnitte.

    Args:
        doc: Bereinigter Docstring.

    Returns:
        {Abschnittsname: Zeilen}, wobei der Text vor der ersten Überschrift unter
        dem Schlüssel '_intro' steht.
    """
    sections: dict[str, list[str]] = {'_intro': []}
    aktuell = '_intro'
    for zeile in doc.splitlines():
        treffer = _SECTION_PATTERN.match(zeile.strip())
        if treffer:
            aktuell = treffer.group(1)
            sections.setdefault(aktuell, [])
            continue
        sections[aktuell].append(zeile)
    return sections


def _parse_args(zeilen: list[str]) -> dict[str, str]:
    """Liest den Args-Abschnitt als {Name: Beschreibung}.

    Fortsetzungszeilen (eingerückt unter einem Eintrag) werden an den vorigen Eintrag
    angehängt, damit mehrzeilige Erklärungen vollständig ankommen.

    Args:
        zeilen: Zeilen des Args-Abschnitts.

    Returns:
        {Parameter- bzw. Eingabename: Beschreibung}.
    """
    args: dict[str, str] = {}
    letzter: Optional[str] = None
    for zeile in zeilen:
        blank = zeile.strip()
        if not blank:
            continue
        treffer = _ARG_PATTERN.match(blank)
        # Eine Fortsetzungszeile ist stärker eingerückt als der Eintrag selbst und
        # enthält keinen eigenen "name:"-Kopf.
        if treffer and not (letzter and len(zeile) - len(zeile.lstrip()) >= 8 and not treffer.group(2)):
            letzter = treffer.group(1)
            args[letzter] = treffer.group(2).strip()
        elif letzter:
            args[letzter] = (args[letzter] + ' ' + blank).strip()
    return args


def _join(zeilen: list[str]) -> str:
    """Abschnittszeilen zu einem Absatztext zusammenfassen.

    Der gemeinsame Einzug des Abschnitts wird abgezogen — die Zeilen unter einer
    Überschrift sind gegenüber dem Docstring-Rumpf zusätzlich eingerückt und trügen
    diesen Einzug sonst bis in die Anzeige.

    Args:
        zeilen: Zeilen eines Abschnitts.

    Returns:
        Text ohne gemeinsamen Einzug und ohne führende/abschließende Leerzeilen.
    """
    gefuellt = [z for z in zeilen if z.strip()]
    if not gefuellt:
        return ''
    einzug = min(len(z) - len(z.lstrip()) for z in gefuellt)
    return '\n'.join(z[einzug:] if z.strip() else '' for z in zeilen).strip()


def parse_docstring(doc: Optional[str]) -> dict[str, Any]:
    """Zerlegt einen Docstring in Kurzfassung, Fließtext, Argumente und Rückgabe.

    Args:
        doc: Roher Docstring.

    Returns:
        {'summary', 'body', 'args', 'returns'} — 'args' ist ein Dict, der Rest Text.
    """
    text = _clean(doc)
    if not text:
        return {'summary': '', 'body': '', 'args': {}, 'returns': ''}

    sections = _split_sections(text)
    intro = _join(sections.get('_intro', []))
    absaetze = intro.split('\n\n', 1)
    summary = absaetze[0].replace('\n', ' ').strip()
    body = absaetze[1].strip() if len(absaetze) > 1 else ''

    args = _parse_args(sections.get('Args', []) or sections.get('Arguments', []))
    returns = _join(sections.get('Returns', []))
    return {'summary': summary, 'body': body, 'args': args, 'returns': returns}


def build_indicator_doc(factory: Any, full_id: str, inputs: list, params: list,
                       outputs: Optional[list] = None) -> dict[str, Any]:
    """Baut die Info-Fenster-Daten eines Indikators.

    Args:
        factory: IndicatorFactory-Klasse des Indikators.
        full_id: Vollständige Katalog-ID, z.B. 'custom:dwsSignumPivot'.
        inputs: Namen der Eingabereihen (factory.input_names).
        params: Namen der Parameter (factory.param_names).
        outputs: Namen der Ausgabereihen (factory.output_names), für die Ausgaben-Texte.

    Returns:
        {'was', 'wie', 'inputs', 'params', 'outputs', 'source'} — die drei Dicts sind
        {Name: Beschreibung} und enthalten nur beschriebene Einträge. 'source' benennt die
        Herkunft ('erklaerung', 'apply_func' oder 'class').
    """
    outputs = outputs or []
    name_ohne_gruppe = full_id.split(':', 1)[-1]

    erklaerung = INDICATOR_EXPLANATIONS.get(name_ohne_gruppe)
    if erklaerung:
        return {
            'was': erklaerung.get('was', ''),
            'wie': erklaerung.get('wie', ''),
            'inputs': {n: t for n, t in (erklaerung.get('inputs') or {}).items() if n in inputs},
            'params': {n: t for n, t in (erklaerung.get('params') or {}).items() if n in params},
            'outputs': {n: t for n, t in (erklaerung.get('outputs') or {}).items() if n in outputs},
            'source': 'erklaerung',
        }

    ist_custom = full_id.startswith('custom:')
    quelle = 'apply_func' if ist_custom else 'class'

    if ist_custom:
        roh = getattr(getattr(factory, 'apply_func', None), '__doc__', '') or ''
        # Fällt der Docstring der Rechenfunktion aus, bleibt die Klasse als Rückfall.
        if not roh.strip():
            roh = getattr(factory, '__doc__', '') or ''
            quelle = 'class'
    else:
        roh = getattr(factory, '__doc__', '') or ''

    zerlegt = parse_docstring(roh)
    args = zerlegt['args']
    return {
        'was': zerlegt['summary'],
        'wie': zerlegt['body'],
        'inputs': {n: args[n] for n in inputs if n in args},
        'params': {n: args[n] for n in params if n in args},
        'outputs': {},
        'source': quelle,
    }

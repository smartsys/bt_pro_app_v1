"""Tests für die Indikator-Beschreibungen aus den Docstrings.

Geprüft wird:
  - Kurzfassung und Fließtext werden am ersten Absatz getrennt
  - der Args-Abschnitt wird je Name zerlegt, auch bei mehrzeiligen Erklärungen
  - der Returns-Abschnitt verliert seinen Einzug
  - Eingaben und Parameter landen getrennt in den Info-Daten
  - ein hinterlegter Erklärtext hat Vorrang vor dem Docstring
  - ohne Erklärtext nehmen eigene Indikatoren den Docstring der Rechenfunktion,
    Bibliotheks-Indikatoren den der Klasse
  - ein fehlender Docstring liefert leere Felder statt eines Fehlers
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.api.utils import indicator_docs
from services.api.utils.indicator_docs import build_indicator_doc, parse_docstring


BEISPIEL_DOC = """Pivot-Hochs und -Tiefs als fortgeschriebene Treppenlinien.

    Die unterste Stufe der Mechanik: Wo liegt das jeweils letzte
    bestätigte Pivot-Hoch?

    Args:
        high: High-Serie.
        left: Balken links des Extrempunkts (Vorgabe 3).
        right: Balken rechts des Extrempunkts, also die Zahl der Balken,
            die auf den Extrempunkt folgen müssen.

    Returns:
        Tuple (high_level, low_level) — letztes bestätigtes
        Pivot-Hoch und -Tief.

    Raises:
        ValueError: Wenn left kleiner als 1 ist.
    """


def test_kurzfassung_und_fliesstext_werden_getrennt():
    zerlegt = parse_docstring(BEISPIEL_DOC)
    assert zerlegt['summary'] == 'Pivot-Hochs und -Tiefs als fortgeschriebene Treppenlinien.'
    assert zerlegt['body'].startswith('Die unterste Stufe der Mechanik')
    # Der Args-Abschnitt gehört nicht mehr in den Fließtext.
    assert 'Args:' not in zerlegt['body']
    assert 'high: High-Serie.' not in zerlegt['body']


def test_argumente_werden_je_name_zerlegt():
    args = parse_docstring(BEISPIEL_DOC)['args']
    assert args['high'] == 'High-Serie.'
    assert args['left'] == 'Balken links des Extrempunkts (Vorgabe 3).'


def test_mehrzeilige_argument_beschreibung_bleibt_vollstaendig():
    args = parse_docstring(BEISPIEL_DOC)['args']
    assert args['right'] == (
        'Balken rechts des Extrempunkts, also die Zahl der Balken, '
        'die auf den Extrempunkt folgen müssen.'
    )


def test_returns_verliert_seinen_einzug():
    returns = parse_docstring(BEISPIEL_DOC)['returns']
    assert returns.startswith('Tuple (high_level, low_level)')
    # Keine Zeile trägt noch den Abschnitts-Einzug.
    assert all(not z.startswith(' ') for z in returns.splitlines())


def test_fehlender_docstring_liefert_leere_felder():
    zerlegt = parse_docstring(None)
    assert zerlegt == {'summary': '', 'body': '', 'args': {}, 'returns': ''}


class _EigeneFactory:
    """Klassentext, der nicht verwendet werden soll."""

    @staticmethod
    def apply_func():
        """Kurzfassung der Rechenfunktion.

        Args:
            high: High-Serie.
            left: Balken links.
        """


class _BibliotheksFactory:
    """Simple Moving Average, Overlap Studies"""

    @staticmethod
    def apply_func():
        """Apply the TA-Lib function with the provided inputs and parameters."""


def test_eigener_indikator_nimmt_die_rechenfunktion_und_trennt_eingaben_von_parametern():
    doc = build_indicator_doc(_EigeneFactory, 'custom:dwsBeispiel', ['high'], ['left'])
    assert doc['was'] == 'Kurzfassung der Rechenfunktion.'
    assert doc['inputs'] == {'high': 'High-Serie.'}
    assert doc['params'] == {'left': 'Balken links.'}
    assert doc['source'] == 'apply_func'


def test_bibliotheks_indikator_nimmt_den_klassentext():
    doc = build_indicator_doc(_BibliotheksFactory, 'talib:SMA', ['close'], ['timeperiod'])
    assert doc['was'] == 'Simple Moving Average, Overlap Studies'
    # Der apply_func der Bibliothek beschreibt nur die Weiterreichung der Arrays.
    assert 'TA-Lib function' not in doc['was']
    assert doc['source'] == 'class'


def test_erklaertext_hat_vorrang_vor_dem_docstring(monkeypatch):
    monkeypatch.setitem(indicator_docs.INDICATOR_EXPLANATIONS, 'dwsBeispiel', {
        'was': 'Zeigt im Chart eine Treppenlinie.',
        'params': {'left': 'Kerzen links des Gipfels.'},
        'outputs': {'result': 'Die Treppenlinie.'},
    })
    doc = build_indicator_doc(_EigeneFactory, 'custom:dwsBeispiel', ['high'], ['left'], ['result'])
    assert doc['was'] == 'Zeigt im Chart eine Treppenlinie.'
    assert doc['params'] == {'left': 'Kerzen links des Gipfels.'}
    assert doc['outputs'] == {'result': 'Die Treppenlinie.'}
    assert doc['source'] == 'erklaerung'


def test_erklaertext_liefert_nur_namen_die_es_am_indikator_gibt(monkeypatch):
    monkeypatch.setitem(indicator_docs.INDICATOR_EXPLANATIONS, 'dwsBeispiel', {
        'was': 'Kurzfassung.',
        'params': {'left': 'Kerzen links.', 'entfallen': 'Alter Parameter.'},
        'outputs': {'result': 'Ergebnis.', 'weg': 'Alte Ausgabe.'},
    })
    doc = build_indicator_doc(_EigeneFactory, 'custom:dwsBeispiel', ['high'], ['left'], ['result'])
    assert 'entfallen' not in doc['params']
    assert 'weg' not in doc['outputs']


def test_unbeschriebene_eingaben_und_parameter_fehlen_statt_leer_dazustehen():
    doc = build_indicator_doc(_EigeneFactory, 'custom:dwsBeispiel', ['high', 'low'], ['left', 'right'])
    assert 'low' not in doc['inputs']
    assert 'right' not in doc['params']

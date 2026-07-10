"""Tests für das Schreiben und Anzeigen von Indikator-Blöcken in der Objekt-Toolbox.

Deckt zwei zusammenhängende Eigenschaften ab:

1. `_merge_indicator_block` — ein unvollständiges Fragment darf keine bestehenden
   Parameter verlieren. Besonders `tf` ist laufzeit-wirksam: fehlt es, bricht der
   Lauf in `indicator_factory.normalize_tf` mit ValueError ab.
2. `render_spec` — der Rechen-Timeframe `tf` muss in der Toolbox-Ausgabe sichtbar
   sein, sonst baut man beim Zurückschreiben unbemerkt einen Block ohne `tf`.

Reine Funktionen, ohne Netzwerk und ohne DB (die Toolbox ist ein stdlib-only CLI).
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_TOOLBOX_PATH = (
    Path(__file__).resolve().parent.parent
    / ".claude" / "skills" / "ds-strategie-session" / "scripts" / "toolbox.py"
)


def _load_toolbox():
    """Lädt toolbox.py als Modul (Ordnername enthält Bindestriche -> kein Package-Import)."""
    spec = importlib.util.spec_from_file_location("toolbox", _TOOLBOX_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["toolbox"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def toolbox():
    return _load_toolbox()


@pytest.fixture
def bestand():
    """Ein bestehender Indikator-Block, wie er in spec_json/config_json steht."""
    return {
        "sma": {
            "indicator": "talib:SMA",
            "tf": "same",
            "close": "close",
            "timeperiod": 30,
        }
    }


# --- _merge_indicator_block ------------------------------------------------

def test_merge_behaelt_nicht_genannte_parameter(toolbox, bestand):
    """Nur timeperiod im Fragment -> tf, close und indicator bleiben erhalten."""
    verb, block = toolbox._merge_indicator_block(bestand, "sma", {"timeperiod": 50}, replace=False)
    assert block == {
        "indicator": "talib:SMA",
        "tf": "same",
        "close": "close",
        "timeperiod": 50,
    }
    assert bestand["sma"] == block
    assert verb == "aktualisiert (timeperiod)"


def test_merge_verliert_tf_nicht(toolbox, bestand):
    """Der laufzeit-kritische Fall: tf überlebt ein Fragment, das es nicht nennt."""
    _, block = toolbox._merge_indicator_block(bestand, "sma", {"timeperiod": 7}, replace=False)
    assert block["tf"] == "same"


def test_merge_ueberschreibt_genannte_parameter(toolbox, bestand):
    """Genannte Parameter gewinnen — auch tf selbst."""
    _, block = toolbox._merge_indicator_block(bestand, "sma", {"tf": "4h"}, replace=False)
    assert block["tf"] == "4h"
    assert block["timeperiod"] == 30


def test_merge_akzeptiert_arange_range_als_wert(toolbox, bestand):
    """In der IndicatorConfig dürfen Werte arange-Dicts sein (Multiparameter-Lauf)."""
    rang = {"type": "arange", "start": 5, "stop": 100, "step": 5, "dtype": "int64"}
    _, block = toolbox._merge_indicator_block(bestand, "sma", {"timeperiod": rang}, replace=False)
    assert block["timeperiod"] == rang
    assert block["tf"] == "same"


def test_merge_nennt_alle_geaenderten_keys_sortiert(toolbox, bestand):
    verb, _ = toolbox._merge_indicator_block(
        bestand, "sma", {"timeperiod": 9, "close": "open"}, replace=False
    )
    assert verb == "aktualisiert (close, timeperiod)"


def test_replace_ersetzt_block_vollstaendig(toolbox, bestand):
    """--replace ist der bewusste Vollersatz: Nicht-Genanntes fällt weg."""
    frag = {"indicator": "talib:SMA", "timeperiod": 9}
    verb, block = toolbox._merge_indicator_block(bestand, "sma", frag, replace=True)
    assert block == frag
    assert "tf" not in block
    assert verb == "ersetzt"


def test_neuer_key_wird_eingefuegt(toolbox, bestand):
    frag = {"indicator": "talib:RSI", "tf": "same", "close": "close", "timeperiod": 14}
    verb, block = toolbox._merge_indicator_block(bestand, "rsi", frag, replace=False)
    assert block == frag
    assert verb == "hinzugefuegt"
    assert set(bestand) == {"sma", "rsi"}


def test_neuer_key_ignoriert_replace_flag(toolbox, bestand):
    """Bei einem neuen Key gibt es nichts zu ersetzen — Ergebnis ist identisch."""
    frag = {"indicator": "talib:RSI", "tf": "same"}
    verb, block = toolbox._merge_indicator_block(bestand, "rsi", frag, replace=True)
    assert block == frag
    assert verb == "hinzugefuegt"


def test_merge_mutiert_den_bestandsblock_nicht_in_place(toolbox, bestand):
    """Der alte Block wird kopiert, nicht verändert — sonst leakt der Merge nach außen."""
    alt = bestand["sma"]
    toolbox._merge_indicator_block(bestand, "sma", {"timeperiod": 50}, replace=False)
    assert alt["timeperiod"] == 30


# --- render_spec ------------------------------------------------------------

def test_render_spec_zeigt_tf(toolbox, capsys):
    spec = {"indicators": {"sma": {"indicator": "talib:SMA", "tf": "4h", "timeperiod": 30}}}
    toolbox.render_spec(spec)
    out = capsys.readouterr().out
    assert "tf=4h" in out


def test_render_spec_zeigt_indicator_und_enabled_nicht_als_parameter(toolbox, capsys):
    """indicator steht in Klammern, enabled als Tag — beide nicht in der Parameter-Liste."""
    spec = {
        "indicators": {
            "sma": {"indicator": "talib:SMA", "tf": "same", "enabled": False, "timeperiod": 30}
        }
    }
    toolbox.render_spec(spec)
    out = capsys.readouterr().out
    assert "(talib:SMA)" in out
    assert "[deaktiviert]" in out
    assert "indicator=" not in out
    assert "enabled=" not in out
    assert "tf=same" in out

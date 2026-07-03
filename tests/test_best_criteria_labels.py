"""Bestwert-Kriterium: Key -> Klartext-Label-Mapping (Single Source, serverseitig).

Verifiziert services/api/utils/best_criteria_labels.py:
- criteria_keys_to_labels bildet die vier stabilen Keys auf ihre deutschen Labels ab
- unbekannte Keys werden übersprungen (keine Ausnahme)
- None/leere Liste -> leere Liste
- VALID_CRITERIA_KEYS deckt genau die vier kanonischen Keys ab
"""

from services.api.utils.best_criteria_labels import (
    BEST_CRITERIA_LABELS,
    VALID_CRITERIA_KEYS,
    criteria_keys_to_labels,
)


def test_alle_vier_keys_bekannt():
    """Genau die vier kanonischen Keys existieren im Katalog."""
    assert VALID_CRITERIA_KEYS == {"max_return", "winrate_band", "sharpe_band", "pf_min30"}
    assert set(BEST_CRITERIA_LABELS) == VALID_CRITERIA_KEYS


def test_keys_auf_labels():
    """Keys werden auf die erwarteten deutschen Labels abgebildet (Reihenfolge erhalten)."""
    labels = criteria_keys_to_labels(["max_return", "winrate_band", "sharpe_band", "pf_min30"])
    assert labels == [
        "Max Total Return",
        "Win-Rate-Band",
        "Sharpe-Band",
        "Profitfaktor (>= 30 Trades)",
    ]


def test_unbekannter_key_wird_uebersprungen():
    """Unbekannte Keys tauchen nicht in der Ausgabe auf (defensive Anzeige, keine Ausnahme)."""
    assert criteria_keys_to_labels(["max_return", "quatsch"]) == ["Max Total Return"]


def test_leer_und_none():
    """None und leere Liste liefern eine leere Label-Liste."""
    assert criteria_keys_to_labels(None) == []
    assert criteria_keys_to_labels([]) == []

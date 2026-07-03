"""Bestwert-Kriterium: Key -> Klartext-Label-Mapping (Single Source, serverseitig).

Verifiziert services/api/utils/best_criteria_labels.py:
- criteria_keys_to_labels bildet die vier stabilen Keys auf ihre deutschen Labels ab
- unbekannte Keys werden übersprungen (keine Ausnahme)
- None/leere Liste -> leere Liste
- VALID_CRITERIA_KEYS deckt genau die vier kanonischen Keys ab
"""

from services.api.utils.best_criteria_labels import (
    BEST_CRITERIA_LABELS,
    BEST_CRITERIA_SHORT,
    VALID_CRITERIA_KEYS,
    criteria_keys_to_badges,
    criteria_keys_to_labels,
)


def test_alle_vier_keys_bekannt():
    """Genau die vier kanonischen Keys existieren in beiden Katalogen (lang + Kürzel)."""
    assert VALID_CRITERIA_KEYS == {"max_return", "winrate_band", "sharpe_band", "pf_min30"}
    assert set(BEST_CRITERIA_LABELS) == VALID_CRITERIA_KEYS
    assert set(BEST_CRITERIA_SHORT) == VALID_CRITERIA_KEYS


def test_keys_auf_labels():
    """Keys werden auf die erwarteten langen Labels abgebildet (Reihenfolge erhalten)."""
    labels = criteria_keys_to_labels(["max_return", "winrate_band", "sharpe_band", "pf_min30"])
    assert labels == [
        "Max Total Return",
        "Win-Rate-Band",
        "Sharpe-Band",
        "Profitfaktor (>= 30 Trades)",
    ]


def test_keys_auf_badges_short_und_long():
    """Badges liefern Einzelbuchstaben-Kürzel (short) + Langform (long) je Kriterium."""
    badges = criteria_keys_to_badges(["max_return", "winrate_band", "sharpe_band", "pf_min30"])
    assert badges == [
        {"short": "T", "long": "Max Total Return"},
        {"short": "W", "long": "Win-Rate-Band"},
        {"short": "S", "long": "Sharpe-Band"},
        {"short": "P", "long": "Profitfaktor (>= 30 Trades)"},
    ]


def test_unbekannter_key_wird_uebersprungen():
    """Unbekannte Keys tauchen weder in Labels noch in Badges auf (keine Ausnahme)."""
    assert criteria_keys_to_labels(["max_return", "quatsch"]) == ["Max Total Return"]
    assert criteria_keys_to_badges(["max_return", "quatsch"]) == [{"short": "T", "long": "Max Total Return"}]


def test_leer_und_none():
    """None und leere Liste liefern eine leere Liste (Labels wie Badges)."""
    assert criteria_keys_to_labels(None) == []
    assert criteria_keys_to_labels([]) == []
    assert criteria_keys_to_badges(None) == []
    assert criteria_keys_to_badges([]) == []

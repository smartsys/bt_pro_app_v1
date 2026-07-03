"""Kanonische Zuordnung Bestwert-Kriterium: stabiler Key -> Kürzel + Klartext-Label.

Single Source für die vier Bestwerte, die ein Result beim run-bestwerte-Lauf gewinnen
kann. In der DB (backtest_results.best_criteria_json) werden ausschließlich die stabilen
Keys gespeichert (kein Drift bei Umbenennung); für die Anzeige liefert der Server aus
DIESER Datei je Kriterium ein kompaktes Kürzel (Badge-Text) UND das lange Klartext-Label
(Hover-Tooltip). Kein zweiter Katalog in JS oder in der Toolbox.

Die langen Labels entsprechen 1:1 der 4er-Definition aus _bestwerte_for_run (Toolbox)
bzw. dem multiparameter-lauf-Workflow.
"""
from typing import List, Optional

# Stabiler Key -> langes Klartext-Label (deutsch, Hover-Tooltip).
BEST_CRITERIA_LABELS = {
    "max_return": "Max Total Return",
    "winrate_band": "Win-Rate-Band",
    "sharpe_band": "Sharpe-Band",
    "pf_min30": "Profitfaktor (>= 30 Trades)",
}

# Stabiler Key -> Einzelbuchstabe (internes Kürzel). Maximal platzsparend in der
# Results-Tabelle; die Langform steht im Hover-Tooltip.
BEST_CRITERIA_SHORT = {
    "max_return": "T",
    "winrate_band": "W",
    "sharpe_band": "S",
    "pf_min30": "P",
}

# Gültige Keys (für Validierung eingehender Kriterium-Listen)
VALID_CRITERIA_KEYS = set(BEST_CRITERIA_LABELS)


def criteria_keys_to_labels(keys: Optional[List[str]]) -> List[str]:
    """Wandelt eine Liste stabiler Keys in die langen Klartext-Labels um.

    Unbekannte Keys werden übersprungen (keine Ausnahme). Leere/None -> leere Liste.
    """
    if not keys:
        return []
    return [BEST_CRITERIA_LABELS[k] for k in keys if k in BEST_CRITERIA_LABELS]


def criteria_keys_to_badges(keys: Optional[List[str]]) -> List[dict]:
    """Wandelt Keys in Badge-Objekte {short, long} für die Anzeige um.

    short = kompaktes Kürzel (Badge-Text), long = Klartext-Label (Hover-Tooltip).
    Unbekannte Keys werden übersprungen. Leere/None -> leere Liste.
    """
    if not keys:
        return []
    return [
        {"short": BEST_CRITERIA_SHORT[k], "long": BEST_CRITERIA_LABELS[k]}
        for k in keys if k in BEST_CRITERIA_LABELS
    ]

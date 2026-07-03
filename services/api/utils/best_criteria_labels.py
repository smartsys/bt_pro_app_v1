"""Kanonische Zuordnung Bestwert-Kriterium: stabiler Key -> deutsches Klartext-Label.

Single Source für die vier Bestwerte, die ein Result beim run-bestwerte-Lauf gewinnen
kann. In der DB (backtest_results.best_criteria_json) werden ausschließlich die stabilen
Keys gespeichert (kein Drift bei Umbenennung); für die Anzeige (Frontend-Badges,
Toolbox-Ausgaben) liefert der Server den Klartext aus DIESER Datei. Kein zweiter
Katalog in JS oder in der Toolbox.

Die Labels entsprechen 1:1 der 4er-Definition aus _bestwerte_for_run (Toolbox) bzw.
dem multiparameter-lauf-Workflow.
"""
from typing import List, Optional

# Stabiler Key -> Klartext-Label (deutsch). Reihenfolge = kanonische Bewertungsreihenfolge.
BEST_CRITERIA_LABELS = {
    "max_return": "Max Total Return",
    "winrate_band": "Win-Rate-Band",
    "sharpe_band": "Sharpe-Band",
    "pf_min30": "Profitfaktor (>= 30 Trades)",
}

# Gültige Keys (für Validierung eingehender Kriterium-Listen)
VALID_CRITERIA_KEYS = set(BEST_CRITERIA_LABELS)


def criteria_keys_to_labels(keys: Optional[List[str]]) -> List[str]:
    """Wandelt eine Liste stabiler Keys in die deutschen Klartext-Labels um.

    Unbekannte Keys werden übersprungen (keine Ausnahme — defensive Anzeige).
    Leere/None-Eingabe -> leere Liste.
    """
    if not keys:
        return []
    return [BEST_CRITERIA_LABELS[k] for k in keys if k in BEST_CRITERIA_LABELS]

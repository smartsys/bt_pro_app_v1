"""Einmal-Migration: Alt-Format {logic, conditions} -> Block-Format {blocks}.

Die Rules-Engine kennt zur Laufzeit ausschließlich das Block-Format
(disjunktive Normalform): eine Gruppe besteht aus Blöcken, innerhalb eines
Blocks sind die Conditions UND-verknüpft, die Blöcke untereinander ODER.

Dieses Modul ist der EINZIGE Ort, der das alte Format {logic, conditions}
überhaupt noch interpretiert. Es wird ausschließlich vom DB-Migrationsskript
verwendet, um gespeicherte Iterationen (spec_json.rules) und Playground-Setups
(strategy_config_json) einmalig auf das Block-Format zu heben. Danach wird es
zur Laufzeit nicht mehr aufgerufen.

Konvertierungsregel (verlustfrei):
    altes logic='AND'  -> EIN Block mit allen Conditions
    altes logic='OR'   -> JE Condition ein eigener Block (DNF-Aufsplittung)
"""

from typing import Any, Optional


def legacy_group_to_blocks(group: Optional[dict]) -> Optional[dict]:
    """Wandelt eine Alt-Gruppe {logic, conditions} in das Block-Format um.

    Ist die Gruppe bereits im Block-Format (enthält 'blocks'), wird sie
    unverändert zurückgegeben (idempotent). None bleibt None.

    Args:
        group: Rule-Gruppe im Alt-Format {logic, conditions} oder None.

    Returns:
        Gruppe im Block-Format {'blocks': [{'conditions': [...]}, ...]} oder None.
    """
    if group is None:
        return None
    if 'blocks' in group:
        return group

    logic = (group.get('logic') or 'AND').upper()
    conditions = list(group.get('conditions') or [])

    if logic == 'OR':
        # ODER: jede Bedingung wird ein eigener Block (Block intern UND, Blöcke ODER)
        return {'blocks': [{'conditions': [cond]} for cond in conditions]}

    # AND (Default): alle Bedingungen in einem Block
    return {'blocks': [{'conditions': conditions}]}


def migrate_rules_json(rules_json: Any) -> Any:
    """Hebt ein komplettes rules_json (entry + exit) auf das Block-Format.

    Idempotent: bereits migrierte Strukturen bleiben unverändert. Nicht-Dicts
    werden unverändert durchgereicht (defensiv für fehlerhafte Altdaten).

    Args:
        rules_json: {'entry': {...}, 'exit': {...}|None} im Alt- oder Block-Format.

    Returns:
        rules_json mit entry/exit im Block-Format.
    """
    if not isinstance(rules_json, dict):
        return rules_json

    out = dict(rules_json)
    if out.get('entry') is not None:
        out['entry'] = legacy_group_to_blocks(out['entry'])
    if out.get('exit') is not None:
        out['exit'] = legacy_group_to_blocks(out['exit'])
    return out

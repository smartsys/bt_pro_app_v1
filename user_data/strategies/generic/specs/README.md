# specs/ — Legacy-Verzeichnis (Deprecated)

**Dieses Verzeichnis ist read-only Legacy.**

## Status

Ab Ticket 12 leben Specs autoritativ in `strategy_iterations.spec_json` (Datenbank).
Spec-Files hier werden nicht mehr als Quelle für aktive Runs genutzt.

## Migration

Das Skript `scripts/sync_specs_to_iterations.py` hat die Specs einmalig in die DB
übertragen. Idempotent bei erneutem Lauf.

## Löschung

Wird durchgeführt sobald nachweislich keine Pipeline mehr auf diese Files zeigt.
Bis dahin: read-only behalten als Referenz.

# Dummy-Vault (Platzhalter)

Dieser Ordner ist nur ein **leerer Platzhalter**, damit der Vault-Mount beim
ersten Start nicht abbricht. Er erfüllt keine Funktion.

Der Pfad wird über `OBSIDIAN_VAULT_HOST_PATH` in der `.env` gesteuert
(Default: `./data/obsidian`).

## Eigenen Vault nutzen

Willst du das Knowledge-Dashboard (semantische Suche über deine Notizen)
verwenden, trag in der `.env` den Pfad zu deinem echten Markdown-Ordner ein:

```
OBSIDIAN_VAULT_HOST_PATH=/pfad/zu/deinem/vault
```

## Verhältnis zu Obsidian

Die App spricht **keine** Obsidian-API an. Der gesamte Datenverkehr läuft über das
gemountete Verzeichnis:

- **Schreiben:** Konzept- und Iterations-Notizen werden direkt als Dateien angelegt,
  umbenannt und gelöscht (`write_text`, `mkdir`, `rename`, `rmtree`).
- **Lesen/Embedding:** Der Indexer liest rekursiv alle `.md` (`rglob("*.md")`),
  erzeugt Embeddings und legt sie für die semantische Suche ab.

Für Speicherung, Embedding und Suche genügt also ein Ordner mit `.md`-Dateien —
egal, ob von Obsidian oder sonstwie erzeugt. Obsidian muss dafür nicht laufen.

**Wozu Obsidian trotzdem gebraucht wird:** In der Konzept-Übersicht baut das Frontend
„In Obsidian öffnen"-Links der Form `obsidian://open?path=…` (Basis:
`OBSIDIAN_VAULT_HOST_PATH`). Das ist ein Deeplink, keine API — klickt man ihn, reicht
das Betriebssystem ihn an die **lokal installierte** Obsidian-App weiter. Damit diese
Links etwas öffnen, muss auf dem Host Obsidian mit diesem Vault vorhanden sein. Ohne
Obsidian laufen nur diese Links ins Leere; alles andere funktioniert weiter.

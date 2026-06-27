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

Obsidian selbst ist nicht nötig — es genügt ein Verzeichnis mit `.md`-Dateien.

"""Utility: Inhalte der Obsidian-Notizen, die die App im Vault anlegt.

Die erzeugten Notizen folgen den Vault-Templates unter
`30_Trading/strategies/_templates/` (strategy-concept.md, status.md,
iteration.md). Felder, die aus der DB bekannt sind, werden befüllt; alles
Redaktionelle bleibt als Platzhalter stehen und wird im Vault ausgefüllt.

Wird ein Vault-Template geändert, muss der passende Builder hier nachgezogen
werden — die Frontmatter-Schlüssel sind die Grundlage der Dataview-Tabellen in
den Konzept-Notizen.
"""
from datetime import date
from typing import Optional


def _yaml_quote(value: Optional[str]) -> str:
    """Setzt einen Text als YAML-String in doppelte Anführungszeichen.

    Args:
        value: Rohtext oder None.

    Returns:
        Escapter YAML-String inklusive Anführungszeichen (leer bei None).
    """
    if not value:
        return '""'
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def build_concept_note(slug: str, name: str, today: Optional[str] = None) -> str:
    """Baut die Konzept-Notiz `<slug>-concept.md` nach dem Vault-Template.

    Args:
        slug: Normalisierter Konzept-Slug (kebab-case).
        name: Anzeigename des Konzepts.
        today: ISO-Datum; None nimmt das heutige Datum.

    Returns:
        Vollständiger Markdown-Inhalt der Konzept-Notiz.
    """
    day = today or date.today().isoformat()
    return (
        "---\n"
        "type: strategy-concept\n"
        f"slug: {slug}\n"
        "status: idea\n"
        f"created: {day}\n"
        f"updated: {day}\n"
        "target_assets: []\n"
        'target_timeframe: ""\n'
        'target_regime: ""\n'
        "tags: [trading]\n"
        "---\n"
        "\n"
        f"# {name} — Konzept\n"
        "\n"
        "> Einzeiler: Was ist die Kern-Idee dieser Strategie?\n"
        "\n"
        "## Mechanik\n"
        "\n"
        "_Entry-Logik, Exit-Logik, Indikator-Zusammenspiel in Prosaform._\n"
        "\n"
        "## Hypothetischer Edge\n"
        "\n"
        "_Warum sollte das funktionieren? Welches Marktverhalten wird ausgenutzt?_\n"
        "\n"
        "## Ziel-Regime\n"
        "\n"
        "_In welchem Marktregime sollte die Strategie funktionieren / nicht funktionieren?_\n"
        "\n"
        "## Abgrenzung zu existierenden Strategien\n"
        "\n"
        "_Worin unterscheidet sich das von bereits implementierten Konzepten?_\n"
        "\n"
        "## Infrastruktur-Check\n"
        "\n"
        "- [ ] Alle benötigten Indikatoren existieren in `user_data/utils/indicators/`\n"
        "- [ ] Spec-Runner unterstützt benötigte Features (State-Primitiven, Multi-Combo, etc.)\n"
        "- [ ] Testdaten (OHLCV) für Ziel-Assets vorhanden\n"
        "\n"
        "## Verweise\n"
        "\n"
        "- **Status:** [[status]]\n"
        "- Quelle: _Link/Paper/Inspiration_\n"
        "- Ähnliche Ansätze im Vault: _Links_\n"
    )


def build_status_note(slug: str, name: str, today: Optional[str] = None) -> str:
    """Baut die `status.md` des Konzepts nach dem Vault-Template.

    Args:
        slug: Normalisierter Konzept-Slug (kebab-case).
        name: Anzeigename des Konzepts.
        today: ISO-Datum; None nimmt das heutige Datum.

    Returns:
        Vollständiger Markdown-Inhalt der Status-Notiz.
    """
    day = today or date.today().isoformat()
    return (
        "---\n"
        "type: strategy-status\n"
        f"strategy: {slug}\n"
        f"updated: {day}\n"
        "---\n"
        "\n"
        f"# {name} — STATUS\n"
        "\n"
        "> **Operativer Anker.** Aktueller Stand, geplante Schritte, beste Iteration, Backlog.\n"
        "> Lesereihenfolge: Kurz-Status → Geplant → Detaildaten.\n"
        "\n"
        "---\n"
        "\n"
        "## Aktueller Stand\n"
        "\n"
        "_2–4 Sätze: Wo steht die Strategie gerade? Was ist zuletzt passiert (Läufe, Favoriten, Erkenntnisse)?_\n"
        "\n"
        "---\n"
        "\n"
        "## Geplant — nächste Schritte (beschlossen)\n"
        "\n"
        "1. _Beschlossener Schritt: Was, mit welchem Werkzeug, mit welchem Ziel — und wer übernimmt?_\n"
        "\n"
        "> Abgrenzung: **Geplant** = beschlossene Reihenfolge. **Backlog** (unten) = priorisierter Ideen-Speicher.\n"
        "\n"
        "---\n"
        "\n"
        "## Beste Iteration (Real-Money-Empfehlung)\n"
        "\n"
        "_Noch keine Iteration gemessen._\n"
        "\n"
        "### Vergleichs-Anker (Notable Results)\n"
        "\n"
        "| Anker | Iteration | Result-ID | Sharpe | Max DD | Hinweis |\n"
        "|---|---|---|---|---|---|\n"
        "| _Beschreibung_ | `VERSION` | `ID` | `X.XX` | `-XX %` | _Kurznote_ |\n"
        "\n"
        "---\n"
        "\n"
        "## Mess-Tracks (eingefroren)\n"
        "\n"
        "| Track | Symbol | Zeitraum | Sizing | Zweck |\n"
        "|---|---|---|---|---|\n"
        "| A | `SYMBOL TIMEFRAME` | `YYYY-MM-DD..YYYY-MM-DD` | value-100 | Referenz, In-Sample |\n"
        "| B | `SYMBOL TIMEFRAME` | `YYYY-MM-DD..YYYY-MM-DD` | percent100 | Stress-Test / Compounding |\n"
        "\n"
        "---\n"
        "\n"
        "## Aktive Iteration\n"
        "\n"
        "— (keine aktive Iteration)\n"
        "\n"
        "---\n"
        "\n"
        "## Letzte Iterationen (Schnellüberblick, max. 3)\n"
        "\n"
        "| Version | Hypothese | Verdict | Vault |\n"
        "|---|---|---|---|\n"
        "| — | — | — | — |\n"
        "\n"
        "---\n"
        "\n"
        "## Backlog — Ideen (priorisiert)\n"
        "\n"
        "Volle Herleitung je Idee in `ideas/` (eine Notiz pro Idee nach `_templates/idea.md`) — hier nur die Kurzliste:\n"
        "\n"
        "1. _Noch keine Ideen._\n"
        "\n"
        "---\n"
        "\n"
        "## Nicht anfassen\n"
        "\n"
        "❌ = verworfen. Details in Lessons.\n"
        "\n"
        "- _Noch nichts verworfen._\n"
        "\n"
        "---\n"
        "\n"
        "## Verweise\n"
        "\n"
        f"- **Vault-Konzept:** [[{slug}-concept]]\n"
        "- **Vault-Iterationen:** `iterations/`\n"
        "- **Vault-Lessons:** `lessons/`\n"
        "- **Workflow-Docs (Projekt):** `documentation/knowledge/strategy-development/workflows/`\n"
    )


def build_iteration_note(
    slug: str,
    version: int,
    version_name: Optional[str],
    iteration_id: int,
    concept_id: int,
    parent_iteration_id: Optional[int],
    parent_version: Optional[int],
    today: Optional[str] = None,
) -> str:
    """Baut die Iterations-Notiz `<slug>-<version>.md` nach dem Vault-Template.

    Args:
        slug: Normalisierter Konzept-Slug (kebab-case).
        version: Fortlaufende Iterations-Nummer.
        version_name: Freies Label ohne Nummer (optional).
        iteration_id: Primärschlüssel der Iteration.
        concept_id: Primärschlüssel des Konzepts.
        parent_iteration_id: Primärschlüssel der Vorgänger-Iteration oder None.
        parent_version: Versions-Nummer der Vorgänger-Iteration oder None
            (nur für den Wikilink im Setup-Abschnitt).
        today: ISO-Datum; None nimmt das heutige Datum.

    Returns:
        Vollständiger Markdown-Inhalt der Iterations-Notiz.
    """
    day = today or date.today().isoformat()
    parent = parent_iteration_id if parent_iteration_id is not None else "null"
    title = f"{version} — {version_name}" if version_name else f"{version} — Titel"
    basis = f"[[{slug}-{parent_version}]]" if parent_version is not None else "_keine (Baseline)_"
    return (
        "---\n"
        "type: strategy-iteration\n"
        f"iteration_id: {iteration_id}\n"
        f"concept_id: {concept_id}\n"
        f"concept_slug: {slug}\n"
        f"version: {version}\n"
        f"version_name: {_yaml_quote(version_name)}\n"
        f"parent_iteration_id: {parent}\n"
        "source_idea: null\n"
        "status: defined\n"
        "workflow_state: drafted\n"
        'hypothesis: ""\n'
        'verdict: ""\n'
        "metrics:\n"
        "  total_return_pct: null\n"
        "  sharpe: null\n"
        "  max_drawdown: null\n"
        "  profit_factor: null\n"
        "  win_rate: null\n"
        "  trades: null\n"
        "  period: null\n"
        "result_ids: []\n"
        f"created_at: {day}\n"
        f"updated: {day}\n"
        "tags: [trading]\n"
        "---\n"
        "\n"
        f"# {title}\n"
        "\n"
        "## Hypothese\n"
        "\n"
        "_Was genau wird getestet? Bei einer Baseline: „Nullmessung, keine echte Hypothese.“_\n"
        "\n"
        "## Setup\n"
        "\n"
        f"- **Basis:** {basis}\n"
        "- **Änderung:** _Was ist neu gegenüber der Parent-Iteration?_\n"
        "- **Indikatoren / Regeln:** _Chain, Entry-/Exit-Bedingungen_\n"
        "- **Param-Raster / Werte:** _Multiparameter-Lauf oder feste Werte_\n"
        "- **Fenster / Testset:** _Symbol, Zeitraum, Track (A/B/OOS)_\n"
        "- **Sizing / Portfolio:** _value-100 / percent100, tp/sl/td_\n"
        "\n"
        f"## Run-Journal — {day}\n"
        "\n"
        "_Vor dem ersten Lauf anlegen; nach jeder Status-Änderung sofort haken._\n"
        "\n"
        "- [ ] Run <id> gestartet (<kurzkommentar>)\n"
        "- [ ] Run <id> completed → Result <id>\n"
        "- [ ] Metriken in Iter-Notiz übernommen\n"
        "- [ ] status.md aktualisiert\n"
        "- [ ] Bestwerte/Favoriten markiert\n"
        "\n"
        "## Ergebnisse\n"
        "\n"
        "_Erst ausfüllen wenn `workflow_state: results_in`._\n"
        "\n"
        "### Kennzahlen\n"
        "\n"
        "| Metrik | Wert |\n"
        "|---|---|\n"
        "| Total Return | — |\n"
        "| Sharpe | — |\n"
        "| Max DD | — |\n"
        "| Profitfaktor | — |\n"
        "| Winrate | — |\n"
        "| Trades | — |\n"
        "\n"
        "### Bemerkenswerte Beobachtungen\n"
        "\n"
        "_Muster, Überraschungen, Widersprüche zur Hypothese?_\n"
        "\n"
        "## Verdict\n"
        "\n"
        "_Erst ausfüllen wenn `workflow_state: verdict_set`._\n"
        "\n"
        "## Lesson-Extrakt\n"
        "\n"
        "_Erst ausfüllen wenn `workflow_state: lesson_extracted`. Verlinkt auf `lessons/<topic>.md` wenn generalisierbar._\n"
        "\n"
        "## Nächste Schritte\n"
        "\n"
        "_Offene Punkte, Folge-Hypothesen, Backlog-Items._\n"
        "\n"
        "## Verwandt\n"
        "\n"
        "- _Links zu Parent-Iter, Ideen-Notiz (source_idea), Lessons, Status, verwandten Iters_\n"
    )

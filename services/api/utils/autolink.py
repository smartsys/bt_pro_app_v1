"""Auto-Linking von URLs und projektinternen Pfaden in Deutungstexten (Ticket 85).

Der Abschlussbericht eines Skill-Laufs schreibt Verweise auf das Sieger-Setup
(``?setupid=N``) und den finalen Analyse-Lauf (``/backtest/runs/{id}/analyse``)
als Freitext in ``interpretation_text`` (siehe Modell-Docstring von
``TestSetRunFinding``). Diese Funktion erkennt genau diese drei Muster —
vollständige ``http(s)``-URLs, den Analyse-Pfad und den Setup-Deeplink — und
rendert sie als klickbare Links. Alles andere bleibt reiner Text.

**Kein XSS-Risiko:** Der komplette Eingabetext läuft durch ``markupsafe.escape``,
bevor irgendetwas zusammengesetzt wird — auch der Text innerhalb der erkannten
Links. Es gibt keinen Pfad, auf dem roher, ungefilterter Text ins Ergebnis
gelangt.
"""

import re
from typing import Optional

from markupsafe import Markup, escape

# Drei Muster, die im Abschlussbericht vorkommen (siehe SKILL.md Phase 8):
# vollständige URLs, der Analyse-Pfad und der Setup-Deeplink (ohne führenden Pfad,
# der Playground liest ihn über die eigene Route).
_LINK_PATTERN = re.compile(
    r'(?P<url>https?://[^\s<>"\']+)'
    r'|(?P<analyse>/backtest/runs/\d+/analyse)'
    r'|(?P<setupid>\?setupid=\d+)'
)


def autolink_html(text: Optional[str]) -> Markup:
    """Escaped einen Deutungstext und verlinkt erkannte URLs/Pfade darin.

    Args:
        text: Roher Deutungstext (``interpretation.text``), kann None sein.

    Returns:
        Sicheres HTML-Fragment (``markupsafe.Markup``) — in Templates ohne
        weiteres ``|safe`` einsetzbar.
    """
    if not text:
        return Markup('')

    parts = []
    pos = 0
    for match in _LINK_PATTERN.finditer(text):
        parts.append(escape(text[pos:match.start()]))
        matched = match.group(0)
        if match.group('setupid'):
            href = '/chart-playground' + matched
        else:
            href = matched
        parts.append(Markup('<a href="{}" target="_blank" rel="noopener">{}</a>').format(href, matched))
        pos = match.end()
    parts.append(escape(text[pos:]))
    return Markup('').join(parts)

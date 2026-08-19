"""Tests für das Auto-Linking von URLs/Pfaden in Befund-Deutungstexten.

Reine Unit-Tests ohne DB — `autolink_html` ist eine pure Funktion.
"""

from services.api.utils.autolink import autolink_html


def test_setupid_deeplink_is_linked():
    result = str(autolink_html('Sieger-Setup: ?setupid=42 laden.'))
    assert '<a href="/chart-playground?setupid=42"' in result
    assert '>?setupid=42</a>' in result


def test_analyse_path_is_linked():
    result = str(autolink_html('Finale Analyse: /backtest/runs/123/analyse ansehen.'))
    assert '<a href="/backtest/runs/123/analyse"' in result
    assert '>/backtest/runs/123/analyse</a>' in result


def test_full_url_is_linked():
    result = str(autolink_html('Siehe https://example.com/report für Details.'))
    assert '<a href="https://example.com/report"' in result


def test_plain_text_stays_unchanged():
    text = 'Reiner Deutungstext ohne jeden Verweis. Nichts wird verlinkt.'
    result = str(autolink_html(text))
    assert result == text
    assert '<a ' not in result


def test_html_in_text_is_escaped_not_injected():
    """Kein XSS: HTML im Deutungstext landet escaped im Ergebnis, nicht als Markup."""
    text = 'Text mit <script>alert(1)</script> und "Anführungszeichen".'
    result = str(autolink_html(text))
    assert '<script>' not in result
    assert '&lt;script&gt;' in result


def test_none_and_empty_text_return_empty_string():
    assert str(autolink_html(None)) == ''
    assert str(autolink_html('')) == ''


def test_mixed_text_links_only_the_recognized_patterns():
    text = 'Vorher-Text, ?setupid=7, Mitte, /backtest/runs/9/analyse, Nachher-Text.'
    result = str(autolink_html(text))
    assert 'Vorher-Text, ' in result
    assert ', Mitte, ' in result
    assert ', Nachher-Text.' in result
    assert result.count('<a ') == 2

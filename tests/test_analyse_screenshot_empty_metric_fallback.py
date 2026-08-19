"""
Test: Leerer ``metric``-Query-Parameter fällt in der Analyse-Screenshot-Route auf die
Standard-Metrik zurück (Nachtrag).

``metric=`` ist ein gesetzter leerer String, nicht ein fehlender Parameter — der
Query-Default von FastAPI greift dann nicht. Ohne Normalisierung landet der leere Wert
unverändert in der gebauten Analyse-URL, die Seite meldet „Unbekannte Metrik: " und die
Route scheitert erst nach dem Renderer-Lauf mit HTTP 502.

``z`` hat eine andere, ausdrücklich gewollte Leer-Semantik (leer = kein Slider) und darf
von diesem Fallback nicht betroffen sein — das prüft dieser Test mit ab.
"""

from urllib.parse import parse_qs, urlparse

from services.api.routes.api_analyse_screenshot import STANDARD_METRIC, build_analyse_url, _resolve_metric


def test_empty_metric_query_param_falls_back_to_standard_metric() -> None:
    """Ein leerer metric-Wert wird vor dem URL-Bau auf STANDARD_METRIC normalisiert."""
    resolved_metric = _resolve_metric('')

    assert resolved_metric == STANDARD_METRIC


def test_whitespace_only_metric_query_param_falls_back_to_standard_metric() -> None:
    """Ein Whitespace-only metric-Wert zählt ebenfalls als leer."""
    resolved_metric = _resolve_metric('   ')

    assert resolved_metric == STANDARD_METRIC


def test_non_empty_metric_query_param_passes_through_unchanged() -> None:
    """Ein gesetzter Metrik-Name bleibt unverändert — kein Eingriff in gültige Werte."""
    resolved_metric = _resolve_metric('sharpe_ratio')

    assert resolved_metric == 'sharpe_ratio'


def test_built_analyse_url_uses_standard_metric_when_metric_param_is_empty() -> None:
    """Die gebaute Analyse-URL trägt bei metric='' die Standard-Metrik, kein leeres Feld."""
    analyse_url = build_analyse_url(
        run_id=866,
        x='supertrend_period',
        y='supertrend_multiplier',
        agg='avg',
        metric=_resolve_metric(''),
        z='',
        x2=None,
        y2=None,
        agg2=None,
        z2=None,
    )

    query_params = parse_qs(urlparse(analyse_url).query, keep_blank_values=True)

    assert query_params['metric'] == [STANDARD_METRIC]


def test_built_analyse_url_keeps_empty_slider_empty_when_metric_is_empty() -> None:
    """Der Fix an metric darf die Slider-Semantik (leer = kein Slider) nicht verändern."""
    analyse_url = build_analyse_url(
        run_id=866,
        x='supertrend_period',
        y='supertrend_multiplier',
        agg='avg',
        metric=_resolve_metric(''),
        z='',
        x2=None,
        y2=None,
        agg2=None,
        z2='',
    )

    query_params = parse_qs(urlparse(analyse_url).query, keep_blank_values=True)

    assert query_params['z'] == ['']
    assert query_params['z2'] == ['']

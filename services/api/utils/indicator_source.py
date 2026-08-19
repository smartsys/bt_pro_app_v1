"""Herkunft des Indikator-Rasters — gespeicherte IndicatorConfig oder inline (Ticket 102).

Testset-Lauf und Preflight nehmen das Parameter-Raster wahlweise über die ID einer
gespeicherten IndicatorConfig oder inline als Dict. Genau eines von beiden ist Pflicht;
die Regel liegt hier, damit beide Routen denselben Klartext-Grund melden statt zweier
abweichender Formulierungen.
"""

from typing import Any, Dict, Optional


def require_exactly_one_indicator_source(
    indicator_config_id: Optional[int],
    indicators: Optional[Dict[str, Any]],
) -> None:
    """Prüft, dass genau eine Raster-Quelle angegeben ist.

    Bewusst ohne Vorrangregel: sind beide oder keine Angabe gesetzt, scheitert der
    Aufruf mit einem Grund im Klartext, statt still eine der beiden zu bevorzugen.

    Args:
        indicator_config_id: ID einer gespeicherten IndicatorConfig oder None.
        indicators: Inline übergebenes Parameter-Raster (Inhalt von ``config_json``)
            oder None.

    Raises:
        ValueError: Wenn beide oder keine der beiden Angaben gesetzt sind.
    """
    if indicator_config_id is not None and indicators is not None:
        raise ValueError(
            'indicator_config_id und indicators schließen sich aus — genau eine '
            'Raster-Quelle angeben.'
        )
    if indicator_config_id is None and indicators is None:
        raise ValueError(
            'Es fehlt das Indikator-Raster: entweder indicator_config_id (gespeicherte '
            'IndicatorConfig) oder indicators (Raster inline) angeben — genau eines von beiden.'
        )

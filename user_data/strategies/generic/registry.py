"""Indikator-Registry für den Generic Spec Runner.

Löst Indikator-Typ-IDs (z.B. 'dwsFastSMA', 'vbt:SUPERTREND', 'talib:SMA',
'custom:dwsFastSMA') auf die zugehörige VBT IndicatorFactory auf.

Diese Funktion wird sowohl vom Spec Runner als auch vom Chart Playground
(services/api/routes/api_chart_playground.py) genutzt - zentrale Stelle,
damit beide Seiten denselben Auflösungs-Mechanismus verwenden.
"""

import importlib
from typing import Any

import vectorbtpro as vbt


_CUSTOM_MODULE_PATH = 'user_data.utils.indicators.custom'


def resolve_indicator_factory(type_id: str) -> Any:
    """Löst eine Indikator-Typ-ID auf eine VBT IndicatorFactory auf.

    Unterstützte Formen:
        - 'dwsFastSMA'        -> user_data.utils.indicators.custom.dwsFastSMA
        - 'custom:dwsFastSMA' -> dasselbe
        - 'vbt:SUPERTREND'    -> vbt.indicator('vbt:SUPERTREND')
        - 'talib:SMA'         -> vbt.indicator('talib:SMA')

    Args:
        type_id: Typ-ID aus dem Spec.

    Returns:
        VBT IndicatorFactory-Objekt mit input_names/param_names/output_names/run.

    Raises:
        ValueError: Wenn der Indikator nicht gefunden wird.
    """
    if not isinstance(type_id, str) or not type_id:
        raise ValueError(f'Ungültige Indikator-Typ-ID: {type_id!r}')

    # Custom-Indikator (mit oder ohne 'custom:'-Präfix)
    if type_id.startswith('custom:'):
        name = type_id.split(':', 1)[1]
        return _load_custom(name)

    # Ohne Präfix und ohne ':' -> zuerst als Custom probieren
    if ':' not in type_id:
        try:
            return _load_custom(type_id)
        except ValueError:
            # Fallback: VBT-Indikator ohne Gruppe
            pass

    try:
        return vbt.indicator(type_id)
    except Exception as e:
        raise ValueError(f'Indikator {type_id!r} nicht gefunden: {e}')


def _load_custom(name: str) -> Any:
    module = importlib.import_module(_CUSTOM_MODULE_PATH)
    factory = getattr(module, name, None)
    if factory is None:
        raise ValueError(f'Custom-Indikator {name!r} nicht gefunden in {_CUSTOM_MODULE_PATH}')
    return factory

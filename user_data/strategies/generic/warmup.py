"""Vorlauf-Prüfung: reicht die Historie für die längste konfigurierte Indikator-Periode?

Ein Indikator mit Periode n braucht n Balken Historie, bevor er einen belastbaren Wert
liefert. Deshalb lädt das System Kerzen ab ``ohlc_start``, handelt aber erst ab ``start``
— der Abstand dazwischen ist der Vorlauf. Ist er kürzer als die längste konfigurierte
Periode, tragen die ersten Balken des Handelsfensters still falsche Indikatorwerte. Bei
``ohlc_start == start`` gibt es überhaupt keinen Vorlauf.

Dieses Modul ist die **einzige** Stelle, die das ausrechnet: Run-Start (Worker) und
Preflight rufen dieselben Funktionen auf, damit kein zweiter Rechenweg entsteht — dasselbe
Prinzip wie bei ``count_total_combos`` für die Kombinationszahl.

Wie eine Periode erkannt wird: VBT trägt an einem Indikator keine Semantik zu seinen
Parametern (``IndicatorBase`` kennt nur ``param_names``/``param_defaults``/``output_flags``
— am 13.08.2026 im vbt-Kernel geprüft). Ob ein Parameter eine Fensterlänge ist, lässt sich
deshalb nur am Namen entscheiden; ``_PERIOD_NAME_PATTERN`` hält diese Regel an einer Stelle
fest. Nicht-Perioden wie ``multiplier``, ``below_pct``, ``threshold``, ``prob``, ``seed``
oder ``value`` fallen dadurch heraus.
"""

import math
import re
from typing import Any, Optional

import pandas as pd

from user_data.strategies.generic.tf_resample import TF_SAME, tf_to_timedelta

# Parameternamen, die eine Fensterlänge in Balken bezeichnen. Deckt TA-Lib
# (timeperiod, fastperiod, slowperiod, signalperiod, fastk_period, ...) und die
# Custom-Indikatoren (length, k_length, window, smooth1, smooth2) ab.
_PERIOD_NAME_PATTERN = re.compile(r'period|length|window|span|lookback|smooth', re.IGNORECASE)

# Zusätzliche Perioden-Parameter, deren Name das Muster nicht trifft. 'signal' ist die
# Glättungslänge des dwsSMI.
_PERIOD_NAME_EXTRAS = {'signal'}


def is_period_param(param_name: str) -> bool:
    """Sagt, ob ein Indikator-Parameter eine Fensterlänge in Balken bezeichnet.

    Args:
        param_name: Name des Parameters aus der IndicatorConfig (z.B. 'length').

    Returns:
        True, wenn der Name als Periode zählt.
    """
    if param_name in _PERIOD_NAME_EXTRAS:
        return True
    return _PERIOD_NAME_PATTERN.search(param_name) is not None


def _tf_factor(indicator_tf: Optional[str], base_timeframe: Optional[str]) -> int:
    """Wie viele Basis-Balken ein Balken des Indikator-Timeframes umfasst.

    Ein Indikator, der auf einem gröberen Timeframe rechnet, braucht seine Periode in
    dessen Balken — umgerechnet auf das Basis-Raster entsprechend mehr.

    Args:
        indicator_tf: Per-Indikator-Timeframe ('same' oder z.B. '1d').
        base_timeframe: Timeframe der geladenen Kerzen (z.B. '4h'); None -> Faktor 1.

    Returns:
        Ganzzahliger Faktor, mindestens 1.
    """
    if not isinstance(indicator_tf, str) or indicator_tf.strip() == '':
        return 1
    trimmed = indicator_tf.strip()
    if trimmed.lower() == TF_SAME:
        return 1
    if base_timeframe is None or str(base_timeframe).strip() == '':
        return 1
    if trimmed.lower() == str(base_timeframe).strip().lower():
        return 1
    ratio = tf_to_timedelta(trimmed) / tf_to_timedelta(str(base_timeframe))
    return max(1, math.ceil(ratio))


def longest_indicator_period(
    indicators_json: dict,
    base_timeframe: Optional[str] = None,
) -> dict:
    """Größte Perioden-Länge über alle aktiven Indikatoren, in Basis-Balken.

    Bei einem Multiparameter-Lauf ist ein Parameter ein Wertebereich (arange-Dict oder
    Liste) — dann zählt der **größte** Wert des Rasters, nicht der Startwert. Die
    Aufschlüsselung der Werte kommt von ``describe_indicator_params``, damit die
    Range-Expansion nicht ein zweites Mal implementiert wird. Stops (``_stops``) sind
    keine Perioden und werden von ``describe_indicator_params`` bereits ausgelassen.

    Args:
        indicators_json: Indikator-Spec aus der IndicatorConfig (``config_json``).
        base_timeframe: Timeframe der geladenen Kerzen (z.B. '4h'). Wird gebraucht, um
            die Periode eines Indikators mit eigenem, gröberem tf auf Basis-Balken
            umzurechnen. None -> keine Umrechnung (Faktor 1).

    Returns:
        Dict mit:
        - ``bars``: längste Periode in Basis-Balken (0, wenn keine Periode konfiguriert ist)
        - ``indicator``: ID des Indikators, der sie stellt (None bei ``bars`` = 0)
        - ``param``: Name des Parameters (None bei ``bars`` = 0)
        - ``value``: der größte Rasterwert dieses Parameters (None bei ``bars`` = 0)
        - ``timeframe``: tf des Indikators wie konfiguriert (None bei ``bars`` = 0)
        - ``tf_factor``: Umrechnungsfaktor tf -> Basis-Balken
        - ``source``: lesbare Herkunft, z.B. 'vwma.length' (None bei ``bars`` = 0)
    """
    # Lokaler Import: indicator_factory zieht vectorbtpro nach — dieses Modul soll
    # dadurch nicht schon beim Import schwer werden.
    from user_data.strategies.generic.indicator_factory import describe_indicator_params

    best: dict = {
        'bars': 0,
        'indicator': None,
        'param': None,
        'value': None,
        'timeframe': None,
        'tf_factor': 1,
        'source': None,
    }

    for ind_id, params in describe_indicator_params(indicators_json or {}):
        entry = (indicators_json or {}).get(ind_id) or {}
        indicator_tf = entry.get('tf')
        factor = _tf_factor(indicator_tf, base_timeframe)
        for param_name, values in params:
            if not is_period_param(param_name):
                continue
            numeric = [
                float(v) for v in values
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            ]
            if not numeric:
                continue
            max_value = max(numeric)
            if max_value <= 0:
                continue
            bars = math.ceil(max_value) * factor
            if bars > best['bars']:
                best = {
                    'bars': int(bars),
                    'indicator': ind_id,
                    'param': param_name,
                    'value': int(max_value) if float(max_value).is_integer() else max_value,
                    'timeframe': indicator_tf,
                    'tf_factor': factor,
                    'source': f'{ind_id}.{param_name}',
                }

    return best


def _bars_between(earlier: Any, later: Any, base_timeframe: str) -> int:
    """Zahl der Basis-Balken zwischen zwei Zeitpunkten (abgerundet, mindestens 0)."""
    delta = pd.Timestamp(later) - pd.Timestamp(earlier)
    if delta.total_seconds() <= 0:
        return 0
    return int(delta / tf_to_timedelta(base_timeframe))


def check_warmup(backtest_config: dict, indicators_json: dict) -> dict:
    """Vergleicht den konfigurierten Vorlauf mit der längsten Indikator-Periode.

    Rein aus den Eckdaten der BacktestConfig gerechnet (``ohlc_start``, ``start``, ``end``,
    ``timeframe``) — es werden keine Kerzen geladen. Damit ist der Aufruf billig genug für
    den Preflight und liefert dort exakt dasselbe Ergebnis wie beim Run-Start.

    Stufen:
    - ``ok``: der Vorlauf deckt die längste Periode ab (oder es ist keine konfiguriert).
    - ``warning``: der Vorlauf ist kürzer als die Periode — die ersten Balken des
      Handelsfensters tragen unvollständig aufgewärmte Indikatorwerte. Bei
      ``ohlc_start == start`` ist das immer der Fall.
    - ``insufficient_history``: schon das gesamte Datenfenster (``ohlc_start``..``end``)
      ist kürzer als die Periode — der Indikator kann überhaupt keinen Wert liefern.

    Args:
        backtest_config: BacktestConfig-Dict mit 'ohlc_start', 'start', 'end', 'timeframe'.
        indicators_json: Indikator-Spec aus der IndicatorConfig.

    Returns:
        Dict mit ``level``, ``note`` (lesbarer deutscher Satz), ``warmup_bars``,
        ``required_bars``, ``available_bars``, ``source`` sowie ``period`` (die volle
        Rückgabe von ``longest_indicator_period``).

    Raises:
        KeyError: Wenn 'ohlc_start', 'start', 'end' oder 'timeframe' fehlen.
    """
    ohlc_start = backtest_config['ohlc_start']
    start = backtest_config['start']
    end = backtest_config['end']
    base_timeframe = backtest_config['timeframe']

    period = longest_indicator_period(indicators_json, base_timeframe)
    required_bars = period['bars']
    warmup_bars = _bars_between(ohlc_start, start, base_timeframe)
    available_bars = _bars_between(ohlc_start, end, base_timeframe)

    tf_hint = ''
    if period['tf_factor'] > 1:
        tf_hint = (
            f", gerechnet auf tf {period['timeframe']} "
            f"= {period['tf_factor']} Basis-Balken je Periode-Balken"
        )

    if required_bars <= 0:
        return {
            'level': 'ok',
            'note': (
                f'Keine Indikator-Periode konfiguriert — ein Vorlauf wird nicht gebraucht. '
                f'Vorhanden sind {warmup_bars} Balken zwischen ohlc_start ({ohlc_start}) '
                f'und start ({start}).'
            ),
            'warmup_bars': warmup_bars,
            'required_bars': 0,
            'available_bars': available_bars,
            'source': None,
            'period': period,
        }

    source_text = (
        f"{period['source']} = {period['value']}{tf_hint}"
    )

    if available_bars < required_bars:
        level = 'insufficient_history'
        note = (
            f'Historie reicht nicht: Zwischen ohlc_start ({ohlc_start}) und end ({end}) '
            f'liegen nur {available_bars} Balken ({base_timeframe}), die längste '
            f'konfigurierte Indikator-Periode braucht {required_bars} Balken '
            f'({source_text}). Der Indikator kann in diesem Fenster keinen Wert liefern.'
        )
    elif warmup_bars <= 0:
        level = 'warning'
        note = (
            f'Kein Vorlauf: ohlc_start ({ohlc_start}) fällt mit start ({start}) zusammen. '
            f'Die längste konfigurierte Indikator-Periode braucht {required_bars} Balken '
            f'({source_text}) — die ersten {required_bars} Balken des Handelsfensters '
            f'tragen unvollständig aufgewärmte Indikatorwerte.'
        )
    elif warmup_bars < required_bars:
        level = 'warning'
        note = (
            f'Vorlauf zu kurz: {warmup_bars} Balken ({base_timeframe}) zwischen ohlc_start '
            f'({ohlc_start}) und start ({start}), die längste konfigurierte '
            f'Indikator-Periode braucht {required_bars} Balken ({source_text}) — die ersten '
            f'{required_bars - warmup_bars} Balken des Handelsfensters tragen unvollständig '
            f'aufgewärmte Indikatorwerte.'
        )
    else:
        level = 'ok'
        note = (
            f'Vorlauf ausreichend: {warmup_bars} Balken ({base_timeframe}) zwischen '
            f'ohlc_start ({ohlc_start}) und start ({start}), die längste konfigurierte '
            f'Indikator-Periode braucht {required_bars} Balken ({source_text}).'
        )

    return {
        'level': level,
        'note': note,
        'warmup_bars': warmup_bars,
        'required_bars': required_bars,
        'available_bars': available_bars,
        'source': period['source'],
        'period': period,
    }

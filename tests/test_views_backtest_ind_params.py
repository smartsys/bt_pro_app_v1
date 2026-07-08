"""Tests fuer _resolve_ind_params in views_backtest.py (Ticket 53 — Dual-Praefix).

Seit Ticket 53 benennt indicator_factory.build_indicators die Param-Level jeder
Indikator-Instanz auf den Spec-ID-Namen um (z.B. 'fast_sma_length' statt
'dwsfastsma_length'). Das Result-Chart-Param-Panel loeste die Zuordnung bisher rein
klassenbasiert auf (Klassenname aus cfg['indicator']) — das matcht seit dem Fix nicht
mehr fuer Custom-Indikatoren (Spec-Key != Klasse). _resolve_ind_params prueft beide
Praefixe (Klasse UND Spec-Key), damit das Panel unabhaengig vom Alter des Results
Werte anzeigt.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.api.routes.views_backtest import _resolve_ind_params


class TestResolveIndParams:
    """Dual-Praefix-Aufloesung: Klassenname UND Spec-Key werden geprueft."""

    def test_class_based_prefix_matches_pre_ticket53_results(self) -> None:
        """Alte Results (vor Ticket 53): Param-Namen tragen den Klassen-Praefix."""
        ind_config = {'fast_sma': {'indicator': 'custom:dwsFastSMA'}}
        actual_params = {'dwsfastsma_length': 10, 'dwsfastsma_multiplier': 2}
        result = _resolve_ind_params(ind_config, actual_params)
        assert result == {'fast_sma': {'length': 10, 'multiplier': 2}}

    def test_spec_key_based_prefix_matches_post_ticket53_results(self) -> None:
        """Neue Results (ab Ticket 53): Param-Namen tragen den Spec-Key-Praefix."""
        ind_config = {'fast_sma': {'indicator': 'custom:dwsFastSMA'}}
        actual_params = {'fast_sma_length': 10, 'fast_sma_multiplier': 2}
        result = _resolve_ind_params(ind_config, actual_params)
        assert result == {'fast_sma': {'length': 10, 'multiplier': 2}}

    def test_directly_referenced_custom_indicator_pre_existing_defect_healed(self) -> None:
        """Bestandsdefekt: direkt referenzierte Custom-Indikatoren (z.B. vwma) wurden
        schon vor Ticket 53 von _uniquify_param_levels auf den Spec-Key umbenannt —
        das rein klassenbasierte Praefix matchte dort nie. Dual-Praefix heilt das mit."""
        ind_config = {'vwma': {'indicator': 'custom:dwsVWMA'}}
        actual_params = {'vwma_length': 15, 'vwma_below_pct': 3}
        result = _resolve_ind_params(ind_config, actual_params)
        assert result == {'vwma': {'length': 15, 'below_pct': 3}}

    def test_talib_indicator_class_equals_spec_key(self) -> None:
        """Talib-Indikatoren: Klasse und Spec-Key faellt oft zusammen — unveraendertes Verhalten."""
        ind_config = {'sma': {'indicator': 'talib:SMA'}}
        actual_params = {'sma_timeperiod': 14}
        result = _resolve_ind_params(ind_config, actual_params)
        assert result == {'sma': {'timeperiod': 14}}

    def test_multiple_indicators_each_resolved_independently(self) -> None:
        ind_config = {
            'fast_sma': {'indicator': 'custom:dwsFastSMA'},
            'vwma': {'indicator': 'custom:dwsVWMA'},
        }
        actual_params = {
            'fast_sma_length': 5, 'fast_sma_multiplier': 1,
            'vwma_length': 20, 'vwma_below_pct': 2,
            'symbol': 'BTCUSDT',
        }
        result = _resolve_ind_params(ind_config, actual_params)
        assert result == {
            'fast_sma': {'length': 5, 'multiplier': 1},
            'vwma': {'length': 20, 'below_pct': 2},
        }

    def test_indicator_without_matching_params_is_omitted(self) -> None:
        """Kein Treffer (weder Klasse noch Spec-Key) -> Indikator fehlt im Ergebnis."""
        ind_config = {'unused': {'indicator': 'custom:dwsSomethingElse'}}
        actual_params = {'fast_sma_length': 5}
        result = _resolve_ind_params(ind_config, actual_params)
        assert result == {}

    def test_missing_indicator_field_falls_back_to_spec_key_only(self) -> None:
        """Fehlendes 'indicator'-Feld -> nur Spec-Key-Praefix greift, kein Crash."""
        ind_config = {'fast_sma': {}}
        actual_params = {'fast_sma_length': 5}
        result = _resolve_ind_params(ind_config, actual_params)
        assert result == {'fast_sma': {'length': 5}}

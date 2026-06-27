"""Test für den Empty-Portfolio-Guard in save_strategy_results (Audit-Fund).

Ein Portfolio mit 0 Parameter-Kombinationen (leere Spalten) entsteht, wenn keine
OHLCV-Daten geladen wurden (fehlendes Symbol oder leerer Zeitbereich).
save_strategy_results muss diesen Fehlzustand sichtbar mit ValueError abweisen,
statt in einen kryptischen IndexError zu laufen oder den Backtest-Run beim
aufrufenden Job still als 'completed' werten zu lassen.

Der Guard greift vor jeder DB-Interaktion (vor get_engine()), daher braucht der
Test keine Datenbank.
"""

import pytest

from user_data.utils.database.repository import save_strategy_results


class _EmptyWrapper:
    """Minimaler Stand-in für portfolios.wrapper mit leeren Spalten."""
    columns: list = []


class _EmptyPortfolio:
    """Minimaler Stand-in für ein vbt.Portfolio ohne Kombinationen."""
    wrapper = _EmptyWrapper()


def test_save_strategy_results_rejects_empty_portfolio() -> None:
    """0 Kombinationen werden mit klarer Fehlermeldung abgewiesen (kein IndexError)."""
    with pytest.raises(ValueError, match="Keine Parameter-Kombinationen"):
        save_strategy_results(
            run_id=1,
            strategy_results={'portfolios': _EmptyPortfolio()},
            spec_runner_version="test",
        )

"""Verhaltenszusagen von VBT, auf denen die risikobasierte Positionsgröße steht.

Die risikobasierte Größe (``size_type='risk_percent'``) rechnet die Ordergröße
zur Laufzeit in der Signal-Funktion und schreibt sie in dasselbe Array, das
``from_signals`` als ``size`` liest. Dass das trägt, ist keine dokumentierte
Zusage, sondern am Container gemessenes Verhalten — und damit etwas, das ein
VBT-Update brechen kann. Diese Datei hält die Messungen fest:

  1. Ein aus der Signal-Funktion beschriebenes ``size``-Array wirkt: VBT kopiert
     das übergebene Array beim Broadcast nicht, solange sich seine Form nicht
     ändert.
  2. Der laufende Kontostand ist an der Signalstelle je Spalte lesbar
     (``c.last_value[c.group]``) — keine Spalte-0-Falle.
  3. Ohne Kreditlinie ist die Risikoregel nicht ungenau, sondern wirkungslos:
     VBT kürzt still auf das verfügbare Geld.
  4. Eine Limit-Order übernimmt die Größe des Balkens, an dem sie **gestellt**
     wurde, nicht die des Füllbalkens.
  5. ``from_ago`` verschiebt die Lesestelle der Größe — deshalb ist die
     Kombination mit ``risk_percent`` verriegelt statt vorgebaut.

Kein Mocking: alle Messungen laufen gegen ``vbt.Portfolio.from_signals``.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import vectorbtpro as vbt
from numba import njit

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from user_data.strategies.generic.risk_sizing import (  # noqa: E402
    build_risk_sizing_spec,
)

_N_BARS = 60
_INDEX = pd.date_range('2024-01-01', periods=_N_BARS, freq='1h')


@njit
def _entry_at_bar_nb(c, size_arr, entry_bar, write_size):
    """Signal-Funktion: ein Einstieg an ``entry_bar``, Größe optional geschrieben."""
    is_entry = c.i == entry_bar
    if is_entry and write_size > 0.0:
        size_arr[c.i, c.col] = write_size
    return is_entry, False, False, False


@njit
def _record_account_value_nb(c, size_arr, seen_value, seen_group, entry_bar):
    """Signal-Funktion: schreibt den an der Signalstelle lesbaren Kontowert mit."""
    seen_value[c.i, c.col] = c.last_value[c.group]
    seen_group[c.i, c.col] = c.group
    is_entry = c.i == entry_bar
    if is_entry:
        size_arr[c.i, c.col] = 10.0 * (c.col + 1)
    return is_entry, False, False, False


@njit
def _risk_entry_nb(c, size_arr, entry_mask, exit_mask, risk_pct, stop_distance):
    """Signal-Funktion mit der Risikoregel: Größe = Kontowert x risk_pct / Abstand."""
    is_entry = entry_mask[c.i]
    is_exit = exit_mask[c.i]
    if is_entry:
        size_arr[c.i, c.col] = (c.last_value[c.group] * risk_pct) / stop_distance
    return is_entry, is_exit, False, False


def _rising_close() -> pd.Series:
    return pd.Series(100.0 + np.arange(_N_BARS) * 0.1, index=_INDEX)


class TestSizeArrayFromSignalFunc:
    """Messung 1: Das beschriebene size-Array wirkt."""

    def test_size_written_in_signal_func_reaches_the_order(self):
        close = _rising_close()

        def _run(write_size: float):
            size_arr = np.full((_N_BARS, 1), 1.0)
            portfolio = vbt.Portfolio.from_signals(
                close,
                signal_func_nb=_entry_at_bar_nb,
                signal_args=(size_arr, 10, write_size),
                size=size_arr,
                size_type='amount',
                init_cash=10_000.0,
                freq='1h',
            )
            return portfolio, size_arr

        untouched, _ = _run(0.0)
        written, size_arr = _run(5.0)

        assert float(untouched.orders.values['size'][0]) == 1.0
        assert float(written.orders.values['size'][0]) == 5.0
        assert size_arr[10, 0] == 5.0, (
            'Die Signal-Funktion muss in genau das Array schreiben, das VBT liest'
        )
        assert float(np.ravel(written.value.iloc[-1])[0]) != float(
            np.ravel(untouched.value.iloc[-1])[0]
        )


class TestAccountValuePerColumn:
    """Messung 2: Der Kontowert an der Signalstelle gehört zur eigenen Spalte."""

    def test_account_value_is_read_per_column_not_from_column_zero(self):
        # Drei Spalten mit auseinanderlaufenden Kursen -> auseinanderlaufende Konten.
        close = pd.DataFrame(
            {
                'a': 100.0 + np.arange(_N_BARS) * 0.1,
                'b': 100.0 + np.arange(_N_BARS) * 0.5,
                'c': 100.0 + np.arange(_N_BARS) * 1.0,
            },
            index=_INDEX,
        )
        size_arr = np.full((_N_BARS, 3), np.inf)
        seen_value = np.full((_N_BARS, 3), np.nan)
        seen_group = np.full((_N_BARS, 3), -1, dtype=np.int64)
        portfolio = vbt.Portfolio.from_signals(
            close,
            signal_func_nb=_record_account_value_nb,
            signal_args=(size_arr, seen_value, seen_group, 5),
            size=size_arr,
            size_type='amount',
            init_cash=10_000.0,
            freq='1h',
        )

        # Ohne cash_sharing ist jede Spalte ihre eigene Gruppe.
        assert (seen_group == np.arange(3)).all()

        value = portfolio.value
        for bar in (20, 40, 55):
            for col in range(3):
                assert seen_value[bar, col] == pytest.approx(
                    float(value.iloc[bar - 1, col]), rel=1e-12
                )
        # Die Spalten laufen wirklich auseinander — sonst wäre der Nachweis leer.
        assert len(set(np.round(seen_value[40], 6))) == 3


class TestSilentTruncationWithoutLeverage:
    """Messung 3: Ohne Kreditlinie ist die Risikoregel wirkungslos, nicht ungenau."""

    def test_without_leverage_orders_are_cut_to_the_available_cash(self):
        # Stopabstand 0,6 bei Kurs ~100: die Risikoregel verlangt eine Nominale von
        # rund dem Fünffachen des Kontos — ohne Kreditlinie unmöglich, mit dem
        # zehnfachen Hebel dagegen genau darstellbar.
        close = _rising_close()
        entry_mask = np.zeros(_N_BARS, dtype=np.bool_)
        entry_mask[[5, 25, 45]] = True
        exit_mask = np.zeros(_N_BARS, dtype=np.bool_)
        exit_mask[[15, 35, 55]] = True

        def _run(leverage: float):
            size_arr = np.full((_N_BARS, 1), np.inf)
            portfolio = vbt.Portfolio.from_signals(
                close,
                signal_func_nb=_risk_entry_nb,
                signal_args=(size_arr, entry_mask, exit_mask, 0.03, 0.6),
                size=size_arr,
                size_type='amount',
                init_cash=10_000.0,
                leverage=leverage,
                freq='1h',
            )
            return portfolio, size_arr

        without, wanted_without = _run(1.0)
        with_credit, wanted_with = _run(10.0)

        orders_without = without.orders.values
        buys_without = orders_without[orders_without['side'] == 0]
        executed = buys_without['size']
        desired = wanted_without[buys_without['idx'], buys_without['col']]

        assert len(executed) >= 3
        assert (executed < desired * (1 - 1e-9)).all(), (
            'Ohne Kreditlinie muss jede dieser Orders gekürzt werden'
        )
        # Aus der variablen Größe wird faktisch eine vom Konto begrenzte: die
        # Nominale bleibt beim Kontowert stehen, statt dem Risiko zu folgen.
        assert (executed < desired * 0.5).all()

        orders_with = with_credit.orders.values
        buys_with = orders_with[orders_with['side'] == 0]
        desired_with = wanted_with[buys_with['idx'], buys_with['col']]
        assert buys_with['size'] == pytest.approx(desired_with, rel=1e-12), (
            'Mit Kreditlinie muss exakt die gewünschte Größe ausgeführt werden'
        )
        assert float(np.ravel(with_credit.value.iloc[-1])[0]) != float(
            np.ravel(without.value.iloc[-1])[0]
        )


class TestLimitOrderSizeSource:
    """Messung 6: Eine Limit-Order trägt die Größe ihres Stell-Balkens."""

    def test_limit_order_uses_the_size_of_the_bar_it_was_placed_on(self):
        # Kurs fällt bis Balken 19 und steigt danach — die Limit-Order füllt spät.
        values = np.concatenate(
            [np.full(10, 100.0), np.linspace(100.0, 96.0, 10), np.linspace(96.0, 105.0, 40)]
        )
        close = pd.Series(values[:_N_BARS], index=_INDEX)
        size_arr = np.zeros((_N_BARS, 1))
        portfolio = vbt.Portfolio.from_signals(
            close,
            signal_func_nb=_entry_at_bar_nb,
            signal_args=(size_arr, 10, 7.0),
            size=size_arr,
            size_type='amount',
            init_cash=100_000.0,
            order_type='limit',
            limit_delta=0.03,
            freq='1h',
        )

        records = portfolio.orders.values
        assert len(records) == 1
        fill_bar = int(records['idx'][0])
        assert fill_bar > 10, 'Die Limit-Order muss später als am Stell-Balken füllen'
        assert size_arr[fill_bar, 0] == 0.0, (
            'Am Füllbalken steht im size-Array nichts — nur so ist der Nachweis aussagekräftig'
        )
        assert float(records['size'][0]) == 7.0


class TestFromAgoShiftsTheSizeLookup:
    """Messung 7 / Anforderung 4: from_ago liest die Größe am falschen Balken."""

    def test_from_ago_reads_the_size_one_bar_earlier(self):
        close = _rising_close()

        def _run(from_ago: int):
            size_arr = np.full((_N_BARS, 1), 1.0)
            portfolio = vbt.Portfolio.from_signals(
                close,
                signal_func_nb=_entry_at_bar_nb,
                signal_args=(size_arr, 10, 7.0),
                size=size_arr,
                size_type='amount',
                init_cash=100_000.0,
                from_ago=from_ago,
                freq='1h',
            )
            return float(portfolio.orders.values['size'][0])

        assert _run(0) == 7.0
        assert _run(1) == 1.0, (
            'Mit from_ago liest VBT size_arr[i - from_ago] — die zur Laufzeit '
            'gerechnete Größe käme nie an'
        )

    def test_risk_percent_together_with_from_ago_is_rejected(self):
        portfolio_cfg = {
            'size_type': 'risk_percent',
            'risk_pct': 0.03,
            'from_ago': 1,
        }
        stops_cfg = {'sl_stop': 0.02, 'delta_format': 'percent'}
        with pytest.raises(ValueError) as exc:
            build_risk_sizing_spec(portfolio_cfg, stops_cfg, stops_swept=False)
        message = str(exc.value)
        assert 'from_ago' in message
        assert '_state_exit_signal_func_nb' in message, (
            'Die Meldung muss die anzupassende Stelle nennen'
        )

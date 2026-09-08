"""Verhaltenszusagen von VBT, auf denen der Hebel je Entry-Block steht.

Der Block-Hebel (Ticket 106) schreibt am Einstiegsbalken den Hebel des feuernden
Regel-Blocks in ein ``leverage``-Array, das zugleich als ``leverage``-Argument an
``from_signals`` geht, und lässt den Lauf im Modus ``lazymult`` rechnen. Dass das
trägt, ist keine dokumentierte Zusage, sondern am Container gemessenes Verhalten —
und damit etwas, das ein VBT-Update still brechen kann. Diese Datei hält die drei
Messungen fest, auf denen die Entscheidung beruht:

  1. **Nur ``lazymult``/``eagermult`` vervielfachen die Größe.** Bei Hebel 2
     bleibt die Nominale in ``lazy``/``eager`` unverändert (der Hebel ist dort
     eine reine Kreditlinie) und verdoppelt sich in ``lazymult``/``eagermult``.
     Für ``value`` und ``amount`` gilt beides; bei ``percent100`` ist die
     Nominale auch in ``lazy`` verdoppelt — das ist ein Nebeneffekt der
     Prozentbasis (Prozent vom Konto **inklusive** Kreditlinie) und kein
     Multiplikator. Darauf darf nichts aufbauen, deshalb steht dieser
     Unterschied hier ausdrücklich mit im Test.
  3. **``leverage`` darf ein Array der Form (T, N) sein, und die Signal-Funktion
     darf es zur Laufzeit beschreiben.** ``lev_arr[i, col] = 3.0`` am
     Einstiegsbalken führt bei fester Summe in ``lazymult`` zur dreifachen
     Größe — derselbe Mechanismus wie beim Size-Array der risikobasierten
     Größe (Ticket 104).
  4. **Unterdeckung wird still gekürzt, nicht gemeldet.** Reicht das Konto für
     die Nominale nicht, kürzt VBT auf Konto x Hebel, ohne dass es auffiele.
     Deshalb bricht der Block-Hebel bei Unterdeckung nicht ab, sondern meldet sie
     über den Weg aus Ticket 104 (Abgleich gewollte gegen ausgeführte Größe).

Die Nummerierung folgt dem Abschnitt „Gemessene VBT-Mechanik" in Ticket 106;
Messung 2 (``lazy`` gegen ``eager``) ist eine reine Auswahlbegründung ohne
Verhaltenszusage und deshalb hier nicht gepinnt.

Kein Mocking: alle Messungen laufen gegen ``vbt.Portfolio.from_signals``.
"""

import numpy as np
import pandas as pd
import pytest
import vectorbtpro as vbt
from numba import njit

_N_BARS = 30
_INDEX = pd.date_range('2024-01-01', periods=_N_BARS, freq='1h')
# Flacher Kurs: die Nominale einer Order ist damit unmittelbar ablesbar und
# hängt nicht daran, an welchem Balken gekauft wurde.
_FLAT_PRICE = 100.0
_ENTRY_BAR = 5
_EXIT_BAR = 20


def _flat_close() -> pd.Series:
    return pd.Series(np.full(_N_BARS, _FLAT_PRICE), index=_INDEX)


def _entry_exit_masks() -> tuple:
    entries = np.zeros(_N_BARS, dtype=np.bool_)
    entries[_ENTRY_BAR] = True
    exits = np.zeros(_N_BARS, dtype=np.bool_)
    exits[_EXIT_BAR] = True
    return entries, exits


def _first_order_nominal(portfolio) -> float:
    """Nominale (Größe x Kurs) der ersten Order eines Portfolios."""
    records = portfolio.orders.values
    assert len(records) >= 1, 'Der Lauf muss eine Order erzeugt haben'
    return float(records['size'][0] * records['price'][0])


@njit
def _entry_with_leverage_nb(c, lev_arr, entry_bar, exit_bar, leverage):
    """Signal-Funktion: schreibt am Einstiegsbalken den Hebel in das leverage-Array."""
    is_entry = c.i == entry_bar
    if is_entry:
        lev_arr[c.i, c.col] = leverage
    return is_entry, c.i == exit_bar, False, False


class TestOnlyMultiplyingModesScaleTheSize:
    """Messung 1: Nur lazymult/eagermult vervielfachen die Größe."""

    @pytest.mark.parametrize(
        'size_type, size_value',
        [('value', 100.0), ('amount', 1.0)],
    )
    def test_absolute_sizes_are_doubled_only_in_the_multiplying_modes(
        self, size_type: str, size_value: float
    ):
        close = _flat_close()
        entries, exits = _entry_exit_masks()

        def _run(leverage: float, leverage_mode: str) -> float:
            portfolio = vbt.Portfolio.from_signals(
                close,
                entries=entries,
                exits=exits,
                size=size_value,
                size_type=size_type,
                init_cash=10_000.0,
                leverage=leverage,
                leverage_mode=leverage_mode,
                freq='1h',
            )
            return _first_order_nominal(portfolio)

        base = _run(1.0, 'lazy')
        assert base == pytest.approx(100.0), (
            'Grundfall ohne Hebel: eine feste Summe von 100 (bzw. 1 Stück zu 100)'
        )
        # Ohne Multiplikator ist der Hebel eine reine Kreditlinie — die
        # angeforderte Größe bleibt, was sie war.
        assert _run(2.0, 'lazy') == pytest.approx(base)
        assert _run(2.0, 'eager') == pytest.approx(base)
        # Mit Multiplikator wird die angeforderte Größe selbst verdoppelt.
        assert _run(2.0, 'lazymult') == pytest.approx(2 * base)
        assert _run(2.0, 'eagermult') == pytest.approx(2 * base)

    def test_percent_size_is_doubled_in_every_mode_and_is_no_multiplier(self):
        # Prozent-Größen rechnen gegen das Konto *inklusive* Kreditlinie. Die
        # Verdopplung tritt deshalb auch in 'lazy' auf, obwohl dort nichts
        # multipliziert wird — genau darauf darf der Block-Hebel nicht aufbauen.
        close = _flat_close()
        entries, exits = _entry_exit_masks()

        def _run(leverage: float, leverage_mode: str) -> float:
            portfolio = vbt.Portfolio.from_signals(
                close,
                entries=entries,
                exits=exits,
                size=50.0,
                size_type='percent100',
                init_cash=10_000.0,
                leverage=leverage,
                leverage_mode=leverage_mode,
                freq='1h',
            )
            return _first_order_nominal(portfolio)

        base = _run(1.0, 'lazy')
        assert base == pytest.approx(5_000.0), '50 % von 10.000 ohne Kreditlinie'
        for mode in ('lazy', 'eager', 'lazymult', 'eagermult'):
            assert _run(2.0, mode) == pytest.approx(2 * base), (
                f'Mit Hebel 2 ist die Prozent-Nominale in {mode} verdoppelt — in '
                f'den nicht multiplizierenden Modi allein wegen der Prozentbasis'
            )


class TestLeverageArrayWrittenAtRuntime:
    """Messung 3: leverage darf ein (T, N)-Array sein, das die Signal-Funktion füllt."""

    def test_leverage_written_in_the_signal_func_reaches_the_order(self):
        close = _flat_close()

        def _run(leverage: float) -> tuple:
            lev_arr = np.full((_N_BARS, 1), 1.0)
            portfolio = vbt.Portfolio.from_signals(
                close,
                signal_func_nb=_entry_with_leverage_nb,
                signal_args=(lev_arr, _ENTRY_BAR, _EXIT_BAR, leverage),
                size=100.0,
                size_type='value',
                init_cash=100_000.0,
                leverage=lev_arr,
                leverage_mode='lazymult',
                freq='1h',
            )
            return _first_order_nominal(portfolio), lev_arr

        nominal_one, arr_one = _run(1.0)
        nominal_three, arr_three = _run(3.0)

        assert nominal_one == pytest.approx(100.0)
        assert nominal_three == pytest.approx(300.0), (
            'Der zur Laufzeit geschriebene Hebel muss die Ordergröße vervielfachen'
        )
        assert arr_one[_ENTRY_BAR, 0] == 1.0
        assert arr_three[_ENTRY_BAR, 0] == 3.0, (
            'Die Signal-Funktion muss in genau das Array schreiben, das VBT liest — '
            'VBT darf es beim Broadcast nicht kopiert haben'
        )

    def test_leverage_array_is_read_per_column(self):
        # Drei Spalten, drei verschiedene Hebel: kein Spalte-0-Kurzschluss.
        close = pd.DataFrame(
            {col: np.full(_N_BARS, _FLAT_PRICE) for col in ('a', 'b', 'c')},
            index=_INDEX,
        )
        lev_arr = np.ones((_N_BARS, 3))
        lev_arr[_ENTRY_BAR] = [1.0, 2.0, 4.0]

        @njit
        def _fixed_leverage_nb(c, entry_bar, exit_bar):
            return c.i == entry_bar, c.i == exit_bar, False, False

        portfolio = vbt.Portfolio.from_signals(
            close,
            signal_func_nb=_fixed_leverage_nb,
            signal_args=(_ENTRY_BAR, _EXIT_BAR),
            size=100.0,
            size_type='value',
            init_cash=100_000.0,
            leverage=lev_arr,
            leverage_mode='lazymult',
            freq='1h',
        )
        records = portfolio.orders.values
        buys = records[records['side'] == 0]
        nominals = {
            int(col): float(size * price)
            for col, size, price in zip(buys['col'], buys['size'], buys['price'])
        }
        assert nominals == {
            0: pytest.approx(100.0),
            1: pytest.approx(200.0),
            2: pytest.approx(400.0),
        }


class TestSilentTruncationOnUndercoverage:
    """Messung 4: Unterdeckung wird auf Konto x Hebel gekürzt, ohne Meldung."""

    @pytest.mark.parametrize(
        'leverage, expected_nominal',
        [(1.0, 80.0), (2.0, 160.0), (3.0, 240.0)],
    )
    def test_order_is_cut_to_account_times_leverage(
        self, leverage: float, expected_nominal: float
    ):
        # Konto 80, gewollte feste Summe 100: die Order passt in keiner Variante
        # ganz, VBT kürzt still auf Konto x Hebel statt abzubrechen.
        close = _flat_close()
        entries, exits = _entry_exit_masks()
        portfolio = vbt.Portfolio.from_signals(
            close,
            entries=entries,
            exits=exits,
            size=100.0,
            size_type='value',
            init_cash=80.0,
            leverage=leverage,
            leverage_mode='lazymult',
            freq='1h',
        )
        assert _first_order_nominal(portfolio) == pytest.approx(expected_nominal), (
            'VBT kürzt eine unterdeckte Order auf Konto x Hebel — lautlos'
        )

    def test_truncation_leaves_no_warning_behind(self):
        # Der Nachweis, dass die Kürzung wirklich still ist: das Portfolio
        # unterscheidet sich in nichts als den Zahlen. Nur deshalb braucht der
        # Block-Hebel einen eigenen Abgleich nach dem Lauf.
        close = _flat_close()
        entries, exits = _entry_exit_masks()
        common = dict(
            close=close,
            entries=entries,
            exits=exits,
            size_type='value',
            init_cash=80.0,
            leverage=2.0,
            leverage_mode='lazymult',
            freq='1h',
        )
        truncated = vbt.Portfolio.from_signals(size=100.0, **common)
        fitting = vbt.Portfolio.from_signals(size=160.0, **common)
        assert _first_order_nominal(truncated) == pytest.approx(
            _first_order_nominal(fitting)
        ), (
            'Die gekürzte Order ist von einer passend gewollten nicht zu '
            'unterscheiden — ohne eigenen Abgleich fällt die Kürzung nirgends auf'
        )

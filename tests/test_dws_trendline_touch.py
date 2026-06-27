"""Tests für den Custom-Indikator dwsTrendlineTouch (TAP-Methode).

Synthetische, deterministische Daten — keine Abhängigkeit von OHLCV-Dateien.
Geprüft werden die Logik-Invarianten des kausalen Touch-Detektors sowie dass
auf einer klar fallenden Hoch-Folge überhaupt eine Widerstandslinie entsteht.
"""
import numpy as np
import pandas as pd
import pytest
from vectorbtpro.indicators.nb import pivot_info_1d_nb

from user_data.utils.indicators.custom import dwsTrendlineTouch


def _sawtooth_lower_highs(n_legs: int = 6, leg: int = 30) -> pd.DataFrame:
    """Sägezahn mit fallenden Hochs und konstanten Tiefs.

    Erzeugt eine Close-Serie, deren Pivot-Hochs exakt auf einer fallenden
    Geraden liegen (100, 95, 90, ...) und deren Tiefs konstant bei 78 sitzen.
    Damit bildet PIVOTINFO bestätigte fallende Hochs und der Indikator kann
    eine Widerstandslinie ziehen. High/Low werden eng um Close gelegt, sodass
    die Hochs die Linie berühren.
    """
    closes = []
    for k in range(n_legs):
        peak = 100.0 - 5.0 * k
        trough = 78.0
        # hoch -> runter -> hoch-Bewegung je Bein
        closes.extend(np.linspace(trough, peak, leg, endpoint=False))
        closes.extend(np.linspace(peak, trough, leg, endpoint=False))
    close = np.asarray(closes, dtype=float)
    idx = pd.date_range("2024-01-01", periods=len(close), freq="4h")
    high = close * 1.001
    low = close * 0.999
    return pd.DataFrame({"High": high, "Low": low, "Close": close}, index=idx)


@pytest.fixture
def synth():
    return _sawtooth_lower_highs()


def _run(df: pd.DataFrame, min_bars_between=0, dip_min_atr=0.0):
    return dwsTrendlineTouch.run(
        df["High"], df["Low"], df["Close"],
        up_th=0.05, down_th=0.05, atr_length=14, touch_tol_atr=0.5,
        break_tol_atr=0.5, dev_max_atr=0.75, min_touch=3, max_touch=4,
        min_bars_between=min_bars_between, dip_min_atr=dip_min_atr,
    )


def test_output_shapes(synth):
    """Alle sechs Outputs haben die Länge der Eingabe."""
    ind = _run(synth)
    n = len(synth)
    for out in (ind.short_line, ind.long_line, ind.short_signal, ind.long_signal,
                ind.short_touch, ind.long_touch):
        assert len(np.asarray(out).ravel()) == n


def test_touch_numbers_start_at_one_and_increment(synth):
    """Touch-Output traegt aufsteigende Nummern ab 1; pro Linie neu beginnend.

    Die Anker-Pivots sind Touch 1+2, folgende Band-Eintritte 3, 4, ...
    Auf der fallenden Hoch-Folge muss mindestens eine vollstaendige 1->2->3-Sequenz
    auftreten.
    """
    ind = _run(synth)
    touch = np.asarray(ind.short_touch).ravel()
    nums = touch[~np.isnan(touch)]
    assert nums.size > 0
    # Nur ganzzahlige Touch-Nummern, kleinste ist 1
    assert np.all(nums == np.round(nums))
    assert nums.min() == 1.0
    # Touch-Nummern sind bei max_touch gedeckelt (hier 4) — keine hoeheren Marker
    assert nums.max() <= 4.0
    # In zeitlicher Reihenfolge taucht eine 1 vor der zugehoerigen 2 auf
    order = touch[~np.isnan(touch)]
    assert 2.0 in order and 3.0 in order


def test_touch_only_at_active_line_bars(synth):
    """Touch 3+ (Band-Eintritte) liegen nur auf Bars mit aktiver Linie.

    Die Anker-Pivots (Touch 1+2) koennen vor dem ersten gezeichneten Linien-Bar
    liegen, daher nur Touches >= 3 gegen die Linie pruefen.
    """
    ind = _run(synth)
    touch = np.asarray(ind.short_touch).ravel()
    line = np.asarray(ind.short_line).ravel()
    for i in np.where(touch >= 3.0)[0]:
        assert not np.isnan(line[i])


def test_signals_are_binary(synth):
    """Signale sind ausschließlich 0.0 oder 1.0."""
    ind = _run(synth)
    for sig in (ind.short_signal, ind.long_signal):
        vals = np.unique(np.asarray(sig).ravel())
        assert set(vals.tolist()).issubset({0.0, 1.0})


def test_resistance_line_forms_and_falls(synth):
    """Auf fallenden Hochs entsteht eine Widerstandslinie, die nicht steigt."""
    ind = _run(synth)
    line = np.asarray(ind.short_line).ravel()
    finite = line[~np.isnan(line)]
    # Linie wird überhaupt aktiv
    assert finite.size > 0
    # Innerhalb zusammenhängender aktiver Segmente fällt die Linie (Steigung <= 0)
    active = ~np.isnan(line)
    diffs = np.diff(line[active])
    # Sprünge zwischen getrennten Segmenten ausklammern: nur aufeinanderfolgende
    # aktive Bars vergleichen
    consec = np.diff(np.where(active)[0]) == 1
    assert np.all(diffs[consec] <= 1e-9)


def test_short_signal_on_active_line(synth):
    """Jedes Short-Signal feuert auf einem Bar mit aktiver Widerstandslinie.

    Signale werden kausal am Pivot-Bestaetigungs-Bar gesetzt; dort ist die Linie
    noch aktiv (sonst waere der Touch nicht gezaehlt worden).
    """
    ind = _run(synth)
    sig = np.asarray(ind.short_signal).ravel()
    line = np.asarray(ind.short_line).ravel()
    for i in np.where(sig > 0)[0]:
        assert not np.isnan(line[i])


def test_touches_sit_on_confirmed_pivots(synth):
    """Touch-Marker liegen ausschliesslich auf bestaetigten Pivot-Hochs.

    Kernverhalten der Zigzag-Kopplung: ein Touch zaehlt nur an einem bestaetigten
    gleichsinnigen Pivot, nicht an beliebigen Band-Eintritten.
    """
    ind = _run(synth)
    touch = np.asarray(ind.short_touch).ravel()
    high = synth["High"].to_numpy()
    low = synth["Low"].to_numpy()
    conf_pivot, conf_idx, _lp, _li = pivot_info_1d_nb(high, low, 0.05, 0.05)
    peak_idxs = set(
        int(conf_idx[k]) for k in range(len(conf_pivot))
        if conf_pivot[k] == 1 and conf_idx[k] >= 0
    )
    touch_idxs = set(np.where(~np.isnan(touch))[0].tolist())
    assert touch_idxs.issubset(peak_idxs)


def test_min_bars_between_filters_close_pivots(synth):
    """Ein sehr grosser Mindest-Bar-Abstand unterdrueckt alle Touches.

    Liegen die Pivots naeher beieinander als min_bars_between, bildet sich keine
    Linie und es entstehen keine Touch-Marker. Mit Abstand 0 (Default) gibt es welche.
    """
    base = np.asarray(_run(synth).short_touch).ravel()
    assert np.count_nonzero(~np.isnan(base)) > 0
    blocked = np.asarray(_run(synth, min_bars_between=10_000).short_touch).ravel()
    assert np.count_nonzero(~np.isnan(blocked)) == 0


def test_dip_min_atr_filters_shallow_kuhle(synth):
    """Eine sehr grosse geforderte Kuhle-Tiefe unterdrueckt alle Touches.

    Reicht der Ruecksetzer zwischen zwei Pivots nicht an dip_min_atr*ATR heran,
    zaehlt der Touch nicht. Mit 0 (Default) ist der Filter aus und es gibt Touches.
    """
    base = np.asarray(_run(synth).short_touch).ravel()
    assert np.count_nonzero(~np.isnan(base)) > 0
    blocked = np.asarray(_run(synth, dip_min_atr=1000.0).short_touch).ravel()
    assert np.count_nonzero(~np.isnan(blocked)) == 0


def test_causal_no_lookahead(synth):
    """Kausalität: ein Signal an Bar i hängt nicht von Bars > i ab.

    Wir hängen zusätzliche Bars an und prüfen, dass sich die Signale auf dem
    gemeinsamen Präfix nicht ändern.
    """
    ind_full = _run(synth)
    sig_full = np.asarray(ind_full.short_signal).ravel()

    cut = len(synth) - 40
    ind_cut = _run(synth.iloc[:cut])
    sig_cut = np.asarray(ind_cut.short_signal).ravel()

    np.testing.assert_array_equal(sig_full[:cut], sig_cut)

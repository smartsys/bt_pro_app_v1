"""Tests für den Custom-Indikator dwsGaussianChannel (Ehlers-Tiefpass mit True-Range-Band).

Synthetische, deterministische Daten — keine Abhängigkeit von OHLCV-Dateien.
Geprüft werden Bandordnung, die analytisch bekannte Gleichstrom-Verstärkung von
exakt 1, die Wirkung der Quellwahl und die Kausalität (kein Blick nach vorn).
"""
import numpy as np
import pandas as pd
import pytest

from user_data.utils.indicators.custom import dwsGaussianChannel


def _ohlc(close: np.ndarray, spanne: float = 0.004) -> pd.DataFrame:
    """OHLC-Gerüst mit **asymmetrischer** Spanne um den Schlusskurs.

    Die Asymmetrie ist nicht Kosmetik: bei High = close*(1+s) und Low = close*(1-s)
    ist hlc3 rechnerisch exakt close, und jeder Test, der die Quellwahl prüfen will,
    liefe ins Leere.
    """
    idx = pd.date_range("2024-01-01", periods=len(close), freq="1D")
    return pd.DataFrame(
        {
            "Open": np.roll(close, 1),
            "High": close * (1.0 + 2.0 * spanne),
            "Low": close * (1.0 - spanne),
            "Close": close,
        },
        index=idx,
    )


def _run(df: pd.DataFrame, **kwargs):
    return dwsGaussianChannel.run(df["Open"], df["High"], df["Low"], df["Close"], **kwargs)


def test_output_shapes():
    df = _ohlc(100 + np.sin(np.linspace(0, 20, 400)) * 10)
    ind = _run(df)
    for out in (ind.filt, ind.hband, ind.lband):
        assert len(np.asarray(out).ravel()) == len(df)


def test_band_order():
    """Das Band liegt symmetrisch um die Mittellinie: lband < filt < hband."""
    df = _ohlc(100 + np.sin(np.linspace(0, 40, 500)) * 15)
    ind = _run(df)
    filt = np.asarray(ind.filt).ravel()
    hband = np.asarray(ind.hband).ravel()
    lband = np.asarray(ind.lband).ravel()
    # Ab dem zweiten Balken ist die gefilterte True Range positiv
    assert np.all(hband[1:] > filt[1:])
    assert np.all(filt[1:] > lband[1:])


def test_konstanter_kurs_konvergiert_gegen_den_kurs():
    """Gleichstrom-Verstärkung ist exakt 1 — bei konstantem Kurs läuft filt dagegen.

    Analytisch: die Summe der Rückkopplungsgewichte ist 1 - alpha^N, der Vorwärts-
    term alpha^N. Ein konstanter Eingang muss deshalb im Beharrungszustand
    unverändert durchlaufen. Zugleich geht die True Range gegen null, das Band
    kollabiert also auf die Mittellinie.
    """
    df = _ohlc(np.full(600, 250.0), spanne=0.0)
    ind = _run(df, period=144, poles=4)
    filt = np.asarray(ind.filt).ravel()
    hband = np.asarray(ind.hband).ravel()
    assert filt[-1] == pytest.approx(250.0, abs=1e-6)
    assert hband[-1] == pytest.approx(250.0, abs=1e-6)


def test_quellwahl_wirkt():
    """hlc3 und close liefern verschiedene Mittellinien, close entspricht der Close-Reihe."""
    df = _ohlc(100 + np.cos(np.linspace(0, 30, 400)) * 8, spanne=0.02)
    mit_hlc3 = np.asarray(_run(df, source="hlc3").filt).ravel()
    mit_close = np.asarray(_run(df, source="close").filt).ravel()
    assert not np.allclose(mit_hlc3, mit_close)

    # 'close' muss dasselbe ergeben wie ein Lauf, dessen High/Low gleich Close sind
    flach = df.copy()
    flach["High"] = flach["Close"]
    flach["Low"] = flach["Close"]
    ueber_hlc3 = np.asarray(_run(flach, source="hlc3").filt).ravel()
    assert np.allclose(mit_close, ueber_hlc3)


def test_unbekannte_quelle_faellt_auf():
    df = _ohlc(np.linspace(100, 120, 50))
    with pytest.raises(ValueError, match="Unbekannte Quelle"):
        _run(df, source="typical")


def test_polzahl_wird_geprueft():
    df = _ohlc(np.linspace(100, 120, 50))
    with pytest.raises(ValueError, match="poles"):
        _run(df, poles=10)


def test_mehr_pole_daempfen_schnelle_schwankungen_staerker():
    """Oberhalb der Grenzfrequenz rollt die Kaskade steiler ab als ein einzelner Pol.

    Die Einschränkung „oberhalb" ist wesentlich und am 2026-09-01 nachgemessen: bei
    einer Schwingung **unterhalb** der Filtergrenze kehrt sich das Verhältnis um — vier
    Pole lassen das Signal dann sauberer durch als einer und streuen deshalb mehr.
    Deshalb prüft dieser Test mit breitbandigem Rauschen, nicht mit einer langsamen
    Sinuskurve.
    """
    kurs = 100 + np.random.default_rng(5).normal(0, 3, 800)
    df = _ohlc(kurs)
    eins = np.asarray(_run(df, poles=1, period=60).filt).ravel()[200:]
    vier = np.asarray(_run(df, poles=4, period=60).filt).ravel()[200:]
    assert np.std(vier) < np.std(eins)


def test_betriebsarten_laufen_durch():
    """Reduced Lag und Fast Response verändern das Ergebnis, ohne NaN zu erzeugen."""
    df = _ohlc(100 + np.sin(np.linspace(0, 25, 500)) * 10)
    normal = np.asarray(_run(df).filt).ravel()
    for kwargs in ({"reduced_lag": True}, {"fast_response": True}):
        werte = np.asarray(_run(df, **kwargs).filt).ravel()
        assert np.all(np.isfinite(werte[200:]))
        assert not np.allclose(normal, werte)


def test_kein_blick_nach_vorn():
    """Ein abgeschnittener Verlauf ändert die bereits berechneten Werte nicht.

    Das ist der Unterschied zu einer Umsetzung, die auf spätere Balken zugreift:
    dort verschöbe sich das Ergebnis rückwirkend, sobald neue Balken dazukommen.
    """
    kurs = 100 + np.cumsum(np.sin(np.linspace(0, 50, 400)))
    voll = np.asarray(_run(_ohlc(kurs)).filt).ravel()
    kurz = np.asarray(_run(_ohlc(kurs[:300])).filt).ravel()
    assert np.allclose(voll[:300], kurz, atol=1e-12)


def test_width_ist_relativer_bandabstand():
    """`width` ist der Bandabstand relativ zur Mittellinie in Prozent.

    Rechnerisch (hband - lband) / filt * 100 auf jedem Balken; bei konstantem Kurs
    kollabiert das Band und die Breite geht gegen null.
    """
    df = _ohlc(100 + np.sin(np.linspace(0, 40, 500)) * 15)
    ind = _run(df)
    filt = np.asarray(ind.filt).ravel()
    hband = np.asarray(ind.hband).ravel()
    lband = np.asarray(ind.lband).ravel()
    width = np.asarray(ind.width).ravel()
    assert len(width) == len(df)
    assert np.allclose(width[1:], (hband[1:] - lband[1:]) / filt[1:] * 100.0)
    assert np.all(width[1:] > 0)

    flach = _run(_ohlc(np.full(600, 250.0), spanne=0.0))
    assert np.asarray(flach.width).ravel()[-1] == pytest.approx(0.0, abs=1e-6)

"""Tests für den Custom-Indikator dwsFVG (Fair Value Gap nach der LuxAlgo-Fassung).

Von Hand gebaute Dreikerzen-Muster mit bekanntem Ergebnis — keine Abhängigkeit von
OHLCV-Dateien. Geprüft werden Erkennung, Zonenkanten, Mindestabstand, Mitigation und
die Kausalität (Verankerung am dritten Balken, kein Blick nach vorn).
"""
import numpy as np
import pandas as pd
import pytest

from user_data.utils.indicators.custom import dwsFVG


def _bars(zeilen) -> pd.DataFrame:
    """Baut ein OHLC-Gerüst aus (high, low, close)-Tripeln."""
    idx = pd.date_range("2024-01-01", periods=len(zeilen), freq="1D")
    return pd.DataFrame(
        {
            "High": [z[0] for z in zeilen],
            "Low": [z[1] for z in zeilen],
            "Close": [z[2] for z in zeilen],
        },
        index=idx,
    )


def _run(df: pd.DataFrame, **kwargs):
    return dwsFVG.run(df["High"], df["Low"], df["Close"], **kwargs)


# Bullische Lücke: high[0] = 10, low[2] = 10.5 -> Zone 10 bis 10.5.
# close[1] = 11.5 liegt über high[0], die Bestätigung sitzt also auf der mittleren Kerze.
BULLISCH = [
    (10.0, 9.0, 9.5),
    (12.0, 9.8, 11.5),
    (13.0, 10.5, 12.0),
]

# Bärische Lücke: low[0] = 12, high[2] = 11 -> Zone 11 bis 12.
BAERISCH = [
    (13.0, 12.0, 12.5),
    (12.5, 10.0, 10.5),
    (11.0, 9.0, 9.5),
]


def test_bullische_luecke_wird_am_dritten_balken_erkannt():
    ind = _run(_bars(BULLISCH))
    signal = np.asarray(ind.signal).ravel()
    assert list(signal) == [0.0, 0.0, 1.0]
    assert np.asarray(ind.bull_top).ravel()[2] == pytest.approx(10.5)
    assert np.asarray(ind.bull_bottom).ravel()[2] == pytest.approx(10.0)
    assert np.isnan(np.asarray(ind.bear_top).ravel()[2])


def test_baerische_luecke_wird_am_dritten_balken_erkannt():
    ind = _run(_bars(BAERISCH))
    signal = np.asarray(ind.signal).ravel()
    assert list(signal) == [0.0, 0.0, -1.0]
    assert np.asarray(ind.bear_top).ravel()[2] == pytest.approx(12.0)
    assert np.asarray(ind.bear_bottom).ravel()[2] == pytest.approx(11.0)
    assert np.isnan(np.asarray(ind.bull_top).ravel()[2])


def test_bestaetigung_der_mittleren_kerze_ist_noetig():
    """Ohne close[1] über high[0] entsteht keine bullische Zone — auch bei offener Lücke."""
    ohne_bestaetigung = [
        (10.0, 9.0, 9.5),
        (12.0, 9.8, 9.9),   # Schluss unter high[0] = 10
        (13.0, 10.5, 12.0),
    ]
    ind = _run(_bars(ohne_bestaetigung))
    assert np.all(np.asarray(ind.signal).ravel() == 0.0)


def test_mindestabstand_unterdrueckt_kleine_luecken():
    """Die Lücke misst 5 %; eine Schwelle darüber verwirft sie, eine darunter nicht."""
    df = _bars(BULLISCH)
    assert np.asarray(_run(df, threshold=0.04).signal).ravel()[2] == 1.0
    assert np.asarray(_run(df, threshold=0.06).signal).ravel()[2] == 0.0


def test_mitigation_bei_schluss_unter_der_unterkante():
    """Bullische Zone gilt als mitigiert, sobald der Schluss unter die Unterkante fällt."""
    zeilen = BULLISCH + [(10.0, 9.0, 9.5)]   # Schluss 9.5 < Unterkante 10.0
    ind = _run(_bars(zeilen))
    bull_top = np.asarray(ind.bull_top).ravel()
    assert bull_top[2] == pytest.approx(10.5)
    assert np.isnan(bull_top[3])


def test_beruehrung_mitigiert_noch_nicht():
    """Ein Docht in der Zone reicht nicht — erst der Schlusskurs jenseits der Kante zählt.

    Genau hier weicht die Fassung des Pakets smart-money-concepts ab, die schon bei
    der ersten Dochtberührung der nahen Kante mitigiert.
    """
    zeilen = BULLISCH + [(12.0, 9.5, 10.2)]  # Docht bis 9.5 unter die Zone, Schluss darüber
    ind = _run(_bars(zeilen))
    bull_top = np.asarray(ind.bull_top).ravel()
    assert bull_top[3] == pytest.approx(10.5)


def test_baerische_mitigation_bei_schluss_ueber_der_oberkante():
    zeilen = BAERISCH + [(13.0, 12.0, 12.5)]  # Schluss 12.5 > Oberkante 12.0
    ind = _run(_bars(zeilen))
    bear_top = np.asarray(ind.bear_top).ravel()
    assert bear_top[2] == pytest.approx(12.0)
    assert np.isnan(bear_top[3])


def test_juengste_offene_zone_wird_ausgegeben():
    """Bei zwei offenen bullischen Zonen trägt die Ausgabe die jüngere."""
    zeilen = BULLISCH + [
        (14.0, 12.5, 13.5),
        (16.0, 13.0, 15.0),
        (17.0, 14.5, 16.0),   # zweite bullische Luecke: high[3] = 14 -> low[5] = 14.5
    ]
    ind = _run(_bars(zeilen))
    signal = np.asarray(ind.signal).ravel()
    assert signal[2] == 1.0 and signal[5] == 1.0
    assert np.asarray(ind.bull_top).ravel()[5] == pytest.approx(14.5)
    assert np.asarray(ind.bull_bottom).ravel()[5] == pytest.approx(14.0)


def test_kein_blick_nach_vorn():
    """Ein abgeschnittener Verlauf ändert die bereits berechneten Werte nicht.

    Die Verankerung am dritten Balken ist der Grund. Eine Umsetzung, die wie
    smart-money-concepts am mittleren Balken verankert und auf den folgenden zugreift,
    scheitert an diesem Test.
    """
    rng = np.random.default_rng(3)
    close = 100 + np.cumsum(rng.normal(0, 2.0, 300))
    high = close + np.abs(rng.normal(0, 1.5, 300))
    low = close - np.abs(rng.normal(0, 1.5, 300))
    df = pd.DataFrame(
        {"High": high, "Low": low, "Close": close},
        index=pd.date_range("2024-01-01", periods=300, freq="1D"),
    )
    voll = _run(df)
    kurz = _run(df.iloc[:200])
    for name in ("signal", "bull_top", "bull_bottom", "bear_top", "bear_bottom"):
        a = np.asarray(getattr(voll, name)).ravel()[:200]
        b = np.asarray(getattr(kurz, name)).ravel()
        np.testing.assert_allclose(a, b, equal_nan=True)


def test_auto_schwelle_verwirft_mehr_als_keine_schwelle():
    """Der expandierende Mittelwert der relativen Spannen ist eine echte Hürde."""
    rng = np.random.default_rng(11)
    close = 100 + np.cumsum(rng.normal(0, 2.0, 400))
    high = close + np.abs(rng.normal(0, 1.5, 400))
    low = close - np.abs(rng.normal(0, 1.5, 400))
    df = pd.DataFrame(
        {"High": high, "Low": low, "Close": close},
        index=pd.date_range("2024-01-01", periods=400, freq="1D"),
    )
    ohne = int((np.asarray(_run(df).signal).ravel() != 0).sum())
    mit = int((np.asarray(_run(df, auto=True).signal).ravel() != 0).sum())
    assert ohne > 0
    assert mit < ohne

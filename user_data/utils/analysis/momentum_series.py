"""Synthetische Reihen mit eingebautem Momentum — Positivkontrolle des Permutationstests (Ticket 80).

Gegenstück zu :mod:`user_data.utils.analysis.synthetic_series`: Das Nullmodell dort
**zerstört** die Reihenfolge, dieses Modul **baut sie ein**. Damit entsteht ein
Kandidat, dessen Vorteil per Konstruktion nur bei erhaltener Bar-Reihenfolge existiert —
genau das, was der Permutationstest finden muss.

**Warum es diesen Baustein braucht** (Befund aus Ticket 79): Die dort vorregistrierte
Positivkontrolle mit ``dwsLookaheadOracle`` ist für dieses Nullmodell konstruktiv
untauglich. Der Orakel-Vorteil ist **permutations-invariant**: Auf jeder synthetischen
Reihe wird die Strategie neu gerechnet, und das Orakel liest ``close[t+6]`` dann aus der
*synthetischen* Zukunft. Sein Vorteil wandert vollständig in die Null-Verteilung
(gemessen: echt Sharpe 2,41 gegen Null-Mittel 3,17, p = 0,92). Der Vorteil hier ist das
Gegenteil davon: Er steckt **in den Daten**, nicht im Regelwerk, und die Permutation
nimmt ihn weg.

**Erzeugungsmodell** (Log-Renditen der Balken):

    r_t   = mu_t + eps_t
    mu_t  = rho * mu_{t-1} + trend_strength * sigma * sqrt(1 - rho^2) * xi_t
    eps_t ~ N(0, sigma),  xi_t ~ N(0, 1)

``mu_t`` ist eine langsam mean-revertierende, verborgene Driftkomponente (AR(1) mit
``rho = 0,99``, Halbwertszeit rund 69 Balken). Sie erzeugt **Trends**: Phasen, in denen
die Renditen im Mittel in dieselbe Richtung zeigen. ``trend_strength`` ist der einzige
Knopf und skaliert die Standardabweichung von ``mu`` relativ zu ``sigma``; bei
``trend_strength = 0`` bleiben reine i.i.d.-Renditen ohne jede Reihenfolge-Information —
das ist die Gegenprobe mit **identischer** Randverteilungsform.

**Driftfrei per Konstruktion:** ``r`` wird nach der Erzeugung zentriert
(``r -= r.mean()``), die Summe der erzeugten Log-Renditen ist also exakt null. (Die
Balken-zu-Balken-Renditen ``log(C_t / C_{t-1})`` ab Balken 1 summieren sich auf
``-r_0``, also auf die Größenordnung einer einzelnen Balkenrendite — Restdrift unter
drei Prozent über zwei Jahre.) Das ist wichtig,
weil die Summe der Log-Renditen eine **Permutationsinvariante** ist: Die synthetischen
Zwillinge haben dieselbe Buy-and-Hold-Rendite wie das Original. Wäre eine positive Drift
eingebaut, könnte ein Long-Kandidat auch auf der permutierten Reihe verdienen und der
Nachweis wäre verwässert. So bleibt als einziger Unterschied zwischen Original und
Zwilling die **Reihenfolge**.

**Balkenaufbau:** ``Open`` ist der Vor-Close (Gap-Komponente exakt null), die ganze
Bar-Rendite steckt im Körper. Die Dochte sind unabhängige Halbnormal-Aufschläge, die
OHLC-Konsistenz (``High >= max(O,C) >= min(O,C) >= Low``) ist damit per Konstruktion
erfüllt — die Bar-Zerlegung des Nullmodells greift ohne Sonderweg.

**Gemessene Nachweisgrenze** (SMA 10/50 Long-Trendfolge, FETUSDT-4h-Index über zwei
Jahre, ``sigma = 0,02``, ``rho = 0,99``, Zahlen in
``documentation/knowledge/signifikanztest.md``): ``trend_strength`` 0,00 und 0,05 sind
nicht nachweisbar, ab 0,15 liegt der echte Wert über dem Maximum der Null-Verteilung.
Die Kontrolle läuft deshalb bei **0,20** — die erste Stufe mit Sicherheitsabstand über
mehrere Daten-Seeds hinweg.

**Nutzung über den echten Job-Pfad:** Das CLI unten schreibt die Reihen als
Pseudo-Symbole in die HDF5-Datei (``ohlcv_<tf>_<exchange>.h5``). Danach zeigt eine
BacktestConfig auf das Pseudo-Symbol, ein normaler Lauf erzeugt das Result, und
``signifikanz-start`` läuft darauf — ohne jede Sonderbehandlung im Job. Aufgeräumt wird
mit dem vorhandenen Verb ``data-delete-symbol`` (siehe Hinweis zu den Schreibrechten in
:func:`main`).
"""

import argparse
import os
from typing import Optional

import numpy as np
import pandas as pd

# Persistenz der verborgenen Driftkomponente. 0,99 entspricht rund 69 Balken
# Halbwertszeit — auf 4h-Balken gut zwei Wochen, also Trends, die eine SMA-Kreuzung
# mit Perioden von 10/50 Balken auch sieht.
DEFAULT_RHO: float = 0.99

# Standardabweichung der Balken-Log-Rendite. 2 Prozent je 4h-Balken liegt in der
# Größenordnung echter Krypto-Reihen.
DEFAULT_SIGMA: float = 0.02

# Streuung der Docht-Aufschläge (Log-Skala), als Halbnormal gezogen.
DEFAULT_WICK_SIGMA: float = 0.004

# Startpreis der Reihe. Frei wählbar — der Test rechnet in Prozent.
DEFAULT_START_PRICE: float = 100.0

# Die vorregistrierte Trendstärke der Positivkontrolle (Ticket 80).
CONTROL_TREND_STRENGTH: float = 0.20

# Pseudo-Symbole der Kontrolle: Name -> (Daten-Seed, Trendstärke).
# SYNTHFLAT* sind die Gegenprobe (kein Reihenfolge-Vorteil), SYNTHMOM20* die
# eigentliche Positivkontrolle, SYNTHMOM05/10/15 die Empfindlichkeitsstaffel.
#
# Die Gegenprobe läuft über **30** Daten-Seeds, nicht über drei: Ohne
# Reihenfolge-Vorteil **ist** die echte Reihe eine Ziehung aus ihrer eigenen
# Null-Verteilung, der p-Wert ist also gleichverteilt. Ein Wert von 0,01 taucht unter
# drei Ziehungen mit rund 3 Prozent Wahrscheinlichkeit auf — mit drei Punkten wäre
# „unauffällig" nicht entscheidbar, und auch zehn Ziehungen (der Umfang der
# Negativkontrolle aus Ticket 79) trennen 10 Prozent Trefferrate nicht sauber von 30
# Prozent. Erst 30 Ziehungen machen die Gleichverteilung prüfbar (Ticket 80).
FLAT_SEEDS: range = range(101, 131)


def _flat_symbol(seed: int) -> str:
    """Name des Gegenproben-Pseudo-Symbols zu einem Daten-Seed.

    Durchnummeriert mit Buchstaben (A, B, ... Z, AA, AB, ...), Seed 101 ist A. Ziffern
    im Symbolnamen sind bewusst vermieden, damit die Gegenproben-Symbole nicht mit den
    Momentum-Stufen (`SYNTHMOM05A` ... `SYNTHMOM20A`) verwechselt werden.
    """
    index = seed - FLAT_SEEDS.start
    letters = ''
    while True:
        letters = chr(ord('A') + index % 26) + letters
        index = index // 26 - 1
        if index < 0:
            return f'SYNTHFLAT{letters}'


CONTROL_SYMBOLS: dict = {
    **{_flat_symbol(seed): (seed, 0.00) for seed in FLAT_SEEDS},
    'SYNTHMOM05A': (101, 0.05),
    'SYNTHMOM10A': (101, 0.10),
    'SYNTHMOM15A': (101, 0.15),
    'SYNTHMOM20A': (101, CONTROL_TREND_STRENGTH),
    'SYNTHMOM20B': (102, CONTROL_TREND_STRENGTH),
    'SYNTHMOM20C': (103, CONTROL_TREND_STRENGTH),
}


def make_momentum_frame(
    template: pd.DataFrame,
    seed: int,
    trend_strength: float,
    rho: float = DEFAULT_RHO,
    sigma: float = DEFAULT_SIGMA,
    wick_sigma: float = DEFAULT_WICK_SIGMA,
    start_price: float = DEFAULT_START_PRICE,
) -> pd.DataFrame:
    """Erzeugt eine OHLCV-Reihe mit eingebautem, driftfreiem Momentum.

    Args:
        template: Echte OHLCV-Reihe. Genutzt werden ausschließlich Zeitindex,
            Spaltennamen und Spalten-Dtypes — keine Preise. Die synthetische Reihe
            ist damit im System nicht von einem normalen Symbol zu unterscheiden.
        seed: Startwert des Zufallsgenerators (Daten-Seed).
        trend_strength: Stärke der verborgenen Driftkomponente, relativ zu ``sigma``.
            0 heißt: keine zeitliche Struktur (Gegenprobe).
        rho: Persistenz der Driftkomponente (0 <= rho < 1).
        sigma: Standardabweichung der Balken-Log-Rendite.
        wick_sigma: Streuung der Docht-Aufschläge (Log-Skala).
        start_price: Preis des ersten Balken-Opens.

    Returns:
        DataFrame mit Index, Spalten und Dtypes des Templates. Die Summe der
        Log-Renditen ist exakt null (driftfrei), OHLC ist je Balken konsistent.

    Raises:
        ValueError: Bei negativer Trendstärke oder unzulässigem ``rho``.
    """
    if trend_strength < 0:
        raise ValueError(f'trend_strength muss >= 0 sein, ist {trend_strength}')
    if not 0.0 <= rho < 1.0:
        raise ValueError(f'rho muss in [0, 1) liegen, ist {rho}')

    rng = np.random.default_rng(seed)
    n_bars = len(template)

    # Verborgene Driftkomponente: stationäres AR(1) mit Standardabweichung
    # trend_strength * sigma. Der Faktor sqrt(1 - rho^2) macht die Skalierung von rho
    # unabhängig — trend_strength bleibt bei jedem rho dieselbe Aussage.
    innovation = rng.normal(0.0, 1.0, n_bars)
    scale = trend_strength * sigma * np.sqrt(1.0 - rho ** 2)
    trend = np.zeros(n_bars)
    for t in range(1, n_bars):
        trend[t] = rho * trend[t - 1] + scale * innovation[t]

    returns = trend + rng.normal(0.0, sigma, n_bars)
    # Exakt driftfrei: die Summe der Log-Renditen ist eine Permutationsinvariante,
    # eine eingebaute Drift würde auch auf der permutierten Reihe verdienen.
    returns = returns - returns.mean()

    close = start_price * np.exp(np.cumsum(returns))
    open_ = np.concatenate([[start_price], close[:-1]])
    upper = np.abs(rng.normal(0.0, wick_sigma, n_bars))
    lower = np.abs(rng.normal(0.0, wick_sigma, n_bars))
    high = np.maximum(open_, close) * np.exp(upper)
    low = np.minimum(open_, close) * np.exp(-lower)
    volume = rng.lognormal(mean=10.0, sigma=0.5, size=n_bars)

    frame = pd.DataFrame(index=template.index, columns=template.columns, dtype='float64')
    values = {'Open': open_, 'High': high, 'Low': low, 'Close': close, 'Volume': volume}
    for column in template.columns:
        frame[column] = values.get(column, volume)
    return frame.astype(template.dtypes.to_dict())


def write_pseudo_symbol(h5_path: str, symbol: str, frame: pd.DataFrame) -> None:
    """Schreibt eine synthetische Reihe als Pseudo-Symbol in die HDF5-Datei.

    Args:
        h5_path: Pfad der HDF5-Datei (``ohlcv_<timeframe>_<exchange>.h5``).
        symbol: Schlüssel im Store, also der Symbolname.
        frame: OHLCV-Reihe aus :func:`make_momentum_frame`.

    Raises:
        FileNotFoundError: Wenn die HDF5-Datei nicht existiert.
    """
    if not os.path.exists(h5_path):
        raise FileNotFoundError(f'HDF5-Datei nicht gefunden: {h5_path}')
    with pd.HDFStore(h5_path, mode='a') as store:
        store.put(symbol, frame, format='table')


def _template_frame(h5_path: str, symbol: str, start: str, end: str) -> pd.DataFrame:
    """Liest die Vorlage-Reihe (Index, Spalten, Dtypes) aus der HDF5-Datei."""
    with pd.HDFStore(h5_path, mode='r') as store:
        frame = store[symbol]
    window = frame.loc[start:end]
    if window.empty:
        raise ValueError(f'Vorlage {symbol} hat im Fenster {start}..{end} keine Balken.')
    return window


def main(argv: Optional[list] = None) -> int:
    """CLI: schreibt die Pseudo-Symbole der Positivkontrolle in die HDF5-Datei.

    Entfernt werden sie mit dem vorhandenen Verb der Toolbox:
    ``python3 toolbox.py data-delete-symbol --timeframe 4h --symbol SYNTHMOM20A``.

    **Schreibrechte:** Gehören die HDF5-Dateien unter ``data/ohlc_data/`` dem Nutzer
    ``root`` (Zustand auf dem Dev-Rechner, Stand 14.08.2026), scheitert jeder Schreib-
    zugriff des App-Containers — er läuft als uid 1000. Betroffen sind gleichermaßen
    dieses CLI, ``data-delete-symbol``, ``data-update`` und ``data-download``. Behelf:
    ``docker exec -u 0 frontend_bt_pro_v1 python -m user_data.utils.analysis.momentum_series``.

    Returns:
        Exit-Code (0 = geschrieben).
    """
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--data-path', default='/app/data/ohlc_data',
                        help='Ordner der HDF5-Dateien')
    parser.add_argument('--timeframe', default='4h')
    parser.add_argument('--exchange', default='binance')
    parser.add_argument('--template-symbol', default='FETUSDT',
                        help='Symbol, dessen Zeitindex und Spalten-Layout übernommen werden')
    parser.add_argument('--start', default='2019-12-01')
    parser.add_argument('--end', default='2022-01-01')
    args = parser.parse_args(argv)

    h5_path = os.path.join(args.data_path, f'ohlcv_{args.timeframe}_{args.exchange}.h5')
    template = _template_frame(h5_path, args.template_symbol, args.start, args.end)
    print(f'Vorlage {args.template_symbol}: {len(template)} Balken '
          f'{template.index[0]} .. {template.index[-1]}')

    for symbol, (seed, strength) in CONTROL_SYMBOLS.items():
        frame = make_momentum_frame(template, seed=seed, trend_strength=strength)
        write_pseudo_symbol(h5_path, symbol, frame)
        log_returns = np.diff(np.log(frame['Close'].to_numpy(dtype=float)))
        autocorr = float(np.corrcoef(log_returns[:-1], log_returns[1:])[0, 1])
        print(f'  {symbol}: Seed {seed}, Trendstärke {strength:.2f}, '
              f'AC(1) {autocorr:+.4f}, Drift {log_returns.sum():+.6f}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

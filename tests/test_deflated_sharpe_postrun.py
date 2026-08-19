"""Tests für den DSR-Nachlauf über den ganzen Lauf (Ticket 54, Anforderung 2/3/6).

Der Nachlauf `repository._calculate_deflated_sharpe` liest die Bausteine aus der
Datenbank statt aus einem Portfolio. Geprüft wird genau das, was diesen Schritt von
einer Kennzahl je Kombination unterscheidet:

- Die Rastergröße kommt aus `backtest_runs.n_combinations`, **nicht** aus `count(*)`
  über die vorliegenden Results (ein ausgedünnter Lauf muss dieselbe Schwelle
  behalten).
- Der gespeicherte Sharpe ist annualisiert und wird mit `ann_factor` auf den Sharpe
  je Balken zurückgerechnet.
- Results ohne persistierte Momente bekommen NULL, keine Zahl.
- Ohne `ann_factor` bricht der Nachlauf sichtbar ab, statt still zu raten.

Die erwarteten Zahlen entstehen über die reine Rechenfunktion aus
`user_data.utils.metrics.deflated_sharpe` — die ist in `tests/test_deflated_sharpe.py`
gegen von Hand hergeleitete Werte abgesichert. Hier geht es um die Verdrahtung.
"""

import numpy as np
import pytest
from sqlalchemy import text

from user_data.utils.metrics.deflated_sharpe import deflated_sharpe_ratio

# Annualisierungsfaktor eines 4h-Laufs bei 365 Tagen Jahresfrequenz: 365*24/4 = 2190.
_ANN_FACTOR = 2190.0


def _insert_run(session, run_id: int, n_combinations: int, ann_factor) -> None:
    """Legt einen minimalen abgeschlossenen backtest_runs-Datensatz an."""
    session.execute(text(
        "INSERT INTO backtest_runs (id, strategy_family, strategy_name, symbol, exchange, "
        "timeframe, start_date, end_date, backtest_config_json, indicators_config_json, "
        "n_combinations, ann_factor, status, created_at) "
        "VALUES (:id, 'test', 'v1', 'FETUSDT', 'binance', '4h', '2022-01-01', '2024-01-01', "
        "'{}', '{}', :n, :ann, 'completed', NOW())"
    ), {'id': run_id, 'n': n_combinations, 'ann': ann_factor})


def _insert_result(
    session,
    result_id: int,
    run_id: int,
    sharpe_annualized,
    skew,
    kurtosis,
    bar_count: int = 4380,
) -> None:
    """Legt ein Result mit den vier Bausteinen des Nachlaufs an."""
    session.execute(text(
        "INSERT INTO backtest_results (id, run_id, params_hash, actual_params_json, "
        "sharpe_ratio, skew, kurtosis, bar_count) "
        "VALUES (:id, :run_id, :hash, '{}', :sharpe, :skew, :kurt, :bars)"
    ), {
        'id': result_id, 'run_id': run_id, 'hash': f'h{result_id}',
        'sharpe': sharpe_annualized, 'skew': skew, 'kurt': kurtosis, 'bars': bar_count,
    })


def _stored_dsr(session, run_id: int) -> list:
    """Gespeicherte DSR-Werte des Laufs, nach Result-ID sortiert."""
    rows = session.execute(text(
        'SELECT deflated_sharpe_ratio FROM backtest_results '
        'WHERE run_id = :run_id ORDER BY id'
    ), {'run_id': run_id}).fetchall()
    return [r.deflated_sharpe_ratio for r in rows]


def test_postrun_writes_values_of_the_pure_function(session):
    """Der Nachlauf schreibt genau das, was die reine Rechenfunktion liefert.

    Inklusive Rückrechnung des annualisierten Sharpe: die Funktion bekommt
    `sharpe_ratio / sqrt(ann_factor)`, nicht den gespeicherten Wert.
    """
    import user_data.utils.database.repository as repo

    sharpe_annualized = [1.8, 2.4, 3.1, 0.9]
    skew = [0.2, -0.4, 1.1, 0.0]
    kurtosis = [3.5, 6.0, 12.0, 3.0]

    _insert_run(session, 910001, n_combinations=4, ann_factor=_ANN_FACTOR)
    for idx, (sr, sk, ku) in enumerate(zip(sharpe_annualized, skew, kurtosis)):
        _insert_result(session, 910100 + idx, 910001, sr, sk, ku)
    session.commit()

    n_written = repo._calculate_deflated_sharpe(session.connection(), 910001)
    session.commit()

    assert n_written == 4

    expected = deflated_sharpe_ratio(
        sharpe=np.array(sharpe_annualized) / np.sqrt(_ANN_FACTOR),
        skew=np.array(skew),
        kurtosis=np.array(kurtosis),
        n=4,
        t=np.full(4, 4380.0),
    )
    assert _stored_dsr(session, 910001) == pytest.approx(expected, abs=1e-12)


def test_grid_size_comes_from_n_combinations_not_row_count(session):
    """Ein ausgedünnter Lauf behält die Schwelle seiner tatsächlichen Rastergröße.

    Zwei Läufe mit identischen Results — einer mit `n_combinations = 3` (alle
    Kombinationen liegen vor), einer mit `n_combinations = 3000` (auf drei Favoriten
    ausgedünnt). Käme `N` aus `count(*)`, wären beide gleich; richtig ist, dass der
    ausgedünnte Lauf die deutlich strengere Schwelle behält.
    """
    import user_data.utils.database.repository as repo

    sharpe_annualized = [1.5, 2.0, 2.6]
    for run_id, n_comb, first_result_id in ((910002, 3, 910200), (910003, 3000, 910300)):
        _insert_run(session, run_id, n_combinations=n_comb, ann_factor=_ANN_FACTOR)
        for idx, sr in enumerate(sharpe_annualized):
            _insert_result(session, first_result_id + idx, run_id, sr, 0.0, 3.0)
    session.commit()

    repo._calculate_deflated_sharpe(session.connection(), 910002)
    repo._calculate_deflated_sharpe(session.connection(), 910003)
    session.commit()

    small_grid = _stored_dsr(session, 910002)
    large_grid = _stored_dsr(session, 910003)

    # Gleiche Kandidaten, größeres Raster -> strengere Schwelle -> kleinere DSR.
    for small, large in zip(small_grid, large_grid):
        assert large < small

    expected_large = deflated_sharpe_ratio(
        sharpe=np.array(sharpe_annualized) / np.sqrt(_ANN_FACTOR),
        skew=np.zeros(3),
        kurtosis=np.full(3, 3.0),
        n=3000,
        t=np.full(3, 4380.0),
    )
    assert large_grid == pytest.approx(expected_large, abs=1e-12)


def test_results_without_moments_stay_empty(session):
    """Ohne Schiefe/Wölbung ist die Kennzahl nicht rechenbar — das Feld bleibt NULL.

    Ein leeres Feld ist ehrlich; eine Zahl aus fehlenden Momenten wäre erfunden. Die
    übrigen Results des Laufs bekommen trotzdem ihren Wert.
    """
    import user_data.utils.database.repository as repo

    _insert_run(session, 910004, n_combinations=3, ann_factor=_ANN_FACTOR)
    _insert_result(session, 910400, 910004, 1.5, 0.2, 3.5)
    _insert_result(session, 910401, 910004, 2.0, None, None)
    _insert_result(session, 910402, 910004, 2.5, 0.1, 4.0)
    session.commit()

    repo._calculate_deflated_sharpe(session.connection(), 910004)
    session.commit()

    stored = _stored_dsr(session, 910004)
    assert stored[0] is not None
    assert stored[1] is None
    assert stored[2] is not None


def test_single_combination_run_gets_no_value(session):
    """Bei einer einzigen Kombination gibt es keinen Mehrfachvergleich.

    Genau dieser Fall lieferte früher eine NaN und trug den Recompute-Schaden: eine
    Kennzahl, die je Kombination gerechnet wurde, musste hier scheitern. Jetzt bleibt
    das Feld ausdrücklich leer.
    """
    import user_data.utils.database.repository as repo

    _insert_run(session, 910005, n_combinations=1, ann_factor=_ANN_FACTOR)
    _insert_result(session, 910500, 910005, 1.5, 0.2, 3.5)
    session.commit()

    repo._calculate_deflated_sharpe(session.connection(), 910005)
    session.commit()

    assert _stored_dsr(session, 910005) == [None]


def test_missing_ann_factor_raises_instead_of_guessing(session):
    """Ohne Annualisierungsfaktor bricht der Nachlauf sichtbar ab.

    Der nicht annualisierte Sharpe ließe sich nur mit einer selbstgebauten
    Timeframe-Tabelle schätzen — genau das ist ausgeschlossen. Also lieber ein
    lauter Fehler als eine still falsche Zahl.
    """
    import user_data.utils.database.repository as repo

    _insert_run(session, 910006, n_combinations=2, ann_factor=None)
    _insert_result(session, 910600, 910006, 1.5, 0.2, 3.5)
    _insert_result(session, 910601, 910006, 2.5, 0.1, 4.0)
    session.commit()

    with pytest.raises(ValueError, match='Annualisierungsfaktor'):
        repo._calculate_deflated_sharpe(session.connection(), 910006)


def test_unknown_run_raises(session):
    """Ein nicht existierender Lauf ist ein Programmierfehler, kein stiller No-op."""
    import user_data.utils.database.repository as repo

    with pytest.raises(ValueError, match='existiert nicht'):
        repo._calculate_deflated_sharpe(session.connection(), 919999)

"""Tests für die Schreibsperre je OHLC-Timeframe-Datei.

Prüft `services/api/ohlc_file_lock.py` ohne echte Redis-Verbindung: die Sperre
nimmt eine Connection per Dependency Injection (`connection=...`), dafür genügt
ein Mock mit einem `.lock(...)`-Aufruf, der ein Lock-Objekt mit
`acquire()`/`extend()`/`release()` liefert (redis-py-Vertrag).
"""

from unittest.mock import MagicMock

import pytest

from services.api.ohlc_file_lock import (
    OhlcFileBusyError,
    ohlc_file_lock,
    ohlc_file_lock_key,
)


def test_schluessel_trennt_timeframes():
    """Zwei Timeframes derselben Börse schreiben verschiedene Dateien -> verschiedene Schlüssel."""
    assert ohlc_file_lock_key('binance', '4h') != ohlc_file_lock_key('binance', '1d')


def test_schluessel_trennt_boersen():
    """Dieselbe Timeframe-Datei auf zwei Börsen ist nicht dieselbe Datei."""
    assert ohlc_file_lock_key('binance', '4h') != ohlc_file_lock_key('bybit', '4h')


def test_schluessel_ist_fuer_dieselbe_datei_gleich():
    """Zwei Schreiber auf dieselbe Datei treffen sich am selben Schlüssel."""
    assert ohlc_file_lock_key('binance', '4h') == ohlc_file_lock_key('binance', '4h')
    assert 'binance' in ohlc_file_lock_key('binance', '4h')
    assert '4h' in ohlc_file_lock_key('binance', '4h')


def _mock_connection(acquire_result: bool = True) -> MagicMock:
    """Baut eine Redis-Connection-Attrappe mit einem Lock-Objekt."""
    conn = MagicMock()
    lock = MagicMock()
    lock.acquire.return_value = acquire_result
    conn.lock.return_value = lock
    return conn


def test_erfolgreicher_block_haelt_und_gibt_die_sperre_frei():
    """Erfolgreicher acquire: der Block läuft, danach wird die Sperre freigegeben."""
    conn = _mock_connection(acquire_result=True)

    with ohlc_file_lock('binance', '4h', ttl=2, wait=1, connection=conn) as held:
        assert held is conn.lock.return_value

    conn.lock.assert_called_once_with(
        'ohlc:file-lock:4h:binance', timeout=2, blocking=True, blocking_timeout=1,
        thread_local=False,
    )
    conn.lock.return_value.acquire.assert_called_once()
    conn.lock.return_value.release.assert_called_once()


def test_belegte_datei_wirft_busy_error_ohne_release():
    """Scheitert acquire() (Timeout beim Warten), wird OhlcFileBusyError geworfen —
    und release() nie aufgerufen, weil die Sperre nie gehalten wurde."""
    conn = _mock_connection(acquire_result=False)

    with pytest.raises(OhlcFileBusyError):
        with ohlc_file_lock('binance', '4h', ttl=2, wait=1, connection=conn):
            pytest.fail('Block darf bei gescheitertem acquire() nicht betreten werden')

    conn.lock.return_value.release.assert_not_called()


def test_exception_im_block_gibt_die_sperre_trotzdem_frei():
    """Ein Fehler beim Schreiben darf die Datei nicht dauerhaft blockiert lassen."""
    conn = _mock_connection(acquire_result=True)

    with pytest.raises(RuntimeError):
        with ohlc_file_lock('binance', '4h', ttl=2, wait=1, connection=conn):
            raise RuntimeError('Schreiben fehlgeschlagen')

    conn.lock.return_value.release.assert_called_once()


def test_verschiedene_timeframes_nutzen_verschiedene_redis_schluessel():
    """Zwei Sperren für verschiedene Timeframes rufen conn.lock() mit unterschiedlichem Key auf
    -> Nachweis, dass die Serialisierung je Datei gilt, nicht global (Akzeptanzkriterium 3)."""
    conn = _mock_connection(acquire_result=True)

    with ohlc_file_lock('binance', '4h', ttl=2, wait=1, connection=conn):
        pass
    with ohlc_file_lock('binance', '1d', ttl=2, wait=1, connection=conn):
        pass

    keys_used = [c.args[0] for c in conn.lock.call_args_list]
    assert keys_used == ['ohlc:file-lock:4h:binance', 'ohlc:file-lock:1d:binance']
    assert len(set(keys_used)) == 2

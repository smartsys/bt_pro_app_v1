"""
Redis-Verbindung

Zentrale Redis-Connection für RQ Queue und Worker.
"""

import os
import socket
from redis import Redis


def get_redis_connection() -> Redis:
    """Erstellt Redis-Connection aus Umgebungsvariablen.

    GEÄNDERT: Mit TCP-Keepalive und Health-Check. Ohne diese reißt die idle
    Verbindung unter Docker/WSL2 nach einigen Minuten still ab; der blockierende
    RQ-Dequeue (BLPOP, ~405s) läuft dann in einen Redis-Timeout, der Worker
    quittiert ('Redis connection timeout, quitting...') und der Container
    respawnt in einer Schleife. Keepalive hält die Verbindung während langer
    idle/Job-Phasen am Leben.
    """
    host = os.getenv('REDIS_HOST', 'redis_bt_pro_v1')
    port = int(os.getenv('REDIS_INTERNAL_PORT', '6379'))
    # Linux-spezifische Keepalive-Feineinstellung (im Container vorhanden);
    # fehlende Optionen werden übersprungen, damit es plattformunabhängig bleibt.
    keepalive_options: dict = {}
    for opt_name, value in (('TCP_KEEPIDLE', 30), ('TCP_KEEPINTVL', 10), ('TCP_KEEPCNT', 3)):
        opt = getattr(socket, opt_name, None)
        if opt is not None:
            keepalive_options[opt] = value
    return Redis(
        host=host,
        port=port,
        socket_keepalive=True,
        socket_keepalive_options=keepalive_options,
        health_check_interval=30,
    )


# Queue-Namen als Konstanten
RECOMPUTE_QUEUE_NAME: str = 'recompute'
BACKTEST_QUEUE_NAME: str = 'backtest'
OHLC_DOWNLOAD_QUEUE_NAME: str = 'ohlc_download'

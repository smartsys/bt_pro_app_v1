FROM debian:bookworm-slim

# Cron + Python3 + pip installieren
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        cron \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Minimale Python-Abhaengigkeiten fuer enqueue_reindex.py
RUN pip3 install --no-cache-dir --break-system-packages \
    rq==1.16.2 \
    redis==5.0.4 \
    psycopg2-binary==2.9.9 \
    SQLAlchemy==2.0.35 \
    python-dotenv==1.0.1

WORKDIR /app

# Crontab-Datei einbinden
COPY services/scheduler/crontab /etc/cron.d/reindex

# Berechtigungen setzen (cron erwartet Modus 644, kein execution bit)
RUN chmod 0644 /etc/cron.d/reindex && \
    crontab /etc/cron.d/reindex

# Log-Datei anlegen
RUN touch /var/log/cron.log

# Cron im Vordergrund starten
CMD ["cron", "-f"]

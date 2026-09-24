# syntax=docker/dockerfile:1
FROM python:3.13-slim

# System-Dependencies fuer TA-Lib und numerische Pakete
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    git \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# TA-Lib C-Library installieren
RUN wget -q http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz \
    && tar -xzf ta-lib-0.4.0-src.tar.gz \
    && cd ta-lib \
    && ./configure --prefix=/usr \
    && make \
    && make install \
    && cd .. \
    && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

WORKDIR /app

# Python Dependencies installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# VBT Pro vom Original installieren — Zugang per SSH-Key als BuildKit-Secret (kein Token, Key nie im Image).
# Wer baut, gibt seinen eigenen Key mit: --secret id=ssh_key,src=<pfad-zum-key> (eigene VBT-Pro-Lizenz noetig).
# GEÄNDERT: Version fest auf v2026.6.27 (Commit 7e2c8e8) — ohne Festlegung holte jeder Neubau
# still den neuesten Stand und veränderte damit die Rechenergebnisse. 2026.6.27 ist der Stand,
# den das Image vom 31.08.2026 enthielt. Gleicher Stand wie in requirements.txt (lokales venv);
# ein Versionswechsel ist eine bewusste Entscheidung.
RUN mkdir -p -m 0700 ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts
RUN --mount=type=secret,id=ssh_key \
    GIT_SSH_COMMAND='ssh -i /run/secrets/ssh_key -o IdentitiesOnly=yes' \
    pip install --no-cache-dir git+ssh://git@github.com/polakowo/vectorbt.pro.git@7e2c8e86425d28ed7d97a3e07fd548b0fc694323

# Arbeitsverzeichnis fuer gemounteten Code
WORKDIR /workspace

# user_data/ wird als Volume gemountet (-v ./user_data:/workspace/user_data)
# .env wird als Volume gemountet (-v ./.env:/workspace/.env)

CMD ["python"]

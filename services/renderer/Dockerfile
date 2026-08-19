# Renderer-Dienst — Playwright-Basis-Image, Chromium ist bereits enthalten.
# Bewusst NICHT das App-Image erweitert: Chromium samt Systembibliotheken hätte das
# Laufzeit-Image aller App-/Worker-Container um mehrere hundert MB aufgebläht.
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY services/renderer/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /app/requirements.txt

COPY services/renderer/server.py /app/renderer/server.py

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "renderer.server:app", "--host", "0.0.0.0", "--port", "8080"]

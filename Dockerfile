# ── Runtime image (Django + Gunicorn) ─────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Runtime libs for psycopg + CairoSVG PDF/PNG export in slim image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libcairo2 \
    libffi8 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    gosu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh docker-app.sh

RUN addgroup --system app && adduser --system --ingroup app --home /app app \
    && chown -R app:app /app

# Entrypoint starts as root, chowns staticfiles volume, then gosu app → docker-app.sh
# (Do not USER app here — see entrypoint.sh.)

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=8s --start-period=300s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/')"

ENTRYPOINT ["./entrypoint.sh"]

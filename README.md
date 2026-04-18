# nTarque

Django 5 app (Jinja2, HTMX) for planning and task workflows.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Optional: copy `.env.example` → `.env` and set `DEBUG=True` for Django’s detailed error pages while developing.

## Docker deployment

1. Copy environment template and edit secrets:

   ```bash
   cp .env.example .env
   ```

   Set at least `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS` (your domain or server IP), and `CSRF_TRUSTED_ORIGINS` with the full origin including scheme — and **port** when not 80/443 (e.g. `http://203.0.113.7:8080` or `https://yourdomain.com`).

2. Build and run:

   ```bash
   docker compose build
   docker compose up -d
   ```

3. Open **http://localhost** (Nginx on port 80). Override the HTTP port with `HTTP_PORT` in `.env` if needed.

The `web` service runs Gunicorn on port 8000 inside the network only; **Nginx** is the public entrypoint. PostgreSQL data is stored in the `pgdata` volume; collected static files use the `staticfiles` volume.

### Health checks

- Application: `GET /health/` returns plain `ok` for Docker and load balancer probes.

## GitHub Actions

CI runs Django checks (including deploy checks), the test suite, and a Docker image build on pushes and pull requests to `main` / `master`.
# sd-mindmap-pro

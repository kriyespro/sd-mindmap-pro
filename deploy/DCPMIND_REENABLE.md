# dcpmind.com — proper multi-app VPS setup

Use this on server `159.195.52.197` when other apps already run on the same host.

## Architecture

```
Browser → host nginx :443 (dcpmind.com only)
       → 127.0.0.1:8088 (Docker nginx)
       → Gunicorn :8000 (web container)
```

Other apps keep their own ports (`8080`, `8089`, `8881`, etc.). This app uses **8088 only**.

---

## Step 1 — `.env` (~/sd-mindmap-pro/.env)

```env
SECRET_KEY=nGnKN2GmdKfORsV2DoPGjASUy6bs70JfrwlmjVTimIYJqcCVbpmFKMMMBkkZ_NL7JB3o

DEBUG=False
USE_HTTPS=True

ALLOWED_HOSTS=dcpmind.com,www.dcpmind.com,159.195.52.197,127.0.0.1,localhost,nginx,web

CSRF_TRUSTED_ORIGINS=https://dcpmind.com,https://www.dcpmind.com

HTTP_PORT=8088

POSTGRES_DB=ntarque
POSTGRES_USER=ntarque
POSTGRES_PASSWORD=Kp9mX2vR7nQw4sL8jH5tYz3Bd6Nc4f

TIME_ZONE=UTC

GUNICORN_WORKERS=2
```

---

## Step 2 — Start Docker

```bash
cd ~/sd-mindmap-pro

# sync DB password if web failed before
docker compose up -d db
sleep 5
docker compose exec db psql -U ntarque -d ntarque -c "ALTER USER ntarque PASSWORD 'Kp9mX2vR7nQw4sL8jH5tYz3Bd6Nc4f';"

docker compose up -d
docker compose ps
docker compose logs --tail=50 web
```

Wait until `web` is **healthy**:

```bash
curl -s http://127.0.0.1:8088/health/
```

---

## Step 3 — Host nginx config

Copy repo template (or edit existing file):

```bash
cd ~/sd-mindmap-pro
sudo cp deploy/nginx-dcpmind-host-ssl.conf /etc/nginx/sites-available/dcpmind.com
```

If SSL cert paths differ, check:

```bash
sudo certbot certificates | grep -A3 dcpmind
```

---

## Step 4 — Enable nginx (CRITICAL)

**Never** use `sites-enabled/dcpmind.com` — it loads first alphabetically and breaks other apps.

```bash
# remove wrong link if present
sudo rm -f /etc/nginx/sites-enabled/dcpmind.com

# enable with name that sorts LAST
sudo ln -sf /etc/nginx/sites-available/dcpmind.com /etc/nginx/sites-enabled/zzz-dcpmind.com

sudo nginx -t
sudo systemctl reload nginx
```

---

## Step 5 — Verify (skip optional catch-all)

The `000-default-ssl-catchall.conf` snippet requires SSL certs on older nginx and can break reload.
**Use only the `zzz-dcpmind.com` symlink** — that is enough on your VPS.

```bash
curl -sI https://dcpmind.com | head -3
curl -sI https://mnxstore.com | head -3
curl -sI https://ornza.com | head -3
```

All should be **200** or **302**, not **400**.

---

## Step 6 — Superadmin (if needed)

```bash
cd ~/sd-mindmap-pro
docker compose exec -it web python manage.py createsuperuser
```

Login: https://dcpmind.com/login/

---

## Stop app later (without touching other apps)

```bash
cd ~/sd-mindmap-pro
docker compose down
sudo rm -f /etc/nginx/sites-enabled/zzz-dcpmind.com
sudo nginx -t && sudo systemctl reload nginx
```

Do **not** run `docker compose down -v` (deletes DB).

---

## Re-enable later

```bash
cd ~/sd-mindmap-pro
docker compose up -d
sudo ln -sf /etc/nginx/sites-available/dcpmind.com /etc/nginx/sites-enabled/zzz-dcpmind.com
sudo nginx -t && sudo systemctl reload nginx
```

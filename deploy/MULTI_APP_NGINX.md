# Multi-app VPS — fix HTTP 400 after adding dcpmind.com

## What happened

On a server with **multiple apps**, host nginx listens on **80/443** for all domains.

If `dcpmind.com` becomes the **default server** (or is the only SSL site), nginx sends **every other domain** to `127.0.0.1:8088` (dcpmind Docker).

Django then returns **400 Bad Request** because the `Host` header is e.g. `otherapp.com` but `.env` only allows `dcpmind.com`.

This is **not** a dcpmind bug — it is nginx routing.

---

## Diagnose (run on VPS)

```bash
# 1) Which nginx block catches each domain?
sudo nginx -T 2>/dev/null | grep -E "listen |server_name |default_server|proxy_pass"

# 2) Does other-domain hit dcpmind? (replace otherapp.com)
curl -sI -H "Host: otherapp.com" http://127.0.0.1/ | head -5

# 3) dcpmind logs — look for "Invalid HTTP_HOST header"
cd ~/sd-mindmap-pro
docker compose logs web --tail=50 | grep -i "host\|400\|disallowed"
```

If (2) returns headers from dcpmind or (3) shows `Invalid HTTP_HOST header`, routing is wrong.

---

## Fix (dcpmind enabled → other apps get 400)

**Cause on your VPS:** `dcpmind.com` is **first alphabetically** in `/etc/nginx/sites-enabled/`, so nginx makes it the **default SSL server** on port 443. Some requests hit `127.0.0.1:8088` → dcpmind Django → **400 DisallowedHost**.

**Quick fix (no other app config changes):**

```bash
# 1) Remove alphabetical-first symlink
sudo rm -f /etc/nginx/sites-enabled/dcpmind.com

# 2) Re-enable with name that sorts LAST (zzz-)
sudo ln -sf /etc/nginx/sites-available/dcpmind.com /etc/nginx/sites-enabled/zzz-dcpmind.com

sudo nginx -t
sudo systemctl reload nginx
```

**Do not add `000-default-ssl-catchall.conf`** on this VPS — nginx requires `ssl_certificate` on every `listen 443 ssl` block and it will fail reload.

---

## Fix (general)

### 1. Each app needs its own `server_name`

Example layout:

| File | server_name | proxy_pass |
|------|-------------|------------|
| `/etc/nginx/sites-available/dcpmind.com` | `dcpmind.com www.dcpmind.com` | `http://127.0.0.1:8088` |
| `/etc/nginx/sites-available/otherapp.com` | `otherapp.com www.otherapp.com` | `http://127.0.0.1:3000` (that app's port) |

**Never** use `server_name _;` on dcpmind host config.

### 2. Re-enable other app configs

```bash
ls -la /etc/nginx/sites-enabled/

# Re-link missing apps (example)
sudo ln -sf /etc/nginx/sites-available/otherapp.com /etc/nginx/sites-enabled/otherapp.com

sudo nginx -t
sudo systemctl reload nginx
```

### 3. Remove accidental default_server from dcpmind

Edit `/etc/nginx/sites-available/dcpmind.com` — `listen` lines must **not** include `default_server`:

```nginx
listen 80;
listen 443 ssl;   # after certbot
```

Not:

```nginx
listen 80 default_server;
listen 443 ssl default_server;
```

If another app should be default, set `default_server` on **that** app's block only.

### 4. After certbot broke other SSL sites

```bash
sudo certbot certificates
ls /etc/nginx/sites-enabled/
```

Re-run certbot per domain (do not delete other sites):

```bash
sudo certbot --nginx -d otherapp.com -d www.otherapp.com
```

### 5. dcpmind `.env` (keep strict — do not add other domains)

```env
ALLOWED_HOSTS=dcpmind.com,www.dcpmind.com,159.195.52.197,127.0.0.1,localhost,nginx,web
CSRF_TRUSTED_ORIGINS=https://dcpmind.com,https://www.dcpmind.com
USE_HTTPS=True
HTTP_PORT=8088
```

Then:

```bash
cd ~/sd-mindmap-pro
docker compose up -d
```

---

## Verify

```bash
curl -sI https://dcpmind.com/ | head -3
curl -sI https://otherapp.com/ | head -3
```

Both should return **200** (or 302), not **400**.

Direct dcpmind (bypass host nginx): `http://159.195.52.197:8088/` — should still work for debugging.

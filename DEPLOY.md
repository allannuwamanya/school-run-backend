# Deployment Guide — SchoolRun on the shared VPS

Backend + admin console, both served from **one domain** behind host-level Nginx, on the same droplet that already runs other apps (e.g. "Bible Banter").

> **Key rule:** only the **host Nginx** listens on ports 80/443. Docker containers are internal-only, reachable solely via `proxy_pass` from Nginx.

## Architecture

```
Internet
   |
   v
Host Nginx (schoolrun.oddshoesdev.xyz, ports 80/443, SSL termination)
   |-- /            -> static React build (admin console), served directly from disk
   |-- /static/     -> alias, Django's collectstatic output
   |-- /media/      -> alias, uploaded files (driver docs, etc.) — persists across redeploys
   |-- /api/        -> proxy_pass -> schoolrun-web container (:8010 on the host, :8000 in-container)
```

Django's own built-in admin site (`django.contrib.admin`, mounted at `/admin/`) is **deliberately not exposed** — the React console is the only admin surface. This also avoids a real path collision: the React app's own client-side routes also start with `/admin/` (`/admin/users`, `/admin/dispatch`, ...).

## Prerequisites

- This VPS already has Docker, the `app-network` Docker network, host Nginx, and Certbot set up (shared with other apps on this box) — don't recreate any of these.
- DNS: `schoolrun.oddshoesdev.xyz` → this droplet's IP.

## 1. Pre-flight checks (do these first — no live server access when this was written)

```bash
docker ps -a                              # confirm no existing container named schoolrun-web/schoolrun-celery/schoolrun-redis
docker network inspect app-network        # see what's already attached
sudo ss -tlnp                             # confirm host port 8010 is free; note what other apps use
sudo nginx -T | grep -A2 proxy_pass       # cross-check existing proxy targets
dig +short schoolrun.oddshoesdev.xyz      # confirm DNS resolves here
```

## 2. Host directories (static/media persist here — this is the whole point of leaving Render)

```bash
sudo mkdir -p /home/schoolrun/staticfiles /home/schoolrun/media
sudo chown -R $USER:$USER /home/schoolrun
chmod -R 755 /home/schoolrun
```

## 3. Backend

```bash
git clone <this-repo> /home/schoolrun/app
cd /home/schoolrun/app
```

Create `/home/schoolrun/app/.env` (never committed — see the table below for every value).

```bash
docker network ls | grep app-network   # confirm it already exists, do NOT create it
docker compose config                  # dry-run validation
docker compose up -d --build
docker compose ps                      # all three services should report healthy
docker compose logs -f schoolrun-web   # confirm migrate/collectstatic succeeded, uvicorn started
```

### `.env` values

| Variable | Action | Value |
|---|---|---|
| `SECRET_KEY` | Reuse | Exact value from the current Render deploy — rotating invalidates every live JWT/session. |
| `DEBUG` | Set | `0` |
| `ALLOWED_HOSTS` | Set | `schoolrun.oddshoesdev.xyz,127.0.0.1,localhost` (localhost needed for the in-container healthcheck) |
| `CORS_ALLOWED_ORIGINS` | Leave unset | Not needed — admin console and API are same-origin now. |
| `CSRF_TRUSTED_ORIGINS` | Set | `https://schoolrun.oddshoesdev.xyz` |
| `DB_CHOICE` | Reuse | `postgres` |
| `DATABASE_URL` | Reuse | Same Neon connection string Render uses today — no DB migration needed. |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Set | `redis://schoolrun-redis:6379/0` — must point at this compose stack's Redis, not Render's. |
| `GOOGLE_CLIENT_ID` | Reuse | Same OAuth client ID as Render. |
| `SITE_NAME` | Reuse | `SchoolRun` |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Reuse | Same bootstrap creds (no-op in practice — the reused Neon DB already has a superuser). |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Reuse | Full service-account JSON as one line. |
| `GDAL_LIBRARY_PATH` / `GEOS_LIBRARY_PATH` | Omit | Windows-local-dev-only; Linux auto-discovers the apt-installed `.so` files. |

## 4. Admin console (static build)

No long-running Node process — build with a throwaway container, Nginx serves the output directly off disk.

```bash
git clone <frontend-repo> /home/schoolrun/admin-fe
cd /home/schoolrun/admin-fe
docker run --rm -v "$PWD":/app -w /app node:22-slim sh -c \
  "npm ci && VITE_API_BASE_URL=/api VITE_USE_MOCKS=false npm run build"
```
Confirm `dist/` now exists at `/home/schoolrun/admin-fe/dist`.

`VITE_API_BASE_URL=/api` is relative (same-origin) — Vite bakes this in at build time, so it must be set correctly on every build, not just left in a `.env` next to the output.

## 5. Nginx

Create `/etc/nginx/sites-available/schoolrun.oddshoesdev.xyz`:

```nginx
server {
    listen 80;
    server_name schoolrun.oddshoesdev.xyz;

    client_max_body_size 20m;   # driver document/photo uploads — Nginx's 1m default breaks this

    root /home/schoolrun/admin-fe/dist;
    index index.html;

    location /static/ {
        alias /home/schoolrun/staticfiles/;
    }

    location /media/ {
        alias /home/schoolrun/media/;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8010;   # no trailing path — preserves the /api/ prefix
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Deliberately no location for Django's own /admin/ — never exposed.
    # A request for /admin/anything falls through to the SPA catch-all
    # below, which is correct: that's the React app's own /admin/* routes.

    location / {
        try_files $uri /index.html;   # SPA fallback
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/schoolrun.oddshoesdev.xyz /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d schoolrun.oddshoesdev.xyz
```

Certbot clones the `location` blocks into the 443 server it creates — **re-open the file afterward and confirm** every `proxy_set_header` line, `client_max_body_size`, both `alias` blocks, and `try_files` survived the clone. Patch back in anything missing, then `nginx -t && systemctl reload nginx` again.

## 6. Verify

1. `docker compose ps` — all three containers healthy.
2. `curl http://127.0.0.1:8010/health/` on the VPS, bypassing Nginx — 200.
3. `curl -I https://schoolrun.oddshoesdev.xyz/` externally — 200, valid cert, admin console loads.
4. Log in through the browser at the real domain with a real test account — confirms DB connectivity + auth end-to-end.
5. `curl -I https://schoolrun.oddshoesdev.xyz/static/admin/css/base.css` — 200, served by Nginx directly.
6. **Media persistence** (the whole reason for this migration): upload a driver document through the real flow → confirm it's fetchable over HTTPS → run a full redeploy (`docker compose up -d --build`) → re-fetch the same URL and confirm it's still there.
7. `docker compose logs schoolrun-celery` — shows the ready banner.
8. Confirm a document/photo URL in an API response renders as `https://`, not `http://`.
9. Confirm `https://schoolrun.oddshoesdev.xyz/admin/` renders the React SPA, **not** a Django admin login — proving that path was never proxied to Django.
10. Confirm Bible Banter's own site still responds normally after the Nginx reload.

## Ongoing redeploys

**Backend:**
```bash
cd /home/schoolrun/app
git pull
docker compose up -d --build
```

**Admin console:**
```bash
cd /home/schoolrun/admin-fe
git pull
docker run --rm -v "$PWD":/app -w /app node:22-slim sh -c \
  "npm ci && VITE_API_BASE_URL=/api VITE_USE_MOCKS=false npm run build"
```
No container restart or Nginx reload needed for the frontend — Nginx reads `dist/` straight off disk, so the new build is live the moment the rebuild finishes.

## Explicitly out of scope here

- Comprehensive audit logging for every admin action (only account deletion logs anything today, via the undeletable `AccountDeletionLog` model) — a separate follow-up feature.
- React Native conversion of the parent/driver-facing app.
- S3/Cloudflare R2 object storage — moot now that this VPS has a persistent disk.

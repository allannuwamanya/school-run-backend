# Deploying SchoolRun to the VPS

Target: **Ubuntu 24.04**, `172.233.141.73`, domain **schoolrun.oddshoesdev.xyz**.

One box runs everything as Docker containers behind a host nginx that
terminates TLS:

```
                         ┌──────────── host nginx (:80/:443, TLS) ───────────┐
schoolrun.oddshoesdev.xyz│  /api /health        → 127.0.0.1:8010 (Django)    │
                         │  /static /media      → /home/schoolrun/*          │
                         │  everything else      → 127.0.0.1:8020 (frontend)  │
                         │  (/admin is the React ops console, not Django)     │
                         └────────────────────────────────────────────────────┘
     backend compose: schoolrun-web, schoolrun-celery, schoolrun-postgres, schoolrun-redis
     frontend compose: schoolrun-frontend
```

Run everything below **as root over SSH** (`ssh root@172.233.141.73`) unless noted.
Fill in every `REPLACE_...` placeholder with a real value — never commit secrets.

---

## 1. DNS (do this first so TLS can be issued later)

At your DNS provider for `oddshoesdev.xyz`, add:

| Type | Name       | Value               |
|------|------------|---------------------|
| A    | schoolrun  | `172.233.141.73`    |
| AAAA | schoolrun  | `2a01:7e03::2000:f0ff:fe81:71af` *(optional, IPv6)* |

Verify it resolves before doing TLS: `dig +short schoolrun.oddshoesdev.xyz`.

---

## 2. Install Docker, nginx, certbot

```bash
apt update && apt upgrade -y

# Docker Engine + compose plugin
curl -fsSL https://get.docker.com | sh
docker compose version   # sanity check

# nginx + certbot
apt install -y nginx certbot python3-certbot-nginx git

# Firewall
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
```

---

## 3. Get the code

```bash
mkdir -p /opt/schoolrun && cd /opt/schoolrun
git clone https://github.com/Odd-Shoes-Dev/school-run-be.git backend
git clone https://github.com/Odd-Shoes-Dev/school-run-fe.git frontend
```

Create the shared Docker network and the host dirs the backend mounts:

```bash
docker network create app-network
mkdir -p /home/schoolrun/staticfiles /home/schoolrun/media
```

---

## 4. Backend env

```bash
cd /opt/schoolrun/backend
cp .env.production.example .env
nano .env      # fill in every REPLACE_... value
```

Generate the two secrets it needs:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # SECRET_KEY
openssl rand -base64 24                                          # POSTGRES_PASSWORD
```

Make sure `POSTGRES_PASSWORD` and the password inside `DATABASE_URL` match, and
paste the Firebase service-account JSON into `FIREBASE_SERVICE_ACCOUNT_JSON`
(one line) so push works.

---

## 5. Database

### 5a. Start Postgres first (empty)

```bash
cd /opt/schoolrun/backend
docker compose up -d schoolrun-postgres
docker compose exec schoolrun-postgres pg_isready -U schoolrun   # wait for "accepting connections"
```

### 5b. Bring the data over — pick ONE:

**Option A — Fresh start (simplest).** If Neon only holds throwaway test data,
skip the migration entirely; Django will build the schema on first boot in the
next step, and `entrypoint.sh` creates the admin from `ADMIN_*`. You can reseed
demo data later with `docker compose exec schoolrun-web python manage.py seed_school_run_data`.

**Option B — Migrate the Neon data.** Uses your existing Neon `DATABASE_URL`
(the one in your local dev `.env` — keep it secret, don't paste it into any
committed file). First check Neon's major version and match the container image
in `docker-compose.yml` if it isn't 16:

```bash
# From your machine or the VPS, with the Neon URL in an env var:
export NEON_URL='postgresql://...neon.tech/neondb?sslmode=require'
docker run --rm postgis/postgis:16-3.4 psql "$NEON_URL" -tAc "show server_version;"
```

Dump from Neon and restore into the container (plain SQL = most version-tolerant):

```bash
docker run --rm postgis/postgis:16-3.4 \
  pg_dump "$NEON_URL" --no-owner --no-privileges --format=plain \
  > /root/neon.sql

docker compose exec -T schoolrun-postgres \
  psql -U schoolrun -d schoolrun -c "CREATE EXTENSION IF NOT EXISTS postgis;"

docker compose exec -T schoolrun-postgres \
  psql -U schoolrun -d schoolrun < /root/neon.sql

rm /root/neon.sql
```

---

## 6. Start the backend

```bash
cd /opt/schoolrun/backend
docker compose up -d --build
docker compose ps
docker compose logs -f schoolrun-web    # watch migrate/collectstatic, ctrl-C when healthy
```

`schoolrun-web` runs migrations + collectstatic + admin bootstrap on boot, then
serves on `127.0.0.1:8010`. Quick check: `curl -s localhost:8010/health/`.

---

## 7. Start the frontend

```bash
cd /opt/schoolrun/frontend
# Optional: bake the Google Maps key into the web build
echo "VITE_GOOGLE_MAPS_KEY=REPLACE_WITH_MAPS_KEY" > .env
docker compose up -d --build
curl -s -o /dev/null -w "%{http_code}\n" localhost:8020   # expect 200
```

---

## 8. Host nginx + TLS

```bash
cp /opt/schoolrun/backend/deploy/nginx/schoolrun.oddshoesdev.xyz.conf \
   /etc/nginx/sites-available/schoolrun.oddshoesdev.xyz.conf
ln -sf /etc/nginx/sites-available/schoolrun.oddshoesdev.xyz.conf \
   /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# Issue the certificate (edits the vhost to add :443 + redirect)
certbot --nginx -d schoolrun.oddshoesdev.xyz --agree-tos -m admin@oddshoesdev.xyz --redirect
```

Certbot installs a renewal timer automatically; confirm with
`systemctl list-timers | grep certbot`.

---

## 9. Point the apps at the new backend

- **Mobile** (`school-run-mobile/.env`): set
  `EXPO_PUBLIC_API_BASE_URL=https://schoolrun.oddshoesdev.xyz/api`, then rebuild
  the app (`npx expo run:android` / a new EAS build) — this is inlined at build
  time, a JS reload won't pick it up.
- **Google OAuth**: in Google Cloud console, add
  `https://schoolrun.oddshoesdev.xyz` to the OAuth client's **Authorized
  JavaScript origins** (web sign-in) so Google login works on the new domain.

---

## 10. Verify

```bash
curl -s https://schoolrun.oddshoesdev.xyz/health/         # backend via TLS
curl -sI https://schoolrun.oddshoesdev.xyz/               # frontend index
```

Open `https://schoolrun.oddshoesdev.xyz/` (web app) in a browser. The ops
console lives at `/admin/` and is part of the React frontend — there is no
separate Django admin.

---

## Day-2 ops

```bash
# Redeploy after pushing changes
cd /opt/schoolrun/backend  && git pull && docker compose up -d --build
cd /opt/schoolrun/frontend && git pull && docker compose up -d --build

# Logs / status
docker compose logs -f schoolrun-web
docker compose logs -f schoolrun-celery
docker compose ps

# Database backup (run on a schedule)
docker compose exec -T schoolrun-postgres \
  pg_dump -U schoolrun schoolrun | gzip > /root/backups/schoolrun-$(date +%F).sql.gz
```

If the API misbehaves over HTTPS (CSRF), the proxy is already sending
`X-Forwarded-Proto`; add `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`
to `main/settings.py` and redeploy.

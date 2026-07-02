# SchoolRun — Backend API & Geo-Logistics Service

SchoolRun is a robust, developer-friendly backend for managing school commute logistics, driver routing, and event-stamped trip manifests. It provides a secure, role-scoped REST API for the React PWA frontend (used by parents and drivers) and a comprehensive admin console for operational staff.

Rather than running heavy realtime WebSockets or WebSockets-over-Redis, SchoolRun captures **one-shot GPS event stamps** at the precise moments drivers check in. This allows parents to follow along via a clear status timeline showing timestamps and distance from the target pin.

---

## 🏛 Architecture

```mermaid
graph TD
    subgraph Client Tier
        PWA[React PWA - Parents & Drivers]
        AdminPanel[Django Admin Console]
    end

    subgraph Service Tier
        DRF[DRF REST API - JWT Auth]
        RouteEngine[Route Engine - Haversine & nearest-neighbour]
        CeleryJobs[Celery Workers - Nightly manifest generator]
    end

    subgraph Infrastructure
        DB[(PostgreSQL + PostGIS)]
        RedisBroker[(Redis - Celery Broker)]
    end

    subgraph External Integrations
        EgoSMS[EgoSMS - SMS notifications]
        FCM[FCM - Web Push notifications]
        Flw[Flutterwave - Subscriptions]
    end

    PWA -->|REST / JWT| DRF
    AdminPanel -->|Django ORM| DRF
    DRF --> RouteEngine
    CeleryJobs --> RouteEngine
    RouteEngine --> DB
    CeleryJobs -.->|Task Queue| RedisBroker
    DRF -.->|Push Notifications| FCM
    DRF -.->|SMS alerts| EgoSMS
    DRF -.->|Payment processing| Flw
```

---

## 🚀 Key Features

* **Phone-First Authentication**: Password-based login using phone numbers (no usernames/emails required) with role-scoped permissions (Parent, Driver, Admin).
* **Nightly Trip & Stop Dispatcher**: A background Celery job runs nightly to build manifests using a **greedy nearest-neighbor spatial algorithm** that computes optimal pickup paths.
* **One-Shot GPS Verification**: When drivers tap "Picked up" or "Arrived", their browser's location coordinates are validated server-side against target school boundaries and home coordinates (`ST_DWithin` / Python Haversine fallback) to auto-mark `gps_verified`.
* **Zero-Config Local Fallback**: Dynamic fallback utilities mock PostGIS (`PointField`, `Point`) and Postgres (`ArrayField`) components using SQLite strings and standard JSON fields if system-level GIS libraries (`GDAL`) are missing. Runs locally out of the box!
* **Transactional Email & Push Notifications**: Integrates with external SMS (EgoSMS) and Web Push (FCM) providers to update parents on manifest status events.

---

## 📂 Domain Structure

The application codebase is modularized into focused Django sub-apps:

* **`accounts`**: Custom user identity, phone credentials, parent profiles, driver onboarding profiles, and verification documents.
* **`children`**: Registration of children, school geofences, and child-specific transport schedules.
* **`trips`**: Driver-to-parent assignments, daily active trips, stop sequences, and live location caches.
* **`payments`**: Subscription plans (Standard, Premium, Family+), transactions, Flutterwave payment gateways, and wallet balances.
* **`incidents`**: Safety incident logs, emergency panic alerts, and direct operational messaging threads.
* **`zones`**: Geographic zoning boundaries for grouping assignments and routes.

---

## ⚙️ Backend Setup

### Prerequisites
* Python 3.10+
* Redis (running for Celery queue)
* PostGIS (optional, required for production geography checks)

### Local Environment Setup (Zero-Config Fallback)
If system-level libraries like `GDAL` or `libproj` are missing, the project will automatically start in **SQLite fallback mode**.

1. **Clone and Create Virtual Environment**:
   ```bash
   git clone <repo-url>
   cd school-run-be
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment (`.env`)**:
   Create a `.env` file from the template:
   ```bash
   cp .env.example .env
   ```
   Add a generated `SECRET_KEY` and set `DB_CHOICE=sqlite`.

4. **Run Migrations & Create Superuser**:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   python manage.py create_super_user
   ```
   *Note: Creating a superuser will prompt for a **phone number** (primary identity) instead of username.*

5. **Start Development Server**:
   ```bash
   python manage.py runserver
   ```

---

## ⏰ Background Jobs (Celery & Redis)

Trips and stop sequences are generated every night for the next day.

### Run Celery Worker:
```bash
celery -A main worker -l info
```

### Run Celery Beat Scheduler:
```bash
celery -A main beat -l info
```

### Running Nightly Job Manually (Management Command):
You can manually run or test the manifest generation command:
```bash
python manage.py shell -c "from trips.tasks import generate_daily_manifests; generate_daily_manifests.delay()"
```

---

## 🔌 API Endpoints (Phase 1 — Frontend Contract)

All endpoints are under `/api/` and return plain JSON. Auth uses **JWT** (`Authorization: Bearer <access>`).  
The full contract spec is in [`API_CONTRACT.md`](https://github.com/Odd-Shoes-Dev/school-run-fe/blob/main/API_CONTRACT.md) (frontend repo).

### Auth (public)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Register a parent (`phone`, `password`, `full_name`) |
| POST | `/api/auth/login` | Login with `phone` + `password` |
| POST | `/api/auth/refresh` | Refresh JWT access token |

### Account (any authenticated)
| Method | Path | Description |
|--------|------|-------------|
| GET/PATCH | `/api/me` | Get/update profile and preferences |

### Schools (any authenticated)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/schools?q=` | Search schools by name |

### Children & Schedule (parent only)
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/api/children` | List or create a child |
| GET/PATCH/DELETE | `/api/children/{id}` | Retrieve, update, or soft-delete a child |
| PUT | `/api/children/{id}/schedule` | Set child's weekly schedule |

### Dashboard (parent only)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dashboard` | Today's trip status per child |
| GET | `/api/parent/driver` | Assigned driver & verification status |

### Driver (driver only)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/driver/manifest?date=` | Today's manifest with ordered stops |
| POST | `/api/driver/trips/{id}/start` | Mark trip in progress |
| POST | `/api/driver/trips/{id}/complete` | Mark trip completed |

### Stops (driver only — one-shot GPS)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/stops/{id}/pickup` | Mark child picked up (with GPS) |
| POST | `/api/stops/{id}/dropoff` | Mark child dropped off (with GPS) |
| POST | `/api/stops/{id}/no-show` | Mark child as no-show |

### History (parent only)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/history?type=` | Paginated ride history |

### Notifications & Devices (any authenticated)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/notifications?unread=` | List notifications |
| POST | `/api/notifications/read` | Mark notifications as read |
| POST | `/api/devices` | Register FCM push token |

### Response formats
- **Success**: plain JSON matching the contract shapes
- **List endpoints**: `{ "count": N, "next": url|null, "previous": url|null, "results": [...] }`
- **Errors**: `{ "detail": "message" }` or `{ "field": ["message"] }`
- **Geo**: Always `{ "lat": float, "lng": float }`

---

## 🗺 Production Deployments (Postgres + PostGIS)

For production environments, PostGIS must be installed and active.

1. **System Libraries**:
   ```bash
   sudo apt install binutils libproj-dev gdal-bin libgdal-dev
   ```

2. **PostgreSQL Setup**:
   Log in to PostgreSQL as superuser and enable PostGIS:
   ```sql
   CREATE EXTENSION IF NOT EXISTS postgis;
   ```

3. **Update `.env`**:
   Set `DB_CHOICE=postgres` and provide your `DATABASE_URL` (e.g. `postgis://user:pass@host:port/dbname`).
# Changelog & Progress Tracker

This document keeps track of all completed components, database schemas, background workers, and APIs added to the **SchoolRun** backend.

---

## 📅 Version 1.0.0 (Phase 1 Database & Core Services)
*Status: Database Complete, Ready for API Controllers*

### 🔑 Authentication & Identity (`accounts`)
* **[Added]** Custom User Model (`CustomUser`): Shifted authentication credentials from standard email/username to **phone-first credentials** to align with regional requirements (Uganda/Lagos).
* **[Added]** User Role Choices: Added role checks for `PARENT`, `DRIVER`, and `ADMIN`.
* **[Added]** User Preference Flags: Built database fields for `push_notifications_enabled`, `location_sharing_enabled`, and `dark_mode`.
* **[Added]** Verification Documents: Implemented `VerificationDocument` with file storage and status choices (`PENDING`, `VERIFIED`, `CLEAR`, `REJECTED`) for verifying driver documents.
* **[Added]** Profile Associations: Integrated `Parent` and `Driver` one-to-one models directly under the accounts system for clean reference.

### 🏫 Logistics & Domain Models (`children`, `trips`)
* **[Added]** School Reference: Added `School` model with GPS pin geofencing bounds.
* **[Added]** Child Profile: Added `Child` registration with photo, allergies, blood type, and pickup coordinates.
* **[Added]** Child Schedule: Created `Schedule` to map transport days (ISO weekday integers 1-7) and pickup/drop-off times.
* **[Added]** Active Assignments: Created `Assignment` table to connect a verified driver to a parent, enforcing a unique constraint of one active driver per parent.
* **[Added]** Trips & Stops:
  * `Trip` model with service date, direction (`TO_SCHOOL`, `TO_HOME`), and status (`SCHEDULED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`).
  * `Stop` model with seq numbers, ETA time, and **event-stamped GPS coordinates** (`picked_point`, `dropped_point`) plus timestamps.

### ⚙️ Database Fallback Layer (`main`)
* **[Added]** Dynamic GIS Fallback Utility (`main/gis_fallback.py`):
  * Solved system `GDAL` library exceptions by dynamically mocking GeoDjango `PointField` and `Point` classes if they are missing locally.
  * Solved `psycopg/psycopg2` module requirements for PostgreSQL `ArrayField` in SQLite environments by falling back to standard `JSONField` serialization.
  * Allows developers to run `migrate`, seed, and run test suites locally using SQLite with no extra system configurations.

### ⏰ Background Tasks & Manifests (`trips/tasks.py`)
* **[Added]** Celery Nightly Dispatcher: Created `generate_daily_manifests` shared task to automatically spin up trips for active driver assignments for the next day.
* **[Added]** Route Path Solver:
  * Implemented greedy nearest-neighbor algorithm using Haversine calculation to dynamically order children's pickup stops by geographic distance.
  * Implemented reverse sequencing for afternoon school-to-home drops.

### 🎛 Admin Interface & Bootstrapping
* **[Added]** Admin Panel Configuration: Added detail grids and list filters for `CustomUser`, `School`, `Child`, `Assignment`, `Trip`, `Driver`, and `VerificationDocument`.
* **[Added]** Seeding script (`seed_school_run_data`): Management command to quickly populate zones and report schedules.
* **[Added]** Superuser bootstrapper (`create_super_user`): Allows instant bootstrapping of admin accounts using environment variables.

---

## 📅 Version 1.1.0 (Phase 1 API — Frontend Contract)
*Status: Deployed — All Phase 1 Endpoints Live*

### 🔌 API Endpoints Added (`api/views.py`, `api/serializers.py`)
* **[Added]** Auth endpoints (`/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`):
  * Phone-based registration and login returning JWT `{ access, refresh, user }`.
  * `Parent` profile auto-created on registration with `emergency_contact`.
* **[Added]** Account endpoint (`GET/PATCH /api/me`):
  * Returns `{ user, is_verified, preferences }` with full_name and preference updates.
* **[Added]** Schools endpoint (`GET /api/schools?q=`):
  * Searchable school lookup returning `{ id, name, address, point }`.
* **[Added]** Children CRUD endpoints (`GET/POST /api/children`, `GET/PATCH/DELETE /api/children/{id}`):
  * Full child profile management with school association and pickup geolocation.
* **[Added]** Schedule endpoint (`PUT /api/children/{id}/schedule`):
  * Weekly schedule with morning/afternoon times and ISO weekday array.
* **[Added]** Parent dashboard (`GET /api/dashboard`):
  * Aggregates each child's today status (trip direction, stop status, ETA, position, last GPS event).
  * Includes assigned driver info (name, plate, phone, rating).
* **[Added]** Parent driver info (`GET /api/parent/driver`):
  * Returns assigned driver details and document verification status.
* **[Added]** Driver manifest (`GET /api/driver/manifest?date=`):
  * Returns trip list with ordered stops, child info, and summary.
* **[Added]** Trip actions (`POST /api/driver/trips/{id}/start`, `/api/driver/trips/{id}/complete`):
  * Status transitions from SCHEDULED → IN_PROGRESS → COMPLETED.
* **[Added]** Stop actions (`POST /api/stops/{id}/pickup|dropoff|no-show`):
  * One-shot GPS capture with haversine distance verification against target pin.
  * Auto-promotes next stop to `NEXT` status.
  * Creates `Notification` record for the child's parent on pickup/dropoff.
* **[Added]** History endpoint (`GET /api/history?type=`):
  * Paginated ride history from completed trips.
* **[Added]** Notifications endpoints (`GET /api/notifications`, `POST /api/notifications/read`):
  * List and batch-mark-read with `all` or `ids` support.
* **[Added]** Device registration (`POST /api/devices`):
  * FCM push token registration with `Device` model persistence.
* **[Fixed]** Error response format — exception handler now includes `detail` field for frontend compatibility.
* **[Fixed]** Dashboard `today_date()` returning `date` class instead of `date.today()`.
* **[Fixed]** Stop timestamps using `timezone.now()` instead of `date.today()`.
* **[Added]** `Device` model in `accounts` for FCM token storage.

### 📝 Documentation
* **[Added]** Full API endpoint reference to `README.md` with method, path, and auth requirements.
* **[Updated]** `CHANGELOG.md` tracking all Phase 1 API deliveries.

---

## 📅 Version 1.2.0 (Phase 1 API — Admin Console & Production Hardening)
*Status: Deployed — All Admin Endpoints Live on Neon Postgres*

### 👨‍💼 Admin Console API (`api/admin_views.py`, `api/admin_serializers.py`, `api/admin_permissions.py`)
* **[Added]** Admin permission gate (`IsAdmin`) — role-based access enforcing `role=ADMIN`.
* **[Added]** `GET /api/admin/overview` — aggregate stats (total drivers, parents, active trips, incidents, pending verifications, today's revenue).
* **[Added]** `GET /api/admin/drivers`, `GET /api/admin/drivers/{id}` — driver list with verification status and detail with document history.
* **[Added]** `POST /api/admin/drivers/{id}/approve`, `POST /api/admin/drivers/{id}/reject`, `POST /api/admin/drivers/{id}/request-docs` — driver verification workflow.
* **[Added]** `POST /api/admin/drivers/create` — admin-side driver creation with auto-user provisioning.
* **[Added]** `POST /api/admin/drivers/{id}/assign`, `POST /api/admin/drivers/{id}/unassign` — assign/unassign a driver to/from a parent.
* **[Added]** `GET /api/admin/parents`, `POST /api/admin/parents/{id}/suspend` — parent list and suspension.
* **[Added]** `GET /api/admin/zones` — zone list with computed driver/family/active-route counts.
* **[Added]** `GET /api/admin/dispatch` — active trips with next-stop position for fleet map (approximate van location from scheduled stop coords — no live GPS ping model yet).
* **[Added]** `GET /api/admin/payments`, `POST /api/admin/payments/{id}/refund` — transaction list and refund processing.
* **[Added]** `GET /api/admin/incidents`, `POST /api/admin/incidents/{id}/resolve` — incident list and resolution.
* **[Added]** `GET /api/admin/analytics` — current-state aggregates (ridership, on-time %, revenue, zone breakdown) with trend fields at 0 (no historical snapshot table yet).

### 🗄️ Database & Infrastructure
* **[Added]** `zone` ForeignKey on `Driver` and `Parent` models (`accounts/migrations/0003`) — enables real zone-level driver/family counts.
* **[Fixed]** `Zone.driver_count`, `Zone.family_count`, and `Zone.active_route_count` — redefined to query actual relations (were dead code pointing at undefined reverse relations).
* **[Changed]** Backend switched from SQLite (local) / Render Postgres (prod) to **Neon Postgres** with real PostGIS geography columns — GDAL/GEOS enabled in Docker and via optional Windows env vars.
* **[Added]** `AlterField` migrations fixing frozen `geography=True` columns on `Child.pickup_point`, `School.location`, `Stop.picked_point`, and `Stop.dropped_point`.
* **[Added]** Docker `gdal-bin`, `libgdal-dev`, `libproj-dev`, `binutils` packages for production PostGIS support.
* **[Updated]** `.env.example` — Neon direct-vs-pooled connection guidance and Windows GDAL env var docs.

### 🐛 Bug Fixes
* **[Fixed]** `StopEventResultSerializer.status` — changed from plain `CharField` to `SerializerMethodField` to read from `obj['stop']`, eliminating 500 error on every `POST /stops/{id}/pickup|dropoff|no-show`.

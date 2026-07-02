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

## 🛠 Next Phase Checklist (API Views & Controllers)
- [ ] Implement DRF JWT authentication views (SimpleJWT) for driver & parent login endpoints.
- [ ] Build `/api/children/` endpoints to register and list child profiles + weekly schedules.
- [ ] Build `/api/dashboard/` for parents to track timeline status updates (stops GPS check-in history).
- [ ] Build `/api/manifest/` for drivers to load active trip sequences and record one-shot GPS events.
- [ ] Wire up SMS (EgoSMS) and Web Push (FCM) dispatch events to stop status transitions.

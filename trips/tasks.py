from __future__ import annotations

import math
from datetime import date, timedelta

from celery import shared_task
from django.db import transaction
from django.db.models import Max

from accounts.models import Driver, Notification
from children.models import Child
from main.firebase_push import notify
from trips.models import Assignment, Trip, Stop


# ---------------------------------------------------------------------------
# Geographic ordering
# ---------------------------------------------------------------------------
def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in metres. Points are (lng, lat)."""
    r = 6_371_000.0
    (lon1, lat1), (lon2, lat2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _nearest_neighbour(children: list[Child]) -> list[Child]:
    """
    Greedy nearest-neighbour ordering over pickup points.
    Deterministic: the anchor is the southern-then-western-most pickup.
    """
    remaining = list(children)
    if len(remaining) <= 2:
        return remaining

    remaining.sort(key=lambda c: (c.pickup_point.y, c.pickup_point.x))
    ordered = [remaining.pop(0)]
    while remaining:
        last = ordered[-1].pickup_point
        nxt = min(
            remaining,
            key=lambda c: _haversine_m(
                (last.x, last.y), (c.pickup_point.x, c.pickup_point.y)
            ),
        )
        ordered.append(nxt)
        remaining.remove(nxt)
    return ordered


# ---------------------------------------------------------------------------
# Trip building
# ---------------------------------------------------------------------------
@transaction.atomic
def _build_trip(driver: Driver, service_date: date, direction: str,
                children: list[Child]) -> bool:
    """
    Create one trip + its stops. Returns True if a new trip was created.
    """
    trip, created = Trip.objects.get_or_create(
        driver=driver,
        service_date=service_date,
        direction=direction,
        defaults={"status": Trip.Status.SCHEDULED},
    )
    if trip.stops.exists():
        return False

    ordered = _nearest_neighbour(children)
    if direction == Trip.Direction.TO_HOME:
        # Drop-offs run in reverse of the morning pickup order.
        ordered = list(reversed(ordered))

    stops = []
    for seq, child in enumerate(ordered, start=1):
        sched = getattr(child, "schedule", None)
        eta = None
        if sched:
            eta = (
                sched.morning_time
                if direction == Trip.Direction.TO_SCHOOL
                else sched.afternoon_time
            )
        stops.append(
            Stop(
                trip=trip,
                child=child,
                sequence=seq,
                status=Stop.Status.UPCOMING,
                eta=eta,
            )
        )
    Stop.objects.bulk_create(stops)
    return created


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
@shared_task
def generate_daily_manifests(service_date: str | None = None) -> dict:
    """
    Build trips for every active driver for `service_date` (default: tomorrow).
    """
    if service_date is None:
        target = date.today() + timedelta(days=1)
    else:
        target = date.fromisoformat(service_date)

    iso_weekday = target.isoweekday()  # 1=Mon .. 7=Sun
    trips_created = 0

    active_drivers = (
        Driver.objects.filter(is_verified=True, assignments__is_active=True)
        .distinct()
    )

    for driver in active_drivers:
        parent_ids = Assignment.objects.filter(
            driver=driver, is_active=True
        ).values_list("parent_id", flat=True)

        from django.db import connection
        if connection.vendor == 'sqlite':
            # SQLite fallback: filter in-memory since __contains JSON lookup is not supported natively in SQLite
            children_qs = Child.objects.filter(
                parent_id__in=parent_ids,
                is_active=True,
            ).select_related("schedule", "school")
            children = [
                c for c in children_qs 
                if hasattr(c, "schedule") and c.schedule is not None and iso_weekday in (c.schedule.days or [])
            ]
        else:
            # Postgres: use DB-level __contains lookup
            children = list(
                Child.objects.filter(
                    parent_id__in=parent_ids,
                    is_active=True,
                    schedule__days__contains=[iso_weekday],
                ).select_related("schedule", "school")
            )
            
        if not children:
            continue

        for direction in (Trip.Direction.TO_SCHOOL, Trip.Direction.TO_HOME):
            if _build_trip(driver, target, direction, children):
                trips_created += 1

    return {"service_date": target.isoformat(), "trips_created": trips_created}


# ---------------------------------------------------------------------------
# Reactive sync (on schedule save)
# ---------------------------------------------------------------------------
def _ensure_trip(driver: Driver, service_date: date, direction: str) -> Trip:
    trip, _ = Trip.objects.get_or_create(
        driver=driver, service_date=service_date, direction=direction,
        defaults={"status": Trip.Status.SCHEDULED},
    )
    return trip


def _append_stop_if_missing(trip: Trip, child: Child, direction: str) -> bool:
    """Adds a Stop for `child` on `trip` if it doesn't already have one,
    appended after the current last stop rather than re-running the
    nearest-neighbour ordering — safe to call on a trip that's already in
    progress, at the cost of not re-optimizing the route."""
    if Stop.objects.filter(trip=trip, child=child).exists():
        return False
    sched = getattr(child, "schedule", None)
    eta = None
    if sched:
        eta = sched.morning_time if direction == Trip.Direction.TO_SCHOOL else sched.afternoon_time
    next_seq = (trip.stops.aggregate(Max("sequence"))["sequence__max"] or 0) + 1
    Stop.objects.create(trip=trip, child=child, sequence=next_seq, status=Stop.Status.UPCOMING, eta=eta)
    return True


@transaction.atomic
def sync_trip_for_schedule(child: Child) -> None:
    """
    Reactive counterpart to generate_daily_manifests: called right after a
    parent saves a child's schedule, so the driver's manifest reflects it
    immediately instead of waiting on the nightly batch job — which nothing
    currently schedules to run anyway. Only builds/updates TODAY's trip;
    future days still rely on generate_daily_manifests once that's wired
    into an actual nightly job.
    """
    assignment = (
        Assignment.objects.filter(parent_id=child.parent_id, is_active=True)
        .select_related("driver__user")
        .first()
    )
    if not assignment or not assignment.driver.is_verified:
        return
    driver = assignment.driver

    sched = getattr(child, "schedule", None)
    if not sched:
        return
    today = date.today()
    if today.isoweekday() not in (sched.days or []):
        return

    added = False
    for direction in (Trip.Direction.TO_SCHOOL, Trip.Direction.TO_HOME):
        trip = _ensure_trip(driver, today, direction)
        if _append_stop_if_missing(trip, child, direction):
            added = True
            # The trip may have already finished its other stops and been
            # marked COMPLETED before this one was added — it has a pending
            # stop again now, so it isn't really done. Without this it stays
            # COMPLETED and never shows up as active on the admin dispatch
            # map once the driver acts on the new stop.
            if trip.status == Trip.Status.COMPLETED:
                trip.status = Trip.Status.IN_PROGRESS
                trip.save(update_fields=["status"])

    if added:
        notify(
            driver.user,
            Notification.Kind.SYSTEM,
            "New pickup added to today's route",
            f"{child.full_name} was scheduled and added to your route today.",
        )

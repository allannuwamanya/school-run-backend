import uuid
from django.db import models
from django.conf import settings
from django.db.models import Q
from main.gis_fallback import PointField
from accounts.models import Base, Driver, Parent
from children.models import Child

# ---------------------------------------------------------------------------
# Assignment (the admin's primary setup job)
# ---------------------------------------------------------------------------
class Assignment(Base):
    driver = models.ForeignKey(
        Driver, on_delete=models.PROTECT, related_name="assignments"
    )
    parent = models.ForeignKey(
        Parent, on_delete=models.CASCADE, related_name="assignments"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["parent"],
                condition=Q(is_active=True),
                name="one_active_driver_per_parent",
            )
        ]
        indexes = [models.Index(fields=["driver", "is_active"])]

    def __str__(self):
        return f"{self.parent} -> {self.driver}"


# ---------------------------------------------------------------------------
# Trips & stops (generated per driver, per day, per direction)
# ---------------------------------------------------------------------------
class Trip(Base):
    class Direction(models.TextChoices):
        TO_SCHOOL = "TO_SCHOOL", "Home to school"
        TO_HOME = "TO_HOME", "School to home"

    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    driver = models.ForeignKey(
        Driver, on_delete=models.PROTECT, related_name="trips"
    )
    service_date = models.DateField()
    direction = models.CharField(max_length=9, choices=Direction.choices)
    status = models.CharField(
        max_length=11, choices=Status.choices, default=Status.SCHEDULED
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["driver", "service_date", "direction"],
                name="one_trip_per_driver_date_direction",
            )
        ]
        indexes = [
            models.Index(fields=["service_date", "status"]),
            models.Index(fields=["driver", "service_date"]),
        ]

    def __str__(self):
        return f"{self.driver} · {self.service_date} · {self.get_direction_display()}"


class Stop(Base):
    class Status(models.TextChoices):
        UPCOMING = "UPCOMING", "Upcoming"
        NEXT = "NEXT", "Next stop"
        PICKED_UP = "PICKED_UP", "Picked up"
        DROPPED = "DROPPED", "Dropped off"
        NO_SHOW = "NO_SHOW", "No show"

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="stops")
    child = models.ForeignKey(Child, on_delete=models.PROTECT, related_name="stops")
    sequence = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=9, choices=Status.choices, default=Status.UPCOMING
    )
    eta = models.TimeField(null=True, blank=True)

    # Event-stamped GPS: captured one-shot from the browser on the driver's tap.
    picked_point = PointField(geography=True, null=True, blank=True)
    picked_at = models.DateTimeField(null=True, blank=True)
    dropped_point = PointField(geography=True, null=True, blank=True)
    dropped_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["trip", "child"], name="child_once_per_trip"
            ),
            models.UniqueConstraint(
                fields=["trip", "sequence"], name="unique_sequence_per_trip"
            ),
        ]

    def __str__(self):
        return f"#{self.sequence} {self.child.full_name} ({self.get_status_display()})"


class LocationPing(Base):
    """Historical GPS fixes from a driver's nav screen (see
    DriverLocationPingView) — powers the admin dispatch map's breadcrumb
    trail. Distinct from Driver.last_point, which only holds the latest fix
    and gets overwritten on every ping."""
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name="location_pings")
    point = PointField(geography=True)

    class Meta:
        indexes = [models.Index(fields=["driver", "created_at"])]

    def __str__(self):
        return f"{self.driver.user.full_name} @ {self.created_at:%H:%M:%S}"


class LiveLocation(models.Model):
    """Last known GPS position of a driver (optional extension)."""
    driver = models.OneToOneField(
        Driver, on_delete=models.CASCADE, related_name='live_location'
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.driver.user.full_name} @ ({self.latitude}, {self.longitude})"

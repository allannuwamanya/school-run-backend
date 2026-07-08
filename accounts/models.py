import uuid
from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager, AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import PermissionDenied
from django.db import models
from rest_framework_simplejwt.tokens import RefreshToken

from main.gis_fallback import PointField

# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------
class Base(models.Model):
    """UUID pk + timestamps for every domain model."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

BaseModel = Base


# ---------------------------------------------------------------------------
# Auth: phone-first custom user
# ---------------------------------------------------------------------------
class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, phone, password=None, **extra):
        if not phone:
            raise ValueError("A phone number is required.")
        user = self.model(phone=phone, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", CustomUser.Role.ADMIN)
        if extra.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(phone, password, **extra)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """
    Login is by phone, not username/email.
    Parents self-register (role=PARENT). Admin creates drivers (role=DRIVER).
    Ops staff are role=ADMIN and use Django admin (is_staff=True).
    """
    class Role(models.TextChoices):
        PARENT = "PARENT", "Parent"
        DRIVER = "DRIVER", "Driver"
        ADMIN = "ADMIN", "Admin"

    class Gender(models.TextChoices):
        FEMALE = "F", "Female"
        MALE = "M", "Male"

    username = None
    first_name = None
    last_name = None

    # Nullable to allow Google-only accounts (no phone collected at sign-in);
    # a unique column permits multiple NULLs on both Postgres and SQLite.
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    email = models.EmailField(max_length=200, null=True, blank=True)
    full_name = models.CharField(max_length=120, blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.PARENT)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True)

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # preferences & verification from contract
    nin_verified = models.BooleanField(default=False)
    nin_number = models.CharField(max_length=20, blank=True)
    push_notifications_enabled = models.BooleanField(default=True)
    location_sharing_enabled = models.BooleanField(default=True)
    dark_mode = models.BooleanField(default=False)

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    objects = UserManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name_plural = "users"

    def __str__(self):
        return self.full_name or self.phone

    def tokens(self):
        refresh = RefreshToken.for_user(self)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token)
        }


# ---------------------------------------------------------------------------
# Parents & Drivers profiles inside accounts to match schema structure
# ---------------------------------------------------------------------------
class Parent(Base):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="parent"
    )
    emergency_contact = models.CharField(max_length=20, blank=True)
    is_verified = models.BooleanField(default=False)
    zone = models.ForeignKey(
        "zones.Zone", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="parent_profiles",
    )

    def __str__(self):
        return self.user.full_name or self.user.phone


class Driver(Base):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="driver"
    )
    vehicle_make = models.CharField(max_length=60, blank=True)
    vehicle_model = models.CharField(max_length=60, blank=True)
    plate = models.CharField(max_length=20, unique=True)
    color = models.CharField(max_length=30, blank=True)
    seats = models.PositiveSmallIntegerField(default=14)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    is_verified = models.BooleanField(default=False)
    driver_since = models.DateField(null=True, blank=True)
    zone = models.ForeignKey(
        "zones.Zone", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="driver_profiles",
    )

    # Foreground-only live tracking: pinged periodically by the nav screen
    # while a trip is in progress (see api/views.py DriverLocationPingView).
    # No screen open, no pings — the admin dispatch map falls back to the
    # target stop's fixed coordinate once this goes stale.
    last_point = PointField(geography=True, null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.full_name or self.user.phone} ({self.plate})"


class VerificationDocument(Base):
    class DocType(models.TextChoices):
        LICENSE = "LICENSE", "Driver's licence"
        INSPECTION = "INSPECTION", "Vehicle inspection report"
        BACKGROUND = "BACKGROUND", "Criminal background check"
        INSURANCE = "INSURANCE", "Vehicle insurance"
        NIN_FRONT = "NIN_FRONT", "National ID (front)"
        NIN_BACK = "NIN_BACK", "National ID (back)"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VERIFIED = "VERIFIED", "Verified"
        CLEAR = "CLEAR", "Clear"
        REJECTED = "REJECTED", "Rejected"

    driver = models.ForeignKey(
        Driver, on_delete=models.CASCADE, related_name="documents"
    )
    doc_type = models.CharField(max_length=12, choices=DocType.choices)
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.PENDING
    )
    file = models.FileField(upload_to="driver_docs/", null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["driver", "doc_type"], name="one_doc_per_type_per_driver"
            )
        ]

    def __str__(self):
        return f"{self.get_doc_type_display()} — {self.driver}"


class UndeletableQuerySet(models.QuerySet):
    def delete(self):
        raise PermissionDenied("Account deletion logs cannot be deleted.")


class AccountDeletionLog(models.Model):
    """Permanent record of an admin deleting a parent/driver login. A
    snapshot, not a live FK to the deleted account — that account (and,
    since the delete cascades, its children/trips) won't exist to look up
    afterward. `delete()` is blocked at both the instance and queryset
    level so this stays a real audit trail rather than something that can
    be quietly cleaned up alongside the account it describes."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    deleted_at = models.DateTimeField(auto_now_add=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="account_deletions_performed",
    )
    deleted_by_name = models.CharField(max_length=120, blank=True)
    target_user_id = models.BigIntegerField()
    target_role = models.CharField(max_length=10)
    target_full_name = models.CharField(max_length=120, blank=True)
    target_phone = models.CharField(max_length=20, blank=True)
    children_deleted = models.PositiveIntegerField(default=0)
    trips_deleted = models.PositiveIntegerField(default=0)

    objects = UndeletableQuerySet.as_manager()

    class Meta:
        ordering = ["-deleted_at"]

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Account deletion logs cannot be deleted.")

    def __str__(self):
        return f"{self.target_full_name or self.target_phone} deleted by {self.deleted_by_name or 'unknown'} at {self.deleted_at}"


class ErrorLog(models.Model):
    level = models.CharField(max_length=50)
    message = models.TextField()
    details = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.level}] {self.timestamp}: {self.message[:50]}"


class Notification(Base):
    class Kind(models.TextChoices):
        PICKUP = "PICKUP", "Picked up"
        ARRIVAL = "ARRIVAL", "Arrived at school"
        DROPOFF = "DROPOFF", "Dropped at home"
        DRIVER_NEARBY = "DRIVER_NEARBY", "Driver nearby"
        SYSTEM = "SYSTEM", "System"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(max_length=13, choices=Kind.choices)
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read"])]

    def __str__(self):
        return f"{self.title} -> {self.recipient}"


class Device(Base):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="devices",
    )
    fcm_token = models.CharField(max_length=500)
    platform = models.CharField(max_length=20, default="web")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "fcm_token"], name="unique_user_device"
            )
        ]

    def __str__(self):
        return f"{self.user.phone} — {self.platform}"

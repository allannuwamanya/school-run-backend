import uuid
from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager, AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
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

    username = None
    first_name = None
    last_name = None

    # Nullable to allow Google-only accounts (no phone collected at sign-in);
    # a unique column permits multiple NULLs on both Postgres and SQLite.
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    email = models.EmailField(max_length=200, null=True, blank=True)
    full_name = models.CharField(max_length=120, blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.PARENT)
    
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # preferences & verification from contract
    nin_verified = models.BooleanField(default=False)
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

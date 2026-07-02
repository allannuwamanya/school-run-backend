from django.db import models
from django.conf import settings
from main.gis_fallback import PointField, ArrayField
from accounts.models import Base, Parent

# ---------------------------------------------------------------------------
# Reference data: School
# ---------------------------------------------------------------------------
class School(Base):
    """Drop-off destination only — no login, no dashboard."""
    name = models.CharField(max_length=160)
    address = models.CharField(max_length=255, blank=True)
    location = PointField(geography=True)

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Children
# ---------------------------------------------------------------------------
class Child(Base):
    class Gender(models.TextChoices):
        FEMALE = "F", "Female"
        MALE = "M", "Male"
        OTHER = "O", "Other"

    parent = models.ForeignKey(
        Parent, on_delete=models.CASCADE, related_name="children"
    )
    school = models.ForeignKey(
        School, on_delete=models.PROTECT, related_name="children"
    )

    full_name = models.CharField(max_length=120)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True)
    blood_type = models.CharField(max_length=3, blank=True)      # e.g. "O+"
    class_name = models.CharField(max_length=40, blank=True)     # e.g. "Grade 3"
    allergies = models.CharField(max_length=255, blank=True)     # e.g. "Peanut allergy"
    photo = models.ImageField(upload_to="children/", null=True, blank=True)

    pickup_address = models.CharField(max_length=255)
    pickup_point = PointField(geography=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["parent", "is_active"])]

    def __str__(self):
        return self.full_name


class Schedule(Base):
    """
    One schedule per child.
    days: ISO weekday numbers, 1=Mon .. 7=Sun.
    """
    child = models.OneToOneField(
        Child, on_delete=models.CASCADE, related_name="schedule"
    )
    morning_time = models.TimeField()
    afternoon_time = models.TimeField()
    days = ArrayField(models.PositiveSmallIntegerField(), default=list)

    def __str__(self):
        return f"Schedule for {self.child.full_name}"

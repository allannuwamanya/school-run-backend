from django.db import models
from accounts.models import BaseModel


class Zone(BaseModel):
    """
    Geographic service area (e.g. Lekki, Ajah, Victoria Island).
    Drivers and parent pick-up locations are assigned to a zone.
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def active_route_count(self):
        return self.routes.filter(is_active=True).count()

    @property
    def driver_count(self):
        return self.driver_profiles.filter(active=True).count()

    @property
    def family_count(self):
        return self.parent_profiles.filter(active=True).count()

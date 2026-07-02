import os
import sys
from django.db import models

# Detect if GDAL is available
try:
    from django.contrib.gis.gdal import GDAL_VERSION
    from django.contrib.gis.db import models as gis
    from django.contrib.gis.geos import Point
    HAS_GDAL = True
except Exception:
    HAS_GDAL = False

# Detect if we should use Postgres contrib fields (e.g. if DB_CHOICE is postgres)
DB_CHOICE = os.environ.get("DB_CHOICE", default="sqlite")

if DB_CHOICE == "postgres":
    try:
        from django.contrib.postgres.fields import ArrayField as DjangoArrayField
        HAS_POSTGRES_FIELDS = True
    except Exception:
        HAS_POSTGRES_FIELDS = False
else:
    HAS_POSTGRES_FIELDS = False

# 1. Point Field Configuration
if HAS_GDAL:
    PointField = gis.PointField
    GeoPoint = Point
else:
    class GeoPoint:
        def __init__(self, x=0.0, y=0.0, srid=4326):
            self.x = float(x)
            self.y = float(y)
            self.srid = srid

        @property
        def coords(self):
            return (self.x, self.y)

        def __str__(self):
            return f"POINT ({self.x} {self.y})"

        def __repr__(self):
            return f"<MockPoint: POINT({self.x} {self.y})>"

    class PointField(models.Field):
        description = "Mock Point Field for environments without GDAL"

        def __init__(self, *args, geography=False, srid=4326, **kwargs):
            self.geography = geography
            self.srid = srid
            super().__init__(*args, **kwargs)

        def db_type(self, connection):
            return 'varchar(128)'

        def from_db_value(self, value, expression, connection):
            if value is None:
                return value
            if isinstance(value, GeoPoint):
                return value
            try:
                val_str = str(value)
                if ";" in val_str:
                    val_str = val_str.split(";")[1]
                val_str = val_str.replace("POINT", "").replace("(", "").replace(")", "").strip()
                parts = val_str.split()
                if len(parts) == 2:
                    return GeoPoint(float(parts[0]), float(parts[1]))
            except Exception:
                pass
            return GeoPoint(0.0, 0.0)

        def to_python(self, value):
            if isinstance(value, GeoPoint):
                return value
            if value is None:
                return value
            return self.from_db_value(value, None, None)

        def get_prep_value(self, value):
            if value is None:
                return None
            if isinstance(value, GeoPoint):
                return f"POINT ({value.x} {value.y})"
            if isinstance(value, (list, tuple)) and len(value) == 2:
                return f"POINT ({value[0]} {value[1]})"
            return str(value)

# 2. Array Field Configuration
if HAS_POSTGRES_FIELDS:
    ArrayField = DjangoArrayField
else:
    class ArrayField(models.JSONField):
        description = "Fallback ArrayField mapped to JSONField for non-Postgres environments"

        def __init__(self, base_field=None, size=None, **kwargs):
            # base_field is ignored in JSONField
            super().__init__(**kwargs)

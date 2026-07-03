# === Stage 1: Builder ===
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=UTC

WORKDIR /app

# Install required system packages and clean up in one layer
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-cache-dir -r requirements.txt

# === Stage 2: Final ===
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=UTC

WORKDIR /app

# Install system dependencies and clean up in one layer
# gdal-bin/libgdal-dev/libproj-dev/binutils: GeoDjango needs the GDAL/GEOS/PROJ
# shared libraries at runtime (ctypes, not a compiled Python extension) to
# enable django.contrib.gis + native PostGIS geography columns — see
# main/gis_fallback.py's HAS_GDAL detection. Matches this README's own
# documented production instructions, which previously weren't wired into
# this Dockerfile.
RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd libgl1 libglib2.0-0 \
    binutils libproj-dev gdal-bin libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages and NLTK data from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy application source
COPY . .

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "main.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
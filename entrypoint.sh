#!/bin/bash
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ -n "$ADMIN_EMAIL" ] && [ -n "$ADMIN_PASSWORD" ]; then
  python manage.py shell -c "
from django.contrib.auth import get_user_model;
User = get_user_model();
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser('$ADMIN_EMAIL', '$ADMIN_EMAIL', '$ADMIN_PASSWORD')
    print('Admin user created')
else:
    print('Admin user already exists')
"
fi

exec uvicorn main.asgi:application --host 0.0.0.0 --port ${PORT:-8000}

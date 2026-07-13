#!/bin/bash
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Login is by phone (USERNAME_FIELD = phone), so the bootstrap admin needs a
# phone, not an email. Email is optional and just stored on the record.
if [ -n "$ADMIN_PHONE" ] && [ -n "$ADMIN_PASSWORD" ]; then
  python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser(phone='$ADMIN_PHONE', password='$ADMIN_PASSWORD', email='$ADMIN_EMAIL', full_name='Admin')
    print('Admin user created')
else:
    print('Admin user already exists')
"
fi

exec uvicorn main.asgi:application --host 0.0.0.0 --port ${PORT:-8000}

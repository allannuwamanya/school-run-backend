"""
Django settings for SchoolRun backend.
"""

import os
import datetime
import dj_database_url
from pathlib import Path
# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = Path(__file__).resolve().parent.parent

# GDAL/GEOS library paths (Windows local dev). Must be set before
# `main.gis_fallback` (or anything importing django.contrib.gis) runs, since
# that's when Django's ctypes loader reads these settings. Unset on
# Linux/production — Django falls back to standard .so auto-discovery there.
GDAL_LIBRARY_PATH = os.environ.get('GDAL_LIBRARY_PATH') or None
GEOS_LIBRARY_PATH = os.environ.get('GEOS_LIBRARY_PATH') or None
# GDAL_DATA / PROJ_LIB are read directly from os.environ by the GDAL/PROJ C
# libraries themselves (not via Django settings) — already populated by
# manage.py's load_dotenv() call before this module executes.

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY')

# In development, you can set this in your .env file
# For production, it MUST be set as an environment variable
if not SECRET_KEY:
    raise ValueError("No SECRET_KEY set for Django application")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = str(os.environ.get('DEBUG')) == "1"  # 1 == True

# The nginx reverse proxy terminates TLS and forwards plain HTTP to the app
# with this header set — without it, request.build_absolute_uri() (used for
# uploaded-document URLs) would report an http:// URL even in production.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# Application definition

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    # Third-party
    'drf_yasg',
    'corsheaders',
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',
    'import_export',
    # SchoolRun apps
    'accounts',
    'zones',
    'children',
    'drivers',
    'trips',
    'payments',
    'incidents',
    'api',
]

from main.gis_fallback import HAS_GDAL
if HAS_GDAL:
    INSTALLED_APPS.insert(0, 'django.contrib.gis')

AUTH_USER_MODEL = 'accounts.CustomUser'

SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Basic': {
            'type': 'basic'
        }
    }
}
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'accounts.middleware.ForcePasswordChangeMiddleware',
]

ROOT_URLCONF = 'main.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'main.wsgi.application'


# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.mysql',
#         'NAME': os.environ.get('DB_NAME'),
#         'USER': os.environ.get('DB_USER'),
#         'PASSWORD': os.environ.get('DB_PASSWORD'),
#         'HOST': os.environ.get('DB_HOST'),
#         'PORT': os.environ.get('DB_PORT')
#     }
# }
DB_CHOICE = os.environ.get("DB_CHOICE", default="sqlite")
if DB_CHOICE == "sqlite":
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

elif DB_CHOICE == "postgres":
    db_config = dj_database_url.config(
        default='postgresql://localhost/schoolrun',
        conn_max_age=600
    )
    if HAS_GDAL:
        db_config['ENGINE'] = 'django.contrib.gis.db.backends.postgis'
    else:
        db_config['ENGINE'] = 'django.db.backends.postgresql'
    
    DATABASES = {
        'default': db_config
    }

else:
    raise ValueError(f"Unsupported DB_CHOICE: {DB_CHOICE}")
REST_FRAMEWORK = {

    'EXCEPTION_HANDLER': 'accounts.utils.custom_exception_handler',
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
}


# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    # {
    #     'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    # },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    # {
    #     'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    # },
    # {
    #     'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    # },
]


# Internationalization
# https://docs.djangoproject.com/en/3.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Africa/Kampala'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.0/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'


# Get the value from the environment variable, defaulting to an empty string
allowed_hosts_str = os.environ.get('ALLOWED_HOSTS', '')

# Split the string into a list, only if the string is not empty
ALLOWED_HOSTS = allowed_hosts_str.split(',') if allowed_hosts_str else []

# Do the same for CORS and CSRF settings
allowed_origins_str = os.environ.get('CORS_ALLOWED_ORIGINS', '')
CORS_ALLOWED_ORIGINS = allowed_origins_str.split(
    ',') if allowed_origins_str else []

trusted_origins_str = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = trusted_origins_str.split(
    ',') if trusted_origins_str else []

# OAuth audience for verifying Google Identity Services ID tokens (see
# api/serializers.py GoogleLoginSerializer). Not a secret — safe to expose.
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
JAZZMIN_SETTINGS = {
    "site_title": os.environ.get('SITE_NAME', 'SchoolRun'),
    "site_brand": f"{os.environ.get('SITE_NAME', 'SchoolRun')} Admin",
    "show_ui_builder": True,
    "hide_apps": ['auth', 'authtoken'],
    "user_avatar": None,
    "icons": {
        "accounts.CustomUser": "fas fa-user",
        "children.Child": "fas fa-child",
        "drivers.DriverProfile": "fas fa-car",
        "trips.Trip": "fas fa-route",
        "payments.Transaction": "fas fa-money-bill",
        "incidents.Incident": "fas fa-exclamation-triangle",
        "zones.Zone": "fas fa-map-marked-alt",
    }
}


MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_URL = '/media/'

SITE_ID = 1

IMPORT_EXPORT_SKIP_ADMIN_LOG = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Testing email on the consoloe
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


# # email confirmation
# EMAIL_HOST = os.environ.get('EMAIL_HOST')
# EMAIL_USE_TLS = True
# EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
# EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
# EMAIL_PORT = os.environ.get('EMAIL_PORT')

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

MIGRATION_MODULES = {
    'accounts':  'migrations.accounts',
    'api':       'migrations.api',
    'zones':     'migrations.zones',
    'children':  'migrations.children',
    'drivers':   'migrations.drivers',
    'trips':     'migrations.trips',
    'payments':  'migrations.payments',
    'incidents': 'migrations.incidents',
}

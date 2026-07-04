import os
import json
from firebase_admin import credentials, initialize_app, messaging

_initialized = False

def _init():
    global _initialized
    if _initialized:
        return

    # Priority: 1) explicit path from env, 2) JSON string from env, 3) GOOGLE_APPLICATION_CREDENTIALS
    sa_path = os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH')
    sa_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
    if sa_path and os.path.exists(str(sa_path)):
        cred = credentials.Certificate(str(sa_path))
        initialize_app(cred)
        _initialized = True
    elif sa_json:
        cred = credentials.Certificate(json.loads(sa_json))
        initialize_app(cred)
        _initialized = True
    else:
        try:
            initialize_app()
            _initialized = True
        except Exception:
            pass  # no Firebase configured — push silently skipped

def _log_error(message: str, details: str = ''):
    from accounts.models import ErrorLog
    try:
        ErrorLog.objects.create(level='ERROR', message=message, details=details)
    except Exception:
        pass  # logging must never break the caller

def _frontend_link() -> str | None:
    # WebpushFCMOptions.link requires HTTPS; local dev origins are plain http
    # and would otherwise make every send fail, so fall back to no link there.
    from django.conf import settings
    origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', None) or []
    return next((o for o in origins if o.startswith('https://')), None)

def send_push(user, title: str, body: str, data: dict | None = None):
    from accounts.models import Device
    _init()
    if not _initialized:
        return
    tokens = list(Device.objects.filter(user=user).values_list('fcm_token', flat=True))
    if not tokens:
        return
    link = _frontend_link()
    message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
        webpush=messaging.WebpushConfig(
            fcm_options=messaging.WebpushFCMOptions(link=link),
        ) if link else None,
    )
    try:
        response = messaging.send_each_for_multicast(message)
    except Exception as exc:
        _log_error(f'FCM send failed for user {user.pk}', str(exc))
        return

    dead_tokens = [
        token
        for token, result in zip(tokens, response.responses)
        if not result.success and isinstance(result.exception, messaging.UnregisteredError)
    ]
    if dead_tokens:
        Device.objects.filter(user=user, fcm_token__in=dead_tokens).delete()

    if response.failure_count and len(dead_tokens) < response.failure_count:
        failures = '; '.join(
            str(result.exception) for result in response.responses if not result.success
        )
        _log_error(f'FCM send partially failed for user {user.pk}', failures)


def notify(recipient, kind: str, title: str, body: str, data: dict | None = None):
    """Create an in-app Notification row and push it to the recipient's devices."""
    from accounts.models import Notification
    notif = Notification.objects.create(
        recipient=recipient, kind=kind, title=title, body=body,
    )
    try:
        send_push(recipient, title, body, data)
    except Exception as exc:
        _log_error(f'send_push raised for user {recipient.pk}', str(exc))
    return notif


def notify_admins(kind: str, title: str, body: str, data: dict | None = None):
    """notify() every admin — powers the admin Overview's Live Activity feed
    pushing new events straight to the browser instead of being polled."""
    from accounts.models import CustomUser
    for admin in CustomUser.objects.filter(role=CustomUser.Role.ADMIN):
        notify(admin, kind, title, body, data)

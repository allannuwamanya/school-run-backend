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

def send_push(user, title: str, body: str, data: dict | None = None):
    from accounts.models import Device
    _init()
    if not _initialized:
        return
    tokens = list(Device.objects.filter(user=user).values_list('token', flat=True))
    if not tokens:
        return
    message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
    )
    messaging.send_each_for_multicast(message)

from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

# Paths a must_change_password user can still reach — enough to see their own
# account, set a new password, and stay logged in/out while doing it.
ALLOWED_PATHS = {
    "/api/me",
    "/api/me/change-password",
    "/api/auth/refresh",
}


class ForcePasswordChangeMiddleware:
    """Blocks API access beyond a small allowlist for any user flagged
    must_change_password=True — set when an admin creates or resets an
    account with a temporary password (AdminStaffListView,
    AdminDriverListView, AdminUserSetPasswordView). Runs its own JWT check
    since Django's session-based AuthenticationMiddleware never sees the
    JWT-authenticated user DRF resolves later, inside the view."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/") and request.path not in ALLOWED_PATHS:
            try:
                result = JWTAuthentication().authenticate(request)
            except (InvalidToken, TokenError):
                result = None
            if result is not None:
                user, _ = result
                if getattr(user, "must_change_password", False):
                    return JsonResponse(
                        {
                            "error": True,
                            "errors": ["You must change your password before continuing."],
                            "status_code": 423,
                            "detail": "You must change your password before continuing.",
                            "code": "PASSWORD_CHANGE_REQUIRED",
                        },
                        status=423,
                    )
        return self.get_response(request)

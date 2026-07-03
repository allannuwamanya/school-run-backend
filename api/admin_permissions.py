from rest_framework.permissions import BasePermission

from accounts.models import CustomUser


class IsAdmin(BasePermission):
    """Restricts a view to authenticated users with role=ADMIN."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == CustomUser.Role.ADMIN
        )

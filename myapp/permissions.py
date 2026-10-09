from rest_framework.permissions import BasePermission


class IsSuperAdmin(BasePermission):
    """Allow dashboard administration only to users with the exact role."""

    message = "Super Admin access required"

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.role == "Super Admin"
        )

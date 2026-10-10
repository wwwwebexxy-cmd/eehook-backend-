"""DRF authentication for HttpOnly JWT cookies with CSRF protection."""

from django.conf import settings
from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication


SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def enforce_csrf(request):
    """Apply Django's CSRF validation for a cookie-authenticated request."""
    check = CSRFCheck(lambda _request: None)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise PermissionDenied(f"CSRF Failed: {reason}")


class CookieJWTAuthentication(JWTAuthentication):
    """Authenticate browser requests from the access cookie.

    Authorization: Bearer remains accepted temporarily so mobile and older
    storefront clients keep working during the cookie migration.  CSRF is only
    required when credentials arrive automatically in a cookie.
    """

    def authenticate(self, request):
        # Browser sessions use the HttpOnly access cookie. Prefer it whenever
        # it is present so a stale bearer token left by an older tab/client
        # cannot downgrade an otherwise valid Super Admin cookie session.
        # Explicit bearer authentication remains available for non-browser
        # clients that do not send the browser cookie.
        raw_token = request.COOKIES.get(settings.JWT_ACCESS_COOKIE_NAME)
        if raw_token:
            if request.method.upper() not in SAFE_METHODS:
                enforce_csrf(request)
            validated_token = self.get_validated_token(raw_token)
            return self.get_user(validated_token), validated_token

        if self.get_header(request) is not None:
            return super().authenticate(request)

        return None

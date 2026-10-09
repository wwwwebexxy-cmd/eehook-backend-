"""Cookie helpers used by the browser authentication endpoints.

JWTs are deliberately kept out of JSON responses.  A browser receives them
only as HttpOnly cookies, while DRF reads the short-lived access cookie.
"""

from django.conf import settings


def _cookie_options(max_age):
    options = {
        "max_age": max_age,
        "httponly": True,
        "secure": settings.JWT_COOKIE_SECURE,
        "samesite": settings.JWT_COOKIE_SAMESITE,
        "path": "/",
    }
    if settings.JWT_COOKIE_DOMAIN:
        options["domain"] = settings.JWT_COOKIE_DOMAIN
    return options


def set_auth_cookies(response, *, access_token, refresh_token):
    """Attach short-lived access and rotating refresh cookies to *response*."""
    access_lifetime = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
    refresh_lifetime = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
    response.set_cookie(
        settings.JWT_ACCESS_COOKIE_NAME,
        access_token,
        **_cookie_options(int(access_lifetime.total_seconds())),
    )
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        refresh_token,
        **_cookie_options(int(refresh_lifetime.total_seconds())),
    )
    return response


def clear_auth_cookies(response):
    """Expire both browser authentication cookies on every logout response."""
    options = {
        "path": "/",
        "samesite": settings.JWT_COOKIE_SAMESITE,
    }
    if settings.JWT_COOKIE_DOMAIN:
        options["domain"] = settings.JWT_COOKIE_DOMAIN
    response.delete_cookie(
        settings.JWT_ACCESS_COOKIE_NAME,
        **options,
    )
    response.delete_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        **options,
    )
    return response


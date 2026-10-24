"""Cookie helpers used by the browser authentication endpoints.

JWTs are deliberately kept out of JSON responses.  A browser receives them
only as HttpOnly cookies, while DRF reads the short-lived access cookie.
"""

from django.conf import settings


def normalize_auth_scope(scope):
    return "admin" if str(scope or "").strip().lower() in {"admin", "super_admin", "superadmin"} else "customer"


def auth_cookie_names(scope="customer"):
    if normalize_auth_scope(scope) == "admin":
        return settings.JWT_ADMIN_ACCESS_COOKIE_NAME, settings.JWT_ADMIN_REFRESH_COOKIE_NAME
    return settings.JWT_ACCESS_COOKIE_NAME, settings.JWT_REFRESH_COOKIE_NAME


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


def set_auth_cookies(response, *, access_token, refresh_token, scope="customer"):
    """Attach short-lived access and rotating refresh cookies to *response*."""
    access_lifetime = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
    refresh_lifetime = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
    access_cookie, refresh_cookie = auth_cookie_names(scope)
    response.set_cookie(
        access_cookie,
        access_token,
        **_cookie_options(int(access_lifetime.total_seconds())),
    )
    response.set_cookie(
        refresh_cookie,
        refresh_token,
        **_cookie_options(int(refresh_lifetime.total_seconds())),
    )
    return response


def clear_auth_cookies(response, scope=None):
    """Expire the requested auth scope, or both scopes for legacy clients."""
    options = {
        "path": "/",
        "samesite": settings.JWT_COOKIE_SAMESITE,
    }
    if settings.JWT_COOKIE_DOMAIN:
        options["domain"] = settings.JWT_COOKIE_DOMAIN
    scopes = ("customer", "admin") if scope is None else (normalize_auth_scope(scope),)
    cookie_names = {name for current_scope in scopes for name in auth_cookie_names(current_scope)}
    for cookie_name in cookie_names:
        response.delete_cookie(cookie_name, **options)
    return response


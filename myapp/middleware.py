"""Small, cache-backed abuse controls for non-DRF Django endpoints.

DRF throttles protect API views, but Django's session-based admin login does
not pass through DRF. These controls therefore live at the middleware layer.
Use a shared cache (Redis or Memcached) in multi-process production
deployments; the local-memory backend is suitable only for development.
"""

import hashlib

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse


class AbuseProtectionMiddleware:
    """Limit request floods and slow down repeated admin login failures."""

    EXEMPT_PREFIXES = ("/static/", "/media/", "/health/")
    EXEMPT_PATHS = ("/payment/stripe-webhook/",)

    @staticmethod
    def _client_ip(request):
        # Do not trust X-Forwarded-For unless a trusted proxy has normalized it.
        return request.META.get("REMOTE_ADDR") or "unknown"

    @staticmethod
    def _key(prefix, value):
        digest = hashlib.sha256(value.encode("utf-8", "ignore")).hexdigest()
        return f"abuse:{prefix}:{digest}"

    @staticmethod
    def _increment(key, timeout):
        if cache.add(key, 1, timeout=timeout):
            return 1
        try:
            return cache.incr(key)
        except ValueError:
            # A concurrent expiry can remove the key between add/incr.
            cache.set(key, 1, timeout=timeout)
            return 1

    @staticmethod
    def _limited_response(retry_after):
        response = JsonResponse(
            {"detail": "Too many requests. Please try again later."},
            status=429,
        )
        response["Retry-After"] = str(max(1, int(retry_after)))
        return response

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        ip = self._client_ip(request)
        is_admin_login = path.rstrip("/") == "/admin/login" and request.method == "POST"

        if is_admin_login:
            username = request.POST.get("username", "").strip().lower()[:254]
            login_key = self._key("admin-login", f"{ip}:{username}")
            login_window = int(getattr(settings, "ADMIN_LOGIN_WINDOW", 900))
            max_attempts = int(getattr(settings, "ADMIN_LOGIN_MAX_ATTEMPTS", 5))
            if cache.get(login_key, 0) >= max_attempts:
                return self._limited_response(login_window)

        exempt = path.startswith(self.EXEMPT_PREFIXES) or path in self.EXEMPT_PATHS
        request_key = self._key("requests", ip)
        window = int(getattr(settings, "GLOBAL_RATE_WINDOW", 60))
        limit = int(getattr(settings, "GLOBAL_RATE_LIMIT", 300))
        if not exempt and self._increment(request_key, window) > limit:
            return self._limited_response(window)

        response = self.get_response(request)

        if is_admin_login:
            # Django redirects after successful authentication. Failed form
            # submissions render the login page with HTTP 200.
            if response.status_code in (301, 302, 303, 307, 308):
                cache.delete(login_key)
            elif response.status_code == 200:
                attempts = self._increment(login_key, login_window)
                if attempts > max_attempts:
                    return self._limited_response(login_window)

        return response

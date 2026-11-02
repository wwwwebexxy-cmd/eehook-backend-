from django.test import SimpleTestCase, override_settings
from django.test.client import RequestFactory

from .middleware import AbuseProtectionMiddleware


class ClientIpResolutionTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(TRUSTED_PROXY_IPS=("127.0.0.1", "::1"))
    def test_uses_x_real_ip_when_request_came_from_trusted_proxy(self):
        request = self.factory.get(
            "/products/",
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_REAL_IP="203.0.113.10",
        )

        self.assertEqual(
            AbuseProtectionMiddleware._client_ip(request),
            "203.0.113.10",
        )

    @override_settings(TRUSTED_PROXY_IPS=("127.0.0.1", "::1"))
    def test_does_not_trust_x_real_ip_from_untrusted_peer(self):
        request = self.factory.get(
            "/products/",
            REMOTE_ADDR="203.0.113.20",
            HTTP_X_REAL_IP="203.0.113.21",
        )

        self.assertEqual(
            AbuseProtectionMiddleware._client_ip(request),
            "203.0.113.20",
        )

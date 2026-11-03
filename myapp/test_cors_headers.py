from django.conf import settings
from django.test import SimpleTestCase


class CorsHeaderConfigurationTests(SimpleTestCase):
    def test_order_idempotency_header_is_allowed(self):
        self.assertIn("idempotency-key", settings.CORS_ALLOW_HEADERS)

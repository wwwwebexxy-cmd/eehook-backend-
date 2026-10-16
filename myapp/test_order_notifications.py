from django.core import mail
from django.test import TestCase, override_settings

from .models import Order, User
from .order_notifications import send_owner_order_email


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="no-reply@example.test",
    ORDER_NOTIFICATION_EMAIL="owner@example.test",
    SITE_URL="https://shop.example.test",
)
class OwnerOrderEmailTests(TestCase):
    def test_new_order_email_contains_dashboard_link(self):
        user = User.objects.create_user(
            email="customer@example.test",
            password="CustomerPass123!",
            first_name="Test Customer",
        )
        order = Order.objects.create(
            user=user,
            total_amount="125.00",
            payment_status="Paid",
            status="Processing",
        )

        self.assertTrue(send_owner_order_email(order.id))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["owner@example.test"])
        self.assertEqual(message.reply_to, ["customer@example.test"])
        self.assertIn("ORD-", message.subject)
        self.assertIn(
            f"https://shop.example.test/eehook-dashboard/orders/{order.id}",
            message.body,
        )
        self.assertEqual(message.alternatives[0][1], "text/html")

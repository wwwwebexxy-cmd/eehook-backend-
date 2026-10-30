from datetime import timedelta

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .customer_emails import (
    send_order_confirmation_email,
    send_paid_invoice_email,
    send_registration_email,
)
from .models import Order, User, WelcomeBonus, WelcomeBonusAssignment


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="no-reply@example.test",
    SITE_URL="https://shop.example.test",
)
class CustomerEmailTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="customer@example.test",
            password="CustomerPass123!",
            first_name="Test Customer",
        )

    def test_registration_email_contains_assigned_welcome_bonus_and_is_idempotent(self):
        now = timezone.now()
        bonus = WelcomeBonus.objects.create(
            name="Welcome AED 50",
            discount_type=WelcomeBonus.DISCOUNT_FIXED,
            fixed_amount="50.00",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=30),
        )
        user = User.objects.create_user(
            email="new-customer@example.test",
            password="CustomerPass123!",
            first_name="New Customer",
        )
        assignment = WelcomeBonusAssignment.objects.get(
            user=user,
            welcome_bonus=bonus,
        )

        self.assertTrue(send_registration_email(user.id))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn("Welcome to EEHOOK", message.subject)
        self.assertIn("New Customer", message.body)
        self.assertIn(assignment.code, message.body)
        self.assertIsNotNone(User.objects.get(pk=user.pk).registration_email_sent_at)

        self.assertFalse(send_registration_email(user.id))
        self.assertEqual(len(mail.outbox), 1)

    def test_registration_endpoint_sends_welcome_email(self):
        response = self.client.post(
            "/register/",
            {
                "first_name": "Registered Customer",
                "email": "registered@example.test",
                "password": "CustomerPass123!",
                "confirm_password": "CustomerPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Registered Customer", mail.outbox[0].body)

    def test_cod_order_confirmation_is_idempotent(self):
        order = Order.objects.create(
            user=self.user,
            total_amount="125.00",
            payment_method="COD",
            payment_status="Pending",
            status="Pending",
        )

        self.assertTrue(send_order_confirmation_email(order.id))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn("Order confirmed", message.subject)
        self.assertIn(f"ORD-{order.pk:06d}", message.body)
        self.assertIsNotNone(Order.objects.get(pk=order.pk).order_confirmation_email_sent_at)

        self.assertFalse(send_order_confirmation_email(order.id))
        self.assertEqual(len(mail.outbox), 1)

    def test_paid_invoice_email_attaches_generated_pdf_and_is_idempotent(self):
        order = Order.objects.create(
            user=self.user,
            subtotal="100.00",
            total_amount="105.00",
            payment_method="Cashfree",
            payment_status="Paid",
            status="Processing",
        )

        self.assertTrue(send_paid_invoice_email(order.id))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn("Paid invoice", message.subject)
        self.assertIn("Your payment has been received", message.body)
        self.assertEqual(len(message.attachments), 1)
        attachment = message.attachments[0]
        self.assertTrue(attachment[0].endswith(".pdf"))
        self.assertEqual(attachment[2], "application/pdf")
        self.assertTrue(attachment[1].startswith(b"%PDF"))
        self.assertIsNotNone(Order.objects.get(pk=order.pk).paid_invoice_email_sent_at)

        self.assertFalse(send_paid_invoice_email(order.id))
        self.assertEqual(len(mail.outbox), 1)

    def test_admin_marking_order_paid_sends_invoice(self):
        admin = User.objects.create_superuser(
            email="admin@example.test",
            password="SuperAdminPass123!",
        )
        order = Order.objects.create(
            user=self.user,
            total_amount="125.00",
            payment_method="COD",
            payment_status="Pending",
            status="Pending",
        )
        self.client.force_authenticate(user=admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(
                f"/orders/{order.pk}/",
                {"payment_status": "Paid"},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Paid invoice", mail.outbox[0].subject)

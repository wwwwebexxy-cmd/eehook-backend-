import base64
from datetime import timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .customer_emails import (
    send_order_confirmation_email,
    send_paid_invoice_email,
    send_registration_email,
)
from .models import (
    Address,
    Category,
    Order,
    OrderItem,
    Product,
    ProductImage,
    ProductVariant,
    SubCategory,
    User,
    WelcomeBonus,
    WelcomeBonusAssignment,
)


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

    def test_registration_email_uses_current_bonus_and_eligible_product_copy(self):
        now = timezone.now()
        category = Category.objects.create(name="Email Category")
        subcategory = SubCategory.objects.create(
            category=category,
            name="Email Subcategory",
        )
        product = Product.objects.create(
            category=category,
            subcategory=subcategory,
            name="Eligible Email Product",
            description="A product shown in the welcome email.",
        )
        active_bonus = WelcomeBonus.objects.create(
            name="Current Welcome AED 50",
            applicability_type=WelcomeBonus.APPLICABILITY_PRODUCT,
            discount_type=WelcomeBonus.DISCOUNT_FIXED,
            fixed_amount="50.00",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=30),
        )
        active_bonus.products.add(product)
        expired_bonus = WelcomeBonus.objects.create(
            name="Expired Welcome AED 90",
            discount_type=WelcomeBonus.DISCOUNT_FIXED,
            fixed_amount="90.00",
            start_date=now - timedelta(days=30),
            end_date=now - timedelta(days=1),
        )
        user = User.objects.create_user(
            email="current-bonus@example.test",
            password="CustomerPass123!",
            first_name="Current Bonus",
        )
        expired_assignment = WelcomeBonusAssignment.objects.create(
            user=user,
            welcome_bonus=expired_bonus,
            code="WB-EXPIRED-EMAIL",
        )

        self.assertTrue(send_registration_email(user.id))
        message = mail.outbox[0]
        html = message.alternatives[0][0]

        self.assertIn("AED 50.00 off", message.body)
        self.assertIn(product.name, message.body)
        self.assertNotIn(expired_assignment.code, message.body)
        self.assertIn("cid:eehook-logo", html)
        self.assertIn(product.name, html)
        self.assertIn("https://www.instagram.com/eehook.ae", html)
        self.assertIn("Member offers", html)
        self.assertLess(html.index("YOUR WELCOME GIFT"), html.index("Member offers"))
        self.assertNotIn("coupon", message.body.lower())
        self.assertNotIn("offer", message.body.lower())
        self.assertNotIn(expired_assignment.code, html)
        self.assertTrue(
            any(
                part.get("Content-ID") == "<eehook-logo>"
                for part in message.message().walk()
            )
        )

    def test_cod_order_confirmation_is_idempotent(self):
        category = Category.objects.create(name="Order Email Category")
        subcategory = SubCategory.objects.create(
            category=category,
            name="Order Email Subcategory",
        )
        product = Product.objects.create(
            category=category,
            subcategory=subcategory,
            name="Order Email Product",
            description="A product rendered in the order email.",
            estimated_delivery_time="30-31 Oct",
        )
        variant = ProductVariant.objects.create(
            product=product,
            price_type="single",
            price="125.00",
            stock=4,
            sku="ORDER-EMAIL-001",
        )
        ProductImage.objects.create(
            variant=variant,
            image=SimpleUploadedFile(
                "order-email.png",
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                ),
                content_type="image/png",
            ),
            is_primary=True,
        )
        address = Address.objects.create(
            user=self.user,
            full_name="Test Customer",
            address_line="Apartment 1, Marina Gate",
            city="Dubai Marina",
            emirate="Dubai",
            country="UAE",
        )
        order = Order.objects.create(
            user=self.user,
            address=address,
            subtotal="125.00",
            discount_amount="5.00",
            total_amount="120.00",
            payment_method="COD",
            payment_status="Pending",
            status="Pending",
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=1,
            original_price="125.00",
            price="120.00",
            total_price="120.00",
        )

        self.assertTrue(send_order_confirmation_email(order.id))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn("Order confirmed", message.subject)
        self.assertIn(f"ORD-{order.pk:06d}", message.body)
        self.assertIn("Order Email Product", message.body)
        self.assertIn("AED 120.00", message.body)
        html = message.alternatives[0][0]
        self.assertIn("ORDER CONFIRMED", html)
        self.assertIn("YOUR ITEMS", html)
        self.assertIn("ORDER-EMAIL-001", html)
        self.assertIn("cid:order-item-0", html)
        self.assertIn("SHIPPING TO", html)
        self.assertIn("PAYMENT", html)
        self.assertIn("VIEW MY ORDER", html)
        self.assertIn("cid:eehook-logo", html)
        self.assertTrue(
            any(
                part.get("Content-ID") == "<eehook-logo>"
                for part in message.message().walk()
            )
        )
        self.assertTrue(
            any(
                part.get("Content-ID") == "<order-item-0>"
                for part in message.message().walk()
            )
        )
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
        html = message.alternatives[0][0]
        self.assertIn("INVOICE", html)
        self.assertIn("PAID", html)
        self.assertIn("BILLED TO", html)
        self.assertIn("ORDER DETAILS", html)
        self.assertIn("WHERE&apos;S MY ORDER?", html)
        self.assertIn("Buy More", html)
        self.assertIn("My Account", html)
        self.assertIn("cid:eehook-logo", html)
        pdf_attachments = [
            attachment
            for attachment in message.attachments
            if isinstance(attachment, tuple)
            and len(attachment) == 3
            and attachment[2] == "application/pdf"
        ]
        self.assertEqual(len(pdf_attachments), 1)
        attachment = pdf_attachments[0]
        self.assertTrue(attachment[0].endswith(".pdf"))
        self.assertEqual(attachment[2], "application/pdf")
        self.assertTrue(attachment[1].startswith(b"%PDF"))
        self.assertTrue(
            any(
                part.get("Content-ID") == "<eehook-logo>"
                for part in message.message().walk()
            )
        )
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

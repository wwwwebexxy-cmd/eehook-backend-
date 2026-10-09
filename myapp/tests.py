from django.test import TestCase
from django.conf import settings

# Create your tests here.

# Keep the security regression suite discoverable by Django's default runner.
from rest_framework.test import APIClient
from django.test import override_settings
from django.core.cache import cache
from django.utils import timezone

from decimal import Decimal
from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from PIL import Image
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from .admin import ProductAdminForm, ProductVariantForm
from .models import (
    Address,
    AdminAuditLog,
    Brand,
    Category,
    Color,
    Coupon,
    CouponApplication,
    CouponUsage,
    Cart,
    Offer,

    Order,
    OrderItem,
    Product,
    ProductImage,
    ProductRelatedProduct,
    ProductVariant,
    ProductVariantUnit,
    ProductView,
    SubCategory,
    TrustBenefit,
    Unit,
    UnitType,
    User,
    Wishlist,
    WelcomeBonus,
    WelcomeBonusAssignment,
    WelcomeBonusNotification,
    WelcomeBonusRedemption,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class TrustBenefitApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            email="trust-benefit-customer@example.invalid",
            password="CustomerPass123!",
            role="Customer",
        )
        self.super_admin = User.objects.create_superuser(
            email="trust-benefit-admin@example.invalid",
            password="SuperAdminPass123!",
        )

    def test_management_endpoint_is_super_admin_only(self):
        self.assertIn(self.client.get("/admin/manage/trust-benefits/").status_code, (401, 403))
        self.client.force_authenticate(user=self.customer)
        self.assertEqual(self.client.get("/admin/manage/trust-benefits/").status_code, 403)
        self.client.force_authenticate(user=self.super_admin)
        self.assertEqual(self.client.get("/admin/manage/trust-benefits/").status_code, 200)
        schema = self.client.get("/admin/manage/schema/")
        self.assertEqual(schema.status_code, 200)
        self.assertIn("trust-benefits", {resource["key"] for resource in schema.data["resources"]})

    def test_icon_key_is_validated_and_crud_supports_activation(self):
        self.client.force_authenticate(user=self.super_admin)
        invalid = self.client.post(
            "/admin/manage/trust-benefits/",
            {
                "key": "unsupported",
                "title": "Unsupported",
                "description": "This should not be accepted.",
                "icon_key": "unsupported",
                "display_order": 1,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)

        created = self.client.post(
            "/admin/manage/trust-benefits/",
            {
                "key": "secure-payment",
                "title": "Secure payment",
                "description": "Payments are processed through Stripe checkout.",
                "icon_key": "secure-payment",
                "display_order": 2,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["icon_key"], "secure-payment")
        deactivated = self.client.patch(
            f"/admin/manage/trust-benefits/{created.data['id']}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(deactivated.status_code, 200)
        self.assertFalse(deactivated.data["is_active"])

    def test_homepage_returns_only_active_benefits_in_display_order(self):
        later = TrustBenefit.objects.create(
            key="delivery-information",
            title="Delivery information",
            description="Delivery details are shown before checkout.",
            icon_key="delivery-information",
            display_order=2,
        )
        first = TrustBenefit.objects.create(
            key="secure-payment",
            title="Secure payment",
            description="Payments are processed through Stripe checkout.",
            icon_key="secure-payment",
            display_order=1,
        )
        TrustBenefit.objects.create(
            key="easy-returns",
            title="Easy returns",
            description="Return information is available before purchase.",
            icon_key="easy-returns",
            display_order=3,
            is_active=False,
        )

        response = self.client.get("/homepage/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["trust_benefits"],
            [
                {
                    "id": first.id,
                    "key": "secure-payment",
                    "title": "Secure payment",
                    "description": "Payments are processed through Stripe checkout.",
                    "icon_key": "secure-payment",
                },
                {
                    "id": later.id,
                    "key": "delivery-information",
                    "title": "Delivery information",
                    "description": "Delivery details are shown before checkout.",
                    "icon_key": "delivery-information",
                },
            ],
        )


@override_settings(SECURE_SSL_REDIRECT=False)
class SecurityBoundaryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        cache.clear()

    def test_cart_requires_authentication(self):
        response = self.client.get("/cart/")
        self.assertIn(response.status_code, (401, 403))

    def test_order_detail_requires_authentication(self):
        response = self.client.get("/order-details/1/")
        self.assertIn(response.status_code, (401, 403))

    def test_admin_dashboard_is_not_public(self):
        response = self.client.get("/admin-dashboard-cards/")
        self.assertIn(response.status_code, (401, 403))

    def test_invalid_catalog_filter_is_rejected(self):
        response = self.client.get("/products/?category=1%20OR%201%3D1")
        self.assertEqual(response.status_code, 400)

    def test_untrusted_ordering_is_rejected(self):
        response = self.client.get("/products/?sort=price%27%20DESC")
        self.assertEqual(response.status_code, 400)

    def test_password_reset_does_not_disclose_account_existence(self):
        response = self.client.post("/forgot-password/", {"email": "not-an-email"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("message", response.data)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_HOST_USER="noreply@example.invalid",
    )
    def test_password_reset_has_a_generic_response_and_revokes_refresh_tokens(self):
        user = User.objects.create_user(
            email="reset-revocation@example.invalid",
            password="ExistingPass123!",
        )
        RefreshToken.for_user(user)
        outstanding = OutstandingToken.objects.get(user=user)

        known = self.client.post("/forgot-password/", {"email": user.email}, format="json")
        unknown = self.client.post(
            "/forgot-password/", {"email": "unknown@example.invalid"}, format="json"
        )
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.data, unknown.data)

        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset = self.client.post(
            f"/reset-password/{uidb64}/{token}/",
            {"password": "NewStrongPass123!", "confirm_password": "NewStrongPass123!"},
            format="json",
        )
        self.assertEqual(reset.status_code, 200, reset.data)
        self.assertTrue(BlacklistedToken.objects.filter(token=outstanding).exists())

    @patch("myapp.views.id_token.verify_oauth2_token")
    def test_google_login_requires_verified_active_account(self, verify_token):
        verify_token.return_value = {
            "email": "unverified@example.invalid",
            "email_verified": False,
        }
        self.assertEqual(
            self.client.post("/google-login/", {"token": "token"}, format="json").status_code,
            400,
        )

        disabled = User.objects.create_user(
            email="disabled@example.invalid",
            password="DisabledPass123!",
            is_active=False,
        )
        verify_token.return_value = {
            "email": disabled.email,
            "email_verified": True,
        }
        self.assertEqual(
            self.client.post("/google-login/", {"token": "token"}, format="json").status_code,
            403,
        )

    @patch("payment.views.stripe.Refund.create")
    def test_unfulfillable_paid_checkout_is_refunded_once(self, refund):
        from payment.views import CheckoutFulfillmentError, refund_unfulfillable_checkout

        user = User.objects.create_user(
            email="refund@example.invalid", password="RefundPass123!"
        )
        address = Address.objects.create(user=user, full_name="Refund Customer")
        session = SimpleNamespace(
            id="cs_refund_once",
            payment_intent="pi_refund_once",
            amount_total=1234,
            metadata={"user_id": str(user.id), "address_id": str(address.id)},
        )

        order = refund_unfulfillable_checkout(
            session, CheckoutFulfillmentError("Insufficient stock")
        )
        replay = refund_unfulfillable_checkout(
            session, CheckoutFulfillmentError("Insufficient stock")
        )

        self.assertEqual(order.id, replay.id)
        self.assertEqual(order.payment_status, "Refunded")
        self.assertEqual(order.status, "Cancelled")
        refund.assert_called_once_with(
            payment_intent="pi_refund_once",
            idempotency_key="checkout-fulfillment-refund:cs_refund_once",
        )

    @override_settings(
        GLOBAL_RATE_LIMIT=1000,
        ADMIN_LOGIN_MAX_ATTEMPTS=2,
        ADMIN_LOGIN_WINDOW=900,
    )
    def test_admin_login_is_locked_after_repeated_failures(self):
        for _ in range(2):
            response = self.client.post(
                "/admin/login/",
                {"username": "admin@example.com", "password": "wrong"},
            )
            self.assertEqual(response.status_code, 200)
        response = self.client.post(
            "/admin/login/",
            {"username": "admin@example.com", "password": "wrong"},
        )
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)


    def test_login_types_keep_customer_and_super_admin_flows_separate(self):
        customer = User.objects.create_user(
            email="customer-login@example.invalid",
            password="CustomerPass123!",
            role="Customer",
        )
        super_admin = User.objects.create_superuser(
            email="super-admin-login@example.invalid",
            password="SuperAdminPass123!",
        )

        customer_response = self.client.post(
            "/login/",
            {"email": customer.email, "password": "CustomerPass123!", "login_type": "customer"},
            format="json",
        )
        self.assertEqual(customer_response.status_code, 200)

        admin_through_customer_response = self.client.post(
            "/login/",
            {"email": super_admin.email, "password": "SuperAdminPass123!", "login_type": "customer"},
            format="json",
        )
        self.assertEqual(admin_through_customer_response.status_code, 403)

        customer_through_admin_response = self.client.post(
            "/login/",
            {"email": customer.email, "password": "CustomerPass123!", "login_type": "super_admin"},
            format="json",
        )
        self.assertEqual(customer_through_admin_response.status_code, 403)

        super_admin_response = self.client.post(
            "/login/",
            {"email": super_admin.email, "password": "SuperAdminPass123!", "login_type": "super_admin"},
            format="json",
        )
        self.assertEqual(super_admin_response.status_code, 200)

    def test_registration_rejects_weak_passwords(self):
        response = self.client.post(
            "/register/",
            {
                "first_name": "New",
                "email": "weak-password@example.invalid",
                "password": "password",
                "confirm_password": "password",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_HOST_USER="noreply@example.invalid",
        SITE_URL="http://localhost:5173",
    )
    def test_forgot_password_sends_frontend_reset_link_and_accepts_strong_password(self):
        user = User.objects.create_user(
            email="reset-flow@example.invalid",
            password="ExistingPass123!",
            role="Customer",
        )

        forgot_response = self.client.post(
            "/forgot-password/",
            {"email": user.email},
            format="json",
        )
        self.assertEqual(forgot_response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        reset_link = next(
            line.strip()
            for line in mail.outbox[0].body.splitlines()
            if "/reset-password/" in line
        )
        reset_path = reset_link.split("http://localhost:5173", 1)[1]

        reset_response = self.client.post(
            f"{reset_path}/",
            {
                "password": "NewStrongPass123!",
                "confirm_password": "NewStrongPass123!",
            },
            format="json",
        )
        self.assertEqual(reset_response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewStrongPass123!"))

        weak_reset_response = self.client.post(
            f"{reset_path}/",
            {
                "password": "weakpass",
                "confirm_password": "weakpass",
            },
            format="json",
        )
        self.assertEqual(weak_reset_response.status_code, 400)
        self.assertIn("password", weak_reset_response.data)

    @override_settings(GLOBAL_RATE_LIMIT=2, GLOBAL_RATE_WINDOW=60)
    def test_global_request_flood_returns_429(self):
        self.client.get("/products/")
        self.client.get("/products/")
        response = self.client.get("/products/")
        self.assertEqual(response.status_code, 429)


@override_settings(SECURE_SSL_REDIRECT=False, JWT_COOKIE_SECURE=True)
class CookieAuthenticationSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = User.objects.create_user(
            email="cookie-user@example.invalid",
            password="CookiePass123!",
            role="Customer",
        )

    def _csrf_token(self):
        response = self.client.get("/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        return response.cookies[settings.CSRF_COOKIE_NAME].value

    def test_http_is_redirected_to_https(self):
        with override_settings(SECURE_SSL_REDIRECT=True):
            response = APIClient().get("/health/", secure=False)
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response["Location"].startswith("https://"))

    def test_login_refresh_rotation_logout_and_session_use_secure_cookies(self):
        csrf_token = self._csrf_token()
        login_response = self.client.post(
            "/login/",
            {
                "email": self.user.email,
                "password": "CookiePass123!",
                "login_type": "customer",
            },
            format="json",
        )
        self.assertEqual(login_response.status_code, 200, login_response.data)
        self.assertNotIn("access", login_response.data)
        self.assertNotIn("refresh", login_response.data)
        for cookie_name in (settings.JWT_ACCESS_COOKIE_NAME, settings.JWT_REFRESH_COOKIE_NAME):
            cookie = login_response.cookies[cookie_name]
            self.assertTrue(cookie["httponly"])
            self.assertTrue(cookie["secure"])
            self.assertEqual(cookie["samesite"], "Lax")

        session_response = self.client.get("/auth/session/")
        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(session_response.data["user"]["id"], self.user.id)
        self.assertEqual(session_response.data["user"]["permissions"], {"is_super_admin": False})

        # Ambient refresh cookies cannot rotate without the CSRF header.
        csrf_failed = self.client.post("/token/refresh/", {}, format="json")
        self.assertEqual(csrf_failed.status_code, 403)

        old_refresh = self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME].value
        old_jti = RefreshToken(old_refresh)["jti"]
        rotated = self.client.post(
            "/token/refresh/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(rotated.status_code, 200, rotated.data)
        self.assertNotIn("access", rotated.data)
        self.assertNotIn("refresh", rotated.data)
        self.assertNotEqual(
            old_refresh,
            rotated.cookies[settings.JWT_REFRESH_COOKIE_NAME].value,
        )
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=old_jti).exists())

        logout = self.client.post(
            "/logout/", {}, format="json", HTTP_X_CSRFTOKEN=csrf_token
        )
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(logout.cookies[settings.JWT_ACCESS_COOKIE_NAME]["max-age"], 0)
        self.assertEqual(logout.cookies[settings.JWT_REFRESH_COOKIE_NAME]["max-age"], 0)
        self.assertEqual(self.client.get("/auth/session/").status_code, 401)

    @patch("myapp.views.id_token.verify_oauth2_token")
    def test_google_login_uses_the_same_cookie_only_contract(self, verify_token):
        verify_token.return_value = {
            "email": self.user.email,
            "email_verified": True,
            "given_name": "Cookie",
        }
        response = self.client.post("/google-login/", {"token": "google-token"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        self.assertIn(settings.JWT_ACCESS_COOKIE_NAME, response.cookies)
        self.assertIn(settings.JWT_REFRESH_COOKIE_NAME, response.cookies)

    def test_django_admin_rejects_staff_member_without_super_admin_role(self):
        staff_customer = User.objects.create_user(
            email="staff-customer@example.invalid",
            password="StaffCustomerPass123!",
            role="Customer",
            is_staff=True,
        )
        self.client.force_login(staff_customer)
        denied = self.client.get("/admin/")
        self.assertEqual(denied.status_code, 302)
        self.assertIn("/admin/login/", denied["Location"])

        super_admin = User.objects.create_superuser(
            email="cookie-admin@example.invalid", password="AdminPass123!"
        )
        self.client.force_login(super_admin)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_authenticated_customer_cannot_access_other_customer_objects(self):
        other = User.objects.create_user(
            email="other-owner@example.invalid", password="OtherPass123!"
        )
        address = Address.objects.create(user=other, full_name="Other owner")
        order = Order.objects.create(user=other, total_amount=Decimal("1.00"))
        self.client.force_authenticate(user=self.user)

        self.assertEqual(self.client.get(f"/order-details/{order.id}/").status_code, 403)
        self.assertEqual(self.client.delete(f"/addresses/{address.id}/").status_code, 403)
        self.assertEqual(
            self.client.post(
                "/payment/create-checkout-session/", {"address": address.id}, format="json"
            ).status_code,
            403,
        )

    @patch("payment.views.stripe.Webhook.construct_event")
    def test_duplicate_signed_webhook_is_idempotent(self, construct_event):
        class StripeSession(dict):
            @property
            def payment_status(self):
                return self["payment_status"]

            @property
            def metadata(self):
                return self["metadata"]

            @property
            def id(self):
                return self["id"]

        session = StripeSession(
            id="cs_duplicate_webhook",
            payment_status="paid",
            metadata={"user_id": str(self.user.id), "address_id": "1"},
        )
        Order.objects.create(
            user=self.user,
            stripe_session_id=session.id,
            payment_status="Paid",
            status="Processing",
            total_amount=Decimal("1.00"),
        )
        construct_event.return_value = {
            "type": "checkout.session.completed",
            "data": {"object": session},
        }
        for _ in range(2):
            response = self.client.post(
                "/payment/stripe-webhook/",
                b"{}",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="test-signature",
            )
            self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.filter(stripe_session_id=session.id).count(), 1)


class CouponApplicationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="coupon-user@example.invalid",
            password="CouponPass123!",
            role="Customer",
        )
        self.other_user = User.objects.create_user(
            email="other-coupon-user@example.invalid",
            password="CouponPass123!",
            role="Customer",
        )
        category = Category.objects.create(
            name="Coupon Test Category",
            image=SimpleUploadedFile("coupon-category.jpg", b"category"),
        )
        subcategory = SubCategory.objects.create(
            category=category,
            name="Coupon Test Subcategory",
        )
        self.product = Product.objects.create(
            category=category,
            subcategory=subcategory,
            name="Coupon Test Product",
            description="A product for coupon validation tests.",
        )
        self.other_product = Product.objects.create(
            category=category,
            subcategory=subcategory,
            name="Other Coupon Test Product",
            description="Another product for coupon validation tests.",
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            price_type="single",
            price=Decimal("10.00"),
            stock=5,
        )
        self.other_variant = ProductVariant.objects.create(
            product=self.other_product,
            price_type="single",
            price=Decimal("12.00"),
            stock=5,
        )
        now = timezone.now()
        self.coupon = Coupon.objects.create(
            code="ONCEONLY",
            discount_percentage=10,
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=1),
        )
        self.client.force_authenticate(user=self.user)

    def validate(self, product):
        return self.client.post(
            "/validate-coupon/",
            {"code": self.coupon.code, "product_id": product.id},
            format="json",
        )

    def test_coupon_application_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.validate(self.product)
        self.assertIn(response.status_code, (401, 403))

    def test_coupon_application_is_once_per_user_coupon_and_product(self):
        first = self.validate(self.product)
        self.assertEqual(first.status_code, 200, first.data)

        second = self.validate(self.product)
        self.assertEqual(second.status_code, 400, second.data)
        self.assertEqual(second.data["error_code"], "COUPON_ALREADY_APPLIED")
        self.assertEqual(
            CouponApplication.objects.filter(
                user=self.user,
                coupon=self.coupon,
                product=self.product,
            ).count(),
            1,
        )

        other_product = self.validate(self.other_product)
        self.assertEqual(other_product.status_code, 200, other_product.data)
        added = self.client.post(
            "/cart/add/",
            {"variant": self.other_variant.id, "quantity": 1},
            format="json",
        )
        self.assertEqual(added.status_code, 200, added.data)
        self.assertEqual(
            Cart.objects.get(user=self.user, variant=self.other_variant).coupon_id,
            self.coupon.id,
        )

        self.client.force_authenticate(user=self.other_user)
        other_user = self.validate(self.product)
        self.assertEqual(other_user.status_code, 200, other_user.data)

    def test_variant_independence_is_enforced_by_product_id(self):
        self.assertEqual(self.validate(self.product).status_code, 200)
        self.assertEqual(self.validate(self.product).status_code, 400)

    def test_coupon_usage_on_one_product_does_not_block_another_product(self):
        CouponUsage.objects.create(
            user=self.user,
            coupon=self.coupon,
            product=self.product,
        )

        used_product = self.validate(self.product)
        self.assertEqual(used_product.status_code, 400)

        other_product = self.validate(self.other_product)
        self.assertEqual(other_product.status_code, 200, other_product.data)

    def test_applied_coupon_is_carried_to_cart_without_becoming_reusable(self):
        self.assertEqual(self.validate(self.product).status_code, 200)

        added = self.client.post(
            "/cart/add/",
            {"variant": self.variant.id, "quantity": 1},
            format="json",
        )
        self.assertEqual(added.status_code, 200, added.data)
        self.assertEqual(
            Cart.objects.get(user=self.user, variant=self.variant).coupon_id,
            self.coupon.id,
        )
        self.assertEqual(self.validate(self.product).status_code, 400)


class CouponEnhancementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            email="coupon-admin@example.invalid",
            password="CouponAdminPass123!",
        )
        self.customer = User.objects.create_user(
            email="coupon-customer@example.invalid",
            password="CouponCustomerPass123!",
            role="Customer",
        )
        self.footwear = Category.objects.create(
            name="Coupon Footwear",
            image=SimpleUploadedFile("footwear.jpg", b"category"),
        )
        self.clothing = Category.objects.create(
            name="Coupon Clothing",
            image=SimpleUploadedFile("clothing.jpg", b"category"),
        )
        self.footwear_subcategory = SubCategory.objects.create(
            category=self.footwear,
            name="Coupon Shoes",
        )
        self.clothing_subcategory = SubCategory.objects.create(
            category=self.clothing,
            name="Coupon Shirts",
        )
        self.shoe = Product.objects.create(
            category=self.footwear,
            subcategory=self.footwear_subcategory,
            name="Coupon Shoe",
            description="A shoe for coupon tests.",
        )
        self.other_shoe = Product.objects.create(
            category=self.footwear,
            subcategory=self.footwear_subcategory,
            name="Other Coupon Shoe",
            description="Another shoe for coupon tests.",
        )
        self.shirt = Product.objects.create(
            category=self.clothing,
            subcategory=self.clothing_subcategory,
            name="Coupon Shirt",
            description="A shirt for coupon tests.",
        )
        self.shoe_variant = ProductVariant.objects.create(
            product=self.shoe,
            price_type="single",
            price="2000.00",
            stock=5,
        )
        self.other_shoe_variant = ProductVariant.objects.create(
            product=self.other_shoe,
            price_type="single",
            price="1000.00",
            stock=5,
        )
        self.shirt_variant = ProductVariant.objects.create(
            product=self.shirt,
            price_type="single",
            price="500.00",
            stock=5,
        )
        self.start = timezone.now() - timedelta(days=1)
        self.end = timezone.now() + timedelta(days=1)

    def coupon_payload(self, **overrides):
        payload = {
            "code": "COUPONTEST",
            "applicability_type": "CATEGORY",
            "category": self.footwear.id,
            "products": [],
            "discount_type": "PERCENTAGE",
            "discount_percentage": "10.00",
            "fixed_amount": None,
            "start_date": self.start.isoformat(),
            "end_date": self.end.isoformat(),
            "is_active": True,
        }
        payload.update(overrides)
        return payload

    def test_admin_accepts_category_percentage_and_product_fixed_coupons(self):
        self.client.force_authenticate(user=self.admin)
        category_response = self.client.post(
            "/admin/manage/coupons/",
            self.coupon_payload(),
            format="json",
        )
        self.assertEqual(category_response.status_code, 201, category_response.data)
        category_coupon = Coupon.objects.get(code="COUPONTEST")
        self.assertEqual(category_coupon.category_id, self.footwear.id)
        self.assertEqual(category_coupon.discount_percentage, Decimal("10.00"))

        product_response = self.client.post(
            "/admin/manage/coupons/",
            self.coupon_payload(
                code="FIXEDTEST",
                applicability_type="PRODUCT",
                category=None,
                products=[self.shoe.id],
                discount_type="FIXED",
                discount_percentage=None,
                fixed_amount="500.00",
            ),
            format="json",
        )
        self.assertEqual(product_response.status_code, 201, product_response.data)
        fixed_coupon = Coupon.objects.get(code="FIXEDTEST")
        self.assertEqual(fixed_coupon.products.get(), self.shoe)
        self.assertIsNone(fixed_coupon.discount_percentage)
        self.assertEqual(fixed_coupon.fixed_amount, Decimal("500.00"))

    def test_admin_rejects_invalid_coupon_combinations(self):
        self.client.force_authenticate(user=self.admin)
        for invalid in (
            {"discount_percentage": "0"},
            {"discount_percentage": "101"},
            {"discount_percentage": "-10"},
            {"applicability_type": "CATEGORY", "category": None},
            {"applicability_type": "PRODUCT", "category": None, "products": []},
        ):
            response = self.client.post(
                "/admin/manage/coupons/",
                self.coupon_payload(code=None, **invalid),
                format="json",
            )
            self.assertEqual(response.status_code, 400, response.data)

    def test_category_coupon_is_applied_only_to_eligible_cart_products(self):
        coupon = Coupon.objects.create(
            code="FOOTWEAR10",
            applicability_type=Coupon.APPLICABILITY_CATEGORY,
            category=self.footwear,
            discount_type=Coupon.DISCOUNT_PERCENTAGE,
            discount_percentage=10,
            start_date=self.start,
            end_date=self.end,
        )
        self.client.force_authenticate(user=self.customer)
        validated = self.client.post(
            "/validate-coupon/",
            {"code": coupon.code, "product_id": self.shoe.id},
            format="json",
        )
        self.assertEqual(validated.status_code, 200, validated.data)

        for variant in (self.shoe_variant, self.other_shoe_variant, self.shirt_variant):
            response = self.client.post(
                "/cart/add/",
                {"variant": variant.id, "quantity": 1},
                format="json",
            )
            self.assertEqual(response.status_code, 200, response.data)

        cart = {
            item.variant.product.name: item
            for item in Cart.objects.filter(user=self.customer).select_related("variant__product")
        }
        self.assertEqual(cart["Coupon Shoe"].coupon_id, coupon.id)
        self.assertEqual(cart["Other Coupon Shoe"].coupon_id, coupon.id)
        self.assertIsNone(cart["Coupon Shirt"].coupon_id)

        response = self.client.get("/cart/")
        self.assertEqual(response.status_code, 200)
        prices = {item["product_name"]: Decimal(str(item["discounted_price"])) for item in response.data["items"]}
        self.assertEqual(prices["Coupon Shoe"], Decimal("1800.00"))
        self.assertEqual(prices["Other Coupon Shoe"], Decimal("900.00"))
        self.assertEqual(prices["Coupon Shirt"], Decimal("500.00"))

    def test_fixed_coupon_is_capped_at_the_eligible_price(self):
        coupon = Coupon.objects.create(
            code="FIXEDCAP",
            applicability_type=Coupon.APPLICABILITY_PRODUCT,
            discount_type=Coupon.DISCOUNT_FIXED,
            fixed_amount=500,
            start_date=self.start,
            end_date=self.end,
        )
        coupon.products.add(self.shirt)
        self.client.force_authenticate(user=self.customer)
        self.assertEqual(
            self.client.post(
                "/validate-coupon/",
                {"code": coupon.code, "product_id": self.shirt.id},
                format="json",
            ).status_code,
            200,
        )
        added = self.client.post(
            "/cart/add/",
            {"variant": self.shirt_variant.id, "quantity": 1},
            format="json",
        )
        self.assertEqual(added.status_code, 200, added.data)
        response = self.client.get("/cart/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["items"][0]["discounted_price"], Decimal("0.00"))

    def create_product_percentage_coupon(self, code="PRODUCT10"):
        coupon = Coupon.objects.create(
            code=code,
            applicability_type=Coupon.APPLICABILITY_PRODUCT,
            discount_type=Coupon.DISCOUNT_PERCENTAGE,
            discount_percentage=10,
            start_date=self.start,
            end_date=self.end,
        )
        coupon.products.add(self.shoe)
        return coupon

    def test_inactive_coupon_validation_returns_strict_error_contract(self):
        coupon = self.create_product_percentage_coupon("INACTIVE10")
        coupon.is_active = False
        coupon.save()
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            "/validate-coupon/",
            {"code": coupon.code, "product_id": self.shoe.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error_code"], "COUPON_INACTIVE")
        self.assertEqual(response.data["detail"], "This coupon is no longer active.")
        self.assertEqual(response.data["coupon_code"], coupon.code)

    def test_expired_coupon_is_rejected_by_server(self):
        coupon = Coupon.objects.create(
            code="EXPIRED10",
            applicability_type=Coupon.APPLICABILITY_PRODUCT,
            discount_type=Coupon.DISCOUNT_PERCENTAGE,
            discount_percentage=10,
            start_date=self.start - timedelta(days=3),
            end_date=self.start - timedelta(days=1),
        )
        coupon.products.add(self.shoe)
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            "/validate-coupon/",
            {"code": coupon.code, "product_id": self.shoe.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error_code"], "COUPON_INACTIVE")

    def test_deactivated_applied_coupon_is_removed_from_cart_and_discount(self):
        coupon = self.create_product_percentage_coupon("DEACTIVATE10")
        self.client.force_authenticate(user=self.customer)
        self.assertEqual(
            self.client.post(
                "/validate-coupon/",
                {"code": coupon.code, "product_id": self.shoe.id},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/cart/add/",
                {"variant": self.shoe_variant.id, "quantity": 1},
                format="json",
            ).status_code,
            200,
        )

        coupon.is_active = False
        coupon.save()

        response = self.client.get("/cart/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["items"][0]["discounted_price"], Decimal("2000.00"))
        self.assertEqual(response.data["items"][0]["coupon_status"], "COUPON_INACTIVE")
        self.assertIsNone(Cart.objects.get(user=self.customer).coupon_id)

    def test_deactivated_coupon_is_not_attached_when_product_is_added(self):
        coupon = self.create_product_percentage_coupon("ADDDEACT10")
        self.client.force_authenticate(user=self.customer)
        self.assertEqual(
            self.client.post(
                "/validate-coupon/",
                {"code": coupon.code, "product_id": self.shoe.id},
                format="json",
            ).status_code,
            200,
        )
        coupon.is_active = False
        coupon.save()

        response = self.client.post(
            "/cart/add/",
            {"variant": self.shoe_variant.id, "quantity": 1},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        cart_item = Cart.objects.get(user=self.customer)
        self.assertIsNone(cart_item.coupon_id)

    def test_direct_order_endpoint_is_disabled_and_preserves_stock(self):
        coupon = self.create_product_percentage_coupon("ORDERDEACT10")
        self.client.force_authenticate(user=self.customer)
        self.assertEqual(
            self.client.post(
                "/validate-coupon/",
                {"code": coupon.code, "product_id": self.shoe.id},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/cart/add/",
                {"variant": self.shoe_variant.id, "quantity": 1},
                format="json",
            ).status_code,
            200,
        )
        coupon.is_active = False
        coupon.save()
        address = Address.objects.create(
            user=self.customer,
            full_name="Coupon Customer",
            address_line="1 Test Street",
            city="Test City",
            postal_code="0000",
        )

        response = self.client.post(
            "/place-order/",
            {"address": address.id},
            format="json",
        )
        self.assertEqual(response.status_code, 410, response.data)
        self.assertEqual(Order.objects.count(), 0)
        stock_before = self.shoe_variant.stock
        self.shoe_variant.refresh_from_db()
        self.assertEqual(self.shoe_variant.stock, stock_before)
        self.assertTrue(Cart.objects.filter(user=self.customer).exists())

    @patch("payment.views.StripeService.create_checkout_session")
    def test_deactivated_coupon_is_removed_before_payment_session_totals(self, create_session):
        coupon = self.create_product_percentage_coupon("PAYMENTDEACT10")
        self.client.force_authenticate(user=self.customer)
        self.assertEqual(
            self.client.post(
                "/validate-coupon/",
                {"code": coupon.code, "product_id": self.shoe.id},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/cart/add/",
                {"variant": self.shoe_variant.id, "quantity": 1},
                format="json",
            ).status_code,
            200,
        )
        coupon.is_active = False
        coupon.save()
        address = Address.objects.create(
            user=self.customer,
            full_name="Coupon Customer",
            address_line="1 Test Street",
            city="Test City",
            postal_code="0000",
        )
        create_session.return_value.url = "https://checkout.stripe.com/c/pay_test"

        response = self.client.post(
            "/payment/create-checkout-session/",
            {"address": address.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        product_line = create_session.call_args.kwargs["line_items"][0]
        self.assertEqual(product_line["price_data"]["unit_amount"], 200000)

    @patch("payment.views.StripeService.create_checkout_session")
    def test_checkout_rejects_non_stripe_or_non_https_redirect_urls(self, create_session):
        self.client.force_authenticate(user=self.customer)
        self.assertEqual(
            self.client.post(
                "/cart/add/", {"variant": self.shoe_variant.id, "quantity": 1}, format="json"
            ).status_code,
            200,
        )
        address = Address.objects.create(user=self.customer, full_name="Stripe URL Customer")
        create_session.return_value.url = "http://checkout.stripe.com/c/not-secure"
        response = self.client.post(
            "/payment/create-checkout-session/", {"address": address.id}, format="json"
        )
        self.assertEqual(response.status_code, 502, response.data)


class ProductWorkflowRegressionTests(TestCase):
    """Regression coverage for the product-management audit findings."""

    def setUp(self):
        self.media_dir = TemporaryDirectory(prefix="product-tests-")
        self.media_override = override_settings(MEDIA_ROOT=self.media_dir.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.media_dir.cleanup)

        self.admin = User.objects.create_superuser(
            email="product-admin@example.invalid",
            password="AuditPass123!",
        )
        self.category = Category.objects.create(
            name="Test Electronics",
            image=self.image_file("category.jpg", (20, 20, 20)),
        )
        self.other_category = Category.objects.create(
            name="Test Footwear",
            image=self.image_file("other-category.jpg", (30, 30, 30)),
        )
        self.subcategory = SubCategory.objects.create(
            category=self.category,
            name="Test Devices",
        )
        self.other_subcategory = SubCategory.objects.create(
            category=self.other_category,
            name="Test Shoes",
        )
        self.black = Color.objects.create(name="Test Black", code="#000000")
        self.white = Color.objects.create(name="Test White", code="#FFFFFF")
        self.weight = UnitType.objects.create(name="Test Weight")
        self.storage = UnitType.objects.create(name="Test Storage")
        self.kg = Unit.objects.create(unit_type=self.weight, name="Test KG")
        self.gb = Unit.objects.create(unit_type=self.storage, name="Test GB")
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    @staticmethod
    def image_file(name, color):
        stream = BytesIO()
        Image.new("RGB", (24, 24), color).save(stream, format="JPEG")
        return SimpleUploadedFile(name, stream.getvalue(), content_type="image/jpeg")

    def create_product(self, name="Test Product", category=None, subcategory=None):
        return Product.objects.create(
            category=category or self.category,
            subcategory=subcategory or self.subcategory,
            name=name,
            description="A product used by the regression suite.",
        )

    def create_variant(self, product, **data):
        payload = {
            "product": product.id,
            "price_type": "single",
            "price": "10.00",
            "stock": 5,
            **data,
        }
        response = self.client.post(
            "/admin/manage/product-variants/", payload, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        return ProductVariant.objects.get(pk=response.data["id"])

    def test_admin_product_search_matches_name_and_skus_case_insensitively(self):
        name_match = self.create_product("iPhone-compatible charger")
        self.create_variant(name_match, sku="NAME-MATCH-SKU")

        variant_sku_match = self.create_product("Unrelated product")
        self.create_variant(variant_sku_match, sku="CAT50-IPHONEX")

        unit_sku_match = self.create_product("Another unrelated product")
        unit_variant = self.create_variant(
            unit_sku_match,
            price_type="multiple",
            price=None,
            stock=0,
        )
        ProductVariantUnit.objects.create(
            variant=unit_variant,
            unit_type=self.storage,
            unit=self.gb,
            sku="CAT50-IPHONEX-256GB",
            price="20.00",
            stock=1,
        )

        response = self.client.get(
            "/admin/manage/products/",
            {"search": "iphone", "page_size": 20},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
        self.assertEqual(
            {item["id"] for item in response.data["results"]},
            {name_match.id, variant_sku_match.id, unit_sku_match.id},
        )

        empty = self.client.get(
            "/admin/manage/products/",
            {"search": "does-not-exist", "page_size": 20},
        )
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.data["count"], 0)

    def test_variant_price_type_validation(self):
        product = self.create_product()

        with self.assertRaises(ValidationError):
            ProductVariant(
                product=product,
                price_type="single",
                price=None,
                stock=1,
            ).full_clean()

        missing_single_price = self.client.post(
            "/admin/manage/product-variants/",
            {"product": product.id, "price_type": "single", "stock": 5},
            format="json",
        )
        self.assertEqual(missing_single_price.status_code, 400)

        multiple_with_price = self.client.post(
            "/admin/manage/product-variants/",
            {
                "product": product.id,
                "price_type": "multiple",
                "price": "10.00",
                "stock": 0,
            },
            format="json",
        )
        self.assertEqual(multiple_with_price.status_code, 400)

        valid_single = self.create_variant(product)
        self.assertEqual(valid_single.price, Decimal("10.00"))
        duplicate_no_color = self.client.post(
            "/admin/manage/product-variants/",
            {
                "product": product.id,
                "price_type": "single",
                "price": "11.00",
                "stock": 1,
            },
            format="json",
        )
        self.assertEqual(duplicate_no_color.status_code, 400)
        valid_multiple = self.create_variant(
            self.create_product("Multiple-price product"),
            color=self.black.id,
            price_type="multiple",
            price=None,
            stock=0,
        )
        self.assertEqual(valid_multiple.price_type, "multiple")

        invalid_admin_form = ProductVariantForm(
            {
                "product": product.id,
                "price_type": "single",
                "price": "",
                "stock": "1",
            }
        )
        self.assertFalse(invalid_admin_form.is_valid())

    def test_category_subcategory_validation_is_shared(self):
        product = Product(
            category=self.category,
            subcategory=self.other_subcategory,
            name="Invalid relationship",
            description="Should fail",
        )
        with self.assertRaises(ValidationError):
            product.full_clean()

        form = ProductAdminForm(
            {
                "category": self.category.id,
                "subcategory": self.other_subcategory.id,
                "name": "Invalid admin relationship",
                "description": "Should fail",
                "is_active": "on",
                "shipping_fee": "0.00",
                "current_viewers_count": "0",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("subcategory", form.errors)

        response = self.client.post(
            "/admin/manage/products/",
            {
                "category": self.category.id,
                "subcategory": self.other_subcategory.id,
                "name": "Invalid API relationship",
                "description": "Should fail",
                "emi_available": False,
                "emi_starting_price": "",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_unit_type_relationship_and_duplicate_labels(self):
        clothing = UnitType.objects.create(name="Test Clothing")
        band = UnitType.objects.create(name="Test Band")
        clothing_m = Unit.objects.create(unit_type=clothing, name="M")
        band_m = Unit.objects.create(unit_type=band, name="M")
        self.assertNotEqual(clothing_m.id, band_m.id)

        product = self.create_product()
        variant = self.create_variant(product, price_type="multiple", price=None, stock=0)
        invalid = self.client.post(
            "/admin/manage/product-variant-units/",
            {
                "variant": variant.id,
                "unit_type": band.id,
                "unit": clothing_m.id,
                "price": "20.00",
                "stock": 3,
            },
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)

        with self.assertRaises(ValidationError):
            ProductVariantUnit(
                variant=variant,
                unit_type=band,
                unit=clothing_m,
                price="20.00",
                stock=3,
            ).full_clean()

        valid = self.client.post(
            "/admin/manage/product-variant-units/",
            {
                "variant": variant.id,
                "unit_type": band.id,
                "unit": band_m.id,
                "sku": "TEST-BAND-M",
                "price": "20.00",
                "stock": 3,
            },
            format="json",
        )
        self.assertEqual(valid.status_code, 201, valid.data)

    def test_images_have_one_primary_and_stable_order(self):
        product = self.create_product()
        variant = self.create_variant(product, color=self.black.id)

        first = self.client.post(
            "/admin/manage/product-images/",
            {
                "variant": variant.id,
                "image": self.image_file("first.jpg", (1, 1, 1)),
                "position": 5,
                "is_primary": False,
            },
            format="multipart",
        )
        self.assertEqual(first.status_code, 201, first.data)

        second = self.client.post(
            "/admin/manage/product-images/",
            {
                "variant": variant.id,
                "image": self.image_file("second.jpg", (2, 2, 2)),
                "position": 1,
                "is_primary": False,
            },
            format="multipart",
        )
        self.assertEqual(second.status_code, 201, second.data)

        third = self.client.post(
            "/admin/manage/product-images/",
            {
                "variant": variant.id,
                "image": self.image_file("third.jpg", (3, 3, 3)),
                "position": 0,
                "is_primary": True,
            },
            format="multipart",
        )
        self.assertEqual(third.status_code, 201, third.data)
        self.assertEqual(
            ProductImage.objects.filter(variant=variant, is_primary=True).count(), 1
        )

        listed = self.client.get(
            "/admin/manage/product-images/", {"variant": variant.id}
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            [item["position"] for item in listed.data["results"]], [0, 1, 5]
        )

        white_variant = self.create_variant(
            product,
            color=self.white.id,
            price_type="multiple",
            price=None,
            stock=0,
        )
        ProductVariantUnit.objects.create(
            variant=white_variant,
            unit_type=self.storage,
            unit=self.gb,
            sku="TEST-WHITE-GB",
            price="25.00",
            stock=2,
        )
        white_image = self.client.post(
            "/admin/manage/product-images/",
            {
                "variant": white_variant.id,
                "image": self.image_file("white.jpg", (5, 5, 5)),
                "position": 0,
                "is_primary": True,
            },
            format="multipart",
        )
        self.assertEqual(white_image.status_code, 201, white_image.data)
        detail = self.client.get(f"/product/{product.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.data["variants"]), 2)
        self.assertEqual(
            {item["color"]["name"] for item in detail.data["variants"]},
            {"Test Black", "Test White"},
        )
        self.assertEqual(
            next(
                item for item in detail.data["variants"]
                if item["color"]["name"] == "Test White"
            )["sizes"][0]["sku"],
            "TEST-WHITE-GB",
        )

        orphan = self.client.post(
            "/admin/manage/product-images/",
            {
                "variant": "",
                "image": self.image_file("orphan.jpg", (4, 4, 4)),
                "is_primary": True,
            },
            format="multipart",
        )
        self.assertEqual(orphan.status_code, 400)

        response = self.client.delete(
            f"/admin/manage/product-images/{third.data['id']}/"
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            ProductImage.objects.filter(variant=variant, is_primary=True).count(), 1
        )

    def test_public_sorting_and_pagination_use_catalog_prices(self):
        low = self.create_product("Low price")
        self.create_variant(low, price="10.00", stock=1)

        middle = self.create_product("Multiple price")
        middle_variant = self.create_variant(
            middle, color=self.black.id, price_type="multiple", price=None, stock=0
        )
        ProductVariantUnit.objects.create(
            variant=middle_variant,
            unit_type=self.storage,
            unit=self.gb,
            price="20.00",
            stock=1,
        )

        high = self.create_product("High price")
        self.create_variant(high, color=self.white.id, price="30.00", stock=1)

        response = self.client.get(
            "/products/", {"sort": "price_low", "page": 1, "page_size": 2}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
        prices = [str(item["starting_price"]) for item in response.data["results"]]
        self.assertEqual(prices, ["10.00", "20.00"])
        self.assertIsNotNone(response.data["next"])

        second_page = self.client.get(
            "/products/", {"sort": "price_low", "page": 2, "page_size": 2}
        )
        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(str(second_page.data["results"][0]["starting_price"]), "30.00")

        search = self.client.get(
            "/search-products/", {"search": "Multiple", "page_size": 1}
        )
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.data["results"][0]["name"], "Multiple price")

    def test_admin_create_rolls_back_when_audit_fails(self):
        before = Product.objects.count()
        with patch(
            "myapp.super_admin_api.AdminAuditLog.objects.create",
            side_effect=RuntimeError("audit failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    "/admin/manage/products/",
                    {
                        "category": self.category.id,
                        "subcategory": self.subcategory.id,
                        "name": "Should roll back",
                        "description": "Transaction test",
                        "emi_available": False,
                    },
                    format="json",
                )
        self.assertEqual(Product.objects.count(), before)

    def test_seeded_unit_catalog_contains_reusable_types(self):
        self.assertTrue(
            Unit.objects.filter(
                unit_type__name="Clothing Size", name="M"
            ).exists()
        )
        self.assertTrue(
            Unit.objects.filter(unit_type__name="Band Size", name="M").exists()
        )
        self.assertTrue(
            Unit.objects.filter(unit_type__name="Storage Capacity", name="1TB").exists()
        )


@override_settings(SECURE_SSL_REDIRECT=False)
class HomepageDiscoveryTests(TestCase):
    def setUp(self):
        self.media_dir = TemporaryDirectory(prefix="homepage-tests-")
        self.media_override = override_settings(MEDIA_ROOT=self.media_dir.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.media_dir.cleanup)

        self.user = User.objects.create_user(
            email="homepage-user@example.invalid",
            password="HomepagePass123!",
        )
        self.category = Category.objects.create(
            name="Homepage Electronics",
            image=self.image_file("homepage-category.jpg", (20, 20, 20)),
        )
        self.subcategory = SubCategory.objects.create(
            category=self.category,
            name="Homepage Devices",
        )
        self.brand = Brand.objects.create(name="Homepage Brand")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @staticmethod
    def image_file(name, color=(30, 30, 30)):
        stream = BytesIO()
        Image.new("RGB", (24, 24), color).save(stream, format="JPEG")
        return SimpleUploadedFile(name, stream.getvalue(), content_type="image/jpeg")

    def create_product(self, name, price="100.00", stock=10, offer=None, brand=None):
        product = Product.objects.create(
            category=self.category,
            subcategory=self.subcategory,
            brand=brand,
            offer=offer,
            name=name,
            description="Homepage discovery product.",
        )
        variant = ProductVariant.objects.create(
            product=product,
            price_type="single",
            price=price,
            stock=stock,
        )
        ProductImage.objects.create(
            variant=variant,
            image=self.image_file(f"{product.id}.jpg"),
            is_primary=True,
        )
        return product, variant

    def create_paid_order_item(self, product, quantity):
        order = Order.objects.create(
            user=self.user,
            payment_status="Paid",
            status="Delivered",
            total_amount=Decimal("100.00"),
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=quantity,
            original_price=Decimal("100.00"),
            discount_amount=Decimal("0.00"),
            price=Decimal("100.00"),
            total_price=Decimal("100.00") * quantity,
        )

    def test_homepage_uses_real_ranked_sections_and_brand_shop_filter(self):
        today = timezone.localdate()
        active_offer = Offer.objects.create(
            title="Homepage active deal",
            description="An active homepage deal.",
            image=self.image_file("active-offer.jpg"),
            discount_percentage=25,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=1),
        )
        expired_offer = Offer.objects.create(
            title="Homepage expired deal",
            description="An expired homepage deal.",
            image=self.image_file("expired-offer.jpg"),
            discount_percentage=90,
            start_date=today - timedelta(days=4),
            end_date=today - timedelta(days=2),
        )
        trending, trending_variant = self.create_product(
            "Homepage trending", brand=self.brand
        )
        deal, _ = self.create_product(
            "Homepage active deal product", offer=active_offer
        )
        expired, _ = self.create_product(
            "Homepage expired deal product", offer=expired_offer
        )
        bestseller, _ = self.create_product("Homepage best seller")
        other_seller, _ = self.create_product("Homepage other seller")
        related, _ = self.create_product("Homepage related product", brand=self.brand)

        ProductView.objects.create(product=trending, user=self.user)
        Wishlist.objects.create(user=self.user, variant=trending_variant)
        self.create_paid_order_item(bestseller, 5)
        self.create_paid_order_item(other_seller, 1)

        response = self.client.get("/homepage/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(trending.id, [item["id"] for item in response.data["trending_now"]])
        self.assertEqual(
            [item["id"] for item in response.data["top_deals"]],
            [deal.id],
        )
        self.assertEqual(response.data["best_sellers"][0]["id"], bestseller.id)
        self.assertNotIn(expired.id, [item["id"] for item in response.data["top_deals"]])
        self.assertTrue(response.data["just_for_you"])
        self.assertNotIn(
            "current_viewers_count",
            response.data["trending_now"][0],
        )
        self.assertEqual(response.data["shop_by_brand"][0]["slug"], "homepage-brand")
        self.assertEqual(
            response.data["shop_by_brand"][0]["product_count"],
            2,
        )
        self.assertEqual(response.data["recently_viewed"][0]["id"], trending.id)
        for section in (
            "new_arrivals",
            "trending_now",
            "top_deals",
            "best_sellers",
            "just_for_you",
            "recently_viewed",
        ):
            self.assertLessEqual(len(response.data[section]), 16)

        shop_response = self.client.get("/products/", {"brand": self.brand.slug})
        self.assertEqual(shop_response.status_code, 200)
        self.assertEqual(
            {item["id"] for item in shop_response.data["results"]},
            {trending.id, related.id},
        )

    def test_recently_viewed_is_empty_until_a_real_view_exists(self):
        empty_client = APIClient()
        empty_response = empty_client.get("/recently-viewed/")
        self.assertEqual(empty_response.status_code, 200)
        self.assertEqual(empty_response.data, [])

        product, _ = self.create_product("Actually viewed product")
        self.client.get(f"/product/{product.id}/")
        recent_response = self.client.get("/recently-viewed/")
        self.assertEqual(recent_response.status_code, 200)
        self.assertEqual([item["id"] for item in recent_response.data], [product.id])


@override_settings(SECURE_SSL_REDIRECT=False)
class RelatedProductsTests(TestCase):
    """Contract tests for the product-detail, admin, and existing cart APIs."""

    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            email="related-customer@example.invalid",
            password="CustomerPass123!",
            role="Customer",
        )
        self.admin = User.objects.create_superuser(
            email="related-admin@example.invalid",
            password="AdminPass123!",
        )
        self.category = Category.objects.create(name="Related electronics", image="category.jpg")
        self.other_category = Category.objects.create(name="Related home", image="home.jpg")
        self.subcategory = SubCategory.objects.create(
            category=self.category, name="Related mobiles"
        )
        self.other_subcategory = SubCategory.objects.create(
            category=self.category, name="Related accessories"
        )
        self.home_subcategory = SubCategory.objects.create(
            category=self.other_category, name="Related appliances"
        )
        self.main, self.main_variant = self.make_product("Related phone")
        self.charger, self.charger_variant = self.make_product("Related charger")
        self.case, self.case_variant = self.make_product(
            "Related case", variants=2
        )
        self.out_of_stock, self.out_of_stock_variant = self.make_product(
            "Related unavailable", stock=0
        )
        self.unrelated, self.unrelated_variant = self.make_product(
            "Related refrigerator",
            category=self.other_category,
            subcategory=self.home_subcategory,
        )
        self.client.force_authenticate(user=self.customer)

    def make_product(self, name, *, category=None, subcategory=None, stock=5, variants=1):
        product = Product.objects.create(
            category=category or self.category,
            subcategory=subcategory or self.subcategory,
            name=name,
            description=f"{name} description",
        )
        first_variant = None
        for index in range(variants):
            color = Color.objects.create(
                name=f"{name} color {index}", code=f"#{index + 11:06d}"
            ) if variants > 1 else None
            variant = ProductVariant.objects.create(
                product=product,
                color=color,
                price_type="single",
                price=Decimal("100.00") + index,
                stock=stock,
            )
            first_variant = first_variant or variant
        return product, first_variant

    def configure_manual(self, *products):
        self.main.related_product_mode = Product.RELATED_PRODUCT_MODE_MANUAL
        self.main.save(update_fields=("related_product_mode",))
        ProductRelatedProduct.objects.bulk_create(
            [
                ProductRelatedProduct(
                    product=self.main, related_product=product, position=position
                )
                for position, product in enumerate(products)
            ]
        )

    def add_main(self):
        return self.client.post(
            "/cart/add/", {"variant": self.main_variant.id, "quantity": 1}, format="json"
        )

    def test_none_mode_has_no_prompt_or_detail_recommendations(self):
        response = self.add_main()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["related_products"], [])
        detail = self.client.get(f"/product/{self.main.id}/")
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data["related_products"], [])

    def test_manual_mode_detail_preserves_order_and_filters_unavailable_targets(self):
        self.configure_manual(self.charger, self.out_of_stock, self.case)
        detail = self.client.get(f"/product/{self.main.id}/")
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(
            [item["id"] for item in detail.data["related_products"]],
            [self.charger.id, self.case.id],
        )
        self.assertLessEqual(len(detail.data["related_products"]), 4)
        self.assertNotIn(self.main.id, [item["id"] for item in detail.data["related_products"]])

    def test_automatic_mode_prefers_same_subcategory_and_never_returns_broad_unrelated_items(self):
        self.main.related_product_mode = Product.RELATED_PRODUCT_MODE_AUTOMATIC
        self.main.save(update_fields=("related_product_mode",))
        response = self.add_main()
        self.assertEqual(response.status_code, 200, response.data)
        ids = [item["id"] for item in response.data["related_products"]]
        self.assertIn(self.charger.id, ids)
        self.assertNotIn(self.main.id, ids)
        self.assertNotIn(self.unrelated.id, ids)
        self.assertLessEqual(len(ids), 4)

    def test_related_cart_confirmation_adds_only_selected_authorized_products(self):
        self.configure_manual(self.charger, self.case)
        first = self.add_main()
        self.assertEqual(first.status_code, 200, first.data)
        selected = self.client.post(
            "/cart/add/",
            {
                "source_product": self.main.id,
                "related_products": [{"product": self.charger.id}],
            },
            format="json",
        )
        self.assertEqual(selected.status_code, 200, selected.data)
        self.assertEqual(selected.data["related_products_added"], [self.charger.id])
        self.assertEqual(
            set(Cart.objects.filter(user=self.customer).values_list("variant__product_id", flat=True)),
            {self.main.id, self.charger.id},
        )

    def test_cart_rejects_injected_unrelated_product(self):
        self.configure_manual(self.charger)
        self.assertEqual(self.add_main().status_code, 200)
        response = self.client.post(
            "/cart/add/",
            {
                "source_product": self.main.id,
                "related_products": [{"product": self.unrelated.id, "variant": self.unrelated_variant.id}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["error_code"], "RELATED_PRODUCT_NOT_ALLOWED")
        self.assertFalse(Cart.objects.filter(user=self.customer, variant=self.unrelated_variant).exists())

    def test_related_product_requires_explicit_choice_for_multiple_variants(self):
        self.configure_manual(self.case)
        self.assertEqual(self.add_main().status_code, 200)
        missing_variant = self.client.post(
            "/cart/add/",
            {"source_product": self.main.id, "related_products": [{"product": self.case.id}]},
            format="json",
        )
        self.assertEqual(missing_variant.status_code, 400, missing_variant.data)
        self.assertEqual(missing_variant.data["error_code"], "RELATED_VARIANT_REQUIRED")
        selected = self.client.post(
            "/cart/add/",
            {
                "source_product": self.main.id,
                "related_products": [{"product": self.case.id, "variant": self.case_variant.id}],
            },
            format="json",
        )
        self.assertEqual(selected.status_code, 200, selected.data)
        self.assertTrue(Cart.objects.filter(user=self.customer, variant=self.case_variant).exists())

    def test_selected_product_that_sells_out_is_skipped_without_blocking_the_main_item(self):
        self.configure_manual(self.charger)
        first = self.add_main()
        self.assertEqual(first.status_code, 200, first.data)
        self.charger_variant.stock = 0
        self.charger_variant.save(update_fields=("stock",))
        selected = self.client.post(
            "/cart/add/",
            {"source_product": self.main.id, "related_products": [{"product": self.charger.id}]},
            format="json",
        )
        self.assertEqual(selected.status_code, 200, selected.data)
        self.assertIn("no longer available", selected.data["message"])
        self.assertTrue(Cart.objects.filter(user=self.customer, variant=self.main_variant).exists())
        self.assertFalse(Cart.objects.filter(user=self.customer, variant=self.charger_variant).exists())

    def test_admin_api_enforces_manual_limit_self_reference_and_mode_switches(self):
        self.client.force_authenticate(user=self.admin)
        too_many = self.client.patch(
            f"/admin/manage/products/{self.main.id}/",
            {
                "related_product_mode": "manual",
                "related_product_ids": [
                    self.charger.id,
                    self.case.id,
                    self.out_of_stock.id,
                    self.unrelated.id,
                    self.main.id,
                ],
            },
            format="json",
        )
        self.assertEqual(too_many.status_code, 400, too_many.data)
        self.assertIn("related_product_ids", too_many.data)

        updated = self.client.patch(
            f"/admin/manage/products/{self.main.id}/",
            {
                "related_product_mode": "manual",
                "related_product_ids": [self.case.id, self.charger.id],
            },
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(
            [item["id"] for item in updated.data["manual_related_products"]],
            [self.case.id, self.charger.id],
        )
        disabled = self.client.patch(
            f"/admin/manage/products/{self.main.id}/",
            {"related_product_mode": "none"},
            format="json",
        )
        self.assertEqual(disabled.status_code, 200, disabled.data)
        self.assertFalse(ProductRelatedProduct.objects.filter(product=self.main).exists())


@override_settings(SECURE_SSL_REDIRECT=False)
class WelcomeBonusFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            email="welcome-customer@example.invalid",
            password="WelcomePass123!",
            role="Customer",
        )
        self.other_customer = User.objects.create_user(
            email="other-welcome-customer@example.invalid",
            password="WelcomePass123!",
            role="Customer",
        )
        self.admin = User.objects.create_superuser(
            email="welcome-admin@example.invalid",
            password="WelcomeAdminPass123!",
        )
        self.category = Category.objects.create(name="Welcome footwear", image="footwear.jpg")
        self.other_category = Category.objects.create(name="Welcome electronics", image="electronics.jpg")
        self.subcategory = SubCategory.objects.create(
            category=self.category, name="Welcome shoes"
        )
        self.other_subcategory = SubCategory.objects.create(
            category=self.other_category, name="Welcome phones"
        )
        self.product = Product.objects.create(
            category=self.category,
            subcategory=self.subcategory,
            name="Welcome shoe",
            description="Eligible welcome-bonus product.",
        )
        self.other_product = Product.objects.create(
            category=self.other_category,
            subcategory=self.other_subcategory,
            name="Welcome phone",
            description="Ineligible welcome-bonus product.",
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, price_type="single", price=Decimal("100.00"), stock=5
        )
        self.other_variant = ProductVariant.objects.create(
            product=self.other_product, price_type="single", price=Decimal("100.00"), stock=5
        )
        now = timezone.now()
        self.bonus = WelcomeBonus.objects.create(
            name="Welcome 10",
            applicability_type=WelcomeBonus.APPLICABILITY_PRODUCT,
            discount_type=WelcomeBonus.DISCOUNT_PERCENTAGE,
            discount_percentage=Decimal("10.00"),
            start_date=now - timedelta(minutes=1),
            end_date=now + timedelta(days=1),
            is_active=True,
        )
        self.bonus.products.add(self.product)
        self.assignment = WelcomeBonusAssignment.objects.get(
            welcome_bonus=self.bonus, user=self.customer
        )
        self.other_assignment = WelcomeBonusAssignment.objects.get(
            welcome_bonus=self.bonus, user=self.other_customer
        )
        self.notification = WelcomeBonusNotification.objects.get(assignment=self.assignment)
        self.client.force_authenticate(user=self.customer)

    def claim_and_copy(self):
        claimed = self.client.post(
            f"/welcome-bonus-notifications/{self.notification.id}/claim/", format="json"
        )
        self.assertEqual(claimed.status_code, 200, claimed.data)
        self.assertNotIn("code", claimed.data)
        copied = self.client.post(
            f"/welcome-bonus-notifications/{self.notification.id}/copy-code/", format="json"
        )
        self.assertEqual(copied.status_code, 200, copied.data)
        self.assertEqual(copied["Cache-Control"], "no-store, private")
        return copied.data["code"]

    def test_assignment_notification_is_masked_and_codes_are_unique(self):
        self.assertNotEqual(self.assignment.code, self.other_assignment.code)
        self.assertTrue(self.assignment.code.startswith("WB-"))
        response = self.client.get("/welcome-bonus-notifications/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["unread_count"], 1)
        payload = response.data["notifications"][0]
        self.assertEqual(payload["masked_code"], "••••••••••••••••")
        self.assertEqual(payload["eligible_target"], "Valid for: Welcome shoe")
        self.assertNotIn("code", payload)
        self.assertNotIn(self.assignment.code, str(payload))

    def test_claim_and_copy_keep_code_hidden_until_clipboard_endpoint(self):
        blocked = self.client.post(
            f"/welcome-bonus-notifications/{self.notification.id}/copy-code/", format="json"
        )
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(blocked.data["error_code"], "WELCOME_BONUS_NOT_CLAIMED")
        code = self.claim_and_copy()
        self.assertEqual(code, self.assignment.code)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, WelcomeBonusAssignment.STATUS_CLAIMED)

    def test_existing_coupon_endpoint_resolves_user_bonus_by_database_ownership(self):
        code = self.claim_and_copy()
        applied = self.client.post(
            "/validate-coupon/",
            {"code": code, "product_id": self.product.id},
            format="json",
        )
        self.assertEqual(applied.status_code, 200, applied.data)
        self.assertEqual(applied.data["promotion_type"], "WELCOME_BONUS")
        self.assertNotIn("code", applied.data)

        added = self.client.post(
            "/cart/add/", {"variant": self.variant.id, "quantity": 1}, format="json"
        )
        self.assertEqual(added.status_code, 200, added.data)
        cart = Cart.objects.get(user=self.customer, variant=self.variant)
        self.assertEqual(cart.welcome_bonus_assignment_id, self.assignment.id)
        self.assertIsNone(cart.coupon_id)
        self.assertEqual(self.client.get("/cart/").data["items"][0]["coupon_code"], None)

    def test_code_is_user_specific_and_product_eligibility_is_enforced(self):
        self.client.force_authenticate(user=self.other_customer)
        ownership = self.client.post(
            "/validate-coupon/",
            {"code": self.assignment.code, "product_id": self.product.id},
            format="json",
        )
        self.assertEqual(ownership.status_code, 403, ownership.data)
        self.assertEqual(ownership.data["error_code"], "WELCOME_BONUS_NOT_ASSIGNED_TO_USER")

        self.client.force_authenticate(user=self.customer)
        code = self.claim_and_copy()
        ineligible = self.client.post(
            "/validate-coupon/",
            {"code": code, "product_id": self.other_product.id},
            format="json",
        )
        self.assertEqual(ineligible.status_code, 400, ineligible.data)
        self.assertEqual(ineligible.data["error_code"], "WELCOME_BONUS_NOT_APPLICABLE")

    def test_direct_order_endpoint_cannot_redeem_bonus_or_consume_stock(self):
        code = self.claim_and_copy()
        self.assertEqual(
            self.client.post(
                "/validate-coupon/",
                {"code": code, "product_id": self.product.id},
                format="json",
            ).status_code,
            200,
        )
        self.client.post("/cart/add/", {"variant": self.variant.id, "quantity": 1}, format="json")
        address = Address.objects.create(
            user=self.customer,
            full_name="Welcome Customer",
            phone="123456789",
            address_line="1 Welcome Way",
            city="Auckland",
            postal_code="1010",
        )
        ordered = self.client.post("/place-order/", {"address": address.id}, format="json")
        self.assertEqual(ordered.status_code, 410, ordered.data)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, WelcomeBonusAssignment.STATUS_CLAIMED)
        self.assertFalse(WelcomeBonusRedemption.objects.filter(assignment=self.assignment).exists())

        # The disabled endpoint must leave the original cart untouched; clear
        # it before setting up the independent inactive-campaign scenario.
        Cart.objects.filter(user=self.customer).delete()

        # A fresh assignment is detached from cart when the campaign is
        # deactivated, proving totals are revalidated server-side.
        follow_up = WelcomeBonus.objects.create(
            name="Inactive check",
            applicability_type=WelcomeBonus.APPLICABILITY_PRODUCT,
            discount_type=WelcomeBonus.DISCOUNT_FIXED,
            fixed_amount=Decimal("5.00"),
            start_date=timezone.now() - timedelta(minutes=1),
            end_date=timezone.now() + timedelta(days=1),
        )
        follow_up.products.add(self.product)
        follow_assignment = WelcomeBonusAssignment.objects.get(
            welcome_bonus=follow_up, user=self.customer
        )
        follow_assignment.status = WelcomeBonusAssignment.STATUS_CLAIMED
        follow_assignment.claimed_at = timezone.now()
        follow_assignment.save()
        Cart.objects.create(
            user=self.customer,
            variant=self.variant,
            quantity=1,
            welcome_bonus_assignment=follow_assignment,
        )
        follow_up.is_active = False
        follow_up.save(update_fields=("is_active",))
        self.client.get("/cart/")
        self.assertIsNone(Cart.objects.get(user=self.customer, variant=self.variant).welcome_bonus_assignment_id)

    def test_category_bonus_applies_to_category_but_not_unrelated_products(self):
        category_bonus = WelcomeBonus.objects.create(
            name="Footwear welcome bonus",
            applicability_type=WelcomeBonus.APPLICABILITY_CATEGORY,
            category=self.category,
            discount_type=WelcomeBonus.DISCOUNT_FIXED,
            fixed_amount=Decimal("20.00"),
            start_date=timezone.now() - timedelta(minutes=1),
            end_date=timezone.now() + timedelta(days=1),
        )
        category_assignment = WelcomeBonusAssignment.objects.get(
            welcome_bonus=category_bonus, user=self.customer
        )
        notification = WelcomeBonusNotification.objects.get(assignment=category_assignment)
        self.assertEqual(
            self.client.post(
                f"/welcome-bonus-notifications/{notification.id}/claim/", format="json"
            ).status_code,
            200,
        )
        code = self.client.post(
            f"/welcome-bonus-notifications/{notification.id}/copy-code/", format="json"
        ).data["code"]
        self.assertEqual(
            self.client.post(
                "/validate-coupon/",
                {"code": code, "product_id": self.product.id},
                format="json",
            ).status_code,
            200,
        )
        rejected = self.client.post(
            "/validate-coupon/",
            {"code": code, "product_id": self.other_product.id},
            format="json",
        )
        self.assertEqual(rejected.status_code, 400, rejected.data)
        self.assertEqual(rejected.data["error_code"], "WELCOME_BONUS_NOT_APPLICABLE")

    def test_admin_api_is_separate_and_protected(self):
        self.client.force_authenticate(user=self.customer)
        self.assertEqual(self.client.get("/admin/manage/welcome-bonuses/").status_code, 403)
        self.client.force_authenticate(user=self.admin)
        listed = self.client.get("/admin/manage/welcome-bonuses/")
        self.assertEqual(listed.status_code, 200, listed.data)
        self.assertEqual(listed.data["results"][0]["assigned_user_count"], 2)
        toggled = self.client.post(
            f"/admin/manage/welcome-bonuses/{self.bonus.id}/toggle-active/", format="json"
        )
        self.assertEqual(toggled.status_code, 200, toggled.data)
        self.assertFalse(toggled.data["is_active"])

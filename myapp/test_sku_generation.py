from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Category, Product, ProductVariant, ProductVariantUnit, SubCategory, Unit, UnitType, User


@override_settings(SECURE_SSL_REDIRECT=False)
class SkuGenerationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="sku-admin@example.invalid",
            password="SkuAdminPass123!",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        category = Category.objects.create(name="SKU Category")
        subcategory = SubCategory.objects.create(category=category, name="SKU Subcategory")
        self.product = Product.objects.create(
            category=category,
            subcategory=subcategory,
            name="SKU Product",
            description="Product used by SKU generation tests.",
        )
        unit_type = UnitType.objects.create(name="SKU Size")
        self.unit = Unit.objects.create(unit_type=unit_type, name="M")
        self.unit_type = unit_type

    def variant_payload(self, **overrides):
        return {
            "product": self.product.id,
            "price_type": "single",
            "price": "20.00",
            "stock": 3,
            **overrides,
        }

    def test_variant_sku_is_optional_and_can_be_generated(self):
        response = self.client.post(
            "/admin/manage/product-variants/",
            self.variant_payload(generate_sku=True),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        variant = ProductVariant.objects.get(pk=response.data["id"])
        self.assertEqual(variant.sku, f"EHK-V-{variant.pk:06d}")

    def test_manual_variant_sku_is_preserved_without_generation(self):
        response = self.client.post(
            "/admin/manage/product-variants/",
            self.variant_payload(sku="MANUAL-SKU-001"),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["sku"], "MANUAL-SKU-001")

    def test_variant_unit_sku_can_be_generated(self):
        variant_response = self.client.post(
            "/admin/manage/product-variants/",
            self.variant_payload(price_type="multiple", price=None),
            format="json",
        )
        self.assertEqual(variant_response.status_code, 201, variant_response.data)

        response = self.client.post(
            "/admin/manage/product-variant-units/",
            {
                "variant": variant_response.data["id"],
                "unit_type": self.unit_type.id,
                "unit": self.unit.id,
                "price": "20.00",
                "stock": 2,
                "generate_sku": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        unit = ProductVariantUnit.objects.get(pk=response.data["id"])
        self.assertEqual(unit.sku, f"EHK-U-{unit.pk:06d}")

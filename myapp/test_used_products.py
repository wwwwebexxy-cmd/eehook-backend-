from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from .models import Cart, Category, Color, Product, ProductVariant, SubCategory, User
from .serializers import ProductSerializer
from .utils import get_product_prices


class UsedProductVariantApiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="used-product-admin@example.invalid",
            password="UsedProductPass123!",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.category = Category.objects.create(name="Used Mobiles")
        self.used_iphones = SubCategory.objects.create(
            category=self.category,
            name="Used iPhones",
        )
        self.iphone_14 = SubCategory.objects.create(
            category=self.category,
            name="iPhone 14 Series",
        )
        self.black = Color.objects.create(name="Used Black", code="#111111")

    def test_used_product_accepts_optional_multiple_subcategories(self):
        response = self.client.post(
            "/admin/manage/products/",
            {
                "category": self.category.id,
                "subcategory_ids": [self.used_iphones.id, self.iphone_14.id],
                "product_type": "used",
                "name": "Used iPhone 14 Pro",
                "description": "Test used phone",
                "shipping_fee": "0",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        product = Product.objects.get(pk=response.data["id"])
        self.assertEqual(product.product_type, Product.PRODUCT_TYPE_USED)
        self.assertEqual(product.subcategory_id, self.used_iphones.id)
        self.assertEqual(
            set(product.subcategories.values_list("id", flat=True)),
            {self.used_iphones.id, self.iphone_14.id},
        )

    def test_variant_option_combinations_have_independent_prices(self):
        product = Product.objects.create(
            category=self.category,
            subcategory=self.used_iphones,
            product_type=Product.PRODUCT_TYPE_USED,
            name="Used iPhone 14 Pro",
            description="Test used phone",
        )
        first = self.client.post(
            "/admin/manage/product-variants/",
            {
                "product": product.id,
                "color": self.black.id,
                "option_values": {"storage": "128 GB", "grade": "A+"},
                "price_type": "single",
                "price": "1200",
                "offer_price": "1100",
                "stock": 1,
            },
            format="json",
        )
        second = self.client.post(
            "/admin/manage/product-variants/",
            {
                "product": product.id,
                "color": self.black.id,
                "option_values": {"storage": "256 GB", "grade": "A"},
                "price_type": "single",
                "price": "1450",
                "stock": 2,
            },
            format="json",
        )

        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 201, second.data)
        self.assertNotEqual(first.data["id"], second.data["id"])
        self.assertEqual(Decimal(str(first.data["offer_price"])), Decimal("1100.00"))
        self.assertEqual(Decimal(str(first.data["discounted_price"])), Decimal("1100.00"))

        duplicate = self.client.post(
            "/admin/manage/product-variants/",
            {
                "product": product.id,
                "color": self.black.id,
                "option_values": {"grade": "A+", "storage": "128 GB"},
                "price_type": "single",
                "price": "1210",
                "stock": 1,
            },
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400, duplicate.data)

        product.refresh_from_db()
        payload = ProductSerializer(product).data
        self.assertEqual(payload["product_type"], "used")
        self.assertEqual(
            {item["option_values"]["storage"] for item in payload["variants"]},
            {"128 GB", "256 GB"},
        )
        self.assertEqual(get_product_prices(product)["discounted_price"], Decimal("1100.00"))

        Cart.objects.create(user=self.admin, variant=ProductVariant.objects.get(pk=first.data["id"]))
        cart_response = self.client.get("/cart/")
        self.assertEqual(cart_response.status_code, 200, cart_response.data)
        self.assertEqual(Decimal(str(cart_response.data["subtotal"])), Decimal("1100.00"))
        self.assertEqual(
            Decimal(str(cart_response.data["items"][0]["discounted_price"])),
            Decimal("1100.00"),
        )

from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.test import RequestFactory, TestCase
from PIL import Image

from .models import Category, Offer, Product, ProductVariant, SubCategory
from .serializers import OfferSerializer
from .utils import calculate_discount_amount, calculate_offer_price, get_offer_for_product, get_product_prices
from .views import offer_products


class OfferDiscountTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Offer test category", image="categories/test.jpg")
        self.subcategory = SubCategory.objects.create(category=self.category, name="Offer test subcategory")
        self.product = Product.objects.create(
            category=self.category,
            subcategory=self.subcategory,
            name="Offer test product",
            description="Offer test product description",
        )
        self.variant_one = ProductVariant.objects.create(
            product=self.product,
            price_type="single",
            price=Decimal("100.00"),
            stock=10,
        )
        self.variant_two = ProductVariant.objects.create(
            product=self.product,
            price_type="single",
            price=Decimal("200.00"),
            stock=10,
        )

    def offer(self, **overrides):
        values = {
            "title": "Test offer",
            "description": "Test offer description",
            "image": SimpleUploadedFile("offer.jpg", b"image", content_type="image/jpeg"),
            "discount_type": Offer.DISCOUNT_PERCENTAGE,
            "discount_percentage": Decimal("10.00"),
            "start_date": date.today() - timedelta(days=1),
            "end_date": date.today() + timedelta(days=1),
        }
        values.update(overrides)
        return Offer.objects.create(**values)

    def test_fixed_amount_offer_reduces_price_and_exposes_fixed_value(self):
        offer = self.offer(
            discount_type=Offer.DISCOUNT_FIXED,
            discount_percentage=None,
            fixed_amount=Decimal("25.00"),
        )

        self.assertEqual(calculate_discount_amount(Decimal("100.00"), offer), Decimal("25.00"))
        self.assertEqual(calculate_offer_price(Decimal("100.00"), offer), Decimal("75.00"))
        self.assertEqual(offer.fixed_amount, Decimal("25.00"))

    def test_only_selected_discount_value_is_valid(self):
        with self.assertRaises(ValidationError):
            self.offer(
                discount_type=Offer.DISCOUNT_PERCENTAGE,
                discount_percentage=None,
                fixed_amount=None,
            )

        with self.assertRaises(ValidationError):
            self.offer(
                discount_type=Offer.DISCOUNT_FIXED,
                discount_percentage=Decimal("10.00"),
                fixed_amount=None,
            )

    def test_offer_without_variants_applies_to_every_variant(self):
        offer = self.offer()
        offer.products.add(self.product)

        self.assertEqual(get_offer_for_product(self.product, self.variant_one), offer)
        self.assertEqual(get_offer_for_product(self.product, self.variant_two), offer)
        self.assertEqual(get_product_prices(self.product)["discounted_price"], Decimal("90.00"))

    def test_offer_with_selected_variants_does_not_discount_other_variants(self):
        offer = self.offer()
        offer.products.add(self.product)
        offer.variants.add(self.variant_one)

        self.assertEqual(get_offer_for_product(self.product, self.variant_one), offer)
        self.assertIsNone(get_offer_for_product(self.product, self.variant_two))
        self.assertEqual(calculate_offer_price(self.variant_two.price, get_offer_for_product(self.product, self.variant_two)), Decimal("200.00"))

    def test_offer_serializer_saves_product_and_variant_targets(self):
        image_stream = BytesIO()
        Image.new("RGB", (8, 8), (20, 120, 80)).save(image_stream, format="JPEG")
        payload = {
            "title": "Targeted offer",
            "description": "Only one variant is discounted.",
            "image": SimpleUploadedFile("targeted-offer.jpg", image_stream.getvalue(), content_type="image/jpeg"),
            "discount_type": Offer.DISCOUNT_PERCENTAGE,
            "discount_percentage": "15",
            "start_date": date.today() - timedelta(days=1),
            "end_date": date.today() + timedelta(days=1),
            "products": [self.product.id],
            "variants": [self.variant_two.id],
        }
        serializer = OfferSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        offer = serializer.save()
        self.assertEqual(list(offer.products.values_list("id", flat=True)), [self.product.id])
        self.assertEqual(list(offer.variants.values_list("id", flat=True)), [self.variant_two.id])

    def test_offer_serializer_accepts_json_relations_from_multipart_form(self):
        image_stream = BytesIO()
        Image.new("RGB", (8, 8), (20, 120, 80)).save(image_stream, format="JPEG")
        payload = QueryDict(mutable=True)
        payload.update({
            "title": "Multipart offer",
            "description": "All variants are discounted.",
            "image": SimpleUploadedFile("multipart-offer.jpg", image_stream.getvalue(), content_type="image/jpeg"),
            "discount_type": Offer.DISCOUNT_PERCENTAGE,
            "discount_percentage": "15",
            "start_date": str(date.today() - timedelta(days=1)),
            "end_date": str(date.today() + timedelta(days=1)),
            "products": "[%s]" % self.product.id,
            "variants": "[]",
        })
        serializer = OfferSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        offer = serializer.save()
        self.assertEqual(list(offer.products.values_list("id", flat=True)), [self.product.id])
        self.assertFalse(offer.variants.exists())

    def test_offer_products_returns_products_from_all_active_offers_with_all_variants(self):
        second_product = Product.objects.create(
            category=self.category,
            subcategory=self.subcategory,
            name="Second offer product",
            description="Second offer product description",
        )
        second_variant = ProductVariant.objects.create(
            product=second_product,
            price_type="single",
            price=Decimal("300.00"),
            stock=10,
        )

        first_offer = self.offer(title="First active offer")
        first_offer.products.add(self.product)
        second_offer = self.offer(title="Second active offer")
        second_offer.products.add(second_product)

        response = offer_products(RequestFactory().get("/offer-products/"))

        self.assertEqual(response.status_code, 200)
        products = response.data["products"]
        product_ids = {item["id"] for item in products}
        self.assertEqual(product_ids, {self.product.id, second_product.id})

        variants_by_product = {
            item["id"]: {variant["id"] for variant in item["variants"]}
            for item in products
        }
        self.assertEqual(
            variants_by_product[self.product.id],
            {self.variant_one.id, self.variant_two.id},
        )
        self.assertEqual(variants_by_product[second_product.id], {second_variant.id})

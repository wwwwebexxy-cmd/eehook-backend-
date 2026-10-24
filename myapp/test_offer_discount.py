from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .models import Offer
from .utils import calculate_discount_amount, calculate_offer_price


class OfferDiscountTests(TestCase):
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

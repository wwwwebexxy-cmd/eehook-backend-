from decimal import Decimal

from django.utils import timezone

from .catalog_pricing import get_product_price_values


def coupon_applies_to_product(coupon, product):
    """Return whether a coupon may be used for a particular product.

    Product coupons retain the legacy behavior where an empty product
    relation means all products. New dashboard-created product coupons are
    validated to have at least one product by the coupon serializer.
    """
    if not coupon or not product:
        return False

    if coupon.applicability_type == "CATEGORY":
        return bool(coupon.category_id and coupon.category_id == product.category_id)

    products = coupon.products.all()
    return not products.exists() or products.filter(pk=product.pk).exists()


def get_latest_coupon(coupon):
    """Reload a coupon so pricing never uses a stale ORM instance."""
    if not coupon:
        return None

    coupon_id = getattr(coupon, "pk", coupon)
    if not coupon_id:
        return None

    from .models import Coupon

    return (
        Coupon.objects
        .prefetch_related("products")
        .filter(pk=coupon_id)
        .first()
    )


def get_eligible_coupon(coupon, product):
    """Return the current eligible coupon, or None when it is unusable."""
    latest = get_latest_coupon(coupon)
    if latest and latest.is_valid and coupon_applies_to_product(latest, product):
        return latest
    return None


def is_coupon_valid_for_product(coupon, product):
    return bool(get_eligible_coupon(coupon, product))


def calculate_coupon_discount_amount(price, coupon):
    """Calculate a bounded, currency-rounded coupon discount for a price."""
    price = max(Decimal(str(price)), Decimal("0.00"))
    if not coupon:
        return Decimal("0.00")

    if coupon.discount_type == "FIXED":
        requested = coupon.fixed_amount or Decimal("0.00")
    else:
        requested = price * (coupon.discount_percentage or Decimal("0.00")) / Decimal("100")

    return min(max(requested, Decimal("0.00")), price).quantize(Decimal("0.01"))


def calculate_coupon_price(price, coupon):
    """Return price after a coupon, never below zero."""
    price = max(Decimal(str(price)), Decimal("0.00"))
    discount = calculate_coupon_discount_amount(price, coupon)
    return (price - discount).quantize(Decimal("0.01"))


def calculate_discounted_unit_price(price, offer=None, coupon=None, product=None):
    """Apply the existing offer and then an eligible coupon to one unit."""
    price = Decimal(str(price or 0))
    discounted = calculate_offer_price(price, offer)
    eligible_coupon = get_eligible_coupon(coupon, product) if product else get_latest_coupon(coupon)
    if eligible_coupon:
        discounted = calculate_coupon_price(discounted, eligible_coupon)
    return max(discounted, Decimal("0.00")).quantize(Decimal("0.01"))


def is_offer_valid(offer):

    if not offer:
        return False

    today = timezone.now().date()

    return (
        offer.is_active and
        offer.start_date <= today <= offer.end_date
    )


def calculate_offer_price(price, offer):

    price = Decimal(str(price))

    if not is_offer_valid(offer):
        return price

    discount = (
        price *
        Decimal(str(offer.discount_percentage))
        / Decimal("100")
    )

    discounted_price = price - discount

    return discounted_price.quantize(
        Decimal("0.01")
    )


def calculate_discount_amount(price, offer):

    price = Decimal(str(price))

    discounted_price = calculate_offer_price(
        price,
        offer
    )

    discount = price - discounted_price

    return discount.quantize(
        Decimal("0.01")
    )


def calculate_shipping(subtotal):

    subtotal = Decimal(str(subtotal))
    
    if subtotal <= Decimal("0"):
        return Decimal("0")

    shipping_rules = [
        (
            Decimal("50"),
            Decimal("5")
        ),
        (
            Decimal("100"),
            Decimal("10")
        ),
    ]

    for minimum_amount, shipping_charge in shipping_rules:

        if subtotal < minimum_amount:
            return shipping_charge

    return Decimal("15")


def calculate_order_total(subtotal):

    subtotal = Decimal(str(subtotal))

    shipping_charge = calculate_shipping(
        subtotal
    )

    total = subtotal + shipping_charge

    return {
        "subtotal": subtotal.quantize(
            Decimal("0.01")
        ),
        "shipping": shipping_charge.quantize(
            Decimal("0.01")
        ),
        "total": total.quantize(
            Decimal("0.01")
        ),
    }
    
def get_product_prices(product):

    prices = get_product_price_values(product)

    if not prices:

        zero = Decimal("0.00")

        return {
            "starting_price": zero,
            "discounted_price": zero,
            "discount_amount": zero,
            "has_offer": False,
            "discount_percentage": 0,
        }

    starting_price = min(prices)

    discounted_price = calculate_offer_price(
        starting_price,
        product.offer
    )

    discount_amount = calculate_discount_amount(
        starting_price,
        product.offer
    )

    has_offer = is_offer_valid(
        product.offer
    )

    discount_percentage = 0

    if has_offer:

        discount_percentage = (
            product.offer.discount_percentage
        )

    return {
        "starting_price": starting_price.quantize(
            Decimal("0.01")
        ),
        "discounted_price": discounted_price.quantize(
            Decimal("0.01")
        ),
        "discount_amount": discount_amount.quantize(
            Decimal("0.01")
        ),
        "has_offer": has_offer,
        "discount_percentage": discount_percentage,
    }
from rest_framework.throttling import SimpleRateThrottle


class AuthRateThrottle(SimpleRateThrottle):
    scope = "auth"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class PaymentRateThrottle(SimpleRateThrottle):
    scope = "payment"

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        ident = str(user.pk) if user and user.is_authenticated else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class SearchRateThrottle(SimpleRateThrottle):
    scope = "search"

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        ident = str(user.pk) if user and user.is_authenticated else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}

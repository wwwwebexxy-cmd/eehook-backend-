from decimal import Decimal

from django.utils import timezone

def get_offer_for_product(product, variant=None):
    """Return the active dashboard offer applicable to a product/variant.

    New offers are linked through Offer.products and optionally
    Offer.variants. An empty variant relation means all variants. The old
    Product.offer relation remains a fallback for existing integrations and
    legacy records.
    """
    if not product:
        return None

    from .models import Offer

    product_id = getattr(product, "pk", product)
    today = timezone.now().date()
    product_offers = Offer.objects.filter(products__pk=product_id)

    if variant is not None:
        variant_id = getattr(variant, "pk", variant)
        selected_offer = (
            product_offers
            .filter(variants__pk=variant_id)
            .filter(is_active=True, start_date__lte=today, end_date__gte=today)
            .order_by("-created_at", "-pk")
            .first()
        )
        if selected_offer:
            return selected_offer

    all_variants_offer = (
        product_offers
        .filter(variants__isnull=True)
        .filter(is_active=True, start_date__lte=today, end_date__gte=today)
        .order_by("-created_at", "-pk")
        .first()
    )
    if all_variants_offer:
        return all_variants_offer

    # If this product already has new dashboard offers, do not let a stale
    # legacy Product.offer leak onto a variant excluded from those offers.
    if product_offers.exists():
        return None

    legacy_offer = getattr(product, "offer", None)
    return legacy_offer if is_offer_valid(legacy_offer) else None


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

    if getattr(offer, "discount_type", "PERCENTAGE") == "FIXED":
        discount = Decimal(str(getattr(offer, "fixed_amount", None) or 0))
    else:
        discount = (
            price *
            Decimal(str(getattr(offer, "discount_percentage", None) or 0))
            / Decimal("100")
        )

    discount = min(max(discount, Decimal("0.00")), max(price, Decimal("0.00")))

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


def get_offer_discount_percentage(price, offer):
    """Return the effective percentage for a product-card discount label."""
    price = Decimal(str(price or 0))
    if not is_offer_valid(offer) or price <= 0:
        return Decimal("0.00")
    return (calculate_discount_amount(price, offer) * Decimal("100") / price).quantize(
        Decimal("0.01")
    )


def calculate_shipping(shipping_fee=0):

    """Return only an explicitly configured shipping fee.

    Shipping must not be inferred from the cart subtotal. A product with no
    configured fee is treated as having no delivery charge.
    """
    shipping_charge = Decimal(str(shipping_fee or 0))
    return max(shipping_charge, Decimal("0.00")).quantize(Decimal("0.01"))


def calculate_cart_shipping(cart_items):

    """Add configured product shipping fees once for each cart line."""
    shipping_charge = Decimal("0.00")

    for item in cart_items:
        product = getattr(getattr(item, "variant", None), "product", None)
        fee = getattr(product, "shipping_fee", 0) or 0
        shipping_charge += max(Decimal(str(fee)), Decimal("0.00"))

    return shipping_charge.quantize(Decimal("0.01"))


def calculate_order_total(subtotal, shipping_fee=0):

    subtotal = Decimal(str(subtotal))

    shipping_charge = calculate_shipping(shipping_fee)

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

    entries = []
    for variant in product.variants.all():
        if variant.price_type == "single":
            if variant.price is not None:
                price = Decimal(str(variant.price))
                entries.append((price, get_offer_for_product(product, variant)))
            continue

        entries.extend(
            (
                Decimal(str(unit.price)),
                get_offer_for_product(product, variant),
            )
            for unit in variant.sizes.all()
            if unit.price is not None
        )

    prices = [price for price, _offer in entries]

    if not prices:

        zero = Decimal("0.00")

        return {
            "starting_price": zero,
            "original_price": zero,
            "discounted_price": zero,
            "discount_amount": zero,
            "has_offer": False,
            "discount_percentage": 0,
            "offer_discount_type": None,
            "offer_discount_value": None,
        }

    starting_price = min(prices)
    discounted_entries = [
        (price, calculate_offer_price(price, offer), offer)
        for price, offer in entries
    ]
    original_price, discounted_price, best_offer = min(
        discounted_entries,
        key=lambda entry: (entry[1], entry[0]),
    )
    discount_amount = max(original_price - discounted_price, Decimal("0.00"))
    has_offer = any(is_offer_valid(offer) for _price, offer in entries)
    discount_percentage = (
        get_offer_discount_percentage(original_price, best_offer)
        if is_offer_valid(best_offer)
        else Decimal("0.00")
    )

    return {
        "starting_price": starting_price.quantize(
            Decimal("0.01")
        ),
        "original_price": original_price.quantize(
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
        "offer_discount_type": best_offer.discount_type if is_offer_valid(best_offer) else None,
        "offer_discount_value": (
            best_offer.fixed_amount
            if is_offer_valid(best_offer) and best_offer.discount_type == "FIXED"
            else best_offer.discount_percentage
            if is_offer_valid(best_offer)
            else None
        ),
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

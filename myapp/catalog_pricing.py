"""Shared product-price calculations used by models, APIs, and admin."""

from decimal import Decimal

from .utils import calculate_effective_price, get_offer_for_product


def get_product_price_values(product):
    """Return all sellable prices for a product in a consistent way."""

    prices = []
    for variant in product.variants.all():
        if variant.price_type == "single":
            if variant.price is not None:
                prices.append(
                    calculate_effective_price(
                        variant.price,
                        get_offer_for_product(product, variant),
                        variant.offer_price,
                    )
                )
            continue

        prices.extend(
            calculate_effective_price(
                unit.price,
                get_offer_for_product(product, variant),
                unit.offer_price,
            )
            for unit in variant.sizes.all()
            if unit.price is not None
        )
    return prices


def get_product_minimum_price(product):
    prices = get_product_price_values(product)
    return min(prices) if prices else None

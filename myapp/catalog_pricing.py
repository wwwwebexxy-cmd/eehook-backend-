"""Shared product-price calculations used by models, APIs, and admin."""

from decimal import Decimal


def get_product_price_values(product):
    """Return all sellable prices for a product in a consistent way."""

    prices = []
    for variant in product.variants.all():
        if variant.price_type == "single":
            if variant.price is not None:
                prices.append(Decimal(str(variant.price)))
            continue

        prices.extend(
            Decimal(str(unit.price))
            for unit in variant.sizes.all()
            if unit.price is not None
        )
    return prices


def get_product_minimum_price(product):
    prices = get_product_price_values(product)
    return min(prices) if prices else None

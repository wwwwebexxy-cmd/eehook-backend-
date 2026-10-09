"""Authoritative related-product discovery and availability helpers.

These helpers deliberately live on the server: the browser only ever sees up
to four already-vetted choices, and cart mutations validate against the same
rules again immediately before they are written.
"""

import re

from django.db.models import Prefetch, Q

from .models import Product, ProductRelatedProduct, ProductVariant


MAX_RELATED_PRODUCTS = 4

# These words do not establish a meaningful compatibility relationship when
# matching product copy across different subcategories.
_COMMON_TERMS = {
    "and", "for", "from", "the", "with", "new", "pro", "max", "mini",
    "product", "edition", "series", "model", "pack", "piece", "pcs",
}


def _available_product_queryset():
    """Products that may be offered as related items.

    A product must be active, belong to an active catalog branch, and have at
    least one purchasable SKU.  This is used both for discovery and for the
    second server-side authorization check during cart addition.
    """
    return (
        Product.objects.filter(
            is_active=True,
            category__is_active=True,
            subcategory__is_active=True,
        )
        .filter(
            Q(
                variants__price_type="single",
                variants__price__isnull=False,
                variants__stock__gt=0,
            )
            | Q(
                variants__price_type="multiple",
                variants__sizes__price__isnull=False,
                variants__sizes__stock__gt=0,
            )
        )
        .distinct()
    )


def _related_variant_queryset():
    """Small SKU payload required by the chooser, already stock-filtered."""
    return (
        ProductVariant.objects.select_related("color", "product__offer")
        .filter(
            Q(price_type="single", price__isnull=False, stock__gt=0)
            | Q(
                price_type="multiple",
                sizes__price__isnull=False,
                sizes__stock__gt=0,
            )
        )
        .distinct()
        .prefetch_related("images", "sizes__unit__unit_type")
        .order_by("id")
    )


def _hydrate_products(product_ids):
    """Fetch a short, fully hydrated product list while preserving its order."""
    if not product_ids:
        return []
    products = (
        _available_product_queryset()
        .filter(pk__in=product_ids)
        .select_related("category", "subcategory", "brand", "offer")
        .prefetch_related(Prefetch("variants", queryset=_related_variant_queryset()))
    )
    by_id = {product.id: product for product in products}
    return [by_id[product_id] for product_id in product_ids if product_id in by_id]


def _keywords(product):
    """Extract conservative compatibility hints from merchant-authored copy."""
    text = " ".join(
        value or ""
        for value in (product.name, product.description, product.key_features)
    ).lower()
    return [
        term
        for term in dict.fromkeys(re.findall(r"[a-z0-9]{3,}", text))
        if term not in _COMMON_TERMS
    ][:12]


def is_possible_automatic_related_product(product, candidate):
    """Whether a target is a relevance candidate before stock filtering.

    Cart confirmation uses this only to distinguish a once-offered product
    that became unavailable from an injected arbitrary product ID. It never
    authorizes a cart write by itself.
    """
    if candidate.id == product.id or candidate.category_id != product.category_id:
        return False
    if candidate.subcategory_id == product.subcategory_id:
        return True
    if product.brand_id and candidate.brand_id == product.brand_id:
        return True
    return bool(set(_keywords(product)) & set(_keywords(candidate)))


def _automatic_related_ids(product):
    """Return relevant automatic recommendations in a deterministic order.

    This project has no ProductType/compatibility model.  We therefore prefer
    the existing subcategory, then same-brand catalog entries, then explicit
    compatibility cues from product copy.  We intentionally do *not* fill
    the remaining spaces with arbitrary products from a broad category.
    """
    candidates = _available_product_queryset().filter(
        category_id=product.category_id
    ).exclude(pk=product.pk)

    selected = []

    def append_ids(queryset):
        for product_id in queryset.values_list("id", flat=True):
            if product_id not in selected:
                selected.append(product_id)
            if len(selected) == MAX_RELATED_PRODUCTS:
                break

    # The selected only() columns keep this discovery query narrow. The final
    # payload is fetched separately with all required related records.
    append_ids(
        candidates.filter(subcategory_id=product.subcategory_id)
        .order_by("-created_at", "id")[:MAX_RELATED_PRODUCTS]
    )

    if len(selected) < MAX_RELATED_PRODUCTS and product.brand_id:
        append_ids(
            candidates.filter(brand_id=product.brand_id)
            .exclude(pk__in=selected)
            .order_by("-created_at", "id")[:MAX_RELATED_PRODUCTS]
        )

    if len(selected) < MAX_RELATED_PRODUCTS:
        keyword_query = Q()
        for keyword in _keywords(product):
            keyword_query |= (
                Q(name__icontains=keyword)
                | Q(description__icontains=keyword)
                | Q(key_features__icontains=keyword)
            )
        if keyword_query:
            append_ids(
                candidates.filter(keyword_query)
                .exclude(pk__in=selected)
                .order_by("-created_at", "id")[:MAX_RELATED_PRODUCTS]
            )

    return selected[:MAX_RELATED_PRODUCTS]


def get_related_product_ids(product):
    """Return the IDs currently allowed for this product's cart upsell."""
    if product.related_product_mode == Product.RELATED_PRODUCT_MODE_NONE:
        return []

    if product.related_product_mode == Product.RELATED_PRODUCT_MODE_MANUAL:
        return list(
            ProductRelatedProduct.objects.filter(product_id=product.id)
            .filter(
                related_product__is_active=True,
                related_product__category__is_active=True,
                related_product__subcategory__is_active=True,
            )
            .filter(
                Q(
                    related_product__variants__price_type="single",
                    related_product__variants__price__isnull=False,
                    related_product__variants__stock__gt=0,
                )
                | Q(
                    related_product__variants__price_type="multiple",
                    related_product__variants__sizes__price__isnull=False,
                    related_product__variants__sizes__stock__gt=0,
                )
            )
            .exclude(related_product_id=product.id)
            .order_by("position", "id")
            .values_list("related_product_id", flat=True)
            .distinct()[:MAX_RELATED_PRODUCTS]
        )

    return _automatic_related_ids(product)


def get_related_products(product):
    """Return at most four hydrated, currently valid upsell products."""
    return _hydrate_products(get_related_product_ids(product))


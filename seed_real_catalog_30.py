"""Create the first 30 catalog products with real-image-ready metadata.

The companion ``catalog_curated_images.py`` command downloads and attaches
three verified public product photographs to every created variant. This
import deliberately does not create generated or AI artwork.
"""

from __future__ import annotations

import os
from decimal import Decimal

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")
django.setup()

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils.text import slugify

from catalog_curated_images import URL_POOLS, download
from myapp.catalog_qa_50 import COLOR_CODES, PRODUCTS
from myapp.models import (
    Category,
    Color,
    Product,
    ProductVariant,
    ProductVariantUnit,
    SubCategory,
    Unit,
    UnitType,
)


CATEGORY_IMAGE_KEYS = {
    "Electronics": "smartphone",
    "Apple Products": "tablet",
    "Gaming Products": "console",
    "Smart Watches": "smartwatch",
    "Wearables": "vr",
}


def content_extension(content_type: str) -> str:
    return {"image/png": "png", "image/webp": "webp"}.get(content_type, "jpg")


def save_category_image(category_name: str, image_key: str) -> str:
    session = __import__("requests").Session()
    session.headers.update({"User-Agent": "EEHookCatalog/1.0"})
    for url in URL_POOLS[image_key]:
        try:
            result = download(session, url)
        except Exception:
            result = None
        if not result:
            continue
        content, content_type = result
        path = (
            f"categories/catalog_real_2026_10/"
            f"{slugify(category_name)}.{content_extension(content_type)}"
        )
        default_storage.delete(path)
        default_storage.save(path, ContentFile(content))
        return path
    raise RuntimeError(f"Could not download a real image for {category_name}")


def ensure_unit(name: str, type_name: str):
    unit_type, _ = UnitType.objects.get_or_create(name=type_name)
    unit, _ = Unit.objects.get_or_create(unit_type=unit_type, name=name)
    return unit_type, unit


def ensure_color(name: str):
    color, _ = Color.objects.get_or_create(
        name=name,
        defaults={"code": COLOR_CODES.get(name, "#6B7280")},
    )
    if color.code != COLOR_CODES.get(name, color.code):
        color.code = COLOR_CODES.get(name, color.code)
        color.save(update_fields=["code"])
    return color


def unit_price(base: Decimal, index: int) -> Decimal:
    multiplier = (Decimal("1.00"), Decimal("1.20"), Decimal("1.35"))[min(index, 2)]
    return (base * multiplier).quantize(Decimal("0.01"))


def create_variants(product: Product, item: dict) -> None:
    ProductVariant.objects.filter(product=product).delete()
    base_price = Decimal(item["price"])
    colors = tuple(item["colors"])
    units = tuple(item["units"])
    kind = item["kind"]

    if kind in {"plain", "colors"}:
        variant_colors = colors or (None,)
        for color_index, color_name in enumerate(variant_colors):
            color = ensure_color(color_name) if color_name else None
            ProductVariant.objects.create(
                product=product,
                color=color,
                sku=f"{item['code']}-V{color_index + 1}",
                price_type="single",
                price=base_price,
                stock=max(1, item["stock"] // len(variant_colors)),
            )
        return

    variant_colors = colors or (None,)
    for color_index, color_name in enumerate(variant_colors):
        color = ensure_color(color_name) if color_name else None
        variant = ProductVariant.objects.create(
            product=product,
            color=color,
            sku=f"{item['code']}-V{color_index + 1}",
            price_type="multiple",
            price=None,
            stock=max(1, item["stock"] // len(variant_colors)),
        )
        for unit_index, unit_name in enumerate(units):
            unit_type, unit = ensure_unit(unit_name, item["unit_type"])
            ProductVariantUnit.objects.create(
                variant=variant,
                unit_type=unit_type,
                unit=unit,
                sku=f"{item['code']}-V{color_index + 1}-U{unit_index + 1}",
                price=unit_price(base_price, unit_index),
                stock=max(1, item["stock"] // len(variant_colors) // len(units)),
            )


@transaction.atomic
def seed() -> None:
    category_images = {
        name: save_category_image(name, key)
        for name, key in CATEGORY_IMAGE_KEYS.items()
    }
    categories = {}
    subcategories = {}
    for item in PRODUCTS[:30]:
        category_name = item["category"]
        subcategory_name = item["subcategory"]
        category = categories.get(category_name)
        if category is None:
            category, _ = Category.objects.get_or_create(name=category_name)
            category.image.name = category_images[category_name]
            category.is_active = True
            category.save(update_fields=["image", "is_active"])
            categories[category_name] = category
        subcategory_key = (category_name, subcategory_name)
        subcategory = subcategories.get(subcategory_key)
        if subcategory is None:
            subcategory, _ = SubCategory.objects.get_or_create(
                category=category,
                name=subcategory_name,
            )
            subcategory.image.name = category_images[category_name]
            subcategory.is_active = True
            subcategory.save(update_fields=["image", "is_active"])
            subcategories[subcategory_key] = subcategory

        product, _ = Product.objects.get_or_create(
            category=category,
            subcategory=subcategory,
            name=item["name"],
        )
        product.description = item["description"]
        product.key_features = "\n".join(
            [
                "Real product photography",
                "Quality checked before listing",
                "Secure EEHook delivery",
            ]
        )
        product.shipping_fee = Decimal("0.00")
        product.estimated_delivery_time = "3-7 business days"
        product.seller_name = "EEHook Marketplace"
        product.warranty_info = "6-month seller warranty"
        product.is_active = True
        product.emi_available = False
        product.emi_starting_price = None
        product.save()
        create_variants(product, item)

    print(
        f"Seeded {len(PRODUCTS[:30])} products across "
        f"{len(categories)} categories and {len(subcategories)} subcategories."
    )


if __name__ == "__main__":
    seed()

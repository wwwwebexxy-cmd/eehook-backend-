"""Safely expand the EEHook demo catalog to eleven categories.

The command is intentionally guarded. It only creates or refreshes records
identified by the existing demo seller marker, never deletes records, and
requires ``--apply`` before changing the database. Image downloads happen on
the backend host so ImageField files are stored where the API serves media.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal, ROUND_HALF_UP

import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils.text import slugify

from catalog_curated_images import URL_POOLS, download
from myapp.catalog_qa_11 import COLOR_CODES, IMPORT_MARKER, PRODUCTS_11
from myapp.models import (
    Category,
    Color,
    Product,
    ProductImage,
    ProductVariant,
    ProductVariantUnit,
    SubCategory,
    Unit,
    UnitType,
)


SUBCATEGORY_IMAGE_KEYS = {
    "Mobiles": "smartphone",
    "Laptop": "laptop",
    "iphone": "smartphone",
    "MacBook": "laptop",
    "IPad": "tablet",
    "Iwatches": "smartwatch",
    "Accessories": "charger",
    "Consoles": "console",
    "Games": "game_box",
    "Gaming Accessories": "headset",
    "Men": "smartwatch",
    "Women": "smartwatch",
    "Unisex": "smartwatch",
    "Fitness Bands": "smartwatch",
    "VR Headsets": "vr",
    "Smart Glasses": "glasses",
    "Perfumes": "perfume",
    "Skincare": "skincare",
    "Makeup": "makeup",
    "Action Figures": "figure",
    "Board Games": "board_game",
    "Educational": "educational",
    "Miscellaneous": "organizer",
    "Vegetables": "spinach",
    "Crocs": "clogs",
    "Headphones": "headset",
    "Cables": "cable",
}


CATEGORY_IMAGE_KEYS = {
    "Electronics": "smartphone",
    "Apple Products": "tablet",
    "Gaming Products": "console",
    "Smart Watches": "smartwatch",
    "Wearables": "vr",
    "Cosmetics": "perfume",
    "Toys": "figure",
    "Other Products": "organizer",
    "Vegetables": "spinach",
    "Footwear": "clogs",
    "Audio Products": "headset",
}


CATEGORY_NAME_ALIASES = {
    "vegetables": "Vegetables",
}


def image_key(item):
    subcategory = item["subcategory"]
    if subcategory in SUBCATEGORY_IMAGE_KEYS:
        return SUBCATEGORY_IMAGE_KEYS[subcategory]
    raise CommandError(f"No image source mapping exists for {subcategory}.")


def content_extension(content_type):
    return {"image/png": "png", "image/webp": "webp"}.get(content_type, "jpg")


class Command(BaseCommand):
    help = "Expand the idempotent EEHook demo catalog to eleven categories and 52 products."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply changes. Without this flag the command only validates sources and data.",
        )

    @staticmethod
    def _money(value):
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _sku_part(value):
        return slugify(str(value)).replace("-", "").upper()

    @staticmethod
    def _ensure_color(name):
        color, _ = Color.objects.get_or_create(
            name=name,
            defaults={"code": COLOR_CODES.get(name, "#6B7280")},
        )
        return color

    @staticmethod
    def _ensure_unit(unit_type_name, unit_name):
        unit_type, _ = UnitType.objects.get_or_create(name=unit_type_name)
        unit, created = Unit.objects.get_or_create(unit_type=unit_type, name=unit_name)
        if created:
            unit.full_clean()
        return unit_type, unit

    def _variant_sku(self, item, color=None):
        return item["code"] if color is None else f"{item['code']}-{self._sku_part(color)}"

    def _unit_sku(self, item, unit_name, color=None):
        parts = [item["code"]]
        if color:
            parts.append(self._sku_part(color))
        parts.append(self._sku_part(unit_name))
        return "-".join(parts)

    def _download_image(self, session, key, path_prefix, position):
        urls = URL_POOLS[key]
        start = int(hashlib.sha256(f"{path_prefix}:{position}".encode()).hexdigest(), 16) % len(urls)
        for offset in range(len(urls)):
            url = urls[(start + offset) % len(urls)]
            try:
                result = download(session, url)
            except requests.RequestException:
                result = None
            if not result:
                continue
            content, content_type = result
            path = f"{path_prefix}-{position}.{content_extension(content_type)}"
            if not default_storage.exists(path):
                default_storage.save(path, ContentFile(content))
            return path
        raise CommandError(f"Could not download a valid image for {path_prefix}.")

    def _ensure_category_image(self, session, category_name, key):
        path_prefix = f"categories/catalog_11_2026_10/{slugify(category_name)}"
        existing = next(
            (
                name
                for name in (f"{path_prefix}.jpg", f"{path_prefix}.png", f"{path_prefix}.webp")
                if default_storage.exists(name)
            ),
            None,
        )
        if existing:
            return existing
        return self._download_image(session, key, path_prefix, 1)

    def _ensure_product_images(self, session, item, variant, color_name):
        current_count = variant.images.count()
        if current_count >= 3:
            return
        key = image_key(item)
        color_part = self._sku_part(color_name or "default").lower()
        path_prefix = f"products/catalog_11_2026_10/{item['code'].lower()}-{color_part}"
        existing_paths = set(variant.images.values_list("image", flat=True))
        paths = []
        for position in range(current_count + 1, 4):
            path = self._download_image(session, key, path_prefix, position)
            if path not in existing_paths:
                paths.append(path)
        for offset, path in enumerate(paths):
            ProductImage.objects.get_or_create(
                variant=variant,
                image=path,
                defaults={"position": current_count + offset, "is_primary": current_count == 0 and offset == 0},
            )
        if not variant.images.filter(is_primary=True).exists():
            first = variant.images.order_by("position", "id").first()
            if first:
                first.is_primary = True
                first.save(update_fields=("is_primary",))

    def _save_variant(self, session, item, product, color_name):
        color = self._ensure_color(color_name) if color_name else None
        variant, _ = ProductVariant.objects.get_or_create(product=product, color=color)
        is_unit_based = item["kind"] in {"units", "color_units"}
        base_price = self._money(item["price"])
        color_index = item["colors"].index(color_name) if color_name else 0
        variant.sku = self._variant_sku(item, color_name)
        variant.price_type = "multiple" if is_unit_based else "single"
        variant.price = None if is_unit_based else base_price + Decimal(color_index * 100)
        variant.stock = item["stock"]
        variant.full_clean()
        variant.save()
        if is_unit_based:
            for unit_index, unit_name in enumerate(item["units"]):
                unit_type, unit = self._ensure_unit(item["unit_type"], unit_name)
                variant_unit, _ = ProductVariantUnit.objects.get_or_create(variant=variant, unit=unit)
                variant_unit.unit_type = unit_type
                variant_unit.sku = self._unit_sku(item, unit_name, color_name)
                variant_unit.price = self._money(base_price * (Decimal("1.00") + Decimal(unit_index) * Decimal("0.15")))
                variant_unit.stock = max(1, item["stock"] - unit_index * 3 - color_index * 2)
                variant_unit.full_clean()
                variant_unit.save()
        self._ensure_product_images(session, item, variant, color_name)

    def _validate_sources(self):
        catalog_categories = {CATEGORY_NAME_ALIASES.get(item["category"], item["category"]) for item in PRODUCTS_11}
        missing = sorted(catalog_categories - set(CATEGORY_IMAGE_KEYS))
        if missing:
            raise CommandError(f"Missing category image mappings: {missing}")
        for item in PRODUCTS_11:
            image_key(item)
            if image_key(item) not in URL_POOLS:
                raise CommandError(f"No image URL pool exists for {item['code']}.")

    def handle(self, *args, **options):
        self._validate_sources()
        session = requests.Session()
        session.headers.update({"User-Agent": "EEHookDemoCatalog/1.0"})
        if not options["apply"]:
            self.stdout.write(self.style.SUCCESS("Validated 11 categories, 52 products, and image source mappings. No database changes made."))
            return

        created_products = 0
        skipped_existing = 0
        with transaction.atomic():
            category_cache = {}
            subcategory_cache = {}
            for item in PRODUCTS_11:
                category_name = CATEGORY_NAME_ALIASES.get(item["category"], item["category"])
                category = category_cache.get(category_name)
                if category is None:
                    category, _ = Category.objects.get_or_create(name=category_name)
                    category_cache[category_name] = category
                    if not category.image:
                        category.image.name = self._ensure_category_image(session, category_name, CATEGORY_IMAGE_KEYS[category_name])
                        category.is_active = True
                        category.save(update_fields=("image", "is_active"))

                subcategory_key = (category_name, item["subcategory"])
                subcategory = subcategory_cache.get(subcategory_key)
                if subcategory is None:
                    subcategory, _ = SubCategory.objects.get_or_create(category=category, name=item["subcategory"])
                    subcategory_cache[subcategory_key] = subcategory
                    if not subcategory.image:
                        subcategory.image.name = self._ensure_category_image(session, category_name, SUBCATEGORY_IMAGE_KEYS[item["subcategory"]])
                        subcategory.is_active = True
                        subcategory.save(update_fields=("image", "is_active"))

                product = Product.objects.filter(category=category, subcategory=subcategory, name=item["name"]).first()
                if product is None:
                    product = Product(category=category, subcategory=subcategory, name=item["name"], seller_name=IMPORT_MARKER)
                    created_products += 1
                elif product.seller_name != IMPORT_MARKER:
                    skipped_existing += 1
                    continue
                product.description = item["description"]
                product.key_features = "\n".join((f"{item['subcategory']} product configuration", "SKU-level stock tracking", "Product-specific catalog imagery"))
                product.shipping_fee = Decimal("0.00")
                product.estimated_delivery_time = "3-5 business days"
                product.seller_name = IMPORT_MARKER
                product.warranty_info = "6-month seller warranty"
                product.is_active = True
                product.emi_available = False
                product.emi_starting_price = None
                product.full_clean()
                product.save()
                colors = item["colors"] if item["kind"] in {"colors", "color_units"} else (None,)
                for color_name in colors:
                    self._save_variant(session, item, product, color_name)

        self.stdout.write(self.style.SUCCESS(f"Catalog expansion complete: {created_products} products created, {skipped_existing} protected existing records skipped, 11 categories targeted."))

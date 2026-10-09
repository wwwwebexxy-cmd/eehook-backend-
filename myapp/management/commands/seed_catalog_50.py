from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from myapp.catalog_qa_50 import (
    COLOR_CODES,
    IMPORT_MARKER,
    PRODUCTS,
    image_tasks,
    variant_image_map,
)
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


class Command(BaseCommand):
    help = "Add or refresh the 50-product, image-backed catalog test set."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate the catalog and its images without changing the database.",
        )

    @staticmethod
    def _money(value):
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _sku_part(value):
        return slugify(str(value)).replace("-", "").upper()

    def _ensure_color(self, name):
        color, _ = Color.objects.get_or_create(
            name=name,
            defaults={"code": COLOR_CODES.get(name, "#6B7280")},
        )
        return color

    @staticmethod
    def _ensure_unit(unit_type_name, unit_name):
        unit_type, _ = UnitType.objects.get_or_create(name=unit_type_name)
        unit, created = Unit.objects.get_or_create(
            unit_type=unit_type,
            name=unit_name,
        )
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

    def _save_images(self, variant, filenames):
        for position, filename in enumerate(filenames):
            image, created = ProductImage.objects.get_or_create(
                variant=variant,
                image=filename,
                defaults={"position": position, "is_primary": position == 0},
            )
            if not created and (
                image.position != position or image.is_primary != (position == 0)
            ):
                image.position = position
                image.is_primary = position == 0
                image.save(update_fields=("position", "is_primary"))

    def _save_variant(self, item, product, color_name, filenames):
        color = self._ensure_color(color_name) if color_name else None
        variant, _ = ProductVariant.objects.get_or_create(product=product, color=color)
        is_unit_based = item["kind"] in {"units", "color_units"}
        base_price = self._money(item["price"])
        color_index = item["colors"].index(color_name) if color_name else 0

        variant.sku = self._variant_sku(item, color_name)
        variant.price_type = "multiple" if is_unit_based else "single"
        variant.price = None if is_unit_based else base_price + Decimal(color_index * 100)
        variant.stock = item["stock"] if not is_unit_based else sum(
            max(1, item["stock"] - unit_index * 3 - color_index * 2)
            for unit_index, _ in enumerate(item["units"])
        )
        variant.full_clean()
        variant.save()

        if is_unit_based:
            for unit_index, unit_name in enumerate(item["units"]):
                unit_type, unit = self._ensure_unit(item["unit_type"], unit_name)
                unit_price = base_price * (Decimal("1.00") + Decimal(unit_index) * Decimal("0.15"))
                unit_stock = max(1, item["stock"] - unit_index * 3 - color_index * 2)
                variant_unit, _ = ProductVariantUnit.objects.get_or_create(
                    variant=variant,
                    unit=unit,
                    defaults={
                        "unit_type": unit_type,
                        "sku": self._unit_sku(item, unit_name, color_name),
                        "price": self._money(unit_price),
                        "stock": unit_stock,
                    },
                )
                variant_unit.unit_type = unit_type
                variant_unit.sku = self._unit_sku(item, unit_name, color_name)
                variant_unit.price = self._money(unit_price)
                variant_unit.stock = unit_stock
                variant_unit.full_clean()
                variant_unit.save()

        self._save_images(variant, filenames)

    def handle(self, *args, **options):
        expected_image_count = len(image_tasks())
        image_root = Path(settings.MEDIA_ROOT)
        missing_images = [
            task["filename"]
            for task in image_tasks()
            if not (image_root / task["filename"]).is_file()
        ]
        if missing_images:
            sample = ", ".join(missing_images[:5])
            raise CommandError(
                f"{len(missing_images)} generated catalog images are missing. "
                f"First missing paths: {sample}"
            )

        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Validated {len(PRODUCTS)} products and {expected_image_count} unique images."
                )
            )
            return

        created_count = 0
        with transaction.atomic():
            for item in PRODUCTS:
                try:
                    category = Category.objects.get(name=item["category"])
                    subcategory = SubCategory.objects.get(
                        category=category,
                        name=item["subcategory"],
                    )
                except (Category.DoesNotExist, SubCategory.DoesNotExist) as error:
                    raise CommandError(
                        f"Missing category mapping for {item['code']}: "
                        f"{item['category']} / {item['subcategory']}"
                    ) from error

                product, created = Product.objects.get_or_create(
                    category=category,
                    subcategory=subcategory,
                    name=item["name"],
                    seller_name=IMPORT_MARKER,
                    defaults={"description": item["description"]},
                )
                created_count += int(created)
                product.description = item["description"]
                product.key_features = "\n".join(
                    (
                        f"{item['subcategory']} product configuration",
                        "SKU-level stock tracking",
                        "Product-specific catalog imagery",
                    )
                )
                product.shipping_fee = Decimal("0.00")
                product.estimated_delivery_time = "3-5 business days"
                product.seller_name = IMPORT_MARKER
                product.warranty_info = "6-month seller warranty"
                product.emi_available = False
                product.emi_starting_price = None
                product.is_active = True
                product.full_clean()
                product.save()

                for color_name, filenames in variant_image_map(item).items():
                    self._save_variant(item, product, color_name, filenames)

        self.stdout.write(
            self.style.SUCCESS(
                f"Catalog import complete: {created_count} created, "
                f"{len(PRODUCTS) - created_count} refreshed, "
                f"{expected_image_count} unique image assets linked."
            )
        )

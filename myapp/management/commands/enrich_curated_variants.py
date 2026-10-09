"""Safely add two colour variants and product-specific choices in place.

This command intentionally does not delete or replace products.  It upgrades
the already verified curated catalog by preserving each product and its
existing primary three-image gallery, then creates one clearly different
colour variant with its own three-image gallery.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils.text import slugify

from myapp.management.commands.refresh_curated_catalog import (
    CATALOG,
    IMPORT_MARKER,
    SECOND_VARIANTS,
    SOURCE_DIRECTORY,
    UNIT_OPTIONS,
    split_gallery,
)
from myapp.models import Color, Product, ProductImage, ProductVariant, ProductVariantUnit, Unit, UnitType


class Command(BaseCommand):
    help = "Add a second, separately imaged colour and two buying choices to each curated product."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate the current catalog and gallery sources without changing data.",
        )

    @staticmethod
    def _money(value):
        return Decimal(str(value)).quantize(Decimal("0.01"))

    @staticmethod
    def _color(name, code):
        color, _ = Color.objects.get_or_create(name=name, defaults={"code": code})
        if color.code != code:
            color.code = code
            color.save(update_fields=("code",))
        return color

    @staticmethod
    def _unit(unit_type_name, unit_name):
        unit_type, _ = UnitType.objects.get_or_create(name=unit_type_name)
        unit, _ = Unit.objects.get_or_create(unit_type=unit_type, name=unit_name)
        return unit_type, unit

    def _product_for(self, item):
        products = Product.objects.filter(
            name=item.name,
            category__name=item.category,
            subcategory__name=item.subcategory,
        )
        if products.count() != 1:
            raise CommandError(
                f"Expected exactly one current product for {item.code} ({item.name}); found {products.count()}."
            )
        return products.get()

    def _validate(self):
        expected_products = []
        for item in CATALOG:
            product = self._product_for(item)
            expected_products.append(product.pk)
            primary = product.variants.filter(color__name=item.color)
            if primary.count() != 1 or primary.get().images.count() != 3:
                raise CommandError(
                    f"{item.name} must retain one three-image {item.color} primary variant before enrichment."
                )
            color_name, _, source, row, rows = SECOND_VARIANTS[item.code]
            if not (SOURCE_DIRECTORY / source).is_file():
                raise CommandError(f"Missing secondary gallery source: {source}")
            if len(split_gallery(SOURCE_DIRECTORY / source, row, rows)) != 3:
                raise CommandError(f"{source} does not contain three usable image panels for {color_name}.")
        if len(set(expected_products)) != len(CATALOG):
            raise CommandError("Catalog entries do not map to 28 distinct products.")

    def _apply_choices(self, variant, item, color_index):
        unit_type_name, unit_names = UNIT_OPTIONS[item.code]
        unit_type, units = None, []
        for unit_name in unit_names:
            unit_type, unit = self._unit(unit_type_name, unit_name)
            units.append(unit)
        existing = {entry.unit_id: entry for entry in variant.sizes.select_related("unit")}
        base_price = self._money(item.price)
        for unit_index, unit in enumerate(units):
            price = self._money(
                base_price * (Decimal("1.00") + Decimal("0.15") * unit_index + Decimal("0.03") * color_index)
            )
            entry = existing.get(unit.pk)
            if entry is None:
                entry = ProductVariantUnit(variant=variant, unit_type=unit_type, unit=unit)
            entry.sku = f"{item.code}-{slugify(variant.color.name).upper()}-{slugify(unit.name).upper()}"
            entry.price = price
            entry.stock = max(5, 25 - unit_index * 5 - color_index * 3)
            entry.full_clean()
            entry.save()
        if variant.sizes.count() != 2:
            raise CommandError(f"{item.name} / {variant.color.name} does not have exactly two buying choices.")
        variant.stock = sum(entry.stock for entry in variant.sizes.all())
        variant.save(update_fields=("stock",))

    def _create_secondary_images(self, variant, item, color_name, source, row, rows, replace=False):
        if variant.images.exists():
            if replace:
                # This is only reached when a previously imported secondary
                # swatch has been corrected to a new, visibly different colour.
                # Its files are pruned after the new gallery is committed.
                variant.images.all().delete()
            elif variant.images.count() != 3:
                raise CommandError(
                    f"{item.name} / {color_name} already has an incomplete gallery; it was left untouched."
                )
            else:
                return
        for position, panel in enumerate(split_gallery(SOURCE_DIRECTORY / source, row, rows)):
            image = ProductImage(variant=variant, position=position, is_primary=position == 0)
            filename = f"curated/{item.code.lower()}-{slugify(color_name)}-{position + 1}.png"
            image.image.save(filename, ContentFile(panel), save=False)
            image.save()

    def handle(self, *args, **options):
        self._validate()
        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Validated {len(CATALOG)} retained products and {len(CATALOG)} separate secondary galleries."
                )
            )
            return

        with transaction.atomic():
            for item in CATALOG:
                product = self._product_for(item)
                product.key_features = (
                    f"{item.subcategory} product\n"
                    "Two distinct colour variants\n"
                    "Three verified images per colour variant"
                )
                product.seller_name = IMPORT_MARKER
                product.is_active = True
                product.save(update_fields=("key_features", "seller_name", "is_active", "updated_at"))

                primary_color = self._color(item.color, item.color_code)
                primary = product.variants.get(color=primary_color)
                primary.sku = f"{item.code}-{slugify(item.color).upper()}"
                primary.price_type = "multiple"
                primary.price = None
                primary.full_clean()
                primary.save(update_fields=("sku", "price_type", "price"))
                self._apply_choices(primary, item, color_index=0)

                color_name, color_code, source, row, rows = SECOND_VARIANTS[item.code]
                secondary_color = self._color(color_name, color_code)
                secondary = product.variants.filter(color=secondary_color).first()
                replace_secondary_gallery = False
                if secondary is None:
                    other_variants = product.variants.exclude(pk=primary.pk)
                    if other_variants.count() == 1:
                        # Preserve the existing secondary variant, choices, and
                        # any client references while correcting its swatch and
                        # its independently sourced image set.
                        secondary = other_variants.get()
                        secondary.color = secondary_color
                        replace_secondary_gallery = True
                    elif other_variants.exists():
                        raise CommandError(
                            f"{item.name} has ambiguous secondary variants; it was left untouched."
                        )
                    else:
                        secondary = ProductVariant(
                            product=product,
                            color=secondary_color,
                            stock=0,
                        )
                secondary.sku = f"{item.code}-{slugify(color_name).upper()}"
                secondary.price_type = "multiple"
                secondary.price = None
                secondary.full_clean()
                secondary.save(update_fields=("color", "sku", "price_type", "price"))
                self._apply_choices(secondary, item, color_index=1)
                self._create_secondary_images(
                    secondary,
                    item,
                    color_name,
                    source,
                    row,
                    rows,
                    replace=replace_secondary_gallery,
                )

            products = Product.objects.filter(seller_name=IMPORT_MARKER)
            variants = ProductVariant.objects.filter(product__in=products)
            if products.count() != len(CATALOG):
                raise CommandError("The curated product count changed unexpectedly.")
            if products.exclude(category_id=F("subcategory__category_id")).exists():
                raise CommandError("A product is mapped to the wrong category/subcategory.")
            if variants.count() != len(CATALOG) * 2:
                raise CommandError("Each curated product must have exactly two colour variants.")
            if any(product.variants.count() != 2 for product in products):
                raise CommandError("At least one product does not have exactly two colour variants.")
            if any(variant.images.count() != 3 or variant.sizes.count() != 2 for variant in variants):
                raise CommandError("Every colour must have three images and two buying choices.")
            if any(product.variants.values("color_id").distinct().count() != 2 for product in products):
                raise CommandError("Each product needs two distinct colour selections.")

        self.stdout.write(
            self.style.SUCCESS(
                f"Enriched {len(CATALOG)} retained products with {len(CATALOG) * 2} colour variants, "
                f"{len(CATALOG) * 2 * 2} buying choices, and {len(CATALOG) * 2 * 3} product images."
            )
        )

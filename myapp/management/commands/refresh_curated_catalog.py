"""Replace the public catalog with a verified category/subcategory catalog.

Every source image is a three-panel product gallery created specifically for
the product and colour named below.  The command splits each panel into a
separate ``ProductImage`` so every colour variant has exactly three product
images.  It deliberately removes the older mixed catalog entries instead of
leaving them available through the public APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils.text import slugify
from PIL import Image

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


IMPORT_MARKER = "EEHook curated catalog 2026-10"
SOURCE_DIRECTORY = Path(settings.MEDIA_ROOT) / "products" / "curated" / "source"


@dataclass(frozen=True)
class CatalogItem:
    code: str
    category: str
    subcategory: str
    name: str
    description: str
    color: str
    color_code: str
    price: str
    source: str
    row: int = 0
    rows: int = 1


# Keep the names intentionally literal.  They make it impossible for the
# Apple/iPhone listing to contain a tablet, a generic phone, or an accessory.
CATALOG = (
    CatalogItem("EL-MOB-01", "Electronics", "Mobiles", "Samsung Galaxy S24 FE", "Android 5G smartphone with a bright display and versatile cameras.", "Graphite", "#374151", "59999.00", "samsung-galaxy-s24-graphite.png"),
    CatalogItem("EL-LAP-01", "Electronics", "Laptop", "Lenovo ThinkPad E14", "14-inch business laptop for everyday work, study, and video calls.", "Black", "#111827", "64999.00", "lenovo-thinkpad-e14-black.png"),
    CatalogItem("AP-IP-14", "Apple Products", "iphone", "Apple iPhone 14", "Apple iPhone 14 with a 6.1-inch display and dual-camera system.", "Midnight", "#172554", "59999.00", "iphone-14-midnight.png"),
    CatalogItem("AP-IP-15", "Apple Products", "iphone", "Apple iPhone 15", "Apple iPhone 15 with Dynamic Island, USB-C, and a 48MP main camera.", "Blue", "#2563EB", "69999.00", "iphone-15-blue.png"),
    CatalogItem("AP-IP-16", "Apple Products", "iphone", "Apple iPhone 16", "Apple iPhone 16 with the A18 chip and an advanced dual-camera system.", "Ultramarine", "#1D4ED8", "79999.00", "iphone-16-ultramarine.png"),
    CatalogItem("AP-PAD-01", "Apple Products", "IPad", "Apple iPad Air 11-inch (M2)", "11-inch Apple iPad Air with M2 performance for notes, drawing, and streaming.", "Blue", "#2563EB", "59999.00", "apple-computers-wearables.png", 0, 3),
    CatalogItem("AP-MAC-01", "Apple Products", "MacBook", "Apple MacBook Air 13-inch (M3)", "13-inch Apple MacBook Air with M3 performance in a thin, portable design.", "Midnight", "#172554", "99999.00", "apple-computers-wearables.png", 1, 3),
    CatalogItem("AP-WAT-01", "Apple Products", "Iwatches", "Apple Watch Series 10", "Apple Watch Series 10 with health insights, activity tracking, and notifications.", "Jet Black", "#111827", "42999.00", "apple-computers-wearables.png", 2, 3),
    CatalogItem("AP-ACC-01", "Apple Products", "Accessories", "Apple MagSafe Charger", "Magnetic Apple MagSafe charger for compatible iPhone models.", "White", "#FFFFFF", "3999.00", "apple-and-gaming-core.png", 0, 3),
    CatalogItem("GM-CON-01", "Gaming Products", "Consoles", "PlayStation 5 Slim Console", "Slim home gaming console with a wireless controller and high-speed storage.", "White", "#FFFFFF", "54999.00", "apple-and-gaming-core.png", 1, 3),
    CatalogItem("GM-GAM-01", "Gaming Products", "Games", "Racing Championship Game for PS5", "Physical racing game for PlayStation 5 with solo and local multiplayer modes.", "Blue", "#2563EB", "3499.00", "apple-and-gaming-core.png", 2, 3),
    CatalogItem("GM-ACC-01", "Gaming Products", "Gaming Accessories", "Wireless Gaming Headset", "Over-ear wireless gaming headset with a boom microphone and plush ear cushions.", "Black", "#111827", "6999.00", "gaming-and-smart-watches.png", 0, 3),
    CatalogItem("SW-MEN-01", "Smart Watches", "Men", "Men's GPS Sport Smartwatch", "Rugged GPS smartwatch with workout tracking, heart-rate monitoring, and a sport band.", "Black", "#111827", "15999.00", "gaming-and-smart-watches.png", 1, 3),
    CatalogItem("SW-WOM-01", "Smart Watches", "Women", "Women's Rose Smartwatch", "Lightweight smartwatch with wellness tracking, notifications, and a comfortable rose band.", "Rose", "#F472B6", "13999.00", "gaming-and-smart-watches.png", 2, 3),
    CatalogItem("SW-UNI-01", "Smart Watches", "Unisex", "Unisex Everyday Smartwatch", "Everyday smartwatch with activity tracking, call alerts, and a bright round display.", "Silver", "#9CA3AF", "12999.00", "watch-and-wearables.png", 0, 3),
    CatalogItem("WR-BND-01", "Wearables", "Fitness Bands", "Fitness Tracker Band", "Slim fitness band for steps, heart rate, sleep, and everyday wellness goals.", "Black", "#111827", "4999.00", "watch-and-wearables.png", 1, 3),
    CatalogItem("WR-VR-01", "Wearables", "VR Headsets", "Standalone VR Headset", "Standalone virtual-reality headset with a smooth visor and two compact controllers.", "White", "#FFFFFF", "29999.00", "watch-and-wearables.png", 2, 3),
    CatalogItem("WR-GLS-01", "Wearables", "Smart Glasses", "Audio Smart Glasses", "Smart glasses with open-ear audio, hands-free calls, and tinted lenses.", "Black", "#111827", "19999.00", "glasses-and-beauty.png", 0, 3),
    CatalogItem("CS-PER-01", "Cosmetics", "Perfumes", "Amber Eau de Parfum", "Warm amber eau de parfum in a premium glass spray bottle.", "Amber", "#F59E0B", "2499.00", "glasses-and-beauty.png", 1, 3),
    CatalogItem("CS-SKN-01", "Cosmetics", "Skincare", "Daily Face Moisturizer", "Lightweight daily face moisturizer in a sealed cosmetic jar.", "Cream", "#FFF7ED", "899.00", "glasses-and-beauty.png", 2, 3),
    CatalogItem("CS-MKP-01", "Cosmetics", "Makeup", "Velvet Lip Color", "Long-wear velvet lip color with rich crimson pigment.", "Crimson", "#BE123C", "699.00", "makeup-and-toys.png", 0, 3),
    CatalogItem("TY-FIG-01", "Toys", "Action Figures", "Space Ranger Action Figure", "Poseable space-ranger action figure with articulated joints and a display base.", "Silver", "#9CA3AF", "1499.00", "makeup-and-toys.png", 1, 3),
    CatalogItem("TY-BRD-01", "Toys", "Board Games", "Fantasy Quest Board Game", "Cooperative fantasy board game with a game board, map tiles, and tokens.", "Purple", "#7E22CE", "1599.00", "makeup-and-toys.png", 2, 3),
    CatalogItem("TY-EDU-01", "Toys", "Educational", "Buildwise Robotics Kit", "Hands-on robotics kit with components for guided STEM building activities.", "Blue", "#2563EB", "2199.00", "education-and-home.png", 0, 3),
    CatalogItem("OT-BOT-01", "Other Products", "Miscellaneous", "Insulated Travel Bottle", "Reusable insulated stainless-steel water bottle with a leak-proof cap.", "Blue", "#2563EB", "799.00", "education-and-home.png", 1, 3),
    CatalogItem("OT-ORG-01", "Other Products", "Miscellaneous", "Desktop Cable Organizer", "Modular desktop organizer for cables, pens, notes, and small work essentials.", "White", "#FFFFFF", "649.00", "education-and-home.png", 2, 3),
    CatalogItem("VG-SPN-01", "vegetables", "Vegetables", "Fresh Baby Spinach", "Fresh baby spinach leaves, packed for salads, smoothies, and everyday cooking.", "Green", "#16A34A", "79.00", "food-and-footwear.png", 0, 2),
    CatalogItem("FW-CLG-01", "Footwear", "Crocs", "Classic Comfort Clogs", "Lightweight ventilated comfort clogs with a cushioned sole and heel strap.", "Black", "#111827", "2499.00", "food-and-footwear.png", 1, 2),
)


# The second entry for every product is deliberately a different, visible
# colour and is sourced from a separate gallery.  This keeps the selector
# meaningful instead of showing the same photos under two swatches.
SECOND_VARIANTS = {
    "EL-MOB-01": ("Sky Blue", "#38BDF8", "electronics-second-colors.png", 0, 2),
    "EL-LAP-01": ("Silver", "#9CA3AF", "electronics-second-colors.png", 1, 2),
    "AP-IP-14": ("Starlight", "#FDE68A", "iphone-second-colors.png", 0, 3),
    "AP-IP-15": ("Black", "#111827", "iphone-second-colors.png", 1, 3),
    "AP-IP-16": ("Pink", "#F472B6", "iphone-second-colors.png", 2, 3),
    "AP-PAD-01": ("Purple", "#7E22CE", "apple-second-colors.png", 0, 3),
    "AP-MAC-01": ("Silver", "#9CA3AF", "apple-second-colors.png", 1, 3),
    "AP-WAT-01": ("Starlight", "#FDE68A", "apple-second-colors.png", 2, 3),
    "AP-ACC-01": ("Graphite", "#374151", "magsafe-gaming-second-colors.png", 0, 3),
    "GM-CON-01": ("Black", "#111827", "magsafe-gaming-second-colors.png", 1, 3),
    "GM-GAM-01": ("Red", "#DC2626", "magsafe-gaming-second-colors.png", 2, 3),
    "GM-ACC-01": ("White", "#FFFFFF", "gaming-watches-second-colors.png", 0, 3),
    "SW-MEN-01": ("Navy", "#1E3A8A", "gaming-watches-second-colors.png", 1, 3),
    "SW-WOM-01": ("Cream", "#FFF7ED", "gaming-watches-second-colors.png", 2, 3),
    "SW-UNI-01": ("Black", "#111827", "watch-wearables-second-colors.png", 0, 3),
    "WR-BND-01": ("Berry", "#BE185D", "watch-wearables-second-colors.png", 1, 3),
    "WR-VR-01": ("Black", "#111827", "watch-wearables-second-colors.png", 2, 3),
    "WR-GLS-01": ("Tortoise", "#78350F", "glasses-beauty-second-colors.png", 0, 3),
    "CS-PER-01": ("Clear", "#E5E7EB", "glasses-beauty-second-colors.png", 1, 3),
    "CS-SKN-01": ("Sage", "#65A30D", "glasses-beauty-second-colors.png", 2, 3),
    "CS-MKP-01": ("Rose", "#F472B6", "makeup-toys-second-colors.png", 0, 3),
    "TY-FIG-01": ("Black", "#111827", "makeup-toys-second-colors.png", 1, 3),
    "TY-BRD-01": ("Blue", "#2563EB", "makeup-toys-second-colors.png", 2, 3),
    "TY-EDU-01": ("Yellow", "#EAB308", "education-home-second-colors.png", 0, 3),
    "OT-BOT-01": ("Black", "#111827", "education-home-second-colors.png", 1, 3),
    "OT-ORG-01": ("Black", "#111827", "education-home-second-colors.png", 2, 3),
    "VG-SPN-01": ("Red", "#991B1B", "red-spinach-second-colors.png", 0, 1),
    "FW-CLG-01": ("Sand", "#D6D3D1", "food-footwear-second-colors.png", 1, 2),
}


# Unit options are product-specific, so storage never appears on vegetables
# and a colour choice is always complemented by a useful buying choice.
UNIT_OPTIONS = {
    "EL-MOB-01": ("Storage", ("128 GB", "256 GB")),
    "EL-LAP-01": ("Storage", ("512 GB", "1 TB")),
    "AP-IP-14": ("Storage", ("128 GB", "256 GB")),
    "AP-IP-15": ("Storage", ("128 GB", "256 GB")),
    "AP-IP-16": ("Storage", ("128 GB", "256 GB")),
    "AP-PAD-01": ("Storage", ("128 GB", "256 GB")),
    "AP-MAC-01": ("Storage", ("256 GB", "512 GB")),
    "AP-WAT-01": ("Case Size", ("42 mm", "46 mm")),
    "AP-ACC-01": ("Cable Length", ("1 m", "2 m")),
    "GM-CON-01": ("Storage", ("1 TB", "2 TB")),
    "GM-GAM-01": ("Game Edition", ("Standard", "Deluxe")),
    "GM-ACC-01": ("Bundle", ("Headset Only", "Headset + Stand")),
    "SW-MEN-01": ("Case Size", ("42 mm", "46 mm")),
    "SW-WOM-01": ("Case Size", ("40 mm", "44 mm")),
    "SW-UNI-01": ("Case Size", ("42 mm", "46 mm")),
    "WR-BND-01": ("Band Size", ("Small", "Large")),
    "WR-VR-01": ("Storage", ("128 GB", "256 GB")),
    "WR-GLS-01": ("Frame Size", ("Medium", "Large")),
    "CS-PER-01": ("Volume", ("50 ml", "100 ml")),
    "CS-SKN-01": ("Weight", ("50 g", "100 g")),
    "CS-MKP-01": ("Volume", ("3 ml", "6 ml")),
    "TY-FIG-01": ("Pack Size", ("1 Piece", "2 Pieces")),
    "TY-BRD-01": ("Game Edition", ("Standard", "Deluxe")),
    "TY-EDU-01": ("Kit Edition", ("Starter", "Advanced")),
    "OT-BOT-01": ("Volume", ("750 ml", "1 L")),
    "OT-ORG-01": ("Pack Size", ("1 Piece", "2 Pieces")),
    "VG-SPN-01": ("Weight", ("250 g", "500 g")),
    "FW-CLG-01": ("Footwear Size", ("7", "9")),
}


def variant_specs(item):
    """Return the two independently sourced colour variants for one product."""
    second = SECOND_VARIANTS[item.code]
    return (
        (item.color, item.color_code, item.source, item.row, item.rows),
        second,
    )


def split_gallery(source: Path, row=0, rows=1):
    """Return the three full-product panels in a generated gallery source."""
    with Image.open(source) as original:
        image = original.convert("RGBA")
    width, height = image.size
    if not 0 <= row < rows:
        raise CommandError(f"Invalid row {row + 1} of {rows} requested from {source.name}.")
    if width < 900 or (rows == 1 and width < height * 2):
        raise CommandError(
            f"{source.name} must be a wide three-panel product gallery; got {width}x{height}."
        )
    top = round(height * row / rows)
    bottom = round(height * (row + 1) / rows)
    row_image = image.crop((0, top, width, bottom))
    panels = []
    for index in range(3):
        left = round(width * index / 3)
        right = round(width * (index + 1) / 3)
        panel = row_image.crop((left, 0, right, row_image.height))
        encoded = BytesIO()
        panel.save(encoded, format="PNG", optimize=True)
        panels.append(encoded.getvalue())
    return panels


class Command(BaseCommand):
    help = "Replace mixed catalog records with verified, three-image colour variants."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate the curated source galleries without changing catalog data.",
        )

    def _validate_sources(self):
        sources = [
            (source, row, rows)
            for item in CATALOG
            for _, _, source, row, rows in variant_specs(item)
        ]
        missing = [source for source, _, _ in sources if not (SOURCE_DIRECTORY / source).is_file()]
        if missing:
            raise CommandError(
                f"{len(missing)} curated gallery source file(s) are missing: {', '.join(sorted(set(missing)))}"
            )
        for source, row, rows in sources:
            panels = split_gallery(SOURCE_DIRECTORY / source, row, rows)
            if len(panels) != 3 or any(not panel for panel in panels):
                raise CommandError(f"{source} did not produce three usable product panels.")

    @staticmethod
    def _remove_stale_media(names, active_names):
        media_root = Path(settings.MEDIA_ROOT).resolve()
        removed = 0
        for name in names - active_names:
            candidate = (media_root / name).resolve()
            if media_root not in candidate.parents or not candidate.is_file():
                continue
            candidate.unlink()
            removed += 1
        return removed

    @staticmethod
    def _money(value):
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

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

    def handle(self, *args, **options):
        self._validate_sources()
        expected_pairs = {(item.category, item.subcategory) for item in CATALOG}
        expected_categories = {item.category for item in CATALOG}

        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Validated {len(CATALOG)} products, {len(CATALOG) * 2} colour variants, "
                    f"{len(expected_pairs)} subcategories, and {len(CATALOG) * 2 * 3} product images."
                )
            )
            return

        stale_media_names = set(
            ProductImage.objects.filter(variant__product__category__name__in=expected_categories)
            .exclude(image="")
            .values_list("image", flat=True)
        )
        stale_media_names.update(
            Category.objects.filter(name__in=expected_categories)
            .exclude(image="")
            .values_list("image", flat=True)
        )
        stale_media_names.update(
            SubCategory.objects.filter(category__name__in=expected_categories)
            .exclude(image="")
            .values_list("image", flat=True)
        )

        category_primary_images = {}
        subcategory_primary_images = {}
        with transaction.atomic():
            # Product deletion also removes variants, their image records, carts, and
            # wishlists that pointed to the removed catalog. There are no orders in
            # the current database, so no purchase history is affected.
            deletion_result = Product.objects.filter(
                category__name__in=expected_categories
            ).delete()
            deleted_products = deletion_result[1].get("myapp.Product", 0)

            products_by_code = {}
            for item in CATALOG:
                category, _ = Category.objects.get_or_create(name=item.category)
                category.is_active = True
                category.save(update_fields=("is_active",))
                subcategory, _ = SubCategory.objects.get_or_create(
                    category=category,
                    name=item.subcategory,
                )
                subcategory.is_active = True
                subcategory.save(update_fields=("is_active",))

                product = Product(
                    category=category,
                    subcategory=subcategory,
                    name=item.name,
                    description=item.description,
                    key_features=(
                        f"{item.subcategory} product\n"
                        "Two distinct colour variants\n"
                        "Three verified images per colour variant"
                    ),
                    shipping_fee="0.00",
                    estimated_delivery_time="3-5 business days",
                    seller_name=IMPORT_MARKER,
                    warranty_info="Seller warranty applies",
                    is_active=True,
                )
                product.full_clean()
                product.save()
                products_by_code[item.code] = product

                unit_type_name, unit_names = UNIT_OPTIONS[item.code]
                for color_index, (color_name, color_code, source, row, rows) in enumerate(
                    variant_specs(item)
                ):
                    color, _ = Color.objects.get_or_create(
                        name=color_name,
                        defaults={"code": color_code},
                    )
                    if color.code != color_code:
                        color.code = color_code
                        color.save(update_fields=("code",))
                    variant = ProductVariant(
                        product=product,
                        color=color,
                        sku=f"{item.code}-{slugify(color_name).upper()}",
                        price_type="multiple",
                        price=None,
                        stock=0,
                    )
                    variant.full_clean()
                    variant.save()

                    base_price = self._money(item.price)
                    for unit_index, unit_name in enumerate(unit_names):
                        unit_type, unit = self._ensure_unit(unit_type_name, unit_name)
                        price = self._money(
                            base_price
                            * (Decimal("1.00") + Decimal("0.15") * unit_index + Decimal("0.03") * color_index)
                        )
                        variant_unit = ProductVariantUnit(
                            variant=variant,
                            unit_type=unit_type,
                            unit=unit,
                            sku=(
                                f"{item.code}-{slugify(color_name).upper()}-"
                                f"{slugify(unit_name).upper()}"
                            ),
                            price=price,
                            stock=max(5, 25 - unit_index * 5 - color_index * 3),
                        )
                        variant_unit.full_clean()
                        variant_unit.save()
                    variant.stock = sum(unit.stock for unit in variant.sizes.all())
                    variant.save(update_fields=("stock",))

                    for position, panel in enumerate(
                        split_gallery(SOURCE_DIRECTORY / source, row, rows)
                    ):
                        product_image = ProductImage(
                            variant=variant,
                            position=position,
                            is_primary=position == 0,
                        )
                        filename = (
                            f"curated/{item.code.lower()}-{slugify(color_name)}-"
                            f"{position + 1}.png"
                        )
                        product_image.image.save(filename, ContentFile(panel), save=False)
                        product_image.save()
                        if position == 0:
                            category_primary_images.setdefault(category.id, product_image.image.name)
                            subcategory_primary_images[(category.id, subcategory.id)] = product_image.image.name

            for category_id, image_name in category_primary_images.items():
                Category.objects.filter(pk=category_id).update(image=image_name, is_active=True)
            for (_, subcategory_id), image_name in subcategory_primary_images.items():
                SubCategory.objects.filter(pk=subcategory_id).update(image=image_name, is_active=True)

            public_products = Product.objects.filter(category__name__in=expected_categories)
            if public_products.count() != len(CATALOG):
                raise CommandError("The resulting catalog does not contain the expected product count.")
            if public_products.exclude(category_id=F("subcategory__category_id")).exists():
                raise CommandError("A product was saved under the wrong category/subcategory pair.")
            variants = ProductVariant.objects.filter(product__in=public_products)
            if variants.count() != len(CATALOG) * 2:
                raise CommandError("Every curated product must have exactly two colour variants.")
            image_counts = [variant.images.count() for variant in variants]
            if not image_counts or any(count != 3 for count in image_counts):
                raise CommandError("Every curated colour variant must have exactly three images.")
            if any(variant.sizes.count() != 2 for variant in variants):
                raise CommandError("Every curated colour variant must have two product-specific options.")

        active_media_names = set(
            ProductImage.objects.filter(variant__product__category__name__in=expected_categories)
            .exclude(image="")
            .values_list("image", flat=True)
        )
        active_media_names.update(
            Category.objects.filter(name__in=expected_categories).exclude(image="").values_list("image", flat=True)
        )
        active_media_names.update(
            SubCategory.objects.filter(category__name__in=expected_categories).exclude(image="").values_list("image", flat=True)
        )
        removed_files = self._remove_stale_media(stale_media_names, active_media_names)
        self.stdout.write(
            self.style.SUCCESS(
                f"Curated catalog complete: removed {deleted_products} old products; "
                f"created {len(CATALOG)} correctly mapped products, "
                f"{len(CATALOG) * 2} colour variants, {len(CATALOG) * 2 * 2} buying options, "
                f"and {len(CATALOG) * 2 * 3} product images; "
                f"removed {removed_files} obsolete referenced media files."
            )
        )

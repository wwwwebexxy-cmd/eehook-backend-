"""Seed the marketplace catalog with the requested retail categories.

This script is intentionally idempotent. It keeps the existing category and
subcategory IDs used by the frontend, updates the placeholder catalog records
in place, and can be run again without creating duplicate products.
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")
django.setup()

from django.db import transaction

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


CATEGORY_IMAGES = {
    "Gaming Products": "categories/generated_gaming_products.png",
    "Smart Watches": "categories/generated_smart_watches.png",
    "Wearables": "categories/generated_wearables.png",
    "Cosmetics": "categories/generated_cosmetics.png",
    "Toys": "categories/generated_toys.png",
    "Other Products": "categories/generated_other_products.png",
}


UNIT_TYPE_ALIASES = {
    "Pack Size": "Pack",
}


SUBCATEGORIES = {
    "Gaming Products": ["Consoles", "Games", "Gaming Accessories"],
    "Smart Watches": ["Men", "Women", "Unisex"],
    "Wearables": ["Fitness Bands", "VR Headsets", "Smart Glasses"],
    "Cosmetics": ["Perfumes", "Skincare", "Makeup"],
    "Toys": ["Action Figures", "Board Games", "Educational"],
    "Other Products": ["Miscellaneous"],
}


def item(
    name,
    description,
    features,
    prices,
    units,
    unit_type,
    *,
    emi=False,
    emi_starting_price=None,
    warranty="6-month seller warranty",
    delivery="3-7 business days",
):
    return {
        "name": name,
        "description": description,
        "features": features,
        "prices": prices,
        "units": units,
        "unit_type": unit_type,
        "emi": emi,
        "emi_starting_price": emi_starting_price,
        "warranty": warranty,
        "delivery": delivery,
    }


PRODUCTS = {
    "Games": [
        item(
            "Neon Kart Racing Game",
            "A fast arcade racing experience with colorful tracks, local multiplayer, and quick sessions for game nights.",
            ["Local multiplayer support", "Bright arcade tracks", "Suitable for ages 10+"],
            [59.99, 79.99],
            ["Standard Edition", "Deluxe Edition"],
            "Game Edition",
            warranty="Digital product support for 30 days",
        ),
        item(
            "Shadow Realm Adventure Game",
            "Explore a richly imagined world, solve environmental puzzles, and build a story-driven adventure at your own pace.",
            ["Story-driven campaign", "Exploration and puzzle gameplay", "Single-player adventure"],
            [69.99, 89.99],
            ["Standard Edition", "Collector Edition"],
            "Game Edition",
            warranty="Digital product support for 30 days",
        ),
    ],
    "Gaming Accessories": [
        item(
            "Pulse RGB Gaming Headset",
            "A comfortable over-ear headset with clear positional audio, a flexible microphone, and adjustable lighting for desktop and console play.",
            ["50 mm audio drivers", "Noise-reducing boom microphone", "Breathable memory-foam cushions"],
            [54.99, 69.99],
            ["Single", "Headset + Stand"],
            "Pack Size",
        ),
        item(
            "Apex Wireless Gamepad",
            "A low-latency wireless controller with textured grips, responsive triggers, and a rechargeable battery for extended sessions.",
            ["Bluetooth and USB connectivity", "Rechargeable battery", "Dual vibration feedback"],
            [44.99, 59.99],
            ["Single", "Controller + Cable"],
            "Pack Size",
        ),
    ],
    "Men": [
        item(
            "Forge Active AMOLED Smartwatch",
            "A durable smartwatch for workdays and training, combining health tracking, call alerts, and a bright AMOLED display.",
            ["1.43-inch AMOLED display", "Heart-rate and sleep tracking", "Up to 10 days battery life"],
            [189.99, 219.99],
            ["40 mm", "44 mm"],
            "Watch Size",
            warranty="1-year seller warranty",
        ),
        item(
            "Summit Sport Smartwatch",
            "A lightweight GPS smartwatch with workout modes, route tracking, and a water-resistant case for active routines.",
            ["Built-in GPS", "100+ workout modes", "5 ATM water resistance"],
            [229.99, 259.99],
            ["40 mm", "44 mm"],
            "Watch Size",
            emi=True,
            emi_starting_price=39.99,
            warranty="1-year seller warranty",
        ),
    ],
    "Women": [
        item(
            "Luna Rose AMOLED Smartwatch",
            "An elegant smartwatch with wellness insights, message notifications, and a soft-touch strap designed for all-day wear.",
            ["1.32-inch AMOLED display", "Stress and cycle tracking", "Customizable watch faces"],
            [179.99, 209.99],
            ["40 mm", "44 mm"],
            "Watch Size",
            warranty="1-year seller warranty",
        ),
        item(
            "Aster Mini Smartwatch",
            "A compact everyday smartwatch with activity tracking, music controls, and a clear display in a slim case.",
            ["1.2-inch color display", "Activity and sleep tracking", "Magnetic charging"],
            [149.99, 179.99],
            ["38 mm", "42 mm"],
            "Watch Size",
            warranty="1-year seller warranty",
        ),
    ],
    "Unisex": [
        item(
            "Orbit Pro GPS Smartwatch",
            "A versatile GPS smartwatch with a bright display, training insights, and a rugged design for everyday adventures.",
            ["Dual-band GPS", "AMOLED always-on display", "Compass and elevation data"],
            [249.99, 279.99],
            ["40 mm", "44 mm"],
            "Watch Size",
            emi=True,
            emi_starting_price=44.99,
            warranty="1-year seller warranty",
        ),
        item(
            "Pulse Everyday Smartwatch",
            "A simple, reliable smartwatch for notifications, steps, heart-rate monitoring, and a full week of regular use.",
            ["Seven-day battery", "Heart-rate monitoring", "Android and iOS compatible"],
            [119.99, 139.99],
            ["40 mm", "44 mm"],
            "Watch Size",
            warranty="1-year seller warranty",
        ),
    ],
    "Fitness Bands": [
        item(
            "Stride Fit Fitness Band",
            "A slim fitness band that tracks daily movement, sleep, heart rate, and workouts without getting in the way.",
            ["Continuous heart-rate tracking", "Sleep and activity insights", "Up to 12 days battery life"],
            [49.99, 59.99],
            ["Small", "Large"],
            "Band Size",
            warranty="6-month seller warranty",
        ),
        item(
            "CoreTrack Health Band",
            "A comfortable health band with guided breathing, step goals, and an easy-to-read display for everyday wellness.",
            ["Blood-oxygen trend tracking", "Step and calorie goals", "Water-resistant design"],
            [39.99, 49.99],
            ["Small", "Large"],
            "Band Size",
            warranty="6-month seller warranty",
        ),
    ],
    "VR Headsets": [
        item(
            "Vista XR VR Headset",
            "A comfortable standalone virtual-reality headset with sharp lenses, room-scale tracking, and a balanced head strap.",
            ["High-resolution dual displays", "Inside-out tracking", "Adjustable facial interface"],
            [299.99, 349.99],
            ["128 GB", "256 GB"],
            "Storage",
            emi=True,
            emi_starting_price=49.99,
            warranty="1-year seller warranty",
        ),
        item(
            "Horizon Immersive VR Headset",
            "An extended-reality headset built for immersive gaming, virtual travel, and creative experiences with room for a growing library.",
            ["Wide field of view", "Spatial audio support", "Two motion controllers included"],
            [399.99, 449.99],
            ["128 GB", "256 GB"],
            "Storage",
            emi=True,
            emi_starting_price=64.99,
            warranty="1-year seller warranty",
        ),
    ],
    "Smart Glasses": [
        item(
            "Halo AR Smart Glasses",
            "Lightweight smart glasses with a discreet heads-up display, navigation cues, and hands-free notifications.",
            ["Tint-adjusting lenses", "Open-ear audio", "Hands-free voice controls"],
            [299.99, 349.99],
            ["Medium", "Large"],
            "Frame Size",
            emi=True,
            emi_starting_price=49.99,
            warranty="1-year seller warranty",
        ),
        item(
            "ClearView Audio Smart Glasses",
            "Everyday smart glasses with open-ear audio, hands-free calls, and a familiar frame shape for commuting and travel.",
            ["Open-ear stereo speakers", "Dual microphones", "UV-protective lenses"],
            [229.99, 269.99],
            ["Medium", "Large"],
            "Frame Size",
            emi=True,
            emi_starting_price=39.99,
            warranty="1-year seller warranty",
        ),
    ],
    "Perfumes": [
        item(
            "Amber Bloom Eau de Parfum",
            "A warm floral fragrance with amber, soft woods, and a gentle citrus opening for day-to-evening wear.",
            ["Eau de parfum concentration", "Floral amber profile", "Glass spray bottle"],
            [39.99, 59.99],
            ["50 ml", "100 ml"],
            "Volume",
            delivery="2-5 business days",
            warranty="Authenticity guarantee",
        ),
        item(
            "Cedar Mist Eau de Toilette",
            "A fresh woody fragrance layered with clean citrus and aromatic herbs in a lightweight everyday spray.",
            ["Fresh woody profile", "Eau de toilette concentration", "Travel-friendly atomizer"],
            [29.99, 44.99],
            ["50 ml", "100 ml"],
            "Volume",
            delivery="2-5 business days",
            warranty="Authenticity guarantee",
        ),
    ],
    "Skincare": [
        item(
            "Daily Dew Hydration Cream",
            "A lightweight face cream designed to replenish moisture and leave skin feeling soft without a heavy finish.",
            ["Hyaluronic-acid hydration", "Lightweight daily texture", "Suitable for normal and dry skin"],
            [24.99, 34.99],
            ["50 g", "100 g"],
            "Weight",
            delivery="2-5 business days",
            warranty="Sealed product guarantee",
        ),
        item(
            "Radiance C+ Face Serum",
            "A brightening facial serum with a smooth, fast-absorbing texture for a simple morning skincare routine.",
            ["Vitamin C formula", "Fast-absorbing serum", "Use with daily sunscreen"],
            [29.99, 44.99],
            ["30 ml", "60 ml"],
            "Volume",
            delivery="2-5 business days",
            warranty="Sealed product guarantee",
        ),
    ],
    "Makeup": [
        item(
            "Soft Glow Face Palette",
            "A compact face palette with blendable blush, highlight, and contour shades for an easy everyday look.",
            ["Blush, highlight, and contour pans", "Blendable pressed powder", "Mirror compact"],
            [27.99, 39.99],
            ["5 g", "10 g"],
            "Weight",
            delivery="2-5 business days",
            warranty="Sealed product guarantee",
        ),
        item(
            "Velvet Tint Lip Color",
            "A comfortable long-wear lip tint with buildable color and a soft velvet finish.",
            ["Buildable color", "Soft velvet finish", "Comfortable daily wear"],
            [14.99, 22.99],
            ["3 g", "6 g"],
            "Weight",
            delivery="2-5 business days",
            warranty="Sealed product guarantee",
        ),
    ],
    "Action Figures": [
        item(
            "Galaxy Ranger Collector Figure",
            "A poseable collector figure with articulated joints and a display stand for shelves, desks, and playrooms.",
            ["Articulated joints", "Display stand included", "Recommended for ages 8+"],
            [34.99, 49.99],
            ["1 piece", "2 piece"],
            "Pack Size",
            delivery="3-6 business days",
            warranty="Replacement for transit damage",
        ),
        item(
            "Mythic Dragon Action Figure",
            "A detailed fantasy dragon figure with movable wings and a sturdy sculpted base for imaginative play or display.",
            ["Movable wings", "Durable molded body", "Recommended for ages 6+"],
            [24.99, 39.99],
            ["1 piece", "2 piece"],
            "Pack Size",
            delivery="3-6 business days",
            warranty="Replacement for transit damage",
        ),
    ],
    "Board Games": [
        item(
            "Castle Quest Strategy Game",
            "A family strategy game of planning, resource gathering, and castle building for competitive game nights.",
            ["2-4 players", "45-minute play time", "Recommended for ages 10+"],
            [39.99, 54.99],
            ["1 set", "2 set"],
            "Pack Size",
            delivery="3-6 business days",
            warranty="Replacement for missing pieces",
        ),
        item(
            "Word Trail Family Game",
            "A quick word-building game that rewards vocabulary, pattern spotting, and creative play across generations.",
            ["2-6 players", "20-minute play time", "Recommended for ages 8+"],
            [24.99, 34.99],
            ["1 set", "2 set"],
            "Pack Size",
            delivery="3-6 business days",
            warranty="Replacement for missing pieces",
        ),
    ],
    "Educational": [
        item(
            "Build & Learn STEM Set",
            "A hands-on construction set that introduces simple machines, balance, and problem solving through guided builds.",
            ["Multiple guided builds", "Hands-on STEM learning", "Recommended for ages 8+"],
            [44.99, 59.99],
            ["1 set", "2 set"],
            "Pack Size",
            delivery="3-6 business days",
            warranty="Replacement for missing pieces",
        ),
        item(
            "Little Lab Discovery Kit",
            "A beginner-friendly science kit with safe experiments that make observation and discovery fun at home.",
            ["Child-friendly experiments", "Learning guide included", "Recommended for ages 7+"],
            [29.99, 39.99],
            ["1 set", "2 set"],
            "Pack Size",
            delivery="3-6 business days",
            warranty="Replacement for missing pieces",
        ),
    ],
    "Miscellaneous": [
        item(
            "ThermoSip Insulated Bottle",
            "A reusable insulated bottle that keeps drinks cool or warm for commutes, workouts, and day trips.",
            ["Double-wall insulation", "Leak-resistant lid", "BPA-free reusable body"],
            [19.99, 29.99],
            ["750 ml", "1 L"],
            "Volume",
            delivery="3-6 business days",
            warranty="6-month seller warranty",
        ),
        item(
            "DeskMate Organizer Set",
            "A practical desktop organizer set for keeping pens, cables, notes, and small accessories easy to reach.",
            ["Modular compartments", "Cable-friendly design", "Easy-clean surface"],
            [17.99, 27.99],
            ["1 set", "2 set"],
            "Pack Size",
            delivery="3-6 business days",
            warranty="6-month seller warranty",
        ),
    ],
}


def ensure_unit(unit_name, unit_type_name):
    unit_type_name = UNIT_TYPE_ALIASES.get(unit_type_name, unit_type_name)
    unit_type, _ = UnitType.objects.get_or_create(name=unit_type_name)
    unit = Unit.objects.filter(unit_type=unit_type, name=unit_name).first()
    if unit is None:
        unit = Unit.objects.filter(unit_type__isnull=True, name=unit_name).first()
    if unit is None:
        unit = Unit.objects.create(name=unit_name, unit_type=unit_type)
    elif unit.unit_type_id != unit_type.id:
        unit.unit_type = unit_type
        unit.save(update_fields=["unit_type"])
    return unit


def update_product(product, product_data, image_name, black, white):
    product.description = product_data["description"]
    product.key_features = "\n".join(product_data["features"])
    product.shipping_fee = 0
    product.estimated_delivery_time = product_data["delivery"]
    product.seller_name = "EEHook Marketplace"
    product.warranty_info = product_data["warranty"]
    product.emi_available = product_data["emi"]
    product.emi_starting_price = product_data["emi_starting_price"]
    product.is_active = True
    product.save()

    variants = list(ProductVariant.objects.filter(product=product).order_by("id"))
    while len(variants) < 2:
        variants.append(ProductVariant.objects.create(product=product, color=None))

    for variant, color in zip(variants[:2], (black, white)):
        duplicate = ProductVariant.objects.filter(
            product=product,
            color=color,
        ).exclude(pk=variant.pk).exists()
        if not duplicate:
            variant.color = color
        variant.price_type = "multiple"
        variant.price = None
        variant.stock = 30
        variant.save()

        unit_type = product_data["unit_type"]
        prepared_units = [
            ensure_unit(name, unit_type)
            for name in product_data["units"]
        ]
        existing_sizes = list(
            ProductVariantUnit.objects.filter(variant=variant).order_by("id")
        )
        for index, (unit, price) in enumerate(
            zip(prepared_units, product_data["prices"])
        ):
            if index < len(existing_sizes):
                size = existing_sizes[index]
                size.unit = unit
                size.unit_type = unit.unit_type
                size.price = price
                size.stock = 30
                size.save()
            else:
                ProductVariantUnit.objects.create(
                    variant=variant,
                    unit_type=unit.unit_type,
                    unit=unit,
                    price=price,
                    stock=30,
                )

    ProductImage.objects.filter(variant__product=product).delete()
    for variant in ProductVariant.objects.filter(product=product):
        ProductImage.objects.create(
            variant=variant,
            image=image_name,
            is_primary=True,
        )


@transaction.atomic
def seed_catalog():
    black, _ = Color.objects.get_or_create(
        name="Black", defaults={"code": "#000000"}
    )
    white, _ = Color.objects.get_or_create(
        name="White", defaults={"code": "#FFFFFF"}
    )

    updated_products = 0
    for category_name, subcategory_names in SUBCATEGORIES.items():
        category, _ = Category.objects.get_or_create(name=category_name)
        category.image.name = CATEGORY_IMAGES[category_name]
        category.is_active = True
        category.save(update_fields=["image", "is_active"])

        for subcategory_name in subcategory_names:
            subcategory, _ = SubCategory.objects.get_or_create(
                category=category,
                name=subcategory_name,
            )
            subcategory.image.name = CATEGORY_IMAGES[category_name]
            subcategory.is_active = True
            subcategory.save(update_fields=["image", "is_active"])

            for index, product_data in enumerate(
                PRODUCTS.get(subcategory_name, [])
            ):
                existing = list(
                    Product.objects.filter(
                        category=category,
                        subcategory=subcategory,
                    ).order_by("id")
                )
                if index < len(existing):
                    product = existing[index]
                    product.name = product_data["name"]
                    product.save(update_fields=["name"])
                else:
                    product = Product.objects.create(
                        category=category,
                        subcategory=subcategory,
                        name=product_data["name"],
                        description=product_data["description"],
                    )
                update_product(
                    product,
                    product_data,
                    CATEGORY_IMAGES[category_name].replace(
                        "categories/", "products/"
                    ),
                    black,
                    white,
                )
                updated_products += 1

    print(
        f"Catalog seeded: {len(SUBCATEGORIES)} categories, "
        f"{sum(len(value) for value in SUBCATEGORIES.values())} subcategories, "
        f"{updated_products} products updated."
    )


if __name__ == "__main__":
    seed_catalog()

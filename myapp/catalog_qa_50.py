"""Data and image-task definitions for the 50-item catalog test import."""

from django.utils.text import slugify


IMPORT_MARKER = "EEHook catalog import 2026-10"
IMAGE_DIRECTORY = "products/catalog_2026_10"

COLOR_CODES = {
    "Amber": "#F59E0B",
    "Berry": "#BE185D",
    "Black": "#111827",
    "Blue": "#2563EB",
    "Clear": "#E5E7EB",
    "Cream": "#FFF7ED",
    "Crimson": "#BE123C",
    "Graphite": "#374151",
    "Lime": "#65A30D",
    "Midnight": "#172554",
    "Navy": "#1E3A8A",
    "Rose": "#F472B6",
    "Sage": "#65A30D",
    "Sand": "#D6D3D1",
    "Silver": "#9CA3AF",
    "Starlight": "#FDE68A",
    "Titanium": "#6B7280",
    "Tortoise": "#78350F",
    "White": "#FFFFFF",
}


def product(
    code,
    category,
    subcategory,
    name,
    description,
    image_subject,
    *,
    kind,
    price,
    stock,
    unit_type=None,
    units=(),
    colors=(),
    detail=False,
):
    """Return one normalized catalog definition.

    Kinds are: ``plain``, ``units``, ``colors``, and ``color_units``.
    """
    if kind in {"units", "color_units"} and (not unit_type or not units):
        raise ValueError(f"{name} needs a unit type and at least one unit")
    if kind in {"colors", "color_units"} and len(colors) < 2:
        raise ValueError(f"{name} needs at least two colors")
    return {
        "code": f"CAT50-{code:03d}",
        "category": category,
        "subcategory": subcategory,
        "name": name,
        "description": description,
        "image_subject": image_subject,
        "kind": kind,
        "price": str(price),
        "stock": int(stock),
        "unit_type": unit_type,
        "units": tuple(units),
        "colors": tuple(colors),
        "detail": bool(detail),
    }


PRODUCTS = (
    product(1, "Electronics", "Mobiles", "Aster Nova 5G Smartphone", "A modern 5G smartphone with a vivid display, dependable battery life, and storage choices for everyday work and entertainment.", "modern 5G smartphone with a full-screen display and dual rear cameras", kind="color_units", price="32999.00", stock=34, unit_type="Storage", units=("128 GB", "256 GB"), colors=("Graphite", "Sage"), detail=True),
    product(2, "Electronics", "Mobiles", "Orbit Lite 5G Smartphone", "A compact 5G phone made for clear calls, fast apps, and comfortable one-hand use.", "compact 5G smartphone with a slim full-screen body", kind="colors", price="22999.00", stock=42, colors=("Black", "Blue")),
    product(3, "Electronics", "Laptop", "Zenith Core 14 Laptop", "A lightweight 14-inch laptop for study, office work, browsing, and everyday creative projects.", "thin 14-inch productivity laptop, open at a slight angle", kind="units", price="64999.00", stock=22, unit_type="Storage", units=("512 GB", "1 TB")),
    product(4, "Electronics", "Laptop", "Vector Air 15 Laptop", "A balanced 15-inch notebook with a spacious display and reliable performance for home and office use.", "sleek 15-inch silver laptop on a clean studio surface", kind="plain", price="52999.00", stock=18),
    product(5, "Apple Products", "iphone", "Lumina Pro Smartphone", "A premium smartphone with a refined metal finish, advanced camera system, and generous storage options.", "premium smartphone with three rear cameras and an edge-to-edge display", kind="color_units", price="89999.00", stock=16, unit_type="Storage", units=("256 GB", "512 GB"), colors=("Titanium", "Midnight")),
    product(6, "Apple Products", "iphone", "Lumina Compact Smartphone", "A compact smartphone that combines a bright display, dependable cameras, and day-long power.", "compact premium smartphone shown front and back", kind="plain", price="53999.00", stock=25),
    product(7, "Apple Products", "IPad", "Canvas Tab 11", "An 11-inch tablet designed for notes, video, drawing, and effortless everyday browsing.", "11-inch tablet with a clean colorful abstract screen and slim stylus", kind="units", price="42999.00", stock=20, unit_type="Storage", units=("128 GB", "256 GB")),
    product(8, "Apple Products", "IPad", "Studio Tab 13", "A large-screen tablet for illustration, streaming, and multitasking with a lightweight design.", "large 13-inch tablet with a slim aluminum frame and stylus", kind="colors", price="58999.00", stock=17, colors=("Silver", "Blue")),
    product(9, "Apple Products", "MacBook", "AeroBook 13 Notebook", "A portable 13-inch notebook with responsive performance for work, study, and travel.", "ultra-thin 13-inch notebook computer, open on a white studio background", kind="units", price="69999.00", stock=15, unit_type="Storage", units=("512 GB", "1 TB")),
    product(10, "Apple Products", "MacBook", "CreatorBook 16 Notebook", "A high-performance 16-inch notebook built for photo work, editing, and demanding daily tasks.", "powerful 16-inch creator laptop with a vivid display", kind="plain", price="94999.00", stock=10),
    product(11, "Apple Products", "Iwatches", "Pulse Arc Smartwatch", "A connected smartwatch with activity tracking, call alerts, and a bright always-on display.", "round premium smartwatch with a smooth silicone band", kind="color_units", price="17999.00", stock=32, unit_type="Watch Size", units=("40 mm", "44 mm"), colors=("Starlight", "Midnight"), detail=True),
    product(12, "Apple Products", "Iwatches", "Tempo Mini Smartwatch", "A compact smartwatch for steps, notifications, sleep tracking, and daily movement goals.", "small rectangular smartwatch with a soft sport band", kind="plain", price="11999.00", stock=38),
    product(13, "Apple Products", "Accessories", "MagDock Wireless Charger", "A magnetic wireless charging stand with a stable base for phones and compatible earbuds.", "minimal magnetic wireless charging stand with an unbranded smartphone", kind="colors", price="3499.00", stock=55, colors=("White", "Graphite")),
    product(14, "Apple Products", "Accessories", "ShieldLink USB-C Cable Set", "A durable USB-C cable set with reinforced connectors for charging, syncing, and travel.", "coiled USB-C charging cable set with two neat connectors", kind="plain", price="1299.00", stock=80),
    product(15, "Gaming Products", "Consoles", "NovaBox Game Console", "A compact living-room game console with fast loading, wireless controllers, and flexible storage.", "modern game console with one wireless controller beside it", kind="units", price="39999.00", stock=14, unit_type="Storage", units=("512 GB", "1 TB")),
    product(16, "Gaming Products", "Consoles", "PocketPlay Retro Console", "A handheld retro game console with a bright display, responsive controls, and a travel-friendly shell.", "handheld retro gaming console with colorful controls", kind="plain", price="8999.00", stock=30),
    product(17, "Gaming Products", "Games", "Skyforge Racing Deluxe", "An arcade racing game with fast tracks, vehicle upgrades, and local multiplayer sessions.", "stylized racing game box art with a futuristic sports car", kind="plain", price="2499.00", stock=45),
    product(18, "Gaming Products", "Games", "Mystic Isles Adventure", "A story-driven exploration game featuring puzzles, quests, and an expansive fantasy world.", "fantasy adventure game box art with a distant island and explorer", kind="plain", price="2799.00", stock=40),
    product(19, "Gaming Products", "Gaming Accessories", "Atlas Pro Gaming Headset", "An over-ear gaming headset with soft cushions, a flexible microphone, and detailed positional sound.", "premium over-ear gaming headset with detachable boom microphone", kind="colors", price="4599.00", stock=37, colors=("Black", "White")),
    product(20, "Gaming Products", "Gaming Accessories", "Vector Wireless Controller", "A responsive wireless controller with textured grips and a charging-ready rechargeable battery.", "wireless game controller in a clean product photography setup", kind="units", price="3799.00", stock=45, unit_type="Pack Size", units=("Single", "Controller + Dock")),
    product(21, "Smart Watches", "Men", "Summit X1 Sport Watch", "A rugged sport watch with GPS-style activity tools, heart-rate tracking, and a water-resistant case.", "rugged round men's sport smartwatch with a textured band", kind="color_units", price="15999.00", stock=28, unit_type="Watch Size", units=("42 mm", "46 mm"), colors=("Black", "Navy"), detail=True),
    product(22, "Smart Watches", "Men", "Ridge Active Watch", "An everyday activity watch with workout modes, notification support, and a long-lasting battery.", "round active smartwatch with a durable dark strap", kind="units", price="12499.00", stock=31, unit_type="Watch Size", units=("40 mm", "44 mm")),
    product(23, "Smart Watches", "Women", "Luna Petal Smartwatch", "An elegant wellness smartwatch with message alerts, sleep insights, and a slim comfortable strap.", "elegant slim smartwatch with a refined rounded case", kind="colors", price="13999.00", stock=29, colors=("Rose", "Cream")),
    product(24, "Smart Watches", "Women", "Aura Mini Watch", "A compact daily smartwatch for reminders, movement goals, and clear health summaries.", "small elegant square smartwatch with a soft pastel band", kind="plain", price="9999.00", stock=35),
    product(25, "Smart Watches", "Unisex", "Horizon GPS Watch", "A versatile GPS watch with training insights, route support, and a bright outdoor-readable display.", "unisex GPS smartwatch with a round bezel and sport strap", kind="units", price="18999.00", stock=26, unit_type="Watch Size", units=("42 mm", "46 mm")),
    product(26, "Smart Watches", "Unisex", "Orbit Daylight Watch", "A reliable unisex smartwatch with clear notifications, step tracking, and week-long battery life.", "unisex square smartwatch with a clean bright display", kind="plain", price="10999.00", stock=34),
    product(27, "Wearables", "Fitness Bands", "CorePulse Fitness Band", "A lightweight fitness band that tracks movement, heart rate, sleep, and everyday wellness goals.", "slim fitness tracker band with a small vertical display", kind="color_units", price="4999.00", stock=48, unit_type="Band Size", units=("Small", "Large"), colors=("Black", "Berry")),
    product(28, "Wearables", "Fitness Bands", "MoveTrack Lite Band", "A simple activity band with an easy-to-read display and long battery life for all-day use.", "minimal fitness band in a white studio product shot", kind="units", price="3699.00", stock=52, unit_type="Band Size", units=("Small", "Large")),
    product(29, "Wearables", "VR Headsets", "Vista One VR Headset", "A comfortable standalone VR headset with immersive lenses, spatial audio, and storage for a growing library.", "modern standalone virtual reality headset with two compact controllers", kind="units", price="29999.00", stock=18, unit_type="Storage", units=("128 GB", "256 GB")),
    product(30, "Wearables", "VR Headsets", "Horizon XR Headset", "An extended-reality headset with a balanced fit, sharp visuals, and intuitive room-scale controls.", "sleek mixed reality headset with a smooth visor", kind="colors", price="37999.00", stock=15, colors=("White", "Black")),
    product(31, "Wearables", "Smart Glasses", "ClearRoute Smart Glasses", "Smart glasses with navigation prompts, open-ear audio, and a familiar lightweight frame shape.", "smart glasses with subtle open-ear audio arms and clear lenses", kind="color_units", price="24999.00", stock=19, unit_type="Frame Size", units=("Medium", "Large"), colors=("Black", "Tortoise"), detail=True),
    product(32, "Wearables", "Smart Glasses", "Echo Lens Audio Glasses", "Everyday audio glasses with discreet speakers, clear calls, and UV-protective lenses.", "modern audio glasses with slim temples and tinted lenses", kind="plain", price="19999.00", stock=22),
    product(33, "Cosmetics", "Perfumes", "Ember Coast Eau de Parfum", "A warm floral fragrance with amber, soft woods, and a fresh citrus opening for day-to-evening wear.", "luxury unbranded glass perfume bottle with amber liquid", kind="units", price="2499.00", stock=46, unit_type="Volume", units=("50 ml", "100 ml")),
    product(34, "Cosmetics", "Perfumes", "Citrus Night Eau de Toilette", "A fresh woody fragrance layered with bright citrus and aromatic herbs in a lightweight daily spray.", "sleek unbranded eau de toilette bottle with a citrus-toned liquid", kind="plain", price="1899.00", stock=51),
    product(35, "Cosmetics", "Skincare", "CalmCloud Face Moisturizer", "A gentle face moisturizer with a lightweight texture for a soft, hydrated everyday finish.", "minimal unbranded face moisturizer jar and cream swirl", kind="units", price="899.00", stock=65, unit_type="Weight", units=("50 g", "100 g")),
    product(36, "Cosmetics", "Skincare", "GlowDrop Vitamin C Serum", "A brightening facial serum in a glass dropper bottle with a quick-absorbing daily formula.", "unbranded amber vitamin C serum dropper bottle with a small pipette", kind="plain", price="1099.00", stock=58),
    product(37, "Cosmetics", "Makeup", "Velvet Muse Lip Color", "A comfortable long-wear lip color with buildable pigment and a soft velvet finish.", "unbranded premium lip color tube with a doe-foot applicator", kind="colors", price="699.00", stock=70, colors=("Crimson", "Rose")),
    product(38, "Cosmetics", "Makeup", "Satin Glow Compact", "A travel-friendly face compact with smooth blendable powder for an even everyday glow.", "open unbranded makeup compact with pressed powder and mirror", kind="units", price="999.00", stock=57, unit_type="Weight", units=("8 g", "16 g")),
    product(39, "Toys", "Action Figures", "Astro Ranger Action Figure", "A poseable space explorer action figure with articulated joints and a sturdy display base.", "detailed poseable space explorer action figure on a small display stand", kind="units", price="1499.00", stock=44, unit_type="Pack Size", units=("1 Piece", "2 Piece")),
    product(40, "Toys", "Action Figures", "Forest Guardian Figure", "A collectible fantasy guardian figure with detailed armor, a removable staff, and a display-ready base.", "detailed fantasy guardian collectible figure with staff", kind="plain", price="1699.00", stock=39),
    product(41, "Toys", "Board Games", "Harbor Traders Board Game", "A family strategy board game about trading, route planning, and building a thriving harbor town.", "family strategy board game box with colorful tokens and board pieces", kind="plain", price="1299.00", stock=50),
    product(42, "Toys", "Board Games", "Questbound Strategy Game", "A cooperative strategy game with quests, map tiles, and replayable scenarios for game nights.", "cooperative fantasy strategy board game box with map tiles", kind="units", price="1599.00", stock=43, unit_type="Game Edition", units=("Standard", "Deluxe")),
    product(43, "Toys", "Educational", "Buildwise Robotics Kit", "A hands-on robotics kit introducing sensors, simple circuits, and guided coding challenges.", "educational robotics kit with small robot parts and colorful blocks", kind="units", price="2199.00", stock=36, unit_type="Pack Size", units=("Starter", "Advanced")),
    product(44, "Toys", "Educational", "Junior Science Lab Set", "A child-friendly science set with safe experiment tools, illustrated guides, and reusable containers.", "children's science experiment kit with colorful safe lab tools", kind="plain", price="1399.00", stock=48),
    product(45, "Other Products", "Miscellaneous", "ThermalPeak Travel Bottle", "A reusable insulated travel bottle that keeps drinks cool or warm for commutes, workouts, and day trips.", "sleek stainless steel insulated water bottle with a leak-proof cap", kind="units", price="799.00", stock=68, unit_type="Volume", units=("750 ml", "1 L")),
    product(46, "Other Products", "Miscellaneous", "CableNest Desk Organizer", "A modular desk organizer for cables, pens, notes, and small work essentials.", "minimal modular desk organizer with compartments and neatly arranged pens", kind="plain", price="649.00", stock=62),
    product(47, "vegetables", "Vegetables", "Garden Fresh Baby Spinach", "Tender baby spinach leaves, freshly packed for salads, smoothies, and quick everyday cooking.", "fresh baby spinach leaves in an unbranded kraft produce bag", kind="units", price="79.00", stock=95, unit_type="Weight", units=("250 g", "500 g")),
    product(48, "vegetables", "Vegetables", "Sunrise Cherry Tomatoes", "Sweet, ripe cherry tomatoes selected for salads, roasting, snacks, and bright everyday meals.", "fresh red cherry tomatoes in a simple unbranded produce tray", kind="plain", price="99.00", stock=88),
    product(49, "Footwear", "Crocs", "Drift Comfort Clogs", "Lightweight everyday clogs with cushioned support, breathable vents, and an easy slip-on fit.", "modern lightweight comfort clogs with ventilation holes", kind="color_units", price="2499.00", stock=44, unit_type="Footwear Size", units=("7", "8", "9"), colors=("Black", "Sand"), detail=True),
    product(50, "Footwear", "Crocs", "Trail Breeze Clogs", "Flexible outdoor clogs with a textured sole, quick-dry finish, and a comfortable adjustable heel strap.", "sporty outdoor comfort clogs with an adjustable heel strap", kind="color_units", price="2699.00", stock=40, unit_type="Footwear Size", units=("7", "8", "9"), colors=("Navy", "Lime")),
)


def image_filename(item, color=None, detail=False):
    suffix = "-detail" if detail else ""
    color_part = f"-{slugify(color)}" if color else ""
    return f"{IMAGE_DIRECTORY}/{item['code'].lower()}{color_part}{suffix}.png"


def variant_image_map(item):
    """Map a color (or None) to that variant's image files."""
    if item["kind"] in {"colors", "color_units"}:
        # A product's primary image belongs to its first color variant.  The
        # remaining color variants are still fully configured and priced, but
        # no image file is reused between variants or products.
        images = {color: [] for color in item["colors"]}
        primary_color = item["colors"][0]
        images[primary_color] = [image_filename(item, primary_color)]
        if item["detail"]:
            images[primary_color].append(
                image_filename(item, primary_color, detail=True)
            )
        return images
    images = {None: [image_filename(item)]}
    if item["detail"]:
        images[None].append(image_filename(item, detail=True))
    return images


def image_prompt(item, color=None, detail=False):
    color_phrase = f" in {color}" if color else ""
    framing = (
        "a close three-quarter detail view that still shows the full product"
        if detail
        else "a centered square product shot with the full item visible"
    )
    return "\n".join(
        (
            "Use case: product-mockup",
            "Asset type: e-commerce catalog image",
            f"Primary request: {item['image_subject']}{color_phrase}",
            "Scene/backdrop: a seamless warm-white studio background",
            "Style/medium: photorealistic commercial product photography",
            f"Composition/framing: {framing}, no crop",
            "Lighting/mood: soft, even studio lighting with a natural shadow",
            "Constraints: one matching product only, no people, no brand logos, no readable packaging text, no watermark",
        )
    )


def image_tasks():
    """Return every workspace-bound generated image task in stable order."""
    tasks = []
    for item in PRODUCTS:
        for color, filenames in variant_image_map(item).items():
            for index, filename in enumerate(filenames):
                tasks.append(
                    {
                        "code": item["code"],
                        "name": item["name"],
                        "filename": filename,
                        "prompt": image_prompt(item, color, detail=index > 0),
                    }
                )
    return tasks


if len(PRODUCTS) != 50:
    raise AssertionError("The catalog import must define exactly 50 products.")
if len({item["code"] for item in PRODUCTS}) != len(PRODUCTS):
    raise AssertionError("Catalog product codes must be unique.")
if len({task["filename"] for task in image_tasks()}) != len(image_tasks()):
    raise AssertionError("Catalog image filenames must be unique.")

"""Extend the demo catalog to eleven categories without duplicating records."""

from .catalog_qa_50 import COLOR_CODES, IMPORT_MARKER, PRODUCTS, product


EXTRA_PRODUCTS = (
    product(
        51,
        "Audio Products",
        "Headphones",
        "StudioFlow Wireless Headphones",
        "Comfortable wireless over-ear headphones with clear sound, a flexible microphone, and a travel-ready foldable design.",
        "premium over-ear wireless headphones in a clean product photograph",
        kind="colors",
        price="3499.00",
        stock=42,
        colors=("Black", "White"),
    ),
    product(
        52,
        "Audio Products",
        "Cables",
        "LinkCore USB-C Cable",
        "A durable braided USB-C cable for charging and syncing phones, tablets, laptops, and everyday accessories.",
        "braided USB-C charging cable with reinforced connectors",
        kind="units",
        price="499.00",
        stock=80,
        unit_type="Cable Length",
        units=("1 m", "2 m"),
    ),
)


PRODUCTS_11 = PRODUCTS + EXTRA_PRODUCTS

if len(PRODUCTS_11) != 52:
    raise AssertionError("The eleven-category demo catalog must define 52 products.")
if len({item["code"] for item in PRODUCTS_11}) != len(PRODUCTS_11):
    raise AssertionError("Demo catalog product codes must be unique.")


__all__ = ("COLOR_CODES", "IMPORT_MARKER", "PRODUCTS_11")

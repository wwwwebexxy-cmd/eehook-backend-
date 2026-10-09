"""Download web-sourced promotional imagery and attach it to every product.

The source pages are kept beside each direct download URL so the assets can be
reviewed or replaced later. Images are grouped by product category because a
promotional banner is a category-level visual rather than the product's main
catalog photograph.
"""

import os
from pathlib import Path

import django
import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")
django.setup()

from django.conf import settings

from myapp.models import Product


BANNERS = {
    "electronics": {
        "filename": "electronics-public-domain.jpg",
        "url": "https://c.pxhere.com/photos/5f/7e/apple_computer_notebook_technology_laptop_screen_electronics_publicdomain-103006.jpg!d",
        "source": "https://pxhere.com/en/photo/103006",
    },
    "gaming": {
        "filename": "gaming-controller-cc0.jpg",
        "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Dark_Xbox_controller_(Unsplash).jpg?width=1600",
        "source": "https://commons.wikimedia.org/wiki/File:Dark_Xbox_controller_(Unsplash).jpg",
    },
    "smart-watches": {
        "filename": "smartwatch-unsplash.jpg",
        "url": "https://images.unsplash.com/photo-1624096104992-9b4fa3a279dd?auto=format&fit=crop&w=1600&q=85",
        "source": "https://unsplash.com/photos/black-smart-watch-with-white-background-O43D6CYzxqM",
    },
    "wearables": {
        "filename": "vr-headset-public-domain.jpg",
        "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Oculus-Rift-CV1-Headset-Front.jpg?width=1600",
        "source": "https://commons.wikimedia.org/wiki/File:Oculus-Rift-CV1-Headset-Front.jpg",
    },
    "cosmetics": {
        "filename": "perfume-bottle-public-domain.jpg",
        "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Perfume_Bottle.jpg?width=1200",
        "source": "https://commons.wikimedia.org/wiki/File:Perfume_Bottle.jpg",
    },
    "toys": {
        "filename": "toy-cc0.jpg",
        "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Toy.jpg?width=1600",
        "source": "https://commons.wikimedia.org/wiki/File:Toy.jpg",
    },
    "other-products": {
        "filename": "water-bottle-cc0.jpg",
        "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Bottle_of_Water.jpg?width=1600",
        "source": "https://commons.wikimedia.org/wiki/File:Bottle_of_Water.jpg",
    },
}


CATEGORY_BANNER_KEYS = {
    "Electronics": "electronics",
    "Apple Products": "electronics",
    "Gaming Products": "gaming",
    "Smart Watches": "smart-watches",
    "Wearables": "wearables",
    "Cosmetics": "cosmetics",
    "Toys": "toys",
    "Other Products": "other-products",
}


def download_banner(key, banner):
    destination = Path(settings.MEDIA_ROOT) / "promotional_banners" / banner["filename"]
    destination.parent.mkdir(parents=True, exist_ok=True)

    response = requests.get(
        banner["url"],
        headers={"User-Agent": "EEHook catalog banner importer/1.0"},
        timeout=45,
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("image/"):
        raise RuntimeError(
            f"{key} returned {content_type or 'an unknown content type'}"
        )

    destination.write_bytes(response.content)
    return destination


def seed_promotional_banners():
    downloaded = {
        key: download_banner(key, banner)
        for key, banner in BANNERS.items()
    }

    updated = 0
    for product in Product.objects.select_related("category").all():
        key = CATEGORY_BANNER_KEYS.get(product.category.name)
        if not key:
            continue
        product.promotional_banner_image.name = (
            f"promotional_banners/{BANNERS[key]['filename']}"
        )
        product.save(update_fields=["promotional_banner_image"])
        updated += 1

    print(f"Downloaded {len(downloaded)} promotional banner images.")
    print(f"Attached promotional banners to {updated} products.")
    for key, banner in BANNERS.items():
        print(f"{key}: {banner['source']}")


if __name__ == "__main__":
    seed_promotional_banners()

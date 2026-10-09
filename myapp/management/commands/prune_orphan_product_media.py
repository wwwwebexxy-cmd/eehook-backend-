"""Safely remove product-media files that are no longer referenced by the catalog."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from myapp.models import ProductImage


class Command(BaseCommand):
    help = "List or remove unreferenced files in MEDIA_ROOT/products."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Delete the listed orphaned files. Omit for a read-only report.",
        )

    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT).resolve()
        product_root = (media_root / "products").resolve()
        if media_root not in product_root.parents or not product_root.is_dir():
            raise CommandError("The resolved products media directory is not safe to prune.")

        active_names = {
            product_image.image.name.replace("\\", "/")
            for product_image in ProductImage.objects.exclude(image="")
        }
        source_prefix = "products/curated/source/"
        orphaned = []
        for candidate in product_root.rglob("*"):
            if not candidate.is_file():
                continue
            resolved = candidate.resolve()
            if product_root not in resolved.parents:
                raise CommandError(f"Unsafe media path encountered: {candidate}")
            relative_name = resolved.relative_to(media_root).as_posix()
            if relative_name in active_names or relative_name.startswith(source_prefix):
                continue
            orphaned.append(resolved)

        size = sum(candidate.stat().st_size for candidate in orphaned)
        action = "Would remove" if not options["apply"] else "Removing"
        self.stdout.write(f"{action} {len(orphaned)} orphaned product-media files ({size} bytes).")
        if not options["apply"]:
            for candidate in orphaned[:20]:
                self.stdout.write(candidate.relative_to(media_root).as_posix())
            return

        for candidate in orphaned:
            candidate.unlink()
        self.stdout.write(self.style.SUCCESS(f"Removed {len(orphaned)} orphaned product-media files."))

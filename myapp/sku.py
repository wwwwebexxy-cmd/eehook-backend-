"""SKU generation and order-item SKU resolution helpers."""


def _unique_sku(model, base, instance=None):
    """Return a SKU that is unused by the supplied model."""
    candidate = base
    suffix = 2
    queryset = model.objects.all()
    if instance and instance.pk:
        queryset = queryset.exclude(pk=instance.pk)
    while queryset.filter(sku=candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def assign_generated_variant_sku(variant):
    if variant.sku:
        return variant.sku
    from .models import ProductVariant

    variant.sku = _unique_sku(ProductVariant, f"EHK-V-{variant.pk:06d}", variant)
    variant.save(update_fields=("sku",))
    return variant.sku


def assign_generated_variant_unit_sku(unit):
    if unit.sku:
        return unit.sku
    from .models import ProductVariantUnit

    unit.sku = _unique_sku(ProductVariantUnit, f"EHK-U-{unit.pk:06d}", unit)
    unit.save(update_fields=("sku",))
    return unit.sku


def resolve_order_item_sku(item):
    """Resolve the sellable unit SKU recorded for an order item."""
    variant_unit = getattr(item, "variant_unit", None)
    if variant_unit and variant_unit.sku:
        return str(variant_unit.sku).strip()

    product = getattr(item, "product", None)
    if not product:
        return None

    variants = product.variants
    variant = variants.filter(color_id=item.color_id).first() if item.color_id else None
    variant = variant or variants.filter(color__isnull=True).first() or variants.first()
    return str(variant.sku).strip() if variant and variant.sku else None

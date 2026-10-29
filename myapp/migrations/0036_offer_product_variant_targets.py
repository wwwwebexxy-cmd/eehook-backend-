from django.db import migrations, models


def backfill_offer_products(apps, schema_editor):
    Offer = apps.get_model("myapp", "Offer")
    Product = apps.get_model("myapp", "Product")
    for product in Product.objects.exclude(offer_id=None).only("id", "offer_id"):
        offer = Offer.objects.get(pk=product.offer_id)
        offer.products.add(product)


class Migration(migrations.Migration):
    dependencies = [
        ("myapp", "0035_address_emirate"),
    ]

    operations = [
        migrations.AddField(
            model_name="offer",
            name="products",
            field=models.ManyToManyField(
                blank=True,
                related_name="offers",
                to="myapp.product",
            ),
        ),
        migrations.AddField(
            model_name="offer",
            name="variants",
            field=models.ManyToManyField(
                blank=True,
                related_name="offers",
                to="myapp.productvariant",
            ),
        ),
        migrations.RunPython(backfill_offer_products, migrations.RunPython.noop),
    ]

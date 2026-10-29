from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("myapp", "0036_offer_product_variant_targets"),
    ]

    operations = [
        migrations.AddField(
            model_name="productvariantunit",
            name="grade",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]

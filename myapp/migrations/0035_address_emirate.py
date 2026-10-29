from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("myapp", "0034_offer_discount_type_and_fixed_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="address",
            name="emirate",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]

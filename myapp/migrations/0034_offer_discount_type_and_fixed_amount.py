from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("myapp", "0033_welcomebonus_subcategory"),
    ]

    operations = [
        migrations.AddField(
            model_name="offer",
            name="discount_type",
            field=models.CharField(
                choices=[("PERCENTAGE", "Percentage"), ("FIXED", "Fixed Amount")],
                default="PERCENTAGE",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="offer",
            name="fixed_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="offer",
            name="discount_percentage",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="offer",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        discount_type="PERCENTAGE",
                        discount_percentage__gt=0,
                        discount_percentage__lte=100,
                        fixed_amount__isnull=True,
                    )
                    | models.Q(
                        discount_type="FIXED",
                        discount_percentage__isnull=True,
                        fixed_amount__gt=0,
                    )
                ),
                name="myapp_offer_valid_discount",
            ),
        ),
    ]

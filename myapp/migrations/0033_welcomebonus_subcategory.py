from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("myapp", "0032_order_payment_method"),
    ]

    operations = [
        migrations.AddField(
            model_name="welcomebonus",
            name="subcategory",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="welcome_bonuses",
                to="myapp.subcategory",
            ),
        ),
    ]

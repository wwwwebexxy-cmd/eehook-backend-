from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("myapp", "0031_producthighlight_text_color_productmessage_text_color"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("Cashfree", "Cashfree"),
                    ("Stripe", "Stripe"),
                    ("COD", "Cash on Delivery"),
                    ("WHATSAPP", "WhatsApp"),
                ],
                default="Cashfree",
                max_length=20,
            ),
        ),
    ]

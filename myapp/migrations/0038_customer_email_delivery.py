from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("myapp", "0037_productvariantunit_grade"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="registration_email_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="order_confirmation_email_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="paid_invoice_email_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

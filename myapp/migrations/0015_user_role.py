from django.db import migrations, models


def promote_existing_superusers(apps, schema_editor):
    User = apps.get_model("myapp", "User")
    User.objects.filter(is_superuser=True).update(role="Super Admin")


class Migration(migrations.Migration):

    dependencies = [
        ("myapp", "0014_rename_quantity_productvariant_stock"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[("Customer", "Customer"), ("Super Admin", "Super Admin")],
                default="Customer",
                max_length=20,
            ),
        ),
        migrations.RunPython(promote_existing_superusers, migrations.RunPython.noop),
    ]

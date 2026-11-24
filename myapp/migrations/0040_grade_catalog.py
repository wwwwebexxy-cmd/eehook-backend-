from django.db import migrations, models


def seed_existing_grades(apps, schema_editor):
    Grade = apps.get_model("myapp", "Grade")
    ProductVariant = apps.get_model("myapp", "ProductVariant")
    ProductVariantUnit = apps.get_model("myapp", "ProductVariantUnit")

    names = set()
    for option_values in ProductVariant.objects.values_list("option_values", flat=True).iterator():
        if isinstance(option_values, dict):
            name = str(option_values.get("grade") or "").strip()
            if name:
                names.add(name)

    for name in ProductVariantUnit.objects.exclude(grade="").values_list("grade", flat=True).iterator():
        name = str(name or "").strip()
        if name:
            names.add(name)

    Grade.objects.bulk_create(
        [Grade(name=name) for name in sorted(names)],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("myapp", "0039_alter_productvariant_unique_together_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Grade",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100, unique=True)),
            ],
            options={"ordering": ("name", "id")},
        ),
        migrations.RunPython(seed_existing_grades, migrations.RunPython.noop),
    ]

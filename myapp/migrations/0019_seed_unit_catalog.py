from django.db import migrations


UNIT_CATALOG = {
    "Weight": ["KG", "Gram", "MG", "Ton"],
    "Volume": ["Liter", "ML"],
    "Length": ["Meter", "CM", "MM", "KM"],
    "Area": ["Sq. Meter", "Sq. Feet", "Sq. Inch"],
    "Quantity": ["Piece", "Unit", "Item"],
    "Count": ["Pair", "Dozen", "Set"],
    "Pack": ["Pack", "Box", "Carton", "Bundle"],
    "Storage": ["KB", "MB", "GB", "TB"],
    "Time": ["Second", "Minute", "Hour", "Day"],
    "Temperature": ["°C", "°F"],
    "Capacity": ["mAh", "Ah"],
    "Power": ["W", "KW"],
    "Energy": ["Wh", "KWh"],
    "Dimension": ["Inch", "CM", "MM"],
    "Screen Size": ["Inch"],
    "Clothing Size": ["XS", "S", "M", "L", "XL", "XXL"],
    "Shoe Size": ["EU", "UK", "US"],
    "Band Size": ["S", "M", "L", "XL"],
    "Frame Size": ["Small", "Medium", "Large"],
    "Watch Size": ["38mm", "40mm", "42mm", "44mm"],
    "Game Edition": ["Standard", "Deluxe", "Collector's"],
    "Storage Capacity": ["64GB", "128GB", "256GB", "512GB", "1TB"],
}


def seed_unit_catalog(apps, schema_editor):
    UnitType = apps.get_model("myapp", "UnitType")
    Unit = apps.get_model("myapp", "Unit")
    for type_name, unit_names in UNIT_CATALOG.items():
        unit_type, _ = UnitType.objects.get_or_create(name=type_name)
        for unit_name in unit_names:
            Unit.objects.get_or_create(unit_type=unit_type, name=unit_name)


class Migration(migrations.Migration):
    dependencies = [("myapp", "0018_alter_productimage_options_productimage_position_and_more")]

    operations = [
        migrations.RunPython(seed_unit_catalog, migrations.RunPython.noop),
    ]

import os
import re

file_path = r'd:\eehook\myapp\serializers.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace serializers keys
content = re.sub(r'\bvariant_unit\s*=\s*serializers\.', 'variant_size = serializers.', content)
content = re.sub(r'\bunit\s*=\s*serializers\.', 'size = serializers.', content)

# Fix SizeSerializer to UnitSerializer
content = re.sub(r'\bSizeSerializer\b', 'UnitSerializer', content)
content = re.sub(r'\bProductVariantSizeSerializer\b', 'ProductVariantUnitSerializer', content)

# In ProductVariantUnitSerializer, map unit to size
content = re.sub(r'\bunit\s*=\s*UnitSerializer\(', 'size = UnitSerializer(source="unit", ', content)

# Update fields lists
content = re.sub(r'"variant_unit"', '"variant_size"', content)
content = re.sub(r'"unit"', '"size"', content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated serializers.py")

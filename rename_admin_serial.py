import os
import re

files_to_modify = [
    r'd:\eehook\myapp\admin.py',
    r'd:\eehook\myapp\serializers.py'
]

replacements = [
    # Exact word replacements (case-sensitive)
    (r'\bProductVariantSize\b', 'ProductVariantUnit'),
    (r'\bSizeType\b', 'UnitType'),
    (r'\bSize\b', 'Unit'),
    
    # lowercase replacements
    (r'\bvariant_size\b', 'variant_unit'),
    (r'\bsize_type\b', 'unit_type'),
    (r'\bsize\b', 'unit'),
]

for file_path in files_to_modify:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    for old, new in replacements:
        content = re.sub(old, new, content)
        
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

print("Renaming completed for admin and serializers")

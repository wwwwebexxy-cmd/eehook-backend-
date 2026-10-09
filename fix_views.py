import os
import re

files_to_modify = [
    r'd:\eehook\myapp\views.py'
]

# We want to change the KEY in request.data.get("variant_unit") back to "variant_size"
replacements = [
    (r'request\.data\.get\("variant_unit"\)', 'request.data.get("variant_size")'),
    (r'request\.data\.get\(\n\s*"variant_unit"\n\s*\)', 'request.data.get(\n        "variant_size"\n    )'),
]

for file_path in files_to_modify:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    for old, new in replacements:
        content = re.sub(old, new, content)
        
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

print("Updated views.py request keys")

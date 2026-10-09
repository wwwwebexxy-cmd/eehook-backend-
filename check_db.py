import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from myapp.models import Category, SubCategory, Product, ProductVariant, ProductImage

print(f"Categories without image: {Category.objects.filter(image='').count()} / {Category.objects.count()}")
print(f"Subcategories without image: {SubCategory.objects.filter(image='').count()} / {SubCategory.objects.count()}")
print(f"Products: {Product.objects.count()}")
print(f"Variants total: {ProductVariant.objects.count()}")

no_color = ProductVariant.objects.filter(color__isnull=True).count()
print(f"Variants without color: {no_color}")

less_than_3_images = []
for v in ProductVariant.objects.all():
    if v.images.count() < 3:
        less_than_3_images.append(v.id)
print(f"Variants with <3 images: {len(less_than_3_images)}")

from django.db.models import Count
print("Variants with multiple price missing sizes:")
multiple_vars = ProductVariant.objects.filter(price_type='multiple').annotate(unit_count=Count('sizes'))
for v in multiple_vars:
    if v.unit_count == 0:
        print(f" - {v.id} ({v.product.name}) has no units!")

"""Authenticated end-to-end audit for the catalog and product workflow.

This script uses a transaction and a temporary MEDIA_ROOT, so the created
records and uploaded files are rolled back/removed after the audit.
"""

import json
import os
import tempfile
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test.utils import override_settings
from rest_framework.test import APIClient

from myapp.models import (
    Category,
    Color,
    Product,
    ProductImage,
    ProductVariant,
    ProductVariantUnit,
    SubCategory,
    Unit,
    UnitType,
)


class AuditFailure(AssertionError):
    pass


def check(condition, message):
    if not condition:
        raise AuditFailure(message)


def image_upload(source, name="real-product.jpg"):
    return SimpleUploadedFile(
        name,
        source.read_bytes(),
        content_type="image/jpeg",
    )


def assert_status(response, expected, label):
    if response.status_code != expected:
        raise AuditFailure(
            f"{label}: expected {expected}, got {response.status_code}: "
            f"{getattr(response, 'data', response.content[:500])}"
        )


def run():
    source_image = (
        Path(settings.MEDIA_ROOT)
        / "promotional_banners"
        / "electronics-public-domain.jpg"
    )
    check(source_image.exists(), f"Real image fixture missing: {source_image}")

    User = get_user_model()
    admin_user = User.objects.filter(role="Super Admin", is_active=True).first()
    check(admin_user is not None, "No active Super Admin exists for API audit")

    requested_category_names = {
        "Electronics",
        "Apple Products",
        "Gaming Products",
        "Smart Watches",
        "Wearables",
        "Cosmetics",
        "Toys",
        "Other Products",
    }
    requested_categories = list(
        Category.objects.filter(name__in=requested_category_names).order_by("id")
    )
    check(
        {category.name for category in requested_categories}
        == requested_category_names,
        "One or more requested categories are missing",
    )
    requested_subcategories = list(
        SubCategory.objects.filter(category__in=requested_categories)
        .select_related("category")
        .order_by("id")
    )
    check(len(requested_subcategories) == 23, "Expected 23 requested subcategories")
    check(
        all(
            Product.objects.filter(subcategory=subcategory).exists()
            for subcategory in requested_subcategories
        ),
        "Every requested subcategory must have at least one product",
    )

    result = {
        "catalog": {
            "categories": len(requested_categories),
            "subcategories": len(requested_subcategories),
            "relationship_errors": 0,
        },
        "crud": {},
        "products": 0,
        "variants": 0,
        "variant_units": 0,
        "images": 0,
        "inventory": {},
        "permissions": {},
        "public_api": {},
    }

    with tempfile.TemporaryDirectory(prefix="catalog-audit-") as media_root:
        with override_settings(MEDIA_ROOT=media_root):
            with transaction.atomic():
                client = APIClient()
                client.force_authenticate(user=admin_user)

                # Authentication and permission boundaries.
                client.force_authenticate(user=None)
                response = client.get("/admin/manage/schema/")
                assert_status(response, 401, "Unauthenticated schema access")
                result["permissions"]["anonymous_schema"] = response.status_code

                customer = User.objects.create_user(
                    email="catalog-audit-customer@example.invalid",
                    password="AuditPass123!",
                    role="Customer",
                )
                client.force_authenticate(user=customer)
                response = client.get("/admin/manage/schema/")
                assert_status(response, 403, "Customer schema access")
                result["permissions"]["customer_schema"] = response.status_code

                client.force_authenticate(user=admin_user)
                response = client.get("/admin/manage/schema/")
                assert_status(response, 200, "Super Admin schema access")
                schema_resources = {
                    item["key"]: item for item in response.data["resources"]
                }
                check("products" in schema_resources, "Product schema missing")
                check(
                    "regions"
                    not in {
                        field["name"]
                        for field in schema_resources["product-variants"]["fields"]
                    },
                    "Disabled product Regions field is still exposed in schema",
                )
                result["permissions"]["admin_schema"] = response.status_code

                # Category CRUD with a real image upload.
                category_response = client.post(
                    "/admin/manage/categories/",
                    {
                        "name": "__AUDIT Category",
                        "is_active": "true",
                        "image": image_upload(source_image, "audit-category.jpg"),
                    },
                    format="multipart",
                )
                assert_status(category_response, 201, "Category create")
                audit_category_id = category_response.data["id"]
                check(category_response.data["image"], "Category image URL missing")
                category_file = Category.objects.get(pk=audit_category_id).image
                check(
                    Path(category_file.path).exists() and category_file.size > 0,
                    "Uploaded category image file is missing",
                )
                response = client.patch(
                    f"/admin/manage/categories/{audit_category_id}/",
                    {"name": "__AUDIT Category Updated"},
                    format="json",
                )
                assert_status(response, 200, "Category update")
                response = client.get(
                    f"/admin/manage/categories/{audit_category_id}/"
                )
                assert_status(response, 200, "Category retrieve")
                response = client.delete(
                    f"/admin/manage/categories/{audit_category_id}/"
                )
                assert_status(response, 204, "Category delete")
                result["crud"]["category"] = "create/update/retrieve/delete passed"

                # Subcategory CRUD and category relationship.
                category = requested_categories[0]
                subcategory_response = client.post(
                    "/admin/manage/subcategories/",
                    {
                        "category": category.id,
                        "name": "__AUDIT Subcategory",
                        "is_active": "true",
                        "image": image_upload(source_image, "audit-subcategory.jpg"),
                    },
                    format="multipart",
                )
                assert_status(subcategory_response, 201, "Subcategory create")
                audit_subcategory_id = subcategory_response.data["id"]
                subcategory_file = SubCategory.objects.get(pk=audit_subcategory_id).image
                check(
                    Path(subcategory_file.path).exists() and subcategory_file.size > 0,
                    "Uploaded subcategory image file is missing",
                )
                check(
                    subcategory_response.data["category"] == category.id,
                    "Subcategory category relationship was not saved",
                )
                response = client.patch(
                    f"/admin/manage/subcategories/{audit_subcategory_id}/",
                    {"name": "__AUDIT Subcategory Updated"},
                    format="json",
                )
                assert_status(response, 200, "Subcategory update")
                response = client.delete(
                    f"/admin/manage/subcategories/{audit_subcategory_id}/"
                )
                assert_status(response, 204, "Subcategory delete")
                result["crud"]["subcategory"] = "create/update/delete passed"

                # Unit Type and Unit CRUD. Unit has no order or stock field.
                unit_type_response = client.post(
                    "/admin/manage/unit-types/",
                    {"name": "__AUDIT Weight"},
                    format="json",
                )
                assert_status(unit_type_response, 201, "Unit Type create")
                audit_unit_type_id = unit_type_response.data["id"]
                unit_response = client.post(
                    "/admin/manage/units/",
                    {"unit_type": audit_unit_type_id, "name": "__AUDIT KG"},
                    format="json",
                )
                assert_status(unit_response, 201, "Unit create")
                audit_unit_id = unit_response.data["id"]
                check("order" not in unit_response.data, "Unit exposes removed order field")
                check("stock" not in unit_response.data, "Unit exposes forbidden stock field")
                invalid_unit = client.post(
                    "/admin/manage/units/",
                    {
                        "unit_type": audit_unit_type_id,
                        "name": "__AUDIT Invalid KG",
                        "stock": 10,
                    },
                    format="json",
                )
                assert_status(invalid_unit, 400, "Unit stock rejection")
                response = client.patch(
                    f"/admin/manage/units/{audit_unit_id}/",
                    {"name": "__AUDIT KG Updated"},
                    format="json",
                )
                assert_status(response, 200, "Unit update")
                response = client.delete(f"/admin/manage/units/{audit_unit_id}/")
                assert_status(response, 204, "Unit delete")
                response = client.delete(
                    f"/admin/manage/unit-types/{audit_unit_type_id}/"
                )
                assert_status(response, 204, "Unit Type delete")
                result["crud"]["unit"] = "create/update/delete passed"

                # Wrong category/subcategory relationship must be rejected.
                wrong_subcategory = requested_subcategories[0]
                wrong_category = requested_categories[1]
                invalid_product = client.post(
                    "/admin/manage/products/",
                    {
                        "category": wrong_category.id,
                        "subcategory": wrong_subcategory.id,
                        "name": "__AUDIT Invalid Relationship",
                        "description": "Must fail category validation",
                        "emi_available": False,
                        "emi_starting_price": "",
                    },
                    format="multipart",
                )
                assert_status(
                    invalid_product, 400, "Product category/subcategory validation"
                )

                # Create one product through the admin API for every requested
                # subcategory, exercising the full relationship matrix.
                created_product_ids = []
                for index, subcategory in enumerate(requested_subcategories, start=1):
                    data = {
                        "category": subcategory.category_id,
                        "subcategory": subcategory.id,
                        "name": f"__AUDIT Product {index} - {subcategory.name}",
                        "description": (
                            f"Real catalog workflow test product for {subcategory.name}."
                        ),
                        "key_features": "Tested product\nReal inventory\nCatalog relation",
                        "shipping_fee": "0.00",
                        "estimated_delivery_time": "3-5 business days",
                        "seller_name": "Audit Seller",
                        "warranty_info": "1 year",
                        "is_active": "true",
                        "emi_available": "false",
                        "emi_starting_price": "",
                    }
                    if index == 1:
                        data["promotional_banner_image"] = image_upload(
                            source_image, "audit-promotional-banner.jpg"
                        )
                    product_response = client.post(
                        "/admin/manage/products/", data, format="multipart"
                    )
                    assert_status(product_response, 201, f"Product create #{index}")
                    product_id = product_response.data["id"]
                    created_product_ids.append(product_id)
                    check(
                        product_response.data["category"] == subcategory.category_id,
                        f"Product #{index} category relationship failed",
                    )
                    check(
                        product_response.data["subcategory"] == subcategory.id,
                        f"Product #{index} subcategory relationship failed",
                    )
                    check(
                        product_response.data["emi_available"] is False
                        and product_response.data["emi_starting_price"] is None,
                        f"Product #{index} EMI normalization failed",
                    )
                result["products"] = len(created_product_ids)

                # Single-price variant: color is optional and product stock is used.
                single_variant_response = client.post(
                    "/admin/manage/product-variants/",
                    {
                        "product": created_product_ids[0],
                        "price_type": "single",
                        "price": "129.99",
                        "stock": 9,
                    },
                    format="json",
                )
                assert_status(single_variant_response, 201, "Single variant create")
                single_variant_id = single_variant_response.data["id"]
                check(
                    single_variant_response.data["color"] is None,
                    "Color should be optional for a product variant",
                )

                # Multiple-price variant and product-level inventory rows.
                multiple_variant_response = client.post(
                    "/admin/manage/product-variants/",
                    {
                        "product": created_product_ids[1],
                        "price_type": "multiple",
                        "price": None,
                        "stock": 0,
                    },
                    format="json",
                )
                assert_status(
                    multiple_variant_response, 201, "Multiple variant create"
                )
                multiple_variant_id = multiple_variant_response.data["id"]
                test_units = list(
                    Unit.objects.exclude(id=audit_unit_id)
                    .filter(unit_type__isnull=False)
                    .order_by("id")[:2]
                )
                check(len(test_units) == 2, "At least two reusable Units are required")
                variant_unit_ids = []
                for price, stock, unit in (("49.00", 6, test_units[0]), ("89.00", 4, test_units[1])):
                    unit_response = client.post(
                        "/admin/manage/product-variant-units/",
                        {
                            "variant": multiple_variant_id,
                            "unit_type": unit.unit_type_id,
                            "unit": unit.id,
                            "price": price,
                            "stock": stock,
                        },
                        format="json",
                    )
                    assert_status(unit_response, 201, "Product Variant Unit create")
                    variant_unit_ids.append(unit_response.data["id"])
                result["variants"] = 2
                result["variant_units"] = len(variant_unit_ids)

                # Two real image uploads linked to the same variant.
                image_ids = []
                for image_index in (1, 2):
                    image_response = client.post(
                        "/admin/manage/product-images/",
                        {
                            "variant": single_variant_id,
                            "is_primary": image_index == 1,
                            "image": image_upload(
                                source_image, f"audit-product-{image_index}.jpg"
                            ),
                        },
                        format="multipart",
                    )
                    assert_status(image_response, 201, f"Product image create #{image_index}")
                    check(image_response.data["image"], "Product image URL missing")
                    product_image_file = ProductImage.objects.get(
                        pk=image_response.data["id"]
                    ).image
                    check(
                        Path(product_image_file.path).exists()
                        and product_image_file.size > 0,
                        f"Uploaded product image file #{image_index} is missing",
                    )
                    image_ids.append(image_response.data["id"])
                result["images"] = len(image_ids)

                # Retrieve/filter/update/delete checks for nested resources.
                response = client.get(
                    f"/admin/manage/product-variants/?product={created_product_ids[1]}"
                )
                assert_status(response, 200, "Product variant product filter")
                check(
                    all(item["product"] == created_product_ids[1] for item in response.data["results"]),
                    "Product variant product filter returned unrelated records",
                )
                response = client.get(
                    f"/admin/manage/product-variant-units/?variant={multiple_variant_id}"
                )
                assert_status(response, 200, "Product variant unit filter")
                check(len(response.data["results"]) == 2, "Variant unit filter count mismatch")
                response = client.patch(
                    f"/admin/manage/products/{created_product_ids[0]}/",
                    {"seller_name": "Audit Seller Updated"},
                    format="json",
                )
                assert_status(response, 200, "Product update")
                response = client.delete(
                    f"/admin/manage/product-images/{image_ids[1]}/"
                )
                assert_status(response, 204, "Product image delete")

                # Customer cart/order workflow for both inventory modes.
                client.force_authenticate(user=customer)
                address_response = client.post(
                    "/addresses/",
                    {
                        "full_name": "Catalog Audit Customer",
                        "phone": "0123456789",
                        "address_line": "1 Audit Street",
                        "city": "Auckland",
                        "postal_code": "1010",
                        "country": "New Zealand",
                        "is_default": True,
                    },
                    format="json",
                )
                assert_status(address_response, 201, "Customer address create")
                address_id = address_response.data["id"]

                single_variant = ProductVariant.objects.get(pk=single_variant_id)
                single_stock_before = single_variant.stock
                response = client.post(
                    "/cart/add/",
                    {"variant": single_variant_id, "quantity": 2},
                    format="json",
                )
                assert_status(response, 200, "Single variant add to cart")
                response = client.get("/cart/")
                assert_status(response, 200, "Single variant cart read")
                check(len(response.data["items"]) == 1, "Single variant cart item missing")
                single_cart_id = response.data["items"][0]["id"]
                response = client.patch(
                    f"/cart/update/{single_cart_id}/",
                    {"quantity": 3},
                    format="json",
                )
                assert_status(response, 200, "Single variant cart quantity update")
                response = client.post(
                    "/place-order/",
                    {"address": address_id},
                    format="json",
                )
                assert_status(response, 201, "Single variant order placement")
                single_order_id = response.data["order_id"]
                single_variant.refresh_from_db()
                check(
                    single_variant.stock == single_stock_before - 3,
                    "Single variant product stock did not decrease on order",
                )
                response = client.patch(f"/cancel-order/{single_order_id}/", {}, format="json")
                assert_status(response, 200, "Single variant order cancellation")
                single_variant.refresh_from_db()
                check(
                    single_variant.stock == single_stock_before,
                    "Single variant stock was not restored on cancellation",
                )

                selected_unit_id = variant_unit_ids[0]
                selected_unit = ProductVariantUnit.objects.get(pk=selected_unit_id)
                multiple_stock_before = selected_unit.stock
                response = client.post(
                    "/cart/add/",
                    {
                        "variant": multiple_variant_id,
                        "variant_size": selected_unit_id,
                        "quantity": 2,
                    },
                    format="json",
                )
                assert_status(response, 200, "Multiple variant add to cart")
                response = client.get("/cart/")
                assert_status(response, 200, "Multiple variant cart read")
                multiple_cart_id = next(
                    item["id"]
                    for item in response.data["items"]
                    if item["variant"] == multiple_variant_id
                )
                response = client.patch(
                    f"/cart/update/{multiple_cart_id}/",
                    {"quantity": 3},
                    format="json",
                )
                assert_status(response, 200, "Multiple variant cart quantity update")
                response = client.post(
                    "/place-order/",
                    {"address": address_id},
                    format="json",
                )
                assert_status(response, 201, "Multiple variant order placement")
                multiple_order_id = response.data["order_id"]
                selected_unit.refresh_from_db()
                check(
                    selected_unit.stock == multiple_stock_before - 3,
                    "Product Variant Unit stock did not decrease on order",
                )
                response = client.patch(
                    f"/cancel-order/{multiple_order_id}/", {}, format="json"
                )
                assert_status(response, 200, "Multiple variant order cancellation")
                selected_unit.refresh_from_db()
                check(
                    selected_unit.stock == multiple_stock_before,
                    "Product Variant Unit stock was not restored on cancellation",
                )

                # A unit from another variant must never be attachable to a
                # single-price product.
                response = client.post(
                    "/cart/add/",
                    {
                        "variant": single_variant_id,
                        "variant_size": selected_unit_id,
                        "quantity": 1,
                    },
                    format="json",
                )
                assert_status(response, 400, "Cross-variant unit rejection")
                result["inventory"] = {
                    "single_price_order_cancel": "passed",
                    "multiple_price_order_cancel": "passed",
                    "cross_variant_unit_rejection": "passed",
                }

                # Public catalog endpoints must expose the linked product.
                client.force_authenticate(user=None)
                response = client.get(f"/product/{created_product_ids[0]}/")
                assert_status(response, 200, "Public product detail")
                result["public_api"]["product_detail"] = response.status_code
                response = client.get("/products/")
                assert_status(response, 200, "Public product list")
                result["public_api"]["product_list"] = response.status_code
                response = client.get(
                    f"/category-products/{requested_categories[0].id}/"
                )
                assert_status(response, 200, "Public category product list")
                result["public_api"]["category_products"] = response.status_code
                response = client.get("/subcategories/")
                assert_status(response, 200, "Public subcategory list")
                result["public_api"]["subcategories"] = response.status_code

                # The transaction is intentionally rolled back below; this is
                # an audit, not a data seeding operation.
                raise RuntimeError(json.dumps(result))


try:
    run()
except RuntimeError as exc:
    print(exc.args[0])
except Exception:
    raise

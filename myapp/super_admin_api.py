"""Super Admin management API for the Order Dashboard.

The Django Admin is the source of truth for which records a Super Admin can
manage. These viewsets expose the same registered models to the dashboard,
including multipart uploads and the nested Product records used by the admin
inlines.
"""

import os

from django.core.files.base import ContentFile
from django.db.models.fields import NOT_PROVIDED
from django.db import transaction
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import filters, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from PIL import Image, UnidentifiedImageError

from .models import (
    Address,
    AdminAuditLog,
    Brand,
    Cart,
    Category,
    Coupon,
    CouponUsage,
    Color,
    HeroBanner,
    HeroSideBanner,
    Offer,
    Order,
    OrderItem,
    Product,
    ProductHighlight,
    ProductMessage,
    ProductImage,
    ProductRelatedProduct,
    ProductVariant,
    ProductVariantUnit,
    PromoBanner,
    Region,
    SubCategory,
    TrustBenefit,
    Unit,
    UnitType,
    User,
    UserProfile,
    Wishlist,
    WelcomeBonus,
)
from .permissions import IsSuperAdmin
from .catalog_pricing import get_product_price_values
from .serializers import CouponSerializer


class SuperAdminPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class AdminUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=False,
        max_length=128,
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "password",
            "first_name",
            "last_name",
            "role",
            "is_staff",
            "is_active",
            "is_superuser",
            "date_joined",
            "last_login",
        )
        read_only_fields = ("id", "date_joined", "last_login")

    def validate(self, attrs):
        password = attrs.get("password")
        if self.instance is None and not password:
            raise serializers.ValidationError({"password": "A strong password is required for a new account."})
        if password:
            try:
                validate_password(password, user=self.instance)
            except DjangoValidationError as error:
                raise serializers.ValidationError({"password": error.messages})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class AdminProductSerializer(serializers.ModelSerializer):
    # The order in this list is the display order.  It is intentionally
    # separate from the read-only relationship payload so a dashboard cannot
    # write arbitrary through-model fields or a fifth relationship.
    related_product_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        write_only=True,
        required=False,
        max_length=4,
    )
    manual_related_products = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "category",
            "subcategory",
            "brand",
            "offer",
            "name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
            "key_features",
            "shipping_fee",
            "estimated_delivery_time",
            "seller_name",
            "warranty_info",
            "current_viewers_count",
            "promotional_banner_image",
            "promotional_banner_link",
            "related_product_mode",
            "related_product_ids",
            "manual_related_products",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        category = attrs.get("category", getattr(self.instance, "category", None))
        subcategory = attrs.get(
            "subcategory", getattr(self.instance, "subcategory", None)
        )
        if category and subcategory and subcategory.category_id != category.id:
            raise serializers.ValidationError(
                {"subcategory": "The subcategory must belong to the selected category."}
            )

        related_ids = attrs.get("related_product_ids")
        mode = attrs.get(
            "related_product_mode",
            getattr(self.instance, "related_product_mode", Product.RELATED_PRODUCT_MODE_NONE),
        )
        if related_ids is not None:
            if len(set(related_ids)) != len(related_ids):
                raise serializers.ValidationError(
                    {"related_product_ids": "Duplicate related products are not allowed."}
                )
            if self.instance and self.instance.pk in related_ids:
                raise serializers.ValidationError(
                    {"related_product_ids": "A product cannot be related to itself."}
                )
            valid_count = Product.objects.filter(
                id__in=related_ids,
                is_active=True,
            ).count()
            if valid_count != len(related_ids):
                raise serializers.ValidationError(
                    {"related_product_ids": "Related products must be active existing products."}
                )
            if mode != Product.RELATED_PRODUCT_MODE_MANUAL and related_ids:
                raise serializers.ValidationError(
                    {"related_product_ids": "Manual related products require Manual mode."}
                )

        return attrs

    @staticmethod
    def _sync_manual_related_products(product, related_ids):
        ProductRelatedProduct.objects.filter(product=product).delete()
        ProductRelatedProduct.objects.bulk_create(
            [
                ProductRelatedProduct(
                    product=product,
                    related_product_id=related_product_id,
                    position=position,
                )
                for position, related_product_id in enumerate(related_ids)
            ]
        )

    def get_manual_related_products(self, obj):
        links = list(obj.related_product_links.all())
        return [
            {
                "id": link.related_product_id,
                "name": link.related_product.name,
                "position": link.position,
            }
            for link in links
        ]

    def create(self, validated_data):
        related_ids = validated_data.pop("related_product_ids", None)
        instance = Product(**validated_data)
        instance.full_clean()
        instance.save()
        if instance.related_product_mode == Product.RELATED_PRODUCT_MODE_MANUAL and related_ids:
            self._sync_manual_related_products(instance, related_ids)
        return instance

    def update(self, instance, validated_data):
        related_ids = validated_data.pop("related_product_ids", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.full_clean()
        instance.save()
        if instance.related_product_mode != Product.RELATED_PRODUCT_MODE_MANUAL:
            ProductRelatedProduct.objects.filter(product=instance).delete()
        elif related_ids is not None:
            self._sync_manual_related_products(instance, related_ids)
        return instance


class AdminProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ("id", "product", "color", "sku", "price_type", "price", "stock")
        read_only_fields = ("id",)

    def validate(self, attrs):
        if "regions" in self.initial_data:
            raise serializers.ValidationError(
                {"regions": "Regions are disabled for product variants."}
            )

        price_type = attrs.get("price_type", getattr(self.instance, "price_type", "single"))
        price = attrs.get("price", getattr(self.instance, "price", None))
        if price_type == "single" and price is None:
            raise serializers.ValidationError(
                {"price": "A single-price variant requires a price."}
            )
        if price_type == "multiple" and price is not None:
            raise serializers.ValidationError(
                {"price": "A multiple-price variant must store prices on its units."}
            )

        product = attrs.get("product", getattr(self.instance, "product", None))
        color = attrs.get("color", getattr(self.instance, "color", None))
        if product and color is None:
            duplicate = ProductVariant.objects.filter(
                product=product,
                color__isnull=True,
            ).exclude(pk=getattr(self.instance, "pk", None)).exists()
            if duplicate:
                raise serializers.ValidationError(
                    {"color": "A product can have only one no-color variant."}
                )
        return attrs

    def create(self, validated_data):
        instance = ProductVariant(**validated_data)
        instance.full_clean()
        instance.save()
        return instance

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.full_clean()
        instance.save()
        return instance


class AdminProductVariantUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariantUnit
        fields = ("id", "variant", "unit_type", "unit", "sku", "price", "stock")
        read_only_fields = ("id",)

    def validate(self, attrs):
        unit = attrs.get("unit", getattr(self.instance, "unit", None))
        unit_type = attrs.get("unit_type", getattr(self.instance, "unit_type", None))
        if unit is None:
            raise serializers.ValidationError({"unit": "A variant unit requires a unit value."})
        if unit_type is None:
            raise serializers.ValidationError({"unit_type": "A variant unit requires a unit type."})
        if not unit.unit_type_id:
            raise serializers.ValidationError(
                {"unit": "The selected unit is not assigned to a unit type."}
            )
        if unit.unit_type_id != unit_type.id:
            raise serializers.ValidationError(
                {"unit_type": "The selected unit does not belong to this unit type."}
            )

        variant = attrs.get("variant", getattr(self.instance, "variant", None))
        price = attrs.get("price", getattr(self.instance, "price", None))
        if variant and price is not None:
            product = variant.product
        return attrs

    def create(self, validated_data):
        instance = ProductVariantUnit(**validated_data)
        instance.full_clean()
        instance.save()
        return instance

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.full_clean()
        instance.save()
        return instance


class AdminProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ("id", "variant", "image", "is_primary", "position")
        read_only_fields = ("id",)

    def validate(self, attrs):
        variant = attrs.get("variant", getattr(self.instance, "variant", None))
        if variant is None:
            raise serializers.ValidationError(
                {"variant": "A product image must belong to a variant."}
            )
        return attrs

    def create(self, validated_data):
        instance = ProductImage(**validated_data)
        instance.full_clean()
        instance.save()
        return instance

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.full_clean()
        instance.save()
        return instance


class AdminModelViewSet(viewsets.ModelViewSet):
    """Common protected CRUD behavior for all Django Admin models."""

    permission_classes = (IsSuperAdmin,)
    pagination_class = SuperAdminPagination
    parser_classes = (JSONParser, FormParser, MultiPartParser)
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ()
    # Never allow clients to turn arbitrary query parameters into ORM
    # expressions. Individual viewsets opt into fields explicitly.
    ordering_fields = ()

    def _validate_uploads(self):
        max_bytes = 5 * 1024 * 1024
        allowed = {"image/jpeg", "image/png", "image/webp"}
        for uploaded in self.request.FILES.values():
            if uploaded.size > max_bytes:
                raise serializers.ValidationError({"file": "Uploaded images must be 5 MB or smaller."})
            if getattr(uploaded, "content_type", "") not in allowed:
                raise serializers.ValidationError({"file": "Only JPEG, PNG, and WebP images are accepted."})
            try:
                uploaded.seek(0)
                with Image.open(uploaded) as image:
                    image.verify()
            except (UnidentifiedImageError, OSError):
                raise serializers.ValidationError({"file": "The uploaded file is not a valid image."})
            finally:
                uploaded.seek(0)

    def _audit(self, action, instance, description=""):
        AdminAuditLog.objects.create(
            admin_user=self.request.user,
            action=action,
            entity_type=instance._meta.label_lower,
            entity_id=str(instance.pk),
            description=description or f"{action.title()} {instance}.",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_create(self, serializer):
        with transaction.atomic():
            self._validate_uploads()
            instance = serializer.save()
            self._audit("create", instance)

    def perform_update(self, serializer):
        with transaction.atomic():
            self._validate_uploads()
            instance = serializer.save()
            self._audit("update", instance)

    def perform_destroy(self, instance):
        with transaction.atomic():
            self._audit("delete", instance)
            instance.delete()


class AdminUserViewSet(AdminModelViewSet):
    queryset = User.objects.all().order_by("email")
    serializer_class = AdminUserSerializer
    search_fields = ("email", "first_name", "last_name", "role")


class AdminBrandViewSet(AdminModelViewSet):
    queryset = Brand.objects.all().order_by("name")
    search_fields = ("name", "slug")

    def get_serializer_class(self):
        class BrandAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = Brand
                fields = "__all__"
                read_only_fields = ("id", "created_at")

        return BrandAdminSerializer


class AdminCategoryViewSet(AdminModelViewSet):
    queryset = Category.objects.all().order_by("name")
    serializer_class = serializers.ModelSerializer
    search_fields = ("name",)

    def get_serializer_class(self):
        class CategoryAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = Category
                fields = "__all__"
                read_only_fields = ("id", "created_at")

        return CategoryAdminSerializer


class AdminSubCategoryViewSet(AdminModelViewSet):
    queryset = SubCategory.objects.select_related("category").all().order_by("name")
    search_fields = ("name", "category__name")

    def get_serializer_class(self):
        class SubCategoryAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = SubCategory
                fields = "__all__"
                read_only_fields = ("id", "created_at")

        return SubCategoryAdminSerializer


class AdminOfferViewSet(AdminModelViewSet):
    queryset = Offer.objects.all().order_by("-created_at")
    search_fields = ("title", "description")

    def get_serializer_class(self):
        class OfferAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = Offer
                fields = "__all__"
                read_only_fields = ("id", "created_at")

        return OfferAdminSerializer


class AdminColorViewSet(AdminModelViewSet):
    queryset = Color.objects.all().order_by("name")
    search_fields = ("name", "code")

    def get_serializer_class(self):
        class ColorAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = Color
                fields = "__all__"
                read_only_fields = ("id",)

        return ColorAdminSerializer


class AdminUnitTypeViewSet(AdminModelViewSet):
    queryset = UnitType.objects.all().order_by("name")
    search_fields = ("name",)

    def get_serializer_class(self):
        class UnitTypeAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = UnitType
                fields = "__all__"
                read_only_fields = ("id",)

        return UnitTypeAdminSerializer


class AdminUnitViewSet(AdminModelViewSet):
    queryset = Unit.objects.select_related("unit_type").all().order_by("name")
    search_fields = ("name", "unit_type__name")

    def get_serializer_class(self):
        class UnitAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = Unit
                # A Unit is only a reusable measurement/label. Inventory
                # belongs to ProductVariant or ProductVariantUnit, never Unit.
                fields = ("id", "unit_type", "name")
                read_only_fields = ("id",)

            def validate(self, attrs):
                forbidden = {
                    field: "Unit does not contain inventory or display-order data."
                    for field in ("stock", "order")
                    if field in self.initial_data
                }
                if forbidden:
                    raise serializers.ValidationError(forbidden)
                return attrs

        return UnitAdminSerializer


class AdminRegionViewSet(AdminModelViewSet):
    queryset = Region.objects.all().order_by("name")
    search_fields = ("name",)

    def get_serializer_class(self):
        class RegionAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = Region
                fields = "__all__"
                read_only_fields = ("id",)

        return RegionAdminSerializer


class AdminProductViewSet(AdminModelViewSet):
    queryset = Product.objects.select_related(
        "category", "subcategory", "brand", "offer"
    ).prefetch_related(
        "related_product_links__related_product"
    ).all()
    serializer_class = AdminProductSerializer
    # Product identifiers live on the product's variants in the current
    # schema: variant SKUs are also the catalog/product codes, while
    # size/unit SKUs are stored one relationship deeper.  SearchFilter uses
    # case-insensitive ``icontains`` lookups for these fields and keeps the
    # standard paginated response unchanged.
    search_fields = (
        "name",
        "description",
        "seller_name",
        "category__name",
        "subcategory__name",
        "variants__sku",
        "variants__sizes__sku",
    )
    ordering = ("-created_at",)

    @action(detail=True, methods=("post",), url_path="duplicate")
    def duplicate(self, request, pk=None):
        """Duplicate a product and all of its catalog media on the server.

        Image files are copied through Django's configured storage instead of
        being downloaded by the browser.  This keeps duplication working with
        local media, S3-compatible storage, and deployments where media URLs
        are not readable from the dashboard origin.
        """
        source = self.get_object()
        with transaction.atomic():
            duplicate = Product(
                category=source.category,
                subcategory=source.subcategory,
                brand=source.brand,
                offer=source.offer,
                name=f"{source.name} (Copy)",
                description=source.description,
                is_active=source.is_active,
                key_features=source.key_features,
                shipping_fee=source.shipping_fee,
                estimated_delivery_time=source.estimated_delivery_time,
                seller_name=source.seller_name,
                warranty_info=source.warranty_info,
                current_viewers_count=0,
                promotional_banner_link=source.promotional_banner_link,
                related_product_mode=Product.RELATED_PRODUCT_MODE_NONE,
            )
            duplicate.full_clean()
            duplicate.save()

            if source.promotional_banner_image:
                _copy_stored_file(
                    source.promotional_banner_image,
                    duplicate.promotional_banner_image,
                    f"duplicate-{duplicate.pk}-banner",
                )
                duplicate.save(update_fields=("promotional_banner_image",))

            source_variants = source.variants.prefetch_related(
                "regions", "sizes", "images"
            ).order_by("id")
            for source_variant in source_variants:
                variant = ProductVariant.objects.create(
                    product=duplicate,
                    color=source_variant.color,
                    price_type=source_variant.price_type,
                    price=source_variant.price,
                    stock=source_variant.stock,
                )
                variant.regions.set(source_variant.regions.all())

                for source_unit in source_variant.sizes.all():
                    # Variant and unit SKUs are unique.  A duplicate gets new
                    # catalog records, so retaining those identifiers would
                    # make the otherwise valid copy fail on uniqueness.
                    ProductVariantUnit.objects.create(
                        variant=variant,
                        unit_type=source_unit.unit_type,
                        unit=source_unit.unit,
                        price=source_unit.price,
                        stock=source_unit.stock,
                    )

                copied_images = []
                source_primary_image = None
                source_images = list(source_variant.images.all())
                for source_image in source_images:
                    if not source_image.image:
                        continue
                    image = ProductImage(
                        variant=variant,
                        position=source_image.position,
                        is_primary=False,
                    )
                    _copy_stored_file(
                        source_image.image,
                        image.image,
                        f"duplicate-{duplicate.pk}-image-{source_image.pk}",
                    )
                    image.save()
                    copied_images.append(image)
                    if source_image.is_primary:
                        source_primary_image = image

                if copied_images:
                    primary_image = source_primary_image or copied_images[0]
                    primary_image.is_primary = True
                    primary_image.save(update_fields=("is_primary",))

            self._audit("duplicate", duplicate, f"Duplicated product {source.pk}.")

        return Response(self.get_serializer(duplicate).data, status=201)


def _copy_stored_file(source_field, target_field, prefix):
    """Copy a configured-storage file into another model field."""
    source_field.open("rb")
    try:
        content = source_field.read()
    finally:
        source_field.close()
    original_name = os.path.basename(source_field.name)
    target_name = f"{prefix}-{original_name}"
    target_field.save(target_name, ContentFile(content), save=False)


class AdminProductHighlightSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductHighlight
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        highlight_type = attrs.get(
            "highlight_type",
            getattr(self.instance, "highlight_type", ProductHighlight.MESSAGE),
        )
        ends_at = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if highlight_type == ProductHighlight.COUNTDOWN and not ends_at:
            raise serializers.ValidationError(
                {"ends_at": "Countdown highlights require an end time."}
            )
        return attrs

    def create(self, validated_data):
        instance = ProductHighlight(**validated_data)
        instance.full_clean()
        instance.save()
        return instance

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.full_clean()
        instance.save()
        return instance


class AdminProductHighlightViewSet(AdminModelViewSet):
    queryset = ProductHighlight.objects.select_related("product").all()
    serializer_class = AdminProductHighlightSerializer
    search_fields = ("product__name", "text")
    ordering = ("product_id", "display_order", "id")

    def get_queryset(self):
        queryset = super().get_queryset()
        product_id = self.request.query_params.get("product")
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        return queryset


class AdminProductMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductMessage
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        message_type = attrs.get(
            "message_type",
            getattr(self.instance, "message_type", ProductMessage.TEXT),
        )
        ends_at = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if message_type == ProductMessage.COUNTDOWN and not ends_at:
            raise serializers.ValidationError(
                {"ends_at": "Countdown messages require an end time."}
            )
        return attrs

    def create(self, validated_data):
        instance = ProductMessage(**validated_data)
        instance.full_clean()
        instance.save()
        return instance

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.full_clean()
        instance.save()
        return instance


class AdminProductMessageViewSet(AdminModelViewSet):
    queryset = ProductMessage.objects.select_related("product").all()
    serializer_class = AdminProductMessageSerializer
    search_fields = ("product__name", "text")
    ordering = ("product_id", "display_order", "id")

    def get_queryset(self):
        queryset = super().get_queryset()
        product_id = self.request.query_params.get("product")
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        return queryset


class AdminProductVariantViewSet(AdminModelViewSet):
    queryset = ProductVariant.objects.select_related("product", "color").order_by("id")
    search_fields = ("product__name", "color__name")

    def get_queryset(self):
        queryset = super().get_queryset()
        product_id = self.request.query_params.get("product")
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        return queryset

    serializer_class = AdminProductVariantSerializer


class AdminProductVariantUnitViewSet(AdminModelViewSet):
    queryset = ProductVariantUnit.objects.select_related(
        "variant__product", "unit", "unit_type"
    ).all().order_by("id")
    search_fields = ("variant__product__name", "unit__name", "unit_type__name")

    def get_queryset(self):
        queryset = super().get_queryset()
        variant_id = self.request.query_params.get("variant")
        product_id = self.request.query_params.get("product")
        if variant_id:
            queryset = queryset.filter(variant_id=variant_id)
        if product_id:
            queryset = queryset.filter(variant__product_id=product_id)
        return queryset

    serializer_class = AdminProductVariantUnitSerializer


class AdminProductImageViewSet(AdminModelViewSet):
    queryset = ProductImage.objects.select_related("variant__product").all().order_by(
        "variant_id", "position", "id"
    )
    search_fields = ("variant__product__name",)

    def get_queryset(self):
        queryset = super().get_queryset()
        variant_id = self.request.query_params.get("variant")
        product_id = self.request.query_params.get("product")
        if variant_id:
            queryset = queryset.filter(variant_id=variant_id)
        if product_id:
            queryset = queryset.filter(variant__product_id=product_id)
        return queryset

    serializer_class = AdminProductImageSerializer

    @action(detail=True, methods=("post",), url_path="set-primary")
    def set_primary(self, request, pk=None):
        """Make exactly this image primary for its variant."""
        image = self.get_object()
        with transaction.atomic():
            locked_image = ProductImage.objects.select_for_update().get(pk=image.pk)
            ProductImage.objects.filter(variant_id=locked_image.variant_id).update(
                is_primary=False
            )
            ProductImage.objects.filter(pk=locked_image.pk).update(is_primary=True)
            locked_image.refresh_from_db()
        return Response(self.get_serializer(locked_image).data)


class AdminWishlistViewSet(AdminModelViewSet):
    queryset = Wishlist.objects.select_related(
        "user", "variant__product", "variant_unit"
    ).all().order_by("-created_at", "-id")
    search_fields = ("user__email", "variant__product__name")

    def get_serializer_class(self):
        class WishlistAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = Wishlist
                fields = "__all__"
                read_only_fields = ("id", "created_at")

        return WishlistAdminSerializer


class AdminCartViewSet(AdminModelViewSet):
    queryset = Cart.objects.select_related(
        "user", "variant__product", "variant_unit", "coupon"
    ).all().order_by("-created_at", "-id")
    search_fields = ("user__email", "variant__product__name", "coupon__code")

    def get_serializer_class(self):
        class CartAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = Cart
                fields = "__all__"
                read_only_fields = ("id", "created_at")

        return CartAdminSerializer


class AdminAddressViewSet(AdminModelViewSet):
    queryset = Address.objects.select_related("user").all().order_by("-created_at")
    search_fields = ("full_name", "phone", "city", "postal_code", "country", "user__email")

    def get_serializer_class(self):
        class AddressAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = Address
                fields = "__all__"
                read_only_fields = ("id", "created_at")

        return AddressAdminSerializer


class AdminUserProfileViewSet(AdminModelViewSet):
    queryset = UserProfile.objects.select_related("user").all().order_by("id")
    search_fields = ("user__email", "phone", "gender")

    def get_serializer_class(self):
        class UserProfileAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = UserProfile
                fields = "__all__"
                read_only_fields = ("id",)

        return UserProfileAdminSerializer


class AdminOrderViewSet(AdminModelViewSet):
    queryset = Order.objects.select_related("user", "address", "cancelled_by").prefetch_related("items").all()
    search_fields = ("user__email", "user__first_name", "stripe_session_id")
    ordering = ("-created_at",)

    def get_serializer_class(self):
        class OrderAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = Order
                fields = "__all__"
                read_only_fields = ("id", "created_at", "updated_at")

        return OrderAdminSerializer


class AdminOrderItemViewSet(AdminModelViewSet):
    queryset = OrderItem.objects.select_related(
        "order", "product", "color", "unit", "variant_unit"
    ).all().order_by("id")
    search_fields = ("product__name", "order__id", "order__user__email")

    def get_serializer_class(self):
        class OrderItemAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = OrderItem
                fields = "__all__"
                read_only_fields = ("id",)

        return OrderItemAdminSerializer


class AdminHeroBannerViewSet(AdminModelViewSet):
    queryset = HeroBanner.objects.all().order_by("display_order")
    search_fields = ("title", "subtitle", "description")

    def get_serializer_class(self):
        class HeroBannerAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = HeroBanner
                fields = "__all__"
                read_only_fields = ("id", "created_at", "updated_at")

        return HeroBannerAdminSerializer


class AdminTrustBenefitViewSet(AdminModelViewSet):
    queryset = TrustBenefit.objects.all().order_by("display_order", "id")
    search_fields = ("key", "title", "description")
    ordering_fields = ("display_order", "created_at", "updated_at", "key", "title")

    class TrustBenefitAdminSerializer(serializers.ModelSerializer):
        class Meta:
            model = TrustBenefit
            fields = (
                "id",
                "key",
                "title",
                "description",
                "icon_key",
                "display_order",
                "is_active",
                "created_at",
                "updated_at",
            )
            read_only_fields = ("id", "created_at", "updated_at")

    serializer_class = TrustBenefitAdminSerializer


class AdminPromoBannerViewSet(AdminModelViewSet):
    queryset = PromoBanner.objects.all().order_by("id")
    search_fields = ("link",)

    def get_serializer_class(self):
        class PromoBannerAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = PromoBanner
                fields = "__all__"
                read_only_fields = ("id",)

        return PromoBannerAdminSerializer


class AdminHeroSideBannerViewSet(AdminModelViewSet):
    queryset = HeroSideBanner.objects.all().order_by("id")
    search_fields = ("link",)

    def get_serializer_class(self):
        class HeroSideBannerAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = HeroSideBanner
                fields = "__all__"
                read_only_fields = ("id",)

        return HeroSideBannerAdminSerializer


class AdminCouponViewSet(AdminModelViewSet):
    queryset = Coupon.objects.select_related("category").prefetch_related("products").all().order_by("-created_at")
    search_fields = ("code", "products__name", "category__name")
    ordering_fields = (
        "code",
        "applicability_type",
        "discount_type",
        "start_date",
        "end_date",
        "is_active",
        "created_at",
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        applicability = self.request.query_params.get("applicability_type")
        discount_type = self.request.query_params.get("discount_type")
        is_active = self.request.query_params.get("is_active")
        category = self.request.query_params.get("category")
        product = self.request.query_params.get("product")

        if applicability in dict(Coupon.APPLICABILITY_CHOICES):
            queryset = queryset.filter(applicability_type=applicability)
        if discount_type in dict(Coupon.DISCOUNT_TYPE_CHOICES):
            queryset = queryset.filter(discount_type=discount_type)
        if is_active in {"true", "false", "1", "0"}:
            queryset = queryset.filter(is_active=is_active in {"true", "1"})
        if category and category.isdigit():
            queryset = queryset.filter(category_id=int(category))
        if product and product.isdigit():
            queryset = queryset.filter(products__id=int(product))
        return queryset.distinct()

    def get_serializer_class(self):
        return CouponSerializer


class AdminCouponUsageViewSet(AdminModelViewSet):
    queryset = CouponUsage.objects.select_related("user", "coupon", "product").all().order_by("-used_at", "-id")
    search_fields = ("user__email", "coupon__code", "product__name")

    def get_serializer_class(self):
        class CouponUsageAdminSerializer(serializers.ModelSerializer):
            class Meta:
                model = CouponUsage
                fields = "__all__"
                read_only_fields = ("id", "used_at")

        return CouponUsageAdminSerializer


ADMIN_RESOURCES = (
    ("users", User, "admin/manage/users/"),
    ("brands", Brand, "admin/manage/brands/"),
    ("categories", Category, "admin/manage/categories/"),
    ("subcategories", SubCategory, "admin/manage/subcategories/"),
    ("offers", Offer, "admin/manage/offers/"),
    ("colors", Color, "admin/manage/colors/"),
    ("unit-types", UnitType, "admin/manage/unit-types/"),
    ("units", Unit, "admin/manage/units/"),
    ("regions", Region, "admin/manage/regions/"),
    ("products", Product, "admin/manage/products/"),
    ("product-highlights", ProductHighlight, "admin/manage/product-highlights/"),
    ("product-messages", ProductMessage, "admin/manage/product-messages/"),
    ("product-variants", ProductVariant, "admin/manage/product-variants/"),
    ("product-variant-units", ProductVariantUnit, "admin/manage/product-variant-units/"),
    ("product-images", ProductImage, "admin/manage/product-images/"),
    ("wishlists", Wishlist, "admin/manage/wishlists/"),
    ("carts", Cart, "admin/manage/carts/"),
    ("addresses", Address, "admin/manage/addresses/"),
    ("user-profiles", UserProfile, "admin/manage/user-profiles/"),
    ("orders", Order, "admin/manage/orders/"),
    ("order-items", OrderItem, "admin/manage/order-items/"),
    ("hero-banners", HeroBanner, "admin/manage/hero-banners/"),
    ("trust-benefits", TrustBenefit, "admin/manage/trust-benefits/"),
    ("promo-banners", PromoBanner, "admin/manage/promo-banners/"),
    ("hero-side-banners", HeroSideBanner, "admin/manage/hero-side-banners/"),
    ("coupons", Coupon, "admin/manage/coupons/"),
    ("welcome-bonuses", WelcomeBonus, "admin/manage/welcome-bonuses/"),
    ("coupon-usages", CouponUsage, "admin/manage/coupon-usages/"),
)

# Fields disabled in the dashboard while retaining their database data.
SCHEMA_EXCLUDED_FIELDS = {
    "product-variants": {"regions"},
}


class SuperAdminSchemaView(APIView):
    permission_classes = (IsSuperAdmin,)

    def get(self, request):
        resources = []
        for key, model, endpoint in ADMIN_RESOURCES:
            fields = []
            excluded_fields = SCHEMA_EXCLUDED_FIELDS.get(key, set())
            for field in model._meta.fields:
                fields.append(
                    {
                        "name": field.name,
                        "type": field.get_internal_type(),
                        "required": not field.blank
                        and not field.null
                        and field.default is NOT_PROVIDED,
                        "read_only": field.auto_created
                        or not field.editable
                        or getattr(field, "auto_now", False)
                        or getattr(field, "auto_now_add", False),
                        "related_model": (
                            field.remote_field.model._meta.label_lower
                            if field.remote_field
                            else None
                        ),
                        "choices": [
                            {"value": value, "label": label}
                            for value, label in (field.choices or [])
                        ],
                    }
                )
            for field in model._meta.many_to_many:
                if field.name in excluded_fields:
                    continue
                fields.append(
                    {
                        "name": field.name,
                        "type": "ManyToManyField",
                        "required": False,
                        "read_only": False,
                        "related_model": field.remote_field.model._meta.label_lower,
                        "choices": [],
                    }
                )
            resources.append(
                {
                    "key": key,
                    "model": model._meta.label_lower,
                    "endpoint": f"/{endpoint}",
                    "capabilities": ["list", "retrieve", "create", "update", "delete"],
                    "fields": fields,
                }
            )
        return Response({"resources": resources})


class SuperAdminOverviewView(APIView):
    permission_classes = (IsSuperAdmin,)

    def get(self, request):
        return Response(
            {
                "resources": {
                    key: model.objects.count() for key, model, _ in ADMIN_RESOURCES
                },
                "orders": {
                    "pending": Order.objects.filter(status="Pending").count(),
                    "processing": Order.objects.filter(status="Processing").count(),
                    "shipped": Order.objects.filter(status="Shipped").count(),
                    "delivered": Order.objects.filter(status="Delivered").count(),
                    "cancelled": Order.objects.filter(status="Cancelled").count(),
                },
            }
        )

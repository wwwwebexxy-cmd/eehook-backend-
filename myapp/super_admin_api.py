"""Super Admin management API for the Order Dashboard.

The Django Admin is the source of truth for which records a Super Admin can
manage. These viewsets expose the same registered models to the dashboard,
including multipart uploads and the nested Product records used by the admin
inlines.
"""

from django.db.models.fields import NOT_PROVIDED
from django.db import transaction
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import filters, serializers, viewsets
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

import nested_admin
from django.contrib import admin
from types import MethodType
from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.db import transaction
from .models import *

admin.site.site_header = "Order Dashboard"
admin.site.site_title = "Order Dashboard"
admin.site.index_title = "Order Dashboard"


def _super_admin_site_permission(_site, request):
    """Django admin must use the same role boundary as API admin endpoints."""
    user = request.user
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and user.is_staff
        and user.role == "Super Admin"
    )


admin.site.has_permission = MethodType(_super_admin_site_permission, admin.site)

@admin.register(User)
class UserAdmin(admin.ModelAdmin):

    list_display = (
        "email",
        "role",
        "is_staff",
        "is_active"
    )

    search_fields = ( "email",)
    list_filter = ("role", "is_active")

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "is_active",
        "created_at"
    )

    search_fields = ("name",)

@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "category",
        "is_active"
    )

    list_filter = ( "category", )


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "discount_percentage",
        "is_active"
    )
    
@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):

    list_display = ("name","code")

@admin.register(UnitType)
class UnitTypeAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)

@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("name", "unit_type")
    list_filter = ("unit_type",)

@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)

class ProductImageInline( nested_admin.NestedTabularInline ):

    model = ProductImage
    extra = 1
    fields = ('image', 'position', 'is_primary')
    ordering = ('position', 'id')

class ProductVariantSizeInline( nested_admin.NestedTabularInline):

    model = ProductVariantUnit
    extra = 1
    fields = ('unit_type', 'unit', 'sku', 'price', 'stock')

class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        exclude = ('regions',)
        widgets = {
            'price_type': forms.RadioSelect(choices=ProductVariant.PRICE_TYPE_CHOICES),
        }

class ProductVariantInline( nested_admin.NestedStackedInline ):

    model = ProductVariant
    form = ProductVariantForm
    extra = 1
    inlines = [
        ProductImageInline,
        ProductVariantSizeInline
    ]

class ProductAdminForm(forms.ModelForm):
    manual_related_products = forms.ModelMultipleChoiceField(
        queryset=Product.objects.none(),
        required=False,
        widget=FilteredSelectMultiple("Related products", is_stacked=False),
        help_text="Select up to four active products. The dashboard API preserves the submitted order.",
    )

    class Meta:
        model = Product
        fields = '__all__'
        # This relationship has an explicit ordered through model, so Django's
        # generic M2M widget cannot safely save it. The dedicated field above
        # is the only supported admin editing surface.
        exclude = ("related_products",)
        widgets = {
            "related_product_mode": forms.RadioSelect(
                choices=Product.RELATED_PRODUCT_MODE_CHOICES
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Product.objects.filter(is_active=True).order_by("name", "id")
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
            if self.instance.related_product_mode == Product.RELATED_PRODUCT_MODE_MANUAL:
                self.initial["manual_related_products"] = list(
                    self.instance.related_product_links.order_by("position", "id").values_list(
                        "related_product_id", flat=True
                    )
                )
        self.fields["manual_related_products"].queryset = queryset

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        subcategory = cleaned_data.get('subcategory')
        if category and subcategory and subcategory.category_id != category.id:
            self.add_error(
                'subcategory',
                'The subcategory must belong to the selected category.',
            )

        mode = cleaned_data.get("related_product_mode")
        related_products = list(cleaned_data.get("manual_related_products") or [])
        if mode == Product.RELATED_PRODUCT_MODE_MANUAL:
            if len(related_products) > 4:
                self.add_error(
                    "manual_related_products",
                    "Select no more than four related products.",
                )
            if self.instance and self.instance.pk in {item.pk for item in related_products}:
                self.add_error(
                    "manual_related_products",
                    "A product cannot be related to itself.",
                )

        return cleaned_data

    def _save_manual_related_products(self, product):
        if product.related_product_mode != Product.RELATED_PRODUCT_MODE_MANUAL:
            ProductRelatedProduct.objects.filter(product=product).delete()
            return
        related_products = list(self.cleaned_data.get("manual_related_products") or [])
        ProductRelatedProduct.objects.filter(product=product).delete()
        ProductRelatedProduct.objects.bulk_create(
            [
                ProductRelatedProduct(
                    product=product,
                    related_product=related_product,
                    position=position,
                )
                for position, related_product in enumerate(related_products)
            ]
        )

    def save(self, commit=True):
        product = super().save(commit=commit)
        if commit:
            self._save_manual_related_products(product)
            return product

        original_save_m2m = self.save_m2m

        def save_m2m():
            original_save_m2m()
            self._save_manual_related_products(product)

        self.save_m2m = save_m2m
        return product

@admin.register(Product)
class ProductAdmin(nested_admin.NestedModelAdmin):
    form = ProductAdminForm
    
    class Media:
        js = ('js/price_toggle.js', 'js/related_products_toggle.js')

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.request = request
        return form

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        # Product, variants, sizes, and images submitted through the nested
        # admin form must commit or roll back together.
        with transaction.atomic():
            return super().changeform_view(request, object_id, form_url, extra_context)

    list_display = (
        "name",
        "category",
        "subcategory",
        "brand",
        "is_active"
    )

    list_filter = (
        "category",
        "subcategory",
        "brand",
        "is_active"
    )

    search_fields = ("name",)

    fieldsets = (
        ("Product Information",
            {    "fields": ("name", "description", "key_features")}
        ),

        ( "Category Details",
            { "fields": ( "category","subcategory", "brand")}
        ),

        ("Offer Details",
            {"fields": ( "offer", ) }
        ),

        ("Sales & Delivery Info",
            {"fields": ("seller_name", "shipping_fee", "estimated_delivery_time", "warranty_info")}
        ),

        ("Promotional & Social",
            {"fields": ("current_viewers_count", "promotional_banner_image", "promotional_banner_link")}
        ),

        ("Related Products",
            {
                "fields": ("related_product_mode", "manual_related_products"),
                "description": (
                    "Manual: choose up to four products. Automatic: recommendations are "
                    "selected from relevant active catalog products. None: no chooser is shown."
                ),
            }
        ),

        ("Status",
            {"fields": ("is_active",)}
        ),
        )

    inlines = [ProductVariantInline]

@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "get_product",
        "variant",
        "variant_unit",
        "created_at"
    )

    def get_product(self, obj):
        return obj.variant.product.name

    get_product.short_description = "Product"

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "variant_unit",
        "quantity"
    )

@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):

    list_display = (
        "full_name",
        "city",
        "postal_code",
        "country",
        "phone"
    )

admin.site.register(UserProfile)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):

    list_display = (
        "order_number",
        "customer_email",
        "total_amount",
        "payment_status",
        "status",
        "created_at",
    )
    list_filter = ("status", "payment_status", "created_at")
    search_fields = ("user__email", "user__first_name", "stripe_session_id")
    ordering = ("-created_at",)

    @admin.display(description="Order")
    def order_number(self, obj):
        return str(obj)

    @admin.display(description="Customer")
    def customer_email(self, obj):
        return obj.user.email

admin.site.register(OrderItem)


@admin.register(HeroBanner)
class HeroBannerAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "display_order",
        "is_active",
    )

    list_filter = (
        "is_active",
    )

    ordering = (
        "display_order",
    )

    search_fields = (
        "title",
        "subtitle",
    )


@admin.register(TrustBenefit)
class TrustBenefitAdmin(admin.ModelAdmin):
    list_display = ("title", "key", "icon_key", "display_order", "is_active", "updated_at")
    list_filter = ("icon_key", "is_active")
    ordering = ("display_order", "id")
    search_fields = ("key", "title", "description")


@admin.register(PromoBanner)
class PromoBannerAdmin(admin.ModelAdmin):
    list_display = ("id", "is_active", "link")
    list_filter = ("is_active",)
    search_fields = ("link",)

@admin.register(HeroSideBanner)
class HeroSideBannerAdmin(admin.ModelAdmin):
    list_display = ("id", "is_active", "link")
    list_filter = ("is_active",)

from django.utils.html import format_html

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    class CouponAdminForm(forms.ModelForm):
        class Meta:
            model = Coupon
            fields = "__all__"

        def clean(self):
            cleaned = super().clean()
            applicability = cleaned.get("applicability_type")
            products = cleaned.get("products")
            category = cleaned.get("category")
            if applicability == Coupon.APPLICABILITY_PRODUCT and not products and not self.instance.pk:
                self.add_error("products", "Select at least one product for a product-wise coupon.")
            if applicability == Coupon.APPLICABILITY_CATEGORY:
                if not category:
                    self.add_error("category", "A category is required for a category-wise coupon.")
                if products:
                    self.add_error("products", "Category-wise coupons must not contain product targets.")
            return cleaned

    form = CouponAdminForm
    list_display = (
        "code",
        "applicability_type",
        "coupon_target",
        "discount_type",
        "discount_value",
        "start_date",
        "end_date",
        "is_active",
    )
    search_fields = ('code', 'products__name', 'category__name')
    autocomplete_fields = ('products', 'category')
    list_filter = ('applicability_type', 'discount_type', 'is_active', 'start_date', 'end_date')

    def coupon_target(self, obj):
        if obj.applicability_type == Coupon.APPLICABILITY_CATEGORY:
            return obj.category.name if obj.category else "-"
        return ", ".join(obj.products.values_list("name", flat=True)[:3]) or "All products (legacy)"

    coupon_target.short_description = "Target"

    def discount_value(self, obj):
        if obj.discount_type == Coupon.DISCOUNT_FIXED:
            return obj.fixed_amount
        return f"{obj.discount_percentage}%"

    discount_value.short_description = "Discount"

    def copy_code_button(self, obj):
        if obj.code:
            return format_html(
                '<button type="button" onclick="navigator.clipboard.writeText(\'{}\'); alert(\'Copied: {}\')" style="cursor: pointer; padding: 2px 6px; background-color: #417690; color: white; border: none; border-radius: 3px;">Copy</button>',
                obj.code, obj.code
            )
        return "-"
    copy_code_button.short_description = "Copy Code"


@admin.register(WelcomeBonus)
class WelcomeBonusAdmin(admin.ModelAdmin):
    """A separate admin section; redemption codes are never listed here."""

    class WelcomeBonusAdminForm(forms.ModelForm):
        class Meta:
            model = WelcomeBonus
            fields = "__all__"

        def clean(self):
            cleaned = super().clean()
            applicability = cleaned.get("applicability_type")
            products = cleaned.get("products")
            category = cleaned.get("category")
            if applicability == WelcomeBonus.APPLICABILITY_PRODUCT and not products:
                self.add_error("products", "Select at least one product for a product-wise welcome bonus.")
            if applicability == WelcomeBonus.APPLICABILITY_CATEGORY:
                if not category:
                    self.add_error("category", "A category is required for a category-wise welcome bonus.")
                if products:
                    self.add_error("products", "Category-wise welcome bonuses must not contain product targets.")
            return cleaned

    form = WelcomeBonusAdminForm
    list_display = (
        "name",
        "applicability_type",
        "welcome_bonus_target",
        "discount_type",
        "discount_value",
        "start_date",
        "end_date",
        "is_active",
        "assigned_count",
        "claimed_count",
        "redeemed_count",
    )
    list_filter = ("applicability_type", "discount_type", "is_active", "start_date", "end_date")
    search_fields = ("name", "products__name", "category__name")
    autocomplete_fields = ("products", "category")
    readonly_fields = ("archived_at", "created_at", "updated_at")

    @admin.display(description="Target")
    def welcome_bonus_target(self, obj):
        if obj.applicability_type == WelcomeBonus.APPLICABILITY_CATEGORY:
            return obj.category.name if obj.category else "-"
        return ", ".join(obj.products.values_list("name", flat=True)[:3])

    @admin.display(description="Discount")
    def discount_value(self, obj):
        return obj.fixed_amount if obj.discount_type == WelcomeBonus.DISCOUNT_FIXED else f"{obj.discount_percentage}%"

    @admin.display(description="Assigned")
    def assigned_count(self, obj):
        return obj.assignments.count()

    @admin.display(description="Claimed")
    def claimed_count(self, obj):
        return obj.assignments.filter(
            status__in=(
                WelcomeBonusAssignment.STATUS_CLAIMED,
                WelcomeBonusAssignment.STATUS_REDEEMED,
            )
        ).count()

    @admin.display(description="Redeemed")
    def redeemed_count(self, obj):
        return obj.assignments.filter(status=WelcomeBonusAssignment.STATUS_REDEEMED).count()

    def delete_model(self, request, obj):
        # Mirror the dashboard's archival delete and retain order history.
        from django.utils import timezone

        obj.is_active = False
        obj.archived_at = timezone.now()
        obj.save(update_fields=("is_active", "archived_at", "updated_at"))

    def delete_queryset(self, request, queryset):
        from django.utils import timezone

        now = timezone.now()
        queryset.update(is_active=False, archived_at=now, updated_at=now)


@admin.register(WelcomeBonusRedemption)
class WelcomeBonusRedemptionAdmin(admin.ModelAdmin):
    list_display = ("order", "user", "welcome_bonus", "promotion_type", "applied_amount", "redeemed_at")
    list_filter = ("promotion_type", "redeemed_at")
    search_fields = ("user__email", "welcome_bonus__name", "order__id")
    fields = (
        "assignment",
        "order",
        "user",
        "welcome_bonus",
        "promotion_type",
        "discount_type",
        "discount_value",
        "applied_amount",
        "redeemed_at",
    )
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):
    list_display = ('user', 'coupon', 'product', 'used_at')
    search_fields = ('user__email', 'coupon__code', 'product__name')
    list_filter = ('used_at',)

@admin.register(CouponApplication)
class CouponApplicationAdmin(admin.ModelAdmin):
    list_display = ('user', 'coupon', 'product', 'applied_at')
    search_fields = ('user__email', 'coupon__code', 'product__name')
    list_filter = ('applied_at',)

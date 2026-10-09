from decimal import Decimal

from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import *
from .utils import *    
from .welcome_bonus import (
    get_eligible_welcome_bonus_assignment,
    calculate_welcome_bonus_price,
    welcome_bonus_validation_error,
)

class RegisterSerializer(serializers.ModelSerializer):

    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "first_name",
            "email",
            "password",
            "confirm_password"
        ]

        extra_kwargs = {
            "password": {
                "write_only": True
            }
        }

    def validate(self, data):

        data["email"] = data["email"].strip().lower()

        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError(
                "Passwords do not match"
            )

        try:
            validate_password(data["password"])
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": error.messages})

        if User.objects.filter(
            email=data["email"]
        ).exists():
            raise serializers.ValidationError(
                "Email already exists"
            )

        return data

    def create(self, validated_data):

        validated_data.pop("confirm_password")

        user = User(
            first_name=validated_data["first_name"],
            email=validated_data["email"],
            is_active=True
        )

        user.set_password(validated_data["password"])
        user.save()

        UserProfile.objects.create(user=user)

        return user
    
class LoginSerializer(serializers.Serializer):

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    def validate(self, data):

        user = authenticate(
            username=data["email"],
            password=data["password"]
        )

        if not user:
            raise serializers.ValidationError(
                "Invalid Email or Password"
            )

        data["user"] = user

        return data
    
class ForgotPasswordSerializer(serializers.Serializer):

    email = serializers.EmailField()
    def validate(self, data):
        data["email"] = data["email"].strip().lower()
        # The caller returns one generic message in both cases to prevent
        # account enumeration.
        data["user"] = User.objects.filter(email=data["email"]).first()
        return data

class ResetPasswordSerializer( serializers.Serializer):

    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    def validate(self, data):

        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError("Passwords do not match")

        try:
            validate_password(data["password"])
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": error.messages})

        return data
    
class CategorySerializer(serializers.ModelSerializer):

    class Meta:
        model = Category

        fields = [
            "id",
            "name",
            "image",
            "is_active"
        ]

class SubCategorySerializer(serializers.ModelSerializer):

    category_name = serializers.CharField(
        source="category.name",
        read_only=True
    )


    class Meta:
        model = SubCategory

        fields = [
            "id",
            "category",
            "category_name",
            "name",
            "image",
            "is_active"
        ]


class BrandSerializer(serializers.ModelSerializer):

    class Meta:
        model = Brand
        fields = [
            "id",
            "name",
            "slug",
            "logo",
            "is_active",
        ]
        read_only_fields = ["id", "slug"]

class ProductImageSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProductImage
        fields = [
            "id",
            "image",
            "is_primary",
            "position",
        ]

class ColorSerializer(serializers.ModelSerializer):

    class Meta:
        model = Color

        fields = [
            "id",
            "name",
            "code"
        ]




class UnitSerializer(serializers.ModelSerializer):

    unit_type = serializers.CharField(source="unit_type.name", read_only=True)

    class Meta:
        model = Unit

        fields = [
            "id",
            "name",
            "unit_type"
        ]

class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = [
            "id",
            "name"
        ]
        
class ProductVariantUnitSerializer(
    serializers.ModelSerializer
):

    size = UnitSerializer(
        source="unit",
        read_only=True
    )

    discounted_price = serializers.SerializerMethodField()

    discount_amount = serializers.SerializerMethodField()

    has_offer = serializers.SerializerMethodField()

    discount_percentage = serializers.SerializerMethodField()

    class Meta:

        model = ProductVariantUnit

        fields = [
            "id",
            "size",
            "sku",
            "price",
            "discounted_price",
            "discount_amount",
            "has_offer",
            "discount_percentage",
            "stock",
        ]

    def get_discounted_price(
        self,
        obj
    ):

        return calculate_offer_price(
            obj.price or 0,
            obj.variant.product.offer
        )

    def get_discount_amount(
        self,
        obj
    ):

        return calculate_discount_amount(
            obj.price or 0,
            obj.variant.product.offer
        )

    def get_has_offer(
        self,
        obj
    ):

        return is_offer_valid(
            obj.variant.product.offer
        )

    def get_discount_percentage(
        self,
        obj
    ):

        if is_offer_valid(
            obj.variant.product.offer
        ):

            return obj.variant.product.offer.discount_percentage

        return 0     

class ProductVariantSerializer(serializers.ModelSerializer):

    color = ColorSerializer(
        read_only=True
    )

    sizes = ProductVariantUnitSerializer(
        many=True,
        read_only=True
    )

    images = ProductImageSerializer(
        many=True,
        read_only=True
    )

    discounted_price = serializers.SerializerMethodField()
    discount_amount = serializers.SerializerMethodField()
    has_offer = serializers.SerializerMethodField()
    discount_percentage = serializers.SerializerMethodField()


    class Meta:
        model = ProductVariant

        fields = [
            "id",
            "color",
            "sku",
            "sizes",
            "images",
            "price_type",
            "price",
            "discounted_price",
            "discount_amount",
            "has_offer",
            "discount_percentage",
            "stock"
        ]

    def get_discounted_price(self, obj):
        if obj.price_type == "single" and obj.price is not None:
            return calculate_offer_price(obj.price, obj.product.offer)
        return None

    def get_discount_amount(self, obj):
        if obj.price_type == "single" and obj.price is not None:
            return calculate_discount_amount(obj.price, obj.product.offer)
        return None

    def get_has_offer(self, obj):
        return is_offer_valid(obj.product.offer)

    def get_discount_percentage(self, obj):
        if is_offer_valid(obj.product.offer):
            return obj.product.offer.discount_percentage
        return 0


class RelatedProductSerializer(serializers.ModelSerializer):
    """The compact, purchasable payload used by the add-to-cart chooser."""

    variants = ProductVariantSerializer(many=True, read_only=True)
    image = serializers.SerializerMethodField()
    starting_price = serializers.SerializerMethodField()
    discounted_price = serializers.SerializerMethodField()
    discount_amount = serializers.SerializerMethodField()
    has_offer = serializers.SerializerMethodField()
    discount_percentage = serializers.SerializerMethodField()
    requires_variant_selection = serializers.SerializerMethodField()
    default_variant_id = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "description",
            "image",
            "variants",
            "starting_price",
            "discounted_price",
            "discount_amount",
            "has_offer",
            "discount_percentage",
            "requires_variant_selection",
            "default_variant_id",
        )

    def _variants(self, obj):
        # The related-product service prefetches only purchasable variants.
        # Keeping this conversion in one place also avoids accidental query
        # repetition while serializing image and variant-choice fields.
        return list(obj.variants.all())

    def get_image(self, obj):
        for variant in self._variants(obj):
            images = list(variant.images.all())
            primary = next((image for image in images if image.is_primary), None)
            image = primary or (images[0] if images else None)
            if image:
                return image.image.url
        return None

    def _prices(self, obj):
        return get_product_prices(obj)

    def get_starting_price(self, obj):
        return self._prices(obj)["starting_price"]

    def get_discounted_price(self, obj):
        return self._prices(obj)["discounted_price"]

    def get_discount_amount(self, obj):
        return self._prices(obj)["discount_amount"]

    def get_has_offer(self, obj):
        return self._prices(obj)["has_offer"]

    def get_discount_percentage(self, obj):
        return self._prices(obj)["discount_percentage"]

    def get_requires_variant_selection(self, obj):
        variants = self._variants(obj)
        return len(variants) != 1 or variants[0].price_type == "multiple"

    def get_default_variant_id(self, obj):
        variants = self._variants(obj)
        if len(variants) == 1 and variants[0].price_type == "single":
            return variants[0].id
        return None


class CartSerializer(serializers.ModelSerializer):

    product = serializers.IntegerField(
        source="variant.product.id",
        read_only=True
    )

    variant = serializers.IntegerField(
        source="variant.id",
        read_only=True
    )

    variant_size = serializers.IntegerField(
        source="variant_unit.id",
        read_only=True
    )

    product_name = serializers.CharField(
        source="variant.product.name",
        read_only=True
    )

    product_image = serializers.SerializerMethodField()

    color = serializers.SerializerMethodField()

    size = serializers.SerializerMethodField()

    unit_type = serializers.SerializerMethodField()

    original_price = serializers.SerializerMethodField()
    stock = serializers.SerializerMethodField()

    def get_color(self, obj):
        return obj.variant.color.name if obj.variant and obj.variant.color else None

    def get_size(self, obj):
        return obj.variant_unit.unit.name if obj.variant_unit and obj.variant_unit.unit else None

    def get_unit_type(self, obj):
        return obj.variant_unit.unit.unit_type.name if obj.variant_unit and obj.variant_unit.unit and getattr(obj.variant_unit.unit, 'unit_type', None) else None

    def get_stock(self, obj):
        return obj.variant_unit.stock if obj.variant_unit else 0

    discounted_price = serializers.SerializerMethodField()

    discount_amount = serializers.SerializerMethodField()

    has_offer = serializers.SerializerMethodField()

    discount_percentage = serializers.SerializerMethodField()

    coupon_code = serializers.SerializerMethodField()

    coupon_discount_type = serializers.SerializerMethodField()

    coupon_status = serializers.SerializerMethodField()

    promotion_type = serializers.SerializerMethodField()

    quantity = serializers.IntegerField(
        read_only=True
    )

    total_price = serializers.SerializerMethodField()

    class Meta:

        model = Cart

        fields = [
            "id",
            "product",
            "variant",
            "variant_size",
            "product_name",
            "product_image",
            "color",
            "size",
            "unit_type",
            "original_price",
            "discounted_price",
            "discount_amount",
            "has_offer",
            "discount_percentage",
            "coupon_code",
            "coupon_discount_type",
            "coupon_status",
            "promotion_type",
            "quantity",
            "stock",
            "total_price",
            "created_at",
        ]

    def get_product_image(
        self,
        obj
    ):

        image = obj.variant.images.filter(
            is_primary=True
        ).first()

        if not image:

            image = obj.variant.images.first()

        if image:

            return image.image.url

        return None

    def get_original_price(self, obj):
        if obj.variant.price_type == "single":
            return obj.variant.price or 0
        if obj.variant_unit:
            return obj.variant_unit.price or 0
        return 0

    def get_discounted_price(
        self,
        obj
    ):
        price = (obj.variant.price or 0) if obj.variant.price_type == "single" else ((obj.variant_unit.price or 0) if obj.variant_unit else 0)
        dp = calculate_offer_price(
            price,
            obj.variant.product.offer
        )
        welcome_bonus = get_eligible_welcome_bonus_assignment(
            getattr(obj, "welcome_bonus_assignment_id", None),
            obj.user,
            obj.variant.product,
        )
        if welcome_bonus:
            dp = calculate_welcome_bonus_price(dp, welcome_bonus)
        else:
            coupon = get_eligible_coupon(getattr(obj, "coupon_id", None), obj.variant.product)
            if coupon:
                dp = calculate_coupon_price(dp, coupon)
        return max(dp, 0).quantize(Decimal("0.01"))

    def get_discount_amount(
        self,
        obj
    ):
        price = (obj.variant.price or 0) if obj.variant.price_type == "single" else ((obj.variant_unit.price or 0) if obj.variant_unit else 0)
        dp = self.get_discounted_price(obj)
        return max(price - dp, 0).quantize(Decimal("0.01"))

    def get_has_offer(
        self,
        obj
    ):
        has_prod = is_offer_valid(obj.variant.product.offer)
        has_promotion = bool(
            get_eligible_welcome_bonus_assignment(
                getattr(obj, "welcome_bonus_assignment_id", None),
                obj.user,
                obj.variant.product,
            )
            or get_eligible_coupon(getattr(obj, "coupon_id", None), obj.variant.product)
        )
        return has_prod or has_promotion

    def get_discount_percentage(
        self,
        obj
    ):
        p_pct = obj.variant.product.offer.discount_percentage if is_offer_valid(obj.variant.product.offer) else 0
        welcome_bonus = get_eligible_welcome_bonus_assignment(
            getattr(obj, "welcome_bonus_assignment_id", None),
            obj.user,
            obj.variant.product,
        )
        if welcome_bonus:
            c_pct = (
                welcome_bonus.welcome_bonus.discount_percentage
                if welcome_bonus.welcome_bonus.discount_type == "PERCENTAGE"
                else 0
            )
        else:
            coupon = get_eligible_coupon(getattr(obj, "coupon_id", None), obj.variant.product)
            c_pct = coupon.discount_percentage if coupon and coupon.discount_type == "PERCENTAGE" else 0
        return p_pct + c_pct

    def get_coupon_code(self, obj):
        # The user-specific welcome code must never be rendered in cart UI.
        if getattr(obj, "welcome_bonus_assignment_id", None):
            return None
        coupon = get_eligible_coupon(getattr(obj, "coupon_id", None), obj.variant.product)
        return coupon.code if coupon else None

    def get_coupon_discount_type(self, obj):
        welcome_bonus = get_eligible_welcome_bonus_assignment(
            getattr(obj, "welcome_bonus_assignment_id", None),
            obj.user,
            obj.variant.product,
        )
        if welcome_bonus:
            return welcome_bonus.welcome_bonus.discount_type
        coupon = get_eligible_coupon(getattr(obj, "coupon_id", None), obj.variant.product)
        return coupon.discount_type if coupon else None

    def get_coupon_status(self, obj):
        if getattr(obj, "coupon_status", None):
            return obj.coupon_status
        if getattr(obj, "welcome_bonus_assignment_id", None):
            welcome_bonus = get_eligible_welcome_bonus_assignment(
                obj.welcome_bonus_assignment_id,
                obj.user,
                obj.variant.product,
            )
            return "WELCOME_BONUS_ACTIVE" if welcome_bonus else "WELCOME_BONUS_INACTIVE"
        if not getattr(obj, "coupon_id", None):
            return None
        return (
            "ACTIVE"
            if get_eligible_coupon(obj.coupon_id, obj.variant.product)
            else "COUPON_INACTIVE"
        )

    def get_promotion_type(self, obj):
        if getattr(obj, "welcome_bonus_assignment_id", None):
            return "WELCOME_BONUS"
        if getattr(obj, "coupon_id", None):
            return "COUPON"
        return None

    def get_total_price(
        self,
        obj
    ):
        discounted_price = self.get_discounted_price(obj)
        return discounted_price * obj.quantity
    
    
class ProfileSerializer(serializers.ModelSerializer):

    phone = serializers.CharField(source="profile.phone", required=False)
    gender = serializers.CharField(source="profile.gender", required=False)
    date_of_birth = serializers.DateField(source="profile.date_of_birth", required=False)

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "email",
            "phone",
            "gender",
            "date_of_birth",
        ]
        read_only_fields = ["email"]

    def update(self, instance, validated_data):

        profile_data = validated_data.pop("profile", {})

        instance.first_name = validated_data.get(
            "first_name",
            instance.first_name
        )

        instance.save()

        profile = UserProfile.objects.get(user=instance)

        profile.phone = profile_data.get(
            "phone",
            profile.phone
        )

        profile.gender = profile_data.get(
            "gender",
            profile.gender
        )

        profile.date_of_birth = profile_data.get(
            "date_of_birth",
            profile.date_of_birth
        )
        profile.save()
        

        return instance


class AddressSerializer(serializers.ModelSerializer):

    class Meta:
        model = Address
        fields = "__all__"
        read_only_fields = ["id", "user", "created_at"]

    def create(self, validated_data):

        user = self.context["request"].user

        if validated_data.get("is_default"):
            Address.objects.filter(user=user).update(is_default=False)

        return Address.objects.create(user=user, **validated_data)

    def update(self, instance, validated_data):

        if validated_data.get("is_default"):
            Address.objects.filter(user=instance.user).exclude(id=instance.id).update(is_default=False)

        return super().update(instance, validated_data)
        
class OfferSerializer(
    serializers.ModelSerializer
):

    class Meta:

        model = Offer

        fields = "__all__"
        
class OrderItemSerializer(
    serializers.ModelSerializer
):

    product_name = serializers.CharField(
        source="product.name",
        read_only=True
    )

    color = serializers.CharField(
        source="color.name",
        read_only=True
    )

    size = serializers.CharField(
        source="unit.name",
        read_only=True
    )

    unit_type = serializers.CharField(
        source="unit.unit_type.name",
        read_only=True
    )

    product_image = serializers.SerializerMethodField()

    class Meta:

        model = OrderItem

        fields = [

            "id",

            "product_name",

            "product_image",

            "color",

            "size",

            "unit_type",

            "quantity",

            "original_price",

            "discount_amount",

            "price",

            "total_price"

        ]

    def get_product_image( self, obj):

        if not obj.product:
            return None

        variant = None

        if obj.color:

            variant = obj.product.variants.filter(
                color=obj.color
            ).first()

        if not variant:

            variant = obj.product.variants.first()

        if not variant:
            return None

        image = variant.images.filter(
            is_primary=True
        ).first()

        if not image:

            image = variant.images.first()

        if image:

            return image.image.url

        return None
class WelcomeBonusRedemptionSummarySerializer(serializers.ModelSerializer):
    welcome_bonus_name = serializers.CharField(source="welcome_bonus.name", read_only=True)

    class Meta:
        model = WelcomeBonusRedemption
        fields = (
            "id",
            "promotion_type",
            "welcome_bonus_name",
            "discount_type",
            "discount_value",
            "applied_amount",
            "redeemed_at",
        )
        read_only_fields = fields


class OrderSerializer(
    serializers.ModelSerializer
):

    items = OrderItemSerializer(
        many=True,
        read_only=True
    )

    customer_name = serializers.CharField(
        source="user.first_name",
        read_only=True
    )

    customer_email = serializers.EmailField(
        source="user.email",
        read_only=True
    )

    payment_method = serializers.CharField(
        read_only=True
    )

    address_name = serializers.CharField(
        source="address.full_name",
        read_only=True
    )

    address_phone = serializers.CharField(
        source="address.phone",
        read_only=True
    )

    address_line = serializers.CharField(
        source="address.address_line",
        read_only=True
    )

    city = serializers.CharField(
        source="address.city",
        read_only=True
    )

    postcode = serializers.CharField(
        source="address.postal_code",
        read_only=True
    )

    country = serializers.CharField(
        source="address.country",
        read_only=True
    )

    welcome_bonus_redemptions = WelcomeBonusRedemptionSummarySerializer(
        many=True,
        read_only=True,
    )

    class Meta:

        model = Order

        fields = [

            "id",

            "customer_name",

            "customer_email",

            "subtotal",

            "discount_amount",

            "shipping_charge",

            "total_amount",

            "payment_method",

            "payment_status",

            "status",

            "created_at",

            "address_name",

            "address_phone",

            "address_line",

            "city",

            "postcode",

            "country",

            "updated_at",

            "cancelled_at",

            "items",

            "welcome_bonus_redemptions",

        ]
class AdminOrderSerializer(
    serializers.ModelSerializer
):

    customer_name = serializers.CharField(
        source="user.first_name",
        read_only=True
    )

    class Meta:

        model = Order

        fields = [

            "id",

            "customer_name",

            "total_amount",


            "payment_status",

            "status",

            "created_at"

        ]
        


class HomeSubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubCategory
        fields = [
            "id",
            "name",
            "image",
        ]

# new added catoegory serializers
class HomeCategorySerializer(serializers.ModelSerializer):
    subcategories = HomeSubCategorySerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "image",
            "subcategories",
        ]
        
        
class WishlistSerializer(serializers.ModelSerializer):

    product = serializers.IntegerField(
        source="variant.product.id",
        read_only=True
    )

    variant = serializers.IntegerField(
        source="variant.id",
        read_only=True
    )

    variant_size = serializers.IntegerField(
        source="variant_unit.id",
        read_only=True
    )

    product_name = serializers.CharField(
        source="variant.product.name",
        read_only=True
    )

    category = serializers.CharField(
        source="variant.product.category.name",
        read_only=True
    )

    color = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    unit_type = serializers.SerializerMethodField()
    stock = serializers.SerializerMethodField()

    def get_color(self, obj):
        return obj.variant.color.name if obj.variant and obj.variant.color else None

    def get_size(self, obj):
        return obj.variant_unit.unit.name if obj.variant_unit and obj.variant_unit.unit else None

    def get_unit_type(self, obj):
        return obj.variant_unit.unit.unit_type.name if obj.variant_unit and obj.variant_unit.unit and getattr(obj.variant_unit.unit, 'unit_type', None) else None

    def get_stock(self, obj):
        return obj.variant_unit.stock if obj.variant_unit else 0

    product_image = serializers.SerializerMethodField()

    original_price = serializers.SerializerMethodField()

    discounted_price = serializers.SerializerMethodField()

    discount_amount = serializers.SerializerMethodField()

    has_offer = serializers.SerializerMethodField()

    discount_percentage = serializers.SerializerMethodField()

    class Meta:

        model = Wishlist

        fields = [
            "id",
            "product",
            "variant",
            "variant_size",
            "product_name",
            "category",
            "color",
            "size",
            "unit_type",
            "stock",
            "product_image",
            "original_price",
            "discounted_price",
            "discount_amount",
            "has_offer",
            "discount_percentage",
            "created_at",
        ]

    def get_product_image(self, obj):

        if not obj.variant:
            return None

        image = obj.variant.images.filter(
            is_primary=True
        ).first()

        if not image:
            image = obj.variant.images.first()

        return image.image.url if image else None

    def get_original_price(self, obj):
        if not obj.variant:
            return None
    def get_original_price(self, obj):
        if not obj.variant:
            return None
        if obj.variant.price_type == "single":
            return obj.variant.price or 0
        if obj.variant_unit:
            return obj.variant_unit.price or 0
        return 0

    def get_discounted_price(self, obj):
        if not obj.variant:
            return None
        price = (obj.variant.price or 0) if obj.variant.price_type == "single" else ((obj.variant_unit.price or 0) if obj.variant_unit else 0)
        return calculate_offer_price(
            price,
            obj.variant.product.offer
        )

    def get_discount_amount(self, obj):
        if not obj.variant:
            return 0
        price = (obj.variant.price or 0) if obj.variant.price_type == "single" else ((obj.variant_unit.price or 0) if obj.variant_unit else 0)
        return calculate_discount_amount(
            price,
            obj.variant.product.offer
        )

    def get_has_offer(self, obj):

        if not obj.variant:
            return False

        return is_offer_valid(
            obj.variant.product.offer
        )

    def get_discount_percentage(self, obj):

        if not obj.variant:
            return 0

        if is_offer_valid(
            obj.variant.product.offer
        ):
            return obj.variant.product.offer.discount_percentage

        return 0
        
class ProductSerializer(serializers.ModelSerializer):

    category = CategorySerializer(
        read_only=True
    )

    subcategory = SubCategorySerializer(
        read_only=True
    )

    brand = BrandSerializer(
        read_only=True
    )

    offer = OfferSerializer(
        read_only=True
    )

    variants = ProductVariantSerializer(
        many=True,
        read_only=True
    )

    starting_price = serializers.SerializerMethodField()

    discounted_price = serializers.SerializerMethodField()

    discount_amount = serializers.SerializerMethodField()

    has_offer = serializers.SerializerMethodField()

    discount_percentage = serializers.SerializerMethodField()

    key_features = serializers.SerializerMethodField()

    related_products = serializers.SerializerMethodField()

    class Meta:

        model = Product

        fields = [
            "id",
            "name",
            "description",
            "category",
            "subcategory",
            "brand",
            "offer",
            "variants",
            "starting_price",
            "discounted_price",
            "discount_amount",
            "has_offer",
            "discount_percentage",
            "is_active",
            "created_at",
            "key_features",
            "shipping_fee",
            "estimated_delivery_time",
            "seller_name",
            "warranty_info",
            "current_viewers_count",
            "promotional_banner_image",
            "promotional_banner_link",
            "related_products",
        ]

    def get_starting_price(
        self,
        obj
    ):

        return get_product_prices(
            obj
        )["starting_price"]

    def get_discounted_price(
        self,
        obj
    ):

        return get_product_prices(
            obj
        )["discounted_price"]

    def get_discount_amount(
        self,
        obj
    ):

        return get_product_prices(
            obj
        )["discount_amount"]

    def get_has_offer(
        self,
        obj
    ):

        return get_product_prices(
            obj
        )["has_offer"]

    def get_discount_percentage(
        self,
        obj
    ):

        return get_product_prices(
            obj
        )["discount_percentage"]

    def get_key_features(self, obj):
        if obj.key_features:
            if isinstance(obj.key_features, list):
                return obj.key_features
            elif isinstance(obj.key_features, str):
                try:
                    import json
                    parsed = json.loads(obj.key_features)
                    if isinstance(parsed, list):
                        return parsed
                except Exception:
                    pass
                return [feature.strip() for feature in obj.key_features.split('\n') if feature.strip()]
        return []

    def get_related_products(self, obj):
        # Kept on the existing product-detail serializer so no parallel
        # product-detail endpoint is needed for the chooser. Catalog lists
        # intentionally opt out, avoiding recommendation queries per card.
        if not self.context.get("include_related_products", False):
            return []
        from .related_products import get_related_products

        products = get_related_products(obj)
        return RelatedProductSerializer(
            products,
            many=True,
            context=self.context,
        ).data


class HomepageProductSerializer(serializers.ModelSerializer):
    """Small product-card payload used by capped homepage discovery sections."""

    category = CategorySerializer(read_only=True)
    subcategory = SubCategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    product_image = serializers.SerializerMethodField()
    starting_price = serializers.SerializerMethodField()
    discounted_price = serializers.SerializerMethodField()
    original_price = serializers.SerializerMethodField()
    current_price = serializers.SerializerMethodField()
    discount_amount = serializers.SerializerMethodField()
    has_offer = serializers.SerializerMethodField()
    discount_percentage = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()
    default_variant_id = serializers.SerializerMethodField()
    default_variant_unit_id = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "category",
            "subcategory",
            "brand",
            "product_image",
            "starting_price",
            "original_price",
            "discounted_price",
            "current_price",
            "discount_amount",
            "has_offer",
            "discount_percentage",
            "in_stock",
            "default_variant_id",
            "default_variant_unit_id",
            "shipping_fee",
            "estimated_delivery_time",
            "warranty_info",
        ]

    def _price_values(self, obj):
        return get_product_prices(obj)

    def _variant_choices(self, obj):
        choices = []
        for variant in obj.variants.all():
            if variant.price_type == "single":
                if variant.price is not None:
                    choices.append((variant.price, variant.id, None, variant.stock > 0))
                continue
            for unit in variant.sizes.all():
                if unit.price is not None:
                    choices.append((unit.price, variant.id, unit.id, unit.stock > 0))
        return sorted(
            choices,
            key=lambda choice: (not choice[3], choice[0], choice[1], choice[2] or 0),
        )

    def _default_choice(self, obj):
        choices = self._variant_choices(obj)
        return choices[0] if choices else (None, None, None, False)

    def get_product_image(self, obj):
        variant_id = self._default_choice(obj)[1]
        variants = sorted(
            obj.variants.all(),
            key=lambda variant: (variant.id != variant_id, variant.id),
        )
        for variant in variants:
            images = list(variant.images.all())
            image = next((item for item in images if item.is_primary), None)
            image = image or (images[0] if images else None)
            if image:
                request = self.context.get("request")
                return request.build_absolute_uri(image.image.url) if request else image.image.url
        return None

    def get_starting_price(self, obj):
        return self._price_values(obj)["starting_price"]

    def get_original_price(self, obj):
        return self._price_values(obj)["starting_price"]

    def get_discounted_price(self, obj):
        return self._price_values(obj)["discounted_price"]

    def get_current_price(self, obj):
        return self._price_values(obj)["discounted_price"]

    def get_discount_amount(self, obj):
        return self._price_values(obj)["discount_amount"]

    def get_has_offer(self, obj):
        return self._price_values(obj)["has_offer"]

    def get_discount_percentage(self, obj):
        return self._price_values(obj)["discount_percentage"]

    def get_in_stock(self, obj):
        return any(choice[3] for choice in self._variant_choices(obj))

    def get_default_variant_id(self, obj):
        return self._default_choice(obj)[1]

    def get_default_variant_unit_id(self, obj):
        return self._default_choice(obj)[2]


class HomepageBrandSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Brand
        fields = ["id", "name", "slug", "logo", "product_count"]


class HomepageTrustBenefitSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrustBenefit
        fields = ["id", "key", "title", "description", "icon_key"]



class WishlistProductSerializer(
    serializers.Serializer
):

    product_id = serializers.IntegerField()

    product_name = serializers.CharField()

    image = serializers.ImageField(
        allow_null=True
    )

    category = serializers.CharField()

    wishlist_count = serializers.IntegerField()
    
class MyOrderSerializer(
    serializers.ModelSerializer
):

    items = OrderItemSerializer(
        many=True,
        read_only=True
    )

    total_items = serializers.SerializerMethodField()

    class Meta:

        model = Order

        fields = [

            "id",

            "created_at",

            "status",

            "payment_status",

            "total_amount",

            "total_items",

            "items",

        ]

    def get_total_items(
        self,
        obj
    ):

        return obj.items.count()
    

class HeroBannerSerializer( serializers.ModelSerializer):
    class Meta:

        model = HeroBanner
        fields = "__all__"

class PromoBannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromoBanner
        fields = "__all__"

class HeroSideBannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = HeroSideBanner
        fields = "__all__"

class CouponSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    target_name = serializers.SerializerMethodField(read_only=True)
    discount_value = serializers.SerializerMethodField(read_only=True)
    applicability_label = serializers.CharField(
        source="get_applicability_type_display",
        read_only=True,
    )
    discount_type_label = serializers.CharField(
        source="get_discount_type_display",
        read_only=True,
    )

    class Meta:
        model = Coupon
        fields = (
            "id",
            "code",
            "products",
            "category",
            "category_name",
            "target_name",
            "applicability_type",
            "applicability_label",
            "discount_type",
            "discount_type_label",
            "discount_percentage",
            "fixed_amount",
            "discount_value",
            "start_date",
            "end_date",
            "is_active",
            "created_at",
        )
        read_only_fields = (
            "id",
            "category_name",
            "target_name",
            "applicability_label",
            "discount_type_label",
            "discount_value",
            "created_at",
        )

    def validate_code(self, value):
        value = value.strip()
        if WelcomeBonusAssignment.objects.filter(code=value).exists():
            raise serializers.ValidationError(
                "This code is reserved for a user-specific welcome bonus."
            )
        return value

    def to_internal_value(self, data):
        # Keep the canonical model field names while accepting the compact
        # names commonly used by dashboard forms.
        data = data.copy()
        if "apply_to" in data and "applicability_type" not in data:
            apply_to = str(data["apply_to"]).upper()
            data["applicability_type"] = {
                "PRODUCT_WISE": Coupon.APPLICABILITY_PRODUCT,
                "CATEGORY_WISE": Coupon.APPLICABILITY_CATEGORY,
            }.get(apply_to, apply_to)
        if "product" in data and "products" not in data:
            data["products"] = [data["product"]]
        if "discount_type" in data:
            discount_type = str(data["discount_type"]).upper()
            if discount_type in {"FIXED_AMOUNT", "FIXED AMOUNT"}:
                data["discount_type"] = Coupon.DISCOUNT_FIXED
            elif discount_type == "PERCENTAGE_DISCOUNT":
                data["discount_type"] = Coupon.DISCOUNT_PERCENTAGE
        if "discount_value" in data:
            discount_type = str(
                data.get(
                    "discount_type",
                    getattr(self.instance, "discount_type", Coupon.DISCOUNT_PERCENTAGE),
                )
            ).upper()
            value_field = (
                "fixed_amount"
                if discount_type in {Coupon.DISCOUNT_FIXED, "FIXED_AMOUNT", "FIXED AMOUNT"}
                else "discount_percentage"
            )
            data.setdefault(value_field, data["discount_value"])
        return super().to_internal_value(data)

    def validate(self, attrs):
        instance = self.instance
        applicability = attrs.get(
            "applicability_type",
            getattr(instance, "applicability_type", Coupon.APPLICABILITY_PRODUCT),
        )
        category = attrs.get("category", getattr(instance, "category", None))
        products = attrs.get("products")
        if products is None and instance is not None:
            products = list(instance.products.all())
        products = list(products or [])

        if applicability == Coupon.APPLICABILITY_CATEGORY:
            if category is None:
                raise serializers.ValidationError(
                    {"category": "A category is required for a category-wise coupon."}
                )
            if products:
                raise serializers.ValidationError(
                    {"products": "Category-wise coupons must not contain product targets."}
                )
        elif applicability == Coupon.APPLICABILITY_PRODUCT:
            if category is not None:
                raise serializers.ValidationError(
                    {"category": "Category must be empty for a product-wise coupon."}
                )
            # Existing legacy coupons with an empty products relation mean
            # all products. Keep those records usable on edit, while every
            # newly-created product-wise coupon must name its target.
            if not products and instance is None:
                raise serializers.ValidationError(
                    {"products": "Select at least one product for a product-wise coupon."}
                )
        else:
            raise serializers.ValidationError(
                {"applicability_type": "Select Product or Category."}
            )

        discount_type = attrs.get(
            "discount_type",
            getattr(instance, "discount_type", Coupon.DISCOUNT_PERCENTAGE),
        )
        percentage = attrs.get(
            "discount_percentage",
            getattr(instance, "discount_percentage", None),
        )
        fixed_amount = attrs.get(
            "fixed_amount",
            getattr(instance, "fixed_amount", None),
        )

        if discount_type == Coupon.DISCOUNT_PERCENTAGE:
            if percentage is None or percentage <= 0 or percentage > 100:
                raise serializers.ValidationError(
                    {"discount_percentage": "Percentage must be greater than 0 and at most 100."}
                )
            attrs["fixed_amount"] = None
        elif discount_type == Coupon.DISCOUNT_FIXED:
            if fixed_amount is None or fixed_amount <= 0:
                raise serializers.ValidationError(
                    {"fixed_amount": "Fixed amount must be greater than 0."}
                )
            attrs["discount_percentage"] = None
        else:
            raise serializers.ValidationError(
                {"discount_type": "Select Percentage or Fixed Amount."}
            )

        start_date = attrs.get("start_date", getattr(instance, "start_date", None))
        end_date = attrs.get("end_date", getattr(instance, "end_date", None))
        if start_date and end_date and start_date >= end_date:
            raise serializers.ValidationError(
                {"end_date": "Expiry date must be after the start date."}
            )
        return attrs

    def create(self, validated_data):
        products = validated_data.pop("products", [])
        instance = Coupon(**validated_data)
        instance.full_clean()
        instance.save()
        instance.products.set(products)
        return instance

    def update(self, instance, validated_data):
        products = validated_data.pop("products", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.full_clean()
        instance.save()
        if products is not None:
            instance.products.set(products)
        return instance

    def get_target_name(self, obj):
        if obj.applicability_type == Coupon.APPLICABILITY_CATEGORY:
            return obj.category.name if obj.category else None
        return list(obj.products.values_list("name", flat=True))

    def get_discount_value(self, obj):
        return obj.fixed_amount if obj.discount_type == Coupon.DISCOUNT_FIXED else obj.discount_percentage


class WelcomeBonusSerializer(serializers.ModelSerializer):
    """Admin-facing campaign serializer. It deliberately has no code field."""

    category_name = serializers.CharField(source="category.name", read_only=True)
    target_name = serializers.SerializerMethodField(read_only=True)
    discount_value = serializers.SerializerMethodField(read_only=True)
    applicability_label = serializers.CharField(
        source="get_applicability_type_display", read_only=True
    )
    discount_type_label = serializers.CharField(
        source="get_discount_type_display", read_only=True
    )
    assigned_user_count = serializers.SerializerMethodField(read_only=True)
    claimed_user_count = serializers.SerializerMethodField(read_only=True)
    redeemed_user_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = WelcomeBonus
        fields = (
            "id",
            "name",
            "products",
            "category",
            "category_name",
            "target_name",
            "applicability_type",
            "applicability_label",
            "discount_type",
            "discount_type_label",
            "discount_percentage",
            "fixed_amount",
            "discount_value",
            "start_date",
            "end_date",
            "is_active",
            "assigned_user_count",
            "claimed_user_count",
            "redeemed_user_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "category_name",
            "target_name",
            "applicability_label",
            "discount_type_label",
            "discount_value",
            "assigned_user_count",
            "claimed_user_count",
            "redeemed_user_count",
            "created_at",
            "updated_at",
        )

    def to_internal_value(self, data):
        data = data.copy()
        if "title" in data and "name" not in data:
            data["name"] = data["title"]
        if "apply_to" in data and "applicability_type" not in data:
            apply_to = str(data["apply_to"]).upper()
            data["applicability_type"] = {
                "PRODUCT_WISE": WelcomeBonus.APPLICABILITY_PRODUCT,
                "CATEGORY_WISE": WelcomeBonus.APPLICABILITY_CATEGORY,
            }.get(apply_to, apply_to)
        if "product" in data and "products" not in data:
            data["products"] = [data["product"]]
        if "discount_type" in data:
            discount_type = str(data["discount_type"]).upper()
            if discount_type in {"FIXED_AMOUNT", "FIXED AMOUNT"}:
                data["discount_type"] = WelcomeBonus.DISCOUNT_FIXED
            elif discount_type == "PERCENTAGE_DISCOUNT":
                data["discount_type"] = WelcomeBonus.DISCOUNT_PERCENTAGE
        if "discount_value" in data:
            discount_type = str(
                data.get(
                    "discount_type",
                    getattr(self.instance, "discount_type", WelcomeBonus.DISCOUNT_PERCENTAGE),
                )
            ).upper()
            field = (
                "fixed_amount"
                if discount_type in {WelcomeBonus.DISCOUNT_FIXED, "FIXED_AMOUNT", "FIXED AMOUNT"}
                else "discount_percentage"
            )
            data.setdefault(field, data["discount_value"])
        return super().to_internal_value(data)

    def validate(self, attrs):
        instance = self.instance
        applicability = attrs.get(
            "applicability_type",
            getattr(instance, "applicability_type", WelcomeBonus.APPLICABILITY_PRODUCT),
        )
        category = attrs.get("category", getattr(instance, "category", None))
        products = attrs.get("products")
        if products is None and instance is not None:
            products = list(instance.products.all())
        products = list(products or [])

        if applicability == WelcomeBonus.APPLICABILITY_CATEGORY:
            if category is None:
                raise serializers.ValidationError(
                    {"category": "A category is required for a category-wise welcome bonus."}
                )
            if products:
                raise serializers.ValidationError(
                    {"products": "Category-wise welcome bonuses must not contain product targets."}
                )
        elif applicability == WelcomeBonus.APPLICABILITY_PRODUCT:
            if category is not None:
                raise serializers.ValidationError(
                    {"category": "Category must be empty for a product-wise welcome bonus."}
                )
            if not products:
                raise serializers.ValidationError(
                    {"products": "Select at least one product for a product-wise welcome bonus."}
                )
        else:
            raise serializers.ValidationError(
                {"applicability_type": "Select Product or Category."}
            )

        discount_type = attrs.get(
            "discount_type",
            getattr(instance, "discount_type", WelcomeBonus.DISCOUNT_PERCENTAGE),
        )
        percentage = attrs.get(
            "discount_percentage", getattr(instance, "discount_percentage", None)
        )
        fixed_amount = attrs.get("fixed_amount", getattr(instance, "fixed_amount", None))
        if discount_type == WelcomeBonus.DISCOUNT_PERCENTAGE:
            if percentage is None or percentage <= 0 or percentage > 100:
                raise serializers.ValidationError(
                    {"discount_percentage": "Percentage must be greater than 0 and at most 100."}
                )
            attrs["fixed_amount"] = None
        elif discount_type == WelcomeBonus.DISCOUNT_FIXED:
            if fixed_amount is None or fixed_amount <= 0:
                raise serializers.ValidationError(
                    {"fixed_amount": "Fixed amount must be greater than 0."}
                )
            attrs["discount_percentage"] = None
        else:
            raise serializers.ValidationError(
                {"discount_type": "Select Percentage or Fixed Amount."}
            )

        start_date = attrs.get("start_date", getattr(instance, "start_date", None))
        end_date = attrs.get("end_date", getattr(instance, "end_date", None))
        if start_date and end_date and start_date >= end_date:
            raise serializers.ValidationError(
                {"end_date": "Expiry date must be after the start date."}
            )
        return attrs

    def create(self, validated_data):
        products = validated_data.pop("products", [])
        instance = WelcomeBonus(**validated_data)
        instance.full_clean()
        instance.save()
        instance.products.set(products)
        return instance

    def update(self, instance, validated_data):
        products = validated_data.pop("products", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.full_clean()
        instance.save()
        if products is not None:
            instance.products.set(products)
        return instance

    def get_target_name(self, obj):
        if obj.applicability_type == WelcomeBonus.APPLICABILITY_CATEGORY:
            return obj.category.name if obj.category else None
        return list(obj.products.values_list("name", flat=True))

    def get_discount_value(self, obj):
        return obj.fixed_amount if obj.discount_type == WelcomeBonus.DISCOUNT_FIXED else obj.discount_percentage

    def _count(self, obj, annotation, status=None):
        if hasattr(obj, annotation):
            return getattr(obj, annotation)
        assignments = obj.assignments
        if not status:
            return assignments.count()
        if isinstance(status, (tuple, list, set)):
            return assignments.filter(status__in=status).count()
        return assignments.filter(status=status).count()

    def get_assigned_user_count(self, obj):
        return self._count(obj, "assigned_user_count")

    def get_claimed_user_count(self, obj):
        return self._count(
            obj,
            "claimed_user_count",
            (
                WelcomeBonusAssignment.STATUS_CLAIMED,
                WelcomeBonusAssignment.STATUS_REDEEMED,
            ),
        )

    def get_redeemed_user_count(self, obj):
        return self._count(obj, "redeemed_user_count", WelcomeBonusAssignment.STATUS_REDEEMED)


class WelcomeBonusNotificationSerializer(serializers.ModelSerializer):
    """Customer notification payload; the redemption code is never serialized."""

    assignment_id = serializers.IntegerField(source="assignment.id", read_only=True)
    title = serializers.SerializerMethodField()
    message = serializers.SerializerMethodField()
    discount_text = serializers.SerializerMethodField()
    eligible_target = serializers.SerializerMethodField()
    masked_code = serializers.SerializerMethodField()
    assignment_status = serializers.SerializerMethodField()
    can_claim = serializers.SerializerMethodField()
    can_copy_code = serializers.SerializerMethodField()
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = WelcomeBonusNotification
        fields = (
            "id",
            "assignment_id",
            "title",
            "message",
            "discount_text",
            "eligible_target",
            "masked_code",
            "assignment_status",
            "can_claim",
            "can_copy_code",
            "is_read",
            "created_at",
        )
        read_only_fields = fields

    def get_title(self, obj):
        return obj.assignment.welcome_bonus.name

    def get_message(self, obj):
        return "You have a Welcome Bonus available. Claim it now and use it on eligible products."

    def get_discount_text(self, obj):
        welcome_bonus = obj.assignment.welcome_bonus
        if welcome_bonus.discount_type == WelcomeBonus.DISCOUNT_FIXED:
            return f"Get {welcome_bonus.fixed_amount} OFF on eligible products."
        return f"Get {welcome_bonus.discount_percentage}% OFF on eligible products."

    def get_eligible_target(self, obj):
        """A display-safe product/category target for the notification UI."""
        welcome_bonus = obj.assignment.welcome_bonus
        if welcome_bonus.applicability_type == WelcomeBonus.APPLICABILITY_CATEGORY:
            category_name = welcome_bonus.category.name if welcome_bonus.category else "selected category"
            return f"Valid for category: {category_name}"

        product_names = list(welcome_bonus.products.values_list("name", flat=True))
        if len(product_names) == 1:
            return f"Valid for: {product_names[0]}"
        if product_names:
            return f"Valid for: {', '.join(product_names)}"
        return "Valid for selected products."

    def get_masked_code(self, obj):
        return "••••••••••••••••"

    def _validation_error(self, obj, *, require_claimed=False):
        return welcome_bonus_validation_error(
            obj.assignment,
            obj.assignment.user,
            require_claimed=require_claimed,
        )

    def get_assignment_status(self, obj):
        assignment = obj.assignment
        if assignment.status == WelcomeBonusAssignment.STATUS_REDEEMED:
            return WelcomeBonusAssignment.STATUS_REDEEMED
        error = self._validation_error(obj)
        if not error:
            return assignment.status
        return {
            "WELCOME_BONUS_INACTIVE": "INACTIVE",
            "WELCOME_BONUS_EXPIRED": "EXPIRED",
        }.get(error[0], assignment.status)

    def get_can_claim(self, obj):
        return bool(
            obj.assignment.status == WelcomeBonusAssignment.STATUS_AVAILABLE
            and not self._validation_error(obj)
        )

    def get_can_copy_code(self, obj):
        return bool(
            obj.assignment.status == WelcomeBonusAssignment.STATUS_CLAIMED
            and not self._validation_error(obj, require_claimed=True)
        )

    def get_is_read(self, obj):
        return obj.read_at is not None

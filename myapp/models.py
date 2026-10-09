from django.db import models, transaction
from django.contrib.auth.models import ( AbstractUser, BaseUserManager)
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils.text import slugify


class UserManager(BaseUserManager):

    def create_user(self, email, password=None, **extra_fields):

        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)

        user = self.model( email=email, **extra_fields )

        user.set_password(password)

        user.save(using=self._db)

        return user

    def create_superuser(self, email, password=None, **extra_fields):

        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", "Super Admin")

        return self.create_user(
            email,
            password,
            **extra_fields
        )

class User(AbstractUser):

    ROLE_CHOICES = (
        ("Customer", "Customer"),
        ("Super Admin", "Super Admin"),
    )

    username = None
    email = models.EmailField( unique=True )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="Customer")

    USERNAME_FIELD = "email"

    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email


class Category(models.Model):

    name = models.CharField(max_length=100,unique=True)
    image = models.ImageField( upload_to="categories/")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class SubCategory(models.Model):

    category = models.ForeignKey( Category, on_delete=models.CASCADE,related_name="subcategories")
    name = models.CharField( max_length=100)
    image = models.ImageField( upload_to="subcategories/", blank=True, null=True )
    is_active = models.BooleanField( default=True )
    created_at = models.DateTimeField( auto_now_add=True )

    def __str__(self):
        return self.name


class Brand(models.Model):
    """A catalog brand that can be assigned to one or more products."""

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    logo = models.ImageField(upload_to="brands/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "brand"
            candidate = base_slug
            suffix = 2
            while Brand.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base_slug}-{suffix}"
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Offer(models.Model):

    title = models.CharField(max_length=200 )
    description = models.TextField()
    image = models.ImageField( upload_to="offers/")
    discount_percentage = models.PositiveIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField( default=True)
    created_at = models.DateTimeField( auto_now_add=True)

    def __str__(self):
        return self.title
    
class Color(models.Model):

    name = models.CharField(max_length=50,unique=True)
    code = models.CharField(max_length=7)

    def __str__(self):
        return self.name
    
class UnitType(models.Model):

    name = models.CharField(max_length=50, unique=True, help_text="e.g. Weight (kg), Clothing Unit (S/M/L), Memory (GB)")

    def __str__(self):
        return self.name

class Unit(models.Model):

    unit_type = models.ForeignKey(UnitType, on_delete=models.CASCADE, null=True, blank=True, related_name="units")
    name = models.CharField(max_length=20)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("unit_type", "name"),
                name="myapp_unit_type_name_unique",
            )
        ]

    def clean(self):
        super().clean()
        # Existing untyped units remain readable for backward compatibility,
        # but every newly-created catalog unit must belong to a type.
        if self._state.adding and not self.unit_type_id:
            raise ValidationError({"unit_type": "A unit type is required."})

    def __str__(self):
        if self.unit_type:
            return f"{self.name} ({self.unit_type.name})"
        return self.name

class Region(models.Model):

    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

class Product(models.Model):

    RELATED_PRODUCT_MODE_NONE = "none"
    RELATED_PRODUCT_MODE_MANUAL = "manual"
    RELATED_PRODUCT_MODE_AUTOMATIC = "automatic"
    RELATED_PRODUCT_MODE_CHOICES = (
        (RELATED_PRODUCT_MODE_NONE, "None"),
        (RELATED_PRODUCT_MODE_MANUAL, "Manual"),
        (RELATED_PRODUCT_MODE_AUTOMATIC, "Automatic"),
    )

    category = models.ForeignKey(Category,on_delete=models.CASCADE)
    subcategory = models.ForeignKey( SubCategory,on_delete=models.CASCADE)
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    offer = models.ForeignKey( Offer, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField( max_length=200 )
    description = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField( auto_now_add=True )
    updated_at = models.DateTimeField( auto_now=True )
    key_features = models.TextField(blank=True, help_text="Enter key features separated by newlines")
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    estimated_delivery_time = models.CharField(max_length=100, blank=True, null=True)
    seller_name = models.CharField(max_length=200, blank=True, null=True)
    warranty_info = models.CharField(max_length=200, blank=True, null=True)
    # Kept in the schema for backwards-compatible migrations, but EMI is
    # permanently disabled and is no longer exposed through the API/admin.
    emi_available = models.BooleanField(default=False, editable=False)
    emi_starting_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, editable=False)
    current_viewers_count = models.PositiveIntegerField(default=0)
    promotional_banner_image = models.ImageField(upload_to="promotional_banners/", blank=True, null=True)
    promotional_banner_link = models.URLField(max_length=500, blank=True, null=True)
    related_product_mode = models.CharField(
        max_length=12,
        choices=RELATED_PRODUCT_MODE_CHOICES,
        default=RELATED_PRODUCT_MODE_NONE,
        help_text="Choose whether related products are hidden, curated manually, or selected automatically.",
    )
    # The explicit through model keeps the merchant's manual ordering and
    # makes the maximum of four a database-backed invariant.
    related_products = models.ManyToManyField(
        "self",
        through="ProductRelatedProduct",
        symmetrical=False,
        related_name="related_to_products",
        blank=True,
    )

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.category_id and self.subcategory_id:
            if self.subcategory.category_id != self.category_id:
                raise ValidationError(
                    {"subcategory": "The subcategory must belong to the selected category."}
                )

        from .catalog_pricing import get_product_minimum_price

        # EMI is disabled globally. Normalize legacy/imported values so no
        # product can accidentally re-enable it.
        self.emi_available = False
        self.emi_starting_price = None


class ProductRelatedProduct(models.Model):
    """An ordered, directed related-product choice made by a merchant."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="related_product_links",
    )
    related_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="related_from_links",
    )
    position = models.PositiveSmallIntegerField(
        validators=(MinValueValidator(0), MaxValueValidator(3)),
        help_text="Display order, from 0 to 3.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("position", "id")
        constraints = (
            models.UniqueConstraint(
                fields=("product", "related_product"),
                name="myapp_related_product_unique_target",
            ),
            models.UniqueConstraint(
                fields=("product", "position"),
                name="myapp_related_product_unique_position",
            ),
            models.CheckConstraint(
                condition=models.Q(position__gte=0, position__lte=3),
                name="myapp_related_product_position_range",
            ),
            models.CheckConstraint(
                condition=~models.Q(product=models.F("related_product")),
                name="myapp_related_product_not_self",
            ),
        )

    def clean(self):
        super().clean()
        if self.product_id and self.related_product_id == self.product_id:
            raise ValidationError(
                {"related_product": "A product cannot be related to itself."}
            )

    def __str__(self):
        return f"{self.product} -> {self.related_product} ({self.position + 1})"

class ProductView(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="unique_views")
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    ip_address = models.CharField(max_length=45, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['product', 'user']),
            models.Index(fields=['product', 'ip_address']),
        ]


class ProductVariant(models.Model):
    PRICE_TYPE_CHOICES = (
        ("single", "Single Price"),
        ("multiple", "Multiple Price"),
    )
    product = models.ForeignKey( Product, on_delete=models.CASCADE, related_name="variants" )
    color = models.ForeignKey(Color,on_delete=models.CASCADE, null=True, blank=True )
    regions = models.ManyToManyField(Region, blank=True)
    sku = models.CharField(max_length=100, unique=True, null=True, blank=True)
    
    price_type = models.CharField(max_length=20, choices=PRICE_TYPE_CHOICES, default="single")
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="For single price")
    stock = models.PositiveIntegerField(default=0, help_text="For single price")

    class Meta:
        unique_together = (
            "product",
            "color"
        )

    def clean(self):
        super().clean()
        if self.product_id and self.color_id is None:
            duplicate = ProductVariant.objects.filter(
                product_id=self.product_id,
                color__isnull=True,
            ).exclude(pk=self.pk).exists()
            if duplicate:
                raise ValidationError(
                    {"color": "A product can have only one no-color variant."}
                )
        if self.price_type == "single" and self.price is None:
            raise ValidationError({"price": "A single-price variant requires a price."})
        if self.price_type == "multiple" and self.price is not None:
            raise ValidationError(
                {"price": "A multiple-price variant must store prices on its units."}
            )

    def __str__(self):
        parts = [self.product.name]
        if self.color:
            parts.append(self.color.name)
        if self.pk:
            try:
                region_names = [r.name for r in self.regions.all()]
                if region_names:
                    parts.append(", ".join(region_names))
            except ValueError:
                pass
        return " - ".join(parts)

class ProductVariantUnit(models.Model):

    variant = models.ForeignKey(ProductVariant,on_delete=models.CASCADE, related_name="sizes" )
    unit_type = models.ForeignKey(UnitType, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Unit (e.g. GB/KG)")
    unit = models.ForeignKey( Unit,  on_delete=models.CASCADE, null=True, blank=True, verbose_name="Quantity (e.g. 128, 1)")
    sku = models.CharField(max_length=100, unique=True, null=True, blank=True)
    price = models.DecimalField( max_digits=10,decimal_places=2)
    stock = models.PositiveIntegerField( default=0)

    class Meta:
        unique_together = (
            "variant",
            "unit"
        )

    def clean(self):
        super().clean()
        if not self.unit_id:
            raise ValidationError({"unit": "A variant unit requires a unit value."})
        if not self.unit_type_id:
            raise ValidationError({"unit_type": "A variant unit requires a unit type."})
        if not self.unit.unit_type_id:
            raise ValidationError(
                {"unit": "The selected unit is not assigned to a unit type."}
            )
        if self.unit.unit_type_id != self.unit_type_id:
            raise ValidationError(
                {"unit_type": "The selected unit does not belong to this unit type."}
            )

    def __str__(self):
        if self.unit:
            return (
                f"{self.variant} - "
                f"{self.unit.name}"
            )

        return str(self.variant)
    
class ProductImage(models.Model):

    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField( upload_to="products/")
    is_primary = models.BooleanField( default=False)
    position = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ("position", "id")

    def clean(self):
        super().clean()
        if not self.variant_id:
            raise ValidationError({"variant": "A product image must belong to a variant."})

    def save(self, *args, **kwargs):
        self.full_clean()
        requested_update_fields = kwargs.get("update_fields")
        original_primary = self.is_primary
        with transaction.atomic():
            if self.variant_id:
                # Lock the owning variant so two concurrent uploads cannot
                # both decide that they are the first/primary image.
                ProductVariant.objects.select_for_update().get(pk=self.variant_id)
                sibling_images = ProductImage.objects.select_for_update().filter(
                    variant_id=self.variant_id
                ).exclude(pk=self.pk)
                if self.is_primary:
                    sibling_images.filter(is_primary=True).update(is_primary=False)
                elif not sibling_images.filter(is_primary=True).exists():
                    self.is_primary = True
            if (
                requested_update_fields is not None
                and self.is_primary != original_primary
            ):
                kwargs["update_fields"] = set(requested_update_fields) | {"is_primary"}
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            replacement = None
            if self.variant_id and self.is_primary:
                ProductVariant.objects.select_for_update().get(pk=self.variant_id)
                replacement = (
                    ProductImage.objects.select_for_update()
                    .filter(variant_id=self.variant_id)
                    .exclude(pk=self.pk)
                    .order_by("position", "id")
                    .first()
                )
            result = super().delete(*args, **kwargs)
            if replacement:
                replacement.is_primary = True
                replacement.save(update_fields=("is_primary",))
            return result

    def __str__(self):
        product_name = self.variant.product.name if self.variant_id else "Unassigned product"
        return f"{product_name} - {self.image.name or 'image'}"

class Wishlist(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    variant = models.ForeignKey(
    ProductVariant,
    on_delete=models.CASCADE,
    related_name="wishlist",
    null=True,
    blank=True
    )

    variant_unit = models.ForeignKey(
    ProductVariantUnit,
    on_delete=models.CASCADE,
    related_name="wishlist",
    null=True,
    blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        unique_together = (
            "user",
            "variant",
            "variant_unit"
        )

    def __str__(self):
        product_name = (
            self.variant.product.name
            if self.variant and self.variant.product
            else "Unknown product"
        )
        color = (
            self.variant.color.name
            if self.variant and self.variant.color
            else "No color"
        )
        unit = (
            self.variant_unit.unit.name
            if self.variant_unit and self.variant_unit.unit
            else "No unit"
        )
        return f"{self.user.email} - {product_name} - {color} - {unit}"
        
class Cart(models.Model):

    user = models.ForeignKey( User, on_delete=models.CASCADE )
    variant = models.ForeignKey( ProductVariant, on_delete=models.CASCADE )
    variant_unit = models.ForeignKey( ProductVariantUnit,on_delete=models.CASCADE, null=True, blank=True)
    quantity = models.PositiveIntegerField( default=1)
    coupon = models.ForeignKey('Coupon', on_delete=models.SET_NULL, null=True, blank=True)
    welcome_bonus_assignment = models.ForeignKey(
        "WelcomeBonusAssignment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cart_items",
    )
    created_at = models.DateTimeField( auto_now_add=True )

    class Meta:
        unique_together = (
            "user",
            "variant",
            "variant_unit"
        )
        constraints = (
            models.CheckConstraint(
                condition=(
                    models.Q(coupon__isnull=True)
                    | models.Q(welcome_bonus_assignment__isnull=True)
                ),
                name="myapp_cart_one_promotion_source",
            ),
        )

    def __str__(self):
        product_name = (
            self.variant.product.name
            if self.variant and self.variant.product
            else "Unknown product"
        )
        color_name = (
            self.variant.color.name
            if self.variant and self.variant.color
            else "No color"
        )
        unit_name = (
            self.variant_unit.unit.name
            if self.variant_unit and self.variant_unit.unit
            else "No unit"
        )
        return f"{self.user.email} - {product_name} - {color_name} - {unit_name}"

class Address(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="addresses"
        ,null=True
    )

    full_name = models.CharField(max_length=100, blank=True,null=True)
    phone = models.CharField(max_length=15, blank=True,null=True)
    address_line = models.TextField(blank=True,null=True)
    city = models.CharField(max_length=100, blank=True,null=True)
    postal_code = models.CharField(max_length=20, blank=True,null=True)
    country = models.CharField(max_length=100, default="New Zealand")
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True,null=True)

    def __str__(self):
        return f"{self.full_name} - {self.city}"
    
class UserProfile(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE
        , related_name="profile"
        ,null=True
    )

    phone = models.CharField(max_length=15, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)

class Order(models.Model):

    STATUS_CHOICES = (
        ("Pending", "Pending"),
        ("Processing", "Processing"),
        ("Shipped", "Shipped"),
        ("Delivered", "Delivered"),
        ("Cancelled", "Cancelled"),
    )

    PAYMENT_STATUS_CHOICES = (
        ("Pending", "Pending"),
        ("Paid", "Paid"),
        ("Failed", "Failed"),
        ("Refunded", "Refunded"),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    address = models.ForeignKey(
        Address,
        on_delete=models.SET_NULL,
        null=True
    )

    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    shipping_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="Pending"
    )

    stripe_session_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="Pending"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(auto_now=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_orders",
    )

    def __str__(self):
        return f"ORD-{self.id:06d}"


class AdminAuditLog(models.Model):
    admin_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50)
    entity_type = models.CharField(max_length=50)
    entity_id = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

class OrderItem(models.Model):

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )

    color = models.ForeignKey(
        Color,
        on_delete=models.SET_NULL,
        null=True
    )
    

    unit = models.ForeignKey(
        Unit,
        on_delete=models.SET_NULL,
        null=True
    )

    quantity = models.PositiveIntegerField()

    original_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    
    variant_unit = models.ForeignKey(
        ProductVariantUnit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    ) 


    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    def __str__(self):
        return self.product.name
    
class HeroBanner(models.Model):

    subtitle = models.CharField(max_length=100)

    title = models.CharField(max_length=200)

    description = models.TextField()

    image = models.ImageField(upload_to="hero_banners/")

    button_text = models.CharField(
        max_length=50,
        default="Explore Collection"
    )

    display_order = models.PositiveIntegerField(default=1)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order"]

    def __str__(self):
        return self.title


class TrustBenefit(models.Model):
    ICON_KEY_CHOICES = (
        ("secure-payment", "Secure payment"),
        ("delivery-information", "Delivery information"),
        ("customer-support", "Customer support"),
        ("easy-returns", "Easy returns"),
    )

    key = models.SlugField(max_length=100, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    icon_key = models.CharField(max_length=32, choices=ICON_KEY_CHOICES)
    display_order = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("display_order", "id")

    def __str__(self):
        return self.title

class PromoBanner(models.Model):

    image = models.ImageField(upload_to="promo_banners/", help_text='The promotional banner image', null=True, blank=True)
    link = models.URLField(max_length=500, blank=True, null=True, help_text='A URL where the user should be redirected if they click the banner')
    is_active = models.BooleanField(default=True, help_text='To easily turn individual banners on or off')

    def __str__(self):
        return f"Promo Banner {self.id}"

class HeroSideBanner(models.Model):

    image = models.ImageField(upload_to="hero_side_banners/", help_text='The actual image file')
    link = models.URLField(max_length=500, blank=True, null=True, help_text='A URL where the user should be redirected if they click the banner')
    is_active = models.BooleanField(default=True, help_text='Only one banner should be active at a time')

    def __str__(self):
        return f"Hero Side Banner {self.id}"

class Coupon(models.Model):

    APPLICABILITY_PRODUCT = "PRODUCT"
    APPLICABILITY_CATEGORY = "CATEGORY"
    APPLICABILITY_CHOICES = (
        (APPLICABILITY_PRODUCT, "Product"),
        (APPLICABILITY_CATEGORY, "Category"),
    )

    DISCOUNT_PERCENTAGE = "PERCENTAGE"
    DISCOUNT_FIXED = "FIXED"
    DISCOUNT_TYPE_CHOICES = (
        (DISCOUNT_PERCENTAGE, "Percentage"),
        (DISCOUNT_FIXED, "Fixed Amount"),
    )

    code = models.CharField(max_length=50, unique=True, blank=True, help_text="Leave blank to auto-generate")
    products = models.ManyToManyField(Product, blank=True, related_name="coupons", help_text="Select specific products. Leave blank to apply to ALL products.")
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="coupons",
    )
    applicability_type = models.CharField(
        max_length=20,
        choices=APPLICABILITY_CHOICES,
        default=APPLICABILITY_PRODUCT,
    )
    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES,
        default=DISCOUNT_PERCENTAGE,
    )
    # Kept for backwards compatibility with the original percentage-only API.
    # It is null for fixed-amount coupons.
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    fixed_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code

    def clean(self):
        super().clean()
        errors = {}

        if self.start_date and self.end_date and self.start_date >= self.end_date:
            errors["end_date"] = "Expiry date must be after the start date."

        if self.applicability_type not in dict(self.APPLICABILITY_CHOICES):
            errors["applicability_type"] = "Select Product or Category."
        elif self.applicability_type == self.APPLICABILITY_CATEGORY and not self.category_id:
            errors["category"] = "A category is required for a category-wise coupon."
        elif self.applicability_type == self.APPLICABILITY_PRODUCT and self.category_id:
            errors["category"] = "Category must be empty for a product-wise coupon."

        if self.discount_type not in dict(self.DISCOUNT_TYPE_CHOICES):
            errors["discount_type"] = "Select Percentage or Fixed Amount."
        elif self.discount_type == self.DISCOUNT_PERCENTAGE:
            if self.discount_percentage is None:
                errors["discount_percentage"] = "A percentage discount is required."
            elif self.discount_percentage <= 0 or self.discount_percentage > 100:
                errors["discount_percentage"] = "Percentage must be greater than 0 and at most 100."
            if self.fixed_amount is not None:
                errors["fixed_amount"] = "Fixed amount must be empty for a percentage coupon."
        elif self.discount_type == self.DISCOUNT_FIXED:
            if self.fixed_amount is None or self.fixed_amount <= 0:
                errors["fixed_amount"] = "Fixed amount must be greater than 0."
            if self.discount_percentage is not None:
                errors["discount_percentage"] = "Percentage must be empty for a fixed-amount coupon."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.code:
            import string, random
            while True:
                code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                if (
                    not Coupon.objects.filter(code=code).exists()
                    and not WelcomeBonusAssignment.objects.filter(code=code).exists()
                ):
                    self.code = code
                    break
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        from django.utils import timezone
        now = timezone.now()
        return self.is_active and self.start_date <= now <= self.end_date

class CouponUsage(models.Model):

    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="usages")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="used_coupons")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="coupon_usages", null=True)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('coupon', 'user', 'product')

    def __str__(self):
        return f"{self.user.email} - {self.coupon.code} on {self.product}"


class CouponApplication(models.Model):
    """Reserve a coupon as soon as a user applies it to a product."""

    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="coupon_applications",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="coupon_applications",
    )
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("coupon", "user", "product")
        indexes = [
            models.Index(fields=("user", "product")),
        ]

    def __str__(self):
        return f"{self.user.email} applied {self.coupon.code} to {self.product}"


class SavedCoupon(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_coupons")
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')

    def __str__(self):
        return f"{self.user.email} saved {self.coupon.code} for {self.product.name}"


class WelcomeBonus(models.Model):
    """An admin-managed welcome-bonus campaign.

    A campaign deliberately does not have a public redemption code. Codes
    live on ``WelcomeBonusAssignment``, one per customer, so a code can never
    be shared between customers.
    """

    APPLICABILITY_PRODUCT = "PRODUCT"
    APPLICABILITY_CATEGORY = "CATEGORY"
    APPLICABILITY_CHOICES = (
        (APPLICABILITY_PRODUCT, "Product"),
        (APPLICABILITY_CATEGORY, "Category"),
    )
    DISCOUNT_PERCENTAGE = "PERCENTAGE"
    DISCOUNT_FIXED = "FIXED"
    DISCOUNT_TYPE_CHOICES = (
        (DISCOUNT_PERCENTAGE, "Percentage"),
        (DISCOUNT_FIXED, "Fixed Amount"),
    )

    name = models.CharField(max_length=200)
    products = models.ManyToManyField(
        Product,
        blank=True,
        related_name="welcome_bonuses",
        help_text="Select the eligible products for a product-wise campaign.",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="welcome_bonuses",
    )
    applicability_type = models.CharField(
        max_length=20,
        choices=APPLICABILITY_CHOICES,
        default=APPLICABILITY_PRODUCT,
    )
    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES,
        default=DISCOUNT_PERCENTAGE,
    )
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    fixed_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    # Deletion is archival. It preserves redemptions and historical orders.
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = (
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F("start_date")),
                name="myapp_welcome_bonus_valid_dates",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        discount_type="PERCENTAGE",
                        discount_percentage__gt=0,
                        discount_percentage__lte=100,
                        fixed_amount__isnull=True,
                    )
                    | models.Q(
                        discount_type="FIXED",
                        fixed_amount__gt=0,
                        discount_percentage__isnull=True,
                    )
                ),
                name="myapp_welcome_bonus_valid_discount",
            ),
        )

    def clean(self):
        super().clean()
        errors = {}
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            errors["end_date"] = "Expiry date must be after the start date."
        if self.applicability_type == self.APPLICABILITY_CATEGORY and not self.category_id:
            errors["category"] = "A category is required for a category-wise welcome bonus."
        if self.applicability_type == self.APPLICABILITY_PRODUCT and self.category_id:
            errors["category"] = "Category must be empty for a product-wise welcome bonus."
        if self.discount_type == self.DISCOUNT_PERCENTAGE:
            if self.discount_percentage is None or not (0 < self.discount_percentage <= 100):
                errors["discount_percentage"] = "Percentage must be greater than 0 and at most 100."
            if self.fixed_amount is not None:
                errors["fixed_amount"] = "Fixed amount must be empty for a percentage discount."
        elif self.discount_type == self.DISCOUNT_FIXED:
            if self.fixed_amount is None or self.fixed_amount <= 0:
                errors["fixed_amount"] = "Fixed amount must be greater than 0."
            if self.discount_percentage is not None:
                errors["discount_percentage"] = "Percentage must be empty for a fixed amount discount."
        else:
            errors["discount_type"] = "Select Percentage or Fixed Amount."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name

    @property
    def is_currently_redeemable(self):
        from django.utils import timezone

        now = timezone.now()
        return bool(
            self.is_active
            and self.archived_at is None
            and self.start_date <= now <= self.end_date
        )


class WelcomeBonusAssignment(models.Model):
    """The private, user-specific entitlement for a welcome-bonus campaign."""

    STATUS_AVAILABLE = "AVAILABLE"
    STATUS_CLAIMED = "CLAIMED"
    STATUS_REDEEMED = "REDEEMED"
    STATUS_CHOICES = (
        (STATUS_AVAILABLE, "Available"),
        (STATUS_CLAIMED, "Claimed"),
        (STATUS_REDEEMED, "Redeemed"),
    )

    welcome_bonus = models.ForeignKey(
        WelcomeBonus,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="welcome_bonus_assignments",
    )
    # Intentionally omitted from notification and admin serializers.
    code = models.CharField(max_length=64, unique=True, editable=False)
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default=STATUS_AVAILABLE,
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("welcome_bonus", "user"),
                name="myapp_welcome_bonus_one_assignment_per_user",
            ),
        )
        indexes = (
            models.Index(fields=("user", "status")),
        )

    def __str__(self):
        return f"{self.welcome_bonus_id} assigned to {self.user_id}"


class WelcomeBonusNotification(models.Model):
    """A backend-owned notification for a welcome-bonus assignment."""

    assignment = models.OneToOneField(
        WelcomeBonusAssignment,
        on_delete=models.CASCADE,
        related_name="notification",
    )
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")


class WelcomeBonusApplication(models.Model):
    """Records a product application without consuming the bonus yet."""

    assignment = models.ForeignKey(
        WelcomeBonusAssignment,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="welcome_bonus_applications",
    )
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("assignment", "product"),
                name="myapp_welcome_bonus_one_application_per_product",
            ),
        )


class SavedWelcomeBonus(models.Model):
    """The cart-safe equivalent of SavedCoupon for a private bonus code."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="saved_welcome_bonuses",
    )
    assignment = models.ForeignKey(
        WelcomeBonusAssignment,
        on_delete=models.CASCADE,
        related_name="saved_products",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="saved_welcome_bonuses",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("user", "product"),
                name="myapp_saved_welcome_bonus_per_product",
            ),
        )


class WelcomeBonusRedemption(models.Model):
    """Immutable promotion snapshot attached to the order history."""

    PROMOTION_TYPE = "WELCOME_BONUS"

    assignment = models.OneToOneField(
        WelcomeBonusAssignment,
        on_delete=models.PROTECT,
        related_name="redemption",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="welcome_bonus_redemptions",
    )
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="welcome_bonus_redemptions")
    welcome_bonus = models.ForeignKey(WelcomeBonus, on_delete=models.PROTECT, related_name="redemptions")
    promotion_type = models.CharField(max_length=32, default=PROMOTION_TYPE, editable=False)
    redemption_code = models.CharField(max_length=64, editable=False)
    discount_type = models.CharField(max_length=20)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    applied_amount = models.DecimalField(max_digits=10, decimal_places=2)
    redeemed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = (
            models.Index(fields=("order", "promotion_type")),
        )

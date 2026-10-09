from django.urls import path
from .import views
from .views import ThrottledTokenRefreshView

urlpatterns = [
    path("health/", views.health_check),
    path("auth/csrf/", views.csrf_token, name="auth_csrf"),
    path("auth/session/", views.auth_session, name="auth_session"),
    path("register/",views.register),
    path("token/refresh/", ThrottledTokenRefreshView.as_view(), name="token_refresh"),
    path("google-login/", views.google_login),
    path("login/",views.login),
    path("logout/", views.logout),
    path("forgot-password/",views.forgot_password),
    path("reset-password/<uidb64>/<token>/",views.reset_password),
    
    # path("categories/",views.get_categories), 
    path("category-products/<int:category_id>/", views.category_products ),
    path("products/",views.get_products),
    path("related-products/<int:pk>/",views.related_products),
    path("new-arrivals/",views.new_arrivals),
    path("homepage/", views.homepage, name="homepage"),
    path("brands/", views.homepage_brands, name="brands"),
    path("recently-viewed/", views.recently_viewed, name="recently-viewed"),
    
    path("subcategories/",views.get_subcategories),
    path("products/",views.get_products),
    path("product/<int:pk>/",views.product_details),
    path("wishlist/add/",views.add_to_wishlist),
    path("wishlist/",views.get_wishlist),
    path("wishlist/remove/<int:id>/",views.remove_wishlist),
    path("cart/add/", views.add_to_cart),
    path("cart/",views.get_cart),
    path("cart/update/<int:id>/", views.update_cart_quantity),
    path("cart/remove/<int:id>/", views.remove_cart_item),
    path("offer-status/", views.offer_status),
    path("offers/",views.get_offers),
    path( "offer-products/",views.offer_products),
    path("search-products/", views.search_products),
    path("place-order/", views.place_order),
    path("my-orders/",views.my_orders),
    path("cancel-order/<int:id>/",views.cancel_order),
    path( "order-details/<int:id>/",views.order_details),
    path(
    "admin-dashboard-cards/", views. admin_dashboard_cards
),

path(
    "admin-orders/",views.admin_orders
),
path(
    "admin-order-details/<int:id>/",
   views.admin_order_details
),

path(
    "update-order-status/<int:id>/",
    views.update_order_status
),
path(
    "low-stock-products/",
    views.low_stock_products
),
path(
    "export-orders-csv/",
    views.export_orders_csv
),
 path("profile/", views.profile),

    path("addresses/", views.address_list),

    path("addresses/<int:pk>/", views.address_detail),
    
    
    path(
        "home/categories/",views.home_categories,name="home-categories"
    ),
path(
    "wishlist-products/",
    views.wishlist_products
),
path(
        "hero-banners/",
        views.get_hero_banners
    ),
    path(
        "api/promo-banners/",
        views.get_promo_banners,
        name="promo-banners"
    ),
    path(
        "api/hero-side-banner/",
        views.get_hero_side_banner,
        name="hero-side-banner"
    ),
    path(
        "validate-coupon/", 
        views.validate_coupon, 
        name="validate-coupon"
    ),
    path(
        "welcome-bonus-notifications/",
        views.welcome_bonus_notifications,
        name="welcome-bonus-notifications",
    ),
    path(
        "welcome-bonus-notifications/<int:notification_id>/claim/",
        views.claim_welcome_bonus,
        name="claim-welcome-bonus",
    ),
    path(
        "welcome-bonus-notifications/<int:notification_id>/read/",
        views.mark_welcome_bonus_notification_read,
        name="read-welcome-bonus-notification",
    ),
    path(
        "welcome-bonus-notifications/<int:notification_id>/copy-code/",
        views.copy_welcome_bonus_code,
        name="copy-welcome-bonus-code",
    ),
]

from rest_framework.routers import DefaultRouter
from .order_admin_api import SuperAdminOrderDetailView, SuperAdminOrderListView
from .super_admin_api import (
    AdminAddressViewSet,
    AdminBrandViewSet,
    AdminCartViewSet,
    AdminCategoryViewSet,
    AdminColorViewSet,
    AdminCouponUsageViewSet,
    AdminCouponViewSet,
    AdminHeroBannerViewSet,
    AdminHeroSideBannerViewSet,
    AdminOfferViewSet,
    AdminOrderItemViewSet,
    AdminOrderViewSet,
    AdminProductImageViewSet,
    AdminProductVariantUnitViewSet,
    AdminProductVariantViewSet,
    AdminProductViewSet,
    AdminPromoBannerViewSet,
    AdminRegionViewSet,
    AdminSubCategoryViewSet,
    AdminTrustBenefitViewSet,
    AdminUnitTypeViewSet,
    AdminUnitViewSet,
    AdminUserProfileViewSet,
    AdminUserViewSet,
    AdminWishlistViewSet,
    SuperAdminOverviewView,
    SuperAdminSchemaView,
)
router = DefaultRouter()
router.register(r'admin-coupons', views.CouponViewSet, basename='admin-coupon')
router.register(r'admin-welcome-bonuses', views.WelcomeBonusViewSet, basename='admin-welcome-bonus')
router.register(r'admin/manage/users', AdminUserViewSet, basename='admin-manage-user')
router.register(r'admin/manage/brands', AdminBrandViewSet, basename='admin-manage-brand')
router.register(r'admin/manage/categories', AdminCategoryViewSet, basename='admin-manage-category')
router.register(r'admin/manage/subcategories', AdminSubCategoryViewSet, basename='admin-manage-subcategory')
router.register(r'admin/manage/offers', AdminOfferViewSet, basename='admin-manage-offer')
router.register(r'admin/manage/colors', AdminColorViewSet, basename='admin-manage-color')
router.register(r'admin/manage/unit-types', AdminUnitTypeViewSet, basename='admin-manage-unit-type')
router.register(r'admin/manage/units', AdminUnitViewSet, basename='admin-manage-unit')
router.register(r'admin/manage/regions', AdminRegionViewSet, basename='admin-manage-region')
router.register(r'admin/manage/products', AdminProductViewSet, basename='admin-manage-product')
router.register(r'admin/manage/product-variants', AdminProductVariantViewSet, basename='admin-manage-product-variant')
router.register(r'admin/manage/product-variant-units', AdminProductVariantUnitViewSet, basename='admin-manage-product-variant-unit')
router.register(r'admin/manage/product-images', AdminProductImageViewSet, basename='admin-manage-product-image')
router.register(r'admin/manage/wishlists', AdminWishlistViewSet, basename='admin-manage-wishlist')
router.register(r'admin/manage/carts', AdminCartViewSet, basename='admin-manage-cart')
router.register(r'admin/manage/addresses', AdminAddressViewSet, basename='admin-manage-address')
router.register(r'admin/manage/user-profiles', AdminUserProfileViewSet, basename='admin-manage-user-profile')
router.register(r'admin/manage/orders', AdminOrderViewSet, basename='admin-manage-order')
router.register(r'admin/manage/order-items', AdminOrderItemViewSet, basename='admin-manage-order-item')
router.register(r'admin/manage/hero-banners', AdminHeroBannerViewSet, basename='admin-manage-hero-banner')
router.register(r'admin/manage/trust-benefits', AdminTrustBenefitViewSet, basename='admin-manage-trust-benefit')
router.register(r'admin/manage/promo-banners', AdminPromoBannerViewSet, basename='admin-manage-promo-banner')
router.register(r'admin/manage/hero-side-banners', AdminHeroSideBannerViewSet, basename='admin-manage-hero-side-banner')
router.register(r'admin/manage/coupons', AdminCouponViewSet, basename='admin-manage-coupon')
router.register(r'admin/manage/welcome-bonuses', views.WelcomeBonusViewSet, basename='admin-manage-welcome-bonus')
router.register(r'admin/manage/coupon-usages', AdminCouponUsageViewSet, basename='admin-manage-coupon-usage')

urlpatterns += router.urls

urlpatterns += [
    path("admin/manage/schema/", SuperAdminSchemaView.as_view(), name="super-admin-schema"),
    path("admin/manage/overview/", SuperAdminOverviewView.as_view(), name="super-admin-overview"),
]

# Strictly protected order-management API for the Support Order Dashboard.
urlpatterns += [
    path("orders/", SuperAdminOrderListView.as_view(), name="admin-orders-api"),
    path(
        "orders/<int:id>/",
        SuperAdminOrderDetailView.as_view(),
        name="admin-order-detail-api",
    ),
]

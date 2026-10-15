from django.contrib import admin

from .models import CashfreeCheckout


@admin.register(CashfreeCheckout)
class CashfreeCheckoutAdmin(admin.ModelAdmin):
    list_display = (
        "cashfree_order_id",
        "user",
        "amount",
        "currency",
        "status",
        "order",
        "created_at",
    )
    list_filter = ("status", "currency", "created_at")
    search_fields = ("cashfree_order_id", "user__email", "payment_session_id")
    readonly_fields = ("created_at", "updated_at")

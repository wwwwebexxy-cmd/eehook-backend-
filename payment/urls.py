from django.urls import path
from .views import *
from .cashfree_views import (
    cashfree_payment_success,
    cashfree_webhook,
    create_cashfree_order,
)

urlpatterns = [
    path(
        "create-cashfree-order/",
        create_cashfree_order,
        name="create_cashfree_order",
    ),
    path(
        "cashfree-success/",
        cashfree_payment_success,
        name="cashfree-success",
    ),
    path(
        "cashfree-webhook/",
        cashfree_webhook,
        name="cashfree_webhook",
    ),
    path(
        "create-checkout-session/",
        create_checkout_session,
        name="create_checkout_session",
    ),
    path(
    "payment-success/",
        payment_success,
        name="payment-success",
    ),
      path(
        "stripe-webhook/",
        stripe_webhook,
        name="stripe_webhook"
    ),
]

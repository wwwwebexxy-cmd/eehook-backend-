from django.conf import settings
from django.db import models


class CashfreeCheckout(models.Model):
    """Server-side snapshot for a Cashfree checkout attempt.

    Cashfree creates its payment order before the customer pays. Keeping the
    cart snapshot here means fulfilment never trusts a cart that may have
    changed while the customer was on the hosted checkout page.
    """

    STATUS_CHOICES = (
        ("Created", "Created"),
        ("Active", "Active"),
        ("Paid", "Paid"),
        ("Fulfilled", "Fulfilled"),
        ("Failed", "Failed"),
        ("Fulfillment Error", "Fulfillment Error"),
        ("Expired", "Expired"),
        ("Terminated", "Terminated"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cashfree_checkouts",
    )
    address = models.ForeignKey(
        "myapp.Address",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cashfree_checkouts",
    )
    order = models.OneToOneField(
        "myapp.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cashfree_checkout",
    )
    cashfree_order_id = models.CharField(max_length=255, unique=True)
    payment_session_id = models.TextField(blank=True)
    idempotency_key = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3)
    snapshot = models.JSONField(default=dict)
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="Created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = (
            models.Index(fields=("user", "status")),
            models.Index(fields=("created_at",)),
        )

    def __str__(self):
        return f"{self.cashfree_order_id} ({self.status})"

"""WhatsApp Cloud API notifications for new orders."""

import logging
import re

import requests
from django.conf import settings


logger = logging.getLogger(__name__)


def send_owner_order_notification(order_id):
    """Send a new-order alert to the configured owner WhatsApp number.

    Missing WhatsApp configuration or a provider error is deliberately logged
    and ignored so that an order is never rolled back because a notification
    provider is temporarily unavailable.
    """
    access_token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
    phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    owner_phone = re.sub(
        r"\D",
        "",
        getattr(settings, "WHATSAPP_OWNER_PHONE", ""),
    )

    if not all((access_token, phone_number_id, owner_phone)):
        logger.warning("WhatsApp owner notification skipped: API is not configured")
        return False

    from .models import Order

    try:
        order = (
            Order.objects.select_related("user", "address")
            .prefetch_related("items__product", "items__color", "items__unit")
            .get(pk=order_id)
        )
    except Order.DoesNotExist:
        logger.error("WhatsApp owner notification skipped: order %s not found", order_id)
        return False

    address = order.address
    customer_name = (
        (address.full_name if address else "")
        or order.user.get_full_name()
        or order.user.email
    )
    item_lines = []
    for item in order.items.all():
        item_lines.append(f"- {item.product.name} x {item.quantity} = {item.total_price}")

    message = (
        "New order received\n"
        f"Order: ORD-{order.id:06d}\n"
        f"Customer: {customer_name}\n"
        f"Phone: {address.phone if address else 'N/A'}\n"
        f"Items:\n{'\n'.join(item_lines)}\n"
        f"Total: {order.total_amount}"
    )

    api_version = getattr(settings, "WHATSAPP_API_VERSION", "v22.0")
    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": owner_phone,
        "type": "text",
        "text": {"preview_url": False, "body": message},
    }

    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("WhatsApp owner notification failed for order %s", order_id)
        return False

    logger.info("WhatsApp owner notification sent for order %s", order_id)
    return True

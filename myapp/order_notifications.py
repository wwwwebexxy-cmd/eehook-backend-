"""Email notifications for newly paid orders.

The SMTP settings are provider-agnostic, so Mailtrap Sandbox and Mailtrap
Email Sending can be used without putting provider credentials in the code.
Notification delivery is deliberately best-effort: an SMTP outage must not
roll back an already-paid order.
"""

import logging
from html import escape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.timezone import localtime

from .models import Order


logger = logging.getLogger(__name__)


def _configured_owner_email():
    return str(
        getattr(settings, "ORDER_NOTIFICATION_EMAIL", "")
        or getattr(settings, "EMAIL_HOST_USER", "")
        or ""
    ).strip()


def _dashboard_url(order):
    site_url = str(getattr(settings, "SITE_URL", "")).rstrip("/")
    return f"{site_url}/eehook-dashboard/orders/{order.pk}"


def send_owner_order_email(order_id):
    """Send an order summary and dashboard link to the configured owner."""

    owner_email = _configured_owner_email()
    if not owner_email:
        logger.warning(
            "Owner order email skipped: ORDER_NOTIFICATION_EMAIL is not configured"
        )
        return False

    try:
        order = (
            Order.objects.select_related("user", "address")
            .prefetch_related("items__product", "items__color", "items__unit")
            .get(pk=order_id)
        )
    except Order.DoesNotExist:
        logger.error("Owner order email skipped: order %s not found", order_id)
        return False

    address = order.address
    customer_name = (
        (address.full_name if address else "")
        or order.user.get_full_name()
        or order.user.email
    )
    dashboard_url = _dashboard_url(order)
    order_number = f"ORD-{order.pk:06d}"
    item_lines = []
    item_rows = []
    for item in order.items.all():
        product_name = item.product.name if item.product_id else "Product"
        item_lines.append(f"- {product_name} x {item.quantity} = {item.total_price}")
        item_rows.append(
            "<tr>"
            f"<td style=\"padding:8px 0\">{escape(product_name)}</td>"
            f"<td style=\"padding:8px 0;text-align:center\">{item.quantity}</td>"
            f"<td style=\"padding:8px 0;text-align:right\">{escape(str(item.total_price))}</td>"
            "</tr>"
        )

    address_lines = [
        address.address_line if address else "",
        address.city if address else "",
        address.postal_code if address else "",
        address.country if address else "",
    ]
    address_text = ", ".join(str(value) for value in address_lines if value)
    created_at = localtime(order.created_at).strftime("%d %b %Y, %I:%M %p")
    phone = address.phone if address else "N/A"

    text_body = "\n".join(
        [
            "New order received",
            f"Order: {order_number}",
            f"Placed: {created_at}",
            f"Customer: {customer_name}",
            f"Email: {order.user.email}",
            f"Phone: {phone}",
            f"Shipping address: {address_text or 'N/A'}",
            "",
            "Items:",
            *(item_lines or ["- No items recorded"]),
            "",
            f"Total: {order.total_amount}",
            f"Payment method: {order.get_payment_method_display()}",
            f"Payment: {order.payment_status}",
            f"Status: {order.status}",
            "",
            f"Open the order dashboard to review and update shipping status: {dashboard_url}",
        ]
    )

    safe_customer = escape(customer_name)
    safe_email = escape(order.user.email)
    safe_phone = escape(str(phone))
    safe_address = escape(address_text or "N/A")
    safe_created_at = escape(created_at)
    safe_status = escape(order.status)
    safe_payment_status = escape(order.payment_status)
    safe_total = escape(str(order.total_amount))
    html_body = f"""
    <div style=\"font-family:Arial,sans-serif;line-height:1.5;color:#1f2937;max-width:640px\">
      <h2 style=\"margin-bottom:4px\">New order received</h2>
      <p style=\"margin-top:0;color:#6b7280\">{escape(order_number)} · {safe_created_at}</p>
      <h3>Customer</h3>
      <p>{safe_customer}<br>{safe_email}<br>{safe_phone}<br>{safe_address}</p>
      <h3>Order summary</h3>
      <table style=\"width:100%;border-collapse:collapse\">
        <thead><tr style=\"border-bottom:1px solid #d1d5db\">
          <th style=\"text-align:left;padding:8px 0\">Item</th>
          <th style=\"text-align:center;padding:8px 0\">Qty</th>
          <th style=\"text-align:right;padding:8px 0\">Amount</th>
        </tr></thead>
        <tbody>{''.join(item_rows) or '<tr><td colspan=\"3\">No items recorded</td></tr>'}</tbody>
      </table>
      <p><strong>Total:</strong> {safe_total}<br>
         <strong>Payment method:</strong> {escape(order.get_payment_method_display())}<br>
         <strong>Payment:</strong> {safe_payment_status}<br>
         <strong>Status:</strong> {safe_status}</p>
      <p>
        <a href=\"{escape(dashboard_url)}\" style=\"display:inline-block;background:#111827;color:#fff;padding:12px 18px;border-radius:6px;text-decoration:none\">
          Open order dashboard
        </a>
      </p>
      <p style=\"font-size:12px;color:#6b7280\">Sign in as an administrator to update Processing, Shipped, Delivered, or Cancelled status.</p>
    </div>
    """

    message = EmailMultiAlternatives(
        subject=f"New order {order_number} received",
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[owner_email],
        # Let the owner reply directly to the customer from the order email.
        reply_to=[order.user.email] if order.user.email else [],
    )
    message.attach_alternative(html_body, "text/html")

    try:
        message.send(fail_silently=False)
    except Exception:
        logger.exception("Owner order email failed for order %s", order_id)
        return False

    logger.info("Owner order email sent for order %s", order_id)
    return True


def send_order_notifications(order_id):
    """Send all configured owner notifications after an order is committed."""

    email_sent = send_owner_order_email(order_id)
    from .whatsapp import send_owner_order_notification as send_whatsapp_notification

    whatsapp_sent = send_whatsapp_notification(order_id)
    return email_sent or whatsapp_sent

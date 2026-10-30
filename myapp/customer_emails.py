"""Customer-facing registration, order, and paid-invoice emails."""

import logging
from html import escape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone
from django.utils.timezone import localtime

from .invoice import render_tax_invoice
from .models import Order, User


logger = logging.getLogger(__name__)


def _site_url(path=""):
    return f"{str(getattr(settings, 'SITE_URL', '')).rstrip('/')}/{path.lstrip('/')}"


def _name(user, address=None):
    return (
        (getattr(address, "full_name", "") if address else "")
        or user.get_full_name()
        or user.email
        or "Customer"
    ).strip()


def _money(value):
    return f"AED {value or 0:,.2f}"


def _order_number(order):
    return f"ORD-{order.pk:06d}"


def _address_text(order):
    address = order.address
    if not address:
        return "Address not provided"
    values = (
        address.address_line,
        address.city,
        address.emirate,
        address.postal_code,
        address.country,
    )
    return ", ".join(str(value).strip() for value in values if value)


def _item_label(item):
    details = []
    if item.color:
        details.append(item.color.name)
    unit = item.variant_unit.unit if item.variant_unit_id and item.variant_unit.unit_id else item.unit
    if unit:
        unit_type = getattr(unit, "unit_type", None)
        details.append(
            f"{unit_type.name}: {unit.name}" if unit_type else unit.name
        )
    if item.variant_unit_id and item.variant_unit.grade:
        details.append(f"Grade: {item.variant_unit.grade}")
    return item.product.name + (f" ({' | '.join(details)})" if details else "")


def _email_shell(title, content):
    return f"""
    <div style=\"margin:0;background:#f8faf8;padding:28px 12px;font-family:Arial,Helvetica,sans-serif;color:#304a54\">
      <table role=\"presentation\" style=\"width:100%;max-width:680px;margin:0 auto;background:#fff;border:1px solid #e2e8e4;border-radius:14px;border-collapse:separate;overflow:hidden\">
        <tr><td style=\"padding:24px 30px;border-bottom:1px solid #e2e8e4\">
          <div style=\"font-size:28px;font-weight:800;letter-spacing:-1px;color:#4f6973\"><span style=\"color:#ff9000\">+</span>eehook</div>
          <div style=\"margin-top:3px;color:#ff9000;font-size:11px;font-style:italic\">Seriously Different</div>
        </td></tr>
        <tr><td style=\"padding:30px\"><h1 style=\"margin:0 0 18px;color:#111;font-size:26px\">{title}</h1>{content}</td></tr>
        <tr><td style=\"padding:18px 30px;background:#fafcfa;border-top:1px solid #e2e8e4;color:#71858d;font-size:12px\">Need help? Email <a href=\"mailto:support@eehook.com\" style=\"color:#d97f00\">support@eehook.com</a>.</td></tr>
      </table>
    </div>
    """


def _text_and_html(subject, text_body, html_body, recipient, *, attachment=None):
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[recipient],
    )
    message.attach_alternative(html_body, "text/html")
    if attachment:
        message.attach(*attachment)
    return message


def _send(message):
    try:
        return bool(message.send(fail_silently=False))
    except Exception:
        logger.exception("Customer email delivery failed", extra={"recipient": message.to})
        return False


def send_registration_email(user_id):
    """Send the welcome email once, after a customer account is created."""
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user_id)
        if user.registration_email_sent_at or not user.email:
            return False

        assignment = (
            user.welcome_bonus_assignments.select_related("welcome_bonus")
            .filter(status__in=("AVAILABLE", "CLAIMED"))
            .order_by("-created_at")
            .first()
        )
        name = _name(user)
        bonus_html = ""
        bonus_text = ""
        if assignment:
            bonus = assignment.welcome_bonus
            if bonus.discount_type == "FIXED":
                discount = _money(bonus.fixed_amount)
                rule = f"{discount} off your first eligible order"
            else:
                discount = f"{bonus.discount_percentage}%"
                rule = f"{discount} off your first eligible order"
            bonus_html = f"""
              <div style=\"margin:24px 0;padding:20px;border:1px solid #ffd08a;border-radius:10px;background:#fff7e8\">
                <div style=\"font-size:12px;color:#9b6a16;font-weight:700;letter-spacing:1px\">YOUR WELCOME GIFT</div>
                <div style=\"margin:8px 0;font-size:24px;color:#111;font-weight:800\">{escape(assignment.code)}</div>
                <div style=\"color:#424242\">{escape(rule)}.</div>
              </div>
            """
            bonus_text = f"\nYour welcome bonus code: {assignment.code} ({rule}).\n"

        subject = "Welcome to EEHOOK"
        text_body = (
            f"Welcome to EEHOOK, {name}.\n\n"
            "Your account is ready. Start shopping for seriously different products.\n"
            f"{bonus_text}\n"
            f"Visit EEHOOK: {_site_url('/')}\n"
        )
        html_body = _email_shell(
            "WELCOME TO EEHOOK",
            f"""
            <p style=\"font-size:20px;font-weight:700;color:#111\">One last step, {escape(name)}.</p>
            <p style=\"line-height:1.65;color:#424242\">Thanks for creating your EEHOOK account. Your account is active and ready for shopping.</p>
            {bonus_html}
            <p><a href=\"{escape(_site_url('/'))}\" style=\"display:inline-block;padding:13px 20px;border-radius:7px;background:#ff9000;color:#111;text-decoration:none;font-weight:800\">START SHOPPING</a></p>
            <p style=\"margin-top:24px;color:#71858d;font-size:12px\">Fast delivery · Easy returns · Member offers</p>
            """,
        )
        message = _text_and_html(subject, text_body, html_body, user.email)
        if not _send(message):
            return False
        user.registration_email_sent_at = timezone.now()
        user.save(update_fields=("registration_email_sent_at",))
        return True


def _get_order(order_id):
    return (
        Order.objects.select_for_update()
        .select_related("user", "address")
        .prefetch_related(
            "items__product",
            "items__color",
            "items__unit__unit_type",
            "items__variant_unit__unit",
            "items__variant_unit__unit_type",
        )
        .get(pk=order_id)
    )


def send_order_confirmation_email(order_id):
    """Send the pending COD/WhatsApp order confirmation once."""
    with transaction.atomic():
        order = _get_order(order_id)
        if (
            order.order_confirmation_email_sent_at
            or not order.user.email
            or order.payment_method not in {"COD", "WHATSAPP"}
        ):
            return False

        name = _name(order.user, order.address)
        number = _order_number(order)
        rows = "".join(
            f"<tr><td style=\"padding:10px 0;border-bottom:1px solid #edf1ee\">{escape(_item_label(item))}</td>"
            f"<td style=\"padding:10px 0;text-align:center;border-bottom:1px solid #edf1ee\">{item.quantity}</td>"
            f"<td style=\"padding:10px 0;text-align:right;border-bottom:1px solid #edf1ee\">{escape(_money(item.total_price))}</td></tr>"
            for item in order.items.all()
        )
        rows = rows or '<tr><td colspan="3" style="padding:10px 0">Your order is being prepared.</td></tr>'
        text_body = (
            f"Order confirmed — {number}\n\nThank you, {name}.\n"
            "We have received your order and are getting it ready.\n\n"
            f"Total: {_money(order.total_amount)}\nShipping to: {_address_text(order)}\n"
        )
        html_body = _email_shell(
            "ORDER CONFIRMED",
            f"""
            <p style=\"font-size:20px;font-weight:700;color:#111\">Thank you, {escape(name)}.</p>
            <p style=\"line-height:1.65;color:#424242\">We’ve received your order and we’re getting it ready. You’ll get another email with tracking details as soon as it ships.</p>
            <div style=\"margin:24px 0;padding:16px;background:#fafcfa;border:1px solid #e2e8e4;border-radius:9px\"><strong>Order {escape(number)}</strong><br><span style=\"color:#71858d\">{escape(localtime(order.created_at).strftime('%d %b %Y'))}</span></div>
            <table style=\"width:100%;border-collapse:collapse;font-size:14px\"><thead><tr><th style=\"text-align:left;padding:8px 0\">Item</th><th style=\"text-align:center;padding:8px 0\">Qty</th><th style=\"text-align:right;padding:8px 0\">Amount</th></tr></thead><tbody>{rows}</tbody></table>
            <p style=\"text-align:right;font-size:18px;font-weight:800;color:#111\">Total: {escape(_money(order.total_amount))}</p>
            <p style=\"color:#424242\"><strong>Shipping to:</strong><br>{escape(_address_text(order))}</p>
            """,
        )
        message = _text_and_html(
            f"Order confirmed — {number}",
            text_body,
            html_body,
            order.user.email,
        )
        if not _send(message):
            return False
        order.order_confirmation_email_sent_at = timezone.now()
        order.save(update_fields=("order_confirmation_email_sent_at", "updated_at"))
        return True


def send_paid_invoice_email(order_id):
    """Send a paid-order email with the generated tax invoice PDF once."""
    with transaction.atomic():
        order = _get_order(order_id)
        if (
            order.paid_invoice_email_sent_at
            or order.payment_status != "Paid"
            or not order.user.email
        ):
            return False

        name = _name(order.user, order.address)
        number = _order_number(order)
        pdf = render_tax_invoice(order)
        filename = f"EEHOOK-{number}-invoice.pdf"
        text_body = (
            f"Paid invoice — {number}\n\nHi {name}, you’re all HOOKED in!\n\n"
            "Thank you for shopping with EEHOOK. Your payment has been received and your order is being prepared. "
            f"Your invoice is attached for your records.\n\nTotal paid: {_money(order.total_amount)}\n"
        )
        html_body = _email_shell(
            "PAYMENT RECEIVED",
            f"""
            <p style=\"font-size:20px;font-weight:700;color:#111\">Hi {escape(name)}, you’re all HOOKED in!</p>
            <p style=\"line-height:1.65;color:#424242\">Thank you for shopping with EEHOOK. Your payment has been received and your order is being prepared. Your invoice is attached for your records.</p>
            <div style=\"margin:24px 0;padding:18px;border-radius:9px;background:#e9f7ef;border:1px solid #b8dfc7\"><strong>PAID</strong><br>Order {escape(number)}<br>Total paid: <strong>{escape(_money(order.total_amount))}</strong></div>
            <p><a href=\"{escape(_site_url(f'/profile'))}\" style=\"display:inline-block;padding:13px 20px;border-radius:7px;background:#ff9000;color:#111;text-decoration:none;font-weight:800\">VIEW MY ORDERS</a></p>
            """,
        )
        message = _text_and_html(
            f"Paid invoice — {number}",
            text_body,
            html_body,
            order.user.email,
            attachment=(filename, pdf, "application/pdf"),
        )
        if not _send(message):
            return False
        order.paid_invoice_email_sent_at = timezone.now()
        order.save(update_fields=("paid_invoice_email_sent_at", "updated_at"))
        return True


def send_customer_order_email(order_id):
    """Select the one customer email appropriate for the order state."""
    order = Order.objects.only("payment_method", "payment_status").get(pk=order_id)
    if order.payment_status == "Paid":
        return send_paid_invoice_email(order_id)
    if order.payment_method in {"COD", "WHATSAPP"}:
        return send_order_confirmation_email(order_id)
    return False

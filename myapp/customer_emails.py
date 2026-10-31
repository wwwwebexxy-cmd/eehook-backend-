"""Customer-facing registration, order, and paid-invoice emails."""

import logging
import mimetypes
from decimal import Decimal, ROUND_HALF_UP
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from html import escape
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone
from django.utils.timezone import localtime

from .invoice import render_tax_invoice
from .models import Order, User
from .sku import resolve_order_item_sku


logger = logging.getLogger(__name__)

EMAIL_LOGO_PATH = Path(__file__).with_name("assets") / "eehook-package-logo.png"
SOCIAL_LINKS = (
    ("X", "https://x.com/eehookonline", "#111111"),
    ("f", "https://www.facebook.com/eehookonline/", "#1877f2"),
    ("t", "https://www.tiktok.com/@eehook.com", "#111111"),
    ("◎", "https://www.instagram.com/eehook.ae", "#e4405f"),
    ("▶", "https://www.youtube.com/@eehook9631", "#ff0000"),
)


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


def _decimal(value):
    return Decimal(str(value or "0")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


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


def _order_item_variant(item):
    if item.variant_unit_id and item.variant_unit and item.variant_unit.variant_id:
        return item.variant_unit.variant

    variants = list(item.product.variants.all())
    if item.color_id:
        matching = next(
            (variant for variant in variants if variant.color_id == item.color_id),
            None,
        )
        if matching:
            return matching
    return next(
        (variant for variant in variants if variant.color_id is None),
        None,
    ) or (variants[0] if variants else None)


def _order_item_sku(item):
    if item.variant_unit_id and item.variant_unit and item.variant_unit.sku:
        return str(item.variant_unit.sku).strip()
    variant = _order_item_variant(item)
    if variant and variant.sku:
        return str(variant.sku).strip()
    return resolve_order_item_sku(item) or "-"


def _order_item_image_path(item):
    variant = _order_item_variant(item)
    if not variant:
        return None
    images = list(variant.images.all())
    image = next((candidate for candidate in images if candidate.is_primary), None)
    image = image or (images[0] if images else None)
    if not image or not image.image:
        return None
    try:
        path = Path(image.image.path)
    except (AttributeError, ValueError, OSError):
        return None
    return path if path.is_file() else None


def _order_item_meta(item):
    details = []
    if item.color:
        details.append(str(item.color.name).strip())
    unit = item.variant_unit.unit if item.variant_unit_id and item.variant_unit.unit_id else item.unit
    if unit:
        unit_type = (
            item.variant_unit.unit_type
            if item.variant_unit_id and item.variant_unit.unit_type_id
            else getattr(unit, "unit_type", None)
        )
        details.append(
            f"{unit_type.name}: {unit.name}" if unit_type else str(unit.name)
        )
    if item.variant_unit_id and item.variant_unit.grade:
        details.append(f"Grade: {item.variant_unit.grade}")
    sku = _order_item_sku(item)
    if sku != "-":
        details.append(sku)
    details.append(f"Qty {item.quantity}")
    return " · ".join(details)


def _order_arrival_text(order):
    for item in order.items.all():
        delivery = str(item.product.estimated_delivery_time or "").strip()
        if delivery:
            return delivery
    return "To be confirmed"


def _order_address_lines(order):
    address = order.address
    if not address:
        return ["Address not provided"]
    lines = []
    if address.full_name:
        lines.append(str(address.full_name).strip())
    if address.address_line:
        lines.append(str(address.address_line).strip())
    locality = [address.city, address.emirate, address.postal_code, address.country]
    locality_text = ", ".join(str(value).strip() for value in locality if value)
    if locality_text:
        lines.append(locality_text)
    return lines or ["Address not provided"]


def _order_payment_lines(order):
    if order.payment_method == "WHATSAPP":
        return ["WhatsApp order", "Payment to be confirmed"]
    return ["Cash on Delivery", "Payment on delivery"]


def _order_totals(order):
    subtotal = _decimal(order.subtotal)
    discount = _decimal(order.discount_amount)
    shipping = _decimal(order.shipping_charge)
    total = _decimal(order.total_amount)
    discounted_subtotal = max(subtotal - discount, Decimal("0.00"))
    included_vat = max(
        total - shipping - discounted_subtotal,
        Decimal("0.00"),
    )
    return {
        "subtotal": _money(subtotal),
        "discount": _money(discount),
        "shipping": "FREE" if shipping == Decimal("0.00") else _money(shipping),
        "vat": _money(included_vat),
        "total": _money(total),
        "has_discount": discount > Decimal("0.00"),
    }


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


def _text_and_html(
    subject,
    text_body,
    html_body,
    recipient,
    *,
    attachment=None,
    inline_images=(),
):
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[recipient],
    )
    message.attach_alternative(html_body, "text/html")
    if attachment:
        message.attach(*attachment)
    for content_id, image_path in inline_images:
        image_path = Path(image_path)
        image_data = image_path.read_bytes()
        try:
            image = MIMEImage(image_data)
        except TypeError:
            mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
            maintype, subtype = mime_type.split("/", 1)
            image = MIMEBase(maintype, subtype)
            image.set_payload(image_data)
            encoders.encode_base64(image)
        image.add_header("Content-ID", f"<{content_id}>")
        image.add_header("Content-Disposition", "inline", filename=image_path.name)
        message.attach(image)
    return message


def _send(message):
    try:
        return bool(message.send(fail_silently=False))
    except Exception:
        logger.exception("Customer email delivery failed", extra={"recipient": message.to})
        return False


def _decimal_text(value):
    return f"{value or 0:.2f}".rstrip("0").rstrip(".")


def _welcome_bonus_scope(bonus):
    if bonus.applicability_type == "CATEGORY":
        scope = bonus.category.name if bonus.category_id else "Selected category"
        if bonus.subcategory_id:
            scope = f"{scope} / {bonus.subcategory.name}"
        return scope

    products = [product.name for product in bonus.products.all()]
    return ", ".join(products) or "Selected products"


def _welcome_bonus_copy(assignment):
    bonus = assignment.welcome_bonus
    if bonus.discount_type == "FIXED":
        discount = f"{_money(bonus.fixed_amount)} off"
    else:
        discount = f"{_decimal_text(bonus.discount_percentage)}% off"
    valid_until = localtime(bonus.end_date).strftime("%d %b %Y")
    return discount, _welcome_bonus_scope(bonus), valid_until


def _welcome_gift_html(assignments):
    if not assignments:
        return ""

    entries = []
    for assignment in assignments:
        discount, scope, valid_until = _welcome_bonus_copy(assignment)
        entries.append(
            f"""
            <div style=\"padding:12px 0;border-top:1px dashed #f0bd68\">
              <div style=\"font-size:24px;line-height:1.15;color:#17364b;font-weight:800;letter-spacing:.3px\">{escape(assignment.code)}</div>
              <div style=\"margin-top:5px;color:#304a54;font-size:15px;line-height:1.45\"><strong>{escape(discount)}</strong> on your first eligible order.</div>
              <div style=\"margin-top:4px;color:#71858d;font-size:12px;line-height:1.45\">Valid on: {escape(scope)}</div>
              <div style=\"margin-top:3px;color:#71858d;font-size:12px;line-height:1.45\">Valid until: {escape(valid_until)}</div>
            </div>
            """
        )
    return f"""
      <div style=\"margin:26px 0;padding:18px 20px;border:1px dashed #e79a27;border-radius:8px;background:#fffaf0\">
        <div style=\"margin-bottom:4px;font-size:12px;color:#a46a13;font-weight:800;letter-spacing:1.2px\">YOUR WELCOME GIFT</div>
        {''.join(entries)}
        <div style=\"margin-top:8px;color:#71858d;font-size:12px;line-height:1.45\">Use the code at checkout while the campaign is active.</div>
      </div>
    """


def _welcome_gift_text(assignments):
    if not assignments:
        return ""
    lines = ["\nYour welcome gift:"]
    for assignment in assignments:
        discount, scope, valid_until = _welcome_bonus_copy(assignment)
        lines.append(
            f"{assignment.code} — {discount} on your first eligible order. "
            f"Valid on: {scope}. Valid until: {valid_until}."
        )
    lines.append("Use the code at checkout while the campaign is active.\n")
    return "\n".join(lines)


def _social_links_html():
    return "".join(
        f"<a href=\"{escape(url)}\" aria-label=\"EEHOOK on {escape(label)}\" style=\"display:inline-block;margin:0 3px;text-decoration:none\"><span style=\"display:inline-block;width:24px;height:24px;line-height:24px;border-radius:50%;background:{color};color:#ffffff;font-size:12px;font-weight:800;text-align:center\">{escape(label)}</span></a>"
        for label, url, color in SOCIAL_LINKS
    )


def _registration_email_html(name, gift_html):
    site_url = escape(_site_url("/"))
    return f"""
    <!doctype html>
    <html lang=\"en\">
      <head>
        <meta http-equiv=\"Content-Type\" content=\"text/html; charset=utf-8\">
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
        <title>Welcome to EEHOOK</title>
        <style>
          @media screen and (max-width: 620px) {{
            .eehook-email-shell {{ padding: 10px !important; }}
            .eehook-email-card {{ width: 100% !important; }}
            .eehook-email-body {{ padding: 28px 20px !important; }}
            .eehook-feature-cell {{ display: block !important; width: 100% !important; padding: 8px 0 !important; }}
          }}
        </style>
      </head>
      <body style=\"margin:0;padding:0;background:#f4f0e6;font-family:Arial,Helvetica,sans-serif;color:#304a54\">
        <div class=\"eehook-email-shell\" style=\"padding:28px 12px;background:#f4f0e6\">
          <table role=\"presentation\" class=\"eehook-email-card\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"width:100%;max-width:620px;margin:0 auto;background:#ffffff;border-top:4px solid #ff9000;border-radius:8px;overflow:hidden\">
            <tr>
              <td style=\"padding:28px 30px 18px;text-align:right\">
                <a href=\"{site_url}\" style=\"text-decoration:none\"><img src=\"cid:eehook-logo\" width=\"165\" alt=\"EEHOOK - Seriously Different\" style=\"display:inline-block;width:165px;max-width:70%;height:auto;border:0\"></a>
              </td>
            </tr>
            <tr>
              <td class=\"eehook-email-body\" style=\"padding:8px 50px 34px\">
                <table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">
                  <tr><td style=\"font-size:12px;line-height:1.4;color:#ff9000;font-weight:800;letter-spacing:.8px\">WELCOME TO <span style=\"color:#38586a\">EEHOOK</span> <a href=\"{escape(_site_url('/login'))}\" style=\"display:inline-block;margin-left:8px;padding:4px 8px;border:1px solid #f0c276;border-radius:12px;color:#a46a13;font-size:10px;text-decoration:none;letter-spacing:0\">Login to your account</a></td></tr>
                  <tr><td style=\"padding-top:26px;font-size:28px;line-height:1.15;color:#17364b;font-weight:800\">One last step, {escape(name)}.</td></tr>
                  <tr><td style=\"padding-top:14px;font-size:15px;line-height:1.65;color:#61717b\">Thanks for creating your EEHOOK account. Your account is active and ready for seriously different products.</td></tr>
                  <tr><td style=\"padding-top:22px\"><a href=\"{site_url}\" style=\"display:inline-block;padding:13px 18px;border-radius:5px;background:#38586a;color:#ffffff;font-size:12px;font-weight:800;letter-spacing:.5px;text-decoration:none\">START SHOPPING</a></td></tr>
                  {f'<tr><td>{gift_html}</td></tr>' if gift_html else ''}
                  <tr><td style=\"padding-top:20px;font-size:12px;line-height:1.55;color:#71858d\">You can manage your account, orders and saved products any time from My Account.</td></tr>
                  <tr><td style=\"padding-top:28px\"><table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\"><tr>
                    <td class=\"eehook-feature-cell\" width=\"33.33%\" valign=\"top\" style=\"padding-right:12px\"><span style=\"display:block;width:22px;height:22px;background:#ff9000\"></span><strong style=\"display:block;padding-top:9px;font-size:13px;color:#304a54\">Fast delivery</strong><span style=\"display:block;padding-top:4px;font-size:11px;line-height:1.45;color:#71858d\">Tracked shipping straight to your door.</span></td>
                    <td class=\"eehook-feature-cell\" width=\"33.33%\" valign=\"top\" style=\"padding:0 6px\"><span style=\"display:block;width:22px;height:22px;background:#ff9000\"></span><strong style=\"display:block;padding-top:9px;font-size:13px;color:#304a54\">Easy returns</strong><span style=\"display:block;padding-top:4px;font-size:11px;line-height:1.45;color:#71858d\">Changed your mind? No stress.</span></td>
                    <td class=\"eehook-feature-cell\" width=\"33.33%\" valign=\"top\" style=\"padding-left:12px\"><span style=\"display:block;width:22px;height:22px;background:#ff9000\"></span><strong style=\"display:block;padding-top:9px;font-size:13px;color:#304a54\">Member offers</strong><span style=\"display:block;padding-top:4px;font-size:11px;line-height:1.45;color:#71858d\">First to know about new drops.</span></td>
                  </tr></table></td></tr>
                </table>
              </td>
            </tr>
            <tr><td style=\"padding:0 50px\"><div style=\"height:1px;background:#e8eceb\"></div></td></tr>
            <tr><td style=\"padding:22px 50px 26px;text-align:center;font-size:11px;line-height:1.55;color:#71858d\">Didn’t you create this account? You can safely ignore this email — nothing will happen without your confirmation.</td></tr>
            <tr><td style=\"padding:22px 30px 24px;background:#38586a;text-align:center\"><div style=\"color:#ff9000;font-size:13px;font-weight:800;letter-spacing:1.3px\">SERIOUSLY DIFFERENT</div><div style=\"padding-top:14px;font-size:11px\"><a href=\"{escape(_site_url('/contact'))}\" style=\"color:#ffffff;text-decoration:none\">Help Centre</a><span style=\"color:#ffb65a;padding:0 5px\">|</span><a href=\"{escape(_site_url('/contact'))}\" style=\"color:#ffffff;text-decoration:none\">Returns</a><span style=\"color:#ffb65a;padding:0 5px\">|</span><a href=\"{escape(_site_url('/profile'))}\" style=\"color:#ffffff;text-decoration:none\">My Account</a><span style=\"color:#ffb65a;padding:0 5px\">|</span><a href=\"{escape(_site_url('/about'))}\" style=\"color:#ffffff;text-decoration:none\">Terms</a></div><div style=\"padding-top:12px;color:#d8e0e3;font-size:11px\">EEHOOK · Dubai, United Arab Emirates · <a href=\"{site_url}\" style=\"color:#ffffff;text-decoration:none\">www.eehook.com</a></div><div style=\"padding-top:6px;color:#d8e0e3;font-size:11px\">Questions? Write to <a href=\"mailto:support@eehook.com\" style=\"color:#ffffff;text-decoration:none\">support@eehook.com</a></div><div style=\"padding-top:13px;color:#b9c8ce;font-size:10px\">You’re receiving this email because an account was created at eehook.com.</div></td></tr>
          </table>
          <div style=\"padding:16px 0 4px;text-align:center\">{_social_links_html()}</div>
        </div>
      </body>
    </html>
    """


def send_registration_email(user_id):
    """Send the welcome email once, after a customer account is created."""
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user_id)
        if user.registration_email_sent_at or not user.email:
            return False

        now = timezone.now()
        assignments = list(
            user.welcome_bonus_assignments.select_related("welcome_bonus")
            .select_related("welcome_bonus__category", "welcome_bonus__subcategory")
            .prefetch_related("welcome_bonus__products")
            .filter(status__in=("AVAILABLE", "CLAIMED"))
            .filter(
                welcome_bonus__is_active=True,
                welcome_bonus__archived_at__isnull=True,
                welcome_bonus__start_date__lte=now,
                welcome_bonus__end_date__gte=now,
            )
            .order_by("created_at", "id")
        )
        name = _name(user)
        gift_html = _welcome_gift_html(assignments)
        gift_text = _welcome_gift_text(assignments)
        subject = "Welcome to EEHOOK — your account is ready"
        text_body = (
            f"Welcome to EEHOOK, {name}.\n\n"
            "Your account is active and ready for seriously different products.\n"
            f"{gift_text}\n"
            f"Start shopping: {_site_url('/')}\n"
        )
        html_body = _registration_email_html(name, gift_html)
        message = _text_and_html(
            subject,
            text_body,
            html_body,
            user.email,
            inline_images=(("eehook-logo", EMAIL_LOGO_PATH),),
        )
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
            "items__product__variants__images",
            "items__color",
            "items__unit__unit_type",
            "items__variant_unit__unit",
            "items__variant_unit__unit_type",
            "items__variant_unit__variant__images",
        )
        .get(pk=order_id)
    )


def _order_item_rows_html(items, image_cids):
    rows = []
    for index, item in enumerate(items):
        product_name = escape(str(item.product.name))
        metadata = escape(_order_item_meta(item))
        image_cid = image_cids.get(index)
        if image_cid:
            visual = (
                f'<img src="cid:{escape(image_cid)}" width="58" height="58" '
                f'alt="{product_name}" style="display:block;width:58px;height:58px;object-fit:contain;border:0">'
            )
        else:
            visual = (
                '<div aria-hidden="true" style="width:58px;height:58px;background:#f4f0e6;'
                'border-radius:4px"></div>'
            )
        rows.append(
            f'''<tr>
              <td style="padding:10px 8px 10px 0;border-bottom:1px solid #e7e0d3;width:68px;vertical-align:middle">{visual}</td>
              <td style="padding:10px 8px;border-bottom:1px solid #e7e0d3;vertical-align:middle">
                <div style="font-size:15px;line-height:1.35;color:#304a54;font-weight:700">{product_name}</div>
                <div style="padding-top:3px;font-size:11px;line-height:1.45;color:#71858d">{metadata}</div>
              </td>
              <td style="padding:10px 0;text-align:right;border-bottom:1px solid #e7e0d3;white-space:nowrap;vertical-align:middle;font-size:14px;color:#304a54">{escape(_money(item.total_price))}</td>
            </tr>'''
        )
    return "".join(rows) or (
        '<tr><td colspan="3" style="padding:14px 0;border-bottom:1px solid #e7e0d3;'
        'font-size:13px;color:#71858d">Your order is being prepared.</td></tr>'
    )


def _order_confirmation_email_html(
    order,
    name,
    number,
    items,
    image_cids,
):
    site_url = escape(_site_url("/"))
    order_url = escape(_site_url("/myorders"))
    arrival = escape(_order_arrival_text(order))
    totals = _order_totals(order)
    address_lines = "<br>".join(escape(line) for line in _order_address_lines(order))
    payment_lines = "<br>".join(escape(line) for line in _order_payment_lines(order))
    discount_row = ""
    if totals["has_discount"]:
        discount_row = f'''
          <tr><td style="padding:6px 0;text-align:left;color:#71858d">Discount</td><td style="padding:6px 0;text-align:right;color:#ff9000">- {escape(totals["discount"])}</td></tr>'''

    return f'''
    <!doctype html>
    <html lang="en">
      <head>
        <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Order confirmed - {escape(number)}</title>
        <style>
          @media screen and (max-width: 620px) {{
            .eehook-email-shell {{ padding: 10px !important; }}
            .eehook-email-card {{ width: 100% !important; }}
            .eehook-email-body {{ padding: 34px 20px 28px !important; }}
            .eehook-email-header {{ padding: 24px 20px 16px !important; }}
            .eehook-meta-cell {{ display: block !important; width: 100% !important; border-right: 0 !important; border-bottom: 1px solid #e7e0d3 !important; }}
            .eehook-meta-cell:last-child {{ border-bottom: 0 !important; }}
            .eehook-info-cell {{ display: block !important; width: 100% !important; padding: 12px 0 0 !important; }}
            .eehook-info-cell + .eehook-info-cell {{ padding-top: 22px !important; }}
            .eehook-items-table {{ font-size: 13px !important; }}
          }}
        </style>
      </head>
      <body style="margin:0;padding:0;background:#f4f0e6;font-family:Arial,Helvetica,sans-serif;color:#304a54">
        <div class="eehook-email-shell" style="padding:28px 12px;background:#f4f0e6">
          <table role="presentation" class="eehook-email-card" width="100%" cellpadding="0" cellspacing="0" style="width:100%;max-width:620px;margin:0 auto;background:#ffffff;border-top:4px solid #ff9000;border-radius:8px;overflow:hidden">
            <tr><td class="eehook-email-header" style="padding:28px 30px 18px;text-align:right;background:#fffaf0">
              <a href="{site_url}" style="text-decoration:none"><img src="cid:eehook-logo" width="165" alt="EEHOOK - Seriously Different" style="display:inline-block;width:165px;max-width:70%;height:auto;border:0"></a>
            </td></tr>
            <tr><td class="eehook-email-body" style="padding:66px 48px 58px">
              <div style="font-size:12px;line-height:1.4;color:#ff9000;font-weight:800;letter-spacing:4px">ORDER CONFIRMED <span style="display:inline-block;width:21px;height:21px;line-height:21px;margin-left:3px;border-radius:50%;background:#ff9000;color:#17364b;text-align:center;font-size:14px;letter-spacing:0">✓</span></div>
              <h1 style="margin:62px 0 10px;font-size:28px;line-height:1.15;color:#38586a;letter-spacing:-.4px">Thank you, {escape(name)}.</h1>
              <p style="margin:0;font-size:15px;line-height:1.65;color:#71858d">We&apos;ve received your order and we&apos;re getting it ready. You&apos;ll get another email with tracking details as soon as it ships.</p>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:28px;border-top:2px solid #ff9000;background:#fffaf0">
                <tr>
                  <td class="eehook-meta-cell" width="33.33%" style="padding:17px 8px;text-align:center;border-right:1px solid #e7e0d3"><div style="font-size:10px;line-height:1.4;color:#71858d;font-weight:800;letter-spacing:2px">ORDER NO.</div><div style="padding-top:7px;font-size:15px;color:#38586a;font-weight:800">#{escape(number)}</div></td>
                  <td class="eehook-meta-cell" width="33.33%" style="padding:17px 8px;text-align:center;border-right:1px solid #e7e0d3"><div style="font-size:10px;line-height:1.4;color:#71858d;font-weight:800;letter-spacing:2px">ORDER DATE</div><div style="padding-top:7px;font-size:15px;color:#38586a;font-weight:800">{escape(localtime(order.created_at).strftime("%d %b %Y"))}</div></td>
                  <td class="eehook-meta-cell" width="33.33%" style="padding:17px 8px;text-align:center"><div style="font-size:10px;line-height:1.4;color:#71858d;font-weight:800;letter-spacing:2px">ARRIVES</div><div style="padding-top:7px;font-size:15px;color:#38586a;font-weight:800">{arrival}</div></td>
                </tr>
              </table>

              <div style="padding-top:44px;font-size:12px;line-height:1.4;color:#38586a;font-weight:800;letter-spacing:3px;border-bottom:2px solid #38586a;padding-bottom:7px">YOUR ITEMS</div>
              <table role="presentation" class="eehook-items-table" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{_order_item_rows_html(items, image_cids)}</table>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:340px;margin:24px 0 0 auto;font-size:14px">
                <tr><td style="padding:6px 0;text-align:left;color:#71858d">Subtotal</td><td style="padding:6px 0;text-align:right;color:#304a54">{escape(totals["subtotal"])}</td></tr>
                {discount_row}
                <tr><td style="padding:6px 0;text-align:left;color:#71858d">Shipping</td><td style="padding:6px 0;text-align:right;color:#304a54">{escape(totals["shipping"])}</td></tr>
                <tr><td style="padding:6px 0;text-align:left;color:#71858d">VAT (5%)</td><td style="padding:6px 0;text-align:right;color:#304a54">{escape(totals["vat"])}</td></tr>
                <tr><td colspan="2" style="padding-top:4px;border-bottom:1px solid #e7e0d3"></td></tr>
                <tr><td style="padding:18px 0 0;text-align:left;color:#38586a;font-size:12px;font-weight:800;letter-spacing:3px">TOTAL</td><td style="padding:14px 0 0;text-align:right;color:#38586a;font-size:25px;font-weight:800">{escape(totals["total"])}</td></tr>
              </table>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:38px">
                <tr>
                  <td class="eehook-info-cell" width="50%" valign="top" style="padding-right:14px"><div style="font-size:12px;color:#38586a;font-weight:800;letter-spacing:3px">SHIPPING TO</div><div style="padding-top:10px;font-size:14px;line-height:1.65;color:#304a54">{address_lines}</div></td>
                  <td class="eehook-info-cell" width="50%" valign="top" style="padding-left:14px"><div style="font-size:12px;color:#38586a;font-weight:800;letter-spacing:3px">PAYMENT</div><div style="padding-top:10px;font-size:14px;line-height:1.65;color:#304a54">{payment_lines}</div></td>
                </tr>
              </table>

              <div style="padding-top:48px;text-align:center"><a href="{order_url}" style="display:inline-block;padding:11px 15px;border-radius:18px;background:#7891a0;color:#ffffff;font-size:12px;font-weight:800;text-decoration:none">VIEW MY ORDER <span style="font-size:18px;line-height:10px;vertical-align:-1px">→</span></a></div>
            </td></tr>
            <tr><td style="padding:40px 30px 44px;background:#38586a;text-align:center"><div style="color:#ff9000;font-size:13px;font-weight:800;letter-spacing:3px">SERIOUSLY DIFFERENT</div><div style="padding-top:20px;font-size:12px"><a href="{escape(_site_url('/contact'))}" style="color:#ffffff;text-decoration:none">Help Centre</a><span style="color:#ffb65a;padding:0 5px">|</span><a href="{escape(_site_url('/contact'))}" style="color:#ffffff;text-decoration:none">Returns</a><span style="color:#ffb65a;padding:0 5px">|</span><a href="{escape(_site_url('/profile'))}" style="color:#ffffff;text-decoration:none">My Account</a><span style="color:#ffb65a;padding:0 5px">|</span><a href="{escape(_site_url('/about'))}" style="color:#ffffff;text-decoration:none">Terms</a></div><div style="padding-top:18px;color:#d8e0e3;font-size:11px">eehook · Dubai, United Arab Emirates · <a href="{site_url}" style="color:#ffffff;text-decoration:none">www.eehook.com</a></div><div style="padding-top:7px;color:#d8e0e3;font-size:11px">Questions? Write to <a href="mailto:support@eehook.com" style="color:#ffffff;text-decoration:none">support@eehook.com</a></div><div style="padding-top:14px;color:#b9c8ce;font-size:10px">You&apos;re receiving this email because you placed an order at eehook.com.</div></td></tr>
          </table>
          <div style="padding:16px 0 4px;text-align:center">{_social_links_html()}</div>
        </div>
      </body>
    </html>
    '''


def _order_confirmation_email_text(order, name, number, items):
    totals = _order_totals(order)
    lines = [
        f"Order confirmed - {number}",
        "",
        f"Thank you, {name}.",
        "We've received your order and we're getting it ready.",
        "",
        "Your items:",
    ]
    for item in items:
        lines.append(
            f"- {item.product.name} / {_order_item_meta(item)} / {_money(item.total_price)}"
        )
    lines.extend(
        [
            "",
            f"Subtotal: {totals['subtotal']}",
        ]
    )
    if totals["has_discount"]:
        lines.append(f"Discount: - {totals['discount']}")
    lines.extend(
        [
            f"Shipping: {totals['shipping']}",
            f"VAT (5%): {totals['vat']}",
            f"Total: {totals['total']}",
            "",
            f"Shipping to: {_address_text(order)}",
            "",
            f"View your order: {_site_url('/myorders')}",
        ]
    )
    return "\n".join(lines)


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
        items = list(order.items.all())
        image_cids = {}
        inline_images = [("eehook-logo", EMAIL_LOGO_PATH)]
        for index, item in enumerate(items):
            image_path = _order_item_image_path(item)
            if image_path:
                content_id = f"order-item-{index}"
                image_cids[index] = content_id
                inline_images.append((content_id, image_path))
        text_body = _order_confirmation_email_text(order, name, number, items)
        html_body = _order_confirmation_email_html(
            order,
            name,
            number,
            items,
            image_cids,
        )
        message = _text_and_html(
            f"Order confirmed - {number}",
            text_body,
            html_body,
            order.user.email,
            inline_images=inline_images,
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

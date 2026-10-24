"""PDF package-strip rendering for the super-admin order dashboard.

The label intentionally uses only data that belongs to the order, customer,
address, and catalog records.  Missing logistics fields are shown as an em
dash instead of being guessed.
"""

from io import BytesIO

from reportlab.graphics.barcode import code128
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import A6, landscape
from reportlab.pdfgen import canvas


PAGE_WIDTH, BASE_PAGE_HEIGHT = landscape(A6)
ORANGE = HexColor("#ff9000")
INK = HexColor("#111111")


def _clean(value, fallback="—"):
    text = "" if value is None else str(value).strip()
    if not text:
        return fallback
    # The built-in PDF fonts are deliberately used for a small, dependency-
    # free label. Replace unsupported characters instead of failing a download.
    return text.encode("cp1252", "replace").decode("cp1252")


def _truncate(value, max_length):
    text = _clean(value)
    return text if len(text) <= max_length else f"{text[: max_length - 1]}…"


def _full_name(order):
    address_name = getattr(order.address, "full_name", None) if order.address else None
    user_name = " ".join(
        part for part in (order.user.first_name, order.user.last_name) if part
    )
    return _clean(address_name or user_name or order.user.email, "Customer")


def _item_context(item):
    unit = item.unit
    unit_type = getattr(unit, "unit_type", None) if unit else None
    variant_unit = item.variant_unit
    if variant_unit:
        unit = variant_unit.unit or unit
        unit_type = variant_unit.unit_type or getattr(unit, "unit_type", None)

    unit_label = _clean(getattr(unit, "name", None)) if unit else "—"
    unit_type_label = _clean(getattr(unit_type, "name", None)) if unit_type else "—"
    size_label = unit_label if unit_type_label == "—" else f"{unit_label} {unit_type_label}"

    regions = []
    if variant_unit and variant_unit.variant_id:
        regions = [region.name for region in variant_unit.variant.regions.all() if region.name]
    address_city = getattr(item.order.address, "city", None) if item.order.address else None
    zone = ", ".join(regions) or _clean(address_city)

    unit_type_lower = unit_type_label.lower()
    unit_lower = unit_label.lower()
    weight = size_label if any(
        token in unit_type_lower or token in unit_lower
        for token in ("weight", "kg", "gram", "g ", "lb", "pound")
    ) else "—"

    product_name = _clean(getattr(item.product, "name", None), "Product")
    if item.color:
        product_name = f"{product_name} · {_clean(item.color.name)}"
    return {
        "name": product_name,
        "size": size_label,
        "unit_type": unit_type_label,
        "weight": weight,
        "zone": zone,
        "delivery": _clean(getattr(item.product, "estimated_delivery_time", None)),
    }


def _draw_section_header(pdf, title, x, y, width):
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(x, y, _clean(title).upper())
    pdf.setLineWidth(1)
    pdf.line(x, y - 5, x + width, y - 5)
    return y - 18


def _draw_field(pdf, label, value, x, y, value_x):
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica", 7.8)
    pdf.drawString(x, y, _clean(label).upper() + ":")
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(value_x, y, _truncate(value, 28))


def _draw_logo(pdf, x, y):
    pdf.setFillColor(ORANGE)
    pdf.rect(x + 27, y + 47, 25, 25, fill=1, stroke=0)
    pdf.rect(x + 15, y + 55, 17, 7, fill=1, stroke=0)
    pdf.rect(x + 15, y + 42, 17, 7, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#4f6973"))
    pdf.setFont("Helvetica-Bold", 19)
    pdf.drawString(x + 3, y + 22, "eehook")
    pdf.setFillColor(ORANGE)
    pdf.setFont("Helvetica-Oblique", 6)
    pdf.drawRightString(x + 73, y + 13, "Serving Different")


def _draw_barcode(pdf, value, x, y, width_limit, height, bar_width=0.8, human=True):
    barcode = code128.Code128(
        _clean(value, "EHK26-0001").replace("—", "-")[:40],
        barHeight=height,
        barWidth=bar_width,
        humanReadable=human,
    )
    scale = min(1, width_limit / max(float(barcode.width), 1))
    pdf.saveState()
    pdf.translate(x, y)
    if scale < 1:
        pdf.scale(scale, 1)
    barcode.drawOn(pdf, 0, 0)
    pdf.restoreState()


def render_package_label(order):
    """Return one landscape A6 package strip for ``order`` as PDF bytes."""

    items = list(order.items.all())
    contexts = [_item_context(item) for item in items]
    order_number = f"EHK26/{order.pk:04d}"
    package_code = order_number.replace("/", "-")
    # The reference label has no item list, while this implementation adds a
    # small barcode row for every ordered product. Reserve that row even for a
    # single-item order, then grow the strip for additional products.
    extra_height = 30 + max(0, len(items) - 1) * 28
    page_height = BASE_PAGE_HEIGHT + extra_height
    address = order.address
    customer_name = _full_name(order)
    phone = _clean(getattr(address, "phone", None) if address else None)
    city = _clean(getattr(address, "city", None) if address else None)
    email = _clean(order.user.email)
    address_lines = [
        _clean(getattr(address, "address_line", None) if address else None),
        ", ".join(
            part
            for part in (
                getattr(address, "city", None) if address else None,
                getattr(address, "postal_code", None) if address else None,
            )
            if part
        ),
        _clean(getattr(address, "country", None) if address else None),
    ]
    address_lines = [line for line in address_lines if line != "—"]

    weight_values = sorted({context["weight"] for context in contexts if context["weight"] != "—"})
    size_values = sorted({context["size"] for context in contexts if context["size"] != "—"})
    zone_values = sorted({context["zone"] for context in contexts if context["zone"] != "—"})
    delivery_values = sorted({context["delivery"] for context in contexts if context["delivery"] != "—"})
    package_info = {
        "ORDER": order_number,
        "WEIGHT": ", ".join(weight_values) or "—",
        "SIZE": ", ".join(size_values) or "—",
        "ZONE": ", ".join(zone_values) or "—",
        "SHIP DATE": "—",
        "REFERENCE": f"ORD-{order.pk:06d}",
        "SERVICE": _clean(order.payment_method, "Standard"),
        "PAYMENT": "PAID" if str(order.payment_status).strip().lower() == "paid" else "UNPAID",
    }

    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(PAGE_WIDTH, page_height))
    margin = 8
    top = page_height - margin
    top_height = 95
    barcode_height = 72
    top_bottom = top - top_height
    barcode_bottom = top_bottom - barcode_height
    lower_bottom = margin
    lower_height = barcode_bottom - lower_bottom

    pdf.setStrokeColor(black)
    pdf.setFillColor(white)
    pdf.setLineWidth(2)
    pdf.rect(margin, margin, PAGE_WIDTH - margin * 2, page_height - margin * 2, fill=1, stroke=1)

    # Header: logo, Ship To, Ship From.
    pdf.line(90, top_bottom, 90, top)
    pdf.line(250, top_bottom, 250, top)
    _draw_logo(pdf, 12, top_bottom + 8)
    x = 100
    y = _draw_section_header(pdf, "SHIP TO", x, top - 17, 140)
    pdf.setFont("Helvetica-Bold", 10.5)
    pdf.setFillColor(INK)
    pdf.drawString(x, y, _truncate(customer_name, 25))
    y -= 15
    pdf.setFont("Helvetica", 8.5)
    for line in address_lines[:3]:
        pdf.drawString(x, y, _truncate(line, 29))
        y -= 12
    pdf.drawString(x, y, _truncate(phone, 29))
    y -= 12
    pdf.drawString(x, y, _truncate(email, 29))

    x = 260
    y = _draw_section_header(pdf, "SHIP FROM", x, top - 17, 145)
    pdf.setFont("Helvetica", 8.5)
    for line in ("EEHOOK", "(Dexon Advertising LLC)", "Warehouse 9", "Al Qusais 5", "Dubai UAE"):
        pdf.drawString(x, y, line)
        y -= 13

    # Large package barcode and a prominent delivery contact block.
    pdf.line(250, barcode_bottom, 250, top_bottom)
    _draw_barcode(pdf, package_code, 28, barcode_bottom + 25, 205, 28, bar_width=0.75)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawCentredString(335, barcode_bottom + 45, _truncate(customer_name, 18).upper())
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawCentredString(335, barcode_bottom + 28, _truncate(phone, 17))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(335, barcode_bottom + 13, _truncate(city, 22))

    # Lower half: package information and item-level barcode references.
    pdf.line(170, lower_bottom, 170, barcode_bottom)
    y = _draw_section_header(pdf, "PACKAGE INFORMATION", 18, barcode_bottom - 16, 140)
    value_x = 76
    for label, value in package_info.items():
        _draw_field(pdf, label, value, 18, y, value_x)
        y -= 13

    x = 182
    y = _draw_section_header(pdf, "SPECIAL INSTRUCTIONS", x, barcode_bottom - 16, 220)
    discount = float(order.discount_amount or 0)
    offer_text = "SPECIAL OFFER" if discount > 0 else "STANDARD DELIVERY"
    if delivery_values:
        offer_text = f"{offer_text} · {_truncate(delivery_values[0], 18)}"
    pdf.setFillColor(HexColor("#fff0d8"))
    pdf.setStrokeColor(ORANGE)
    pdf.roundRect(x, y - 18, 205, 22, 4, fill=1, stroke=1)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawCentredString(x + 102, y - 10, _truncate(offer_text, 38).upper())
    y -= 31

    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawString(x, y, "ITEM BARCODES")
    y -= 12
    for index, (item, context) in enumerate(zip(items, contexts), start=1):
        item_code = f"{package_code}-P{index:02d}"
        pdf.setFont("Helvetica", 6.8)
        pdf.drawString(x, y, _truncate(f"{item.quantity} × {context['name']}", 35))
        _draw_barcode(pdf, item_code, x, y - 16, 100, 13, bar_width=0.45, human=False)
        pdf.setFont("Helvetica", 6.4)
        pdf.drawString(x + 106, y - 11, item_code)
        y -= 27

    collection_label = (
        "COD / WHATSAPP ORDER" if order.payment_method in ("COD", "WHATSAPP") else "PREPAID ORDER"
    )
    payment_label = "PAID" if str(order.payment_status).strip().lower() == "paid" else "UNPAID"
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawCentredString(x + 66, lower_bottom + 31, collection_label)
    pdf.drawCentredString(x + 66, lower_bottom + 19, f"PAYMENT: {payment_label}")
    if order.payment_method in ("COD", "WHATSAPP") and order.payment_status != "Paid":
        amount = f"AED {order.total_amount:,.2f}"
    else:
        amount = "PAID"
    pdf.setFillColor(HexColor("#ffb34d"))
    pdf.setStrokeColor(INK)
    pdf.roundRect(x + 145, lower_bottom + 10, 75, 27, 6, fill=1, stroke=1)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(x + 182.5, lower_bottom + 20, amount)

    pdf.showPage()
    pdf.save()
    return stream.getvalue()

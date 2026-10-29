"""Backend-generated tax invoice PDFs for paid EEHOOK orders."""

from decimal import Decimal, ROUND_HALF_UP
from html import escape
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.utils.timezone import localtime
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import portrait
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from .sku import resolve_order_item_sku


VAT_RATE = Decimal("0.05")
PAGE_WIDTH, BASE_PAGE_HEIGHT = portrait((216 * mm, 303 * mm))
INK = HexColor("#111111")
MUTED = HexColor("#424242")
ORANGE = HexColor("#ff9000")
SLATE = HexColor("#4f6973")
LIGHT_ORANGE = HexColor("#fff4e5")
TABLE_LINE = HexColor("#222222")
EEHOOK_LOGO_PATH = Path(__file__).with_name("assets") / "eehook-package-logo.png"
MARGIN = 48
CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2


def _clean(value, fallback="-"):
    text = "" if value is None else str(value).strip()
    if not text:
        return fallback
    return text.encode("cp1252", "replace").decode("cp1252")


def _money(value):
    return Decimal(str(value or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _money_text(value):
    return f"{_money(value):,.2f}"


def _invoice_number(order):
    return f"INV-EHK26-{order.pk:04d}"


def _order_number(order):
    return f"EHK26/{order.pk:04d}"


def _full_name(order):
    address = getattr(order, "address", None)
    address_name = getattr(address, "full_name", None) if address else None
    user = getattr(order, "user", None)
    user_name = " ".join(
        part for part in (getattr(user, "first_name", ""), getattr(user, "last_name", "")) if part
    )
    return _clean(address_name or user_name or getattr(user, "email", None), "Customer")


def _address_lines(address):
    if not address:
        return ["-"]
    lines = [
        getattr(address, "address_line", None),
        ", ".join(
            part
            for part in (
                getattr(address, "city", None),
                getattr(address, "emirate", None),
                getattr(address, "postal_code", None),
            )
            if part
        ),
        getattr(address, "country", None),
    ]
    return [_clean(line) for line in lines if line]


def _draw_logo(pdf, x, y, scale=1):
    if EEHOOK_LOGO_PATH.is_file():
        image = ImageReader(str(EEHOOK_LOGO_PATH))
        image_width, image_height = image.getSize()
        # The supplied logo is placed on a white canvas. Crop that whitespace
        # at render time so the invoice gets the actual mark, not a tiny logo
        # surrounded by the source image margins.
        crop_left, crop_top, crop_right, crop_bottom = 28, 36, 250, 125
        crop_width = crop_right - crop_left
        crop_height = crop_bottom - crop_top
        box_width = 78 * scale
        box_height = 70 * scale
        crop_scale = min(box_width / crop_width, box_height / crop_height)
        draw_width = image_width * crop_scale
        draw_height = image_height * crop_scale
        crop_draw_width = crop_width * crop_scale
        crop_draw_height = crop_height * crop_scale
        draw_x = x + (box_width - crop_draw_width) / 2 - crop_left * crop_scale
        draw_y = y + (box_height - crop_draw_height) / 2 - (image_height - crop_bottom) * crop_scale

        pdf.saveState()
        clip = pdf.beginPath()
        clip.rect(x, y, box_width, box_height)
        pdf.clipPath(clip, stroke=0, fill=0)
        pdf.drawImage(
            image,
            draw_x,
            draw_y,
            width=draw_width,
            height=draw_height,
            preserveAspectRatio=False,
            mask="auto",
        )
        pdf.restoreState()
        return

    # Keep the vector fallback for older deployments where the bundled asset
    # has not been installed yet.
    pdf.saveState()
    pdf.setFillColor(ORANGE)
    pdf.rect(x + 27 * scale, y + 47 * scale, 25 * scale, 25 * scale, fill=1, stroke=0)
    pdf.rect(x + 15 * scale, y + 55 * scale, 17 * scale, 7 * scale, fill=1, stroke=0)
    pdf.rect(x + 15 * scale, y + 42 * scale, 17 * scale, 7 * scale, fill=1, stroke=0)
    pdf.setFillColor(SLATE)
    pdf.setFont("Helvetica-Bold", 19 * scale)
    pdf.drawString(x + 3 * scale, y + 22 * scale, "eehook")
    pdf.setFillColor(ORANGE)
    pdf.setFont("Helvetica-Oblique", 6 * scale)
    pdf.drawRightString(x + 73 * scale, y + 13 * scale, "Seriously Different")
    pdf.restoreState()


def _draw_label_value(pdf, label, value, x, y, value_x, font_size=8.5):
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", font_size)
    pdf.drawString(x, y, f"{_clean(label)}:")
    pdf.setFont("Helvetica", font_size)
    pdf.drawString(value_x, y, _clean(value))


def _draw_block(pdf, title, lines, x, y, width, title_size=9.5, line_size=8.5, line_gap=12):
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", title_size)
    pdf.drawString(x, y, _clean(title))
    y -= 17
    pdf.setFont("Helvetica", line_size)
    for line in lines:
        pdf.drawString(x, y, _clean(line))
        y -= line_gap
    return y


def _item_sku(item):
    return _clean(resolve_order_item_sku(item), "-")


def _item_description(item):
    product_name = escape(_clean(getattr(item.product, "name", None), "Product"))
    details = []
    if item.color:
        details.append(_clean(item.color.name))
    unit = getattr(item, "unit", None)
    variant_unit = getattr(item, "variant_unit", None)
    if variant_unit:
        unit = variant_unit.unit or unit
        unit_type = variant_unit.unit_type or getattr(unit, "unit_type", None)
    else:
        unit_type = getattr(unit, "unit_type", None) if unit else None
    if unit:
        unit_text = _clean(unit.name)
        if unit_type:
            unit_text = f"{_clean(unit_type.name)}: {unit_text}"
        details.append(unit_text)
    grade = _clean(getattr(variant_unit, "grade", None), "") if variant_unit else ""
    if grade:
        details.append(f"Grade: {grade}")
    return product_name if not details else f"{product_name}<br/>{escape(' | '.join(details))}"


def _invoice_lines(order):
    rows = []
    for index, item in enumerate(order.items.all(), start=1):
        quantity = int(item.quantity or 1)
        gross_unit = _money(item.price)
        gross_total = _money(item.total_price or gross_unit * quantity)
        rows.append(
            {
                "item_number": f"{index:06d}",
                "sku": _item_sku(item),
                "description": _item_description(item),
                "quantity": quantity,
                "gross_unit": gross_unit,
                "gross_total": gross_total,
                "taxable": True,
            }
        )

    shipping = _money(order.shipping_charge)
    if shipping:
        rows.append(
            {
                "item_number": "",
                "sku": "SHIP",
                "description": "Delivery / Shipping",
                "quantity": 1,
                "gross_unit": shipping,
                "gross_total": shipping,
                "taxable": False,
            }
        )

    if not rows:
        rows.append(
            {
                "item_number": "",
                "sku": "ORDER",
                "description": "Order total",
                "quantity": 1,
                "gross_unit": _money(order.total_amount),
                "gross_total": _money(order.total_amount),
                "taxable": True,
            }
        )

    taxable_rows = [row for row in rows if row["taxable"]]
    taxable_gross = sum((row["gross_total"] for row in taxable_rows), Decimal("0.00"))
    total_net = _money(taxable_gross / (Decimal("1") + VAT_RATE))
    running_net = Decimal("0.00")
    last_taxable = taxable_rows[-1] if taxable_rows else None
    for row in rows:
        if row["taxable"]:
            if row is last_taxable:
                row["net_total"] = _money(total_net - running_net)
            else:
                row["net_total"] = _money(
                    row["gross_total"] / (Decimal("1") + VAT_RATE)
                )
            row["vat"] = row["gross_total"] - row["net_total"]
            running_net += row["net_total"]
            row["tax_rate"] = "5.00"
        else:
            row["net_total"] = row["gross_total"]
            row["vat"] = Decimal("0.00")
            row["tax_rate"] = "0.00"
        row["net_unit"] = _money(row["net_total"] / max(row["quantity"], 1))
    return rows


def _paragraph(text, style):
    return Paragraph(text, style)


def _build_table(pdf, order, table_top, rows=None):
    rows = _invoice_lines(order) if rows is None else rows
    body_style = ParagraphStyle(
        "InvoiceBody",
        fontName="Helvetica",
        fontSize=6.7,
        leading=8.2,
        textColor=INK,
        alignment=TA_LEFT,
    )
    header_style = ParagraphStyle(
        "InvoiceHeader",
        fontName="Helvetica-Bold",
        fontSize=6.5,
        leading=7.2,
        textColor=INK,
        alignment=TA_CENTER,
    )
    right_style = ParagraphStyle(
        "InvoiceRight",
        parent=body_style,
        alignment=TA_RIGHT,
    )
    center_style = ParagraphStyle(
        "InvoiceCenter",
        parent=body_style,
        alignment=TA_CENTER,
    )
    headers = [
        "Item<br/>Number",
        "SKU",
        "Product Description",
        "Quantity<br/>Shipped",
        "Value Per Unit<br/>(Excl.VAT)",
        "Extended Value<br/>(Excl.VAT)",
        "Tax<br/>Rate %",
        "VAT<br/>Amount",
    ]
    data = [[_paragraph(header, header_style) for header in headers]]
    for row in rows:
        data.append(
            [
                _paragraph(escape(row["item_number"]), center_style),
                _paragraph(escape(row["sku"]), body_style),
                _paragraph(row["description"], body_style),
                _paragraph(str(row["quantity"]), center_style),
                _paragraph(_money_text(row["net_unit"]), right_style),
                _paragraph(_money_text(row["net_total"]), right_style),
                _paragraph(row["tax_rate"], right_style),
                _paragraph(_money_text(row["vat"]), right_style),
            ]
        )
    table = Table(
        data,
        colWidths=[42, 62, 150, 45, 68, 73, 34, 42],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.8, TABLE_LINE),
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#fafafa")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    _, table_height = table.wrap(CONTENT_WIDTH, BASE_PAGE_HEIGHT)
    table.drawOn(pdf, MARGIN, table_top - table_height)
    return table_height


def _draw_summary(pdf, order, page_height, rows):
    x = 355
    y = 218
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawString(x, y, "VAT Basis")
    pdf.drawString(x + 58, y, "VAT Amount")
    pdf.drawString(x + 126, y, "VAT Rate")
    y -= 26
    gross_total = _money(order.total_amount)
    net_total = _money(
        sum((row["net_total"] for row in rows if row["taxable"]), Decimal("0.00"))
    )
    vat_total = _money(
        sum((row["vat"] for row in rows if row["taxable"]), Decimal("0.00"))
    )
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(x + 2, y, _money_text(net_total))
    pdf.drawString(x + 61, y, _money_text(vat_total))
    pdf.drawString(x + 132, y, "5.00 %")
    y -= 27
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(x, y, "Total Price (Incl.VAT)")
    pdf.drawRightString(PAGE_WIDTH - MARGIN, y, f"AED  {_money_text(gross_total)}")
    pdf.setStrokeColor(INK)
    pdf.setLineWidth(0.8)
    pdf.line(x, y + 16, PAGE_WIDTH - MARGIN, y + 16)

    left_x = MARGIN
    note_y = 232
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7.2)
    method = _clean(order.get_payment_method_display() if hasattr(order, "get_payment_method_display") else order.payment_method)
    pdf.drawString(left_x, note_y, f"This invoice amount has been paid by {method}")
    pdf.drawString(left_x, note_y - 19, "Thank you for shopping at the EEHOOK.")
    pdf.drawString(left_x, note_y - 42, "If you have any questions regarding this invoice or the goods")
    pdf.drawString(left_x, note_y - 53, "delivered, please contact our Customer Service Department.")
    pdf.drawString(left_x, note_y - 76, "Phone: +971 547369369   All Day ; 9:00 - 22:00")
    pdf.drawString(left_x, note_y - 87, "Web: www.eehook.com/support")


def _draw_social_icon(pdf, platform, x, y, size):
    """Draw a compact vector social icon without adding a font dependency."""

    pdf.saveState()
    pdf.setFillColor(HexColor("#202035"))
    pdf.circle(x + size / 2, y + size / 2, size / 2, fill=1, stroke=0)

    if platform == "instagram":
        pdf.setStrokeColor(white)
        pdf.setLineWidth(1.2)
        pdf.roundRect(x + 4, y + 4, size - 8, size - 8, 3, fill=0, stroke=1)
        pdf.circle(x + size / 2, y + size / 2, size * 0.15, fill=0, stroke=1)
        pdf.setFillColor(white)
        pdf.circle(x + size - 5, y + size - 5, 1, fill=1, stroke=0)
    elif platform == "facebook":
        pdf.setFillColor(white)
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawCentredString(x + size / 2, y + 3, "f")
    elif platform == "tiktok":
        pdf.setStrokeColor(white)
        pdf.setFillColor(white)
        pdf.setLineWidth(1.4)
        pdf.line(x + size * 0.58, y + size * 0.72, x + size * 0.58, y + size * 0.34)
        pdf.line(x + size * 0.58, y + size * 0.72, x + size * 0.80, y + size * 0.65)
        pdf.circle(x + size * 0.42, y + size * 0.28, size * 0.13, fill=1, stroke=0)
    elif platform == "youtube":
        pdf.setFillColor(HexColor("#ff0000"))
        pdf.roundRect(x + 2, y + 5, size - 4, size - 10, 3, fill=1, stroke=0)
        triangle = pdf.beginPath()
        triangle.moveTo(x + size * 0.43, y + size * 0.34)
        triangle.lineTo(x + size * 0.43, y + size * 0.66)
        triangle.lineTo(x + size * 0.70, y + size * 0.50)
        triangle.close()
        pdf.setFillColor(white)
        pdf.drawPath(triangle, fill=1, stroke=0)
    elif platform == "x":
        pdf.setStrokeColor(white)
        pdf.setLineWidth(1.5)
        pdf.line(x + 5, y + 5, x + size - 5, y + size - 5)
        pdf.line(x + size - 5, y + 5, x + 5, y + size - 5)
    elif platform == "snapchat":
        pdf.setFillColor(HexColor("#fffc00"))
        pdf.circle(x + size / 2, y + size / 2, size * 0.31, fill=1, stroke=0)
        pdf.setFillColor(HexColor("#111111"))
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawCentredString(x + size / 2, y + 4.5, "S")

    pdf.restoreState()


def _draw_footer(pdf, page_height):
    y = 56
    center = PAGE_WIDTH / 2
    icon_size = 18
    gap = 8
    social_links = (
        ("instagram", "https://www.instagram.com/eehook.ae"),
        ("facebook", "https://www.facebook.com/eehookonline/"),
        ("tiktok", "https://www.tiktok.com/@eehook.com"),
        ("youtube", "https://www.youtube.com/@eehook9631"),
        ("x", "https://x.com/eehookonline"),
        ("snapchat", "https://www.snapchat.com/add/eehook.com"),
    )
    total_width = len(social_links) * icon_size + (len(social_links) - 1) * gap
    start_x = center - total_width / 2
    for index, (platform, url) in enumerate(social_links):
        x = start_x + index * (icon_size + gap)
        _draw_social_icon(pdf, platform, x, y, icon_size)
        pdf.linkURL(url, (x, y, x + icon_size, y + icon_size), relative=0, thickness=0)

    pdf.setFillColor(HexColor("#303047"))
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(center, y - 22, "Follow our social media @eehook")


def render_tax_invoice(order):
    """Return a portrait tax invoice PDF for a paid order."""

    rows = _invoice_lines(order)
    probe = BytesIO()
    probe_pdf = canvas.Canvas(probe, pagesize=(PAGE_WIDTH, BASE_PAGE_HEIGHT))
    probe_table_height = _build_table(
        probe_pdf, order, BASE_PAGE_HEIGHT - 360, rows=rows
    )
    probe_pdf.save()
    page_height = max(BASE_PAGE_HEIGHT, 700 + probe_table_height)

    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(PAGE_WIDTH, page_height))
    top = page_height - MARGIN
    pdf.setFillColor(white)
    pdf.rect(0, 0, PAGE_WIDTH, page_height, fill=1, stroke=0)

    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(MARGIN, top - 18, "Tax Invoice")
    seller_name = getattr(settings, "INVOICE_SELLER_NAME", "DEXON Advertising LLC")
    seller_lines = [
        seller_name,
        getattr(settings, "INVOICE_SELLER_ADDRESS", "S09 Beirut St"),
        getattr(settings, "INVOICE_SELLER_CITY", "Al Qusais Ind 5 Dubai"),
        getattr(settings, "INVOICE_SELLER_COUNTRY", "United Arab Emirates"),
        f"VAT No: {getattr(settings, 'INVOICE_SELLER_VAT_NUMBER', '104131003600003')}",
    ]
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawString(MARGIN, top - 41, _clean(seller_lines[0]))
    pdf.setFont("Helvetica", 8.5)
    for index, line in enumerate(seller_lines[1:], start=1):
        pdf.drawString(MARGIN, top - 41 - index * 14, _clean(line))
    _draw_logo(pdf, PAGE_WIDTH - MARGIN - 92, top - 93, scale=1.18)

    invoice_date = localtime(order.created_at).strftime("%d.%m.%Y") if order.created_at else "-"
    left_y = top - 177
    _draw_label_value(pdf, "Tax Invoice Number", _invoice_number(order), MARGIN, left_y, MARGIN + 125)
    _draw_label_value(pdf, "EEHOOK Order Number", _order_number(order), MARGIN, left_y - 17, MARGIN + 125)
    _draw_label_value(pdf, "Invoice Date", invoice_date, MARGIN, left_y - 34, MARGIN + 125)
    _draw_label_value(pdf, "Due Date", invoice_date, MARGIN, left_y - 51, MARGIN + 125)

    address = getattr(order, "address", None)
    customer_lines = [_full_name(order), *_address_lines(address)]
    bill_x = 350
    _draw_block(pdf, "Bill to", customer_lines, bill_x, top - 155, 200)
    _draw_block(pdf, "Ship to", customer_lines, bill_x, top - 250, 200)

    payment_method = order.get_payment_method_display() if hasattr(order, "get_payment_method_display") else order.payment_method
    payment_y = top - 285
    _draw_label_value(pdf, "Payment Method", payment_method, MARGIN, payment_y, MARGIN + 87)
    _draw_label_value(pdf, "Date Ordered", invoice_date, MARGIN, payment_y - 17, MARGIN + 87)
    _draw_label_value(pdf, "Payment Status", _clean(order.payment_status), MARGIN, payment_y - 34, MARGIN + 87)

    table_top = page_height - 405
    _build_table(pdf, order, table_top, rows=rows)
    _draw_summary(pdf, order, page_height, rows)
    _draw_footer(pdf, page_height)
    pdf.showPage()
    pdf.save()
    return stream.getvalue()

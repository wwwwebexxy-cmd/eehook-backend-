from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from .invoice import _invoice_lines, render_tax_invoice
from .models import Address, Category, Order, OrderItem, Product, ProductVariant, SubCategory, User
from .package_label import _item_context


class TaxInvoiceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            email="invoice-customer@example.invalid",
            password="CustomerPass123!",
            first_name="Sadiqe",
            last_name="Hassan",
        )
        self.admin = User.objects.create_superuser(
            email="invoice-admin@example.invalid",
            password="SuperAdminPass123!",
        )
        category = Category.objects.create(name="Invoice Category")
        subcategory = SubCategory.objects.create(category=category, name="Invoice Subcategory")
        product = Product.objects.create(
            category=category,
            subcategory=subcategory,
            name="Invoice Test Product",
            description="Invoice test product",
        )
        variant = ProductVariant.objects.create(
            product=product,
            sku="INV-TEST-001",
            price_type="single",
            price="105.00",
            stock=5,
        )
        address = Address.objects.create(
            user=self.customer,
            full_name="Sadiqe Hassan",
            phone="0547369369",
            address_line="Deira",
            city="Dubai",
            postal_code="00000",
            country="United Arab Emirates",
        )
        self.order = Order.objects.create(
            user=self.customer,
            address=address,
            subtotal="105.00",
            discount_amount="0.00",
            shipping_charge="10.00",
            total_amount="115.00",
            payment_status="Paid",
            payment_method="Cashfree",
            status="Processing",
        )
        OrderItem.objects.create(
            order=self.order,
            product=product,
            quantity=1,
            original_price="105.00",
            price="105.00",
            total_price="105.00",
        )

    def test_delivery_charge_is_not_taxable(self):
        rows = _invoice_lines(self.order)
        product_row = next(row for row in rows if row["sku"] == "INV-TEST-001")
        delivery_row = next(row for row in rows if row["sku"] == "SHIP")

        self.assertEqual(product_row["tax_rate"], "5.00")
        self.assertEqual(product_row["vat"], Decimal("5.00"))
        self.assertEqual(delivery_row["tax_rate"], "0.00")
        self.assertEqual(delivery_row["vat"], Decimal("0.00"))
        self.assertEqual(delivery_row["net_total"], Decimal("10.00"))

    def test_package_label_context_includes_product_sku(self):
        item = self.order.items.first()
        self.assertEqual(_item_context(item)["sku"], "INV-TEST-001")

    def test_render_tax_invoice_uses_tax_inclusive_totals(self):
        pdf = render_tax_invoice(self.order)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1000)

    def test_customer_can_download_paid_invoice_but_not_unpaid_invoice(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.get(f"/my-orders/{self.order.id}/invoice/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("tax-invoice.pdf", response["Content-Disposition"])

        self.order.payment_status = "Pending"
        self.order.save(update_fields=("payment_status",))
        response = self.client.get(f"/my-orders/{self.order.id}/invoice/")
        self.assertEqual(response.status_code, 409)

    def test_admin_can_download_paid_invoice(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f"/orders/{self.order.id}/invoice/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

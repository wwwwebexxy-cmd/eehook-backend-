import base64
import hashlib
import hmac
import json
import logging
import secrets
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from myapp.models import (
    Address,
    Cart,
    Order,
    OrderItem,
    ProductVariant,
    ProductVariantUnit,
    SavedCoupon,
    SavedWelcomeBonus,
    WelcomeBonusAssignment,
)
from myapp.utils import (
    PaymentRateThrottle,
    calculate_coupon_price,
    calculate_offer_price,
    calculate_order_total,
    get_eligible_coupon,
)
from myapp.welcome_bonus import (
    calculate_welcome_bonus_price,
    get_eligible_welcome_bonus_assignment,
    redeem_welcome_bonus_assignment,
)
from myapp.order_notifications import send_order_notifications

from .cashfree_services import CashfreeAPIError, CashfreeService
from .models import CashfreeCheckout


logger = logging.getLogger(__name__)


class CheckoutFulfillmentError(ValueError):
    """The payment succeeded, but the order snapshot cannot be fulfilled."""


def _money(value):
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def _cashfree_currency():
    currency = str(getattr(settings, "CASHFREE_ORDER_CURRENCY", "AED") or "AED").upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("CASHFREE_ORDER_CURRENCY must be a three-letter currency code.")
    return currency


def _phone_for_cashfree(address):
    raw_phone = str(address.phone or "")
    digits = "".join(character for character in raw_phone if character.isdigit())
    if len(digits) < 8:
        return ""
    return digits[-15:]


def _customer_name(user, address):
    return (
        str(address.full_name or "").strip()
        or str(user.get_full_name() or "").strip()
        or str(user.email).split("@", 1)[0]
    )[:100]


def _snapshot_from_cart(user):
    cart_items = list(
        Cart.objects.filter(user=user).select_related(
            "variant",
            "variant__product",
            "variant__product__offer",
            "variant__color",
            "variant_unit",
            "variant_unit__unit",
            "welcome_bonus_assignment",
        )
    )
    if not cart_items:
        raise ValueError("Cart is empty")

    original_subtotal = Decimal("0.00")
    discount_total = Decimal("0.00")
    discounted_subtotal = Decimal("0.00")
    products = []

    for item in cart_items:
        if item.variant.price_type == "multiple":
            if not item.variant_unit:
                raise ValueError(f"{item.variant.product.name} has no selectable unit.")
            available_stock = item.variant_unit.stock
            original_price = Decimal(str(item.variant_unit.price))
        else:
            available_stock = item.variant.stock
            original_price = Decimal(str(item.variant.price or 0))

        if item.quantity > available_stock:
            raise ValueError(
                f"{item.variant.product.name} has only {available_stock} item(s) left."
            )

        discounted_price = calculate_offer_price(
            original_price,
            item.variant.product.offer,
        )
        welcome_bonus_assignment_id = item.welcome_bonus_assignment_id
        welcome_bonus_assignment = get_eligible_welcome_bonus_assignment(
            welcome_bonus_assignment_id,
            user,
            item.variant.product,
        )
        coupon_id = item.coupon_id
        coupon = None

        if welcome_bonus_assignment:
            discounted_price = calculate_welcome_bonus_price(
                discounted_price,
                welcome_bonus_assignment,
            )
        elif welcome_bonus_assignment_id:
            Cart.objects.filter(
                pk=item.pk,
                welcome_bonus_assignment_id=welcome_bonus_assignment_id,
            ).update(welcome_bonus_assignment=None)
            SavedWelcomeBonus.objects.filter(
                user=user,
                product=item.variant.product,
                assignment_id=welcome_bonus_assignment_id,
            ).delete()
            item.welcome_bonus_assignment = None
        else:
            coupon = get_eligible_coupon(coupon_id, item.variant.product)

        if coupon:
            discounted_price = calculate_coupon_price(discounted_price, coupon)
        elif coupon_id and not welcome_bonus_assignment:
            Cart.objects.filter(pk=item.pk, coupon_id=coupon_id).update(coupon=None)
            SavedCoupon.objects.filter(
                user=user,
                product=item.variant.product,
                coupon_id=coupon_id,
            ).delete()
            item.coupon = None

        discount_amount = original_price - discounted_price
        original_subtotal += original_price * item.quantity
        discount_total += discount_amount * item.quantity
        discounted_subtotal += discounted_price * item.quantity

        products.append(
            {
                "variant_id": item.variant_id,
                "variant_unit_id": item.variant_unit_id,
                "coupon_id": coupon.id if coupon else None,
                "welcome_bonus_assignment_id": (
                    welcome_bonus_assignment.id if welcome_bonus_assignment else None
                ),
                "quantity": item.quantity,
                "original_price": str(_money(original_price)),
                "discount_amount": str(_money(discount_amount)),
                "price": str(_money(discounted_price)),
            }
        )

    totals = calculate_order_total(discounted_subtotal)
    return {
        "products": products,
        "original_subtotal": str(_money(original_subtotal)),
        "discount_total": str(_money(discount_total)),
        "discounted_subtotal": str(_money(discounted_subtotal)),
        "shipping_charge": str(_money(totals["shipping"])),
        "total": str(_money(totals["total"])),
    }


def _checkout_response(checkout):
    return Response(
        {
            "payment_session_id": checkout.payment_session_id,
            "cashfree_order_id": checkout.cashfree_order_id,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([PaymentRateThrottle])
def create_cashfree_order(request):
    if not getattr(settings, "CASHFREE_ENABLED", False):
        return Response(
            {"message": "Online payments are temporarily unavailable."},
            status=status.HTTP_410_GONE,
        )

    address_id = request.data.get("address")
    if not address_id:
        return Response({"message": "Address is required"}, status=status.HTTP_400_BAD_REQUEST)

    address = Address.objects.filter(id=address_id, user=request.user).first()
    if not address:
        return Response({"message": "Address not found"}, status=status.HTTP_404_NOT_FOUND)

    phone = _phone_for_cashfree(address)
    if not phone:
        return Response(
            {"message": "A valid phone number is required for Cashfree payment."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    idempotency_key = request.META.get("HTTP_IDEMPOTENCY_KEY", "").strip()[:255] or None
    if idempotency_key:
        previous = CashfreeCheckout.objects.filter(
            user=request.user,
            idempotency_key=idempotency_key,
        ).first()
        if previous and previous.payment_session_id:
            return _checkout_response(previous)
        if previous:
            return Response(
                {"message": "This payment attempt is still being prepared."},
                status=status.HTTP_409_CONFLICT,
            )

    try:
        currency = _cashfree_currency()
        snapshot = _snapshot_from_cart(request.user)
        amount = _money(snapshot["total"])
        if amount <= 0:
            raise ValueError("The order total must be greater than zero.")
    except ValueError as error:
        return Response({"message": str(error)}, status=status.HTTP_400_BAD_REQUEST)

    cashfree_order_id = f"eehook-{request.user.id}-{secrets.token_hex(16)}"
    notify_url = str(
        getattr(settings, "CASHFREE_WEBHOOK_URL", "")
        or f"{settings.SITE_URL}/backend/payment/cashfree-webhook/"
    ).rstrip("/") + "/"
    return_url = f"{settings.SITE_URL}/payment-success?order_id={cashfree_order_id}"

    checkout = CashfreeCheckout.objects.create(
        user=request.user,
        address=address,
        cashfree_order_id=cashfree_order_id,
        idempotency_key=idempotency_key,
        amount=amount,
        currency=currency,
        snapshot=snapshot,
        status="Created",
    )

    try:
        cashfree_order = CashfreeService.create_order(
            order_id=cashfree_order_id,
            amount=amount,
            currency=currency,
            customer_details={
                "customer_id": str(request.user.id),
                "customer_name": _customer_name(request.user, address),
                "customer_email": request.user.email,
                "customer_phone": phone,
            },
            return_url=return_url,
            notify_url=notify_url,
            idempotency_key=idempotency_key or cashfree_order_id,
        )
        payment_session_id = str(cashfree_order.get("payment_session_id") or "").strip()
        if not payment_session_id:
            raise CashfreeAPIError("Cashfree did not return a payment session.")
    except CashfreeAPIError as error:
        checkout.status = "Failed"
        checkout.save(update_fields=("status", "updated_at"))
        logger.exception(
            "Cashfree order creation failed",
            extra={"user_id": request.user.id, "cashfree_status": error.status_code},
        )
        return Response(
            {"message": "Unable to start payment. Please try again later."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    checkout.payment_session_id = payment_session_id
    checkout.status = "Active"
    checkout.save(update_fields=("payment_session_id", "status", "updated_at"))
    return _checkout_response(checkout)


def _cashfree_amount_is_valid(checkout, cashfree_order):
    try:
        provider_amount = _money(cashfree_order.get("order_amount"))
    except (InvalidOperation, TypeError):
        return False
    provider_currency = str(cashfree_order.get("order_currency") or "").upper()
    return provider_amount == _money(checkout.amount) and provider_currency == checkout.currency


def _get_verified_paid_cashfree_order(checkout):
    try:
        cashfree_order = CashfreeService.get_order(checkout.cashfree_order_id)
    except CashfreeAPIError:
        logger.exception(
            "Cashfree order verification failed",
            extra={"cashfree_order_id": checkout.cashfree_order_id},
        )
        raise

    provider_status = str(cashfree_order.get("order_status") or "").upper()
    if provider_status != "PAID":
        if provider_status in {"EXPIRED", "TERMINATED", "TERMINATION_REQUESTED"}:
            checkout.status = "Expired" if provider_status == "EXPIRED" else "Terminated"
        else:
            checkout.status = "Active"
        checkout.save(update_fields=("status", "updated_at"))
        return None

    if not _cashfree_amount_is_valid(checkout, cashfree_order):
        raise CheckoutFulfillmentError("Cashfree payment amount or currency does not match the order.")
    return cashfree_order


def _snapshot_decimal(snapshot, key):
    return _money(snapshot.get(key, "0.00"))


@transaction.atomic
def fulfill_cashfree_checkout(checkout):
    checkout = (
        CashfreeCheckout.objects.select_for_update()
        .select_related("address")
        .get(pk=checkout.pk)
    )
    if checkout.order_id:
        checkout.status = "Fulfilled"
        checkout.save(update_fields=("status", "updated_at"))
        return checkout.order

    snapshot = checkout.snapshot or {}
    product_snapshots = snapshot.get("products") or []
    if not product_snapshots:
        raise CheckoutFulfillmentError("No products found in the payment snapshot.")

    expected_total = _snapshot_decimal(snapshot, "total")
    if expected_total != _money(checkout.amount):
        raise CheckoutFulfillmentError("Payment amount does not match the order total.")

    address = Address.objects.filter(id=checkout.address_id, user_id=checkout.user_id).first()
    if not address:
        raise CheckoutFulfillmentError("Delivery address not found.")

    variant_unit_ids = [
        item["variant_unit_id"]
        for item in product_snapshots
        if item.get("variant_unit_id") is not None
    ]
    variant_ids = [
        item["variant_id"]
        for item in product_snapshots
        if item.get("variant_unit_id") is None and item.get("variant_id") is not None
    ]

    locked_units = {
        variant_unit.id: variant_unit
        for variant_unit in ProductVariantUnit.objects.select_for_update()
        .select_related("variant", "variant__product", "variant__color", "unit")
        .filter(id__in=variant_unit_ids)
    }
    locked_variants = {
        variant.id: variant
        for variant in ProductVariant.objects.select_for_update()
        .select_related("product", "color")
        .filter(id__in=variant_ids)
    }

    welcome_bonus_ids = {
        item.get("welcome_bonus_assignment_id")
        for item in product_snapshots
        if item.get("welcome_bonus_assignment_id")
    }
    locked_welcome_bonuses = {
        assignment.id: assignment
        for assignment in WelcomeBonusAssignment.objects.select_for_update()
        .select_related("welcome_bonus", "user")
        .prefetch_related("welcome_bonus__products")
        .filter(id__in=welcome_bonus_ids)
    }

    for item in product_snapshots:
        variant_unit = locked_units.get(item.get("variant_unit_id"))
        variant = locked_variants.get(item.get("variant_id"))
        if not variant_unit and not variant:
            raise CheckoutFulfillmentError("Product variant not found.")
        stock_record = variant_unit or variant
        product_name = (
            variant_unit.variant.product.name if variant_unit else variant.product.name
        )
        if stock_record.stock < int(item.get("quantity") or 0):
            raise CheckoutFulfillmentError(f"Insufficient stock for {product_name}.")

    for item in product_snapshots:
        coupon_id = item.get("coupon_id")
        if not coupon_id:
            continue
        variant_unit = locked_units.get(item.get("variant_unit_id"))
        variant = locked_variants.get(item.get("variant_id"))
        selected_variant = variant_unit.variant if variant_unit else variant
        if not get_eligible_coupon(coupon_id, selected_variant.product):
            raise CheckoutFulfillmentError("Coupon is no longer active.")

    welcome_bonus_amounts = {}
    for item in product_snapshots:
        assignment_id = item.get("welcome_bonus_assignment_id")
        if not assignment_id:
            continue
        assignment = locked_welcome_bonuses.get(assignment_id)
        variant_unit = locked_units.get(item.get("variant_unit_id"))
        variant = locked_variants.get(item.get("variant_id"))
        selected_variant = variant_unit.variant if variant_unit else variant
        if not assignment or assignment.user_id != checkout.user_id:
            raise CheckoutFulfillmentError("Welcome bonus is no longer available.")
        assignment = get_eligible_welcome_bonus_assignment(
            assignment,
            assignment.user,
            selected_variant.product,
        )
        if not assignment:
            raise CheckoutFulfillmentError("Welcome bonus is no longer active.")
        current_original_price = variant_unit.price if variant_unit else selected_variant.price
        current_offer_price = calculate_offer_price(
            current_original_price,
            selected_variant.product.offer,
        )
        current_discounted_price = calculate_welcome_bonus_price(
            current_offer_price,
            assignment,
        )
        if (
            _money(current_discounted_price) != _snapshot_decimal(item, "price")
            or _money(current_original_price) != _snapshot_decimal(item, "original_price")
        ):
            raise CheckoutFulfillmentError("Welcome bonus price changed.")
        welcome_bonus_amounts[assignment.id] = (
            welcome_bonus_amounts.get(assignment.id, Decimal("0.00"))
            + (current_offer_price - current_discounted_price) * int(item["quantity"])
        )

    order = Order.objects.create(
        user_id=checkout.user_id,
        address=address,
        subtotal=_snapshot_decimal(snapshot, "original_subtotal"),
        discount_amount=_snapshot_decimal(snapshot, "discount_total"),
        shipping_charge=_snapshot_decimal(snapshot, "shipping_charge"),
        total_amount=expected_total,
        payment_status="Paid",
        payment_method="Cashfree",
        status="Processing",
    )

    for item in product_snapshots:
        variant_unit = locked_units.get(item.get("variant_unit_id"))
        variant = locked_variants.get(item.get("variant_id"))
        selected_variant = variant_unit.variant if variant_unit else variant
        quantity = int(item["quantity"])
        OrderItem.objects.create(
            order=order,
            product=selected_variant.product,
            color=selected_variant.color,
            unit=variant_unit.unit if variant_unit else None,
            variant_unit=variant_unit,
            quantity=quantity,
            original_price=_snapshot_decimal(item, "original_price"),
            discount_amount=_snapshot_decimal(item, "discount_amount"),
            price=_snapshot_decimal(item, "price"),
            total_price=_snapshot_decimal(item, "price") * quantity,
        )

    for item in product_snapshots:
        variant_unit = locked_units.get(item.get("variant_unit_id"))
        variant = locked_variants.get(item.get("variant_id"))
        stock_record = variant_unit or variant
        stock_record.stock -= int(item["quantity"])
        stock_record.save(update_fields=("stock",))

    for assignment_id, applied_amount in welcome_bonus_amounts.items():
        assignment = locked_welcome_bonuses.get(assignment_id)
        if assignment:
            redeem_welcome_bonus_assignment(assignment, order, applied_amount)

    for item in product_snapshots:
        cart_filter = {"user_id": checkout.user_id}
        if item.get("variant_unit_id") is not None:
            cart_filter["variant_unit_id"] = item["variant_unit_id"]
        else:
            cart_filter["variant_id"] = item["variant_id"]
            cart_filter["variant_unit__isnull"] = True
        Cart.objects.filter(**cart_filter).delete()

    checkout.order = order
    checkout.status = "Fulfilled"
    checkout.save(update_fields=("order", "status", "updated_at"))
    transaction.on_commit(lambda order_id=order.id: send_order_notifications(order_id))
    return order


def _success_response(order):
    return Response({"message": "Payment successful", "order_id": order.id})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def cashfree_payment_success(request):
    cashfree_order_id = str(request.GET.get("order_id") or "").strip()
    if not cashfree_order_id:
        return Response(
            {"message": "Cashfree order ID is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    checkout = CashfreeCheckout.objects.filter(cashfree_order_id=cashfree_order_id).first()
    if not checkout:
        return Response({"message": "Invalid payment order."}, status=status.HTTP_400_BAD_REQUEST)
    if checkout.user_id != request.user.id:
        return Response(
            {"message": "Unauthorized payment order."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if checkout.order_id:
        return _success_response(checkout.order)

    try:
        cashfree_order = _get_verified_paid_cashfree_order(checkout)
        if not cashfree_order:
            return Response(
                {
                    "message": "Payment has not been completed.",
                    "payment_status": checkout.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        order = fulfill_cashfree_checkout(checkout)
    except CheckoutFulfillmentError as error:
        checkout.status = "Fulfillment Error"
        checkout.save(update_fields=("status", "updated_at"))
        logger.exception(
            "Cashfree payment succeeded but order fulfilment failed",
            extra={"cashfree_order_id": checkout.cashfree_order_id},
        )
        return Response({"message": str(error)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except CashfreeAPIError:
        return Response(
            {"message": "Payment verification is temporarily unavailable."},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except Exception:
        logger.exception(
            "Unexpected Cashfree order fulfilment failure",
            extra={"cashfree_order_id": checkout.cashfree_order_id},
        )
        return Response(
            {"message": "Payment was received but order processing failed. Please contact support."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return _success_response(order)


def _webhook_order_id(event):
    data = event.get("data") or {}
    order = data.get("order") or {}
    return str(
        order.get("order_id")
        or data.get("order_id")
        or event.get("order_id")
        or ""
    ).strip()


def _webhook_is_success(event):
    data = event.get("data") or {}
    payment = data.get("payment") or {}
    event_type = str(event.get("type") or event.get("event_type") or "").upper()
    payment_status = str(payment.get("payment_status") or data.get("payment_status") or "").upper()
    order_status = str((data.get("order") or {}).get("order_status") or "").upper()
    return (
        event_type == "PAYMENT_SUCCESS_WEBHOOK"
        or payment_status == "SUCCESS"
        or order_status == "PAID"
    )


def _verify_webhook_signature(raw_body, signature, timestamp):
    secret = str(getattr(settings, "CASHFREE_CLIENT_SECRET", "") or "").strip()
    if not secret or not signature or not timestamp:
        return False
    signed_payload = f"{timestamp}{raw_body}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).digest()
    expected_signature = base64.b64encode(expected).decode("ascii")
    return hmac.compare_digest(expected_signature, str(signature))


@csrf_exempt
def cashfree_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)

    raw_body = request.body.decode("utf-8")
    signature = request.META.get("HTTP_X_WEBHOOK_SIGNATURE", "")
    timestamp = request.META.get("HTTP_X_WEBHOOK_TIMESTAMP", "")
    if not _verify_webhook_signature(raw_body, signature, timestamp):
        return HttpResponse(status=400)

    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    cashfree_order_id = _webhook_order_id(event)
    if not cashfree_order_id:
        return HttpResponse(status=400)

    checkout = CashfreeCheckout.objects.filter(cashfree_order_id=cashfree_order_id).first()
    if not checkout:
        logger.warning("Received Cashfree webhook for unknown order", extra={"cashfree_order_id": cashfree_order_id})
        return HttpResponse(status=200)

    if not _webhook_is_success(event):
        event_type = str(event.get("type") or event.get("event_type") or "").upper()
        if "FAILED" in event_type or "EXPIRED" in event_type or "CANCEL" in event_type:
            checkout.status = "Failed"
            checkout.save(update_fields=("status", "updated_at"))
        return HttpResponse(status=200)

    try:
        cashfree_order = _get_verified_paid_cashfree_order(checkout)
        if cashfree_order:
            fulfill_cashfree_checkout(checkout)
    except Exception:
        logger.exception(
            "Cashfree webhook fulfilment failed",
            extra={"cashfree_order_id": cashfree_order_id},
        )
        return HttpResponse(status=500)

    return HttpResponse(status=200)

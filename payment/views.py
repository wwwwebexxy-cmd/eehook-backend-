from decimal import Decimal

import stripe

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from urllib.parse import urlparse
import logging

from rest_framework.decorators import (
    api_view,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from myapp.models import (
    Cart,
    Address,
    AdminAuditLog,
    Order,
    OrderItem,
    ProductVariant,
    ProductVariantUnit,
    SavedCoupon,
    SavedWelcomeBonus,
    WelcomeBonusAssignment,
)
from myapp.whatsapp import send_owner_order_notification

from myapp.utils import (
    calculate_offer_price,
    calculate_order_total,
    calculate_coupon_price,
    get_eligible_coupon,
    PaymentRateThrottle,
)
from myapp.welcome_bonus import (
    calculate_welcome_bonus_price,
    get_eligible_welcome_bonus_assignment,
    redeem_welcome_bonus_assignment,
)

from .services import StripeService

logger = logging.getLogger(__name__)


stripe.api_key = settings.STRIPE_SECRET_KEY


# =========================================================
# CREATE STRIPE CHECKOUT SESSION
# =========================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([PaymentRateThrottle])
@transaction.atomic
def create_checkout_session(request):

    address_id = request.data.get("address")

    if not address_id:

        return Response(
            {
                "message": "Address is required"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    address = Address.objects.filter(id=address_id).first()
    if not address:
        return Response({"message": "Address not found"}, status=status.HTTP_404_NOT_FOUND)
    if address.user_id != request.user.id:
        return Response(
            {"detail": "You do not have permission to use this address."},
            status=status.HTTP_403_FORBIDDEN,
        )


    cart_items = list(
        Cart.objects
        .filter(
            user=request.user
        )
        .select_related(
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

        return Response(
            {
                "message": "Cart is empty"
            },
            status=status.HTTP_400_BAD_REQUEST
        )


    original_subtotal = Decimal("0.00")
    discount_total = Decimal("0.00")
    discounted_subtotal = Decimal("0.00")
    line_items = []


    # =====================================================
    # VALIDATE CART + CALCULATE PRICES
    # =====================================================

    for item in cart_items:

        if item.variant.price_type == "multiple":
            if not item.variant_unit:
                return Response(
                    {"message": f"{item.variant.product.name} has no selectable unit."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            available_stock = item.variant_unit.stock
            original_price = Decimal(str(item.variant_unit.price))
        else:
            available_stock = item.variant.stock
            original_price = Decimal(str(item.variant.price or 0))

        if item.quantity > available_stock:

            return Response(
                {
                    "message":
                    f"{item.variant.product.name} has only "
                    f"{available_stock} item(s) left."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        discounted_price = calculate_offer_price(
            original_price,
            item.variant.product.offer
        )

        welcome_bonus_assignment_id = item.welcome_bonus_assignment_id
        welcome_bonus_assignment = get_eligible_welcome_bonus_assignment(
            welcome_bonus_assignment_id,
            request.user,
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
                user=request.user,
                product=item.variant.product,
                assignment_id=welcome_bonus_assignment_id,
            ).delete()
            item.welcome_bonus_assignment = None
        else:
            coupon = get_eligible_coupon(coupon_id, item.variant.product)
        if coupon:
            discounted_price = calculate_coupon_price(discounted_price, coupon)
        elif coupon_id and not welcome_bonus_assignment:
            Cart.objects.filter(
                pk=item.pk,
                coupon_id=coupon_id,
            ).update(coupon=None)
            SavedCoupon.objects.filter(
                user=request.user,
                product=item.variant.product,
                coupon_id=coupon_id,
            ).delete()
            item.coupon = None

        discount_amount = original_price - discounted_price


        original_subtotal += (
            original_price * item.quantity
        )


        discount_total += (
            discount_amount * item.quantity
        )


        discounted_subtotal += (
            discounted_price * item.quantity
        )


        line_items.append(
            {
                "price_data": {
                    "currency": "aed",

                    "product_data": {
                        "name": item.variant.product.name,

                        # Save the product snapshot inside Stripe.
                        # This lets the webhook create the Order only
                        # after payment, without creating a Pending Order.
                        "metadata": {
                            "type": "product",
                            "variant_id": str(item.variant_id),
                            "variant_unit_id": str(item.variant_unit_id or ""),
                            "coupon_id": str(coupon.id if coupon else ""),
                            "welcome_bonus_assignment_id": str(
                                welcome_bonus_assignment.id
                                if welcome_bonus_assignment
                                else ""
                            ),
                            "original_price": str(original_price),
                            "discount_amount": str(discount_amount),
                            "discounted_price": str(discounted_price),
                        },
                    },

                    "unit_amount": int(
                        discounted_price * 100
                    ),
                },

                "quantity": item.quantity,
            }
        )


    totals = calculate_order_total(
        discounted_subtotal
    )


    # =====================================================
    # SHIPPING
    # =====================================================

    if totals["shipping"] > 0:

        line_items.append(
            {
                "price_data": {
                    "currency": "aed",

                    "product_data": {
                        "name": "Shipping",

                        "metadata": {
                            "type": "shipping",
                        },
                    },

                    "unit_amount": int(
                        totals["shipping"] * 100
                    ),
                },

                "quantity": 1,
            }
        )


    # =====================================================
    # CREATE STRIPE SESSION
    #
    # IMPORTANT:
    # No Order / OrderItem is created here.
    # The Order will be created only after Stripe confirms
    # that the payment is successful.
    # =====================================================

    try:

        session = StripeService.create_checkout_session(

            line_items=line_items,

            success_url=(
                f"{settings.SITE_URL}/payment-success"
                "?session_id={CHECKOUT_SESSION_ID}"
            ),

            cancel_url=f"{settings.SITE_URL}/checkout",

            metadata={
                "user_id": str(request.user.id),
                "address_id": str(address.id),
            },
            idempotency_key=(
                request.META.get("HTTP_IDEMPOTENCY_KEY", "")[:255] or None
            ),

        )

    except Exception:
        logger.exception("Stripe checkout session creation failed", extra={"user_id": request.user.id})

        return Response(
            {
                "message": "Unable to start payment. Please try again later."
            },
            status=500
        )


    checkout_url = getattr(session, "url", "")
    parsed_url = urlparse(checkout_url)
    if parsed_url.scheme != "https" or parsed_url.hostname != "checkout.stripe.com":
        logger.critical("Stripe returned an unexpected Checkout URL", extra={"user_id": request.user.id})
        return Response(
            {"message": "Unable to start secure payment. Please try again later."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response({"checkout_url": checkout_url})


# =========================================================
# FULFILL PAID ORDER
# =========================================================


class CheckoutFulfillmentError(ValueError):
    """A paid checkout cannot be fulfilled and must be refunded."""


def refund_unfulfillable_checkout(session, error):
    """Refund a paid, unfulfillable checkout exactly once and retain an audit record.

    A webhook must never endlessly retry after a stock/coupon race while the
    customer has already been charged. Stripe's idempotency key makes retrying
    this method safe if our database transaction is interrupted.
    """
    existing_order = Order.objects.filter(stripe_session_id=session.id).first()
    if existing_order:
        return existing_order

    payment_intent = getattr(session, "payment_intent", None)
    if not payment_intent:
        raise RuntimeError("A paid Stripe session is missing its payment intent.")

    stripe.Refund.create(
        payment_intent=str(payment_intent),
        idempotency_key=f"checkout-fulfillment-refund:{session.id}",
    )

    metadata = session.metadata or {}
    try:
        user_id = int(metadata["user_id"])
    except (KeyError, TypeError, ValueError) as exc:
        logger.critical(
            "Refunded Stripe checkout %s could not be recorded: invalid user metadata",
            session.id,
        )
        raise RuntimeError("Refunded checkout has invalid user metadata.") from exc

    address_id = metadata.get("address_id")
    address = Address.objects.filter(id=address_id, user_id=user_id).first()
    total = Decimal(str(session.amount_total or 0)) / Decimal("100")

    try:
        with transaction.atomic():
            order = Order.objects.create(
                user_id=user_id,
                address=address,
                subtotal=total,
                discount_amount=Decimal("0.00"),
                shipping_charge=Decimal("0.00"),
                total_amount=total,
                payment_status="Refunded",
                status="Cancelled",
                stripe_session_id=session.id,
            )
            AdminAuditLog.objects.create(
                action="stripe_refund",
                entity_type="order",
                entity_id=str(order.id),
                description=(
                    "Automatic Stripe refund after checkout fulfillment failure: "
                    f"{error}"
                ),
            )
    except IntegrityError:
        order = Order.objects.get(stripe_session_id=session.id)

    logger.warning(
        "Automatically refunded Stripe checkout %s because fulfillment failed: %s",
        session.id,
        error,
    )
    return order


def fulfill_or_refund_paid_order(session):
    try:
        return fulfill_paid_order(session)
    except CheckoutFulfillmentError as error:
        return refund_unfulfillable_checkout(session, error)

@transaction.atomic
def fulfill_paid_order(session):

    # =====================================================
    # VERIFY PAYMENT FIRST
    # =====================================================

    if session.payment_status != "paid":

        raise ValueError(
            "Payment is not paid"
        )


    user_id = session.metadata.get("user_id")
    address_id = session.metadata.get("address_id")


    if not user_id:

        raise ValueError(
            "User ID missing from Stripe metadata"
        )


    if not address_id:

        raise ValueError(
            "Address ID missing from Stripe metadata"
        )


    try:

        user_id = int(user_id)
        address_id = int(address_id)

    except (TypeError, ValueError):

        raise ValueError(
            "Invalid user or address ID"
        )


    # =====================================================
    # IDEMPOTENCY
    #
    # Webhook and payment-success API can both reach this
    # function. If this Stripe session already created an
    # order, return it instead of creating a duplicate.
    # =====================================================

    existing_order = (
        Order.objects
        .filter(stripe_session_id=session.id)
        .first()
    )

    if existing_order:

        return existing_order


    # =====================================================
    # VERIFY CURRENCY
    # =====================================================

    if not session.currency:

        raise ValueError(
            "Payment currency missing"
        )


    if session.currency.lower() != "aed":

        raise ValueError(
            "Invalid payment currency"
        )


    # =====================================================
    # GET STRIPE LINE ITEMS
    #
    # We use the Stripe Checkout line items as the payment
    # snapshot. This avoids depending on the user's cart after
    # payment.
    # =====================================================

    stripe_line_items = stripe.checkout.Session.list_line_items(
        session.id,
        limit=100,
        expand=["data.price.product"],
    )


    product_snapshots = []
    shipping_charge = Decimal("0.00")


    for line_item in stripe_line_items.data:

        product = line_item.price.product

        if not product:

            raise ValueError(
                "Stripe product information is missing"
            )

        metadata = product.metadata or {}
        item_type = metadata.get("type")


        if item_type == "shipping":

            shipping_charge += (
                Decimal(line_item.amount_total or 0) /
                Decimal("100")
            )

            continue


        if item_type != "product":

            raise ValueError(
                "Invalid Stripe line item"
            )


        variant_unit_id = metadata.get("variant_unit_id") or None
        variant_id = metadata.get("variant_id") or None

        if not variant_unit_id and not variant_id:
            raise ValueError("Product variant missing from Stripe line item")


        quantity = int(line_item.quantity or 0)

        if quantity <= 0:

            raise ValueError(
                "Invalid product quantity"
            )


        product_snapshots.append(
            {
                "variant_unit_id": int(variant_unit_id) if variant_unit_id else None,
                "variant_id": int(variant_id) if variant_id else None,
                "coupon_id": int(metadata["coupon_id"]) if metadata.get("coupon_id") else None,
                "welcome_bonus_assignment_id": (
                    int(metadata["welcome_bonus_assignment_id"])
                    if metadata.get("welcome_bonus_assignment_id")
                    else None
                ),
                "quantity": quantity,
                "original_price": Decimal(
                    metadata.get("original_price", "0")
                ),
                "discount_amount": Decimal(
                    metadata.get("discount_amount", "0")
                ),
                "price": Decimal(
                    metadata.get("discounted_price", "0")
                ),
            }
        )


    if not product_snapshots:

        raise ValueError(
            "No products found in Stripe session"
        )


    # =====================================================
    # VERIFY TOTAL AMOUNT
    # =====================================================

    expected_total = Decimal("0.00")
    original_subtotal = Decimal("0.00")
    discount_total = Decimal("0.00")
    discounted_subtotal = Decimal("0.00")


    for snapshot in product_snapshots:

        quantity = snapshot["quantity"]
        original_price = snapshot["original_price"]
        discount_amount = snapshot["discount_amount"]
        price = snapshot["price"]

        original_subtotal += (
            original_price * quantity
        )

        discount_total += (
            discount_amount * quantity
        )

        discounted_subtotal += (
            price * quantity
        )


    expected_total = (
        discounted_subtotal + shipping_charge
    )

    expected_amount = int(
        expected_total * 100
    )


    if session.amount_total != expected_amount:

        raise ValueError(
            "Stripe payment amount does not match order total"
        )


    # =====================================================
    # GET ADDRESS
    # =====================================================

    try:

        address = Address.objects.get(
            id=address_id,
            user_id=user_id
        )

    except Address.DoesNotExist:

        raise CheckoutFulfillmentError(
            "Address not found"
        )


    # =====================================================
    # LOCK STOCK ROWS
    # =====================================================

    variant_size_ids = [
        snapshot["variant_unit_id"]
        for snapshot in product_snapshots
        if snapshot["variant_unit_id"] is not None
    ]

    variant_ids = [
        snapshot["variant_id"]
        for snapshot in product_snapshots
        if snapshot["variant_id"] is not None
    ]


    locked_sizes = {
        variant_unit.id: variant_unit
        for variant_unit in (
            ProductVariantUnit.objects
            .select_for_update()
            .select_related(
                "variant",
                "variant__product",
                "variant__color",
                "unit",
            )
            .filter(
                id__in=variant_size_ids
            )
        )
    }

    locked_variants = {
        variant.id: variant
        for variant in (
            ProductVariant.objects
            .select_for_update()
            .select_related("product", "color")
            .filter(id__in=variant_ids)
        )
    }

    welcome_bonus_assignment_ids = {
        snapshot["welcome_bonus_assignment_id"]
        for snapshot in product_snapshots
        if snapshot.get("welcome_bonus_assignment_id")
    }
    locked_welcome_bonus_assignments = {
        assignment.id: assignment
        for assignment in (
            WelcomeBonusAssignment.objects.select_for_update()
            .select_related("welcome_bonus", "user")
            .prefetch_related("welcome_bonus__products")
            .filter(id__in=welcome_bonus_assignment_ids)
        )
    }


    # =====================================================
    # CHECK STOCK AGAIN
    # =====================================================

    for snapshot in product_snapshots:

        variant_unit = locked_sizes.get(snapshot["variant_unit_id"])
        variant = locked_variants.get(snapshot["variant_id"])

        if not variant_unit and not variant:

            raise CheckoutFulfillmentError(
                "Product variant not found"
            )

        stock = variant_unit.stock if variant_unit else variant.stock
        product_name = variant_unit.variant.product.name if variant_unit else variant.product.name
        if stock < snapshot["quantity"]:

            raise CheckoutFulfillmentError(
                f"Insufficient stock for "
                f"{product_name}"
            )

    # A coupon may be deactivated after the Stripe session was created but
    # before payment fulfillment. Do not create an order from that stale
    # discounted snapshot.
    for snapshot in product_snapshots:
        if not snapshot.get("coupon_id"):
            continue
        variant_unit = locked_sizes.get(snapshot["variant_unit_id"])
        variant = locked_variants.get(snapshot["variant_id"])
        selected_variant = variant_unit.variant if variant_unit else variant
        if not get_eligible_coupon(snapshot["coupon_id"], selected_variant.product):
            raise CheckoutFulfillmentError("Coupon is no longer active.")

    # Revalidate the private entitlement, ownership, campaign state and the
    # calculated server-side price immediately before creating the order. A
    # change after the Stripe session was opened must not consume the code.
    welcome_bonus_amounts = {}
    for snapshot in product_snapshots:
        assignment_id = snapshot.get("welcome_bonus_assignment_id")
        if not assignment_id:
            continue
        assignment = locked_welcome_bonus_assignments.get(assignment_id)
        if not assignment or assignment.user_id != user_id:
            raise CheckoutFulfillmentError("Welcome bonus is no longer available.")
        variant_unit = locked_sizes.get(snapshot["variant_unit_id"])
        variant = locked_variants.get(snapshot["variant_id"])
        selected_variant = variant_unit.variant if variant_unit else variant
        assignment = get_eligible_welcome_bonus_assignment(
            assignment,
            assignment.user,
            selected_variant.product,
        )
        if not assignment:
            raise CheckoutFulfillmentError("Welcome bonus is no longer active.")
        current_original_price = (
            variant_unit.price if variant_unit else selected_variant.price
        )
        current_offer_price = calculate_offer_price(
            current_original_price,
            selected_variant.product.offer,
        )
        current_discounted_price = calculate_welcome_bonus_price(
            current_offer_price,
            assignment,
        )
        if (
            current_discounted_price != snapshot["price"]
            or current_original_price != snapshot["original_price"]
        ):
            raise CheckoutFulfillmentError("Welcome bonus price changed.")
        welcome_bonus_amounts[assignment.id] = (
            welcome_bonus_amounts.get(assignment.id, Decimal("0.00"))
            + (current_offer_price - current_discounted_price) * snapshot["quantity"]
        )


    # =====================================================
    # CREATE PAID ORDER
    #
    # This is the first time Order is created.
    # =====================================================

    order = Order.objects.create(

        user_id=user_id,

        address=address,

        subtotal=original_subtotal,

        discount_amount=discount_total,

        shipping_charge=shipping_charge,

        total_amount=expected_total,

        payment_status="Paid",

        status="Processing",

        stripe_session_id=session.id,

    )


    # =====================================================
    # CREATE ORDER ITEMS
    # =====================================================

    for snapshot in product_snapshots:

        variant_unit = locked_sizes.get(snapshot["variant_unit_id"])
        variant = locked_variants.get(snapshot["variant_id"])
        selected_variant = variant_unit.variant if variant_unit else variant

        OrderItem.objects.create(

            order=order,

            product=selected_variant.product,

            color=selected_variant.color,

            unit=variant_unit.unit if variant_unit else None,

            variant_unit=variant_unit,

            quantity=snapshot["quantity"],

            original_price=snapshot["original_price"],

            discount_amount=snapshot["discount_amount"],

            price=snapshot["price"],

            total_price=(
                snapshot["price"] *
                snapshot["quantity"]
            ),

        )


    # =====================================================
    # REDUCE STOCK
    # =====================================================

    for snapshot in product_snapshots:

        variant_unit = locked_sizes.get(snapshot["variant_unit_id"])
        variant = locked_variants.get(snapshot["variant_id"])
        stock_record = variant_unit or variant
        stock_record.stock -= snapshot["quantity"]
        stock_record.save(update_fields=["stock"])

    for assignment_id, applied_amount in welcome_bonus_amounts.items():
        assignment = locked_welcome_bonus_assignments.get(assignment_id)
        if assignment:
            redeem_welcome_bonus_assignment(assignment, order, applied_amount)


    # =====================================================
    # REMOVE ONLY PURCHASED ITEMS FROM CART
    # =====================================================

    for snapshot in product_snapshots:

        cart_filter = {"user_id": user_id}
        if snapshot["variant_unit_id"] is not None:
            cart_filter["variant_unit_id"] = snapshot["variant_unit_id"]
        else:
            cart_filter["variant_id"] = snapshot["variant_id"]
            cart_filter["variant_unit__isnull"] = True
        Cart.objects.filter(**cart_filter).delete()

    transaction.on_commit(
        lambda order_id=order.id: send_owner_order_notification(order_id)
    )


    return order


# =========================================================
# PAYMENT SUCCESS PAGE API
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_success(request):

    session_id = request.GET.get(
        "session_id"
    )


    if not session_id:

        return Response(
            {
                "message":
                "Session ID is required"
            },
            status=status.HTTP_400_BAD_REQUEST
        )


    try:

        session = (
            stripe.checkout.Session.retrieve(
                session_id
            )
        )

    except Exception:

        return Response(
            {
                "message":
                "Invalid payment session"
            },
            status=status.HTTP_400_BAD_REQUEST
        )


    # =====================================================
    # LOGGED-IN USER MUST OWN THIS STRIPE SESSION
    # =====================================================

    session_user_id = session.metadata.get(
        "user_id"
    )


    if (
        not session_user_id
        or
        str(request.user.id)
        != str(session_user_id)
    ):

        return Response(
            {
                "message":
                "Unauthorized payment session"
            },
            status=status.HTTP_403_FORBIDDEN
        )


    if session.payment_status != "paid":

        return Response(
            {
                "message":
                "Payment has not been completed"
            },
            status=status.HTTP_400_BAD_REQUEST
        )


    try:

        # The webhook may already have created the order.
        # If not, this safely creates it after verifying payment.
        order = fulfill_or_refund_paid_order(session)

    except ValueError as error:

        return Response(
            {
                "message":
                str(error)
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    except Exception:

        return Response(
            {
                "message":
                "Payment was received but order processing failed. "
                "Please contact support."
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


    if order.payment_status == "Refunded":
        return Response(
            {
                "message": "Payment was refunded because the order could not be fulfilled.",
                "order_id": order.id,
                "payment_status": order.payment_status,
            },
            status=status.HTTP_409_CONFLICT,
        )

    return Response(
        {
            "message":
            "Payment successful",

            "order_id":
            order.id,
        }
    )


# =========================================================
# STRIPE WEBHOOK
# =========================================================

@csrf_exempt
def stripe_webhook(request):

    if request.method != "POST":

        return HttpResponse(
            status=405
        )


    payload = request.body

    signature = request.META.get(
        "HTTP_STRIPE_SIGNATURE"
    )


    if not signature:

        return HttpResponse(
            status=400
        )


    try:

        event = (
            stripe.Webhook.construct_event(

                payload,

                signature,

                settings.STRIPE_WEBHOOK_SECRET,

            )
        )


    except ValueError:

        return HttpResponse(
            status=400
        )


    except stripe.error.SignatureVerificationError:

        return HttpResponse(
            status=400
        )


    # =====================================================
    # PAYMENT COMPLETED
    # =====================================================

    if event["type"] == "checkout.session.completed":

        session = event["data"]["object"]


        if session.get(
            "payment_status"
        ) == "paid":

            try:

                fulfill_or_refund_paid_order(session)

            except Exception:

                # Returning 500 tells Stripe delivery failed,
                # so Stripe can retry the webhook.

                return HttpResponse(
                    status=500
                )


    # =====================================================
    # ASYNC PAYMENT SUCCESS
    # =====================================================

    elif (
        event["type"]
        ==
        "checkout.session.async_payment_succeeded"
    ):

        session = event["data"]["object"]


        try:

            fulfill_or_refund_paid_order(session)

        except Exception:

            return HttpResponse(
                status=500
            )


    return HttpResponse(
        status=200
    )


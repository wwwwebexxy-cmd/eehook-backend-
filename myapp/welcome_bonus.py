"""Server-side welcome-bonus rules and lifecycle helpers.

This module is deliberately shared by the validation endpoint, cart, direct
checkout and Stripe fulfilment paths.  Keeping that decision-making here makes
the database, rather than a browser payload, the authority for every price.
"""

import secrets
import string
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    Cart,
    Coupon,
    SavedWelcomeBonus,
    User,
    WelcomeBonus,
    WelcomeBonusAssignment,
    WelcomeBonusNotification,
    WelcomeBonusRedemption,
)


CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def welcome_bonus_applies_to_product(welcome_bonus, product):
    if not welcome_bonus or not product:
        return False
    if welcome_bonus.applicability_type == WelcomeBonus.APPLICABILITY_CATEGORY:
        return bool(
            welcome_bonus.category_id
            and welcome_bonus.category_id == product.category_id
        )
    return welcome_bonus.products.filter(pk=product.pk).exists()


def _new_redemption_code():
    return "WB-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(12))


def create_assignment(welcome_bonus, user):
    """Return the one assignment for a campaign/user, generating a safe code.

    Both the campaign/user and code uniqueness rules are protected at the
    database level.  The retry also handles the exceptionally unlikely random
    code collision without exposing it to a caller.
    """
    existing = WelcomeBonusAssignment.objects.filter(
        welcome_bonus=welcome_bonus, user=user
    ).first()
    if existing:
        return existing

    for _ in range(20):
        code = _new_redemption_code()
        if Coupon.objects.filter(code=code).exists():
            continue
        try:
            with transaction.atomic():
                assignment = WelcomeBonusAssignment.objects.create(
                    welcome_bonus=welcome_bonus,
                    user=user,
                    code=code,
                )
                WelcomeBonusNotification.objects.create(assignment=assignment)
                return assignment
        except IntegrityError:
            # A parallel request can create the campaign/user row first.
            assignment = WelcomeBonusAssignment.objects.filter(
                welcome_bonus=welcome_bonus, user=user
            ).first()
            if assignment:
                return assignment
    raise RuntimeError("Could not generate a unique welcome-bonus code.")


def assign_welcome_bonus_to_existing_users(welcome_bonus):
    """Assign a new campaign to every active customer exactly once."""
    users = User.objects.filter(is_active=True, role="Customer").only("id")
    return [create_assignment(welcome_bonus, user) for user in users.iterator()]


def assign_active_welcome_bonuses_to_user(user):
    """Give a newly registered customer every non-expired campaign once."""
    if not user.is_active or user.role != "Customer":
        return []
    bonuses = WelcomeBonus.objects.filter(
        archived_at__isnull=True,
        end_date__gte=timezone.now(),
    )
    return [create_assignment(welcome_bonus, user) for welcome_bonus in bonuses]


def get_latest_welcome_bonus_assignment(assignment):
    assignment_id = getattr(assignment, "pk", assignment)
    if not assignment_id:
        return None
    return (
        WelcomeBonusAssignment.objects.select_related("welcome_bonus", "user")
        .prefetch_related("welcome_bonus__products")
        .filter(pk=assignment_id)
        .first()
    )


def welcome_bonus_validation_error(assignment, user, product=None, *, require_claimed=True):
    """Return a stable error code/message or ``None`` when it is valid."""
    if not assignment:
        return ("WELCOME_BONUS_INVALID", "Invalid welcome bonus code.")
    if assignment.user_id != user.id:
        # Do not identify the legitimate code owner or campaign.
        return (
            "WELCOME_BONUS_NOT_ASSIGNED_TO_USER",
            "This welcome bonus is not available for the current user.",
        )
    if assignment.status == WelcomeBonusAssignment.STATUS_REDEEMED:
        return ("WELCOME_BONUS_ALREADY_REDEEMED", "This welcome bonus has already been redeemed.")

    welcome_bonus = assignment.welcome_bonus
    now = timezone.now()
    if not welcome_bonus.is_active or welcome_bonus.archived_at is not None:
        return ("WELCOME_BONUS_INACTIVE", "This welcome bonus is no longer active.")
    if now < welcome_bonus.start_date:
        return ("WELCOME_BONUS_NOT_STARTED", "This welcome bonus is not available yet.")
    if now > welcome_bonus.end_date:
        return ("WELCOME_BONUS_EXPIRED", "This welcome bonus has expired.")
    if require_claimed and assignment.status != WelcomeBonusAssignment.STATUS_CLAIMED:
        return ("WELCOME_BONUS_NOT_CLAIMED", "Claim this welcome bonus before using it.")
    if product is not None and not welcome_bonus_applies_to_product(welcome_bonus, product):
        return (
            "WELCOME_BONUS_NOT_APPLICABLE",
            "This welcome bonus is not applicable to this product.",
        )
    return None


def get_eligible_welcome_bonus_assignment(assignment, user, product):
    latest = get_latest_welcome_bonus_assignment(assignment)
    if latest and not welcome_bonus_validation_error(latest, user, product):
        return latest
    return None


def calculate_welcome_bonus_discount_amount(price, assignment):
    """Return a bounded per-unit discount using the campaign's DB values."""
    price = max(Decimal(str(price or 0)), Decimal("0.00"))
    if not assignment:
        return Decimal("0.00")
    welcome_bonus = assignment.welcome_bonus
    if welcome_bonus.discount_type == WelcomeBonus.DISCOUNT_FIXED:
        requested = welcome_bonus.fixed_amount or Decimal("0.00")
    else:
        requested = price * (welcome_bonus.discount_percentage or Decimal("0.00")) / Decimal("100")
    return min(max(requested, Decimal("0.00")), price).quantize(Decimal("0.01"))


def calculate_welcome_bonus_price(price, assignment):
    price = max(Decimal(str(price or 0)), Decimal("0.00"))
    return (price - calculate_welcome_bonus_discount_amount(price, assignment)).quantize(
        Decimal("0.01")
    )


def redeem_welcome_bonus_assignment(assignment, order, applied_amount):
    """Persist an immutable order snapshot and consume one claimed code.

    The caller must hold the assignment's row lock in the same transaction.
    """
    if assignment.status == WelcomeBonusAssignment.STATUS_REDEEMED:
        raise ValueError("Welcome bonus has already been redeemed.")
    validation_error = welcome_bonus_validation_error(assignment, assignment.user)
    if validation_error:
        raise ValueError(validation_error[1])

    welcome_bonus = assignment.welcome_bonus
    discount_value = (
        welcome_bonus.fixed_amount
        if welcome_bonus.discount_type == WelcomeBonus.DISCOUNT_FIXED
        else welcome_bonus.discount_percentage
    )
    WelcomeBonusRedemption.objects.create(
        assignment=assignment,
        order=order,
        user=assignment.user,
        welcome_bonus=welcome_bonus,
        redemption_code=assignment.code,
        discount_type=welcome_bonus.discount_type,
        discount_value=discount_value,
        applied_amount=max(Decimal(str(applied_amount or 0)), Decimal("0.00")),
    )
    assignment.status = WelcomeBonusAssignment.STATUS_REDEEMED
    assignment.redeemed_at = timezone.now()
    assignment.save(update_fields=("status", "redeemed_at", "updated_at"))
    SavedWelcomeBonus.objects.filter(assignment=assignment).delete()
    Cart.objects.filter(welcome_bonus_assignment=assignment).update(
        welcome_bonus_assignment=None
    )


def promotion_discounted_price(price, *, coupon=None, welcome_bonus_assignment=None):
    """Apply exactly one validated promotion after any product offer."""
    from .utils import calculate_coupon_price

    if welcome_bonus_assignment:
        return calculate_welcome_bonus_price(price, welcome_bonus_assignment)
    if coupon:
        return calculate_coupon_price(price, coupon)
    return Decimal(str(price or 0)).quantize(Decimal("0.01"))

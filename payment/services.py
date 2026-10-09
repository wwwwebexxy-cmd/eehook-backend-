import stripe
from django.conf import settings


stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeService:

    @staticmethod
    def create_checkout_session(
        line_items,
        success_url,
        cancel_url,
        metadata=None,
        idempotency_key=None,
    ):

        create_kwargs = {
            "payment_method_types": [
                "card"
            ],
            "mode": "payment",
            "line_items": line_items,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": metadata or {},
        }
        if idempotency_key:
            create_kwargs["idempotency_key"] = idempotency_key
        session = stripe.checkout.Session.create(**create_kwargs)

        return session

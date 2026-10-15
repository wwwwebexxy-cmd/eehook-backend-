import uuid

import requests

from django.conf import settings


class CashfreeAPIError(RuntimeError):
    """An error returned by the Cashfree Payments API."""

    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class CashfreeService:
    API_VERSION = "2023-08-01"

    @classmethod
    def environment(cls):
        return str(getattr(settings, "CASHFREE_ENV", "sandbox")).strip().lower()

    @classmethod
    def base_url(cls):
        if cls.environment() in {"production", "prod", "live"}:
            return "https://api.cashfree.com/pg"
        return "https://sandbox.cashfree.com/pg"

    @classmethod
    def _headers(cls, *, idempotency_key=None):
        client_id = str(getattr(settings, "CASHFREE_CLIENT_ID", "") or "").strip()
        client_secret = str(getattr(settings, "CASHFREE_CLIENT_SECRET", "") or "").strip()
        if not client_id or not client_secret:
            raise CashfreeAPIError("Cashfree credentials are not configured.")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-api-version": cls.API_VERSION,
            "x-client-id": client_id,
            "x-client-secret": client_secret,
            "x-request-id": str(uuid.uuid4()),
        }
        if idempotency_key:
            headers["x-idempotency-key"] = str(idempotency_key)[:255]
        return headers

    @classmethod
    def _request(cls, method, path, *, json=None, idempotency_key=None):
        try:
            response = requests.request(
                method,
                f"{cls.base_url()}{path}",
                headers=cls._headers(idempotency_key=idempotency_key),
                json=json,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise CashfreeAPIError("Cashfree is temporarily unavailable.") from exc

        try:
            response_body = response.json()
        except ValueError:
            response_body = {"detail": response.text[:500]}

        if not response.ok:
            raise CashfreeAPIError(
                "Cashfree rejected the payment request.",
                status_code=response.status_code,
                response_body=response_body,
            )
        return response_body

    @classmethod
    def create_order(
        cls,
        *,
        order_id,
        amount,
        currency,
        customer_details,
        return_url,
        notify_url,
        idempotency_key=None,
    ):
        payload = {
            "order_id": order_id,
            "order_amount": float(amount),
            "order_currency": currency,
            "customer_details": customer_details,
            "order_meta": {
                "return_url": return_url,
                "notify_url": notify_url,
            },
            "order_note": "eehook online order",
        }
        return cls._request(
            "POST",
            "/orders",
            json=payload,
            idempotency_key=idempotency_key or order_id,
        )

    @classmethod
    def get_order(cls, order_id):
        return cls._request("GET", f"/orders/{order_id}")

    @classmethod
    def get_payments(cls, order_id):
        return cls._request("GET", f"/orders/{order_id}/payments")

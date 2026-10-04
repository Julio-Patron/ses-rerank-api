import logging
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from gateway.billing import credit_pack, pack_for_price
from gateway.database import get_database_adapter
from gateway.runtime import debug_enabled

try:
    import stripe
except ImportError:
    stripe = None

logger = logging.getLogger(__name__)

router = APIRouter()


def _webhook_secret() -> str:
    return os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()


def _mapping_get(value, key, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    getter = getattr(value, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except TypeError:
            return getter(key)
    return getattr(value, key, default)


def _paid_price_id(session) -> str:
    """Read the first expanded Checkout line-item price. Never trust metadata."""
    line_items = _mapping_get(session, "line_items")
    data = _mapping_get(line_items, "data") if line_items is not None else None
    if not data:
        return ""
    price = _mapping_get(data[0], "price")
    if isinstance(price, str):
        return price
    price_id = _mapping_get(price, "id", "")
    return str(price_id or "")


@router.post("/v1/webhooks/stripe", summary="Stripe webhook for credit packs")
async def stripe_webhook(request: Request):
    """Credit the Checkout tenant after a verified payment. Never returns a raw key."""
    if request.query_params.get("simulated") == "true":
        if not debug_enabled():
            raise HTTPException(status_code=404, detail="Not found")
        event = await request.json()
    else:
        secret = _webhook_secret()
        if not stripe or not secret:
            raise HTTPException(status_code=503, detail="Stripe integration is not configured")

        payload = await request.body()
        signature = request.headers.get("stripe-signature")
        try:
            event = stripe.Webhook.construct_event(payload, signature, secret)
        except Exception as exc:
            error_type = getattr(getattr(stripe, "error", None), "SignatureVerificationError", None)
            if isinstance(exc, ValueError) or (error_type and isinstance(exc, error_type)):
                raise HTTPException(status_code=400, detail="Invalid signature")
            logger.exception("Stripe webhook verification failed")
            raise HTTPException(status_code=400, detail="Invalid signature")

    if event.get("type") != "checkout.session.completed":
        return JSONResponse({"status": "ignored", "reason": "unsupported_event"})

    session = event.get("data", {}).get("object", {})
    event_id = event.get("id")
    if not event_id:
        raise HTTPException(status_code=400, detail="Invalid payload")

    tenant_id = session.get("client_reference_id")
    if request.query_params.get("simulated") == "true":
        pack_name = (session.get("metadata") or {}).get("pack", "")
        pack = credit_pack(pack_name)
    else:
        if session.get("payment_status") != "paid":
            return JSONResponse({"status": "ignored", "reason": "unpaid"})
        session_id = session.get("id")
        if not session_id:
            raise HTTPException(status_code=400, detail="Invalid payload")
        try:
            paid_session = stripe.checkout.Session.retrieve(
                session_id,
                expand=["line_items"],
            )
        except Exception:
            logger.exception("Stripe session retrieve failed for event %s", event_id)
            raise HTTPException(status_code=502, detail="Could not verify payment")
        paid_tenant = _mapping_get(paid_session, "client_reference_id")
        if paid_tenant:
            tenant_id = paid_tenant
        pack = pack_for_price(_paid_price_id(paid_session))
    if pack is None or not tenant_id:
        logger.error("Stripe event %s is missing a configured pack or tenant", event_id)
        return JSONResponse({"status": "ignored", "reason": "unbillable"})

    db = get_database_adapter()
    try:
        result = await db.apply_paid_pack(
            event_id=event_id,
            tenant_id=str(tenant_id),
            plan_tier=pack["name"],
            credits_to_add=pack["credits"],
            rate_limit=pack["rate_limit"],
            checkout_session_id=session.get("id"),
        )
    except Exception:
        logger.exception("Stripe credit grant failed for event %s", event_id)
        raise HTTPException(status_code=500, detail="Database Error")

    if not result:
        return JSONResponse({"status": "ignored", "reason": "already_processed"})
    if result.get("status") == "unknown_tenant":
        return JSONResponse({"status": "ignored", "reason": "unknown_tenant"})
    if result.get("status") not in {"updated", "created"}:
        logger.error("Stripe event %s could not be delivered", event_id)
        raise HTTPException(status_code=500, detail="Database Error")
    return JSONResponse({"status": "success"})

import os
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from gateway.database import get_database_adapter

try:
    import stripe
except ImportError:
    stripe = None

logger = logging.getLogger(__name__)

router = APIRouter()

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY", "")

if stripe:
    stripe.api_key = STRIPE_API_KEY

@router.post("/v1/webhooks/stripe", summary="Stripe Webhook para recarga de créditos")
async def stripe_webhook(request: Request):
    """
    Recibe eventos de Stripe cuando un cliente completa un pago (Checkout Session).
    Extrae el email, genera una API Key y le asigna los créditos comprados.
    """
    if not stripe or not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Stripe integration is not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error(f"Invalid Stripe payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid Stripe signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        customer_email = session.get("customer_details", {}).get("email")
        amount_paid = session.get("amount_total", 0)  # cents ($49.00 = 4900)

        # Business rule: 100,000 credits for >= $49; otherwise starter pack
        credits_to_add = 100000 if amount_paid >= 4900 else 10000
        plan_tier = "growth" if amount_paid >= 4900 else "developer"

        logger.info(
            "Processing Stripe payment for %s. Assigning %s credits.",
            customer_email,
            credits_to_add,
        )

        db = get_database_adapter()
        try:
            namespace = (
                f"user_{customer_email.split('@')[0]}"
                if customer_email
                else "user_stripe"
            )
            new_key_data = await db.create_api_key(
                name=f"Stripe Purchase ({plan_tier})",
                namespace=namespace,
                rate_limit=500 if plan_tier == "growth" else 60,
                role="client",
            )
            key_hash = new_key_data["key_details"]["key"]
            await db.set_credits(key_hash, credits_to_add)
            key_prefix = new_key_data["key_details"].get("key_prefix", "")
            logger.info("API Key generated successfully. Prefix: %s", key_prefix)

        except Exception as e:
            logger.error(f"Error registrando compra en DB: {e}")
            raise HTTPException(status_code=500, detail="Database Error")

    return JSONResponse({"status": "success"})

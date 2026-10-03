import logging
import os

from fastapi import APIRouter, HTTPException, Request
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
    Extrae el email, genera una API Key y le asigna los créditos comprados, o recarga si ya existe.
    """
    # Usar un payload simulado si recibimos un query param de test
    if request.query_params.get("simulated") == "true":
        payload_data = await request.json()
        event = payload_data
    else:
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
        event_id = event.get("id", "evt_simulated_" + os.urandom(4).hex())
        
        customer_email = session.get("customer_details", {}).get("email")
        if not customer_email:
            customer_email = session.get("customer_email", "unknown@example.com")
            
        amount_paid = session.get("amount_total", 0)  # cents ($49.00 = 4900)

        # Business rule: 100,000 credits for >= $49; otherwise starter pack
        credits_to_add = 100000 if amount_paid >= 4900 else 10000
        plan_tier = "growth" if amount_paid >= 4900 else "developer"
        rate_limit = 500 if plan_tier == "growth" else 60

        logger.info(
            "Processing Stripe payment %s for %s. Assigning %s credits.",
            event_id,
            customer_email,
            credits_to_add,
        )

        db = get_database_adapter()
        try:
            result = await db.process_stripe_event(
                event_id=event_id,
                customer_email=customer_email,
                plan_tier=plan_tier,
                credits_to_add=credits_to_add,
                rate_limit=rate_limit
            )
            
            if not result:
                logger.info("Event %s already processed (Idempotency).", event_id)
                return JSONResponse({"status": "ignored", "reason": "already_processed"})
                
            if result["status"] == "created":
                logger.info("New API Key generated successfully. Prefix: %s", result["key_prefix"])
            else:
                logger.info("Existing API Key updated successfully. Prefix: %s", result["key_prefix"])

        except Exception as e:
            logger.error(f"Error registrando compra en DB: {e}")
            raise HTTPException(status_code=500, detail="Database Error")

    return JSONResponse({"status": "success"})

import os
import json
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from gateway.database import get_database_adapter
import hashlib
import uuid

# Si no tienes instalada la librería 'stripe', la puedes instalar con 'pip install stripe'
try:
    import stripe
except ImportError:
    stripe = None

logger = logging.getLogger(__name__)

router = APIRouter()

# Variables de entorno para Stripe
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
        
        # 1. Extraer información del cliente
        customer_email = session.get("customer_details", {}).get("email")
        
        # 2. Identificar qué compró (Growth vs Enterprise credit pack)
        # Puedes mapear el amount_total a la cantidad de créditos.
        amount_paid = session.get("amount_total", 0) # En centavos ($50.00 = 5000)
        
        # Lógica de negocio: 100,000 créditos cuestan $49 USD (4900 centavos)
        credits_to_add = 100000 if amount_paid >= 4900 else 10000
        plan_tier = "growth" if amount_paid >= 4900 else "developer"
        
        # 3. Generar la nueva API Key
        raw_key = f"ses_live_{uuid.uuid4().hex}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:15] + "..."

        logger.info(f"Procesando pago para {customer_email}. Asignando {credits_to_add} créditos.")

        # 4. Registrar en SQLite / Postgres
        db = get_database_adapter()
        # NOTA: Debes asegurar que create_api_key en database.py soporte inyectar 'credits_remaining' o hacer un update después.
        try:
            # Creamos la key (Ajusta los parámetros según tu método create_api_key)
            namespace = f"user_{customer_email.split('@')[0]}" if customer_email else "user_stripe"
            new_key_data = await db.create_api_key(
                name=f"Stripe Purchase ({plan_tier})",
                namespace=namespace,
                rate_limit=500 if plan_tier == "growth" else 60,
                role="client"
            )
            # Actualizamos sus créditos (requerirías un método explícito para set_credits si create_api_key no lo recibe,
            # pero por simplicidad de este webhook asumo que lo inyectarás o harás un UPDATE).
            # await db.set_credits(key_hash, credits_to_add)
            
            # 5. Enviar la API Key al usuario por email (Resend, SendGrid)
            # send_email(customer_email, f"Tu API Key de SES Rerank", f"Tu token es: {raw_key}")
            logger.info(f"API Key generada exitosamente. Prefix: {key_prefix}")
            
        except Exception as e:
            logger.error(f"Error registrando compra en DB: {e}")
            raise HTTPException(status_code=500, detail="Database Error")

    return JSONResponse({"status": "success"})

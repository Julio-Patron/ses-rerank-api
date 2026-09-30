import asyncio
import httpx
import json

async def simulate_stripe_webhook():
    # Simulamos un evento de checkout_session_completed
    event = {
        "id": "evt_test_123456789",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_a1b2c3d4",
                "customer_details": {
                    "email": "testclient@example.com"
                },
                "amount_total": 4900 # $49.00
            }
        }
    }
    
    print(f"Simulando Webhook para {event['data']['object']['customer_details']['email']}")
    
    # 1. Ejecución inicial (creación)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/v1/webhooks/stripe?simulated=true",
            json=event
        )
        print("Intento 1 (Creación):", response.status_code, response.json())
        
    # 2. Prueba de Idempotencia (Replay attack / Reintento)
    print("\nProbando protección de replay/idempotencia con el mismo event_id...")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/v1/webhooks/stripe?simulated=true",
            json=event
        )
        print("Intento 2 (Replay):", response.status_code, response.json())
        
    # 3. Prueba de Recarga (Mismo cliente, compra de nuevo)
    print("\nSimulando segunda compra para el mismo cliente (Top-up)...")
    event_2 = event.copy()
    event_2["id"] = "evt_test_987654321" # Nuevo ID de evento
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/v1/webhooks/stripe?simulated=true",
            json=event_2
        )
        print("Intento 3 (Recarga de créditos):", response.status_code, response.json())

if __name__ == "__main__":
    asyncio.run(simulate_stripe_webhook())

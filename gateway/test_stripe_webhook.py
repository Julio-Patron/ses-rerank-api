"""Stripe webhook E2E: checkout.session.completed assigns 100,000 credits."""

import hashlib
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

for _mod in (
    "qdrant_client",
    "qdrant_client.http",
    "sentence_transformers",
    "jas_vector_core",
    "redis",
    "redis.asyncio",
):
    sys.modules.setdefault(_mod, MagicMock())

os.environ["DEBUG"] = "true"
os.environ["GATEWAY_ADMIN_KEY"] = "ses_stripe_webhook_test_admin_key_32c"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_secret_for_unit_tests"
os.environ["STRIPE_API_KEY"] = "sk_test_dummy"

try:
    import stripe  # noqa: F401
except ImportError:
    sys.modules["stripe"] = MagicMock()

from gateway.server import app


@pytest.fixture
def stripe_client():
    mock_db = MagicMock()
    mock_db.connect = AsyncMock()
    mock_db.bootstrap_admin_key = AsyncMock()
    mock_db.revoke_api_key = AsyncMock(return_value=True)

    created = {}

    async def create_api_key(name, namespace, rate_limit, role):
        raw = "ses_stripe_generated_key_abc"
        key_hash = hashlib.sha256(raw.encode()).hexdigest()
        created["key_hash"] = key_hash
        created["raw"] = raw
        return {
            "key": raw,
            "key_details": {
                "key": key_hash,
                "id": "stripe_key_id",
                "tenant_id": "stripe_tenant",
                "key_prefix": raw[:15],
                "name": name,
                "namespace": namespace,
                "rate_limit": rate_limit,
                "role": role,
            },
        }

    mock_db.create_api_key = create_api_key
    mock_db.set_credits = AsyncMock(
        return_value={"credits_remaining": 100000, "tokens_saved_total": 0}
    )
    mock_db.apply_paid_pack = AsyncMock(
        return_value={"status": "updated", "key_prefix": "ses_abc123"}
    )

    fake_event = {
        "id": "evt_test",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_session",
                "payment_status": "paid",
                "client_reference_id": "tenant_123",
                "metadata": {"pack": "developer"},
                "customer_details": {"email": "buyer@example.com"},
                "amount_total": 100,
            }
        },
    }

    with patch("gateway.server.get_database_adapter", return_value=mock_db), \
         patch("gateway.stripe_webhook.get_database_adapter", return_value=mock_db), \
         patch("gateway.server._probe_qdrant", new_callable=AsyncMock, return_value=True), \
         patch("gateway.server._probe_redis", new_callable=AsyncMock, return_value=True), \
         patch("gateway.server._probe_ollama", new_callable=AsyncMock, return_value=True), \
         patch("gateway.server.redis_available", False), \
         patch("gateway.stripe_webhook.stripe") as mock_stripe:

        mock_stripe.Webhook.construct_event.return_value = fake_event
        mock_stripe.checkout.Session.retrieve.return_value = {
            "id": "cs_test_session",
            "payment_status": "paid",
            "client_reference_id": "tenant_123",
            "line_items": {"data": [{"price": {"id": "price_growth_test"}}]},
        }
        mock_stripe.error = MagicMock()
        mock_stripe.error.SignatureVerificationError = type(
            "SignatureVerificationError", (Exception,), {}
        )

        yield TestClient(app), mock_db, created, mock_stripe


def test_stripe_checkout_assigns_pack_credits_not_amount(stripe_client, monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_GROWTH", "price_growth_test")
    monkeypatch.setenv("STRIPE_CREDITS_GROWTH", "100000")
    monkeypatch.setenv("STRIPE_PRICE_DEVELOPER", "price_developer_test")
    client, mock_db, created, _stripe = stripe_client
    response = client.post(
        "/v1/webhooks/stripe",
        content=json.dumps({"id": "evt_test"}),
        headers={
            "Content-Type": "application/json",
            "stripe-signature": "t=1,v1=fake",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert "key" not in body
    assert "ses_" not in response.text
    mock_db.apply_paid_pack.assert_awaited_once()
    kwargs = mock_db.apply_paid_pack.await_args.kwargs
    assert kwargs["tenant_id"] == "tenant_123"
    assert kwargs["credits_to_add"] == 100000
    assert kwargs["plan_tier"] == "growth"
    assert "customer_email" not in kwargs


def test_stripe_ignores_metadata_when_price_does_not_match(stripe_client, monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_GROWTH", "price_growth_test")
    monkeypatch.setenv("STRIPE_PRICE_DEVELOPER", "price_developer_test")
    client, mock_db, _created, mock_stripe = stripe_client
    mock_stripe.checkout.Session.retrieve.return_value = {
        "id": "cs_test_session",
        "client_reference_id": "tenant_123",
        "line_items": {"data": [{"price": {"id": "price_attacker_cheap"}}]},
    }
    response = client.post(
        "/v1/webhooks/stripe",
        content=json.dumps({"id": "evt_test"}),
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert response.status_code == 200
    assert response.json()["reason"] == "unbillable"
    mock_db.apply_paid_pack.assert_not_called()


def test_stripe_unconfigured_returns_503(monkeypatch):
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "ses_stripe_webhook_test_admin_key_32c")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "")
    with patch("gateway.stripe_webhook.stripe", MagicMock()), \
         patch("gateway.server.get_database_adapter") as mock_db_func, \
         patch("gateway.server._probe_qdrant", new_callable=AsyncMock, return_value=True), \
         patch("gateway.server._probe_redis", new_callable=AsyncMock, return_value=True), \
         patch("gateway.server._probe_ollama", new_callable=AsyncMock, return_value=True), \
         patch("gateway.server.redis_available", False):
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.bootstrap_admin_key = AsyncMock()
        mock_db.revoke_api_key = AsyncMock()
        mock_db_func.return_value = mock_db
        client = TestClient(app)
        response = client.post("/v1/webhooks/stripe", content=b"{}")
        assert response.status_code == 503

"""Paid rerank path and Stripe credit-pack safety."""

import hashlib
import json
import os
import sys
from types import SimpleNamespace
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
os.environ["GATEWAY_ADMIN_KEY"] = "ses_billing_test_admin_key_32_chars"

from gateway.server import app
import gateway.server as server_module


CUSTOMER_KEY = "ses_billing_customer_key_32_chars_ok"


class _RateLimitPipe:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def incr(self, *_args, **_kwargs):
        return self

    def expire(self, *_args, **_kwargs):
        return self

    async def execute(self):
        return [1]


def _redis_client():
    redis = AsyncMock()
    redis.pipeline = MagicMock(return_value=_RateLimitPipe())
    return redis
RERANK_OK = {
    "results": [{"index": 0, "relevance_score": 0.9, "document": "Dell XPS"}],
    "meta": {"token_metrics": {"input_tokens": 8, "output_tokens": 4, "saved_tokens": 4}},
}


@pytest.fixture
def billing_client():
    key_hash = hashlib.sha256(CUSTOMER_KEY.encode()).hexdigest()
    state = {"credits": 100, "charges": 0}

    with patch("gateway.server.get_database_adapter") as db_factory, \
         patch("gateway.stripe_webhook.get_database_adapter") as webhook_db_factory, \
         patch("gateway.server._probe_qdrant", new_callable=AsyncMock, return_value=True), \
         patch("gateway.server._probe_redis", new_callable=AsyncMock, return_value=True), \
         patch("gateway.server._probe_ollama", new_callable=AsyncMock, return_value=True), \
         patch("gateway.server.redis_available", False), \
         patch("gateway.server.RerankerService") as reranker_class:
        database = MagicMock()
        database.connect = AsyncMock()
        database.bootstrap_admin_key = AsyncMock()
        database.revoke_api_key = AsyncMock()
        database.log_usage = AsyncMock()

        async def get_api_key(candidate):
            if candidate != key_hash:
                return None
            return {
                "key": key_hash,
                "id": "billing-key",
                "tenant_id": "tenant-billing",
                "name": "Buyer",
                "namespace": "tenant_billing",
                "rate_limit": 60,
                "role": "client",
                "credits_remaining": state["credits"],
            }

        async def update_credits(_key_hash, deducted, _saved):
            state["charges"] += 1
            state["credits"] -= deducted
            return {"credits_remaining": state["credits"], "tokens_saved_total": _saved}

        database.get_api_key = get_api_key
        database.update_credits = update_credits
        database.apply_paid_pack = AsyncMock(return_value={"status": "updated", "key_prefix": "ses_bill"})
        db_factory.return_value = database
        webhook_db_factory.return_value = database
        reranker = AsyncMock()
        reranker.rerank.return_value = RERANK_OK
        reranker_class.return_value = reranker
        server_module.reranker_service = reranker
        yield TestClient(app), database, state, reranker


def test_object_documents_rerank_without_queue(billing_client):
    client, _database, state, reranker = billing_client
    redis = _redis_client()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.rpush = AsyncMock()
    with patch("gateway.server.redis_available", True), patch("gateway.server.redis_client", redis):
        response = client.post(
            "/v1/rerank",
            json={
                "query": "laptop",
                "documents": [{"text": "Dell XPS", "metadata": {"price": 1800}}],
                "top_n": 1,
                "jsonlogic_filter": {"<": [{"var": "price"}, 2000]},
            },
            headers={"Authorization": CUSTOMER_KEY},
        )
    assert response.status_code == 200
    assert response.json()["meta"]["tokens_saved"] == 4
    assert state["charges"] == 1
    redis.rpush.assert_not_called()
    reranker.rerank.assert_awaited()


def test_rerank_failure_does_not_charge_or_leak(billing_client):
    client, _database, state, reranker = billing_client
    reranker.rerank.side_effect = RuntimeError("onnx secret exploded")
    response = client.post(
        "/v1/rerank",
        json={"query": "q", "documents": ["a"], "top_n": 1},
        headers={"Authorization": CUSTOMER_KEY},
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "Rerank failed"
    assert "onnx" not in response.text
    assert state["charges"] == 0


def test_idempotent_retry_does_not_charge(billing_client):
    client, _database, state, reranker = billing_client
    cached = json.dumps({"digest": "ignored", "result": RERANK_OK})
    redis = _redis_client()
    redis.get = AsyncMock(return_value=cached)
    with patch("gateway.server.redis_available", True), \
         patch("gateway.server.redis_client", redis), \
         patch("gateway.server.canonical_rerank_digest", return_value="ignored"):
        response = client.post(
            "/v1/rerank",
            json={"query": "q", "documents": ["a"], "top_n": 1},
            headers={"Authorization": CUSTOMER_KEY, "Idempotency-Key": "retry-1"},
        )
    assert response.status_code == 200
    assert response.json()["meta"]["credits_deducted"] == 0
    assert state["charges"] == 0
    reranker.rerank.assert_not_called()


def test_checkout_binds_tenant_and_price(billing_client, monkeypatch):
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_billing")
    monkeypatch.setenv("STRIPE_PRICE_DEVELOPER", "price_developer_test")
    client, _database, _state, _reranker = billing_client
    stripe = MagicMock()
    stripe.checkout.Session.create.return_value = SimpleNamespace(url="https://checkout.stripe.test/pay")
    with patch("gateway.server._stripe_module", return_value=stripe):
        response = client.post(
            "/v1/billing/checkout",
            json={"pack": "developer"},
            headers={"Authorization": f"Bearer {CUSTOMER_KEY}"},
        )
    assert response.status_code == 200
    assert response.json()["url"].startswith("https://checkout.stripe.test/")
    kwargs = stripe.checkout.Session.create.call_args.kwargs
    assert kwargs["client_reference_id"] == "tenant-billing"
    assert kwargs["line_items"] == [{"price": "price_developer_test", "quantity": 1}]
    assert kwargs["metadata"]["pack"] == "developer"


def test_simulated_webhook_hidden_when_debug_false(billing_client, monkeypatch):
    monkeypatch.setenv("DEBUG", "false")
    client, database, _state, _reranker = billing_client
    response = client.post(
        "/v1/webhooks/stripe?simulated=true",
        json={"id": "evt_sim", "type": "checkout.session.completed", "data": {"object": {}}},
    )
    assert response.status_code == 404
    database.apply_paid_pack.assert_not_called()


def test_webhook_rejects_bad_signature(billing_client, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_billing_test")
    client, database, _state, _reranker = billing_client

    class SignatureVerificationError(Exception):
        pass

    stripe = MagicMock()
    stripe.error.SignatureVerificationError = SignatureVerificationError
    stripe.Webhook.construct_event.side_effect = SignatureVerificationError("bad")
    with patch("gateway.stripe_webhook.stripe", stripe):
        response = client.post(
            "/v1/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=bad"},
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid signature"
    database.apply_paid_pack.assert_not_called()


def test_webhook_replay_does_not_grant_again(billing_client, monkeypatch):
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("STRIPE_PRICE_GROWTH", "price_growth_test")
    monkeypatch.setenv("STRIPE_CREDITS_GROWTH", "100000")
    client, database, _state, _reranker = billing_client
    database.apply_paid_pack = AsyncMock(return_value=None)
    response = client.post(
        "/v1/webhooks/stripe?simulated=true",
        json={
            "id": "evt_replay",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_replay",
                    "client_reference_id": "tenant-billing",
                    "metadata": {"pack": "growth"},
                    "amount_total": 4900,
                }
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["reason"] == "already_processed"
    database.apply_paid_pack.assert_awaited_once()

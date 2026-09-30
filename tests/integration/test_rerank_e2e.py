"""E2E TestClient coverage for /v1/rerank credits and Self-Healing errors."""

import hashlib
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

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
TEST_KEY = "ses_e2e_rerank_test_key_32chars_min"
os.environ["GATEWAY_ADMIN_KEY"] = TEST_KEY

from gateway.server import app

RERANK_OK = {
    "results": [{"index": 0, "relevance_score": 0.99, "document": "doc0"}],
    "meta": {
        "token_metrics": {
            "input_tokens": 20,
            "output_tokens": 8,
            "saved_tokens": 12,
            "savings_percentage": 60.0,
        }
    },
}


@pytest.fixture
def e2e_client():
    key_hash = hashlib.sha256(TEST_KEY.encode()).hexdigest()
    state = {
        "credits_remaining": 100,
        "tokens_saved_total": 0,
    }

    with patch("gateway.server.get_database_adapter") as mock_db_func, \
         patch("gateway.server._probe_qdrant", new_callable=AsyncMock, return_value=True), \
         patch("gateway.server._probe_redis", new_callable=AsyncMock, return_value=True), \
         patch("gateway.server._probe_ollama", new_callable=AsyncMock, return_value=True), \
         patch("gateway.server.redis_available", False), \
         patch("gateway.server.RerankerService") as mock_reranker_class:

        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.bootstrap_admin_key = AsyncMock()
        mock_db.revoke_api_key = AsyncMock(return_value=True)
        mock_db.log_usage = AsyncMock()

        async def get_api_key(h):
            if h != key_hash:
                return None
            return {
                "key": key_hash,
                "id": "e2e_key",
                "key_prefix": TEST_KEY[:15],
                "name": "E2E",
                "namespace": "tenant_e2e",
                "rate_limit": 1000,
                "role": "admin",
                "tenant_id": "tenant_e2e",
                "credits_remaining": state["credits_remaining"],
                "tokens_saved_total": state["tokens_saved_total"],
            }

        async def update_credits(h, deducted, tokens_saved):
            state["credits_remaining"] -= deducted
            state["tokens_saved_total"] += tokens_saved
            return {
                "credits_remaining": state["credits_remaining"],
                "tokens_saved_total": state["tokens_saved_total"],
            }

        mock_db.get_api_key = get_api_key
        mock_db.update_credits = update_credits
        mock_db_func.return_value = mock_db

        mock_instance = AsyncMock()
        mock_instance.rerank.return_value = RERANK_OK
        mock_reranker_class.return_value = mock_instance

        yield TestClient(app), state


def _headers():
    return {"Authorization": f"Bearer {TEST_KEY}"}


def test_e2e_rerank_deducts_one_credit_for_le_25_docs(e2e_client):
    client, state = e2e_client
    docs = [f"document number {i}" for i in range(25)]
    before = state["credits_remaining"]
    response = client.post(
        "/v1/rerank",
        json={"query": "q", "documents": docs, "top_n": 3},
        headers=_headers(),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["credits_deducted"] == 1
    assert state["credits_remaining"] == before - 1


def test_e2e_rerank_deducts_two_credits_for_26_docs(e2e_client):
    client, state = e2e_client
    docs = [f"document number {i}" for i in range(26)]
    before = state["credits_remaining"]
    response = client.post(
        "/v1/rerank",
        json={"query": "q", "documents": docs, "top_n": 3},
        headers=_headers(),
    )
    assert response.status_code == 200
    assert response.json()["meta"]["credits_deducted"] == 2
    assert state["credits_remaining"] == before - 2


def test_e2e_self_healing_empty_documents(e2e_client):
    client, _ = e2e_client
    response = client.post(
        "/v1/rerank",
        json={"query": "q", "documents": [], "top_n": 1},
        headers=_headers(),
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "invalid_parameters"
    assert body["retryable"] is True


def test_e2e_self_healing_top_n_exceeds_docs(e2e_client):
    client, _ = e2e_client
    response = client.post(
        "/v1/rerank",
        json={"query": "q", "documents": ["a", "b"], "top_n": 5},
        headers=_headers(),
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "invalid_parameters"
    assert body["retryable"] is True
    assert "top_n" in body["message"]


def test_e2e_insufficient_credits(e2e_client):
    client, state = e2e_client
    state["credits_remaining"] = 0
    response = client.post(
        "/v1/rerank",
        json={"query": "q", "documents": ["a"], "top_n": 1},
        headers=_headers(),
    )
    assert response.status_code == 402
    assert "Insufficient credits" in response.json()["detail"]

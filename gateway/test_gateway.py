import os
import sys
import json
import pytest
import hashlib
from unittest.mock import MagicMock, AsyncMock, create_autospec, patch
from fastapi.testclient import TestClient

# Inject parent directory path to import 'ses' and 'gateway'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set environment variable for tests
os.environ["DEBUG"] = "true"
TEST_ADMIN_KEY = "ses_test_admin_key_only_for_tests_2026"
os.environ["GATEWAY_ADMIN_KEY"] = TEST_ADMIN_KEY

import gateway.server as server_module
from gateway.database import DatabaseAdapter
from gateway.server import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def mock_gateway_services():
    """Mock the RAG Engine, LLM Provider, and Database Adapter for 100% offline unit tests."""
    with patch("gateway.server.get_vector_service") as mock_service, \
         patch("gateway.server.LocalLLMProvider") as mock_llm_class, \
         patch("gateway.server.get_database_adapter") as mock_db_func, \
         patch("gateway.server._probe_qdrant", new_callable=AsyncMock, return_value=True), \
         patch("gateway.server._probe_redis", new_callable=AsyncMock, return_value=True), \
         patch("gateway.server._probe_ollama", new_callable=AsyncMock, return_value=True), \
         patch("gateway.server.redis_available", False):
        
        # Setup mock database state
        active_hashes = {
            hashlib.sha256(TEST_ADMIN_KEY.encode()).hexdigest(): {
                "key": hashlib.sha256(TEST_ADMIN_KEY.encode()).hexdigest(),
                "id": "key_uuid_dev",
                "key_prefix": TEST_ADMIN_KEY[:15],
                "name": "Test Administrator",
                "namespace": "tenant_12345678",
                "rate_limit": 100,
                "role": "admin",
                "tenant_id": "tenant_uuid_dev",
                "credits_remaining": 1000,
                "tokens_saved_total": 0
            }
        }
        
        # Setup mock database
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.bootstrap_admin_key = AsyncMock()
        
        # Dynamic get_api_key mock
        async def mock_get_api_key(key_hash):
            return active_hashes.get(key_hash)
        mock_db.get_api_key = mock_get_api_key
        
        # Dynamic create_api_key mock
        async def mock_create_api_key(name, namespace, rate_limit, role):
            raw_token = "ses_mock_generated_token_999"
            new_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            key_data = {
                "key": new_hash,
                "id": "key_uuid_999",
                "key_prefix": raw_token[:15],
                "name": name,
                "namespace": f"tenant_marketing",
                "rate_limit": rate_limit,
                "role": role,
                "tenant_id": "tenant_uuid_marketing"
            }
            active_hashes[new_hash] = key_data
            return {
                "key": raw_token,
                "key_details": {
                    "key": new_hash,
                    "id": "key_uuid_999",
                    "tenant_id": "tenant_uuid_marketing",
                    "key_prefix": raw_token[:15],
                    "name": name,
                    "namespace": f"tenant_marketing",
                    "rate_limit": rate_limit,
                    "role": role,
                    "created_at": 1718520000
                }
            }
        mock_db.create_api_key = mock_create_api_key
        
        # Dynamic revoke_api_key mock
        async def mock_revoke_api_key(key_token_or_prefix):
            target_hash = None
            if key_token_or_prefix.startswith("ses_") and len(key_token_or_prefix) == 28:
                target_hash = hashlib.sha256(key_token_or_prefix.encode()).hexdigest()
            else:
                for h, data in active_hashes.items():
                    if data["key_prefix"] == key_token_or_prefix:
                        target_hash = h
                        break
            if target_hash and target_hash in active_hashes:
                del active_hashes[target_hash]
                return True
            return False
        mock_db.revoke_api_key = mock_revoke_api_key
        
        # mock list_api_keys
        mock_db.list_api_keys = AsyncMock(return_value=[
            {
                "key": TEST_ADMIN_KEY[:15] + "...",
                "name": "Test Administrator",
                "namespace": "tenant_12345678",
                "rate_limit": 100,
                "role": "admin",
                "created_at": 1718520000
            }
        ])
        
        mock_db.log_usage = AsyncMock()
        mock_db.get_analytics = AsyncMock(return_value={
            "total_requests": 50,
            "total_errors": 0,
            "total_searches": 30,
            "total_ingestions": 20,
            "average_latency_ms": 1.2,
            "keys_performance": [
                {
                    "name": "Test Administrator",
                    "namespace": "tenant_12345678",
                    "role": "admin",
                    "total_calls": 50,
                    "avg_latency_ms": 1.2
                }
            ],
            "recent_logs": [
                {
                    "timestamp": "2026-06-16T10:00:00Z",
                    "key_name": "Test Administrator",
                    "endpoint": "/api/v1/search",
                    "namespace": "tenant_12345678",
                    "status_code": 200,
                    "latency_ms": 1.2
                }
            ]
        })
        
        async def mock_update_credits(key_hash, credits_deducted, tokens_saved):
            if key_hash in active_hashes:
                return {
                    "credits_remaining": 990,
                    "tokens_saved_total": tokens_saved
                }
            raise ValueError("API Key not found")
        mock_db.update_credits = mock_update_credits

        mock_db_func.return_value = mock_db

        # Setup mock vector engine
        mock_engine = MagicMock()
        mock_engine.search = AsyncMock(return_value={
            "results": [
                {
                    "id": "doc_123",
                    "score": 0.85,
                    "text": "This is sample text about rescission clauses.",
                    "metadata": {"filename": "contract.pdf", "page_number": 2},
                    "indexed_at": 1718520000
                }
            ],
            "total_documents": 10,
            "processing_time_ms": 1.5,
            "rust_acceleration": False
        })
        
        mock_engine.ingest_file = AsyncMock(return_value={
            "status": "success",
            "document_id": "doc_abc",
            "file_type": "pdf",
            "content_length": 5000,
            "chunks_count": 5,
            "processing_time": 0.2
        })
        
        mock_engine.index_documents = AsyncMock(return_value={
            "indexed_count": 1,
            "total_documents": 11,
            "namespace": "personal_default"
        })
        
        mock_engine.list_documents = AsyncMock(return_value=[
            {
                "id": "doc_123",
                "text_snippet": "This is sample text...",
                "metadata": {"filename": "contract.pdf"},
                "indexed_at": 1718520000
            }
        ])
        
        mock_engine.delete_document = AsyncMock(return_value=True)
        mock_engine.get_stats = AsyncMock(return_value={
            "total_documents": 10,
            "embedding_dimension": 384,
            "rust_acceleration": False
        })
        
        mock_service.return_value = mock_engine
        
        # Setup mock LLM
        mock_llm = MagicMock()
        mock_llm.generate_answer = AsyncMock(return_value="Based on page 2 of contract.pdf, the rescission clause states that parties can rescind with a 30-day notice.")
        mock_llm_class.return_value = mock_llm
        
        yield mock_engine, mock_llm


def test_health_endpoint_does_not_initialize_rag_engine():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["services"]["qdrant"] == "connected"
    server_module.get_vector_service.assert_not_called()


def test_liveness_does_not_probe_dependencies():
    with patch("gateway.server._dependency_health", new_callable=AsyncMock) as health_probe:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    health_probe.assert_not_awaited()


def test_readiness_returns_503_when_a_required_dependency_is_down():
    degraded = {
        "status": "degraded",
        "timestamp": "2026-09-02T00:00:00Z",
        "services": {
            "qdrant": "connected",
            "redis": "connected",
            "ollama_api": "disconnected",
            "rust_acceleration": "inactive",
        },
    }
    with patch(
        "gateway.server._dependency_health",
        new_callable=AsyncMock,
        return_value=degraded,
    ):
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == degraded


def test_readiness_returns_200_when_required_dependencies_are_up():
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_unauthorized_access():
    response = client.post("/api/v1/search", json={"query": "hello"})
    assert response.status_code == 401
    assert "Missing API Key" in response.json()["detail"]


def test_invalid_api_key():
    response = client.post("/api/v1/search", json={"query": "hello"}, headers={"X-API-Key": "invalid_key"})
    assert response.status_code == 403
    assert "Invalid or expired" in response.json()["detail"]


def test_gateway_admin_key_must_be_explicit_and_strong(monkeypatch):
    monkeypatch.delenv("GATEWAY_ADMIN_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GATEWAY_ADMIN_KEY is required"):
        server_module.require_gateway_admin_key()

    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "short")
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        server_module.require_gateway_admin_key()

    monkeypatch.setenv(
        "GATEWAY_ADMIN_KEY",
        "replace_with_a_unique_ses_key_of_at_least_32_characters",
    )
    with pytest.raises(RuntimeError, match="placeholder"):
        server_module.require_gateway_admin_key()

    monkeypatch.setenv("GATEWAY_ADMIN_KEY", TEST_ADMIN_KEY)
    assert server_module.require_gateway_admin_key() == TEST_ADMIN_KEY


def test_cors_rejects_wildcard(monkeypatch):
    monkeypatch.setenv("GATEWAY_CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="wildcard"):
        server_module.configured_cors_origins()


def test_cors_defaults_include_both_local_portal_hosts(monkeypatch):
    monkeypatch.delenv("GATEWAY_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    origins = server_module.configured_cors_origins()

    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins


def test_cors_accepts_legacy_environment_alias(monkeypatch):
    monkeypatch.delenv("GATEWAY_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://legacy.example.com")

    assert server_module.configured_cors_origins() == ["https://legacy.example.com"]


def test_cors_preflight_accepts_readme_portal_origin():
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"


@pytest.mark.asyncio
async def test_gateway_lifespan_initializes_persistent_state(monkeypatch):
    database = MagicMock()
    database.connect = AsyncMock()
    database.revoke_api_key = AsyncMock()
    database.bootstrap_admin_key = AsyncMock()
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", TEST_ADMIN_KEY)

    with patch("gateway.server.get_database_adapter", return_value=database), \
         patch("gateway.server.redis_available", False):
        async with server_module.gateway_lifespan(server_module.app):
            pass

    database.connect.assert_awaited_once_with()
    database.revoke_api_key.assert_awaited_once_with("ses_dev_secret_key")
    database.bootstrap_admin_key.assert_awaited_once_with(TEST_ADMIN_KEY)


@pytest.mark.asyncio
async def test_rate_limit_fails_closed_in_production_without_redis():
    key_data = {"key": "hashed-test-key", "rate_limit": 60}
    with patch("gateway.server.DEBUG", False), patch("gateway.server.redis_available", False):
        with pytest.raises(server_module.HTTPException) as exc_info:
            await server_module.check_rate_limit(key_data)

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_persistent_metric_logging_uses_database_contract():
    strict_db = create_autospec(DatabaseAdapter, instance=True)
    key_data = {
        "key": "hashed-test-key",
        "id": "key-123",
        "tenant_id": "tenant-123",
        "name": "Metrics Client",
        "namespace": "tenant_metrics",
    }

    with patch("gateway.server.get_database_adapter", return_value=strict_db), \
         patch("gateway.server.redis_available", False):
        await server_module.log_request_metric(
            key_data,
            "/api/v1/search",
            200,
            12.5,
            tokens=7,
        )

    strict_db.log_usage.assert_awaited_once_with(
        tenant_id="tenant-123",
        api_key_id="key-123",
        endpoint="/api/v1/search",
        tokens=7,
        latency_ms=12.5,
    )


def test_admin_api_key_management():
    headers = {"X-API-Key": TEST_ADMIN_KEY}
    
    # 1. Create a new client key
    key_payload = {
        "name": "Frontend Web App",
        "namespace": "marketing",
        "rate_limit": 50,
        "role": "client"
    }
    create_res = client.post("/api/v1/admin/keys", json=key_payload, headers=headers)
    assert create_res.status_code == 200
    create_payload = create_res.json()
    new_key_data = create_payload["key_details"]
    assert new_key_data["name"] == "Frontend Web App"
    assert new_key_data["role"] == "client"
    assert new_key_data["id"] == "key_uuid_999"
    assert new_key_data["tenant_id"] == "tenant_uuid_marketing"
    new_token = create_payload["key"]
    
    # 2. Verify we can search using the newly generated key
    search_payload = {
        "query": "hello",
        "generate_answer": False
    }
    search_res = client.post("/api/v1/search", json=search_payload, headers={"X-API-Key": new_token})
    assert search_res.status_code == 200
    
    # 3. Revoke/delete the key using admin privileges
    delete_res = client.delete(f"/api/v1/admin/keys/{new_token}", headers=headers)
    assert delete_res.status_code == 200
    
    # 4. Confirm the revoked key no longer has search privileges (403)
    search_res_revoked = client.post("/api/v1/search", json=search_payload, headers={"X-API-Key": new_token})
    assert search_res_revoked.status_code == 403

def test_api_stats():
    headers = {"X-API-Key": TEST_ADMIN_KEY}
    response = client.get("/api/v1/stats", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "stats" in data
    assert "namespace" in data
    assert data["namespace"] == "tenant_12345678"
    assert data["stats"]["total_documents"] == 10

def test_rerank():
    # RerankService will be invoked
    # Make sure we use the 'Authorization' header
    headers = {"Authorization": f"Bearer {TEST_ADMIN_KEY}"}
    payload = {
        "query": "hello world",
        "documents": ["doc1", "doc2 hello", "world peace"],
        "top_n": 2,
        "return_documents": True
    }
    
    # We should also mock RerankerService
    with patch("gateway.server.RerankerService") as mock_reranker_class:
        mock_instance = AsyncMock()
        mock_instance.rerank.return_value = {
            "results": [
                {"index": 1, "relevance_score": 0.9, "document": "doc2 hello"},
                {"index": 2, "relevance_score": 0.5, "document": "world peace"}
            ],
            "meta": {
                "token_metrics": {
                    "input_tokens": 10,
                    "output_tokens": 6,
                    "saved_tokens": 4,
                    "savings_percentage": 40.0
                }
            }
        }
        mock_reranker_class.return_value = mock_instance
        
        response = client.post("/v1/rerank", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2
        assert data["meta"]["credits_deducted"] == 1
        assert data["meta"]["credits_remaining"] == 990
        assert data["meta"]["tokens_saved"] == 4

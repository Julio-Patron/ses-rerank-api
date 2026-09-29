"""Tests for fail-closed authentication and rate limiting behavior."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient

# Set DEBUG=false for fail-closed tests
os.environ["DEBUG"] = "false"
os.environ["GATEWAY_ADMIN_KEY"] = "secure_admin_key_that_is_long_enough_for_production"
os.environ["GATEWAY_CORS_ORIGINS"] = "http://localhost:3000"
os.environ["QDRANT_API_KEY"] = "test_key"
os.environ["REDIS_PASSWORD"] = "test_pass"

from gateway.server import (
    app,
    get_api_key_details,
    check_rate_limit,
    require_gateway_admin_key,
    configured_cors_origins,
    redis_available,
    redis_client,
)


class TestFailClosedAuth:
    """Tests that validate fail-closed behavior when DEBUG=false."""

    def test_require_gateway_admin_key_rejects_placeholder(self):
        """GATEWAY_ADMIN_KEY with placeholder should raise RuntimeError."""
        with patch.dict(os.environ, {"GATEWAY_ADMIN_KEY": "change_me_this_key"}):
            with pytest.raises(RuntimeError, match="placeholder"):
                require_gateway_admin_key()

    def test_require_gateway_admin_key_rejects_legacy(self):
        """GATEWAY_ADMIN_KEY with legacy compromised key should raise RuntimeError."""
        with patch.dict(os.environ, {"GATEWAY_ADMIN_KEY": "ses_dev_secret_key"}):
            with pytest.raises(RuntimeError, match="revoked legacy"):
                require_gateway_admin_key()

    def test_require_gateway_admin_key_rejects_short(self):
        """GATEWAY_ADMIN_KEY too short should raise RuntimeError."""
        with patch.dict(os.environ, {"GATEWAY_ADMIN_KEY": "short"}):
            with pytest.raises(RuntimeError, match="at least 32 characters"):
                require_gateway_admin_key()

    def test_require_gateway_admin_key_accepts_valid(self):
        """Valid GATEWAY_ADMIN_KEY should be accepted."""
        with patch.dict(os.environ, {"GATEWAY_ADMIN_KEY": "valid_production_key_that_is_long_enough"}):
            result = require_gateway_admin_key()
            assert result == "valid_production_key_that_is_long_enough"

    def test_configured_cors_origins_rejects_wildcard(self):
        """CORS origins with wildcard should raise RuntimeError."""
        with patch.dict(os.environ, {"GATEWAY_CORS_ORIGINS": "http://localhost:3000,*"}):
            with pytest.raises(RuntimeError, match="wildcard"):
                configured_cors_origins()

    def test_configured_cors_origins_accepts_valid(self):
        """Valid CORS origins should be parsed."""
        with patch.dict(os.environ, {"GATEWAY_CORS_ORIGINS": "http://localhost:3000,https://app.example.com"}):
            origins = configured_cors_origins()
            assert "http://localhost:3000" in origins
            assert "https://app.example.com" in origins


class TestFailClosedRateLimit:
    """Tests for rate limiting fail-closed behavior."""

    @pytest.mark.asyncio
    async def test_check_rate_limit_fails_closed_when_redis_unavailable(self):
        """Rate limit should fail closed (503) when Redis unavailable and DEBUG=false."""
        # Ensure Redis is not available
        with patch("gateway.server.redis_available", False), \
             patch("gateway.server.DEBUG", False):
            
            key_data = {
                "key": "test_hash",
                "rate_limit": 10,
                "namespace": "test_ns",
                "name": "test_client",
                "id": 1,
                "tenant_id": 1,
            }
            
            with pytest.raises(HTTPException) as exc_info:
                await check_rate_limit(key_data)
            
            assert exc_info.value.status_code == 503
            assert "Rate limiting service unavailable" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_check_rate_limit_fails_closed_on_redis_error(self):
        """Rate limit should fail closed (503) on Redis error when DEBUG=false."""
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(side_effect=Exception("Redis connection failed"))
        mock_redis.expire = AsyncMock()
        
        with patch("gateway.server.redis_available", True), \
             patch("gateway.server.redis_client", mock_redis), \
             patch("gateway.server.DEBUG", False):
            
            key_data = {
                "key": "test_hash",
                "rate_limit": 10,
                "namespace": "test_ns",
                "name": "test_client",
                "id": 1,
                "tenant_id": 1,
            }
            
            with pytest.raises(HTTPException) as exc_info:
                await check_rate_limit(key_data)
            
            assert exc_info.value.status_code == 503
            assert "Rate limiting service unavailable" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_check_rate_limit_allows_in_memory_fallback_when_debug_true(self):
        """Rate limit should allow in-memory fallback when DEBUG=true."""
        with patch("gateway.server.redis_available", False), \
             patch("gateway.server.DEBUG", True):
            
            key_data = {
                "key": "test_hash",
                "rate_limit": 10,
                "namespace": "test_ns",
                "name": "test_client",
                "id": 1,
                "tenant_id": 1,
            }
            
            # Should not raise - uses in-memory fallback
            await check_rate_limit(key_data)
            await check_rate_limit(key_data)  # Second call


class TestFailClosedApiKeyValidation:
    """Tests for API key validation fail-closed behavior."""

    @pytest.mark.asyncio
    async def test_get_api_key_details_rejects_missing_key(self):
        """Missing API key should return 401."""
        with pytest.raises(HTTPException) as exc_info:
            await get_api_key_details(api_key=None)
        
        assert exc_info.value.status_code == 401
        assert "Missing API Key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_api_key_details_rejects_invalid_key(self):
        """Invalid API key should return 403."""
        # Mock both Redis and DB to return no key
        with patch("gateway.server.redis_available", False), \
             patch("gateway.server.get_database_adapter") as mock_db_adapter:
            
            mock_db = AsyncMock()
            mock_db.get_api_key = AsyncMock(return_value=None)
            mock_db_adapter.return_value = mock_db
            
            with pytest.raises(HTTPException) as exc_info:
                await get_api_key_details(api_key="invalid_key")
            
            assert exc_info.value.status_code == 403
            assert "Invalid or expired API Key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_api_key_details_accepts_valid_key(self):
        """Valid API key should return key data."""
        with patch("gateway.server.redis_available", False), \
             patch("gateway.server.get_database_adapter") as mock_db_adapter:
            
            mock_db = AsyncMock()
            mock_db.get_api_key = AsyncMock(return_value={
                "id": 1,
                "key": "valid_hash",
                "name": "test_client",
                "namespace": "test_ns",
                "rate_limit": 60,
                "role": "client",
                "tenant_id": 1,
            })
            mock_db_adapter.return_value = mock_db
            
            result = await get_api_key_details(api_key="valid_key")
            
            assert result["name"] == "test_client"
            assert result["namespace"] == "test_ns"


class TestGatewayEndpointsFailClosed:
    """Integration tests for gateway endpoints with fail-closed behavior."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_search_requires_api_key(self, client):
        """Search endpoint should require API key."""
        response = client.post("/api/v1/search", json={"query": "test"})
        # Should be 401 (missing key) or 403 (invalid key) - not 200 or 500
        assert response.status_code in (401, 403)

    def test_ingest_requires_api_key(self, client):
        """Ingest endpoint should require API key."""
        response = client.post("/api/v1/ingest/text", json={"text": "test", "filename": "test.txt"})
        assert response.status_code in (401, 403)

    def test_admin_requires_admin_role(self, client):
        """Admin endpoints should require admin role."""
        response = client.get("/api/v1/admin/keys")
        assert response.status_code in (401, 403)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
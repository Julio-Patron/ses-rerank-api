import hashlib

import pytest

from gateway.database import SQLiteDatabaseAdapter


@pytest.mark.asyncio
async def test_bootstrap_key_has_administrator_role(tmp_path):
    adapter = SQLiteDatabaseAdapter(str(tmp_path / "gateway.db"))
    await adapter.connect()

    raw_key = "ses_test_bootstrap_administrator_key_2026"
    await adapter.bootstrap_admin_key(raw_key)

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    stored = await adapter.get_api_key(key_hash)

    assert stored is not None
    assert stored["role"] == "admin"
    assert stored["key"] == key_hash
    assert raw_key not in stored.values()


@pytest.mark.asyncio
async def test_created_key_is_returned_once_and_cached_as_hash(tmp_path):
    adapter = SQLiteDatabaseAdapter(str(tmp_path / "gateway.db"))
    await adapter.connect()

    result = await adapter.create_api_key(
        name="Test Client",
        namespace="requested_namespace",
        rate_limit=50,
        role="client",
    )

    raw_key = result["key"]
    expected_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    assert raw_key.startswith("ses_")
    assert result["key_details"]["key"] == expected_hash
    assert result["key_details"]["key"] != raw_key
    assert result["key_details"]["id"]
    assert result["key_details"]["tenant_id"]
    assert result["key_details"]["key_prefix"] == raw_key[:15]

    await adapter.log_usage(
        tenant_id=result["key_details"]["tenant_id"],
        api_key_id=result["key_details"]["id"],
        endpoint="/v1/rerank",
        tokens=12,
        latency_ms=4.5,
    )
    await adapter.update_credits(expected_hash, credits_deducted=1, tokens_saved=30)
    analytics = await adapter.get_analytics()

    assert analytics["total_requests"] == 1
    assert analytics["total_reranks"] == 1
    assert analytics["tokens_saved_total"] == 30
    assert analytics["recent_logs"][0]["endpoint"] == "/v1/rerank"


@pytest.mark.asyncio
async def test_ping_succeeds_on_a_fresh_database(tmp_path):
    adapter = SQLiteDatabaseAdapter(str(tmp_path / "gateway.db"))
    await adapter.connect()

    await adapter.ping()

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
        endpoint="/api/v1/search",
        tokens=12,
        latency_ms=4.5,
    )
    analytics = await adapter.get_analytics()

    assert analytics["total_requests"] == 1
    assert analytics["total_searches"] == 1
    assert analytics["recent_logs"][0]["endpoint"] == "/api/v1/search"


@pytest.mark.asyncio
async def test_paid_pack_credits_only_the_checkout_tenant(tmp_path):
    adapter = SQLiteDatabaseAdapter(str(tmp_path / "gateway.db"))
    await adapter.connect()

    buyer = await adapter.signup_by_email("buyer@example.com")
    other = await adapter.signup_by_email("buyer-other@example.com")
    buyer_hash = hashlib.sha256(buyer["api_key"].encode()).hexdigest()
    other_hash = hashlib.sha256(other["api_key"].encode()).hexdigest()
    buyer_row = await adapter.get_api_key(buyer_hash)
    other_row = await adapter.get_api_key(other_hash)

    result = await adapter.apply_paid_pack(
        event_id="evt_pack_1",
        tenant_id=buyer_row["tenant_id"],
        plan_tier="growth",
        credits_to_add=100000,
        rate_limit=500,
        checkout_session_id="cs_test_topup",
    )
    assert result["status"] == "updated"
    assert "key" not in result
    assert buyer["api_key"] not in str(result)

    replay = await adapter.apply_paid_pack(
        event_id="evt_pack_1",
        tenant_id=other_row["tenant_id"],
        plan_tier="growth",
        credits_to_add=100000,
        rate_limit=500,
        checkout_session_id="cs_test_topup",
    )
    assert replay is None

    buyer_usage = await adapter.get_usage(buyer_hash)
    other_usage = await adapter.get_usage(other_hash)
    assert buyer_usage["credits_remaining"] == 101000
    assert other_usage["credits_remaining"] == 1000
    assert buyer_usage["plan_tier"] == "growth"


@pytest.mark.asyncio
async def test_paid_pack_claim_returns_key_once(tmp_path):
    adapter = SQLiteDatabaseAdapter(str(tmp_path / "gateway.db"))
    await adapter.connect()
    created = await adapter.signup_by_email("first-buy@example.com")
    key_hash = hashlib.sha256(created["api_key"].encode()).hexdigest()
    tenant_id = (await adapter.get_api_key(key_hash))["tenant_id"]
    await adapter.revoke_api_key(created["api_key"])

    result = await adapter.apply_paid_pack(
        event_id="evt_claim_1",
        tenant_id=tenant_id,
        plan_tier="developer",
        credits_to_add=10000,
        rate_limit=60,
        checkout_session_id="cs_test_claim",
    )
    assert result["status"] == "created"
    assert result["claim_required"] is True
    assert "key" not in result

    claimed = await adapter.claim_checkout_key("cs_test_claim")
    assert claimed.startswith("ses_")
    assert claimed != created["api_key"]
    assert await adapter.claim_checkout_key("cs_test_claim") is None
    stored = await adapter.get_api_key(hashlib.sha256(claimed.encode()).hexdigest())
    assert stored["credits_remaining"] == 10000
    assert claimed not in stored.values()

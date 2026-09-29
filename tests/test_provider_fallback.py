"""Tests for provider fallback and routing behavior."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ses.core.providers import (
    ProviderRouter,
    LocalSentenceTransformerProvider,
    DummyEmbeddingProvider,
    ProviderState,
    ProviderConfig,
    create_test_router,
)
from ses.core.rag import OfflineRAGEngine


def working_dummy(name="dummy-success"):
    return DummyEmbeddingProvider(
        config=ProviderConfig(name=name, timeout=1.0, max_retries=0),
        should_fail=False,
    )


def test_local_provider_dimension_prefers_current_sentence_transformers_api():
    class CurrentModel:
        def get_embedding_dimension(self):
            return 384

        def get_sentence_embedding_dimension(self):
            raise AssertionError("deprecated API should not be used")

    provider = LocalSentenceTransformerProvider(device="cpu")
    provider._model = CurrentModel()

    assert provider.dimension == 384


def test_local_provider_dimension_supports_legacy_sentence_transformers_api():
    class LegacyModel:
        def get_sentence_embedding_dimension(self):
            return 384

    provider = LocalSentenceTransformerProvider(device="cpu")
    provider._model = LegacyModel()

    assert provider.dimension == 384


@pytest.mark.asyncio
async def test_provider_router_fallback_on_failure():
    """Test that router falls back to secondary provider when primary fails."""
    # Create router with failing primary and working fallback
    router = create_test_router(primary_should_fail=True)

    # Should succeed via a deterministic in-memory fallback.
    result = await router.embed(["test text"])
    assert len(result) == 1
    assert len(result[0]) == 384

    # One provider failure is counted once by the provider/router boundary.
    primary = router.providers[0]
    assert primary.metrics.failed_calls == 1
    assert primary.metrics.state == ProviderState.HEALTHY
    # Fallback should have succeeded
    fallback = router.providers[1]
    assert fallback.metrics.successful_calls >= 1


@pytest.mark.asyncio
async def test_provider_router_uses_primary_when_healthy():
    """Test that router uses primary provider when it succeeds."""
    router = create_test_router(primary_should_fail=False)

    result = await router.embed(["test text"])
    assert len(result) == 1

    primary = router.providers[0]
    assert primary.metrics.successful_calls == 1
    assert primary.metrics.state == ProviderState.HEALTHY
    # Fallback should not be called
    fallback = router.providers[1]
    assert fallback.metrics.total_calls == 0


@pytest.mark.asyncio
async def test_provider_router_circuit_breaker_opens_after_threshold():
    """Test circuit breaker opens on failing provider after threshold, but router succeeds via fallback."""
    config = ProviderConfig(
        name="failing-test",
        circuit_breaker_threshold=3,
        circuit_breaker_timeout=60.0,
        timeout=1.0,
        max_retries=0
    )

    failing_provider = DummyEmbeddingProvider(config=config, should_fail=True)
    working_provider = working_dummy()

    router = ProviderRouter([failing_provider, working_provider])

    # Make 3 calls - each will fail on primary, succeed on fallback
    for i in range(3):
        result = await router.embed(["test"])
        assert len(result) == 1

    # After 3+ failures, primary's circuit should be OPEN
    assert failing_provider.metrics.state == ProviderState.OPEN
    assert failing_provider.metrics.failed_calls >= 3
    # Fallback should have succeeded each time
    assert working_provider.metrics.successful_calls == 3


@pytest.mark.asyncio
async def test_provider_router_circuit_breaker_half_open_recovery():
    """Test circuit breaker allows recovery test after timeout."""
    config = ProviderConfig(
        name="flaky-test",
        circuit_breaker_threshold=2,
        circuit_breaker_timeout=0.1,  # Very short for test
        timeout=1.0,
        max_retries=0
    )

    # Provider that fails twice then succeeds
    call_count = [0]

    class FlakyProvider(DummyEmbeddingProvider):
        async def embed(self, texts):
            call_count[0] += 1
            if call_count[0] <= 2:
                return await super().embed(texts)  # Will fail
            # Third call succeeds
            self.record_success()
            return [[0.0] * 384 for _ in texts]

    flaky = FlakyProvider(config=config, should_fail=True)
    working = working_dummy()

    router = ProviderRouter([flaky, working])

    # First 2 calls fail on flaky, succeed on working
    for _ in range(2):
        result = await router.embed(["test"])
        assert len(result) == 1

    assert flaky.metrics.state == ProviderState.OPEN

    # Wait for circuit breaker timeout
    await asyncio.sleep(0.15)

    # Next call should test recovery (half-open) - flaky now works
    result = await router.embed(["test"])
    assert len(result) == 1
    # Should have used flaky provider (now working) since it's first in chain
    assert flaky.metrics.successful_calls == 1


@pytest.mark.asyncio
async def test_offline_rag_engine_uses_provider_router():
    """Test OfflineRAGEngine uses provider router for embeddings."""
    # Create engine with test router
    test_router = create_test_router(primary_should_fail=True)
    engine = OfflineRAGEngine(router=test_router)

    # Mock vector store to avoid actual DB calls
    engine.vector_store.ensure_collection = AsyncMock()
    engine.vector_store.upsert_points = AsyncMock()
    engine.redis.pipeline = MagicMock(return_value=AsyncMock(
        lpush=MagicMock(), ltrim=MagicMock(), zincrby=MagicMock(), execute=AsyncMock()
    ))

    # Ingest a file - should use fallback provider
    import io
    result = await engine.ingest_file(
        namespace="test_ns",
        file_obj=io.BytesIO(b"test content"),
        filename="test.txt",
        metadata={"source": "test"}
    )

    assert result["status"] == "success"
    # Primary should have failed, fallback succeeded
    primary = test_router.providers[0]
    fallback = test_router.providers[1]
    assert primary.metrics.failed_calls >= 1
    assert fallback.metrics.successful_calls >= 1


@pytest.mark.asyncio
async def test_provider_metrics_observable():
    """Test provider metrics are exposed for observability."""
    router = create_test_router(primary_should_fail=True)

    await router.embed(["test"])
    await router.embed_query("query test")

    metrics = router.get_provider_metrics()
    assert "dummy-primary" in metrics
    assert "dummy-fallback" in metrics
    assert metrics["dummy-primary"]["failed_calls"] == 2
    assert metrics["dummy-fallback"]["successful_calls"] == 2


@pytest.mark.asyncio
async def test_ollama_provider_timeout_and_retry():
    """Test Ollama provider respects timeout and retry config."""
    from ses.core.providers import OllamaEmbeddingProvider, ProviderConfig

    config = ProviderConfig(
        name="ollama-test",
        timeout=0.1,
        max_retries=2,
        retry_backoff=0.05
    )

    # Provider pointing to non-existent server
    provider = OllamaEmbeddingProvider(
        base_url="http://localhost:9999",
        model="test",
        config=config
    )

    with pytest.raises(Exception):
        await provider.embed(["test"])

    # Should have retried
    assert provider.metrics.failed_calls >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Make tests/conftest resilient when legacy RAG modules were removed."""

import os
import sys
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

os.environ.setdefault("DEBUG", "true")

# Soft-mock optional deps only when they are not actually installed.
for _mod in (
    "qdrant_client",
    "qdrant_client.http",
    "sentence_transformers",
    "jas_vector_core",
    "redis",
    "redis.asyncio",
):
    if _mod in sys.modules:
        continue
    try:
        __import__(_mod)
    except ImportError:
        sys.modules[_mod] = MagicMock()


@pytest.fixture(autouse=True)
def mock_external_dependencies(request):
    if request.node.get_closest_marker("integration"):
        yield
        return

    mock_router = MagicMock()
    mock_router.embed = AsyncMock(return_value=[[0.1] * 384])
    mock_router.embed_query = AsyncMock(return_value=[0.1] * 384)
    mock_router.get_primary_provider = MagicMock()
    mock_router.get_primary_provider.return_value.dimension = 384
    mock_router.get_primary_provider.return_value.model_name = "test-model"
    mock_router.get_provider_metrics = MagicMock(return_value={})

    mock_qdrant = MagicMock()
    mock_qdrant.get_collection = AsyncMock()
    mock_qdrant.create_collection = AsyncMock()
    mock_qdrant.upsert = AsyncMock()
    mock_res = MagicMock()
    mock_res.points = []
    mock_qdrant.query_points = AsyncMock(return_value=mock_res)
    mock_qdrant.query_batch_points = AsyncMock(return_value=[])
    mock_qdrant.retrieve = AsyncMock(return_value=[])
    mock_qdrant.delete = AsyncMock()
    mock_qdrant.delete_collection = AsyncMock()

    mock_redis = AsyncMock()
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.sadd = AsyncMock()
    mock_redis.smembers = AsyncMock(return_value=set())
    mock_redis.keys = AsyncMock(return_value=[])
    mock_redis.delete = AsyncMock()
    mock_redis.close = AsyncMock()
    mock_redis.pipeline = MagicMock(
        return_value=AsyncMock(
            lpush=MagicMock(),
            ltrim=MagicMock(),
            zincrby=MagicMock(),
            execute=AsyncMock(),
        )
    )

    patches = []
    # Only patch modules that still exist after the SaaS extract.
    try:
        import ses.core.vector_store  # noqa: F401

        patches.append(
            patch("ses.core.vector_store.AsyncQdrantClient", return_value=mock_qdrant)
        )
    except Exception:
        pass

    try:
        import ses.core.rag  # noqa: F401

        patches.append(patch("ses.core.rag.get_provider_router", return_value=mock_router))
        patches.append(patch("ses.core.rag.redis.Redis", return_value=mock_redis))
    except Exception:
        pass

    # Enter all patches
    entered = []
    try:
        for p in patches:
            entered.append(p)
            p.start()
        yield {
            "router": mock_router,
            "qdrant": mock_qdrant,
            "redis": mock_redis,
        }
    finally:
        for p in reversed(entered):
            p.stop()

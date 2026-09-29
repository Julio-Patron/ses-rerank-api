import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

os.environ.setdefault("DEBUG", "true")

@pytest.fixture(autouse=True)
def mock_external_dependencies(request):
    if request.node.get_closest_marker("integration"):
        # Don't mock for integration tests
        yield
        return

    # 1. Mock Provider Router with embedding methods
    mock_router = MagicMock()
    mock_router.embed = AsyncMock(return_value=[[0.1] * 384])
    mock_router.embed_query = AsyncMock(return_value=[0.1] * 384)
    mock_router.get_primary_provider = MagicMock()
    mock_router.get_primary_provider.return_value.dimension = 384
    mock_router.get_primary_provider.return_value.model_name = "test-model"
    mock_router.get_provider_metrics = MagicMock(return_value={})
    
    # 2. Mock AsyncQdrantClient
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
    
    # 3. Mock Redis
    mock_redis = AsyncMock()
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.sadd = AsyncMock()
    mock_redis.smembers = AsyncMock(return_value=set())
    mock_redis.keys = AsyncMock(return_value=[])
    mock_redis.delete = AsyncMock()
    mock_redis.close = AsyncMock()
    mock_redis.pipeline = MagicMock(return_value=AsyncMock(
        lpush=MagicMock(), ltrim=MagicMock(), zincrby=MagicMock(), execute=AsyncMock()
    ))
    
    # Apply patches
    with patch("ses.core.rag.get_provider_router", return_value=mock_router), \
         patch("ses.core.vector_store.AsyncQdrantClient", return_value=mock_qdrant), \
         patch("ses.core.rag.redis.Redis", return_value=mock_redis):
        
        yield {
            "router": mock_router,
            "qdrant": mock_qdrant,
            "redis": mock_redis
        }

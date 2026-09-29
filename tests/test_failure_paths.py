"""Real loopback failure-path checks for external service clients."""

import pytest
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis as AsyncRedisClient
from redis.exceptions import RedisError

from ses.core.llm import LocalLLMProvider


@pytest.mark.asyncio
async def test_qdrant_connection_failure_is_observable(unused_tcp_port):
    client = AsyncQdrantClient(
        url=f"http://127.0.0.1:{unused_tcp_port}",
        check_compatibility=False,
    )
    try:
        with pytest.raises(Exception):
            await client.get_collections()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_redis_connection_failure_is_observable(unused_tcp_port):
    client = AsyncRedisClient(
        host="127.0.0.1",
        port=unused_tcp_port,
        socket_connect_timeout=0.25,
        socket_timeout=0.25,
    )
    try:
        with pytest.raises(RedisError):
            await client.ping()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_ollama_connection_failure_returns_documented_fallback(unused_tcp_port):
    provider = LocalLLMProvider(model_override="test-model")
    provider.ollama_url = f"http://127.0.0.1:{unused_tcp_port}/api/generate"

    result = await provider.generate_answer(
        query="test query",
        context_docs=[{"text": "test context"}],
    )

    assert result == (
        "No fue posible generar una respuesta con el proveedor LLM local. "
        "Verifique que Ollama esté en ejecución."
    )

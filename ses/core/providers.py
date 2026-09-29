"""
Embedding provider abstraction with fallback, timeout, retry, and circuit breaker.

This module implements the provider routing pattern for SES:
- Abstract EmbeddingProvider interface
- Local SentenceTransformer provider (default)
- Ollama provider (optional, for remote embeddings)
- Dummy provider (for testing fallback behavior)
- ProviderRouter with circuit breaker, timeout, and retry logic
"""

import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class ProviderState(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OPEN = "open"  # Circuit breaker open - failing fast


@dataclass
class ProviderConfig:
    name: str
    timeout: float = 30.0
    max_retries: int = 2
    retry_backoff: float = 1.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: float = 60.0


@dataclass
class ProviderMetrics:
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    consecutive_failures: int = 0
    last_failure_time: float = 0
    last_success_time: float = 0
    state: ProviderState = ProviderState.HEALTHY


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self.metrics = ProviderMetrics()

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts."""
        pass

    @abstractmethod
    async def embed_query(self, query: str) -> List[float]:
        """Generate embedding for a single query."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model name for identification."""
        pass

    def is_healthy(self) -> bool:
        return self.metrics.state == ProviderState.HEALTHY

    def record_success(self):
        self.metrics.total_calls += 1
        self.metrics.successful_calls += 1
        self.metrics.consecutive_failures = 0
        self.metrics.last_success_time = time.monotonic()
        if self.metrics.state == ProviderState.DEGRADED:
            self.metrics.state = ProviderState.HEALTHY
            logger.info("Provider %s recovered to HEALTHY", self.config.name)

    def record_failure(self):
        self.metrics.total_calls += 1
        self.metrics.failed_calls += 1
        self.metrics.consecutive_failures += 1
        self.metrics.last_failure_time = time.monotonic()

        if self.metrics.consecutive_failures >= self.config.circuit_breaker_threshold:
            if self.metrics.state != ProviderState.OPEN:
                self.metrics.state = ProviderState.OPEN
                logger.warning(
                    "Circuit breaker OPEN for provider %s after %d consecutive failures",
                    self.config.name,
                    self.metrics.consecutive_failures,
                )
        elif self.metrics.consecutive_failures >= self.config.circuit_breaker_threshold // 2:
            if self.metrics.state == ProviderState.HEALTHY:
                self.metrics.state = ProviderState.DEGRADED
                logger.warning(
                    "Provider %s DEGRADED (%d/%d failures)",
                    self.config.name,
                    self.metrics.consecutive_failures,
                    self.config.circuit_breaker_threshold,
                )

    def maybe_reset_circuit(self) -> bool:
        """Check if circuit breaker should be reset (half-open test)."""
        if self.metrics.state == ProviderState.OPEN:
            if time.monotonic() - self.metrics.last_failure_time > self.config.circuit_breaker_timeout:
                self.metrics.state = ProviderState.DEGRADED
                logger.info("Circuit breaker HALF-OPEN for provider %s (testing recovery)", self.config.name)
                return True
        return False


class LocalSentenceTransformerProvider(EmbeddingProvider):
    """Local SentenceTransformer embedding provider (CPU/GPU)."""

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: str = "cpu",
        config: Optional[ProviderConfig] = None,
    ):
        cfg = config or ProviderConfig(name=f"local-{model_name}", timeout=30.0)
        super().__init__(cfg)
        self._model_name = model_name
        self._device = device
        self._model: Optional[SentenceTransformer] = None

    def _ensure_model(self):
        if self._model is None:
            logger.info("Loading local embedding model: %s on %s", self._model_name, self._device)
            self._model = SentenceTransformer(self._model_name, device=self._device)

    async def embed(self, texts: List[str]) -> List[List[float]]:
        self._ensure_model()
        try:
            embeddings = await asyncio.to_thread(self._model.encode, texts, convert_to_numpy=True)
            if isinstance(embeddings, np.ndarray):
                embeddings = embeddings.tolist()
            self.record_success()
            return embeddings
        except Exception as e:
            self.record_failure()
            logger.error("Local provider embed failed: %s", e)
            raise

    async def embed_query(self, query: str) -> List[float]:
        self._ensure_model()
        try:
            embedding = await asyncio.to_thread(self._model.encode, query, convert_to_numpy=True)
            if isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()
            self.record_success()
            return embedding
        except Exception as e:
            self.record_failure()
            logger.error("Local provider embed_query failed: %s", e)
            raise

    @property
    def dimension(self) -> int:
        self._ensure_model()
        get_dimension = getattr(self._model, "get_embedding_dimension", None)
        if not callable(get_dimension):
            get_dimension = self._model.get_sentence_embedding_dimension

        dimension = get_dimension()
        if dimension is None:
            raise RuntimeError(
                f"Embedding model {self._model_name!r} did not report a dimension."
            )
        return int(dimension)

    @property
    def model_name(self) -> str:
        return self._model_name


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Ollama HTTP embedding provider."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        config: Optional[ProviderConfig] = None,
    ):
        cfg = config or ProviderConfig(name=f"ollama-{model}", timeout=60.0, max_retries=3)
        super().__init__(cfg)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._dimension: Optional[int] = None
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.config.timeout)
        return self._client

    async def _discover_dimension(self) -> int:
        if self._dimension is not None:
            return self._dimension
        try:
            client = await self._get_client()
            resp = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": "test"},
            )
            resp.raise_for_status()
            data = resp.json()
            self._dimension = len(data.get("embedding", []))
            return self._dimension
        except Exception:
            self._dimension = 768
            return self._dimension

    async def embed(self, texts: List[str]) -> List[List[float]]:
        client = await self._get_client()
        last_error = None

        for attempt in range(self.config.max_retries + 1):
            try:
                embeddings = []
                for text in texts:
                    resp = await client.post(
                        f"{self.base_url}/api/embeddings",
                        json={"model": self.model, "prompt": text},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    embeddings.append(data["embedding"])

                if self._dimension is None:
                    self._dimension = len(embeddings[0]) if embeddings else 768

                self.record_success()
                return embeddings

            except Exception as e:
                last_error = e
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_backoff * (attempt + 1))

        self.record_failure()
        logger.error("Ollama provider embed failed after retries: %s", last_error)
        raise last_error

    async def embed_query(self, query: str) -> List[float]:
        client = await self._get_client()
        last_error = None

        for attempt in range(self.config.max_retries + 1):
            try:
                resp = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": query},
                )
                resp.raise_for_status()
                data = resp.json()
                embedding = data["embedding"]

                if self._dimension is None:
                    self._dimension = len(embedding)

                self.record_success()
                return embedding

            except Exception as e:
                last_error = e
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_backoff * (attempt + 1))

        self.record_failure()
        logger.error("Ollama provider embed_query failed after retries: %s", last_error)
        raise last_error

    @property
    def dimension(self) -> int:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return self._dimension or 768
        except RuntimeError:
            pass
        return self._dimension or 768

    @property
    def model_name(self) -> str:
        return f"ollama:{self.model}"

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class DummyEmbeddingProvider(EmbeddingProvider):
    """Dummy provider that always fails - for testing fallback behavior."""

    def __init__(self, config: Optional[ProviderConfig] = None, should_fail: bool = True):
        cfg = config or ProviderConfig(name="dummy-fail", timeout=1.0, max_retries=0)
        super().__init__(cfg)
        self._should_fail = should_fail
        self._dimension = 384

    async def embed(self, texts: List[str]) -> List[List[float]]:
        if self._should_fail:
            self.record_failure()
            raise RuntimeError("Dummy provider configured to fail")
        self.record_success()
        return [[0.0] * self._dimension for _ in texts]

    async def embed_query(self, query: str) -> List[float]:
        if self._should_fail:
            self.record_failure()
            raise RuntimeError("Dummy provider configured to fail")
        self.record_success()
        return [0.0] * self._dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return "dummy"


class ProviderRouter:
    """
    Routes embedding requests through a chain of providers with fallback.

    Features:
    - Ordered provider chain (primary -> fallbacks)
    - Circuit breaker per provider
    - Timeout and retry per provider
    - Automatic recovery testing (half-open state)
    - Observable metrics per provider
    """

    def __init__(self, providers: List[EmbeddingProvider]):
        if not providers:
            raise ValueError("At least one provider required")
        self.providers = providers
        self._primary = providers[0]

    async def embed(self, texts: List[str]) -> List[List[float]]:
        last_error = None

        for provider in self.providers:
            if provider.maybe_reset_circuit():
                logger.info("Testing recovered provider: %s", provider.config.name)

            if provider.metrics.state == ProviderState.OPEN:
                logger.debug("Skipping provider %s (circuit OPEN)", provider.config.name)
                continue

            try:
                logger.debug("Trying provider: %s", provider.config.name)
                failed_calls_before = provider.metrics.failed_calls
                result = await asyncio.wait_for(
                    provider.embed(texts),
                    timeout=provider.config.timeout,
                )
                logger.info("Embedding succeeded via provider: %s", provider.config.name)
                return result
            except asyncio.TimeoutError:
                last_error = TimeoutError(f"Provider {provider.config.name} timed out")
                if provider.metrics.failed_calls == failed_calls_before:
                    provider.record_failure()
                logger.warning("Provider %s timed out", provider.config.name)
            except Exception as e:
                last_error = e
                if provider.metrics.failed_calls == failed_calls_before:
                    provider.record_failure()
                logger.warning("Provider %s failed: %s", provider.config.name, e)

        logger.error("All providers failed for embed")
        raise last_error or RuntimeError("All embedding providers failed")

    async def embed_query(self, query: str) -> List[float]:
        last_error = None

        for provider in self.providers:
            if provider.maybe_reset_circuit():
                logger.info("Testing recovered provider: %s", provider.config.name)

            if provider.metrics.state == ProviderState.OPEN:
                logger.debug("Skipping provider %s (circuit OPEN)", provider.config.name)
                continue

            try:
                logger.debug("Trying provider for query: %s", provider.config.name)
                failed_calls_before = provider.metrics.failed_calls
                result = await asyncio.wait_for(
                    provider.embed_query(query),
                    timeout=provider.config.timeout,
                )
                logger.info("Query embedding succeeded via provider: %s", provider.config.name)
                return result
            except asyncio.TimeoutError:
                last_error = TimeoutError(f"Provider {provider.config.name} timed out")
                if provider.metrics.failed_calls == failed_calls_before:
                    provider.record_failure()
                logger.warning("Provider %s timed out", provider.config.name)
            except Exception as e:
                last_error = e
                if provider.metrics.failed_calls == failed_calls_before:
                    provider.record_failure()
                logger.warning("Provider %s failed: %s", provider.config.name, e)

        logger.error("All providers failed for embed_query")
        raise last_error or RuntimeError("All embedding providers failed")

    def get_primary_provider(self) -> EmbeddingProvider:
        return self._primary

    def get_provider_metrics(self) -> Dict[str, Dict[str, Any]]:
        return {
            p.config.name: {
                "state": p.metrics.state.value,
                "total_calls": p.metrics.total_calls,
                "successful_calls": p.metrics.successful_calls,
                "failed_calls": p.metrics.failed_calls,
                "consecutive_failures": p.metrics.consecutive_failures,
            }
            for p in self.providers
        }

    async def close(self):
        for provider in self.providers:
            if hasattr(provider, "close") and callable(provider.close):
                await provider.close()


def create_default_router() -> ProviderRouter:
    """Create the default provider router from environment configuration."""
    model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    device = os.getenv("EMBEDDING_DEVICE", "cpu")
    ollama_url = os.getenv("OLLAMA_BASE_URL")
    ollama_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

    providers: List[EmbeddingProvider] = []

    primary = LocalSentenceTransformerProvider(model_name=model_name, device=device)
    providers.append(primary)

    if ollama_url:
        ollama = OllamaEmbeddingProvider(base_url=ollama_url, model=ollama_model)
        providers.append(ollama)
        logger.info("Provider chain: %s -> %s", primary.config.name, ollama.config.name)
    else:
        logger.info("Provider chain: %s (no Ollama configured)", primary.config.name)

    return ProviderRouter(providers)


def create_test_router(primary_should_fail: bool = False) -> ProviderRouter:
    """Create a deterministic router that never loads an external model."""
    primary = DummyEmbeddingProvider(
        config=ProviderConfig(name="dummy-primary", timeout=1.0, max_retries=0),
        should_fail=primary_should_fail,
    )
    fallback = DummyEmbeddingProvider(
        config=ProviderConfig(name="dummy-fallback", timeout=1.0, max_retries=0),
        should_fail=False,
    )
    return ProviderRouter([primary, fallback])

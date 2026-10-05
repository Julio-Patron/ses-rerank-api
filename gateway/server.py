import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    Security,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field

from gateway.database import get_database_adapter
from ses.config import (
    DEBUG,
    PUBLIC_API_URL,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
    RERANK_INTRA_THREADS,
    RERANK_MAX_TOKENS,
    RERANK_MODEL_DIR,
    RERANK_MODEL_FILE,
    RERANK_QUEUE_TIMEOUT_SECONDS,
)
from ses.services.rerank_queue import (
    ERROR_INVALID_REQUEST,
    HEARTBEAT_KEY,
    QUEUE_KEY,
    result_key,
)
from ses.services.reranker import InvalidRerankRequest, RerankerService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ses_enterprise_gateway")

_LEGACY_COMPROMISED_ADMIN_KEY = "ses_dev_secret_key"
_MIN_ADMIN_KEY_LENGTH = 32

# One credit covers up to this many documents in a /v1/rerank call.
DOCUMENTS_PER_CREDIT = 25
MAX_DOCUMENTS_PER_REQUEST = 1000
# Cache TTLs for rerank results (seconds).
IDEMPOTENCY_TTL_SECONDS = 86400
DEDUP_TTL_SECONDS = 60


def require_gateway_admin_key() -> str:
    """Return a configured bootstrap key or fail before serving traffic."""
    admin_key = os.getenv("GATEWAY_ADMIN_KEY", "").strip()
    if not admin_key:
        raise RuntimeError(
            "GATEWAY_ADMIN_KEY is required. Run scripts/rotate_local_secrets.py "
            "for local development or inject it through a production secret manager."
        )
    if hmac.compare_digest(admin_key, _LEGACY_COMPROMISED_ADMIN_KEY):
        raise RuntimeError("GATEWAY_ADMIN_KEY uses the revoked legacy development key.")
    if admin_key.lower().startswith(("replace_", "change_me")):
        raise RuntimeError("GATEWAY_ADMIN_KEY still contains an example placeholder.")
    if len(admin_key) < _MIN_ADMIN_KEY_LENGTH:
        raise RuntimeError(
            f"GATEWAY_ADMIN_KEY must contain at least {_MIN_ADMIN_KEY_LENGTH} characters."
        )
    return admin_key


def configured_cors_origins() -> List[str]:
    raw_origins = (
        os.getenv("GATEWAY_CORS_ORIGINS", "").strip()
        or os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
        or (
            "http://127.0.0.1:8000,http://localhost:8000,"
            "http://127.0.0.1:3000,http://localhost:3000"
        )
    )
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    if "*" in origins:
        raise RuntimeError("GATEWAY_CORS_ORIGINS cannot contain a wildcard origin.")
    return origins


# In-process engine: serves requests when no worker is online and is the
# fallback when the Redis queue fails.
reranker_service: Optional[RerankerService] = None


@asynccontextmanager
async def gateway_lifespan(_app: FastAPI):
    """Initialize persistent Gateway state before accepting traffic."""
    global redis_available
    global reranker_service

    try:
        if os.path.exists(os.path.join(RERANK_MODEL_DIR, RERANK_MODEL_FILE)):
            reranker_service = RerankerService(
                RERANK_MODEL_DIR,
                model_file=RERANK_MODEL_FILE,
                max_length=RERANK_MAX_TOKENS,
                intra_threads=RERANK_INTRA_THREADS,
            )
            logger.info("Initialized ONNX cross-encoder from %s", RERANK_MODEL_DIR)
        else:
            logger.warning(
                "Model %s not found in %s. Run scripts/download_onnx.py; reranking is disabled.",
                RERANK_MODEL_FILE,
                RERANK_MODEL_DIR,
            )
    except Exception as e:
        logger.error(f"Failed to load RerankerService: {e}")

    if redis_client is not None:
        try:
            await redis_client.ping()
            redis_available = True
            logger.info("Connected to Redis for rate limiting, caching and the worker queue.")
        except Exception as e:
            redis_available = False
            logger.warning(f"Redis ping failed: {e}. Falling back to in-memory limiters.")

    db = get_database_adapter()
    await db.connect()

    await db.revoke_api_key(_LEGACY_COMPROMISED_ADMIN_KEY)
    if redis_available:
        legacy_hash = hashlib.sha256(_LEGACY_COMPROMISED_ADMIN_KEY.encode()).hexdigest()
        try:
            await redis_client.delete(f"gateway:key:{legacy_hash}")
        except Exception:
            pass

    await db.bootstrap_admin_key(require_gateway_admin_key())
    yield


app = FastAPI(
    title="SES Rerank API",
    description=(
        "Multilingual cross-encoder reranking for RAG pipelines and AI agents. "
        "Send the candidates your retriever found; get back the most relevant ones "
        "with 0-1 relevance scores, so you pass fewer, better documents to your LLM."
    ),
    version="1.0.0",
    lifespan=gateway_lifespan,
)

# CORS Middleware for client dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

redis_available = False
redis_client = None
# Separate client for BLPOP: a short socket timeout would abort the blocking
# wait for a worker reply long before RERANK_QUEUE_TIMEOUT_SECONDS.
redis_queue_client = None

_HEALTH_PROBE_TIMEOUT_SECONDS = 2.0

try:
    import redis.asyncio as redis

    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD or None,
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )
    redis_queue_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD or None,
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=RERANK_QUEUE_TIMEOUT_SECONDS + 5,
    )
except Exception as e:
    redis_available = False
    logger.warning(f"Redis client could not be initialized: {e}. Using in-memory limiters.")


async def _probe_redis() -> bool:
    """Probe the configured Redis client even after an earlier failed ping."""
    if redis_client is None:
        return False
    try:
        await asyncio.wait_for(redis_client.ping(), timeout=_HEALTH_PROBE_TIMEOUT_SECONDS)
        return True
    except Exception:
        return False


async def _probe_database() -> bool:
    try:
        await asyncio.wait_for(
            get_database_adapter().ping(), timeout=_HEALTH_PROBE_TIMEOUT_SECONDS
        )
        return True
    except Exception:
        return False


async def _worker_online() -> bool:
    """True when at least one worker.py has refreshed its heartbeat recently."""
    if not redis_available or redis_client is None:
        return False
    try:
        return bool(await redis_client.exists(HEARTBEAT_KEY))
    except Exception:
        return False


async def _dependency_health() -> Dict[str, Any]:
    redis_ok, database_ok, worker_ok = await asyncio.gather(
        _probe_redis(), _probe_database(), _worker_online()
    )
    engine_ok = reranker_service is not None
    # Redis is optional only in DEBUG, mirroring the rate limiter's fail-closed rule.
    ready = engine_ok and database_ok and (redis_ok or DEBUG)
    return {
        "status": "healthy" if ready else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "services": {
            "reranker": "loaded" if engine_ok else "not_loaded",
            "database": "connected" if database_ok else "disconnected",
            "redis": "connected" if redis_ok else "disconnected",
            "rerank_worker": "online" if worker_ok else "offline",
        },
    }


# --- MIDDLEWARES & AUTHENTICATOR ADAPTER ---


async def get_api_key_details(api_key: str = Depends(API_KEY_HEADER)) -> Dict[str, Any]:
    """
    Adapter Pattern for API Key Verification.
    Validates api_key against Redis cache, with automatic miss query to database.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API Key in header X-API-Key"
        )

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    # 1. Check Redis Cache
    if redis_available:
        try:
            redis_key_data = await redis_client.get(f"gateway:key:{key_hash}")
            if redis_key_data:
                return json.loads(redis_key_data)
        except Exception as e:
            logger.error(f"Redis get key error: {e}")

    # 2. Query Persistent SQL Database (SQLite/PostgreSQL)
    try:
        db = get_database_adapter()
        key_data = await db.get_api_key(key_hash)

        if key_data:
            # Sync to Redis cache (expire in 5 minutes)
            if redis_available:
                try:
                    await redis_client.setex(f"gateway:key:{key_hash}", 300, json.dumps(key_data))
                except Exception:
                    pass
            return key_data
    except Exception as e:
        logger.error(f"Database api key retrieval failed: {e}")

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired API Key")


async def check_rate_limit(key_data: Dict[str, Any]):
    api_key_hash = key_data["key"]  # SHA-256 hash
    rate_limit = key_data.get("rate_limit", 60)

    current_minute = int(time.time() // 60)

    if redis_available:
        try:
            redis_limit_key = f"gateway:rate:{api_key_hash}:{current_minute}"
            async with redis_client.pipeline(transaction=True) as pipe:
                pipe.incr(redis_limit_key)
                pipe.expire(redis_limit_key, 65)
                results = await pipe.execute()

            requests_count = results[0]
            if requests_count > rate_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Allowed: {rate_limit} req/min.",
                )
            return
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Redis rate limit error: {e}")

            if not DEBUG:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Rate limiting service unavailable.",
                )

    if not redis_available and not DEBUG:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiting service unavailable.",
        )

    # In-memory rate limiting fallback
    limit_key = f"{api_key_hash}:{current_minute}"

    # Prune old metrics keys
    pruned_limits = {
        k: v for k, v in in_memory_rate_limits.items() if k.endswith(str(current_minute))
    }
    in_memory_rate_limits.clear()
    in_memory_rate_limits.update(pruned_limits)

    count = in_memory_rate_limits.get(limit_key, 0) + 1
    in_memory_rate_limits[limit_key] = count

    if count > rate_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Allowed: {rate_limit} req/min.",
        )


in_memory_rate_limits = {}


async def log_request_metric(
    key_data: Dict[str, Any], endpoint: str, status_code: int, latency_ms: float, tokens: int = 0
):
    tenant_id = key_data.get("tenant_id")
    api_key_id = key_data.get("id")
    key_name = key_data.get("name")
    namespace = key_data.get("namespace")

    # 1. Log to persistent SQL database
    try:
        db = get_database_adapter()
        await db.log_usage(
            tenant_id=tenant_id,
            api_key_id=api_key_id,
            endpoint=endpoint,
            tokens=tokens,
            latency_ms=latency_ms,
        )
    except Exception as e:
        logger.error(f"Failed to log usage metrics to SQL Database: {e}")

    # 2. Redis dynamic charts / cache updates
    if redis_available:
        try:
            await redis_client.incr("gateway:metrics:total_requests")
            if status_code >= 400:
                await redis_client.incr("gateway:metrics:total_errors")
            if endpoint == "/v1/rerank":
                await redis_client.incr("gateway:metrics:total_reranks")

            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "key_name": key_name,
                "namespace": namespace,
                "endpoint": endpoint,
                "status_code": status_code,
                "latency_ms": latency_ms,
            }
            await redis_client.lpush("gateway:metrics:recent_logs", json.dumps(log_entry))
            await redis_client.ltrim("gateway:metrics:recent_logs", 0, 99)  # Keep 100 logs
        except Exception as e:
            logger.error(f"Redis metrics update failed: {e}")


# --- REQUEST & RESPONSE SCHEMAS ---


class APIKeyCreatePayload(BaseModel):
    name: str = Field(..., description="Descriptive name for the API key client")
    namespace: str = Field("personal_default", description="Logical namespace of the key")
    rate_limit: int = Field(60, description="Maximum requests per minute")
    role: str = Field("client", description="Security role (admin or client)")


class DocumentObj(BaseModel):
    text: str = Field(..., description="Document text that will be scored against the query.")
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Arbitrary JSON metadata. Used by `jsonlogic_filter` and echoed back.",
    )


class RerankRequest(BaseModel):
    query: str = Field(..., description="Search query or question the documents should answer.")
    documents: List[Union[str, DocumentObj]] = Field(
        ...,
        description=(
            f"Candidate documents (1-{MAX_DOCUMENTS_PER_REQUEST}), either plain strings or "
            "objects with `text` and optional `metadata`. Each call costs one credit per "
            f"{DOCUMENTS_PER_CREDIT} documents."
        ),
    )
    top_n: int = Field(
        5, description="How many of the most relevant documents to return (1-len(documents))."
    )
    return_documents: bool = Field(
        True, description="Include each returned document in the response, not just its index."
    )
    jsonlogic_filter: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Optional JSONLogic rule evaluated against each document's `metadata` before "
            'scoring; only documents where it is `true` are ranked. Example: {">=": '
            '[{"var": "year"}, 2024]}'
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query": "¿Cuántos días de vacaciones tiene un trabajador con un año?",
                    "documents": [
                        "El aguinaldo deberá pagarse antes del 20 de diciembre.",
                        {
                            "text": "Con un año de servicio corresponden doce días de vacaciones.",
                            "metadata": {"source": "LFT", "year": 2023},
                        },
                    ],
                    "top_n": 1,
                }
            ]
        }
    }


class RerankDocumentResult(BaseModel):
    index: int = Field(..., description="Position of the document in the request's `documents`.")
    relevance_score: float = Field(
        ..., description="Relevance between 0 and 1 (sigmoid of the cross-encoder logit)."
    )
    document: Optional[Union[str, DocumentObj]] = Field(
        None, description="The document as sent, when `return_documents` is true."
    )


class RerankTokenMetrics(BaseModel):
    input_tokens: int = Field(
        ..., description="Estimated LLM tokens of the query plus every input document."
    )
    output_tokens: int = Field(
        ..., description="Estimated LLM tokens of the query plus the returned documents."
    )
    saved_tokens: int = Field(
        ..., description="input_tokens - output_tokens: tokens you no longer send to your LLM."
    )
    savings_percentage: float = Field(..., description="saved_tokens as a percentage of input.")


class RerankMeta(BaseModel):
    tokens: RerankTokenMetrics
    credits_deducted: int = Field(..., description="Credits charged for this call.")
    credits_remaining: int = Field(..., description="Credits left on the API key.")
    tokens_saved_total: int = Field(..., description="Tokens saved by this key across all calls.")
    latency_ms: float = Field(..., description="Time spent by the Gateway on this call.")
    cached: bool = Field(
        ..., description="True when served from the idempotency/deduplication cache."
    )


class RerankResponse(BaseModel):
    results: List[RerankDocumentResult] = Field(
        ..., description="The `top_n` most relevant documents, highest score first."
    )
    meta: RerankMeta


class SelfHealingErrorBody(BaseModel):
    error: str = Field(..., description="Machine-readable error code.")
    message: str = Field(..., description="Explanation an LLM agent can use to fix the call.")
    retryable: bool = Field(..., description="True when the call can succeed once corrected.")


class ErrorDetail(BaseModel):
    detail: str


class SignupRequest(BaseModel):
    email: str = Field(..., description="Email address for self-serve registration")


class SignupResponse(BaseModel):
    api_key: str
    credits: int
    plan_tier: str
    quickstart: Dict[str, str]


class UsageResponse(BaseModel):
    account_name: str
    plan_tier: str
    credits_remaining: int
    tokens_saved_total: int
    rate_limit: int


class SelfHealingError(Exception):
    """A client error answered with a message an LLM agent can act on."""

    def __init__(self, error: str, message: str):
        super().__init__(message)
        self.error = error
        self.message = message


@app.exception_handler(SelfHealingError)
async def _self_healing_error_handler(_request: Request, exc: SelfHealingError):
    return JSONResponse(
        status_code=400,
        content={"error": exc.error, "message": exc.message, "retryable": True},
    )


# --- API ROUTES ---

AUTHORIZATION_HEADER = APIKeyHeader(name="Authorization", auto_error=False)


def parse_authorization_api_key(authorization: Optional[str]) -> str:
    """Extract an API key from an Authorization header.

    Accepts ``Bearer <token>`` (scheme case-insensitive) or a raw token with no
    scheme. Rejects empty tokens and unknown schemes so the raw header value is
    never treated as a key when a non-Bearer scheme is present.
    """
    if not authorization or not authorization.strip():
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    value = authorization.strip()
    parts = value.split(None, 1)
    if len(parts) == 2:
        scheme, token = parts[0], parts[1].strip()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Unsupported Authorization scheme")
        if not token:
            raise HTTPException(status_code=401, detail="Empty Bearer token")
        return token

    # Single token: "Bearer" alone is empty; otherwise accept raw API key.
    if value.lower() == "bearer":
        raise HTTPException(status_code=401, detail="Empty Bearer token")
    return value


def validate_rerank_payload(payload: RerankRequest) -> None:
    count = len(payload.documents)
    if count == 0:
        raise SelfHealingError(
            "invalid_parameters",
            "The 'documents' list cannot be empty. Please provide at least one document "
            "to rerank.",
        )
    if count > MAX_DOCUMENTS_PER_REQUEST:
        raise SelfHealingError(
            "invalid_parameters",
            f"At most {MAX_DOCUMENTS_PER_REQUEST} documents can be reranked per call; got "
            f"{count}. Split the documents into several calls and retry.",
        )
    if payload.top_n < 1:
        raise SelfHealingError(
            "invalid_parameters",
            f"The parameter 'top_n' ({payload.top_n}) must be at least 1. Please set 'top_n' "
            f"to an integer between 1 and {count} and retry.",
        )
    if payload.top_n > count:
        raise SelfHealingError(
            "invalid_parameters",
            f"The parameter 'top_n' ({payload.top_n}) cannot be greater than the number of "
            f"provided documents ({count}). Please set 'top_n' to an integer between 1 and "
            f"{count} and retry.",
        )


def documents_as_json(documents: List[Union[str, DocumentObj]]) -> List[Union[str, Dict]]:
    """One JSON-native shape for the cache key, the worker queue and the engine."""
    return [
        doc if isinstance(doc, str) else doc.model_dump(exclude_none=True) for doc in documents
    ]


def rerank_cache_key(
    tenant_id: str,
    payload: RerankRequest,
    documents: List[Union[str, Dict]],
    idempotency_key: Optional[str],
) -> str:
    if idempotency_key:
        return f"gateway:idempotency:{tenant_id}:{idempotency_key}"
    fingerprint = json.dumps(
        {
            "query": payload.query,
            "documents": documents,
            "top_n": payload.top_n,
            "jsonlogic_filter": payload.jsonlogic_filter,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    payload_hash = hashlib.sha256(fingerprint.encode()).hexdigest()
    return f"gateway:cache:rerank:{tenant_id}:{payload_hash}"


async def _rerank_in_process(
    query: str, documents: List, top_n: int, jsonlogic_filter: Optional[Dict]
) -> Dict[str, Any]:
    if reranker_service is None:
        raise HTTPException(status_code=503, detail="Reranker engine is not loaded")
    try:
        return await reranker_service.rerank(
            query=query, documents=documents, top_n=top_n, jsonlogic_filter=jsonlogic_filter
        )
    except InvalidRerankRequest as e:
        raise SelfHealingError("invalid_filter", f"The 'jsonlogic_filter' is invalid: {e}")


async def _rerank_via_queue(
    query: str, documents: List, top_n: int, jsonlogic_filter: Optional[Dict]
) -> Dict[str, Any]:
    task_id = str(uuid.uuid4())
    task = {
        "task_id": task_id,
        "query": query,
        "documents": documents,
        "top_n": top_n,
        "jsonlogic_filter": jsonlogic_filter,
    }
    await redis_client.rpush(QUEUE_KEY, json.dumps(task))
    reply = await redis_queue_client.blpop([result_key(task_id)], timeout=RERANK_QUEUE_TIMEOUT_SECONDS)
    if reply is None:
        raise HTTPException(status_code=504, detail="Reranking worker timeout")

    result = json.loads(reply[1])
    if "error" in result:
        if result.get("error_type") == ERROR_INVALID_REQUEST:
            raise SelfHealingError(
                "invalid_filter", f"The 'jsonlogic_filter' is invalid: {result['error']}"
            )
        raise HTTPException(status_code=500, detail="Reranking failed")
    return result


async def run_rerank(
    query: str, documents: List, top_n: int, jsonlogic_filter: Optional[Dict]
) -> Dict[str, Any]:
    """Send the task to a worker when one is online, otherwise rerank in-process."""
    if await _worker_online():
        try:
            return await _rerank_via_queue(query, documents, top_n, jsonlogic_filter)
        except (HTTPException, SelfHealingError):
            raise
        except Exception as e:
            logger.error(f"Redis queue error, reranking in-process: {e}")
    return await _rerank_in_process(query, documents, top_n, jsonlogic_filter)


_RERANK_ERROR_RESPONSES = {
    400: {"model": SelfHealingErrorBody, "description": "Invalid parameters or filter."},
    401: {"model": ErrorDetail, "description": "Missing or malformed Authorization header."},
    402: {"model": ErrorDetail, "description": "Not enough credits for this call."},
    403: {"model": ErrorDetail, "description": "Unknown or revoked API key."},
    429: {"model": ErrorDetail, "description": "Per-key rate limit exceeded."},
    503: {"model": ErrorDetail, "description": "Reranker engine or rate limiter unavailable."},
    504: {"model": ErrorDetail, "description": "No worker answered in time."},
}


@app.post(
    "/v1/rerank",
    response_model=RerankResponse,
    summary="Rerank documents by relevance to a query",
    responses=_RERANK_ERROR_RESPONSES,
)
async def api_rerank(
    payload: RerankRequest,
    api_key: str = Security(AUTHORIZATION_HEADER),
    idempotency_key: Optional[str] = Header(
        None,
        alias="Idempotency-Key",
        description="Replays within 24 h return the cached result instead of recomputing.",
    ),
):
    """Score every document against the query with a cross-encoder and return the
    `top_n` best. Authenticate with `Authorization: Bearer <api_key>`."""
    api_key = parse_authorization_api_key(api_key)

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    db = get_database_adapter()
    key_data = await db.get_api_key(key_hash)
    if not key_data:
        raise HTTPException(status_code=403, detail="Invalid API Key")

    await check_rate_limit(key_data)
    validate_rerank_payload(payload)

    credits_needed = -(-len(payload.documents) // DOCUMENTS_PER_CREDIT)
    if key_data.get("credits_remaining", 0) < credits_needed:
        raise HTTPException(status_code=402, detail="Insufficient credits")

    t0 = time.perf_counter()
    documents = documents_as_json(payload.documents)
    tenant_id = key_data.get("tenant_id", "default")

    result = None
    cache_key = None
    if redis_available:
        cache_key = rerank_cache_key(tenant_id, payload, documents, idempotency_key)
        try:
            cached_result = await redis_client.get(cache_key)
            if cached_result:
                result = json.loads(cached_result)
        except Exception as e:
            logger.error(f"Redis get cache error: {e}")
    cached = result is not None

    if result is None:
        result = await run_rerank(
            payload.query, documents, payload.top_n, payload.jsonlogic_filter
        )
        if cache_key:
            try:
                ttl = IDEMPOTENCY_TTL_SECONDS if idempotency_key else DEDUP_TTL_SECONDS
                await redis_client.setex(cache_key, ttl, json.dumps(result))
            except Exception as e:
                logger.error(f"Redis set cache error: {e}")

    token_metrics = result.get("meta", {}).get("token_metrics", {})
    tokens = RerankTokenMetrics(
        input_tokens=token_metrics.get("input_tokens", 0),
        output_tokens=token_metrics.get("output_tokens", 0),
        saved_tokens=token_metrics.get("saved_tokens", 0),
        savings_percentage=token_metrics.get("savings_percentage", 0.0),
    )

    try:
        update_res = await db.update_credits(key_hash, credits_needed, tokens.saved_tokens)
    except ValueError:
        # A concurrent call spent the credits between the check above and now.
        raise HTTPException(status_code=402, detail="Insufficient credits")

    results = [
        RerankDocumentResult(
            index=r["index"],
            relevance_score=r["relevance_score"],
            document=r["document"] if payload.return_documents else None,
        )
        for r in result.get("results", [])
    ]

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    meta = RerankMeta(
        tokens=tokens,
        credits_deducted=credits_needed,
        credits_remaining=update_res.get("credits_remaining", 0),
        tokens_saved_total=update_res.get("tokens_saved_total", 0),
        latency_ms=latency_ms,
        cached=cached,
    )

    asyncio.create_task(
        log_request_metric(key_data, "/v1/rerank", 200, latency_ms, tokens=tokens.input_tokens)
    )

    return RerankResponse(results=results, meta=meta)


@app.post("/v1/auth/signup", response_model=SignupResponse, summary="Self-serve registration")
async def api_signup(payload: SignupRequest):
    """
    Registers a new developer and issues a free API key with 1,000 credits.
    """
    db = get_database_adapter()
    try:
        result = await db.signup_by_email(payload.email)
        api_key = result["api_key"]

        curl_snippet = f"""curl -X POST "{PUBLIC_API_URL}/v1/rerank" \\
     -H "Authorization: Bearer {api_key}" \\
     -H "Content-Type: application/json" \\
     -d '{{
           "query": "Which clause talks about termination?",
           "documents": ["The contract is valid for 5 years.", "Termination is allowed with 30 days notice."],
           "top_n": 1
         }}'"""

        python_snippet = f"""from ses_langchain_compressor import SESRerankCompressor
from langchain.retrievers import ContextualCompressionRetriever

reranker = SESRerankCompressor(
    ses_api_key="{api_key}",
    ses_api_url="{PUBLIC_API_URL}/v1/rerank",
    top_n=3
)
compression_retriever = ContextualCompressionRetriever(
    base_compressor=reranker,
    base_retriever=your_vector_store.as_retriever(search_kwargs={{"k": 25}})
)"""

        return SignupResponse(
            api_key=api_key,
            credits=result["credits"],
            plan_tier=result["plan_tier"],
            quickstart={"curl": curl_snippet, "python_langchain": python_snippet},
        )
    except ValueError as e:
        if str(e) == "email_already_registered":
            raise HTTPException(status_code=400, detail="This email is already registered.")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/v1/usage", response_model=UsageResponse, summary="Check credit balance and savings")
async def api_usage(api_key: str = Security(AUTHORIZATION_HEADER)):
    """
    Returns the current usage metrics and remaining credits for the authenticated user.
    """
    api_key = parse_authorization_api_key(api_key)
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    db = get_database_adapter()
    usage = await db.get_usage(key_hash)

    if not usage:
        raise HTTPException(status_code=403, detail="Invalid API Key")

    return UsageResponse(**usage)


@app.get("/healthz", summary="Gateway process liveness")
async def gateway_liveness():
    """Return process liveness without touching any satellite dependency."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


@app.get("/readyz", summary="Gateway dependency readiness")
async def gateway_readiness():
    """Return 503 until the model is loaded and every required dependency answers."""
    health = await _dependency_health()
    return JSONResponse(
        status_code=200 if health["status"] == "healthy" else 503,
        content=health,
    )


@app.get("/api/v1/health", summary="Detailed dependency health")
async def api_health():
    """Report the state of the reranker engine, database, Redis and workers."""
    return await _dependency_health()


# --- ADMIN MONETIZATION & MANAGEMENT ROUTES ---


def verify_admin_key(key_data: Dict[str, Any] = Depends(get_api_key_details)):
    if key_data.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden. Admin privileges required."
        )
    return key_data


@app.get("/api/v1/admin/keys", summary="Admin endpoint to list API keys")
async def admin_list_keys(admin_data: Dict[str, Any] = Depends(verify_admin_key)):
    try:
        db = get_database_adapter()
        keys = await db.list_api_keys()
        return {"keys": keys}
    except Exception as e:
        logger.exception("Error listing keys:")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/admin/keys", summary="Admin endpoint to create API keys")
async def admin_create_key(
    payload: APIKeyCreatePayload, admin_data: Dict[str, Any] = Depends(verify_admin_key)
):
    try:
        db = get_database_adapter()
        result = await db.create_api_key(
            name=payload.name,
            namespace=payload.namespace,
            rate_limit=payload.rate_limit,
            role=payload.role,
        )

        # Save to Redis cache for instant activation
        if redis_available:
            new_key_data = result["key_details"]
            new_key_raw = result["key"]
            new_hash = hashlib.sha256(new_key_raw.encode()).hexdigest()
            try:
                await redis_client.setex(f"gateway:key:{new_hash}", 300, json.dumps(new_key_data))
            except Exception:
                pass

        logger.info(
            f"Created new API key for client '{payload.name}' in namespace '{payload.namespace}'"
        )
        return result
    except Exception as e:
        logger.exception("Error creating API key:")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/admin/keys/{key_to_delete}", summary="Admin endpoint to revoke API keys")
async def admin_delete_key(
    key_to_delete: str, admin_data: Dict[str, Any] = Depends(verify_admin_key)
):
    try:
        db = get_database_adapter()
        success = await db.revoke_api_key(key_to_delete)
        if not success:
            raise HTTPException(status_code=404, detail="API Key not found or already revoked.")

        # Delete from Redis cache
        if redis_available:
            try:
                # If a full key token is provided, delete its specific hash
                if key_to_delete.startswith("ses_") and len(key_to_delete) == 28:
                    key_hash = hashlib.sha256(key_to_delete.encode()).hexdigest()
                    await redis_client.delete(f"gateway:key:{key_hash}")
            except Exception as e:
                logger.error(f"Failed to clear key from Redis: {e}")

        logger.info("Revoked API key token.")
        return {"status": "success", "message": "API Key revoked successfully."}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error revoking API key:")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/admin/analytics", summary="Aggregated business and usage analytics")
async def admin_analytics(admin_data: Dict[str, Any] = Depends(verify_admin_key)):
    try:
        db = get_database_adapter()
        analytics = await db.get_analytics()

        # Merge with Redis live data if available
        if redis_available:
            try:
                for field in ("total_requests", "total_errors", "total_reranks"):
                    live_value = await redis_client.get(f"gateway:metrics:{field}")
                    if live_value:
                        analytics[field] = int(live_value)
            except Exception as e:
                logger.error(f"Failed to fetch live Redis analytics: {e}")

        return analytics
    except Exception as e:
        logger.exception("Error getting admin analytics:")
        raise HTTPException(status_code=500, detail=str(e))


# --- STRIPE WEBHOOK ---
from gateway.stripe_webhook import router as stripe_webhook_router  # noqa: E402

app.include_router(stripe_webhook_router)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Security,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security.api_key import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from qdrant_client import AsyncQdrantClient

# Core imports
from ses.config import (
    OLLAMA_BASE_URL,
    QDRANT_API_KEY,
    QDRANT_URL,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
)

DEBUG = True
# Database imports
from gateway.database import get_database_adapter
from ses.services.reranker import RerankerService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ses_enterprise_gateway")

_LEGACY_COMPROMISED_ADMIN_KEY = "ses_dev_secret_key"
_MIN_ADMIN_KEY_LENGTH = 32


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


# Global instance
reranker_service = None

@asynccontextmanager
async def gateway_lifespan(_app: FastAPI):
    """Initialize persistent Gateway state before accepting traffic."""
    global redis_available
    global reranker_service
    
    # Initialize RerankerService
    model_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "model_onnx"))
    try:
        if os.path.exists(model_dir):
            reranker_service = RerankerService(model_dir)
            logger.info("🧠 Initialized ONNX CrossEncoder Engine.")
        else:
            logger.warning(f"⚠️ model_onnx directory not found at {model_dir}. Reranker will not work.")
    except Exception as e:
        logger.error(f"❌ Failed to load RerankerService: {e}")

    if redis_client is not None:
        try:
            await redis_client.ping()
            redis_available = True
            logger.info("🔌 Connected to Redis for Enterprise Rate Limiting & Cache.")
        except Exception as e:
            redis_available = False
            logger.warning(f"⚠️ Redis ping failed: {e}. Falling back to local/in-memory limiters.")

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
    title="SES Enterprise Gateway",
    description="Commercial API Layer for SES Offline RAG Engine",
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

# Helper to check Redis connection
redis_available = False
redis_client = None

_HEALTH_PROBE_TIMEOUT_SECONDS = 2.0

try:
    import redis.asyncio as redis
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )
except Exception as e:
    redis_available = False
    logger.warning(f"⚠️ Redis client could not be initialized: {e}. Using In-Memory limiters.")


async def _probe_qdrant() -> bool:
    """Probe Qdrant without constructing the RAG engine or embedding model."""
    client = None
    try:
        client = AsyncQdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
            timeout=_HEALTH_PROBE_TIMEOUT_SECONDS,
        )
        await asyncio.wait_for(
            client.get_collections(),
            timeout=_HEALTH_PROBE_TIMEOUT_SECONDS,
        )
        return True
    except Exception:
        return False
    finally:
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass


async def _probe_redis() -> bool:
    """Probe the configured Redis client even after an earlier failed ping."""
    if redis_client is None:
        return False
    try:
        await asyncio.wait_for(
            redis_client.ping(),
            timeout=_HEALTH_PROBE_TIMEOUT_SECONDS,
        )
        return True
    except Exception:
        return False


def _ollama_http_probe() -> bool:
    import urllib.request

    req = urllib.request.Request(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags")
    with urllib.request.urlopen(req, timeout=_HEALTH_PROBE_TIMEOUT_SECONDS) as response:
        return response.status == 200


async def _probe_ollama() -> bool:
    """Probe Ollama off the event loop using its stable tags endpoint."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_ollama_http_probe),
            timeout=_HEALTH_PROBE_TIMEOUT_SECONDS,
        )
    except Exception:
        return False


def _rust_acceleration_available() -> bool:
    """Return True when the native jas_vector_core extension is importable."""
    try:
        import jas_vector_core

        # Test suites may inject MagicMock placeholders into sys.modules.
        if type(jas_vector_core).__name__ == "MagicMock":
            return False
        fn = getattr(jas_vector_core, "cosine_similarity_search_numpy", None)
        return callable(fn) and type(fn).__name__ != "MagicMock"
    except Exception:
        return False


async def _dependency_health() -> Dict[str, Any]:
    qdrant_ok, redis_ok, ollama_ok = await asyncio.gather(
        _probe_qdrant(),
        _probe_redis(),
        _probe_ollama(),
    )
    ready = qdrant_ok and redis_ok and ollama_ok
    return {
        "status": "healthy" if ready else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "services": {
            "qdrant": "connected" if qdrant_ok else "disconnected",
            "redis": "connected" if redis_ok else "disconnected",
            "ollama_api": "connected" if ollama_ok else "disconnected",
            "rust_acceleration": "active" if _rust_acceleration_available() else "inactive",
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
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key in header X-API-Key"
        )
    
    # Calculate SHA-256 hash
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

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid or expired API Key"
    )

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
                    detail=f"Rate limit exceeded. Allowed: {rate_limit} req/min."
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
    pruned_limits = {k: v for k, v in in_memory_rate_limits.items() if k.endswith(str(current_minute))}
    in_memory_rate_limits.clear()
    in_memory_rate_limits.update(pruned_limits)
    
    count = in_memory_rate_limits.get(limit_key, 0) + 1
    in_memory_rate_limits[limit_key] = count
    
    if count > rate_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Allowed: {rate_limit} req/min."
        )

in_memory_rate_limits = {}

async def log_request_metric(key_data: Dict[str, Any], endpoint: str, status_code: int, latency_ms: float, tokens: int = 0):
    tenant_id = key_data.get("tenant_id")
    api_key_id = key_data.get("id")
    api_key_hash = key_data.get("key")
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
            latency_ms=latency_ms
        )
    except Exception as e:
        logger.error(f"Failed to log usage metrics to SQL Database: {e}")
        
    # 2. Redis dynamic charts / cache updates
    if redis_available:
        try:
            await redis_client.incr("gateway:metrics:total_requests")
            if status_code >= 400:
                await redis_client.incr("gateway:metrics:total_errors")
            if "search" in endpoint:
                await redis_client.incr("gateway:metrics:total_searches")
            elif "ingest" in endpoint:
                await redis_client.incr("gateway:metrics:total_ingestions")
                
            # Log to list
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "key_name": key_name,
                "namespace": namespace,
                "endpoint": endpoint,
                "status_code": status_code,
                "latency_ms": latency_ms
            }
            await redis_client.lpush("gateway:metrics:recent_logs", json.dumps(log_entry))
            await redis_client.ltrim("gateway:metrics:recent_logs", 0, 99) # Keep 100 logs
        except Exception as e:
            logger.error(f"Redis metrics update failed: {e}")


# --- REQUEST & RESPONSE SCHEMAS ---

class SearchRequestPayload(BaseModel):
    query: str = Field(..., description="Query string for search")
    top_k: int = Field(5, description="Number of results to return")
    threshold: float = Field(0.0, description="Minimum confidence score threshold")
    generate_answer: bool = Field(True, description="Generate natural language response using LLM")
    model_override: Optional[str] = Field(None, description="Override default Ollama model")

class IngestTextRequestPayload(BaseModel):
    text: str = Field(..., description="Raw text content to index")
    filename: str = Field(..., description="Simulated filename for the document")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata dictionary")

class APIKeyCreatePayload(BaseModel):
    name: str = Field(..., description="Descriptive name for the API key client")
    namespace: str = Field("personal_default", description="Isolate search directory namespace")
    rate_limit: int = Field(60, description="Maximum requests per minute")
    role: str = Field("client", description="Security role (admin or client)")

class DocumentObj(BaseModel):
    text: str
    metadata: Optional[Dict[str, Any]] = None

class RerankRequest(BaseModel):
    query: str = Field(..., description="Query string for reranking")
    documents: List[Union[str, DocumentObj]] = Field(..., description="List of documents to rerank")
    top_n: int = Field(5, description="Number of top documents to return")
    return_documents: bool = Field(True, description="Whether to include documents in response")
    jsonlogic_filter: Optional[Dict[str, Any]] = Field(None, description="Optional JSONLogic rule to pre-filter documents by their metadata")

class RerankDocumentResult(BaseModel):
    index: int
    relevance_score: float
    document: Optional[Union[str, DocumentObj]] = None

class RerankTokenMetrics(BaseModel):
    total_tokens: int

class RerankMeta(BaseModel):
    tokens: RerankTokenMetrics
    credits_deducted: int
    credits_remaining: int
    tokens_saved: int

class RerankResponse(BaseModel):
    results: List[RerankDocumentResult]
    meta: RerankMeta

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


@app.post("/v1/rerank", response_model=RerankResponse, summary="Rerank documents")
async def api_rerank(
    payload: RerankRequest, 
    api_key: str = Security(AUTHORIZATION_HEADER),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", description="Strict Idempotency key for network retries")
):
    api_key = parse_authorization_api_key(api_key)

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    db = get_database_adapter()
    key_data = await db.get_api_key(key_hash)
    if not key_data:
        raise HTTPException(status_code=403, detail="Invalid API Key")

    # 1. Rate Limiting (Phase 3)
    await check_rate_limit(key_data)

    # 2. Self-Healing Parameters Validation (Phase 3)
    if len(payload.documents) == 0:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_parameters",
                "message": "The 'documents' list cannot be empty. Please provide at least one document to rerank.",
                "retryable": True
            }
        )
    if payload.top_n > len(payload.documents):
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_parameters",
                "message": f"The parameter 'top_n' ({payload.top_n}) cannot be greater than the number of provided documents ({len(payload.documents)}). Please set 'top_n' to an integer between 1 and {len(payload.documents)} and retry.",
                "retryable": True
            }
        )

    credits_remaining = key_data.get("credits_remaining", 0)
    credits_needed = max(1, (len(payload.documents) + 24) // 25)
    
    if credits_remaining < credits_needed:
        raise HTTPException(status_code=402, detail="Insufficient credits")

    t0 = time.time()
    
    # 3. Redis Strict Idempotency & Deduplication
    tenant_id = key_data.get("tenant_id", "default")
    result = None
    cache_key = None

    if redis_available:
        if idempotency_key:
            # Idempotency based on explicitly provided client key (O(1) checking, zero CPU payload hashing)
            cache_key = f"gateway:idempotency:{tenant_id}:{idempotency_key}"
        else:
            # Fallback to payload hashing if no idempotency key provided
            payload_hash = hashlib.sha256((payload.query + "".join(payload.documents) + str(payload.top_n)).encode()).hexdigest()
            cache_key = f"gateway:cache:rerank:{tenant_id}:{payload_hash}"
            
        try:
            cached_result = await redis_client.get(cache_key)
            if cached_result:
                result = json.loads(cached_result)
        except Exception as e:
            logger.error(f"Redis get cache error: {e}")

    if not result:
        if reranker_service is None:
            raise HTTPException(status_code=500, detail="Reranker Engine is not initialized")
            
        # [MENSAGERÍA/COLAS]: Aquí en el futuro en lugar de await asyncio.to_thread sincrónico,
        # podríamos enviar la petición a una cola Celery/Redis y esperar el resultado usando pub/sub.
        result = await reranker_service.rerank(
            query=payload.query,
            documents=payload.documents,
            top_n=payload.top_n,
            jsonlogic_filter=payload.jsonlogic_filter
        )
        if redis_available and cache_key:
            try:
                # Cache for 24 hours if using idempotency key, else 60 seconds
                ttl = 86400 if idempotency_key else 60
                await redis_client.setex(cache_key, ttl, json.dumps(result))
            except Exception as e:
                logger.error(f"Redis set cache error: {e}")

    # Calculate tokens saved
    saved_tokens = result.get("meta", {}).get("token_metrics", {}).get("saved_tokens", 0)
    total_tokens = result.get("meta", {}).get("token_metrics", {}).get("input_tokens", 0)
    
    # Update credits
    update_res = await db.update_credits(key_hash, credits_needed, saved_tokens)
    
    final_credits_remaining = update_res.get("credits_remaining", 0)
    final_tokens_saved_total = update_res.get("tokens_saved_total", 0)

    # Prepare response
    docs_res = []
    for r in result.get("results", []):
        doc_text = r["document"] if payload.return_documents else None
        docs_res.append(RerankDocumentResult(
            index=r["index"],
            relevance_score=r["relevance_score"],
            document=doc_text
        ))

    meta = RerankMeta(
        tokens=RerankTokenMetrics(total_tokens=total_tokens),
        credits_deducted=credits_needed,
        credits_remaining=final_credits_remaining,
        tokens_saved=final_tokens_saved_total
    )

    latency_ms = (time.time() - t0) * 1000
    # Also log request metric (Async metrics injection)
    asyncio.create_task(
        log_request_metric(key_data, "/v1/rerank", 200, latency_ms, tokens=total_tokens)
    )

    return RerankResponse(results=docs_res, meta=meta)

@app.post("/v1/auth/signup", response_model=SignupResponse, summary="Self-serve registration")
async def api_signup(payload: SignupRequest):
    """
    Registers a new developer and issues a free API key with 1,000 credits.
    """
    db = get_database_adapter()
    try:
        result = await db.signup_by_email(payload.email)
        api_key = result["api_key"]
        
        # Prepare quickstart snippets
        curl_snippet = f"""curl -X POST "http://localhost:8000/v1/rerank" \\
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
    ses_api_url="http://localhost:8000/v1/rerank",
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
            quickstart={
                "curl": curl_snippet,
                "python_langchain": python_snippet
            }
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
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
    }


@app.get("/readyz", summary="Gateway dependency readiness")
async def gateway_readiness():
    """Return 503 until every required production dependency is reachable."""
    health = await _dependency_health()
    return JSONResponse(
        status_code=200 if health["status"] == "healthy" else 503,
        content=health,
    )


@app.get("/api/v1/health", summary="Detailed health monitor of satellite services")
async def api_health():
    """Report dependency state without initializing embeddings or the RAG engine."""
    return await _dependency_health()


# --- ADMIN MONETIZATION & MANAGEMENT ROUTES ---

def verify_admin_key(key_data: Dict[str, Any] = Depends(get_api_key_details)):
    if key_data.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden. Admin privileges required."
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
async def admin_create_key(payload: APIKeyCreatePayload, admin_data: Dict[str, Any] = Depends(verify_admin_key)):
    try:
        db = get_database_adapter()
        result = await db.create_api_key(
            name=payload.name,
            namespace=payload.namespace,
            rate_limit=payload.rate_limit,
            role=payload.role
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
                
        logger.info(f"🔑 Created new API key for client '{payload.name}' in namespace '{payload.namespace}'")
        return result
    except Exception as e:
        logger.exception("Error creating API key:")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/admin/keys/{key_to_delete}", summary="Admin endpoint to revoke API keys")
async def admin_delete_key(key_to_delete: str, admin_data: Dict[str, Any] = Depends(verify_admin_key)):
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
                
        logger.info("🚫 Revoked API key token.")
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
                total_reqs = await redis_client.get("gateway:metrics:total_requests")
                if total_reqs:
                    analytics["total_requests"] = int(total_reqs)
                    
                total_errs = await redis_client.get("gateway:metrics:total_errors")
                if total_errs:
                    analytics["total_errors"] = int(total_errs)
                    
                total_srch = await redis_client.get("gateway:metrics:total_searches")
                if total_srch:
                    analytics["total_searches"] = int(total_srch)
                    
                total_ingst = await redis_client.get("gateway:metrics:total_ingestions")
                if total_ingst:
                    analytics["total_ingestions"] = int(total_ingst)
            except Exception as e:
                logger.error(f"Failed to fetch live Redis analytics: {e}")
                
        return analytics
    except Exception as e:
        logger.exception("Error getting admin analytics:")
        raise HTTPException(status_code=500, detail=str(e))


# --- STRIPE WEBHOOK ---
from gateway.stripe_webhook import router as stripe_webhook_router

app.include_router(stripe_webhook_router)


# --- REPORT ENDPOINTS ---


@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
async def dashboard_root():
    static_file_path = "gateway/static/index.html"
    if os.path.exists(static_file_path):
        with open(static_file_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>SES Enterprise Gateway</h1><p>Dashboard static files missing.</p>")

# Mount static files directory
if os.path.exists("gateway/static"):
    app.mount("/static", StaticFiles(directory="gateway/static"), name="static")

import os

from dotenv import load_dotenv

# Honor the documented local .env workflow without overriding process-level
# environment variables supplied by production secret managers.
load_dotenv(override=False)


def _missing_or_placeholder(value) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    return normalized.startswith(("change_me", "replace_"))


def _optional_int(name: str):
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else None


# --- Environment & Debug ---
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# --- Redis (rate limiting, caching, worker queue) ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

if not DEBUG and _missing_or_placeholder(REDIS_PASSWORD):
    raise ValueError("CRITICAL: a non-placeholder REDIS_PASSWORD is mandatory in production.")

# --- Reranker model ---
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RERANK_MODEL_DIR = os.getenv("RERANK_MODEL_DIR", os.path.join(_REPO_ROOT, "model_onnx"))
RERANK_MODEL_FILE = os.getenv("RERANK_MODEL_FILE", "model.onnx")
# Longest (query + document) pair fed to the cross-encoder, in model tokens.
RERANK_MAX_TOKENS = int(os.getenv("RERANK_MAX_TOKENS", "512"))
# ONNX Runtime intra-op threads; unset uses every logical CPU.
RERANK_INTRA_THREADS = _optional_int("RERANK_INTRA_THREADS")

# --- Worker queue ---
# How long the Gateway waits for a worker reply before answering 504.
RERANK_QUEUE_TIMEOUT_SECONDS = float(os.getenv("RERANK_QUEUE_TIMEOUT_SECONDS", "30"))

# --- Public URL shown in signup quickstart snippets ---
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "http://localhost:8000").rstrip("/")

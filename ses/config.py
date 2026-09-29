import os
import json

from dotenv import load_dotenv


# Honor the documented local .env workflow without overriding process-level
# environment variables supplied by production secret managers.
load_dotenv(override=False)


def _missing_or_placeholder(value) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    return normalized.startswith(("change_me", "replace_"))

# --- Environment & Debug ---
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# --- Embedding Model ---
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")
VECTOR_SIZE = 384

# --- Chunking ---
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

# --- Qdrant ---
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)

if not DEBUG and _missing_or_placeholder(QDRANT_API_KEY):
    raise ValueError("CRITICAL: a non-placeholder QDRANT_API_KEY is mandatory in production.")

# --- Redis ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

if not DEBUG and _missing_or_placeholder(REDIS_PASSWORD):
    raise ValueError("CRITICAL: a non-placeholder REDIS_PASSWORD is mandatory in production.")

# --- Metadata ---
ALLOWED_METADATA_KEYS = {"source", "author", "date", "tags", "category", "title", "url"}
EXCLUDED_METADATA_KEYS = {"text_snippet", "full_text", "original_id"}

# --- Persistence ---
MOUNT_MANIFEST_PATH = os.getenv("MOUNT_MANIFEST_PATH", "data/mount_manifest.json")

# --- SES Personal / Watcher ---
WATCH_DIRECTORIES = [d.strip() for d in os.getenv("WATCH_DIRECTORIES", "").split(",")] if os.getenv("WATCH_DIRECTORIES") else []
PERSONAL_NAMESPACE = os.getenv("PERSONAL_NAMESPACE", "personal_default")
DEBOUNCE_SECONDS = float(os.getenv("DEBOUNCE_SECONDS", "2.0"))

# --- Local LLM ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "60.0"))

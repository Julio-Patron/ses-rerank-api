"""
SES Core — Offline-First RAG & Document Intelligence Platform.
"""

import os
from typing import Optional, Dict, Any, List

_default_engine = None


def get_engine():
    """Return singleton OfflineRAGEngine instance."""
    global _default_engine
    if _default_engine is None:
        from .core.rag import OfflineRAGEngine
        _default_engine = OfflineRAGEngine()
    return _default_engine


async def mount(directory: str, namespace: str = "default", watch: bool = False) -> List[Dict[str, Any]]:
    """
    Mount and index a directory into the SES vector store (Mount Mode).
    
    Example:
        import ses
        await ses.mount("/data/docs", namespace="legal")
    """
    from .watcher.scanner import scan_directory
    engine = get_engine()
    results = []
    for entry in scan_directory(directory):
        fpath = entry["path"]
        fname = entry["filename"]
        try:
            with open(fpath, "rb") as f:
                res = await engine.ingest_file(
                    namespace=namespace,
                    file_obj=f,
                    filename=fname,
                    metadata={"source_path": fpath, "content_hash": entry.get("content_hash", "")}
                )
                results.append(res)
        except Exception as e:
            results.append({"status": "error", "error": str(e), "filename": fname})
    return results


async def search(query: str, namespace: str = "default", top_k: int = 5, generate_answer: bool = False):
    """
    Execute a semantic search query with PyO3 Rust re-ranking.
    
    Example:
        import ses
        results = await ses.search("termination conditions", namespace="legal")
    """
    engine = get_engine()
    return await engine.search(
        namespace=namespace,
        query=query,
        top_k=top_k,
        generate_answer=generate_answer
    )


async def ingest(file_path: str, namespace: str = "default", metadata: Optional[Dict[str, Any]] = None):
    """
    Ingest a single document file into SES.
    """
    engine = get_engine()
    fname = os.path.basename(file_path)
    meta = dict(metadata or {})
    meta["source_path"] = os.path.abspath(file_path)
    with open(file_path, "rb") as f:
        return await engine.ingest_file(
            namespace=namespace,
            file_obj=f,
            filename=fname,
            metadata=meta
        )


def __getattr__(name: str):
    if name == "OfflineRAGEngine":
        from .core.rag import OfflineRAGEngine
        return OfflineRAGEngine
    if name == "LocalLLMProvider":
        from .core.llm import LocalLLMProvider
        return LocalLLMProvider
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "OfflineRAGEngine",
    "LocalLLMProvider",
    "mount",
    "search",
    "ingest",
    "get_engine",
]

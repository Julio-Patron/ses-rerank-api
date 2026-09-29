"""End-to-end integration tests for SES Core with live services.

These tests require Qdrant and Redis running via Docker Compose. They use the
default local CPU embedding provider and verify that the full RAG pipeline
works: ingestion, vector storage, retrieval, and caching.
"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from ses.core.rag import OfflineRAGEngine

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_e2e_ingest_and_search():
    """Ingest a test document and verify it can be retrieved."""
    # Arrange: create a temporary text file with known content
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_doc.txt"
        test_content = "This is a test document about semantic search and vector databases."
        test_file.write_text(test_content, encoding="utf-8")

        # Initialize the engine (will read connection info from env)
        engine = OfflineRAGEngine()
        await engine._ensure_initialized()  # Ensure client connections are ready

        namespace = "integration_test"

        # Act: ingest the file
        with open(test_file, "rb") as f:
            ingest_result = await engine.ingest_file(
                namespace=namespace,
                file_obj=f,
                filename=test_file.name,
                metadata={"source": "test", "description": "E2E test"},
            )

        assert ingest_result.get("status") == "success", f"Ingest failed: {ingest_result}"
        doc_id = ingest_result.get("document_id")
        assert doc_id is not None, "No document ID returned from ingest"

        # Wait a moment for indexing to propagate (optional)
        await asyncio.sleep(0.5)

        # Act: search for a term present in the document
        search_query = "semantic search"
        search_result = await engine.search(namespace=namespace, query=search_query, limit=5)

        # Assert: we should get at least one result
        assert search_result.get("status") == "success", f"Search failed: {search_result}"
        results = search_result.get("results", [])
        assert len(results) > 0, "Expected at least one search result"
        # Verify the returned text contains something from our document (chunk may be truncated)
        found_text = " ".join([r.get("text", "") for r in results]).lower()
        assert "semantic" in found_text or "vector" in found_text, (
            f"Search results do not contain expected terms: {found_text}"
        )

        # Clean up: delete the document (optional, keeps namespace clean for next test)
        delete_ok = await engine.delete_document(namespace=namespace, document_id=doc_id)
        assert delete_ok is True, "Failed to delete test document"


@pytest.mark.asyncio
async def test_e2e_redis_caching():
    """Verify that repeated searches use Redis cache (optional)."""
    # This test is lightweight: we just ensure the search call succeeds twice.
    # A more sophisticated test would inspect Redis directly, but that adds
    # coupling to the caching implementation details.
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_doc2.txt"
        test_file.write_text("Redis caching test content.", encoding="utf-8")

        engine = OfflineRAGEngine()
        await engine._ensure_initialized()
        namespace = "integration_test_cache"

        # Ingest
        with open(test_file, "rb") as f:
            ingest_result = await engine.ingest_file(
                namespace=namespace,
                file_obj=f,
                filename=test_file.name,
                metadata={"source": "test"},
            )
        assert ingest_result.get("status") == "success"

        # First search
        result1 = await engine.search(namespace=namespace, query="Redis caching", limit=5)
        assert result1.get("status") == "success"

        # Second search (should hit cache if implemented)
        result2 = await engine.search(namespace=namespace, query="Redis caching", limit=5)
        assert result2.get("status") == "success"

        # Verify that the retrieved documents and text are consistent across queries
        docs1 = result1.get("results", [])
        docs2 = result2.get("results", [])
        assert len(docs1) > 0 and len(docs2) > 0
        assert [r.get("id") for r in docs1] == [r.get("id") for r in docs2]
        assert [r.get("text") for r in docs1] == [r.get("text") for r in docs2]

        # Clean up
        doc_id = ingest_result.get("document_id")
        if doc_id:
            await engine.delete_document(namespace=namespace, document_id=doc_id)
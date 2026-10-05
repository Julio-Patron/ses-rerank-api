import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import worker
from ses.services.rerank_queue import ERROR_INTERNAL, ERROR_INVALID_REQUEST, RESULT_TTL_SECONDS
from ses.services.reranker import InvalidRerankRequest

TASK = {
    "task_id": "task-1",
    "query": "q",
    "documents": ["a", {"text": "b", "metadata": {"year": 2024}}],
    "top_n": 1,
    "jsonlogic_filter": {">=": [{"var": "year"}, 2020]},
}


@pytest.mark.asyncio
async def test_process_task_forwards_the_task_to_the_engine():
    service = MagicMock()
    service.rerank = AsyncMock(return_value={"results": [], "meta": {}})

    result = await worker.process_task(service, TASK)

    assert result == {"results": [], "meta": {}}
    service.rerank.assert_awaited_once_with(
        query="q",
        documents=TASK["documents"],
        top_n=1,
        jsonlogic_filter=TASK["jsonlogic_filter"],
    )


@pytest.mark.asyncio
async def test_process_task_reports_client_errors_as_invalid_request():
    service = MagicMock()
    service.rerank = AsyncMock(side_effect=InvalidRerankRequest("bad rule"))

    result = await worker.process_task(service, TASK)

    assert result == {"error": "bad rule", "error_type": ERROR_INVALID_REQUEST}


@pytest.mark.asyncio
async def test_process_task_hides_internal_error_details():
    service = MagicMock()
    service.rerank = AsyncMock(side_effect=RuntimeError("onnx exploded at 0xdeadbeef"))

    result = await worker.process_task(service, TASK)

    assert result == {"error": "Reranking failed", "error_type": ERROR_INTERNAL}


@pytest.mark.asyncio
async def test_publish_result_pushes_and_expires_the_reply():
    pipe = MagicMock()
    pipe.execute = AsyncMock()
    pipeline_cm = MagicMock()
    pipeline_cm.__aenter__ = AsyncMock(return_value=pipe)
    pipeline_cm.__aexit__ = AsyncMock(return_value=False)
    redis_client = MagicMock()
    redis_client.pipeline.return_value = pipeline_cm

    await worker.publish_result(redis_client, "task-1", {"results": []})

    pipe.rpush.assert_called_once_with("ses_rerank_result:task-1", json.dumps({"results": []}))
    pipe.expire.assert_called_once_with("ses_rerank_result:task-1", RESULT_TTL_SECONDS)
    pipe.execute.assert_awaited_once()

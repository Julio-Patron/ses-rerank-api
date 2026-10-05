"""SES Rerank worker: consumes rerank tasks from Redis and runs the ONNX engine.

Run one or more of these next to the Gateway when Redis is available:

    python worker.py
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict

import redis.asyncio as redis

from ses.config import (
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
    RERANK_INTRA_THREADS,
    RERANK_MAX_TOKENS,
    RERANK_MODEL_DIR,
    RERANK_MODEL_FILE,
)
from ses.services.rerank_queue import (
    ERROR_INTERNAL,
    ERROR_INVALID_REQUEST,
    HEARTBEAT_INTERVAL_SECONDS,
    HEARTBEAT_KEY,
    HEARTBEAT_TTL_SECONDS,
    QUEUE_KEY,
    RESULT_TTL_SECONDS,
    result_key,
)
from ses.services.reranker import InvalidRerankRequest, RerankerService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ses_worker")


async def process_task(reranker_service: RerankerService, task: Dict[str, Any]) -> Dict[str, Any]:
    """Run one rerank task and return the payload to send back to the Gateway."""
    try:
        return await reranker_service.rerank(
            query=task["query"],
            documents=task["documents"],
            top_n=task["top_n"],
            jsonlogic_filter=task.get("jsonlogic_filter"),
        )
    except InvalidRerankRequest as exc:
        return {"error": str(exc), "error_type": ERROR_INVALID_REQUEST}
    except Exception:
        logger.exception("Rerank task %s failed", task.get("task_id"))
        return {"error": "Reranking failed", "error_type": ERROR_INTERNAL}


async def publish_result(redis_client, task_id: str, result: Dict[str, Any]) -> None:
    key = result_key(task_id)
    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.rpush(key, json.dumps(result))
        pipe.expire(key, RESULT_TTL_SECONDS)
        await pipe.execute()


async def heartbeat(redis_client) -> None:
    """Advertise this worker so the Gateway knows the queue has a consumer."""
    while True:
        try:
            await redis_client.set(HEARTBEAT_KEY, "1", ex=HEARTBEAT_TTL_SECONDS)
        except Exception as exc:
            logger.warning("Heartbeat failed: %s", exc)
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


async def consume(redis_client, reranker_service: RerankerService) -> None:
    while True:
        try:
            _, task_json = await redis_client.brpop(QUEUE_KEY, timeout=0)
            task = json.loads(task_json)
        except Exception as exc:
            logger.error("Worker loop error: %s", exc)
            await asyncio.sleep(1)
            continue

        task_id = task.get("task_id")
        if not task_id:
            logger.error("Discarding task without task_id")
            continue

        result = await process_task(reranker_service, task)
        try:
            await publish_result(redis_client, task_id, result)
        except Exception as exc:
            logger.error("Could not publish result for task %s: %s", task_id, exc)


async def main() -> None:
    logger.info("Starting SES Rerank Worker...")
    try:
        reranker_service = RerankerService(
            RERANK_MODEL_DIR,
            model_file=RERANK_MODEL_FILE,
            max_length=RERANK_MAX_TOKENS,
            intra_threads=RERANK_INTRA_THREADS,
        )
    except Exception as exc:
        logger.error("Failed to initialize Reranker Engine: %s", exc)
        sys.exit(1)

    # No socket_timeout: BRPOP blocks indefinitely waiting for work.
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD or None,
        decode_responses=True,
    )
    try:
        await redis_client.ping()
    except Exception as exc:
        logger.error("Failed to connect to Redis at %s:%s: %s", REDIS_HOST, REDIS_PORT, exc)
        sys.exit(1)

    logger.info("Worker ready; waiting for tasks on '%s'", QUEUE_KEY)
    await asyncio.gather(heartbeat(redis_client), consume(redis_client, reranker_service))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")

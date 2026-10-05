"""Redis contract shared by the Gateway (producer) and worker.py (consumer).

The Gateway RPUSHes a task to QUEUE_KEY and BLPOPs result_key(task_id). Workers
refresh HEARTBEAT_KEY while alive; the Gateway only enqueues when it exists and
otherwise reranks in-process, so a stack without workers still answers.
"""

QUEUE_KEY = "ses_rerank_queue"
RESULT_KEY_PREFIX = "ses_rerank_result:"
HEARTBEAT_KEY = "ses:worker:heartbeat"
HEARTBEAT_INTERVAL_SECONDS = 5
HEARTBEAT_TTL_SECONDS = 15
# Results expire so an abandoned reply (Gateway timed out) cannot leak memory.
RESULT_TTL_SECONDS = 60

# Values of the "error_type" field in a failed task result.
ERROR_INVALID_REQUEST = "invalid_request"
ERROR_INTERNAL = "internal"


def result_key(task_id: str) -> str:
    return f"{RESULT_KEY_PREFIX}{task_id}"

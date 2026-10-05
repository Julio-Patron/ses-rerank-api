"""SES Rerank: multilingual cross-encoder reranking service.

The reranking engine lives in ``ses.services.reranker``; the HTTP API is the
FastAPI app in ``gateway.server`` and the queue consumer is ``worker.py``.
"""

__version__ = "1.0.0"

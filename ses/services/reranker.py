import asyncio
import json
import math
import time
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
from jas_vector_core import CrossEncoderEngine, filter_metadata
from transformers import AutoTokenizer

ENGINE_NAME = "jas_vector_core:rust_onnx_crossencoder"

# A document is either plain text or a JSON object {"text": ..., "metadata": {...}}.
# Objects exposing .text/.metadata (e.g. Pydantic models) are accepted too.
Document = Union[str, Mapping[str, Any]]


class InvalidRerankRequest(ValueError):
    """The request cannot be processed as sent (e.g. an invalid JSONLogic rule)."""


def sigmoid(logit: float) -> float:
    """Map a cross-encoder logit to a 0-1 relevance score (numerically stable)."""
    if logit >= 0:
        return 1.0 / (1.0 + math.exp(-logit))
    exp = math.exp(logit)
    return exp / (1.0 + exp)


def split_document(doc: Document) -> Tuple[str, Optional[Dict[str, Any]]]:
    if isinstance(doc, str):
        return doc, None
    if isinstance(doc, Mapping):
        return str(doc.get("text") or ""), doc.get("metadata")
    return str(getattr(doc, "text", "") or ""), getattr(doc, "metadata", None)


def _as_int64(array) -> np.ndarray:
    return np.ascontiguousarray(array, dtype=np.int64)


class RerankerService:
    def __init__(
        self,
        model_dir: str,
        model_file: str = "model.onnx",
        max_length: int = 512,
        intra_threads: Optional[int] = None,
    ):
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.engine = CrossEncoderEngine(model_dir, model_file, intra_threads)
        self.max_length = max_length

    def _estimate_tokens(self, text: str) -> int:
        """Rough LLM-token estimate (~1.33 tokens per whitespace word)."""
        return int(round(len(text.split()) * 1.33))

    def _score(self, query: str, texts: Sequence[str], top_n: int) -> List[Tuple[int, float]]:
        """Tokenize and run the ONNX engine. Blocking; call through asyncio.to_thread."""
        encodings = self.tokenizer(
            [query] * len(texts),
            list(texts),
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="np",
        )
        token_type_ids = encodings.get("token_type_ids")
        return self.engine.rerank_batch(
            _as_int64(encodings["input_ids"]),
            _as_int64(encodings["attention_mask"]),
            None if token_type_ids is None else _as_int64(token_type_ids),
            top_n,
        )

    async def rerank(
        self,
        query: str,
        documents: Sequence[Document],
        top_n: int,
        jsonlogic_filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        start_time = time.perf_counter()

        if not documents:
            return {"results": [], "meta": {}}

        doc_texts: List[str] = []
        doc_metadata_json: List[str] = []
        for doc in documents:
            text, metadata = split_document(doc)
            doc_texts.append(text)
            doc_metadata_json.append(json.dumps(metadata) if metadata else "{}")

        if jsonlogic_filter:
            try:
                passed_indices = filter_metadata(json.dumps(jsonlogic_filter), doc_metadata_json)
            except ValueError as exc:
                raise InvalidRerankRequest(str(exc)) from exc
        else:
            passed_indices = list(range(len(documents)))

        results = []
        if passed_indices:
            ranked = await asyncio.to_thread(
                self._score, query, [doc_texts[i] for i in passed_indices], top_n
            )
            for local_idx, logit in ranked:
                original_idx = passed_indices[int(local_idx)]
                results.append(
                    {
                        "index": original_idx,
                        "relevance_score": sigmoid(float(logit)),
                        "document": documents[original_idx],
                    }
                )

        query_tokens = self._estimate_tokens(query)
        input_tokens = query_tokens + sum(self._estimate_tokens(t) for t in doc_texts)
        output_tokens = (
            query_tokens + sum(self._estimate_tokens(doc_texts[r["index"]]) for r in results)
            if results
            else 0
        )
        saved_tokens = input_tokens - output_tokens
        savings_percentage = (saved_tokens / input_tokens * 100.0) if input_tokens > 0 else 0.0

        return {
            "results": results,
            "meta": {
                "engine": ENGINE_NAME,
                "latency_ms": round((time.perf_counter() - start_time) * 1000.0, 2),
                "input_documents_count": len(documents),
                "returned_documents_count": len(results),
                "token_metrics": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "saved_tokens": saved_tokens,
                    "savings_percentage": round(savings_percentage, 2),
                },
            },
        }

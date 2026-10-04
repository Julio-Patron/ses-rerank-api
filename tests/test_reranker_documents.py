"""Offline coverage for document shapes and filter failures."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("jas_vector_core", MagicMock())
sys.modules.setdefault("transformers", MagicMock())

from ses.services.reranker import RerankerService, _document_text_and_metadata


class _Tokenizer:
    def __call__(self, pairs, padding, truncation, return_tensors):
        import numpy as np

        count = len(pairs)
        return {
            "input_ids": np.zeros((count, 2), dtype=np.int64),
            "attention_mask": np.ones((count, 2), dtype=np.int64),
            "token_type_ids": np.zeros((count, 2), dtype=np.int64),
        }


class _Engine:
    def rerank_batch(self, input_ids, attention_mask, token_type_ids, top_n):
        return [(0, 0.8)]


def _service(monkeypatch):
    monkeypatch.setattr(
        "ses.services.reranker.AutoTokenizer.from_pretrained",
        lambda _path: _Tokenizer(),
    )
    monkeypatch.setattr(
        "ses.services.reranker.CrossEncoderEngine",
        lambda _path: _Engine(),
    )
    return RerankerService("unused-model-dir")


def test_document_parts_accept_dict_and_model():
    assert _document_text_and_metadata("plain") == ("plain", {})
    assert _document_text_and_metadata({"text": "laptop", "metadata": {"price": 10}}) == (
        "laptop",
        {"price": 10},
    )
    modeled = SimpleNamespace(text="chair", metadata={"price": 50})
    assert _document_text_and_metadata(modeled) == ("chair", {"price": 50})


@pytest.mark.asyncio
async def test_rerank_dict_documents_returns_text(monkeypatch):
    service = _service(monkeypatch)
    monkeypatch.setattr(
        "jas_vector_core.filter_metadata",
        lambda rule, metadata: [0],
        raising=False,
    )
    result = await service.rerank(
        query="laptop",
        documents=[
            {"text": "Dell XPS", "metadata": {"price": 1800}},
            {"text": "Chair", "metadata": {"price": 50}},
        ],
        top_n=1,
        jsonlogic_filter={"<": [{"var": "price"}, 2000]},
    )
    assert result["results"][0]["document"] == "Dell XPS"
    assert result["results"][0]["index"] == 0


@pytest.mark.asyncio
async def test_invalid_filter_does_not_leak_engine_error(monkeypatch):
    service = _service(monkeypatch)

    def _explode(rule, metadata):
        raise RuntimeError("secret filter internals")

    monkeypatch.setattr("jas_vector_core.filter_metadata", _explode, raising=False)
    with pytest.raises(ValueError, match="Invalid jsonlogic_filter") as exc_info:
        await service.rerank(
            query="q",
            documents=[{"text": "doc", "metadata": {}}],
            top_n=1,
            jsonlogic_filter={"==": [1, 1]},
        )
    assert "secret" not in str(exc_info.value)

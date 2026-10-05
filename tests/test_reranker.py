from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ses.services.reranker import (
    InvalidRerankRequest,
    RerankerService,
    sigmoid,
    split_document,
)


@pytest.fixture
def reranker():
    with patch("ses.services.reranker.AutoTokenizer") as MockTokenizer, \
         patch("ses.services.reranker.CrossEncoderEngine") as MockEngineClass:
        tokenizer = MagicMock()
        tokenizer.return_value = {
            "input_ids": [[1, 2]],
            "attention_mask": [[1, 1]],
            "token_type_ids": [[0, 0]],
        }
        MockTokenizer.from_pretrained.return_value = tokenizer
        MockEngineClass.return_value = MagicMock()

        service = RerankerService("dummy_path")
        # yield inside the with block so patches stay active!
        yield service


def test_sigmoid_maps_logits_to_unit_interval():
    assert sigmoid(0.0) == 0.5
    assert sigmoid(10.0) > 0.9999
    assert sigmoid(-800.0) == 0.0  # no overflow on very negative logits
    assert sigmoid(800.0) == 1.0


def test_split_document_accepts_strings_dicts_and_objects():
    assert split_document("plain") == ("plain", None)
    assert split_document({"text": "t", "metadata": {"a": 1}}) == ("t", {"a": 1})
    assert split_document({"text": "t"}) == ("t", None)
    assert split_document(SimpleNamespace(text="obj", metadata=None)) == ("obj", None)


def test_estimate_tokens_formula(reranker):
    assert reranker._estimate_tokens("one two three") == round(3 * 1.33)
    assert reranker._estimate_tokens("") == 0
    assert reranker._estimate_tokens("single") == round(1 * 1.33)


@pytest.mark.asyncio
async def test_rerank_returns_sigmoid_scores_from_rust_engine(reranker):
    reranker.engine.rerank_batch.return_value = [(0, 2.0), (1, -1.0)]

    result = await reranker.rerank(query="test query", documents=["doc 1", "doc 2"], top_n=2)

    assert [r["index"] for r in result["results"]] == [0, 1]
    assert result["results"][0]["relevance_score"] == pytest.approx(sigmoid(2.0))
    assert result["results"][1]["relevance_score"] == pytest.approx(sigmoid(-1.0))
    assert result["meta"]["engine"] == "jas_vector_core:rust_onnx_crossencoder"
    # top_n == all docs -> no token savings
    assert result["meta"]["token_metrics"]["saved_tokens"] == 0


@pytest.mark.asyncio
async def test_rerank_passes_none_when_tokenizer_has_no_token_type_ids(reranker):
    reranker.tokenizer.return_value = {"input_ids": [[1, 2]], "attention_mask": [[1, 1]]}
    reranker.engine.rerank_batch.return_value = [(0, 1.0)]

    await reranker.rerank(query="q", documents=["d"], top_n=1)

    assert reranker.engine.rerank_batch.call_args.args[2] is None


@pytest.mark.asyncio
async def test_rerank_roi_token_formulas(reranker):
    """Exact ROI (token savings) math against _estimate_tokens."""
    query = "alpha beta"
    documents = ["one two three four", "five six", "seven eight nine"]
    reranker.engine.rerank_batch.return_value = [(1, 0.95)]

    result = await reranker.rerank(query=query, documents=documents, top_n=1)

    query_tokens = reranker._estimate_tokens(query)
    input_tokens = query_tokens + sum(reranker._estimate_tokens(d) for d in documents)
    output_tokens = query_tokens + reranker._estimate_tokens(documents[1])
    saved_tokens = input_tokens - output_tokens

    metrics = result["meta"]["token_metrics"]
    assert metrics["input_tokens"] == input_tokens
    assert metrics["output_tokens"] == output_tokens
    assert metrics["saved_tokens"] == saved_tokens
    assert metrics["savings_percentage"] == round(saved_tokens / input_tokens * 100.0, 2)
    assert saved_tokens > 0


@pytest.mark.asyncio
async def test_jsonlogic_filter_maps_scores_back_to_original_indices(reranker):
    documents = [
        {"text": "old", "metadata": {"year": 2019}},
        {"text": "new", "metadata": {"year": 2024}},
        "no metadata",
    ]
    reranker.engine.rerank_batch.return_value = [(0, 3.0)]

    with patch("ses.services.reranker.filter_metadata", return_value=[1]) as filter_metadata:
        result = await reranker.rerank(
            query="q", documents=documents, top_n=1, jsonlogic_filter={">=": [1, 0]}
        )

    assert filter_metadata.call_args.args[1] == ['{"year": 2019}', '{"year": 2024}', "{}"]
    assert result["results"] == [
        {"index": 1, "relevance_score": pytest.approx(sigmoid(3.0)), "document": documents[1]}
    ]


@pytest.mark.asyncio
async def test_filter_that_excludes_everything_skips_inference(reranker):
    with patch("ses.services.reranker.filter_metadata", return_value=[]):
        result = await reranker.rerank(
            query="q", documents=["a", "b"], top_n=1, jsonlogic_filter={"==": [1, 2]}
        )

    assert result["results"] == []
    assert result["meta"]["token_metrics"]["output_tokens"] == 0
    reranker.engine.rerank_batch.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_jsonlogic_rule_raises_invalid_rerank_request(reranker):
    with patch("ses.services.reranker.filter_metadata", side_effect=ValueError("bad rule")):
        with pytest.raises(InvalidRerankRequest, match="bad rule"):
            await reranker.rerank(
                query="q", documents=["a"], top_n=1, jsonlogic_filter={"bad": []}
            )

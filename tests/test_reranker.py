import sys
from unittest.mock import MagicMock, patch

import pytest

# Inject empty mocks for optional dependencies so tests don't crash
sys.modules['qdrant_client'] = MagicMock()
sys.modules['qdrant_client.http'] = MagicMock()
sys.modules['sentence_transformers'] = MagicMock()
sys.modules['redis'] = MagicMock()
sys.modules['redis.asyncio'] = MagicMock()

from ses.services.reranker import RerankerService


@pytest.fixture
def reranker():
    with patch('ses.services.reranker.AutoTokenizer') as MockTokenizer, \
         patch('ses.services.reranker.CrossEncoderEngine') as MockEngineClass:
        
        # The mock tokenizer needs to return a dictionary when called
        mock_tokenizer_instance = MagicMock()
        mock_tokenizer_instance.return_value = {
            "input_ids": [1, 2],
            "attention_mask": [1, 1],
            "token_type_ids": [0, 0]
        }
        MockTokenizer.from_pretrained.return_value = mock_tokenizer_instance
        
        mock_engine_instance = MagicMock()
        MockEngineClass.return_value = mock_engine_instance

        service = RerankerService("dummy_path")
        # yield inside the with block so patches stay active!
        yield service


def test_estimate_tokens_formula(reranker):
    assert reranker._estimate_tokens("one two three") == round(3 * 1.33)
    assert reranker._estimate_tokens("") == 0
    assert reranker._estimate_tokens("single") == round(1 * 1.33)


@pytest.mark.asyncio
async def test_rerank_calls_rust_engine_batch(reranker):
    query = "test query"
    documents = ["doc 1", "document 2 text here"]
    
    # Mock the Rust cross-encoder engine returning top 2 results
    reranker.engine.rerank_batch.return_value = [(0, 0.99), (1, 0.5)]
    
    result = await reranker.rerank(
        query=query,
        documents=documents,
        top_n=2
    )
    
    assert len(result["results"]) == 2
    assert result["results"][0]["index"] == 0
    assert result["results"][0]["relevance_score"] == 0.99
    assert result["meta"]["engine"] == "jas_vector_core:rust_onnx_crossencoder"
    assert "token_metrics" in result["meta"]
    assert result["meta"]["token_metrics"]["input_tokens"] > 0
    # top_n == all docs -> no token savings
    assert result["meta"]["token_metrics"]["saved_tokens"] == 0 


@pytest.mark.asyncio
async def test_rerank_roi_token_formulas(reranker):
    """Exact ROI (token savings) math against _estimate_tokens."""
    query = "alpha beta"
    documents = [
        "one two three four",
        "five six",
        "seven eight nine",
    ]

    # Return only the middle document (index 1)
    reranker.engine.rerank_batch.return_value = [(1, 0.95)]

    result = await reranker.rerank(
        query=query,
        documents=documents,
        top_n=1
    )

    query_tokens = reranker._estimate_tokens(query)
    input_docs_tokens = sum(reranker._estimate_tokens(d) for d in documents)
    output_docs_tokens = reranker._estimate_tokens(documents[1])
    
    input_tokens = query_tokens + input_docs_tokens
    output_tokens = query_tokens + output_docs_tokens
    saved_tokens = input_tokens - output_tokens
    savings_percentage = round(saved_tokens / input_tokens * 100.0, 2)

    metrics = result["meta"]["token_metrics"]
    assert metrics["input_tokens"] == input_tokens
    assert metrics["output_tokens"] == output_tokens
    assert metrics["saved_tokens"] == saved_tokens
    assert metrics["savings_percentage"] == savings_percentage
    assert saved_tokens > 0

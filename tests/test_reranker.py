import pytest
import sys
from unittest.mock import AsyncMock, patch, MagicMock

sys.modules['jas_vector_core'] = MagicMock()
sys.modules['qdrant_client'] = MagicMock()
sys.modules['qdrant_client.http'] = MagicMock()
sys.modules['sentence_transformers'] = MagicMock()
sys.modules['redis'] = MagicMock()
sys.modules['redis.asyncio'] = MagicMock()
from ses.services.reranker import RerankerService

@pytest.fixture
def reranker():
    return RerankerService()


def test_estimate_tokens_formula(reranker):
    assert reranker._estimate_tokens("one two three") == int(round(3 * 1.33))
    assert reranker._estimate_tokens("") == 0
    assert reranker._estimate_tokens("single") == int(round(1 * 1.33))


@pytest.mark.asyncio
async def test_rerank_with_provided_vectors(reranker):
    query = "test query"
    documents = ["doc 1", "document 2 text here"]
    query_vector = [0.1, 0.2]
    document_vectors = [[0.1, 0.2], [0.3, 0.4]]
    
    with patch('ses.services.reranker.jas_vector_core.cosine_similarity_search_numpy') as mock_search:
        mock_search.return_value = [(0, 0.99), (1, 0.5)]
        
        result = await reranker.rerank(
            query=query,
            documents=documents,
            top_n=2,
            document_vectors=document_vectors,
            query_vector=query_vector
        )
        
        assert len(result["results"]) == 2
        assert result["results"][0]["index"] == 0
        assert result["results"][0]["relevance_score"] == 0.99
        assert result["meta"]["engine"] == "jas_vector_core:rust"
        assert "token_metrics" in result["meta"]
        assert result["meta"]["token_metrics"]["input_tokens"] > 0
        # top_n == all docs → no token savings
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
    query_vector = [0.1, 0.2]
    document_vectors = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]

    # Return only the middle document (index 1)
    with patch('ses.services.reranker.jas_vector_core.cosine_similarity_search_numpy') as mock_search:
        mock_search.return_value = [(1, 0.95)]

        result = await reranker.rerank(
            query=query,
            documents=documents,
            top_n=1,
            document_vectors=document_vectors,
            query_vector=query_vector,
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

        
@pytest.mark.asyncio
async def test_rerank_without_vectors(reranker):
    query = "test query"
    documents = ["doc 1", "document 2 text here", "a third document"]
    
    mock_model = AsyncMock()
    mock_model.encode.side_effect = [
        [[0.1, 0.2]], # query
        [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]] # documents
    ]
    
    with patch('ses.services.reranker.get_embedding_model', return_value=mock_model), \
         patch('ses.services.reranker.jas_vector_core.cosine_similarity_search_numpy') as mock_search:
        
        mock_search.return_value = [(1, 0.8)]
        
        result = await reranker.rerank(
            query=query,
            documents=documents,
            top_n=1
        )
        
        assert len(result["results"]) == 1
        assert result["results"][0]["index"] == 1
        assert mock_model.encode.call_count == 2
        assert result["meta"]["token_metrics"]["saved_tokens"] > 0

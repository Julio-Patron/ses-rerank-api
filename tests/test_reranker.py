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
        assert result["meta"]["token_metrics"]["saved_tokens"] == 0 
        
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

import pytest
from unittest.mock import patch, MagicMock
from ses.core.llm import LocalLLMProvider

def test_local_llm_provider_initialization():
    provider = LocalLLMProvider(model_override="test-llama")
    assert provider.model == "test-llama"

@pytest.mark.asyncio
async def test_generate_answer_no_context():
    provider = LocalLLMProvider()
    response = await provider.generate_answer("query", [])
    assert "no contiene información suficiente" in response

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_generate_answer_success(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"response": "Respuesta mockeada"}
    mock_post.return_value = mock_response

    provider = LocalLLMProvider()
    docs = [{"text": "Contexto de prueba", "metadata": {"file_name": "test.txt"}}]
    
    response = await provider.generate_answer("¿Qué es esto?", docs)
    assert response == "Respuesta mockeada"

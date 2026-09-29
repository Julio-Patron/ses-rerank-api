import httpx
from typing import Any, Dict, List, Optional, Sequence
from langchain_core.callbacks.manager import Callbacks
from langchain_core.documents import BaseDocumentCompressor, Document
from pydantic import ConfigDict, Field

class SESRerankCompressor(BaseDocumentCompressor):
    """Document compressor that uses SES Rerank API to drop low relevance documents."""

    ses_api_url: str = Field(default="http://localhost:8000/v1/rerank")
    ses_api_key: str = Field(default=...)
    top_n: int = Field(default=3)
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def compress_documents(
        self,
        documents: Sequence[Document],
        query: str,
        callbacks: Optional[Callbacks] = None,
    ) -> Sequence[Document]:
        """Compress documents using SES Rerank API."""
        if not documents:
            return []

        doc_texts = [doc.page_content for doc in documents]
        
        headers = {
            "Authorization": f"Bearer {self.ses_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "query": query,
            "documents": doc_texts,
            "top_n": self.top_n,
            "return_documents": False # We already have the content
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(self.ses_api_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            raise RuntimeError(f"Error calling SES Rerank API: {e}")

        # Re-order and filter the original documents based on SES results
        final_docs = []
        for result in data.get("results", []):
            idx = result["index"]
            score = result["relevance_score"]
            doc = documents[idx]
            # Add the score to metadata
            doc.metadata["ses_relevance_score"] = score
            final_docs.append(doc)

        return final_docs

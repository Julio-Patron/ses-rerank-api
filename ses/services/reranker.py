import time
from typing import List, Optional, Dict, Any
import numpy as np

import jas_vector_core
from ses.core.embeddings import get_embedding_model

class RerankerService:
    def _estimate_tokens(self, text: str) -> int:
        return int(round(len(text.split()) * 1.33))

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: int,
        document_vectors: Optional[List[List[float]]] = None,
        query_vector: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        start_time = time.perf_counter()

        if query_vector is None or document_vectors is None:
            model = get_embedding_model()
            if query_vector is None:
                query_res = await model.encode([query])
                query_vector = query_res[0] if isinstance(query_res, (list, tuple)) else query_res[0].tolist() if isinstance(query_res, np.ndarray) else query_res[0]
            if document_vectors is None:
                doc_res = await model.encode(documents)
                document_vectors = doc_res if isinstance(doc_res, (list, tuple)) else doc_res.tolist() if isinstance(doc_res, np.ndarray) else doc_res

        query_array = np.array(query_vector, dtype=np.float32, order='C')
        document_matrix = np.array(document_vectors, dtype=np.float32, order='C')

        search_results = jas_vector_core.cosine_similarity_search_numpy(query_array, document_matrix, top_n)
        
        results = []
        output_docs_tokens = 0
        for item in search_results:
            # item could be (index, score) or an object
            if isinstance(item, tuple) or isinstance(item, list):
                idx = int(item[0])
                score = float(item[1])
            elif hasattr(item, 'index') and hasattr(item, 'score'):
                idx = int(item.index)
                score = float(item.score)
            else:
                idx = int(item['index'])
                score = float(item['score'])

            doc_text = documents[idx]
            output_docs_tokens += self._estimate_tokens(doc_text)
            results.append({
                "index": idx,
                "relevance_score": score,
                "document": doc_text
            })

        end_time = time.perf_counter()
        latency_ms = (end_time - start_time) * 1000.0

        query_tokens = self._estimate_tokens(query)
        input_docs_tokens = sum(self._estimate_tokens(doc) for doc in documents)
        
        input_tokens = query_tokens + input_docs_tokens
        output_tokens = query_tokens + output_docs_tokens
        saved_tokens = input_tokens - output_tokens
        savings_percentage = (saved_tokens / input_tokens * 100.0) if input_tokens > 0 else 0.0

        return {
            "results": results,
            "meta": {
                "engine": "jas_vector_core:rust",
                "latency_ms": round(latency_ms, 2),
                "input_documents_count": len(documents),
                "returned_documents_count": len(results),
                "token_metrics": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "saved_tokens": saved_tokens,
                    "savings_percentage": round(savings_percentage, 2)
                }
            }
        }

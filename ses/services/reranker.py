import time
from typing import List, Optional, Dict, Any

from transformers import AutoTokenizer
from jas_vector_core import CrossEncoderEngine

class RerankerService:
    def __init__(self, model_dir: str):
        # Cargamos el tokenizador rápido en Python
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        # Inicializamos la sesión ONNX en nuestro binario de Rust
        self.engine = CrossEncoderEngine(model_dir)

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

        if not documents:
            return {"results": [], "meta": {}}

        # Preparamos los pares (query, doc)
        pairs = [[query, doc] for doc in documents]
        
        # Tokenizamos todo el lote con padding
        encodings = self.tokenizer(
            pairs, 
            padding=True, 
            truncation=True, 
            return_tensors=None # Queremos listas planas para pasarlas a Rust
        )

        # Pasamos los arreglos enteros a Rust para inferencia de alto rendimiento
        # Rust devolverá una lista de tuplas [(indice, score), ...] ordenadas
        search_results = self.engine.rerank_batch(
            encodings["input_ids"],
            encodings["attention_mask"],
            top_n
        )
        
        results = []
        output_docs_tokens = 0
        for item in search_results:
            if isinstance(item, tuple) or isinstance(item, list):
                idx = int(item[0])
                score = float(item[1])
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
                "engine": "jas_vector_core:rust_onnx_crossencoder",
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

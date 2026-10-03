import asyncio
import time
import json
from typing import Any, Dict, List, Optional, Union

from jas_vector_core import CrossEncoderEngine
from transformers import AutoTokenizer


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
        documents: List[Union[str, Dict[str, Any]]],
        top_n: int,
        document_vectors: Optional[List[List[float]]] = None,
        query_vector: Optional[List[float]] = None,
        jsonlogic_filter: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        start_time = time.perf_counter()

        if not documents:
            return {"results": [], "meta": {}}

        # Parse text and metadata from documents
        doc_texts = []
        doc_metadata_json = []
        for doc in documents:
            if isinstance(doc, str):
                doc_texts.append(doc)
                doc_metadata_json.append("{}")
            else:
                doc_texts.append(doc.text)
                metadata = doc.metadata or {}
                doc_metadata_json.append(json.dumps(metadata) if metadata else "{}")
        
        # Apply JSONLogic filter if provided
        if jsonlogic_filter:
            import jas_vector_core
            rule_str = json.dumps(jsonlogic_filter)
            try:
                # filter_metadata is executed in a background thread
                passed_indices = await asyncio.to_thread(
                    jas_vector_core.filter_metadata,
                    rule_str,
                    doc_metadata_json
                )
            except Exception as e:
                raise ValueError(f"JSONLogic Error: {e}")
        else:
            passed_indices = list(range(len(documents)))
            
        print(f"DEBUG: rule={jsonlogic_filter}, metadata={doc_metadata_json}, passed={passed_indices}")

        if not passed_indices:
            return {
                "results": [],
                "meta": {
                    "engine": "jas_vector_core:rust_onnx_crossencoder",
                    "latency_ms": round((time.perf_counter() - start_time) * 1000.0, 2),
                    "input_documents_count": len(documents),
                    "returned_documents_count": 0,
                    "token_metrics": {
                        "input_tokens": self._estimate_tokens(query) + sum(self._estimate_tokens(d) for d in doc_texts),
                        "output_tokens": 0,
                        "saved_tokens": self._estimate_tokens(query) + sum(self._estimate_tokens(d) for d in doc_texts),
                        "savings_percentage": 100.0
                    }
                }
            }

        # Prepare pairs only for documents that passed the filter
        pairs = [[query, doc_texts[i]] for i in passed_indices]
        
        # Tokenize only the filtered batch
        encodings = self.tokenizer(
            pairs, 
            padding=True, 
            truncation=True, 
            return_tensors="np" # numpy for zero-copy to Rust
        )

        # Run high performance inference in Rust
        search_results = await asyncio.to_thread(
            self.engine.rerank_batch,
            encodings["input_ids"],
            encodings["attention_mask"],
            encodings["token_type_ids"],
            top_n
        )
        
        results = []
        output_docs_tokens = 0
        for item in search_results:
            if isinstance(item, tuple) or isinstance(item, list):
                local_idx = int(item[0])
                score = float(item[1])
            else:
                local_idx = int(item['index'])
                score = float(item['score'])

            # Map the local index back to the original index
            original_idx = passed_indices[local_idx]
            doc_obj = documents[original_idx]
            
            output_docs_tokens += self._estimate_tokens(doc_texts[original_idx])
            results.append({
                "index": original_idx,
                "relevance_score": score,
                "document": doc_obj
            })

        end_time = time.perf_counter()
        latency_ms = (end_time - start_time) * 1000.0

        query_tokens = self._estimate_tokens(query)
        input_docs_tokens = sum(self._estimate_tokens(doc_text) for doc_text in doc_texts)
        
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

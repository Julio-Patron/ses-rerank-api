import time

import numpy as np

rust_core_available = False
try:
    import jas_vector_core
    rust_core_available = True
except ImportError:
    pass

def generate_mock_vectors(num_vectors, dimension=384):
    vectors = []
    for _ in range(num_vectors):
        v = np.random.randn(dimension).astype(np.float32)
        norm = np.linalg.norm(v)
        if norm > 0:
            v = v / norm
        vectors.append(v.tolist())
    return vectors

def python_cosine_similarity_search(query_vector, document_vectors, top_k=5):
    q = np.array(query_vector)
    q_norm = np.linalg.norm(q)
    scores = []
    for idx, d_vec in enumerate(document_vectors):
        d = np.array(d_vec)
        d_norm = np.linalg.norm(d)
        if q_norm > 0 and d_norm > 0:
            score = np.dot(q, d) / (q_norm * d_norm)
        else:
            score = 0.0
        scores.append((idx, float(score)))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_k]

def benchmark_search(num_documents=1000, dimensions=384, top_k=10, iterations=50):
    print(f"\n--- BENCHMARK: Búsqueda Semántica con {num_documents} Documentos ({dimensions}d) ---")
    
    query = generate_mock_vectors(1, dimensions)[0]
    docs = generate_mock_vectors(num_documents, dimensions)
    
    print("Corriendo búsqueda en Python Puro...")
    start_time = time.perf_counter()
    for _ in range(iterations):
        _ = python_cosine_similarity_search(query, docs, top_k)
    python_duration = (time.perf_counter() - start_time) / iterations * 1000
    print(f"  -> Python: {python_duration:.4f} ms por búsqueda")
    
    if rust_core_available:
        print("Corriendo búsqueda acelerada en Rust...")
        q_np = np.array(query, dtype=np.float32)
        docs_np = np.array(docs, dtype=np.float32)
        
        rust_search = getattr(jas_vector_core, "cosine_similarity_search_numpy", getattr(jas_vector_core, "cosine_similarity_search", None))
        
        if rust_search:
            _ = rust_search(q_np, docs_np, top_k)
            start_time = time.perf_counter()
            for _ in range(iterations):
                _ = rust_search(q_np, docs_np, top_k)
            rust_duration = (time.perf_counter() - start_time) / iterations * 1000
            print(f"  -> Rust Core: {rust_duration:.4f} ms por búsqueda")
            speedup = python_duration / rust_duration
            print(f"  -> Aceleración Rust vs Python: {speedup:.2f}x de velocidad")
    else:
        print("  -> Rust Core: NO DISPONIBLE")

def main():
    print("=========================================================")
    print("           SES SEMANTIC ENGINE PERFORMANCE SUITE         ")
    print("=========================================================")
    benchmark_search(num_documents=100, iterations=100)
    benchmark_search(num_documents=1000, iterations=50)
    benchmark_search(num_documents=5000, iterations=20)
    print("=========================================================")

if __name__ == "__main__":
    main()

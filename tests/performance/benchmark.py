import sys
import os
import time
import random
import numpy as np

os.environ.setdefault("DEBUG", "true")

# Ensure parent directory is in path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from ses.core.chunking import chunk_text

# Check Rust core availability
rust_core_available = False
try:
    import jas_vector_core
    rust_core_available = True
except ImportError:
    pass

def generate_mock_vectors(num_vectors, dimension=384):
    """Generate random float32 vectors normalized for cosine similarity."""
    vectors = []
    for _ in range(num_vectors):
        v = np.random.randn(dimension).astype(np.float32)
        norm = np.linalg.norm(v)
        if norm > 0:
            v = v / norm
        vectors.append(v.tolist())
    return vectors

def python_cosine_similarity_search(query_vector, document_vectors, top_k=5):
    """Pure Python fallback for cosine similarity search."""
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
    
    # 1. Pure Python Search Benchmark
    print("Corriendo búsqueda en Python Puro...")
    start_time = time.perf_counter()
    for _ in range(iterations):
        _ = python_cosine_similarity_search(query, docs, top_k)
    python_duration = (time.perf_counter() - start_time) / iterations * 1000 # ms per search
    print(f"  -> Python: {python_duration:.4f} ms por búsqueda")
    
    # 2. Rust Core Search Benchmark (if available)
    if rust_core_available:
        print("Corriendo búsqueda acelerada en Rust...")
        q_np = np.array(query, dtype=np.float32)
        docs_np = np.array(docs, dtype=np.float32)
        
        # Warmup
        rust_search = getattr(
            jas_vector_core,
            "cosine_similarity_search_numpy",
            jas_vector_core.cosine_similarity_search,
        )
        _ = rust_search(q_np, docs_np, top_k)
        
        start_time = time.perf_counter()
        for _ in range(iterations):
            _ = rust_search(q_np, docs_np, top_k)
        rust_duration = (time.perf_counter() - start_time) / iterations * 1000 # ms per search
        print(f"  -> Rust Core: {rust_duration:.4f} ms por búsqueda")
        
        speedup = python_duration / rust_duration
        print(f"  -> Aceleración Rust vs Python: {speedup:.2f}x de velocidad")
    else:
        print("  -> Rust Core: NO DISPONIBLE (Compila core_rs/ para habilitar)")

def benchmark_chunking(iterations=10):
    print("\n--- BENCHMARK: Throughput de Chunking Semántico ---")
    
    # Generate mock document of 500 paragraphs
    paragraphs = [
        "El motor semántico SES lee directamente el universo documental original en modo solo lectura "
        "y genera un índice semántico derivado en Qdrant sin alterar la fuente original de verdad."
        for _ in range(500)
    ]
    large_text = "\n\n".join(paragraphs)
    text_length_kb = len(large_text) / 1024
    
    print(f"Procesando documento grande ({text_length_kb:.2f} KB)...")
    start_time = time.perf_counter()
    for _ in range(iterations):
        _ = chunk_text(large_text, chunk_size=1000, chunk_overlap=200)
    duration = (time.perf_counter() - start_time) / iterations
    
    throughput_kb_s = text_length_kb / duration
    print(f"  -> Tiempo Promedio de Segmentación: {duration:.4f} s")
    print(f"  -> Throughput: {throughput_kb_s:.2f} KB/segundo")

def benchmark_streaming_scan(num_files=1000):
    import tempfile
    import shutil
    from ses.watcher.scanner import scan_directory

    print(f"\n--- BENCHMARK: Streaming Directory Scanner ({num_files} Archivos) ---")
    temp_dir = tempfile.mkdtemp(prefix="ses_bench_scan_")
    try:
        sample_content = "SES Mount Mode streaming benchmark content for large scale validation.\n" * 10
        for i in range(num_files):
            sub_dir = os.path.join(temp_dir, f"sub_{i % 10}")
            os.makedirs(sub_dir, exist_ok=True)
            file_path = os.path.join(sub_dir, f"doc_{i}.txt")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(sample_content)

        start_time = time.perf_counter()
        count = 0
        for _ in scan_directory(temp_dir):
            count += 1
        elapsed = time.perf_counter() - start_time
        rate = count / elapsed if elapsed > 0 else 0
        print(f"  -> Archivos escaneados: {count} en {elapsed:.4f} s")
        print(f"  -> Throughput de Escaneo: {rate:.2f} archivos/segundo")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def main():
    print("=========================================================")
    print("           SES SEMANTIC ENGINE PERFORMANCE SUITE         ")
    print("=========================================================")
    print(f"Estado de Aceleración Rust Core: {'ACTIVO 🚀' if rust_core_available else 'INACTIVO ⚠️'}")
    
    benchmark_streaming_scan(num_files=1000)
    benchmark_chunking()
    benchmark_search(num_documents=100, iterations=100)
    benchmark_search(num_documents=1000, iterations=50)
    benchmark_search(num_documents=5000, iterations=20)
    print("=========================================================")

if __name__ == "__main__":
    main()

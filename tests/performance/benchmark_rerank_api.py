import asyncio
import time
import httpx
import statistics
from pprint import pprint

# Constantes de la prueba
ENDPOINT_URL = "http://localhost:8000/v1/rerank"
API_KEY = "ses_live_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6" # Assumes a valid test API Key exists or will be injected
CONCURRENT_USERS = 100
DOCUMENTS_PER_REQUEST = 50

# Generar datos sintéticos
TEST_QUERY = "Condiciones para la recisión de un contrato mercantil internacional por causa de fuerza mayor"
TEST_DOCUMENTS = [
    f"Cláusula {i}: El contrato de suministro internacional establece que ante situaciones de fuerza mayor, ninguna parte será indemnizada." if i % 7 == 0 else f"Documento genérico de relleno número {i} sobre regulaciones de exportación y aduanas para bienes de consumo."
    for i in range(DOCUMENTS_PER_REQUEST)
]

async def send_rerank_request(client: httpx.AsyncClient) -> float:
    """Envía una petición de rerank y devuelve la latencia en milisegundos."""
    payload = {
        "query": TEST_QUERY,
        "documents": TEST_DOCUMENTS,
        "top_n": 5
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    t0 = time.perf_counter()
    response = await client.post(ENDPOINT_URL, json=payload, headers=headers)
    t1 = time.perf_counter()
    
    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.text}")
        
    return (t1 - t0) * 1000

async def run_benchmark():
    print("=========================================================")
    print("      SES RERANK API - CONCURRENCY & LATENCY BENCHMARK    ")
    print("=========================================================")
    print(f"Concurrencia: {CONCURRENT_USERS} peticiones simultáneas")
    print(f"Documentos por petición: {DOCUMENTS_PER_REQUEST}")
    print("Calentando cliente HTTP...")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Lanza las peticiones en paralelo
        t_start = time.perf_counter()
        tasks = [send_rerank_request(client) for _ in range(CONCURRENT_USERS)]
        latencies = await asyncio.gather(*tasks)
        t_end = time.perf_counter()
        
    total_time = t_end - t_start
    throughput = CONCURRENT_USERS / total_time
    
    valid_latencies = [l for l in latencies if l > 0]
    
    if not valid_latencies:
        print("Ninguna petición fue exitosa. Verifica que la API Key sea válida y el servidor esté corriendo.")
        return

    print("---------------------------------------------------------")
    print(f"Total Peticiones: {len(valid_latencies)}")
    print(f"Tiempo Total: {total_time:.2f} segundos")
    print(f"Throughput: {throughput:.2f} requests/sec")
    print("--- Latencia (Round-trip HTTP + Inferencia) ---")
    print(f"Promedio (Mean): {statistics.mean(valid_latencies):.2f} ms")
    print(f"Mediana (p50): {statistics.median(valid_latencies):.2f} ms")
    print(f"p90: {statistics.quantiles(valid_latencies, n=100)[89]:.2f} ms")
    print(f"p99: {statistics.quantiles(valid_latencies, n=100)[98]:.2f} ms")
    print("=========================================================")

if __name__ == "__main__":
    asyncio.run(run_benchmark())

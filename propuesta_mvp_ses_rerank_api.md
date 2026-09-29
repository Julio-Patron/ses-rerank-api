# 🚀 Propuesta de Producto MVP: SES Rerank API (Token Optimizer para Agentes)

> **Documento de Especificación de Producto y Hoja de Ruta Técnica**  
> **Base de Código:** SES Core (`jas_vector_core` + FastAPI Gateway)  
> **Audiencia:** Desarrolladores de agentes de IA, plataformas RAG y arquitectos de sistemas LLM.

---

## 1. Resumen Ejecutivo y Tesis de Negocio

### El Problema
En arquitecturas de agentes autónomos (LangGraph, CrewAI, AutoGen, LlamaIndex), los agentes recuperan habitualmente entre 20 y 80 fragmentos candidatos de múltiples orígenes (bases vectoriales, APIs externas, logs, boletines). Inyectar este volumen sin filtrar en la ventana de contexto de un LLM genera tres fallos críticos:
1. **Costos desmedidos:** Multiplica exponencialmente los tokens de entrada en bucles *ReAct* repetitivos.
2. **Degradación de inferencia (*Lost in the Middle*):** La atención del LLM se diluye entre candidatos irrelevantes, provocando respuestas ambiguas o alucinaciones.
3. **Latencia acumulada:** Tokens innecesarios aumentan directamente el tiempo de primer token (TTFT) del modelo.

### La Solución: SES Rerank API
Un microservicio desacoplado de re-ordenamiento semántico ultrarrápido ejecutado en memoria (*zero-copy*). Recibe la consulta del agente y una lista de documentos candidatos, ejecuta similitud coseno acelerada en Rust mediante `jas_vector_core`, y devuelve en un rango sub-10ms únicamente los $N$ fragmentos con mayor relevancia, adjuntando la métrica cuantitativa de tokens ahorrados.

### Propuesta de Valor Comercial
> *"Por cada $1.00 USD invertido en SES Rerank, ahorras entre $3.50 y $8.00 USD en consumo de tokens en modelos de frontera (GPT-4o, Claude 3.5 Sonnet), mejorando la precisión y reduciendo la latencia de respuesta del agente."*

---

## 2. Mapeo contra el Estado Actual del Repositorio

El proyecto no parte de cero; reutiliza de forma modular los componentes consolidados en el inventario de **SES Core**:

```
[ Agente / Framework (LangChain, CrewAI, TypeScript SDK) ]
                           │
                           │ POST /v1/rerank (Bearer API-Key)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. SES GATEWAY (gateway/)                                    │
│    - FastAPI + Uvicorn                                      │
│    - Auth & Cuotas: SQLite cifrado                          │
│    - Rate-limiting y Caché de consultas: Redis             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ Punteros en memoria / PyO3
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. CÓMPUTO NUCLEAR (core_rs/ -> jas_vector_core)            │
│    - Aceleración en Rust                                    │
│    - Cálculo Coseno Zero-Copy                               │
│    - Re-ranking de 10-100 documentos en < 10 ms             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. METROLOGÍA Y RESPUESTA (ses/ + gateway/)                 │
│    - Conteo y estimación de tokens (Input vs Output)        │
│    - Serialización JSON compacta                            │
│    - Telemetría analítica a Redis y SQLite                  │
└─────────────────────────────────────────────────────────────┘
```

| Componente | Archivos / Módulos en Repo | Adaptación requerida para el MVP |
| :--- | :--- | :--- |
| **Acelerador de Re-ranking** | `core_rs/` (`jas_vector_core` vía Maturin + PyO3) | Exponer una interfaz Python directa (`ses/reranker.py`) que acepte tensores/vectores sin requerir conexión obligatoria a Qdrant. |
| **API Gateway** | `gateway/` (FastAPI + SQLite) | Añadir la ruta `POST /v1/rerank` con autenticación por Bearer Token y registro de métricas. |
| **Caché y Control de Flujo** | Contenedor `Redis` de Docker Compose | Control de límites de tasa (*rate limits*) por clave y deduplicación de queries repetidas. |
| **SDKs** | `sdk/` (TypeScript `@ses-ai/client`, Go) | Integrar método nativo `.rerank()` y crear wrapper como compresión documental para LangChain/LlamaIndex. |
| **Certificación de Desempeño** | `tests/performance/benchmark.py` | Adaptar la prueba de estrés para generar reportes públicos de latencia bajo cargas concurrentes. |

---

## 3. Especificación Técnica de la API

### Endpoint Central: `POST /v1/rerank`

#### Headers
```http
Authorization: Bearer ses_live_xxxxxxxxxxxxxxxxxxxxxxxx
Content-Type: application/json
```

#### Request Body
```json
{
  "query": "¿Cuáles son las condiciones de rescisión contractual por causa fortuita?",
  "documents": [
    "Cláusula 1: Definiciones generales y personalidad de las partes...",
    "Cláusula 14: En caso de rescisión por caso fortuito o fuerza mayor, ninguna de las partes estará sujeta a indemnización, debiendo liquidarse únicamente los saldos devengados...",
    "Cláusula 22: Domicilios convencionales y notificaciones por vía electrónica...",
    "Anexo B: Cronograma estimado de entrega de suministros e insumos..."
  ],
  "top_n": 1,
  "return_documents": true
}
```

#### Response Body (`200 OK`)
```json
{
  "results": [
    {
      "index": 1,
      "relevance_score": 0.9542,
      "document": "Cláusula 14: En caso de rescisión por caso fortuito o fuerza mayor, ninguna de las partes estará sujeta a indemnización, debiendo liquidarse únicamente los saldos devengados..."
    }
  ],
  "meta": {
    "engine": "jas_vector_core:rust",
    "latency_ms": 3.84,
    "input_documents_count": 4,
    "returned_documents_count": 1,
    "token_metrics": {
      "estimated_input_tokens": 1240,
      "estimated_output_tokens": 48,
      "estimated_tokens_saved": 1192,
      "savings_percentage": 96.1
    }
  }
}
```

#### Manejo de Errores Semánticos para Agentes (Self-Healing)
Si el agente envía parámetros incompatibles, la respuesta incluye instrucciones correctivas directas para que el LLM rectifique en su siguiente iteración:
```json
{
  "error": "invalid_top_n",
  "message": "The parameter 'top_n' (5) cannot be greater than the number of provided documents (2). Please set 'top_n' to an integer between 1 and 2 and retry.",
  "retryable": true
}
```

---

## 4. Plan de Implementación por Fases (4 Sprints)

### Sprint 1: Aislamiento del Núcleo y Microservicio (Días 1 a 7)
* **Objetivo:** Desacoplar el cómputo de Rust de la dependencia obligatoria de almacenamiento NAS y Qdrant.
* **Entregables:**
  * Crear módulo `ses/services/reranker.py`.
  * Adaptar llamadas de `jas_vector_core` para procesar listas de embeddings en memoria.
  * Añadir endpoint `POST /v1/rerank` en `gateway/api/`.

### Sprint 2: Estimación de Tokens, Control de Cuotas y Caché (Días 8 a 14)
* **Objetivo:** Convertir el endpoint en un producto medible y monetizable.
* **Entregables:**
  * Implementar algoritmo ligero de aproximación BPE (Byte-Pair Encoding) para estimar tokens de entrada y salida sin sobrecoste de CPU.
  * Decorador en FastAPI con Redis para límites de peticiones por minuto (RPM).
  * Registro en la base SQLite del consumo de cada API Key (`tokens_saved`, `calls_count`, `latency_avg`).

### Sprint 3: Integración en SDKs y Compatibilidad con Ecosistemas (Días 15 a 21)
* **Objetivo:** Reducir a menos de 5 minutos el tiempo de adopción técnica para un desarrollador.
* **Entregables:**
  * Extender `@ses-ai/client` (TypeScript) para incluir el método:
    ```typescript
    const result = await ses.rerank({
      query: userQuery,
      documents: candidateChunks,
      topN: 3
    });
    ```
  * Publicar adaptador compatible con `BaseDocumentCompressor` de LangChain y retrievers de LlamaIndex.

### Sprint 4: Benchmarking, Documentación y Lanzamiento (Días 22 a 28)
* **Objetivo:** Validación de estabilidad bajo carga y publicación del portal.
* **Entregables:**
  * Ejecutar suite sintética `tests/performance/benchmark.py` con 100 usuarios concurrentes y lotes de 50 documentos.
  * Publicar en el portal de Next.js (`portal/`) la sección "API Keys & Token Savings Analytics".
  * Desplegar la documentación interactiva OpenAPI en `/docs` del Gateway.

---

## 5. Estrategia de Monetización y Precios

### Modelo de Cobro
El servicio se tarifará con base en el concepto de **Créditos de Re-ranking**:
* $1\text{ crédito} = 1\text{ consulta con hasta } 25\text{ documentos candidatos}$.
* Consultas de 26 a 50 documentos descuentan $2\text{ créditos}$.

### Estructura de Planes

| Plan | Tarifa Mensual | Créditos Incluidos | Latencia Garantizada | Características |
| :--- | :--- | :--- | :--- | :--- |
| **Developer** | Gratuito | 10,000 / mes | Best-effort (< 25 ms) | Acceso al SDK, 1 API Key, soporte comunitario. |
| **Growth (Agentes)** | $49 USD / mes | 100,000 / mes ($0.00049/req) | < 10 ms | Métricas de ahorro de tokens, 5 API Keys, Redis Cache. |
| **Enterprise** | $299 USD / mes | 1,000,000 / mes + excedentes | Sub-5 ms dedicada | SLA 99.9%, despliegue on-premise opcional con Docker, soporte directo. |

---

## 6. Siguientes Pasos Inmediatos

1. Validar el enlace PyO3 de `core_rs` para confirmar si la función de similitud coseno actual en `jas_vector_core` puede ser invocada directamente pasando dos tensores (`query_vector`, `matrix_of_candidate_vectors`) sin tocar disco.
2. Definir si el MVP calculará los embeddings de los textos en el servidor (usando el proveedor local de `ses/`) o si permitirá que los clientes envíen directamente vectores precalculados para latencia mínima.
# 🚀 Task List: Camino al Release (SES Rerank API)

Este documento reemplaza la propuesta original del MVP. Las Fases 1 a 4 de desarrollo puro ya fueron completadas y el repositorio fue extraído exitosamente como un producto SaaS independiente (`Rerank-API-SaaS`).

El objetivo actual es **certificar la calidad del código** y ejecutar un **lanzamiento a producción**.

## 📊 Propuesta de Valor Comercial (Recordatorio)
> *"Por cada $1.00 USD invertido en SES Rerank, ahorras entre $3.50 y $8.00 USD en consumo de tokens en modelos de frontera (GPT-4o, Claude 3.5 Sonnet), mejorando la precisión y reduciendo la latencia de respuesta del agente."*

---

## 📋 Lista de Tareas (Roadmap to V1.0)

### Fase 1: Auditoría Integral y Limpieza
- [x] Extraer el proyecto a un repositorio limpio (SaaS Rerank independiente).
- [x] Eliminar dependencias y módulos legacy del buscador semántico local (`ses/cli.py`, `ses/watcher`, etc.).
- [x] Limpiar rutas del Gateway (`/api/v1/search`) dejando únicamente el endpoint `/v1/rerank` y los de administración de llaves.
- [x] Depurar el portal frontend (Next.js) para convertirlo en el Dashboard "Token-Gated" de analíticas de clientes.
- [x] **Auditoría de Seguridad:** Revisar manejo de variables de entorno y confirmación de que la validación Bearer no es vulnerable a inyección.
- [x] **Auditoría de Rendimiento:** Confirmar que `jas_vector_core` no sufre *memory leaks* al recibir picos de miles de peticiones simultáneas en la nube.

### Fase 2: Pruebas (Tests) Unitarias y End-to-End (E2E)
- [x] **Reparar tests unitarios rotos:** El desacople rompió las dependencias de `mock_gateway_services` en `gateway/test_gateway.py`. Actualizar los mocks para que `pytest` pase al 100%.
- [x] **Test Unitario de Rerank (`tests/test_reranker.py`):** Crear test verificando la exactitud del motor matemático en Python y las fórmulas de ROI (ahorro de tokens).
- [x] **Test E2E de FastAPI:** Levantar un `TestClient` asíncrono para verificar que `/v1/rerank` descuenta exactamente 1 crédito para <=25 documentos y devuelve error de *Self-Healing* en casos límite.
- [x] **Test del webhook de Stripe:** Un Checkout `paid` acredita el pack del Price ID, no el `amount_total`. Un Price ID desconocido no acredita. El modo `?simulated=true` solo existe con `DEBUG=true`.

### Fase 3: Infraestructura, Empaquetado y Documentación
- [x] **Packs de crédito hospedados:** Checkout, webhook por Price ID, portal `/billing` y `docker-compose.prod.yml` (Postgres, Redis, Gateway, Portal).
- [ ] **Refinamiento del Dockerfile:** Probar la construcción completa de la imagen `runner` para asegurar que el binario de Rust corre en Alpine/Slim sin fallas de Glibc.
- [ ] **Documentación API (Swagger/Redoc):** Asegurar que las descripciones de los esquemas Pydantic (`RerankRequest`, `RerankResponse`) estén documentadas para que OpenAPI auto-genere una página impecable para los clientes.

### Fase 4: Primer Release (V1.0)
- [ ] Asignar la versión `1.0.0` en `pyproject.toml`, `Cargo.toml` y `package.json`.
- [ ] Lanzar una Release oficial en GitHub.
- [ ] **Despliegue a Producción:** Subir la imagen Docker a Render, Railway o DigitalOcean.
- [ ] Conectar Stripe Live y probar el flujo de compra real con 1 USD.

### Fase 5: Go-To-Market (Infiltración Indie Hacker)
- [ ] Publicar el Pull Request en el repositorio de **LangChain** para incluir `SESRerankCompressor`.
- [ ] Escribir y publicar artículo de lanzamiento en **Indie Hackers**.
- [ ] Publicar tabla de benchmarks (SES vs Cohere) en **Hacker News (Show HN)** y **Reddit (`r/LocalLLaMA`)**.
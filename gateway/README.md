# SES Gateway

El Gateway es la capa FastAPI de SES Core. Expone búsqueda, ingestión,
documentos, salud, llaves administrativas, analítica y reportes PDF. También
sirve un dashboard estático en la ruta raíz.

Su estado actual es beta: los contratos y controles principales están
implementados y cubiertos por pruebas, pero todavía faltan pruebas end-to-end
con Qdrant, Redis y Ollama reales, además de paridad Docker reproducible.

## Arquitectura

~~~text
Cliente / Portal
      |
      v
FastAPI Gateway
  |      |       |
  v      v       v
Qdrant  Redis   Ollama
  |
SQLite local para llaves y telemetría
~~~

El aislamiento lógico usa el namespace asociado a cada llave. Este repositorio
no demuestra todavía aislamiento de infraestructura por cliente, RBAC
corporativo completo, facturación comercial ni SLAs.

## Seguridad comprobada

- <code>GATEWAY_ADMIN_KEY</code> es obligatorio y no tiene valor conocido por
  defecto.
- Las llaves creadas se muestran una sola vez y se almacenan como hashes.
- CORS se restringe mediante <code>GATEWAY_CORS_ORIGINS</code>.
- En producción, una caída de Redis hace fallar las rutas protegidas con
  <code>503</code>; el fallback local solo existe con <code>DEBUG=true</code>.
- <code>.env</code>, bases SQLite y llaves de firma están excluidas de Git.

Genere secretos locales únicos:

~~~powershell
python -m pip install -e ".[server]"
Copy-Item .env.example .env
python scripts/rotate_local_secrets.py
~~~

Reinicie el Gateway después de rotar. En producción, inyecte los secretos desde
un gestor externo y mantenga <code>DEBUG=false</code>.

## Servicios requeridos

El Compose canónico inicia Qdrant, Redis y Ollama con versiones fijas. Configure
secretos locales únicos antes de levantarlo:

~~~powershell
Copy-Item .env.compose.example .env.compose
# Edite QDRANT_API_KEY y REDIS_PASSWORD
docker compose --env-file .env.compose up -d
~~~

El Compose cubre dependencias; Gateway y Portal continúan ejecutándose desde el
código fuente.

## Arranque

Desde la raíz:

~~~powershell
python gateway/run.py
~~~

El servidor queda en <http://127.0.0.1:8000>.

Todas las rutas protegidas esperan <code>X-API-Key: &lt;llave&gt;</code>.

## Contratos HTTP implementados

### RAG y documentos

- <code>POST /api/v1/search</code>
- <code>POST /api/v1/ingest/file</code>
- <code>POST /api/v1/ingest/text</code>
- <code>GET /api/v1/documents</code>
- <code>DELETE /api/v1/documents/{doc_id}</code>
- <code>GET /api/v1/stats</code>

La búsqueda reporta <code>rust_accelerated</code>. La ruta Rust es opcional y
solo se intenta cuando el wheel está instalado y Qdrant devuelve más de 50
candidatos.

### Salud

- <code>GET /healthz</code> (liveness del proceso, sin inicializar modelos)
- <code>GET /readyz</code> (readiness de Qdrant, Redis y Ollama; responde 503 si falta una dependencia)
- <code>GET /api/v1/health</code>

Reporta estado del Gateway y dependencias. Un estado HTTP exitoso no implica que
todos los servicios satélite estén disponibles; revise el cuerpo de respuesta.

### Administración

- <code>GET /api/v1/admin/keys</code>
- <code>POST /api/v1/admin/keys</code>
- <code>DELETE /api/v1/admin/keys/{key_to_delete}</code>
- <code>GET /api/v1/admin/analytics</code>
- <code>GET /api/v1/admin/reports/usage</code>
- <code>GET /api/v1/admin/reports/health</code>
- <code>POST /api/v1/reports/evidence</code>

La telemetría persistente conserva `id` y `tenant_id` al crear llaves y su
contrato se valida extremo a extremo con SQLite. PostgreSQL real y cualquier
uso como fuente de facturación continúan siendo gates separados.

## Portal

El cliente Next.js vive en [portal/](../portal/README.md). Conserva URL y llave
en <code>localStorage</code> del navegador y consume estos contratos sin datos
de demostración.

## Pruebas

~~~powershell
pytest -q gateway/test_gateway.py gateway/test_database.py -p no:cacheprovider
~~~

La suite del Gateway usa dobles estrictos y SQLite real. La suite general añade
fallos de conexión loopback para Qdrant, Redis y Ollama. El E2E exitoso contra
servicios reales continúa separado como gate abierto.

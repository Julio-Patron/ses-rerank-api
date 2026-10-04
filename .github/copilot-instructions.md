# Copilot instructions for SES Rerank API

## Build, test, and run

Use Python 3.12 for parity with CI. From the repository root:

```powershell
python -m pip install -e ".[dev,server]"
pytest -q -p no:cacheprovider
pytest -q gateway/test_gateway.py gateway/test_database.py -p no:cacheprovider
pytest -q gateway/test_database.py::test_bootstrap_key_has_administrator_role -p no:cacheprovider
flake8 ses tests gateway --count --select=E9,F63,F7,F82 --show-source --statistics
```

`pyproject.toml` excludes tests marked `integration` by default. With Qdrant and Redis configured through the Compose stack, run them explicitly:

```powershell
Copy-Item .env.compose.example .env.compose
docker compose --env-file .env.compose up -d qdrant redis
pytest -q -m integration tests/integration
```

Build and validate the optional Rust/PyO3 extension:

```powershell
cargo fmt --manifest-path core_rs/Cargo.toml -- --check
cargo test --manifest-path core_rs/Cargo.toml
cargo test --manifest-path core_rs/Cargo.toml ranks_by_cosine_similarity_and_respects_top_k
cargo clippy --manifest-path core_rs/Cargo.toml --all-targets -- -D warnings
python -m maturin build --release --interpreter python --out core_rs/target/wheels
```

Portal commands:

```powershell
npm ci --prefix portal
npm --prefix portal run lint
npm --prefix portal run test
npm --prefix portal run test -- __tests__/api.test.ts
npm --prefix portal run build
npm --prefix portal run dev -- --hostname 127.0.0.1 --port 3000
```

Other SDK checks:

```powershell
npm ci --prefix sdk/typescript
npm --prefix sdk/typescript run build
Push-Location sdk\go; go test ./...; Pop-Location
Push-Location sdk\go; go test -run TestClient_Search; Pop-Location
```

For local services, copy `.env.example` to `.env`, run `python scripts/rotate_local_secrets.py`, and start the Gateway with `python gateway/run.py`. `docker-compose.yml` starts pinned Qdrant, Redis, and Ollama dependencies; it does not start the Gateway or Portal.

## Architecture

- `gateway/server.py` is the FastAPI composition root. Its lifespan loads the ONNX model from `model_onnx/`, constructs `RerankerService`, connects the selected database adapter, revokes the known legacy key, and bootstraps `GATEWAY_ADMIN_KEY`.
- The SaaS request path is `POST /v1/rerank`: authenticate an `Authorization` token, enforce per-key rate limits and credits, deduplicate through Redis, call `ses/services/reranker.py`, update credits/token savings, and persist usage telemetry. Signup, usage, checkout, and claim endpoints share the `/v1` API. Do not put `ses_rerank_queue` or `worker.py` back on that path.
- Credit packs are one-time Stripe payments, not subscriptions. `gateway/billing.py` maps `developer` and `growth` to `STRIPE_PRICE_*`. Charge the submitted document count (1 credit per 25 documents, minimum 1); a JSONLogic filter saves CPU, not credits. The webhook grants credits only for a signed, `paid` Checkout session whose Price ID matches a configured pack, and only to `client_reference_id`. `?simulated=true` is a `DEBUG=true` local path and must stay 404 otherwise. Webhook responses and listings never include a raw key.
- `ses/services/reranker.py` tokenizes query/document pairs with Transformers, then offloads Rust ONNX cross-encoder inference to a worker thread. `core_rs/src/cross_encoder.rs` owns ONNX execution; `core_rs/src/lib.rs` also exports NumPy cosine-search functions through PyO3.
- `gateway/database.py` defines one async `DatabaseAdapter` contract with SQLite and PostgreSQL implementations. `get_database_adapter()` is a process singleton selected by `POSTGRES_ENABLED`; SQLite at `data/gateway.db` is the default.
- Redis has three distinct roles: API-key caching, fixed-window rate limiting, and tenant-scoped rerank-result caching. Production is intentionally fail-closed for rate limiting when Redis is unavailable; the in-memory fallback is allowed only with `DEBUG=true`.
- `portal/` is a Next.js browser client. `portal/lib/api.ts` is the single HTTP adapter, stores the Gateway URL and key in browser `localStorage`, maps transport failures to `GatewayError`, and applies request timeouts. Never put an API key in a `NEXT_PUBLIC_*` variable.
- The repository still contains Semantic Engine/RAG-era modules and clients (`ses/core`, `/api/v1/*` calls in the Portal and SDKs) alongside the newer `/v1/rerank` SaaS API. Before changing a client contract, inspect the routes currently registered in `gateway/server.py`; update server schemas, `portal/lib/types.ts`, `portal/lib/api.ts`, SDK types, and contract tests together rather than assuming older README examples are live.

## Repository-specific conventions

- Treat live code, tests, and `.github/workflows/ci.yml` as authoritative when they conflict with historical README/context files.
- Keep API keys one-time-visible: persist only SHA-256 hashes and safe prefixes. Authentication/cache lookups use the hash; listings must never expose raw keys or full hashes.
- Preserve both authentication contracts deliberately: `/v1/rerank` accepts a raw or case-insensitive `Bearer` value in `Authorization`; administration endpoints use `X-API-Key`. Unsupported schemes and empty tokens are explicit 401 errors.
- Keep tenant identity in cache and persistence keys. Rerank cache entries include `tenant_id`; database records and telemetry carry both tenant and API-key IDs.
- Blocking model inference and SQLite work must not run on the event loop. Follow the existing `asyncio.to_thread` pattern; network stores use async clients.
- Unit tests must remain offline. Gateway tests replace the database, Redis, dependency probes, and reranker with strict mocks; integration tests alone may require real Qdrant/Redis services.
- Native acceleration is optional outside the rerank ONNX path. Python callers should validate importability/callability and retain their documented fallback rather than assuming a wheel is installed.
- Configuration comes from environment variables in `ses/config.py` and `gateway/database.py`. Update `.env.example`/`.env.compose.example` when adding required settings, never commit populated `.env` files, model artifacts, databases, or generated reports.
- Changes to the native package may require synchronized metadata across root `pyproject.toml`, `core_rs/Cargo.toml`, and SDK package manifests; release automation validates these surfaces independently.

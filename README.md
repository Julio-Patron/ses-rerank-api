# SES Rerank API

An ultra-low latency, zero-copy Semantic Reranker designed for AI Agents (LangChain, LlamaIndex, CrewAI) to drastically reduce LLM token costs and eliminate hallucinations. 

Powered by **Rust**, delivered via a fast **FastAPI Gateway**, and designed for Indie Hackers and Solo Founders looking for a commercially viable SaaS boilerplate.

## Why SES Rerank?

When using Vector Databases (Qdrant, Pinecone) for Retrieval-Augmented Generation (RAG), typical top-K retrieval pulls in hundreds of irrelevant tokens. Feeding these to GPT-4o or Claude costs money and degrades reasoning.

SES Rerank solves this by acting as a fast middle-layer:
1. You retrieve 50 documents from your DB.
2. You pass them to SES Rerank API.
3. We execute a zero-copy Rust similarity search in **< 10ms**.
4. We return the top 5 most relevant documents.
5. **You save 85% on your OpenAI API bill.**

## Quick Start (local dependencies)

`docker-compose.yml` starts pinned Qdrant, Redis, and Ollama. It does not start the Gateway or Portal.

```powershell
Copy-Item .env.example .env
python scripts/rotate_local_secrets.py
python scripts/download_onnx.py
python gateway/run.py
```

- Gateway API: `http://127.0.0.1:8000`
- Customer billing UI: `http://127.0.0.1:3000/billing`
- Operator portal: `http://127.0.0.1:3000`

## Local Development
Requires Python 3.10+ and the Rust toolchain (to compile `jas_vector_core`).
```bash
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -e ".[dev,server]"
```
Download the ONNX model to `model_onnx/model.onnx` before starting the server using `python scripts/download_onnx.py`.

## Hosted credit packs

Production sells one-time Stripe credit packs, not subscriptions. SQLite is the local default. The hosted stack uses Postgres.

```powershell
python scripts/deploy_production.py
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

`docker-compose.prod.yml` runs Postgres, Redis, the Gateway, and the Portal. `DEBUG` is forced to `false`. It does not start a worker queue, Qdrant, or Ollama. The Gateway image downloads `model_onnx/model.onnx` during the build.

Set these before accepting live payments:

- `STRIPE_API_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_DEVELOPER` and `STRIPE_PRICE_GROWTH`
- `GATEWAY_ADMIN_KEY`, `POSTGRES_PASSWORD`, and `REDIS_PASSWORD`
- `GATEWAY_CORS_ORIGINS` and `BILLING_SUCCESS_URL` for the public Portal origin

Point Stripe at `POST /v1/webhooks/stripe`.

## Billing contract

- `POST /v1/auth/signup` issues a free key once. The raw key is not stored.
- `POST /v1/billing/checkout` requires the customer `Authorization` key and starts Checkout for `developer` or `growth`. The Price ID comes from the server, not the browser.
- `POST /v1/webhooks/stripe` grants credits only when the signature is valid, `payment_status` is `paid`, and the paid Price ID matches a configured pack. Credits go to `client_reference_id`. The response never includes a raw key.
- `POST /v1/billing/claim` reveals a newly created key once, then deletes the claim.
- `?simulated=true` exists only for local development when `DEBUG=true`. It is not a production payment path.
- `POST /v1/rerank` charges 1 credit per 25 submitted documents, with a minimum of 1. A metadata filter saves CPU, not credits. An `Idempotency-Key` retry of the same body does not charge again.

The customer page is `/billing`. It stores the buyer key in `ses_customer_api_key`. The operator console still uses `ses_api_key` and `X-API-Key`.

## Architecture
- **Rust Core (`jas_vector_core`)**: ONNX cross-encoder execution via `ort` and PyO3.
- **SES Gateway**: FastAPI server for `/v1/rerank`, credit checks, and Stripe Checkout.
- **Postgres**: billing store for the hosted stack. SQLite remains the local default.
- **Redis**: rate limiting, idempotency, and a short rerank cache.
- **Portal**: operator console plus the customer page at `/billing`.

## LangChain Integration
We provide a native compressor in `sdk/python/ses_langchain_compressor.py`.

```python
from ses_langchain_compressor import SESRerankCompressor
from langchain.retrievers import ContextualCompressionRetriever

reranker = SESRerankCompressor(
    ses_api_key="ses_live_tu_api_key",
    ses_api_url="https://tu-dominio.com/v1/rerank",
    top_n=3
)

compression_retriever = ContextualCompressionRetriever(
    base_compressor=reranker,
    base_retriever=your_vector_store.as_retriever(search_kwargs={"k": 50})
)
# Enjoy 85% fewer tokens sent to your LLM!
```

## Built for Indie Hackers (SaaS Ready)
The hosted product sells prepaid credit packs. It is not a subscription.
- **Credit packs:** Stripe Checkout sells `developer` and `growth` packs. Credits are granted from the paid Price ID, never from `amount_total` or client metadata.
- **Idempotent rerank:** Redis is the rate limiter, the idempotency store, and a short compute cache. It is not a worker queue on the request path.
- **Self-Healing Errors:** If an LLM agent sends bad parameters (e.g. `top_n` > `len(docs)`), the API returns a descriptive error guiding the LLM to self-correct.

## License
Commercial / GPL-3.0 (See `LICENSE`).

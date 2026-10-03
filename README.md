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

## Quick Start (Docker Compose)
To start the entire Semantic Engine stack (Qdrant, Redis, Ollama, Gateway API, and Portal):
```bash
docker compose up -d --build
```
- Gateway API: `http://localhost:8000`
- Portal Console: `http://localhost:3000`

## Local Development
Requires Python 3.10+ and the Rust toolchain (to compile `jas_vector_core`).
```bash
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -e ".[dev,server]"
```
Download the ONNX model to `model_onnx/model.onnx` before starting the server using `python scripts/download_onnx.py`.

## Deployment
This project is built as a containerized stack.
- **Gateway API**: Deploy the `gateway/Dockerfile` to Railway or Render.
- **Portal Console**: Deploy `portal/Dockerfile` as a Next.js app.
- **Qdrant & Redis**: Use managed instances or standard Docker images.
*(Note on Database Choice: The Gateway uses SQLite by default for zero-dependency local tracking. Only upgrade to Postgres once 10+ paying customers require multi-region analytics.)*

## Architecture
- **Rust Core (`jas_vector_core`)**: ONNX cross-encoder execution via `ort` and PyO3.
- **SES Gateway**: FastAPI server handling authentication, ratelimiting (Redis), and RAG endpoints.
- **Qdrant**: Vector database for document embeddings.
- **Ollama**: Local generation model backend.
- **Portal**: Next.js dashboard for monitoring and API key management.

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
This repository is fully decoupled and ready to generate MRR (Monthly Recurring Revenue).
- **Redis Caching:** Duplicate queries return instantly (Zero CPU cost).
- **Stripe Webhook:** Included in `gateway/stripe_webhook.py` (simulated mode on by default). Just plug your Stripe Secret and the system will automatically provision 100K API Credits when a user buys a subscription.
- **Self-Healing Errors:** If an LLM agent sends bad parameters (e.g. `top_n` > `len(docs)`), the API returns a descriptive error guiding the LLM to self-correct.

## License
Commercial / GPL-3.0 (See `LICENSE`).

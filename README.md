# SES Rerank API 🚀

An ultra-low latency, zero-copy Semantic Reranker designed for AI Agents (LangChain, LlamaIndex, CrewAI) to drastically reduce LLM token costs and eliminate hallucinations. 

Powered by **Rust**, delivered via a fast **FastAPI Gateway**, and designed for Indie Hackers and Solo Founders looking for a commercially viable SaaS boilerplate.

## 🌟 Why SES Rerank?

When using Vector Databases (Qdrant, Pinecone) for Retrieval-Augmented Generation (RAG), typical top-K retrieval pulls in hundreds of irrelevant tokens. Feeding these to GPT-4o or Claude costs money and degrades reasoning.

SES Rerank solves this by acting as a fast middle-layer:
1. You retrieve 50 documents from your DB.
2. You pass them to SES Rerank API.
3. We execute a zero-copy Rust similarity search in **< 10ms**.
4. We return the top 5 most relevant documents.
5. **You save 85% on your OpenAI API bill.**

### Architecture
- **Engine:** `jas_vector_core` (PyO3 + Rust `ndarray` + Rayon).
- **API Gateway:** FastAPI + Redis (Rate Limiting/Caching) + SQLite (Credits tracking).
- **Billing:** Built-in `stripe_webhook.py` to sell credits automatically.

## 🚀 Quick Start (Docker)

To deploy the production-ready API on your server or PaaS (Render, Railway):

```bash
docker-compose -f docker-compose.prod.yml up -d --build
```

### 1. Request a Rerank
```bash
curl -X POST "http://localhost:8000/v1/rerank" \
     -H "Authorization: Bearer ses_live_tu_api_key" \
     -H "Content-Type: application/json" \
     -d '{
           "query": "Can we terminate the contract for force majeure?",
           "documents": ["Contract clause 5: ...", "Garbage doc 1..."],
           "top_n": 1
         }'
```

### 2. LangChain Integration
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

## 💰 Built for Indie Hackers (SaaS Ready)
This repository is fully decoupled and ready to generate MRR (Monthly Recurring Revenue).
- **Redis Caching:** Duplicate queries return instantly (Zero CPU cost).
- **Stripe Webhook:** Included in `gateway/stripe_webhook.py`. Just plug your Stripe Secret and the system will automatically provision 100K API Credits when a user buys a subscription.
- **Self-Healing Errors:** If an LLM agent sends bad parameters (e.g. `top_n` > `len(docs)`), the API returns a descriptive error guiding the LLM to self-correct.

## ⚖️ License
Commercial / GPL-3.0 (See `LICENSE`).

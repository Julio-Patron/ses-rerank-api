# @ses-ai/client

Official TypeScript/JavaScript client SDK for **Semantic Engine (SES)**.

Enables search, hybrid cognitive re-ranking, document ingestion, and offline RAG generation across web applications, Next.js, Node.js microservices, and AI Agent workflows.

---

## 📦 Installation

```bash
npm install @ses-ai/client
# or
pnpm add @ses-ai/client
# or
yarn add @ses-ai/client
```

---

## 🚀 Quickstart

### 1. Initialize Client
```typescript
import { SemanticEngineClient } from "@ses-ai/client";

const client = new SemanticEngineClient({
  baseUrl: "http://localhost:8000",
  apiKey: process.env.SES_API_KEY!,
});
```

### 2. Search & Generate Local RAG Answer
```typescript
const searchResults = await client.search({
  namespace: "legal_docs",
  query: "What is the termination clause notice period?",
  topK: 5,
  generateAnswer: true, // Ask the local LLM (Ollama) to answer using context
});

console.log("Answer:", searchResults.answer);
console.log("Documents found:", searchResults.results);
```

### 3. Ingest Raw Text
```typescript
const ingestResult = await client.ingestText({
  namespace: "legal_docs",
  text: "Contracts require a minimum of 30 days notice prior to renewal date.",
  metadata: { author: "Legal Dept", year: 2026 },
});

console.log("Ingested Document ID:", ingestResult.document_id);
```

### 4. Upload & Index Files (PDF, DOCX, XLSX, TXT)
```typescript
import fs from "node:fs";

const fileBuffer = fs.readFileSync("./policy.pdf");

await client.ingestFile({
  namespace: "policies",
  file: fileBuffer,
  filename: "policy.pdf",
  metadata: { category: "HR" },
});
```

### 5. Check Cluster Health
```typescript
const health = await client.getHealth();
console.log("Status:", health.status); // "healthy"
console.log("Qdrant:", health.components.qdrant.status);
```

---

## 🔒 Enterprise & Administrative Features

```typescript
// Create a new API key for a microservice
const newKey = await client.createApiKey("service_agent_01", "standard");
console.log("New API Key:", newKey.api_key);

// Fetch Gateway usage analytics
const stats = await client.getAnalytics();
console.log("Total Requests:", stats.total_requests);
console.log("Success Rate:", `${stats.success_rate * 100}%`);
```

---

## 📜 License
GPL-3.0-only

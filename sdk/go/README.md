# Semantic Engine Go SDK (`ses-go`)

Official high-performance Go client for **Semantic Engine (SES)**.

Provides idiomatic, zero-dependency (standard library only) client bindings for semantic vector search, offline document ingestion, and hybrid cognitive RAG generation.

---

## 📦 Installation

```bash
go get github.com/elbuilder77/Semantic-Engine/sdk/go
```

---

## 🚀 Quickstart

### 1. Initialize Client
```go
package main

import (
	"context"
	"fmt"
	"log"

	ses "github.com/elbuilder77/Semantic-Engine/sdk/go"
)

func main() {
	client, err := ses.NewClient(ses.ClientConfig{
		BaseURL: "http://localhost:8000",
		APIKey:  "your_gateway_api_key",
	})
	if err != nil {
		log.Fatalf("Failed to initialize SES client: %v", err)
	}

	// 2. Perform Semantic Search & RAG Generation
	ctx := context.Background()
	searchResp, err := client.Search(ctx, ses.SearchRequest{
		Namespace:      "contracts",
		Query:          "What are the confidentiality obligations?",
		TopK:           5,
		GenerateAnswer: true,
	})
	if err != nil {
		log.Fatalf("Search failed: %v", err)
	}

	if searchResp.Answer != nil {
		fmt.Printf("RAG Answer: %s\n", *searchResp.Answer)
	}

	for _, result := range searchResp.Results {
		fmt.Printf("Found [%.2f score]: %s\n", result.Score, result.Text)
	}
}
```

### 3. Ingest Plain Text
```go
ingestResp, err := client.IngestText(ctx, ses.IngestTextRequest{
    Namespace: "contracts",
    Text:      "Party A and Party B agree to standard non-disclosure terms for 2 years.",
    Metadata:  map[string]interface{}{"type": "NDA", "year": 2026},
})
if err != nil {
    log.Fatalf("Ingest failed: %v", err)
}
fmt.Printf("Document Ingested: ID=%s, Chunks=%d\n", ingestResp.DocumentID, ingestResp.ChunksCount)
```

### 4. Upload and Index Files (PDF, DOCX, XLSX, TXT)
```go
file, err := os.Open("agreement.pdf")
if err != nil {
    log.Fatal(err)
}
defer file.Close()

resp, err := client.IngestFile(ctx, "contracts", "agreement.pdf", file, map[string]interface{}{"department": "legal"})
if err != nil {
    log.Fatalf("File ingestion failed: %v", err)
}
fmt.Printf("File indexed: DocumentID=%s\n", resp.DocumentID)
```

---

## 📜 License
GPL-3.0-only

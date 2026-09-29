package ses

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestClient_Search(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-API-Key") != "test_key_123" {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}
		if r.URL.Path != "/api/v1/search" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{
			"status": "success",
			"query": "vector search",
			"namespace": "default",
			"results": [{"id": "doc1", "score": 0.95, "text": "sample chunk", "metadata": {}}],
			"answer": null,
			"total_documents": 1,
			"search_time_ms": 12.5,
			"total_time_ms": 15.0,
			"rust_accelerated": false
		}`))
	}))
	defer server.Close()

	client, err := NewClient(ClientConfig{
		BaseURL: server.URL,
		APIKey:  "test_key_123",
	})
	if err != nil {
		t.Fatalf("unexpected error creating client: %v", err)
	}

	resp, err := client.Search(context.Background(), SearchRequest{
		Query: "vector search",
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	if len(resp.Results) != 1 {
		t.Errorf("expected 1 result, got %d", len(resp.Results))
	}
	if resp.Results[0].ID != "doc1" {
		t.Errorf("expected doc1, got %s", resp.Results[0].ID)
	}
}

func TestClient_IngestText(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/ingest/text" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{
			"status": "success",
			"document_id": "doc_xyz",
			"chunks_count": 3,
			"processing_time_ms": 45.2
		}`))
	}))
	defer server.Close()

	client, err := NewClient(ClientConfig{
		BaseURL: server.URL,
		APIKey:  "key123",
	})
	if err != nil {
		t.Fatalf("error creating client: %v", err)
	}

	resp, err := client.IngestText(context.Background(), IngestTextRequest{
		Text: "Hello Semantic Engine",
	})
	if err != nil {
		t.Fatalf("IngestText failed: %v", err)
	}

	if resp.Status != "success" || resp.DocumentID != "doc_xyz" {
		t.Errorf("unexpected response: %+v", resp)
	}
}

func TestClient_IngestFile(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/ingest/file" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{
			"status": "success",
			"document_id": "file_123",
			"chunks_count": 5,
			"processing_time_ms": 80.0
		}`))
	}))
	defer server.Close()

	client, err := NewClient(ClientConfig{
		BaseURL: server.URL,
		APIKey:  "key123",
	})
	if err != nil {
		t.Fatalf("error creating client: %v", err)
	}

	dummyReader := io.NopCloser(strings.NewReader("dummy file content"))
	resp, err := client.IngestFile(context.Background(), "legal", "test.txt", dummyReader, map[string]interface{}{"tag": "contract"})
	if err != nil {
		t.Fatalf("IngestFile failed: %v", err)
	}

	if resp.DocumentID != "file_123" {
		t.Errorf("expected file_123, got %s", resp.DocumentID)
	}
}

func TestClient_Health(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{
			"status": "healthy",
			"version": "2.0.0",
			"environment": "production",
			"components": {}
		}`))
	}))
	defer server.Close()

	client, err := NewClient(ClientConfig{
		BaseURL: server.URL,
		APIKey:  "key123",
	})
	if err != nil {
		t.Fatalf("error creating client: %v", err)
	}

	resp, err := client.Health(context.Background())
	if err != nil {
		t.Fatalf("Health check failed: %v", err)
	}

	if resp.Status != "healthy" || resp.Version != "2.0.0" {
		t.Errorf("unexpected health status: %+v", resp)
	}
}

package ses

import (
	"net/http"
	"time"
)

// ClientConfig holds configuration for the SES client.
type ClientConfig struct {
	BaseURL    string
	APIKey     string
	HTTPClient HTTPDoer
	Timeout    time.Duration
}

// HTTPDoer interface for mockability.
type HTTPDoer interface {
	Do(req *http.Request) (*http.Response, error)
}

// SearchRequest parameters for semantic search.
type SearchRequest struct {
	Query          string  `json:"query"`
	Namespace      string  `json:"namespace,omitempty"`
	TopK           int     `json:"top_k,omitempty"`
	Threshold      float64 `json:"threshold,omitempty"`
	GenerateAnswer bool    `json:"generate_answer,omitempty"`
	ModelOverride  string  `json:"model_override,omitempty"`
}

// SearchResultItem represents a retrieved document chunk.
type SearchResultItem struct {
	ID       string                 `json:"id"`
	Score    float64                `json:"score"`
	Text     string                 `json:"text"`
	Metadata map[string]interface{} `json:"metadata"`
}

// SearchResponse returned by the search endpoint.
type SearchResponse struct {
	Query           string                 `json:"query"`
	Namespace       string                 `json:"namespace"`
	Results         []SearchResultItem     `json:"results"`
	Answer          *string                `json:"answer"`
	TotalDocuments  int                    `json:"total_documents"`
	SearchTimeMS    float64                `json:"search_time_ms"`
	TotalTimeMS     float64                `json:"total_time_ms"`
	RustAccelerated bool                   `json:"rust_accelerated"`
	Metadata        map[string]interface{} `json:"metadata,omitempty"`
}

// IngestTextRequest parameters to ingest plain text.
type IngestTextRequest struct {
	Text      string                 `json:"text"`
	Namespace string                 `json:"namespace,omitempty"`
	Metadata  map[string]interface{} `json:"metadata,omitempty"`
}

// IngestResponse returned after document ingestion.
type IngestResponse struct {
	Status           string  `json:"status"`
	DocumentID       string  `json:"document_id,omitempty"`
	ChunksCount      int     `json:"chunks_count,omitempty"`
	ProcessingTimeMS float64 `json:"processing_time_ms,omitempty"`
	Filename         string  `json:"filename,omitempty"`
	Error            string  `json:"error,omitempty"`
}

// DocumentItem represents an indexed document.
type DocumentItem struct {
	ID          string                 `json:"id"`
	TextSnippet string                 `json:"text_snippet"`
	Metadata    map[string]interface{} `json:"metadata"`
	IndexedAt   string                 `json:"indexed_at,omitempty"`
}

// HealthResponse represents cluster status.
type HealthResponse struct {
	Status      string                 `json:"status"`
	Version     string                 `json:"version"`
	Environment string                 `json:"environment"`
	Components  map[string]interface{} `json:"components"`
}

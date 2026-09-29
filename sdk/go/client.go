package ses

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// Client is the official Go SDK client for SES Semantic Engine.
type Client struct {
	baseURL    string
	apiKey     string
	httpClient HTTPDoer
	timeout    time.Duration
}

// NewClient creates a new SES client.
func NewClient(config ClientConfig) (*Client, error) {
	if config.APIKey == "" {
		return nil, fmt.Errorf("ses: APIKey is required")
	}

	baseURL := config.BaseURL
	if baseURL == "" {
		baseURL = "http://localhost:8000"
	}
	baseURL = strings.TrimRight(baseURL, "/")

	timeout := config.Timeout
	if timeout == 0 {
		timeout = 30 * time.Second
	}

	httpClient := config.HTTPClient
	if httpClient == nil {
		httpClient = &http.Client{Timeout: timeout}
	}

	return &Client{
		baseURL:    baseURL,
		apiKey:     config.APIKey,
		httpClient: httpClient,
		timeout:    timeout,
	}, nil
}

func (c *Client) doRequest(ctx context.Context, method, path string, body io.Reader, contentType string, target interface{}) error {
	reqURL := fmt.Sprintf("%s%s", c.baseURL, path)
	req, err := http.NewRequestWithContext(ctx, method, reqURL, body)
	if err != nil {
		return fmt.Errorf("ses: failed to create request: %w", err)
	}

	req.Header.Set("X-API-Key", c.apiKey)
	if contentType != "" {
		req.Header.Set("Content-Type", contentType)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("ses: request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("ses: error response (HTTP %d): %s", resp.StatusCode, string(bodyBytes))
	}

	if target != nil {
		if err := json.NewDecoder(resp.Body).Decode(target); err != nil {
			return fmt.Errorf("ses: failed to decode response: %w", err)
		}
	}

	return nil
}

// Search performs semantic search and optional local RAG generation.
func (c *Client) Search(ctx context.Context, req SearchRequest) (*SearchResponse, error) {
	if req.Namespace == "" {
		req.Namespace = "default"
	}
	if req.TopK <= 0 {
		req.TopK = 5
	}

	data, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("ses: failed to marshal search request: %w", err)
	}

	var resp SearchResponse
	if err := c.doRequest(ctx, http.MethodPost, "/api/v1/search", bytes.NewReader(data), "application/json", &resp); err != nil {
		return nil, err
	}

	return &resp, nil
}

// IngestText indexes plain text into a namespace.
func (c *Client) IngestText(ctx context.Context, req IngestTextRequest) (*IngestResponse, error) {
	if req.Namespace == "" {
		req.Namespace = "default"
	}

	data, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("ses: failed to marshal ingest request: %w", err)
	}

	var resp IngestResponse
	if err := c.doRequest(ctx, http.MethodPost, "/api/v1/ingest/text", bytes.NewReader(data), "application/json", &resp); err != nil {
		return nil, err
	}

	return &resp, nil
}

// IngestFile uploads and indexes a binary file (PDF, DOCX, XLSX, TXT).
func (c *Client) IngestFile(ctx context.Context, namespace, filename string, fileReader io.Reader, metadata map[string]interface{}) (*IngestResponse, error) {
	if namespace == "" {
		namespace = "default"
	}

	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)

	part, err := writer.CreateFormFile("file", filename)
	if err != nil {
		return nil, fmt.Errorf("ses: failed to create form file: %w", err)
	}

	if _, err := io.Copy(part, fileReader); err != nil {
		return nil, fmt.Errorf("ses: failed to copy file content: %w", err)
	}

	if err := writer.WriteField("namespace", namespace); err != nil {
		return nil, fmt.Errorf("ses: failed to write namespace field: %w", err)
	}

	if metadata != nil {
		metaBytes, err := json.Marshal(metadata)
		if err == nil {
			_ = writer.WriteField("metadata", string(metaBytes))
		}
	}

	if err := writer.Close(); err != nil {
		return nil, fmt.Errorf("ses: failed to close multipart writer: %w", err)
	}

	var resp IngestResponse
	if err := c.doRequest(ctx, http.MethodPost, "/api/v1/ingest/file", body, writer.FormDataContentType(), &resp); err != nil {
		return nil, err
	}

	return &resp, nil
}

// ListDocuments lists documents in a namespace.
func (c *Client) ListDocuments(ctx context.Context, namespace string) ([]DocumentItem, error) {
	if namespace == "" {
		namespace = "default"
	}

	path := fmt.Sprintf("/api/v1/documents?namespace=%s", url.QueryEscape(namespace))
	var result struct {
		Documents []DocumentItem `json:"documents"`
	}

	if err := c.doRequest(ctx, http.MethodGet, path, nil, "", &result); err != nil {
		return nil, err
	}

	return result.Documents, nil
}

// DeleteDocument deletes a document by ID.
func (c *Client) DeleteDocument(ctx context.Context, namespace, documentID string) (bool, error) {
	path := fmt.Sprintf("/api/v1/documents/%s?namespace=%s", url.PathEscape(documentID), url.QueryEscape(namespace))
	var result struct {
		Status string `json:"status"`
	}

	if err := c.doRequest(ctx, http.MethodDelete, path, nil, "", &result); err != nil {
		return false, err
	}

	return result.Status == "success", nil
}

// Health checks the cluster status.
func (c *Client) Health(ctx context.Context) (*HealthResponse, error) {
	var resp HealthResponse
	if err := c.doRequest(ctx, http.MethodGet, "/api/v1/health", nil, "", &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

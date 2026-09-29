import type {
  ClientOptions,
  SearchParams,
  SearchResponse,
  IngestTextParams,
  IngestFileParams,
  IngestResponse,
  DocumentItem,
  HealthResponse,
  ApiKeyDetails,
  ApiAnalytics,
  RerankParams,
  RerankResponse,
} from "./types.js";

export class SemanticEngineClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly timeoutMs: number;

  constructor(options: ClientOptions) {
    if (!options.apiKey) {
      throw new Error("SemanticEngineClient: apiKey is required.");
    }
    this.baseUrl = (options.baseUrl || "http://localhost:8000").replace(/\/+$/, "");
    this.apiKey = options.apiKey;
    this.timeoutMs = options.timeoutMs || 30000;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;
    const headers = new Headers(options.headers || {});
    headers.set("X-API-Key", this.apiKey);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await fetch(url, {
        ...options,
        headers,
        signal: controller.signal,
      });

      if (!response.ok) {
        let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
        try {
          const errorBody = await response.json();
          if (errorBody && typeof errorBody.detail === "string") {
            errorMessage = errorBody.detail;
          }
        } catch {
          // Ignore JSON parse errors for non-JSON responses
        }
        throw new Error(errorMessage);
      }

      return (await response.json()) as T;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  /**
   * Search vectors and optionally generate RAG answer via local LLM.
   */
  async search(params: SearchParams): Promise<SearchResponse> {
    return this.request<SearchResponse>("/api/v1/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: params.query,
        namespace: params.namespace || "default",
        top_k: params.topK || 5,
        threshold: params.threshold || 0.0,
        generate_answer: params.generateAnswer || false,
        model_override: params.modelOverride,
      }),
    });
  }

  /**
   * Rerank a list of documents based on semantic relevance to a query.
   * Leverages zero-copy Rust acceleration.
   */
  async rerank(params: RerankParams): Promise<RerankResponse> {
    return this.request<RerankResponse>("/v1/rerank", {
      method: "POST",
      headers: { 
        "Content-Type": "application/json",
        "Authorization": `Bearer ${this.apiKey}`
      },
      body: JSON.stringify({
        query: params.query,
        documents: params.documents,
        top_n: params.topN || 5,
        return_documents: params.returnDocuments ?? true,
      }),
    });
  }

  /**
   * Ingest raw text into a specific namespace.
   */
  async ingestText(params: IngestTextParams): Promise<IngestResponse> {
    return this.request<IngestResponse>("/api/v1/ingest/text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: params.text,
        namespace: params.namespace || "default",
        metadata: params.metadata || {},
      }),
    });
  }

  /**
   * Upload and ingest a file (PDF, DOCX, XLSX, TXT).
   */
  async ingestFile(params: IngestFileParams): Promise<IngestResponse> {
    const formData = new FormData();
    const fileBlob = params.file instanceof Blob 
      ? params.file 
      : new Blob([params.file as unknown as BlobPart]);

    formData.append("file", fileBlob, params.filename);
    formData.append("namespace", params.namespace || "default");
    if (params.metadata) {
      formData.append("metadata", JSON.stringify(params.metadata));
    }

    return this.request<IngestResponse>("/api/v1/ingest/file", {
      method: "POST",
      body: formData,
    });
  }

  /**
   * List indexed documents in a namespace.
   */
  async listDocuments(namespace = "default"): Promise<DocumentItem[]> {
    const data = await this.request<{ documents: DocumentItem[] }>(
      `/api/v1/documents?namespace=${encodeURIComponent(namespace)}`
    );
    return data.documents || [];
  }

  /**
   * Delete a document by its ID.
   */
  async deleteDocument(namespace: string, documentId: string): Promise<boolean> {
    const data = await this.request<{ status: string }>(
      `/api/v1/documents/${encodeURIComponent(documentId)}?namespace=${encodeURIComponent(namespace)}`,
      { method: "DELETE" }
    );
    return data.status === "success";
  }

  /**
   * Get cluster health status (Qdrant, Redis, Ollama).
   */
  async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>("/api/v1/health");
  }

  /**
   * Get API usage analytics and latency statistics (Admin role required).
   */
  async getAnalytics(): Promise<ApiAnalytics> {
    return this.request<ApiAnalytics>("/api/v1/admin/stats");
  }

  /**
   * Create a new API key (Admin role required).
   */
  async createApiKey(keyName: string, tier = "standard"): Promise<ApiKeyDetails> {
    return this.request<ApiKeyDetails>("/api/v1/admin/keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key_name: keyName, tier }),
    });
  }

  /**
   * Revoke an API key (Admin role required).
   */
  async revokeApiKey(keyName: string): Promise<boolean> {
    const data = await this.request<{ status: string }>(
      `/api/v1/admin/keys/${encodeURIComponent(keyName)}`,
      { method: "DELETE" }
    );
    return data.status === "success";
  }
}

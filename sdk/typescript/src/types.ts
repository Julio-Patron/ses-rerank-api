export interface ClientOptions {
  baseUrl?: string;
  apiKey: string;
  timeoutMs?: number;
}

export interface SearchParams {
  query: string;
  namespace?: string;
  topK?: number;
  threshold?: number;
  generateAnswer?: boolean;
  modelOverride?: string;
}

export interface SearchResultItem {
  id: string;
  score: number;
  text: string;
  metadata: Record<string, unknown>;
}

export interface SearchResponse {
  query: string;
  namespace: string;
  results: SearchResultItem[];
  answer: string | null;
  total_documents: number;
  search_time_ms: number;
  total_time_ms: number;
  rust_accelerated: boolean;
  metadata?: Record<string, unknown>;
}

export interface IngestTextParams {
  text: string;
  namespace?: string;
  metadata?: Record<string, unknown>;
}

export interface IngestFileParams {
  file: Blob | File | Buffer;
  filename: string;
  namespace?: string;
  metadata?: Record<string, unknown>;
}

export interface IngestResponse {
  status: "success" | "error";
  document_id?: string;
  chunks_count?: number;
  processing_time_ms?: number;
  filename?: string;
  error?: string;
}

export interface DocumentItem {
  id: string;
  text_snippet: string;
  metadata: Record<string, unknown>;
  indexed_at?: string;
}

export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  version: string;
  environment: string;
  components: {
    qdrant: { status: string; url: string };
    redis: { status: string; host: string };
    ollama: { status: string; model: string };
  };
}

export interface ApiKeyDetails {
  key_name: string;
  tier: string;
  active: boolean;
  created_at: string;
  key_preview: string;
  api_key?: string;
}

export interface EndpointMetric {
  total_calls: number;
  avg_latency_ms: number;
  errors_count: number;
}

export interface ApiAnalytics {
  total_requests: number;
  success_rate: number;
  avg_latency_ms: number;
  endpoints: Record<string, EndpointMetric>;
}

export interface RerankParams {
  query: string;
  documents: string[];
  topN?: number;
  returnDocuments?: boolean;
}

export interface RerankDocumentResult {
  index: number;
  relevance_score: number;
  document?: string;
}

export interface RerankTokenMetrics {
  total_tokens: number;
}

export interface RerankMeta {
  tokens: RerankTokenMetrics;
  credits_deducted: number;
  credits_remaining: number;
  tokens_saved: number;
}

export interface RerankResponse {
  results: RerankDocumentResult[];
  meta: RerankMeta;
}

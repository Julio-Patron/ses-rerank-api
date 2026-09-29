export type ApiKeyRole = "admin" | "client" | string;

export interface ApiKeyData {
  key: string;
  name: string;
  namespace: string;
  rate_limit: number;
  role: ApiKeyRole;
  created_at: number;
}

export interface CreateApiKeyRequest {
  name: string;
  namespace: string;
  rate_limit: number;
  role: ApiKeyRole;
}

export interface CreateApiKeyResponse {
  key: string;
  key_details: ApiKeyData;
}

export interface DocumentMetadata {
  filename?: string;
  file_name?: string;
  namespace?: string;
  upload_time?: string;
  total_chunks?: number;
  chunk_index?: number;
  file_size?: number;
  [key: string]: unknown;
}

export interface DocumentItem {
  id: string;
  text?: string;
  text_snippet?: string;
  metadata?: DocumentMetadata;
  indexed_at?: number | string;
}

export interface SearchResultItem extends DocumentItem {
  score: number;
}

export interface SearchRequest {
  query: string;
  top_k: number;
  threshold: number;
  generate_answer: boolean;
  model_override?: string;
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
}

export interface HealthResponse {
  status: "healthy" | "degraded" | string;
  timestamp: string;
  services: Record<string, string>;
}

export interface UsageLog {
  timestamp: string;
  key_name: string;
  endpoint: string;
  namespace: string;
  status_code: number;
  latency_ms: number;
}

export interface KeyPerformance {
  name: string;
  namespace: string;
  role: ApiKeyRole;
  total_calls: number;
  avg_latency_ms: number;
}

export interface AnalyticsData {
  total_requests: number;
  total_errors: number;
  total_searches: number;
  total_ingestions: number;
  average_latency_ms: number;
  keys_performance: KeyPerformance[];
  recent_logs: UsageLog[];
}

export interface DocumentListResponse {
  documents: DocumentItem[];
  count: number;
  namespace: string;
}

export interface ApiKeyListResponse {
  keys: ApiKeyData[];
}

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { api } from '../lib/api';
import { GatewayError } from '../lib/gateway-errors';

describe('Portal API Client (Contract & Integration)', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('ses_api_url', 'http://localhost:8000');
    localStorage.setItem('ses_api_key', 'ses_test_api_key_123');
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('getHealth sends GET request and returns health payload', async () => {
    const mockHealth = {
      status: 'healthy',
      timestamp: '2026-08-28T00:00:00Z',
      services: {
        qdrant: 'connected',
        redis: 'connected',
        ollama_api: 'connected',
        rust_acceleration: 'active'
      }
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockHealth
    } as Response);

    const result = await api.getHealth();
    expect(result.status).toBe('healthy');
    expect(result.services.qdrant).toBe('connected');
    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/health',
      expect.objectContaining({ cache: 'no-store' })
    );
  });

  it('search sends POST with payload and authorization header', async () => {
    const mockSearchResponse = {
      query: 'contract clause',
      namespace: 'tenant_default',
      results: [
        {
          id: 'doc-1',
          score: 0.92,
          text: 'Termination clause details',
          text_snippet: 'Termination clause details',
          metadata: { filename: 'contract.pdf' },
          indexed_at: 1700000000
        }
      ],
      answer: 'The contract specifies a 30-day notice.',
      total_documents: 15,
      search_time_ms: 2.1,
      total_time_ms: 15.4,
      rust_accelerated: true,
      metadata: { llm_status: 'success', search_time_ms: 2.1, total_time_ms: 15.4 }
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockSearchResponse
    } as Response);

    const payload = {
      query: 'contract clause',
      top_k: 5,
      threshold: 0.1,
      generate_answer: true
    };

    const result = await api.search(payload);
    expect(result.query).toBe('contract clause');
    expect(result.results.length).toBe(1);
    expect(result.rust_accelerated).toBe(true);

    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/search',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(payload)
      })
    );
  });

  it('listDocuments requests with limit query param', async () => {
    const mockDocs = {
      documents: [
        {
          id: 'doc-1',
          text_snippet: 'Sample snippet',
          metadata: { filename: 'note.txt' },
          indexed_at: 1700000000
        }
      ],
      count: 1,
      namespace: 'tenant_default'
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockDocs
    } as Response);

    const result = await api.listDocuments(25);
    expect(result.count).toBe(1);
    expect(result.documents[0].id).toBe('doc-1');
    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/documents?limit=25',
      expect.anything()
    );
  });

  it('deleteDocument sends DELETE request to document path', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'success', message: 'Document doc-123 deleted' })
    } as Response);

    const result = await api.deleteDocument('doc-123');
    expect(result.status).toBe('success');
    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/documents/doc-123',
      expect.objectContaining({ method: 'DELETE' })
    );
  });

  it('createApiKey sends client details and receives key details', async () => {
    const mockCreated = {
      key: 'ses_secret_token_live',
      key_details: {
        key: 'hash_of_key',
        id: 'key-id-1',
        tenant_id: 'tenant-id-1',
        key_prefix: 'ses_secret_toke',
        name: 'New App Key',
        namespace: 'tenant_app',
        rate_limit: 100,
        role: 'client',
        created_at: 1700000000
      }
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockCreated
    } as Response);

    const result = await api.createApiKey({
      name: 'New App Key',
      namespace: 'tenant_app',
      rate_limit: 100,
      role: 'client'
    });

    expect(result.key).toBe('ses_secret_token_live');
    expect(result.key_details.name).toBe('New App Key');
  });

  it('throws descriptive error on 401/403 with response detail', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: 'Forbidden',
      json: async () => ({ detail: 'Invalid or expired API Key' })
    } as Response);

    await expect(api.search({ query: 'test' })).rejects.toThrow('Invalid or expired API Key');
  });

  it('rejects protected requests locally when the API key is missing', async () => {
    localStorage.removeItem('ses_api_key');
    global.fetch = vi.fn();

    await expect(api.getAnalytics()).rejects.toMatchObject({
      kind: 'configuration',
    });
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('classifies service-unavailable responses as dependency failures', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      statusText: 'Service Unavailable',
      json: async () => ({ detail: 'Rate limiting service unavailable.' })
    } as Response);

    try {
      await api.search({ query: 'test' });
      throw new Error('Expected the request to fail');
    } catch (error) {
      expect(error).toBeInstanceOf(GatewayError);
      expect(error).toMatchObject({ kind: 'dependency', status: 503 });
    }
  });

  it('classifies browser fetch failures as network or CORS failures', async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(api.search({ query: 'test' })).rejects.toMatchObject({
      kind: 'network',
    });
  });
});

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SearchPage from '../app/search/page';
import { ToastProvider } from '../components/Toast';
import { api } from '../lib/api';
import { GatewayError } from '../lib/gateway-errors';

vi.mock('../lib/api', () => ({
  api: {
    search: vi.fn(),
    downloadReport: vi.fn(),
  },
}));

describe('SearchPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders search input, options and empty state initially', () => {
    render(
      <ToastProvider>
        <SearchPage />
      </ToastProvider>
    );

    expect(screen.getByText('RAG Search')).toBeDefined();
    expect(screen.getByPlaceholderText('Ask a question about your documents...')).toBeDefined();
    expect(screen.getByText('Ready to search')).toBeDefined();
  });

  it('performs search and displays results and synthesized answer', async () => {
    vi.mocked(api.search).mockResolvedValue({
      query: 'What is semantic search?',
      namespace: 'default',
      results: [
        {
          id: 'chunk_01',
          text: 'Semantic search uses vector embeddings for semantic similarity.',
          score: 0.92,
          metadata: { filename: 'guide.pdf', chunk_index: 1 },
          indexed_at: 1735689600,
        },
      ],
      answer: 'Semantic search is a retrieval technique using dense vector representations.',
      total_documents: 1,
      search_time_ms: 14.2,
      total_time_ms: 18.5,
      rust_accelerated: true,
    });

    render(
      <ToastProvider>
        <SearchPage />
      </ToastProvider>
    );

    const input = screen.getByPlaceholderText('Ask a question about your documents...');
    fireEvent.change(input, { target: { value: 'What is semantic search?' } });

    const searchButton = screen.getByRole('button', { name: /search/i });
    fireEvent.click(searchButton);

    await waitFor(() => {
      expect(screen.getByText('Synthesized Answer')).toBeDefined();
      expect(screen.getByText('Semantic search is a retrieval technique using dense vector representations.')).toBeDefined();
      expect(screen.getByText('guide.pdf')).toBeDefined();
      expect(screen.getByText('Rust hybrid')).toBeDefined();
    });
  });

  it('shows an actionable connection state after a failed search', async () => {
    vi.mocked(api.search).mockRejectedValue(
      new GatewayError('network', 'Failed to fetch'),
    );

    render(
      <ToastProvider>
        <SearchPage />
      </ToastProvider>
    );

    fireEvent.change(
      screen.getByPlaceholderText('Ask a question about your documents...'),
      { target: { value: 'test query' } },
    );
    fireEvent.click(screen.getByRole('button', { name: /^search$/i }));

    await waitFor(() => {
      expect(screen.getByText('Gateway unavailable')).toBeDefined();
      expect(screen.getAllByText(/could not reach the Gateway/i).length).toBeGreaterThan(0);
      expect(screen.queryByText('Ready to search')).toBeNull();
    });
  });
});

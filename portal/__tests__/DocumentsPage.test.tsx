import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import DocumentsPage from '../app/documents/page';
import { ToastProvider } from '../components/Toast';
import { api } from '../lib/api';
import { GatewayError } from '../lib/gateway-errors';

vi.mock('../lib/api', () => ({
  api: {
    listDocuments: vi.fn(),
    ingestFile: vi.fn(),
    deleteDocument: vi.fn(),
  },
}));

describe('DocumentsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders uploaded document list', async () => {
    vi.mocked(api.listDocuments).mockResolvedValue({
      documents: [
        {
          id: 'doc_abc',
          text_snippet: 'Sample contract text...',
          metadata: { filename: 'sample.pdf', namespace: 'contracts', total_chunks: 2 },
        },
      ],
    });

    render(
      <ToastProvider>
        <DocumentsPage />
      </ToastProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Knowledge Base')).toBeDefined();
      expect(screen.getByText('sample.pdf')).toBeDefined();
      expect(screen.getByText('contracts')).toBeDefined();
    });
  });

  it('deletes document when confirmed', async () => {
    vi.mocked(api.listDocuments).mockResolvedValue({
      documents: [
        {
          id: 'doc_to_delete',
          text_snippet: 'Temporary text',
          metadata: { filename: 'to_delete.txt', namespace: 'default' },
        },
      ],
    });
    vi.mocked(api.deleteDocument).mockResolvedValue({ status: 'success' });

    render(
      <ToastProvider>
        <DocumentsPage />
      </ToastProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('to_delete.txt')).toBeDefined();
    });

    const deleteBtn = screen.getByTitle('Delete Document');
    fireEvent.click(deleteBtn);

    const yesBtn = screen.getByText('Yes');
    fireEvent.click(yesBtn);

    await waitFor(() => {
      expect(api.deleteDocument).toHaveBeenCalledWith('doc_to_delete');
    });
  });

  it('distinguishes an unavailable Gateway from an empty collection', async () => {
    vi.mocked(api.listDocuments).mockRejectedValue(
      new GatewayError('dependency', 'Qdrant unavailable', 503),
    );

    render(
      <ToastProvider>
        <DocumentsPage />
      </ToastProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Gateway unavailable')).toBeDefined();
      expect(screen.getByText(/required service is unavailable/i)).toBeDefined();
      expect(screen.getByText('Indexed Documents (Unavailable)')).toBeDefined();
      expect(screen.queryByText('No documents yet')).toBeNull();
    });
  });
});

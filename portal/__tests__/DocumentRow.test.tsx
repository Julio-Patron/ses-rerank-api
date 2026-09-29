import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { DocumentRow } from '../components/DocumentRow';
import { DocumentItem } from '../lib/types';

describe('DocumentRow', () => {
  const mockDoc: DocumentItem = {
    id: 'doc_12345',
    text_snippet: 'This is a test document snippet',
    metadata: {
      filename: 'contract.pdf',
      namespace: 'legal',
      total_chunks: 4,
      upload_time: '2026-01-01T12:00:00Z',
    },
  };

  it('renders document metadata properly', () => {
    const onDelete = vi.fn().mockResolvedValue(undefined);
    render(<DocumentRow doc={mockDoc} onDelete={onDelete} />);

    expect(screen.getByText('contract.pdf')).toBeDefined();
    expect(screen.getByText('legal')).toBeDefined();
    expect(screen.getByText('4 Chunks')).toBeDefined();
    expect(screen.getByText('Indexed')).toBeDefined();
  });

  it('shows confirmation prompt and calls onDelete when confirmed', async () => {
    const onDelete = vi.fn().mockResolvedValue(undefined);
    render(<DocumentRow doc={mockDoc} onDelete={onDelete} />);

    // Click delete icon button
    const deleteBtn = screen.getByTitle('Delete Document');
    fireEvent.click(deleteBtn);

    // Confirm prompt should appear
    expect(screen.getByText('Delete?')).toBeDefined();
    const yesBtn = screen.getByText('Yes');
    fireEvent.click(yesBtn);

    expect(onDelete).toHaveBeenCalledWith('doc_12345');
  });

  it('cancels deletion when clicking No', () => {
    const onDelete = vi.fn().mockResolvedValue(undefined);
    render(<DocumentRow doc={mockDoc} onDelete={onDelete} />);

    const deleteBtn = screen.getByTitle('Delete Document');
    fireEvent.click(deleteBtn);

    const noBtn = screen.getByText('No');
    fireEvent.click(noBtn);

    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.queryByText('Delete?')).toBeNull();
  });
});

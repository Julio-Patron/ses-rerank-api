import React from 'react';
import { render, screen } from '@testing-library/react';
import { SearchResult } from '../components/SearchResult';
import { SearchResultItem } from '../lib/types';

describe('SearchResult', () => {
  const mockResult: SearchResultItem = {
    id: '123',
    text: 'Some matched text',
    score: 0.85,
    text_snippet: 'matched text snippet',
    metadata: {
      filename: 'document.pdf',
      chunk_index: 2
    },
    indexed_at: 1672531200 // 2023-01-01
  };

  it('renders filename and text snippet', () => {
    render(<SearchResult result={mockResult} />);
    expect(screen.getByText('document.pdf')).toBeDefined();
    expect(screen.getByText('matched text snippet')).toBeDefined();
    expect(screen.getByText('85% Match')).toBeDefined();
    expect(screen.getByText('Chunk 2')).toBeDefined();
  });

  it('uses fallback file name when metadata missing', () => {
    const resultWithoutMetadata = { ...mockResult, metadata: {} };
    render(<SearchResult result={resultWithoutMetadata} />);
    expect(screen.getByText('Unknown file')).toBeDefined();
  });
});

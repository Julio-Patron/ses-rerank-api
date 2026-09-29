import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { EmptyState } from '../components/EmptyState';
import { FileText } from 'lucide-react';

describe('EmptyState', () => {
  it('renders title, description and icon', () => {
    render(
      <EmptyState
        icon={FileText}
        title="No documents yet"
        description="Upload your first document to begin indexing."
      />
    );

    expect(screen.getByText('No documents yet')).toBeDefined();
    expect(screen.getByText('Upload your first document to begin indexing.')).toBeDefined();
  });
});

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ApiKeyRow } from '../components/ApiKeyRow';
import { ToastProvider } from '../components/Toast';
import { ApiKeyData } from '../lib/types';

describe('ApiKeyRow', () => {
  const mockKey: ApiKeyData = {
    key: 'ses_live_abc123',
    name: 'agent_key_01',
    role: 'admin',
    namespace: 'default',
    rate_limit: 120,
    created_at: 1735689600,
  };

  it('renders key details and role badge properly', () => {
    const onRevoke = vi.fn().mockResolvedValue(undefined);
    render(
      <ToastProvider>
        <ApiKeyRow apiKey={mockKey} onRevoke={onRevoke} />
      </ToastProvider>
    );

    expect(screen.getByText('agent_key_01')).toBeDefined();
    expect(screen.getByText('ADMIN')).toBeDefined();
    expect(screen.getByText('ses_live_abc123')).toBeDefined();
    expect(screen.getByText('Limit: 120/min')).toBeDefined();
  });

  it('shows revoke confirmation and executes onRevoke callback', () => {
    const onRevoke = vi.fn().mockResolvedValue(undefined);
    render(
      <ToastProvider>
        <ApiKeyRow apiKey={mockKey} onRevoke={onRevoke} />
      </ToastProvider>
    );

    const revokeBtn = screen.getByTitle('Revoke Key');
    fireEvent.click(revokeBtn);

    expect(screen.getByText('Revoke?')).toBeDefined();
    const yesBtn = screen.getByText('Yes');
    fireEvent.click(yesBtn);

    expect(onRevoke).toHaveBeenCalledWith('ses_live_abc123');
  });

  it('renders full key to copy banner when fullKeyToCopy prop is provided', () => {
    const onRevoke = vi.fn().mockResolvedValue(undefined);
    render(
      <ToastProvider>
        <ApiKeyRow
          apiKey={mockKey}
          onRevoke={onRevoke}
          fullKeyToCopy="ses_live_full_secret_raw_token_xyz"
        />
      </ToastProvider>
    );

    expect(screen.getByText('ses_live_full_secret_raw_token_xyz')).toBeDefined();
    expect(screen.getByText("Copy this key now. You won't be able to see it again.")).toBeDefined();
  });
});

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import KeysPage from '../app/keys/page';
import { ToastProvider } from '../components/Toast';
import { api } from '../lib/api';

vi.mock('../lib/api', () => ({
  api: {
    listApiKeys: vi.fn(),
    createApiKey: vi.fn(),
    revokeApiKey: vi.fn(),
  },
}));

describe('KeysPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders API keys list and creation form', async () => {
    vi.mocked(api.listApiKeys).mockResolvedValue({
      keys: [
        {
          key: 'ses_live_admin123',
          name: 'master_key',
          role: 'admin',
          namespace: 'default',
          rate_limit: 500,
          created_at: 1735689600,
        },
      ],
    });

    render(
      <ToastProvider>
        <KeysPage />
      </ToastProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('API Keys')).toBeDefined();
      expect(screen.getByText('master_key')).toBeDefined();
      expect(screen.getByText('Generate API Key')).toBeDefined();
    });
  });

  it('creates new API key when submitting form', async () => {
    vi.mocked(api.listApiKeys).mockResolvedValue({ keys: [] });
    vi.mocked(api.createApiKey).mockResolvedValue({
      key: 'ses_live_new_raw_token_999',
      name: 'new_service_key',
      role: 'client',
      namespace: 'global',
      rate_limit: 100,
      created_at: 1735689600,
    });

    render(
      <ToastProvider>
        <KeysPage />
      </ToastProvider>
    );

    const nameInput = screen.getByPlaceholderText('e.g. Production Web App');
    fireEvent.change(nameInput, { target: { value: 'new_service_key' } });

    const submitBtn = screen.getByRole('button', { name: /generate api key/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(api.createApiKey).toHaveBeenCalledWith({
        name: 'new_service_key',
        role: 'client',
        rate_limit: 100,
        namespace: 'global',
      });
    });
  });
});

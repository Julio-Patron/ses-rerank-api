import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SettingsPage from '../app/settings/page';
import { ToastProvider } from '../components/Toast';
import { api } from '../lib/api';
import { GatewayError } from '../lib/gateway-errors';

vi.mock('../lib/api', () => ({
  api: {
    getHealth: vi.fn(),
    getAnalytics: vi.fn(),
  },
}));

describe('SettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders settings form and saves values into localStorage', async () => {
    render(
      <ToastProvider>
        <SettingsPage />
      </ToastProvider>
    );

    const urlInput = screen.getByPlaceholderText('http://localhost:8000');
    const keyInput = screen.getByPlaceholderText('ses_...');

    fireEvent.change(urlInput, { target: { value: 'http://127.0.0.1:8000' } });
    fireEvent.change(keyInput, { target: { value: 'ses_live_admin_secret_key' } });

    const saveBtn = screen.getByRole('button', { name: /save settings/i });
    fireEvent.click(saveBtn);

    expect(localStorage.getItem('ses_api_url')).toBe('http://127.0.0.1:8000');
    expect(localStorage.getItem('ses_api_key')).toBe('ses_live_admin_secret_key');
  });

  it('tests connection and displays connected status on success', async () => {
    vi.mocked(api.getHealth).mockResolvedValue({
      status: 'healthy',
      version: '2.0.0',
      environment: 'production',
      services: {},
    });
    vi.mocked(api.getAnalytics).mockResolvedValue({
      total_searches: 10,
      total_ingestions: 5,
      average_latency_ms: 20,
    });

    render(
      <ToastProvider>
        <SettingsPage />
      </ToastProvider>
    );

    const testBtn = screen.getByRole('button', { name: /test connection/i });
    fireEvent.click(testBtn);

    await waitFor(() => {
      expect(screen.getByText('Connected')).toBeDefined();
    });
  });

  it('shows the concrete authentication failure when connection testing fails', async () => {
    vi.mocked(api.getHealth).mockResolvedValue({
      status: 'healthy',
      timestamp: '2026-09-02T00:00:00Z',
      services: {},
    });
    vi.mocked(api.getAnalytics).mockRejectedValue(
      new GatewayError('authentication', 'Invalid API key', 403),
    );

    render(
      <ToastProvider>
        <SettingsPage />
      </ToastProvider>
    );

    fireEvent.click(screen.getByRole('button', { name: /test connection/i }));

    await waitFor(() => {
      expect(screen.getAllByText(/rejected this API key/i).length).toBeGreaterThan(0);
    });
  });
});

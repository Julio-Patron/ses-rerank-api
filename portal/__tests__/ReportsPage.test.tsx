import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ReportsPage from '../app/reports/page';
import { ToastProvider } from '../components/Toast';
import { api } from '../lib/api';

vi.mock('../lib/api', () => ({
  api: {
    downloadReport: vi.fn(),
  },
}));

describe('ReportsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders report cards and triggers PDF report downloads', async () => {
    vi.mocked(api.downloadReport).mockResolvedValue(undefined);

    render(
      <ToastProvider>
        <ReportsPage />
      </ToastProvider>
    );

    expect(screen.getByText('Corporate Reports')).toBeDefined();
    expect(screen.getByText('Usage & Billing Analytics')).toBeDefined();
    expect(screen.getByText('System Health Snapshot')).toBeDefined();

    const usageBtn = screen.getByRole('button', { name: /generate usage report/i });
    fireEvent.click(usageBtn);

    await waitFor(() => {
      expect(api.downloadReport).toHaveBeenCalledWith('/api/v1/admin/reports/usage');
    });

    const healthBtn = screen.getByRole('button', { name: /generate health report/i });
    fireEvent.click(healthBtn);

    await waitFor(() => {
      expect(api.downloadReport).toHaveBeenCalledWith('/api/v1/admin/reports/health');
    });
  });
});

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import DashboardPage from '../app/dashboard/page';
import { api } from '../lib/api';
import { GatewayError } from '../lib/gateway-errors';

vi.mock('../lib/api', () => ({
  api: {
    getAnalytics: vi.fn(),
    getHealth: vi.fn(),
  },
}));

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading spinner and then metrics and activity table', async () => {
    vi.mocked(api.getAnalytics).mockResolvedValue({
      total_searches: 42,
      total_ingestions: 15,
      average_latency_ms: 24.5,
      keys_performance: [{ key_name: 'admin_key', calls: 57, avg_latency: 24.5 }],
      recent_logs: [
        {
          timestamp: '2026-08-28T04:00:00Z',
          endpoint: '/api/v1/search',
          key_name: 'admin_key',
          status_code: 200,
          latency_ms: 18.2,
        },
      ],
    });

    vi.mocked(api.getHealth).mockResolvedValue({
      status: 'healthy',
      version: '2.0.0',
      environment: 'production',
      services: {
        qdrant: 'healthy',
        redis: 'healthy',
        ollama: 'healthy',
      },
    });

    render(<DashboardPage />);

    // Initially shows loading state
    expect(screen.getByText('Loading dashboard metrics...')).toBeDefined();

    // After resolution, shows dashboard content
    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeDefined();
      expect(screen.getByText('42')).toBeDefined();
      expect(screen.getByText('15')).toBeDefined();
      expect(screen.getByText('24.5 ms')).toBeDefined();
      expect(screen.getByText('/api/v1/search')).toBeDefined();
    });
  });

  it('shows a connection error instead of zero metrics when the Gateway fails', async () => {
    vi.mocked(api.getAnalytics).mockRejectedValue(
      new GatewayError('authentication', 'Invalid API key', 403),
    );
    vi.mocked(api.getHealth).mockResolvedValue({
      status: 'healthy',
      timestamp: '2026-09-02T00:00:00Z',
      services: {},
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText('Gateway unavailable')).toBeDefined();
      expect(screen.getByText(/rejected this API key/i)).toBeDefined();
      expect(screen.queryByText('Total Searches')).toBeNull();
    });
  });
});

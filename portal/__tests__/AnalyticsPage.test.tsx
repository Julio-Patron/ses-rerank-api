import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import AnalyticsPage from '../app/analytics/page';
import { api } from '../lib/api';

vi.mock('../lib/api', () => ({
  api: {
    getAnalytics: vi.fn(),
  },
}));

// Mock ResizeObserver which is used by recharts ResponsiveContainer
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

describe('AnalyticsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders analytics charts and key performance metrics', async () => {
    vi.mocked(api.getAnalytics).mockResolvedValue({
      total_requests: 120,
      total_errors: 2,
      total_searches: 85,
      total_ingestions: 35,
      average_latency_ms: 28.4,
      recent_logs: [
        {
          timestamp: '2026-08-28T04:00:00Z',
          endpoint: '/api/v1/search',
          key_name: 'prod_app_key',
          status_code: 200,
          latency_ms: 18.2,
        },
      ],
      keys_performance: [
        {
          name: 'prod_app_key',
          namespace: 'production',
          role: 'client',
          total_calls: 118,
          avg_latency_ms: 27.9,
        },
      ],
    });

    render(<AnalyticsPage />);

    await waitFor(() => {
      expect(screen.getByText('Analytics')).toBeDefined();
      expect(screen.getByText('Observed Request Volume')).toBeDefined();
      expect(screen.getByText('API Key Performance')).toBeDefined();
      expect(screen.getByText('prod_app_key')).toBeDefined();
      expect(screen.getByText('production')).toBeDefined();
      expect(screen.getByText('118')).toBeDefined();
    });
  });
});

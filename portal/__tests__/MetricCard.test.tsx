import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MetricCard } from '../components/MetricCard';
import { Search } from 'lucide-react';

describe('MetricCard', () => {
  it('renders title and string/number values correctly', () => {
    render(
      <MetricCard
        title="Total Searches"
        value={1542}
        icon={Search}
      />
    );
    expect(screen.getByText('Total Searches')).toBeDefined();
    expect(screen.getByText('1542')).toBeDefined();
  });

  it('renders positive trend badge when trend isPositive is true', () => {
    render(
      <MetricCard
        title="Latency"
        value="35.2 ms"
        icon={Search}
        trend={{ value: 12.5, isPositive: true }}
      />
    );
    expect(screen.getByText('+12.5%')).toBeDefined();
  });

  it('renders negative trend badge when trend isPositive is false', () => {
    render(
      <MetricCard
        title="Error Rate"
        value="0.1%"
        icon={Search}
        trend={{ value: 5.0, isPositive: false }}
      />
    );
    expect(screen.getByText('-5%')).toBeDefined();
  });
});

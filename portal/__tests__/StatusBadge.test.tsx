import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { StatusBadge } from '../components/StatusBadge';

describe('StatusBadge', () => {
  it('renders healthy status with proper label', () => {
    render(<StatusBadge status="healthy" />);
    expect(screen.getByText(/healthy/i)).toBeDefined();
  });

  it('renders degraded status with proper label', () => {
    render(<StatusBadge status="degraded" />);
    expect(screen.getByText(/degraded/i)).toBeDefined();
  });

  it('renders unhealthy status with proper label', () => {
    render(<StatusBadge status="unhealthy" />);
    expect(screen.getByText(/unhealthy/i)).toBeDefined();
  });

  it('renders unknown status fallback', () => {
    render(<StatusBadge status="custom_state" />);
    expect(screen.getByText(/custom_state/i)).toBeDefined();
  });
});

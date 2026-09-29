import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { ToastProvider, useToast } from '../components/Toast';

const TestComponent = () => {
  const { toast } = useToast();
  return (
    <div>
      <button onClick={() => toast('Success message', 'success')}>Show Success</button>
      <button onClick={() => toast('Error message', 'error')}>Show Error</button>
    </div>
  );
};

describe('ToastProvider', () => {
  it('shows success toast', () => {
    render(
      <ToastProvider>
        <TestComponent />
      </ToastProvider>
    );

    act(() => {
      screen.getByText('Show Success').click();
    });

    expect(screen.getByText('Success message')).toBeDefined();
  });

  it('shows error toast', () => {
    render(
      <ToastProvider>
        <TestComponent />
      </ToastProvider>
    );

    act(() => {
      screen.getByText('Show Error').click();
    });

    expect(screen.getByText('Error message')).toBeDefined();
  });
});

import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { ToastProvider } from '@/components/ui/Toast';
import { CalendarProvider } from '@/features/calendar/CalendarContext';
import { Feed } from '@/features/calendar/components/Feed';

function wrap(ui: ReactElement) {
  return render(
    <ToastProvider>
      <CalendarProvider>{ui}</CalendarProvider>
    </ToastProvider>,
  );
}

describe('Feed', () => {
  it('renders eight day rows from mock today', () => {
    wrap(<Feed />);
    const rows = screen.getAllByRole('button');
    expect(rows.length).toBe(8);
  });
});

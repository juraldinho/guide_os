import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { ToastProvider } from '@/components/ui/Toast';
import { CalendarProvider } from '@/features/calendar/CalendarContext';
import { ReportsPage } from '@/features/reports/ReportsPage';

function wrap(ui: ReactElement) {
  return render(
    <ToastProvider>
      <CalendarProvider>{ui}</CalendarProvider>
    </ToastProvider>,
  );
}

describe('ReportsPage', () => {
  it('renders five summary metric labels', () => {
    wrap(<ReportsPage />);
    expect(screen.getByText('Туров')).toBeInTheDocument();
    expect(screen.getByText('Рабочих дней')).toBeInTheDocument();
    expect(screen.getByText('Доход ($)')).toBeInTheDocument();
    expect(screen.getByText('Оплаченных туров')).toBeInTheDocument();
    expect(screen.getByText('Неоплаченных туров')).toBeInTheDocument();
  });
});

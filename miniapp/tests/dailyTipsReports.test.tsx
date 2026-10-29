import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { ToastProvider } from '@/components/ui/Toast';
import { CalendarProvider } from '@/features/calendar/CalendarContext';
import { ReportsPage } from '@/features/reports/ReportsPage';
import { getIncomeReportRange } from '@/features/reports/lib/periods';
import { guideOsClient } from '@/api/createClient';
import { __resetMockStore } from '@/api/mock/store';

afterEach(() => { cleanup(); vi.restoreAllMocks(); __resetMockStore(); });

it('includes tips-only dates for all-time and retains tips with tour filters', async () => {
  await guideOsClient.setDailyTip('1999-01-01', 37);
  const get = vi.spyOn(guideOsClient, 'getReportsSummary');
  render(<ToastProvider><CalendarProvider><ReportsPage /></CalendarProvider></ToastProvider>);
  fireEvent.click(screen.getByText('За весь период'));
  const summary = await screen.findByTestId('tour-reports-summary');
  await waitFor(() => expect(within(summary).getByText('$37')).toBeInTheDocument());
  expect(get).toHaveBeenCalledWith(expect.objectContaining({ from: '0001-01-01', to: '9999-12-31' }));
  expect(within(summary).getByText('Доход от туров')).toBeInTheDocument();
  expect(within(summary).getByText('Общий доход')).toBeInTheDocument();
  expect(screen.getByText(/Фильтры применяются к турам/)).toBeInTheDocument();
  expect(getIncomeReportRange('month', 1, 2024, [])).toEqual({ from: '2024-02-01', to: '2024-02-29' });
  expect(getIncomeReportRange('year', 1, 2024, [])).toEqual({ from: '2024-01-01', to: '2024-12-31' });
});

it('shows report failure and allows retry without presenting false zero income', async () => {
  const request = vi.spyOn(guideOsClient, 'getReportsSummary').mockRejectedValue(new Error('offline'));
  render(<ToastProvider><CalendarProvider><ReportsPage /></CalendarProvider></ToastProvider>);
  await screen.findByText(/Не удалось загрузить итоги/);
  expect(screen.queryByTestId('tour-reports-summary')).not.toBeInTheDocument();
  request.mockRestore();
  fireEvent.click(screen.getByText('Повторить'));
  await screen.findByTestId('tour-reports-summary');
});

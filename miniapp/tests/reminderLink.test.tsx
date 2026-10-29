import { StrictMode } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CalendarProvider, useCalendar } from '@/features/calendar/CalendarContext';
import { CalendarOverlays } from '@/features/calendar/components/CalendarOverlays';
import { ToastProvider } from '@/components/ui/Toast';
import { guideOsClient } from '@/api/createClient';
import type { CalendarEntry } from '@/api/types';

const entry: CalendarEntry = {
  id: '11', type: 'tour', title: 'Тур из напоминания',
  startDate: '2026-10-29', endDate: '2026-10-31',
  startTime: null, endTime: null, income: 100, status: 'confirmed', payment: 'paid',
};
function Probe() {
  const c = useCalendar();
  return <><div data-testid="context">{JSON.stringify({ tab: c.activeTab, date: c.selectedDate,
    screen: c.calendarScreen, focus: c.guideOperatorFocus, overlay: c.overlay })}</div>
    <button onClick={c.closeOverlay}>Close</button><CalendarOverlays /></>;
}
function setup(query = '?reminder_entry=19&reminder_date=2026-10-30', value: CalendarEntry | null = entry) {
  window.history.replaceState(null, '', '/' + query);
  vi.spyOn(guideOsClient, 'listEntries').mockResolvedValue([]);
  const get = vi.spyOn(guideOsClient, 'getEntry').mockResolvedValue(value);
  render(<StrictMode><ToastProvider><CalendarProvider><Probe /></CalendarProvider></ToastProvider></StrictMode>);
  return get;
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); window.history.replaceState(null, '', '/'); });

it('opens canonical multi-day detail even outside the loaded calendar range; consumes once', async () => {
  const get = setup('?reminder_entry=19&reminder_date=2026-10-30&keep=1#tgWebAppData=preserved');
  expect(await screen.findByText('Тур из напоминания')).toBeInTheDocument();
  expect(get).toHaveBeenCalledTimes(1);
  expect(get).toHaveBeenCalledWith('19');
  expect(screen.getByTestId('context')).toHaveTextContent('2026-10-30');
  expect(window.location.search).toBe('?keep=1');
  expect(window.location.hash).toBe('#tgWebAppData=preserved');
  fireEvent.click(screen.getByText('Close'));
  await waitFor(() => expect(screen.queryByText('Карточка тура')).not.toBeInTheDocument());
  expect(get).toHaveBeenCalledTimes(1);
});

it('uses current tour date if the tour was moved after sending the reminder', async () => {
  setup('?reminder_entry=19&reminder_date=2026-09-01');
  await screen.findByText('Тур из напоминания');
  expect(screen.getByTestId('context')).toHaveTextContent('2026-10-29');
});

it.each([null])('handles missing/deleted/foreign entry without opening a card', async (value) => {
  setup(undefined, value);
  expect(await screen.findByRole('status')).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Тур не найден'));
  expect(screen.queryByText('Карточка тура')).not.toBeInTheDocument();
});

it.each([
  '?reminder_entry=0&reminder_date=2026-10-30',
  '?reminder_entry=9223372036854775808&reminder_date=2026-10-30',
  '?reminder_entry=19&reminder_date=2026-02-30',
  '?reminder_entry=19&reminder_entry=20&reminder_date=2026-10-30',
  '?reminder_entry=19', '',
])('ignores invalid or absent navigation parameters: %s', async (query) => {
  const get = setup(query);
  await waitFor(() => expect(guideOsClient.listEntries).toHaveBeenCalled());
  expect(get).not.toHaveBeenCalled();
  expect(screen.queryByText('Карточка тура')).not.toBeInTheDocument();
});

it('preserves operator assignment navigation and the focused-day return context', async () => {
  setup(undefined, { ...entry, guideOperatorAssignmentId: 'assignment-test', income: null, payment: null });
  await waitFor(() => expect(screen.getByTestId('context')).toHaveTextContent('guide_operator'));
  const context = JSON.parse(screen.getByTestId('context').textContent!);
  expect(context.focus.assignmentId).toBe('assignment-test');
  expect(context.focus.focusDate).toBe('2026-10-30');
  expect(context.focus.returnTo).toMatchObject({ calendarScreen: 'day', selectedDate: '2026-10-30', viewMonth: 9, viewYear: 2026 });
});

it('handles API errors without opening a card and keeps the link for reload retry', async () => {
  window.history.replaceState(null, '', '/?reminder_entry=19&reminder_date=2026-10-30');
  vi.spyOn(guideOsClient, 'listEntries').mockResolvedValue([]);
  vi.spyOn(guideOsClient, 'getEntry').mockRejectedValue(new Error('offline'));
  render(<ToastProvider><CalendarProvider><Probe /></CalendarProvider></ToastProvider>);
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Не удалось открыть тур'));
  expect(screen.queryByText('Карточка тура')).not.toBeInTheDocument();
  expect(window.location.search).toContain('reminder_entry=19');
});

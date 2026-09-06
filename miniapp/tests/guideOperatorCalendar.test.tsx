// @ts-nocheck — Node built-ins / test harness not in app tsconfig.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { guideOsClient } from '@/api/createClient';
import { __resetMockStore } from '@/api/mock/store';
import { ToastProvider } from '@/components/ui/Toast';
import { CalendarProvider, useCalendar } from '@/features/calendar/CalendarContext';
import { AppShell } from '@/app/AppShell';
import { DayDetail } from '@/features/calendar/components/DayDetail';
import { CalendarOverlays } from '@/features/calendar/components/CalendarOverlays';
import { t } from '@/i18n/strings';

vi.mock('react-virtuoso', async () => {
  const React = await import('react');
  const Virtuoso = React.forwardRef((props: Record<string, unknown>, ref: React.Ref<unknown>) => {
    React.useImperativeHandle(ref, () => ({
      scrollToIndex: vi.fn(),
    }));
    const data = (props.data as string[]) ?? [];
    const itemContent = props.itemContent as
      | ((index: number, iso: string) => React.ReactNode)
      | undefined;
    const computeItemKey = props.computeItemKey as
      | ((index: number, iso: string) => string)
      | undefined;
    const needed = new Set(['2026-09-15', '2026-09-16', '2026-09-17']);
    return (
      <div data-testid="virtuoso-mock">
        {data.map((iso, index) => {
          if (!needed.has(iso)) return null;
          return (
            <div key={computeItemKey?.(index, iso) ?? iso}>
              {itemContent?.(index, iso)}
            </div>
          );
        })}
      </div>
    );
  });
  return { Virtuoso };
});

function wrap(ui: React.ReactElement) {
  return render(
    <ToastProvider>
      <CalendarProvider>{ui}</CalendarProvider>
    </ToastProvider>,
  );
}

function DayProbe({ date }: { date: string }) {
  const { openDayDetail, openDetail, entries, calendarScreen } = useCalendar();
  return (
    <div>
      <button type="button" onClick={() => openDayDetail(date)}>
        open-day
      </button>
      <ul>
        {entries
          .filter((e) => e.startDate <= date && date <= e.endDate)
          .map((e) => (
            <li key={e.id}>
              <button type="button" onClick={() => openDetail(e.id)}>
                open-{e.id}
              </button>
            </li>
          ))}
      </ul>
      {calendarScreen === 'day' ? <DayDetail /> : null}
      <CalendarOverlays />
    </div>
  );
}

describe('Guide Operator calendar UX (GO6B3)', () => {
  beforeEach(() => {
    __resetMockStore();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('labels accepted Guide Operator rows with company and daily city', async () => {
    wrap(<DayProbe date="2026-09-16" />);
    await waitFor(() => screen.getByRole('button', { name: 'open-go_t_accepted_01' }));
    fireEvent.click(screen.getByRole('button', { name: 'open-day' }));
    await waitFor(() => {
      expect(screen.getByText(t.assignedViaGuideOperator)).toBeTruthy();
    });
    expect(screen.getByText(/Khiva Operator Co/)).toBeTruthy();
    expect(screen.getByText(/Хива — Ичан-Кала/)).toBeTruthy();
  });

  it('opens Guide Operator detail from calendar and focuses selected date', async () => {
    wrap(<AppShell />);
    await waitFor(() => screen.getByTestId('virtuoso-mock'));

    fireEvent.click(
      screen.getByRole('button', {
        name: (_label, element) =>
          element.getAttribute('data-feed-date') === '2026-09-16',
      }),
    );

    await waitFor(() => screen.getByTestId('go-calendar-entry-go_t_accepted_01'));
    fireEvent.click(screen.getByTestId('go-calendar-entry-go_t_accepted_01'));

    await waitFor(() => {
      expect(screen.getByText(t.guideOperatorDetailTitle)).toBeTruthy();
    });
    expect(screen.queryByRole('button', { name: t.guideOperatorAccept })).toBeNull();
    expect(screen.queryByRole('button', { name: t.edit })).toBeNull();
    expect(screen.queryByRole('button', { name: t.delete })).toBeNull();
    expect(screen.getByTestId('go-focused-day')).toHaveTextContent('2026-09-16');
    expect(screen.getByText('Хива — Ичан-Кала')).toBeTruthy();
  });

  it('Back restores calendar day context after Guide Operator deep link', async () => {
    wrap(<AppShell />);
    await waitFor(() => screen.getByTestId('virtuoso-mock'));

    fireEvent.click(
      screen.getByRole('button', {
        name: (_label, element) =>
          element.getAttribute('data-feed-date') === '2026-09-16',
      }),
    );
    await waitFor(() => screen.getByTestId('go-calendar-entry-go_t_accepted_01'));
    fireEvent.click(screen.getByTestId('go-calendar-entry-go_t_accepted_01'));
    await waitFor(() => screen.getByText(t.guideOperatorDetailTitle));

    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));

    await waitFor(() => {
      expect(screen.getByTestId('go-calendar-entry-go_t_accepted_01')).toBeTruthy();
    });
  });

  it('loads accepted assignment detail directly even when absent from pending list', async () => {
    const pending = await guideOsClient.listPendingGuideOperatorAssignments();
    expect(pending.find((row) => row.id === 'goasg_accepted_01')).toBeUndefined();

    const detail = await guideOsClient.getGuideOperatorAssignment('goasg_accepted_01');
    expect(detail?.assignment.status).toBe('accepted');
    expect(detail?.assignment.companyName).toBe('Khiva Operator Co');
    expect(detail?.workingPackage).toBeTruthy();
  });

  it('shows not-found UI when assignment detail is missing', async () => {
    vi.spyOn(guideOsClient, 'getGuideOperatorAssignment').mockResolvedValue(null);
    wrap(<AppShell />);
    await waitFor(() => screen.getByTestId('virtuoso-mock'));
    fireEvent.click(
      screen.getByRole('button', {
        name: (_label, element) =>
          element.getAttribute('data-feed-date') === '2026-09-16',
      }),
    );
    await waitFor(() => screen.getByTestId('go-calendar-entry-go_t_accepted_01'));
    fireEvent.click(screen.getByTestId('go-calendar-entry-go_t_accepted_01'));
    await waitFor(() => {
      expect(screen.getByText(t.guideOperatorDetailNotFound)).toBeTruthy();
    });
  });

  it('keeps edit/copy/delete for personal tours', async () => {
    wrap(<DayProbe date="2026-08-28" />);
    await waitFor(() => screen.getByRole('button', { name: 'open-t1' }));
    fireEvent.click(screen.getByRole('button', { name: 'open-day' }));
    await waitFor(() => screen.getByText('Обзорный Самарканд'));
    fireEvent.click(screen.getByRole('button', { name: 'open-t1' }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: t.edit })).toBeTruthy();
      expect(screen.getByRole('button', { name: t.copyAction })).toBeTruthy();
      expect(screen.getByRole('button', { name: t.delete })).toBeTruthy();
    });
    expect(screen.queryByText(t.assignedViaGuideOperator)).toBeNull();
  });

  it('shows critical pending badge on operator calendar rows', async () => {
    const { __testEntries } = await import('@/api/mock/store');
    const entry = __testEntries().find((row) => row.id === 'go_t_accepted_01');
    expect(entry).toBeTruthy();
    entry!.guideOperatorPendingCritical = true;
    wrap(<DayProbe date="2026-09-15" />);
    await waitFor(() => screen.getByRole('button', { name: 'open-go_t_accepted_01' }));
    fireEvent.click(screen.getByRole('button', { name: 'open-day' }));
    await waitFor(() => screen.getByTestId('go-calendar-critical-go_t_accepted_01'));
    expect(screen.getByLabelText(t.guideOperatorCriticalPendingAria)).toBeTruthy();
  });

  it('hides mutation actions when opening operator-managed entry from calendar', async () => {
    wrap(<AppShell />);
    await waitFor(() => screen.getByTestId('virtuoso-mock'));
    fireEvent.click(
      screen.getByRole('button', {
        name: (_label, element) =>
          element.getAttribute('data-feed-date') === '2026-09-15',
      }),
    );
    await waitFor(() => screen.getByTestId('go-calendar-entry-go_t_accepted_01'));
    fireEvent.click(screen.getByTestId('go-calendar-entry-go_t_accepted_01'));
    await waitFor(() => screen.getByText(t.guideOperatorDetailTitle));
    expect(screen.queryByRole('button', { name: t.edit })).toBeNull();
    expect(screen.queryByRole('button', { name: t.copyAction })).toBeNull();
    expect(screen.queryByRole('button', { name: t.delete })).toBeNull();
    expect(screen.queryByRole('button', { name: t.guideOperatorAccept })).toBeNull();
  });

  it('hides income and payment for Guide Operator calendar rows', async () => {
    wrap(<DayProbe date="2026-09-16" />);
    await waitFor(() => screen.getByRole('button', { name: 'open-go_t_accepted_01' }));
    fireEvent.click(screen.getByRole('button', { name: 'open-day' }));
    await waitFor(() => screen.getByText(t.assignedViaGuideOperator));
    expect(screen.queryByText('$0')).toBeNull();
    expect(screen.queryByText(t.paymentUnpaid)).toBeNull();
    expect(screen.queryByText(t.paymentPaid)).toBeNull();
    expect(screen.getByText(/Khiva Operator Co/)).toBeTruthy();
  });

  it('does not place cancelled assignments on the calendar', async () => {
    const lists = await guideOsClient.listGuideOperatorAssignmentLists();
    expect(lists.cancelled.map((row) => row.id)).toEqual([
      'goasg_cancelled_newer_01',
      'goasg_cancelled_older_02',
    ]);
    expect(lists.upcoming.every((row) => row.status !== 'cancelled')).toBe(true);
    expect(lists.completed.every((row) => row.status !== 'cancelled')).toBe(true);

    const entries = await guideOsClient.listEntries();
    expect(
      entries.some(
        (entry) =>
          entry.guideOperatorAssignmentId === 'goasg_cancelled_newer_01' ||
          entry.guideOperatorAssignmentId === 'goasg_cancelled_older_02' ||
          entry.company === 'Fergana Operator' ||
          entry.company === 'Nukus Expeditions',
      ),
    ).toBe(false);

    wrap(<DayProbe date="2026-09-22" />);
    await waitFor(() => screen.getByRole('button', { name: 'open-day' }));
    fireEvent.click(screen.getByRole('button', { name: 'open-day' }));
    await waitFor(() => {
      expect(screen.queryByText('Fergana Operator')).toBeNull();
      expect(screen.queryByText(t.assignedViaGuideOperator)).toBeNull();
    });
  });

  it('shows calendar unread marker and clears it after acknowledge', async () => {
    wrap(<AppShell />);
    await waitFor(() => screen.getByTestId('virtuoso-mock'));
    await waitFor(() => {
      expect(screen.getAllByTestId('go-feed-unread-go_t_accepted_01').length).toBeGreaterThan(0);
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: (_label, element) =>
          element.getAttribute('data-feed-date') === '2026-09-16',
      }),
    );
    await waitFor(() => screen.getByTestId('go-calendar-entry-go_t_accepted_01'));
    await waitFor(() => screen.getByTestId('go-calendar-unread-go_t_accepted_01'));

    fireEvent.click(screen.getByTestId('go-calendar-entry-go_t_accepted_01'));
    await waitFor(() => screen.getByTestId('go-acknowledge'));
    fireEvent.click(screen.getByTestId('go-acknowledge'));
    await waitFor(() => {
      expect(screen.getByText(t.guideOperatorAcknowledgedToast)).toBeTruthy();
    });
    await waitFor(() => {
      expect(screen.queryByTestId('go-acknowledge')).toBeNull();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    await waitFor(() => screen.getByTestId('go-calendar-entry-go_t_accepted_01'));
    expect(screen.queryByTestId('go-calendar-unread-go_t_accepted_01')).toBeNull();
    expect(screen.queryAllByTestId('go-feed-unread-go_t_accepted_01')).toHaveLength(0);
  });
});

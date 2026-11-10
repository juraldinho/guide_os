// @ts-nocheck — Node built-ins / test harness not in app tsconfig.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { guideOsClient } from '@/api/createClient';
import { __resetMockStore } from '@/api/mock/store';
import { ToastProvider } from '@/components/ui/Toast';
import { CalendarProvider, useCalendar } from '@/features/calendar/CalendarContext';
import { AppShell } from '@/app/AppShell';
import { DayDetail } from '@/features/calendar/components/DayDetail';
import { CalendarOverlays } from '@/features/calendar/components/CalendarOverlays';
import { t } from '@/i18n/strings';

const { scrollToIndex } = vi.hoisted(() => ({ scrollToIndex: vi.fn() }));

vi.mock('react-virtuoso', async () => {
  const React = await import('react');
  const Virtuoso = React.forwardRef((props: Record<string, unknown>, ref: React.Ref<unknown>) => {
    React.useImperativeHandle(ref, () => ({
      scrollToIndex,
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
    scrollToIndex.mockClear();
    window.history.replaceState(null, '', '/');
  });

  afterEach(() => {
    cleanup();
    window.history.replaceState(null, '', '/');
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


// Read-only fixtures follow the backend reader DTO: one calendar row per date,
// nullable assignment projection ID, active package distinct from pending/history.
async function explicitFixtures() {
  const base = await guideOsClient.getGuideOperatorAssignment('goasg_accepted_01');
  const dayIds = ['10000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000003'];
  const make = (id, role, dates) => {
    const pkg = {
      schema_version: 'assignment.working_package.v2', company_id: base.assignment.companyId,
      source_tour_revision: 1,
      tour: { id: '20000000-0000-4000-8000-000000000001', reference: 'SAME', title: 'Общий тур',
        start_date: '2026-09-15', end_date: '2026-09-17', timezone: 'Asia/Tashkent',
        city_or_route: 'Хива', language: 'ru', tourist_count: 10, customer_or_agency: null },
      assignment: { id, guide_os_id: '30000000-0000-4000-8000-000000000001', role,
        start_date: dates[0], end_date: dates.at(-1), recipient_instructions: `Инструкции ${role}` },
      days: dates.map((date, i) => ({ tour_day_id: dayIds[i], date, title: 'Рабочий день',
        city_or_route: 'Хива', instructions: `Активный день ${date}`,
        events: [{ start_time: '10:00', end_time: '11:00', event_type: 'visit', title: 'Экскурсия',
          place: 'Музей', description: 'Описание события', important_instruction: 'Важное указание' }] })),
      drivers: [{ day_ids: [dayIds[0]], name: 'Водитель', phone: null, city_or_route: 'Хива',
        instructions: 'Встреча водителя', information_status: 'confirmed' }],
      contacts: [{ day_ids: [dayIds[0]], name: 'Контакт', role: 'Организатор', phone: null,
        instructions: 'Инструкции контакта' }],
      group_summary: { name_or_code: 'Группа', tourist_count: 10, recipient_information: 'Информация группы' },
      working_conditions: null, remuneration: null,
    };
    return { ...structuredClone(base), assignment: { ...base.assignment, id, role,
      status: 'accepted', projectionTourId: null, startDate: dates[0], endDate: dates.at(-1),
      activeVersionNumber: 1, activeVersionUnread: false, pendingCriticalVersionNumber: null },
      workingPackage: pkg, conflictDates: [], pendingCriticalVersion: null,
      activeVersion: { versionNumber: 1, severity: 'initial', publishedAt: base.activeVersion.publishedAt,
        changeSummary: [], unread: false, sourceEventId: null },
      versions: [{ versionNumber: 1, severity: 'initial', publishedAt: base.activeVersion.publishedAt,
        changeSummary: [], workingPackage: pkg, sourceEventId: null }] };
  };
  const a = make('40000000-0000-4000-8000-000000000001', 'main_guide', ['2026-09-15', '2026-09-17']);
  const b = make('40000000-0000-4000-8000-000000000002', 'local_guide', ['2026-09-15']);
  const details = { [a.assignment.id]: a, [b.assignment.id]: b };
  let entries = [a, b].flatMap((detail, index) => detail.workingPackage.days.map((day, i) => ({
    id: `daily-${index}-${i}`, type: 'tour', title: 'Общий тур', startDate: day.date, endDate: day.date,
    startTime: null, endTime: null, income: null, payment: null, status: 'confirmed',
    company: detail.assignment.companyName, location: 'Хива', note: `go_assignment:${detail.assignment.id}`,
    source: 'Guide Operator', groupId: `${detail.assignment.id}:${day.tour_day_id}`,
    guideOperatorAssignmentId: detail.assignment.id, guideOperatorVersion: 1,
    guideOperatorVersionUnread: false, guideOperatorPendingCritical: false,
  })));
  vi.spyOn(guideOsClient, 'listEntries').mockImplementation(async () => structuredClone(entries));
  vi.spyOn(guideOsClient, 'listGuideOperatorAssignmentLists').mockResolvedValue({ asOfDate: '2026-09-15',
    awaiting: [], upcoming: [], inProgress: [], completed: [], cancelled: [] });
  vi.spyOn(guideOsClient, 'listGuideOperatorConnections').mockResolvedValue([]);
  vi.spyOn(guideOsClient, 'getGuideOperatorAssignment').mockImplementation(async (id) => structuredClone(details[id] ?? null));
  return { a, b, details, cancelA: () => {
    a.assignment.status = 'cancelled'; a.assignment.cancelledAt = '2026-09-15T10:00:00+00:00';
    entries = entries.filter((e) => e.guideOperatorAssignmentId !== a.assignment.id);
  }, setPending: () => {
    const pkg = structuredClone(a.workingPackage);
    pkg.days[1].date = '2026-09-18'; pkg.days[1].instructions = 'Предложенный день';
    pkg.assignment.end_date = '2026-09-18';
    const version = { ...a.versions[0], versionNumber: 2, severity: 'critical', workingPackage: pkg };
    a.versions.push(version);
    a.assignment.pendingCriticalVersionNumber = 2;
    a.pendingCriticalVersion = { ...version, conflictDates: [] };
    entries.forEach((e) => { if (e.guideOperatorAssignmentId === a.assignment.id) e.guideOperatorPendingCritical = true; });
  } };
}

function NavigationProbe() {
  const c = useCalendar();
  return <>
    <output data-testid="navigation-state">{JSON.stringify({ date: c.selectedDate, screen: c.calendarScreen,
      month: c.viewMonth, year: c.viewYear, expanded: c.monthExpanded, focus: c.guideOperatorFocus })}</output>
    <button onClick={() => c.openDayDetail('2026-09-17')}>set-origin</button>
    <button onClick={c.openFeed}>origin-feed</button>
    <button onClick={() => c.openDetail('daily-0-1')}>origin-assignment</button>
    <button onClick={() => void c.refreshEntries()}>refresh-fixture</button>
  </>;
}

const openFixtureDay = (date) => fireEvent.click(screen.getByRole('button', {
  name: (_label, element) => element.getAttribute('data-feed-date') === date,
}));

const nav = () => JSON.parse(screen.getByTestId('navigation-state').textContent);

describe('Explicit-day read-only calendar and package', () => {
  beforeEach(() => { __resetMockStore(); vi.restoreAllMocks(); scrollToIndex.mockClear(); window.history.replaceState(null, '', '/'); });
  afterEach(() => { cleanup(); window.history.replaceState(null, '', '/'); });

  it('keeps sparse gaps free and opens independent roles with the exact selected day', async () => {
    const { a, b } = await explicitFixtures();
    wrap(<><AppShell /><NavigationProbe /></>);
    await screen.findByTestId('virtuoso-mock');
    openFixtureDay('2026-09-16');
    expect((await screen.findAllByText(t.dayFullyFree)).length).toBeGreaterThan(0);
    expect(screen.queryByTestId(/go-calendar-entry/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: t.backToFeed }));
    openFixtureDay('2026-09-15');
    const main = await screen.findByTestId('go-calendar-entry-daily-0-0');
    const local = screen.getByTestId('go-calendar-entry-daily-1-0');
    await within(main).findByText('Основной гид');
    await within(local).findByText('Местный гид');
    fireEvent.keyDown(local, { key: 'Enter' });
    await screen.findByTestId('go-focused-day');
    expect(nav().focus.assignmentId).toBe(b.assignment.id);
    expect(screen.getByTestId('go-focused-day')).toHaveTextContent('2026-09-15');
    expect(screen.getByText('Инструкции local_guide')).toBeTruthy();
    expect(screen.getByText('Встреча водителя')).toBeTruthy();
    expect(screen.getByText('Инструкции контакта')).toBeTruthy();
    expect(screen.getByText('Информация группы')).toBeTruthy();
    expect(screen.getByText('Важное указание')).toBeTruthy();
    expect(screen.queryByRole('button', { name: t.edit })).toBeNull();
    expect(screen.queryByText(/\$0|Не оплачено/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    expect(nav()).toMatchObject({ date: '2026-09-15', screen: 'day' });
    fireEvent.click(await screen.findByTestId('go-calendar-entry-daily-0-0'));
    await screen.findByTestId('go-focused-day');
    expect(nav().focus.assignmentId).toBe(a.assignment.id);
    expect(screen.getByText('Инструкции main_guide')).toBeTruthy();
  });

  it('restores feed date/view and invokes the existing scroll anchor after Back', async () => {
    await explicitFixtures();
    wrap(<><AppShell /><NavigationProbe /></>);
    await screen.findByTestId('virtuoso-mock');
    fireEvent.click(screen.getByText('set-origin'));
    fireEvent.click(screen.getByText('origin-feed'));
    const origin = nav();
    scrollToIndex.mockClear();
    fireEvent.click(screen.getByText('origin-assignment'));
    await screen.findByTestId('go-focused-day');
    expect(screen.getByTestId('go-focused-day')).toHaveTextContent('2026-09-17');
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    await screen.findByTestId('virtuoso-mock');
    expect(nav()).toMatchObject({ date: origin.date, screen: 'feed', month: origin.month, year: origin.year, expanded: origin.expanded });
    const { ALL_FEED_DATES } = await import('@/features/calendar/components/Feed');
    await waitFor(() => expect(scrollToIndex).toHaveBeenCalledWith({ index: ALL_FEED_DATES.indexOf('2026-09-17'), align: 'start', behavior: 'auto' }));
    // The normal day → assignment → day → feed path must restore the same date too.
    openFixtureDay('2026-09-17');
    fireEvent.click(await screen.findByTestId('go-calendar-entry-daily-0-1'));
    await screen.findByTestId('go-focused-day');
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    scrollToIndex.mockClear();
    fireEvent.click(await screen.findByRole('button', { name: t.backToFeed }));
    await waitFor(() => expect(scrollToIndex).toHaveBeenCalledWith(expect.objectContaining({ index: ALL_FEED_DATES.indexOf('2026-09-17') })));
  });

  it('loads a direct accepted assignment absent from every list and keeps pending content separate', async () => {
    const f = await explicitFixtures(); f.setPending();
    window.history.replaceState(null, '', `/?go_assignment=${f.a.assignment.id}`);
    wrap(<><AppShell /><NavigationProbe /></>);
    await screen.findByText('Инструкции main_guide');
    expect(screen.getByText('Активный день 2026-09-17')).toBeTruthy();
    expect(screen.queryByText('Предложенный день')).toBeNull();
    expect(screen.getByTestId('go-critical-pending')).toBeTruthy();
    expect(screen.queryByTestId('go-confirm-critical')).toBeNull();
    expect(screen.queryByTestId('go-reject-critical')).toBeNull();
    expect(screen.queryByTestId('go-acknowledge')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    await screen.findByTestId('virtuoso-mock');
    openFixtureDay('2026-09-17');
    expect(await screen.findByTestId('go-calendar-critical-daily-0-1')).toBeTruthy();
    expect(screen.getByTestId('go-calendar-entry-daily-0-1')).toHaveTextContent('Общий тур');
  });

  it('a cancelled role keeps its history but does not remove the other role', async () => {
    const f = await explicitFixtures(); f.cancelA();
    window.history.replaceState(null, '', `/?go_assignment=${f.a.assignment.id}`);
    wrap(<><AppShell /><NavigationProbe /></>);
    await screen.findByTestId('go-cancelled-banner');
    expect(screen.getByText('Активный день 2026-09-17')).toBeTruthy();
    expect(screen.queryByTestId('go-confirm-critical')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    await screen.findByTestId('virtuoso-mock');
    openFixtureDay('2026-09-15');
    await screen.findByTestId('go-calendar-entry-daily-1-0');
    expect(screen.queryByTestId('go-calendar-entry-daily-0-0')).toBeNull();
    await screen.findByText('Местный гид');
  });
});


describe('Explicit read-only reader edge states', () => {
  beforeEach(() => { __resetMockStore(); vi.restoreAllMocks(); window.history.replaceState(null, '', '/'); });
  afterEach(() => { cleanup(); window.history.replaceState(null, '', '/'); });

  it('retains independent entry links if role metadata is unavailable', async () => {
    await explicitFixtures();
    vi.spyOn(guideOsClient, 'getGuideOperatorAssignment').mockRejectedValue(new TypeError('offline'));
    wrap(<><AppShell /><NavigationProbe /></>);
    await screen.findByTestId('virtuoso-mock');
    openFixtureDay('2026-09-15');
    const a = await screen.findByTestId('go-calendar-entry-daily-0-0');
    const b = screen.getByTestId('go-calendar-entry-daily-1-0');
    expect(a.textContent).not.toBe(b.textContent);
    fireEvent.click(a);
    await screen.findByText(t.guideOperatorDetailError);
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    await screen.findByTestId('go-calendar-entry-daily-1-0');
  });

  it('keeps active content after pending is rejected while retaining version history', async () => {
    const f = await explicitFixtures(); f.setPending();
    f.a.pendingCriticalVersion = null;
    f.a.assignment.pendingCriticalVersionNumber = null;
    window.history.replaceState(null, '', `/?go_assignment=${f.a.assignment.id}`);
    wrap(<AppShell />);
    await screen.findByText('Активный день 2026-09-17');
    expect(screen.queryByText('Предложенный день')).toBeNull();
    expect(screen.queryByTestId('go-critical-pending')).toBeNull();
    expect(screen.getByTestId('go-version-history')).toBeTruthy();
  });
});

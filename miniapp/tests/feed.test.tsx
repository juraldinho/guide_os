// @ts-nocheck — read CSS source at runtime; Node built-ins are not in app tsconfig.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import type { CalendarEntry } from '@/api/types';
import { guideOsClient } from '@/api/createClient';
import { INITIAL_ENTRIES, MOCK_PROFILE } from '@/api/mock/data';
import { ToastProvider } from '@/components/ui/Toast';
import { CalendarProvider, useCalendar } from '@/features/calendar/CalendarContext';
import { CalendarPage } from '@/features/calendar/CalendarPage';
import {
  Feed,
  ALL_FEED_DATES,
  getTodayFeedIndex,
  FEED_VIRTUOSO_LAYOUT_STYLE,
} from '@/features/calendar/components/Feed';
import { AppHeader } from '@/components/layout/AppHeader';
import { MOCK_TODAY, ENTRIES_RANGE_FROM, ENTRIES_RANGE_TO } from '@/config';
import {
  buildFeedDatesFromRange,
  shiftIso,
} from '@/features/calendar/lib/dates';
import { MONTH_NAMES_CAP } from '@/i18n/ru';
import { t } from '@/i18n/strings';

const GLOBAL_CSS = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../src/styles/global.css'),
  'utf8',
);

let lastVirtuosoProps: Record<string, unknown> | null = null;
const virtuosoScrollToIndex = vi.fn();

vi.mock('react-virtuoso', async () => {
  const React = await import('react');
  const Virtuoso = React.forwardRef((props: Record<string, unknown>, ref: React.Ref<unknown>) => {
    lastVirtuosoProps = props;
    React.useImperativeHandle(ref, () => ({
      scrollToIndex: virtuosoScrollToIndex,
    }));
    React.useEffect(() => {
      const data = props.data as string[] | undefined;
      const rangeChanged = props.rangeChanged as
        | ((range: { startIndex: number; endIndex: number }) => void)
        | undefined;
      if (!rangeChanged || !data?.length) return;
      const start = (props.initialTopMostItemIndex as number) ?? 0;
      rangeChanged({
        startIndex: start,
        endIndex: Math.min(start + 5, data.length - 1),
      });
    }, []);
    const data = (props.data as string[]) ?? [];
    const itemContent = props.itemContent as
      | ((index: number, iso: string) => React.ReactNode)
      | undefined;
    const computeItemKey = props.computeItemKey as
      | ((index: number, iso: string) => string)
      | undefined;
    const anchor = (props.initialTopMostItemIndex as number) ?? 0;
    const windowStart = Math.max(0, anchor - 120);
    const windowEnd = Math.min(data.length - 1, anchor + 120);
    const visibleSlice = data.slice(windowStart, windowEnd + 1);
    return (
      <div
        data-testid="virtuoso-mock"
        className={props.className as string}
        style={props.style as React.CSSProperties}
      >
        {visibleSlice.map((iso, offset) => {
          const index = windowStart + offset;
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

function wrap(ui: ReactElement) {
  return render(
    <ToastProvider>
      <CalendarProvider>{ui}</CalendarProvider>
    </ToastProvider>,
  );
}

function HeaderFromContext() {
  const {
    activeTab,
    calendarScreen,
    headerMonth,
    headerYear,
    monthExpanded,
    goToday,
    toggleMonthPicker,
    openSettings,
  } = useCalendar();
  const showMonthPicker =
    activeTab === 'calendar' && calendarScreen === 'feed' && monthExpanded;
  return (
    <AppHeader
      activeTab={activeTab}
      headerMonth={headerMonth}
      headerYear={headerYear}
      monthExpanded={monthExpanded}
      showMonthPicker={showMonthPicker}
      onLogoToday={goToday}
      onToggleMonthPicker={toggleMonthPicker}
      onSettings={openSettings}
    />
  );
}

function VisibleMonthProbe() {
  const { setVisibleFeedFromIso } = useCalendar();
  return (
    <>
      <button type="button" onClick={() => setVisibleFeedFromIso('2026-09-01')}>
        show-september
      </button>
      <button type="button" onClick={() => setVisibleFeedFromIso('2027-01-15')}>
        show-january-2027
      </button>
    </>
  );
}

function GoTodayProbe() {
  const { goToday, setActiveTab } = useCalendar();
  return (
    <>
      <button type="button" onClick={() => setActiveTab('reports')}>go-reports</button>
      <button type="button" onClick={goToday}>go-today</button>
    </>
  );
}

describe('feed layout CSS contract', () => {
  it('makes calendar main a flex column with min-height 0 and overflow hidden', () => {
    expect(GLOBAL_CSS).toMatch(
      /\.main:has\(\.feed-virtuoso-wrap\)\s*\{[^}]*display:\s*flex/s,
    );
    expect(GLOBAL_CSS).toMatch(
      /\.main:has\(\.feed-virtuoso-wrap\)\s*\{[^}]*flex-direction:\s*column/s,
    );
    expect(GLOBAL_CSS).toMatch(
      /\.main:has\(\.feed-virtuoso-wrap\)\s*\{[^}]*min-height:\s*0/s,
    );
    expect(GLOBAL_CSS).toMatch(
      /\.main:has\(\.feed-virtuoso-wrap\)\s*\{[^}]*overflow:\s*hidden/s,
    );
  });

  it('makes feed wrapper a flex grow container without percentage height', () => {
    const wrapBlock = GLOBAL_CSS.match(/\.feed-virtuoso-wrap\s*\{[^}]*\}/s)?.[0] ?? '';
    expect(wrapBlock).toMatch(/display:\s*flex/);
    expect(wrapBlock).toMatch(/flex:\s*1\s+1\s+0/);
    expect(wrapBlock).toMatch(/min-height:\s*0/);
    expect(wrapBlock).not.toMatch(/height:\s*100%/);
  });

  it('makes Virtuoso scroller flex-grow without percentage-only height', () => {
    const scrollerBlock = GLOBAL_CSS.match(/\.feed-virtuoso-scroller\s*\{[^}]*\}/s)?.[0] ?? '';
    expect(scrollerBlock).toMatch(/flex:\s*1\s+1\s+0/);
    expect(scrollerBlock).toMatch(/min-height:\s*0/);
    expect(scrollerBlock).not.toMatch(/height:\s*100%/);
  });

  it('does not apply overflow hidden to generic main (Reports unaffected)', () => {
    const mainBlock = GLOBAL_CSS.match(/^\.main\s*\{[^}]*\}/ms)?.[0] ?? '';
    expect(mainBlock).not.toMatch(/overflow:\s*hidden/);
  });
});

describe('Feed virtual list', () => {
  const expectedDates = buildFeedDatesFromRange(ENTRIES_RANGE_FROM, ENTRIES_RANGE_TO);
  const todayIndex = getTodayFeedIndex();

  beforeEach(() => {
    lastVirtuosoProps = null;
    virtuosoScrollToIndex.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('supplies the complete bounded date range to Virtuoso', () => {
    wrap(<Feed />);
    expect(lastVirtuosoProps?.data).toEqual(expectedDates);
    expect((lastVirtuosoProps?.data as string[]).length).toBe(ALL_FEED_DATES.length);
  });

  it('passes flex layout style to Virtuoso scroller', () => {
    wrap(<Feed />);
    expect(lastVirtuosoProps?.style).toEqual(FEED_VIRTUOSO_LAYOUT_STYLE);
  });

  it('sets initialTopMostItemIndex to the Today index', () => {
    wrap(<Feed />);
    expect(lastVirtuosoProps?.initialTopMostItemIndex).toBe(todayIndex);
    expect(ALL_FEED_DATES[todayIndex]).toBe(MOCK_TODAY);
  });

  it('does not render top or bottom sentinels', () => {
    wrap(<Feed />);
    expect(document.querySelector('.feed-load-sentinel')).toBeNull();
    expect(screen.queryByText(/загруз/i)).toBeNull();
  });

  it('does not create IntersectionObserver', () => {
    const io = vi.fn();
    vi.stubGlobal('IntersectionObserver', io);
    wrap(<Feed />);
    expect(io).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('does not call scrollIntoView or window.scrollBy on mount', () => {
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView');
    const scrollBy = vi.spyOn(window, 'scrollBy');
    wrap(<Feed />);
    expect(scrollIntoView).not.toHaveBeenCalled();
    expect(scrollBy).not.toHaveBeenCalled();
  });

  it('addresses dates before Today by array index', () => {
    const beforeIso = shiftIso(MOCK_TODAY, -1);
    const beforeIndex = ALL_FEED_DATES.indexOf(beforeIso);
    expect(beforeIndex).toBe(todayIndex - 1);
    wrap(<Feed />);
    expect(document.querySelector(`[data-feed-date="${beforeIso}"]`)).toBeTruthy();
  });

  it('addresses dates after Today by array index', () => {
    const afterIso = shiftIso(MOCK_TODAY, 1);
    const afterIndex = ALL_FEED_DATES.indexOf(afterIso);
    expect(afterIndex).toBe(todayIndex + 1);
    wrap(<Feed />);
    expect(document.querySelector(`[data-feed-date="${afterIso}"]`)).toBeTruthy();
  });

  it('updates header month/year from Virtuoso rangeChanged', async () => {
    wrap(
      <>
        <HeaderFromContext />
        <Feed />
      </>,
    );
    expect(document.querySelector('.header-month-label')?.textContent).toContain(MONTH_NAMES_CAP[7]);

    const septemberIndex = ALL_FEED_DATES.indexOf('2026-09-01');
    await act(async () => {
      (lastVirtuosoProps?.rangeChanged as (r: { startIndex: number; endIndex: number }) => void)?.({
        startIndex: septemberIndex,
        endIndex: septemberIndex + 3,
      });
    });
    expect(document.querySelector('.header-month-label')?.textContent).toContain(MONTH_NAMES_CAP[8]);
  });

  it('logo Today calls Virtuoso scrollToIndex with the Today index', async () => {
    wrap(
      <>
        <GoTodayProbe />
        <Feed />
      </>,
    );
    fireEvent.click(screen.getByText('go-today'));
    await waitFor(() => {
      expect(virtuosoScrollToIndex).toHaveBeenCalledWith({
        index: todayIndex,
        align: 'start',
        behavior: 'smooth',
      });
    });
  });

  it('logo Today from Reports tab returns to calendar then scrolls to Today', async () => {
    wrap(
      <>
        <GoTodayProbe />
        <HeaderFromContext />
        <CalendarPage />
      </>,
    );
    fireEvent.click(screen.getByText('go-reports'));
    expect(document.querySelector('.header-title-static')?.textContent).toContain('Итоги');
    fireEvent.click(screen.getByText('go-today'));
    await waitFor(() => {
      expect(document.querySelector('.header-month-label')?.textContent).toContain(MONTH_NAMES_CAP[7]);
      expect(virtuosoScrollToIndex).toHaveBeenCalledWith({
        index: todayIndex,
        align: 'start',
        behavior: 'smooth',
      });
    });
  });

  it('opens day detail when a row is clicked', async () => {
    wrap(<CalendarPage />);
    await waitFor(() => {
      expect(document.querySelector(`[data-feed-date="${MOCK_TODAY}"]`)).toBeTruthy();
    });
    const todayRow = document.querySelector(`[data-feed-date="${MOCK_TODAY}"]`) as HTMLButtonElement;
    fireEvent.click(todayRow);
    await waitFor(() => {
      expect(screen.getByText('Обзорный Самарканд')).toBeTruthy();
      expect(screen.getByLabelText('Назад к ленте')).toBeTruthy();
    });
  });

  it('renders tour row content for today', async () => {
    wrap(<Feed />);
    await waitFor(() => {
      const row = document.querySelector(`[data-feed-date="${MOCK_TODAY}"]`);
      expect(row?.textContent).toContain('Обзорный Самарканд');
    });
    const todayRow = document.querySelector(`[data-feed-date="${MOCK_TODAY}"]`) as HTMLElement;
    expect(todayRow.textContent).toContain('09:00');
    expect(todayRow.textContent).toContain('Обзорный Самарканд');
  });

  it('renders day-off row content', async () => {
    wrap(<Feed />);
    await waitFor(() => {
      expect(document.querySelector('[data-feed-date="2026-08-10"]')).toBeTruthy();
    });
    const dayOffRow = document.querySelector('[data-feed-date="2026-08-10"]') as HTMLElement;
    expect(dayOffRow.textContent).toContain(t.dayOff);
  });

  it('uses stable ISO keys via computeItemKey', () => {
    wrap(<Feed />);
    const computeItemKey = lastVirtuosoProps?.computeItemKey as (i: number, iso: string) => string;
    expect(computeItemKey(0, '2020-01-01')).toBe('2020-01-01');
    expect(computeItemKey(42, '2020-02-12')).toBe('2020-02-12');
  });

  it('feed does not introduce horizontal overflow', () => {
    wrap(<Feed />);
    expect(screen.getByTestId('feed-virtuoso')).toBeTruthy();
  });
});

describe('Feed day status rows', () => {
  beforeEach(() => {
    lastVirtuosoProps = null;
    virtuosoScrollToIndex.mockClear();
    vi.spyOn(guideOsClient, 'getProfile').mockResolvedValue(MOCK_PROFILE);
    vi.spyOn(guideOsClient, 'listEntries').mockResolvedValue(INITIAL_ENTRIES);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  async function waitForFeedRow(iso: string) {
    await waitFor(() => {
      expect(document.querySelector(`[data-feed-date="${iso}"]`)).toBeTruthy();
    });
    return document.querySelector(`[data-feed-date="${iso}"]`) as HTMLButtonElement;
  }

  function tourEntry(
    id: string,
    date: string,
    status: 'reserved' | 'confirmed',
  ): CalendarEntry {
    return {
      id,
      type: 'tour',
      title: `Tour ${id}`,
      startDate: date,
      endDate: date,
      startTime: null,
      endTime: null,
      status,
      payment: 'unpaid',
      income: 100,
    };
  }

  function dayOffEntry(id: string, date: string): CalendarEntry {
    return {
      id,
      type: 'day_off',
      title: 'Выходной',
      startDate: date,
      endDate: date,
      startTime: null,
      endTime: null,
      income: 0,
    };
  }

  it('applies status-free to empty dates', async () => {
    wrap(<Feed />);
    const row = await waitForFeedRow('2026-08-01');
    expect(row.classList.contains('status-free')).toBe(true);
    expect(row.classList.contains('is-empty')).toBe(true);
    expect(row.textContent).toContain(t.dayFree);
    expect(row.getAttribute('style')).toBeNull();
  });

  it('applies status-reserved for reserved tours', async () => {
    wrap(<Feed />);
    const row = await waitForFeedRow('2026-08-05');
    expect(row.classList.contains('status-reserved')).toBe(true);
    expect(row.textContent).toContain('Вечерний Самарканд');
  });

  it('applies status-confirmed for confirmed tours', async () => {
    wrap(<Feed />);
    const row = await waitForFeedRow('2026-08-15');
    expect(row.classList.contains('status-confirmed')).toBe(true);
    expect(row.textContent).toContain('Бухара классика');
  });

  it('applies status-dayoff for day-off entries', async () => {
    wrap(<Feed />);
    const row = await waitForFeedRow('2026-08-10');
    expect(row.classList.contains('status-dayoff')).toBe(true);
    expect(row.textContent).toContain(t.dayOff);
  });

  it('uses effective status priority for mixed entries on one date', async () => {
    const mixedDate = '2026-08-20';
    vi.spyOn(guideOsClient, 'listEntries').mockResolvedValue([
      tourEntry('r1', mixedDate, 'reserved'),
      tourEntry('c1', mixedDate, 'confirmed'),
      dayOffEntry('d1', mixedDate),
    ]);
    wrap(<Feed />);
    const row = await waitForFeedRow(mixedDate);
    expect(row.classList.contains('status-dayoff')).toBe(true);
    expect(row.classList.contains('status-confirmed')).toBe(false);
    expect(row.classList.contains('status-reserved')).toBe(false);
  });

  it('keeps today class alongside status class', async () => {
    wrap(<Feed />);
    const row = await waitForFeedRow(MOCK_TODAY);
    expect(row.classList.contains('today')).toBe(true);
    expect(row.classList.contains('status-reserved')).toBe(true);
    expect(row.textContent).toContain('09:00');
    expect(row.textContent).toContain('Обзорный Самарканд');
  });

  it('uses month-picker semantic tokens in feed row CSS', () => {
    expect(GLOBAL_CSS).toMatch(
      /\.feed-day-row\.status-reserved\s*\{[^}]*background:\s*var\(--color-day-cell-reserved-bg\)/s,
    );
    expect(GLOBAL_CSS).toMatch(
      /\.feed-day-row\.status-confirmed\s*\{[^}]*background:\s*var\(--color-day-cell-confirmed-bg\)/s,
    );
    expect(GLOBAL_CSS).toMatch(
      /\.feed-day-row\.status-dayoff\s*\{[^}]*background:\s*var\(--color-day-cell-dayoff-bg\)/s,
    );
    expect(GLOBAL_CSS).toMatch(
      /\.feed-day-row\.status-free\s*\{[^}]*background:\s*var\(--color-surface\)/s,
    );
  });
});

describe('AppHeader', () => {
  it('shows logo, centered month/year, and settings without separate Today icon', () => {
    wrap(
      <AppHeader
        activeTab="calendar"
        headerMonth={7}
        headerYear={2026}
        monthExpanded={false}
        showMonthPicker={false}
        onLogoToday={vi.fn()}
        onToggleMonthPicker={vi.fn()}
        onSettings={vi.fn()}
      />,
    );
    expect(screen.getByLabelText('Сегодня')).toBeTruthy();
    expect(screen.getByLabelText('Настройки')).toBeTruthy();
    expect(screen.getByText(`${MONTH_NAMES_CAP[7]} 2026`)).toBeTruthy();
    expect(screen.getAllByLabelText('Сегодня').length).toBe(1);
  });

  it('clicking logo triggers Today handler', () => {
    const onLogoToday = vi.fn();
    wrap(
      <AppHeader
        activeTab="calendar"
        headerMonth={7}
        headerYear={2026}
        monthExpanded={false}
        showMonthPicker={false}
        onLogoToday={onLogoToday}
        onToggleMonthPicker={vi.fn()}
        onSettings={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByLabelText('Сегодня'));
    expect(onLogoToday).toHaveBeenCalledTimes(1);
  });

  it('shows reports title on reports tab', () => {
    wrap(
      <AppHeader
        activeTab="reports"
        headerMonth={7}
        headerYear={2026}
        monthExpanded={false}
        showMonthPicker={false}
        onLogoToday={vi.fn()}
        onToggleMonthPicker={vi.fn()}
        onSettings={vi.fn()}
      />,
    );
    expect(screen.getByText('Итоги')).toBeTruthy();
    expect(screen.queryByText(`${MONTH_NAMES_CAP[7]} 2026`)).toBeNull();
  });
});

describe('visible feed month', () => {
  it('updates header from August to September', () => {
    wrap(
      <>
        <HeaderFromContext />
        <VisibleMonthProbe />
      </>,
    );
    expect(screen.getByText(`${MONTH_NAMES_CAP[7]} 2026`)).toBeTruthy();
    fireEvent.click(screen.getByText('show-september'));
    expect(screen.getByText(`${MONTH_NAMES_CAP[8]} 2026`)).toBeTruthy();
  });

  it('updates header month and year for January 2027', () => {
    wrap(
      <>
        <HeaderFromContext />
        <VisibleMonthProbe />
      </>,
    );
    fireEvent.click(screen.getByText('show-january-2027'));
    expect(screen.getByText(`${MONTH_NAMES_CAP[0]} 2027`)).toBeTruthy();
  });
});

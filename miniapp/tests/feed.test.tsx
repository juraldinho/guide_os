import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import type { ReactElement } from 'react';
import { StrictMode } from 'react';
import { guideOsClient } from '@/api/createClient';
import { ToastProvider } from '@/components/ui/Toast';
import { CalendarProvider, useCalendar } from '@/features/calendar/CalendarContext';
import { CalendarPage } from '@/features/calendar/CalendarPage';
import { Feed, pickVisibleFeedIso, getStickyHeaderBottom } from '@/features/calendar/components/Feed';
import { AppHeader } from '@/components/layout/AppHeader';
import { MOCK_TODAY, USE_MOCK_API, ENTRIES_RANGE_FROM, ENTRIES_RANGE_TO } from '@/config';
import {
  buildFeedDates,
  buildFeedDatesFromRange,
  defaultFeedRange,
  FEED_INITIAL_DAYS,
  FEED_CHUNK_DAYS,
  shiftIso,
} from '@/features/calendar/lib/dates';
import { MONTH_NAMES_CAP } from '@/i18n/ru';

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

function FeedProbe() {
  const { feedFrom, feedTo, feedDayCount, entriesReady, extendFeed, prependFeed } = useCalendar();
  return (
    <>
      <span data-testid="feed-from">{feedFrom}</span>
      <span data-testid="feed-to">{feedTo}</span>
      <span data-testid="feed-count">{feedDayCount}</span>
      <span data-testid="entries-ready">{entriesReady ? 'yes' : 'no'}</span>
      <button type="button" onClick={extendFeed}>extend-feed</button>
      <button type="button" onClick={prependFeed}>prepend-feed</button>
    </>
  );
}

function GoTodayProbe() {
  const { goToday, prependFeed } = useCalendar();
  return (
    <>
      <button type="button" onClick={() => prependFeed()}>prepend-once</button>
      <button type="button" onClick={goToday}>go-today</button>
    </>
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

function ToggleMonthPicker() {
  const { toggleMonthPicker } = useCalendar();
  return (
    <button type="button" onClick={toggleMonthPicker}>toggle-picker</button>
  );
}

function mockRect(bottom: number, top = bottom - 48) {
  return {
    top,
    bottom,
    left: 0,
    right: 100,
    width: 100,
    height: bottom - top,
    x: 0,
    y: top,
    toJSON: () => ({}),
  };
}

function mockRowBottom(row: HTMLElement, bottom: number) {
  Object.defineProperty(row, 'getBoundingClientRect', {
    configurable: true,
    value: () => mockRect(bottom),
  });
}

async function waitForEntriesReady() {
  await waitFor(() => {
    expect(screen.getByTestId('entries-ready').textContent).toBe('yes');
  });
}

async function waitForFeedInitialized() {
  await waitForEntriesReady();
  await flushFeedRaf(2);
}

function silentPreloadFrom(): string {
  const next = shiftIso(MOCK_TODAY, -FEED_CHUNK_DAYS);
  return next < ENTRIES_RANGE_FROM ? ENTRIES_RANGE_FROM : next;
}

function countAfterSilentPreload(): number {
  return FEED_INITIAL_DAYS + FEED_CHUNK_DAYS;
}

async function flushFeedRaf(times = 2) {
  for (let i = 0; i < times; i++) {
    await act(async () => {
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
    });
  }
}

type ObserverHook = {
  callback: IntersectionObserverCallback;
  observe: ReturnType<typeof vi.fn>;
};

function installIntersectionObserverCapture() {
  const hooks: ObserverHook[] = [];
  vi.stubGlobal(
    'IntersectionObserver',
    vi.fn((callback: IntersectionObserverCallback) => {
      const observe = vi.fn();
      hooks.push({ callback, observe });
      return {
        observe,
        disconnect: vi.fn(),
        unobserve: vi.fn(),
      };
    }),
  );
  return hooks;
}

function observerForTarget(hooks: ObserverHook[], target: Element) {
  return hooks.find((hook) =>
    hook.observe.mock.calls.some((call) => call[0] === target),
  );
}

function latestObserverForTarget(hooks: ObserverHook[], target: Element) {
  const matched = hooks.filter((hook) =>
    hook.observe.mock.calls.some((call) => call[0] === target),
  );
  return matched.at(-1);
}

async function fireObserverIntersecting(hooks: ObserverHook[], target: Element) {
  const hook = latestObserverForTarget(hooks, target);
  if (!hook) return;
  await act(async () => {
    hook.callback(
      [{ isIntersecting: true, target } as IntersectionObserverEntry],
      {} as IntersectionObserver,
    );
  });
}

async function fireObserverNotIntersecting(hooks: ObserverHook[], target: Element) {
  const hook = latestObserverForTarget(hooks, target);
  if (!hook) return;
  await act(async () => {
    hook.callback(
      [{ isIntersecting: false, target } as IntersectionObserverEntry],
      {} as IntersectionObserver,
    );
  });
}

function simulateScrollY(y: number) {
  Object.defineProperty(window, 'scrollY', { configurable: true, value: y, writable: true });
  Object.defineProperty(document.documentElement, 'scrollTop', { configurable: true, value: y, writable: true });
  Object.defineProperty(document.body, 'scrollTop', { configurable: true, value: y, writable: true });
}

describe('pickVisibleFeedIso', () => {
  const HEADER_BOTTOM = 100;

  function rowMap(rects: Record<string, number>) {
    const elements = new Map<string, HTMLElement>();
    for (const [iso, bottom] of Object.entries(rects)) {
      const el = document.createElement('button');
      Object.defineProperty(el, 'getBoundingClientRect', {
        configurable: true,
        value: () => mockRect(bottom),
      });
      elements.set(iso, el);
    }
    return (iso: string) => elements.get(iso);
  }

  it('keeps August while 31 August bottom is 1px below header', () => {
    const dates = ['2026-08-31', '2026-09-01'];
    const iso = pickVisibleFeedIso(
      dates,
      rowMap({ '2026-08-31': HEADER_BOTTOM + 1, '2026-09-01': HEADER_BOTTOM + 60 }),
      HEADER_BOTTOM,
    );
    expect(iso).toBe('2026-08-31');
  });

  it('switches to September when 31 August bottom equals header bottom', () => {
    const dates = ['2026-08-31', '2026-09-01'];
    const iso = pickVisibleFeedIso(
      dates,
      rowMap({ '2026-08-31': HEADER_BOTTOM, '2026-09-01': HEADER_BOTTOM + 60 }),
      HEADER_BOTTOM,
    );
    expect(iso).toBe('2026-09-01');
  });

  it('returns to August when 31 August becomes 1px visible again', () => {
    const dates = ['2026-08-31', '2026-09-01'];
    const getRow = rowMap({ '2026-08-31': HEADER_BOTTOM + 1, '2026-09-01': HEADER_BOTTOM + 60 });
    expect(pickVisibleFeedIso(dates, getRow, HEADER_BOTTOM)).toBe('2026-08-31');
    const scrolledUp = rowMap({ '2026-08-31': HEADER_BOTTOM, '2026-09-01': HEADER_BOTTOM + 60 });
    expect(pickVisibleFeedIso(dates, scrolledUp, HEADER_BOTTOM)).toBe('2026-09-01');
    const scrolledBack = rowMap({ '2026-08-31': HEADER_BOTTOM + 1, '2026-09-01': HEADER_BOTTOM + 200 });
    expect(pickVisibleFeedIso(dates, scrolledBack, HEADER_BOTTOM)).toBe('2026-08-31');
  });

  it('switches to October when 30 September disappears above header', () => {
    const dates = ['2026-09-30', '2026-10-01'];
    const iso = pickVisibleFeedIso(
      dates,
      rowMap({ '2026-09-30': HEADER_BOTTOM, '2026-10-01': HEADER_BOTTOM + 40 }),
      HEADER_BOTTOM,
    );
    expect(iso).toBe('2026-10-01');
  });

  it('switches month and year from December 2026 to January 2027', () => {
    const dates = ['2026-12-31', '2027-01-01'];
    const iso = pickVisibleFeedIso(
      dates,
      rowMap({ '2026-12-31': HEADER_BOTTOM, '2027-01-01': HEADER_BOTTOM + 40 }),
      HEADER_BOTTOM,
    );
    expect(iso).toBe('2027-01-01');
  });
});

describe('Feed scroll month tracking', () => {
  const HEADER_BOTTOM = 100;

  beforeEach(() => {
    simulateScrollY(0);
    Element.prototype.scrollIntoView = vi.fn();
    vi.stubGlobal(
      'IntersectionObserver',
      vi.fn(() => ({
        observe: vi.fn(),
        disconnect: vi.fn(),
        unobserve: vi.fn(),
      })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('schedules only one rAF calculation per frame for multiple scroll events', async () => {
    wrap(<Feed />);
    await flushFeedRaf();

    const rafCallbacks: FrameRequestCallback[] = [];
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
      rafCallbacks.push(cb);
      return rafCallbacks.length;
    });

    fireEvent.scroll(window);
    fireEvent.scroll(window);
    fireEvent.scroll(window);

    expect(rafCallbacks.length).toBe(1);
  });

  it('switches header from September to August when scrolling upward', async () => {
    wrap(
      <>
        <HeaderFromContext />
        <VisibleMonthProbe />
        <Feed />
      </>,
    );

    const header = document.querySelector('.header') as HTMLElement;
    Object.defineProperty(header, 'getBoundingClientRect', {
      configurable: true,
      value: () => mockRect(HEADER_BOTTOM, 52),
    });

    fireEvent.click(screen.getByText('show-september'));
    expect(document.querySelector('.header-month-label')?.textContent).toContain(MONTH_NAMES_CAP[8]);

    const rows = screen.getAllByRole('button');
    rows.forEach((row) => {
      const iso = row.getAttribute('data-feed-date') ?? '';
      if (iso === '2026-08-31') {
        mockRowBottom(row, HEADER_BOTTOM + 1);
      } else if (iso < '2026-08-31') {
        mockRowBottom(row, HEADER_BOTTOM);
      } else {
        mockRowBottom(row, HEADER_BOTTOM + 200);
      }
    });

    fireEvent.scroll(document);
    await waitFor(() => {
      expect(document.querySelector('.header-month-label')?.textContent).toContain(MONTH_NAMES_CAP[7]);
    });
  });

  it('switches header month and year upward across January boundary', async () => {
    wrap(
      <>
        <FeedProbe />
        <HeaderFromContext />
        <VisibleMonthProbe />
        <Feed />
      </>,
    );

    for (let i = 0; i < 4; i++) {
      fireEvent.click(screen.getByText('extend-feed'));
    }

    const header = document.querySelector('.header') as HTMLElement;
    Object.defineProperty(header, 'getBoundingClientRect', {
      configurable: true,
      value: () => mockRect(HEADER_BOTTOM, 52),
    });

    fireEvent.click(screen.getByText('show-january-2027'));
    expect(document.querySelector('.header-month-label')?.textContent).toContain(`${MONTH_NAMES_CAP[0]} 2027`);

    const rows = screen.getAllByRole('button');
    const dec31 = rows.find((r) => r.getAttribute('data-feed-date') === '2026-12-31');
    expect(dec31).toBeTruthy();
    rows.forEach((row) => {
      const iso = row.getAttribute('data-feed-date') ?? '';
      if (iso === '2026-12-31') {
        mockRowBottom(row, HEADER_BOTTOM + 1);
      } else if (iso < '2026-12-31') {
        mockRowBottom(row, HEADER_BOTTOM);
      } else {
        mockRowBottom(row, HEADER_BOTTOM + 200);
      }
    });

    fireEvent.scroll(document);
    await waitFor(() => {
      expect(document.querySelector('.header-month-label')?.textContent).toContain(`${MONTH_NAMES_CAP[11]} 2026`);
    });
  });

  it('recalculates on document capture scroll', async () => {
    wrap(
      <>
        <HeaderFromContext />
        <Feed />
      </>,
    );

    const header = document.querySelector('.header') as HTMLElement;
    Object.defineProperty(header, 'getBoundingClientRect', {
      configurable: true,
      value: () => mockRect(HEADER_BOTTOM, 52),
    });

    await waitFor(() => {
      expect(document.querySelector('.header-month-label')?.textContent).toContain(MONTH_NAMES_CAP[7]);
    });

    const rows = screen.getAllByRole('button');
    const september = rows.find((r) => r.getAttribute('data-feed-date') === '2026-09-01');
    expect(september).toBeTruthy();
    rows.forEach((row) => {
      const iso = row.getAttribute('data-feed-date') ?? '';
      if (iso < '2026-09-01') {
        mockRowBottom(row, HEADER_BOTTOM);
      } else if (iso === '2026-09-01') {
        mockRowBottom(row, HEADER_BOTTOM + 40);
      } else {
        mockRowBottom(row, HEADER_BOTTOM + 200);
      }
    });

    fireEvent.scroll(document);
    await waitFor(() => {
      expect(document.querySelector('.header-month-label')?.textContent).toContain(MONTH_NAMES_CAP[8]);
    });
  });

  it('does not change header from scroll while month picker is open', async () => {
    wrap(
      <>
        <HeaderFromContext />
        <ToggleMonthPicker />
        <Feed />
      </>,
    );

    const header = document.querySelector('.header') as HTMLElement;
    Object.defineProperty(header, 'getBoundingClientRect', {
      configurable: true,
      value: () => mockRect(HEADER_BOTTOM, 52),
    });

    fireEvent.click(screen.getByText('toggle-picker'));
    expect(document.querySelector('.header-month-label')?.textContent).toContain(MONTH_NAMES_CAP[7]);

    const rows = screen.getAllByRole('button');
    rows.forEach((row) => {
      const iso = row.getAttribute('data-feed-date') ?? '';
      if (iso === '2026-10-01') {
        mockRowBottom(row, HEADER_BOTTOM + 40);
      } else {
        mockRowBottom(row, HEADER_BOTTOM);
      }
    });

    fireEvent.scroll(document);
    await waitFor(() => {
      expect(document.querySelector('.header-month-label')?.textContent).toContain(MONTH_NAMES_CAP[7]);
      expect(document.querySelector('.header-month-label')?.textContent).not.toContain(MONTH_NAMES_CAP[9]);
    });
  });

  it('removes scroll listeners on unmount', () => {
    const docRemove = vi.spyOn(document, 'removeEventListener');
    const winRemove = vi.spyOn(window, 'removeEventListener');
    const { unmount } = wrap(<Feed />);
    unmount();
    expect(docRemove).toHaveBeenCalledWith('scroll', expect.any(Function), true);
    expect(winRemove).toHaveBeenCalledWith('scroll', expect.any(Function));
    expect(winRemove).toHaveBeenCalledWith('resize', expect.any(Function));
  });

  it('uses rendered header bottom boundary', () => {
    document.querySelectorAll('.header').forEach((el) => el.remove());
    const header = document.createElement('header');
    header.className = 'header';
    Object.defineProperty(header, 'getBoundingClientRect', {
      configurable: true,
      value: () => mockRect(88, 44),
    });
    document.body.appendChild(header);
    expect(getStickyHeaderBottom()).toBe(88);
    document.body.removeChild(header);
  });
});

describe('defaultFeedRange', () => {
  it('starts on today with forward initial span', () => {
    const { from, to } = defaultFeedRange(MOCK_TODAY);
    const dates = buildFeedDatesFromRange(from, to);
    expect(from).toBe(MOCK_TODAY);
    expect(to).toBe(shiftIso(MOCK_TODAY, FEED_INITIAL_DAYS - 1));
    expect(dates[0]).toBe(MOCK_TODAY);
    expect(dates.length).toBe(FEED_INITIAL_DAYS);
  });

  it('prepend chunk math clamps at ENTRIES_RANGE_FROM', () => {
    const from = '2020-02-01';
    const next = shiftIso(from, -FEED_CHUNK_DAYS);
    const clamped = next < ENTRIES_RANGE_FROM ? ENTRIES_RANGE_FROM : next;
    expect(clamped).toBe(ENTRIES_RANGE_FROM);
  });

  it('extend chunk math clamps at ENTRIES_RANGE_TO', () => {
    const to = '2030-12-01';
    const next = shiftIso(to, FEED_CHUNK_DAYS);
    const clamped = next > ENTRIES_RANGE_TO ? ENTRIES_RANGE_TO : next;
    expect(clamped).toBe(ENTRIES_RANGE_TO);
  });
});

describe('buildFeedDates', () => {
  it('starts on mock today with initial chunk size', () => {
    const dates = buildFeedDates(MOCK_TODAY, FEED_INITIAL_DAYS);
    expect(dates.length).toBe(FEED_INITIAL_DAYS);
    expect(dates[0]).toBe(MOCK_TODAY);
  });

  it('appends consecutive dates without duplicates across chunks', () => {
    const first = buildFeedDates(MOCK_TODAY, FEED_INITIAL_DAYS);
    const extended = buildFeedDates(MOCK_TODAY, FEED_INITIAL_DAYS + FEED_CHUNK_DAYS);
    expect(extended.length).toBe(FEED_INITIAL_DAYS + FEED_CHUNK_DAYS);
    const unique = new Set(extended);
    expect(unique.size).toBe(extended.length);
    expect(extended.slice(0, first.length)).toEqual(first);
  });

  it('crosses December to January with correct year', () => {
    const dates = buildFeedDates('2026-12-01', 35);
    expect(dates[30]).toBe('2026-12-31');
    expect(dates[31]).toBe('2027-01-01');
  });

  it('includes January 2027 when scrolling from August 2026', () => {
    const dates = buildFeedDates('2026-08-28', 160);
    expect(dates.includes('2027-01-15')).toBe(true);
  });
});

describe('Feed', () => {
  beforeEach(() => {
    simulateScrollY(0);
    Element.prototype.scrollIntoView = vi.fn();
    vi.stubGlobal(
      'IntersectionObserver',
      vi.fn(() => ({
        observe: vi.fn(),
        disconnect: vi.fn(),
        unobserve: vi.fn(),
      })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders forward initial day count from today', () => {
    wrap(<Feed />);
    const rows = screen.getAllByRole('button');
    expect(rows.length).toBe(FEED_INITIAL_DAYS);
    expect(rows.length).toBe(
      buildFeedDatesFromRange(
        defaultFeedRange(MOCK_TODAY).from,
        defaultFeedRange(MOCK_TODAY).to,
      ).length,
    );
  });

  it('first row is mock today', () => {
    wrap(<Feed />);
    const rows = screen.getAllByRole('button');
    expect(rows[0].getAttribute('data-feed-date')).toBe(MOCK_TODAY);
  });

  it('includes today without prepended past days before entries settle', () => {
    let resolveEntries!: (value: unknown[]) => void;
    const entriesPromise = new Promise<unknown[]>((resolve) => {
      resolveEntries = resolve;
    });
    vi.spyOn(guideOsClient, 'listEntries').mockReturnValue(entriesPromise as never);

    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    expect(screen.getByTestId('entries-ready').textContent).toBe('no');
    const isos = screen
      .getAllByRole('button')
      .map((r) => r.getAttribute('data-feed-date'))
      .filter(Boolean) as string[];
    expect(isos[0]).toBe(MOCK_TODAY);
    expect(isos.some((iso) => iso < MOCK_TODAY)).toBe(false);

    resolveEntries([]);
  });

  it('keeps chronological ascending DOM order', () => {
    wrap(<Feed />);
    const isos = screen
      .getAllByRole('button')
      .map((r) => r.getAttribute('data-feed-date'))
      .filter(Boolean) as string[];
    for (let i = 1; i < isos.length; i++) {
      expect(isos[i] >= isos[i - 1]).toBe(true);
    }
  });

  it('uses distinct top and bottom sentinel markers', () => {
    wrap(<Feed />);
    expect(screen.getByTestId('feed-sentinel-top')).toBeTruthy();
    expect(screen.getByTestId('feed-sentinel-bottom')).toBeTruthy();
  });

  it('opens day detail when a row is clicked', () => {
    wrap(<CalendarPage />);
    const rows = screen.getAllByRole('button');
    fireEvent.click(rows[1]);
    expect(screen.getByLabelText('Назад к ленте')).toBeTruthy();
  });

  it('extends feed forward by one chunk without duplicates', async () => {
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    const toBefore = screen.getByTestId('feed-to').textContent;
    const countBefore = Number(screen.getByTestId('feed-count').textContent);
    fireEvent.click(screen.getByText('extend-feed'));
    await waitFor(() => {
      expect(screen.getByTestId('feed-to').textContent).not.toBe(toBefore);
      expect(Number(screen.getByTestId('feed-count').textContent)).toBe(
        countBefore + FEED_CHUNK_DAYS,
      );
    });
    const rows = screen.getAllByRole('button');
    const isos = rows.map((r) => r.getAttribute('data-feed-date')).filter(Boolean);
    expect(new Set(isos).size).toBe(isos.length);
  });

  it('prepends feed backward by one chunk without duplicates', async () => {
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    const fromBefore = screen.getByTestId('feed-from').textContent;
    const countBefore = Number(screen.getByTestId('feed-count').textContent);
    fireEvent.click(screen.getByText('prepend-feed'));
    await waitFor(() => {
      expect(screen.getByTestId('feed-from').textContent).not.toBe(fromBefore);
      expect(Number(screen.getByTestId('feed-count').textContent)).toBe(
        countBefore + FEED_CHUNK_DAYS,
      );
    });
    const isos = screen
      .getAllByRole('button')
      .map((r) => r.getAttribute('data-feed-date'))
      .filter(Boolean);
    expect(new Set(isos).size).toBe(isos.length);
  });

  it('prepending preserves visible row position via scroll correction', async () => {
    const observerHooks = installIntersectionObserverCapture();
    const HEADER_BOTTOM = 100;
    const header = document.createElement('header');
    header.className = 'header';
    Object.defineProperty(header, 'getBoundingClientRect', {
      configurable: true,
      value: () => mockRect(HEADER_BOTTOM, 52),
    });
    document.body.appendChild(header);

    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await flushFeedRaf();
    await waitForFeedInitialized();

    const scrollBy = vi.spyOn(window, 'scrollBy').mockImplementation(() => {});

    const rows = screen.getAllByRole('button');
    rows.forEach((row) => {
      const iso = row.getAttribute('data-feed-date') ?? '';
      if (iso < MOCK_TODAY) {
        mockRowBottom(row, HEADER_BOTTOM);
      } else if (iso === MOCK_TODAY) {
        mockRowBottom(row, HEADER_BOTTOM + 60);
      } else {
        mockRowBottom(row, HEADER_BOTTOM + 200);
      }
    });

    let todayRectReads = 0;
    const todayRow = rows.find((r) => r.getAttribute('data-feed-date') === MOCK_TODAY);
    Object.defineProperty(todayRow!, 'getBoundingClientRect', {
      configurable: true,
      value: () => {
        todayRectReads += 1;
        const top = todayRectReads <= 2 ? HEADER_BOTTOM + 12 : HEADER_BOTTOM + 92;
        return mockRect(top + 48, top);
      },
    });

    todayRectReads = 0;
    await fireObserverIntersecting(observerHooks, screen.getByTestId('feed-sentinel-top'));

    await waitFor(() => {
      expect(screen.getAllByRole('button').length).toBeGreaterThan(rows.length);
    });
    await waitFor(() => {
      expect(scrollBy).toHaveBeenCalledWith({ top: 80, left: 0, behavior: 'auto' });
    });
    document.body.removeChild(header);
    scrollBy.mockRestore();
  });

  it('logo Today works after prepending into the past', async () => {
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView');
    wrap(
      <>
        <FeedProbe />
        <HeaderFromContext />
        <GoTodayProbe />
        <Feed />
      </>,
    );
    const initialFrom = screen.getByTestId('feed-from').textContent;
    fireEvent.click(screen.getByText('prepend-once'));
    await waitFor(() => {
      expect(screen.getByTestId('feed-from').textContent).not.toBe(initialFrom);
    });

    fireEvent.click(screen.getByLabelText('Сегодня'));
    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalled();
      expect(screen.getByText(`${MONTH_NAMES_CAP[7]} 2026`)).toBeTruthy();
    });
    scrollIntoView.mockRestore();
  });

  it('prepend-feed stops at ENTRIES_RANGE_FROM', async () => {
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    for (let i = 0; i < 90; i++) {
      fireEvent.click(screen.getByText('prepend-feed'));
    }
    await waitFor(() => {
      expect(screen.getByTestId('feed-from').textContent).toBe(ENTRIES_RANGE_FROM);
    });
  });

  it('extend-feed stops at ENTRIES_RANGE_TO', async () => {
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    for (let i = 0; i < 90; i++) {
      fireEvent.click(screen.getByText('extend-feed'));
    }
    await waitFor(() => {
      expect(screen.getByTestId('feed-to').textContent).toBe(ENTRIES_RANGE_TO);
    });
  });

  it('feed does not introduce horizontal overflow', () => {
    wrap(<Feed />);
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(
      document.documentElement.clientWidth + 1,
    );
  });

  it('mock mode keeps deterministic today date', () => {
    expect(USE_MOCK_API).toBe(true);
    expect(MOCK_TODAY).toBe('2026-08-28');
  });
});

describe('Feed sentinel regression', () => {
  const initialTo = defaultFeedRange(MOCK_TODAY).to;
  const afterSilentFrom = silentPreloadFrom();
  let observerHooks: ObserverHook[];

  beforeEach(() => {
    simulateScrollY(0);
    Element.prototype.scrollIntoView = vi.fn();
    observerHooks = installIntersectionObserverCapture();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('initial mount does not call scrollIntoView', () => {
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView');
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    expect(scrollIntoView).not.toHaveBeenCalled();
    scrollIntoView.mockRestore();
  });

  it('sentinel observers are not active before entriesReady', async () => {
    let resolveEntries!: (value: unknown[]) => void;
    const entriesPromise = new Promise<unknown[]>((resolve) => {
      resolveEntries = resolve;
    });
    vi.spyOn(guideOsClient, 'listEntries').mockReturnValue(entriesPromise as never);

    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    expect(screen.getByTestId('entries-ready').textContent).toBe('no');
    expect(observerForTarget(observerHooks, screen.getByTestId('feed-sentinel-top'))).toBeUndefined();
    expect(observerForTarget(observerHooks, screen.getByTestId('feed-sentinel-bottom'))).toBeUndefined();

    await act(async () => {
      resolveEntries([]);
      await entriesPromise;
    });
  });

  it('silently preloads exactly one past chunk after entries become ready', async () => {
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await waitForFeedInitialized();
    expect(screen.getByTestId('feed-from').textContent).toBe(afterSilentFrom);
    expect(Number(screen.getByTestId('feed-count').textContent)).toBe(countAfterSilentPreload());
  });

  it('silent preload keeps today at the same visual top with one scrollBy', async () => {
    const scrollBy = vi.spyOn(window, 'scrollBy').mockImplementation(() => {});
    let todayTop = 120;
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );

    const todayRow = document.querySelector(`[data-feed-date="${MOCK_TODAY}"]`) as HTMLElement;
    Object.defineProperty(todayRow, 'getBoundingClientRect', {
      configurable: true,
      value: () => {
        const top = todayTop;
        todayTop += 80;
        return mockRect(top + 48, top);
      },
    });

    await waitForEntriesReady();
    await flushFeedRaf(2);

    expect(scrollBy).toHaveBeenCalledTimes(1);
    expect(scrollBy).toHaveBeenCalledWith({ top: 80, left: 0, behavior: 'auto' });
    scrollBy.mockRestore();
  });

  it('entries height changes after init do not move today or call scrollIntoView', async () => {
    const scrollBy = vi.spyOn(window, 'scrollBy').mockImplementation(() => {});
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView');

    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await waitForFeedInitialized();

    const todayTop = 100;
    const todayRow = document.querySelector(`[data-feed-date="${MOCK_TODAY}"]`) as HTMLElement;
    Object.defineProperty(todayRow, 'getBoundingClientRect', {
      configurable: true,
      value: () => mockRect(todayTop + 48, todayTop),
    });

    const scrollCallsAfterInit = scrollBy.mock.calls.length;
    await act(async () => {
      await guideOsClient.listEntries();
    });
    await flushFeedRaf();

    expect(scrollBy.mock.calls.length).toBe(scrollCallsAfterInit);
    expect(scrollIntoView).not.toHaveBeenCalled();
    expect(todayRow.getBoundingClientRect().top).toBe(todayTop);

    scrollBy.mockRestore();
    scrollIntoView.mockRestore();
  });

  it('after initialization, repeated scroll does not prepend again', async () => {
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await waitForFeedInitialized();
    const fromAfterInit = screen.getByTestId('feed-from').textContent;

    fireEvent.scroll(window);
    await flushFeedRaf();
    expect(screen.getByTestId('feed-from').textContent).toBe(fromAfterInit);
  });

  it('top sentinel intersection prepends exactly one chunk', async () => {
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await waitForFeedInitialized();

    const topSentinel = screen.getByTestId('feed-sentinel-top');
    await fireObserverIntersecting(observerHooks, topSentinel);
    await waitFor(() => {
      expect(screen.getByTestId('feed-from').textContent).not.toBe(afterSilentFrom);
    });
    expect(Number(screen.getByTestId('feed-count').textContent)).toBe(
      countAfterSilentPreload() + FEED_CHUNK_DAYS,
    );
  });

  it('leaving and re-entering top sentinel loads the next backward chunk', async () => {
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await waitForFeedInitialized();

    const topSentinel = screen.getByTestId('feed-sentinel-top');
    await fireObserverIntersecting(observerHooks, topSentinel);
    await waitFor(() => {
      expect(screen.getByTestId('feed-from').textContent).not.toBe(afterSilentFrom);
    });
    const fromAfterFirst = screen.getByTestId('feed-from').textContent;

    await fireObserverNotIntersecting(observerHooks, topSentinel);
    await fireObserverIntersecting(observerHooks, topSentinel);
    await waitFor(() => {
      expect(screen.getByTestId('feed-from').textContent).not.toBe(fromAfterFirst);
    });
  });

  it('logo Today does not prepend additional chunks', async () => {
    wrap(
      <>
        <FeedProbe />
        <HeaderFromContext />
        <Feed />
      </>,
    );
    await waitForFeedInitialized();

    fireEvent.click(screen.getByLabelText('Сегодня'));
    await waitFor(() => {
      expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    });
    expect(screen.getByTestId('feed-from').textContent).toBe(afterSilentFrom);
  });

  it('scroll-anchor correction uses one scrollBy after user prepend', async () => {
    const HEADER_BOTTOM = 100;
    const header = document.createElement('header');
    header.className = 'header';
    Object.defineProperty(header, 'getBoundingClientRect', {
      configurable: true,
      value: () => mockRect(HEADER_BOTTOM, 52),
    });
    document.body.appendChild(header);

    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await waitForFeedInitialized();

    const scrollBy = vi.spyOn(window, 'scrollBy').mockImplementation(() => {});
    const rows = screen.getAllByRole('button');
    rows.forEach((row) => {
      const iso = row.getAttribute('data-feed-date') ?? '';
      if (iso < MOCK_TODAY) {
        mockRowBottom(row, HEADER_BOTTOM);
      } else if (iso === MOCK_TODAY) {
        mockRowBottom(row, HEADER_BOTTOM + 60);
      } else {
        mockRowBottom(row, HEADER_BOTTOM + 200);
      }
    });

    let todayRectReads = 0;
    const todayRow = rows.find((r) => r.getAttribute('data-feed-date') === MOCK_TODAY);
    Object.defineProperty(todayRow!, 'getBoundingClientRect', {
      configurable: true,
      value: () => {
        todayRectReads += 1;
        const top = todayRectReads <= 2 ? HEADER_BOTTOM + 12 : HEADER_BOTTOM + 92;
        return mockRect(top + 48, top);
      },
    });

    const topSentinel = screen.getByTestId('feed-sentinel-top');
    const scrollCallsAfterInit = scrollBy.mock.calls.length;
    await fireObserverIntersecting(observerHooks, topSentinel);
    await waitFor(() => {
      expect(screen.getByTestId('feed-from').textContent).not.toBe(afterSilentFrom);
    });
    await waitFor(() => {
      expect(scrollBy.mock.calls.length).toBe(scrollCallsAfterInit + 1);
    });
    expect(scrollBy).toHaveBeenCalledWith({ top: 80, left: 0, behavior: 'auto' });

    document.body.removeChild(header);
    scrollBy.mockRestore();
  });

  it('bottom sentinel intersection extends exactly one chunk', async () => {
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await waitForFeedInitialized();

    const bottomSentinel = screen.getByTestId('feed-sentinel-bottom');
    await fireObserverIntersecting(observerHooks, bottomSentinel);
    await waitFor(() => {
      expect(screen.getByTestId('feed-to').textContent).not.toBe(initialTo);
    });
    expect(Number(screen.getByTestId('feed-count').textContent)).toBe(
      countAfterSilentPreload() + FEED_CHUNK_DAYS,
    );
  });

  it('bottom sentinel repeatedly extends future chunks', async () => {
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await waitForFeedInitialized();

    const bottomSentinel = screen.getByTestId('feed-sentinel-bottom');
    await fireObserverIntersecting(observerHooks, bottomSentinel);
    await waitFor(() => {
      expect(screen.getByTestId('feed-to').textContent).not.toBe(initialTo);
    });
    const toAfterFirst = screen.getByTestId('feed-to').textContent;

    await fireObserverNotIntersecting(observerHooks, bottomSentinel);
    await fireObserverIntersecting(observerHooks, bottomSentinel);
    await waitFor(() => {
      expect(screen.getByTestId('feed-to').textContent).not.toBe(toAfterFirst);
    });
  });

  it('StrictMode does not auto-prepend beyond silent preload on mount', async () => {
    render(
      <StrictMode>
        <ToastProvider>
          <CalendarProvider>
            <FeedProbe />
            <Feed />
          </CalendarProvider>
        </ToastProvider>
      </StrictMode>,
    );
    await waitForFeedInitialized();
    expect(screen.getByTestId('feed-from').textContent).toBe(afterSilentFrom);
    expect(screen.getByTestId('feed-to').textContent).toBe(initialTo);
    expect(Number(screen.getByTestId('feed-count').textContent)).toBe(countAfterSilentPreload());
  });

  it('feed remount does not call scrollIntoView on open', async () => {
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView');

    const { unmount } = wrap(<Feed />);
    await flushFeedRaf();
    const callsAfterFirst = scrollIntoView.mock.calls.length;

    simulateScrollY(800);
    unmount();

    wrap(<Feed />);
    await flushFeedRaf();

    expect(scrollIntoView.mock.calls.length).toBe(callsAfterFirst);
    scrollIntoView.mockRestore();
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

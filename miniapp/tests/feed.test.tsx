import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import type { ReactElement } from 'react';
import { StrictMode } from 'react';
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
  const { feedFrom, feedTo, feedDayCount, extendFeed, prependFeed } = useCalendar();
  return (
    <>
      <span data-testid="feed-from">{feedFrom}</span>
      <span data-testid="feed-to">{feedTo}</span>
      <span data-testid="feed-count">{feedDayCount}</span>
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

type ObserverHook = {
  cb: IntersectionObserverCallback;
  target: Element | null;
};

function installIntersectionObserverCapture(autoFireOnObserve = false) {
  const hooks: ObserverHook[] = [];
  const factory = vi.fn((cb: IntersectionObserverCallback) => ({
    observe: vi.fn((el: Element) => {
      hooks.push({ cb, target: el });
      if (autoFireOnObserve) {
        cb([{ isIntersecting: true, target: el } as IntersectionObserverEntry], {} as IntersectionObserver);
      }
    }),
    disconnect: vi.fn(),
    unobserve: vi.fn(),
  }));
  vi.stubGlobal('IntersectionObserver', factory);
  return { hooks, factory };
}

function simulateScrollY(y: number) {
  Object.defineProperty(window, 'scrollY', { configurable: true, value: y, writable: true });
  Object.defineProperty(document.documentElement, 'scrollTop', { configurable: true, value: y, writable: true });
  Object.defineProperty(document.body, 'scrollTop', { configurable: true, value: y, writable: true });
}

function markSentinelOutside(hook: ObserverHook) {
  hook.cb(
    [{ isIntersecting: false, target: hook.target! } as IntersectionObserverEntry],
    {} as IntersectionObserver,
  );
}

function markSentinelIntersecting(hook: ObserverHook) {
  hook.cb(
    [{ isIntersecting: true, target: hook.target! } as IntersectionObserverEntry],
    {} as IntersectionObserver,
  );
}

function findObserverHook(hooks: ObserverHook[], testId: string) {
  return hooks.find((h) => h.target?.getAttribute('data-testid') === testId);
}

async function flushObserversEnabled() {
  await act(async () => {
    await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
  });
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
    await flushObserversEnabled();

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
  it('includes today with dates before and after for immediate bidirectional scroll', () => {
    const { from, to } = defaultFeedRange(MOCK_TODAY);
    const dates = buildFeedDatesFromRange(from, to);
    expect(dates.includes(MOCK_TODAY)).toBe(true);
    expect(dates.some((d) => d < MOCK_TODAY)).toBe(true);
    expect(dates.some((d) => d > MOCK_TODAY)).toBe(true);
    expect(dates[0]).toBe(from);
    expect(dates[dates.length - 1]).toBe(to);
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

  it('renders bidirectional initial day count', () => {
    wrap(<Feed />);
    const rows = screen.getAllByRole('button');
    const expectedCount = buildFeedDatesFromRange(
      defaultFeedRange(MOCK_TODAY).from,
      defaultFeedRange(MOCK_TODAY).to,
    ).length;
    expect(rows.length).toBe(expectedCount);
    expect(rows.length).toBeGreaterThan(FEED_INITIAL_DAYS);
  });

  it('includes today with earlier dates in the feed', () => {
    wrap(<Feed />);
    const isos = screen
      .getAllByRole('button')
      .map((r) => r.getAttribute('data-feed-date'))
      .filter(Boolean) as string[];
    expect(isos.includes(MOCK_TODAY)).toBe(true);
    expect(isos.some((iso) => iso < MOCK_TODAY)).toBe(true);
    expect(isos[0] < MOCK_TODAY).toBe(true);
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
    const HEADER_BOTTOM = 100;
    const header = document.createElement('header');
    header.className = 'header';
    Object.defineProperty(header, 'getBoundingClientRect', {
      configurable: true,
      value: () => mockRect(HEADER_BOTTOM, 52),
    });
    document.body.appendChild(header);

    const { hooks } = installIntersectionObserverCapture(false);
    wrap(<Feed />);
    await flushObserversEnabled();

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

    let todayTop = HEADER_BOTTOM + 12;
    let todayRectReads = 0;
    const todayRow = rows.find((r) => r.getAttribute('data-feed-date') === MOCK_TODAY);
    Object.defineProperty(todayRow!, 'getBoundingClientRect', {
      configurable: true,
      value: () => {
        todayRectReads += 1;
        const top = todayRectReads <= 2 ? todayTop : HEADER_BOTTOM + 92;
        return mockRect(top + 48, top);
      },
    });

    const topHook = findObserverHook(hooks, 'feed-sentinel-top');
    expect(topHook).toBeTruthy();
    markSentinelOutside(topHook!);
    markSentinelIntersecting(topHook!);

    await waitFor(() => {
      expect(scrollBy).toHaveBeenCalledWith(0, 80);
    });
    document.body.removeChild(header);
    scrollBy.mockRestore();
  });

  it('logo Today works after prepending into the past', async () => {
    const scrollBy = vi.spyOn(window, 'scrollBy').mockImplementation(() => {});
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

    const todayRow = screen
      .getAllByRole('button')
      .find((r) => r.getAttribute('data-feed-date') === MOCK_TODAY);
    expect(todayRow).toBeTruthy();
    mockRowBottom(todayRow!, 420);

    fireEvent.click(screen.getByLabelText('Сегодня'));
    await waitFor(() => {
      expect(scrollBy).toHaveBeenCalled();
      expect(screen.getByText(`${MONTH_NAMES_CAP[7]} 2026`)).toBeTruthy();
    });
    scrollBy.mockRestore();
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
  const defaultFrom = defaultFeedRange(MOCK_TODAY).from;
  const defaultTo = defaultFeedRange(MOCK_TODAY).to;

  beforeEach(() => {
    simulateScrollY(0);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('initial render does not prepend when top sentinel intersects on observe', async () => {
    installIntersectionObserverCapture(true);
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await flushObserversEnabled();
    await waitFor(() => {
      expect(screen.getByTestId('feed-from').textContent).toBe(defaultFrom);
    });
  });

  it('initial render does not extend when bottom sentinel intersects on observe', async () => {
    installIntersectionObserverCapture(true);
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await flushObserversEnabled();
    await waitFor(() => {
      expect(screen.getByTestId('feed-to').textContent).toBe(defaultTo);
    });
  });

  it('after initial positioning, intersection alone does not load chunks', async () => {
    const { hooks } = installIntersectionObserverCapture(false);
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await flushObserversEnabled();

    const topHook = findObserverHook(hooks, 'feed-sentinel-top');
    const bottomHook = findObserverHook(hooks, 'feed-sentinel-bottom');
    expect(topHook).toBeTruthy();
    expect(bottomHook).toBeTruthy();

    topHook!.cb([{ isIntersecting: true, target: topHook!.target! } as IntersectionObserverEntry], {} as IntersectionObserver);
    bottomHook!.cb([{ isIntersecting: true, target: bottomHook!.target! } as IntersectionObserverEntry], {} as IntersectionObserver);

    expect(screen.getByTestId('feed-from').textContent).toBe(defaultFrom);
    expect(screen.getByTestId('feed-to').textContent).toBe(defaultTo);
  });

  it('top intersection before sentinel was outside does not prepend', async () => {
    const { hooks } = installIntersectionObserverCapture(false);
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await flushObserversEnabled();

    const topHook = findObserverHook(hooks, 'feed-sentinel-top');
    topHook!.cb([{ isIntersecting: true, target: topHook!.target! } as IntersectionObserverEntry], {} as IntersectionObserver);
    expect(screen.getByTestId('feed-from').textContent).toBe(defaultFrom);
  });

  it('top intersection after sentinel left viewport prepends exactly one chunk', async () => {
    const { hooks } = installIntersectionObserverCapture(false);
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await flushObserversEnabled();

    const topHook = findObserverHook(hooks, 'feed-sentinel-top');
    markSentinelOutside(topHook!);
    markSentinelIntersecting(topHook!);

    await waitFor(() => {
      expect(screen.getByTestId('feed-from').textContent).not.toBe(defaultFrom);
    });

    const fromAfterFirst = screen.getByTestId('feed-from').textContent;
    markSentinelIntersecting(topHook!);
    expect(screen.getByTestId('feed-from').textContent).toBe(fromAfterFirst);
  });

  it('re-arms top sentinel only after it leaves the viewport', async () => {
    const { hooks } = installIntersectionObserverCapture(false);
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await flushObserversEnabled();

    const topHook = findObserverHook(hooks, 'feed-sentinel-top');
    markSentinelOutside(topHook!);
    markSentinelIntersecting(topHook!);
    await waitFor(() => {
      expect(screen.getByTestId('feed-from').textContent).not.toBe(defaultFrom);
    });
    const fromAfterFirst = screen.getByTestId('feed-from').textContent;

    markSentinelOutside(topHook!);
    markSentinelIntersecting(topHook!);

    await waitFor(() => {
      expect(screen.getByTestId('feed-from').textContent).not.toBe(fromAfterFirst);
    });
  });

  it('logo Today scroll does not prepend additional chunks', async () => {
    installIntersectionObserverCapture(true);
    const scrollBy = vi.spyOn(window, 'scrollBy').mockImplementation(() => {});
    wrap(
      <>
        <FeedProbe />
        <HeaderFromContext />
        <Feed />
      </>,
    );
    await flushObserversEnabled();

    const todayRow = screen
      .getAllByRole('button')
      .find((r) => r.getAttribute('data-feed-date') === MOCK_TODAY);
    expect(todayRow).toBeTruthy();
    mockRowBottom(todayRow!, 420);

    fireEvent.click(screen.getByLabelText('Сегодня'));
    await waitFor(() => {
      expect(scrollBy).toHaveBeenCalled();
    });
    expect(screen.getByTestId('feed-from').textContent).toBe(defaultFrom);
    scrollBy.mockRestore();
  });

  it('scroll-anchor correction does not trigger a second prepend while sentinel stays intersecting', async () => {
    const HEADER_BOTTOM = 100;
    const header = document.createElement('header');
    header.className = 'header';
    Object.defineProperty(header, 'getBoundingClientRect', {
      configurable: true,
      value: () => mockRect(HEADER_BOTTOM, 52),
    });
    document.body.appendChild(header);

    const { hooks } = installIntersectionObserverCapture(false);
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await flushObserversEnabled();

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

    const todayRow = rows.find((r) => r.getAttribute('data-feed-date') === MOCK_TODAY);
    let todayRectReads = 0;
    Object.defineProperty(todayRow!, 'getBoundingClientRect', {
      configurable: true,
      value: () => {
        todayRectReads += 1;
        const top = todayRectReads <= 2 ? HEADER_BOTTOM + 12 : HEADER_BOTTOM + 92;
        return mockRect(top + 48, top);
      },
    });

    const topHook = findObserverHook(hooks, 'feed-sentinel-top');
    markSentinelOutside(topHook!);
    markSentinelIntersecting(topHook!);
    await waitFor(() => {
      expect(screen.getByTestId('feed-from').textContent).not.toBe(defaultFrom);
    });
    const fromAfterFirst = screen.getByTestId('feed-from').textContent;

    await waitFor(() => expect(scrollBy).toHaveBeenCalledWith(0, 80));

    markSentinelOutside(topHook!);
    markSentinelIntersecting(topHook!);
    expect(screen.getByTestId('feed-from').textContent).toBe(fromAfterFirst);

    document.body.removeChild(header);
    scrollBy.mockRestore();
  });

  it('bottom intersection after sentinel left viewport appends exactly one chunk', async () => {
    const { hooks } = installIntersectionObserverCapture(false);
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    await flushObserversEnabled();

    const bottomHook = findObserverHook(hooks, 'feed-sentinel-bottom');
    markSentinelOutside(bottomHook!);
    markSentinelIntersecting(bottomHook!);

    await waitFor(() => {
      expect(screen.getByTestId('feed-to').textContent).not.toBe(defaultTo);
    });

    const toAfterFirst = screen.getByTestId('feed-to').textContent;
    markSentinelIntersecting(bottomHook!);
    expect(screen.getByTestId('feed-to').textContent).toBe(toAfterFirst);
  });

  it('positions today directly below the sticky header on first open', async () => {
    const HEADER_BOTTOM = 100;
    installIntersectionObserverCapture(false);

    const header = document.createElement('header');
    header.className = 'header';
    Object.defineProperty(header, 'getBoundingClientRect', {
      configurable: true,
      value: () => mockRect(HEADER_BOTTOM, 52),
    });
    document.body.appendChild(header);

    const scrollBy = vi.spyOn(window, 'scrollBy').mockImplementation(() => {});
    wrap(<Feed />);

    await flushObserversEnabled();

    expect(scrollBy).toHaveBeenCalled();
    const todayRow = screen
      .getAllByRole('button')
      .find((r) => r.getAttribute('data-feed-date') === MOCK_TODAY);
    expect(todayRow).toBeTruthy();
    const todayTop = todayRow!.getBoundingClientRect().top;
    expect(scrollBy.mock.calls.some((call) => call[0] === 0 && call[1] === todayTop - HEADER_BOTTOM)).toBe(true);
    document.body.removeChild(header);
    scrollBy.mockRestore();
  });

  it('StrictMode does not auto-prepend when sentinels intersect on observe', async () => {
    const { factory } = installIntersectionObserverCapture(true);
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
    await flushObserversEnabled();
    await waitFor(() => {
      expect(screen.getByTestId('feed-from').textContent).toBe(defaultFrom);
      expect(screen.getByTestId('feed-to').textContent).toBe(defaultTo);
    });
    expect(factory.mock.calls.length).toBeGreaterThan(0);
  });

  it('repositions today on feed remount like Mini App reopen', async () => {
    const HEADER_BOTTOM = 100;
    const header = document.createElement('header');
    header.className = 'header';
    Object.defineProperty(header, 'getBoundingClientRect', {
      configurable: true,
      value: () => mockRect(HEADER_BOTTOM, 52),
    });
    document.body.appendChild(header);

    installIntersectionObserverCapture(false);
    const scrollBy = vi.spyOn(window, 'scrollBy').mockImplementation(() => {});

    const { unmount } = wrap(<Feed />);
    await flushObserversEnabled();
    const callsAfterFirst = scrollBy.mock.calls.length;

    simulateScrollY(800);
    unmount();

    wrap(<Feed />);
    await flushObserversEnabled();

    expect(scrollBy.mock.calls.length).toBeGreaterThan(callsAfterFirst);
    document.body.removeChild(header);
    scrollBy.mockRestore();
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

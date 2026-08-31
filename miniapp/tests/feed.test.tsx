import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { ToastProvider } from '@/components/ui/Toast';
import { CalendarProvider, useCalendar } from '@/features/calendar/CalendarContext';
import { CalendarPage } from '@/features/calendar/CalendarPage';
import { Feed, pickVisibleFeedIso, getStickyHeaderBottom } from '@/features/calendar/components/Feed';
import { AppHeader } from '@/components/layout/AppHeader';
import { MOCK_TODAY, USE_MOCK_API } from '@/config';
import {
  buildFeedDates,
  FEED_INITIAL_DAYS,
  FEED_CHUNK_DAYS,
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
  const { feedDayCount, extendFeed } = useCalendar();
  return (
    <>
      <span data-testid="feed-count">{feedDayCount}</span>
      <button type="button" onClick={extendFeed}>extend-feed</button>
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

  it('schedules only one rAF calculation per frame for multiple scroll events', () => {
    const rafCallbacks: FrameRequestCallback[] = [];
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
      rafCallbacks.push(cb);
      return rafCallbacks.length;
    });

    wrap(<Feed />);
    fireEvent.scroll(window);
    fireEvent.scroll(window);
    fireEvent.scroll(window);

    expect(rafCallbacks.length).toBe(1);
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

  it('renders more than eight day rows from mock today', () => {
    wrap(<Feed />);
    const rows = screen.getAllByRole('button');
    expect(rows.length).toBeGreaterThan(8);
    expect(rows.length).toBe(FEED_INITIAL_DAYS);
  });

  it('first row is mock today', () => {
    wrap(<Feed />);
    const rows = screen.getAllByRole('button');
    expect(rows[0].getAttribute('data-feed-date')).toBe(MOCK_TODAY);
  });

  it('opens day detail when a row is clicked', () => {
    wrap(<CalendarPage />);
    const rows = screen.getAllByRole('button');
    fireEvent.click(rows[1]);
    expect(screen.getByLabelText('Назад к ленте')).toBeTruthy();
  });

  it('extends feed chunk without duplicates', async () => {
    wrap(
      <>
        <FeedProbe />
        <Feed />
      </>,
    );
    expect(screen.getByTestId('feed-count').textContent).toBe(String(FEED_INITIAL_DAYS));
    fireEvent.click(screen.getByText('extend-feed'));
    await waitFor(() => {
      expect(screen.getByTestId('feed-count').textContent).toBe(
        String(FEED_INITIAL_DAYS + FEED_CHUNK_DAYS),
      );
    });
    const rows = screen.getAllByRole('button');
    const isos = rows.map((r) => r.getAttribute('data-feed-date')).filter(Boolean);
    expect(new Set(isos).size).toBe(isos.length);
  });

  it('mock mode keeps deterministic today date', () => {
    expect(USE_MOCK_API).toBe(true);
    expect(MOCK_TODAY).toBe('2026-08-28');
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

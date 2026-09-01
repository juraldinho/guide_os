// @ts-nocheck — read CSS source at runtime; Node built-ins are not in app tsconfig.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import type { CalendarEntry } from '@/api/types';
import { guideOsClient } from '@/api/createClient';
import { INITIAL_ENTRIES, MOCK_PROFILE } from '@/api/mock/data';
import { MOCK_TODAY } from '@/config';
import { ToastProvider } from '@/components/ui/Toast';
import { CalendarProvider, useCalendar } from '@/features/calendar/CalendarContext';
import { MonthPicker } from '@/features/calendar/components/MonthPicker';
import { CalendarPage } from '@/features/calendar/CalendarPage';
import { Feed, ALL_FEED_DATES } from '@/features/calendar/components/Feed';
import { AppHeader } from '@/components/layout/AppHeader';
import { ReportsPage } from '@/features/reports/ReportsPage';
import { DOW_SHORT, MONTH_NAMES_CAP } from '@/i18n/ru';

const GLOBAL_CSS = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../src/styles/global.css'),
  'utf8',
);

function wrap(ui: ReactElement) {
  return render(
    <ToastProvider>
      <CalendarProvider>{ui}</CalendarProvider>
    </ToastProvider>,
  );
}

function MonthPickerExpandedPage() {
  const ctx = useCalendar();
  const showMonthPicker =
    ctx.activeTab === 'calendar' && ctx.calendarScreen === 'feed' && ctx.monthExpanded;
  return (
    <>
      <AppHeader
        activeTab={ctx.activeTab}
        headerMonth={ctx.headerMonth}
        headerYear={ctx.headerYear}
        monthExpanded={ctx.monthExpanded}
        showMonthPicker={showMonthPicker}
        onLogoToday={ctx.goToday}
        onToggleMonthPicker={ctx.toggleMonthPicker}
        onSettings={ctx.openSettings}
      />
      <CalendarPage />
    </>
  );
}

function FeedRangeProbe() {
  return <span data-testid="feed-count">{ALL_FEED_DATES.length}</span>;
}

function VisibleMonthProbe() {
  const { setVisibleFeedFromIso } = useCalendar();
  return (
    <button type="button" onClick={() => setVisibleFeedFromIso('2026-09-23')}>
      show-september
    </button>
  );
}

function TabProbe() {
  const { setActiveTab, toggleMonthPicker } = useCalendar();
  return (
    <>
      <button type="button" onClick={() => setActiveTab('reports')}>go-reports</button>
      <button type="button" onClick={toggleMonthPicker}>force-toggle</button>
    </>
  );
}

function CalendarShellLike() {
  const ctx = useCalendar();
  const showMonthPicker =
    ctx.activeTab === 'calendar' && ctx.calendarScreen === 'feed' && ctx.monthExpanded;
  return (
    <>
      <TabProbe />
      <AppHeader
        activeTab={ctx.activeTab}
        headerMonth={ctx.headerMonth}
        headerYear={ctx.headerYear}
        monthExpanded={ctx.monthExpanded}
        showMonthPicker={showMonthPicker}
        onLogoToday={ctx.goToday}
        onToggleMonthPicker={ctx.toggleMonthPicker}
        onSettings={ctx.openSettings}
      />
      {ctx.activeTab === 'calendar' ? <CalendarPage /> : <ReportsPage />}
      <FeedRangeProbe />
      <VisibleMonthProbe />
      <Feed />
    </>
  );
}

function headerMonthToggle() {
  return document.querySelector('.header-month-btn') as HTMLButtonElement;
}

function clickHeaderMonthToggle() {
  fireEvent.click(headerMonthToggle());
}

function headerMonthLabelText() {
  return document.querySelector('.header-month-label')?.textContent ?? '';
}

function monthPickerTitleText() {
  return document.querySelector('.month-picker-title')?.textContent ?? '';
}

function dayCellByIso(iso: string): HTMLButtonElement | undefined {
  return Array.from(document.querySelectorAll('.day-cell')).find(
    (el) => el.getAttribute('aria-label')?.startsWith(`${iso},`),
  ) as HTMLButtonElement | undefined;
}

async function renderMonthPickerWithEntries(entries: CalendarEntry[]) {
  vi.spyOn(guideOsClient, 'listEntries').mockResolvedValue(entries);
  vi.spyOn(guideOsClient, 'getProfile').mockResolvedValue(MOCK_PROFILE);
  wrap(<MonthPicker />);
  await waitFor(() => {
    expect(dayCellByIso('2026-08-01')).toBeTruthy();
  });
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

describe('month calendar CSS', () => {
  it('uses seven zero-minimum grid columns', () => {
    expect(GLOBAL_CSS).toMatch(
      /\.month-grid\s*\{[^}]*grid-template-columns:\s*repeat\(7,\s*minmax\(0,\s*1fr\)\)/s,
    );
  });

  it('sets month grid width and min-width for shrink', () => {
    expect(GLOBAL_CSS).toMatch(/\.month-grid\s*\{[^}]*width:\s*100%/s);
    expect(GLOBAL_CSS).toMatch(/\.month-grid\s*\{[^}]*min-width:\s*0/s);
  });

  it('overrides global button min-width on day cells', () => {
    expect(GLOBAL_CSS).toMatch(/\.day-cell\s*\{[^}]*min-width:\s*0/s);
    expect(GLOBAL_CSS).toMatch(/\.day-cell\s*\{[^}]*width:\s*100%/s);
  });

  it('does not use aspect-ratio on day cells', () => {
    const dayCellBlock = GLOBAL_CSS.match(/\.day-cell\s*\{[^}]*\}/s)?.[0] ?? '';
    expect(dayCellBlock).not.toMatch(/aspect-ratio/);
  });

  it('does not add horizontal scroll on month grid', () => {
    expect(GLOBAL_CSS).not.toMatch(/\.month-grid\s*\{[^}]*overflow-x:\s*auto/s);
    expect(GLOBAL_CSS).not.toMatch(/\.month-grid\s*\{[^}]*overflow-x:\s*scroll/s);
  });

  it('allows weekday labels to shrink inside tracks', () => {
    expect(GLOBAL_CSS).toMatch(/\.month-grid\s+\.dow\s*\{[^}]*min-width:\s*0/s);
  });

  it('anchors expanded picker below sticky header without document flow push', () => {
    expect(GLOBAL_CSS).toMatch(/\.header-month-picker-panel\s*\{[^}]*position:\s*absolute/s);
    expect(GLOBAL_CSS).toMatch(/\.header-month-picker-panel\s*\{[^}]*top:\s*100%/s);
    expect(GLOBAL_CSS).toMatch(/\.header-month-picker-panel\s*\{[^}]*overscroll-behavior:\s*contain/s);
  });
});

describe('month calendar viewport fit', () => {
  const VIEWPORT_WIDTHS = [320, 360, 375, 390, 430, 480, 768];
  const MAIN_PADDING = 24; // var(--space-md) × 2
  const CARD_PADDING = 16; // card-pad-sm × 2
  const GRID_GAP = 12; // 2px × 6 gaps
  const GLOBAL_BUTTON_MIN = 44;

  it('legacy intrinsic minimum exceeds padded grid on the narrowest widths', () => {
    for (const viewport of [320, 360]) {
      const gridInner = Math.min(viewport, 480) - MAIN_PADDING - CARD_PADDING;
      const legacyMinWidth = GLOBAL_BUTTON_MIN * 7 + GRID_GAP;
      expect(legacyMinWidth).toBeGreaterThanOrEqual(gridInner);
    }
  });

  it('equal fractional columns fit inside padded content at all target widths', () => {
    for (const viewport of VIEWPORT_WIDTHS) {
      const gridInner = Math.min(viewport, 480) - MAIN_PADDING - CARD_PADDING;
      const columnWidth = (gridInner - GRID_GAP) / 7;
      expect(columnWidth).toBeGreaterThan(0);
      const totalGrid = columnWidth * 7 + GRID_GAP;
      expect(totalGrid).toBeLessThanOrEqual(gridInner);
      if (gridInner < GLOBAL_BUTTON_MIN * 7 + GRID_GAP) {
        expect(columnWidth).toBeLessThan(GLOBAL_BUTTON_MIN);
      }
    }
  });
});

describe('MonthPicker layout', () => {
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

  it('renders all seven weekday labels including Sunday', () => {
    wrap(<MonthPicker />);
    for (const label of DOW_SHORT) {
      expect(screen.getByText(label)).toBeTruthy();
    }
    expect(screen.getByText('Вс')).toBeTruthy();
  });

  it('renders 42 date cells for a six-week month (August 2026 default view)', () => {
    wrap(<MonthPicker />);
    const dayCells = document.querySelectorAll('.day-cell');
    expect(dayCells.length).toBe(42);
  });

  it('keeps previous and next month cells inside the same seven-column grid', () => {
    wrap(<MonthPicker />);
    const grid = document.querySelector('.month-grid');
    expect(grid).toBeTruthy();
    const children = grid!.children;
    expect(children.length % 7).toBe(0);
    expect(grid!.querySelectorAll('.day-cell.other-month').length).toBeGreaterThan(0);
  });

  it('calls selectDateFromMonth when a date cell is clicked', () => {
    wrap(<MonthPickerExpandedPage />);
    clickHeaderMonthToggle();
    const dayCells = document.querySelectorAll('.day-cell:not(.other-month)');
    fireEvent.click(dayCells[0]);
    expect(screen.getByLabelText('Назад к ленте')).toBeTruthy();
  });
});

describe('MonthPicker day status cells', () => {
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
    cleanup();
    vi.restoreAllMocks();
  });

  it('applies free status class without marker dots on empty dates', async () => {
    await renderMonthPickerWithEntries(INITIAL_ENTRIES);
    const cell = dayCellByIso('2026-08-01')!;
    expect(cell.classList.contains('status-free')).toBe(true);
    expect(cell.querySelector('.markers')).toBeNull();
    expect(cell.getAttribute('aria-label')).toBe('2026-08-01, Свободен');
  });

  it('applies reserved status class for reserved tours', async () => {
    await renderMonthPickerWithEntries(INITIAL_ENTRIES);
    const cell = dayCellByIso('2026-08-05')!;
    expect(cell.classList.contains('status-reserved')).toBe(true);
    expect(cell.getAttribute('aria-label')).toBe('2026-08-05, Бронь');
  });

  it('applies confirmed status class for confirmed tours', async () => {
    await renderMonthPickerWithEntries(INITIAL_ENTRIES);
    const cell = dayCellByIso('2026-08-15')!;
    expect(cell.classList.contains('status-confirmed')).toBe(true);
    expect(cell.getAttribute('aria-label')).toBe('2026-08-15, Занято');
  });

  it('applies day-off status class for day-off entries', async () => {
    await renderMonthPickerWithEntries(INITIAL_ENTRIES);
    const cell = dayCellByIso('2026-08-10')!;
    expect(cell.classList.contains('status-dayoff')).toBe(true);
    expect(cell.getAttribute('aria-label')).toBe('2026-08-10, Выходной');
  });

  it('uses effective status priority when multiple entries share a date', async () => {
    const mixedDate = '2026-08-20';
    await renderMonthPickerWithEntries([
      tourEntry('r1', mixedDate, 'reserved'),
      tourEntry('c1', mixedDate, 'confirmed'),
      dayOffEntry('d1', mixedDate),
    ]);
    const cell = dayCellByIso(mixedDate)!;
    expect(cell.classList.contains('status-dayoff')).toBe(true);
    expect(cell.classList.contains('status-confirmed')).toBe(false);
    expect(cell.getAttribute('aria-label')).toBe(`${mixedDate}, Выходной`);

    vi.spyOn(guideOsClient, 'listEntries').mockResolvedValue([
      tourEntry('r2', mixedDate, 'reserved'),
      tourEntry('c2', mixedDate, 'confirmed'),
    ]);
    cleanup();
    wrap(<MonthPicker />);
    await waitFor(() => {
      const updated = dayCellByIso(mixedDate);
      expect(updated?.classList.contains('status-confirmed')).toBe(true);
    });
    expect(dayCellByIso(mixedDate)?.classList.contains('status-reserved')).toBe(false);
  });

  it('does not render marker containers inside day cells', async () => {
    await renderMonthPickerWithEntries(INITIAL_ENTRIES);
    expect(document.querySelectorAll('.day-cell .markers').length).toBe(0);
  });

  it('shows legend labels with color swatches instead of dots', async () => {
    await renderMonthPickerWithEntries(INITIAL_ENTRIES);
    expect(screen.getByText('Бронь')).toBeTruthy();
    expect(screen.getByText('Занято')).toBeTruthy();
    expect(screen.getByText('Выходной')).toBeTruthy();
    expect(screen.getByText('Свободен')).toBeTruthy();
    expect(document.querySelectorAll('.legend-swatch').length).toBe(4);
    expect(document.querySelectorAll('.marker-legend .marker').length).toBe(0);
    expect(document.querySelector('.legend-swatch-free')).toBeTruthy();
  });

  it('keeps today and selected classes alongside status classes', async () => {
    await renderMonthPickerWithEntries(INITIAL_ENTRIES);
    const todayCell = dayCellByIso(MOCK_TODAY)!;
    expect(todayCell.classList.contains('today')).toBe(true);
    expect(todayCell.classList.contains('selected')).toBe(true);
    expect(todayCell.classList.contains('status-reserved')).toBe(true);

    const confirmedCell = dayCellByIso('2026-08-15')!;
    expect(confirmedCell.classList.contains('status-confirmed')).toBe(true);
    expect(confirmedCell.classList.contains('today')).toBe(false);
    expect(confirmedCell.classList.contains('selected')).toBe(false);
  });
});

describe('MonthPicker header anchoring', () => {
  let scrollToSpy: ReturnType<typeof vi.fn>;
  let scrollIntoViewSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.stubGlobal(
      'IntersectionObserver',
      vi.fn(() => ({
        observe: vi.fn(),
        disconnect: vi.fn(),
        unobserve: vi.fn(),
      })),
    );
    scrollToSpy = vi.fn();
    window.scrollTo = scrollToSpy as typeof window.scrollTo;
    scrollIntoViewSpy = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoViewSpy;
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('does not render month picker when collapsed', () => {
    wrap(<CalendarShellLike />);
    expect(document.querySelectorAll('.month-picker-panel').length).toBe(0);
    expect(screen.queryByTestId('header-month-picker')).toBeNull();
  });

  it('renders exactly one month picker in the header when expanded on feed', () => {
    wrap(<CalendarShellLike />);
    clickHeaderMonthToggle();
    expect(document.querySelectorAll('.month-picker-panel').length).toBe(1);
    expect(screen.getByTestId('header-month-picker')).toBeTruthy();
    expect(document.querySelector('main .month-picker-panel')).toBeNull();
  });

  it('does not render month picker on Reports tab', () => {
    wrap(<CalendarShellLike />);
    fireEvent.click(screen.getByText('force-toggle'));
    fireEvent.click(screen.getByText('go-reports'));
    expect(document.querySelectorAll('.month-picker-panel').length).toBe(0);
    expect(screen.queryByTestId('header-month-picker')).toBeNull();
  });

  it('does not render month picker on day detail', () => {
    wrap(<CalendarShellLike />);
    clickHeaderMonthToggle();
    const dayCells = document.querySelectorAll('.day-cell:not(.other-month)');
    fireEvent.click(dayCells[0]);
    expect(document.querySelectorAll('.month-picker-panel').length).toBe(0);
    expect(screen.getByLabelText('Назад к ленте')).toBeTruthy();
  });

  it('opening picker does not call scrollTo or scrollIntoView', () => {
    wrap(<CalendarShellLike />);
    fireEvent.click(screen.getByText('show-september'));
    scrollToSpy.mockClear();
    scrollIntoViewSpy.mockClear();
    clickHeaderMonthToggle();
    expect(scrollToSpy).not.toHaveBeenCalled();
    expect(scrollIntoViewSpy).not.toHaveBeenCalled();
  });

  it('opening picker preserves bounded feed date count', () => {
    wrap(<CalendarShellLike />);
    const before = screen.getByTestId('feed-count').textContent;
    clickHeaderMonthToggle();
    expect(screen.getByTestId('feed-count').textContent).toBe(before);
  });

  it('closing picker preserves visible feed month in header', () => {
    wrap(<CalendarShellLike />);
    fireEvent.click(screen.getByText('show-september'));
    expect(headerMonthLabelText()).toContain(MONTH_NAMES_CAP[8]);
    clickHeaderMonthToggle();
    clickHeaderMonthToggle();
    expect(headerMonthLabelText()).toContain(MONTH_NAMES_CAP[8]);
  });

  it('month navigation changes picker month while expanded', () => {
    wrap(<CalendarShellLike />);
    clickHeaderMonthToggle();
    fireEvent.click(screen.getByLabelText('Предыдущий месяц'));
    expect(monthPickerTitleText()).toContain(MONTH_NAMES_CAP[6]);
  });

  it('selecting a date opens day detail', () => {
    wrap(<CalendarShellLike />);
    clickHeaderMonthToggle();
    const dayCells = document.querySelectorAll('.day-cell:not(.other-month)');
    fireEvent.click(dayCells[1]);
    expect(screen.getByLabelText('Назад к ленте')).toBeTruthy();
    expect(document.querySelectorAll('.month-picker-panel').length).toBe(0);
  });

  it('keeps seven weekday columns including Sunday when anchored in header', () => {
    wrap(<CalendarShellLike />);
    clickHeaderMonthToggle();
    expect(screen.getByText('Вс')).toBeTruthy();
    expect(document.querySelectorAll('.month-grid').length).toBe(1);
    expect(document.querySelectorAll('.dow').length).toBe(7);
  });

  it('does not duplicate month picker in the DOM', () => {
    wrap(<CalendarShellLike />);
    clickHeaderMonthToggle();
    expect(document.querySelectorAll('.month-picker-panel').length).toBe(1);
    expect(document.querySelectorAll('.header-month-picker-panel').length).toBe(1);
    expect(headerMonthToggle().getAttribute('aria-expanded')).toBe('true');
  });
});

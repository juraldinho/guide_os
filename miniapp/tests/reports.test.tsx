// @ts-nocheck — read CSS source at runtime; Node built-ins are not in app tsconfig.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { ToastProvider } from '@/components/ui/Toast';
import { CalendarProvider } from '@/features/calendar/CalendarContext';
import { ReportsPage } from '@/features/reports/ReportsPage';
import { CommissionReportsSection } from '@/features/reports/CommissionReportsSection';
import {
  getCommissionReportRange,
  getReportRange,
} from '@/features/reports/lib/periods';
import { AppHeader } from '@/components/layout/AppHeader';
import { GlobalOverlays } from '@/app/GlobalOverlays';
import { guideOsClient } from '@/api/createClient';
import { ENTRIES_RANGE_FROM, ENTRIES_RANGE_TO } from '@/config';
import { INITIAL_ENTRIES } from '@/api/mock/data';
import { __resetMockStore } from '@/api/mock/store';
import type { CommissionReportsSummary } from '@/api/types';
import { t } from '@/i18n/strings';

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

function commissionSection() {
  return screen.getByTestId('commission-reports-section');
}

const emptySummary: CommissionReportsSummary = {
  totalCommission: 0,
  recordCount: 0,
  byCompany: [],
  period: { from: '2026-08-01', to: '2026-08-31' },
};

const successSummary: CommissionReportsSummary = {
  totalCommission: 85,
  recordCount: 3,
  byCompany: [
    {
      placeId: 'place_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      companyName: 'Company A',
      totalCommission: 55,
      recordCount: 2,
    },
    {
      placeId: 'place_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
      companyName: 'Company B',
      totalCommission: 30,
      recordCount: 1,
    },
  ],
  period: { from: '2026-08-01', to: '2026-08-31' },
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  __resetMockStore();
});

describe('getCommissionReportRange', () => {
  it('returns the selected calendar month', () => {
    expect(getCommissionReportRange('month', 7, 2026)).toEqual({
      from: '2026-08-01',
      to: '2026-08-31',
    });
  });

  it('returns February end for non-leap year', () => {
    expect(getCommissionReportRange('month', 1, 2025)).toEqual({
      from: '2025-02-01',
      to: '2025-02-28',
    });
  });

  it('returns leap-year February end', () => {
    expect(getCommissionReportRange('month', 1, 2024)).toEqual({
      from: '2024-02-01',
      to: '2024-02-29',
    });
  });

  it('returns full calendar year inclusive', () => {
    expect(getCommissionReportRange('year', 7, 2026)).toEqual({
      from: '2026-01-01',
      to: '2026-12-31',
    });
  });

  it('uses Mini App data horizon for all-period', () => {
    expect(getCommissionReportRange('all', 7, 2026)).toEqual({
      from: ENTRIES_RANGE_FROM,
      to: ENTRIES_RANGE_TO,
    });
  });

  it('all-period commission range does not depend on tour entries', () => {
    const withTours = getCommissionReportRange('all', 0, 2026);
    const tourRange = getReportRange('all', 0, 2026, INITIAL_ENTRIES);
    expect(withTours).toEqual({ from: ENTRIES_RANGE_FROM, to: ENTRIES_RANGE_TO });
    expect(withTours).not.toEqual(tourRange);
  });

  it('preserves existing tour getReportRange month/year/all behavior', () => {
    expect(getReportRange('month', 7, 2026, INITIAL_ENTRIES)).toEqual({
      from: '2026-08-01',
      to: '2026-08-31',
    });
    expect(getReportRange('year', 7, 2026, INITIAL_ENTRIES)).toEqual({
      from: '2026-01-01',
      to: '2026-12-31',
    });
    expect(getReportRange('all', 7, 2026, INITIAL_ENTRIES)).toEqual(
      getReportRange('all', 7, 2026, INITIAL_ENTRIES),
    );
    const all = getReportRange('all', 7, 2026, INITIAL_ENTRIES);
    expect(all.from <= all.to).toBe(true);
    expect(all).not.toEqual({ from: ENTRIES_RANGE_FROM, to: ENTRIES_RANGE_TO });
  });
});

describe('ReportsPage', () => {
  it('renders five summary metric labels', async () => {
    wrap(<ReportsPage />);
    expect(screen.getByText('Туров')).toBeInTheDocument();
    expect(screen.getByText('Рабочих дней')).toBeInTheDocument();
    expect(screen.getByText('Доход ($)')).toBeInTheDocument();
    expect(screen.getByText('Оплаченных туров')).toBeInTheDocument();
    expect(screen.getByText('Неоплаченных туров')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: t.commissionReportsTitle })).toBeTruthy();
    });
  });

  it('does not render duplicate in-content Итоги page heading', async () => {
    wrap(<ReportsPage />);
    expect(document.querySelector('main .page-title')).toBeNull();
    const main = document.querySelector('main.main')!;
    expect(within(main).queryByRole('heading', { name: t.reportsTitle })).toBeNull();
    await waitFor(() => {
      expect(within(main).getByRole('heading', { name: t.commissionReportsTitle })).toBeTruthy();
    });
  });

  it('starts with period controls as first content', () => {
    wrap(<ReportsPage />);
    const main = document.querySelector('main.main');
    expect(main).toBeTruthy();
    const firstChild = main!.firstElementChild;
    expect(firstChild?.classList.contains('filter-row')).toBe(true);
    expect(screen.getByText(t.periodMonth)).toBeTruthy();
    expect(screen.getByText(t.periodYear)).toBeTruthy();
    expect(screen.getByText(t.periodAll)).toBeTruthy();
  });

  it('places commission section between tour summary and share-free-dates', async () => {
    wrap(<ReportsPage />);
    await waitFor(() => {
      expect(screen.getByText(t.commissionReportsTotal)).toBeTruthy();
    });
    const main = document.querySelector('main.main')!;
    const tour = within(main).getByTestId('tour-reports-summary');
    const commissions = within(main).getByTestId('commission-reports-section');
    const share = within(main).getByRole('button', { name: t.shareFreeDates });
    const position = (node: Element) =>
      Array.from(main.children).findIndex((child) => child === node || child.contains(node));
    expect(position(tour)).toBeLessThan(position(commissions));
    expect(position(commissions)).toBeLessThan(position(share));
  });

  it('shows initial commission loading state', () => {
    let resolveSummary!: (value: CommissionReportsSummary) => void;
    vi.spyOn(guideOsClient, 'getCommissionReportsSummary').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveSummary = resolve;
        }),
    );
    wrap(<ReportsPage />);
    expect(within(commissionSection()).getByRole('status')).toHaveTextContent(
      t.commissionReportsLoading,
    );
    expect(within(commissionSection()).queryByText(t.commissionReportsTotal)).toBeNull();
    act(() => {
      resolveSummary(emptySummary);
    });
  });

  it('renders successful commission metrics and company breakdown in server order', async () => {
    vi.spyOn(guideOsClient, 'getCommissionReportsSummary').mockResolvedValue({
      ...successSummary,
      byCompany: [
        {
          placeId: 'place_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
          companyName: 'Same Name',
          totalCommission: 30,
          recordCount: 1,
        },
        {
          placeId: 'place_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
          companyName: 'Same Name',
          totalCommission: 20,
          recordCount: 1,
        },
      ],
    });
    wrap(<ReportsPage />);
    await waitFor(() => {
      expect(screen.getByText(t.commissionReportsTotal)).toBeTruthy();
    });
    const section = commissionSection();
    expect(within(section).getByText('85')).toBeTruthy();
    expect(within(section).getByText('3')).toBeTruthy();
    expect(within(section).getByText(t.commissionReportsByCompany)).toBeTruthy();
    expect(within(section).getByText(t.commissionReportsCompanyTotal(30))).toBeTruthy();
    expect(within(section).getByText(t.commissionReportsCompanyTotal(20))).toBeTruthy();
    const names = within(section)
      .getAllByText('Same Name')
      .map((node) => node.textContent);
    expect(names).toHaveLength(2);
    const listItems = within(section).getAllByRole('listitem');
    expect(listItems[0]).toHaveTextContent('Комиссия: 30');
    expect(listItems[1]).toHaveTextContent('Комиссия: 20');
    expect(section.textContent).not.toContain('place_');
    expect(section.textContent).not.toMatch(/\$|PTS|Баллы/);
  });

  it('shows empty commission state without company breakdown', async () => {
    vi.spyOn(guideOsClient, 'getCommissionReportsSummary').mockResolvedValue(emptySummary);
    wrap(<ReportsPage />);
    await waitFor(() => {
      expect(screen.getByText(t.commissionReportsEmpty)).toBeTruthy();
    });
    expect(screen.queryByText(t.commissionReportsByCompany)).toBeNull();
    const section = commissionSection();
    expect(within(section).getByText(t.commissionReportsTotal)).toBeTruthy();
    expect(within(section).getByText(t.commissionReportsCount)).toBeTruthy();
    const values = within(section)
      .getAllByText('0')
      .map((node) => node.textContent);
    expect(values.length).toBeGreaterThanOrEqual(2);
  });

  it('keeps tour summary and share action when commission load fails', async () => {
    vi.spyOn(guideOsClient, 'getCommissionReportsSummary').mockRejectedValue(new Error('fail'));
    wrap(
      <>
        <ReportsPage />
        <GlobalOverlays />
      </>,
    );
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(t.commissionReportsLoadError);
    });
    expect(screen.getByText('Туров')).toBeTruthy();
    expect(screen.getByRole('button', { name: t.shareFreeDates })).toBeTruthy();
    expect(screen.queryByText('fail')).toBeNull();
  });

  it('retries the same commission range', async () => {
    const spy = vi
      .spyOn(guideOsClient, 'getCommissionReportsSummary')
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValueOnce(successSummary);
    wrap(<ReportsPage />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: t.retry })).toBeTruthy();
    });
    fireEvent.click(screen.getByRole('button', { name: t.retry }));
    await waitFor(() => {
      expect(screen.getByText(t.commissionReportsTotal)).toBeTruthy();
    });
    expect(spy).toHaveBeenCalledTimes(2);
    expect(spy.mock.calls[0]?.[0]).toEqual({ from: '2026-08-01', to: '2026-08-31' });
    expect(spy.mock.calls[1]?.[0]).toEqual({ from: '2026-08-01', to: '2026-08-31' });
  });

  it('sends month, previous/next month, year, previous year, and all-period ranges', async () => {
    const spy = vi
      .spyOn(guideOsClient, 'getCommissionReportsSummary')
      .mockResolvedValue(emptySummary);
    wrap(<ReportsPage />);
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy.mock.calls.at(-1)?.[0]).toEqual({ from: '2026-08-01', to: '2026-08-31' });

    fireEvent.click(screen.getByRole('button', { name: t.prevMonth }));
    await waitFor(() =>
      expect(spy.mock.calls.at(-1)?.[0]).toEqual({ from: '2026-07-01', to: '2026-07-31' }),
    );

    fireEvent.click(screen.getByRole('button', { name: t.nextMonth }));
    await waitFor(() =>
      expect(spy.mock.calls.at(-1)?.[0]).toEqual({ from: '2026-08-01', to: '2026-08-31' }),
    );

    fireEvent.click(screen.getByText(t.periodYear));
    await waitFor(() =>
      expect(spy.mock.calls.at(-1)?.[0]).toEqual({ from: '2026-01-01', to: '2026-12-31' }),
    );

    fireEvent.click(screen.getByRole('button', { name: t.prevYear }));
    await waitFor(() =>
      expect(spy.mock.calls.at(-1)?.[0]).toEqual({ from: '2025-01-01', to: '2025-12-31' }),
    );

    fireEvent.click(screen.getByText(t.periodAll));
    await waitFor(() =>
      expect(spy.mock.calls.at(-1)?.[0]).toEqual({
        from: ENTRIES_RANGE_FROM,
        to: ENTRIES_RANGE_TO,
      }),
    );
  });

  it('does not refetch commissions when tour status or payment filters change', async () => {
    const spy = vi
      .spyOn(guideOsClient, 'getCommissionReportsSummary')
      .mockResolvedValue(successSummary);
    wrap(<ReportsPage />);
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByText(t.statusReserved));
    fireEvent.click(screen.getByText(t.paymentPaid));
    await act(async () => {
      await Promise.resolve();
    });
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('clears stale success when range changes and ignores older resolution', async () => {
    let resolveFirst!: (value: CommissionReportsSummary) => void;
    let resolveSecond!: (value: CommissionReportsSummary) => void;
    const spy = vi.spyOn(guideOsClient, 'getCommissionReportsSummary').mockImplementation(
      (params) =>
        new Promise((resolve) => {
          if (params.from === '2026-08-01') resolveFirst = resolve;
          else resolveSecond = resolve;
        }),
    );
    wrap(<ReportsPage />);
    expect(within(commissionSection()).getByRole('status')).toHaveTextContent(
      t.commissionReportsLoading,
    );

    fireEvent.click(screen.getByRole('button', { name: t.prevMonth }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
    expect(within(commissionSection()).getByRole('status')).toHaveTextContent(
      t.commissionReportsLoading,
    );
    expect(within(commissionSection()).queryByText(t.commissionReportsTotal)).toBeNull();

    await act(async () => {
      resolveFirst({
        ...successSummary,
        totalCommission: 999,
        period: { from: '2026-08-01', to: '2026-08-31' },
      });
    });
    expect(within(commissionSection()).queryByText('999')).toBeNull();

    await act(async () => {
      resolveSecond({
        ...emptySummary,
        totalCommission: 4,
        recordCount: 1,
        byCompany: [
          {
            placeId: 'place_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
            companyName: 'July Co',
            totalCommission: 4,
            recordCount: 1,
          },
        ],
        period: { from: '2026-07-01', to: '2026-07-31' },
      });
    });
    await waitFor(() => {
      expect(screen.getByText('July Co')).toBeTruthy();
      expect(within(commissionSection()).getByText('4')).toBeTruthy();
    });
    expect(within(commissionSection()).queryByText('999')).toBeNull();
  });

  it('ignores rejected older-range request after newer success', async () => {
    let rejectFirst!: (reason?: unknown) => void;
    let resolveSecond!: (value: CommissionReportsSummary) => void;
    vi.spyOn(guideOsClient, 'getCommissionReportsSummary').mockImplementation((params) => {
      if (params.from === '2026-08-01') {
        return new Promise((_, reject) => {
          rejectFirst = reject;
        });
      }
      return new Promise((resolve) => {
        resolveSecond = resolve;
      });
    });
    wrap(<ReportsPage />);
    fireEvent.click(screen.getByRole('button', { name: t.prevMonth }));
    await act(async () => {
      resolveSecond({
        ...successSummary,
        totalCommission: 12,
        recordCount: 1,
        byCompany: [
          {
            placeId: 'place_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
            companyName: 'Kept',
            totalCommission: 12,
            recordCount: 1,
          },
        ],
        period: { from: '2026-07-01', to: '2026-07-31' },
      });
    });
    await waitFor(() => expect(screen.getByText('Kept')).toBeTruthy());
    await act(async () => {
      rejectFirst(new Error('stale'));
    });
    expect(screen.getByText('Kept')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('ignores late completion after unmount', async () => {
    let resolveLate!: (value: CommissionReportsSummary) => void;
    vi.spyOn(guideOsClient, 'getCommissionReportsSummary').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveLate = resolve;
        }),
    );
    const view = wrap(<ReportsPage />);
    view.unmount();
    await act(async () => {
      resolveLate(successSummary);
    });
    expect(screen.queryByText(t.commissionReportsTotal)).toBeNull();
  });

  it('renders calculated mock summary in default mock mode', async () => {
    wrap(<ReportsPage />);
    await waitFor(() => {
      expect(within(commissionSection()).getByText(t.commissionReportsTotal)).toBeTruthy();
    });
    const section = commissionSection();
    expect(within(section).getByText('80')).toBeTruthy();
    expect(within(section).getByText('3')).toBeTruthy();
    expect(within(section).getByText('Бухара Арт')).toBeTruthy();
    expect(within(section).getByText('Restaurant Platan')).toBeTruthy();
  });

  it('keeps accessible heading, loading, error, and list semantics', async () => {
    vi.spyOn(guideOsClient, 'getCommissionReportsSummary')
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValueOnce(successSummary);
    wrap(<ReportsPage />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByRole('heading', { name: t.commissionReportsTitle })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: t.retry }));
    await waitFor(() => expect(screen.getByRole('list')).toBeTruthy());
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });

  it('renders share free dates button and it is clickable', async () => {
    wrap(
      <>
        <ReportsPage />
        <GlobalOverlays />
      </>,
    );
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: t.commissionReportsTitle })).toBeTruthy();
    });
    const button = screen.getByRole('button', { name: t.shareFreeDates });
    expect(button).toBeTruthy();
    fireEvent.click(button);
    expect(screen.getByText(t.freeDatesTitle)).toBeTruthy();
  });
});

describe('Reports sticky header', () => {
  it('still shows Итоги in the sticky header on reports tab', () => {
    wrap(
      <AppHeader
        activeTab="reports"
        headerMonth={7}
        headerYear={2026}
        monthExpanded={false}
        showMonthPicker={false}
        onLogoToday={() => undefined}
        onToggleMonthPicker={() => undefined}
        onSettings={() => undefined}
      />,
    );
    expect(screen.getByText(t.reportsTitle)).toBeTruthy();
    expect(document.querySelector('.header-title-static')).toBeTruthy();
  });
});

describe('CommissionReportsSection isolated', () => {
  it('requests only the provided range', async () => {
    const spy = vi
      .spyOn(guideOsClient, 'getCommissionReportsSummary')
      .mockResolvedValue(emptySummary);
    render(
      <CommissionReportsSection range={{ from: '2025-03-01', to: '2025-03-31' }} />,
    );
    await waitFor(() => expect(spy).toHaveBeenCalledWith({ from: '2025-03-01', to: '2025-03-31' }));
  });
});

describe('main bottom safe clearance CSS', () => {
  it('defines shared bottom-nav offset on app shell', () => {
    expect(GLOBAL_CSS).toMatch(/\.app-shell\s*\{[^}]*--bottom-nav-offset:\s*80px/s);
  });

  it('includes bottom-nav offset, safe-area, and content spacing on main', () => {
    expect(GLOBAL_CSS).toMatch(
      /\.main\s*\{[^}]*padding-bottom:\s*calc\(var\(--bottom-nav-offset\)\s*\+\s*var\(--safe-bottom\)\s*\+\s*var\(--space-md\)\)/s,
    );
  });

  it('uses longhand padding on main base rule', () => {
    const mainBlock = GLOBAL_CSS.match(/\.main\s*\{[^}]*\}/s)?.[0] ?? '';
    expect(mainBlock).toMatch(/padding-inline:/);
    expect(mainBlock).toMatch(/padding-top:/);
    expect(mainBlock).not.toMatch(/^\s*padding:\s/);
  });

  it('wide breakpoint does not reset main bottom padding with shorthand', () => {
    const wideBlock = GLOBAL_CSS.match(
      /@media\s*\(min-width:\s*400px\)\s*\{[^}]*\.main\s*\{[^}]*\}/s,
    )?.[0] ?? '';
    expect(wideBlock).toMatch(/padding-inline:/);
    expect(wideBlock).toMatch(/padding-top:/);
    expect(wideBlock).not.toMatch(/\.main\s*\{[^}]*padding:\s*var\(--space-lg\)/s);
    expect(GLOBAL_CSS).toMatch(
      /\.main\s*\{[^}]*padding-bottom:\s*calc\(var\(--bottom-nav-offset\)/s,
    );
  });

  it('narrow breakpoint does not reset main bottom padding with shorthand', () => {
    const narrowBlock = GLOBAL_CSS.match(
      /@media\s*\(max-width:\s*360px\)\s*\{[\s\S]*?\.main\s*\{[^}]*\}/s,
    )?.[0] ?? '';
    expect(narrowBlock).toMatch(/padding-inline:\s*10px/);
    expect(narrowBlock).toMatch(/padding-top:\s*10px/);
    expect(narrowBlock).not.toMatch(/\.main\s*\{[^}]*padding:\s*10px/s);
  });

  it('does not add button-specific spacer or margin workaround for share action', () => {
    expect(GLOBAL_CSS).not.toMatch(/share-free-dates/);
    expect(GLOBAL_CSS).not.toMatch(/btn-block\s*\{[^}]*margin-bottom:\s*120px/s);
  });

  it('preserves calendar main side and top padding tokens', () => {
    expect(GLOBAL_CSS).toMatch(/\.main\s*\{[^}]*padding-inline:\s*var\(--space-md\)/s);
    expect(GLOBAL_CSS).toMatch(/\.main\s*\{[^}]*padding-top:\s*var\(--space-md\)/s);
  });
});

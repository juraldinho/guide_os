// @ts-nocheck — read CSS source at runtime; Node built-ins are not in app tsconfig.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReactElement } from 'react';
import { ToastProvider } from '@/components/ui/Toast';
import { CalendarProvider } from '@/features/calendar/CalendarContext';
import { ReportsPage } from '@/features/reports/ReportsPage';
import { AppHeader } from '@/components/layout/AppHeader';
import { GlobalOverlays } from '@/app/GlobalOverlays';
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

describe('ReportsPage', () => {
  it('renders five summary metric labels', () => {
    wrap(<ReportsPage />);
    expect(screen.getByText('Туров')).toBeInTheDocument();
    expect(screen.getByText('Рабочих дней')).toBeInTheDocument();
    expect(screen.getByText('Доход ($)')).toBeInTheDocument();
    expect(screen.getByText('Оплаченных туров')).toBeInTheDocument();
    expect(screen.getByText('Неоплаченных туров')).toBeInTheDocument();
  });

  it('does not render duplicate in-content Итоги page heading', () => {
    wrap(<ReportsPage />);
    expect(document.querySelector('main .page-title')).toBeNull();
    expect(document.querySelectorAll('main h2').length).toBe(0);
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

  it('renders share free dates button and it is clickable', () => {
    wrap(
      <>
        <ReportsPage />
        <GlobalOverlays />
      </>,
    );
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

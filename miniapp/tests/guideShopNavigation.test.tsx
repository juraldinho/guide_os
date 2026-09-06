// @ts-nocheck — read CSS source at runtime; Node built-ins are not in app tsconfig.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AppHeader } from '@/components/layout/AppHeader';
import { BottomNav } from '@/components/layout/BottomNav';
import { GuideShopPage } from '@/features/guideshop/GuideShopPage';
import { t } from '@/i18n/strings';

const GLOBAL_CSS = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../src/styles/global.css'),
  'utf8',
);

describe('GuideShop navigation foundation', () => {
  it('renders tabs in the canonical order', () => {
    render(<BottomNav activeTab="calendar" onTabChange={() => undefined} />);
    expect(screen.getAllByRole('button').map((button) => button.textContent)).toEqual([
      t.calendar,
      t.reports,
      t.guideShop,
      t.guideOperator,
    ]);
  });

  it('changes to GuideShop when its button is clicked', () => {
    const onTabChange = vi.fn();
    render(<BottomNav activeTab="calendar" onTabChange={onTabChange} />);
    fireEvent.click(screen.getByRole('button', { name: t.guideShop }));
    expect(onTabChange).toHaveBeenCalledWith('guideshop');
  });

  it('changes to Guide Operator when its button is clicked', () => {
    const onTabChange = vi.fn();
    render(<BottomNav activeTab="calendar" onTabChange={onTabChange} />);
    fireEvent.click(screen.getByRole('button', { name: t.guideOperator }));
    expect(onTabChange).toHaveBeenCalledWith('guide_operator');
  });

  it('marks only the active tab as the current page', () => {
    render(<BottomNav activeTab="guideshop" onTabChange={() => undefined} />);
    expect(screen.getByRole('button', { name: t.guideShop })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('button', { name: t.calendar })).not.toHaveAttribute(
      'aria-current',
    );
  });

  it('scrolls the active tab into the visible nav area', () => {
    const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView');
    const { rerender } = render(
      <BottomNav activeTab="calendar" onTabChange={() => undefined} />,
    );
    rerender(<BottomNav activeTab="guideshop" onTabChange={() => undefined} />);
    expect(scrollIntoView).toHaveBeenLastCalledWith({
      behavior: 'smooth',
      block: 'nearest',
      inline: 'nearest',
    });
    scrollIntoView.mockRestore();
  });

  it('shows GuideShop as the static sticky-header title', () => {
    render(
      <AppHeader
        activeTab="guideshop"
        headerMonth={8}
        headerYear={2026}
        monthExpanded={false}
        showMonthPicker={false}
        onLogoToday={() => undefined}
        onToggleMonthPicker={() => undefined}
        onSettings={() => undefined}
      />,
    );
    expect(screen.getByText(t.guideShop)).toHaveClass('header-title-static');
    expect(screen.queryByRole('button', { name: /2026/ })).toBeNull();
  });

  it('renders separate official and personal placeholder sections', () => {
    render(<GuideShopPage />);
    expect(screen.getByRole('heading', { name: t.guideShopOfficial })).toBeTruthy();
    expect(screen.getByRole('heading', { name: t.guideShopPersonal })).toBeTruthy();
  });
});

describe('scalable bottom navigation CSS', () => {
  it('scrolls only the internal track horizontally', () => {
    expect(GLOBAL_CSS).toMatch(
      /\.bottom-nav-track\s*\{[^}]*overflow-x:\s*auto[^}]*scroll-snap-type:\s*x mandatory/s,
    );
    const navRule = GLOBAL_CSS.match(/\.bottom-nav\s*\{[^}]*\}/s)?.[0] ?? '';
    expect(navRule).not.toMatch(/overflow-x:/);
  });

  it('keeps items scalable with a stable minimum width and snap alignment', () => {
    expect(GLOBAL_CSS).toMatch(/\.nav-item\s*\{[^}]*flex:\s*1 0 112px/s);
    expect(GLOBAL_CSS).toMatch(/\.nav-item\s*\{[^}]*scroll-snap-align:\s*nearest/s);
    expect(GLOBAL_CSS).toMatch(/\.nav-item\s*\{[^}]*min-height:\s*56px/s);
  });

  it('keeps the fixed navigation safe-area padding', () => {
    expect(GLOBAL_CSS).toMatch(
      /\.bottom-nav\s*\{[^}]*padding-bottom:\s*var\(--safe-bottom\)/s,
    );
  });
});

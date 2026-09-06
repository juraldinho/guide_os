import type { TabId } from '@/api/types';
import { t } from '@/i18n/strings';
import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { IconCalendar, IconGuideShop, IconReports } from '@/components/ui/Icons';

interface BottomNavProps {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
}

function IconGuideOperator() {
  return (
    <svg
      className="nav-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <path d="M12 3l8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V7l8-4Z" />
      <path d="M9.5 12.5l1.8 1.8 3.7-3.8" />
    </svg>
  );
}

export function BottomNav({ activeTab, onTabChange }: BottomNavProps) {
  const activeItemRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    activeItemRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest',
      inline: 'nearest',
    });
  }, [activeTab]);

  const tabButton = (
    tab: TabId,
    label: string,
    icon: ReactNode,
  ) => {
    const active = activeTab === tab;
    return (
      <button
        key={tab}
        ref={active ? activeItemRef : null}
        type="button"
        className={`nav-item${active ? ' active' : ''}`}
        onClick={() => onTabChange(tab)}
        aria-current={active ? 'page' : undefined}
      >
        {icon}
        <span>{label}</span>
      </button>
    );
  };

  return (
    <nav className="bottom-nav" aria-label="Основная навигация">
      <div className="bottom-nav-track">
        {tabButton('calendar', t.calendar, <IconCalendar />)}
        {tabButton('reports', t.reports, <IconReports />)}
        {tabButton('guideshop', t.guideShop, <IconGuideShop />)}
        {tabButton('guide_operator', t.guideOperator, <IconGuideOperator />)}
      </div>
    </nav>
  );
}

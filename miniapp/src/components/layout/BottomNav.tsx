import type { TabId } from '@/api/types';
import { t } from '@/i18n/strings';
import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { IconCalendar, IconGuideShop, IconReports } from '@/components/ui/Icons';

interface BottomNavProps {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
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
      </div>
    </nav>
  );
}

import type { TabId } from '@/api/types';
import { t } from '@/i18n/strings';
import { IconCalendar, IconReports } from '@/components/ui/Icons';

interface BottomNavProps {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
}

export function BottomNav({ activeTab, onTabChange }: BottomNavProps) {
  return (
    <nav className="bottom-nav" aria-label="Основная навигация">
      <button
        type="button"
        className={`nav-item${activeTab === 'calendar' ? ' active' : ''}`}
        onClick={() => onTabChange('calendar')}
      >
        <IconCalendar />
        {t.calendar}
      </button>
      <button
        type="button"
        className={`nav-item${activeTab === 'reports' ? ' active' : ''}`}
        onClick={() => onTabChange('reports')}
      >
        <IconReports />
        {t.reports}
      </button>
    </nav>
  );
}

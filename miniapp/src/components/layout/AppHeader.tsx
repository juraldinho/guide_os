import { MonthPicker } from '@/features/calendar/components/MonthPicker';
import { MONTH_NAMES_CAP } from '@/i18n/ru';
import { t } from '@/i18n/strings';
import { IconChevronDown, IconChevronUp, IconSettings } from '@/components/ui/Icons';

interface AppHeaderProps {
  activeTab: 'calendar' | 'reports';
  headerMonth: number;
  headerYear: number;
  monthExpanded: boolean;
  showMonthPicker: boolean;
  onLogoToday: () => void;
  onToggleMonthPicker: () => void;
  onSettings: () => void;
}

export function AppHeader({
  activeTab,
  headerMonth,
  headerYear,
  monthExpanded,
  showMonthPicker,
  onLogoToday,
  onToggleMonthPicker,
  onSettings,
}: AppHeaderProps) {
  const chevron = monthExpanded ? <IconChevronUp /> : <IconChevronDown />;

  return (
    <header className="header">
      <div className="header-grid">
        <button
          type="button"
          className="header-logo-btn"
          onClick={onLogoToday}
          aria-label={t.today}
        >
          <img src="/assets/logo.svg" alt="" className="logo-mark" />
        </button>

        <div className="header-center">
          {activeTab === 'calendar' ? (
            <button
              type="button"
              className="header-month-btn"
              onClick={onToggleMonthPicker}
              aria-expanded={monthExpanded}
            >
              <span className="header-month-label">
                {MONTH_NAMES_CAP[headerMonth]} {headerYear}
              </span>
              <span className="month-chevron">{chevron}</span>
            </button>
          ) : (
            <span className="header-title-static">{t.reportsTitle}</span>
          )}
        </div>

        <button
          type="button"
          className="header-settings-btn icon-btn"
          onClick={onSettings}
          title={t.settings}
          aria-label={t.settings}
        >
          <IconSettings />
        </button>
      </div>
      {showMonthPicker ? (
        <div className="header-month-picker-panel" data-testid="header-month-picker">
          <MonthPicker />
        </div>
      ) : null}
    </header>
  );
}

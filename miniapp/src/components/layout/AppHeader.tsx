import { t } from '@/i18n/strings';
import { IconToday, IconSettings } from '@/components/ui/Icons';

interface AppHeaderProps {
  onToday: () => void;
  onSettings: () => void;
}

export function AppHeader({ onToday, onSettings }: AppHeaderProps) {
  return (
    <header className="header">
      <div className="header-row">
        <div className="logo-wrap">
          <img src="/assets/logo.svg" alt={t.appName} className="logo-mark" />
        </div>
        <div className="header-actions">
          <button type="button" className="icon-btn" onClick={onToday} title={t.today} aria-label={t.today}>
            <IconToday />
          </button>
          <button type="button" className="icon-btn" onClick={onSettings} title={t.settings} aria-label={t.settings}>
            <IconSettings />
          </button>
        </div>
      </div>
    </header>
  );
}

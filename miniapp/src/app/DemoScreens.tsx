import { IconError, IconOffline } from '@/components/ui/Icons';
import { t } from '@/i18n/strings';
import { useCalendar } from '@/features/calendar/CalendarContext';

export function DemoLoadingScreen() {
  return (
    <div className="loading-screen">
      <div className="spinner" aria-hidden="true" />
      <p>{t.demoLoadingMessage}</p>
    </div>
  );
}

export function DemoErrorScreen() {
  const { retryDemo } = useCalendar();
  return (
    <div className="state-screen" style={{ paddingTop: 48 }}>
      <IconError />
      <h2>{t.demoErrorTitle}</h2>
      <p className="text-muted">{t.demoErrorMessage}</p>
      <button type="button" className="btn btn-primary" onClick={retryDemo}>
        {t.retry}
      </button>
    </div>
  );
}

export function DemoOfflineScreen() {
  const { retryDemo } = useCalendar();
  return (
    <div className="offline-screen">
      <div className="state-screen">
        <IconOffline />
        <h2>{t.demoOfflineTitle}</h2>
        <p>{t.demoOfflineMessage}</p>
        <button type="button" className="btn btn-primary" onClick={retryDemo}>
          {t.retry}
        </button>
      </div>
    </div>
  );
}

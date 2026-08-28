import { OverlaySheet } from '@/components/ui/OverlaySheet';
import { t } from '@/i18n/strings';
import { useCalendar } from '@/features/calendar/CalendarContext';

export function DemoStatesOverlay() {
  const { closeOverlay, showDemoLoading, showDemoError, showDemoOffline } = useCalendar();

  return (
    <OverlaySheet title={t.demoStatesTitle} onClose={closeOverlay}>
      <button type="button" className="btn btn-secondary btn-block" onClick={showDemoLoading}>
        {t.demoLoading}
      </button>
      <button
        type="button"
        className="btn btn-secondary btn-block"
        style={{ marginTop: 8 }}
        onClick={showDemoError}
      >
        {t.demoError}
      </button>
      <button
        type="button"
        className="btn btn-secondary btn-block"
        style={{ marginTop: 8 }}
        onClick={showDemoOffline}
      >
        {t.demoOffline}
      </button>
      <button
        type="button"
        className="btn btn-secondary btn-block"
        style={{ marginTop: 8 }}
        onClick={closeOverlay}
      >
        {t.close}
      </button>
    </OverlaySheet>
  );
}

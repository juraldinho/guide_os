import { useCalendar } from '@/features/calendar/CalendarContext';
import { FreeDatesOverlay } from '@/features/reports/FreeDatesOverlay';
import { DemoStatesOverlay } from '@/features/settings/DemoStatesOverlay';
import { SettingsOverlay } from '@/features/settings/SettingsOverlay';

export function GlobalOverlays() {
  const { settingsOpen, overlay, freeDatesSession } = useCalendar();

  if (settingsOpen) return <SettingsOverlay />;
  if (overlay === 'free-dates') return <FreeDatesOverlay key={freeDatesSession} />;
  if (overlay === 'demo-states') return <DemoStatesOverlay />;
  return null;
}

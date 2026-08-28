import { ToastProvider } from '@/components/ui/Toast';
import { CalendarProvider } from '@/features/calendar/CalendarContext';
import { applyThemeMode, loadStoredTheme } from '@/telegram/mockAdapter';
import { AppShell } from './AppShell';

applyThemeMode(loadStoredTheme());

export function AppProviders() {
  return (
    <ToastProvider>
      <CalendarProvider>
        <AppShell />
      </CalendarProvider>
    </ToastProvider>
  );
}

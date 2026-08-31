import { useEffect } from 'react';
import { ToastProvider } from '@/components/ui/Toast';
import { CalendarProvider } from '@/features/calendar/CalendarContext';
import { applyThemeMode, loadStoredTheme } from '@/telegram/mockAdapter';
import { initializeTelegramWebApp } from '@/telegram/webApp';
import { AppShell } from './AppShell';

applyThemeMode(loadStoredTheme());

export function AppProviders() {
  useEffect(() => {
    initializeTelegramWebApp();
  }, []);

  return (
    <ToastProvider>
      <CalendarProvider>
        <AppShell />
      </CalendarProvider>
    </ToastProvider>
  );
}

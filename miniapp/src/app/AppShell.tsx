import { BottomNav } from '@/components/layout/BottomNav';
import { AppHeader } from '@/components/layout/AppHeader';
import { CalendarPage } from '@/features/calendar/CalendarPage';
import { useCalendar } from '@/features/calendar/CalendarContext';
import { ReportsPage } from '@/features/reports/ReportsPage';
import { GlobalOverlays } from './GlobalOverlays';
import { DemoErrorScreen, DemoLoadingScreen, DemoOfflineScreen } from './DemoScreens';

export function AppShell() {
  const { activeTab, setActiveTab, goToday, openSettings, demoLoading, demoError, demoOffline } =
    useCalendar();

  if (demoLoading) return <DemoLoadingScreen />;
  if (demoOffline) return <DemoOfflineScreen />;
  if (demoError) return <DemoErrorScreen />;

  return (
    <>
      <div className="app-shell">
        <AppHeader onToday={goToday} onSettings={openSettings} />
        {activeTab === 'calendar' ? <CalendarPage /> : <ReportsPage />}
        <BottomNav activeTab={activeTab} onTabChange={setActiveTab} />
      </div>
      <GlobalOverlays />
    </>
  );
}

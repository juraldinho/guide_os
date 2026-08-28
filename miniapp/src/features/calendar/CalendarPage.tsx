import { useCalendar } from './CalendarContext';
import { CalendarChrome } from './components/CalendarChrome';
import { CalendarOverlays } from './components/CalendarOverlays';
import { DayDetail } from './components/DayDetail';
import { Feed } from './components/Feed';
import { MonthPicker } from './components/MonthPicker';

export function CalendarPage() {
  const { calendarScreen, monthExpanded } = useCalendar();

  if (calendarScreen === 'day') {
    return (
      <>
        <DayDetail />
        <CalendarOverlays />
      </>
    );
  }

  return (
    <>
      <main className="main">
        <CalendarChrome />
        {monthExpanded && <MonthPicker />}
        <Feed />
      </main>
      <CalendarOverlays />
    </>
  );
}

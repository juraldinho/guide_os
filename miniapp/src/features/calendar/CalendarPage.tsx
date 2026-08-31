import { useCalendar } from './CalendarContext';
import { CalendarOverlays } from './components/CalendarOverlays';
import { DayDetail } from './components/DayDetail';
import { Feed } from './components/Feed';

export function CalendarPage() {
  const { calendarScreen } = useCalendar();

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
        <Feed />
      </main>
      <CalendarOverlays />
    </>
  );
}

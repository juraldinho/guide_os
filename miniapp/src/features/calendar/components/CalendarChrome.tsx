import { MONTH_NAMES_CAP } from '@/i18n/ru';
import { IconChevronDown, IconChevronUp } from '@/components/ui/Icons';
import { useCalendar } from '../CalendarContext';

export function CalendarChrome() {
  const { monthExpanded, viewMonth, viewYear, toggleMonthPicker } = useCalendar();
  const chevron = monthExpanded ? <IconChevronUp /> : <IconChevronDown />;

  return (
    <div className="calendar-period-row">
      <button
        type="button"
        className="month-header-btn"
        onClick={toggleMonthPicker}
        aria-expanded={monthExpanded}
      >
        {MONTH_NAMES_CAP[viewMonth]} {viewYear}
        {chevron}
      </button>
    </div>
  );
}

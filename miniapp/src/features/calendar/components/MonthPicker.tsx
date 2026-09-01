import { MOCK_TODAY } from '@/config';
import { MONTH_NAMES_CAP, DOW_SHORT } from '@/i18n/ru';
import { t } from '@/i18n/strings';
import { dayStatus } from '@/features/calendar/lib/dayStatus';
import { useCalendar } from '@/features/calendar/CalendarContext';
import { IconChevronLeft, IconChevronRight } from '@/components/ui/Icons';
import type { DayStatusKind } from '@/api/types';

const STATUS_LABEL: Record<DayStatusKind, string> = {
  free: t.markerFree,
  reserved: t.markerReserved,
  confirmed: t.markerConfirmed,
  dayoff: t.markerDayOff,
};

export function MonthPicker() {
  const {
    entries,
    viewMonth,
    viewYear,
    selectedDate,
    prevMonth,
    nextMonth,
    selectDateFromMonth,
  } = useCalendar();

  const first = new Date(viewYear, viewMonth, 1);
  let startDow = first.getDay();
  startDow = startDow === 0 ? 6 : startDow - 1;
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const prevDays = new Date(viewYear, viewMonth, 0).getDate();

  const cells: { num: number; iso: string; other: boolean }[] = [];

  for (let i = 0; i < startDow; i++) {
    const day = prevDays - startDow + i + 1;
    const m = viewMonth === 0 ? 11 : viewMonth - 1;
    const y = viewMonth === 0 ? viewYear - 1 : viewYear;
    const iso = `${y}-${String(m + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    cells.push({ num: day, iso, other: true });
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const iso = `${viewYear}-${String(viewMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    cells.push({ num: d, iso, other: false });
  }

  const total = startDow + daysInMonth;
  const rem = total % 7 === 0 ? 0 : 7 - (total % 7);
  for (let i = 1; i <= rem; i++) {
    const m = viewMonth === 11 ? 0 : viewMonth + 1;
    const y = viewMonth === 11 ? viewYear + 1 : viewYear;
    const iso = `${y}-${String(m + 1).padStart(2, '0')}-${String(i).padStart(2, '0')}`;
    cells.push({ num: i, iso, other: true });
  }

  return (
    <div className="month-picker-panel">
      <div className="month-picker-nav">
        <button type="button" className="icon-btn" onClick={prevMonth} aria-label={t.prevMonth}>
          <IconChevronLeft />
        </button>
        <span className="month-picker-title">{MONTH_NAMES_CAP[viewMonth]} {viewYear}</span>
        <button type="button" className="icon-btn" onClick={nextMonth} aria-label={t.nextMonth}>
          <IconChevronRight />
        </button>
      </div>
      <div className="marker-legend" aria-hidden="true">
        <span><span className="legend-swatch legend-swatch-reserved" /> {t.markerReserved}</span>
        <span><span className="legend-swatch legend-swatch-confirmed" /> {t.markerConfirmed}</span>
        <span><span className="legend-swatch legend-swatch-dayoff" /> {t.markerDayOff}</span>
        <span><span className="legend-swatch legend-swatch-free" /> {t.markerFree}</span>
      </div>
      <div className="card card-pad-sm">
        <div className="month-grid">
          {DOW_SHORT.map((d) => (
            <div key={d} className="dow">{d}</div>
          ))}
          {cells.map((cell) => {
            const today = cell.iso === MOCK_TODAY;
            const sel = cell.iso === selectedDate;
            const status = dayStatus(cell.iso, entries);
            return (
              <button
                key={cell.iso}
                type="button"
                className={`day-cell status-${status}${today ? ' today' : ''}${sel ? ' selected' : ''}${cell.other ? ' other-month' : ''}`}
                onClick={() => selectDateFromMonth(cell.iso)}
                aria-label={`${cell.iso}, ${STATUS_LABEL[status]}`}
              >
                <span>{cell.num}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

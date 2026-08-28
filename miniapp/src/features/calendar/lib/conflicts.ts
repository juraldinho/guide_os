import type { CalendarEntry, ConflictResult } from '@/api/types';
import { t } from '@/i18n/strings';
import { dateInEntry, daysInRange } from './dates';
function isFullDayEntry(entry: Partial<CalendarEntry>): boolean {
  return entry.type === 'day_off' || !entry.startTime || !entry.endTime;
}

function timesOverlap(
  aStart: string,
  aEnd: string,
  bStart: string,
  bEnd: string,
  aFull: boolean,
  bFull: boolean,
): boolean {
  if (aFull || bFull) return true;
  return aStart < bEnd && bStart < aEnd;
}

export function checkConflicts(
  entry: Partial<CalendarEntry>,
  entries: CalendarEntry[],
  excludeId?: string,
): ConflictResult {
  if (!entry.startDate || !entry.endDate) return null;

  const dates = daysInRange(entry.startDate, entry.endDate);
  let warning: ConflictResult = null;

  for (const date of dates) {
    for (const ex of entries) {
      if (ex.id === excludeId) continue;
      if (!dateInEntry(date, ex)) continue;

      if (ex.type === 'day_off') {
        return {
          block: true,
          date,
          ex,
          reason: t.conflictDayOff,
        };
      }

      const entryFull = isFullDayEntry(entry);
      const exFull = isFullDayEntry(ex);
      const overlap = timesOverlap(
        entry.startTime || '00:00',
        entry.endTime || '24:00',
        ex.startTime || '00:00',
        ex.endTime || '24:00',
        entryFull,
        exFull,
      );

      if (overlap) {
        const timeLabel = exFull ? t.allDay : `${ex.startTime}–${ex.endTime}`;
        return {
          block: true,
          date,
          ex,
          entry,
          reason: t.conflictTimeOverlap(ex.title, timeLabel),
        };
      }

      if (!warning) warning = { warn: true, date, ex };
    }
  }

  return warning;
}

export function entryFromTourForm(
  form: import('@/api/types').TourFormValues,
): Omit<CalendarEntry, 'id'> {
  return {
    type: 'tour',
    title: form.title.trim(),
    company: form.company,
    location: form.location,
    startDate: form.startDate,
    endDate: form.endDate || form.startDate,
    startTime: form.useTime ? form.startTime : null,
    endTime: form.useTime ? form.endTime : null,
    status: form.status,
    payment: form.payment,
    income: form.income,
    note: form.note,
    source: 'Mini App',
  };
}

import type { CalendarEntry } from '@/api/types';
import { MONTH_NAMES, MONTH_NAMES_CAP, MONTH_NAMES_IN } from '@/i18n/ru';
import { dayStatus } from '@/features/calendar/lib/dayStatus';
import {
  daysInRange,
  fmtDate,
  fmtDateShort,
  parseDate,
  toISO,
} from '@/features/calendar/lib/dates';
import type { AvailOpenFrom, ReportsPeriod } from './types';
import { getAvailContextRange } from './periods';

function isFullCalendarMonth(from: string, to: string): boolean {
  const start = parseDate(from);
  const end = parseDate(to);
  const lastDay = new Date(end.getFullYear(), end.getMonth() + 1, 0).getDate();
  return (
    start.getDate() === 1 &&
    end.getDate() === lastDay &&
    start.getMonth() === end.getMonth() &&
    start.getFullYear() === end.getFullYear()
  );
}

export function buildFreeDatesHeading(from: string, to: string): string {
  if (isFullCalendarMonth(from, to)) {
    return `Свободные даты в ${MONTH_NAMES_IN[parseDate(from).getMonth()]}:`;
  }
  return `Свободные даты с ${fmtDate(from)} по ${fmtDate(to)}:`;
}

function compressRanges(dates: string[]): { start: string; end: string }[] {
  if (!dates.length) return [];
  const sorted = [...dates].sort();
  const out: { start: string; end: string }[] = [];
  let start = sorted[0];
  let end = sorted[0];
  for (let i = 1; i < sorted.length; i++) {
    const prev = parseDate(end);
    const next = new Date(prev.getFullYear(), prev.getMonth(), prev.getDate() + 1);
    if (toISO(next) === sorted[i]) end = sorted[i];
    else {
      out.push({ start, end });
      start = sorted[i];
      end = sorted[i];
    }
  }
  out.push({ start, end });
  return out;
}

export function buildFreeDatesText(
  entries: CalendarEntry[],
  availOpenFrom: AvailOpenFrom,
  avail: { useCustom: boolean; customFrom: string; customTo: string },
  calendarCtx: {
    calendarScreen: 'feed' | 'day';
    selectedDate: string;
    viewMonth: number;
    viewYear: number;
  },
  reports: { period: ReportsPeriod; month: number; year: number },
): string {
  const { from, to } = getAvailContextRange(
    availOpenFrom,
    avail,
    calendarCtx,
    reports,
    entries,
  );
  const free = daysInRange(from, to).filter((d) => dayStatus(d, entries) === 'free');
  if (!free.length) return '';

  const ranges = compressRanges(free);
  const parts = ranges.map((r) => {
    if (r.start === r.end) {
      const d = parseDate(r.start);
      return `${d.getDate()} ${MONTH_NAMES[d.getMonth()]}`;
    }
    const a = parseDate(r.start);
    const b = parseDate(r.end);
    if (a.getMonth() === b.getMonth()) {
      return `${a.getDate()}–${b.getDate()} ${MONTH_NAMES[a.getMonth()]}`;
    }
    return `${fmtDateShort(r.start)}–${fmtDateShort(r.end)}`;
  });
  const joined =
    parts.length > 1
      ? `${parts.slice(0, -1).join(', ')} и ${parts[parts.length - 1]}`
      : parts[0];
  return `${buildFreeDatesHeading(from, to)} ${joined}.`;
}

export function describeAvailContext(
  availOpenFrom: AvailOpenFrom,
  avail: { useCustom: boolean; customFrom: string; customTo: string },
  calendarCtx: {
    calendarScreen: 'feed' | 'day';
    selectedDate: string;
    viewMonth: number;
    viewYear: number;
  },
  reports: { period: ReportsPeriod; month: number; year: number },
  entries: CalendarEntry[],
): string {
  const { from, to } = getAvailContextRange(
    availOpenFrom,
    avail,
    calendarCtx,
    reports,
    entries,
  );
  if (avail.useCustom) {
    return `Диапазон: ${fmtDate(from)} – ${fmtDate(to)}`;
  }
  if (availOpenFrom === 'calendar') {
    const { year, month } = calendarCtx.calendarScreen === 'day'
      ? { year: parseDate(calendarCtx.selectedDate).getFullYear(), month: parseDate(calendarCtx.selectedDate).getMonth() }
      : { year: calendarCtx.viewYear, month: calendarCtx.viewMonth };
    return `Календарь: ${MONTH_NAMES_CAP[month]} ${year}`;
  }
  if (reports.period === 'month') {
    return `Итоги: ${MONTH_NAMES_CAP[reports.month]} ${reports.year}`;
  }
  if (reports.period === 'year') {
    return `Итоги: ${reports.year}`;
  }
  return 'Итоги: за весь период';
}

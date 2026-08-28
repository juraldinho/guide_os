import { MOCK_TODAY } from '@/config';
import type { CalendarEntry } from '@/api/types';
import type { DateRange, ReportsPeriod } from './types';
import { parseDate } from '@/features/calendar/lib/dates';

export function monthStartEnd(year: number, month: number): DateRange {
  const from = `${year}-${String(month + 1).padStart(2, '0')}-01`;
  const lastDay = new Date(year, month + 1, 0).getDate();
  const to = `${year}-${String(month + 1).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;
  return { from, to };
}

export function getMockTodayYear(): number {
  return parseDate(MOCK_TODAY).getFullYear();
}

export function getAllMockDataRange(entries: CalendarEntry[]): DateRange {
  let min = MOCK_TODAY;
  let max = MOCK_TODAY;
  entries.forEach((e) => {
    if (e.startDate < min) min = e.startDate;
    if (e.endDate > max) max = e.endDate;
  });
  return { from: min, to: max };
}

export function getReportRange(
  period: ReportsPeriod,
  reportsMonth: number,
  reportsYear: number,
  entries: CalendarEntry[],
): DateRange {
  const maxYear = getMockTodayYear();
  if (period === 'month') {
    return monthStartEnd(reportsYear, reportsMonth);
  }
  if (period === 'year') {
    const from = `${reportsYear}-01-01`;
    const to = reportsYear < maxYear ? `${reportsYear}-12-31` : MOCK_TODAY;
    return { from, to };
  }
  return getAllMockDataRange(entries);
}

export function getCalendarAvailMonth(
  calendarScreen: 'feed' | 'day',
  selectedDate: string,
  viewMonth: number,
  viewYear: number,
): { year: number; month: number } {
  if (calendarScreen === 'day') {
    const d = parseDate(selectedDate);
    return { year: d.getFullYear(), month: d.getMonth() };
  }
  return { year: viewYear, month: viewMonth };
}

export function getAvailContextRange(
  availOpenFrom: 'calendar' | 'reports',
  avail: { useCustom: boolean; customFrom: string; customTo: string },
  calendarCtx: {
    calendarScreen: 'feed' | 'day';
    selectedDate: string;
    viewMonth: number;
    viewYear: number;
  },
  reports: { period: ReportsPeriod; month: number; year: number },
  entries: CalendarEntry[],
): DateRange {
  if (avail.useCustom && avail.customFrom && avail.customTo) {
    const from = avail.customFrom <= avail.customTo ? avail.customFrom : avail.customTo;
    const to = avail.customFrom <= avail.customTo ? avail.customTo : avail.customFrom;
    return { from, to };
  }
  if (availOpenFrom === 'calendar') {
    const { year, month } = getCalendarAvailMonth(
      calendarCtx.calendarScreen,
      calendarCtx.selectedDate,
      calendarCtx.viewMonth,
      calendarCtx.viewYear,
    );
    return monthStartEnd(year, month);
  }
  return getReportRange(reports.period, reports.month, reports.year, entries);
}

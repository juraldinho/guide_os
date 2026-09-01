import { MOCK_TODAY } from '@/config';
import { DOW_SHORT_UPPER, MONTH_NAMES, MONTH_NAMES_CAP } from '@/i18n/ru';

export const FEED_INITIAL_DAYS = 31;
export const FEED_CHUNK_DAYS = 31;

export function parseDate(s: string): Date {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function toISO(dt: Date): string {
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, '0');
  const d = String(dt.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function daysInRange(start: string, end: string): string[] {
  const out: string[] = [];
  let d = parseDate(start);
  const e = parseDate(end);
  while (d <= e) {
    out.push(toISO(d));
    d = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1);
  }
  return out;
}

export function dateInEntry(date: string, entry: { startDate: string; endDate: string }): boolean {
  return daysInRange(entry.startDate, entry.endDate).includes(date);
}

export function fmtDate(s: string): string {
  const dt = parseDate(s);
  return `${dt.getDate()} ${MONTH_NAMES[dt.getMonth()]}`;
}

export function fmtDateShort(s: string): string {
  const dt = parseDate(s);
  return `${dt.getDate()}.${String(dt.getMonth() + 1).padStart(2, '0')}`;
}

export function fmtDateLong(s: string): string {
  const dt = parseDate(s);
  return `${dt.getDate()} ${MONTH_NAMES[dt.getMonth()]} ${dt.getFullYear()}`;
}

export function dowShortUpper(dateStr: string): string {
  return DOW_SHORT_UPPER[parseDate(dateStr).getDay()];
}

export function getFeedDates(): string[] {
  return buildFeedDates(MOCK_TODAY, FEED_INITIAL_DAYS);
}

/** Consecutive ISO dates from `startIso` inclusive for `dayCount` days. */
export function buildFeedDates(startIso: string, dayCount: number): string[] {
  if (dayCount <= 0) return [];
  const start = parseDate(startIso);
  const out: string[] = [];
  for (let i = 0; i < dayCount; i++) {
    const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
    out.push(toISO(d));
  }
  return out;
}

export function shiftIso(iso: string, dayDelta: number): string {
  const d = parseDate(iso);
  const next = new Date(d.getFullYear(), d.getMonth(), d.getDate() + dayDelta);
  return toISO(next);
}

export function buildFeedDatesFromRange(fromIso: string, toIso: string): string[] {
  if (toIso < fromIso) return [];
  return daysInRange(fromIso, toIso);
}

/** Initial bidirectional window: one chunk into the past and the legacy forward span. */
export function defaultFeedRange(todayIso: string): { from: string; to: string } {
  return {
    from: shiftIso(todayIso, -FEED_CHUNK_DAYS),
    to: shiftIso(todayIso, FEED_INITIAL_DAYS - 1),
  };
}

/** Days from `startIso` through `endIso` inclusive. */
export function countDaysInclusive(startIso: string, endIso: string): number {
  const start = parseDate(startIso);
  const end = parseDate(endIso);
  if (end < start) return 0;
  const ms = end.getTime() - start.getTime();
  return Math.floor(ms / 86400000) + 1;
}

export function monthLabel(monthIndex: number, year: number): string {
  return `${MONTH_NAMES_CAP[monthIndex]} ${year}`;
}

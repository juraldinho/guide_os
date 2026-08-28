import { MOCK_TODAY } from '@/config';
import { DOW_SHORT_UPPER, MONTH_NAMES, MONTH_NAMES_CAP } from '@/i18n/ru';

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
  const start = parseDate(MOCK_TODAY);
  const out: string[] = [];
  for (let i = 0; i < 8; i++) {
    const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
    out.push(toISO(d));
  }
  return out;
}

export function monthLabel(monthIndex: number, year: number): string {
  return `${MONTH_NAMES_CAP[monthIndex]} ${year}`;
}

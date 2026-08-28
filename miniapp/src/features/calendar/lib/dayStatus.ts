import type { CalendarEntry, DayStatusKind, MarkerKind } from '@/api/types';
import { dateInEntry } from './dates';

export function entriesOnDate(date: string, entries: CalendarEntry[]): CalendarEntry[] {
  return entries.filter((e) => dateInEntry(date, e));
}

export function dayStatus(date: string, entries: CalendarEntry[]): DayStatusKind {
  const dayEntries = entriesOnDate(date, entries);
  if (!dayEntries.length) return 'free';
  if (dayEntries.some((e) => e.type === 'day_off')) return 'dayoff';
  const toursOnly = dayEntries.filter((e) => e.type === 'tour');
  if (toursOnly.some((e) => e.status === 'confirmed')) return 'confirmed';
  if (toursOnly.some((e) => e.status === 'reserved')) return 'reserved';
  return 'free';
}

export function markersForDate(date: string, entries: CalendarEntry[]): MarkerKind[] {
  const dayEntries = entriesOnDate(date, entries);
  const markers: MarkerKind[] = [];
  dayEntries.forEach((e) => {
    if (e.type === 'day_off') markers.push('dayoff');
    else if (e.status === 'reserved') markers.push('reserved');
    else if (e.status === 'confirmed') markers.push('confirmed');
  });
  return markers.length ? markers : dayStatus(date, entries) === 'free' ? ['free'] : [];
}

export function isFullDay(entry: CalendarEntry): boolean {
  return entry.type === 'day_off' || !entry.startTime || !entry.endTime;
}

export function getPartialAvailability(date: string, entries: CalendarEntry[]): string | null {
  const tours = entriesOnDate(date, entries).filter(
    (e) => e.type === 'tour' && e.startTime && e.endTime,
  );
  if (!tours.length) return null;
  const latest = tours.reduce((max, e) => (e.endTime! > max ? e.endTime! : max), '00:00');
  if (latest < '23:00') return `Свободен после ${latest}`;
  return null;
}

export function locationFor(entry: CalendarEntry, date: string): string {
  if (entry.dayLocations?.[date]) return entry.dayLocations[date];
  return entry.location || '—';
}

export function sortEntriesForDay(entries: CalendarEntry[]): CalendarEntry[] {
  return [...entries].sort((a, b) => {
    if (isFullDay(a)) return -1;
    if (isFullDay(b)) return 1;
    return (a.startTime || '') < (b.startTime || '') ? -1 : 1;
  });
}

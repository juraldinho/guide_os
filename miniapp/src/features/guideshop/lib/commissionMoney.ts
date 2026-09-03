import { TIMEZONE } from '@/config';
import type { PersonalCommission } from '@/api/types';

const COMMISSION_RE = /^[1-9]\d*$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export type ParseResult<T> = { ok: true; value: T } | { ok: false };

/** Required positive safe integer; empty/invalid → not ok. */
export function parseCommissionInput(raw: string): ParseResult<number> {
  const trimmed = raw.trim();
  if (!trimmed) return { ok: false };
  if (!COMMISSION_RE.test(trimmed)) return { ok: false };
  const value = Number(trimmed);
  if (!Number.isSafeInteger(value) || value <= 0) return { ok: false };
  return { ok: true, value };
}

export function businessDateToOccurredAt(date: string): string {
  if (!DATE_RE.test(date)) {
    throw new RangeError('invalid business date');
  }
  return `${date}T00:00:00+05:00`;
}

function tashkentDateParts(iso: string): { year: string; month: string; day: string } {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    throw new RangeError('invalid occurredAt');
  }
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(parsed);
  const value = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? '';
  return {
    year: value('year'),
    month: value('month'),
    day: value('day'),
  };
}

export function occurredAtToBusinessDate(iso: string): string {
  const { year, month, day } = tashkentDateParts(iso);
  return `${year}-${month}-${day}`;
}

export function formatOccurredAtDisplay(iso: string): string {
  const { year, month, day } = tashkentDateParts(iso);
  return `${day}.${month}.${year}`;
}

/** Active rows with receivedPoints only; ignore legacy money fields. */
export function isUserFacingCommission(item: PersonalCommission): boolean {
  return item.status === 'active' && item.receivedPoints != null && item.receivedPoints > 0;
}

export interface CommissionSummary {
  total: number;
  isEmpty: boolean;
}

export function summarizeActiveCommissions(
  commissions: PersonalCommission[],
): CommissionSummary {
  let total = 0;
  for (const item of commissions) {
    if (!isUserFacingCommission(item) || item.receivedPoints == null) continue;
    const next = total + item.receivedPoints;
    if (!Number.isSafeInteger(next)) {
      throw new RangeError('summary overflow');
    }
    total = next;
  }
  return { total, isEmpty: total === 0 };
}

export function sortCommissionsNewestFirst(
  commissions: PersonalCommission[],
): PersonalCommission[] {
  return [...commissions].sort((a, b) => {
    if (a.occurredAt === b.occurredAt) return b.id.localeCompare(a.id);
    return a.occurredAt < b.occurredAt ? 1 : -1;
  });
}

export function isBusinessDateAfter(date: string, businessToday: string): boolean {
  if (!DATE_RE.test(date) || !DATE_RE.test(businessToday)) return true;
  return date > businessToday;
}

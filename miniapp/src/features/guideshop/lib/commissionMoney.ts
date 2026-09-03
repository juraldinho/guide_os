import { TIMEZONE } from '@/config';
import type { PersonalCommission } from '@/api/types';

const MONEY_RE = /^\d+([.,]\d{1,2})?$/;
const POINTS_RE = /^[1-9]\d*$/;
const CURRENCY_RE = /^[A-Z]{3}$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export type ParseResult<T> = { ok: true; value: T } | { ok: false };

/** Empty optional money → null; otherwise exact integer minor units (2 decimals). */
export function parseMoneyToMinor(raw: string): ParseResult<number | null> {
  const trimmed = raw.trim();
  if (!trimmed) return { ok: true, value: null };
  if (!MONEY_RE.test(trimmed)) return { ok: false };
  const normalized = trimmed.replace(',', '.');
  const [wholePart, fracPart = ''] = normalized.split('.');
  if (!/^\d+$/.test(wholePart)) return { ok: false };
  const frac = `${fracPart}00`.slice(0, 2);
  const digits = `${wholePart}${frac}`.replace(/^0+(?=\d)/, '') || '0';
  if (digits.length > 15) return { ok: false };
  const minor = Number(digits);
  if (!Number.isSafeInteger(minor) || minor < 0) return { ok: false };
  return { ok: true, value: minor };
}

/** Format minor units as decimal string without float math. */
export function formatMinorUnits(minor: number): string {
  if (!Number.isSafeInteger(minor) || minor < 0) {
    throw new RangeError('invalid minor units');
  }
  const negative = false;
  const abs = String(minor);
  const padded = abs.padStart(3, '0');
  const whole = padded.slice(0, -2).replace(/^0+(?=\d)/, '') || '0';
  const frac = padded.slice(-2);
  return `${negative ? '-' : ''}${whole}.${frac}`;
}

export function formatMoneyAmount(minor: number, currency: string): string {
  return `${currency} ${formatMinorUnits(minor)}`;
}

export function parsePointsInput(raw: string): ParseResult<number | null> {
  const trimmed = raw.trim();
  if (!trimmed) return { ok: true, value: null };
  if (!POINTS_RE.test(trimmed)) return { ok: false };
  const value = Number(trimmed);
  if (!Number.isSafeInteger(value) || value <= 0) return { ok: false };
  return { ok: true, value };
}

export function normalizeCurrencyInput(raw: string): ParseResult<string | null> {
  const trimmed = raw.trim();
  if (!trimmed) return { ok: true, value: null };
  const upper = trimmed.toUpperCase();
  if (!CURRENCY_RE.test(upper)) return { ok: false };
  return { ok: true, value: upper };
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

export interface CommissionSummary {
  incomesByCurrency: Array<{ currency: string; minor: number }>;
  pointsTotal: number;
  isEmpty: boolean;
}

/** Active records only; sum receivedIncomeMinor by currency; points separate. */
export function summarizeActiveCommissions(
  commissions: PersonalCommission[],
): CommissionSummary {
  const totals = new Map<string, number>();
  let pointsTotal = 0;
  for (const item of commissions) {
    if (item.status !== 'active') continue;
    if (item.receivedIncomeMinor != null && item.currency) {
      const prev = totals.get(item.currency) ?? 0;
      const next = prev + item.receivedIncomeMinor;
      if (!Number.isSafeInteger(next)) {
        throw new RangeError('summary overflow');
      }
      totals.set(item.currency, next);
    }
    if (item.receivedPoints != null) {
      const next = pointsTotal + item.receivedPoints;
      if (!Number.isSafeInteger(next)) {
        throw new RangeError('summary overflow');
      }
      pointsTotal = next;
    }
  }
  const incomesByCurrency = [...totals.entries()]
    .map(([currency, minor]) => ({ currency, minor }))
    .sort((a, b) => a.currency.localeCompare(b.currency));
  return {
    incomesByCurrency,
    pointsTotal,
    isEmpty: incomesByCurrency.length === 0 && pointsTotal === 0,
  };
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

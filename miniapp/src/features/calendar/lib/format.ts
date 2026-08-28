import type { CalendarEntry, PaymentStatus, TourStatus } from '@/api/types';
import { t } from '@/i18n/strings';

export function timeLabel(entry: CalendarEntry): string {
  if (entry.type === 'day_off') return t.allDay;
  if (!entry.startTime || !entry.endTime) return t.allDay;
  return `${entry.startTime}–${entry.endTime}`;
}

export function statusLabel(status?: TourStatus): string {
  if (status === 'reserved') return t.statusReserved;
  if (status === 'confirmed') return t.statusConfirmed;
  return '';
}

export function paymentLabel(payment?: PaymentStatus): string {
  return payment === 'paid' ? t.paymentPaid : t.paymentUnpaid;
}

export function dayStatusText(status: string): string {
  switch (status) {
    case 'free': return t.dayFree;
    case 'dayoff': return t.dayOff;
    case 'reserved': return t.statusReserved;
    case 'confirmed': return t.statusConfirmed;
    default: return '';
  }
}

export function dayAvailabilitySummary(
  _date: string,
  _entries: CalendarEntry[],
  partial: string | null,
  status: string,
): string {
  if (status === 'free') return t.dayFullyFree;
  if (status === 'dayoff') return t.dayOff;
  if (partial) return partial;
  return t.dayBusy;
}

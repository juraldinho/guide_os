import type { CalendarEntry } from '@/api/types';
import { daysInRange } from '@/features/calendar/lib/dates';
import { isGuideOperatorManaged } from '@/features/calendar/lib/dayStatus';
import type { DateRange, ReportsFilters, ReportsSummary } from './types';

export function calcSummary(
  entries: CalendarEntry[],
  range: DateRange,
  filters: ReportsFilters,
): ReportsSummary {
  const { from, to } = range;
  let tourCount = 0;
  let income = 0;
  let paidTours = 0;
  let unpaidTours = 0;
  const workDaysSet = new Set<string>();

  entries.forEach((e) => {
    if (e.type === 'day_off') return;
    if (filters.status !== 'all' && e.status !== filters.status) return;
    const operatorManaged = isGuideOperatorManaged(e);
    // Guide Operator has no paid/unpaid fee state — exclude from payment filters.
    if (filters.payment !== 'all') {
      if (operatorManaged || e.payment !== filters.payment) return;
    }
    if (filters.company && !(e.company || '').includes(filters.company)) return;
    if (filters.location && !(e.location || '').includes(filters.location)) return;

    const overlap = daysInRange(e.startDate, e.endDate).filter((d) => d >= from && d <= to);
    if (!overlap.length) return;

    tourCount += 1;
    overlap.forEach((d) => workDaysSet.add(d));
    if (!operatorManaged) {
      income += (e.income || 0) * overlap.length;
      if (e.payment === 'paid') paidTours += 1;
      else unpaidTours += 1;
    }
  });

  return {
    tourCount,
    workDays: workDaysSet.size,
    income,
    paidTours,
    unpaidTours,
  };
}

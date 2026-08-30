import { describe, expect, it } from 'vitest';
import { INITIAL_ENTRIES } from '@/api/mock/data';
import { calcSummary } from '@/features/reports/lib/summary';
import { getReportRange, getMockTodayYear } from '@/features/reports/lib/periods';

describe('calcSummary', () => {
  it('counts overlapping days and income for month period', () => {
    const range = { from: '2026-08-01', to: '2026-08-31' };
    const summary = calcSummary(INITIAL_ENTRIES, range, {
      status: 'all',
      payment: 'all',
      company: '',
      location: '',
    });
    expect(summary.tourCount).toBe(4);
    expect(summary.workDays).toBeGreaterThan(0);
    expect(summary.income).toBeGreaterThan(0);
  });

  it('filters by payment status', () => {
    const range = { from: '2026-08-01', to: '2026-08-31' };
    const paid = calcSummary(INITIAL_ENTRIES, range, {
      status: 'all',
      payment: 'paid',
      company: '',
      location: '',
    });
    expect(paid.paidTours).toBe(1);
    expect(paid.unpaidTours).toBe(0);
  });
});

describe('getReportRange', () => {
  it('includes the full selected year, including planned future tours', () => {
    const maxYear = getMockTodayYear();
    expect(maxYear).toBe(2026);
    const range = getReportRange('year', 7, 2026, INITIAL_ENTRIES);
    expect(range.from).toBe('2026-01-01');
    expect(range.to).toBe('2026-12-31');
  });

  it('uses full december for past years', () => {
    const range = getReportRange('year', 7, 2025, INITIAL_ENTRIES);
    expect(range.from).toBe('2025-01-01');
    expect(range.to).toBe('2025-12-31');
  });
});

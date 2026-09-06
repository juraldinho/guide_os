import { describe, expect, it } from 'vitest';
import { INITIAL_ENTRIES } from '@/api/mock/data';
import type { CalendarEntry } from '@/api/types';
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

  it('counts Guide Operator as work days without income or paid/unpaid', () => {
    const range = { from: '2026-09-01', to: '2026-09-30' };
    const summary = calcSummary(INITIAL_ENTRIES, range, {
      status: 'all',
      payment: 'all',
      company: '',
      location: '',
    });
    expect(summary.tourCount).toBe(1);
    expect(summary.workDays).toBe(3);
    expect(summary.income).toBe(0);
    expect(summary.paidTours).toBe(0);
    expect(summary.unpaidTours).toBe(0);
  });

  it('excludes Guide Operator from paid and unpaid payment filters', () => {
    const range = { from: '2026-09-01', to: '2026-09-30' };
    const paid = calcSummary(INITIAL_ENTRIES, range, {
      status: 'all',
      payment: 'paid',
      company: '',
      location: '',
    });
    const unpaid = calcSummary(INITIAL_ENTRIES, range, {
      status: 'all',
      payment: 'unpaid',
      company: '',
      location: '',
    });
    expect(paid.tourCount).toBe(0);
    expect(unpaid.tourCount).toBe(0);
  });

  it('dedupes work days when personal and operator share a date', () => {
    const entries: CalendarEntry[] = [
      {
        id: 'p1',
        type: 'tour',
        title: 'Personal',
        startDate: '2026-10-01',
        endDate: '2026-10-01',
        startTime: null,
        endTime: null,
        status: 'confirmed',
        payment: 'paid',
        income: 90,
        source: 'Mini App',
      },
      {
        id: 'go1',
        type: 'tour',
        title: 'Operator',
        startDate: '2026-10-01',
        endDate: '2026-10-01',
        startTime: null,
        endTime: null,
        status: 'confirmed',
        payment: null,
        income: null,
        source: 'Guide Operator',
        guideOperatorAssignmentId: 'goasg_x',
        guideOperatorVersion: 1,
      },
    ];
    const summary = calcSummary(entries, { from: '2026-10-01', to: '2026-10-31' }, {
      status: 'all',
      payment: 'all',
      company: '',
      location: '',
    });
    expect(summary.tourCount).toBe(2);
    expect(summary.workDays).toBe(1);
    expect(summary.income).toBe(90);
    expect(summary.paidTours).toBe(1);
    expect(summary.unpaidTours).toBe(0);
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

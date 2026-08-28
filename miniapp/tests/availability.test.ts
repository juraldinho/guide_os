import { describe, expect, it } from 'vitest';
import { INITIAL_ENTRIES } from '@/api/mock/data';
import { buildFreeDatesHeading, buildFreeDatesText } from '@/features/reports/lib/availability';

const calendarCtx = {
  calendarScreen: 'feed' as const,
  selectedDate: '2026-08-28',
  viewMonth: 8,
  viewYear: 2026,
};

const reports = { period: 'month' as const, month: 8, year: 2026 };

describe('buildFreeDatesHeading', () => {
  it('uses month name for full calendar month', () => {
    expect(buildFreeDatesHeading('2026-09-01', '2026-09-30')).toBe('Свободные даты в сентябре:');
  });

  it('uses date range for cross-month span', () => {
    const heading = buildFreeDatesHeading('2026-08-15', '2026-09-10');
    expect(heading).toMatch(/^Свободные даты с /);
    expect(heading).toMatch(/ по /);
  });
});

describe('buildFreeDatesText', () => {
  it('uses custom date range when enabled', () => {
    const text = buildFreeDatesText(
      INITIAL_ENTRIES,
      'reports',
      { useCustom: true, customFrom: '2026-09-01', customTo: '2026-09-30' },
      calendarCtx,
      reports,
    );
    expect(text).toContain('Свободные даты в сентябре:');
    expect(text).not.toContain('августе');
  });
});

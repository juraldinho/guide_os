import { describe, expect, it, beforeEach } from 'vitest';
import { INITIAL_ENTRIES } from '@/api/mock/data';
import { __resetMockStore } from '@/api/mock/store';
import type { CalendarEntry } from '@/api/types';
import { checkConflicts } from '@/features/calendar/lib/conflicts';

describe('checkConflicts', () => {
  beforeEach(() => {
    __resetMockStore();
  });

  it('blocks overlapping time on same day', () => {
    const entries = INITIAL_ENTRIES as CalendarEntry[];
    const draft = {
      type: 'tour' as const,
      title: 'Новый',
      startDate: '2026-08-28',
      endDate: '2026-08-28',
      startTime: '12:00',
      endTime: '16:00',
      income: 50,
    };
    const result = checkConflicts(draft, entries);
    expect(result).not.toBeNull();
    expect(result && 'block' in result && result.block).toBe(true);
  });

  it('warns on same date without time overlap', () => {
    const entries = INITIAL_ENTRIES as CalendarEntry[];
    const draft = {
      type: 'tour' as const,
      title: 'Вечер',
      startDate: '2026-08-28',
      endDate: '2026-08-28',
      startTime: '15:00',
      endTime: '17:00',
      income: 50,
    };
    const result = checkConflicts(draft, entries);
    expect(result).not.toBeNull();
    expect(result && 'warn' in result).toBe(true);
  });

  it('blocks day off conflict', () => {
    const entries = INITIAL_ENTRIES as CalendarEntry[];
    const draft = {
      type: 'tour' as const,
      title: 'Тур',
      startDate: '2026-08-10',
      endDate: '2026-08-10',
      startTime: null,
      endTime: null,
      income: 0,
    };
    const result = checkConflicts(draft, entries);
    expect(result && 'block' in result && result.block).toBe(true);
  });
});

import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockClient, __resetMockStore } from '@/api/mock/store';
import { createHttpClient, __testSetSessionToken, __testClearSession } from '@/api/httpClient';
import { MAX_DAILY_TIPS } from '@/api/types';

afterEach(() => { __resetMockStore(); __testClearSession(); vi.unstubAllGlobals(); });

describe('daily tips client', () => {
  it('replaces, removes and keeps tips independent of tours and filters', async () => {
    const date = '1999-01-01';
    for (const amount of [10, 20, 20]) await mockClient.setDailyTip(date, amount);
    expect(await mockClient.getDailyTip(date)).toEqual({ date, amount: 20 });
    const summary = await mockClient.getReportsSummary({ from: '0001-01-01', to: '9999-12-31', status: 'all', payment: 'paid', company: 'absent' });
    expect(summary).toMatchObject({ income: 0, tips: 20, totalEarnings: 20, tourCount: 0, workDays: 0 });
    expect(await mockClient.listDailyTips('2026-01-01', '2026-12-31')).toEqual([]);
    for (let i = 0; i < 2; i++) await mockClient.setDailyTip(date, 0);
    expect(await mockClient.listDailyTips('0001-01-01', '9999-12-31')).toEqual([]);
  });

  it('validates dates and integer bounds in mocks', async () => {
    for (const amount of [-1, 1.5, NaN, Infinity, MAX_DAILY_TIPS + 1, true, '20']) {
      await expect(mockClient.setDailyTip('2026-10-22', amount as number)).rejects.toThrow();
    }
    for (const date of ['2026-02-30', '20261022', '0000-01-01']) {
      await expect(mockClient.setDailyTip(date, 1)).rejects.toThrow();
    }
    await expect(mockClient.setDailyTip('2024-02-29', MAX_DAILY_TIPS)).resolves.toMatchObject({ amount: MAX_DAILY_TIPS });
  });

  it('uses authenticated HTTP routes with replacement payload and safe errors', async () => {
    __testSetSessionToken('test-session');
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { date: '2026-10-22', amount: 20 } }), { status: 200 }));
    vi.stubGlobal('fetch', fetcher);
    const client = createHttpClient();
    expect(await client.setDailyTip('2026-10-22', 20)).toEqual({ date: '2026-10-22', amount: 20 });
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toContain('/app/v1/daily-tips/2026-10-22');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body)).toEqual({ amount: 20 });
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer test-session');
    fetcher.mockResolvedValue(new Response(JSON.stringify({ data: { tips: [{ date: '2026-10-22', amount: 20 }] } }), { status: 200 }));
    expect(await client.listDailyTips('2026-10-01', '2026-10-31')).toHaveLength(1);
    fetcher.mockResolvedValue(new Response(JSON.stringify({ error: { code: 'validation_error', message: 'Некорректная сумма.' } }), { status: 400 }));
    await expect(client.setDailyTip('2026-10-22', -1)).rejects.toThrow('Некорректная сумма.');
  });
});

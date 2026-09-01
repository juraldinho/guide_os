import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement, useEffect } from 'react';
import { render, waitFor } from '@testing-library/react';
import {
  __testClearSession,
  __testSetSessionToken,
  ApiConflictError,
  createHttpClient,
} from '@/api/httpClient';
import { ToastProvider } from '@/components/ui/Toast';
import { CalendarProvider, useCalendar } from '@/features/calendar/CalendarContext';
import { MOCK_PROFILE } from '@/api/mock/data';
import { mockClient, __resetMockStore } from '@/api/mock/store';

const profileResponse = {
  name: 'Test Guide',
  telegramId: '123456789',
  types: [
    {
      type: 'local' as const,
      label: 'Локальный гид',
      geo: ['Самарканд'],
      allUzbekistan: false,
    },
  ],
  languages: ['Русский'],
  notifications: { enabled: true, time: '08:00' },
};

function CalendarContextProbe({
  onCtx,
}: {
  onCtx: (ctx: ReturnType<typeof useCalendar>) => void;
}) {
  const ctx = useCalendar();
  useEffect(() => {
    onCtx(ctx);
  }, [ctx, onCtx]);
  return null;
}

function renderCalendarContext(onCtx: (ctx: ReturnType<typeof useCalendar>) => void) {
  render(
    createElement(
      ToastProvider,
      null,
      createElement(
        CalendarProvider,
        null,
        createElement(CalendarContextProbe, { onCtx }),
      ),
    ),
  );
}
const entry = {
  id: '1',
  type: 'tour' as const,
  title: 'Test',
  startDate: '2026-08-28',
  endDate: '2026-08-28',
  startTime: null,
  endTime: null,
  income: 100,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('httpClient', () => {
  beforeEach(() => {
    __testClearSession();
    window.Telegram = { WebApp: { initData: '' } };
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('bootstraps session with Telegram initData and lists entries', async () => {
    window.Telegram = { WebApp: { initData: 'query_id=1&user=%7B%7D&hash=abc' } };
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ data: { session_token: 'tok_abc', session_expires_at: null, user: {} } }),
      )
      .mockResolvedValueOnce(jsonResponse({ data: { entries: [entry] } }));

    const client = createHttpClient();
    const entries = await client.listEntries();

    expect(entries).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/app/v1/session');
    const headers = fetchMock.mock.calls[1]?.[1]?.headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer tok_abc');
  });

  it('reuses stored session token without second bootstrap when initData is absent', async () => {
    window.Telegram = { WebApp: { initData: '' } };
    __testSetSessionToken('stored_tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: { entries: [] } }));

    await createHttpClient().listEntries();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toContain('/app/v1/entries');
    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer stored_tok');
  });

  it('bootstraps with initData instead of trusting a stored session token', async () => {
    window.Telegram = { WebApp: { initData: 'query_id=1&user=%7B%7D&hash=abc' } };
    __testSetSessionToken('stale_tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ data: { session_token: 'fresh_tok', session_expires_at: null, user: {} } }),
      )
      .mockResolvedValueOnce(jsonResponse({ data: { entries: [entry] } }));

    const entries = await createHttpClient().listEntries();

    expect(entries).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/app/v1/session');
    const sessionInit = fetchMock.mock.calls[0]?.[1];
    expect(JSON.parse(String(sessionInit?.body))).toEqual({
      init_data: 'query_id=1&user=%7B%7D&hash=abc',
    });
    const entriesHeaders = fetchMock.mock.calls[1]?.[1]?.headers as Headers;
    expect(entriesHeaders.get('Authorization')).toBe('Bearer fresh_tok');
    expect(entriesHeaders.get('Authorization')).not.toBe('Bearer stale_tok');
  });

  it('deduplicates session bootstrap across concurrent API calls', async () => {
    window.Telegram = { WebApp: { initData: 'query_id=1&user=%7B%7D&hash=abc' } };
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ data: { session_token: 'tok_concurrent', session_expires_at: null, user: {} } }),
      )
      .mockResolvedValueOnce(jsonResponse({ data: { entries: [] } }))
      .mockResolvedValueOnce(jsonResponse({ data: { entries: [] } }));

    const client = createHttpClient();
    await Promise.all([client.listEntries(), client.listEntries()]);

    const sessionCalls = fetchMock.mock.calls.filter((call) => call[0] === '/app/v1/session');
    expect(sessionCalls).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('clears stale token on 401, re-bootstraps with initData, and retries once', async () => {
    window.Telegram = { WebApp: { initData: 'query_id=1&user=%7B%7D&hash=abc' } };
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ data: { session_token: 'fresh_tok', session_expires_at: null, user: {} } }),
      )
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'auth_required', message: 'expired' } }, 401))
      .mockResolvedValueOnce(
        jsonResponse({ data: { session_token: 'renewed_tok', session_expires_at: null, user: {} } }),
      )
      .mockResolvedValueOnce(jsonResponse({ data: { entries: [entry] } }));

    const entries = await createHttpClient().listEntries();

    expect(entries).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/app/v1/session');
    expect(fetchMock.mock.calls[1]?.[0]).toContain('/app/v1/entries');
    expect(fetchMock.mock.calls[2]?.[0]).toBe('/app/v1/session');
    expect(fetchMock.mock.calls[3]?.[0]).toContain('/app/v1/entries');
    const retryEntriesHeaders = fetchMock.mock.calls[3]?.[1]?.headers as Headers;
    expect(retryEntriesHeaders.get('Authorization')).toBe('Bearer renewed_tok');
  });

  it('maps date_warning conflict to ApiConflictError', async () => {
    __testSetSessionToken('tok');
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(
        {
          error: {
            code: 'date_warning',
            message: 'На этой дате уже есть тур.',
            details: {
              conflict_kind: 'date_warning',
              date: '2026-08-28',
              existing_entry: entry,
              ack_field: 'ack_date_warning',
            },
          },
        },
        409,
      ),
    );

    await expect(
      createHttpClient().createTour({
        title: 'X',
        startDate: '2026-08-28',
        endDate: '2026-08-28',
        useTime: false,
        startTime: '09:00',
        endTime: '14:00',
        company: '',
        location: '',
        income: 0,
        status: 'reserved',
        payment: 'unpaid',
        note: '',
      }),
    ).rejects.toBeInstanceOf(ApiConflictError);
  });

  it('sends ack_date_warning on tour write when requested', async () => {
    __testSetSessionToken('tok');
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ data: entry }, 201));

    await createHttpClient().createTour(
      {
        title: 'X',
        startDate: '2026-08-28',
        endDate: '2026-08-28',
        useTime: false,
        startTime: '09:00',
        endTime: '14:00',
        company: '',
        location: '',
        income: 0,
        status: 'reserved',
        payment: 'unpaid',
        note: '',
      },
      { ackDateWarning: true },
    );

    const init = vi.mocked(fetch).mock.calls[0]?.[1];
    expect(JSON.parse(String(init?.body))).toMatchObject({ ack_date_warning: true });
  });

  it('fetches reports summary with filter query params', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        data: {
          tourCount: 2,
          workDays: 5,
          income: 300,
          paidTours: 1,
          unpaidTours: 1,
          period: { from: '2026-08-01', to: '2026-08-31' },
        },
      }),
    );

    const summary = await createHttpClient().getReportsSummary({
      from: '2026-08-01',
      to: '2026-08-31',
      status: 'confirmed',
      payment: 'paid',
    });

    expect(summary.tourCount).toBe(2);
    expect(fetchMock.mock.calls[0]?.[0]).toContain('/app/v1/reports/summary');
    expect(fetchMock.mock.calls[0]?.[0]).toContain('status=confirmed');
    expect(fetchMock.mock.calls[0]?.[0]).toContain('payment=paid');
  });

  it('previews availability text from API', async () => {
    __testSetSessionToken('tok');
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        data: {
          heading: 'Свободные даты в августе:',
          text: 'Свободные даты в августе: 1–3 августа.',
          freeDates: ['2026-08-01'],
          ranges: [{ start: '2026-08-01', end: '2026-08-03' }],
        },
      }),
    );

    const preview = await createHttpClient().previewAvailability({
      from: '2026-08-01',
      to: '2026-08-31',
    });

    expect(preview.text).toContain('августе');
    const init = vi.mocked(fetch).mock.calls[0]?.[1];
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toMatchObject({
      from: '2026-08-01',
      to: '2026-08-31',
      format: 'text',
    });
  });
});

describe('profile PATCH contract', () => {
  beforeEach(() => {
    __testClearSession();
    window.Telegram = { WebApp: { initData: '' } };
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends professional profile fields without label or telegramId', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: profileResponse }));

    await createHttpClient().updateProfile({
      types: [{ type: 'local', geo: ['Самарканд'], allUzbekistan: false }],
      languages: ['Русский', 'Английский'],
    });

    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.method).toBe('PATCH');
    const body = JSON.parse(String(init?.body));
    expect(body).toEqual({
      types: [{ type: 'local', geo: ['Самарканд'], allUzbekistan: false }],
      languages: ['Русский', 'Английский'],
    });
    expect(body.telegramId).toBeUndefined();
    expect(body.label).toBeUndefined();
    expect(body.types?.[0]?.label).toBeUndefined();
  });

  it('sends name-only PATCH without other profile fields', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: profileResponse }));

    await createHttpClient().updateProfile({ name: 'Новое имя' });

    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    expect(body).toEqual({ name: 'Новое имя' });
    expect(body.types).toBeUndefined();
    expect(body.languages).toBeUndefined();
    expect(body.notifications).toBeUndefined();
    expect(body.telegramId).toBeUndefined();
  });

  it('sends notifications-only PATCH without other profile fields', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: profileResponse }));

    await createHttpClient().updateProfile({ notifications: { enabled: false } });

    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    expect(body).toEqual({ notifications: { enabled: false } });
    expect(body.name).toBeUndefined();
    expect(body.types).toBeUndefined();
    expect(body.languages).toBeUndefined();
    expect(body.telegramId).toBeUndefined();
  });
});

describe('mock profile contract', () => {
  beforeEach(() => {
    __resetMockStore();
  });

  it('getProfile returns cloned types, geography, languages, and allUzbekistan', async () => {
    const profile = await mockClient.getProfile();
    expect(profile.types[0]).toMatchObject({
      type: 'local',
      geo: ['Самарканд'],
      allUzbekistan: false,
    });
    expect(profile.types[1]).toMatchObject({
      type: 'route',
      geo: [],
      allUzbekistan: true,
    });
    expect(profile.languages).toEqual(['Русский', 'Английский']);

    profile.types[0].geo.push('mutated');
    profile.languages.push('mutated');

    const fresh = await mockClient.getProfile();
    expect(fresh.types[0].geo).toEqual(['Самарканд']);
    expect(fresh.languages).toEqual(['Русский', 'Английский']);
  });

  it('updateProfile persists professional data with derived labels', async () => {
    const updated = await mockClient.updateProfile({
      types: [{ type: 'accompanying', geo: ['Ташкент'], allUzbekistan: false }],
      languages: ['Узбекский'],
    });

    expect(updated.types).toEqual([
      {
        type: 'accompanying',
        label: 'Сопровождающий гид',
        geo: ['Ташкент'],
        allUzbekistan: false,
      },
    ]);
    expect(updated.languages).toEqual(['Узбекский']);
    expect(updated.name).toBe(MOCK_PROFILE.name);
    expect(updated.telegramId).toBe(MOCK_PROFILE.telegramId);
  });

  it('updateProfile clears types and languages on explicit empty arrays', async () => {
    const updated = await mockClient.updateProfile({ types: [], languages: [] });
    expect(updated.types).toEqual([]);
    expect(updated.languages).toEqual([]);
  });
});

describe('CalendarContext saveProfessionalProfile', () => {
  beforeEach(() => {
    __resetMockStore();
  });

  it('replaces profile only after successful save', async () => {
    let ctx: ReturnType<typeof useCalendar> | null = null;
    renderCalendarContext((value) => {
      ctx = value;
    });

    await waitFor(() => expect(ctx?.profile).not.toBeNull());
    const beforeName = ctx!.profile!.name;

    const ok = await ctx!.saveProfessionalProfile(
      [{ type: 'accompanying', geo: ['Бухара'], allUzbekistan: false }],
      ['Узбекский'],
    );

    expect(ok).toBe(true);
    await waitFor(() => {
      expect(ctx!.profile?.types).toEqual([
        {
          type: 'accompanying',
          label: 'Сопровождающий гид',
          geo: ['Бухара'],
          allUzbekistan: false,
        },
      ]);
    });
    expect(ctx!.profile?.languages).toEqual(['Узбекский']);
    expect(ctx!.profile?.name).toBe(beforeName);
  });

  it('preserves profile on failed save', async () => {
    vi.spyOn(mockClient, 'updateProfile').mockRejectedValueOnce(new Error('save failed'));

    let ctx: ReturnType<typeof useCalendar> | null = null;
    renderCalendarContext((value) => {
      ctx = value;
    });

    await waitFor(() => expect(ctx?.profile).not.toBeNull());
    const snapshot = ctx!.profile;

    const ok = await ctx!.saveProfessionalProfile([], ['Русский']);

    expect(ok).toBe(false);
    expect(ctx!.profile).toEqual(snapshot);
  });
});

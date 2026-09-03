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
import {
  mockClient,
  __resetMockStore,
  __testOfficialCompanies,
  __testOfficialVisits,
  __testOfficialPointsSummary,
  __testOfficialHistory,
  __testPersonalPlaces,
} from '@/api/mock/store';

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

describe('personal places HTTP client', () => {
  const place = {
    id: 'place_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    name: 'Бухара Арт',
    category: 'Магазин',
    generalLocation: 'Бухара',
    landmark: null,
    note: null,
    status: 'active' as const,
    createdAt: '2026-08-01T10:00:00Z',
    updatedAt: '2026-08-01T10:00:00Z',
  };

  beforeEach(() => {
    __testClearSession();
    window.Telegram = { WebApp: { initData: '' } };
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('lists personal places from /app/v1/personal-places', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: { places: [place] } }));

    const places = await createHttpClient().listPersonalPlaces();

    expect(places).toEqual([place]);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/app/v1/personal-places');
  });

  it('lists with includeInactive=true exact query', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: { places: [place] } }));

    await createHttpClient().listPersonalPlaces({ includeInactive: true });

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/app/v1/personal-places?includeInactive=true',
    );
  });

  it('gets personal place with encoded id', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: place }));

    const result = await createHttpClient().getPersonalPlace(place.id);

    expect(result).toEqual(place);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/app/v1/personal-places/${encodeURIComponent(place.id)}`,
    );
  });

  it('returns null only on not_found for getPersonalPlace', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: 'not_found', message: 'missing' } }, 404),
      )
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: 'auth_required', message: 'auth' } }, 401),
      );

    await expect(createHttpClient().getPersonalPlace(place.id)).resolves.toBeNull();
    await expect(createHttpClient().getPersonalPlace(place.id)).rejects.toMatchObject({
      code: 'auth_required',
    });
  });

  it('creates personal place with POST body and Idempotency-Key', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: place }, 201));

    const input = {
      name: 'Бухара Арт',
      category: 'Магазин',
      generalLocation: 'Бухара',
      landmark: null,
      note: null,
    };
    await createHttpClient().createPersonalPlace(input);

    const init = fetchMock.mock.calls[0]?.[1];
    const headers = init?.headers as Headers;
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual(input);
    expect(headers.get('Idempotency-Key')).toBeTruthy();
    expect(JSON.parse(String(init?.body))).not.toHaveProperty('id');
    expect(JSON.parse(String(init?.body))).not.toHaveProperty('status');
    expect(JSON.parse(String(init?.body))).not.toHaveProperty('userId');
  });

  it('updates personal place with PUT complete body and Idempotency-Key', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: place }));

    const input = {
      name: 'Updated',
      category: null,
      generalLocation: null,
      landmark: null,
      note: null,
    };
    await createHttpClient().updatePersonalPlace(place.id, input);

    const init = fetchMock.mock.calls[0]?.[1];
    const headers = init?.headers as Headers;
    expect(init?.method).toBe('PUT');
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/app/v1/personal-places/${encodeURIComponent(place.id)}`,
    );
    expect(JSON.parse(String(init?.body))).toEqual(input);
    expect(headers.get('Idempotency-Key')).toBeTruthy();
  });

  it('deactivates personal place with POST, Idempotency-Key, and no body', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: {} }));

    await createHttpClient().deactivatePersonalPlace(place.id);

    const init = fetchMock.mock.calls[0]?.[1];
    const headers = init?.headers as Headers;
    expect(init?.method).toBe('POST');
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/app/v1/personal-places/${encodeURIComponent(place.id)}/deactivate`,
    );
    expect(init?.body).toBeUndefined();
    expect(headers.get('Idempotency-Key')).toBeTruthy();
  });
});

describe('httpClient personal commissions', () => {
  const commission = {
    id: 'entry_11111111111111111111111111111111',
    placeId: 'place_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    occurredAt: '2026-08-10T05:00:00Z',
    purchaseAmountMinor: null,
    receivedIncomeMinor: null,
    receivedPoints: 5,
    currency: null,
    note: 'note',
    status: 'active' as const,
    createdAt: '2026-08-10T06:00:00Z',
    updatedAt: '2026-08-10T06:00:00Z',
  };

  beforeEach(() => {
    __testClearSession();
    __resetMockStore();
    window.Telegram = { WebApp: { initData: '' } };
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('lists commissions from nested encoded place path', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: { commissions: [commission] } }));

    const list = await createHttpClient().listPersonalCommissions(commission.placeId);

    expect(list).toEqual([commission]);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/app/v1/personal-places/${encodeURIComponent(commission.placeId)}/commissions`,
    );
  });

  it('lists with includeInactive=true exact query', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: { commissions: [commission] } }));

    await createHttpClient().listPersonalCommissions(commission.placeId, {
      includeInactive: true,
    });

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/app/v1/personal-places/${encodeURIComponent(commission.placeId)}/commissions?includeInactive=true`,
    );
  });

  it('gets commission with encoded id', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: commission }));

    const result = await createHttpClient().getPersonalCommission(commission.id);

    expect(result).toEqual(commission);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/app/v1/personal-commissions/${encodeURIComponent(commission.id)}`,
    );
  });

  it('returns null only on not_found for getPersonalCommission', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: 'not_found', message: 'missing' } }, 404),
      )
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: 'auth_required', message: 'auth' } }, 401),
      );

    await expect(createHttpClient().getPersonalCommission(commission.id)).resolves.toBeNull();
    await expect(createHttpClient().getPersonalCommission(commission.id)).rejects.toMatchObject({
      code: 'auth_required',
    });
  });

  it('creates commission with POST body and Idempotency-Key', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: commission }, 201));

    const input = {
      occurredAt: '2026-08-10T00:00:00+05:00',
      purchaseAmountMinor: null,
      receivedIncomeMinor: null,
      receivedPoints: 5,
      currency: null,
      note: 'note',
    };
    await createHttpClient().createPersonalCommission(commission.placeId, input);

    const init = fetchMock.mock.calls[0]?.[1];
    const headers = init?.headers as Headers;
    expect(init?.method).toBe('POST');
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/app/v1/personal-places/${encodeURIComponent(commission.placeId)}/commissions`,
    );
    expect(JSON.parse(String(init?.body))).toEqual(input);
    expect(headers.get('Idempotency-Key')).toBeTruthy();
    expect(JSON.parse(String(init?.body))).not.toHaveProperty('id');
    expect(JSON.parse(String(init?.body))).not.toHaveProperty('status');
    expect(JSON.parse(String(init?.body))).not.toHaveProperty('userId');
  });

  it('updates commission with PUT complete body and Idempotency-Key', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: commission }));

    const input = {
      occurredAt: '2026-08-10T00:00:00+05:00',
      purchaseAmountMinor: null,
      receivedIncomeMinor: null,
      receivedPoints: 9,
      currency: null,
      note: null,
    };
    await createHttpClient().updatePersonalCommission(commission.id, input);

    const init = fetchMock.mock.calls[0]?.[1];
    const headers = init?.headers as Headers;
    expect(init?.method).toBe('PUT');
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/app/v1/personal-commissions/${encodeURIComponent(commission.id)}`,
    );
    expect(JSON.parse(String(init?.body))).toEqual(input);
    expect(headers.get('Idempotency-Key')).toBeTruthy();
  });

  it('deactivates commission with POST, Idempotency-Key, and no body', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: {} }));

    await createHttpClient().deactivatePersonalCommission(commission.id);

    const init = fetchMock.mock.calls[0]?.[1];
    const headers = init?.headers as Headers;
    expect(init?.method).toBe('POST');
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/app/v1/personal-commissions/${encodeURIComponent(commission.id)}/deactivate`,
    );
    expect(init?.body).toBeUndefined();
    expect(headers.get('Idempotency-Key')).toBeTruthy();
  });
});

describe('official GuideShop companies API', () => {
  const company = {
    id: 'gsco_silkroad_01',
    displayName: 'Silk Road Emporium',
    status: 'active',
    phone: '+998901112233',
    address: 'Registan Square, Samarkand',
    description: 'Official partner',
    type: 'shop',
  };

  const sparseCompany = {
    id: 'gsco_nullfields_02',
    displayName: 'Sparse Co',
    status: 'pending_review',
    phone: null,
    address: null,
    description: null,
    type: null,
  };

  beforeEach(() => {
    __testClearSession();
    window.Telegram = { WebApp: { initData: '' } };
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('lists official companies from GET /app/v1/guideshop/companies with bearer token', async () => {
    __testSetSessionToken('tok_official');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        data: {
          companies: [company, sparseCompany],
          page: { nextCursor: 'opaque_cursor_token_01' },
        },
      }),
    );

    const result = await createHttpClient().listOfficialCompanies();

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/app/v1/guideshop/companies');
    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer tok_official');
    expect(result.companies).toEqual([company, sparseCompany]);
    expect(result.companies[0]).toEqual({
      id: 'gsco_silkroad_01',
      displayName: 'Silk Road Emporium',
      status: 'active',
      phone: '+998901112233',
      address: 'Registan Square, Samarkand',
      description: 'Official partner',
      type: 'shop',
    });
    expect(result.companies[1]?.phone).toBeNull();
    expect(result.companies[1]?.address).toBeNull();
    expect(result.companies[1]?.description).toBeNull();
    expect(result.companies[1]?.type).toBeNull();
    expect(result.companies[1]?.status).toBe('pending_review');
    expect(result.page.nextCursor).toBe('opaque_cursor_token_01');
  });

  it('gets official company with encodeURIComponent and returns the company', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    const weirdId = 'gsco/alpha:beta';
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: { ...company, id: weirdId } }));

    const result = await createHttpClient().getOfficialCompany(weirdId);

    expect(result).toEqual({ ...company, id: weirdId });
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/app/v1/guideshop/companies/${encodeURIComponent(weirdId)}`,
    );
  });

  it('returns null only on exact not_found for getOfficialCompany', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: 'not_found', message: 'missing' } }, 404),
      )
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: 'access_denied', message: 'denied' } }, 403),
      )
      .mockResolvedValueOnce(
        jsonResponse(
          { error: { code: 'integration_disabled', message: 'disabled' } },
          503,
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse(
          { error: { code: 'temporarily_unavailable', message: 'outage' } },
          503,
        ),
      );

    await expect(createHttpClient().getOfficialCompany(company.id)).resolves.toBeNull();
    await expect(createHttpClient().getOfficialCompany(company.id)).rejects.toMatchObject({
      code: 'access_denied',
      status: 403,
    });
    await expect(createHttpClient().getOfficialCompany(company.id)).rejects.toMatchObject({
      code: 'integration_disabled',
      status: 503,
    });
    await expect(createHttpClient().getOfficialCompany(company.id)).rejects.toMatchObject({
      code: 'temporarily_unavailable',
      status: 503,
    });
  });

  it('does not convert list 503 to an empty result', async () => {
    __testSetSessionToken('tok');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: 'integration_disabled', message: 'disabled' } },
        503,
      ),
    );

    await expect(createHttpClient().listOfficialCompanies()).rejects.toMatchObject({
      code: 'integration_disabled',
      status: 503,
    });
  });

  it('applies existing 401 session recovery to an official request', async () => {
    window.Telegram = { WebApp: { initData: 'query_id=1&user=%7B%7D&hash=abc' } };
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ data: { session_token: 'fresh_tok', session_expires_at: null, user: {} } }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: 'auth_required', message: 'expired' } }, 401),
      )
      .mockResolvedValueOnce(
        jsonResponse({ data: { session_token: 'renewed_tok', session_expires_at: null, user: {} } }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          data: { companies: [company], page: { nextCursor: null } },
        }),
      );

    const result = await createHttpClient().listOfficialCompanies();

    expect(result.companies).toEqual([company]);
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/app/v1/session');
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/app/v1/guideshop/companies');
    expect(fetchMock.mock.calls[2]?.[0]).toBe('/app/v1/session');
    expect(fetchMock.mock.calls[3]?.[0]).toBe('/app/v1/guideshop/companies');
    const retryHeaders = fetchMock.mock.calls[3]?.[1]?.headers as Headers;
    expect(retryHeaders.get('Authorization')).toBe('Bearer renewed_tok');
  });
});

describe('official GuideShop mock parity', () => {
  beforeEach(() => {
    __resetMockStore();
  });

  it('returns deterministic official records and clones', async () => {
    const first = await mockClient.listOfficialCompanies();
    expect(first.page).toEqual({ nextCursor: null });
    expect(first.companies.length).toBeGreaterThanOrEqual(3);
    expect(first.companies.some((item) => item.phone !== null && item.address !== null)).toBe(
      true,
    );
    expect(
      first.companies.some(
        (item) =>
          item.phone === null &&
          item.address === null &&
          item.description === null &&
          item.type === null,
      ),
    ).toBe(true);
    expect(new Set(first.companies.map((item) => item.displayName)).size).toBe(
      first.companies.length,
    );

    const stored = __testOfficialCompanies();
    first.companies[0].displayName = 'mutated';
    const second = await mockClient.listOfficialCompanies();
    expect(second.companies[0]?.displayName).toBe(stored[0]?.displayName);
    expect(second.companies[0]?.displayName).not.toBe('mutated');
  });

  it('returns matching detail, null for missing, and keeps personal ids independent', async () => {
    const listed = await mockClient.listOfficialCompanies();
    const target = listed.companies[0];
    expect(target).toBeTruthy();

    const detail = await mockClient.getOfficialCompany(target.id);
    expect(detail).toEqual(target);
    detail!.displayName = 'mutated-detail';
    const again = await mockClient.getOfficialCompany(target.id);
    expect(again?.displayName).toBe(target.displayName);

    await expect(mockClient.getOfficialCompany('missing-official-id')).resolves.toBeNull();

    const places = await mockClient.listPersonalPlaces();
    const officialIds = new Set(listed.companies.map((item) => item.id));
    const personalIds = new Set(places.map((item) => item.id));
    for (const id of officialIds) {
      expect(id.startsWith('place_')).toBe(false);
      expect(personalIds.has(id)).toBe(false);
    }
    expect(__testPersonalPlaces().some((place) => officialIds.has(place.id))).toBe(false);
    expect(__testOfficialCompanies().some((company) => personalIds.has(company.id))).toBe(
      false,
    );
  });

  it('exposes no official-company mutation methods on GuideOsClient', () => {
    const client = mockClient as unknown as Record<string, unknown>;
    for (const method of [
      'createOfficialCompany',
      'updateOfficialCompany',
      'deactivateOfficialCompany',
      'deleteOfficialCompany',
      'createOfficialCommission',
      'listOfficialPoints',
      'listOfficialPayouts',
      'createOfficialVisit',
      'updateOfficialVisit',
      'deleteOfficialVisit',
      'createOfficialPoints',
      'createOfficialSale',
      'updateOfficialSale',
      'deleteOfficialSale',
      'createOfficialHistory',
      'getOfficialHistory',
    ]) {
      expect(client).not.toHaveProperty(method);
    }
    expect(typeof mockClient.listOfficialCompanies).toBe('function');
    expect(typeof mockClient.getOfficialCompany).toBe('function');
    expect(typeof mockClient.listOfficialVisits).toBe('function');
    expect(typeof mockClient.getOfficialVisit).toBe('function');
    expect(typeof mockClient.getOfficialPointsSummary).toBe('function');
    expect(typeof mockClient.listOfficialHistory).toBe('function');
    expect(mockClient).not.toHaveProperty('listOfficialSales');
    expect(mockClient).not.toHaveProperty('getOfficialSale');
  });
});

describe('official GuideShop visits API', () => {
  const visit = {
    id: 'gsvis_silk_01',
    companyId: 'gsco_silkroad_01',
    visitAt: '2026-08-10T09:00:00Z',
    status: 'completed',
    touristCount: 4,
    customerPaymentStatus: 'paid',
    customerPaidAt: '2026-08-10T11:30:00Z',
    createdAt: '2026-08-10T09:05:00Z',
    updatedAt: '2026-08-10T11:30:00Z',
    points: [{ amount: '10.00', unit: 'PTS', status: 'pending' }],
  };

  beforeEach(() => {
    __testClearSession();
    window.Telegram = { WebApp: { initData: '' } };
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('lists official visits from GET /app/v1/guideshop/visits with bearer token', async () => {
    __testSetSessionToken('tok_visits');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        data: { visits: [visit], page: { nextCursor: null } },
      }),
    );

    const result = await createHttpClient().listOfficialVisits();
    expect(result.visits).toEqual([visit]);
    expect(result.page).toEqual({ nextCursor: null });
    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/app/v1/guideshop/visits');
    expect(headers.get('Authorization')).toBe('Bearer tok_visits');
  });

  it('forwards opaque cursor query without decoding', async () => {
    __testSetSessionToken('tok_visits');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        data: { visits: [], page: { nextCursor: 'next_opaque' } },
      }),
    );

    await createHttpClient().listOfficialVisits({ cursor: 'opaque_page_two' });
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/app/v1/guideshop/visits?cursor=opaque_page_two',
    );
  });

  it('gets visit detail and maps not_found to null', async () => {
    __testSetSessionToken('tok_visits');
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ data: visit }))
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: 'not_found', message: 'Визит не найден.' } }, 404),
      );

    const client = createHttpClient();
    await expect(client.getOfficialVisit(visit.id)).resolves.toEqual(visit);
    await expect(client.getOfficialVisit('missing_visit_id')).resolves.toBeNull();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/app/v1/guideshop/visits/${encodeURIComponent(visit.id)}`,
    );
  });

  it('mock visits are deterministic and omit guide membership fields', async () => {
    __resetMockStore();
    const listed = await mockClient.listOfficialVisits();
    expect(listed.visits.length).toBeGreaterThan(0);
    expect(listed.page.nextCursor).toBeNull();
    for (const item of listed.visits) {
      expect(item).not.toHaveProperty('guideMembershipId');
      expect(item).not.toHaveProperty('guide_membership_id');
      expect(item.points).toBeUndefined();
    }
    const first = listed.visits[0]!;
    const detail = await mockClient.getOfficialVisit(first.id);
    expect(detail?.id).toBe(first.id);
    expect(Array.isArray(detail?.points)).toBe(true);
    await expect(mockClient.getOfficialVisit('missing_visit_xx')).resolves.toBeNull();
    expect(__testOfficialVisits().some((item) => item.id === first.id)).toBe(true);
  });
});

describe('official GuideShop points summary API', () => {
  const summary = {
    unit: 'PTS',
    pendingTotal: '12.50',
    creditedTotal: '4.00',
    companies: [
      {
        companyId: 'gsco_silkroad_01',
        displayName: 'Silk Road Emporium',
        pendingTotal: '10.00',
        creditedTotal: '3.00',
      },
    ],
  };

  beforeEach(() => {
    __testClearSession();
    window.Telegram = { WebApp: { initData: '' } };
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads points summary from GET /app/v1/guideshop/points/summary', async () => {
    __testSetSessionToken('tok_points');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ data: summary }));

    const result = await createHttpClient().getOfficialPointsSummary();
    expect(result).toEqual(summary);
    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/app/v1/guideshop/points/summary');
    expect(headers.get('Authorization')).toBe('Bearer tok_points');
  });

  it('mock points summary is deterministic and PTS-only', async () => {
    __resetMockStore();
    const result = await mockClient.getOfficialPointsSummary();
    expect(result.unit).toBe('PTS');
    expect(result.companies.length).toBeGreaterThan(0);
    expect(result).not.toHaveProperty('schema_version');
    expect(result.companies[0]).not.toHaveProperty('company_id');
    expect(__testOfficialPointsSummary().pendingTotal).toBe(result.pendingTotal);
  });
});

describe('official GuideShop sales API withdrawn', () => {
  it('does not expose sales methods on GuideOsClient', () => {
    const client = createHttpClient() as unknown as Record<string, unknown>;
    expect(client).not.toHaveProperty('listOfficialSales');
    expect(client).not.toHaveProperty('getOfficialSale');
    expect(mockClient as unknown as Record<string, unknown>).not.toHaveProperty(
      'listOfficialSales',
    );
    expect(mockClient as unknown as Record<string, unknown>).not.toHaveProperty(
      'getOfficialSale',
    );
  });
});

describe('official GuideShop history API', () => {
  const payout = {
    id: 'gspay_silk_01',
    pointsAccrualId: 'gsacc_silk_01',
    companyId: 'gsco_silkroad_01',
    visitId: 'gsvis_silk_01',
    amount: '3.00',
    unit: 'PTS',
    paidAt: '2026-08-12T10:00:00Z',
    createdAt: '2026-08-12T10:00:00Z',
  };

  beforeEach(() => {
    __testClearSession();
    window.Telegram = { WebApp: { initData: '' } };
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('lists official history from GET /app/v1/guideshop/history with bearer token', async () => {
    __testSetSessionToken('tok_history');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        data: { history: [payout], page: { nextCursor: null } },
      }),
    );

    const result = await createHttpClient().listOfficialHistory();
    expect(result.history).toEqual([payout]);
    expect(result.page).toEqual({ nextCursor: null });
    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/app/v1/guideshop/history');
    expect(headers.get('Authorization')).toBe('Bearer tok_history');
  });

  it('forwards opaque history cursor without decoding', async () => {
    __testSetSessionToken('tok_history');
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        data: { history: [], page: { nextCursor: 'next_opaque' } },
      }),
    );

    await createHttpClient().listOfficialHistory({ cursor: 'opaque_page_two' });
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/app/v1/guideshop/history?cursor=opaque_page_two',
    );
  });

  it('mock history is deterministic PTS payouts', async () => {
    __resetMockStore();
    const listed = await mockClient.listOfficialHistory();
    expect(listed.history.length).toBeGreaterThan(0);
    expect(listed.page.nextCursor).toBeNull();
    for (const item of listed.history) {
      expect(item.unit).toBe('PTS');
      expect(typeof item.amount).toBe('string');
      expect(item).not.toHaveProperty('payout_id');
    }
    expect(__testOfficialHistory().some((item) => item.id === listed.history[0]!.id)).toBe(
      true,
    );
  });
});

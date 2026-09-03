import {
  API_BASE_URL,
  DEV_USER_ID,
  ENTRIES_RANGE_FROM,
  ENTRIES_RANGE_TO,
} from '@/config';
import type { GuideOsClient, WriteOptions } from './client';
import type {
  AvailabilityPreview,
  AvailabilityPreviewParams,
  CalendarEntry,
  DayOffFormValues,
  GuideProfile,
  GuideProfilePatch,
  ListPersonalCommissionsOptions,
  ListPersonalPlacesOptions,
  PersonalCommission,
  PersonalCommissionInput,
  PersonalPlace,
  PersonalPlaceInput,
  ReportsSummary,
  ReportsSummaryParams,
  TourFormValues,
} from './types';

const SESSION_KEY = 'guide_os_session_token';

interface ApiEnvelope<T> {
  data?: T;
  error?: { code: string; message: string; details?: ConflictDetails };
}

interface ConflictDetails {
  conflict_kind: string;
  date: string;
  existing_entry: CalendarEntry;
  ack_field?: string;
  reason_code?: string;
}

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export class ApiConflictError extends ApiError {
  constructor(
    code: string,
    message: string,
    public readonly details: ConflictDetails,
  ) {
    super(code, message, 409);
    this.name = 'ApiConflictError';
  }
}

let sessionToken: string | null = null;
let bootstrapPromise: Promise<void> | null = null;
let initDataBootstrapDone = false;

function hasTelegramInitData(): boolean {
  return Boolean(window.Telegram?.WebApp?.initData?.trim());
}

function readStoredToken(): string | null {
  try {
    return sessionStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

function persistToken(token: string | null): void {
  sessionToken = token;
  try {
    if (token) sessionStorage.setItem(SESSION_KEY, token);
    else sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
}

function clearSession(): void {
  persistToken(null);
}

async function bootstrapSession(options?: { forceInitData?: boolean }): Promise<void> {
  const forceInitData = options?.forceInitData ?? false;
  const initData = window.Telegram?.WebApp?.initData?.trim();

  if (initData) {
    if (!forceInitData && initDataBootstrapDone) {
      return;
    }

    const res = await fetch(`${API_BASE_URL}/app/v1/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ init_data: initData }),
    });
    const json = (await res.json()) as ApiEnvelope<{ session_token: string }>;
    if (!res.ok || !json.data?.session_token) {
      const err = json.error;
      throw new ApiError(
        err?.code ?? 'auth_invalid',
        err?.message ?? 'Не удалось создать сессию.',
        res.status,
      );
    }
    persistToken(json.data.session_token);
    initDataBootstrapDone = true;
    return;
  }

  if (!forceInitData) {
    const stored = readStoredToken();
    if (stored) {
      sessionToken = stored;
      return;
    }
  }

  const body: Record<string, string> = DEV_USER_ID ? { dev_user_id: DEV_USER_ID } : {};

  if (!body.dev_user_id) {
    throw new ApiError(
      'auth_required',
      'Нет Telegram initData. Укажите VITE_DEV_USER_ID для локальной разработки.',
      401,
    );
  }

  const res = await fetch(`${API_BASE_URL}/app/v1/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const json = (await res.json()) as ApiEnvelope<{ session_token: string }>;
  if (!res.ok || !json.data?.session_token) {
    const err = json.error;
    throw new ApiError(
      err?.code ?? 'auth_invalid',
      err?.message ?? 'Не удалось создать сессию.',
      res.status,
    );
  }
  persistToken(json.data.session_token);
}

async function ensureSession(options?: { forceInitData?: boolean }): Promise<void> {
  const forceInitData = options?.forceInitData ?? false;
  const initDataPresent = hasTelegramInitData();

  if (
    sessionToken &&
    !forceInitData &&
    (initDataPresent ? initDataBootstrapDone : true)
  ) {
    return;
  }

  if (!bootstrapPromise) {
    bootstrapPromise = bootstrapSession({ forceInitData }).finally(() => {
      bootstrapPromise = null;
    });
  }
  await bootstrapPromise;
}

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

function tourBody(form: TourFormValues, options?: WriteOptions): Record<string, unknown> {
  return {
    ...form,
    ack_date_warning: Boolean(options?.ackDateWarning),
  };
}

function dayOffBody(form: DayOffFormValues, options?: WriteOptions): Record<string, unknown> {
  return {
    startDate: form.startDate,
    endDate: form.endDate,
    ack_date_warning: Boolean(options?.ackDateWarning),
  };
}

async function apiRequest<T>(
  path: string,
  init: RequestInit & { skipAuth?: boolean } = {},
): Promise<T> {
  const { skipAuth, ...fetchInit } = init;
  if (!skipAuth) await ensureSession();

  const headers = new Headers(fetchInit.headers);
  if (!headers.has('Content-Type') && fetchInit.body) {
    headers.set('Content-Type', 'application/json');
  }
  if (!skipAuth && sessionToken) {
    headers.set('Authorization', `Bearer ${sessionToken}`);
  }

  const doFetch = () =>
    fetch(`${API_BASE_URL}${path}`, {
      ...fetchInit,
      headers,
    });

  let res = await doFetch();
  if (!skipAuth && res.status === 401 && sessionToken) {
    clearSession();
    await ensureSession({ forceInitData: true });
    headers.set('Authorization', `Bearer ${sessionToken}`);
    res = await doFetch();
  }

  const json = (await res.json()) as ApiEnvelope<T>;
  if (!res.ok) {
    const err = json.error;
    const code = err?.code ?? 'internal_error';
    const message = err?.message ?? 'Ошибка запроса.';
    const details = err?.details;
    if (res.status === 409 && details?.conflict_kind && details.existing_entry) {
      throw new ApiConflictError(code, message, details);
    }
    throw new ApiError(code, message, res.status);
  }
  if (json.data === undefined) {
    throw new ApiError('internal_error', 'Пустой ответ сервера.', res.status);
  }
  return json.data;
}

export function createHttpClient(): GuideOsClient {
  return {
    async listEntries() {
      const data = await apiRequest<{ entries: CalendarEntry[] }>(
        `/app/v1/entries?from=${ENTRIES_RANGE_FROM}&to=${ENTRIES_RANGE_TO}`,
      );
      return data.entries;
    },

    async getEntry(id: string) {
      try {
        return await apiRequest<CalendarEntry>(`/app/v1/entries/${encodeURIComponent(id)}`);
      } catch (e) {
        if (e instanceof ApiError && e.code === 'not_found') return null;
        throw e;
      }
    },

    async createTour(form: TourFormValues, options?: WriteOptions) {
      return apiRequest<CalendarEntry>('/app/v1/tours', {
        method: 'POST',
        headers: { 'Idempotency-Key': newIdempotencyKey() },
        body: JSON.stringify(tourBody(form, options)),
      });
    },

    async updateTour(id: string, form: TourFormValues, options?: WriteOptions) {
      return apiRequest<CalendarEntry>(`/app/v1/entries/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        headers: { 'Idempotency-Key': newIdempotencyKey() },
        body: JSON.stringify(tourBody(form, options)),
      });
    },

    async createDayOff(form: DayOffFormValues, options?: WriteOptions) {
      return apiRequest<CalendarEntry>('/app/v1/day-offs', {
        method: 'POST',
        headers: { 'Idempotency-Key': newIdempotencyKey() },
        body: JSON.stringify(dayOffBody(form, options)),
      });
    },

    async deleteEntry(id: string) {
      await apiRequest<Record<string, never>>(`/app/v1/entries/${encodeURIComponent(id)}`, {
        method: 'DELETE',
        headers: { 'Idempotency-Key': newIdempotencyKey() },
      });
    },

    async updateDayLocations(id: string, locations: Record<string, string>) {
      return apiRequest<CalendarEntry>(`/app/v1/entries/${encodeURIComponent(id)}/day-locations`, {
        method: 'PATCH',
        headers: { 'Idempotency-Key': newIdempotencyKey() },
        body: JSON.stringify({ locations }),
      });
    },

    async getProfile() {
      return apiRequest<GuideProfile>('/app/v1/profile');
    },

    async updateProfile(patch: GuideProfilePatch) {
      return apiRequest<GuideProfile>('/app/v1/profile', {
        method: 'PATCH',
        headers: { 'Idempotency-Key': newIdempotencyKey() },
        body: JSON.stringify(patch),
      });
    },

    async getReportsSummary(params: ReportsSummaryParams) {
      const query = new URLSearchParams({
        from: params.from,
        to: params.to,
        status: params.status,
        payment: params.payment,
      });
      if (params.company) query.set('company', params.company);
      if (params.location) query.set('location', params.location);
      return apiRequest<ReportsSummary>(`/app/v1/reports/summary?${query.toString()}`);
    },

    async previewAvailability(params: AvailabilityPreviewParams) {
      return apiRequest<AvailabilityPreview>('/app/v1/availability/preview', {
        method: 'POST',
        body: JSON.stringify({
          from: params.from,
          to: params.to,
          format: params.format ?? 'text',
        }),
      });
    },

    async listPersonalPlaces(options?: ListPersonalPlacesOptions) {
      const path =
        options?.includeInactive === true
          ? '/app/v1/personal-places?includeInactive=true'
          : '/app/v1/personal-places';
      const data = await apiRequest<{ places: PersonalPlace[] }>(path);
      return data.places;
    },

    async getPersonalPlace(id: string) {
      try {
        return await apiRequest<PersonalPlace>(
          `/app/v1/personal-places/${encodeURIComponent(id)}`,
        );
      } catch (e) {
        if (e instanceof ApiError && e.code === 'not_found') return null;
        throw e;
      }
    },

    async createPersonalPlace(input: PersonalPlaceInput) {
      return apiRequest<PersonalPlace>('/app/v1/personal-places', {
        method: 'POST',
        headers: { 'Idempotency-Key': newIdempotencyKey() },
        body: JSON.stringify(input),
      });
    },

    async updatePersonalPlace(id: string, input: PersonalPlaceInput) {
      return apiRequest<PersonalPlace>(
        `/app/v1/personal-places/${encodeURIComponent(id)}`,
        {
          method: 'PUT',
          headers: { 'Idempotency-Key': newIdempotencyKey() },
          body: JSON.stringify(input),
        },
      );
    },

    async deactivatePersonalPlace(id: string) {
      await apiRequest<Record<string, never>>(
        `/app/v1/personal-places/${encodeURIComponent(id)}/deactivate`,
        {
          method: 'POST',
          headers: { 'Idempotency-Key': newIdempotencyKey() },
        },
      );
    },

    async listPersonalCommissions(placeId: string, options?: ListPersonalCommissionsOptions) {
      const base = `/app/v1/personal-places/${encodeURIComponent(placeId)}/commissions`;
      const path = options?.includeInactive === true ? `${base}?includeInactive=true` : base;
      const data = await apiRequest<{ commissions: PersonalCommission[] }>(path);
      return data.commissions;
    },

    async getPersonalCommission(id: string) {
      try {
        return await apiRequest<PersonalCommission>(
          `/app/v1/personal-commissions/${encodeURIComponent(id)}`,
        );
      } catch (e) {
        if (e instanceof ApiError && e.code === 'not_found') return null;
        throw e;
      }
    },

    async createPersonalCommission(placeId: string, input: PersonalCommissionInput) {
      return apiRequest<PersonalCommission>(
        `/app/v1/personal-places/${encodeURIComponent(placeId)}/commissions`,
        {
          method: 'POST',
          headers: { 'Idempotency-Key': newIdempotencyKey() },
          body: JSON.stringify(input),
        },
      );
    },

    async updatePersonalCommission(id: string, input: PersonalCommissionInput) {
      return apiRequest<PersonalCommission>(
        `/app/v1/personal-commissions/${encodeURIComponent(id)}`,
        {
          method: 'PUT',
          headers: { 'Idempotency-Key': newIdempotencyKey() },
          body: JSON.stringify(input),
        },
      );
    },

    async deactivatePersonalCommission(id: string) {
      await apiRequest<Record<string, never>>(
        `/app/v1/personal-commissions/${encodeURIComponent(id)}/deactivate`,
        {
          method: 'POST',
          headers: { 'Idempotency-Key': newIdempotencyKey() },
        },
      );
    },
  };
}

/** Test-only helpers */
export function __testClearSession(): void {
  clearSession();
  initDataBootstrapDone = false;
}

export function __testSetSessionToken(token: string): void {
  persistToken(token);
}

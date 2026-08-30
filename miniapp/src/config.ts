export const TIMEZONE = 'Asia/Tashkent';

/** Default true — set VITE_USE_MOCK_API=false to call Guide OS Web API. */
export const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API !== 'false';

const FIXED_MOCK_TODAY = '2026-08-28';

function todayInBusinessTimezone(): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const value = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? '';
  return `${value('year')}-${value('month')}-${value('day')}`;
}

/** Fixed in mock mode; real Asia/Tashkent date in HTTP mode. */
export const MOCK_TODAY = USE_MOCK_API ? FIXED_MOCK_TODAY : todayInBusinessTimezone();

/** Empty string = same origin (Vite dev proxy → guide_os_miniapp_api.py). */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? '';

/** Dev-only session bootstrap when API runs with MINI_APP_API_DEV_AUTH=true. */
export const DEV_USER_ID = (import.meta.env.VITE_DEV_USER_ID as string | undefined)?.trim() || '';

export const ENTRIES_RANGE_FROM = '2020-01-01';
export const ENTRIES_RANGE_TO = '2030-12-31';

export interface TelegramWebApp {
  initData?: string;
  ready?: () => void;
  expand?: () => void;
}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp;
    };
  }
}

let initialized = false;

/**
 * Signal readiness and request maximum standard Mini App height in Telegram.
 * Idempotent: safe under React StrictMode double-mount and repeated calls.
 */
export function initializeTelegramWebApp(): void {
  if (initialized) return;

  const webApp = window.Telegram?.WebApp;
  if (!webApp) return;

  initialized = true;

  try {
    webApp.ready?.();
    webApp.expand?.();
  } catch {
    /* Telegram SDK unavailable or threw — continue without Mini App integration */
  }
}

/** Test-only: reset idempotent guard between test cases. */
export function __testResetTelegramWebAppInit(): void {
  initialized = false;
}

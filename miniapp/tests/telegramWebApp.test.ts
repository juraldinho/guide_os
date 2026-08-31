// @ts-nocheck — read source at runtime; Node built-ins are not in app tsconfig.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  __testResetTelegramWebAppInit,
  initializeTelegramWebApp,
} from '@/telegram/webApp';

const WEB_APP_SOURCE = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../src/telegram/webApp.ts'),
  'utf8',
);

describe('initializeTelegramWebApp', () => {
  beforeEach(() => {
    __testResetTelegramWebAppInit();
    delete (window as { Telegram?: unknown }).Telegram;
  });

  afterEach(() => {
    __testResetTelegramWebAppInit();
    delete (window as { Telegram?: unknown }).Telegram;
  });

  it('calls ready() and expand() when Telegram WebApp is available', () => {
    const ready = vi.fn();
    const expand = vi.fn();
    window.Telegram = { WebApp: { ready, expand } };

    initializeTelegramWebApp();

    expect(ready).toHaveBeenCalledTimes(1);
    expect(expand).toHaveBeenCalledTimes(1);
  });

  it('calls ready() before expand()', () => {
    const order: string[] = [];
    const ready = vi.fn(() => order.push('ready'));
    const expand = vi.fn(() => order.push('expand'));
    window.Telegram = { WebApp: { ready, expand } };

    initializeTelegramWebApp();

    expect(order).toEqual(['ready', 'expand']);
  });

  it('does not throw when window.Telegram is missing', () => {
    expect(() => initializeTelegramWebApp()).not.toThrow();
  });

  it('does not throw when ready or expand are missing', () => {
    window.Telegram = { WebApp: { initData: 'hash=abc' } };
    expect(() => initializeTelegramWebApp()).not.toThrow();

    __testResetTelegramWebAppInit();
    window.Telegram = { WebApp: { ready: vi.fn() } };
    expect(() => initializeTelegramWebApp()).not.toThrow();
  });

  it('is idempotent under repeated initialization', () => {
    const ready = vi.fn();
    const expand = vi.fn();
    window.Telegram = { WebApp: { ready, expand } };

    initializeTelegramWebApp();
    initializeTelegramWebApp();

    expect(ready).toHaveBeenCalledTimes(1);
    expect(expand).toHaveBeenCalledTimes(1);
  });

  it('does not use requestFullscreen or disableVerticalSwipes', () => {
    expect(WEB_APP_SOURCE).not.toMatch(/requestFullscreen/);
    expect(WEB_APP_SOURCE).not.toMatch(/disableVerticalSwipes/);
  });
});

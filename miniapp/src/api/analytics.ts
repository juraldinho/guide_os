import { guideOsClient } from './createClient';
import type { MiniAppAnalyticsEventName } from './types';

export function trackMiniAppEvent(name: MiniAppAnalyticsEventName): void {
  void guideOsClient.trackAnalyticsEvent(name).catch(() => {
    // Analytics is best-effort and must never affect product behavior.
  });
}

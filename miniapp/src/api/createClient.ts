import { USE_MOCK_API } from '@/config';
import type { GuideOsClient } from './client';
import { createHttpClient } from './httpClient';
import { mockClient } from './mock/store';

export function createGuideOsClient(): GuideOsClient {
  if (USE_MOCK_API) return mockClient;
  return createHttpClient();
}

export const guideOsClient = createGuideOsClient();

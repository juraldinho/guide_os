import type { GuideOsClient } from '../client';
import type { CalendarEntry, DayOffFormValues, GuideProfile, TourFormValues } from '../types';
import { INITIAL_ENTRIES, MOCK_PROFILE } from './data';

let nextId = 10;
const entries: CalendarEntry[] = INITIAL_ENTRIES.map((e) => ({ ...e }));
let profile: GuideProfile = { ...MOCK_PROFILE, types: MOCK_PROFILE.types.map((t) => ({ ...t, geo: [...t.geo] })) };

function tourFromForm(form: TourFormValues): Omit<CalendarEntry, 'id'> {
  return {
    type: 'tour',
    title: form.title.trim(),
    company: form.company,
    location: form.location,
    startDate: form.startDate,
    endDate: form.endDate || form.startDate,
    startTime: form.useTime ? form.startTime : null,
    endTime: form.useTime ? form.endTime : null,
    status: form.status,
    payment: form.payment,
    income: form.income,
    note: form.note,
    source: 'Mini App',
  };
}

export const mockClient: GuideOsClient = {
  async listEntries() {
    return entries.map((e) => ({ ...e }));
  },

  async getEntry(id: string) {
    const entry = entries.find((e) => e.id === id);
    return entry ? { ...entry } : null;
  },

  async createTour(form: TourFormValues) {
    const entry: CalendarEntry = { ...tourFromForm(form), id: `t${nextId++}` };
    entries.push(entry);
    return { ...entry };
  },

  async updateTour(id: string, form: TourFormValues) {
    const idx = entries.findIndex((e) => e.id === id);
    if (idx < 0) throw new Error('Tour not found');
    entries[idx] = { ...entries[idx], ...tourFromForm(form), id };
    return { ...entries[idx] };
  },

  async createDayOff(form: DayOffFormValues) {
    const entry: CalendarEntry = {
      id: `d${nextId++}`,
      type: 'day_off',
      title: 'Выходной',
      startDate: form.startDate,
      endDate: form.endDate,
      startTime: null,
      endTime: null,
      income: 0,
      source: 'Mini App',
    };
    entries.push(entry);
    return { ...entry };
  },

  async deleteEntry(id: string) {
    const idx = entries.findIndex((e) => e.id === id);
    if (idx >= 0) entries.splice(idx, 1);
  },

  async updateDayLocations(id: string, locations: Record<string, string>) {
    const entry = entries.find((e) => e.id === id);
    if (!entry) throw new Error('Tour not found');
    entry.dayLocations = { ...locations };
    return { ...entry };
  },

  async getProfile() {
    return {
      ...profile,
      types: profile.types.map((t) => ({ ...t, geo: [...t.geo] })),
      notifications: { ...profile.notifications },
    };
  },

  async updateProfile(patch: Partial<GuideProfile>) {
    if (patch.name !== undefined) profile.name = patch.name;
    if (patch.telegramId !== undefined) profile.telegramId = patch.telegramId;
    if (patch.types !== undefined) profile.types = patch.types.map((t) => ({ ...t, geo: [...t.geo] }));
    if (patch.notifications !== undefined) {
      profile.notifications = { ...profile.notifications, ...patch.notifications };
    }
    return mockClient.getProfile();
  },
};

/** Test-only access to in-memory entries */
export function __testEntries(): CalendarEntry[] {
  return entries;
}

export function __resetMockStore() {
  entries.length = 0;
  entries.push(...INITIAL_ENTRIES.map((e) => ({ ...e })));
  nextId = 10;
  profile = {
    ...MOCK_PROFILE,
    types: MOCK_PROFILE.types.map((t) => ({ ...t, geo: [...t.geo] })),
    notifications: { ...MOCK_PROFILE.notifications },
  };
}

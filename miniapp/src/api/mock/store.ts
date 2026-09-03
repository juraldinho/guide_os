import type { GuideOsClient, GuideShopReadOptions, WriteOptions } from '../client';
import type {
  AvailabilityPreviewParams,
  CalendarEntry,
  DayOffFormValues,
  GuideProfile,
  GuideProfilePatch,
  GuideTypeCode,
  ListPersonalCommissionsOptions,
  ListPersonalPlacesOptions,
  ListOfficialVisitsOptions,
  ListOfficialHistoryOptions,
  OfficialCompany,
  OfficialHistoryItem,
  OfficialPointsSummary,
  OfficialVisit,
  OfficialVisitPoint,
  PersonalCommission,
  PersonalCommissionInput,
  PersonalPlace,
  PersonalPlaceInput,
  ReportsSummaryParams,
  TourFormValues,
} from '../types';
import { buildAvailabilityPreview } from '@/features/reports/lib/availability';
import { calcSummary } from '@/features/reports/lib/summary';
import { INITIAL_ENTRIES, MOCK_PROFILE } from './data';

const MOCK_GUIDE_TYPE_LABELS: Record<GuideTypeCode, string> = {
  local: 'Локальный гид',
  route: 'Маршрутный гид',
  accompanying: 'Сопровождающий гид',
};

const PLACE_A = 'place_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const PLACE_B = 'place_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

const OFFICIAL_A = 'gsco_silkroad_01';
const OFFICIAL_B = 'gsco_nullfields_02';
const OFFICIAL_C = 'gsco_ceramic_shop_03';

const INITIAL_OFFICIAL_COMPANIES: OfficialCompany[] = [
  {
    id: OFFICIAL_A,
    displayName: 'Silk Road Emporium',
    status: 'active',
    phone: '+998901112233',
    address: 'Registan Square, Samarkand',
    description: 'Official GuideShop partner for crafts and textiles',
    type: 'shop',
  },
  {
    id: OFFICIAL_B,
    displayName: 'Bukhara Courtyard Cafe',
    status: 'inactive',
    phone: null,
    address: null,
    description: null,
    type: null,
  },
  {
    id: OFFICIAL_C,
    displayName: 'Khiva Ceramic Workshop',
    status: 'active',
    phone: '+998933334455',
    address: 'Ichan-Kala, Khiva',
    description: 'Handmade ceramics for tour groups',
    type: 'workshop',
  },
];

const VISIT_A = 'gsvis_silk_01';
const VISIT_B = 'gsvis_silk_02';
const VISIT_C = 'gsvis_khiva_03';

const INITIAL_OFFICIAL_VISITS: OfficialVisit[] = [
  {
    id: VISIT_A,
    companyId: OFFICIAL_A,
    visitAt: '2026-08-10T09:00:00Z',
    status: 'completed',
    touristCount: 4,
    customerPaymentStatus: 'paid',
    customerPaidAt: '2026-08-10T11:30:00Z',
    createdAt: '2026-08-10T09:05:00Z',
    updatedAt: '2026-08-10T11:30:00Z',
  },
  {
    id: VISIT_B,
    companyId: OFFICIAL_A,
    visitAt: '2026-08-18T14:00:00Z',
    status: 'active',
    touristCount: 2,
    customerPaymentStatus: 'unpaid',
    customerPaidAt: null,
    createdAt: '2026-08-18T14:05:00Z',
    updatedAt: '2026-08-18T14:05:00Z',
  },
  {
    id: VISIT_C,
    companyId: OFFICIAL_C,
    visitAt: '2026-08-20T08:30:00Z',
    status: 'cancelled',
    touristCount: 0,
    customerPaymentStatus: 'unpaid',
    customerPaidAt: null,
    createdAt: '2026-08-20T08:35:00Z',
    updatedAt: '2026-08-20T09:00:00Z',
  },
];

const INITIAL_OFFICIAL_POINTS_SUMMARY: OfficialPointsSummary = {
  unit: 'PTS',
  pendingTotal: '12.50',
  creditedTotal: '4.00',
  companies: [
    {
      companyId: OFFICIAL_A,
      displayName: 'Silk Road Emporium',
      pendingTotal: '10.00',
      creditedTotal: '3.00',
    },
    {
      companyId: OFFICIAL_C,
      displayName: 'Khiva Ceramic Workshop',
      pendingTotal: '2.50',
      creditedTotal: '1.00',
    },
  ],
};

const INITIAL_OFFICIAL_VISIT_POINTS: Record<string, OfficialVisitPoint[]> = {
  [VISIT_A]: [{ amount: '10.00', unit: 'PTS', status: 'pending' }],
  [VISIT_B]: [],
  [VISIT_C]: [{ amount: '2.50', unit: 'PTS', status: 'credited' }],
};

const PAYOUT_A = 'gspay_silk_01';
const PAYOUT_B = 'gspay_khiva_02';

const INITIAL_OFFICIAL_HISTORY: OfficialHistoryItem[] = [
  {
    id: PAYOUT_A,
    pointsAccrualId: 'gsacc_silk_01',
    companyId: OFFICIAL_A,
    visitId: VISIT_A,
    amount: '3.00',
    unit: 'PTS',
    paidAt: '2026-08-12T10:00:00Z',
    createdAt: '2026-08-12T10:00:00Z',
  },
  {
    id: PAYOUT_B,
    pointsAccrualId: 'gsacc_khiva_02',
    companyId: OFFICIAL_C,
    visitId: VISIT_C,
    amount: '1.00',
    unit: 'PTS',
    paidAt: '2026-08-21T08:00:00Z',
    createdAt: '2026-08-21T08:00:00Z',
  },
];

const INITIAL_PERSONAL_PLACES: PersonalPlace[] = [
  {
    id: PLACE_A,
    name: 'Бухара Арт',
    category: 'Магазин',
    generalLocation: 'Бухара',
    landmark: 'Рядом с Ляби-Хауз',
    note: 'Личная компания для учёта комиссий',
    status: 'active',
    createdAt: '2026-08-01T10:00:00Z',
    updatedAt: '2026-08-01T10:00:00Z',
  },
  {
    id: PLACE_B,
    name: 'Restaurant Platan',
    category: 'Ресторан',
    generalLocation: 'Самарканд',
    landmark: null,
    note: null,
    status: 'active',
    createdAt: '2026-08-02T10:00:00Z',
    updatedAt: '2026-08-02T10:00:00Z',
  },
];

const INITIAL_PERSONAL_COMMISSIONS: PersonalCommission[] = [
  {
    id: 'entry_11111111111111111111111111111111',
    placeId: PLACE_A,
    occurredAt: '2026-08-10T05:00:00Z',
    purchaseAmountMinor: null,
    receivedIncomeMinor: null,
    receivedPoints: 15,
    currency: null,
    note: 'Первая комиссия',
    status: 'active',
    createdAt: '2026-08-10T06:00:00Z',
    updatedAt: '2026-08-10T06:00:00Z',
  },
  {
    id: 'entry_22222222222222222222222222222222',
    placeId: PLACE_A,
    occurredAt: '2026-08-12T05:00:00Z',
    purchaseAmountMinor: null,
    receivedIncomeMinor: null,
    receivedPoints: 40,
    currency: null,
    note: 'Вторая комиссия',
    status: 'active',
    createdAt: '2026-08-12T06:00:00Z',
    updatedAt: '2026-08-12T06:00:00Z',
  },
  {
    id: 'entry_33333333333333333333333333333333',
    placeId: PLACE_B,
    occurredAt: '2026-08-14T05:00:00Z',
    purchaseAmountMinor: null,
    receivedIncomeMinor: null,
    receivedPoints: 25,
    currency: null,
    note: 'Комиссия Platan',
    status: 'active',
    createdAt: '2026-08-14T06:00:00Z',
    updatedAt: '2026-08-14T06:00:00Z',
  },
  {
    id: 'entry_44444444444444444444444444444444',
    placeId: PLACE_A,
    occurredAt: '2026-08-05T05:00:00Z',
    purchaseAmountMinor: null,
    receivedIncomeMinor: null,
    receivedPoints: 10,
    currency: null,
    note: 'Неактивная запись',
    status: 'inactive',
    createdAt: '2026-08-05T06:00:00Z',
    updatedAt: '2026-08-05T07:00:00Z',
  },
];

function cloneProfile(source: GuideProfile): GuideProfile {
  return {
    ...source,
    types: source.types.map((t) => ({ ...t, geo: [...t.geo] })),
    languages: [...source.languages],
    notifications: { ...source.notifications },
  };
}

function clonePlace(place: PersonalPlace): PersonalPlace {
  return { ...place };
}

function cloneOfficialCompany(company: OfficialCompany): OfficialCompany {
  return { ...company };
}

function cloneOfficialVisit(visit: OfficialVisit): OfficialVisit {
  return {
    ...visit,
    points: visit.points?.map((point) => ({ ...point })),
  };
}

function cloneOfficialPointsSummary(summary: OfficialPointsSummary): OfficialPointsSummary {
  return {
    ...summary,
    companies: summary.companies.map((item) => ({ ...item })),
  };
}

function cloneOfficialHistoryItem(item: OfficialHistoryItem): OfficialHistoryItem {
  return { ...item };
}

function cloneCommission(item: PersonalCommission): PersonalCommission {
  return { ...item };
}

function utcNow(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
}

let nextId = 10;
let nextPlaceSeq = 12;
let nextCommissionSeq = 20;
const entries: CalendarEntry[] = INITIAL_ENTRIES.map((e) => ({ ...e }));
let profile: GuideProfile = cloneProfile(MOCK_PROFILE);
let personalPlaces: PersonalPlace[] = INITIAL_PERSONAL_PLACES.map(clonePlace);
let personalCommissions: PersonalCommission[] = INITIAL_PERSONAL_COMMISSIONS.map(cloneCommission);
let officialCompanies: OfficialCompany[] = INITIAL_OFFICIAL_COMPANIES.map(cloneOfficialCompany);
let officialVisits: OfficialVisit[] = INITIAL_OFFICIAL_VISITS.map(cloneOfficialVisit);
let officialPointsSummary: OfficialPointsSummary = cloneOfficialPointsSummary(
  INITIAL_OFFICIAL_POINTS_SUMMARY,
);
let officialHistory: OfficialHistoryItem[] = INITIAL_OFFICIAL_HISTORY.map(
  cloneOfficialHistoryItem,
);

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

function nextPlaceId(): string {
  const hex = nextPlaceSeq.toString(16).padStart(32, 'c');
  nextPlaceSeq += 1;
  return `place_${hex}`;
}

function nextCommissionId(): string {
  const hex = nextCommissionSeq.toString(16).padStart(32, 'e');
  nextCommissionSeq += 1;
  return `entry_${hex}`;
}

export const mockClient: GuideOsClient = {
  async listEntries() {
    return entries.map((e) => ({ ...e }));
  },

  async getEntry(id: string) {
    const entry = entries.find((e) => e.id === id);
    return entry ? { ...entry } : null;
  },

  async createTour(form: TourFormValues, _options?: WriteOptions) {
    const entry: CalendarEntry = { ...tourFromForm(form), id: `t${nextId++}` };
    entries.push(entry);
    return { ...entry };
  },

  async updateTour(id: string, form: TourFormValues, _options?: WriteOptions) {
    const idx = entries.findIndex((e) => e.id === id);
    if (idx < 0) throw new Error('Tour not found');
    entries[idx] = { ...entries[idx], ...tourFromForm(form), id };
    return { ...entries[idx] };
  },

  async createDayOff(form: DayOffFormValues, _options?: WriteOptions) {
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
    return cloneProfile(profile);
  },

  async updateProfile(patch: GuideProfilePatch) {
    if (patch.name !== undefined) profile.name = patch.name;
    if (patch.types !== undefined) {
      profile.types = patch.types.map((t) => ({
        type: t.type,
        label: MOCK_GUIDE_TYPE_LABELS[t.type],
        geo: [...t.geo],
        allUzbekistan: t.allUzbekistan,
      }));
    }
    if (patch.languages !== undefined) profile.languages = [...patch.languages];
    if (patch.notifications !== undefined) {
      profile.notifications = { ...profile.notifications, ...patch.notifications };
    }
    return mockClient.getProfile();
  },

  async getReportsSummary(params: ReportsSummaryParams) {
    const summary = calcSummary(entries, { from: params.from, to: params.to }, {
      status: params.status,
      payment: params.payment,
      company: params.company ?? '',
      location: params.location ?? '',
    });
    return {
      ...summary,
      period: { from: params.from, to: params.to },
    };
  },

  async previewAvailability(params: AvailabilityPreviewParams) {
    return buildAvailabilityPreview(entries, params.from, params.to);
  },

  async listPersonalPlaces(options?: ListPersonalPlacesOptions) {
    const includeInactive = options?.includeInactive === true;
    return personalPlaces
      .filter((place) => includeInactive || place.status === 'active')
      .map(clonePlace);
  },

  async getPersonalPlace(id: string) {
    const place = personalPlaces.find((item) => item.id === id);
    return place ? clonePlace(place) : null;
  },

  async createPersonalPlace(input: PersonalPlaceInput) {
    const now = utcNow();
    const place: PersonalPlace = {
      id: nextPlaceId(),
      name: input.name,
      category: input.category,
      generalLocation: input.generalLocation,
      landmark: input.landmark,
      note: input.note,
      status: 'active',
      createdAt: now,
      updatedAt: now,
    };
    personalPlaces.push(place);
    return clonePlace(place);
  },

  async updatePersonalPlace(id: string, input: PersonalPlaceInput) {
    const idx = personalPlaces.findIndex((item) => item.id === id && item.status === 'active');
    if (idx < 0) throw new Error('Personal place not found');
    personalPlaces[idx] = {
      ...personalPlaces[idx],
      name: input.name,
      category: input.category,
      generalLocation: input.generalLocation,
      landmark: input.landmark,
      note: input.note,
      updatedAt: utcNow(),
    };
    return clonePlace(personalPlaces[idx]);
  },

  async deactivatePersonalPlace(id: string) {
    const place = personalPlaces.find((item) => item.id === id && item.status === 'active');
    if (!place) throw new Error('Personal place not found');
    place.status = 'inactive';
    place.updatedAt = utcNow();
  },

  async listPersonalCommissions(placeId: string, options?: ListPersonalCommissionsOptions) {
    const includeInactive = options?.includeInactive === true;
    return personalCommissions
      .filter((item) => item.placeId === placeId)
      .filter((item) => includeInactive || item.status === 'active')
      .map(cloneCommission);
  },

  async getPersonalCommission(id: string) {
    const item = personalCommissions.find((entry) => entry.id === id);
    return item ? cloneCommission(item) : null;
  },

  async createPersonalCommission(placeId: string, input: PersonalCommissionInput) {
    const parent = personalPlaces.find((place) => place.id === placeId && place.status === 'active');
    if (!parent) throw new Error('Personal place not found');
    const now = utcNow();
    const created: PersonalCommission = {
      id: nextCommissionId(),
      placeId,
      occurredAt: input.occurredAt,
      purchaseAmountMinor: input.purchaseAmountMinor,
      receivedIncomeMinor: input.receivedIncomeMinor,
      receivedPoints: input.receivedPoints,
      currency: input.currency,
      note: input.note,
      status: 'active',
      createdAt: now,
      updatedAt: now,
    };
    personalCommissions.push(created);
    return cloneCommission(created);
  },

  async updatePersonalCommission(id: string, input: PersonalCommissionInput) {
    const idx = personalCommissions.findIndex(
      (item) => item.id === id && item.status === 'active',
    );
    if (idx < 0) throw new Error('Personal commission not found');
    personalCommissions[idx] = {
      ...personalCommissions[idx],
      occurredAt: input.occurredAt,
      purchaseAmountMinor: input.purchaseAmountMinor,
      receivedIncomeMinor: input.receivedIncomeMinor,
      receivedPoints: input.receivedPoints,
      currency: input.currency,
      note: input.note,
      updatedAt: utcNow(),
    };
    return cloneCommission(personalCommissions[idx]);
  },

  async deactivatePersonalCommission(id: string) {
    const item = personalCommissions.find((entry) => entry.id === id && entry.status === 'active');
    if (!item) throw new Error('Personal commission not found');
    item.status = 'inactive';
    item.updatedAt = utcNow();
  },

  async listOfficialCompanies(_options?: GuideShopReadOptions) {
    void _options;
    return {
      companies: officialCompanies.map(cloneOfficialCompany),
      page: { nextCursor: null },
    };
  },

  async getOfficialCompany(id: string, _options?: GuideShopReadOptions) {
    void _options;
    const company = officialCompanies.find((item) => item.id === id);
    return company ? cloneOfficialCompany(company) : null;
  },

  async listOfficialVisits(options?: ListOfficialVisitsOptions) {
    void options;
    return {
      visits: officialVisits.map(cloneOfficialVisit),
      page: { nextCursor: null },
    };
  },

  async getOfficialVisit(id: string, _options?: GuideShopReadOptions) {
    void _options;
    const visit = officialVisits.find((item) => item.id === id);
    if (!visit) return null;
    const points = INITIAL_OFFICIAL_VISIT_POINTS[id] ?? [];
    return {
      ...cloneOfficialVisit(visit),
      points: points.map((point) => ({ ...point })),
    };
  },

  async getOfficialPointsSummary(_options?: GuideShopReadOptions) {
    void _options;
    return cloneOfficialPointsSummary(officialPointsSummary);
  },

  async listOfficialHistory(options?: ListOfficialHistoryOptions) {
    void options;
    return {
      history: officialHistory.map(cloneOfficialHistoryItem),
      page: { nextCursor: null },
    };
  },
};

/** Test-only access to in-memory entries */
export function __testEntries(): CalendarEntry[] {
  return entries;
}

/** Test-only access to in-memory personal places */
export function __testPersonalPlaces(): PersonalPlace[] {
  return personalPlaces;
}

/** Test-only access to in-memory personal commissions */
export function __testPersonalCommissions(): PersonalCommission[] {
  return personalCommissions;
}

/** Test-only access to in-memory official companies */
export function __testOfficialCompanies(): OfficialCompany[] {
  return officialCompanies;
}

/** Test-only access to in-memory official visits */
export function __testOfficialVisits(): OfficialVisit[] {
  return officialVisits;
}

/** Test-only access to in-memory official points summary */
export function __testOfficialPointsSummary(): OfficialPointsSummary {
  return officialPointsSummary;
}

/** Test-only access to in-memory official payout history */
export function __testOfficialHistory(): OfficialHistoryItem[] {
  return officialHistory;
}

export function __resetMockStore() {
  entries.length = 0;
  entries.push(...INITIAL_ENTRIES.map((e) => ({ ...e })));
  nextId = 10;
  nextPlaceSeq = 12;
  nextCommissionSeq = 20;
  profile = cloneProfile(MOCK_PROFILE);
  personalPlaces = INITIAL_PERSONAL_PLACES.map(clonePlace);
  personalCommissions = INITIAL_PERSONAL_COMMISSIONS.map(cloneCommission);
  officialCompanies = INITIAL_OFFICIAL_COMPANIES.map(cloneOfficialCompany);
  officialVisits = INITIAL_OFFICIAL_VISITS.map(cloneOfficialVisit);
  officialPointsSummary = cloneOfficialPointsSummary(INITIAL_OFFICIAL_POINTS_SUMMARY);
  officialHistory = INITIAL_OFFICIAL_HISTORY.map(cloneOfficialHistoryItem);
}

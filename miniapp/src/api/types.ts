export type EntryType = 'tour' | 'day_off';
export type TourStatus = 'reserved' | 'confirmed';
export type PaymentStatus = 'paid' | 'unpaid';
export type DayStatusKind = 'free' | 'reserved' | 'confirmed' | 'dayoff';
export type MarkerKind = DayStatusKind;
export type SourceKind = 'Guide OS bot' | 'Mini App' | string;

export interface CalendarEntry {
  id: string;
  type: EntryType;
  title: string;
  startDate: string;
  endDate: string;
  startTime: string | null;
  endTime: string | null;
  status?: TourStatus;
  payment?: PaymentStatus;
  income: number;
  company?: string;
  location?: string;
  note?: string;
  source?: SourceKind;
  dayLocations?: Record<string, string>;
}

export interface TourFormValues {
  title: string;
  startDate: string;
  endDate: string;
  useTime: boolean;
  startTime: string;
  endTime: string;
  company: string;
  location: string;
  income: number;
  status: TourStatus;
  payment: PaymentStatus;
  note: string;
}

export interface DayOffFormValues {
  startDate: string;
  endDate: string;
}

export type OverlayKind =
  | 'add-select'
  | 'tour-form'
  | 'dayoff-form'
  | 'detail'
  | 'delete'
  | 'conflict'
  | 'warning'
  | 'multi-location'
  | 'free-dates'
  | 'demo-states';

export interface ConflictBlock {
  block: true;
  date: string;
  ex: CalendarEntry;
  reason: string;
  entry?: Partial<CalendarEntry>;
}

export interface ConflictWarn {
  warn: true;
  date: string;
  ex: CalendarEntry;
}

export type ConflictResult = ConflictBlock | ConflictWarn | null;

export type TabId = 'calendar' | 'reports' | 'guideshop';
export type CalendarScreen = 'feed' | 'day';

export interface TourFormOverlayData {
  form: TourFormValues;
  editId?: string;
  edit?: boolean;
  copy?: boolean;
}

export interface ConflictOverlayData {
  reason: string;
  form: TourFormValues;
  editId?: string;
  edit?: boolean;
  copy?: boolean;
}

export interface WarningOverlayData extends ConflictWarn {
  form: TourFormValues;
  editId?: string;
}

export interface MultiLocationOverlayData {
  id: string;
  days: string[];
  locations: Record<string, string>;
}

export interface DetailOverlayData {
  id: string;
}

export interface DeleteOverlayData {
  id: string;
}

export interface DayOffOverlayData {
  form: DayOffFormValues;
}

export type OverlayData =
  | TourFormOverlayData
  | ConflictOverlayData
  | WarningOverlayData
  | MultiLocationOverlayData
  | DetailOverlayData
  | DeleteOverlayData
  | DayOffOverlayData
  | Record<string, never>;

export type GuideTypeCode = 'local' | 'route' | 'accompanying';

export interface GuideType {
  type: GuideTypeCode;
  label: string;
  geo: string[];
  allUzbekistan: boolean;
}

export interface GuideTypeInput {
  type: GuideTypeCode;
  geo: string[];
  allUzbekistan: boolean;
}

export interface GuideProfile {
  name: string;
  telegramId: string;
  types: GuideType[];
  languages: string[];
  notifications: {
    enabled: boolean;
    time: string;
  };
}

export interface GuideProfilePatch {
  name?: string;
  types?: GuideTypeInput[];
  languages?: string[];
  notifications?: {
    enabled?: boolean;
    time?: string;
  };
}

export interface ReportsSummaryPeriod {
  from: string;
  to: string;
}

export interface ReportsSummary {
  tourCount: number;
  workDays: number;
  income: number;
  paidTours: number;
  unpaidTours: number;
  period?: ReportsSummaryPeriod;
}

export interface AvailabilityPreview {
  heading: string;
  text: string;
  freeDates: string[];
  ranges: { start: string; end: string }[];
}

export interface ReportsSummaryParams {
  from: string;
  to: string;
  status: 'all' | 'reserved' | 'confirmed';
  payment: 'all' | 'paid' | 'unpaid';
  company?: string;
  location?: string;
}

export interface AvailabilityPreviewParams {
  from: string;
  to: string;
  format?: 'text' | 'structured';
}

export type PersonalPlaceStatus = 'active' | 'inactive';

export interface PersonalPlace {
  id: string;
  name: string;
  category: string | null;
  generalLocation: string | null;
  landmark: string | null;
  note: string | null;
  status: PersonalPlaceStatus;
  createdAt: string;
  updatedAt: string;
}

export interface PersonalPlaceInput {
  name: string;
  category: string | null;
  generalLocation: string | null;
  landmark: string | null;
  note: string | null;
}

export interface ListPersonalPlacesOptions {
  includeInactive?: boolean;
}

export type PersonalCommissionStatus = 'active' | 'inactive';

export interface PersonalCommission {
  id: string;
  placeId: string;
  occurredAt: string;
  purchaseAmountMinor: number | null;
  receivedIncomeMinor: number | null;
  receivedPoints: number | null;
  currency: string | null;
  note: string | null;
  status: PersonalCommissionStatus;
  createdAt: string;
  updatedAt: string;
}

export interface PersonalCommissionInput {
  occurredAt: string;
  purchaseAmountMinor: number | null;
  receivedIncomeMinor: number | null;
  receivedPoints: number | null;
  currency: string | null;
  note: string | null;
}

export interface ListPersonalCommissionsOptions {
  includeInactive?: boolean;
}

export type OfficialCompanyStatus = 'active' | 'inactive' | string;

export interface OfficialCompany {
  id: string;
  displayName: string;
  status: OfficialCompanyStatus;
  phone: string | null;
  address: string | null;
  description: string | null;
  type: string | null;
}

export interface OfficialCompaniesPage {
  nextCursor: string | null;
}

export interface OfficialCompaniesResult {
  companies: OfficialCompany[];
  page: OfficialCompaniesPage;
}

export type OfficialVisitStatus = 'active' | 'completed' | 'cancelled' | string;

export type OfficialVisitPaymentStatus = 'unpaid' | 'paid' | string;

export interface OfficialVisit {
  id: string;
  companyId: string;
  visitAt: string;
  status: OfficialVisitStatus;
  touristCount: number;
  customerPaymentStatus: OfficialVisitPaymentStatus;
  customerPaidAt: string | null;
  createdAt: string;
  updatedAt: string;
  /** Present on visit detail only (Option A). */
  points?: OfficialVisitPoint[];
}

export interface OfficialVisitPoint {
  amount: string;
  unit: 'PTS' | string;
  status: 'pending' | 'credited' | string;
}

export interface OfficialVisitsPage {
  nextCursor: string | null;
}

export interface OfficialVisitsResult {
  visits: OfficialVisit[];
  page: OfficialVisitsPage;
}

export interface ListOfficialVisitsOptions {
  cursor?: string;
}

export interface OfficialPointsCompanySummary {
  companyId: string;
  displayName: string;
  pendingTotal: string;
  creditedTotal: string;
}

export interface OfficialPointsSummary {
  unit: 'PTS' | string;
  pendingTotal: string;
  creditedTotal: string;
  companies: OfficialPointsCompanySummary[];
}

export interface OfficialHistoryItem {
  id: string;
  pointsAccrualId: string;
  companyId: string;
  visitId: string;
  amount: string;
  unit: 'PTS' | string;
  paidAt: string;
  createdAt: string;
}

export interface OfficialHistoryPage {
  nextCursor: string | null;
}

export interface OfficialHistoryResult {
  history: OfficialHistoryItem[];
  page: OfficialHistoryPage;
}

export interface ListOfficialHistoryOptions {
  cursor?: string;
}

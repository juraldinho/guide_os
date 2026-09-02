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

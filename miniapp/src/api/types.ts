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
  payment?: PaymentStatus | null;
  /** Daily rate; null means unknown / not applicable (Guide Operator projections). */
  income: number | null;
  company?: string;
  location?: string;
  note?: string;
  source?: SourceKind;
  dayLocations?: Record<string, string>;
  /** Present when this calendar row is a Guide Operator projection. */
  guideOperatorAssignmentId?: string | null;
  /** Active working-package version for the projected assignment. */
  guideOperatorVersion?: number | null;
  /** True when the active ordinary version has not been acknowledged. */
  guideOperatorVersionUnread?: boolean | null;
  /** True when a critical version awaits guide confirm/reject. */
  guideOperatorPendingCritical?: boolean | null;
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

export type TabId = 'calendar' | 'reports' | 'guideshop' | 'guide_operator';
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

export interface CommissionReportsSummaryParams {
  from: string;
  to: string;
}

export interface CommissionReportsCompanySummary {
  placeId: string;
  companyName: string;
  totalCommission: number;
  recordCount: number;
}

export interface CommissionReportsSummary {
  totalCommission: number;
  recordCount: number;
  byCompany: CommissionReportsCompanySummary[];
  period: ReportsSummaryPeriod;
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
  signal?: AbortSignal;
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
  signal?: AbortSignal;
}

export type GuideOperatorAssignmentStatus =
  | 'offered'
  | 'accepted'
  | 'declined'
  | 'cancelled';

export type GuideOperatorLifecycleSection =
  | 'awaiting'
  | 'upcoming'
  | 'in_progress'
  | 'completed'
  | 'cancelled';

export interface GuideOperatorAssignment {
  id: string;
  companyId: string;
  companyName: string;
  role: string;
  startDate: string;
  endDate: string;
  responseDeadline: string | null;
  operatorMessage: string | null;
  status: GuideOperatorAssignmentStatus;
  activeVersionNumber: number;
  activeVersionUnread: boolean;
  pendingCriticalVersionNumber: number | null;
  projectionTourId: string | null;
  offeredAt: string;
  decidedAt: string | null;
  cancelledAt: string | null;
}

export interface GuideOperatorAssignmentLists {
  asOfDate: string;
  awaiting: GuideOperatorAssignment[];
  upcoming: GuideOperatorAssignment[];
  inProgress: GuideOperatorAssignment[];
  completed: GuideOperatorAssignment[];
  cancelled: GuideOperatorAssignment[];
}

export interface GuideOperatorChangeSummaryItem {
  code?: string;
  severity?: string;
  path?: string;
  change?: string;
  before?: unknown;
  after?: unknown;
  [key: string]: unknown;
}

export interface GuideOperatorAssignmentVersion {
  versionNumber: number;
  severity: 'initial' | 'ordinary' | 'critical' | string;
  publishedAt: string;
  changeSummary: GuideOperatorChangeSummaryItem[];
  workingPackage: Record<string, unknown>;
  sourceEventId?: string | null;
}

export interface GuideOperatorActiveVersion {
  versionNumber: number;
  severity: 'initial' | 'ordinary' | 'critical' | string;
  publishedAt: string;
  changeSummary: GuideOperatorChangeSummaryItem[];
  unread: boolean;
  sourceEventId?: string | null;
}

export interface GuideOperatorPendingCriticalVersion {
  versionNumber: number;
  severity: 'critical' | string;
  publishedAt: string;
  changeSummary: GuideOperatorChangeSummaryItem[];
  workingPackage: Record<string, unknown>;
  sourceEventId?: string | null;
  conflictDates: string[];
}

export interface GuideOperatorAssignmentDetail {
  assignment: GuideOperatorAssignment;
  workingPackage: Record<string, unknown>;
  conflictDates: string[];
  activeVersion: GuideOperatorActiveVersion;
  pendingCriticalVersion: GuideOperatorPendingCriticalVersion | null;
  versions: GuideOperatorAssignmentVersion[];
}

export interface GuideOperatorDecisionInput {
  decisionEventId: string;
}

export interface GuideOperatorDecisionResult {
  assignmentId: string;
  status: GuideOperatorAssignmentStatus;
  decision: 'accept' | 'decline';
  decisionEventId: string;
  projectionTourId: string | null;
  replayed: boolean;
}

export interface GuideOperatorVersionAcknowledgeInput {
  decisionEventId: string;
  versionNumber: number;
}

export interface GuideOperatorVersionAcknowledgeResult {
  assignmentId: string;
  versionNumber: number;
  decisionEventId: string;
  unread: boolean;
  replayed: boolean;
}

export interface GuideOperatorCriticalDecisionInput {
  decisionEventId: string;
  versionNumber: number;
}

export interface GuideOperatorCriticalDecisionResult {
  assignmentId: string;
  status: GuideOperatorAssignmentStatus;
  decision: 'confirm_critical' | 'reject_critical';
  versionNumber: number;
  decisionEventId: string;
  pendingCriticalVersionNumber: number | null;
  activeVersionNumber: number;
  projectionTourId: string | null;
  replayed: boolean;
}

export type GuideOperatorConnectionStatus =
  | 'invited'
  | 'confirmed'
  | 'declined'
  | 'disconnected';

export interface GuideOperatorConnection {
  id: string;
  companyName: string;
  status: GuideOperatorConnectionStatus;
  invitedAt: string;
  invitationExpiresAt: string;
  decidedAt: string | null;
  disconnectedAt: string | null;
  expired: boolean;
  actionable: boolean;
}

export interface GuideOperatorConnectionDecisionInput {
  decisionEventId: string;
}

export interface GuideOperatorConnectionDecisionResult {
  connectionId: string;
  status: GuideOperatorConnectionStatus;
  decision: 'confirm' | 'decline';
  decisionEventId: string;
  replayed: boolean;
}

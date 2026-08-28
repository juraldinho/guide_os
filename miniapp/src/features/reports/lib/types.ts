export type ReportsPeriod = 'month' | 'year' | 'all';
export type AvailOpenFrom = 'calendar' | 'reports';
export type ThemeMode = 'telegram' | 'light' | 'dark';
export type FilterStatus = 'all' | 'reserved' | 'confirmed';
export type FilterPayment = 'all' | 'paid' | 'unpaid';

export interface GuideType {
  type: string;
  label: string;
  geo: string[];
}

export interface GuideProfile {
  name: string;
  telegramId: string;
  types: GuideType[];
  notifications: { enabled: boolean; time: string };
}

export interface DateRange {
  from: string;
  to: string;
}

export interface ReportsSummary {
  tourCount: number;
  workDays: number;
  income: number;
  paidTours: number;
  unpaidTours: number;
}

export interface ReportsFilters {
  status: FilterStatus;
  payment: FilterPayment;
  company: string;
  location: string;
}

export interface ReportsState {
  period: ReportsPeriod;
  month: number;
  year: number;
}

export interface AvailabilityState {
  openFrom: AvailOpenFrom;
  useCustom: boolean;
  customFrom: string;
  customTo: string;
}

export interface CalendarAvailContext {
  calendarScreen: 'feed' | 'day';
  selectedDate: string;
  viewMonth: number;
  viewYear: number;
}

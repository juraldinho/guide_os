import type {
  AvailabilityPreview,
  AvailabilityPreviewParams,
  CalendarEntry,
  DayOffFormValues,
  GuideProfile,
  ReportsSummary,
  ReportsSummaryParams,
  TourFormValues,
} from './types';

export interface WriteOptions {
  ackDateWarning?: boolean;
}

export interface GuideOsClient {
  listEntries(): Promise<CalendarEntry[]>;
  getEntry(id: string): Promise<CalendarEntry | null>;
  createTour(form: TourFormValues, options?: WriteOptions): Promise<CalendarEntry>;
  updateTour(id: string, form: TourFormValues, options?: WriteOptions): Promise<CalendarEntry>;
  createDayOff(form: DayOffFormValues, options?: WriteOptions): Promise<CalendarEntry>;
  deleteEntry(id: string): Promise<void>;
  updateDayLocations(id: string, locations: Record<string, string>): Promise<CalendarEntry>;
  getProfile(): Promise<GuideProfile>;
  updateProfile(patch: Partial<GuideProfile>): Promise<GuideProfile>;
  getReportsSummary(params: ReportsSummaryParams): Promise<ReportsSummary>;
  previewAvailability(params: AvailabilityPreviewParams): Promise<AvailabilityPreview>;
}

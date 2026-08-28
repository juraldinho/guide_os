import type {
  CalendarEntry,
  DayOffFormValues,
  GuideProfile,
  TourFormValues,
} from './types';

export interface GuideOsClient {
  listEntries(): Promise<CalendarEntry[]>;
  getEntry(id: string): Promise<CalendarEntry | null>;
  createTour(form: TourFormValues): Promise<CalendarEntry>;
  updateTour(id: string, form: TourFormValues): Promise<CalendarEntry>;
  createDayOff(form: DayOffFormValues): Promise<CalendarEntry>;
  deleteEntry(id: string): Promise<void>;
  updateDayLocations(id: string, locations: Record<string, string>): Promise<CalendarEntry>;
  getProfile(): Promise<GuideProfile>;
  updateProfile(patch: Partial<GuideProfile>): Promise<GuideProfile>;
}

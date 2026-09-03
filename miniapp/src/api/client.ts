import type {
  AvailabilityPreview,
  AvailabilityPreviewParams,
  CalendarEntry,
  DayOffFormValues,
  GuideProfile,
  GuideProfilePatch,
  ListPersonalCommissionsOptions,
  ListPersonalPlacesOptions,
  ListOfficialVisitsOptions,
  ListOfficialHistoryOptions,
  OfficialCompaniesResult,
  OfficialCompany,
  OfficialHistoryResult,
  OfficialPointsSummary,
  OfficialVisit,
  OfficialVisitsResult,
  PersonalCommission,
  PersonalCommissionInput,
  PersonalPlace,
  PersonalPlaceInput,
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
  updateProfile(patch: GuideProfilePatch): Promise<GuideProfile>;
  getReportsSummary(params: ReportsSummaryParams): Promise<ReportsSummary>;
  previewAvailability(params: AvailabilityPreviewParams): Promise<AvailabilityPreview>;
  listPersonalPlaces(options?: ListPersonalPlacesOptions): Promise<PersonalPlace[]>;
  getPersonalPlace(id: string): Promise<PersonalPlace | null>;
  createPersonalPlace(input: PersonalPlaceInput): Promise<PersonalPlace>;
  updatePersonalPlace(id: string, input: PersonalPlaceInput): Promise<PersonalPlace>;
  deactivatePersonalPlace(id: string): Promise<void>;
  listPersonalCommissions(
    placeId: string,
    options?: ListPersonalCommissionsOptions,
  ): Promise<PersonalCommission[]>;
  getPersonalCommission(id: string): Promise<PersonalCommission | null>;
  createPersonalCommission(
    placeId: string,
    input: PersonalCommissionInput,
  ): Promise<PersonalCommission>;
  updatePersonalCommission(
    id: string,
    input: PersonalCommissionInput,
  ): Promise<PersonalCommission>;
  deactivatePersonalCommission(id: string): Promise<void>;
  listOfficialCompanies(): Promise<OfficialCompaniesResult>;
  getOfficialCompany(id: string): Promise<OfficialCompany | null>;
  listOfficialVisits(options?: ListOfficialVisitsOptions): Promise<OfficialVisitsResult>;
  getOfficialVisit(id: string): Promise<OfficialVisit | null>;
  getOfficialPointsSummary(): Promise<OfficialPointsSummary>;
  listOfficialHistory(options?: ListOfficialHistoryOptions): Promise<OfficialHistoryResult>;
}

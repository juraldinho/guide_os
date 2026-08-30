import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { ApiConflictError } from '@/api/httpClient';
import { guideOsClient } from '@/api/createClient';
import type {
  CalendarEntry,
  CalendarScreen,
  ConflictOverlayData,
  DayOffFormValues,
  DetailOverlayData,
  GuideProfile,
  MultiLocationOverlayData,
  OverlayData,
  OverlayKind,
  TabId,
  TourFormOverlayData,
  TourFormValues,
  WarningOverlayData,
} from '@/api/types';
import { MOCK_TODAY, USE_MOCK_API } from '@/config';
import { useToast } from '@/components/ui/Toast';
import { checkConflicts } from '@/features/calendar/lib/conflicts';
import { daysInRange } from '@/features/calendar/lib/dates';
import type {
  AvailOpenFrom,
  FilterPayment,
  FilterStatus,
  ReportsPeriod,
} from '@/features/reports/lib/types';
import { buildFreeDatesText } from '@/features/reports/lib/availability';
import { t } from '@/i18n/strings';
import { applyThemeMode, loadStoredTheme, type ThemeMode } from '@/telegram/mockAdapter';
import { copyText } from '@/utils/copyText';

function defaultTourForm(selectedDate: string, prefill?: Partial<TourFormValues>): TourFormValues {
  const base: TourFormValues = {
    title: '',
    startDate: selectedDate,
    endDate: selectedDate,
    useTime: false,
    startTime: '09:00',
    endTime: '14:00',
    company: '',
    location: '',
    income: 0,
    status: 'reserved',
    payment: 'unpaid',
    note: '',
  };
  return { ...base, ...prefill };
}

interface CalendarContextValue {
  entries: CalendarEntry[];
  activeTab: TabId;
  calendarScreen: CalendarScreen;
  monthExpanded: boolean;
  selectedDate: string;
  viewMonth: number;
  viewYear: number;
  overlay: OverlayKind | null;
  overlayData: OverlayData;
  overlayReturn: 'day' | null;
  setActiveTab: (tab: TabId) => void;
  toggleMonthPicker: () => void;
  prevMonth: () => void;
  nextMonth: () => void;
  openDayDetail: (iso: string) => void;
  selectDateFromMonth: (iso: string) => void;
  openFeed: () => void;
  goToday: () => void;
  openAdd: () => void;
  openTourForm: (prefill?: Partial<TourFormValues>) => void;
  openDayOffForm: () => void;
  closeOverlay: () => void;
  returnToTourFormFromConflict: (target: 'time' | 'date') => void;
  saveTour: (form: TourFormValues) => void;
  ackWarningAndSave: () => void;
  saveDayOff: (form: DayOffFormValues) => void;
  openDetail: (id: string) => void;
  editTour: (id: string) => void;
  copyTour: (id: string) => void;
  openDelete: (id: string) => void;
  confirmDelete: () => void;
  saveDayLocations: (locations: Record<string, string>) => void;
  updateMultiLocation: (day: string, value: string) => void;
  settingsOpen: boolean;
  profile: GuideProfile | null;
  themeMode: ThemeMode;
  reportsPeriod: ReportsPeriod;
  reportsMonth: number;
  reportsYear: number;
  filterStatus: FilterStatus;
  filterPayment: FilterPayment;
  availOpenFrom: AvailOpenFrom;
  freeDatesSession: number;
  availUseCustom: boolean;
  availCustomFrom: string;
  availCustomTo: string;
  demoLoading: boolean;
  demoError: boolean;
  demoOffline: boolean;
  openSettings: () => void;
  closeSettings: () => void;
  setReportsPeriod: (period: ReportsPeriod) => void;
  prevReportsMonth: () => void;
  nextReportsMonth: () => void;
  prevReportsYear: () => void;
  nextReportsYear: () => void;
  setFilterStatus: (status: FilterStatus) => void;
  setFilterPayment: (payment: FilterPayment) => void;
  openFreeDates: () => void;
  setAvailContextMode: (custom: boolean, from?: string, to?: string) => void;
  setAvailCustomFrom: (value: string) => void;
  setAvailCustomTo: (value: string) => void;
  copyFreeDates: () => void;
  copyTelegramId: () => void;
  updateProfileName: (name: string) => void;
  toggleNotif: () => void;
  updateNotifTime: (time: string) => void;
  setThemeMode: (mode: ThemeMode) => void;
  openDemoStates: () => void;
  showDemoLoading: () => void;
  showDemoError: () => void;
  showDemoOffline: () => void;
  retryDemo: () => void;
}

const CalendarContext = createContext<CalendarContextValue | null>(null);

export function CalendarProvider({ children }: { children: ReactNode }) {
  const { showToast } = useToast();
  const [entries, setEntries] = useState<CalendarEntry[]>([]);
  const [activeTab, setActiveTabState] = useState<TabId>('calendar');
  const [calendarScreen, setCalendarScreen] = useState<CalendarScreen>('feed');
  const [monthExpanded, setMonthExpanded] = useState(false);
  const [selectedDate, setSelectedDate] = useState(MOCK_TODAY);
  const [viewMonth, setViewMonth] = useState(7);
  const [viewYear, setViewYear] = useState(2026);
  const [overlay, setOverlay] = useState<OverlayKind | null>(null);
  const [overlayData, setOverlayData] = useState<OverlayData>({});
  const [overlayReturn, setOverlayReturn] = useState<'day' | null>(null);
  const [dateWarningAck, setDateWarningAck] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [profile, setProfile] = useState<GuideProfile | null>(null);
  const [themeMode, setThemeModeState] = useState<ThemeMode>(loadStoredTheme());
  const [reportsPeriod, setReportsPeriodState] = useState<ReportsPeriod>('month');
  const [reportsMonth, setReportsMonth] = useState(7);
  const [reportsYear, setReportsYear] = useState(2026);
  const [filterStatus, setFilterStatusState] = useState<FilterStatus>('all');
  const [filterPayment, setFilterPaymentState] = useState<FilterPayment>('all');
  const [availOpenFrom, setAvailOpenFrom] = useState<AvailOpenFrom>('calendar');
  const [freeDatesSession, setFreeDatesSession] = useState(0);
  const [availUseCustom, setAvailUseCustom] = useState(false);
  const [availCustomFrom, setAvailCustomFromState] = useState('2026-08-01');
  const [availCustomTo, setAvailCustomToState] = useState('2026-08-31');
  const [demoLoading, setDemoLoading] = useState(false);
  const [demoError, setDemoError] = useState(false);
  const [demoOffline, setDemoOffline] = useState(false);

  const refreshEntries = useCallback(async () => {
    const list = await guideOsClient.listEntries();
    setEntries(list);
  }, []);

  useEffect(() => {
    refreshEntries();
    guideOsClient.getProfile().then(setProfile);
  }, [refreshEntries]);

  const setActiveTab = useCallback((tab: TabId) => {
    setActiveTabState(tab);
    if (tab === 'calendar' && calendarScreen !== 'day') {
      setCalendarScreen('feed');
    }
  }, [calendarScreen]);

  const closeOverlay = useCallback(() => {
    setOverlay(null);
    setOverlayData({});
    setDeleteId(null);
    if (overlayReturn === 'day') {
      setOverlayReturn(null);
      setCalendarScreen('day');
    }
  }, [overlayReturn]);

  const openAdd = useCallback(() => {
    setOverlay('add-select');
    setOverlayData({});
    if (calendarScreen === 'day') setOverlayReturn('day');
  }, [calendarScreen]);

  const openTourForm = useCallback(
    (prefill?: Partial<TourFormValues>) => {
      let form = defaultTourForm(selectedDate, prefill);
      if (USE_MOCK_API && selectedDate === MOCK_TODAY && !prefill) {
        form = {
          ...form,
          startTime: '12:00',
          endTime: '16:00',
          useTime: true,
          title: 'Новый тур (конфликт)',
        };
      }
      const data: TourFormOverlayData = {
        form,
        edit: (overlayData as TourFormOverlayData).edit,
        copy: (overlayData as TourFormOverlayData).copy,
        editId: (overlayData as TourFormOverlayData).editId,
      };
      setOverlay('tour-form');
      setOverlayData(data);
    },
    [selectedDate, overlayData],
  );

  const openDayOffForm = useCallback(() => {
    setOverlay('dayoff-form');
    setOverlayData({
      form: { startDate: selectedDate, endDate: selectedDate },
    });
  }, [selectedDate]);

  const returnToTourFormFromConflict = useCallback(
    (target: 'time' | 'date') => {
      const data = overlayData as ConflictOverlayData;
      setOverlay('tour-form');
      setOverlayData({
        form: data.form || defaultTourForm(selectedDate),
        editId: data.editId,
        edit: data.edit,
        copy: data.copy,
      });
      const focusId = target === 'time' ? 'f-start-time' : 'f-start';
      requestAnimationFrame(() => {
        const el = document.getElementById(focusId);
        if (el) el.focus();
      });
    },
    [overlayData, selectedDate],
  );

  const saveTour = useCallback(
    async (form: TourFormValues) => {
      if (!form.title.trim()) {
        showToast(t.toastTitleRequired);
        return;
      }
      if (form.endDate < form.startDate) {
        showToast(t.toastEndBeforeStart);
        return;
      }
      if (form.useTime && form.startTime >= form.endTime) {
        showToast(t.toastTimeOrder);
        return;
      }

      const tourData = overlayData as TourFormOverlayData;
      const editId = tourData.editId;
      const draft = {
        type: 'tour' as const,
        title: form.title.trim(),
        company: form.company,
        location: form.location,
        startDate: form.startDate,
        endDate: form.endDate,
        startTime: form.useTime ? form.startTime : null,
        endTime: form.useTime ? form.endTime : null,
        status: form.status,
        payment: form.payment,
        income: form.income,
        note: form.note,
        source: 'Mini App' as const,
      };

      const conflict = checkConflicts(draft, entries, editId);

      if (conflict && 'block' in conflict && conflict.block) {
        setOverlay('conflict');
        setOverlayData({
          reason: conflict.reason,
          form,
          editId,
          edit: tourData.edit,
          copy: tourData.copy,
        });
        return;
      }

      if (conflict && 'warn' in conflict && !dateWarningAck) {
        setOverlay('warning');
        setOverlayData({ ...conflict, form, editId } as WarningOverlayData);
        return;
      }

      setDateWarningAck(false);

      const writeOpts = dateWarningAck ? { ackDateWarning: true } : undefined;

      try {
        if (editId) {
          await guideOsClient.updateTour(editId, form, writeOpts);
          showToast(t.toastUpdated);
        } else {
          const created = await guideOsClient.createTour(form, writeOpts);
          showToast(t.toastSaved);
          if (created.startDate !== created.endDate) {
            const days = daysInRange(created.startDate, created.endDate);
            const locs: Record<string, string> = {};
            days.forEach((d) => {
              locs[d] = created.location || '';
            });
            setOverlay('multi-location');
            setOverlayData({ id: created.id, days, locations: locs } as MultiLocationOverlayData);
            await refreshEntries();
            return;
          }
        }
      } catch (e) {
        if (e instanceof ApiConflictError) {
          const { details } = e;
          if (details.conflict_kind === 'date_warning') {
            setOverlay('warning');
            setOverlayData({
              warn: true,
              date: details.date,
              ex: details.existing_entry,
              form,
              editId,
            } as WarningOverlayData);
            return;
          }
          setOverlay('conflict');
          setOverlayData({
            reason: e.message,
            form,
            editId,
            edit: tourData.edit,
            copy: tourData.copy,
          });
          return;
        }
        throw e;
      }

      await refreshEntries();
      setSelectedDate(form.startDate);
      setCalendarScreen('day');
      setOverlay(null);
      setOverlayData({});
      setDeleteId(null);
      if (overlayReturn === 'day') {
        setOverlayReturn(null);
      }
    },
    [entries, overlayData, dateWarningAck, overlayReturn, refreshEntries, showToast],
  );

  const ackWarningAndSave = useCallback(() => {
    setDateWarningAck(true);
    const data = overlayData as WarningOverlayData;
    saveTour(data.form);
  }, [overlayData, saveTour]);

  const saveDayOff = useCallback(
    async (form: DayOffFormValues) => {
      const draft = {
        type: 'day_off' as const,
        title: 'Выходной',
        startDate: form.startDate,
        endDate: form.endDate,
        startTime: null,
        endTime: null,
        income: 0,
      };
      const conflict = checkConflicts(draft, entries);
      if (conflict && 'block' in conflict) {
        showToast(conflict.reason);
        return;
      }
      await guideOsClient.createDayOff(form);
      showToast(t.toastDayOffSaved);
      await refreshEntries();
      closeOverlay();
    },
    [entries, refreshEntries, closeOverlay, showToast],
  );

  const openDetail = useCallback(
    (id: string) => {
      setOverlay('detail');
      setOverlayData({ id } as DetailOverlayData);
      if (calendarScreen === 'day') setOverlayReturn('day');
    },
    [calendarScreen],
  );

  const editTour = useCallback(
    async (id: string) => {
      const e = await guideOsClient.getEntry(id);
      if (!e || e.type !== 'tour') return;
      setOverlay('tour-form');
      setOverlayData({
        edit: true,
        editId: id,
        form: {
          title: e.title,
          startDate: e.startDate,
          endDate: e.endDate,
          useTime: Boolean(e.startTime && e.endTime),
          startTime: e.startTime || '09:00',
          endTime: e.endTime || '14:00',
          company: e.company || '',
          location: e.location || '',
          income: e.income,
          status: e.status || 'reserved',
          payment: e.payment || 'unpaid',
          note: e.note || '',
        },
      });
    },
    [],
  );

  const copyTour = useCallback(
    async (id: string) => {
      const e = await guideOsClient.getEntry(id);
      if (!e || e.type !== 'tour') return;
      setOverlay('tour-form');
      setOverlayData({
        copy: true,
        form: {
          title: e.title,
          startDate: selectedDate,
          endDate: selectedDate,
          useTime: Boolean(e.startTime && e.endTime),
          startTime: e.startTime || '09:00',
          endTime: e.endTime || '14:00',
          company: e.company || '',
          location: e.location || '',
          income: e.income,
          status: e.status || 'reserved',
          payment: e.payment || 'unpaid',
          note: e.note || '',
        },
      });
    },
    [selectedDate],
  );

  const openDelete = useCallback((id: string) => {
    setOverlay('delete');
    setOverlayData({ id });
    setDeleteId(id);
  }, []);

  const confirmDelete = useCallback(async () => {
    if (!deleteId) return;
    await guideOsClient.deleteEntry(deleteId);
    showToast(t.toastDeleted);
    closeOverlay();
    await refreshEntries();
  }, [deleteId, closeOverlay, refreshEntries, showToast]);

  const saveDayLocations = useCallback(
    async (locations: Record<string, string>) => {
      const data = overlayData as MultiLocationOverlayData;
      await guideOsClient.updateDayLocations(data.id, locations);
      closeOverlay();
      await refreshEntries();
    },
    [overlayData, closeOverlay, refreshEntries],
  );

  const updateMultiLocation = useCallback((day: string, value: string) => {
    const data = overlayData as MultiLocationOverlayData;
    setOverlayData({
      ...data,
      locations: { ...data.locations, [day]: value },
    });
  }, [overlayData]);

  const calendarCtx = useMemo(
    () => ({ calendarScreen, selectedDate, viewMonth, viewYear }),
    [calendarScreen, selectedDate, viewMonth, viewYear],
  );

  const reportsState = useMemo(
    () => ({ period: reportsPeriod, month: reportsMonth, year: reportsYear }),
    [reportsPeriod, reportsMonth, reportsYear],
  );

  const availState = useMemo(
    () => ({ useCustom: availUseCustom, customFrom: availCustomFrom, customTo: availCustomTo }),
    [availUseCustom, availCustomFrom, availCustomTo],
  );

  const openSettings = useCallback(() => setSettingsOpen(true), []);
  const closeSettings = useCallback(() => setSettingsOpen(false), []);

  const setReportsPeriod = useCallback((period: ReportsPeriod) => setReportsPeriodState(period), []);

  const prevReportsMonth = useCallback(() => {
    setReportsMonth((m) => {
      if (m <= 0) {
        setReportsYear((y) => y - 1);
        return 11;
      }
      return m - 1;
    });
  }, []);

  const nextReportsMonth = useCallback(() => {
    setReportsMonth((m) => {
      if (m >= 11) {
        setReportsYear((y) => y + 1);
        return 0;
      }
      return m + 1;
    });
  }, []);

  const prevReportsYear = useCallback(() => setReportsYear((y) => y - 1), []);

  const nextReportsYear = useCallback(() => {
    setReportsYear((y) => {
      const maxYear = parseInt(MOCK_TODAY.slice(0, 4), 10);
      if (y < maxYear) return y + 1;
      return y;
    });
  }, []);

  const setFilterStatus = useCallback((status: FilterStatus) => setFilterStatusState(status), []);
  const setFilterPayment = useCallback((payment: FilterPayment) => setFilterPaymentState(payment), []);

  const openFreeDates = useCallback(() => {
    setAvailOpenFrom(activeTab === 'reports' ? 'reports' : 'calendar');
    setAvailUseCustom(false);
    setFreeDatesSession((s) => s + 1);
    setOverlay('free-dates');
    setOverlayData({});
  }, [activeTab]);

  const setAvailContextMode = useCallback(
    (custom: boolean, from?: string, to?: string) => {
      setAvailUseCustom(custom);
      if (custom && from && to) {
        setAvailCustomFromState(from);
        setAvailCustomToState(to);
      }
    },
    [],
  );

  const setAvailCustomFrom = useCallback((value: string) => setAvailCustomFromState(value), []);
  const setAvailCustomTo = useCallback((value: string) => setAvailCustomToState(value), []);

  const copyFreeDates = useCallback(async () => {
    const text = buildFreeDatesText(entries, availOpenFrom, availState, calendarCtx, reportsState);
    if (!text) return;
    const ok = await copyText(text);
    showToast(ok ? t.toastCopied : t.toastCopyFailed);
  }, [entries, availOpenFrom, availState, calendarCtx, reportsState, showToast]);

  const copyTelegramId = useCallback(async () => {
    if (!profile) return;
    const ok = await copyText(profile.telegramId);
    showToast(ok ? t.toastCopied : t.toastCopyFailed);
  }, [profile, showToast]);

  const updateProfileName = useCallback(async (name: string) => {
    const updated = await guideOsClient.updateProfile({ name });
    setProfile(updated);
  }, []);

  const toggleNotif = useCallback(async () => {
    if (!profile) return;
    const updated = await guideOsClient.updateProfile({
      notifications: { ...profile.notifications, enabled: !profile.notifications.enabled },
    });
    setProfile(updated);
  }, [profile]);

  const updateNotifTime = useCallback(async (time: string) => {
    if (!profile) return;
    const updated = await guideOsClient.updateProfile({
      notifications: { ...profile.notifications, time },
    });
    setProfile(updated);
  }, [profile]);

  const setThemeMode = useCallback((mode: ThemeMode) => {
    setThemeModeState(mode);
    applyThemeMode(mode);
  }, []);

  const openDemoStates = useCallback(() => {
    setOverlay('demo-states');
    setOverlayData({});
  }, []);

  const showDemoLoading = useCallback(() => {
    setSettingsOpen(false);
    setOverlay(null);
    setOverlayData({});
    setDemoLoading(true);
    window.setTimeout(() => setDemoLoading(false), 2000);
  }, []);

  const showDemoError = useCallback(() => {
    setSettingsOpen(false);
    setOverlay(null);
    setOverlayData({});
    setDemoError(true);
  }, []);

  const showDemoOffline = useCallback(() => {
    setSettingsOpen(false);
    setOverlay(null);
    setOverlayData({});
    setDemoOffline(true);
  }, []);

  const retryDemo = useCallback(() => {
    setDemoError(false);
    setDemoOffline(false);
  }, []);

  const value = useMemo<CalendarContextValue>(
    () => ({
      entries,
      activeTab,
      calendarScreen,
      monthExpanded,
      selectedDate,
      viewMonth,
      viewYear,
      overlay,
      overlayData,
      overlayReturn,
      setActiveTab,
      toggleMonthPicker: () => setMonthExpanded((v) => !v),
      prevMonth: () => {
        if (viewMonth <= 0) {
          setViewMonth(11);
          setViewYear((y) => y - 1);
        } else {
          setViewMonth((m) => m - 1);
        }
      },
      nextMonth: () => {
        if (viewMonth >= 11) {
          setViewMonth(0);
          setViewYear((y) => y + 1);
        } else {
          setViewMonth((m) => m + 1);
        }
      },
      openDayDetail: (iso: string) => {
        setSelectedDate(iso);
        setCalendarScreen('day');
        setMonthExpanded(false);
      },
      selectDateFromMonth: (iso: string) => {
        setSelectedDate(iso);
        setCalendarScreen('day');
        setMonthExpanded(false);
      },
      openFeed: () => setCalendarScreen('feed'),
      goToday: () => {
        setSelectedDate(MOCK_TODAY);
        setViewMonth(7);
        setViewYear(2026);
        setCalendarScreen('feed');
        setMonthExpanded(false);
      },
      openAdd,
      openTourForm,
      openDayOffForm,
      closeOverlay,
      returnToTourFormFromConflict,
      saveTour,
      ackWarningAndSave,
      saveDayOff,
      openDetail,
      editTour,
      copyTour,
      openDelete,
      confirmDelete,
      saveDayLocations,
      updateMultiLocation,
      settingsOpen,
      profile,
      themeMode,
      reportsPeriod,
      reportsMonth,
      reportsYear,
      filterStatus,
      filterPayment,
      availOpenFrom,
      freeDatesSession,
      availUseCustom,
      availCustomFrom,
      availCustomTo,
      demoLoading,
      demoError,
      demoOffline,
      openSettings,
      closeSettings,
      setReportsPeriod,
      prevReportsMonth,
      nextReportsMonth,
      prevReportsYear,
      nextReportsYear,
      setFilterStatus,
      setFilterPayment,
      openFreeDates,
      setAvailContextMode,
      setAvailCustomFrom,
      setAvailCustomTo,
      copyFreeDates,
      copyTelegramId,
      updateProfileName,
      toggleNotif,
      updateNotifTime,
      setThemeMode,
      openDemoStates,
      showDemoLoading,
      showDemoError,
      showDemoOffline,
      retryDemo,
    }),
    [
      entries,
      activeTab,
      calendarScreen,
      monthExpanded,
      selectedDate,
      viewMonth,
      viewYear,
      overlay,
      overlayData,
      overlayReturn,
      setActiveTab,
      openAdd,
      openTourForm,
      openDayOffForm,
      closeOverlay,
      returnToTourFormFromConflict,
      saveTour,
      ackWarningAndSave,
      saveDayOff,
      openDetail,
      editTour,
      copyTour,
      openDelete,
      confirmDelete,
      saveDayLocations,
      updateMultiLocation,
      settingsOpen,
      profile,
      themeMode,
      reportsPeriod,
      reportsMonth,
      reportsYear,
      filterStatus,
      filterPayment,
      availOpenFrom,
      freeDatesSession,
      availUseCustom,
      availCustomFrom,
      availCustomTo,
      demoLoading,
      demoError,
      demoOffline,
      openSettings,
      closeSettings,
      setReportsPeriod,
      prevReportsMonth,
      nextReportsMonth,
      prevReportsYear,
      nextReportsYear,
      setFilterStatus,
      setFilterPayment,
      openFreeDates,
      setAvailContextMode,
      setAvailCustomFrom,
      setAvailCustomTo,
      copyFreeDates,
      copyTelegramId,
      updateProfileName,
      toggleNotif,
      updateNotifTime,
      setThemeMode,
      openDemoStates,
      showDemoLoading,
      showDemoError,
      showDemoOffline,
      retryDemo,
    ],
  );

  return <CalendarContext.Provider value={value}>{children}</CalendarContext.Provider>;
}

export function useCalendar(): CalendarContextValue {
  const ctx = useContext(CalendarContext);
  if (!ctx) throw new Error('useCalendar must be used within CalendarProvider');
  return ctx;
}

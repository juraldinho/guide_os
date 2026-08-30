import { useEffect, useMemo, useState } from 'react';
import { OverlaySheet } from '@/components/ui/OverlaySheet';
import { Chip } from '@/components/ui/Chip';
import { useToast } from '@/components/ui/Toast';
import { guideOsClient } from '@/api/createClient';
import type { AvailabilityPreview } from '@/api/types';
import { USE_MOCK_API } from '@/config';
import { t } from '@/i18n/strings';
import { useCalendar } from '@/features/calendar/CalendarContext';
import { buildFreeDatesText, describeAvailContext } from './lib/availability';
import { getAvailContextRange } from './lib/periods';
import { copyText } from '@/utils/copyText';

function initialCustomRange(
  availOpenFrom: 'calendar' | 'reports',
  calendarCtx: {
    calendarScreen: 'feed' | 'day';
    selectedDate: string;
    viewMonth: number;
    viewYear: number;
  },
  reports: { period: import('./lib/types').ReportsPeriod; month: number; year: number },
  entries: import('@/api/types').CalendarEntry[],
) {
  return getAvailContextRange(
    availOpenFrom,
    { useCustom: false, customFrom: '', customTo: '' },
    calendarCtx,
    reports,
    entries,
  );
}

export function FreeDatesOverlay() {
  const {
    entries,
    availOpenFrom,
    calendarScreen,
    selectedDate,
    viewMonth,
    viewYear,
    reportsPeriod,
    reportsMonth,
    reportsYear,
    closeOverlay,
  } = useCalendar();
  const { showToast } = useToast();

  const calendarCtx = useMemo(
    () => ({ calendarScreen, selectedDate, viewMonth, viewYear }),
    [calendarScreen, selectedDate, viewMonth, viewYear],
  );
  const reports = useMemo(
    () => ({ period: reportsPeriod, month: reportsMonth, year: reportsYear }),
    [reportsPeriod, reportsMonth, reportsYear],
  );

  const contextRange = useMemo(
    () => initialCustomRange(availOpenFrom, calendarCtx, reports, entries),
    [availOpenFrom, calendarCtx, reports, entries],
  );

  const [useCustom, setUseCustom] = useState(false);
  const [customFrom, setCustomFrom] = useState(contextRange.from);
  const [customTo, setCustomTo] = useState(contextRange.to);

  const avail = useMemo(
    () => ({ useCustom, customFrom, customTo }),
    [useCustom, customFrom, customTo],
  );

  const availRange = useMemo(
    () =>
      getAvailContextRange(availOpenFrom, avail, calendarCtx, reports, entries),
    [availOpenFrom, avail, calendarCtx, reports, entries],
  );

  const [apiPreview, setApiPreview] = useState<AvailabilityPreview | null>(null);

  useEffect(() => {
    if (USE_MOCK_API) {
      setApiPreview(null);
      return;
    }

    let cancelled = false;
    guideOsClient
      .previewAvailability({ from: availRange.from, to: availRange.to })
      .then((data) => {
        if (!cancelled) setApiPreview(data);
      })
      .catch(() => {
        if (!cancelled) setApiPreview({ heading: '', text: '', freeDates: [], ranges: [] });
      });

    return () => {
      cancelled = true;
    };
  }, [availRange.from, availRange.to]);

  const contextText = describeAvailContext(availOpenFrom, avail, calendarCtx, reports, entries);
  const mockFreeText = buildFreeDatesText(entries, availOpenFrom, avail, calendarCtx, reports);
  const freeText = USE_MOCK_API ? mockFreeText : (apiPreview?.text ?? '');

  const enableCustomMode = () => {
    setUseCustom(true);
    setCustomFrom(contextRange.from);
    setCustomTo(contextRange.to);
  };

  const handleCopy = async () => {
    if (!freeText) return;
    const ok = await copyText(freeText);
    showToast(ok ? t.toastCopied : t.toastCopyFailed);
  };

  return (
    <OverlaySheet title={t.freeDatesTitle} onClose={closeOverlay}>
      <p className="text-muted" style={{ marginBottom: 8 }}>{contextText}</p>
      <div className="filter-row">
        <Chip
          label={t.availAuto}
          active={!useCustom}
          onClick={() => setUseCustom(false)}
        />
        <Chip
          label={t.availRange}
          active={useCustom}
          onClick={enableCustomMode}
        />
      </div>
      {useCustom && (
        <div className="form-row">
          <div className="form-group">
            <label className="form-label" htmlFor="avail-from">{t.availFrom}</label>
            <input
              id="avail-from"
              type="date"
              className="form-input"
              value={customFrom}
              onChange={(e) => setCustomFrom(e.target.value)}
              onInput={(e) => setCustomFrom((e.target as HTMLInputElement).value)}
            />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="avail-to">{t.availTo}</label>
            <input
              id="avail-to"
              type="date"
              className="form-input"
              value={customTo}
              onChange={(e) => setCustomTo(e.target.value)}
              onInput={(e) => setCustomTo((e.target as HTMLInputElement).value)}
            />
          </div>
        </div>
      )}
      {freeText ? (
        <>
          <div className="preview-box">{freeText}</div>
          <button type="button" className="btn btn-primary btn-block" onClick={handleCopy}>
            {t.copyClipboard}
          </button>
        </>
      ) : (
        <div className="empty-state card">
          <p>{t.freeDatesEmpty}</p>
        </div>
      )}
    </OverlaySheet>
  );
}

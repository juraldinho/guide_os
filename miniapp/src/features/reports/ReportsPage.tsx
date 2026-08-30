import { useEffect, useMemo, useState } from 'react';
import { Chip } from '@/components/ui/Chip';
import { IconChevronLeft, IconChevronRight } from '@/components/ui/Icons';
import { guideOsClient } from '@/api/createClient';
import { USE_MOCK_API } from '@/config';
import { MONTH_NAMES_CAP } from '@/i18n/ru';
import { t } from '@/i18n/strings';
import { useCalendar } from '@/features/calendar/CalendarContext';
import { getReportRange, getMockTodayYear } from './lib/periods';
import { calcSummary } from './lib/summary';
import type { ReportsSummary } from './lib/types';

const EMPTY_SUMMARY: ReportsSummary = {
  tourCount: 0,
  workDays: 0,
  income: 0,
  paidTours: 0,
  unpaidTours: 0,
};

export function ReportsPage() {
  const {
    entries,
    reportsPeriod,
    reportsMonth,
    reportsYear,
    filterStatus,
    filterPayment,
    setReportsPeriod,
    prevReportsMonth,
    nextReportsMonth,
    prevReportsYear,
    nextReportsYear,
    setFilterStatus,
    setFilterPayment,
    openFreeDates,
  } = useCalendar();

  const maxYear = getMockTodayYear();
  const range = getReportRange(reportsPeriod, reportsMonth, reportsYear, entries);
  const mockSummary = useMemo(
    () =>
      calcSummary(entries, range, {
        status: filterStatus,
        payment: filterPayment,
        company: '',
        location: '',
      }),
    [entries, range, filterStatus, filterPayment],
  );

  const [apiSummary, setApiSummary] = useState<ReportsSummary | null>(null);

  useEffect(() => {
    if (USE_MOCK_API) {
      setApiSummary(null);
      return;
    }

    let cancelled = false;
    guideOsClient
      .getReportsSummary({
        from: range.from,
        to: range.to,
        status: filterStatus,
        payment: filterPayment,
      })
      .then((data) => {
        if (!cancelled) setApiSummary(data);
      })
      .catch(() => {
        if (!cancelled) setApiSummary(EMPTY_SUMMARY);
      });

    return () => {
      cancelled = true;
    };
  }, [range.from, range.to, filterStatus, filterPayment]);

  const summary = USE_MOCK_API ? mockSummary : (apiSummary ?? EMPTY_SUMMARY);

  return (
    <main className="main">
      <h2 className="page-title">{t.reportsTitle}</h2>

      <div className="filter-row" role="group" aria-label={t.reportsPeriodLabel}>
        <Chip
          label={t.periodMonth}
          active={reportsPeriod === 'month'}
          onClick={() => setReportsPeriod('month')}
        />
        <Chip
          label={t.periodYear}
          active={reportsPeriod === 'year'}
          onClick={() => setReportsPeriod('year')}
        />
        <Chip
          label={t.periodAll}
          active={reportsPeriod === 'all'}
          onClick={() => setReportsPeriod('all')}
        />
      </div>

      {reportsPeriod === 'month' && (
        <div className="month-picker-nav" style={{ marginBottom: 12 }}>
          <button type="button" className="icon-btn" onClick={prevReportsMonth} aria-label={t.prevMonth}>
            <IconChevronLeft />
          </button>
          <span className="month-picker-title">
            {MONTH_NAMES_CAP[reportsMonth]} {reportsYear}
          </span>
          <button type="button" className="icon-btn" onClick={nextReportsMonth} aria-label={t.nextMonth}>
            <IconChevronRight />
          </button>
        </div>
      )}

      {reportsPeriod === 'year' && (
        <div className="month-picker-nav" style={{ marginBottom: 12 }}>
          <button type="button" className="icon-btn" onClick={prevReportsYear} aria-label={t.prevYear}>
            <IconChevronLeft />
          </button>
          <span className="month-picker-title">{reportsYear}</span>
          <button
            type="button"
            className="icon-btn"
            onClick={nextReportsYear}
            disabled={reportsYear >= maxYear}
            aria-label={t.nextYear}
            style={reportsYear >= maxYear ? { opacity: 0.4 } : undefined}
          >
            <IconChevronRight />
          </button>
        </div>
      )}

      {reportsPeriod === 'all' && (
        <p className="text-hint text-muted" style={{ marginBottom: 12 }}>{t.periodAllHint}</p>
      )}

      <div className="filter-row" aria-label={t.filterStatusLabel}>
        <Chip label={t.filterAll} active={filterStatus === 'all'} onClick={() => setFilterStatus('all')} />
        <Chip
          label={t.statusReserved}
          active={filterStatus === 'reserved'}
          onClick={() => setFilterStatus('reserved')}
        />
        <Chip
          label={t.statusConfirmed}
          active={filterStatus === 'confirmed'}
          onClick={() => setFilterStatus('confirmed')}
        />
      </div>

      <div className="filter-row">
        <Chip label={t.filterAll} active={filterPayment === 'all'} onClick={() => setFilterPayment('all')} />
        <Chip
          label={t.paymentPaid}
          active={filterPayment === 'paid'}
          onClick={() => setFilterPayment('paid')}
        />
        <Chip
          label={t.paymentUnpaid}
          active={filterPayment === 'unpaid'}
          onClick={() => setFilterPayment('unpaid')}
        />
      </div>

      <div className="summary-grid">
        <div className="summary-item">
          <div className="label">{t.metricTours}</div>
          <div className="value">{summary.tourCount}</div>
        </div>
        <div className="summary-item">
          <div className="label">{t.metricWorkDays}</div>
          <div className="value">{summary.workDays}</div>
        </div>
        <div className="summary-item">
          <div className="label">{t.metricIncome}</div>
          <div className="value">${summary.income}</div>
        </div>
        <div className="summary-item">
          <div className="label">{t.metricPaidTours}</div>
          <div className="value">{summary.paidTours}</div>
        </div>
        <div className="summary-item">
          <div className="label">{t.metricUnpaidTours}</div>
          <div className="value">{summary.unpaidTours}</div>
        </div>
      </div>

      <button type="button" className="btn btn-secondary btn-block" onClick={openFreeDates}>
        {t.shareFreeDates}
      </button>
    </main>
  );
}

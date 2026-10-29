import { useEffect, useMemo, useRef, useState } from 'react';
import { trackMiniAppEvent } from '@/api/analytics';
import { Chip } from '@/components/ui/Chip';
import { IconChevronLeft, IconChevronRight } from '@/components/ui/Icons';
import { guideOsClient } from '@/api/createClient';
import { MONTH_NAMES_CAP } from '@/i18n/ru';
import { t } from '@/i18n/strings';
import { useCalendar } from '@/features/calendar/CalendarContext';
import { CommissionReportsSection } from './CommissionReportsSection';
import { getCommissionReportRange, getIncomeReportRange, getMockTodayYear } from './lib/periods';
import type { ReportsSummary } from '@/api/types';

const EMPTY_SUMMARY: ReportsSummary = {
  tourCount: 0,
  workDays: 0,
  income: 0,
  tips: 0,
  totalEarnings: 0,
  paidTours: 0,
  unpaidTours: 0,
};

export function ReportsPage() {
  const {
    entries,
    tipsRevision,
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
  const range = getIncomeReportRange(reportsPeriod, reportsMonth, reportsYear, entries);
  const commissionRange = useMemo(
    () => getCommissionReportRange(reportsPeriod, reportsMonth, reportsYear),
    [reportsPeriod, reportsMonth, reportsYear],
  );
  const [apiSummary, setApiSummary] = useState<ReportsSummary | null>(null);
  const expectedIncomeTrackedRef = useRef(false);
  const [summaryLoaded, setSummaryLoaded] = useState(false);

  const [summaryError, setSummaryError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {

    let cancelled = false;
    setSummaryLoaded(false);
    setSummaryError(false);
    guideOsClient
      .getReportsSummary({
        from: range.from,
        to: range.to,
        status: filterStatus,
        payment: filterPayment,
      })
      .then((data) => {
        if (!cancelled) {
          setApiSummary(data);
          setSummaryLoaded(true);
        }
      })
      .catch(() => {
        if (!cancelled) setSummaryError(true);
      });

    return () => {
      cancelled = true;
    };
  }, [range.from, range.to, filterStatus, filterPayment, tipsRevision, entries, attempt]);

  useEffect(() => {
    if (!summaryLoaded || expectedIncomeTrackedRef.current) return;
    expectedIncomeTrackedRef.current = true;
    trackMiniAppEvent('expected_income_viewed');
  }, [summaryLoaded]);

  const summary = apiSummary ?? EMPTY_SUMMARY;

  return (
    <main className="main">
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

      <p className="text-muted">Фильтры применяются к турам. Чаевые учитываются за весь выбранный период.</p>
      <p className="text-muted">Доход от туров включает выбранные оплаченные и неоплаченные туры. Чаевые уже получены.</p>
      {summaryError ? <div role="alert">Не удалось загрузить итоги. <button className="btn btn-secondary" onClick={() => setAttempt((n) => n + 1)}>Повторить</button></div> :
      !summaryLoaded ? <p role="status">Загрузка итогов…</p> :
      <div className="summary-grid" data-testid="tour-reports-summary">
        <div className="summary-item">
          <div className="label">{t.metricTours}</div>
          <div className="value">{summary.tourCount}</div>
        </div>
        <div className="summary-item">
          <div className="label">{t.metricWorkDays}</div>
          <div className="value">{summary.workDays}</div>
        </div>
        <div className="summary-item">
          <div className="label">Доход от туров</div>
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
        <div className="summary-item">
          <div className="label">Чаевые</div>
          <div className="value">${summary.tips}</div>
        </div>
        <div className="summary-item">
          <div className="label">Общий доход</div>
          <div className="value">${summary.totalEarnings}</div>
        </div>
      </div>}

      <CommissionReportsSection range={commissionRange} />

      <button type="button" className="btn btn-secondary btn-block" onClick={openFreeDates}>
        {t.shareFreeDates}
      </button>
    </main>
  );
}

import { useEffect, useState } from 'react';
import { guideOsClient } from '@/api/createClient';
import type { CommissionReportsSummary } from '@/api/types';
import { t } from '@/i18n/strings';

export interface CommissionReportsSectionProps {
  range: {
    from: string;
    to: string;
  };
}

type LoadState = 'loading' | 'success' | 'error';

export function CommissionReportsSection({ range }: CommissionReportsSectionProps) {
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [summary, setSummary] = useState<CommissionReportsSummary | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoadState('loading');
    setSummary(null);

    guideOsClient
      .getCommissionReportsSummary({ from: range.from, to: range.to })
      .then((data) => {
        if (cancelled) return;
        setSummary(data);
        setLoadState('success');
      })
      .catch(() => {
        if (cancelled) return;
        setSummary(null);
        setLoadState('error');
      });

    return () => {
      cancelled = true;
    };
  }, [range.from, range.to, retryNonce]);

  const isEmpty =
    loadState === 'success' &&
    summary != null &&
    summary.totalCommission === 0 &&
    summary.recordCount === 0 &&
    summary.byCompany.length === 0;

  return (
    <section
      className="card card-pad-sm"
      style={{ marginBottom: 'var(--space-md)' }}
      aria-labelledby="commission-reports-title"
      data-testid="commission-reports-section"
    >
      <h2
        id="commission-reports-title"
        style={{ fontSize: 16, fontWeight: 600, margin: '0 0 var(--space-sm)' }}
      >
        {t.commissionReportsTitle}
      </h2>

      {loadState === 'loading' && (
        <p className="text-muted" role="status">
          {t.commissionReportsLoading}
        </p>
      )}

      {loadState === 'error' && (
        <div role="alert">
          <p className="text-muted" style={{ marginBottom: 'var(--space-sm)' }}>
            {t.commissionReportsLoadError}
          </p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setRetryNonce((value) => value + 1)}
          >
            {t.retry}
          </button>
        </div>
      )}

      {loadState === 'success' && summary != null && (
        <>
          <div className="summary-grid" style={{ marginBottom: isEmpty ? 'var(--space-sm)' : undefined }}>
            <div className="summary-item">
              <div className="label">{t.commissionReportsTotal}</div>
              <div className="value">{summary.totalCommission}</div>
            </div>
            <div className="summary-item">
              <div className="label">{t.commissionReportsCount}</div>
              <div className="value">{summary.recordCount}</div>
            </div>
          </div>

          {isEmpty ? (
            <p className="text-muted" role="status">
              {t.commissionReportsEmpty}
            </p>
          ) : (
            <>
              <h3
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  margin: '0 0 var(--space-sm)',
                }}
              >
                {t.commissionReportsByCompany}
              </h3>
              <ul
                style={{
                  listStyle: 'none',
                  margin: 0,
                  padding: 0,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 'var(--space-sm)',
                }}
              >
                {summary.byCompany.map((row) => (
                  <li key={row.placeId}>
                    <div className="detail-row" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                      <span className="guideshop-wrap" style={{ fontWeight: 500 }}>
                        {row.companyName}
                      </span>
                      <span className="detail-label">
                        {t.commissionReportsCompanyTotal(row.totalCommission)}
                      </span>
                      <span className="detail-label">
                        {t.commissionReportsCompanyCount(row.recordCount)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  );
}

import { useEffect, useMemo, useState } from 'react';
import { ApiError } from '@/api/httpClient';
import { guideOsClient } from '@/api/createClient';
import type { OfficialPointsCompanySummary, OfficialPointsSummary } from '@/api/types';
import { OverlaySheet } from '@/components/ui/OverlaySheet';
import {
  OfficialHistorySheet,
  companyNameMapFromSummary,
} from '@/features/guideshop/OfficialHistorySheet';
import { t } from '@/i18n/strings';

type SummaryError = 'integration_disabled' | 'access_denied' | 'generic';

function formatPts(amount: string, unit: string): string {
  return `${amount} ${unit}`;
}

interface OfficialPointsSheetProps {
  companyId: string;
  companyDisplayName: string;
  open: boolean;
  onClose: () => void;
}

export function OfficialPointsSheet({
  companyId,
  companyDisplayName,
  open,
  onClose,
}: OfficialPointsSheetProps) {
  const [summary, setSummary] = useState<OfficialPointsSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<SummaryError | null>(null);
  const [loadNonce, setLoadNonce] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(false);

  useEffect(() => {
    if (!open) {
      setSummary(null);
      setError(null);
      setLoading(false);
      setHistoryOpen(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSummary(null);
    void guideOsClient
      .getOfficialPointsSummary()
      .then((result) => {
        if (cancelled) return;
        setSummary(result);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setSummary(null);
        if (err instanceof ApiError && err.code === 'integration_disabled') {
          setError('integration_disabled');
        } else if (err instanceof ApiError && err.code === 'access_denied') {
          setError('access_denied');
        } else {
          setError('generic');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, loadNonce]);

  const companyNameMap = useMemo(
    () => companyNameMapFromSummary(summary?.companies ?? []),
    [summary],
  );

  if (!open) return null;

  const companyRow: OfficialPointsCompanySummary | null =
    summary?.companies.find((item) => item.companyId === companyId) ?? null;

  const errorMessage =
    error === 'integration_disabled'
      ? t.guideShopOfficialIntegrationDisabled
      : error === 'access_denied'
        ? t.guideShopOfficialAccessDenied
        : t.guideShopPointsLoadError;

  const unit = summary?.unit ?? 'PTS';
  const isEmpty =
    summary != null &&
    summary.pendingTotal === '0.00' &&
    summary.creditedTotal === '0.00' &&
    summary.companies.length === 0;

  const closePoints = () => {
    setHistoryOpen(false);
    onClose();
  };

  return (
    <>
      {!historyOpen && (
        <OverlaySheet
          title={t.guideShopPointsTitle}
          onClose={closePoints}
          footer={
            <div className="guideshop-detail-actions">
              {summary && !loading && !error && (
                <button
                  type="button"
                  className="btn btn-secondary btn-block"
                  onClick={() => setHistoryOpen(true)}
                >
                  {t.guideShopHistoryAction}
                </button>
              )}
              {error === 'generic' && (
                <button
                  type="button"
                  className="btn btn-primary btn-block"
                  onClick={() => setLoadNonce((value) => value + 1)}
                >
                  {t.retry}
                </button>
              )}
              <button type="button" className="btn btn-secondary btn-block" onClick={closePoints}>
                {t.close}
              </button>
            </div>
          }
        >
          <div className="guideshop-detail-body">
            <span className="guideshop-badge guideshop-badge-official">
              {t.guideShopOfficialBadge}
            </span>
            <p className="text-muted guideshop-wrap">{companyDisplayName}</p>

            {loading && (
              <p className="text-muted" role="status">
                {t.guideShopPointsLoading}
              </p>
            )}

            {!loading && error && (
              <p className="guideshop-section-error" role="alert">
                {errorMessage}
              </p>
            )}

            {!loading && !error && summary && (
              <>
                {isEmpty ? (
                  <p className="text-muted" role="status">
                    {t.guideShopPointsEmpty}
                  </p>
                ) : (
                  <>
                    <div className="guideshop-points-totals">
                      <div className="detail-row">
                        <span className="detail-label">{t.guideShopPointsPending}</span>
                        <span className="detail-value">
                          {formatPts(summary.pendingTotal, unit)}
                        </span>
                      </div>
                      <div className="detail-row">
                        <span className="detail-label">{t.guideShopPointsCredited}</span>
                        <span className="detail-value">
                          {formatPts(summary.creditedTotal, unit)}
                        </span>
                      </div>
                    </div>

                    <h3 className="guideshop-points-company-title">
                      {t.guideShopPointsCompanyBlock}
                    </h3>
                    {companyRow ? (
                      <div className="guideshop-points-company-card">
                        <strong className="guideshop-wrap">{companyRow.displayName}</strong>
                        <div className="detail-row">
                          <span className="detail-label">{t.guideShopPointsPending}</span>
                          <span className="detail-value">
                            {formatPts(companyRow.pendingTotal, unit)}
                          </span>
                        </div>
                        <div className="detail-row">
                          <span className="detail-label">{t.guideShopPointsCredited}</span>
                          <span className="detail-value">
                            {formatPts(companyRow.creditedTotal, unit)}
                          </span>
                        </div>
                      </div>
                    ) : (
                      <p className="text-muted" role="status">
                        {t.guideShopPointsCompanyEmpty}
                      </p>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        </OverlaySheet>
      )}

      <OfficialHistorySheet
        companyId={companyId}
        companyDisplayName={companyDisplayName}
        companyNameMap={companyNameMap}
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
      />
    </>
  );
}

import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '@/api/httpClient';
import { guideOsClient } from '@/api/createClient';
import type { OfficialVisit } from '@/api/types';
import { OverlaySheet } from '@/components/ui/OverlaySheet';
import { TIMEZONE } from '@/config';
import { t } from '@/i18n/strings';

function formatVisitAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: TIMEZONE,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function formatVisitStatus(status: string): string {
  if (status === 'active') return t.guideShopVisitStatusActive;
  if (status === 'completed') return t.guideShopVisitStatusCompleted;
  if (status === 'cancelled') return t.guideShopVisitStatusCancelled;
  return t.guideShopVisitStatusUnknown(status);
}

function formatPaymentStatus(status: string): string {
  if (status === 'paid') return t.guideShopVisitPaymentPaid;
  if (status === 'unpaid') return t.guideShopVisitPaymentUnpaid;
  return t.guideShopVisitPaymentUnknown(status);
}

type ListError = 'integration_disabled' | 'access_denied' | 'generic';

interface OfficialVisitsSheetsProps {
  companyId: string;
  companyDisplayName: string;
  open: boolean;
  onClose: () => void;
}

export function OfficialVisitsSheets({
  companyId,
  companyDisplayName,
  open,
  onClose,
}: OfficialVisitsSheetsProps) {
  const [visits, setVisits] = useState<OfficialVisit[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [listError, setListError] = useState<ListError | null>(null);

  const [selectedVisitId, setSelectedVisitId] = useState<string | null>(null);
  const [visitDetail, setVisitDetail] = useState<OfficialVisit | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(false);
  const [detailNotFound, setDetailNotFound] = useState(false);
  const [detailNonce, setDetailNonce] = useState(0);

  const applyListError = (error: unknown) => {
    if (error instanceof ApiError && error.code === 'integration_disabled') {
      setListError('integration_disabled');
    } else if (error instanceof ApiError && error.code === 'access_denied') {
      setListError('access_denied');
    } else {
      setListError('generic');
    }
  };

  const loadVisits = useCallback(async () => {
    setLoading(true);
    setListError(null);
    setVisits([]);
    setNextCursor(null);
    try {
      const result = await guideOsClient.listOfficialVisits();
      setVisits(result.visits.filter((visit) => visit.companyId === companyId));
      setNextCursor(result.page.nextCursor);
    } catch (error) {
      setVisits([]);
      setNextCursor(null);
      applyListError(error);
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  const loadMore = useCallback(async () => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const result = await guideOsClient.listOfficialVisits({ cursor: nextCursor });
      const matched = result.visits.filter((visit) => visit.companyId === companyId);
      setVisits((prev) => [...prev, ...matched]);
      setNextCursor(result.page.nextCursor);
    } catch (error) {
      applyListError(error);
    } finally {
      setLoadingMore(false);
    }
  }, [companyId, loadingMore, nextCursor]);

  useEffect(() => {
    if (!open) {
      setVisits([]);
      setNextCursor(null);
      setListError(null);
      setLoading(false);
      setSelectedVisitId(null);
      return;
    }
    void loadVisits();
  }, [open, loadVisits]);

  useEffect(() => {
    if (!selectedVisitId) {
      setVisitDetail(null);
      setDetailLoading(false);
      setDetailError(false);
      setDetailNotFound(false);
      return;
    }

    let cancelled = false;
    setVisitDetail(null);
    setDetailLoading(true);
    setDetailError(false);
    setDetailNotFound(false);

    void guideOsClient
      .getOfficialVisit(selectedVisitId)
      .then((visit) => {
        if (cancelled) return;
        if (visit === null) {
          setDetailNotFound(true);
          setVisitDetail(null);
        } else {
          setVisitDetail(visit);
        }
      })
      .catch(() => {
        if (cancelled) return;
        setDetailError(true);
        setVisitDetail(null);
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedVisitId, detailNonce]);

  if (!open) return null;

  const listErrorMessage =
    listError === 'integration_disabled'
      ? t.guideShopOfficialIntegrationDisabled
      : listError === 'access_denied'
        ? t.guideShopOfficialAccessDenied
        : t.guideShopVisitsLoadError;

  const closeVisits = () => {
    setSelectedVisitId(null);
    onClose();
  };

  const closeVisitDetail = () => {
    setSelectedVisitId(null);
  };

  const detailTitle =
    visitDetail != null
      ? formatVisitAt(visitDetail.visitAt)
      : t.guideShopVisitDetailTitle;

  return (
    <>
      <OverlaySheet
        title={t.guideShopVisitsTitle}
        onClose={closeVisits}
        footer={
          <div className="guideshop-detail-actions">
            {listError === 'generic' && (
              <button
                type="button"
                className="btn btn-primary btn-block"
                onClick={() => void loadVisits()}
              >
                {t.retry}
              </button>
            )}
            <button type="button" className="btn btn-secondary btn-block" onClick={closeVisits}>
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
              {t.guideShopVisitsLoading}
            </p>
          )}

          {!loading && listError && (
            <p className="guideshop-section-error" role="alert">
              {listErrorMessage}
            </p>
          )}

          {!loading && !listError && visits.length === 0 && (
            <p className="text-muted" role="status">
              {t.guideShopVisitsEmpty}
            </p>
          )}

          {!loading && !listError && visits.length > 0 && (
            <ul className="guideshop-visit-list">
              {visits.map((visit) => (
                <li key={visit.id}>
                  <button
                    type="button"
                    className="guideshop-visit-row"
                    onClick={() => setSelectedVisitId(visit.id)}
                    aria-label={t.guideShopOpenVisit(formatVisitAt(visit.visitAt))}
                  >
                    <strong className="guideshop-visit-date">
                      {formatVisitAt(visit.visitAt)}
                    </strong>
                    <span className="guideshop-visit-meta">
                      {t.guideShopVisitTourists(visit.touristCount)}
                    </span>
                    <span className="guideshop-visit-meta">
                      {formatVisitStatus(visit.status)}
                    </span>
                    <span className="guideshop-visit-meta">
                      {formatPaymentStatus(visit.customerPaymentStatus)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {!loading && !listError && nextCursor && (
            <button
              type="button"
              className="btn btn-secondary btn-block"
              disabled={loadingMore}
              onClick={() => void loadMore()}
            >
              {loadingMore ? t.guideShopVisitsLoadingMore : t.guideShopVisitsLoadMore}
            </button>
          )}
        </div>
      </OverlaySheet>

      {selectedVisitId && (
        <OverlaySheet
          title={detailTitle}
          onClose={closeVisitDetail}
          footer={
            <div className="guideshop-detail-actions">
              {detailError && (
                <button
                  type="button"
                  className="btn btn-primary btn-block"
                  onClick={() => setDetailNonce((value) => value + 1)}
                >
                  {t.retry}
                </button>
              )}
              <button
                type="button"
                className="btn btn-secondary btn-block"
                onClick={closeVisitDetail}
              >
                {t.close}
              </button>
            </div>
          }
        >
          <div className="guideshop-detail-body">
            {detailLoading && (
              <p className="text-muted" role="status">
                {t.guideShopVisitDetailLoading}
              </p>
            )}

            {!detailLoading && detailError && (
              <p className="guideshop-section-error" role="alert">
                {t.guideShopVisitDetailError}
              </p>
            )}

            {!detailLoading && detailNotFound && (
              <p className="text-muted" role="status">
                {t.guideShopVisitDetailNotFound}
              </p>
            )}

            {!detailLoading && visitDetail && (
              <>
                <span className="guideshop-badge guideshop-badge-official">
                  {t.guideShopOfficialBadge}
                </span>
                <div className="detail-row">
                  <span className="detail-label">{t.guideShopVisitFieldCompany}</span>
                  <span className="detail-value guideshop-wrap">{companyDisplayName}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">{t.guideShopVisitFieldDate}</span>
                  <span className="detail-value">{formatVisitAt(visitDetail.visitAt)}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">{t.guideShopVisitFieldTourists}</span>
                  <span className="detail-value">{visitDetail.touristCount}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">{t.guideShopVisitFieldStatus}</span>
                  <span className="detail-value">
                    {formatVisitStatus(visitDetail.status)}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">{t.guideShopVisitFieldPayment}</span>
                  <span className="detail-value">
                    {formatPaymentStatus(visitDetail.customerPaymentStatus)}
                  </span>
                </div>
                {visitDetail.customerPaymentStatus === 'paid' &&
                  visitDetail.customerPaidAt && (
                    <div className="detail-row">
                      <span className="detail-label">{t.guideShopVisitFieldPaidAt}</span>
                      <span className="detail-value">
                        {formatVisitAt(visitDetail.customerPaidAt)}
                      </span>
                    </div>
                  )}
              </>
            )}
          </div>
        </OverlaySheet>
      )}
    </>
  );
}

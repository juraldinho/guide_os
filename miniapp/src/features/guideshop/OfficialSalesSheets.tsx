import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '@/api/httpClient';
import { guideOsClient } from '@/api/createClient';
import type { OfficialSale } from '@/api/types';
import { OverlaySheet } from '@/components/ui/OverlaySheet';
import { TIMEZONE } from '@/config';
import { t } from '@/i18n/strings';

function formatSaleAt(iso: string): string {
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

function formatAmount(amount: string, currency: string): string {
  return `${amount} ${currency}`;
}

function formatPaymentMethod(method: string): string {
  if (method === 'cash') return t.guideShopSalePaymentCash;
  if (method === 'card') return t.guideShopSalePaymentCard;
  if (method === 'transfer') return t.guideShopSalePaymentTransfer;
  if (method === 'unknown') return t.guideShopSalePaymentUnknown;
  return t.guideShopSalePaymentOther(method);
}

type ListError = 'integration_disabled' | 'access_denied' | 'generic';

interface OfficialSalesSheetsProps {
  companyId: string;
  companyDisplayName: string;
  open: boolean;
  onClose: () => void;
}

export function OfficialSalesSheets({
  companyId,
  companyDisplayName,
  open,
  onClose,
}: OfficialSalesSheetsProps) {
  const [sales, setSales] = useState<OfficialSale[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [listError, setListError] = useState<ListError | null>(null);

  const [selectedSaleId, setSelectedSaleId] = useState<string | null>(null);
  const [saleDetail, setSaleDetail] = useState<OfficialSale | null>(null);
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

  const loadSales = useCallback(async () => {
    setLoading(true);
    setListError(null);
    setSales([]);
    setNextCursor(null);
    try {
      const result = await guideOsClient.listOfficialSales();
      setSales(result.sales.filter((sale) => sale.companyId === companyId));
      setNextCursor(result.page.nextCursor);
    } catch (error) {
      setSales([]);
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
      const result = await guideOsClient.listOfficialSales({ cursor: nextCursor });
      const matched = result.sales.filter((sale) => sale.companyId === companyId);
      setSales((prev) => [...prev, ...matched]);
      setNextCursor(result.page.nextCursor);
    } catch (error) {
      applyListError(error);
    } finally {
      setLoadingMore(false);
    }
  }, [companyId, loadingMore, nextCursor]);

  useEffect(() => {
    if (!open) {
      setSales([]);
      setNextCursor(null);
      setListError(null);
      setLoading(false);
      setSelectedSaleId(null);
      return;
    }
    void loadSales();
  }, [open, loadSales]);

  useEffect(() => {
    if (!selectedSaleId) {
      setSaleDetail(null);
      setDetailLoading(false);
      setDetailError(false);
      setDetailNotFound(false);
      return;
    }

    let cancelled = false;
    setSaleDetail(null);
    setDetailLoading(true);
    setDetailError(false);
    setDetailNotFound(false);

    void guideOsClient
      .getOfficialSale(selectedSaleId)
      .then((sale) => {
        if (cancelled) return;
        if (sale === null) {
          setDetailNotFound(true);
          setSaleDetail(null);
        } else {
          setSaleDetail(sale);
        }
      })
      .catch(() => {
        if (cancelled) return;
        setDetailError(true);
        setSaleDetail(null);
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedSaleId, detailNonce]);

  if (!open) return null;

  const listErrorMessage =
    listError === 'integration_disabled'
      ? t.guideShopOfficialIntegrationDisabled
      : listError === 'access_denied'
        ? t.guideShopOfficialAccessDenied
        : t.guideShopSalesLoadError;

  const closeSales = () => {
    setSelectedSaleId(null);
    onClose();
  };

  const closeSaleDetail = () => {
    setSelectedSaleId(null);
  };

  const detailTitle =
    saleDetail != null
      ? formatAmount(saleDetail.amount, saleDetail.currency)
      : t.guideShopSaleDetailTitle;

  return (
    <>
      <OverlaySheet
        title={t.guideShopSalesTitle}
        onClose={closeSales}
        footer={
          <div className="guideshop-detail-actions">
            {listError === 'generic' && (
              <button
                type="button"
                className="btn btn-primary btn-block"
                onClick={() => void loadSales()}
              >
                {t.retry}
              </button>
            )}
            <button type="button" className="btn btn-secondary btn-block" onClick={closeSales}>
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
              {t.guideShopSalesLoading}
            </p>
          )}

          {!loading && listError && (
            <p className="guideshop-section-error" role="alert">
              {listErrorMessage}
            </p>
          )}

          {!loading && !listError && sales.length === 0 && (
            <p className="text-muted" role="status">
              {t.guideShopSalesEmpty}
            </p>
          )}

          {!loading && !listError && sales.length > 0 && (
            <ul className="guideshop-visit-list">
              {sales.map((sale) => (
                <li key={sale.id}>
                  <button
                    type="button"
                    className="guideshop-visit-row"
                    onClick={() => setSelectedSaleId(sale.id)}
                    aria-label={t.guideShopOpenSale(
                      formatAmount(sale.amount, sale.currency),
                    )}
                  >
                    <strong className="guideshop-visit-date">
                      {formatAmount(sale.amount, sale.currency)}
                    </strong>
                    <span className="guideshop-visit-meta guideshop-wrap">
                      {sale.categoryName}
                    </span>
                    <span className="guideshop-visit-meta">
                      {formatPaymentMethod(sale.paymentMethod)}
                    </span>
                    <span className="guideshop-visit-meta">
                      {formatSaleAt(sale.createdAt)}
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
              {loadingMore ? t.guideShopSalesLoadingMore : t.guideShopSalesLoadMore}
            </button>
          )}
        </div>
      </OverlaySheet>

      {selectedSaleId && (
        <OverlaySheet
          title={detailTitle}
          onClose={closeSaleDetail}
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
                onClick={closeSaleDetail}
              >
                {t.close}
              </button>
            </div>
          }
        >
          <div className="guideshop-detail-body">
            {detailLoading && (
              <p className="text-muted" role="status">
                {t.guideShopSaleDetailLoading}
              </p>
            )}

            {!detailLoading && detailError && (
              <p className="guideshop-section-error" role="alert">
                {t.guideShopSaleDetailError}
              </p>
            )}

            {!detailLoading && detailNotFound && (
              <p className="text-muted" role="status">
                {t.guideShopSaleDetailNotFound}
              </p>
            )}

            {!detailLoading && saleDetail && (
              <>
                <span className="guideshop-badge guideshop-badge-official">
                  {t.guideShopOfficialBadge}
                </span>
                <div className="detail-row">
                  <span className="detail-label">{t.guideShopSaleFieldCompany}</span>
                  <span className="detail-value guideshop-wrap">{companyDisplayName}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">{t.guideShopSaleFieldAmount}</span>
                  <span className="detail-value">
                    {formatAmount(saleDetail.amount, saleDetail.currency)}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">{t.guideShopSaleFieldCategory}</span>
                  <span className="detail-value guideshop-wrap">
                    {saleDetail.categoryName}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">{t.guideShopSaleFieldPayment}</span>
                  <span className="detail-value">
                    {formatPaymentMethod(saleDetail.paymentMethod)}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">{t.guideShopSaleFieldCreated}</span>
                  <span className="detail-value">{formatSaleAt(saleDetail.createdAt)}</span>
                </div>
                {saleDetail.comment && (
                  <div className="detail-row">
                    <span className="detail-label">{t.guideShopSaleFieldComment}</span>
                    <span className="detail-value guideshop-wrap">{saleDetail.comment}</span>
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

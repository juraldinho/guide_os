import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError } from '@/api/httpClient';
import { guideOsClient } from '@/api/createClient';
import type { OfficialHistoryItem, OfficialPointsCompanySummary } from '@/api/types';
import { OverlaySheet } from '@/components/ui/OverlaySheet';
import { TIMEZONE } from '@/config';
import { t } from '@/i18n/strings';

function formatPaidAt(iso: string): string {
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

function formatPts(amount: string, unit: string): string {
  return `${amount} ${unit}`;
}

type ListError = 'integration_disabled' | 'access_denied' | 'generic';

interface OfficialHistorySheetProps {
  companyId: string;
  companyDisplayName: string;
  companyNameMap: Record<string, string>;
  open: boolean;
  onClose: () => void;
}

export function OfficialHistorySheet({
  companyId,
  companyDisplayName,
  companyNameMap,
  open,
  onClose,
}: OfficialHistorySheetProps) {
  const [items, setItems] = useState<OfficialHistoryItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [listError, setListError] = useState<ListError | null>(null);

  const names = useMemo(() => {
    const map = { ...companyNameMap };
    if (companyId && companyDisplayName) {
      map[companyId] = companyDisplayName;
    }
    return map;
  }, [companyId, companyDisplayName, companyNameMap]);

  const resolveCompanyName = (id: string): string =>
    names[id] ?? t.guideShopHistoryUnknownCompany;

  const applyListError = (error: unknown) => {
    if (error instanceof ApiError && error.code === 'integration_disabled') {
      setListError('integration_disabled');
    } else if (error instanceof ApiError && error.code === 'access_denied') {
      setListError('access_denied');
    } else {
      setListError('generic');
    }
  };

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setListError(null);
    setItems([]);
    setNextCursor(null);
    try {
      const result = await guideOsClient.listOfficialHistory();
      setItems(result.history.filter((item) => item.companyId === companyId));
      setNextCursor(result.page.nextCursor);
    } catch (error) {
      setItems([]);
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
      const result = await guideOsClient.listOfficialHistory({ cursor: nextCursor });
      const matched = result.history.filter((item) => item.companyId === companyId);
      setItems((prev) => [...prev, ...matched]);
      setNextCursor(result.page.nextCursor);
    } catch (error) {
      applyListError(error);
    } finally {
      setLoadingMore(false);
    }
  }, [companyId, loadingMore, nextCursor]);

  useEffect(() => {
    if (!open) {
      setItems([]);
      setNextCursor(null);
      setListError(null);
      setLoading(false);
      return;
    }
    void loadHistory();
  }, [open, loadHistory]);

  if (!open) return null;

  const listErrorMessage =
    listError === 'integration_disabled'
      ? t.guideShopOfficialIntegrationDisabled
      : listError === 'access_denied'
        ? t.guideShopOfficialAccessDenied
        : t.guideShopHistoryLoadError;

  return (
    <OverlaySheet
      title={t.guideShopHistoryTitle}
      onClose={onClose}
      footer={
        <div className="guideshop-detail-actions">
          {listError === 'generic' && (
            <button
              type="button"
              className="btn btn-primary btn-block"
              onClick={() => void loadHistory()}
            >
              {t.retry}
            </button>
          )}
          <button type="button" className="btn btn-secondary btn-block" onClick={onClose}>
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
            {t.guideShopHistoryLoading}
          </p>
        )}

        {!loading && listError && (
          <p className="guideshop-section-error" role="alert">
            {listErrorMessage}
          </p>
        )}

        {!loading && !listError && items.length === 0 && (
          <p className="text-muted" role="status">
            {t.guideShopHistoryEmpty}
          </p>
        )}

        {!loading && !listError && items.length > 0 && (
          <ul className="guideshop-visit-list">
            {items.map((item) => (
              <li key={item.id} className="guideshop-history-row">
                <strong className="guideshop-visit-date">
                  {formatPts(item.amount, item.unit)}
                </strong>
                <span className="guideshop-visit-meta guideshop-wrap">
                  {resolveCompanyName(item.companyId)}
                </span>
                <span className="guideshop-visit-meta">{formatPaidAt(item.paidAt)}</span>
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
            {loadingMore ? t.guideShopHistoryLoadingMore : t.guideShopHistoryLoadMore}
          </button>
        )}
      </div>
    </OverlaySheet>
  );
}

export function companyNameMapFromSummary(
  companies: OfficialPointsCompanySummary[],
): Record<string, string> {
  const map: Record<string, string> = {};
  for (const item of companies) {
    map[item.companyId] = item.displayName;
  }
  return map;
}

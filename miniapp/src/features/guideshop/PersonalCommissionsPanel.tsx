import type { PersonalCommission } from '@/api/types';
import { t } from '@/i18n/strings';
import {
  formatMoneyAmount,
  formatOccurredAtDisplay,
  sortCommissionsNewestFirst,
  summarizeActiveCommissions,
} from './lib/commissionMoney';

interface PersonalCommissionsPanelProps {
  commissions: PersonalCommission[];
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  onOpen: (commission: PersonalCommission) => void;
}

export function PersonalCommissionsPanel({
  commissions,
  loading,
  error,
  onRetry,
  onOpen,
}: PersonalCommissionsPanelProps) {
  const active = commissions.filter((item) => item.status === 'active');
  const summary = summarizeActiveCommissions(active);
  const history = sortCommissionsNewestFirst(active);

  return (
    <section className="guideshop-commissions" aria-labelledby="guideshop-commissions-title">
      <h3 id="guideshop-commissions-title" className="guideshop-commissions-title">
        {t.guideShopCommissionsTitle}
      </h3>

      {loading && (
        <p className="text-muted" role="status">
          {t.guideShopCommissionsLoading}
        </p>
      )}

      {!loading && error && (
        <div className="guideshop-section-error" role="alert">
          <p>{t.guideShopCommissionsLoadError}</p>
          <button type="button" className="btn btn-secondary" onClick={onRetry}>
            {t.retry}
          </button>
        </div>
      )}

      {!loading && !error && (
        <>
          <div className="guideshop-commission-summary" aria-label={t.guideShopCommissionsSummary}>
            {summary.isEmpty ? (
              <p className="text-muted">{t.guideShopCommissionsEmptySummary}</p>
            ) : (
              <>
                {summary.incomesByCurrency.length > 0 && (
                  <ul className="guideshop-commission-totals">
                    {summary.incomesByCurrency.map((row) => (
                      <li key={row.currency} className="guideshop-commission-total">
                        {formatMoneyAmount(row.minor, row.currency)}
                      </li>
                    ))}
                  </ul>
                )}
                {summary.pointsTotal > 0 && (
                  <p className="guideshop-commission-points">
                    {t.guideShopCommissionsPoints(summary.pointsTotal)}
                  </p>
                )}
              </>
            )}
          </div>

          <div className="guideshop-commission-history">
            <h4 className="guideshop-commission-history-title">{t.guideShopCommissionsHistory}</h4>
            {history.length === 0 ? (
              <p className="text-muted">{t.guideShopCommissionsEmptyHistory}</p>
            ) : (
              <ul className="guideshop-commission-list">
                {history.map((item) => {
                  const dateLabel = formatOccurredAtDisplay(item.occurredAt);
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        className="guideshop-commission-row"
                        onClick={() => onOpen(item)}
                        aria-label={t.guideShopOpenCommission(dateLabel)}
                      >
                        <span className="guideshop-commission-date">{dateLabel}</span>
                        <span className="guideshop-commission-meta">
                          {item.purchaseAmountMinor != null && item.currency && (
                            <span>
                              {t.guideShopCommissionPurchase}:{' '}
                              {formatMoneyAmount(item.purchaseAmountMinor, item.currency)}
                            </span>
                          )}
                          {item.receivedIncomeMinor != null && item.currency && (
                            <span>
                              {t.guideShopCommissionIncome}:{' '}
                              {formatMoneyAmount(item.receivedIncomeMinor, item.currency)}
                            </span>
                          )}
                          {item.receivedPoints != null && (
                            <span>
                              {t.guideShopCommissionPointsLabel} — {item.receivedPoints}
                            </span>
                          )}
                          {item.note && (
                            <span className="guideshop-commission-note-preview">{item.note}</span>
                          )}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </>
      )}
    </section>
  );
}

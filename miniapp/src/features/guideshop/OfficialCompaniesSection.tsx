import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError } from '@/api/httpClient';
import { guideOsClient } from '@/api/createClient';
import type { OfficialCompany } from '@/api/types';
import { OverlaySheet } from '@/components/ui/OverlaySheet';
import { OfficialVisitsSheets } from '@/features/guideshop/OfficialVisitsSheets';
import { OfficialPointsSheet } from '@/features/guideshop/OfficialPointsSheet';
import { t } from '@/i18n/strings';

function formatOfficialStatus(status: string): string {
  if (status === 'active') return t.guideShopOfficialStatusActive;
  if (status === 'inactive') return t.guideShopOfficialStatusInactive;
  return t.guideShopOfficialStatusUnknown(status);
}

function matchesOfficialSearch(company: OfficialCompany, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  const fields = [company.displayName, company.type, company.address, company.phone];
  return fields.some((value) => value?.toLowerCase().includes(needle));
}

function optionalValue(value: string | null): string {
  if (value === null || !value.trim()) return t.guideShopOfficialNotSpecified;
  return value;
}

type OfficialListError = 'integration_disabled' | 'access_denied' | 'generic';

interface OfficialCompaniesSectionProps {
  searchQuery: string;
}

export function OfficialCompaniesSection({ searchQuery }: OfficialCompaniesSectionProps) {
  const [companies, setCompanies] = useState<OfficialCompany[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<OfficialListError | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<OfficialCompany | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(false);
  const [detailNotFound, setDetailNotFound] = useState(false);
  const [detailNonce, setDetailNonce] = useState(0);
  const [visitsOpen, setVisitsOpen] = useState(false);
  const [pointsOpen, setPointsOpen] = useState(false);

  const loadCompanies = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setListError(null);
    try {
      const result = await guideOsClient.listOfficialCompanies({ signal });
      if (signal?.aborted) return;
      setCompanies(result.companies);
    } catch (error) {
      if (signal?.aborted) return;
      setCompanies([]);
      if (error instanceof ApiError && error.code === 'integration_disabled') {
        setListError('integration_disabled');
      } else if (error instanceof ApiError && error.code === 'access_denied') {
        setListError('access_denied');
      } else {
        setListError('generic');
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadCompanies(controller.signal);
    return () => controller.abort();
  }, [loadCompanies]);

  useEffect(() => {
    setVisitsOpen(false);
    setPointsOpen(false);
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setDetailLoading(false);
      setDetailError(false);
      setDetailNotFound(false);
      return;
    }

    const controller = new AbortController();
    setDetail(null);
    setDetailLoading(true);
    setDetailError(false);
    setDetailNotFound(false);

    void guideOsClient
      .getOfficialCompany(selectedId, { signal: controller.signal })
      .then((company) => {
        if (controller.signal.aborted) return;
        if (company === null) {
          setDetailNotFound(true);
          setDetail(null);
        } else {
          setDetail(company);
        }
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof Error && error.name === 'AbortError') return;
        setDetailError(true);
        setDetail(null);
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false);
      });

    return () => {
      controller.abort();
    };
  }, [selectedId, detailNonce]);

  const filtered = useMemo(
    () => companies.filter((company) => matchesOfficialSearch(company, searchQuery)),
    [companies, searchQuery],
  );

  const selectedSummary = companies.find((company) => company.id === selectedId) ?? null;
  const hasQuery = searchQuery.trim().length > 0;
  const sheetTitle =
    detail?.displayName ?? selectedSummary?.displayName ?? t.guideShopOfficial;

  const closeDetail = () => {
    setVisitsOpen(false);
    setPointsOpen(false);
    setSelectedId(null);
  };

  const listErrorMessage =
    listError === 'integration_disabled'
      ? t.guideShopOfficialIntegrationDisabled
      : listError === 'access_denied'
        ? t.guideShopOfficialAccessDenied
        : t.guideShopOfficialLoadError;

  return (
    <section className="guideshop-official-section" aria-labelledby="guideshop-official-title">
      <h2 id="guideshop-official-title" className="guideshop-section-title">
        {t.guideShopOfficial}
      </h2>

      {loading && (
        <p className="text-muted" role="status">
          {t.guideShopOfficialLoading}
        </p>
      )}

      {!loading && listError && (
        <div className="guideshop-section-error" role="alert">
          <p>{listErrorMessage}</p>
          {listError === 'generic' && (
            <button type="button" className="btn btn-secondary" onClick={() => void loadCompanies()}>
              {t.retry}
            </button>
          )}
        </div>
      )}

      {!loading && !listError && companies.length === 0 && (
        <p className="text-muted" role="status">
          {t.guideShopOfficialEmpty}
        </p>
      )}

      {!loading && !listError && companies.length > 0 && filtered.length === 0 && hasQuery && (
        <p className="text-muted" role="status">
          {t.guideShopOfficialNoResults}
        </p>
      )}

      {!loading && !listError && filtered.length > 0 && (
        <ul className="guideshop-place-list">
          {filtered.map((company) => (
            <li key={company.id}>
              <button
                type="button"
                className="card guideshop-place-card"
                onClick={() => setSelectedId(company.id)}
                aria-label={t.guideShopOpenOfficialCompany(company.displayName)}
              >
                <span className="guideshop-badge guideshop-badge-official">
                  {t.guideShopOfficialBadge}
                </span>
                <strong className="guideshop-place-name">{company.displayName}</strong>
                {company.type && (
                  <span className="text-muted guideshop-wrap">{company.type}</span>
                )}
                {company.address && (
                  <span className="text-muted guideshop-wrap">{company.address}</span>
                )}
                <span className="guideshop-official-status">
                  {formatOfficialStatus(company.status)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {selectedId && !visitsOpen && !pointsOpen && (
        <OverlaySheet
          title={sheetTitle}
          onClose={closeDetail}
          footer={
            <div className="guideshop-detail-actions">
              {detail && !detailLoading && !detailError && !detailNotFound && (
                <>
                  <button
                    type="button"
                    className="btn btn-primary btn-block"
                    onClick={() => setVisitsOpen(true)}
                  >
                    {t.guideShopVisitsAction}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-block"
                    onClick={() => setPointsOpen(true)}
                  >
                    {t.guideShopPointsAction}
                  </button>
                </>
              )}
              {detailError && (
                <button
                  type="button"
                  className="btn btn-primary btn-block"
                  onClick={() => setDetailNonce((value) => value + 1)}
                >
                  {t.retry}
                </button>
              )}
              <button type="button" className="btn btn-secondary btn-block" onClick={closeDetail}>
                {t.close}
              </button>
            </div>
          }
        >
          <div className="guideshop-detail-body">
            {detailLoading && (
              <p className="text-muted" role="status">
                {t.guideShopOfficialDetailLoading}
              </p>
            )}

            {!detailLoading && detailError && (
              <p className="guideshop-section-error" role="alert">
                {t.guideShopOfficialDetailError}
              </p>
            )}

            {!detailLoading && detailNotFound && (
              <p className="text-muted" role="status">
                {t.guideShopOfficialDetailNotFound}
              </p>
            )}

            {!detailLoading && detail && (
              <>
                <span className="guideshop-badge guideshop-badge-official">
                  {t.guideShopOfficialBadge}
                </span>
                <div className="detail-row">
                  <span className="detail-label">{t.guideShopOfficialFieldType}</span>
                  <span className="detail-value guideshop-wrap">
                    {optionalValue(detail.type)}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">{t.guideShopOfficialFieldStatus}</span>
                  <span className="detail-value">{formatOfficialStatus(detail.status)}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">{t.guideShopOfficialFieldPhone}</span>
                  <span className="detail-value guideshop-wrap">
                    {detail.phone && detail.phone.trim() ? (
                      <a className="guideshop-phone-link" href={`tel:${detail.phone}`}>
                        {detail.phone}
                      </a>
                    ) : (
                      t.guideShopOfficialNotSpecified
                    )}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">{t.guideShopOfficialFieldAddress}</span>
                  <span className="detail-value guideshop-wrap">
                    {optionalValue(detail.address)}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">{t.guideShopOfficialFieldDescription}</span>
                  <span className="detail-value guideshop-wrap">
                    {optionalValue(detail.description)}
                  </span>
                </div>
              </>
            )}
          </div>
        </OverlaySheet>
      )}

      {selectedId && detail && (
        <OfficialVisitsSheets
          companyId={detail.id}
          companyDisplayName={detail.displayName}
          open={visitsOpen}
          onClose={() => setVisitsOpen(false)}
        />
      )}

      {selectedId && detail && (
        <OfficialPointsSheet
          companyId={detail.id}
          companyDisplayName={detail.displayName}
          open={pointsOpen}
          onClose={() => setPointsOpen(false)}
        />
      )}
    </section>
  );
}

import { useCallback, useEffect, useMemo, useState } from 'react';
import { guideOsClient } from '@/api/createClient';
import type {
  PersonalCommission,
  PersonalCommissionInput,
  PersonalPlace,
  PersonalPlaceInput,
} from '@/api/types';
import { OverlaySheet } from '@/components/ui/OverlaySheet';
import { t } from '@/i18n/strings';
import { PersonalCommissionFormSheet } from './PersonalCommissionFormSheet';
import { PersonalCommissionsPanel } from './PersonalCommissionsPanel';
import { PersonalPlaceFormSheet } from './PersonalPlaceFormSheet';
import { formatOccurredAtDisplay } from './lib/commissionMoney';

function matchesSearch(place: PersonalPlace, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  const fields = [place.name, place.category, place.generalLocation, place.landmark];
  return fields.some((value) => value?.toLowerCase().includes(needle));
}

interface PersonalPlacesSectionProps {
  searchQuery: string;
  createOpen: boolean;
  onCreateOpenChange: (open: boolean) => void;
}

export function PersonalPlacesSection({
  searchQuery,
  createOpen,
  onCreateOpenChange,
}: PersonalPlacesSectionProps) {
  const [places, setPlaces] = useState<PersonalPlace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [deactivating, setDeactivating] = useState(false);

  const [commissions, setCommissions] = useState<PersonalCommission[]>([]);
  const [commissionsLoading, setCommissionsLoading] = useState(false);
  const [commissionsError, setCommissionsError] = useState(false);
  const [commissionCreateOpen, setCommissionCreateOpen] = useState(false);
  const [selectedCommissionId, setSelectedCommissionId] = useState<string | null>(null);
  const [commissionEditing, setCommissionEditing] = useState(false);
  const [confirmCommissionDeactivate, setConfirmCommissionDeactivate] = useState(false);
  const [commissionActionError, setCommissionActionError] = useState<string | null>(null);
  const [commissionDeactivating, setCommissionDeactivating] = useState(false);

  const loadPlaces = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const list = await guideOsClient.listPersonalPlaces();
      setPlaces(list);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadCommissions = useCallback(async (placeId: string) => {
    setCommissionsLoading(true);
    setCommissionsError(false);
    try {
      const list = await guideOsClient.listPersonalCommissions(placeId);
      setCommissions(list);
    } catch {
      setCommissionsError(true);
    } finally {
      setCommissionsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPlaces();
  }, [loadPlaces]);

  useEffect(() => {
    if (!selectedId) {
      setCommissions([]);
      setCommissionsError(false);
      setCommissionsLoading(false);
      return;
    }
    void loadCommissions(selectedId);
  }, [selectedId, loadCommissions]);

  const filtered = useMemo(
    () => places.filter((place) => matchesSearch(place, searchQuery)),
    [places, searchQuery],
  );

  const selected = places.find((place) => place.id === selectedId) ?? null;
  const selectedCommission =
    commissions.find((item) => item.id === selectedCommissionId) ?? null;
  const hasQuery = searchQuery.trim().length > 0;

  const resetCommissionChildState = () => {
    setCommissionCreateOpen(false);
    setSelectedCommissionId(null);
    setCommissionEditing(false);
    setConfirmCommissionDeactivate(false);
    setCommissionActionError(null);
  };

  const closeDetail = () => {
    setSelectedId(null);
    setEditing(false);
    setConfirmDeactivate(false);
    setActionError(null);
    resetCommissionChildState();
  };

  const returnToCompanyDetail = () => {
    resetCommissionChildState();
  };

  const handleCreate = async (input: PersonalPlaceInput): Promise<boolean> => {
    try {
      const created = await guideOsClient.createPersonalPlace(input);
      setPlaces((prev) => [...prev.filter((item) => item.id !== created.id), created]);
      onCreateOpenChange(false);
      return true;
    } catch {
      return false;
    }
  };

  const handleUpdate = async (input: PersonalPlaceInput): Promise<boolean> => {
    if (!selected) return false;
    try {
      const updated = await guideOsClient.updatePersonalPlace(selected.id, input);
      setPlaces((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setEditing(false);
      setActionError(null);
      return true;
    } catch {
      return false;
    }
  };

  const handleDeactivate = async () => {
    if (!selected || deactivating) return;
    setDeactivating(true);
    setActionError(null);
    try {
      await guideOsClient.deactivatePersonalPlace(selected.id);
      await loadPlaces();
      closeDetail();
    } catch {
      setActionError(t.guideShopDeactivateError);
    } finally {
      setDeactivating(false);
    }
  };

  const handleCommissionCreate = async (
    input: PersonalCommissionInput,
  ): Promise<boolean> => {
    if (!selected) return false;
    try {
      const created = await guideOsClient.createPersonalCommission(selected.id, input);
      setCommissions((prev) => [...prev.filter((item) => item.id !== created.id), created]);
      setCommissionCreateOpen(false);
      return true;
    } catch {
      return false;
    }
  };

  const handleCommissionUpdate = async (
    input: PersonalCommissionInput,
  ): Promise<boolean> => {
    if (!selectedCommission) return false;
    try {
      const updated = await guideOsClient.updatePersonalCommission(
        selectedCommission.id,
        input,
      );
      setCommissions((prev) =>
        prev.map((item) => (item.id === updated.id ? updated : item)),
      );
      setCommissionEditing(false);
      setSelectedCommissionId(updated.id);
      setCommissionActionError(null);
      return true;
    } catch {
      return false;
    }
  };

  const handleCommissionDeactivate = async () => {
    if (!selected || !selectedCommission || commissionDeactivating) return;
    setCommissionDeactivating(true);
    setCommissionActionError(null);
    try {
      await guideOsClient.deactivatePersonalCommission(selectedCommission.id);
      await loadCommissions(selected.id);
      returnToCompanyDetail();
    } catch {
      setCommissionActionError(t.guideShopCommissionDeactivateError);
    } finally {
      setCommissionDeactivating(false);
    }
  };

  const showCompanyDetail =
    Boolean(selected) &&
    !editing &&
    !confirmDeactivate &&
    !commissionCreateOpen &&
    !selectedCommissionId &&
    !commissionEditing &&
    !confirmCommissionDeactivate;

  return (
    <section className="guideshop-personal-section" aria-labelledby="guideshop-personal-title">
      <div className="guideshop-section-header">
        <h2 id="guideshop-personal-title" className="guideshop-section-title">
          {t.guideShopPersonal}
        </h2>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => onCreateOpenChange(true)}
        >
          {t.guideShopAddCompany}
        </button>
      </div>

      {loading && (
        <p className="text-muted" role="status">
          {t.guideShopLoading}
        </p>
      )}

      {!loading && error && (
        <div className="guideshop-section-error" role="alert">
          <p>{t.guideShopLoadError}</p>
          <button type="button" className="btn btn-secondary" onClick={() => void loadPlaces()}>
            {t.retry}
          </button>
        </div>
      )}

      {!loading && !error && places.length === 0 && (
        <div className="guideshop-empty">
          <p className="guideshop-empty-title">{t.guideShopEmptyTitle}</p>
          <p className="text-muted">{t.guideShopEmptyHint}</p>
          <button
            type="button"
            className="btn btn-primary btn-block"
            onClick={() => onCreateOpenChange(true)}
          >
            {t.guideShopAddCompany}
          </button>
        </div>
      )}

      {!loading && !error && places.length > 0 && filtered.length === 0 && hasQuery && (
        <p className="text-muted" role="status">
          {t.guideShopNoResults}
        </p>
      )}

      {!loading && !error && filtered.length > 0 && (
        <ul className="guideshop-place-list">
          {filtered.map((place) => (
            <li key={place.id}>
              <button
                type="button"
                className="card guideshop-place-card"
                onClick={() => {
                  setSelectedId(place.id);
                  setActionError(null);
                  resetCommissionChildState();
                }}
                aria-label={t.guideShopOpenCompany(place.name)}
              >
                <span className="guideshop-badge">{t.guideShopMyBadge}</span>
                <strong className="guideshop-place-name">{place.name}</strong>
                {place.category && <span className="text-muted">{place.category}</span>}
                {place.generalLocation && (
                  <span className="text-muted">{place.generalLocation}</span>
                )}
                {place.landmark && <span className="text-muted">{place.landmark}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}

      {createOpen && (
        <PersonalPlaceFormSheet
          mode="create"
          onClose={() => onCreateOpenChange(false)}
          onSubmit={handleCreate}
        />
      )}

      {showCompanyDetail && selected && (
        <OverlaySheet
          title={selected.name}
          onClose={closeDetail}
          footer={
            <div className="guideshop-detail-actions">
              <button
                type="button"
                className="btn btn-primary btn-block"
                onClick={() => {
                  setCommissionCreateOpen(true);
                  setCommissionActionError(null);
                }}
              >
                {t.guideShopAddCommission}
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-block"
                onClick={() => setEditing(true)}
              >
                {t.edit}
              </button>
              <button
                type="button"
                className="btn btn-danger btn-block"
                onClick={() => {
                  setConfirmDeactivate(true);
                  setActionError(null);
                }}
              >
                {t.guideShopDeactivate}
              </button>
              <button type="button" className="btn btn-secondary btn-block" onClick={closeDetail}>
                {t.close}
              </button>
            </div>
          }
        >
          <div className="guideshop-detail-body">
            <span className="guideshop-badge">{t.guideShopMyBadge}</span>
            {selected.category && (
              <div className="detail-row">
                <span className="detail-label">{t.guideShopFieldCategory}</span>
                <span className="detail-value">{selected.category}</span>
              </div>
            )}
            {selected.generalLocation && (
              <div className="detail-row">
                <span className="detail-label">{t.guideShopFieldLocation}</span>
                <span className="detail-value">{selected.generalLocation}</span>
              </div>
            )}
            {selected.landmark && (
              <div className="detail-row">
                <span className="detail-label">{t.guideShopFieldLandmark}</span>
                <span className="detail-value">{selected.landmark}</span>
              </div>
            )}
            {selected.note && (
              <div className="detail-row">
                <span className="detail-label">{t.guideShopFieldNote}</span>
                <span className="detail-value">{selected.note}</span>
              </div>
            )}
            <PersonalCommissionsPanel
              commissions={commissions}
              loading={commissionsLoading}
              error={commissionsError}
              onRetry={() => {
                if (selectedId) void loadCommissions(selectedId);
              }}
              onOpen={(item) => {
                setSelectedCommissionId(item.id);
                setCommissionActionError(null);
              }}
            />
          </div>
        </OverlaySheet>
      )}

      {selected && editing && (
        <PersonalPlaceFormSheet
          mode="edit"
          initialPlace={selected}
          onClose={() => setEditing(false)}
          onSubmit={handleUpdate}
        />
      )}

      {selected && confirmDeactivate && (
        <OverlaySheet
          title={t.guideShopDeactivateTitle}
          onClose={() => setConfirmDeactivate(false)}
          center
          footer={
            <div className="guideshop-detail-actions">
              <button
                type="button"
                className="btn btn-danger btn-block"
                onClick={() => void handleDeactivate()}
                disabled={deactivating}
              >
                {deactivating ? t.guideShopDeactivating : t.guideShopDeactivate}
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-block"
                onClick={() => setConfirmDeactivate(false)}
                disabled={deactivating}
              >
                {t.cancel}
              </button>
            </div>
          }
        >
          <p>{t.guideShopDeactivateHint}</p>
          {actionError && (
            <p className="prof-validation-error" role="alert">
              {actionError}
            </p>
          )}
        </OverlaySheet>
      )}

      {selected && commissionCreateOpen && (
        <PersonalCommissionFormSheet
          mode="create"
          onClose={() => setCommissionCreateOpen(false)}
          onSubmit={handleCommissionCreate}
        />
      )}

      {selected && selectedCommission && !commissionEditing && !confirmCommissionDeactivate && (
        <OverlaySheet
          title={t.guideShopCommissionDetailTitle}
          onClose={returnToCompanyDetail}
          footer={
            <div className="guideshop-detail-actions">
              <button
                type="button"
                className="btn btn-secondary btn-block"
                onClick={() => setCommissionEditing(true)}
              >
                {t.edit}
              </button>
              <button
                type="button"
                className="btn btn-danger btn-block"
                onClick={() => {
                  setConfirmCommissionDeactivate(true);
                  setCommissionActionError(null);
                }}
              >
                {t.guideShopDeactivate}
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-block"
                onClick={returnToCompanyDetail}
              >
                {t.guideShopBackToCompany}
              </button>
            </div>
          }
        >
          <div className="guideshop-detail-body">
            <div className="detail-row">
              <span className="detail-label">{t.guideShopCommissionFieldDate}</span>
              <span className="detail-value">
                {formatOccurredAtDisplay(selectedCommission.occurredAt)}
              </span>
            </div>
            {selectedCommission.receivedPoints != null && (
              <div className="detail-row">
                <span className="detail-label">{t.guideShopCommissionFieldCommission}</span>
                <span className="detail-value">{selectedCommission.receivedPoints}</span>
              </div>
            )}
            {selectedCommission.note && (
              <div className="detail-row">
                <span className="detail-label">{t.guideShopFieldNote}</span>
                <span className="detail-value guideshop-commission-note">
                  {selectedCommission.note}
                </span>
              </div>
            )}
          </div>
        </OverlaySheet>
      )}

      {selected && selectedCommission && commissionEditing && (
        <PersonalCommissionFormSheet
          mode="edit"
          initialCommission={selectedCommission}
          onClose={() => setCommissionEditing(false)}
          onSubmit={handleCommissionUpdate}
        />
      )}

      {selected && selectedCommission && confirmCommissionDeactivate && (
        <OverlaySheet
          title={t.guideShopCommissionDeactivateTitle}
          onClose={() => setConfirmCommissionDeactivate(false)}
          center
          footer={
            <div className="guideshop-detail-actions">
              <button
                type="button"
                className="btn btn-danger btn-block"
                onClick={() => void handleCommissionDeactivate()}
                disabled={commissionDeactivating}
              >
                {commissionDeactivating
                  ? t.guideShopDeactivating
                  : t.guideShopDeactivate}
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-block"
                onClick={() => setConfirmCommissionDeactivate(false)}
                disabled={commissionDeactivating}
              >
                {t.cancel}
              </button>
            </div>
          }
        >
          <p>{t.guideShopCommissionDeactivateHint}</p>
          {commissionActionError && (
            <p className="prof-validation-error" role="alert">
              {commissionActionError}
            </p>
          )}
        </OverlaySheet>
      )}
    </section>
  );
}

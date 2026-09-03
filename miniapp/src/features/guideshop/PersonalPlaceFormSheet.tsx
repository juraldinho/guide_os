import { useEffect, useState } from 'react';
import type { PersonalPlace, PersonalPlaceInput } from '@/api/types';
import { OverlaySheet } from '@/components/ui/OverlaySheet';
import { t } from '@/i18n/strings';

interface FieldErrors {
  name?: string;
  category?: string;
  generalLocation?: string;
  landmark?: string;
  note?: string;
}

interface Draft {
  name: string;
  category: string;
  generalLocation: string;
  landmark: string;
  note: string;
}

function emptyDraft(): Draft {
  return {
    name: '',
    category: '',
    generalLocation: '',
    landmark: '',
    note: '',
  };
}

function draftFromPlace(place: PersonalPlace): Draft {
  return {
    name: place.name,
    category: place.category ?? '',
    generalLocation: place.generalLocation ?? '',
    landmark: place.landmark ?? '',
    note: place.note ?? '',
  };
}

function validateDraft(draft: Draft): FieldErrors {
  const errors: FieldErrors = {};
  const name = draft.name.trim();
  if (!name) errors.name = t.guideShopValNameRequired;
  else if (name.length > 100) errors.name = t.guideShopValNameTooLong;
  if (draft.category.trim().length > 100) errors.category = t.guideShopValCategoryTooLong;
  if (draft.generalLocation.trim().length > 200) {
    errors.generalLocation = t.guideShopValLocationTooLong;
  }
  if (draft.landmark.trim().length > 200) errors.landmark = t.guideShopValLandmarkTooLong;
  if (draft.note.trim().length > 500) errors.note = t.guideShopValNoteTooLong;
  return errors;
}

function normalizeDraft(draft: Draft): PersonalPlaceInput {
  const optional = (value: string): string | null => {
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
  };
  return {
    name: draft.name.trim(),
    category: optional(draft.category),
    generalLocation: optional(draft.generalLocation),
    landmark: optional(draft.landmark),
    note: optional(draft.note),
  };
}

interface PersonalPlaceFormSheetProps {
  mode: 'create' | 'edit';
  initialPlace?: PersonalPlace | null;
  onClose: () => void;
  onSubmit: (input: PersonalPlaceInput) => Promise<boolean>;
}

export function PersonalPlaceFormSheet({
  mode,
  initialPlace = null,
  onClose,
  onSubmit,
}: PersonalPlaceFormSheetProps) {
  const [draft, setDraft] = useState<Draft>(() =>
    mode === 'edit' && initialPlace ? draftFromPlace(initialPlace) : emptyDraft(),
  );
  const [errors, setErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(mode === 'edit' && initialPlace ? draftFromPlace(initialPlace) : emptyDraft());
    setErrors({});
    setSubmitError(null);
  }, [mode, initialPlace]);

  const title = mode === 'create' ? t.guideShopNewCompany : t.guideShopEditCompany;

  const handleSave = async () => {
    const nextErrors = validateDraft(draft);
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }
    setSaving(true);
    setSubmitError(null);
    try {
      const ok = await onSubmit(normalizeDraft(draft));
      if (!ok) setSubmitError(t.guideShopSaveError);
    } catch {
      setSubmitError(t.guideShopSaveError);
    } finally {
      setSaving(false);
    }
  };

  return (
    <OverlaySheet
      title={title}
      onClose={onClose}
      footer={
        <div className="form-row">
          <button
            type="button"
            className="btn btn-secondary btn-block"
            onClick={onClose}
            disabled={saving}
          >
            {t.cancel}
          </button>
          <button
            type="button"
            className="btn btn-primary btn-block"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? t.guideShopSaving : t.save}
          </button>
        </div>
      }
    >
      <div className="form-group">
        <label className="form-label" htmlFor="pp-name">
          {t.guideShopFieldName}
        </label>
        <input
          id="pp-name"
          className="form-input"
          value={draft.name}
          onChange={(e) => {
            setDraft((prev) => ({ ...prev, name: e.target.value }));
            setErrors((prev) => ({ ...prev, name: undefined }));
          }}
        />
        {errors.name && (
          <p className="prof-validation-error" role="alert">
            {errors.name}
          </p>
        )}
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="pp-category">
          {t.guideShopFieldCategory}
        </label>
        <input
          id="pp-category"
          className="form-input"
          value={draft.category}
          onChange={(e) => {
            setDraft((prev) => ({ ...prev, category: e.target.value }));
            setErrors((prev) => ({ ...prev, category: undefined }));
          }}
        />
        {errors.category && (
          <p className="prof-validation-error" role="alert">
            {errors.category}
          </p>
        )}
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="pp-location">
          {t.guideShopFieldLocation}
        </label>
        <input
          id="pp-location"
          className="form-input"
          value={draft.generalLocation}
          onChange={(e) => {
            setDraft((prev) => ({ ...prev, generalLocation: e.target.value }));
            setErrors((prev) => ({ ...prev, generalLocation: undefined }));
          }}
        />
        {errors.generalLocation && (
          <p className="prof-validation-error" role="alert">
            {errors.generalLocation}
          </p>
        )}
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="pp-landmark">
          {t.guideShopFieldLandmark}
        </label>
        <input
          id="pp-landmark"
          className="form-input"
          value={draft.landmark}
          onChange={(e) => {
            setDraft((prev) => ({ ...prev, landmark: e.target.value }));
            setErrors((prev) => ({ ...prev, landmark: undefined }));
          }}
        />
        {errors.landmark && (
          <p className="prof-validation-error" role="alert">
            {errors.landmark}
          </p>
        )}
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="pp-note">
          {t.guideShopFieldNote}
        </label>
        <textarea
          id="pp-note"
          className="form-textarea"
          value={draft.note}
          onChange={(e) => {
            setDraft((prev) => ({ ...prev, note: e.target.value }));
            setErrors((prev) => ({ ...prev, note: undefined }));
          }}
        />
        {errors.note && (
          <p className="prof-validation-error" role="alert">
            {errors.note}
          </p>
        )}
      </div>

      {submitError && (
        <p className="prof-validation-error" role="alert">
          {submitError}
        </p>
      )}
    </OverlaySheet>
  );
}

export { normalizeDraft, validateDraft };

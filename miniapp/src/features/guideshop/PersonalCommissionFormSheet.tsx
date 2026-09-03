import { useEffect, useState } from 'react';
import type { PersonalCommission, PersonalCommissionInput } from '@/api/types';
import { MOCK_TODAY } from '@/config';
import { OverlaySheet } from '@/components/ui/OverlaySheet';
import { t } from '@/i18n/strings';
import {
  businessDateToOccurredAt,
  isBusinessDateAfter,
  occurredAtToBusinessDate,
  parseCommissionInput,
} from './lib/commissionMoney';

interface FieldErrors {
  date?: string;
  commission?: string;
  note?: string;
}

interface Draft {
  date: string;
  commission: string;
  note: string;
}

function emptyDraft(): Draft {
  return {
    date: MOCK_TODAY,
    commission: '',
    note: '',
  };
}

function draftFromCommission(item: PersonalCommission): Draft {
  return {
    date: occurredAtToBusinessDate(item.occurredAt),
    commission: item.receivedPoints == null ? '' : String(item.receivedPoints),
    note: item.note ?? '',
  };
}

function validateDraft(draft: Draft): FieldErrors {
  const errors: FieldErrors = {};
  if (!/^\d{4}-\d{2}-\d{2}$/.test(draft.date)) {
    errors.date = t.guideShopCommissionValDateRequired;
  } else if (isBusinessDateAfter(draft.date, MOCK_TODAY)) {
    errors.date = t.guideShopCommissionValDateFuture;
  }

  const commission = parseCommissionInput(draft.commission);
  if (!commission.ok) {
    errors.commission = t.guideShopCommissionValInvalid;
  }

  if (draft.note.trim().length > 500) {
    errors.note = t.guideShopValNoteTooLong;
  }

  return errors;
}

function normalizeDraft(draft: Draft): PersonalCommissionInput {
  const commission = parseCommissionInput(draft.commission);
  if (!commission.ok) {
    throw new Error('invalid draft');
  }
  const note = draft.note.trim();
  return {
    occurredAt: businessDateToOccurredAt(draft.date),
    purchaseAmountMinor: null,
    receivedIncomeMinor: null,
    receivedPoints: commission.value,
    currency: null,
    note: note ? note : null,
  };
}

interface PersonalCommissionFormSheetProps {
  mode: 'create' | 'edit';
  initialCommission?: PersonalCommission | null;
  onClose: () => void;
  onSubmit: (input: PersonalCommissionInput) => Promise<boolean>;
}

export function PersonalCommissionFormSheet({
  mode,
  initialCommission = null,
  onClose,
  onSubmit,
}: PersonalCommissionFormSheetProps) {
  const [draft, setDraft] = useState<Draft>(() =>
    mode === 'edit' && initialCommission
      ? draftFromCommission(initialCommission)
      : emptyDraft(),
  );
  const [errors, setErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(
      mode === 'edit' && initialCommission
        ? draftFromCommission(initialCommission)
        : emptyDraft(),
    );
    setErrors({});
    setSubmitError(null);
  }, [mode, initialCommission]);

  const title =
    mode === 'create' ? t.guideShopAddCommission : t.guideShopEditCommission;

  const handleSave = async () => {
    if (saving) return;
    const nextErrors = validateDraft(draft);
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }
    setSaving(true);
    setSubmitError(null);
    try {
      const ok = await onSubmit(normalizeDraft(draft));
      if (!ok) setSubmitError(t.guideShopCommissionSaveError);
    } catch {
      setSubmitError(t.guideShopCommissionSaveError);
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
            onClick={() => void handleSave()}
            disabled={saving}
          >
            {saving ? t.guideShopSaving : t.save}
          </button>
        </div>
      }
    >
      <div className="form-group">
        <label className="form-label" htmlFor="pc-date">
          {t.guideShopCommissionFieldDate}
        </label>
        <input
          id="pc-date"
          type="date"
          className="form-input"
          value={draft.date}
          max={MOCK_TODAY}
          onChange={(e) => {
            setDraft((prev) => ({ ...prev, date: e.target.value }));
            setErrors((prev) => ({ ...prev, date: undefined }));
          }}
        />
        {errors.date && (
          <p className="prof-validation-error" role="alert">
            {errors.date}
          </p>
        )}
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="pc-commission">
          {t.guideShopCommissionFieldCommission}
        </label>
        <input
          id="pc-commission"
          className="form-input"
          inputMode="numeric"
          autoComplete="off"
          value={draft.commission}
          onChange={(e) => {
            setDraft((prev) => ({ ...prev, commission: e.target.value }));
            setErrors((prev) => ({ ...prev, commission: undefined }));
          }}
        />
        {errors.commission && (
          <p className="prof-validation-error" role="alert">
            {errors.commission}
          </p>
        )}
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="pc-note">
          {t.guideShopFieldNote}
        </label>
        <textarea
          id="pc-note"
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

export { normalizeDraft, validateDraft, draftFromCommission, emptyDraft };

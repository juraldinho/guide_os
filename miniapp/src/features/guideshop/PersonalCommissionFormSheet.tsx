import { useEffect, useState } from 'react';
import type { PersonalCommission, PersonalCommissionInput } from '@/api/types';
import { MOCK_TODAY } from '@/config';
import { OverlaySheet } from '@/components/ui/OverlaySheet';
import { t } from '@/i18n/strings';
import {
  businessDateToOccurredAt,
  formatMinorUnits,
  isBusinessDateAfter,
  normalizeCurrencyInput,
  occurredAtToBusinessDate,
  parseMoneyToMinor,
  parsePointsInput,
} from './lib/commissionMoney';

interface FieldErrors {
  date?: string;
  purchase?: string;
  income?: string;
  points?: string;
  currency?: string;
  note?: string;
  outcome?: string;
}

interface Draft {
  date: string;
  purchase: string;
  income: string;
  points: string;
  currency: string;
  note: string;
}

function emptyDraft(): Draft {
  return {
    date: MOCK_TODAY,
    purchase: '',
    income: '',
    points: '',
    currency: '',
    note: '',
  };
}

function draftFromCommission(item: PersonalCommission): Draft {
  return {
    date: occurredAtToBusinessDate(item.occurredAt),
    purchase:
      item.purchaseAmountMinor == null ? '' : formatMinorUnits(item.purchaseAmountMinor),
    income:
      item.receivedIncomeMinor == null ? '' : formatMinorUnits(item.receivedIncomeMinor),
    points: item.receivedPoints == null ? '' : String(item.receivedPoints),
    currency: item.currency ?? '',
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

  const purchase = parseMoneyToMinor(draft.purchase);
  if (!purchase.ok) errors.purchase = t.guideShopCommissionValMoneyInvalid;
  const income = parseMoneyToMinor(draft.income);
  if (!income.ok) errors.income = t.guideShopCommissionValMoneyInvalid;
  const points = parsePointsInput(draft.points);
  if (!points.ok) errors.points = t.guideShopCommissionValPointsInvalid;
  const currency = normalizeCurrencyInput(draft.currency);
  if (!currency.ok) errors.currency = t.guideShopCommissionValCurrencyInvalid;

  if (purchase.ok && income.ok && points.ok && currency.ok) {
    const hasMoney = purchase.value != null || income.value != null;
    if (hasMoney && currency.value == null) {
      errors.currency = t.guideShopCommissionValCurrencyRequired;
    }
    if (!hasMoney && currency.value != null) {
      errors.currency = t.guideShopCommissionValCurrencyUnexpected;
    }
    const hasOutcome =
      (purchase.value != null && purchase.value > 0) ||
      (income.value != null && income.value > 0) ||
      (points.value != null && points.value > 0);
    if (!hasOutcome) {
      errors.outcome = t.guideShopCommissionValOutcomeRequired;
    }
  }

  if (draft.note.trim().length > 500) {
    errors.note = t.guideShopValNoteTooLong;
  }

  return errors;
}

function normalizeDraft(draft: Draft): PersonalCommissionInput {
  const purchase = parseMoneyToMinor(draft.purchase);
  const income = parseMoneyToMinor(draft.income);
  const points = parsePointsInput(draft.points);
  const currency = normalizeCurrencyInput(draft.currency);
  if (!purchase.ok || !income.ok || !points.ok || !currency.ok) {
    throw new Error('invalid draft');
  }
  const note = draft.note.trim();
  return {
    occurredAt: businessDateToOccurredAt(draft.date),
    purchaseAmountMinor: purchase.value,
    receivedIncomeMinor: income.value,
    receivedPoints: points.value,
    currency: currency.value,
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
        <label className="form-label" htmlFor="pc-purchase">
          {t.guideShopCommissionFieldPurchase}
        </label>
        <input
          id="pc-purchase"
          className="form-input"
          inputMode="decimal"
          autoComplete="off"
          value={draft.purchase}
          aria-describedby="pc-money-hint"
          onChange={(e) => {
            setDraft((prev) => ({ ...prev, purchase: e.target.value }));
            setErrors((prev) => ({ ...prev, purchase: undefined, outcome: undefined }));
          }}
        />
        {errors.purchase && (
          <p className="prof-validation-error" role="alert">
            {errors.purchase}
          </p>
        )}
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="pc-income">
          {t.guideShopCommissionFieldIncome}
        </label>
        <input
          id="pc-income"
          className="form-input"
          inputMode="decimal"
          autoComplete="off"
          value={draft.income}
          aria-describedby="pc-money-hint"
          onChange={(e) => {
            setDraft((prev) => ({ ...prev, income: e.target.value }));
            setErrors((prev) => ({ ...prev, income: undefined, outcome: undefined }));
          }}
        />
        {errors.income && (
          <p className="prof-validation-error" role="alert">
            {errors.income}
          </p>
        )}
      </div>

      <p id="pc-money-hint" className="text-muted guideshop-commission-hint">
        {t.guideShopCommissionMoneyHint}
      </p>

      <div className="form-group">
        <label className="form-label" htmlFor="pc-points">
          {t.guideShopCommissionFieldPoints}
        </label>
        <input
          id="pc-points"
          className="form-input"
          inputMode="numeric"
          autoComplete="off"
          value={draft.points}
          onChange={(e) => {
            setDraft((prev) => ({ ...prev, points: e.target.value }));
            setErrors((prev) => ({ ...prev, points: undefined, outcome: undefined }));
          }}
        />
        {errors.points && (
          <p className="prof-validation-error" role="alert">
            {errors.points}
          </p>
        )}
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="pc-currency">
          {t.guideShopCommissionFieldCurrency}
        </label>
        <input
          id="pc-currency"
          className="form-input"
          autoComplete="off"
          value={draft.currency}
          onChange={(e) => {
            setDraft((prev) => ({ ...prev, currency: e.target.value }));
            setErrors((prev) => ({ ...prev, currency: undefined }));
          }}
        />
        {errors.currency && (
          <p className="prof-validation-error" role="alert">
            {errors.currency}
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

      {errors.outcome && (
        <p className="prof-validation-error" role="alert">
          {errors.outcome}
        </p>
      )}
      {submitError && (
        <p className="prof-validation-error" role="alert">
          {submitError}
        </p>
      )}
    </OverlaySheet>
  );
}

export { normalizeDraft, validateDraft, draftFromCommission, emptyDraft };

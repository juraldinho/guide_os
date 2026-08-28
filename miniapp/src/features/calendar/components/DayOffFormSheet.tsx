import { useState } from 'react';
import type { DayOffFormValues } from '@/api/types';
import { OverlaySheet } from '@/components/ui/OverlaySheet';
import { t } from '@/i18n/strings';

export function DayOffFormSheet({
  initial,
  onClose,
  onSave,
}: {
  initial: DayOffFormValues;
  onClose: () => void;
  onSave: (form: DayOffFormValues) => void;
}) {
  const [form, setForm] = useState(initial);

  return (
    <OverlaySheet title={t.dayOff} onClose={onClose}>
      <div className="form-group">
        <label className="form-label" htmlFor="f-do-start">{t.fieldStartDate}</label>
        <input
          id="f-do-start"
          type="date"
          className="form-input"
          value={form.startDate}
          onChange={(e) => setForm({ ...form, startDate: e.target.value })}
        />
      </div>
      <div className="form-group">
        <label className="form-label" htmlFor="f-do-end">{t.fieldEndDate}</label>
        <input
          id="f-do-end"
          type="date"
          className="form-input"
          value={form.endDate}
          onChange={(e) => setForm({ ...form, endDate: e.target.value })}
        />
      </div>
      <p className="text-muted">{t.dayOffHint}</p>
      <button type="button" className="btn btn-primary btn-block" onClick={() => onSave(form)}>
        {t.saveDayOff}
      </button>
    </OverlaySheet>
  );
}

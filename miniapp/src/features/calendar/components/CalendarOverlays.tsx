import { useState } from 'react';
import type {
  ConflictOverlayData,
  DayOffOverlayData,
  DetailOverlayData,
  MultiLocationOverlayData,
  TourFormOverlayData,
  TourFormValues,
  WarningOverlayData,
} from '@/api/types';
import { MOCK_TODAY, USE_MOCK_API } from '@/config';
import { OverlaySheet } from '@/components/ui/OverlaySheet';
import { fmtDate } from '../lib/dates';
import { locationFor } from '../lib/dayStatus';
import { paymentLabel, statusLabel, timeLabel } from '../lib/format';
import { t } from '@/i18n/strings';
import { useCalendar } from '../CalendarContext';
import { DayOffFormSheet } from './DayOffFormSheet';

function TourFormFields({
  initial,
  onSubmit,
}: {
  initial: TourFormValues;
  onSubmit: (form: TourFormValues) => void;
}) {
  const [form, setForm] = useState<TourFormValues>(initial);

  const update = <K extends keyof TourFormValues>(key: K, value: TourFormValues[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const showConflictHint =
    USE_MOCK_API &&
    form.startDate === MOCK_TODAY &&
    form.useTime &&
    form.startTime === '12:00' &&
    form.endTime === '16:00';

  return (
    <>
      <div className="form-group">
        <label className="form-label" htmlFor="f-title">{t.fieldTitle}</label>
        <input
          id="f-title"
          className="form-input"
          value={form.title}
          onChange={(e) => update('title', e.target.value)}
        />
      </div>
      <div className="form-group">
        <label className="form-label" htmlFor="f-start">{t.fieldStartDate}</label>
        <input
          id="f-start"
          type="date"
          className="form-input"
          value={form.startDate}
          onChange={(e) => update('startDate', e.target.value)}
        />
      </div>
      <div className="form-group">
        <label className="form-label" htmlFor="f-end">{t.fieldEndDate}</label>
        <input
          id="f-end"
          type="date"
          className="form-input"
          value={form.endDate}
          onChange={(e) => update('endDate', e.target.value)}
        />
      </div>
      <div className="toggle-row">
        <span>{t.fieldUseTime}</span>
        <button
          type="button"
          className={`toggle${form.useTime ? ' on' : ''}`}
          id="f-time-toggle"
          onClick={() => update('useTime', !form.useTime)}
          aria-pressed={form.useTime}
        />
      </div>
      {form.useTime && (
        <div className="form-row">
          <div className="form-group">
            <label className="form-label" htmlFor="f-start-time">{t.fieldStartTime}</label>
            <input
              id="f-start-time"
              type="time"
              className="form-input"
              value={form.startTime}
              onChange={(e) => update('startTime', e.target.value)}
            />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="f-end-time">{t.fieldEndTime}</label>
            <input
              id="f-end-time"
              type="time"
              className="form-input"
              value={form.endTime}
              onChange={(e) => update('endTime', e.target.value)}
            />
          </div>
        </div>
      )}
      <div className="form-group">
        <label className="form-label" htmlFor="f-company">{t.fieldCompany}</label>
        <input
          id="f-company"
          className="form-input"
          value={form.company}
          placeholder="Silk Road Travel"
          onChange={(e) => update('company', e.target.value)}
        />
      </div>
      <div className="form-group">
        <label className="form-label" htmlFor="f-location">{t.fieldLocation}</label>
        <input
          id="f-location"
          className="form-input"
          value={form.location}
          onChange={(e) => update('location', e.target.value)}
        />
      </div>
      <div className="form-group">
        <label className="form-label" htmlFor="f-income">{t.fieldIncome}</label>
        <input
          id="f-income"
          type="number"
          className="form-input"
          value={form.income || ''}
          onChange={(e) => update('income', parseInt(e.target.value, 10) || 0)}
        />
      </div>
      <div className="form-row">
        <div className="form-group">
          <label className="form-label" htmlFor="f-status">{t.fieldStatus}</label>
          <select
            id="f-status"
            className="form-select"
            value={form.status}
            onChange={(e) => update('status', e.target.value as TourFormValues['status'])}
          >
            <option value="reserved">{t.statusReserved}</option>
            <option value="confirmed">{t.statusConfirmed}</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="f-payment">{t.fieldPayment}</label>
          <select
            id="f-payment"
            className="form-select"
            value={form.payment}
            onChange={(e) => update('payment', e.target.value as TourFormValues['payment'])}
          >
            <option value="unpaid">{t.paymentUnpaid}</option>
            <option value="paid">{t.paymentPaid}</option>
          </select>
        </div>
      </div>
      <div className="form-group">
        <label className="form-label" htmlFor="f-note">{t.fieldNote}</label>
        <textarea
          id="f-note"
          className="form-textarea"
          value={form.note}
          onChange={(e) => update('note', e.target.value)}
        />
      </div>
      {showConflictHint && <p className="text-hint">{t.conflictDemoHint}</p>}
      <button type="button" className="btn btn-primary btn-block" onClick={() => onSubmit(form)}>
        {t.saveTour}
      </button>
    </>
  );
}

export function CalendarOverlays() {
  const {
    overlay,
    overlayData,
    entries,
    selectedDate,
    closeOverlay,
    openTourForm,
    openDayOffForm,
    returnToTourFormFromConflict,
    saveTour,
    ackWarningAndSave,
    saveDayOff,
    editTour,
    copyTour,
    openDelete,
    confirmDelete,
    saveDayLocations,
    updateMultiLocation,
  } = useCalendar();

  if (!overlay || overlay === 'free-dates' || overlay === 'demo-states') return null;

  if (overlay === 'add-select') {
    return (
      <OverlaySheet title={t.addTitle} onClose={closeOverlay}>
        <button type="button" className="btn btn-secondary btn-block" onClick={() => openTourForm()}>
          {t.tour}
        </button>
        <button
          type="button"
          className="btn btn-secondary btn-block"
          style={{ marginTop: 8 }}
          onClick={openDayOffForm}
        >
          {t.dayOff}
        </button>
      </OverlaySheet>
    );
  }

  if (overlay === 'tour-form') {
    const data = overlayData as TourFormOverlayData;
    const title = data.edit ? t.editTour : data.copy ? t.copyTour : t.newTour;
    return (
      <OverlaySheet title={title} onClose={closeOverlay}>
        <TourFormFields initial={data.form} onSubmit={saveTour} />
      </OverlaySheet>
    );
  }

  if (overlay === 'dayoff-form') {
    const data = overlayData as DayOffOverlayData;
    return (
      <DayOffFormSheet
        initial={data.form}
        onClose={closeOverlay}
        onSave={saveDayOff}
      />
    );
  }

  if (overlay === 'detail') {
    const { id } = overlayData as DetailOverlayData;
    const e = entries.find((x) => x.id === id);
    if (!e) {
      return (
        <OverlaySheet title={t.tourCard} onClose={closeOverlay}>
          <p>{t.tourNotFound}</p>
        </OverlaySheet>
      );
    }

    if (e.type === 'day_off') {
      return (
        <OverlaySheet title={t.tourCard} onClose={closeOverlay}>
          <div className="detail-row">
            <span className="detail-label">{t.detailType}</span>
            <span className="detail-value">{t.dayOff}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">{t.detailDates}</span>
            <span className="detail-value">
              {fmtDate(e.startDate)}
              {e.endDate !== e.startDate ? ` – ${fmtDate(e.endDate)}` : ''}
            </span>
          </div>
          <button
            type="button"
            className="btn btn-danger btn-block"
            style={{ marginTop: 16 }}
            onClick={() => openDelete(id)}
          >
            {t.delete}
          </button>
        </OverlaySheet>
      );
    }

    const dateRange =
      e.startDate === e.endDate
        ? fmtDate(e.startDate)
        : `${fmtDate(e.startDate)} – ${fmtDate(e.endDate)}`;

    return (
      <OverlaySheet title={t.tourCard} onClose={closeOverlay}>
        <div className="detail-row">
          <span className="detail-label">{t.detailName}</span>
          <span className="detail-value">{e.title}</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">{t.detailDates}</span>
          <span className="detail-value">{dateRange}</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">{t.detailTime}</span>
          <span className="detail-value">{timeLabel(e)}</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">{t.detailCompany}</span>
          <span className="detail-value">{e.company || '—'}</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">{t.detailLocation}</span>
          <span className="detail-value">{locationFor(e, selectedDate)}</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">{t.detailIncome}</span>
          <span className="detail-value">${e.income || 0}</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">{t.detailPayment}</span>
          <span className="detail-value">{paymentLabel(e.payment)}</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">{t.detailStatus}</span>
          <span className="detail-value">{statusLabel(e.status)}</span>
        </div>
        {e.note && (
          <div className="detail-row">
            <span className="detail-label">{t.detailNote}</span>
            <span className="detail-value">{e.note}</span>
          </div>
        )}
        <div className="detail-row">
          <span className="detail-label">{t.detailSource}</span>
          <span className="detail-value">{e.source || 'Mini App'}</span>
        </div>
        <div className="detail-actions">
          <button type="button" className="btn btn-secondary" onClick={() => editTour(id)}>
            {t.edit}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => copyTour(id)}>
            {t.copyAction}
          </button>
          <button type="button" className="btn btn-danger" onClick={() => openDelete(id)}>
            {t.delete}
          </button>
        </div>
      </OverlaySheet>
    );
  }

  if (overlay === 'delete') {
    const { id } = overlayData as DetailOverlayData;
    const e = entries.find((x) => x.id === id);
    const multi = e && e.startDate !== e.endDate;
    return (
      <OverlaySheet title={t.confirm} onClose={closeOverlay} center>
        <p>{multi ? t.deleteMultiDay : t.deleteTour}</p>
        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <button type="button" className="btn btn-danger btn-block" onClick={confirmDelete}>
            {t.yes}
          </button>
          <button type="button" className="btn btn-secondary btn-block" onClick={closeOverlay}>
            {t.no}
          </button>
        </div>
      </OverlaySheet>
    );
  }

  if (overlay === 'conflict') {
    const data = overlayData as ConflictOverlayData;
    return (
      <OverlaySheet title={t.conflictTitle} onClose={closeOverlay} center>
        <div className="alert alert-danger">{data.reason}</div>
        <button
          type="button"
          className="btn btn-primary btn-block"
          onClick={() => returnToTourFormFromConflict('time')}
        >
          {t.changeTime}
        </button>
        <button
          type="button"
          className="btn btn-secondary btn-block"
          style={{ marginTop: 8 }}
          onClick={() => returnToTourFormFromConflict('date')}
        >
          {t.changeDate}
        </button>
      </OverlaySheet>
    );
  }

  if (overlay === 'warning') {
    const data = overlayData as WarningOverlayData;
    const dateLabel = fmtDate(data.date);
    const body = t.dateWarningBody(dateLabel, data.ex.title, timeLabel(data.ex));
    return (
      <OverlaySheet title={t.dateWarningTitle} onClose={closeOverlay} center>
        <div className="alert alert-warning">{body}</div>
        <button type="button" className="btn btn-primary btn-block" onClick={ackWarningAndSave}>
          {t.save}
        </button>
        <button
          type="button"
          className="btn btn-secondary btn-block"
          style={{ marginTop: 8 }}
          onClick={closeOverlay}
        >
          {t.cancel}
        </button>
      </OverlaySheet>
    );
  }

  if (overlay === 'multi-location') {
    const data = overlayData as MultiLocationOverlayData;
    return (
      <OverlaySheet title={t.multiLocationTitle} onClose={closeOverlay}>
        <p className="text-muted">{t.multiLocationHint}</p>
        {data.days.map((d) => (
          <div key={d} className="form-group">
            <label className="form-label">{fmtDate(d)}</label>
            <input
              className="form-input"
              value={data.locations[d] || ''}
              onChange={(e) => updateMultiLocation(d, e.target.value)}
            />
          </div>
        ))}
        <button
          type="button"
          className="btn btn-primary btn-block"
          onClick={() => saveDayLocations(data.locations)}
        >
          {t.done}
        </button>
      </OverlaySheet>
    );
  }

  return null;
}

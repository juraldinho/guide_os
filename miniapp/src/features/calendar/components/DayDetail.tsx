import { fmtDateLong } from '../lib/dates';
import {
  dayStatus,
  entriesOnDate,
  getPartialAvailability,
  locationFor,
  sortEntriesForDay,
} from '../lib/dayStatus';
import {
  dayAvailabilitySummary,
  paymentLabel,
  statusLabel,
  timeLabel,
} from '../lib/format';
import { t } from '@/i18n/strings';
import { IconBack } from '@/components/ui/Icons';
import { useCalendar } from '../CalendarContext';

export function DayDetail() {
  const { entries, selectedDate, openFeed, openAdd, openDetail, openFreeDates } = useCalendar();
  const dayEntries = sortEntriesForDay(entriesOnDate(selectedDate, entries));
  const status = dayStatus(selectedDate, entries);
  const partial = getPartialAvailability(selectedDate, entries);
  const summary = dayAvailabilitySummary(selectedDate, entries, partial, status);

  return (
    <main className="main">
      <div className="day-detail-header">
        <button type="button" className="icon-btn" onClick={openFeed} aria-label={t.backToFeed}>
          <IconBack />
        </button>
        <div className="day-detail-title">
          <h2 className="page-title" style={{ marginBottom: 4 }}>{fmtDateLong(selectedDate)}</h2>
          <p className="text-muted">{summary}</p>
        </div>
      </div>
      {partial && <div className="alert alert-info">{partial}</div>}
      {dayEntries.length === 0 ? (
        <p className="text-muted">{t.dayFullyFree}</p>
      ) : (
        dayEntries.map((e) => (
          <div
            key={e.id}
            className="day-detail-entry"
            onClick={() => openDetail(e.id)}
          >
            {e.type === 'day_off' ? (
              <>
                <div className="entry-title">{t.dayOff}</div>
                <div className="entry-row">{t.allDay}</div>
              </>
            ) : (
              <>
                <div className="entry-title">{e.title}</div>
                <div className="entry-row">
                  {timeLabel(e)} · {statusLabel(e.status)} · {paymentLabel(e.payment)}
                </div>
                <div className="entry-row">
                  {e.company || '—'} · {locationFor(e, selectedDate)}
                </div>
                {e.income ? <div className="entry-row">${e.income}</div> : null}
              </>
            )}
          </div>
        ))
      )}
      <button type="button" className="btn btn-primary btn-block" style={{ marginTop: 16 }} onClick={openAdd}>
        {t.add}
      </button>
      <button
        type="button"
        className="btn btn-secondary btn-block"
        style={{ marginTop: 8 }}
        onClick={openFreeDates}
      >
        {t.shareFreeDates}
      </button>
    </main>
  );
}

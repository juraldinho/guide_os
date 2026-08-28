import { MOCK_TODAY } from '@/config';
import { getFeedDates, parseDate, dowShortUpper } from '../lib/dates';
import { dayStatus, entriesOnDate, sortEntriesForDay } from '../lib/dayStatus';
import { dayStatusText, statusLabel, timeLabel } from '../lib/format';
import { t } from '@/i18n/strings';
import { useCalendar } from '../CalendarContext';

export function Feed() {
  const { entries, openDayDetail } = useCalendar();
  const dates = getFeedDates();

  return (
    <div className="day-feed">
      {dates.map((iso) => {
        const dayEntries = sortEntriesForDay(entriesOnDate(iso, entries));
        const today = iso === MOCK_TODAY;
        const empty = dayEntries.length === 0;
        const status = dayStatus(iso, entries);

        return (
          <button
            key={iso}
            type="button"
            className={`feed-day-row${today ? ' today' : ''}${empty ? ' is-empty' : ''}`}
            onClick={() => openDayDetail(iso)}
          >
            <div className="feed-day-meta">
              <div className="feed-day-num">{parseDate(iso).getDate()}</div>
              <div className="feed-day-dow">{dowShortUpper(iso)}</div>
            </div>
            <div className="feed-day-body">
              <div className="feed-day-status">{dayStatusText(status)}</div>
              {empty ? (
                <div className="feed-day-empty">{t.dayFree}</div>
              ) : dayEntries[0].type === 'day_off' ? (
                <div className="feed-tour-line">{t.dayOff}</div>
              ) : (
                <>
                  <div className="feed-tour-line">
                    {timeLabel(dayEntries[0])}
                    <br />
                    {dayEntries[0].title}
                  </div>
                  <div className="feed-tour-meta">
                    {statusLabel(dayEntries[0].status)}
                    {dayEntries.length > 1 ? ` · ${t.moreTours(dayEntries.length - 1)}` : ''}
                  </div>
                </>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}

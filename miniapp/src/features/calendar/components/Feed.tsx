import type { CalendarEntry } from '@/api/types';
import { useCallback, useEffect, useMemo, useRef, type CSSProperties } from 'react';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import { ENTRIES_RANGE_FROM, ENTRIES_RANGE_TO, MOCK_TODAY } from '@/config';
import { t } from '@/i18n/strings';
import {
  buildFeedDatesFromRange,
  parseDate,
  dowShortUpper,
} from '../lib/dates';
import { dayStatus, entriesOnDate, sortEntriesForDay } from '../lib/dayStatus';
import { dayStatusText, statusLabel, timeLabel } from '../lib/format';
import { useCalendar } from '../CalendarContext';

/** Overrides Virtuoso inline `height: 100%` so the scroller grows in a flex chain. */
export const FEED_VIRTUOSO_LAYOUT_STYLE: CSSProperties = {
  flex: '1 1 0',
  minHeight: 0,
  height: 'auto',
};

/** Full bounded calendar range rendered virtually (one row per day). */
export const ALL_FEED_DATES = buildFeedDatesFromRange(
  ENTRIES_RANGE_FROM,
  ENTRIES_RANGE_TO,
);

export function getTodayFeedIndex(): number {
  const index = ALL_FEED_DATES.indexOf(MOCK_TODAY);
  return index >= 0 ? index : 0;
}

function FeedDayRow({
  iso,
  isToday,
  entries,
  onOpen,
}: {
  iso: string;
  isToday: boolean;
  entries: CalendarEntry[];
  onOpen: (iso: string) => void;
}) {
  const dayEntries = sortEntriesForDay(entriesOnDate(iso, entries));
  const empty = dayEntries.length === 0;
  const status = dayStatus(iso, entries);

  return (
    <button
      type="button"
      data-feed-date={iso}
      className={`feed-day-row status-${status}${isToday ? ' today' : ''}${empty ? ' is-empty' : ''}`}
      onClick={() => onOpen(iso)}
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
}

export function Feed() {
  const {
    entries,
    scrollToTodaySignal,
    monthExpanded,
    openDayDetail,
    setVisibleFeedFromIso,
  } = useCalendar();

  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const monthExpandedRef = useRef(monthExpanded);
  monthExpandedRef.current = monthExpanded;

  const todayIndex = useMemo(() => getTodayFeedIndex(), []);

  const handleRangeChanged = useCallback(
    (range: { startIndex: number; endIndex: number }) => {
      if (monthExpandedRef.current) return;
      const iso = ALL_FEED_DATES[range.startIndex];
      if (iso) setVisibleFeedFromIso(iso);
    },
    [setVisibleFeedFromIso],
  );

  useEffect(() => {
    if (scrollToTodaySignal === 0) return;
    virtuosoRef.current?.scrollToIndex({
      index: todayIndex,
      align: 'start',
      behavior: 'smooth',
    });
  }, [scrollToTodaySignal, todayIndex]);

  return (
    <div className="feed-virtuoso-wrap" data-testid="feed-virtuoso">
      <Virtuoso
        ref={virtuosoRef}
        className="feed-virtuoso-scroller"
        style={FEED_VIRTUOSO_LAYOUT_STYLE}
        data={ALL_FEED_DATES}
        computeItemKey={(_, iso) => iso}
        initialTopMostItemIndex={todayIndex}
        increaseViewportBy={0}
        rangeChanged={handleRangeChanged}
        itemContent={(index, iso) => (
          <FeedDayRow
            iso={iso}
            isToday={index === todayIndex}
            entries={entries}
            onOpen={openDayDetail}
          />
        )}
      />
    </div>
  );
}

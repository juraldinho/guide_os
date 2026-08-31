import { useCallback, useEffect, useMemo, useRef } from 'react';
import { MOCK_TODAY } from '@/config';
import { t } from '@/i18n/strings';
import { buildFeedDates, parseDate, dowShortUpper } from '../lib/dates';
import { dayStatus, entriesOnDate, sortEntriesForDay } from '../lib/dayStatus';
import { dayStatusText, statusLabel, timeLabel } from '../lib/format';
import { useCalendar } from '../CalendarContext';

/** Subpixel guard only — not a visible scroll delay. */
export const HEADER_BOUNDARY_EPSILON = 1e-3;

export function getStickyHeaderBottom(): number {
  const header = document.querySelector('.header');
  if (!header) return 0;
  return header.getBoundingClientRect().bottom;
}

/**
 * First chronological feed row with any part still below the sticky header bottom.
 * Row is authoritative while rect.bottom is strictly below headerBottom (+ epsilon).
 */
export function pickVisibleFeedIso(
  dates: readonly string[],
  getRowElement: (iso: string) => HTMLElement | undefined,
  headerBottom: number,
): string | null {
  const boundary = headerBottom + HEADER_BOUNDARY_EPSILON;
  for (const iso of dates) {
    const el = getRowElement(iso);
    if (!el) continue;
    const { bottom } = el.getBoundingClientRect();
    if (bottom > boundary) return iso;
  }
  return null;
}

function monthYearKey(iso: string): string {
  const d = parseDate(iso);
  return `${d.getFullYear()}-${d.getMonth()}`;
}

export function Feed() {
  const {
    entries,
    feedDayCount,
    scrollToTodaySignal,
    monthExpanded,
    openDayDetail,
    setVisibleFeedFromIso,
    extendFeed,
  } = useCalendar();

  const dates = useMemo(
    () => buildFeedDates(MOCK_TODAY, feedDayCount),
    [feedDayCount],
  );

  const rowRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const sentinelRef = useRef<HTMLDivElement>(null);
  const scrollRaf = useRef(0);
  const lastReportedMonthYearRef = useRef<string | null>(null);

  const updateVisibleFromScroll = useCallback(() => {
    if (monthExpanded) return;

    const iso = pickVisibleFeedIso(
      dates,
      (date) => rowRefs.current.get(date),
      getStickyHeaderBottom(),
    );
    if (!iso) return;

    const key = monthYearKey(iso);
    if (key === lastReportedMonthYearRef.current) return;

    lastReportedMonthYearRef.current = key;
    setVisibleFeedFromIso(iso);
  }, [dates, monthExpanded, setVisibleFeedFromIso]);

  const scheduleVisibleUpdate = useCallback(() => {
    if (scrollRaf.current) return;
    scrollRaf.current = window.requestAnimationFrame(() => {
      scrollRaf.current = 0;
      updateVisibleFromScroll();
    });
  }, [updateVisibleFromScroll]);

  useEffect(() => {
    const onScroll = () => scheduleVisibleUpdate();

    document.addEventListener('scroll', onScroll, { capture: true, passive: true });
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);

    const viewport = window.visualViewport;
    if (viewport) {
      viewport.addEventListener('scroll', onScroll);
      viewport.addEventListener('resize', onScroll);
    }

    scheduleVisibleUpdate();

    return () => {
      document.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      if (viewport) {
        viewport.removeEventListener('scroll', onScroll);
        viewport.removeEventListener('resize', onScroll);
      }
      if (scrollRaf.current) window.cancelAnimationFrame(scrollRaf.current);
      scrollRaf.current = 0;
    };
  }, [scheduleVisibleUpdate]);

  useEffect(() => {
    scheduleVisibleUpdate();
  }, [dates.length, scheduleVisibleUpdate]);

  useEffect(() => {
    if (!monthExpanded) {
      scheduleVisibleUpdate();
    }
  }, [monthExpanded, scheduleVisibleUpdate]);

  useEffect(() => {
    if (!sentinelRef.current) return;
    const sentinel = sentinelRef.current;
    const observer = new IntersectionObserver(
      (entriesObserved) => {
        if (entriesObserved.some((e) => e.isIntersecting)) {
          extendFeed();
        }
      },
      { root: null, rootMargin: '200px 0px 200px 0px', threshold: 0 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [extendFeed, dates.length]);

  useEffect(() => {
    if (scrollToTodaySignal === 0) return;
    const el = rowRefs.current.get(MOCK_TODAY);
    if (el) {
      el.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
    scheduleVisibleUpdate();
    const followUp = window.setInterval(scheduleVisibleUpdate, 120);
    window.setTimeout(() => window.clearInterval(followUp), 900);
  }, [scrollToTodaySignal, scheduleVisibleUpdate]);

  const setRowRef = (iso: string, el: HTMLButtonElement | null) => {
    if (el) rowRefs.current.set(iso, el);
    else rowRefs.current.delete(iso);
  };

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
            ref={(el) => setRowRef(iso, el)}
            type="button"
            data-feed-date={iso}
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
      <div ref={sentinelRef} className="feed-load-sentinel" aria-hidden="true" />
    </div>
  );
}

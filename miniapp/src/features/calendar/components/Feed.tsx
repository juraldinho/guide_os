import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
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

/** Subpixel guard only — not a visible scroll delay. */
export const HEADER_BOUNDARY_EPSILON = 1e-3;

const FEED_IO_ROOT_MARGIN = '200px 0px 200px 0px';

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

function scrollByDelta(delta: number) {
  if (delta === 0) return;
  window.scrollBy({ top: delta, left: 0, behavior: 'auto' });
}

export function Feed() {
  const {
    entries,
    entriesReady,
    feedFrom,
    feedTo,
    scrollToTodaySignal,
    monthExpanded,
    openDayDetail,
    setVisibleFeedFromIso,
    extendFeed,
    prependFeed,
  } = useCalendar();

  const dates = useMemo(
    () => buildFeedDatesFromRange(feedFrom, feedTo),
    [feedFrom, feedTo],
  );

  const rowRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const topSentinelRef = useRef<HTMLDivElement>(null);
  const bottomSentinelRef = useRef<HTMLDivElement>(null);
  const scrollRaf = useRef(0);
  const lastReportedMonthYearRef = useRef<string | null>(null);
  const prependPendingRef = useRef(false);
  const extendPendingRef = useRef(false);
  const pendingPrependAnchorRef = useRef<{ iso: string; top: number } | null>(null);
  const silentPreloadTopRef = useRef<number | null>(null);
  const silentPreloadStartedRef = useRef(false);
  const [feedObserversEnabled, setFeedObserversEnabled] = useState(false);

  const feedFromRef = useRef(feedFrom);
  feedFromRef.current = feedFrom;
  const feedToRef = useRef(feedTo);
  feedToRef.current = feedTo;
  const monthExpandedRef = useRef(monthExpanded);
  monthExpandedRef.current = monthExpanded;

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

  const requestPrepend = useCallback(() => {
    if (prependPendingRef.current || monthExpandedRef.current) return;
    if (feedFromRef.current <= ENTRIES_RANGE_FROM) return;

    const anchorIso = pickVisibleFeedIso(
      dates,
      (date) => rowRefs.current.get(date),
      getStickyHeaderBottom(),
    );
    const anchorEl = anchorIso ? rowRefs.current.get(anchorIso) : null;

    prependPendingRef.current = true;
    if (anchorIso && anchorEl) {
      pendingPrependAnchorRef.current = {
        iso: anchorIso,
        top: anchorEl.getBoundingClientRect().top,
      };
    } else {
      pendingPrependAnchorRef.current = null;
    }
    prependFeed();
  }, [dates, prependFeed]);

  const requestExtend = useCallback(() => {
    if (extendPendingRef.current || monthExpandedRef.current) return;
    if (feedToRef.current >= ENTRIES_RANGE_TO) return;
    extendPendingRef.current = true;
    extendFeed();
  }, [extendFeed]);

  const requestPrependRef = useRef(requestPrepend);
  requestPrependRef.current = requestPrepend;
  const requestExtendRef = useRef(requestExtend);
  requestExtendRef.current = requestExtend;

  useLayoutEffect(() => {
    if (!entriesReady || silentPreloadStartedRef.current) return;
    if (!dates.includes(MOCK_TODAY)) return;

    const todayEl = rowRefs.current.get(MOCK_TODAY);
    if (!todayEl) return;

    silentPreloadStartedRef.current = true;
    silentPreloadTopRef.current = todayEl.getBoundingClientRect().top;
    prependFeed();
  }, [entriesReady, dates, prependFeed]);

  useLayoutEffect(() => {
    if (silentPreloadTopRef.current !== null) {
      const todayEl = rowRefs.current.get(MOCK_TODAY);
      if (todayEl) {
        const delta = todayEl.getBoundingClientRect().top - silentPreloadTopRef.current;
        scrollByDelta(delta);
      }
      silentPreloadTopRef.current = null;
      setFeedObserversEnabled(true);
    }

    const pending = pendingPrependAnchorRef.current;
    if (pending) {
      const anchorEl = rowRefs.current.get(pending.iso);
      if (anchorEl) {
        const delta = anchorEl.getBoundingClientRect().top - pending.top;
        scrollByDelta(delta);
      }
      pendingPrependAnchorRef.current = null;
      prependPendingRef.current = false;
    } else if (prependPendingRef.current) {
      prependPendingRef.current = false;
    }
  }, [feedFrom]);

  useLayoutEffect(() => {
    extendPendingRef.current = false;
  }, [feedTo]);

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
    if (!feedObserversEnabled) return;

    const bottomSentinel = bottomSentinelRef.current;
    const topSentinel = topSentinelRef.current;
    if (!bottomSentinel || !topSentinel) return;

    const bottomObserver = new IntersectionObserver(
      (entriesObserved) => {
        if (entriesObserved.some((e) => e.isIntersecting)) {
          requestExtendRef.current();
        }
      },
      { root: null, rootMargin: FEED_IO_ROOT_MARGIN, threshold: 0 },
    );
    const topObserver = new IntersectionObserver(
      (entriesObserved) => {
        if (entriesObserved.some((e) => e.isIntersecting)) {
          requestPrependRef.current();
        }
      },
      { root: null, rootMargin: FEED_IO_ROOT_MARGIN, threshold: 0 },
    );

    bottomObserver.observe(bottomSentinel);
    topObserver.observe(topSentinel);

    return () => {
      bottomObserver.disconnect();
      topObserver.disconnect();
    };
  }, [feedObserversEnabled]);

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
      <div
        ref={topSentinelRef}
        className="feed-load-sentinel feed-load-sentinel-top"
        data-testid="feed-sentinel-top"
        aria-hidden="true"
      />
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
      <div
        ref={bottomSentinelRef}
        className="feed-load-sentinel"
        data-testid="feed-sentinel-bottom"
        aria-hidden="true"
      />
    </div>
  );
}

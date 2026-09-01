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

/** Matches legacy IntersectionObserver rootMargin top/bottom padding. */
export const FEED_LOAD_MARGIN = 200;

export function getStickyHeaderBottom(): number {
  const header = document.querySelector('.header');
  if (!header) return 0;
  return header.getBoundingClientRect().bottom;
}

function getViewportHeight(): number {
  return window.innerHeight || document.documentElement.clientHeight || 0;
}

/**
 * Top sentinel entered the prepend band (near viewport top while scrolling up).
 */
export function isTopSentinelInPrependZone(el: HTMLElement): boolean {
  const { top, bottom } = el.getBoundingClientRect();
  return bottom > 0 && top < FEED_LOAD_MARGIN;
}

/**
 * Bottom sentinel entered the extend band (near viewport bottom while scrolling down).
 */
export function isBottomSentinelInExtendZone(el: HTMLElement): boolean {
  const { top } = el.getBoundingClientRect();
  return top < getViewportHeight() + FEED_LOAD_MARGIN;
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

function applyScrollDelta(delta: number) {
  if (delta === 0) return;
  window.scrollBy(0, delta);
  document.documentElement.scrollTop += delta;
  document.body.scrollTop += delta;
}

function scrollTodayIntoView(smooth: boolean) {
  const el = document.querySelector(`[data-feed-date="${MOCK_TODAY}"]`) as HTMLElement | null;
  if (!el) return;
  el.scrollIntoView({
    block: 'start',
    inline: 'nearest',
    behavior: smooth ? 'smooth' : 'auto',
  });
}

export function Feed() {
  const {
    entries,
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
  const initialPositioningDoneRef = useRef(false);
  const initialPositioningCompleteRef = useRef(false);
  const [chunkLoadingEnabled, setChunkLoadingEnabled] = useState(false);

  const feedFromRef = useRef(feedFrom);
  feedFromRef.current = feedFrom;
  const feedToRef = useRef(feedTo);
  feedToRef.current = feedTo;
  const monthExpandedRef = useRef(monthExpanded);
  monthExpandedRef.current = monthExpanded;
  const chunkLoadingEnabledRef = useRef(false);
  chunkLoadingEnabledRef.current = chunkLoadingEnabled;

  const topInZoneRef = useRef(false);
  const bottomInZoneRef = useRef(false);
  const programmaticScrollRef = useRef(false);
  const programmaticScrollClearRaf = useRef(0);

  const runProgrammaticScroll = useCallback((fn: () => void, deferClear = false) => {
    programmaticScrollRef.current = true;
    if (programmaticScrollClearRaf.current) {
      window.cancelAnimationFrame(programmaticScrollClearRaf.current);
      programmaticScrollClearRaf.current = 0;
    }
    fn();
    if (!deferClear) {
      programmaticScrollRef.current = false;
      return;
    }
    window.requestAnimationFrame(() => {
      programmaticScrollClearRaf.current = window.requestAnimationFrame(() => {
        programmaticScrollClearRaf.current = 0;
        programmaticScrollRef.current = false;
      });
    });
  }, []);

  const syncSentinelZoneState = useCallback(() => {
    const topSentinel = topSentinelRef.current;
    const bottomSentinel = bottomSentinelRef.current;
    if (topSentinel) {
      topInZoneRef.current = isTopSentinelInPrependZone(topSentinel);
    }
    if (bottomSentinel) {
      bottomInZoneRef.current = isBottomSentinelInExtendZone(bottomSentinel);
    }
  }, []);

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

  const runBoundaryCheck = useCallback(() => {
    if (!chunkLoadingEnabledRef.current || monthExpandedRef.current) return;
    if (programmaticScrollRef.current) return;

    const topSentinel = topSentinelRef.current;
    if (topSentinel && !prependPendingRef.current && feedFromRef.current > ENTRIES_RANGE_FROM) {
      const inZone = isTopSentinelInPrependZone(topSentinel);
      const enteredZone = inZone && !topInZoneRef.current;
      topInZoneRef.current = inZone;
      if (enteredZone) {
        requestPrepend();
      }
    }

    const bottomSentinel = bottomSentinelRef.current;
    if (bottomSentinel && !extendPendingRef.current && feedToRef.current < ENTRIES_RANGE_TO) {
      const inZone = isBottomSentinelInExtendZone(bottomSentinel);
      const enteredZone = inZone && !bottomInZoneRef.current;
      bottomInZoneRef.current = inZone;
      if (enteredZone) {
        requestExtend();
      }
    }
  }, [requestExtend, requestPrepend]);

  const scheduleScrollWork = useCallback(() => {
    if (scrollRaf.current) return;
    scrollRaf.current = window.requestAnimationFrame(() => {
      scrollRaf.current = 0;
      runBoundaryCheck();
      updateVisibleFromScroll();
    });
  }, [runBoundaryCheck, updateVisibleFromScroll]);

  useLayoutEffect(() => {
    const pending = pendingPrependAnchorRef.current;
    if (!pending) {
      if (prependPendingRef.current) {
        prependPendingRef.current = false;
        syncSentinelZoneState();
        scheduleScrollWork();
      }
      return;
    }

    const anchorEl = rowRefs.current.get(pending.iso);
    if (anchorEl) {
      const delta = anchorEl.getBoundingClientRect().top - pending.top;
      runProgrammaticScroll(() => applyScrollDelta(delta));
    }

    pendingPrependAnchorRef.current = null;
    prependPendingRef.current = false;
    syncSentinelZoneState();
    scheduleScrollWork();
  }, [feedFrom, runProgrammaticScroll, scheduleScrollWork, syncSentinelZoneState]);

  useLayoutEffect(() => {
    extendPendingRef.current = false;
    syncSentinelZoneState();
  }, [feedTo, syncSentinelZoneState]);

  useLayoutEffect(() => {
    if (!dates.includes(MOCK_TODAY)) return;

    const todayEl = rowRefs.current.get(MOCK_TODAY);
    if (!todayEl) return;
    if (initialPositioningDoneRef.current) return;

    runProgrammaticScroll(() => scrollTodayIntoView(false));
    initialPositioningDoneRef.current = true;
    initialPositioningCompleteRef.current = true;
    topInZoneRef.current = false;
    bottomInZoneRef.current = false;
    window.requestAnimationFrame(() => {
      syncSentinelZoneState();
      setChunkLoadingEnabled(true);
    });
  }, [dates, runProgrammaticScroll, syncSentinelZoneState]);

  useEffect(() => {
    if (!chunkLoadingEnabled) return;
    syncSentinelZoneState();
    scheduleScrollWork();
  }, [chunkLoadingEnabled, scheduleScrollWork, syncSentinelZoneState]);

  useEffect(() => {
    const onScroll = () => scheduleScrollWork();

    document.addEventListener('scroll', onScroll, { capture: true, passive: true });
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);

    const viewport = window.visualViewport;
    if (viewport) {
      viewport.addEventListener('scroll', onScroll);
      viewport.addEventListener('resize', onScroll);
    }

    scheduleScrollWork();

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
  }, [scheduleScrollWork]);

  useEffect(() => {
    scheduleScrollWork();
  }, [dates.length, scheduleScrollWork]);

  useEffect(() => {
    if (!monthExpanded) {
      scheduleScrollWork();
    }
  }, [monthExpanded, scheduleScrollWork]);

  useEffect(() => {
    if (scrollToTodaySignal === 0) return;
    runProgrammaticScroll(() => scrollTodayIntoView(true), true);
    scheduleScrollWork();
    const followUp = window.setInterval(scheduleScrollWork, 120);
    window.setTimeout(() => window.clearInterval(followUp), 900);
  }, [scrollToTodaySignal, runProgrammaticScroll, scheduleScrollWork]);

  useEffect(() => {
    return () => {
      if (programmaticScrollClearRaf.current) {
        window.cancelAnimationFrame(programmaticScrollClearRaf.current);
      }
    };
  }, []);

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

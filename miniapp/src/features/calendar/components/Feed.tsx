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

/** Survives React StrictMode remount within one Mini App session. */
let feedInitialPositionSessionDone = false;

/** Test-only: reset session initial-position flag between test runs. */
export function resetFeedInitialPositionSessionForTests(): void {
  feedInitialPositionSessionDone = false;
}

export function getStickyHeaderBottom(): number {
  const header = document.querySelector('.header');
  if (!header) return 0;
  return header.getBoundingClientRect().bottom;
}

function getScrollY(): number {
  return window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
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

function scrollTodayBelowHeader(smooth: boolean) {
  const el = document.querySelector(`[data-feed-date="${MOCK_TODAY}"]`) as HTMLElement | null;
  if (!el) return;
  const headerBottom = getStickyHeaderBottom();
  const top = el.getBoundingClientRect().top;
  const delta = top - headerBottom;
  if (delta === 0) return;
  if (smooth) {
    window.scrollBy({ top: delta, left: 0, behavior: 'smooth' });
  } else {
    applyScrollDelta(delta);
  }
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
  const initialPositioningCompleteRef = useRef(feedInitialPositionSessionDone);
  const [observersEnabled, setObserversEnabled] = useState(false);

  const feedFromRef = useRef(feedFrom);
  feedFromRef.current = feedFrom;
  const feedToRef = useRef(feedTo);
  feedToRef.current = feedTo;
  const monthExpandedRef = useRef(monthExpanded);
  monthExpandedRef.current = monthExpanded;

  const lastScrollYRef = useRef(0);
  const userIntentUpRef = useRef(false);
  const userIntentDownRef = useRef(false);
  const topSentinelArmedRef = useRef(true);
  const bottomSentinelArmedRef = useRef(true);
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
      lastScrollYRef.current = getScrollY();
      return;
    }
    window.requestAnimationFrame(() => {
      programmaticScrollClearRaf.current = window.requestAnimationFrame(() => {
        programmaticScrollClearRaf.current = 0;
        programmaticScrollRef.current = false;
        lastScrollYRef.current = getScrollY();
      });
    });
  }, []);

  const trackUserScrollIntent = useCallback(() => {
    if (programmaticScrollRef.current) return;

    const y = getScrollY();
    const delta = y - lastScrollYRef.current;
    if (delta < -1) userIntentUpRef.current = true;
    if (delta > 1) userIntentDownRef.current = true;
    lastScrollYRef.current = y;
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

  useLayoutEffect(() => {
    const pending = pendingPrependAnchorRef.current;
    if (!pending) {
      if (prependPendingRef.current) {
        prependPendingRef.current = false;
        scheduleVisibleUpdate();
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
    scheduleVisibleUpdate();
  }, [feedFrom, runProgrammaticScroll, scheduleVisibleUpdate]);

  useLayoutEffect(() => {
    extendPendingRef.current = false;
  }, [feedTo]);

  useLayoutEffect(() => {
    if (!dates.includes(MOCK_TODAY)) return;

    if (feedInitialPositionSessionDone) {
      initialPositioningCompleteRef.current = true;
      lastScrollYRef.current = getScrollY();
      if (!observersEnabled) {
        window.requestAnimationFrame(() => setObserversEnabled(true));
      }
      return;
    }

    runProgrammaticScroll(() => scrollTodayBelowHeader(false));
    feedInitialPositionSessionDone = true;
    initialPositioningCompleteRef.current = true;
    lastScrollYRef.current = getScrollY();
    scheduleVisibleUpdate();

    window.requestAnimationFrame(() => {
      setObserversEnabled(true);
    });
  }, [dates, observersEnabled, runProgrammaticScroll, scheduleVisibleUpdate]);

  useEffect(() => {
    const onScroll = () => {
      trackUserScrollIntent();
      scheduleVisibleUpdate();
    };

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
  }, [scheduleVisibleUpdate, trackUserScrollIntent]);

  useEffect(() => {
    scheduleVisibleUpdate();
  }, [dates.length, scheduleVisibleUpdate]);

  useEffect(() => {
    if (!monthExpanded) {
      scheduleVisibleUpdate();
    }
  }, [monthExpanded, scheduleVisibleUpdate]);

  useEffect(() => {
    if (!observersEnabled || !topSentinelRef.current) return;
    const sentinel = topSentinelRef.current;
    const observer = new IntersectionObserver(
      (entriesObserved) => {
        const entry = entriesObserved.find((e) => e.target === sentinel) ?? entriesObserved[0];
        if (!entry) return;

        if (!entry.isIntersecting) {
          topSentinelArmedRef.current = true;
          return;
        }

        if (!initialPositioningCompleteRef.current) return;
        if (!topSentinelArmedRef.current) return;
        if (!userIntentUpRef.current) return;
        if (prependPendingRef.current) return;
        if (monthExpandedRef.current) return;
        if (feedFromRef.current <= ENTRIES_RANGE_FROM) return;

        topSentinelArmedRef.current = false;
        userIntentUpRef.current = false;
        requestPrepend();
      },
      { root: null, rootMargin: '200px 0px 200px 0px', threshold: 0 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [observersEnabled, requestPrepend]);

  useEffect(() => {
    if (!observersEnabled || !bottomSentinelRef.current) return;
    const sentinel = bottomSentinelRef.current;
    const observer = new IntersectionObserver(
      (entriesObserved) => {
        const entry = entriesObserved.find((e) => e.target === sentinel) ?? entriesObserved[0];
        if (!entry) return;

        if (!entry.isIntersecting) {
          bottomSentinelArmedRef.current = true;
          return;
        }

        if (!initialPositioningCompleteRef.current) return;
        if (!bottomSentinelArmedRef.current) return;
        if (!userIntentDownRef.current) return;
        if (extendPendingRef.current) return;
        if (monthExpandedRef.current) return;
        if (feedToRef.current >= ENTRIES_RANGE_TO) return;

        bottomSentinelArmedRef.current = false;
        userIntentDownRef.current = false;
        requestExtend();
      },
      { root: null, rootMargin: '200px 0px 200px 0px', threshold: 0 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [observersEnabled, requestExtend]);

  useEffect(() => {
    if (scrollToTodaySignal === 0) return;
    runProgrammaticScroll(() => scrollTodayBelowHeader(true), true);
    scheduleVisibleUpdate();
    const followUp = window.setInterval(scheduleVisibleUpdate, 120);
    window.setTimeout(() => window.clearInterval(followUp), 900);
  }, [scrollToTodaySignal, runProgrammaticScroll, scheduleVisibleUpdate]);

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

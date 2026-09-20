import { StrictMode } from 'react';
import { act, render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { guideOsClient } from '@/api/createClient';
import { __resetMockStore } from '@/api/mock/store';
import type { MiniAppAnalyticsEventName, TourFormValues } from '@/api/types';
import { ToastProvider } from '@/components/ui/Toast';
import { CalendarProvider, useCalendar } from '@/features/calendar/CalendarContext';

type CalendarApi = ReturnType<typeof useCalendar>;

let calendar: CalendarApi;

function Probe() {
  calendar = useCalendar();
  return null;
}

function mount(strict = false) {
  const tree = (
    <ToastProvider>
      <CalendarProvider>
        <Probe />
      </CalendarProvider>
    </ToastProvider>
  );
  return render(strict ? <StrictMode>{tree}</StrictMode> : tree);
}

function eventNames(spy: {
  mock: { calls: readonly (readonly unknown[])[] };
}): MiniAppAnalyticsEventName[] {
  return spy.mock.calls.map(([name]) => name as MiniAppAnalyticsEventName);
}

const validTour: TourFormValues = {
  title: 'Synthetic tour',
  startDate: '2027-12-01',
  endDate: '2027-12-01',
  useTime: false,
  startTime: '09:00',
  endTime: '14:00',
  company: '',
  location: '',
  income: 0,
  status: 'reserved',
  payment: 'unpaid',
  note: '',
};

describe('Mini App product analytics', () => {
  beforeEach(() => {
    __resetMockStore();
    vi.restoreAllMocks();
  });

  it('records the initial Calendar view exactly once under StrictMode', async () => {
    const track = vi.spyOn(guideOsClient, 'trackAnalyticsEvent').mockResolvedValue(undefined);
    mount(true);

    await waitFor(() => {
      expect(eventNames(track)).toEqual(['miniapp_calendar_opened']);
    });
  });

  it('records only real tab transitions, including a return to Calendar', async () => {
    const track = vi.spyOn(guideOsClient, 'trackAnalyticsEvent').mockResolvedValue(undefined);
    mount();
    await waitFor(() => expect(track).toHaveBeenCalledTimes(1));

    act(() => calendar.setActiveTab('reports'));
    act(() => calendar.setActiveTab('reports'));
    act(() => calendar.setActiveTab('guideshop'));
    act(() => calendar.setActiveTab('guide_operator'));
    act(() => calendar.setActiveTab('calendar'));

    expect(eventNames(track)).toEqual([
      'miniapp_calendar_opened',
      'miniapp_reports_opened',
      'miniapp_guideshop_opened',
      'miniapp_guide_operator_opened',
      'miniapp_calendar_opened',
    ]);
  });

  it('records profile only on closed-to-open transitions', async () => {
    const track = vi.spyOn(guideOsClient, 'trackAnalyticsEvent').mockResolvedValue(undefined);
    mount();
    await waitFor(() => expect(track).toHaveBeenCalledTimes(1));

    act(() => calendar.openSettings());
    act(() => calendar.openSettings());
    act(() => calendar.closeSettings());
    act(() => calendar.openSettings());

    expect(eventNames(track).filter((name) => name === 'miniapp_profile_opened')).toHaveLength(2);
  });

  it('records picker openings and day openings without dates or metadata', async () => {
    const track = vi.spyOn(guideOsClient, 'trackAnalyticsEvent').mockResolvedValue(undefined);
    mount();
    await waitFor(() => expect(track).toHaveBeenCalledTimes(1));

    act(() => calendar.toggleMonthPicker());
    act(() => calendar.toggleMonthPicker());
    act(() => calendar.toggleMonthPicker());
    act(() => calendar.selectDateFromMonth('2026-09-02'));
    act(() => calendar.openDayDetail('2026-09-03'));

    expect(eventNames(track)).toEqual([
      'miniapp_calendar_opened',
      'miniapp_month_picker_opened',
      'miniapp_month_picker_opened',
      'miniapp_day_opened',
      'miniapp_day_opened',
    ]);
    expect(track.mock.calls.every((call) => call.length === 1)).toBe(true);
    expect(JSON.stringify(track.mock.calls)).not.toContain('2026-09');
  });

  it('records create start and one explicit unsaved cancellation', async () => {
    const track = vi.spyOn(guideOsClient, 'trackAnalyticsEvent').mockResolvedValue(undefined);
    mount();
    await waitFor(() => expect(track).toHaveBeenCalledTimes(1));

    act(() => calendar.openTourForm());
    act(() => calendar.closeOverlay());
    act(() => calendar.closeOverlay());

    expect(eventNames(track)).toEqual([
      'miniapp_calendar_opened',
      'miniapp_tour_create_started',
      'miniapp_tour_create_cancelled',
    ]);
  });

  it('does not record save intent when existing validation rejects the form', async () => {
    const track = vi.spyOn(guideOsClient, 'trackAnalyticsEvent').mockResolvedValue(undefined);
    const create = vi.spyOn(guideOsClient, 'createTour');
    mount();
    await waitFor(() => expect(track).toHaveBeenCalledTimes(1));

    await act(async () => {
      await (calendar.saveTour({ ...validTour, title: '' }) as unknown as Promise<void>);
    });

    expect(eventNames(track)).not.toContain('miniapp_tour_save_clicked');
    expect(create).not.toHaveBeenCalled();
  });

  it('records a valid save click before the API request and not as cancellation', async () => {
    const order: string[] = [];
    const track = vi.spyOn(guideOsClient, 'trackAnalyticsEvent').mockImplementation(async (name) => {
      order.push(name);
    });
    vi.spyOn(guideOsClient, 'createTour').mockImplementation(async (form) => {
      order.push('api');
      return {
        id: 'synthetic',
        type: 'tour',
        title: form.title,
        startDate: form.startDate,
        endDate: form.endDate,
        startTime: null,
        endTime: null,
        income: 0,
      };
    });
    mount();
    await waitFor(() => expect(track).toHaveBeenCalledTimes(1));
    act(() => calendar.openTourForm());

    await act(async () => {
      await (calendar.saveTour(validTour) as unknown as Promise<void>);
    });

    expect(order).toContain('miniapp_tour_save_clicked');
    expect(order.indexOf('miniapp_tour_save_clicked')).toBeLessThan(order.indexOf('api'));
    expect(order).not.toContain('miniapp_tour_create_cancelled');
    expect(eventNames(track).filter((name) => name === 'miniapp_tour_save_clicked')).toHaveLength(1);
  });

  it('measures each intentional valid retry after an API failure', async () => {
    const track = vi.spyOn(guideOsClient, 'trackAnalyticsEvent').mockResolvedValue(undefined);
    const create = vi
      .spyOn(guideOsClient, 'createTour')
      .mockRejectedValueOnce(new Error('synthetic failure'))
      .mockImplementationOnce(async (form) => ({
        id: 'synthetic',
        type: 'tour',
        title: form.title,
        startDate: form.startDate,
        endDate: form.endDate,
        startTime: null,
        endTime: null,
        income: 0,
      }));
    mount();
    await waitFor(() => expect(track).toHaveBeenCalledTimes(1));
    act(() => calendar.openTourForm());

    let firstError: unknown;
    await act(async () => {
      try {
        await (calendar.saveTour(validTour) as unknown as Promise<void>);
      } catch (error) {
        firstError = error;
      }
    });
    expect(firstError).toEqual(new Error('synthetic failure'));
    await act(async () => {
      await (calendar.saveTour(validTour) as unknown as Promise<void>);
    });

    expect(create).toHaveBeenCalledTimes(2);
    expect(eventNames(track).filter((name) => name === 'miniapp_tour_save_clicked')).toHaveLength(2);
  });

  it('records edit and confirmed deletion intents only at their action boundaries', async () => {
    const track = vi.spyOn(guideOsClient, 'trackAnalyticsEvent').mockResolvedValue(undefined);
    vi.spyOn(guideOsClient, 'getEntry').mockResolvedValue({
      id: 'ordinary',
      type: 'tour',
      title: 'Ordinary',
      startDate: '2027-12-01',
      endDate: '2027-12-01',
      startTime: null,
      endTime: null,
      income: 0,
    });
    vi.spyOn(guideOsClient, 'deleteEntry').mockResolvedValue(undefined);
    mount();
    await waitFor(() => expect(track).toHaveBeenCalledTimes(1));

    await act(async () => {
      await (calendar.editTour('ordinary') as unknown as Promise<void>);
    });
    act(() => calendar.openDelete('ordinary'));
    await act(async () => {
      await (calendar.confirmDelete() as unknown as Promise<void>);
    });

    expect(eventNames(track)).toContain('miniapp_tour_edit_started');
    expect(eventNames(track).filter((name) => name === 'miniapp_tour_delete_started')).toHaveLength(1);
  });

  it('suppresses analytics rejection without blocking navigation or form opening', async () => {
    vi.spyOn(guideOsClient, 'trackAnalyticsEvent').mockRejectedValue(new Error('private failure'));
    mount();
    await waitFor(() => expect(calendar).toBeDefined());

    act(() => calendar.setActiveTab('reports'));
    await waitFor(() => expect(calendar.activeTab).toBe('reports'));
    act(() => calendar.openTourForm());
    await waitFor(() => expect(calendar.overlay).toBe('tour-form'));
  });

  it('never emits the reserved multi-step event names', async () => {
    const track = vi.spyOn(guideOsClient, 'trackAnalyticsEvent').mockResolvedValue(undefined);
    mount();
    await waitFor(() => expect(track).toHaveBeenCalledTimes(1));
    act(() => calendar.openTourForm());
    await act(async () => {
      await (calendar.saveTour(validTour) as unknown as Promise<void>);
    });

    const names = eventNames(track) as string[];
    expect(names).not.toContain('miniapp_tour_step_dates_completed');
    expect(names).not.toContain('miniapp_tour_step_details_completed');
  });
});

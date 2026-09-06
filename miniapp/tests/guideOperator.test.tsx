import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { guideOsClient } from '@/api/createClient';
import { __resetMockStore } from '@/api/mock/store';
import { ApiError } from '@/api/httpClient';
import { ToastProvider } from '@/components/ui/Toast';
import { BottomNav } from '@/components/layout/BottomNav';
import { AppHeader } from '@/components/layout/AppHeader';
import { CalendarProvider } from '@/features/calendar/CalendarContext';
import { GuideOperatorPage } from '@/features/guideOperator/GuideOperatorPage';
import { t } from '@/i18n/strings';

function renderPage() {
  return render(
    <ToastProvider>
      <CalendarProvider>
        <GuideOperatorPage />
      </CalendarProvider>
    </ToastProvider>,
  );
}

describe('Guide Operator UI (GO6B2)', () => {
  beforeEach(() => {
    __resetMockStore();
    vi.restoreAllMocks();
    vi.spyOn(guideOsClient, 'listGuideOperatorConnections').mockResolvedValue([]);
  });

  afterEach(() => {
    cleanup();
  });

  it('places Guide Operator fourth in bottom navigation', () => {
    render(<BottomNav activeTab="guide_operator" onTabChange={() => undefined} />);
    expect(screen.getAllByRole('button').map((button) => button.textContent)).toEqual([
      t.calendar,
      t.reports,
      t.guideShop,
      t.guideOperator,
    ]);
    expect(screen.getByRole('button', { name: t.guideOperator })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('shows Guide Operator as sticky header title', () => {
    render(
      <AppHeader
        activeTab="guide_operator"
        headerMonth={8}
        headerYear={2026}
        monthExpanded={false}
        showMonthPicker={false}
        onLogoToday={() => undefined}
        onToggleMonthPicker={() => undefined}
        onSettings={() => undefined}
      />,
    );
    expect(screen.getByText(t.guideOperator)).toHaveClass('header-title-static');
  });

  it('shows loading then awaiting offers', async () => {
    let resolveList!: (
      value: Awaited<ReturnType<typeof guideOsClient.listGuideOperatorAssignmentLists>>,
    ) => void;
    vi.spyOn(guideOsClient, 'listGuideOperatorAssignmentLists').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveList = resolve;
        }),
    );
    vi.spyOn(guideOsClient, 'getGuideOperatorAssignment').mockResolvedValue(null);

    renderPage();
    expect(screen.getByText(t.guideOperatorLoading)).toBeTruthy();

    resolveList({
      asOfDate: '2026-08-28',
      awaiting: [
        {
          id: 'goasg_samarkand_01',
          companyId: 'goco_demo_01',
          companyName: 'Silk Road Operator',
          role: 'main_guide',
          startDate: '2026-09-10',
          endDate: '2026-09-12',
          responseDeadline: '2026-09-05T18:00:00Z',
          operatorMessage: 'Пожалуйста, подтвердите участие',
          status: 'offered',
          activeVersionNumber: 1,
          activeVersionUnread: false,
          pendingCriticalVersionNumber: null,
          projectionTourId: null,
          offeredAt: '2026-09-01T10:00:00Z',
          decidedAt: null,
          cancelledAt: null,
        },
      ],
      upcoming: [],
      inProgress: [],
      completed: [],
      cancelled: [],
    });

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: t.guideOperatorOpenOffer('Silk Road Operator') }),
      ).toBeTruthy();
    });
  });

  it('shows empty state when there are no pending offers', async () => {
    vi.spyOn(guideOsClient, 'listGuideOperatorAssignmentLists').mockResolvedValue({
      asOfDate: '2026-08-28',
      awaiting: [],
      upcoming: [],
      inProgress: [],
      completed: [],
      cancelled: [],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(t.guideOperatorEmpty)).toBeTruthy();
    });
    expect(screen.getByText(t.guideOperatorEmptyHint)).toBeTruthy();
  });

  it('shows error state with retry', async () => {
    vi.spyOn(guideOsClient, 'listGuideOperatorAssignmentLists')
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce({
        asOfDate: '2026-08-28',
        awaiting: [],
        upcoming: [],
        inProgress: [],
        completed: [],
        cancelled: [],
      });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(t.guideOperatorLoadError)).toBeTruthy();
    });
    fireEvent.click(screen.getByRole('button', { name: t.retry }));
    await waitFor(() => {
      expect(screen.getByText(t.guideOperatorEmpty)).toBeTruthy();
    });
  });

  it('switches lifecycle sections and opens accepted detail without actions', async () => {
    renderPage();
    await waitFor(() => screen.getByTestId('go-list-awaiting'));

    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorUpcomingTitle }));
    await waitFor(() => screen.getByTestId('go-list-upcoming'));
    expect(screen.getByText('Khiva Operator Co')).toBeTruthy();
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideOperatorOpenAssignment('Хива — обновлённая программа'),
      }),
    );
    await waitFor(() => screen.getByText(t.guideOperatorSectionOverview));
    expect(screen.queryByRole('button', { name: t.guideOperatorAccept })).toBeNull();
    expect(screen.queryByRole('button', { name: t.guideOperatorDecline })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));

    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorInProgressTitle }));
    await waitFor(() => screen.getByTestId('go-list-in_progress'));
    expect(screen.getByText('Tashkent Day Tours')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorCompletedTitle }));
    await waitFor(() => screen.getByTestId('go-list-completed'));
    expect(screen.getByText('Bukhara Heritage')).toBeTruthy();
  });

  it('shows unread indicator, structured diff, history, and clears after acknowledge', async () => {
    renderPage();
    await waitFor(() => screen.getByTestId('go-list-awaiting'));
    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorUpcomingTitle }));
    await waitFor(() => screen.getByTestId('go-list-unread-goasg_accepted_01'));
    expect(screen.getByLabelText(t.guideOperatorUnreadAria)).toBeTruthy();

    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideOperatorOpenAssignment('Хива — обновлённая программа'),
      }),
    );
    await waitFor(() => screen.getByTestId('go-changes-section'));
    expect(screen.getByText(t.guideOperatorChangesTitle)).toBeTruthy();
    expect(screen.getByText(t.guideOperatorChangeBefore)).toBeTruthy();
    expect(screen.getByText(t.guideOperatorChangeAfter)).toBeTruthy();
    expect(screen.getByText('Хива по назначению')).toBeTruthy();
    expect(screen.getAllByText('Хива — обновлённая программа').length).toBeGreaterThan(0);
    expect(screen.getByTestId('go-version-history')).toBeTruthy();
    expect(screen.getByRole('button', { name: t.guideOperatorVersionLabel(1) })).toBeTruthy();
    expect(screen.getByRole('button', { name: t.guideOperatorVersionLabel(2) })).toBeTruthy();
    expect(screen.getByTestId('go-acknowledge')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorVersionLabel(1) }));
    await waitFor(() => {
      expect(screen.getAllByText('Хива по назначению').length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByTestId('go-acknowledge'));
    await waitFor(() => {
      expect(screen.getByText(t.guideOperatorAcknowledgedToast)).toBeTruthy();
    });
    await waitFor(() => {
      expect(screen.queryByTestId('go-acknowledge')).toBeNull();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    await waitFor(() => screen.getByTestId('go-list-upcoming'));
    expect(screen.queryByTestId('go-list-unread-goasg_accepted_01')).toBeNull();
  });

  it('hides acknowledge when version is already read', async () => {
    renderPage();
    await waitFor(() => screen.getByTestId('go-list-awaiting'));
    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorInProgressTitle }));
    await waitFor(() => screen.getByTestId('go-list-in_progress'));
    expect(screen.queryByTestId('go-list-unread-goasg_in_progress_01')).toBeNull();
    fireEvent.click(
      screen.getByRole('button', { name: t.guideOperatorOpenAssignment('Ташкент сегодня') }),
    );
    await waitFor(() => screen.getByText(t.guideOperatorSectionOverview));
    expect(screen.queryByTestId('go-acknowledge')).toBeNull();
    expect(screen.queryByTestId('go-changes-section')).toBeNull();
    expect(screen.queryByRole('button', { name: t.guideOperatorAccept })).toBeNull();
  });

  it('shows cancelled section sorted newest-first with retained detail and no actions', async () => {
    renderPage();
    await waitFor(() => screen.getByTestId('go-list-awaiting'));

    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorCancelledTitle }));
    await waitFor(() => screen.getByTestId('go-list-cancelled'));
    const cards = screen.getAllByRole('button', {
      name: /Открыть назначение:/,
    });
    expect(cards[0]?.textContent).toContain('Fergana Operator');
    expect(cards[1]?.textContent).toContain('Nukus Expeditions');
    expect(screen.getByText(`${t.guideOperatorFieldCancelledAt}: 2026-08-30`)).toBeTruthy();
    expect(screen.queryByText('Khiva Operator Co')).toBeNull();

    fireEvent.click(
      screen.getByRole('button', { name: t.guideOperatorOpenAssignment('Фергана отменена') }),
    );
    await waitFor(() => screen.getByTestId('go-cancelled-banner'));
    expect(screen.getByText(t.guideOperatorCancelledBanner)).toBeTruthy();
    expect(screen.getByText(t.guideOperatorSectionOverview)).toBeTruthy();
    expect(screen.getByText(t.guideOperatorSectionProgram)).toBeTruthy();
    expect(screen.getByText('T-501')).toBeTruthy();
    expect(screen.getAllByText('2026-09-22 — 2026-09-24').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: t.guideOperatorAccept })).toBeNull();
    expect(screen.queryByRole('button', { name: t.guideOperatorDecline })).toBeNull();
    expect(screen.queryByRole('button', { name: t.edit })).toBeNull();
    expect(screen.queryByText(t.guideOperatorBackToCalendar)).toBeNull();
  });

  it('refreshes cancelled list after retry from error', async () => {
    vi.spyOn(guideOsClient, 'listGuideOperatorAssignmentLists')
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockImplementation(() =>
        Promise.resolve({
          asOfDate: '2026-08-28',
          awaiting: [],
          upcoming: [],
          inProgress: [],
          completed: [],
          cancelled: [
            {
              id: 'goasg_cancelled_newer_01',
              companyId: 'goco_demo_06',
              companyName: 'Fergana Operator',
              role: 'main_guide',
              startDate: '2026-09-22',
              endDate: '2026-09-24',
              responseDeadline: null,
              operatorMessage: null,
              status: 'cancelled',
              activeVersionNumber: 1,
              activeVersionUnread: false,
              pendingCriticalVersionNumber: null,
              projectionTourId: null,
              offeredAt: '2026-08-25T10:00:00Z',
              decidedAt: '2026-08-26T12:00:00Z',
              cancelledAt: '2026-08-30T14:00:00Z',
            },
          ],
        }),
      );
    vi.spyOn(guideOsClient, 'getGuideOperatorAssignment').mockResolvedValue({
      assignment: {
        id: 'goasg_cancelled_newer_01',
        companyId: 'goco_demo_06',
        companyName: 'Fergana Operator',
        role: 'main_guide',
        startDate: '2026-09-22',
        endDate: '2026-09-24',
        responseDeadline: null,
        operatorMessage: null,
        status: 'cancelled',
        activeVersionNumber: 1,
        activeVersionUnread: false,
        pendingCriticalVersionNumber: null,
        projectionTourId: null,
        offeredAt: '2026-08-25T10:00:00Z',
        decidedAt: '2026-08-26T12:00:00Z',
        cancelledAt: '2026-08-30T14:00:00Z',
      },
      workingPackage: {
        tour: { title: 'Фергана отменена', reference: 'T-501', city_or_route: 'Фергана' },
        days: [],
      },
      conflictDates: [],
      activeVersion: {
        versionNumber: 1,
        severity: 'initial',
        publishedAt: '2026-08-25T10:00:00Z',
        changeSummary: [],
        unread: false,
        sourceEventId: 'evt_initial_goasg_cancelled_newer_01',
      },
      pendingCriticalVersion: null,
      versions: [
        {
          versionNumber: 1,
          severity: 'initial',
          publishedAt: '2026-08-25T10:00:00Z',
          changeSummary: [],
          workingPackage: {
            tour: { title: 'Фергана отменена', reference: 'T-501', city_or_route: 'Фергана' },
            days: [],
          },
          sourceEventId: 'evt_initial_goasg_cancelled_newer_01',
        },
      ],
    });

    renderPage();
    await waitFor(() => {
      expect(screen.getByText(t.guideOperatorOfflineError)).toBeTruthy();
    });
    fireEvent.click(screen.getByRole('button', { name: t.retry }));
    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorCancelledTitle }));
    await waitFor(() => {
      expect(screen.getByText('Fergana Operator')).toBeTruthy();
    });
  });

  it('refreshes lists after accept moves offer out of awaiting', async () => {
    renderPage();
    await waitFor(() => screen.getByText('Silk Road Operator'));
    fireEvent.click(
      screen.getByRole('button', { name: t.guideOperatorOpenOffer('Самарканд классика') }),
    );
    await waitFor(() => screen.getByRole('button', { name: t.guideOperatorAccept }));
    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorAccept }));
    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorConfirmYesAccept }));
    await waitFor(() => {
      expect(screen.queryByText(t.guideOperatorDetailTitle)).toBeNull();
    });
    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorUpcomingTitle }));
    await waitFor(() => {
      expect(screen.getByText('Silk Road Operator')).toBeTruthy();
    });
  });
  it('opens detail and renders working package sections', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Silk Road Operator')).toBeTruthy();
    });
    fireEvent.click(screen.getByRole('button', { name: /Silk Road Operator|Самарканд классика/ }));
    await waitFor(() => {
      expect(screen.getByText(t.guideOperatorSectionOverview)).toBeTruthy();
    });
    expect(screen.getByText(t.guideOperatorSectionProgram)).toBeTruthy();
    expect(screen.getByText(t.guideOperatorSectionGroup)).toBeTruthy();
    expect(screen.getByText(t.guideOperatorSectionDrivers)).toBeTruthy();
    expect(screen.getByText(t.guideOperatorSectionConditions)).toBeTruthy();
    expect(screen.getByText(t.guideOperatorSectionContacts)).toBeTruthy();
    expect(screen.getByText((text) => text.includes('Встреча группы'))).toBeTruthy();
    expect(screen.getByText('Алишер')).toBeTruthy();
    expect(screen.getByText('Марина')).toBeTruthy();
    expect(screen.queryByText('Hidden')).toBeNull();
  });

  it('accepts an offer after confirmation and prevents duplicate submit', async () => {
    const acceptSpy = vi.spyOn(guideOsClient, 'acceptGuideOperatorAssignment');
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Silk Road Operator')).toBeTruthy();
    });
    fireEvent.click(
      screen.getByRole('button', { name: t.guideOperatorOpenOffer('Самарканд классика') }),
    );
    await waitFor(() => {
      expect(screen.getByRole('button', { name: t.guideOperatorAccept })).toBeTruthy();
    });
    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorAccept }));
    expect(screen.getByText(t.guideOperatorConfirmAcceptTitle)).toBeTruthy();

    acceptSpy.mockImplementation(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
      return {
        assignmentId: 'goasg_samarkand_01',
        status: 'accepted',
        decision: 'accept',
        decisionEventId: 'evt',
        projectionTourId: '99',
        replayed: false,
      };
    });

    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorConfirmYesAccept }));
    expect(screen.getByRole('button', { name: t.guideOperatorSubmitting })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorSubmitting }));
    await waitFor(() => {
      expect(acceptSpy).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.queryByText(t.guideOperatorDetailTitle)).toBeNull();
    });
  });

  it('declines an offer after confirmation', async () => {
    const declineSpy = vi.spyOn(guideOsClient, 'declineGuideOperatorAssignment');
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Silk Road Operator')).toBeTruthy();
    });
    fireEvent.click(
      screen.getByRole('button', { name: t.guideOperatorOpenOffer('Самарканд классика') }),
    );
    await waitFor(() => {
      expect(screen.getByRole('button', { name: t.guideOperatorDecline })).toBeTruthy();
    });
    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorDecline }));
    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorConfirmYesDecline }));
    await waitFor(() => {
      expect(declineSpy).toHaveBeenCalledTimes(1);
    });
  });

  it('shows conflict dates and blocks accept for conflicting offers', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Conflict Tours')).toBeTruthy();
    });
    fireEvent.click(
      screen.getByRole('button', { name: t.guideOperatorOpenOffer('Конфликтный день') }),
    );
    await waitFor(() => {
      expect(screen.getByText(t.guideOperatorConflictsTitle)).toBeTruthy();
    });
    expect(screen.getAllByText('2026-09-20').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: t.guideOperatorAccept })).toBeDisabled();
  });

  it('surfaces actionable API conflict errors', async () => {
    vi.spyOn(guideOsClient, 'acceptGuideOperatorAssignment').mockRejectedValue(
      new ApiError('calendar_conflict', 'conflict', 409),
    );
    // Use the free offer but force conflict on accept.
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Silk Road Operator')).toBeTruthy();
    });
    fireEvent.click(
      screen.getByRole('button', { name: t.guideOperatorOpenOffer('Самарканд классика') }),
    );
    await waitFor(() => {
      expect(screen.getByRole('button', { name: t.guideOperatorAccept })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorAccept }));
    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorConfirmYesAccept }));
    await waitFor(() => {
      expect(screen.getByText(t.guideOperatorConflictError)).toBeTruthy();
    });
  });

  it('shows critical pending indicator, separate changes, and reject keeps active package', async () => {
    renderPage();
    await waitFor(() => screen.getByTestId('go-list-awaiting'));
    fireEvent.click(screen.getByRole('button', { name: t.guideOperatorInProgressTitle }));
    await waitFor(() => screen.getByTestId('go-list-critical-goasg_in_progress_01'));
    expect(screen.getByText(t.guideOperatorCriticalPendingBadge)).toBeTruthy();

    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideOperatorOpenAssignment('Ташкент сегодня'),
      }),
    );
    await waitFor(() => screen.getByTestId('go-critical-pending'));
    expect(screen.getByTestId('go-critical-pending')).toBeTruthy();
    expect(screen.getAllByTestId('go-critical-change-item').length).toBeGreaterThan(0);
    expect(screen.getAllByText(t.guideOperatorCriticalPendingBadge).length).toBeGreaterThan(0);
    expect(screen.getAllByText('2026-08-29').length).toBeGreaterThan(0);
    expect(screen.getAllByText('2026-08-31').length).toBeGreaterThan(0);
    // Active package overview remains the previous dates.
    expect(
      screen.getAllByText(formatDateRangeLike('2026-08-27', '2026-08-29')).length,
    ).toBeGreaterThan(0);
    expect(screen.getByTestId('go-confirm-critical')).toBeTruthy();
    expect(screen.getByTestId('go-reject-critical')).toBeTruthy();

    fireEvent.click(screen.getByTestId('go-reject-critical'));
    fireEvent.click(screen.getByTestId('go-critical-confirm-yes'));
    await waitFor(() => {
      expect(screen.getByText(t.guideOperatorCriticalRejectedToast)).toBeTruthy();
    });
    await waitFor(() => {
      expect(screen.queryByTestId('go-critical-pending')).toBeNull();
    });
    expect(screen.getByTestId('go-version-history')).toBeTruthy();
    expect(screen.getByRole('button', { name: t.guideOperatorVersionLabel(2) })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
    await waitFor(() => screen.getByTestId('go-list-in_progress'));
    expect(screen.queryByTestId('go-list-critical-goasg_in_progress_01')).toBeNull();
  });
});

function formatDateRangeLike(start: string, end: string): string {
  if (start === end) return start;
  return `${start} — ${end}`;
}
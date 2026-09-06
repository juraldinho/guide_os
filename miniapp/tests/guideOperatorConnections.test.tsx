import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { guideOsClient } from '@/api/createClient';
import { __resetMockStore } from '@/api/mock/store';
import { ApiError } from '@/api/httpClient';
import { ToastProvider } from '@/components/ui/Toast';
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

const EMPTY_LISTS = {
  asOfDate: '2026-08-28',
  awaiting: [],
  upcoming: [],
  inProgress: [],
  completed: [],
  cancelled: [],
};

describe('Guide Operator connections UI (GO8C3)', () => {
  beforeEach(() => {
    __resetMockStore();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders pending invitations above assignment sections with actions', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('go-connections-section')).toBeTruthy();
    });
    const connectionsSection = screen.getByTestId('go-connections-section');
    const chips = screen.getByRole('tablist', { name: t.guideOperator });
    expect(
      connectionsSection.compareDocumentPosition(chips) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    expect(screen.getByText(t.guideOperatorConnectionInvitedBadge)).toBeTruthy();
    expect(screen.getByText(t.guideOperatorConnectionConfirmedBadge)).toBeTruthy();
    expect(screen.getByText(t.guideOperatorConnectionExpiredBadge)).toBeTruthy();
    expect(screen.getByText(t.guideOperatorConnectionDeclinedBadge)).toBeTruthy();
    expect(screen.getByText(t.guideOperatorConnectionDisconnectedBadge)).toBeTruthy();

    expect(screen.getByTestId('go-connection-confirm-gocon_pending_01')).toBeTruthy();
    expect(screen.getByTestId('go-connection-decline-gocon_pending_01')).toBeTruthy();
    expect(screen.queryByTestId('go-connection-confirm-gocon_confirmed_01')).toBeNull();
    expect(screen.queryByTestId('go-connection-confirm-gocon_expired_01')).toBeNull();
  });

  it('confirms invitation after explicit confirmation and refreshes', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('go-connection-confirm-gocon_pending_01')).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId('go-connection-confirm-gocon_pending_01'));
    expect(screen.getByTestId('go-connection-confirm-dialog-gocon_pending_01')).toBeTruthy();
    fireEvent.click(screen.getByTestId('go-connection-confirm-yes-gocon_pending_01'));
    await waitFor(() => {
      expect(screen.queryByTestId('go-connection-confirm-gocon_pending_01')).toBeNull();
    });
    expect(screen.getByTestId('go-connection-status-gocon_pending_01').textContent).toBe(
      t.guideOperatorConnectionConfirmedBadge,
    );
  });

  it('declines invitation after explicit confirmation', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('go-connection-decline-gocon_pending_01')).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId('go-connection-decline-gocon_pending_01'));
    fireEvent.click(screen.getByTestId('go-connection-confirm-yes-gocon_pending_01'));
    await waitFor(() => {
      expect(screen.getByTestId('go-connection-status-gocon_pending_01').textContent).toBe(
        t.guideOperatorConnectionDeclinedBadge,
      );
    });
  });

  it('shows connection decision errors for stale invitations', async () => {
    vi.spyOn(guideOsClient, 'listGuideOperatorAssignmentLists').mockResolvedValue(EMPTY_LISTS);
    vi.spyOn(guideOsClient, 'listGuideOperatorConnections').mockResolvedValue([
      {
        id: 'gocon_stale',
        companyName: 'Stale Co',
        status: 'invited',
        invitedAt: '2026-09-01T00:00:00Z',
        invitationExpiresAt: '2099-01-01T00:00:00Z',
        decidedAt: null,
        disconnectedAt: null,
        expired: false,
        actionable: true,
      },
    ]);
    vi.spyOn(guideOsClient, 'confirmGuideOperatorConnection').mockRejectedValue(
      new ApiError('connection_not_actionable', 'Приглашение больше недоступно для ответа.', 409),
    );

    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('go-connection-confirm-gocon_stale')).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId('go-connection-confirm-gocon_stale'));
    fireEvent.click(screen.getByTestId('go-connection-confirm-yes-gocon_stale'));
    await waitFor(() => {
      expect(screen.getByTestId('go-connection-action-error').textContent).toBe(
        t.guideOperatorConnectionNotActionableError,
      );
    });
  });
});

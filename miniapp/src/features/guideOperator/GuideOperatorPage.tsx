import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { ApiError } from '@/api/httpClient';
import { guideOsClient } from '@/api/createClient';
import type {
  GuideOperatorAssignment,
  GuideOperatorAssignmentDetail,
  GuideOperatorAssignmentLists,
  GuideOperatorChangeSummaryItem,
  GuideOperatorConnection,
  GuideOperatorLifecycleSection,
} from '@/api/types';
import { OverlaySheet } from '@/components/ui/OverlaySheet';
import { Chip } from '@/components/ui/Chip';
import { useToast } from '@/components/ui/Toast';
import { useCalendar } from '@/features/calendar/CalendarContext';
import { t } from '@/i18n/strings';

type ListError = 'offline' | 'generic';
type ConfirmKind = 'accept' | 'decline' | 'confirm_critical' | 'reject_critical' | null;
type ConnectionConfirmKind = 'confirm' | 'decline' | null;

const EMPTY_LISTS: GuideOperatorAssignmentLists = {
  asOfDate: '',
  awaiting: [],
  upcoming: [],
  inProgress: [],
  completed: [],
  cancelled: [],
};

const SECTION_ORDER: GuideOperatorLifecycleSection[] = [
  'awaiting',
  'upcoming',
  'in_progress',
  'completed',
  'cancelled',
];

function sectionLabel(section: GuideOperatorLifecycleSection): string {
  if (section === 'awaiting') return t.guideOperatorPendingTitle;
  if (section === 'upcoming') return t.guideOperatorUpcomingTitle;
  if (section === 'in_progress') return t.guideOperatorInProgressTitle;
  if (section === 'completed') return t.guideOperatorCompletedTitle;
  return t.guideOperatorCancelledTitle;
}

function sectionEmpty(section: GuideOperatorLifecycleSection): { title: string; hint?: string } {
  if (section === 'awaiting') {
    return { title: t.guideOperatorEmpty, hint: t.guideOperatorEmptyHint };
  }
  if (section === 'upcoming') return { title: t.guideOperatorEmptyUpcoming };
  if (section === 'in_progress') return { title: t.guideOperatorEmptyInProgress };
  if (section === 'completed') return { title: t.guideOperatorEmptyCompleted };
  return { title: t.guideOperatorEmptyCancelled };
}

function rowsForSection(
  lists: GuideOperatorAssignmentLists,
  section: GuideOperatorLifecycleSection,
): GuideOperatorAssignment[] {
  if (section === 'awaiting') return lists.awaiting;
  if (section === 'upcoming') return lists.upcoming;
  if (section === 'in_progress') return lists.inProgress;
  if (section === 'completed') return lists.completed;
  return lists.cancelled;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function formatDateRange(start: string, end: string): string {
  return start === end ? start : `${start} — ${end}`;
}

function formatCancellationDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(iso);
  return match ? match[1] : iso;
}

function roleLabel(role: string): string {
  if (role === 'main_guide') return t.guideOperatorRoleMain;
  if (role === 'assistant_guide') return t.guideOperatorRoleAssistant;
  return t.guideOperatorRoleUnknown(role);
}

function tourTitle(assignment: GuideOperatorAssignment, pkg: Record<string, unknown>): string {
  const tour = asRecord(pkg.tour);
  return (
    asString(tour?.title) ||
    asString(tour?.reference) ||
    assignment.companyName
  );
}

function cityOrRoute(_assignment: GuideOperatorAssignment, pkg: Record<string, unknown>): string | null {
  const tour = asRecord(pkg.tour);
  return asString(tour?.city_or_route) || asString(tour?.cityOrRoute) || null;
}

function referenceOf(pkg: Record<string, unknown>): string | null {
  const tour = asRecord(pkg.tour);
  return asString(tour?.reference) || null;
}

function decisionErrorMessage(
  error: unknown,
  context: 'offer' | 'critical' | 'ack' | 'connection' = 'offer',
): string {
  if (error instanceof ApiError) {
    if (error.code === 'calendar_conflict') {
      return context === 'critical'
        ? t.guideOperatorCriticalConflictError
        : t.guideOperatorConflictError;
    }
    if (error.code === 'assignment_not_actionable') {
      return context === 'critical'
        ? t.guideOperatorCriticalStaleError
        : t.guideOperatorNotActionableError;
    }
    if (error.code === 'connection_not_actionable') {
      return error.message.includes('истёк')
        ? t.guideOperatorConnectionExpiredError
        : t.guideOperatorConnectionNotActionableError;
    }
    if (error.message.trim()) return error.message;
  }
  if (error instanceof TypeError) return t.guideOperatorOfflineError;
  return t.guideOperatorDecisionError;
}

function connectionStatusLabel(connection: GuideOperatorConnection): string {
  if (connection.actionable) return t.guideOperatorConnectionInvitedBadge;
  if (connection.status === 'confirmed') return t.guideOperatorConnectionConfirmedBadge;
  if (connection.status === 'declined') return t.guideOperatorConnectionDeclinedBadge;
  if (connection.status === 'disconnected') {
    return t.guideOperatorConnectionDisconnectedBadge;
  }
  if (connection.expired || connection.status === 'invited') {
    return t.guideOperatorConnectionExpiredBadge;
  }
  return connection.status;
}

function formatChangeValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string') return value.trim() || '—';
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function changeItemLabel(item: GuideOperatorChangeSummaryItem): string {
  return (
    asString(item.path) ||
    asString(item.code) ||
    asString(item.change) ||
    t.guideOperatorChangesTitle
  );
}

function UnreadIndicator({ testId }: { testId?: string }) {
  return (
    <span
      className="guide-operator-unread-dot"
      role="status"
      aria-label={t.guideOperatorUnreadAria}
      data-testid={testId}
    />
  );
}

function CriticalPendingBadge({ testId }: { testId?: string }) {
  return (
    <span
      className="guide-operator-critical-badge"
      role="status"
      aria-label={t.guideOperatorCriticalPendingAria}
      data-testid={testId}
    >
      {t.guideOperatorCriticalPendingBadge}
    </span>
  );
}

function ChangeSummaryList({
  items,
  testIdPrefix = 'go-change',
}: {
  items: GuideOperatorChangeSummaryItem[];
  testIdPrefix?: string;
}) {
  if (items.length === 0) {
    return <p className="text-muted">{t.guideOperatorEmptyChanges}</p>;
  }
  return (
    <ul className="guide-operator-change-list">
      {items.map((item, index) => (
        <li
          key={`${changeItemLabel(item)}-${index}`}
          className="guide-operator-change-item"
          data-testid={`${testIdPrefix}-item`}
        >
          <span className="guide-operator-change-path">{changeItemLabel(item)}</span>
          <div className="guide-operator-change-pair">
            <div className="guide-operator-change-side">
              <span className="guide-operator-change-side-label">
                {t.guideOperatorChangeBefore}
              </span>
              <span className="guide-operator-wrap">{formatChangeValue(item.before)}</span>
            </div>
            <div className="guide-operator-change-side">
              <span className="guide-operator-change-side-label">
                {t.guideOperatorChangeAfter}
              </span>
              <span className="guide-operator-wrap">{formatChangeValue(item.after)}</span>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail-row">
      <span className="detail-label">{label}</span>
      <span className="detail-value guide-operator-wrap">{value}</span>
    </div>
  );
}

function WorkingPackageSections({
  detail,
  focusDate,
  viewingPackage,
}: {
  detail: GuideOperatorAssignmentDetail;
  focusDate: string | null;
  viewingPackage: Record<string, unknown>;
}) {
  const pkg = viewingPackage;
  const tour = asRecord(pkg.tour);
  const days = asArray(pkg.days);
  const drivers = asArray(pkg.drivers);
  const group = asRecord(pkg.group_summary) ?? asRecord(pkg.groupSummary);
  const conditions =
    asRecord(pkg.working_conditions) ?? asRecord(pkg.workingConditions);
  const contacts = asArray(pkg.contacts).filter((item) => {
    const row = asRecord(item);
    if (!row) return false;
    if (row.visible_to_guide === false || row.visibleToGuide === false) return false;
    return true;
  });
  const focusRef = useRef<HTMLLIElement | null>(null);

  useEffect(() => {
    if (!focusDate || !focusRef.current) return;
    focusRef.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [focusDate, detail.assignment.id, viewingPackage]);

  const showChanges =
    detail.activeVersion.unread || detail.activeVersion.changeSummary.length > 0;

  return (
    <div className="guide-operator-package">
      {detail.assignment.status === 'cancelled' ? (
        <p
          className="guide-operator-cancelled-banner"
          role="status"
          data-testid="go-cancelled-banner"
        >
          {t.guideOperatorCancelledBanner}
        </p>
      ) : null}
      {showChanges ? (
        <section
          className="guide-operator-changes"
          aria-labelledby="go-changes-title"
          data-testid="go-changes-section"
        >
          <h3 id="go-changes-title" className="guide-operator-section-title">
            {t.guideOperatorChangesTitle}
          </h3>
          {detail.activeVersion.changeSummary.length === 0 ? (
            <p className="text-muted">{t.guideOperatorEmptyChanges}</p>
          ) : (
            <ChangeSummaryList items={detail.activeVersion.changeSummary} />
          )}
        </section>
      ) : null}
      <section aria-labelledby="go-overview-title">
        <h3 id="go-overview-title" className="guide-operator-section-title">
          {t.guideOperatorSectionOverview}
        </h3>
        <DetailRow label={t.guideOperatorFieldCompany} value={detail.assignment.companyName} />
        <DetailRow
          label={t.guideOperatorFieldTour}
          value={tourTitle(detail.assignment, pkg)}
        />
        {referenceOf(pkg) ? (
          <DetailRow label={t.guideOperatorFieldReference} value={referenceOf(pkg)!} />
        ) : null}
        <DetailRow
          label={t.guideOperatorFieldDates}
          value={formatDateRange(detail.assignment.startDate, detail.assignment.endDate)}
        />
        {formatCancellationDate(detail.assignment.cancelledAt) ? (
          <DetailRow
            label={t.guideOperatorFieldCancelledAt}
            value={formatCancellationDate(detail.assignment.cancelledAt)!}
          />
        ) : null}
        {cityOrRoute(detail.assignment, pkg) ? (
          <DetailRow
            label={t.guideOperatorFieldCity}
            value={cityOrRoute(detail.assignment, pkg)!}
          />
        ) : null}
        <DetailRow
          label={t.guideOperatorFieldRole}
          value={roleLabel(detail.assignment.role)}
        />
        {asString(tour?.language) ? (
          <DetailRow label={t.guideOperatorFieldLanguage} value={asString(tour?.language)!} />
        ) : null}
        {typeof tour?.tourist_count === 'number' || typeof tour?.touristCount === 'number' ? (
          <DetailRow
            label={t.guideOperatorFieldTourists}
            value={String(tour?.tourist_count ?? tour?.touristCount)}
          />
        ) : null}
        {detail.assignment.responseDeadline ? (
          <DetailRow
            label={t.guideOperatorFieldDeadline}
            value={detail.assignment.responseDeadline}
          />
        ) : null}
        {detail.assignment.operatorMessage ? (
          <DetailRow
            label={t.guideOperatorFieldMessage}
            value={detail.assignment.operatorMessage}
          />
        ) : null}
      </section>

      {detail.conflictDates.length > 0 && detail.assignment.status === 'offered' ? (
        <section className="guide-operator-conflict" aria-live="polite">
          <h3 className="guide-operator-section-title">{t.guideOperatorConflictsTitle}</h3>
          <p className="text-muted">{t.guideOperatorConflictsHint}</p>
          <p className="guide-operator-wrap">{detail.conflictDates.join(', ')}</p>
        </section>
      ) : null}

      <section aria-labelledby="go-program-title">
        <h3 id="go-program-title" className="guide-operator-section-title">
          {t.guideOperatorSectionProgram}
        </h3>
        {days.length === 0 ? (
          <p className="text-muted">{t.guideOperatorNoProgramDays}</p>
        ) : (
          <ul className="guide-operator-day-list">
            {days.map((raw, index) => {
              const day = asRecord(raw);
              if (!day) return null;
              const date = asString(day.date) || `day-${index}`;
              const events = asArray(day.events);
              const focused = Boolean(focusDate && date === focusDate);
              return (
                <li
                  key={date}
                  ref={focused ? focusRef : undefined}
                  className={`card guide-operator-day-card${focused ? ' is-focused' : ''}`}
                  data-testid={focused ? 'go-focused-day' : undefined}
                  aria-current={focused ? 'date' : undefined}
                >
                  <strong className="guide-operator-wrap">
                    {date}
                    {asString(day.title) ? ` · ${asString(day.title)}` : ''}
                  </strong>
                  {asString(day.city_or_route) || asString(day.cityOrRoute) ? (
                    <p className="text-muted guide-operator-wrap">
                      {asString(day.city_or_route) || asString(day.cityOrRoute)}
                    </p>
                  ) : null}
                  {asString(day.comment) ? (
                    <p className="guide-operator-wrap">{asString(day.comment)}</p>
                  ) : null}
                  {events.length > 0 ? (
                    <ul className="guide-operator-event-list">
                      {events.map((eventRaw, eventIndex) => {
                        const event = asRecord(eventRaw);
                        if (!event) return null;
                        const start = asString(event.start_time) || asString(event.startTime);
                        const end = asString(event.end_time) || asString(event.endTime);
                        const time =
                          start && end ? `${start}–${end}` : start || end || null;
                        return (
                          <li key={`${date}-event-${eventIndex}`}>
                            <span className="guide-operator-wrap">
                              {time ? `${time} · ` : ''}
                              {asString(event.title) || t.guideOperatorEventLabel}
                            </span>
                            {asString(event.place) ? (
                              <span className="text-muted guide-operator-wrap">
                                {' '}
                                · {asString(event.place)}
                              </span>
                            ) : null}
                          </li>
                        );
                      })}
                    </ul>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section aria-labelledby="go-group-title">
        <h3 id="go-group-title" className="guide-operator-section-title">
          {t.guideOperatorSectionGroup}
        </h3>
        {!group ? (
          <p className="text-muted">{t.guideOperatorNoGroup}</p>
        ) : (
          <>
            {asString(group.name_or_code) || asString(group.nameOrCode) ? (
              <DetailRow
                label={t.guideOperatorFieldGroupCode}
                value={(asString(group.name_or_code) || asString(group.nameOrCode))!}
              />
            ) : null}
            {typeof group.tourist_count === 'number' || typeof group.touristCount === 'number' ? (
              <DetailRow
                label={t.guideOperatorFieldTourists}
                value={String(group.tourist_count ?? group.touristCount)}
              />
            ) : null}
            {asString(group.information) ? (
              <DetailRow label={t.guideOperatorFieldInformation} value={asString(group.information)!} />
            ) : null}
            {asString(group.comment) ? (
              <DetailRow label={t.guideOperatorFieldComment} value={asString(group.comment)!} />
            ) : null}
          </>
        )}
      </section>

      <section aria-labelledby="go-drivers-title">
        <h3 id="go-drivers-title" className="guide-operator-section-title">
          {t.guideOperatorSectionDrivers}
        </h3>
        {drivers.length === 0 ? (
          <p className="text-muted">{t.guideOperatorNoDrivers}</p>
        ) : (
          <ul className="guide-operator-day-list">
            {drivers.map((raw, index) => {
              const driver = asRecord(raw);
              if (!driver) return null;
              const status = asString(driver.information_status) || asString(driver.informationStatus);
              return (
                <li key={`driver-${index}`} className="card guide-operator-day-card">
                  <strong className="guide-operator-wrap">
                    {asString(driver.name) || t.guideOperatorDriverFallback}
                  </strong>
                  {asString(driver.phone) ? (
                    <p className="guide-operator-wrap">{asString(driver.phone)}</p>
                  ) : null}
                  {(asString(driver.start_date) || asString(driver.startDate)) &&
                  (asString(driver.end_date) || asString(driver.endDate)) ? (
                    <p className="text-muted guide-operator-wrap">
                      {formatDateRange(
                        (asString(driver.start_date) || asString(driver.startDate))!,
                        (asString(driver.end_date) || asString(driver.endDate))!,
                      )}
                    </p>
                  ) : null}
                  {status === 'confirmed' ? (
                    <p className="text-muted">{t.guideOperatorDriverConfirmed}</p>
                  ) : status === 'pending' ? (
                    <p className="text-muted">{t.guideOperatorDriverPending}</p>
                  ) : null}
                  {asString(driver.comment) ? (
                    <p className="guide-operator-wrap">{asString(driver.comment)}</p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section aria-labelledby="go-conditions-title">
        <h3 id="go-conditions-title" className="guide-operator-section-title">
          {t.guideOperatorSectionConditions}
        </h3>
        {!conditions ? (
          <p className="text-muted">{t.guideOperatorNoConditions}</p>
        ) : (
          <>
            {asString(conditions.allowance_text) || asString(conditions.allowanceText) ? (
              <DetailRow
                label={t.guideOperatorFieldAllowance}
                value={(asString(conditions.allowance_text) || asString(conditions.allowanceText))!}
              />
            ) : null}
            {asString(conditions.meals_text) || asString(conditions.mealsText) ? (
              <DetailRow
                label={t.guideOperatorFieldMeals}
                value={(asString(conditions.meals_text) || asString(conditions.mealsText))!}
              />
            ) : null}
            {asString(conditions.entrance_tickets_text) ||
            asString(conditions.entranceTicketsText) ? (
              <DetailRow
                label={t.guideOperatorFieldTickets}
                value={
                  (asString(conditions.entrance_tickets_text) ||
                    asString(conditions.entranceTicketsText))!
                }
              />
            ) : null}
            {asString(conditions.transport_text) || asString(conditions.transportText) ? (
              <DetailRow
                label={t.guideOperatorFieldTransport}
                value={(asString(conditions.transport_text) || asString(conditions.transportText))!}
              />
            ) : null}
            {asString(conditions.additional_instructions) ||
            asString(conditions.additionalInstructions) ? (
              <DetailRow
                label={t.guideOperatorFieldExtra}
                value={
                  (asString(conditions.additional_instructions) ||
                    asString(conditions.additionalInstructions))!
                }
              />
            ) : null}
          </>
        )}
      </section>

      <section aria-labelledby="go-contacts-title">
        <h3 id="go-contacts-title" className="guide-operator-section-title">
          {t.guideOperatorSectionContacts}
        </h3>
        {contacts.length === 0 ? (
          <p className="text-muted">{t.guideOperatorNoContacts}</p>
        ) : (
          <ul className="guide-operator-day-list">
            {contacts.map((raw, index) => {
              const contact = asRecord(raw);
              if (!contact) return null;
              return (
                <li key={`contact-${index}`} className="card guide-operator-day-card">
                  <strong className="guide-operator-wrap">
                    {asString(contact.name) || t.guideOperatorContactFallback}
                  </strong>
                  {asString(contact.role) ? (
                    <p className="text-muted guide-operator-wrap">{asString(contact.role)}</p>
                  ) : null}
                  {asString(contact.phone) ? (
                    <p>
                      <a className="guideshop-phone-link" href={`tel:${asString(contact.phone)}`}>
                        {asString(contact.phone)}
                      </a>
                    </p>
                  ) : null}
                  {asString(contact.comment) ? (
                    <p className="guide-operator-wrap">{asString(contact.comment)}</p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

export function GuideOperatorPage() {
  const titleId = useId();
  const { showToast } = useToast();
  const { guideOperatorFocus, returnFromGuideOperatorCalendar, refreshEntries } = useCalendar();
  const [section, setSection] = useState<GuideOperatorLifecycleSection>('awaiting');
  const [lists, setLists] = useState<GuideOperatorAssignmentLists>(EMPTY_LISTS);
  const [connections, setConnections] = useState<GuideOperatorConnection[]>([]);
  const [cardMeta, setCardMeta] = useState<
    Record<string, { title: string; city: string | null; reference: string | null }>
  >({});
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<ListError | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<GuideOperatorAssignmentDetail | null>(null);
  const [viewingVersionNumber, setViewingVersionNumber] = useState<number | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(false);
  const [detailNotFound, setDetailNotFound] = useState(false);
  const [confirmKind, setConfirmKind] = useState<ConfirmKind>(null);
  const [connectionConfirm, setConnectionConfirm] = useState<{
    id: string;
    kind: ConnectionConfirmKind;
  } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [connectionActionError, setConnectionActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!guideOperatorFocus?.assignmentId) return;
    setSelectedId(guideOperatorFocus.assignmentId);
  }, [guideOperatorFocus?.assignmentId]);

  const loadLists = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setListError(null);
    try {
      const [payload, connectionRows] = await Promise.all([
        guideOsClient.listGuideOperatorAssignmentLists(),
        guideOsClient.listGuideOperatorConnections(),
      ]);
      if (signal?.aborted) return;
      setLists(payload);
      setConnections(connectionRows);
      const allRows = [
        ...payload.awaiting,
        ...payload.upcoming,
        ...payload.inProgress,
        ...payload.completed,
        ...payload.cancelled,
      ];
      const metaEntries = await Promise.all(
        allRows.map(async (row) => {
          try {
            const detailRow = await guideOsClient.getGuideOperatorAssignment(row.id);
            if (!detailRow) {
              return [row.id, { title: row.companyName, city: null, reference: null }] as const;
            }
            return [
              row.id,
              {
                title: tourTitle(row, detailRow.workingPackage),
                city: cityOrRoute(row, detailRow.workingPackage),
                reference: referenceOf(detailRow.workingPackage),
              },
            ] as const;
          } catch {
            return [row.id, { title: row.companyName, city: null, reference: null }] as const;
          }
        }),
      );
      if (signal?.aborted) return;
      setCardMeta(Object.fromEntries(metaEntries));
    } catch (error) {
      if (signal?.aborted) return;
      setLists(EMPTY_LISTS);
      setConnections([]);
      setCardMeta({});
      setListError(error instanceof TypeError ? 'offline' : 'generic');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadLists(controller.signal);
    return () => controller.abort();
  }, [loadLists]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setViewingVersionNumber(null);
      setDetailLoading(false);
      setDetailError(false);
      setDetailNotFound(false);
      setConfirmKind(null);
      setSubmitting(false);
      setActionError(null);
      return;
    }

    const controller = new AbortController();
    setDetail(null);
    setViewingVersionNumber(null);
    setDetailLoading(true);
    setDetailError(false);
    setDetailNotFound(false);
    setConfirmKind(null);
    setActionError(null);

    void guideOsClient
      .getGuideOperatorAssignment(selectedId)
      .then((row) => {
        if (controller.signal.aborted) return;
        if (row === null) {
          setDetailNotFound(true);
          setDetail(null);
        } else {
          setDetail(row);
          setViewingVersionNumber(row.activeVersion.versionNumber);
        }
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setDetailError(true);
        setDetail(null);
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false);
      });

    return () => controller.abort();
  }, [selectedId]);

  const closeDetail = () => {
    if (submitting) return;
    const fromCalendar = Boolean(guideOperatorFocus);
    setSelectedId(null);
    if (fromCalendar) {
      returnFromGuideOperatorCalendar();
    }
  };

  const submitConnectionDecision = async (kind: 'confirm' | 'decline') => {
    if (!connectionConfirm || connectionConfirm.kind !== kind || submitting) return;
    setSubmitting(true);
    setConnectionActionError(null);
    const decisionEventId = crypto.randomUUID();
    try {
      if (kind === 'confirm') {
        await guideOsClient.confirmGuideOperatorConnection(connectionConfirm.id, {
          decisionEventId,
        });
        showToast(t.guideOperatorConnectionConfirmedToast);
      } else {
        await guideOsClient.declineGuideOperatorConnection(connectionConfirm.id, {
          decisionEventId,
        });
        showToast(t.guideOperatorConnectionDeclinedToast);
      }
      setConnectionConfirm(null);
      await loadLists();
    } catch (error) {
      setConnectionActionError(decisionErrorMessage(error, 'connection'));
      setConnectionConfirm(null);
    } finally {
      setSubmitting(false);
    }
  };

  const submitDecision = async (kind: 'accept' | 'decline') => {
    if (!selectedId || submitting) return;
    setSubmitting(true);
    setActionError(null);
    const decisionEventId = crypto.randomUUID();
    try {
      if (kind === 'accept') {
        await guideOsClient.acceptGuideOperatorAssignment(selectedId, { decisionEventId });
        showToast(t.guideOperatorAcceptedToast);
      } else {
        await guideOsClient.declineGuideOperatorAssignment(selectedId, { decisionEventId });
        showToast(t.guideOperatorDeclinedToast);
      }
      setSelectedId(null);
      await loadLists();
      if (typeof refreshEntries === 'function') {
        await refreshEntries();
      }
    } catch (error) {
      setActionError(decisionErrorMessage(error));
      setConfirmKind(null);
    } finally {
      setSubmitting(false);
    }
  };

  const submitAcknowledge = async () => {
    if (!selectedId || !detail || submitting) return;
    setSubmitting(true);
    setActionError(null);
    const decisionEventId = crypto.randomUUID();
    try {
      await guideOsClient.acknowledgeGuideOperatorVersion(selectedId, {
        decisionEventId,
        versionNumber: detail.activeVersion.versionNumber,
      });
      showToast(t.guideOperatorAcknowledgedToast);
      await loadLists();
      const refreshed = await guideOsClient.getGuideOperatorAssignment(selectedId);
      if (refreshed) {
        setDetail(refreshed);
        setViewingVersionNumber(refreshed.activeVersion.versionNumber);
      }
      if (typeof refreshEntries === 'function') {
        await refreshEntries();
      }
    } catch (error) {
      setActionError(decisionErrorMessage(error, 'ack'));
    } finally {
      setSubmitting(false);
    }
  };

  const submitCriticalDecision = async (kind: 'confirm_critical' | 'reject_critical') => {
    if (!selectedId || !detail?.pendingCriticalVersion || submitting) return;
    setSubmitting(true);
    setActionError(null);
    const decisionEventId = crypto.randomUUID();
    const versionNumber = detail.pendingCriticalVersion.versionNumber;
    try {
      if (kind === 'confirm_critical') {
        await guideOsClient.confirmGuideOperatorCriticalVersion(selectedId, {
          decisionEventId,
          versionNumber,
        });
        showToast(t.guideOperatorCriticalConfirmedToast);
      } else {
        await guideOsClient.rejectGuideOperatorCriticalVersion(selectedId, {
          decisionEventId,
          versionNumber,
        });
        showToast(t.guideOperatorCriticalRejectedToast);
      }
      setConfirmKind(null);
      await loadLists();
      const refreshed = await guideOsClient.getGuideOperatorAssignment(selectedId);
      if (refreshed) {
        setDetail(refreshed);
        setViewingVersionNumber(refreshed.activeVersion.versionNumber);
      } else {
        setDetail(null);
        setDetailNotFound(true);
      }
      if (typeof refreshEntries === 'function') {
        await refreshEntries();
      }
    } catch (error) {
      setActionError(decisionErrorMessage(error, 'critical'));
      setConfirmKind(null);
      try {
        const refreshed = await guideOsClient.getGuideOperatorAssignment(selectedId);
        if (refreshed) {
          setDetail(refreshed);
          setViewingVersionNumber(refreshed.activeVersion.versionNumber);
        }
        await loadLists();
      } catch {
        /* keep prior detail */
      }
    } finally {
      setSubmitting(false);
    }
  };

  const visibleRows = rowsForSection(lists, section);
  const emptyCopy = sectionEmpty(section);
  const viewingVersion =
    detail?.versions.find((row) => row.versionNumber === viewingVersionNumber) ?? null;
  const viewingPackage = viewingVersion?.workingPackage ?? detail?.workingPackage ?? {};
  const canAcknowledge =
    Boolean(detail) &&
    detail!.assignment.status === 'accepted' &&
    detail!.activeVersion.unread &&
    detail!.activeVersion.severity === 'ordinary' &&
    !detail!.pendingCriticalVersion;
  const canDecideCritical =
    Boolean(detail) &&
    detail!.assignment.status === 'accepted' &&
    detail!.pendingCriticalVersion !== null;

  return (
    <main className="main guide-operator-page" aria-labelledby={titleId}>
      <h2 id={titleId} className="guide-operator-page-title">
        {t.guideOperatorPageTitle}
      </h2>

      {!loading && !listError ? (
        <section
          className="guide-operator-connections"
          aria-labelledby="go-connections-title"
          data-testid="go-connections-section"
        >
          <h3 id="go-connections-title" className="guide-operator-section-title">
            {t.guideOperatorConnectionsTitle}
          </h3>
          {connections.length === 0 ? (
            <div className="guide-operator-empty" data-testid="go-connections-empty">
              <p>{t.guideOperatorConnectionsEmpty}</p>
              <p className="text-muted">{t.guideOperatorConnectionsEmptyHint}</p>
            </div>
          ) : (
            <ul className="guideshop-place-list" data-testid="go-connections-list">
              {connections.map((connection) => {
                const confirming =
                  connectionConfirm?.id === connection.id ? connectionConfirm.kind : null;
                return (
                  <li
                    key={connection.id}
                    className="card guideshop-place-card guide-operator-connection-card"
                    data-testid={`go-connection-${connection.id}`}
                  >
                    <span className="guide-operator-offer-card-head">
                      <strong className="guideshop-place-name">{connection.companyName}</strong>
                      <span
                        className={`guide-operator-connection-badge status-${connection.status}${
                          connection.expired ? ' is-expired' : ''
                        }`}
                        data-testid={`go-connection-status-${connection.id}`}
                      >
                        {connectionStatusLabel(connection)}
                      </span>
                    </span>
                    <span className="text-muted guide-operator-wrap">
                      {t.guideOperatorConnectionExpires}: {connection.invitationExpiresAt}
                    </span>
                    {connectionActionError && confirming === null && connection.actionable ? (
                      <p role="alert">{connectionActionError}</p>
                    ) : null}
                    {connection.actionable ? (
                      confirming === null ? (
                        <div className="guide-operator-actions guide-operator-connection-actions">
                          <button
                            type="button"
                            className="btn btn-primary"
                            disabled={submitting}
                            data-testid={`go-connection-confirm-${connection.id}`}
                            onClick={() =>
                              setConnectionConfirm({ id: connection.id, kind: 'confirm' })
                            }
                          >
                            {t.guideOperatorConnectionConfirm}
                          </button>
                          <button
                            type="button"
                            className="btn btn-danger"
                            disabled={submitting}
                            data-testid={`go-connection-decline-${connection.id}`}
                            onClick={() =>
                              setConnectionConfirm({ id: connection.id, kind: 'decline' })
                            }
                          >
                            {t.guideOperatorConnectionDecline}
                          </button>
                        </div>
                      ) : (
                        <div
                          className="guide-operator-confirm"
                          role="group"
                          aria-label={
                            confirming === 'confirm'
                              ? t.guideOperatorConnectionConfirmTitle
                              : t.guideOperatorConnectionDeclineTitle
                          }
                          data-testid={`go-connection-confirm-dialog-${connection.id}`}
                        >
                          <p>
                            <strong>
                              {confirming === 'confirm'
                                ? t.guideOperatorConnectionConfirmTitle
                                : t.guideOperatorConnectionDeclineTitle}
                            </strong>
                          </p>
                          <p>
                            {confirming === 'confirm'
                              ? t.guideOperatorConnectionConfirmBody
                              : t.guideOperatorConnectionDeclineBody}
                          </p>
                          <button
                            type="button"
                            className={
                              confirming === 'confirm'
                                ? 'btn btn-primary btn-block'
                                : 'btn btn-danger btn-block'
                            }
                            disabled={submitting}
                            data-testid={`go-connection-confirm-yes-${connection.id}`}
                            onClick={() => void submitConnectionDecision(confirming)}
                          >
                            {submitting
                              ? t.guideOperatorSubmitting
                              : confirming === 'confirm'
                                ? t.guideOperatorConnectionConfirmYes
                                : t.guideOperatorConnectionDeclineYes}
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary btn-block"
                            disabled={submitting}
                            onClick={() => setConnectionConfirm(null)}
                          >
                            {t.cancel}
                          </button>
                        </div>
                      )
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
          {connectionActionError && !connectionConfirm ? (
            <p role="alert" data-testid="go-connection-action-error">
              {connectionActionError}
            </p>
          ) : null}
        </section>
      ) : null}

      <div className="chip-row guide-operator-section-chips" role="tablist" aria-label={t.guideOperator}>
        {SECTION_ORDER.map((id) => (
          <Chip
            key={id}
            label={sectionLabel(id)}
            active={section === id}
            onClick={() => setSection(id)}
          />
        ))}
      </div>

      {loading ? <p className="text-muted">{t.guideOperatorLoading}</p> : null}

      {!loading && listError ? (
        <div className="guideshop-section-error" role="alert">
          <p>
            {listError === 'offline'
              ? t.guideOperatorOfflineError
              : t.guideOperatorLoadError}
          </p>
          <button type="button" className="btn btn-secondary" onClick={() => void loadLists()}>
            {t.retry}
          </button>
        </div>
      ) : null}

      {!loading && !listError && visibleRows.length === 0 ? (
        <div className="guide-operator-empty" data-testid={`go-empty-${section}`}>
          <p>{emptyCopy.title}</p>
          {emptyCopy.hint ? <p className="text-muted">{emptyCopy.hint}</p> : null}
        </div>
      ) : null}

      {!loading && !listError && visibleRows.length > 0 ? (
        <ul className="guideshop-place-list" data-testid={`go-list-${section}`}>
          {visibleRows.map((row) => {
            const meta = cardMeta[row.id];
            const title = meta?.title || row.companyName;
            const openLabel =
              row.status === 'offered'
                ? t.guideOperatorOpenOffer(title)
                : t.guideOperatorOpenAssignment(title);
            return (
              <li key={row.id}>
                <button
                  type="button"
                  className="card guideshop-place-card guide-operator-offer-card"
                  onClick={() => setSelectedId(row.id)}
                  aria-label={openLabel}
                >
                  <span className="guide-operator-offer-card-head">
                    <strong className="guideshop-place-name">{row.companyName}</strong>
                    {row.pendingCriticalVersionNumber ? (
                      <CriticalPendingBadge testId={`go-list-critical-${row.id}`} />
                    ) : row.activeVersionUnread ? (
                      <UnreadIndicator testId={`go-list-unread-${row.id}`} />
                    ) : null}
                  </span>
                  <span className="guide-operator-wrap">{title}</span>
                  {meta?.reference ? (
                    <span className="text-muted guide-operator-wrap">
                      {t.guideOperatorFieldReference}: {meta.reference}
                    </span>
                  ) : null}
                  <span className="text-muted guide-operator-wrap">
                    {formatDateRange(row.startDate, row.endDate)}
                  </span>
                  {row.status === 'cancelled' && formatCancellationDate(row.cancelledAt) ? (
                    <span className="text-muted guide-operator-wrap">
                      {t.guideOperatorFieldCancelledAt}:{' '}
                      {formatCancellationDate(row.cancelledAt)}
                    </span>
                  ) : null}
                  {meta?.city ? (
                    <span className="text-muted guide-operator-wrap">{meta.city}</span>
                  ) : null}
                  <span className="text-muted guide-operator-wrap">
                    {roleLabel(row.role)}
                  </span>
                  {row.status === 'offered' && row.responseDeadline ? (
                    <span className="text-muted guide-operator-wrap">
                      {t.guideOperatorFieldDeadline}: {row.responseDeadline}
                    </span>
                  ) : null}
                  {row.operatorMessage ? (
                    <span className="guide-operator-wrap">{row.operatorMessage}</span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}

      {selectedId ? (
        <OverlaySheet
          title={t.guideOperatorDetailTitle}
          onClose={closeDetail}
        >
          {detailLoading ? <p className="text-muted">{t.guideOperatorDetailLoading}</p> : null}
          {detailNotFound ? <p role="alert">{t.guideOperatorDetailNotFound}</p> : null}
          {detailError ? <p role="alert">{t.guideOperatorDetailError}</p> : null}
          {detail ? (
            <>
              {detail.versions.length > 1 ? (
                <section
                  className="guide-operator-version-history"
                  aria-labelledby="go-version-history-title"
                  data-testid="go-version-history"
                >
                  <h3 id="go-version-history-title" className="guide-operator-section-title">
                    {t.guideOperatorVersionHistory}
                  </h3>
                  <div className="guide-operator-version-chips" role="tablist">
                    {[...detail.versions]
                      .sort((a, b) => b.versionNumber - a.versionNumber)
                      .map((version) => (
                        <Chip
                          key={version.versionNumber}
                          label={t.guideOperatorVersionLabel(version.versionNumber)}
                          active={viewingVersionNumber === version.versionNumber}
                          onClick={() => setViewingVersionNumber(version.versionNumber)}
                        />
                      ))}
                  </div>
                </section>
              ) : null}
              {detail.pendingCriticalVersion ? (
                <section
                  className="guide-operator-critical-pending"
                  aria-labelledby="go-critical-pending-title"
                  data-testid="go-critical-pending"
                >
                  <h3 id="go-critical-pending-title" className="guide-operator-section-title">
                    {t.guideOperatorCriticalPendingTitle}
                  </h3>
                  <p className="text-muted">
                    {t.guideOperatorVersionLabel(detail.pendingCriticalVersion.versionNumber)}
                  </p>
                  <ChangeSummaryList
                    items={detail.pendingCriticalVersion.changeSummary}
                    testIdPrefix="go-critical-change"
                  />
                  {detail.pendingCriticalVersion.conflictDates.length > 0 ? (
                    <div
                      className="guideshop-section-error"
                      role="alert"
                      data-testid="go-critical-conflicts"
                    >
                      <p>
                        <strong>{t.guideOperatorCriticalConflictTitle}</strong>
                      </p>
                      <p>{t.guideOperatorCriticalConflictHint}</p>
                      <ul>
                        {detail.pendingCriticalVersion.conflictDates.map((date) => (
                          <li key={date}>{date}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </section>
              ) : null}
              <WorkingPackageSections
                detail={detail}
                focusDate={guideOperatorFocus?.focusDate ?? null}
                viewingPackage={viewingPackage}
              />
              {actionError ? (
                <p className="guideshop-section-error" role="alert">
                  {actionError}
                </p>
              ) : null}
              {canDecideCritical && confirmKind === null ? (
                <div className="guide-operator-actions">
                  <button
                    type="button"
                    className="btn btn-primary btn-block"
                    disabled={
                      submitting ||
                      (detail.pendingCriticalVersion?.conflictDates.length ?? 0) > 0
                    }
                    data-testid="go-confirm-critical"
                    onClick={() => setConfirmKind('confirm_critical')}
                  >
                    {t.guideOperatorConfirmCritical}
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger btn-block"
                    disabled={submitting}
                    data-testid="go-reject-critical"
                    onClick={() => setConfirmKind('reject_critical')}
                  >
                    {t.guideOperatorRejectCritical}
                  </button>
                </div>
              ) : null}
              {canDecideCritical &&
              (confirmKind === 'confirm_critical' || confirmKind === 'reject_critical') ? (
                <div
                  className="guide-operator-confirm"
                  role="group"
                  aria-label={
                    confirmKind === 'confirm_critical'
                      ? t.guideOperatorConfirmCriticalTitle
                      : t.guideOperatorRejectCriticalTitle
                  }
                >
                  <p>
                    <strong>
                      {confirmKind === 'confirm_critical'
                        ? t.guideOperatorConfirmCriticalTitle
                        : t.guideOperatorRejectCriticalTitle}
                    </strong>
                  </p>
                  <p>
                    {confirmKind === 'confirm_critical'
                      ? t.guideOperatorConfirmCriticalBody
                      : t.guideOperatorRejectCriticalBody}
                  </p>
                  <button
                    type="button"
                    className={
                      confirmKind === 'confirm_critical'
                        ? 'btn btn-primary btn-block'
                        : 'btn btn-danger btn-block'
                    }
                    disabled={submitting}
                    data-testid="go-critical-confirm-yes"
                    onClick={() => void submitCriticalDecision(confirmKind)}
                  >
                    {submitting
                      ? t.guideOperatorSubmitting
                      : confirmKind === 'confirm_critical'
                        ? t.guideOperatorConfirmCritical
                        : t.guideOperatorRejectCritical}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-block"
                    disabled={submitting}
                    onClick={() => setConfirmKind(null)}
                  >
                    {t.cancel}
                  </button>
                </div>
              ) : null}
              {canAcknowledge ? (
                <div className="guide-operator-actions">
                  <button
                    type="button"
                    className="btn btn-primary btn-block"
                    disabled={submitting}
                    data-testid="go-acknowledge"
                    onClick={() => void submitAcknowledge()}
                  >
                    {submitting ? t.guideOperatorSubmitting : t.guideOperatorAcknowledge}
                  </button>
                </div>
              ) : null}
              {detail.assignment.status === 'offered' ? (
                confirmKind === null ? (
                  <div className="guide-operator-actions">
                    <button
                      type="button"
                      className="btn btn-primary btn-block"
                      disabled={submitting || detail.conflictDates.length > 0}
                      onClick={() => setConfirmKind('accept')}
                    >
                      {t.guideOperatorAccept}
                    </button>
                    <button
                      type="button"
                      className="btn btn-danger btn-block"
                      disabled={submitting}
                      onClick={() => setConfirmKind('decline')}
                    >
                      {t.guideOperatorDecline}
                    </button>
                  </div>
                ) : confirmKind === 'accept' || confirmKind === 'decline' ? (
                  <div className="guide-operator-confirm" role="group" aria-label={
                    confirmKind === 'accept'
                      ? t.guideOperatorConfirmAcceptTitle
                      : t.guideOperatorConfirmDeclineTitle
                  }>
                    <p>
                      <strong>
                        {confirmKind === 'accept'
                          ? t.guideOperatorConfirmAcceptTitle
                          : t.guideOperatorConfirmDeclineTitle}
                      </strong>
                    </p>
                    <p className="text-muted">
                      {confirmKind === 'accept'
                        ? t.guideOperatorConfirmAcceptBody
                        : t.guideOperatorConfirmDeclineBody}
                    </p>
                    <button
                      type="button"
                      className={`btn btn-block ${
                        confirmKind === 'accept' ? 'btn-primary' : 'btn-danger'
                      }`}
                      disabled={submitting}
                      onClick={() => void submitDecision(confirmKind)}
                    >
                      {submitting
                        ? t.guideOperatorSubmitting
                        : confirmKind === 'accept'
                          ? t.guideOperatorConfirmYesAccept
                          : t.guideOperatorConfirmYesDecline}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-block"
                      disabled={submitting}
                      onClick={() => setConfirmKind(null)}
                    >
                      {t.cancel}
                    </button>
                  </div>
                ) : null
              ) : null}
            </>
          ) : null}
        </OverlaySheet>
      ) : null}
    </main>
  );
}

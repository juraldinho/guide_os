import type { GuideOsClient, GuideShopReadOptions, WriteOptions } from '../client';
import type {
  AvailabilityPreviewParams,
  CalendarEntry,
  CommissionReportsCompanySummary,
  CommissionReportsSummary,
  CommissionReportsSummaryParams,
  DayOffFormValues,
  GuideProfile,
  GuideProfilePatch,
  GuideTypeCode,
  ListPersonalCommissionsOptions,
  ListPersonalPlacesOptions,
  ListOfficialVisitsOptions,
  ListOfficialHistoryOptions,
  OfficialCompany,
  OfficialHistoryItem,
  OfficialPointsSummary,
  OfficialVisit,
  OfficialVisitPoint,
  GuideOperatorActiveVersion,
  GuideOperatorAssignment,
  GuideOperatorAssignmentDetail,
  GuideOperatorAssignmentLists,
  GuideOperatorAssignmentVersion,
  GuideOperatorChangeSummaryItem,
  GuideOperatorDecisionInput,
  GuideOperatorDecisionResult,
  GuideOperatorCriticalDecisionInput,
  GuideOperatorCriticalDecisionResult,
  GuideOperatorVersionAcknowledgeInput,
  GuideOperatorVersionAcknowledgeResult,
  GuideOperatorConnection,
  GuideOperatorConnectionDecisionInput,
  GuideOperatorConnectionDecisionResult,
  PersonalCommission,
  PersonalCommissionInput,
  PersonalPlace,
  PersonalPlaceInput,
  ReportsSummaryParams,
  TourFormValues,
} from '../types';
import { ApiError } from '../httpClient';
import { MOCK_TODAY } from '@/config';

const OFFER_A = 'goasg_samarkand_01';
const OFFER_B = 'goasg_conflict_02';
const ACCEPTED_A = 'goasg_accepted_01';
const ACCEPTED_IN_PROGRESS = 'goasg_in_progress_01';
const ACCEPTED_COMPLETED = 'goasg_completed_01';
const CANCELLED_NEWER = 'goasg_cancelled_newer_01';
const CANCELLED_OLDER = 'goasg_cancelled_older_02';
const CONNECTION_PENDING = 'gocon_pending_01';
const CONNECTION_CONFIRMED = 'gocon_confirmed_01';
const CONNECTION_EXPIRED = 'gocon_expired_01';
const CONNECTION_DECLINED = 'gocon_declined_01';
const CONNECTION_DISCONNECTED = 'gocon_disconnected_01';

function packageDateRange(assignmentId: string): { start: string; end: string } {
  if (assignmentId === ACCEPTED_A) return { start: '2026-09-15', end: '2026-09-17' };
  if (assignmentId === ACCEPTED_IN_PROGRESS) return { start: '2026-08-27', end: '2026-08-29' };
  if (assignmentId === ACCEPTED_COMPLETED) return { start: '2026-08-10', end: '2026-08-12' };
  if (assignmentId === CANCELLED_NEWER) return { start: '2026-09-22', end: '2026-09-24' };
  if (assignmentId === CANCELLED_OLDER) return { start: '2026-07-20', end: '2026-07-22' };
  if (assignmentId === OFFER_A) return { start: '2026-09-10', end: '2026-09-12' };
  return { start: '2026-09-20', end: '2026-09-20' };
}

function buildWorkingPackage(assignmentId: string, title: string, city: string) {
  const { start, end } = packageDateRange(assignmentId);
  const days =
    assignmentId === ACCEPTED_A
      ? [
          {
            date: '2026-09-15',
            title: 'День 1',
            city_or_route: 'Хива',
            comment: 'Встреча в аэропорту',
            events: [
              {
                start_time: '10:00',
                end_time: '11:00',
                event_type: 'meeting',
                title: 'Встреча группы',
                place: 'Аэропорт Ургенч',
                description: null,
                important_instruction: 'Табличка с названием',
              },
            ],
          },
          {
            date: '2026-09-16',
            title: 'День 2',
            city_or_route: 'Хива — Ичан-Кала',
            comment: 'Основная экскурсия',
            events: [
              {
                start_time: '09:30',
                end_time: '13:00',
                event_type: 'excursion',
                title: 'Ичан-Кала',
                place: 'Восточные ворота',
                description: 'Пешая часть',
                important_instruction: null,
              },
            ],
          },
          {
            date: '2026-09-17',
            title: 'День 3',
            city_or_route: 'Хива — отъезд',
            comment: 'Трансфер',
            events: [
              {
                start_time: '08:00',
                end_time: '09:00',
                event_type: 'transfer',
                title: 'Выезд',
                place: 'Отель',
                description: null,
                important_instruction: null,
              },
            ],
          },
        ]
      : [
          {
            date: start,
            title: 'День 1',
            city_or_route: city,
            comment: 'Сбор группы у отеля',
            events: [
              {
                start_time: '09:00',
                end_time: '10:00',
                event_type: 'meeting',
                title: 'Встреча группы',
                place: 'Лобби отеля',
                description: null,
                important_instruction: 'Иметь бейдж',
              },
              {
                start_time: '10:30',
                end_time: '13:00',
                event_type: 'excursion',
                title: 'Обзорная экскурсия',
                place: city,
                description: 'Пешая часть',
                important_instruction: null,
              },
            ],
          },
        ];

  return {
    tour: {
      id: `tour_${assignmentId}`,
      reference:
        assignmentId === ACCEPTED_A
          ? 'T-401'
          : assignmentId === OFFER_A
            ? 'T-301'
            : assignmentId === CANCELLED_NEWER
              ? 'T-501'
              : assignmentId === CANCELLED_OLDER
                ? 'T-502'
                : 'T-302',
      title,
      start_date: start,
      end_date: end,
      timezone: 'Asia/Tashkent',
      city_or_route: city,
      language: 'русский',
      tourist_count: 12,
      customer_or_agency: 'Demo Agency',
    },
    assignment: {
      id: assignmentId,
      role: 'main_guide',
      start_date: start,
      end_date: end,
    },
    days,
    drivers: [
      {
        start_date: start,
        end_date: end,
        city_or_route: city,
        name: 'Алишер',
        phone: '+998901112233',
        comment: 'Минивэн',
        information_status: 'confirmed',
      },
    ],
    group_summary: {
      name_or_code: assignmentId === ACCEPTED_A ? 'GRP-9' : 'GRP-7',
      tourist_count: 12,
      information: 'Смешанная группа',
      comment: null,
    },
    working_conditions: {
      allowance_text: 'По стандарту компании',
      meals_text: 'Завтрак включён',
      entrance_tickets_text: 'Оператор оплачивает',
      transport_text: 'Авто с водителем',
      additional_instructions: 'Форма: деловой casual',
    },
    contacts: [
      {
        name: 'Марина',
        role: 'responsible_operator',
        phone: '+998907778899',
        comment: 'Основной контакт',
        visible_to_guide: true,
      },
      {
        name: 'Hidden',
        role: 'other',
        phone: '+998900000000',
        comment: 'internal',
        visible_to_guide: false,
      },
    ],
  };
}

const INITIAL_GUIDE_OPERATOR_CONNECTIONS: GuideOperatorConnection[] = [
  {
    id: CONNECTION_PENDING,
    companyName: 'Silk Road Operator',
    status: 'invited',
    invitedAt: '2026-09-01T09:00:00Z',
    invitationExpiresAt: '2099-12-31T23:59:59Z',
    decidedAt: null,
    disconnectedAt: null,
    expired: false,
    actionable: true,
  },
  {
    id: CONNECTION_CONFIRMED,
    companyName: 'Khiva Partners',
    status: 'confirmed',
    invitedAt: '2026-08-01T10:00:00Z',
    invitationExpiresAt: '2099-12-31T23:59:59Z',
    decidedAt: '2026-08-02T12:00:00Z',
    disconnectedAt: null,
    expired: false,
    actionable: false,
  },
  {
    id: CONNECTION_EXPIRED,
    companyName: 'Expired Tours LLC',
    status: 'invited',
    invitedAt: '2026-01-01T10:00:00Z',
    invitationExpiresAt: '2026-01-15T10:00:00Z',
    decidedAt: null,
    disconnectedAt: null,
    expired: true,
    actionable: false,
  },
  {
    id: CONNECTION_DECLINED,
    companyName: 'Declined Co',
    status: 'declined',
    invitedAt: '2026-07-01T10:00:00Z',
    invitationExpiresAt: '2099-12-31T23:59:59Z',
    decidedAt: '2026-07-02T10:00:00Z',
    disconnectedAt: null,
    expired: false,
    actionable: false,
  },
  {
    id: CONNECTION_DISCONNECTED,
    companyName: 'Former Partner',
    status: 'disconnected',
    invitedAt: '2026-05-01T10:00:00Z',
    invitationExpiresAt: '2099-12-31T23:59:59Z',
    decidedAt: '2026-05-02T10:00:00Z',
    disconnectedAt: '2026-08-20T10:00:00Z',
    expired: false,
    actionable: false,
  },
];

const INITIAL_GUIDE_OPERATOR_OFFERS: GuideOperatorAssignment[] = [
  {
    id: OFFER_A,
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
  {
    id: OFFER_B,
    companyId: 'goco_demo_02',
    companyName: 'Conflict Tours',
    role: 'main_guide',
    startDate: '2026-09-20',
    endDate: '2026-09-20',
    responseDeadline: null,
    operatorMessage: 'Есть пересечение с вашим календарём',
    status: 'offered',
    activeVersionNumber: 1,
    activeVersionUnread: false,
  pendingCriticalVersionNumber: null,
    projectionTourId: null,
    offeredAt: '2026-09-02T10:00:00Z',
    decidedAt: null,
    cancelledAt: null,
  },
];

const INITIAL_ACCEPTED_ASSIGNMENT: GuideOperatorAssignment = {
  id: ACCEPTED_A,
  companyId: 'goco_demo_03',
  companyName: 'Khiva Operator Co',
  role: 'main_guide',
  startDate: '2026-09-15',
  endDate: '2026-09-17',
  responseDeadline: null,
  operatorMessage: 'Уже принято — смотрите детали в календаре',
  status: 'accepted',
  activeVersionNumber: 2,
  activeVersionUnread: true,
  pendingCriticalVersionNumber: null,
  projectionTourId: 'go_t_accepted_01',
  offeredAt: '2026-08-20T10:00:00Z',
  decidedAt: '2026-08-21T12:00:00Z',
  cancelledAt: null,
};

const INITIAL_IN_PROGRESS_ASSIGNMENT: GuideOperatorAssignment = {
  id: ACCEPTED_IN_PROGRESS,
  companyId: 'goco_demo_04',
  companyName: 'Tashkent Day Tours',
  role: 'main_guide',
  startDate: '2026-08-27',
  endDate: '2026-08-29',
  responseDeadline: null,
  operatorMessage: null,
  status: 'accepted',
  activeVersionNumber: 1,
  activeVersionUnread: false,
  pendingCriticalVersionNumber: null,
  projectionTourId: 'go_t_in_progress_01',
  offeredAt: '2026-08-15T10:00:00Z',
  decidedAt: '2026-08-16T12:00:00Z',
  cancelledAt: null,
};

const INITIAL_COMPLETED_ASSIGNMENT: GuideOperatorAssignment = {
  id: ACCEPTED_COMPLETED,
  companyId: 'goco_demo_05',
  companyName: 'Bukhara Heritage',
  role: 'assistant_guide',
  startDate: '2026-08-10',
  endDate: '2026-08-12',
  responseDeadline: null,
  operatorMessage: null,
  status: 'accepted',
  activeVersionNumber: 1,
  activeVersionUnread: false,
  pendingCriticalVersionNumber: null,
  projectionTourId: 'go_t_completed_01',
  offeredAt: '2026-08-01T10:00:00Z',
  decidedAt: '2026-08-02T12:00:00Z',
  cancelledAt: null,
};

const INITIAL_CANCELLED_NEWER: GuideOperatorAssignment = {
  id: CANCELLED_NEWER,
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
};

const INITIAL_CANCELLED_OLDER: GuideOperatorAssignment = {
  id: CANCELLED_OLDER,
  companyId: 'goco_demo_07',
  companyName: 'Nukus Expeditions',
  role: 'assistant_guide',
  startDate: '2026-07-20',
  endDate: '2026-07-22',
  responseDeadline: null,
  operatorMessage: null,
  status: 'cancelled',
  activeVersionNumber: 1,
  activeVersionUnread: false,
  pendingCriticalVersionNumber: null,
  projectionTourId: null,
  offeredAt: '2026-07-01T10:00:00Z',
  decidedAt: '2026-07-02T12:00:00Z',
  cancelledAt: '2026-07-10T09:00:00Z',
};

function buildInitialVersionBundle(
  assignment: GuideOperatorAssignment,
  workingPackage: Record<string, unknown>,
  conflictDates: string[] = [],
): GuideOperatorAssignmentDetail {
  const publishedAt = assignment.offeredAt;
  const sourceEventId = `evt_initial_${assignment.id}`;
  const version: GuideOperatorAssignmentVersion = {
    versionNumber: 1,
    severity: 'initial',
    publishedAt,
    changeSummary: [],
    workingPackage: structuredClone(workingPackage),
    sourceEventId,
  };
  const activeVersion: GuideOperatorActiveVersion = {
    versionNumber: 1,
    severity: 'initial',
    publishedAt,
    changeSummary: [],
    unread: false,
    sourceEventId,
  };
  return {
    assignment: {
      ...assignment,
      activeVersionNumber: 1,
      activeVersionUnread: false,
      pendingCriticalVersionNumber: null,
    },
    workingPackage: structuredClone(workingPackage),
    conflictDates: [...conflictDates],
    activeVersion,
    pendingCriticalVersion: null,
    versions: [version],
  };
}

const KHIVA_V1_PACKAGE = buildWorkingPackage(ACCEPTED_A, 'Хива по назначению', 'Хива');
const KHIVA_V2_PACKAGE = (() => {
  const pkg = structuredClone(KHIVA_V1_PACKAGE) as Record<string, unknown>;
  const tour = { ...(pkg.tour as Record<string, unknown>), title: 'Хива — обновлённая программа' };
  pkg.tour = tour;
  return pkg;
})();
const KHIVA_V2_CHANGE_SUMMARY: GuideOperatorChangeSummaryItem[] = [
  {
    code: 'tour_title_changed',
    severity: 'ordinary',
    path: 'tour.title',
    change: 'updated',
    before: 'Хива по назначению',
    after: 'Хива — обновлённая программа',
  },
];

const INITIAL_GUIDE_OPERATOR_DETAILS: Record<string, GuideOperatorAssignmentDetail> = {
  [OFFER_A]: buildInitialVersionBundle(
    INITIAL_GUIDE_OPERATOR_OFFERS[0],
    buildWorkingPackage(OFFER_A, 'Самарканд классика', 'Самарканд'),
  ),
  [OFFER_B]: buildInitialVersionBundle(
    INITIAL_GUIDE_OPERATOR_OFFERS[1],
    buildWorkingPackage(OFFER_B, 'Конфликтный день', 'Бухара'),
    ['2026-09-20'],
  ),
  [ACCEPTED_A]: {
    assignment: INITIAL_ACCEPTED_ASSIGNMENT,
    workingPackage: structuredClone(KHIVA_V2_PACKAGE),
    conflictDates: [],
    activeVersion: {
      versionNumber: 2,
      severity: 'ordinary',
      publishedAt: '2026-09-01T08:00:00Z',
      changeSummary: structuredClone(KHIVA_V2_CHANGE_SUMMARY),
      unread: true,
      sourceEventId: 'evt_go_version_accepted_01_v2',
    },
    pendingCriticalVersion: null,
    versions: [
      {
        versionNumber: 1,
        severity: 'initial',
        publishedAt: '2026-08-20T10:00:00Z',
        changeSummary: [],
        workingPackage: structuredClone(KHIVA_V1_PACKAGE),
        sourceEventId: 'evt_initial_goasg_accepted_01',
      },
      {
        versionNumber: 2,
        severity: 'ordinary',
        publishedAt: '2026-09-01T08:00:00Z',
        changeSummary: structuredClone(KHIVA_V2_CHANGE_SUMMARY),
        workingPackage: structuredClone(KHIVA_V2_PACKAGE),
        sourceEventId: 'evt_go_version_accepted_01_v2',
      },
    ],
  },
  [ACCEPTED_IN_PROGRESS]: (() => {
    const basePackage = buildWorkingPackage(
      ACCEPTED_IN_PROGRESS,
      'Ташкент сегодня',
      'Ташкент',
    );
    const pendingPackage = structuredClone(basePackage) as Record<string, unknown>;
    const assignmentPart = {
      ...(pendingPackage.assignment as Record<string, unknown>),
      start_date: '2026-08-27',
      end_date: '2026-08-31',
      role: 'assistant_guide',
    };
    pendingPackage.assignment = assignmentPart;
    const tourPart = {
      ...(pendingPackage.tour as Record<string, unknown>),
      title: 'Ташкент — расширенные даты',
    };
    pendingPackage.tour = tourPart;
    const days = Array.isArray(pendingPackage.days)
      ? (pendingPackage.days as Record<string, unknown>[])
      : [];
    if (days[0]) days[0] = { ...days[0], date: '2026-08-27' };
    if (days[1]) days[1] = { ...days[1], date: '2026-08-31' };
    pendingPackage.days = days;
    const changeSummary: GuideOperatorChangeSummaryItem[] = [
      {
        code: 'end_date_changed',
        severity: 'critical',
        path: 'assignment.end_date',
        change: 'updated',
        before: '2026-08-29',
        after: '2026-08-31',
      },
      {
        code: 'role_changed',
        severity: 'critical',
        path: 'assignment.role',
        change: 'updated',
        before: 'main_guide',
        after: 'assistant_guide',
      },
    ];
    const assignment = {
      ...INITIAL_IN_PROGRESS_ASSIGNMENT,
      pendingCriticalVersionNumber: 2,
    };
    return {
      assignment,
      workingPackage: structuredClone(basePackage),
      conflictDates: [],
      activeVersion: {
        versionNumber: 1,
        severity: 'initial',
        publishedAt: assignment.offeredAt,
        changeSummary: [],
        unread: false,
        sourceEventId: `evt_initial_${ACCEPTED_IN_PROGRESS}`,
      },
      pendingCriticalVersion: {
        versionNumber: 2,
        severity: 'critical',
        publishedAt: '2026-08-26T09:00:00Z',
        changeSummary: structuredClone(changeSummary),
        workingPackage: structuredClone(pendingPackage),
        sourceEventId: 'evt_go_critical_in_progress_v2',
        conflictDates: [],
      },
      versions: [
        {
          versionNumber: 1,
          severity: 'initial',
          publishedAt: assignment.offeredAt,
          changeSummary: [],
          workingPackage: structuredClone(basePackage),
          sourceEventId: `evt_initial_${ACCEPTED_IN_PROGRESS}`,
        },
        {
          versionNumber: 2,
          severity: 'critical',
          publishedAt: '2026-08-26T09:00:00Z',
          changeSummary: structuredClone(changeSummary),
          workingPackage: structuredClone(pendingPackage),
          sourceEventId: 'evt_go_critical_in_progress_v2',
        },
      ],
    } satisfies GuideOperatorAssignmentDetail;
  })(),
  [ACCEPTED_COMPLETED]: buildInitialVersionBundle(
    INITIAL_COMPLETED_ASSIGNMENT,
    buildWorkingPackage(ACCEPTED_COMPLETED, 'Бухара завершена', 'Бухара'),
  ),
  [CANCELLED_NEWER]: buildInitialVersionBundle(
    INITIAL_CANCELLED_NEWER,
    buildWorkingPackage(CANCELLED_NEWER, 'Фергана отменена', 'Фергана'),
  ),
  [CANCELLED_OLDER]: buildInitialVersionBundle(
    INITIAL_CANCELLED_OLDER,
    buildWorkingPackage(CANCELLED_OLDER, 'Нукус отменён', 'Нукус'),
  ),
};
import { buildAvailabilityPreview } from '@/features/reports/lib/availability';
import { calcSummary } from '@/features/reports/lib/summary';
import { occurredAtToBusinessDate } from '@/features/guideshop/lib/commissionMoney';
import { INITIAL_ENTRIES, MOCK_PROFILE } from './data';

const MOCK_GUIDE_TYPE_LABELS: Record<GuideTypeCode, string> = {
  local: 'Локальный гид',
  route: 'Маршрутный гид',
  accompanying: 'Сопровождающий гид',
};

const PLACE_A = 'place_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const PLACE_B = 'place_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

const UNRESOLVED_COMPANY_NAME = 'Компания не найдена';

const OFFICIAL_A = 'gsco_silkroad_01';
const OFFICIAL_B = 'gsco_nullfields_02';
const OFFICIAL_C = 'gsco_ceramic_shop_03';

const INITIAL_OFFICIAL_COMPANIES: OfficialCompany[] = [
  {
    id: OFFICIAL_A,
    displayName: 'Silk Road Emporium',
    status: 'active',
    phone: '+998901112233',
    address: 'Registan Square, Samarkand',
    description: 'Official GuideShop partner for crafts and textiles',
    type: 'shop',
  },
  {
    id: OFFICIAL_B,
    displayName: 'Bukhara Courtyard Cafe',
    status: 'inactive',
    phone: null,
    address: null,
    description: null,
    type: null,
  },
  {
    id: OFFICIAL_C,
    displayName: 'Khiva Ceramic Workshop',
    status: 'active',
    phone: '+998933334455',
    address: 'Ichan-Kala, Khiva',
    description: 'Handmade ceramics for tour groups',
    type: 'workshop',
  },
];

const VISIT_A = 'gsvis_silk_01';
const VISIT_B = 'gsvis_silk_02';
const VISIT_C = 'gsvis_khiva_03';

const INITIAL_OFFICIAL_VISITS: OfficialVisit[] = [
  {
    id: VISIT_A,
    companyId: OFFICIAL_A,
    visitAt: '2026-08-10T09:00:00Z',
    status: 'completed',
    touristCount: 4,
    customerPaymentStatus: 'paid',
    customerPaidAt: '2026-08-10T11:30:00Z',
    createdAt: '2026-08-10T09:05:00Z',
    updatedAt: '2026-08-10T11:30:00Z',
  },
  {
    id: VISIT_B,
    companyId: OFFICIAL_A,
    visitAt: '2026-08-18T14:00:00Z',
    status: 'active',
    touristCount: 2,
    customerPaymentStatus: 'unpaid',
    customerPaidAt: null,
    createdAt: '2026-08-18T14:05:00Z',
    updatedAt: '2026-08-18T14:05:00Z',
  },
  {
    id: VISIT_C,
    companyId: OFFICIAL_C,
    visitAt: '2026-08-20T08:30:00Z',
    status: 'cancelled',
    touristCount: 0,
    customerPaymentStatus: 'unpaid',
    customerPaidAt: null,
    createdAt: '2026-08-20T08:35:00Z',
    updatedAt: '2026-08-20T09:00:00Z',
  },
];

const INITIAL_OFFICIAL_POINTS_SUMMARY: OfficialPointsSummary = {
  unit: 'PTS',
  pendingTotal: '12.50',
  creditedTotal: '4.00',
  companies: [
    {
      companyId: OFFICIAL_A,
      displayName: 'Silk Road Emporium',
      pendingTotal: '10.00',
      creditedTotal: '3.00',
    },
    {
      companyId: OFFICIAL_C,
      displayName: 'Khiva Ceramic Workshop',
      pendingTotal: '2.50',
      creditedTotal: '1.00',
    },
  ],
};

const INITIAL_OFFICIAL_VISIT_POINTS: Record<string, OfficialVisitPoint[]> = {
  [VISIT_A]: [{ amount: '10.00', unit: 'PTS', status: 'pending' }],
  [VISIT_B]: [],
  [VISIT_C]: [{ amount: '2.50', unit: 'PTS', status: 'credited' }],
};

const PAYOUT_A = 'gspay_silk_01';
const PAYOUT_B = 'gspay_khiva_02';

const INITIAL_OFFICIAL_HISTORY: OfficialHistoryItem[] = [
  {
    id: PAYOUT_A,
    pointsAccrualId: 'gsacc_silk_01',
    companyId: OFFICIAL_A,
    visitId: VISIT_A,
    amount: '3.00',
    unit: 'PTS',
    paidAt: '2026-08-12T10:00:00Z',
    createdAt: '2026-08-12T10:00:00Z',
  },
  {
    id: PAYOUT_B,
    pointsAccrualId: 'gsacc_khiva_02',
    companyId: OFFICIAL_C,
    visitId: VISIT_C,
    amount: '1.00',
    unit: 'PTS',
    paidAt: '2026-08-21T08:00:00Z',
    createdAt: '2026-08-21T08:00:00Z',
  },
];

const INITIAL_PERSONAL_PLACES: PersonalPlace[] = [
  {
    id: PLACE_A,
    name: 'Бухара Арт',
    category: 'Магазин',
    generalLocation: 'Бухара',
    landmark: 'Рядом с Ляби-Хауз',
    note: 'Личная компания для учёта комиссий',
    status: 'active',
    createdAt: '2026-08-01T10:00:00Z',
    updatedAt: '2026-08-01T10:00:00Z',
  },
  {
    id: PLACE_B,
    name: 'Restaurant Platan',
    category: 'Ресторан',
    generalLocation: 'Самарканд',
    landmark: null,
    note: null,
    status: 'active',
    createdAt: '2026-08-02T10:00:00Z',
    updatedAt: '2026-08-02T10:00:00Z',
  },
];

const INITIAL_PERSONAL_COMMISSIONS: PersonalCommission[] = [
  {
    id: 'entry_11111111111111111111111111111111',
    placeId: PLACE_A,
    occurredAt: '2026-08-10T05:00:00Z',
    purchaseAmountMinor: null,
    receivedIncomeMinor: null,
    receivedPoints: 15,
    currency: null,
    note: 'Первая комиссия',
    status: 'active',
    createdAt: '2026-08-10T06:00:00Z',
    updatedAt: '2026-08-10T06:00:00Z',
  },
  {
    id: 'entry_22222222222222222222222222222222',
    placeId: PLACE_A,
    occurredAt: '2026-08-12T05:00:00Z',
    purchaseAmountMinor: null,
    receivedIncomeMinor: null,
    receivedPoints: 40,
    currency: null,
    note: 'Вторая комиссия',
    status: 'active',
    createdAt: '2026-08-12T06:00:00Z',
    updatedAt: '2026-08-12T06:00:00Z',
  },
  {
    id: 'entry_33333333333333333333333333333333',
    placeId: PLACE_B,
    occurredAt: '2026-08-14T05:00:00Z',
    purchaseAmountMinor: null,
    receivedIncomeMinor: null,
    receivedPoints: 25,
    currency: null,
    note: 'Комиссия Platan',
    status: 'active',
    createdAt: '2026-08-14T06:00:00Z',
    updatedAt: '2026-08-14T06:00:00Z',
  },
  {
    id: 'entry_44444444444444444444444444444444',
    placeId: PLACE_A,
    occurredAt: '2026-08-05T05:00:00Z',
    purchaseAmountMinor: null,
    receivedIncomeMinor: null,
    receivedPoints: 10,
    currency: null,
    note: 'Неактивная запись',
    status: 'inactive',
    createdAt: '2026-08-05T06:00:00Z',
    updatedAt: '2026-08-05T07:00:00Z',
  },
];

function cloneProfile(source: GuideProfile): GuideProfile {
  return {
    ...source,
    types: source.types.map((t) => ({ ...t, geo: [...t.geo] })),
    languages: [...source.languages],
    notifications: { ...source.notifications },
  };
}

function clonePlace(place: PersonalPlace): PersonalPlace {
  return { ...place };
}

function cloneOfficialCompany(company: OfficialCompany): OfficialCompany {
  return { ...company };
}

function cloneOfficialVisit(visit: OfficialVisit): OfficialVisit {
  return {
    ...visit,
    points: visit.points?.map((point) => ({ ...point })),
  };
}

function cloneOfficialPointsSummary(summary: OfficialPointsSummary): OfficialPointsSummary {
  return {
    ...summary,
    companies: summary.companies.map((item) => ({ ...item })),
  };
}

function cloneOfficialHistoryItem(item: OfficialHistoryItem): OfficialHistoryItem {
  return { ...item };
}

function cloneCommission(item: PersonalCommission): PersonalCommission {
  return { ...item };
}

function utcNow(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
}

let nextId = 10;
let nextPlaceSeq = 12;
let nextCommissionSeq = 20;
const entries: CalendarEntry[] = INITIAL_ENTRIES.map((e) => ({ ...e }));
let profile: GuideProfile = cloneProfile(MOCK_PROFILE);
let personalPlaces: PersonalPlace[] = INITIAL_PERSONAL_PLACES.map(clonePlace);
let personalCommissions: PersonalCommission[] = INITIAL_PERSONAL_COMMISSIONS.map(cloneCommission);
let officialCompanies: OfficialCompany[] = INITIAL_OFFICIAL_COMPANIES.map(cloneOfficialCompany);
let officialVisits: OfficialVisit[] = INITIAL_OFFICIAL_VISITS.map(cloneOfficialVisit);
let officialPointsSummary: OfficialPointsSummary = cloneOfficialPointsSummary(
  INITIAL_OFFICIAL_POINTS_SUMMARY,
);
let officialHistory: OfficialHistoryItem[] = INITIAL_OFFICIAL_HISTORY.map(
  cloneOfficialHistoryItem,
);
let guideOperatorOffers: GuideOperatorAssignment[] = INITIAL_GUIDE_OPERATOR_OFFERS.map(
  (row) => ({ ...row }),
);
let guideOperatorConnections: GuideOperatorConnection[] =
  INITIAL_GUIDE_OPERATOR_CONNECTIONS.map((row) => ({ ...row }));
let guideOperatorDetails: Record<string, GuideOperatorAssignmentDetail> = Object.fromEntries(
  Object.entries(INITIAL_GUIDE_OPERATOR_DETAILS).map(([id, detail]) => [
    id,
    cloneGuideOperatorDetail(detail),
  ]),
);
const guideOperatorDecisions = new Map<string, GuideOperatorDecisionResult>();
const guideOperatorConnectionDecisions = new Map<
  string,
  GuideOperatorConnectionDecisionResult
>();
const guideOperatorCriticalDecisions = new Map<string, GuideOperatorCriticalDecisionResult>();
const guideOperatorCriticalDecisionsByAssignmentVersion = new Map<
  string,
  GuideOperatorCriticalDecisionResult
>();
const guideOperatorVersionAcks = new Map<string, GuideOperatorVersionAcknowledgeResult>();
const guideOperatorVersionAcksByAssignmentVersion = new Map<
  string,
  GuideOperatorVersionAcknowledgeResult
>();

function cloneGuideOperatorAssignment(row: GuideOperatorAssignment): GuideOperatorAssignment {
  return { ...row };
}

function cloneGuideOperatorDetail(
  detail: GuideOperatorAssignmentDetail,
): GuideOperatorAssignmentDetail {
  return {
    assignment: cloneGuideOperatorAssignment(detail.assignment),
    workingPackage: structuredClone(detail.workingPackage),
    conflictDates: [...detail.conflictDates],
    activeVersion: {
      ...detail.activeVersion,
      changeSummary: structuredClone(detail.activeVersion.changeSummary),
    },
    pendingCriticalVersion: detail.pendingCriticalVersion
      ? {
          ...detail.pendingCriticalVersion,
          changeSummary: structuredClone(detail.pendingCriticalVersion.changeSummary),
          workingPackage: structuredClone(detail.pendingCriticalVersion.workingPackage),
          conflictDates: [...detail.pendingCriticalVersion.conflictDates],
        }
      : null,
    versions: detail.versions.map((version) => ({
      ...version,
      changeSummary: structuredClone(version.changeSummary),
      workingPackage: structuredClone(version.workingPackage),
    })),
  };
}

function versionAckKey(assignmentId: string, versionNumber: number): string {
  return `${assignmentId}:${versionNumber}`;
}

function partitionGuideOperatorLists(
  details: Record<string, GuideOperatorAssignmentDetail>,
  asOfDate: string,
): GuideOperatorAssignmentLists {
  const awaiting: GuideOperatorAssignment[] = [];
  const upcoming: GuideOperatorAssignment[] = [];
  const inProgress: GuideOperatorAssignment[] = [];
  const completed: GuideOperatorAssignment[] = [];
  const cancelled: GuideOperatorAssignment[] = [];

  for (const detail of Object.values(details)) {
    const row = cloneGuideOperatorAssignment(detail.assignment);
    if (row.status === 'offered') {
      awaiting.push(row);
      continue;
    }
    if (row.status === 'cancelled') {
      cancelled.push(row);
      continue;
    }
    if (row.status !== 'accepted') continue;
    if (row.startDate > asOfDate) upcoming.push(row);
    else if (row.endDate < asOfDate) completed.push(row);
    else inProgress.push(row);
  }

  const byStart = (a: GuideOperatorAssignment, b: GuideOperatorAssignment) =>
    a.startDate.localeCompare(b.startDate) || a.id.localeCompare(b.id);
  awaiting.sort(byStart);
  upcoming.sort(byStart);
  inProgress.sort(byStart);
  completed.sort(
    (a, b) =>
      b.endDate.localeCompare(a.endDate) ||
      b.startDate.localeCompare(a.startDate) ||
      b.id.localeCompare(a.id),
  );
  cancelled.sort(
    (a, b) =>
      (b.cancelledAt || '').localeCompare(a.cancelledAt || '') ||
      b.id.localeCompare(a.id),
  );

  return { asOfDate, awaiting, upcoming, inProgress, completed, cancelled };
}

function tourFromForm(form: TourFormValues): Omit<CalendarEntry, 'id'> {
  return {
    type: 'tour',
    title: form.title.trim(),
    company: form.company,
    location: form.location,
    startDate: form.startDate,
    endDate: form.endDate || form.startDate,
    startTime: form.useTime ? form.startTime : null,
    endTime: form.useTime ? form.endTime : null,
    status: form.status,
    payment: form.payment,
    income: form.income,
    note: form.note,
    source: 'Mini App',
  };
}

function nextPlaceId(): string {
  const hex = nextPlaceSeq.toString(16).padStart(32, 'c');
  nextPlaceSeq += 1;
  return `place_${hex}`;
}

function nextCommissionId(): string {
  const hex = nextCommissionSeq.toString(16).padStart(32, 'e');
  nextCommissionSeq += 1;
  return `entry_${hex}`;
}

function mockLocalBusinessDate(occurredAt: string): string | null {
  try {
    return occurredAtToBusinessDate(occurredAt);
  } catch {
    return null;
  }
}

function calcCommissionReportsSummary(
  params: CommissionReportsSummaryParams,
): CommissionReportsSummary {
  if (typeof params.from !== 'string' || typeof params.to !== 'string') {
    throw new Error('Invalid commission reports range');
  }
  if (params.from > params.to) {
    throw new Error('Invalid commission reports range');
  }

  const placeNames = new Map(personalPlaces.map((place) => [place.id, place.name]));
  const grouped = new Map<string, CommissionReportsCompanySummary>();
  let totalCommission = 0;
  let recordCount = 0;

  for (const sale of personalCommissions) {
    if (sale.status !== 'active') continue;
    const points = sale.receivedPoints;
    if (typeof points !== 'number' || !Number.isInteger(points) || points <= 0) continue;
    const localDay = mockLocalBusinessDate(sale.occurredAt);
    if (localDay == null || localDay < params.from || localDay > params.to) continue;

    let row = grouped.get(sale.placeId);
    if (!row) {
      row = {
        placeId: sale.placeId,
        companyName: placeNames.get(sale.placeId) ?? UNRESOLVED_COMPANY_NAME,
        totalCommission: 0,
        recordCount: 0,
      };
      grouped.set(sale.placeId, row);
    }
    row.totalCommission += points;
    row.recordCount += 1;
    totalCommission += points;
    recordCount += 1;
  }

  const byCompany = [...grouped.values()]
    .map((row) => ({ ...row }))
    .sort((a, b) => {
      if (a.totalCommission !== b.totalCommission) {
        return b.totalCommission - a.totalCommission;
      }
      const nameCmp = a.companyName.toLocaleLowerCase().localeCompare(
        b.companyName.toLocaleLowerCase(),
      );
      if (nameCmp !== 0) return nameCmp;
      return a.placeId.localeCompare(b.placeId);
    });

  return {
    totalCommission,
    recordCount,
    byCompany,
    period: { from: params.from, to: params.to },
  };
}

export const mockClient: GuideOsClient = {
  async listEntries() {
    return entries.map((e) => ({ ...e }));
  },

  async getEntry(id: string) {
    const entry = entries.find((e) => e.id === id);
    return entry ? { ...entry } : null;
  },

  async createTour(form: TourFormValues, _options?: WriteOptions) {
    const entry: CalendarEntry = { ...tourFromForm(form), id: `t${nextId++}` };
    entries.push(entry);
    return { ...entry };
  },

  async updateTour(id: string, form: TourFormValues, _options?: WriteOptions) {
    const idx = entries.findIndex((e) => e.id === id);
    if (idx < 0) throw new Error('Tour not found');
    entries[idx] = { ...entries[idx], ...tourFromForm(form), id };
    return { ...entries[idx] };
  },

  async createDayOff(form: DayOffFormValues, _options?: WriteOptions) {
    const entry: CalendarEntry = {
      id: `d${nextId++}`,
      type: 'day_off',
      title: 'Выходной',
      startDate: form.startDate,
      endDate: form.endDate,
      startTime: null,
      endTime: null,
      income: 0,
      source: 'Mini App',
    };
    entries.push(entry);
    return { ...entry };
  },

  async deleteEntry(id: string) {
    const idx = entries.findIndex((e) => e.id === id);
    if (idx >= 0) entries.splice(idx, 1);
  },

  async updateDayLocations(id: string, locations: Record<string, string>) {
    const entry = entries.find((e) => e.id === id);
    if (!entry) throw new Error('Tour not found');
    entry.dayLocations = { ...locations };
    return { ...entry };
  },

  async getProfile() {
    return cloneProfile(profile);
  },

  async updateProfile(patch: GuideProfilePatch) {
    if (patch.name !== undefined) profile.name = patch.name;
    if (patch.types !== undefined) {
      profile.types = patch.types.map((t) => ({
        type: t.type,
        label: MOCK_GUIDE_TYPE_LABELS[t.type],
        geo: [...t.geo],
        allUzbekistan: t.allUzbekistan,
      }));
    }
    if (patch.languages !== undefined) profile.languages = [...patch.languages];
    if (patch.notifications !== undefined) {
      profile.notifications = { ...profile.notifications, ...patch.notifications };
    }
    return mockClient.getProfile();
  },

  async getReportsSummary(params: ReportsSummaryParams) {
    const summary = calcSummary(entries, { from: params.from, to: params.to }, {
      status: params.status,
      payment: params.payment,
      company: params.company ?? '',
      location: params.location ?? '',
    });
    return {
      ...summary,
      period: { from: params.from, to: params.to },
    };
  },

  async getCommissionReportsSummary(params: CommissionReportsSummaryParams) {
    return calcCommissionReportsSummary(params);
  },

  async previewAvailability(params: AvailabilityPreviewParams) {
    return buildAvailabilityPreview(entries, params.from, params.to);
  },

  async listPersonalPlaces(options?: ListPersonalPlacesOptions) {
    const includeInactive = options?.includeInactive === true;
    return personalPlaces
      .filter((place) => includeInactive || place.status === 'active')
      .map(clonePlace);
  },

  async getPersonalPlace(id: string) {
    const place = personalPlaces.find((item) => item.id === id);
    return place ? clonePlace(place) : null;
  },

  async createPersonalPlace(input: PersonalPlaceInput) {
    const now = utcNow();
    const place: PersonalPlace = {
      id: nextPlaceId(),
      name: input.name,
      category: input.category,
      generalLocation: input.generalLocation,
      landmark: input.landmark,
      note: input.note,
      status: 'active',
      createdAt: now,
      updatedAt: now,
    };
    personalPlaces.push(place);
    return clonePlace(place);
  },

  async updatePersonalPlace(id: string, input: PersonalPlaceInput) {
    const idx = personalPlaces.findIndex((item) => item.id === id && item.status === 'active');
    if (idx < 0) throw new Error('Personal place not found');
    personalPlaces[idx] = {
      ...personalPlaces[idx],
      name: input.name,
      category: input.category,
      generalLocation: input.generalLocation,
      landmark: input.landmark,
      note: input.note,
      updatedAt: utcNow(),
    };
    return clonePlace(personalPlaces[idx]);
  },

  async deactivatePersonalPlace(id: string) {
    const place = personalPlaces.find((item) => item.id === id && item.status === 'active');
    if (!place) throw new Error('Personal place not found');
    place.status = 'inactive';
    place.updatedAt = utcNow();
  },

  async listPersonalCommissions(placeId: string, options?: ListPersonalCommissionsOptions) {
    const includeInactive = options?.includeInactive === true;
    return personalCommissions
      .filter((item) => item.placeId === placeId)
      .filter((item) => includeInactive || item.status === 'active')
      .map(cloneCommission);
  },

  async getPersonalCommission(id: string) {
    const item = personalCommissions.find((entry) => entry.id === id);
    return item ? cloneCommission(item) : null;
  },

  async createPersonalCommission(placeId: string, input: PersonalCommissionInput) {
    const parent = personalPlaces.find((place) => place.id === placeId && place.status === 'active');
    if (!parent) throw new Error('Personal place not found');
    const now = utcNow();
    const created: PersonalCommission = {
      id: nextCommissionId(),
      placeId,
      occurredAt: input.occurredAt,
      purchaseAmountMinor: input.purchaseAmountMinor,
      receivedIncomeMinor: input.receivedIncomeMinor,
      receivedPoints: input.receivedPoints,
      currency: input.currency,
      note: input.note,
      status: 'active',
      createdAt: now,
      updatedAt: now,
    };
    personalCommissions.push(created);
    return cloneCommission(created);
  },

  async updatePersonalCommission(id: string, input: PersonalCommissionInput) {
    const idx = personalCommissions.findIndex(
      (item) => item.id === id && item.status === 'active',
    );
    if (idx < 0) throw new Error('Personal commission not found');
    personalCommissions[idx] = {
      ...personalCommissions[idx],
      occurredAt: input.occurredAt,
      purchaseAmountMinor: input.purchaseAmountMinor,
      receivedIncomeMinor: input.receivedIncomeMinor,
      receivedPoints: input.receivedPoints,
      currency: input.currency,
      note: input.note,
      updatedAt: utcNow(),
    };
    return cloneCommission(personalCommissions[idx]);
  },

  async deactivatePersonalCommission(id: string) {
    const item = personalCommissions.find((entry) => entry.id === id && entry.status === 'active');
    if (!item) throw new Error('Personal commission not found');
    item.status = 'inactive';
    item.updatedAt = utcNow();
  },

  async listOfficialCompanies(_options?: GuideShopReadOptions) {
    void _options;
    return {
      companies: officialCompanies.map(cloneOfficialCompany),
      page: { nextCursor: null },
    };
  },

  async getOfficialCompany(id: string, _options?: GuideShopReadOptions) {
    void _options;
    const company = officialCompanies.find((item) => item.id === id);
    return company ? cloneOfficialCompany(company) : null;
  },

  async listOfficialVisits(options?: ListOfficialVisitsOptions) {
    void options;
    return {
      visits: officialVisits.map(cloneOfficialVisit),
      page: { nextCursor: null },
    };
  },

  async getOfficialVisit(id: string, _options?: GuideShopReadOptions) {
    void _options;
    const visit = officialVisits.find((item) => item.id === id);
    if (!visit) return null;
    const points = INITIAL_OFFICIAL_VISIT_POINTS[id] ?? [];
    return {
      ...cloneOfficialVisit(visit),
      points: points.map((point) => ({ ...point })),
    };
  },

  async getOfficialPointsSummary(_options?: GuideShopReadOptions) {
    void _options;
    return cloneOfficialPointsSummary(officialPointsSummary);
  },

  async listOfficialHistory(options?: ListOfficialHistoryOptions) {
    void options;
    return {
      history: officialHistory.map(cloneOfficialHistoryItem),
      page: { nextCursor: null },
    };
  },

  async listPendingGuideOperatorAssignments() {
    return guideOperatorOffers
      .filter((row) => row.status === 'offered')
      .map(cloneGuideOperatorAssignment);
  },

  async listGuideOperatorAssignmentLists() {
    return partitionGuideOperatorLists(guideOperatorDetails, MOCK_TODAY);
  },

  async getGuideOperatorAssignment(id: string) {
    const detail = guideOperatorDetails[id];
    if (!detail) return null;
    return cloneGuideOperatorDetail(detail);
  },

  async acceptGuideOperatorAssignment(
    id: string,
    input: GuideOperatorDecisionInput,
  ): Promise<GuideOperatorDecisionResult> {
    const existing = guideOperatorDecisions.get(input.decisionEventId);
    if (existing) {
      if (existing.assignmentId !== id || existing.decision !== 'accept') {
        throw new ApiError('idempotency_conflict', 'Конфликт идемпотентности запроса.', 409);
      }
      return { ...existing, replayed: true };
    }

    const detail = guideOperatorDetails[id];
    if (!detail || detail.assignment.status !== 'offered') {
      throw new ApiError('not_found', 'Назначение не найдено.', 404);
    }
    if (detail.conflictDates.length > 0) {
      throw new ApiError(
        'calendar_conflict',
        'Назначение пересекается с занятыми датами в календаре.',
        409,
      );
    }

    const decidedAt = utcNow();
    const projectionTourId = String(nextId++);
    const publishedAt = detail.assignment.offeredAt;
    const sourceEventId = `evt_initial_${id}`;
    const v1Package = structuredClone(detail.workingPackage);
    const updated: GuideOperatorAssignment = {
      ...detail.assignment,
      status: 'accepted',
      projectionTourId,
      decidedAt,
      activeVersionNumber: 1,
      activeVersionUnread: false,
  pendingCriticalVersionNumber: null,
    };
    detail.assignment = updated;
    detail.activeVersion = {
      versionNumber: 1,
      severity: 'initial',
      publishedAt,
      changeSummary: [],
      unread: false,
      sourceEventId,
    };
    detail.pendingCriticalVersion = null;
    detail.versions = [
      {
        versionNumber: 1,
        severity: 'initial',
        publishedAt,
        changeSummary: [],
        workingPackage: structuredClone(v1Package),
        sourceEventId,
      },
    ];
    detail.workingPackage = structuredClone(v1Package);
    guideOperatorOffers = guideOperatorOffers.filter((row) => row.id !== id);

    const pkg = detail.workingPackage as Record<string, unknown>;
    const tour = (pkg.tour ?? {}) as Record<string, unknown>;
    const dayRows = Array.isArray(pkg.days) ? pkg.days : [];
    const dayLocations: Record<string, string> = {};
    for (const raw of dayRows) {
      if (!raw || typeof raw !== 'object') continue;
      const day = raw as Record<string, unknown>;
      const date = typeof day.date === 'string' ? day.date : null;
      const city =
        typeof day.city_or_route === 'string'
          ? day.city_or_route
          : typeof day.cityOrRoute === 'string'
            ? day.cityOrRoute
            : null;
      if (date && city) dayLocations[date] = city;
    }
    entries.push({
      id: projectionTourId,
      type: 'tour',
      title:
        (typeof tour.title === 'string' && tour.title) ||
        detail.assignment.companyName,
      company: detail.assignment.companyName,
      location:
        (typeof tour.city_or_route === 'string' && tour.city_or_route) ||
        (typeof tour.cityOrRoute === 'string' && tour.cityOrRoute) ||
        '',
      startDate: detail.assignment.startDate,
      endDate: detail.assignment.endDate,
      startTime: null,
      endTime: null,
      status: 'confirmed',
      payment: null,
      income: null,
      source: 'Guide Operator',
      guideOperatorAssignmentId: id,
      guideOperatorVersion: detail.assignment.activeVersionNumber,
      guideOperatorVersionUnread: false,
      guideOperatorPendingCritical: false,
      dayLocations: Object.keys(dayLocations).length ? dayLocations : undefined,
    });

    const result: GuideOperatorDecisionResult = {
      assignmentId: id,
      status: 'accepted',
      decision: 'accept',
      decisionEventId: input.decisionEventId,
      projectionTourId,
      replayed: false,
    };
    guideOperatorDecisions.set(input.decisionEventId, result);
    return { ...result };
  },

  async declineGuideOperatorAssignment(
    id: string,
    input: GuideOperatorDecisionInput,
  ): Promise<GuideOperatorDecisionResult> {
    const existing = guideOperatorDecisions.get(input.decisionEventId);
    if (existing) {
      if (existing.assignmentId !== id || existing.decision !== 'decline') {
        throw new ApiError('idempotency_conflict', 'Конфликт идемпотентности запроса.', 409);
      }
      return { ...existing, replayed: true };
    }

    const detail = guideOperatorDetails[id];
    if (!detail || detail.assignment.status !== 'offered') {
      throw new ApiError('not_found', 'Назначение не найдено.', 404);
    }

    const decidedAt = utcNow();
    detail.assignment = {
      ...detail.assignment,
      status: 'declined',
      projectionTourId: null,
      decidedAt,
      activeVersionUnread: false,
  pendingCriticalVersionNumber: null,
    };
    guideOperatorOffers = guideOperatorOffers.filter((row) => row.id !== id);
    const result: GuideOperatorDecisionResult = {
      assignmentId: id,
      status: 'declined',
      decision: 'decline',
      decisionEventId: input.decisionEventId,
      projectionTourId: null,
      replayed: false,
    };
    guideOperatorDecisions.set(input.decisionEventId, result);
    return { ...result };
  },

  async acknowledgeGuideOperatorVersion(
    id: string,
    input: GuideOperatorVersionAcknowledgeInput,
  ): Promise<GuideOperatorVersionAcknowledgeResult> {
    const existingByEvent = guideOperatorVersionAcks.get(input.decisionEventId);
    if (existingByEvent) {
      if (
        existingByEvent.assignmentId !== id ||
        existingByEvent.versionNumber !== input.versionNumber
      ) {
        throw new ApiError('idempotency_conflict', 'Конфликт идемпотентности запроса.', 409);
      }
      return { ...existingByEvent, replayed: true };
    }

    const existingByVersion = guideOperatorVersionAcksByAssignmentVersion.get(
      versionAckKey(id, input.versionNumber),
    );
    if (existingByVersion) {
      return { ...existingByVersion, replayed: true };
    }

    const detail = guideOperatorDetails[id];
    if (!detail) {
      throw new ApiError('not_found', 'Назначение не найдено.', 404);
    }
    if (detail.assignment.status === 'cancelled') {
      throw new ApiError(
        'assignment_not_actionable',
        'Отменённые назначения нельзя подтвердить как прочитанные.',
        409,
      );
    }
    if (detail.assignment.status !== 'accepted') {
      throw new ApiError(
        'assignment_not_actionable',
        'Подтвердить можно только принятое назначение.',
        409,
      );
    }
    if (detail.assignment.activeVersionNumber !== input.versionNumber) {
      throw new ApiError(
        'conflict',
        'Номер версии не совпадает с активной версией назначения.',
        409,
      );
    }
    const versionRow = detail.versions.find((row) => row.versionNumber === input.versionNumber);
    if (!versionRow) {
      throw new ApiError('not_found', 'Версия назначения не найдена.', 404);
    }
    if (versionRow.severity === 'critical') {
      throw new ApiError(
        'assignment_not_actionable',
        'Критические версии нельзя подтвердить как обычное прочтение.',
        409,
      );
    }
    if (versionRow.severity !== 'ordinary') {
      throw new ApiError(
        'assignment_not_actionable',
        'Подтвердить можно только обычную активную версию.',
        409,
      );
    }
    if (!detail.assignment.activeVersionUnread || !detail.activeVersion.unread) {
      throw new ApiError(
        'assignment_not_actionable',
        'Нет непрочитанных обычных изменений для подтверждения.',
        409,
      );
    }

    detail.assignment = {
      ...detail.assignment,
      activeVersionUnread: false,
    };
    detail.activeVersion = {
      ...detail.activeVersion,
      unread: false,
    };
    for (const entry of entries) {
      if (entry.guideOperatorAssignmentId === id) {
        entry.guideOperatorVersionUnread = false;
      }
    }

    const result: GuideOperatorVersionAcknowledgeResult = {
      assignmentId: id,
      versionNumber: input.versionNumber,
      decisionEventId: input.decisionEventId,
      unread: false,
      replayed: false,
    };
    guideOperatorVersionAcks.set(input.decisionEventId, result);
    guideOperatorVersionAcksByAssignmentVersion.set(
      versionAckKey(id, input.versionNumber),
      result,
    );
    return { ...result };
  },

  async confirmGuideOperatorCriticalVersion(
    id: string,
    input: GuideOperatorCriticalDecisionInput,
  ): Promise<GuideOperatorCriticalDecisionResult> {
    return decideMockCritical(id, input, 'confirm_critical');
  },

  async rejectGuideOperatorCriticalVersion(
    id: string,
    input: GuideOperatorCriticalDecisionInput,
  ): Promise<GuideOperatorCriticalDecisionResult> {
    return decideMockCritical(id, input, 'reject_critical');
  },

  async listGuideOperatorConnections() {
    return guideOperatorConnections.map((row) => ({ ...row }));
  },

  async confirmGuideOperatorConnection(
    id: string,
    input: GuideOperatorConnectionDecisionInput,
  ): Promise<GuideOperatorConnectionDecisionResult> {
    return decideMockConnection(id, input, 'confirm');
  },

  async declineGuideOperatorConnection(
    id: string,
    input: GuideOperatorConnectionDecisionInput,
  ): Promise<GuideOperatorConnectionDecisionResult> {
    return decideMockConnection(id, input, 'decline');
  },
};

function decideMockConnection(
  id: string,
  input: GuideOperatorConnectionDecisionInput,
  decision: 'confirm' | 'decline',
): GuideOperatorConnectionDecisionResult {
  const existing = guideOperatorConnectionDecisions.get(input.decisionEventId);
  if (existing) {
    if (existing.connectionId !== id || existing.decision !== decision) {
      throw new ApiError('idempotency_conflict', 'Конфликт идемпотентности запроса.', 409);
    }
    return { ...existing, replayed: true };
  }

  const index = guideOperatorConnections.findIndex((row) => row.id === id);
  if (index < 0) {
    throw new ApiError('not_found', 'Подключение не найдено.', 404);
  }
  const connection = guideOperatorConnections[index];
  if (!connection.actionable || connection.status !== 'invited' || connection.expired) {
    throw new ApiError(
      'connection_not_actionable',
      connection.expired
        ? 'Срок приглашения истёк.'
        : 'Приглашение больше недоступно для ответа.',
      409,
    );
  }

  const decidedAt = utcNow();
  const status = decision === 'confirm' ? 'confirmed' : 'declined';
  const updated: GuideOperatorConnection = {
    ...connection,
    status,
    decidedAt,
    expired: false,
    actionable: false,
  };
  guideOperatorConnections[index] = updated;
  const result: GuideOperatorConnectionDecisionResult = {
    connectionId: id,
    status,
    decision,
    decisionEventId: input.decisionEventId,
    replayed: false,
  };
  guideOperatorConnectionDecisions.set(input.decisionEventId, result);
  return { ...result };
}

function decideMockCritical(
  id: string,
  input: GuideOperatorCriticalDecisionInput,
  decision: 'confirm_critical' | 'reject_critical',
): GuideOperatorCriticalDecisionResult {
  const existingByEvent = guideOperatorCriticalDecisions.get(input.decisionEventId);
  if (existingByEvent) {
    if (
      existingByEvent.assignmentId !== id ||
      existingByEvent.versionNumber !== input.versionNumber ||
      existingByEvent.decision !== decision
    ) {
      throw new ApiError('idempotency_conflict', 'Конфликт идемпотентности запроса.', 409);
    }
    return { ...existingByEvent, replayed: true };
  }
  const existingByVersion = guideOperatorCriticalDecisionsByAssignmentVersion.get(
    versionAckKey(id, input.versionNumber),
  );
  if (existingByVersion) {
    if (existingByVersion.decision !== decision) {
      throw new ApiError('idempotency_conflict', 'Конфликт идемпотентности запроса.', 409);
    }
    return { ...existingByVersion, replayed: true };
  }

  const detail = guideOperatorDetails[id];
  if (!detail) {
    throw new ApiError('not_found', 'Назначение не найдено.', 404);
  }
  if (detail.assignment.status === 'cancelled') {
    throw new ApiError(
      'assignment_not_actionable',
      'Критическая версия больше недоступна для решения.',
      409,
    );
  }
  if (detail.assignment.status !== 'accepted' || !detail.pendingCriticalVersion) {
    throw new ApiError(
      'assignment_not_actionable',
      'Критическая версия больше недоступна для решения.',
      409,
    );
  }
  if (
    detail.assignment.pendingCriticalVersionNumber !== input.versionNumber ||
    detail.pendingCriticalVersion.versionNumber !== input.versionNumber
  ) {
    throw new ApiError(
      'idempotency_conflict',
      'Конфликт идемпотентности запроса.',
      409,
    );
  }

  if (decision === 'confirm_critical') {
    if (detail.pendingCriticalVersion.conflictDates.length > 0) {
      throw new ApiError(
        'calendar_conflict',
        'Новые даты пересекаются с занятыми датами в календаре.',
        409,
      );
    }
    const pending = detail.pendingCriticalVersion;
    const pkg = pending.workingPackage as Record<string, unknown>;
    const assignmentPart = (pkg.assignment ?? {}) as Record<string, unknown>;
    const tourPart = (pkg.tour ?? {}) as Record<string, unknown>;
    const startDate =
      typeof assignmentPart.start_date === 'string'
        ? assignmentPart.start_date
        : detail.assignment.startDate;
    const endDate =
      typeof assignmentPart.end_date === 'string'
        ? assignmentPart.end_date
        : detail.assignment.endDate;
    const role =
      typeof assignmentPart.role === 'string' ? assignmentPart.role : detail.assignment.role;
    const title =
      (typeof tourPart.title === 'string' && tourPart.title) || detail.assignment.companyName;
    const city =
      (typeof tourPart.city_or_route === 'string' && tourPart.city_or_route) ||
      (typeof tourPart.cityOrRoute === 'string' && tourPart.cityOrRoute) ||
      '';

    detail.assignment = {
      ...detail.assignment,
      startDate,
      endDate,
      role,
      activeVersionNumber: pending.versionNumber,
      pendingCriticalVersionNumber: null,
      activeVersionUnread: false,
    };
    detail.workingPackage = structuredClone(pending.workingPackage);
    detail.activeVersion = {
      versionNumber: pending.versionNumber,
      severity: 'critical',
      publishedAt: pending.publishedAt,
      changeSummary: structuredClone(pending.changeSummary),
      unread: false,
      sourceEventId: pending.sourceEventId,
    };
    detail.pendingCriticalVersion = null;

    for (const entry of entries) {
      if (entry.guideOperatorAssignmentId === id) {
        entry.startDate = startDate;
        entry.endDate = endDate;
        entry.title = title;
        entry.location = city;
        entry.guideOperatorVersion = pending.versionNumber;
        entry.guideOperatorVersionUnread = false;
        entry.guideOperatorPendingCritical = false;
      }
    }
  } else {
    detail.assignment = {
      ...detail.assignment,
      pendingCriticalVersionNumber: null,
    };
    detail.pendingCriticalVersion = null;
    for (const entry of entries) {
      if (entry.guideOperatorAssignmentId === id) {
        entry.guideOperatorPendingCritical = false;
      }
    }
  }

  const result: GuideOperatorCriticalDecisionResult = {
    assignmentId: id,
    status: detail.assignment.status,
    decision,
    versionNumber: input.versionNumber,
    decisionEventId: input.decisionEventId,
    pendingCriticalVersionNumber: null,
    activeVersionNumber: detail.assignment.activeVersionNumber,
    projectionTourId: detail.assignment.projectionTourId,
    replayed: false,
  };
  guideOperatorCriticalDecisions.set(input.decisionEventId, result);
  guideOperatorCriticalDecisionsByAssignmentVersion.set(
    versionAckKey(id, input.versionNumber),
    result,
  );
  return { ...result };
}

/** Test-only access to in-memory entries */
export function __testEntries(): CalendarEntry[] {
  return entries;
}

/** Test-only access to in-memory personal places */
export function __testPersonalPlaces(): PersonalPlace[] {
  return personalPlaces;
}

/** Test-only access to in-memory personal commissions */
export function __testPersonalCommissions(): PersonalCommission[] {
  return personalCommissions;
}

/** Test-only access to in-memory official companies */
export function __testOfficialCompanies(): OfficialCompany[] {
  return officialCompanies;
}

/** Test-only access to in-memory official visits */
export function __testOfficialVisits(): OfficialVisit[] {
  return officialVisits;
}

/** Test-only access to in-memory official points summary */
export function __testOfficialPointsSummary(): OfficialPointsSummary {
  return officialPointsSummary;
}

/** Test-only access to in-memory official payout history */
export function __testOfficialHistory(): OfficialHistoryItem[] {
  return officialHistory;
}

export function __resetMockStore() {
  entries.length = 0;
  entries.push(...INITIAL_ENTRIES.map((e) => ({ ...e })));
  nextId = 10;
  nextPlaceSeq = 12;
  nextCommissionSeq = 20;
  profile = cloneProfile(MOCK_PROFILE);
  personalPlaces = INITIAL_PERSONAL_PLACES.map(clonePlace);
  personalCommissions = INITIAL_PERSONAL_COMMISSIONS.map(cloneCommission);
  officialCompanies = INITIAL_OFFICIAL_COMPANIES.map(cloneOfficialCompany);
  officialVisits = INITIAL_OFFICIAL_VISITS.map(cloneOfficialVisit);
  officialPointsSummary = cloneOfficialPointsSummary(INITIAL_OFFICIAL_POINTS_SUMMARY);
  officialHistory = INITIAL_OFFICIAL_HISTORY.map(cloneOfficialHistoryItem);
  guideOperatorOffers = INITIAL_GUIDE_OPERATOR_OFFERS.map(cloneGuideOperatorAssignment);
  guideOperatorConnections = INITIAL_GUIDE_OPERATOR_CONNECTIONS.map((row) => ({ ...row }));
  guideOperatorDetails = Object.fromEntries(
    Object.entries(INITIAL_GUIDE_OPERATOR_DETAILS).map(([id, detail]) => [
      id,
      cloneGuideOperatorDetail(detail),
    ]),
  );
  guideOperatorDecisions.clear();
  guideOperatorConnectionDecisions.clear();
  guideOperatorCriticalDecisions.clear();
  guideOperatorCriticalDecisionsByAssignmentVersion.clear();
  guideOperatorVersionAcks.clear();
  guideOperatorVersionAcksByAssignmentVersion.clear();
}

// @ts-nocheck — read CSS source at runtime; Node built-ins are not in app tsconfig.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { PersonalCommission, PersonalPlace } from '@/api/types';
import { guideOsClient } from '@/api/createClient';
import {
  mockClient,
  __resetMockStore,
  __testPersonalCommissions,
} from '@/api/mock/store';
import { MOCK_TODAY } from '@/config';
import { GuideShopPage } from '@/features/guideshop/GuideShopPage';
import {
  businessDateToOccurredAt,
  formatMinorUnits,
  formatMoneyAmount,
  occurredAtToBusinessDate,
  parseMoneyToMinor,
  summarizeActiveCommissions,
} from '@/features/guideshop/lib/commissionMoney';
import { t } from '@/i18n/strings';

const GLOBAL_CSS = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../src/styles/global.css'),
  'utf8',
);

const placeA: PersonalPlace = {
  id: 'place_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  name: 'Бухара Арт',
  category: 'Магазин',
  generalLocation: 'Бухара',
  landmark: 'Рядом с Ляби-Хауз',
  note: 'Секретная заметка',
  status: 'active',
  createdAt: '2026-08-01T10:00:00Z',
  updatedAt: '2026-08-01T10:00:00Z',
};

const usdCommission: PersonalCommission = {
  id: 'entry_11111111111111111111111111111111',
  placeId: placeA.id,
  occurredAt: '2026-08-10T05:00:00Z',
  purchaseAmountMinor: 20000,
  receivedIncomeMinor: 12500,
  receivedPoints: null,
  currency: 'USD',
  note: 'USD комиссия',
  status: 'active',
  createdAt: '2026-08-10T06:00:00Z',
  updatedAt: '2026-08-10T06:00:00Z',
};

const uzsCommission: PersonalCommission = {
  id: 'entry_22222222222222222222222222222222',
  placeId: placeA.id,
  occurredAt: '2026-08-12T05:00:00Z',
  purchaseAmountMinor: 100000000,
  receivedIncomeMinor: 50000000,
  receivedPoints: null,
  currency: 'UZS',
  note: 'UZS комиссия',
  status: 'active',
  createdAt: '2026-08-12T06:00:00Z',
  updatedAt: '2026-08-12T06:00:00Z',
};

const pointsCommission: PersonalCommission = {
  id: 'entry_33333333333333333333333333333333',
  placeId: placeA.id,
  occurredAt: '2026-08-14T05:00:00Z',
  purchaseAmountMinor: null,
  receivedIncomeMinor: null,
  receivedPoints: 25,
  currency: null,
  note: 'Только баллы',
  status: 'active',
  createdAt: '2026-08-14T06:00:00Z',
  updatedAt: '2026-08-14T06:00:00Z',
};

const inactiveCommission: PersonalCommission = {
  id: 'entry_44444444444444444444444444444444',
  placeId: placeA.id,
  occurredAt: '2026-08-05T05:00:00Z',
  purchaseAmountMinor: null,
  receivedIncomeMinor: 99900,
  receivedPoints: 99,
  currency: 'USD',
  note: 'Неактивная запись',
  status: 'inactive',
  createdAt: '2026-08-05T06:00:00Z',
  updatedAt: '2026-08-05T07:00:00Z',
};

function renderPage() {
  return render(<GuideShopPage />);
}

async function waitForPlacesLoaded() {
  await waitFor(() => {
    expect(screen.queryByText(t.guideShopLoading)).not.toBeInTheDocument();
  });
}

async function openCompany(place: PersonalPlace = placeA) {
  fireEvent.click(screen.getByRole('button', { name: t.guideShopOpenCompany(place.name) }));
}

async function waitForCommissionsLoaded() {
  await waitFor(() => {
    expect(screen.queryByText(t.guideShopCommissionsLoading)).not.toBeInTheDocument();
  });
}

describe('GuideShop personal commissions UI', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    __resetMockStore();
  });

  afterEach(() => {
    cleanup();
  });

  it('loads commissions only when company detail opens', async () => {
    const listSpy = vi.spyOn(guideOsClient, 'listPersonalCommissions');
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    renderPage();
    await waitForPlacesLoaded();
    expect(listSpy).not.toHaveBeenCalled();
    await openCompany();
    await waitFor(() => expect(listSpy).toHaveBeenCalledTimes(1));
    expect(listSpy).toHaveBeenCalledWith(placeA.id);
  });

  it('shows pending commission status inside company detail', async () => {
    let resolveList: ((value: PersonalCommission[]) => void) | undefined;
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveList = resolve;
        }),
    );
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    expect(screen.getAllByText(placeA.name).length).toBeGreaterThan(0);
    expect(screen.getByRole('status')).toHaveTextContent(t.guideShopCommissionsLoading);
    resolveList?.([]);
    await waitForCommissionsLoaded();
  });

  it('keeps commission load error local and preserves company metadata', async () => {
    const listSpy = vi
      .spyOn(guideOsClient, 'listPersonalCommissions')
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValueOnce([]);
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(t.guideShopCommissionsLoadError),
    );
    expect(screen.getAllByText(placeA.name).length).toBeGreaterThan(0);
    expect(screen.getByText('Секретная заметка')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.guideShopAddCommission })).toBeInTheDocument();
    expect(screen.queryByText(t.guideShopLoadError)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: t.retry }));
    await waitFor(() => expect(listSpy).toHaveBeenCalledTimes(2));
  });

  it('summarizes received income by currency and points separately', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([
      usdCommission,
      uzsCommission,
      pointsCommission,
      inactiveCommission,
    ]);
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    expect(screen.getByText('USD 125.00')).toBeInTheDocument();
    expect(screen.getByText('UZS 500000.00')).toBeInTheDocument();
    expect(screen.getByText(t.guideShopCommissionsPoints(25))).toBeInTheDocument();
    expect(screen.queryByText('USD 999.00')).not.toBeInTheDocument();
    expect(screen.queryByText(/Баллы: 99/)).not.toBeInTheDocument();
    expect(screen.queryByText('USD 200.00')).not.toBeInTheDocument();
  });

  it('shows empty summary when no income or points', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([
      {
        ...usdCommission,
        receivedIncomeMinor: null,
        receivedPoints: null,
        purchaseAmountMinor: 1000,
      },
    ]);
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    expect(screen.getByText(t.guideShopCommissionsEmptySummary)).toBeInTheDocument();
  });

  it('sums large safe-integer income without precision loss', () => {
    const summary = summarizeActiveCommissions([
      {
        ...usdCommission,
        id: 'entry_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        receivedIncomeMinor: 9007199254740800,
      },
      {
        ...usdCommission,
        id: 'entry_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
        receivedIncomeMinor: 191,
      },
    ]);
    expect(summary.incomesByCurrency).toEqual([{ currency: 'USD', minor: 9007199254740991 }]);
  });

  it('renders active history newest first without internal ids', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([
      usdCommission,
      uzsCommission,
      pointsCommission,
      inactiveCommission,
    ]);
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    const rows = screen.getAllByRole('button', { name: /Открыть комиссию за/ });
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveAccessibleName('Открыть комиссию за 14.08.2026');
    expect(rows[1]).toHaveAccessibleName('Открыть комиссию за 12.08.2026');
    expect(rows[2]).toHaveAccessibleName('Открыть комиссию за 10.08.2026');
    expect(screen.queryByText(usdCommission.id)).not.toBeInTheDocument();
    expect(screen.queryByText(inactiveCommission.note!)).not.toBeInTheDocument();
    expect(screen.queryByText(/GuideShop points/i)).not.toBeInTheDocument();
  });

  it('opens commission detail and returns to the same company', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([pointsCommission]);
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    fireEvent.click(screen.getByRole('button', { name: 'Открыть комиссию за 14.08.2026' }));
    expect(screen.getByText(t.guideShopCommissionDetailTitle)).toBeInTheDocument();
    expect(screen.getByText('14.08.2026')).toBeInTheDocument();
    expect(screen.getByText('25')).toBeInTheDocument();
    expect(screen.getByText('Только баллы')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: t.guideShopBackToCompany }));
    expect(screen.getAllByText(placeA.name).length).toBeGreaterThan(0);
    expect(screen.getByText('Секретная заметка')).toBeInTheDocument();
    expect(screen.getByText(t.guideShopCommissionsTitle)).toBeInTheDocument();
  });

  it('defaults create date to Guide OS business date', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    fireEvent.click(screen.getByRole('button', { name: t.guideShopAddCommission }));
    expect(screen.getByLabelText(t.guideShopCommissionFieldDate)).toHaveValue(MOCK_TODAY);
  });

  it('creates points-only and money-only commissions with exact payload', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
    const createSpy = vi.spyOn(guideOsClient, 'createPersonalCommission').mockResolvedValue({
      ...pointsCommission,
      id: 'entry_cccccccccccccccccccccccccccccccc',
      receivedPoints: 7,
    });
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    fireEvent.click(screen.getByRole('button', { name: t.guideShopAddCommission }));
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldPoints), {
      target: { value: '7' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    await waitFor(() => expect(createSpy).toHaveBeenCalledTimes(1));
    expect(createSpy.mock.calls[0]?.[1]).toEqual({
      occurredAt: businessDateToOccurredAt(MOCK_TODAY),
      purchaseAmountMinor: null,
      receivedIncomeMinor: null,
      receivedPoints: 7,
      currency: null,
      note: null,
    });

    createSpy.mockResolvedValueOnce({
      ...usdCommission,
      id: 'entry_dddddddddddddddddddddddddddddddd',
      purchaseAmountMinor: 1050,
      receivedIncomeMinor: null,
      receivedPoints: null,
      currency: 'USD',
    });
    fireEvent.click(screen.getByRole('button', { name: t.guideShopAddCommission }));
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldPurchase), {
      target: { value: '10,50' },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldCurrency), {
      target: { value: 'usd' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    await waitFor(() => expect(createSpy).toHaveBeenCalledTimes(2));
    expect(createSpy.mock.calls[1]?.[1]).toEqual({
      occurredAt: businessDateToOccurredAt(MOCK_TODAY),
      purchaseAmountMinor: 1050,
      receivedIncomeMinor: null,
      receivedPoints: null,
      currency: 'USD',
      note: null,
    });
  });

  it('parses dot and comma money identically and blocks duplicate submit', async () => {
    expect(parseMoneyToMinor('10.5')).toEqual({ ok: true, value: 1050 });
    expect(parseMoneyToMinor('10,50')).toEqual({ ok: true, value: 1050 });

    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
    let resolveCreate: ((value: PersonalCommission) => void) | undefined;
    const createSpy = vi.spyOn(guideOsClient, 'createPersonalCommission').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCreate = resolve;
        }),
    );
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    fireEvent.click(screen.getByRole('button', { name: t.guideShopAddCommission }));
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldIncome), {
      target: { value: '10.50' },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldCurrency), {
      target: { value: 'USD' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    fireEvent.click(screen.getByRole('button', { name: t.guideShopSaving }));
    expect(createSpy).toHaveBeenCalledTimes(1);
    resolveCreate?.({
      ...usdCommission,
      id: 'entry_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
      receivedIncomeMinor: 1050,
      purchaseAmountMinor: null,
      receivedPoints: null,
    });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: t.guideShopAddCommission })).toBeInTheDocument(),
    );
  });

  it('preserves draft on create rejection', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
    vi.spyOn(guideOsClient, 'createPersonalCommission').mockRejectedValue(new Error('fail'));
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    fireEvent.click(screen.getByRole('button', { name: t.guideShopAddCommission }));
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldPoints), {
      target: { value: '3' },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopFieldNote), {
      target: { value: 'draft note' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(t.guideShopCommissionSaveError),
    );
    expect(screen.getByLabelText(t.guideShopCommissionFieldPoints)).toHaveValue('3');
    expect(screen.getByLabelText(t.guideShopFieldNote)).toHaveValue('draft note');
  });

  it('blocks invalid validation cases before save', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
    const createSpy = vi.spyOn(guideOsClient, 'createPersonalCommission');
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    fireEvent.click(screen.getByRole('button', { name: t.guideShopAddCommission }));

    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(screen.getByText(t.guideShopCommissionValOutcomeRequired)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldPurchase), {
      target: { value: '1.234' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(screen.getByText(t.guideShopCommissionValMoneyInvalid)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldPurchase), {
      target: { value: '9007199254740992.00' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(screen.getByText(t.guideShopCommissionValMoneyInvalid)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldPurchase), {
      target: { value: '' },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldPoints), {
      target: { value: '0' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(screen.getByText(t.guideShopCommissionValPointsInvalid)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldPoints), {
      target: { value: '' },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldIncome), {
      target: { value: '10' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(screen.getByText(t.guideShopCommissionValCurrencyRequired)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldIncome), {
      target: { value: '' },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldPoints), {
      target: { value: '2' },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldCurrency), {
      target: { value: 'USD' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(screen.getByText(t.guideShopCommissionValCurrencyUnexpected)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldCurrency), {
      target: { value: 'US' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(screen.getByText(t.guideShopCommissionValCurrencyInvalid)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldCurrency), {
      target: { value: '' },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldDate), {
      target: { value: '2099-01-01' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(screen.getByText(t.guideShopCommissionValDateFuture)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldDate), {
      target: { value: MOCK_TODAY },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopFieldNote), {
      target: { value: 'x'.repeat(501) },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(screen.getByText(t.guideShopValNoteTooLong)).toBeInTheDocument();
    expect(createSpy).not.toHaveBeenCalled();
  });

  it('restores edit values without timezone day shift and sends full replacement', async () => {
    const boundary: PersonalCommission = {
      ...usdCommission,
      occurredAt: '2026-08-15T19:00:00Z',
      purchaseAmountMinor: 1050,
      receivedIncomeMinor: 250,
      receivedPoints: 4,
      currency: 'USD',
      note: 'boundary',
    };
    expect(occurredAtToBusinessDate(boundary.occurredAt)).toBe('2026-08-16');
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([boundary]);
    const updateSpy = vi.spyOn(guideOsClient, 'updatePersonalCommission').mockResolvedValue({
      ...boundary,
      receivedPoints: 8,
      note: 'updated',
    });
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    fireEvent.click(screen.getByRole('button', { name: 'Открыть комиссию за 16.08.2026' }));
    fireEvent.click(screen.getByRole('button', { name: t.edit }));
    expect(screen.getByLabelText(t.guideShopCommissionFieldDate)).toHaveValue('2026-08-16');
    expect(screen.getByLabelText(t.guideShopCommissionFieldPurchase)).toHaveValue('10.50');
    expect(screen.getByLabelText(t.guideShopCommissionFieldIncome)).toHaveValue('2.50');
    expect(screen.getByLabelText(t.guideShopCommissionFieldPoints)).toHaveValue('4');
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldPoints), {
      target: { value: '8' },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopFieldNote), {
      target: { value: 'updated' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    await waitFor(() => expect(updateSpy).toHaveBeenCalledTimes(1));
    expect(updateSpy.mock.calls[0]?.[1]).toEqual({
      occurredAt: '2026-08-16T00:00:00+05:00',
      purchaseAmountMinor: 1050,
      receivedIncomeMinor: 250,
      receivedPoints: 8,
      currency: 'USD',
      note: 'updated',
    });
  });

  it('preserves draft and confirmed record on edit failure; cancel discards', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([pointsCommission]);
    vi.spyOn(guideOsClient, 'updatePersonalCommission').mockRejectedValue(new Error('fail'));
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    fireEvent.click(screen.getByRole('button', { name: 'Открыть комиссию за 14.08.2026' }));
    fireEvent.click(screen.getByRole('button', { name: t.edit }));
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldPoints), {
      target: { value: '40' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(t.guideShopCommissionSaveError),
    );
    expect(screen.getByLabelText(t.guideShopCommissionFieldPoints)).toHaveValue('40');
    fireEvent.click(screen.getByRole('button', { name: t.cancel }));
    expect(screen.getByText('25')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: t.edit }));
    expect(screen.getByLabelText(t.guideShopCommissionFieldPoints)).toHaveValue('25');
  });

  it('requires confirmation for deactivate and reloads active history', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    const listSpy = vi
      .spyOn(guideOsClient, 'listPersonalCommissions')
      .mockResolvedValueOnce([pointsCommission])
      .mockResolvedValueOnce([]);
    const deactivateSpy = vi
      .spyOn(guideOsClient, 'deactivatePersonalCommission')
      .mockResolvedValue(undefined);
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    fireEvent.click(screen.getByRole('button', { name: 'Открыть комиссию за 14.08.2026' }));
    fireEvent.click(screen.getByRole('button', { name: t.guideShopDeactivate }));
    expect(screen.getByText(t.guideShopCommissionDeactivateTitle)).toBeInTheDocument();
    expect(screen.getByText(t.guideShopCommissionDeactivateHint)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: t.cancel }));
    expect(deactivateSpy).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: t.guideShopDeactivate }));
    fireEvent.click(screen.getAllByRole('button', { name: t.guideShopDeactivate })[0]!);
    await waitFor(() => expect(deactivateSpy).toHaveBeenCalledWith(pointsCommission.id));
    await waitFor(() => expect(listSpy).toHaveBeenCalledTimes(2));
    expect(screen.getAllByText(placeA.name).length).toBeGreaterThan(0);
    expect(screen.getByText(t.guideShopCommissionsEmptyHistory)).toBeInTheDocument();
  });

  it('preserves deactivate context on failure', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([pointsCommission]);
    vi.spyOn(guideOsClient, 'deactivatePersonalCommission').mockRejectedValue(new Error('fail'));
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    fireEvent.click(screen.getByRole('button', { name: 'Открыть комиссию за 14.08.2026' }));
    fireEvent.click(screen.getByRole('button', { name: t.guideShopDeactivate }));
    fireEvent.click(screen.getAllByRole('button', { name: t.guideShopDeactivate })[0]!);
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(t.guideShopCommissionDeactivateError),
    );
    expect(screen.getByText(t.guideShopCommissionDeactivateTitle)).toBeInTheDocument();
  });

  it('mock parity: filter, persist, get inactive, clone, reset', async () => {
    const active = await mockClient.listPersonalCommissions(placeA.id);
    expect(active.every((item) => item.status === 'active')).toBe(true);
    const withInactive = await mockClient.listPersonalCommissions(placeA.id, {
      includeInactive: true,
    });
    expect(withInactive.some((item) => item.status === 'inactive')).toBe(true);

    const created = await mockClient.createPersonalCommission(placeA.id, {
      occurredAt: '2026-08-01T00:00:00+05:00',
      purchaseAmountMinor: null,
      receivedIncomeMinor: null,
      receivedPoints: 2,
      currency: null,
      note: 'created',
    });
    expect(created.id.startsWith('entry_')).toBe(true);
    const updated = await mockClient.updatePersonalCommission(created.id, {
      occurredAt: '2026-08-01T00:00:00+05:00',
      purchaseAmountMinor: null,
      receivedIncomeMinor: null,
      receivedPoints: 3,
      currency: null,
      note: 'updated',
    });
    expect(updated.receivedPoints).toBe(3);
    await mockClient.deactivatePersonalCommission(created.id);
    const got = await mockClient.getPersonalCommission(created.id);
    expect(got?.status).toBe('inactive');

    const raw = __testPersonalCommissions().find((item) => item.id === created.id)!;
    const listed = (await mockClient.listPersonalCommissions(placeA.id, {
      includeInactive: true,
    })).find((item) => item.id === created.id)!;
    listed.note = 'mutated';
    expect(raw.note).toBe('updated');

    __resetMockStore();
    const resetList = await mockClient.listPersonalCommissions(placeA.id, {
      includeInactive: true,
    });
    expect(resetList.map((item) => item.id).sort()).toEqual(
      [
        'entry_11111111111111111111111111111111',
        'entry_22222222222222222222222222222222',
        'entry_44444444444444444444444444444444',
      ].sort(),
    );
  });

  it('pure helper money/date tables and a11y/css contracts', () => {
    const moneyCases: Array<[string, number | null | false]> = [
      ['0', 0],
      ['10', 1000],
      ['10.5', 1050],
      ['10.50', 1050],
      ['10,50', 1050],
      ['500000', 50000000],
      ['', null],
      ['-1', false],
      ['1.234', false],
      ['1,234', false],
      ['NaN', false],
      ['Infinity', false],
      ['1e3', false],
      ['text', false],
    ];
    for (const [raw, expected] of moneyCases) {
      const parsed = parseMoneyToMinor(raw);
      if (expected === false) expect(parsed.ok).toBe(false);
      else expect(parsed).toEqual({ ok: true, value: expected });
    }
    expect(formatMinorUnits(12500)).toBe('125.00');
    expect(formatMinorUnits(50000000)).toBe('500000.00');
    expect(formatMoneyAmount(12500, 'USD')).toBe('USD 125.00');
    expect(businessDateToOccurredAt('2026-08-15')).toBe('2026-08-15T00:00:00+05:00');
    expect(occurredAtToBusinessDate('2026-08-15T18:59:59Z')).toBe('2026-08-15');
    expect(occurredAtToBusinessDate('2026-08-15T19:00:00Z')).toBe('2026-08-16');

    expect(GLOBAL_CSS).toMatch(/\.guideshop-commission-row[\s\S]*min-height:\s*44px/);
    expect(GLOBAL_CSS).toMatch(/\.guideshop-commission-total[\s\S]*overflow-wrap:\s*anywhere/);
    expect(GLOBAL_CSS).toMatch(/\.guideshop-commissions[\s\S]*min-width:\s*0/);
  });

  it('associates labels and uses alert/status semantics', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    fireEvent.click(screen.getByRole('button', { name: t.guideShopAddCommission }));
    expect(screen.getByLabelText(t.guideShopCommissionFieldDate)).toBeInTheDocument();
    expect(screen.getByLabelText(t.guideShopCommissionFieldPurchase)).toBeInTheDocument();
    expect(screen.getByLabelText(t.guideShopCommissionFieldIncome)).toBeInTheDocument();
    expect(screen.getByLabelText(t.guideShopCommissionFieldPoints)).toBeInTheDocument();
    expect(screen.getByLabelText(t.guideShopCommissionFieldCurrency)).toBeInTheDocument();
    expect(screen.getByLabelText(t.guideShopFieldNote)).toBeInTheDocument();
    expect(screen.getByText(t.guideShopCommissionMoneyHint)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});

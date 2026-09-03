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
  occurredAtToBusinessDate,
  parseCommissionInput,
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

const commissionA: PersonalCommission = {
  id: 'entry_11111111111111111111111111111111',
  placeId: placeA.id,
  occurredAt: '2026-08-10T05:00:00Z',
  purchaseAmountMinor: null,
  receivedIncomeMinor: null,
  receivedPoints: 15,
  currency: null,
  note: 'Первая комиссия',
  status: 'active',
  createdAt: '2026-08-10T06:00:00Z',
  updatedAt: '2026-08-10T06:00:00Z',
};

const commissionB: PersonalCommission = {
  id: 'entry_22222222222222222222222222222222',
  placeId: placeA.id,
  occurredAt: '2026-08-12T05:00:00Z',
  purchaseAmountMinor: null,
  receivedIncomeMinor: null,
  receivedPoints: 40,
  currency: null,
  note: 'Вторая комиссия',
  status: 'active',
  createdAt: '2026-08-12T06:00:00Z',
  updatedAt: '2026-08-12T06:00:00Z',
};

const inactiveCommission: PersonalCommission = {
  id: 'entry_44444444444444444444444444444444',
  placeId: placeA.id,
  occurredAt: '2026-08-05T05:00:00Z',
  purchaseAmountMinor: null,
  receivedIncomeMinor: null,
  receivedPoints: 10,
  currency: null,
  note: 'Неактивная запись',
  status: 'inactive',
  createdAt: '2026-08-05T06:00:00Z',
  updatedAt: '2026-08-05T07:00:00Z',
};

const legacyMoneyOnly: PersonalCommission = {
  id: 'entry_55555555555555555555555555555555',
  placeId: placeA.id,
  occurredAt: '2026-08-08T05:00:00Z',
  purchaseAmountMinor: 10000,
  receivedIncomeMinor: 12500,
  receivedPoints: null,
  currency: 'USD',
  note: 'LEGACY_USD_NOTE',
  status: 'active',
  createdAt: '2026-08-08T06:00:00Z',
  updatedAt: '2026-08-08T06:00:00Z',
};

function renderPage() {
  return render(<GuideShopPage />);
}

async function waitForPlacesLoaded() {
  await waitFor(() => {
    expect(screen.queryByText(t.guideShopLoading)).not.toBeInTheDocument();
  });
}

async function openCompany() {
  fireEvent.click(screen.getByRole('button', { name: t.guideShopOpenCompany(placeA.name) }));
}

async function waitForCommissionsLoaded() {
  await waitFor(() => {
    expect(screen.queryByText(t.guideShopCommissionsLoading)).not.toBeInTheDocument();
  });
}

async function openCreateForm() {
  fireEvent.click(screen.getByRole('button', { name: t.guideShopAddCommission }));
}

describe('GuideShop personal commissions UI (simplified)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    __resetMockStore();
  });

  afterEach(() => {
    cleanup();
  });

  it('form renders exactly Date, Commission, Note and no obsolete fields', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    await openCreateForm();

    expect(screen.getByLabelText(t.guideShopCommissionFieldDate)).toBeInTheDocument();
    expect(screen.getByLabelText(t.guideShopCommissionFieldCommission)).toBeInTheDocument();
    expect(screen.getByLabelText(t.guideShopFieldNote)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Сумма покупки/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Полученная комиссия/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Валюта/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Балл/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/points/i)).not.toBeInTheDocument();
  });

  it('accepts valid positive integer and rejects invalid commission values', async () => {
    expect(parseCommissionInput('15')).toEqual({ ok: true, value: 15 });
    for (const bad of ['0', '-1', '1.5', '10,5', '1e3', 'abc', '', '  ', '9007199254740992']) {
      expect(parseCommissionInput(bad).ok).toBe(false);
    }

    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
    const createSpy = vi.spyOn(guideOsClient, 'createPersonalCommission');
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    await openCreateForm();

    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(screen.getByText(t.guideShopCommissionValInvalid)).toBeInTheDocument();

    for (const bad of ['0', '-1', '1.5', '10,5', '1e3', 'text', '9007199254740992']) {
      fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldCommission), {
        target: { value: bad },
      });
      fireEvent.click(screen.getByRole('button', { name: t.save }));
      expect(screen.getByText(t.guideShopCommissionValInvalid)).toBeInTheDocument();
    }
    expect(createSpy).not.toHaveBeenCalled();
  });

  it('create sends receivedPoints with null money/currency compatibility fields', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
    const createSpy = vi.spyOn(guideOsClient, 'createPersonalCommission').mockResolvedValue({
      ...commissionA,
      id: 'entry_cccccccccccccccccccccccccccccccc',
      receivedPoints: 17,
      note: 'note',
    });
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    await openCreateForm();
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldCommission), {
      target: { value: '17' },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopFieldNote), {
      target: { value: 'note' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    await waitFor(() => expect(createSpy).toHaveBeenCalledTimes(1));
    expect(createSpy.mock.calls[0]?.[1]).toEqual({
      occurredAt: businessDateToOccurredAt(MOCK_TODAY),
      purchaseAmountMinor: null,
      receivedIncomeMinor: null,
      receivedPoints: 17,
      currency: null,
      note: 'note',
    });
  });

  it('edit restores commission from receivedPoints and sends compatibility payload', async () => {
    const boundary: PersonalCommission = {
      ...commissionA,
      occurredAt: '2026-08-15T19:00:00Z',
      receivedPoints: 4,
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
    expect(screen.getByLabelText(t.guideShopCommissionFieldCommission)).toHaveValue('4');
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldCommission), {
      target: { value: '8' },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopFieldNote), {
      target: { value: 'updated' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    await waitFor(() => expect(updateSpy).toHaveBeenCalledTimes(1));
    expect(updateSpy.mock.calls[0]?.[1]).toEqual({
      occurredAt: '2026-08-16T00:00:00+05:00',
      purchaseAmountMinor: null,
      receivedIncomeMinor: null,
      receivedPoints: 8,
      currency: null,
      note: 'updated',
    });
  });

  it('summary totals active receivedPoints with Комиссия label and excludes inactive', async () => {
    const summary = summarizeActiveCommissions([
      commissionA,
      commissionB,
      inactiveCommission,
      legacyMoneyOnly,
    ]);
    expect(summary).toEqual({ total: 55, isEmpty: false });

    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([
      commissionA,
      commissionB,
      inactiveCommission,
      legacyMoneyOnly,
    ]);
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    expect(screen.getByText(t.guideShopCommissionAmount(55))).toBeInTheDocument();
    expect(screen.queryByText(/Балл/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/USD/)).not.toBeInTheDocument();
    expect(screen.queryByText('LEGACY_USD_NOTE')).not.toBeInTheDocument();
    expect(screen.queryByText(t.guideShopCommissionAmount(10))).not.toBeInTheDocument();
  });

  it('history and detail show only date, commission, and note', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([
      commissionA,
      legacyMoneyOnly,
    ]);
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    const rows = screen.getAllByRole('button', { name: /Открыть комиссию за/ });
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent('10.08.2026');
    expect(rows[0]).toHaveTextContent(t.guideShopCommissionAmount(15));
    expect(rows[0]).toHaveTextContent('Первая комиссия');
    expect(screen.queryByText(/Покупка/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/USD/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Балл/i)).not.toBeInTheDocument();

    fireEvent.click(rows[0]!);
    expect(screen.getByText(t.guideShopCommissionDetailTitle)).toBeInTheDocument();
    expect(screen.getByText('10.08.2026')).toBeInTheDocument();
    expect(screen.getByText('15')).toBeInTheDocument();
    expect(screen.getByText('Первая комиссия')).toBeInTheDocument();
    expect(screen.queryByText(/Покупка/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Валюта/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Балл/i)).not.toBeInTheDocument();
  });

  it('failed save preserves all three draft fields', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
    vi.spyOn(guideOsClient, 'createPersonalCommission').mockRejectedValue(new Error('fail'));
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    await openCreateForm();
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldDate), {
      target: { value: '2026-08-20' },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopCommissionFieldCommission), {
      target: { value: '9' },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopFieldNote), {
      target: { value: 'draft note' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(t.guideShopCommissionSaveError),
    );
    expect(screen.getByLabelText(t.guideShopCommissionFieldDate)).toHaveValue('2026-08-20');
    expect(screen.getByLabelText(t.guideShopCommissionFieldCommission)).toHaveValue('9');
    expect(screen.getByLabelText(t.guideShopFieldNote)).toHaveValue('draft note');
  });

  it('deactivate confirms, reloads active history, and preserves failure context', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    const listSpy = vi
      .spyOn(guideOsClient, 'listPersonalCommissions')
      .mockResolvedValueOnce([commissionA])
      .mockResolvedValueOnce([]);
    const deactivateSpy = vi
      .spyOn(guideOsClient, 'deactivatePersonalCommission')
      .mockResolvedValue(undefined);
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    fireEvent.click(screen.getByRole('button', { name: 'Открыть комиссию за 10.08.2026' }));
    fireEvent.click(screen.getByRole('button', { name: t.guideShopDeactivate }));
    expect(screen.getByText(t.guideShopCommissionDeactivateTitle)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: t.cancel }));
    expect(deactivateSpy).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: t.guideShopDeactivate }));
    fireEvent.click(screen.getAllByRole('button', { name: t.guideShopDeactivate })[0]!);
    await waitFor(() => expect(deactivateSpy).toHaveBeenCalledWith(commissionA.id));
    await waitFor(() => expect(listSpy).toHaveBeenCalledTimes(2));
    expect(screen.getByText(t.guideShopCommissionsEmptyHistory)).toBeInTheDocument();
  });

  it('Asia/Tashkent date conversion remains correct', () => {
    expect(businessDateToOccurredAt('2026-08-15')).toBe('2026-08-15T00:00:00+05:00');
    expect(occurredAtToBusinessDate('2026-08-15T18:59:59Z')).toBe('2026-08-15');
    expect(occurredAtToBusinessDate('2026-08-15T19:00:00Z')).toBe('2026-08-16');
  });

  it('mock records use simplified commission shape', async () => {
    const list = await mockClient.listPersonalCommissions(placeA.id, { includeInactive: true });
    expect(list.length).toBeGreaterThan(0);
    for (const item of list) {
      expect(item.purchaseAmountMinor).toBeNull();
      expect(item.receivedIncomeMinor).toBeNull();
      expect(item.currency).toBeNull();
      expect(item.receivedPoints).toBeTruthy();
    }
    const created = await mockClient.createPersonalCommission(placeA.id, {
      occurredAt: '2026-08-01T00:00:00+05:00',
      purchaseAmountMinor: null,
      receivedIncomeMinor: null,
      receivedPoints: 3,
      currency: null,
      note: null,
    });
    expect(created.receivedPoints).toBe(3);
    expect(created.currency).toBeNull();
    const raw = __testPersonalCommissions().find((item) => item.id === created.id)!;
    const clone = (await mockClient.getPersonalCommission(created.id))!;
    clone.note = 'mutated';
    expect(raw.note).toBeNull();
    __resetMockStore();
    expect(__testPersonalCommissions().map((item) => item.id).sort()).toEqual(
      [
        'entry_11111111111111111111111111111111',
        'entry_22222222222222222222222222222222',
        'entry_33333333333333333333333333333333',
        'entry_44444444444444444444444444444444',
      ].sort(),
    );
  });

  it('defaults create date to Guide OS business date', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([placeA]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
    renderPage();
    await waitForPlacesLoaded();
    await openCompany();
    await waitForCommissionsLoaded();
    await openCreateForm();
    expect(screen.getByLabelText(t.guideShopCommissionFieldDate)).toHaveValue(MOCK_TODAY);
  });

  it('keeps css touch and overflow contracts', () => {
    expect(GLOBAL_CSS).toMatch(/\.guideshop-commission-row[\s\S]*min-height:\s*44px/);
    expect(GLOBAL_CSS).toMatch(/\.guideshop-commission-total[\s\S]*overflow-wrap:\s*anywhere/);
    expect(GLOBAL_CSS).toMatch(/\.guideshop-commissions[\s\S]*min-width:\s*0/);
  });
});

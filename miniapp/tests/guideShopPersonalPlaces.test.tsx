// @ts-nocheck — read CSS source at runtime; Node built-ins are not in app tsconfig.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ApiError } from '@/api/httpClient';
import type { OfficialCompany, PersonalPlace } from '@/api/types';
import { guideOsClient } from '@/api/createClient';
import { mockClient, __resetMockStore, __testPersonalPlaces } from '@/api/mock/store';
import { GuideShopPage } from '@/features/guideshop/GuideShopPage';
import { t } from '@/i18n/strings';

const GLOBAL_CSS = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../src/styles/global.css'),
  'utf8',
);

const activePlace: PersonalPlace = {
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

const officialFull: OfficialCompany = {
  id: 'gsco_silkroad_01',
  displayName: 'Silk Road Emporium',
  status: 'active',
  phone: '+998901112233',
  address: 'Registan Square, Samarkand',
  description: 'Official partner',
  type: 'shop',
};

const officialSparse: OfficialCompany = {
  id: 'gsco_nullfields_02',
  displayName: 'Sparse Official Co',
  status: 'pending_review',
  phone: null,
  address: null,
  description: null,
  type: null,
};

const officialWorkshop: OfficialCompany = {
  id: 'gsco_ceramic_shop_03',
  displayName: 'Khiva Ceramic Workshop',
  status: 'inactive',
  phone: '+998933334455',
  address: 'Ichan-Kala, Khiva',
  description: 'Handmade ceramics',
  type: 'workshop',
};

function emptyOfficialResult() {
  return { companies: [] as OfficialCompany[], page: { nextCursor: null } };
}

function renderPage() {
  return render(<GuideShopPage />);
}

async function waitForLoaded() {
  await waitFor(() => {
    expect(screen.queryByText(t.guideShopLoading)).not.toBeInTheDocument();
    expect(screen.queryByText(t.guideShopOfficialLoading)).not.toBeInTheDocument();
  });
}

function mockOfficialEmpty() {
  vi.spyOn(guideOsClient, 'listOfficialCompanies').mockResolvedValue(emptyOfficialResult());
}

describe('GuideShop personal places UI', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    __resetMockStore();
    mockOfficialEmpty();
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
  });

  afterEach(() => {
    cleanup();
  });

  it('shows loading state while list is pending', async () => {
    let resolveList: ((value: PersonalPlace[]) => void) | undefined;
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveList = resolve;
        }),
    );
    renderPage();
    expect(screen.getByText(t.guideShopLoading)).toBeInTheDocument();
    resolveList?.([]);
    await waitForLoaded();
  });

  it('shows empty state when there are no personal companies', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([]);
    renderPage();
    await waitForLoaded();
    expect(screen.getByText(t.guideShopEmptyTitle)).toBeInTheDocument();
    expect(screen.getByText(t.guideShopEmptyHint)).toBeInTheDocument();
  });

  it('keeps personal list error section-local with retry', async () => {
    const listSpy = vi
      .spyOn(guideOsClient, 'listPersonalPlaces')
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValueOnce([]);
    renderPage();
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(t.guideShopLoadError));
    expect(screen.getByText(t.guideShopOfficial)).toBeInTheDocument();
    expect(screen.getByText(t.guideShopOfficialEmpty)).toBeInTheDocument();
    expect(screen.queryByText(t.guideShopComingSoon)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: t.retry }));
    await waitFor(() => expect(listSpy).toHaveBeenCalledTimes(2));
  });

  it('shows no-results state distinct from empty state', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([activePlace]);
    renderPage();
    await waitForLoaded();
    fireEvent.change(screen.getByLabelText(t.guideShopSearchLabel), {
      target: { value: 'неттакого' },
    });
    expect(screen.getByText(t.guideShopNoResults)).toBeInTheDocument();
    expect(screen.queryByText(t.guideShopEmptyTitle)).not.toBeInTheDocument();
  });

  it('renders available metadata without internal ids', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([activePlace]);
    renderPage();
    await waitForLoaded();
    expect(screen.getByText(activePlace.name)).toBeInTheDocument();
    expect(screen.getByText('Магазин')).toBeInTheDocument();
    expect(screen.getByText('Бухара')).toBeInTheDocument();
    expect(screen.getByText('Рядом с Ляби-Хауз')).toBeInTheDocument();
    expect(screen.queryByText(activePlace.id)).not.toBeInTheDocument();
    expect(screen.queryByText('Секретная заметка')).not.toBeInTheDocument();
  });

  it('search matches name/category/location/landmark but not note', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([activePlace]);
    renderPage();
    await waitForLoaded();

    fireEvent.change(screen.getByLabelText(t.guideShopSearchLabel), {
      target: { value: 'бухара арт' },
    });
    expect(screen.getByText(activePlace.name)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopSearchLabel), {
      target: { value: 'магазин' },
    });
    expect(screen.getByText(activePlace.name)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopSearchLabel), {
      target: { value: 'ляби' },
    });
    expect(screen.getByText(activePlace.name)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopSearchLabel), {
      target: { value: 'секретная' },
    });
    expect(screen.getByText(t.guideShopNoResults)).toBeInTheDocument();
  });

  it('opens detail with edit/deactivate and commission add action', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([activePlace]);
    renderPage();
    await waitForLoaded();
    fireEvent.click(screen.getByRole('button', { name: t.guideShopOpenCompany(activePlace.name) }));
    expect(screen.getByRole('button', { name: t.edit })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.guideShopDeactivate })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.guideShopAddCommission })).toBeInTheDocument();
    expect(screen.getByText(t.guideShopCommissionsTitle)).toBeInTheDocument();
    expect(screen.getByText('Секретная заметка')).toBeInTheDocument();
  });

  it('create form validates required name and length limits', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([]);
    renderPage();
    await waitForLoaded();
    fireEvent.click(screen.getAllByRole('button', { name: t.guideShopAddCompany })[0]!);
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(screen.getByText(t.guideShopValNameRequired)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopFieldName), {
      target: { value: 'x'.repeat(101) },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopFieldCategory), {
      target: { value: 'x'.repeat(101) },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopFieldLocation), {
      target: { value: 'x'.repeat(201) },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopFieldLandmark), {
      target: { value: 'x'.repeat(201) },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopFieldNote), {
      target: { value: 'x'.repeat(501) },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(screen.getByText(t.guideShopValNameTooLong)).toBeInTheDocument();
    expect(screen.getByText(t.guideShopValCategoryTooLong)).toBeInTheDocument();
    expect(screen.getByText(t.guideShopValLocationTooLong)).toBeInTheDocument();
    expect(screen.getByText(t.guideShopValLandmarkTooLong)).toBeInTheDocument();
    expect(screen.getByText(t.guideShopValNoteTooLong)).toBeInTheDocument();
  });

  it('create trims values, nulls empty optionals, and closes on success', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([]);
    const createSpy = vi.spyOn(guideOsClient, 'createPersonalPlace').mockResolvedValue({
      ...activePlace,
      id: 'place_cccccccccccccccccccccccccccccccc',
      name: 'New Place',
      category: null,
      generalLocation: null,
      landmark: null,
      note: null,
    });
    renderPage();
    await waitForLoaded();
    fireEvent.click(screen.getAllByRole('button', { name: t.guideShopAddCompany })[0]!);
    fireEvent.change(screen.getByLabelText(t.guideShopFieldName), {
      target: { value: '  New Place  ' },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopFieldCategory), {
      target: { value: '   ' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    await waitFor(() => expect(createSpy).toHaveBeenCalledTimes(1));
    expect(createSpy.mock.calls[0]?.[0]).toEqual({
      name: 'New Place',
      category: null,
      generalLocation: null,
      landmark: null,
      note: null,
    });
    await waitFor(() => {
      expect(screen.queryByText(t.guideShopNewCompany)).not.toBeInTheDocument();
    });
    expect(screen.getByText('New Place')).toBeInTheDocument();
  });

  it('create rejection preserves draft and keeps form open', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([]);
    vi.spyOn(guideOsClient, 'createPersonalPlace').mockRejectedValue(new Error('fail'));
    renderPage();
    await waitForLoaded();
    fireEvent.click(screen.getAllByRole('button', { name: t.guideShopAddCompany })[0]!);
    fireEvent.change(screen.getByLabelText(t.guideShopFieldName), {
      target: { value: 'Draft Co' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(t.guideShopSaveError));
    expect(screen.getByLabelText(t.guideShopFieldName)).toHaveValue('Draft Co');
    expect(screen.getByText(t.guideShopNewCompany)).toBeInTheDocument();
  });

  it('blocks duplicate create submission while in flight', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([]);
    let resolveCreate: ((value: PersonalPlace) => void) | undefined;
    const createSpy = vi.spyOn(guideOsClient, 'createPersonalPlace').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCreate = resolve;
        }),
    );
    renderPage();
    await waitForLoaded();
    fireEvent.click(screen.getAllByRole('button', { name: t.guideShopAddCompany })[0]!);
    fireEvent.change(screen.getByLabelText(t.guideShopFieldName), {
      target: { value: 'Once' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(screen.getByRole('button', { name: t.guideShopSaving })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: t.guideShopSaving }));
    expect(createSpy).toHaveBeenCalledTimes(1);
    resolveCreate?.({
      ...activePlace,
      id: 'place_dddddddddddddddddddddddddddddddd',
      name: 'Once',
    });
    await waitFor(() => {
      expect(screen.queryByText(t.guideShopNewCompany)).not.toBeInTheDocument();
    });
  });

  it('edit restores values and replaces card after successful save', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([activePlace]);
    const updateSpy = vi.spyOn(guideOsClient, 'updatePersonalPlace').mockResolvedValue({
      ...activePlace,
      name: 'Updated Name',
      category: null,
      generalLocation: null,
      landmark: null,
      note: null,
    });
    renderPage();
    await waitForLoaded();
    fireEvent.click(screen.getByRole('button', { name: t.guideShopOpenCompany(activePlace.name) }));
    fireEvent.click(screen.getByRole('button', { name: t.edit }));
    expect(screen.getByLabelText(t.guideShopFieldName)).toHaveValue(activePlace.name);
    fireEvent.change(screen.getByLabelText(t.guideShopFieldName), {
      target: { value: 'Updated Name' },
    });
    fireEvent.change(screen.getByLabelText(t.guideShopFieldCategory), {
      target: { value: '' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    await waitFor(() => expect(updateSpy).toHaveBeenCalledTimes(1));
    expect(updateSpy.mock.calls[0]?.[1]).toEqual({
      name: 'Updated Name',
      category: null,
      generalLocation: 'Бухара',
      landmark: 'Рядом с Ляби-Хауз',
      note: 'Секретная заметка',
    });
    await waitFor(() => expect(screen.getAllByText('Updated Name').length).toBeGreaterThan(0));
  });

  it('failed edit preserves draft and previous confirmed card', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([activePlace]);
    vi.spyOn(guideOsClient, 'updatePersonalPlace').mockRejectedValue(new Error('fail'));
    renderPage();
    await waitForLoaded();
    fireEvent.click(screen.getByRole('button', { name: t.guideShopOpenCompany(activePlace.name) }));
    fireEvent.click(screen.getByRole('button', { name: t.edit }));
    fireEvent.change(screen.getByLabelText(t.guideShopFieldName), {
      target: { value: 'Broken Draft' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(t.guideShopSaveError));
    expect(screen.getByLabelText(t.guideShopFieldName)).toHaveValue('Broken Draft');
    fireEvent.click(screen.getByRole('button', { name: t.cancel }));
    expect(screen.getAllByText(activePlace.name).length).toBeGreaterThan(0);
  });

  it('cancel discards create draft', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([]);
    renderPage();
    await waitForLoaded();
    fireEvent.click(screen.getAllByRole('button', { name: t.guideShopAddCompany })[0]!);
    fireEvent.change(screen.getByLabelText(t.guideShopFieldName), {
      target: { value: 'Temp' },
    });
    fireEvent.click(screen.getByRole('button', { name: t.cancel }));
    fireEvent.click(screen.getAllByRole('button', { name: t.guideShopAddCompany })[0]!);
    expect(screen.getByLabelText(t.guideShopFieldName)).toHaveValue('');
  });

  it('deactivate requires confirmation and cancel performs no request', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([activePlace]);
    const deactivateSpy = vi.spyOn(guideOsClient, 'deactivatePersonalPlace');
    renderPage();
    await waitForLoaded();
    fireEvent.click(screen.getByRole('button', { name: t.guideShopOpenCompany(activePlace.name) }));
    fireEvent.click(screen.getByRole('button', { name: t.guideShopDeactivate }));
    expect(screen.getByText(t.guideShopDeactivateTitle)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: t.cancel }));
    expect(deactivateSpy).not.toHaveBeenCalled();
  });

  it('successful deactivate reloads active list and closes flow', async () => {
    const listSpy = vi
      .spyOn(guideOsClient, 'listPersonalPlaces')
      .mockResolvedValueOnce([activePlace])
      .mockResolvedValueOnce([]);
    vi.spyOn(guideOsClient, 'deactivatePersonalPlace').mockResolvedValue();
    renderPage();
    await waitForLoaded();
    fireEvent.click(screen.getByRole('button', { name: t.guideShopOpenCompany(activePlace.name) }));
    fireEvent.click(screen.getByRole('button', { name: t.guideShopDeactivate }));
    fireEvent.click(screen.getByRole('button', { name: t.guideShopDeactivate }));
    await waitFor(() => expect(listSpy).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByText(t.guideShopEmptyTitle)).toBeInTheDocument());
  });

  it('failed deactivate keeps confirmation context and shows error', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([activePlace]);
    vi.spyOn(guideOsClient, 'deactivatePersonalPlace').mockRejectedValue(new Error('fail'));
    renderPage();
    await waitForLoaded();
    fireEvent.click(screen.getByRole('button', { name: t.guideShopOpenCompany(activePlace.name) }));
    fireEvent.click(screen.getByRole('button', { name: t.guideShopDeactivate }));
    fireEvent.click(screen.getByRole('button', { name: t.guideShopDeactivate }));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(t.guideShopDeactivateError),
    );
    expect(screen.getByText(t.guideShopDeactivateTitle)).toBeInTheDocument();
  });

  it('does not expose a deletePersonalPlace client method', () => {
    expect('deletePersonalPlace' in guideOsClient).toBe(false);
  });
});

describe('GuideShop personal places mock parity', () => {
  beforeEach(() => {
    __resetMockStore();
  });

  it('default list excludes inactive places', async () => {
    const created = await mockClient.createPersonalPlace({
      name: 'Temp',
      category: null,
      generalLocation: null,
      landmark: null,
      note: null,
    });
    await mockClient.deactivatePersonalPlace(created.id);
    const active = await mockClient.listPersonalPlaces();
    expect(active.some((place) => place.id === created.id)).toBe(false);
  });

  it('includeInactive=true returns inactive places', async () => {
    const created = await mockClient.createPersonalPlace({
      name: 'Temp',
      category: null,
      generalLocation: null,
      landmark: null,
      note: null,
    });
    await mockClient.deactivatePersonalPlace(created.id);
    const all = await mockClient.listPersonalPlaces({ includeInactive: true });
    expect(all.some((place) => place.id === created.id && place.status === 'inactive')).toBe(
      true,
    );
  });

  it('create/update/deactivate persist and responses are cloned', async () => {
    const created = await mockClient.createPersonalPlace({
      name: 'Clone Me',
      category: 'A',
      generalLocation: null,
      landmark: null,
      note: null,
    });
    created.name = 'mutated';
    const fetched = await mockClient.getPersonalPlace(created.id);
    expect(fetched?.name).toBe('Clone Me');

    const updated = await mockClient.updatePersonalPlace(created.id, {
      name: 'Updated',
      category: null,
      generalLocation: 'Samarkand',
      landmark: null,
      note: null,
    });
    expect(updated.name).toBe('Updated');
    await mockClient.deactivatePersonalPlace(created.id);
    const inactive = __testPersonalPlaces().find((place) => place.id === created.id);
    expect(inactive?.status).toBe('inactive');
  });

  it('__resetMockStore restores deterministic personal places', async () => {
    await mockClient.createPersonalPlace({
      name: 'Extra',
      category: null,
      generalLocation: null,
      landmark: null,
      note: null,
    });
    __resetMockStore();
    const places = await mockClient.listPersonalPlaces();
    expect(places.map((place) => place.id)).toEqual([
      'place_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'place_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    ]);
  });
});

describe('GuideShop accessibility and CSS', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    __resetMockStore();
    mockOfficialEmpty();
  });

  afterEach(() => {
    cleanup();
  });

  it('associates form labels and exposes accessible names', async () => {
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([]);
    renderPage();
    await waitForLoaded();
    fireEvent.click(screen.getAllByRole('button', { name: t.guideShopAddCompany })[0]!);
    expect(screen.getByLabelText(t.guideShopFieldName)).toBeInTheDocument();
    expect(screen.getByLabelText(t.guideShopFieldCategory)).toBeInTheDocument();
    expect(screen.getByLabelText(t.guideShopSearchLabel)).toBeInTheDocument();
  });

  it('loading and error use status/alert semantics', async () => {
    let rejectList: ((reason?: unknown) => void) | undefined;
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockImplementation(
      () =>
        new Promise((_, reject) => {
          rejectList = reject;
        }),
    );
    renderPage();
    expect(screen.getByText(t.guideShopLoading)).toBeInTheDocument();
    rejectList?.(new Error('fail'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('CSS prevents page overflow and keeps touch targets', () => {
    expect(GLOBAL_CSS).toContain('.guideshop-page');
    expect(GLOBAL_CSS).toContain('overflow-x: hidden');
    expect(GLOBAL_CSS).toContain('.guideshop-place-card');
    expect(GLOBAL_CSS).toContain('min-height: 44px');
    expect(GLOBAL_CSS).toContain('.guideshop-official-section');
    expect(GLOBAL_CSS).toContain('.guideshop-badge-official');
    expect(GLOBAL_CSS).toContain('overflow-wrap: anywhere');
    expect(GLOBAL_CSS).toContain('word-break: break-word');
  });
});

describe('GuideShop official companies UI', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    __resetMockStore();
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
  });

  afterEach(() => {
    cleanup();
  });

  it('shows official loading, success list, badge, and status labels', async () => {
    let resolveList: ((value: { companies: OfficialCompany[]; page: { nextCursor: null } }) => void) | undefined;
    vi.spyOn(guideOsClient, 'listOfficialCompanies').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveList = resolve;
        }),
    );
    renderPage();
    expect(screen.getByText(t.guideShopOfficialLoading)).toBeInTheDocument();
    resolveList?.({
      companies: [officialFull, officialSparse, officialWorkshop],
      page: { nextCursor: null },
    });
    await waitForLoaded();

    expect(screen.getByText(officialFull.displayName)).toBeInTheDocument();
    expect(screen.getAllByText(t.guideShopOfficialBadge).length).toBeGreaterThan(0);
    expect(screen.getByText(t.guideShopOfficialStatusActive)).toBeInTheDocument();
    expect(screen.getByText(t.guideShopOfficialStatusInactive)).toBeInTheDocument();
    expect(
      screen.getByText(t.guideShopOfficialStatusUnknown('pending_review')),
    ).toBeInTheDocument();
    expect(screen.getByText('shop')).toBeInTheDocument();
    expect(screen.getByText('Registan Square, Samarkand')).toBeInTheDocument();
    expect(screen.queryByText(officialFull.id)).not.toBeInTheDocument();
    expect(screen.getByText(officialSparse.displayName)).toBeInTheDocument();
  });

  it('shows empty-catalog and distinct no-results states', async () => {
    vi.spyOn(guideOsClient, 'listOfficialCompanies')
      .mockResolvedValueOnce(emptyOfficialResult())
      .mockResolvedValueOnce({
        companies: [officialFull],
        page: { nextCursor: null },
      });

    const { unmount } = renderPage();
    await waitForLoaded();
    expect(screen.getByText(t.guideShopOfficialEmpty)).toBeInTheDocument();
    expect(screen.queryByText(t.guideShopOfficialNoResults)).not.toBeInTheDocument();
    unmount();

    renderPage();
    await waitForLoaded();
    fireEvent.change(screen.getByLabelText(t.guideShopSearchLabel), {
      target: { value: 'неттакого' },
    });
    expect(screen.getByText(t.guideShopOfficialNoResults)).toBeInTheDocument();
    expect(screen.queryByText(t.guideShopOfficialEmpty)).not.toBeInTheDocument();
  });

  it('searches official name/type/address/phone but not id or description', async () => {
    vi.spyOn(guideOsClient, 'listOfficialCompanies').mockResolvedValue({
      companies: [officialFull, officialWorkshop],
      page: { nextCursor: null },
    });
    renderPage();
    await waitForLoaded();

    fireEvent.change(screen.getByLabelText(t.guideShopSearchLabel), {
      target: { value: 'silk road' },
    });
    expect(screen.getByText(officialFull.displayName)).toBeInTheDocument();
    expect(screen.queryByText(officialWorkshop.displayName)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopSearchLabel), {
      target: { value: 'workshop' },
    });
    expect(screen.getByText(officialWorkshop.displayName)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopSearchLabel), {
      target: { value: 'ichan-kala' },
    });
    expect(screen.getByText(officialWorkshop.displayName)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopSearchLabel), {
      target: { value: '+998901112233' },
    });
    expect(screen.getByText(officialFull.displayName)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopSearchLabel), {
      target: { value: officialFull.id },
    });
    expect(screen.getByText(t.guideShopOfficialNoResults)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopSearchLabel), {
      target: { value: 'official partner' },
    });
    expect(screen.getByText(t.guideShopOfficialNoResults)).toBeInTheDocument();
  });

  it('keeps official and personal search results independent including identical names', async () => {
    const twinPersonal: PersonalPlace = {
      ...activePlace,
      id: 'place_twin_personal_aaaaaaaaaaaaaaaa',
      name: 'Silk Road Emporium',
    };
    vi.spyOn(guideOsClient, 'listOfficialCompanies').mockResolvedValue({
      companies: [officialFull],
      page: { nextCursor: null },
    });
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([twinPersonal, activePlace]);

    renderPage();
    await waitForLoaded();

    fireEvent.change(screen.getByLabelText(t.guideShopSearchLabel), {
      target: { value: 'silk road emporium' },
    });
    expect(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: t.guideShopOpenCompany(twinPersonal.name) }),
    ).toBeInTheDocument();
    expect(screen.queryByText(t.guideShopOfficialNoResults)).not.toBeInTheDocument();
    expect(screen.queryByText(t.guideShopNoResults)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopSearchLabel), {
      target: { value: 'бухара арт' },
    });
    expect(screen.getByText(t.guideShopOfficialNoResults)).toBeInTheDocument();
    expect(screen.getByText(activePlace.name)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t.guideShopSearchLabel), {
      target: { value: 'registan' },
    });
    expect(screen.getByText(officialFull.displayName)).toBeInTheDocument();
    expect(screen.getByText(t.guideShopNoResults)).toBeInTheDocument();
  });

  it('opens read-only detail with approved fields and no mutation actions', async () => {
    vi.spyOn(guideOsClient, 'listOfficialCompanies').mockResolvedValue({
      companies: [officialFull],
      page: { nextCursor: null },
    });
    const detailSpy = vi
      .spyOn(guideOsClient, 'getOfficialCompany')
      .mockResolvedValue(officialFull);

    renderPage();
    await waitForLoaded();
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    );

    await waitFor(() => expect(detailSpy).toHaveBeenCalledWith(officialFull.id));
    const sheet = screen.getByText(t.guideShopOfficialFieldDescription).closest('.sheet');
    expect(sheet).toBeTruthy();
    expect(within(sheet!).getByText(t.guideShopOfficialBadge)).toBeInTheDocument();
    expect(within(sheet!).getByText('shop')).toBeInTheDocument();
    expect(within(sheet!).getByText(t.guideShopOfficialStatusActive)).toBeInTheDocument();
    expect(within(sheet!).getByText(officialFull.phone!)).toBeInTheDocument();
    expect(within(sheet!).getByText(officialFull.address!)).toBeInTheDocument();
    expect(within(sheet!).getByText(officialFull.description!)).toBeInTheDocument();
    expect(within(sheet!).queryByText(officialFull.id)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.edit })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.guideShopDeactivate })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: t.guideShopAddCommission }),
    ).not.toBeInTheDocument();
  });

  it('shows detail loading, not-found, error/retry, and preserves search on close', async () => {
    vi.spyOn(guideOsClient, 'listOfficialCompanies').mockResolvedValue({
      companies: [officialFull, officialWorkshop],
      page: { nextCursor: null },
    });
    let resolveDetail: ((value: OfficialCompany | null) => void) | undefined;
    const detailSpy = vi.spyOn(guideOsClient, 'getOfficialCompany').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveDetail = resolve;
        }),
    );

    renderPage();
    await waitForLoaded();
    fireEvent.change(screen.getByLabelText(t.guideShopSearchLabel), {
      target: { value: 'silk' },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    );
    expect(screen.getByText(t.guideShopOfficialDetailLoading)).toBeInTheDocument();
    resolveDetail?.(null);
    await waitFor(() =>
      expect(screen.getByText(t.guideShopOfficialDetailNotFound)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getAllByRole('button', { name: t.close }).at(-1)!);
    expect(screen.getByLabelText(t.guideShopSearchLabel)).toHaveValue('silk');
    expect(screen.getByText(officialFull.displayName)).toBeInTheDocument();

    detailSpy.mockRejectedValueOnce(new Error('fail')).mockResolvedValueOnce(officialFull);
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    );
    await waitFor(() =>
      expect(screen.getByText(t.guideShopOfficialDetailError)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: t.retry }));
    await waitFor(() => expect(screen.getByText(officialFull.description!)).toBeInTheDocument());
  });

  it('ignores stale detail responses after a newer selection', async () => {
    vi.spyOn(guideOsClient, 'listOfficialCompanies').mockResolvedValue({
      companies: [officialFull, officialWorkshop],
      page: { nextCursor: null },
    });
    let resolveFirst: ((value: OfficialCompany | null) => void) | undefined;
    let resolveSecond: ((value: OfficialCompany | null) => void) | undefined;
    vi.spyOn(guideOsClient, 'getOfficialCompany').mockImplementation((id: string) => {
      if (id === officialFull.id) {
        return new Promise((resolve) => {
          resolveFirst = resolve;
        });
      }
      return new Promise((resolve) => {
        resolveSecond = resolve;
      });
    });

    renderPage();
    await waitForLoaded();
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialWorkshop.displayName),
      }),
    );
    resolveSecond?.(officialWorkshop);
    await waitFor(() =>
      expect(screen.getByText(officialWorkshop.description!)).toBeInTheDocument(),
    );
    resolveFirst?.(officialFull);
    await waitFor(() =>
      expect(screen.queryByText(officialFull.description!)).not.toBeInTheDocument(),
    );
    expect(screen.getByText(officialWorkshop.description!)).toBeInTheDocument();
  });

  it('maps dedicated official list errors and retries only official catalog', async () => {
    const officialSpy = vi
      .spyOn(guideOsClient, 'listOfficialCompanies')
      .mockRejectedValueOnce(new ApiError('integration_disabled', 'off', 503))
      .mockRejectedValueOnce(new ApiError('access_denied', 'denied', 403))
      .mockRejectedValueOnce(new ApiError('temporarily_unavailable', 'down', 503))
      .mockResolvedValueOnce({
        companies: [officialFull],
        page: { nextCursor: null },
      });
    const personalSpy = vi
      .spyOn(guideOsClient, 'listPersonalPlaces')
      .mockResolvedValue([activePlace]);

    const { unmount } = renderPage();
    await waitFor(() =>
      expect(screen.getByText(t.guideShopOfficialIntegrationDisabled)).toBeInTheDocument(),
    );
    expect(screen.queryByRole('button', { name: t.retry })).not.toBeInTheDocument();
    expect(screen.getByText(activePlace.name)).toBeInTheDocument();
    unmount();

    const second = renderPage();
    await waitFor(() =>
      expect(screen.getByText(t.guideShopOfficialAccessDenied)).toBeInTheDocument(),
    );
    expect(screen.getByText(activePlace.name)).toBeInTheDocument();
    second.unmount();

    renderPage();
    await waitFor(() =>
      expect(screen.getByText(t.guideShopOfficialLoadError)).toBeInTheDocument(),
    );
    const personalCallsBeforeRetry = personalSpy.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: t.retry }));
    await waitFor(() => expect(screen.getByText(officialFull.displayName)).toBeInTheDocument());
    expect(officialSpy.mock.calls.length).toBeGreaterThanOrEqual(4);
    expect(personalSpy.mock.calls.length).toBe(personalCallsBeforeRetry);
  });

  it('starts official and personal requests independently and isolates failures', async () => {
    let resolveOfficial:
      | ((value: { companies: OfficialCompany[]; page: { nextCursor: null } }) => void)
      | undefined;
    let resolvePersonal: ((value: PersonalPlace[]) => void) | undefined;

    vi.spyOn(guideOsClient, 'listOfficialCompanies').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveOfficial = resolve;
        }),
    );
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePersonal = resolve;
        }),
    );

    renderPage();
    expect(screen.getByText(t.guideShopOfficialLoading)).toBeInTheDocument();
    expect(screen.getByText(t.guideShopLoading)).toBeInTheDocument();

    resolveOfficial?.({ companies: [officialFull], page: { nextCursor: null } });
    await waitFor(() => expect(screen.getByText(officialFull.displayName)).toBeInTheDocument());
    expect(screen.getByText(t.guideShopLoading)).toBeInTheDocument();

    resolvePersonal?.([activePlace]);
    await waitFor(() => expect(screen.getByText(activePlace.name)).toBeInTheDocument());

    cleanup();
    vi.restoreAllMocks();
    __resetMockStore();
    vi.spyOn(guideOsClient, 'listOfficialCompanies').mockRejectedValue(
      new ApiError('temporarily_unavailable', 'down', 503),
    );
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([activePlace]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(t.guideShopOfficialLoadError)).toBeInTheDocument(),
    );
    expect(screen.getByText(activePlace.name)).toBeInTheDocument();

    cleanup();
    vi.restoreAllMocks();
    __resetMockStore();
    vi.spyOn(guideOsClient, 'listOfficialCompanies').mockResolvedValue({
      companies: [officialFull],
      page: { nextCursor: null },
    });
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockRejectedValue(new Error('fail'));
    renderPage();
    await waitFor(() => expect(screen.getByText(officialFull.displayName)).toBeInTheDocument());
    expect(screen.getByText(t.guideShopLoadError)).toBeInTheDocument();
  });

  it('closing official detail does not alter personal-company state', async () => {
    vi.spyOn(guideOsClient, 'listOfficialCompanies').mockResolvedValue({
      companies: [officialFull],
      page: { nextCursor: null },
    });
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([activePlace]);
    vi.spyOn(guideOsClient, 'getOfficialCompany').mockResolvedValue(officialFull);
    const personalListSpy = vi.spyOn(guideOsClient, 'listPersonalPlaces');

    renderPage();
    await waitForLoaded();
    const personalCalls = personalListSpy.mock.calls.length;
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    );
    await waitFor(() => expect(screen.getByText(officialFull.description!)).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('button', { name: t.close }).at(-1)!);
    expect(screen.getByText(activePlace.name)).toBeInTheDocument();
    expect(personalListSpy.mock.calls.length).toBe(personalCalls);
  });
});

describe('GuideShop official visits UI', () => {
  const visitForCompany = {
    id: 'gsvis_silk_01',
    companyId: officialFull.id,
    visitAt: '2026-08-10T09:00:00Z',
    status: 'completed',
    touristCount: 4,
    customerPaymentStatus: 'paid',
    customerPaidAt: '2026-08-10T11:30:00Z',
    createdAt: '2026-08-10T09:05:00Z',
    updatedAt: '2026-08-10T11:30:00Z',
  };

  const visitOtherCompany = {
    id: 'gsvis_khiva_03',
    companyId: officialWorkshop.id,
    visitAt: '2026-08-20T08:30:00Z',
    status: 'cancelled',
    touristCount: 0,
    customerPaymentStatus: 'unpaid',
    customerPaidAt: null,
    createdAt: '2026-08-20T08:35:00Z',
    updatedAt: '2026-08-20T09:00:00Z',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    __resetMockStore();
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([activePlace]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
    vi.spyOn(guideOsClient, 'listOfficialCompanies').mockResolvedValue({
      companies: [officialFull, officialWorkshop],
      page: { nextCursor: null },
    });
    vi.spyOn(guideOsClient, 'getOfficialCompany').mockResolvedValue(officialFull);
  });

  afterEach(() => {
    cleanup();
  });

  it('opens company-scoped visits list and detail without opaque IDs', async () => {
    vi.spyOn(guideOsClient, 'listOfficialVisits').mockResolvedValue({
      visits: [visitForCompany, visitOtherCompany],
      page: { nextCursor: null },
    });
    const detailSpy = vi
      .spyOn(guideOsClient, 'getOfficialVisit')
      .mockResolvedValue(visitForCompany);

    renderPage();
    await waitForLoaded();
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    );
    await waitFor(() => expect(screen.getByText(officialFull.description!)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: t.guideShopVisitsAction }));

    await waitFor(() => expect(screen.getByText(t.guideShopVisitsTitle)).toBeInTheDocument());
    expect(screen.getByText(t.guideShopVisitTourists(4))).toBeInTheDocument();
    expect(screen.getByText(t.guideShopVisitStatusCompleted)).toBeInTheDocument();
    expect(screen.getByText(t.guideShopVisitPaymentPaid)).toBeInTheDocument();
    expect(screen.queryByText(visitOtherCompany.id)).not.toBeInTheDocument();
    expect(screen.queryByText(visitForCompany.id)).not.toBeInTheDocument();
    expect(screen.queryByText(officialFull.id)).not.toBeInTheDocument();
    expect(screen.queryByText(t.guideShopVisitStatusCancelled)).not.toBeInTheDocument();

    fireEvent.click(screen.getByText(t.guideShopVisitTourists(4)).closest('button')!);
    await waitFor(() => expect(detailSpy).toHaveBeenCalledWith(visitForCompany.id));
    await waitFor(() =>
      expect(screen.getByText(t.guideShopVisitFieldPaidAt)).toBeInTheDocument(),
    );
    const visitDetailSheet = screen.getByText(t.guideShopVisitFieldPaidAt).closest('.sheet');
    expect(visitDetailSheet).toBeTruthy();
    expect(within(visitDetailSheet!).getByText(officialFull.displayName)).toBeInTheDocument();
    expect(within(visitDetailSheet!).queryByText(visitForCompany.id)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.edit })).not.toBeInTheDocument();
  });

  it('keeps personal companies visible when visits list fails', async () => {
    vi.spyOn(guideOsClient, 'listOfficialVisits').mockRejectedValue(
      new ApiError('temporarily_unavailable', 'down', 503),
    );

    renderPage();
    await waitForLoaded();
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    );
    await waitFor(() => expect(screen.getByText(officialFull.description!)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: t.guideShopVisitsAction }));
    await waitFor(() => expect(screen.getByText(t.guideShopVisitsLoadError)).toBeInTheDocument());
    expect(screen.getByText(activePlace.name)).toBeInTheDocument();
  });

  it('shows empty state when company has no matching visits', async () => {
    vi.spyOn(guideOsClient, 'listOfficialVisits').mockResolvedValue({
      visits: [visitOtherCompany],
      page: { nextCursor: null },
    });

    renderPage();
    await waitForLoaded();
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    );
    await waitFor(() => expect(screen.getByText(officialFull.description!)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: t.guideShopVisitsAction }));
    await waitFor(() => expect(screen.getByText(t.guideShopVisitsEmpty)).toBeInTheDocument());
  });
});

describe('GuideShop official points summary UI', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    __resetMockStore();
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([activePlace]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
    vi.spyOn(guideOsClient, 'listOfficialCompanies').mockResolvedValue({
      companies: [officialFull, officialWorkshop],
      page: { nextCursor: null },
    });
    vi.spyOn(guideOsClient, 'getOfficialCompany').mockResolvedValue(officialFull);
  });

  afterEach(() => {
    cleanup();
  });

  it('opens GuideShop points summary with company-scoped row and no opaque IDs', async () => {
    vi.spyOn(guideOsClient, 'getOfficialPointsSummary').mockResolvedValue({
      unit: 'PTS',
      pendingTotal: '12.50',
      creditedTotal: '4.00',
      companies: [
        {
          companyId: officialFull.id,
          displayName: officialFull.displayName,
          pendingTotal: '10.00',
          creditedTotal: '3.00',
        },
        {
          companyId: officialWorkshop.id,
          displayName: officialWorkshop.displayName,
          pendingTotal: '2.50',
          creditedTotal: '1.00',
        },
      ],
    });

    renderPage();
    await waitForLoaded();
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    );
    await waitFor(() => expect(screen.getByText(officialFull.description!)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: t.guideShopPointsAction }));

    await waitFor(() => expect(screen.getByText(t.guideShopPointsTitle)).toBeInTheDocument());
    const sheet = screen.getByText(t.guideShopPointsTitle).closest('.sheet');
    expect(sheet).toBeTruthy();
    expect(within(sheet!).getByText(t.guideShopOfficialBadge)).toBeInTheDocument();
    expect(within(sheet!).getByText('12.50 PTS')).toBeInTheDocument();
    expect(within(sheet!).getByText('4.00 PTS')).toBeInTheDocument();
    expect(within(sheet!).getByText(t.guideShopPointsCompanyBlock)).toBeInTheDocument();
    expect(within(sheet!).getByText('10.00 PTS')).toBeInTheDocument();
    expect(within(sheet!).getByText('3.00 PTS')).toBeInTheDocument();
    expect(within(sheet!).getAllByText(t.guideShopPointsPending).length).toBeGreaterThanOrEqual(2);
    expect(within(sheet!).queryByText(officialFull.id)).not.toBeInTheDocument();
    expect(within(sheet!).queryByText(officialWorkshop.id)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.guideShopAddCommission })).not.toBeInTheDocument();
  });

  it('keeps personal companies visible when points summary fails', async () => {
    vi.spyOn(guideOsClient, 'getOfficialPointsSummary').mockRejectedValue(
      new ApiError('temporarily_unavailable', 'down', 503),
    );

    renderPage();
    await waitForLoaded();
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    );
    await waitFor(() => expect(screen.getByText(officialFull.description!)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: t.guideShopPointsAction }));
    await waitFor(() => expect(screen.getByText(t.guideShopPointsLoadError)).toBeInTheDocument());
    expect(screen.getByText(activePlace.name)).toBeInTheDocument();
  });

  it('shows company-empty copy when summary has no row for current company', async () => {
    vi.spyOn(guideOsClient, 'getOfficialPointsSummary').mockResolvedValue({
      unit: 'PTS',
      pendingTotal: '2.50',
      creditedTotal: '1.00',
      companies: [
        {
          companyId: officialWorkshop.id,
          displayName: officialWorkshop.displayName,
          pendingTotal: '2.50',
          creditedTotal: '1.00',
        },
      ],
    });

    renderPage();
    await waitForLoaded();
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    );
    await waitFor(() => expect(screen.getByText(officialFull.description!)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: t.guideShopPointsAction }));
    await waitFor(() =>
      expect(screen.getByText(t.guideShopPointsCompanyEmpty)).toBeInTheDocument(),
    );
    expect(screen.getByText('2.50 PTS')).toBeInTheDocument();
  });
});

describe('GuideShop official sales UI', () => {
  const saleForCompany = {
    id: 'gssale_silk_01',
    visitId: 'gsvis_silk_01',
    companyId: officialFull.id,
    amount: '125.40',
    currency: 'USD',
    status: 'active',
    paymentMethod: 'card',
    comment: 'Group textiles',
    categoryId: 'gscat_textiles',
    categoryName: 'Textiles',
    createdAt: '2026-08-10T12:00:00Z',
    updatedAt: '2026-08-10T12:00:00Z',
  };

  const saleOtherCompany = {
    id: 'gssale_khiva_03',
    visitId: 'gsvis_khiva_03',
    companyId: officialWorkshop.id,
    amount: '72.25',
    currency: 'USD',
    status: 'active',
    paymentMethod: 'transfer',
    comment: null,
    categoryId: null,
    categoryName: 'Category unavailable',
    createdAt: '2026-08-20T09:15:00Z',
    updatedAt: '2026-08-20T09:15:00Z',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    __resetMockStore();
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([activePlace]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
    vi.spyOn(guideOsClient, 'listOfficialCompanies').mockResolvedValue({
      companies: [officialFull, officialWorkshop],
      page: { nextCursor: null },
    });
    vi.spyOn(guideOsClient, 'getOfficialCompany').mockResolvedValue(officialFull);
  });

  afterEach(() => {
    cleanup();
  });

  it('opens company-scoped GuideShop sales list and detail without opaque IDs', async () => {
    vi.spyOn(guideOsClient, 'listOfficialSales').mockResolvedValue({
      sales: [saleForCompany, saleOtherCompany],
      page: { nextCursor: null },
    });
    const detailSpy = vi
      .spyOn(guideOsClient, 'getOfficialSale')
      .mockResolvedValue(saleForCompany);

    renderPage();
    await waitForLoaded();
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    );
    await waitFor(() => expect(screen.getByText(officialFull.description!)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: t.guideShopSalesAction }));

    await waitFor(() => expect(screen.getByText(t.guideShopSalesTitle)).toBeInTheDocument());
    const listSheet = screen.getByText(t.guideShopSalesTitle).closest('.sheet');
    expect(listSheet).toBeTruthy();
    expect(within(listSheet!).getByText('125.40 USD')).toBeInTheDocument();
    expect(within(listSheet!).getByText('Textiles')).toBeInTheDocument();
    expect(within(listSheet!).getByText(t.guideShopSalePaymentCard)).toBeInTheDocument();
    expect(within(listSheet!).queryByText('72.25 USD')).not.toBeInTheDocument();
    expect(within(listSheet!).queryByText(saleForCompany.id)).not.toBeInTheDocument();
    expect(within(listSheet!).queryByText(saleForCompany.visitId)).not.toBeInTheDocument();
    expect(within(listSheet!).queryByText(officialFull.id)).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenSale('125.40 USD'),
      }),
    );
    await waitFor(() => expect(detailSpy).toHaveBeenCalledWith(saleForCompany.id));
    await waitFor(() =>
      expect(screen.getByText(t.guideShopSaleFieldComment)).toBeInTheDocument(),
    );
    const detailSheet = screen.getByText(t.guideShopSaleFieldComment).closest('.sheet');
    expect(detailSheet).toBeTruthy();
    expect(within(detailSheet!).getByText('Group textiles')).toBeInTheDocument();
    expect(within(detailSheet!).queryByText(saleForCompany.id)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.guideShopAddCommission })).not.toBeInTheDocument();
  });

  it('keeps personal companies visible when sales list fails', async () => {
    vi.spyOn(guideOsClient, 'listOfficialSales').mockRejectedValue(
      new ApiError('temporarily_unavailable', 'down', 503),
    );

    renderPage();
    await waitForLoaded();
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    );
    await waitFor(() => expect(screen.getByText(officialFull.description!)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: t.guideShopSalesAction }));
    await waitFor(() => expect(screen.getByText(t.guideShopSalesLoadError)).toBeInTheDocument());
    expect(screen.getByText(activePlace.name)).toBeInTheDocument();
  });

  it('shows empty state when company has no matching sales', async () => {
    vi.spyOn(guideOsClient, 'listOfficialSales').mockResolvedValue({
      sales: [saleOtherCompany],
      page: { nextCursor: null },
    });

    renderPage();
    await waitForLoaded();
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    );
    await waitFor(() => expect(screen.getByText(officialFull.description!)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: t.guideShopSalesAction }));
    await waitFor(() => expect(screen.getByText(t.guideShopSalesEmpty)).toBeInTheDocument());
  });
});

describe('GuideShop official payout history UI', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    __resetMockStore();
    vi.spyOn(guideOsClient, 'listPersonalPlaces').mockResolvedValue([activePlace]);
    vi.spyOn(guideOsClient, 'listPersonalCommissions').mockResolvedValue([]);
    vi.spyOn(guideOsClient, 'listOfficialCompanies').mockResolvedValue({
      companies: [officialFull, officialWorkshop],
      page: { nextCursor: null },
    });
    vi.spyOn(guideOsClient, 'getOfficialCompany').mockResolvedValue(officialFull);
    vi.spyOn(guideOsClient, 'getOfficialPointsSummary').mockResolvedValue({
      unit: 'PTS',
      pendingTotal: '12.50',
      creditedTotal: '4.00',
      companies: [
        {
          companyId: officialFull.id,
          displayName: officialFull.displayName,
          pendingTotal: '10.00',
          creditedTotal: '3.00',
        },
      ],
    });
  });

  afterEach(() => {
    cleanup();
  });

  it('opens history from points sheet with company-scoped PTS rows and no opaque IDs', async () => {
    vi.spyOn(guideOsClient, 'listOfficialHistory').mockResolvedValue({
      history: [
        {
          id: 'gspay_silk_01',
          pointsAccrualId: 'gsacc_silk_01',
          companyId: officialFull.id,
          visitId: 'gsvis_silk_01',
          amount: '3.00',
          unit: 'PTS',
          paidAt: '2026-08-12T10:00:00Z',
          createdAt: '2026-08-12T10:00:00Z',
        },
        {
          id: 'gspay_khiva_02',
          pointsAccrualId: 'gsacc_khiva_02',
          companyId: officialWorkshop.id,
          visitId: 'gsvis_khiva_03',
          amount: '1.00',
          unit: 'PTS',
          paidAt: '2026-08-21T08:00:00Z',
          createdAt: '2026-08-21T08:00:00Z',
        },
      ],
      page: { nextCursor: null },
    });

    renderPage();
    await waitForLoaded();
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    );
    await waitFor(() => expect(screen.getByText(officialFull.description!)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: t.guideShopPointsAction }));
    await waitFor(() => expect(screen.getByText(t.guideShopPointsTitle)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: t.guideShopHistoryAction }));

    await waitFor(() => expect(screen.getByText(t.guideShopHistoryTitle)).toBeInTheDocument());
    const sheet = screen.getByText(t.guideShopHistoryTitle).closest('.sheet');
    expect(sheet).toBeTruthy();
    expect(within(sheet!).getByText(t.guideShopOfficialBadge)).toBeInTheDocument();
    expect(within(sheet!).getByText('3.00 PTS')).toBeInTheDocument();
    expect(within(sheet!).getAllByText(officialFull.displayName).length).toBeGreaterThanOrEqual(1);
    expect(within(sheet!).queryByText('1.00 PTS')).not.toBeInTheDocument();
    expect(within(sheet!).queryByText('gspay_silk_01')).not.toBeInTheDocument();
    expect(within(sheet!).queryByText('gsacc_silk_01')).not.toBeInTheDocument();
    expect(within(sheet!).queryByText(officialFull.id)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.guideShopAddCommission })).not.toBeInTheDocument();
  });

  it('keeps personal companies visible when history fails', async () => {
    vi.spyOn(guideOsClient, 'listOfficialHistory').mockRejectedValue(
      new ApiError('temporarily_unavailable', 'down', 503),
    );

    renderPage();
    await waitForLoaded();
    fireEvent.click(
      screen.getByRole('button', {
        name: t.guideShopOpenOfficialCompany(officialFull.displayName),
      }),
    );
    await waitFor(() => expect(screen.getByText(officialFull.description!)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: t.guideShopPointsAction }));
    await waitFor(() => expect(screen.getByText(t.guideShopHistoryAction)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: t.guideShopHistoryAction }));
    await waitFor(() => expect(screen.getByText(t.guideShopHistoryLoadError)).toBeInTheDocument());
    expect(screen.getByText(activePlace.name)).toBeInTheDocument();
  });
});

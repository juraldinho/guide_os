// @ts-nocheck — read CSS source at runtime; Node built-ins are not in app tsconfig.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { PersonalPlace } from '@/api/types';
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

function renderPage() {
  return render(<GuideShopPage />);
}

async function waitForLoaded() {
  await waitFor(() => {
    expect(screen.queryByText(t.guideShopLoading)).not.toBeInTheDocument();
  });
}

describe('GuideShop personal places UI', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    __resetMockStore();
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
    expect(screen.getByRole('status')).toHaveTextContent(t.guideShopLoading);
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
    expect(screen.getByText(t.guideShopComingSoon)).toBeInTheDocument();
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
    expect(screen.getByRole('status')).toBeInTheDocument();
    rejectList?.(new Error('fail'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('CSS prevents page overflow and keeps touch targets', () => {
    expect(GLOBAL_CSS).toContain('.guideshop-page');
    expect(GLOBAL_CSS).toContain('overflow-x: hidden');
    expect(GLOBAL_CSS).toContain('.guideshop-place-card');
    expect(GLOBAL_CSS).toContain('min-height: 44px');
  });
});

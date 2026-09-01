import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import type { GuideProfile } from '@/api/types';
import { ToastProvider } from '@/components/ui/Toast';
import { useCalendar } from '@/features/calendar/CalendarContext';
import {
  GEOGRAPHY_OPTIONS,
  ProfessionalProfileEditor,
} from '@/features/settings/ProfessionalProfileEditor';
import { SettingsOverlay } from '@/features/settings/SettingsOverlay';
import { t } from '@/i18n/strings';

vi.mock('@/features/calendar/CalendarContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/calendar/CalendarContext')>();
  return {
    ...actual,
    useCalendar: vi.fn(),
  };
});

const baseProfile: GuideProfile = {
  name: 'Алишер Каримов',
  telegramId: '3847291056',
  types: [],
  languages: [],
  notifications: { enabled: true, time: '08:00' },
};

const configuredProfile: GuideProfile = {
  ...baseProfile,
  types: [
    {
      type: 'local',
      label: 'Локальный гид',
      geo: ['Самарканд'],
      allUzbekistan: false,
    },
    {
      type: 'route',
      label: 'Маршрутный гид',
      geo: [],
      allUzbekistan: true,
    },
    {
      type: 'accompanying',
      label: 'Сопровождающий гид',
      geo: ['Бухара', 'Хива'],
      allUzbekistan: false,
    },
  ],
  languages: ['Русский', 'Английский'],
};

function renderEditor(
  profile: GuideProfile,
  saveProfessionalProfile = vi.fn().mockResolvedValue(true),
) {
  return render(
    <ProfessionalProfileEditor profile={profile} saveProfessionalProfile={saveProfessionalProfile} />,
  );
}

function openEditor() {
  fireEvent.click(screen.getByRole('button', { name: t.profFillProfile }));
}

function openEditorFromConfigured() {
  fireEvent.click(screen.getByRole('button', { name: t.profEditProfile }));
}

function toggleType(label: string) {
  fireEvent.click(screen.getByLabelText(label));
}

function localFieldset() {
  return screen.getByText(t.profLocalGeoLegend).closest('fieldset');
}

function routeFieldset() {
  return screen.getByText(t.profRouteGeoLegend).closest('fieldset');
}

function accompanyingFieldset() {
  return screen.getByText(t.profAccompanyingGeoLegend).closest('fieldset');
}

function selectLocalGeo(geo: string) {
  const fieldset = localFieldset();
  const label = fieldset?.querySelector(`input[value="${geo}"]`)?.closest('label');
  if (!label) throw new Error(`Local geo not found: ${geo}`);
  fireEvent.click(label);
}

function toggleRouteGeo(geo: string) {
  const fieldset = routeFieldset();
  const labels = fieldset?.querySelectorAll('label') ?? [];
  const label = Array.from(labels).find((el) => el.textContent?.includes(geo));
  if (!label) throw new Error(`Route geo not found: ${geo}`);
  fireEvent.click(label);
}

function toggleAccompanyingGeo(geo: string) {
  const fieldset = accompanyingFieldset();
  const labels = fieldset?.querySelectorAll('label') ?? [];
  const label = Array.from(labels).find((el) => el.textContent?.includes(geo));
  if (!label) throw new Error(`Accompanying geo not found: ${geo}`);
  fireEvent.click(label);
}

function toggleAllUzbekistanInRoute() {
  const checkbox = routeFieldset()?.querySelector('input[type="checkbox"]') as HTMLInputElement;
  fireEvent.click(checkbox);
}

function toggleAllUzbekistanInAccompanying() {
  const checkbox = accompanyingFieldset()?.querySelector('input[type="checkbox"]') as HTMLInputElement;
  fireEvent.click(checkbox);
}

function clickSave() {
  fireEvent.click(screen.getByRole('button', { name: t.save }));
}

function selectPresetLanguage(lang: string) {
  fireEvent.click(screen.getByRole('button', { name: lang }));
}

function addCustomLanguage(value: string) {
  fireEvent.change(screen.getByLabelText(t.profOtherLanguage), { target: { value } });
  fireEvent.click(screen.getByRole('button', { name: t.profAddLanguage }));
}

describe('ProfessionalProfileEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe('summary mode', () => {
    it('shows empty state and fill action', () => {
      renderEditor(baseProfile);
      expect(screen.getByText(t.profProfileEmpty)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: t.profFillProfile })).toBeInTheDocument();
    });

    it('shows configured types, geography, all-uzbekistan, and languages', () => {
      renderEditor(configuredProfile);
      expect(screen.getByText('Локальный гид')).toBeInTheDocument();
      expect(screen.getByText('Самарканд')).toBeInTheDocument();
      expect(screen.getByText(t.profAllUzbekistan)).toBeInTheDocument();
      expect(screen.getByText('Бухара, Хива')).toBeInTheDocument();
      expect(screen.getByText('Русский, Английский')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: t.profEditProfile })).toBeInTheDocument();
    });

    it('opens editor with current values via Изменить', () => {
      renderEditor(configuredProfile);
      openEditorFromConfigured();
      expect(screen.getByLabelText(t.profGuideTypeLocal)).toBeChecked();
      expect(screen.getByLabelText(t.profGuideTypeRoute)).toBeChecked();
      expect(screen.getByLabelText(t.profGuideTypeAccompanying)).toBeChecked();
      expect(screen.getByRole('button', { name: t.save })).toBeInTheDocument();
    });

    it('shows types-only summary with Изменить', () => {
      const typesOnlyProfile: GuideProfile = {
        ...baseProfile,
        types: [
          {
            type: 'local',
            label: 'Локальный гид',
            geo: ['Самарканд'],
            allUzbekistan: false,
          },
        ],
        languages: [],
      };
      renderEditor(typesOnlyProfile);
      expect(screen.queryByText(t.profProfileEmpty)).not.toBeInTheDocument();
      expect(screen.getByText('Локальный гид')).toBeInTheDocument();
      expect(screen.getByText('Самарканд')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: t.profEditProfile })).toBeInTheDocument();
    });

    it('shows languages-only summary with Изменить', () => {
      const languagesOnlyProfile: GuideProfile = {
        ...baseProfile,
        types: [],
        languages: ['Русский', 'Английский'],
      };
      renderEditor(languagesOnlyProfile);
      expect(screen.queryByText(t.profProfileEmpty)).not.toBeInTheDocument();
      expect(screen.getByText('Русский, Английский')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: t.profEditProfile })).toBeInTheDocument();
    });
  });

  describe('type and geography', () => {
    it('allows multiple guide types', () => {
      renderEditor(baseProfile);
      openEditor();
      toggleType(t.profGuideTypeLocal);
      toggleType(t.profGuideTypeRoute);
      toggleType(t.profGuideTypeAccompanying);
      expect(screen.getByLabelText(t.profGuideTypeLocal)).toBeChecked();
      expect(screen.getByLabelText(t.profGuideTypeRoute)).toBeChecked();
      expect(screen.getByLabelText(t.profGuideTypeAccompanying)).toBeChecked();
    });

    it('local guide allows exactly one geography selection', () => {
      renderEditor(baseProfile);
      openEditor();
      toggleType(t.profGuideTypeLocal);
      selectLocalGeo('Самарканд');
      selectLocalGeo('Ташкент');
      const checked = localFieldset()?.querySelectorAll('input[type="radio"]:checked');
      expect(checked?.length).toBe(1);
      expect((checked?.[0] as HTMLInputElement)?.value).toBe('Ташкент');
    });

    it('route allows multiple geography values', () => {
      renderEditor(baseProfile);
      openEditor();
      toggleType(t.profGuideTypeRoute);
      toggleRouteGeo('Самарканд');
      toggleRouteGeo('Бухара');
      expect(routeFieldset()?.querySelectorAll('input[type="checkbox"]:checked').length).toBe(2);
    });

    it('route all-uzbekistan clears individual route geography', () => {
      renderEditor(baseProfile);
      openEditor();
      toggleType(t.profGuideTypeRoute);
      toggleRouteGeo('Самарканд');
      toggleAllUzbekistanInRoute();
      expect(routeFieldset()?.querySelectorAll('input[type="checkbox"]:checked').length).toBe(1);
      toggleAllUzbekistanInRoute();
      expect(routeFieldset()?.querySelectorAll('input[type="checkbox"]:checked').length).toBe(0);
    });

    it('accompanying geography is independent from route geography', () => {
      renderEditor(baseProfile);
      openEditor();
      toggleType(t.profGuideTypeRoute);
      toggleType(t.profGuideTypeAccompanying);
      toggleRouteGeo('Самарканд');
      toggleAccompanyingGeo('Бухара');
      expect(routeFieldset()?.querySelectorAll('input[type="checkbox"]:checked').length).toBe(1);
      expect(accompanyingFieldset()?.querySelectorAll('input[type="checkbox"]:checked').length).toBe(1);
    });

    it('deselecting a type removes it from outgoing payload', async () => {
      const saveProfessionalProfile = vi.fn().mockResolvedValue(true);
      renderEditor(configuredProfile, saveProfessionalProfile);
      openEditorFromConfigured();
      toggleType(t.profGuideTypeAccompanying);
      fireEvent.click(screen.getByRole('button', { name: t.save }));
      await waitFor(() => expect(saveProfessionalProfile).toHaveBeenCalled());
      const [types] = saveProfessionalProfile.mock.calls[0];
      expect(types.map((item: { type: string }) => item.type)).toEqual(['local', 'route']);
    });

    it('re-selecting a type starts with empty draft', () => {
      renderEditor(configuredProfile);
      openEditorFromConfigured();
      toggleType(t.profGuideTypeRoute);
      toggleType(t.profGuideTypeRoute);
      expect(routeFieldset()?.querySelectorAll('input[type="checkbox"]:checked').length).toBe(0);
    });
  });

  describe('languages', () => {
    it('allows multiple preset languages', () => {
      renderEditor(baseProfile);
      openEditor();
      toggleType(t.profGuideTypeLocal);
      selectLocalGeo(GEOGRAPHY_OPTIONS[0]);
      selectPresetLanguage('Русский');
      selectPresetLanguage('Английский');
      expect(screen.getByRole('button', { name: 'Русский' })).toHaveAttribute('aria-pressed', 'true');
      expect(screen.getByRole('button', { name: 'Английский' })).toHaveAttribute('aria-pressed', 'true');
    });

    it('adds custom language with accessible removal label', () => {
      renderEditor(baseProfile);
      openEditor();
      addCustomLanguage('Польский');
      const btn = screen.getByRole('button', { name: t.profRemoveLanguage('Польский') });
      expect(btn).toHaveTextContent('Польский');
      expect(btn).toHaveAttribute('aria-pressed', 'true');
    });

    it('trims custom language', async () => {
      const saveProfessionalProfile = vi.fn().mockResolvedValue(true);
      renderEditor(baseProfile, saveProfessionalProfile);
      openEditor();
      toggleType(t.profGuideTypeLocal);
      selectLocalGeo('Самарканд');
      addCustomLanguage('  Польский  ');
      fireEvent.click(screen.getByRole('button', { name: t.save }));
      await waitFor(() => expect(saveProfessionalProfile).toHaveBeenCalled());
      const [, languages] = saveProfessionalProfile.mock.calls[0];
      expect(languages).toEqual(['Польский']);
    });

    it('rejects duplicate language case-insensitively', () => {
      renderEditor(baseProfile);
      openEditor();
      selectPresetLanguage('Русский');
      addCustomLanguage('русский');
      expect(screen.getByText(t.profValDuplicateLanguage)).toBeInTheDocument();
    });

    it('rejects custom language over 50 characters', () => {
      renderEditor(baseProfile);
      openEditor();
      addCustomLanguage('а'.repeat(51));
      expect(screen.getByText(t.profValLanguageTooLong)).toBeInTheDocument();
    });

    it('rejects more than 20 languages', () => {
      renderEditor(baseProfile);
      openEditor();
      for (let i = 0; i < 20; i += 1) {
        addCustomLanguage(`Язык ${i}`);
      }
      addCustomLanguage('Ещё один');
      expect(screen.getByText(t.profValLanguageMax20)).toBeInTheDocument();
    });

    it('removes a selected language', () => {
      renderEditor(baseProfile);
      openEditor();
      selectPresetLanguage('Русский');
      fireEvent.click(screen.getByRole('button', { name: 'Русский' }));
      expect(screen.getByRole('button', { name: 'Русский' })).toHaveAttribute('aria-pressed', 'false');
    });
  });

  describe('all-uzbekistan payloads', () => {
    it('sends route all-uzbekistan with empty geo', async () => {
      const saveProfessionalProfile = vi.fn().mockResolvedValue(true);
      renderEditor(baseProfile, saveProfessionalProfile);
      openEditor();
      toggleType(t.profGuideTypeRoute);
      toggleAllUzbekistanInRoute();
      selectPresetLanguage('Русский');
      clickSave();
      await waitFor(() => expect(saveProfessionalProfile).toHaveBeenCalled());
      const [types] = saveProfessionalProfile.mock.calls[0];
      expect(types).toEqual([
        { type: 'route', geo: [], allUzbekistan: true },
      ]);
    });

    it('sends accompanying all-uzbekistan with empty geo', async () => {
      const saveProfessionalProfile = vi.fn().mockResolvedValue(true);
      renderEditor(baseProfile, saveProfessionalProfile);
      openEditor();
      toggleType(t.profGuideTypeAccompanying);
      toggleAllUzbekistanInAccompanying();
      selectPresetLanguage('Русский');
      clickSave();
      await waitFor(() => expect(saveProfessionalProfile).toHaveBeenCalled());
      const [types] = saveProfessionalProfile.mock.calls[0];
      expect(types).toEqual([
        { type: 'accompanying', geo: [], allUzbekistan: true },
      ]);
    });

    it('keeps route and accompanying drafts independent in payload', async () => {
      const saveProfessionalProfile = vi.fn().mockResolvedValue(true);
      renderEditor(baseProfile, saveProfessionalProfile);
      openEditor();
      toggleType(t.profGuideTypeRoute);
      toggleType(t.profGuideTypeAccompanying);
      toggleAllUzbekistanInRoute();
      toggleAccompanyingGeo('Бухара');
      toggleAccompanyingGeo('Хива');
      selectPresetLanguage('Русский');
      clickSave();
      await waitFor(() => expect(saveProfessionalProfile).toHaveBeenCalled());
      const [types] = saveProfessionalProfile.mock.calls[0];
      expect(types).toEqual([
        { type: 'route', geo: [], allUzbekistan: true },
        { type: 'accompanying', geo: ['Бухара', 'Хива'], allUzbekistan: false },
      ]);
    });
  });

  describe('save, cancel, and errors', () => {
    it('save sends only GuideTypeInput fields and languages', async () => {
      const saveProfessionalProfile = vi.fn().mockResolvedValue(true);
      renderEditor(baseProfile, saveProfessionalProfile);
      openEditor();
      toggleType(t.profGuideTypeLocal);
      selectLocalGeo('Самарканд');
      selectPresetLanguage('Русский');
      fireEvent.click(screen.getByRole('button', { name: t.save }));
      await waitFor(() => expect(saveProfessionalProfile).toHaveBeenCalled());
      const [types, languages] = saveProfessionalProfile.mock.calls[0];
      expect(types).toEqual([
        { type: 'local', geo: ['Самарканд'], allUzbekistan: false },
      ]);
      expect(languages).toEqual(['Русский']);
      expect(types[0]).not.toHaveProperty('label');
    });

    it('payload omits label, telegramId, name, and notifications', async () => {
      const saveProfessionalProfile = vi.fn().mockResolvedValue(true);
      renderEditor(configuredProfile, saveProfessionalProfile);
      openEditorFromConfigured();
      fireEvent.click(screen.getByRole('button', { name: t.save }));
      await waitFor(() => expect(saveProfessionalProfile).toHaveBeenCalled());
      const serialized = JSON.stringify(saveProfessionalProfile.mock.calls[0]);
      expect(serialized).not.toContain('telegramId');
      expect(serialized).not.toContain('"label"');
      expect(serialized).not.toContain('notifications');
      expect(serialized).not.toContain(baseProfile.name);
    });

    it('successful save closes editor and updates summary', async () => {
      const updatedProfile: GuideProfile = {
        ...baseProfile,
        types: [
          {
            type: 'local',
            label: 'Локальный гид',
            geo: ['Ташкент'],
            allUzbekistan: false,
          },
        ],
        languages: ['Узбекский'],
      };
      const saveProfessionalProfile = vi.fn().mockResolvedValue(true);
      const { rerender } = renderEditor(baseProfile, saveProfessionalProfile);
      openEditor();
      toggleType(t.profGuideTypeLocal);
      selectLocalGeo('Ташкент');
      selectPresetLanguage('Узбекский');
      fireEvent.click(screen.getByRole('button', { name: t.save }));
      await waitFor(() => expect(saveProfessionalProfile).toHaveBeenCalled());
      rerender(
        <ProfessionalProfileEditor profile={updatedProfile} saveProfessionalProfile={saveProfessionalProfile} />,
      );
      await waitFor(() => {
        expect(screen.getByRole('button', { name: t.profEditProfile })).toBeInTheDocument();
      });
      expect(screen.getByText('Ташкент')).toBeInTheDocument();
      expect(screen.getByText('Узбекский')).toBeInTheDocument();
    });

    it('failed save keeps editor open with draft', async () => {
      const saveProfessionalProfile = vi.fn().mockResolvedValue(false);
      renderEditor(baseProfile, saveProfessionalProfile);
      openEditor();
      toggleType(t.profGuideTypeLocal);
      selectLocalGeo('Самарканд');
      selectPresetLanguage('Русский');
      fireEvent.click(screen.getByRole('button', { name: t.save }));
      await waitFor(() => expect(saveProfessionalProfile).toHaveBeenCalled());
      expect(screen.getByRole('button', { name: t.save })).toBeInTheDocument();
      expect(screen.getByLabelText(t.profGuideTypeLocal)).toBeChecked();
    });

    it('disables save during in-flight request', async () => {
      let resolveSave: ((value: boolean) => void) | undefined;
      const saveProfessionalProfile = vi.fn(
        () =>
          new Promise<boolean>((resolve) => {
            resolveSave = resolve;
          }),
      );
      renderEditor(baseProfile, saveProfessionalProfile);
      openEditor();
      toggleType(t.profGuideTypeLocal);
      selectLocalGeo('Самарканд');
      selectPresetLanguage('Русский');
      fireEvent.click(screen.getByRole('button', { name: t.save }));
      expect(screen.getByRole('button', { name: t.profSaving })).toBeDisabled();
      resolveSave?.(true);
      await waitFor(() => {
        expect(screen.queryByRole('button', { name: t.profSaving })).not.toBeInTheDocument();
      });
    });

    it('cancel discards draft changes', () => {
      renderEditor(configuredProfile);
      openEditorFromConfigured();
      toggleType(t.profGuideTypeLocal);
      fireEvent.click(screen.getByRole('button', { name: t.cancel }));
      expect(screen.getByRole('button', { name: t.profEditProfile })).toBeInTheDocument();
      openEditorFromConfigured();
      expect(screen.getByLabelText(t.profGuideTypeLocal)).toBeChecked();
    });

    it('closing and reopening settings does not preserve unsaved draft', () => {
      const saveProfessionalProfile = vi.fn().mockResolvedValue(true);
      const { unmount } = renderEditor(configuredProfile, saveProfessionalProfile);
      openEditorFromConfigured();
      toggleType(t.profGuideTypeLocal);
      unmount();
      renderEditor(configuredProfile, saveProfessionalProfile);
      expect(screen.getByRole('button', { name: t.profEditProfile })).toBeInTheDocument();
      openEditorFromConfigured();
      expect(screen.getByLabelText(t.profGuideTypeLocal)).toBeChecked();
    });

    it('validation blocks save when required fields missing', async () => {
      const saveProfessionalProfile = vi.fn().mockResolvedValue(true);
      renderEditor(baseProfile, saveProfessionalProfile);
      openEditor();
      toggleType(t.profGuideTypeLocal);
      clickSave();
      expect(screen.getByText(t.profValLocalGeo)).toBeInTheDocument();
      expect(saveProfessionalProfile).not.toHaveBeenCalled();
    });

    it('blocks save with no selected guide type', async () => {
      const saveProfessionalProfile = vi.fn().mockResolvedValue(true);
      renderEditor(baseProfile, saveProfessionalProfile);
      openEditor();
      clickSave();
      expect(screen.getByText(t.profValNoType)).toBeInTheDocument();
      expect(saveProfessionalProfile).not.toHaveBeenCalled();
    });

    it('blocks save when local type has no city', async () => {
      const saveProfessionalProfile = vi.fn().mockResolvedValue(true);
      renderEditor(baseProfile, saveProfessionalProfile);
      openEditor();
      toggleType(t.profGuideTypeLocal);
      selectPresetLanguage('Русский');
      clickSave();
      expect(screen.getByText(t.profValLocalGeo)).toBeInTheDocument();
      expect(saveProfessionalProfile).not.toHaveBeenCalled();
    });

    it('blocks save when route type has no geography', async () => {
      const saveProfessionalProfile = vi.fn().mockResolvedValue(true);
      renderEditor(baseProfile, saveProfessionalProfile);
      openEditor();
      toggleType(t.profGuideTypeRoute);
      selectPresetLanguage('Русский');
      clickSave();
      expect(screen.getByText(t.profValRouteGeo)).toBeInTheDocument();
      expect(saveProfessionalProfile).not.toHaveBeenCalled();
    });

    it('blocks save when accompanying type has no geography', async () => {
      const saveProfessionalProfile = vi.fn().mockResolvedValue(true);
      renderEditor(baseProfile, saveProfessionalProfile);
      openEditor();
      toggleType(t.profGuideTypeAccompanying);
      selectPresetLanguage('Русский');
      clickSave();
      expect(screen.getByText(t.profValAccompanyingGeo)).toBeInTheDocument();
      expect(saveProfessionalProfile).not.toHaveBeenCalled();
    });

    it('blocks save when type and geography are valid but no language selected', async () => {
      const saveProfessionalProfile = vi.fn().mockResolvedValue(true);
      renderEditor(baseProfile, saveProfessionalProfile);
      openEditor();
      toggleType(t.profGuideTypeLocal);
      selectLocalGeo('Самарканд');
      clickSave();
      expect(screen.getByText(t.profValNoLanguage)).toBeInTheDocument();
      expect(saveProfessionalProfile).not.toHaveBeenCalled();
    });

    it('rejected save promise keeps editor open and preserves draft', async () => {
      const saveProfessionalProfile = vi.fn().mockRejectedValue(new Error('network fail'));
      renderEditor(baseProfile, saveProfessionalProfile);
      openEditor();
      toggleType(t.profGuideTypeLocal);
      selectLocalGeo('Самарканд');
      selectPresetLanguage('Русский');
      clickSave();
      await waitFor(() => expect(saveProfessionalProfile).toHaveBeenCalled());
      expect(screen.getByRole('button', { name: t.save })).toBeInTheDocument();
      expect(screen.getByLabelText(t.profGuideTypeLocal)).toBeChecked();
      expect(screen.getByRole('button', { name: 'Русский' })).toHaveAttribute('aria-pressed', 'true');
    });
  });
});

describe('SettingsOverlay regression', () => {
  const mockCalendar = {
    profile: configuredProfile,
    themeMode: 'telegram' as const,
    closeSettings: vi.fn(),
    updateProfileName: vi.fn(),
    copyTelegramId: vi.fn(),
    saveProfessionalProfile: vi.fn(),
    toggleNotif: vi.fn(),
    updateNotifTime: vi.fn(),
    setThemeMode: vi.fn(),
    openDemoStates: vi.fn(),
  };

  beforeEach(() => {
    vi.mocked(useCalendar).mockReturnValue(mockCalendar as never);
  });

  afterEach(() => {
    cleanup();
  });

  it('keeps name editing, telegram id, notifications, interface language, and theme controls', () => {
    render(
      <ToastProvider>
        <SettingsOverlay />
      </ToastProvider>,
    );

    expect(screen.getByLabelText(t.settingsDisplayName)).toHaveValue(configuredProfile.name);
    expect(screen.getByText(configuredProfile.telegramId)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.copyTelegramId })).toBeInTheDocument();
    expect(screen.getByText(t.settingsReminders)).toBeInTheDocument();
    expect(screen.getByLabelText(t.settingsReminderTime)).toHaveValue('08:00');
    expect(screen.getByText(t.settingsLanguage)).toBeInTheDocument();
    expect(screen.getByText(t.settingsLanguageValue)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.themeTelegram })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.themeLight })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.themeDark })).toBeInTheDocument();
  });
});

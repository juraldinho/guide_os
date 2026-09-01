import { useCallback, useMemo, useState } from 'react';
import type { GuideProfile, GuideTypeCode, GuideTypeInput } from '@/api/types';
import { t } from '@/i18n/strings';

export const GEOGRAPHY_OPTIONS = [
  'Самарканд',
  'Ташкент',
  'Бухара',
  'Хива',
  'Каракалпакстан',
  'Сурхандарья',
  'Шахрисабз',
  'Ферганская долина',
] as const;

export const PRESET_TOUR_LANGUAGES = [
  'Русский',
  'Узбекский',
  'Английский',
  'Французский',
  'Немецкий',
  'Испанский',
  'Итальянский',
  'Турецкий',
  'Китайский',
  'Японский',
  'Корейский',
  'Арабский',
] as const;

const TYPE_ORDER: GuideTypeCode[] = ['local', 'route', 'accompanying'];

const GUIDE_TYPE_LABELS: Record<GuideTypeCode, string> = {
  local: t.profGuideTypeLocal,
  route: t.profGuideTypeRoute,
  accompanying: t.profGuideTypeAccompanying,
};

type TypeDraft = { geo: string[]; allUzbekistan: boolean };
type TypeDraftMap = Partial<Record<GuideTypeCode, TypeDraft>>;

type FieldErrors = {
  types?: string;
  localGeo?: string;
  routeGeo?: string;
  accompanyingGeo?: string;
  languages?: string;
  customLanguage?: string;
};

function isProfileConfigured(profile: GuideProfile): boolean {
  return profile.types.length > 0 || profile.languages.length > 0;
}

function draftFromProfile(profile: GuideProfile): { selectedTypes: GuideTypeCode[]; typeDrafts: TypeDraftMap; languages: string[] } {
  const typeDrafts: TypeDraftMap = {};
  const selectedTypes: GuideTypeCode[] = [];
  for (const item of profile.types) {
    selectedTypes.push(item.type);
    typeDrafts[item.type] = { geo: [...item.geo], allUzbekistan: item.allUzbekistan };
  }
  return { selectedTypes, typeDrafts, languages: [...profile.languages] };
}

function formatGeography(draft: TypeDraft): string {
  if (draft.allUzbekistan) return t.profAllUzbekistan;
  return draft.geo.join(', ');
}

function normalizeLanguage(value: string): string {
  return value.trim().toLowerCase();
}

function hasLanguage(languages: string[], candidate: string): boolean {
  const normalized = normalizeLanguage(candidate);
  return languages.some((lang) => normalizeLanguage(lang) === normalized);
}

function buildTypeInputs(selectedTypes: GuideTypeCode[], typeDrafts: TypeDraftMap): GuideTypeInput[] {
  return selectedTypes.map((type) => {
    const draft = typeDrafts[type] ?? { geo: [], allUzbekistan: false };
    return {
      type,
      geo: draft.allUzbekistan ? [] : [...draft.geo],
      allUzbekistan: draft.allUzbekistan,
    };
  });
}

interface ProfessionalProfileEditorProps {
  profile: GuideProfile;
  saveProfessionalProfile: (types: GuideTypeInput[], languages: string[]) => Promise<boolean>;
}

export function ProfessionalProfileEditor({
  profile,
  saveProfessionalProfile,
}: ProfessionalProfileEditorProps) {
  const [mode, setMode] = useState<'summary' | 'edit'>('summary');
  const [selectedTypes, setSelectedTypes] = useState<GuideTypeCode[]>([]);
  const [typeDrafts, setTypeDrafts] = useState<TypeDraftMap>({});
  const [draftLanguages, setDraftLanguages] = useState<string[]>([]);
  const [customLanguageInput, setCustomLanguageInput] = useState('');
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState(false);

  const configured = isProfileConfigured(profile);

  const openEditor = useCallback(() => {
    const draft = draftFromProfile(profile);
    setSelectedTypes(draft.selectedTypes);
    setTypeDrafts(draft.typeDrafts);
    setDraftLanguages(draft.languages);
    setCustomLanguageInput('');
    setFieldErrors({});
    setMode('edit');
  }, [profile]);

  const cancelEdit = useCallback(() => {
    const draft = draftFromProfile(profile);
    setSelectedTypes(draft.selectedTypes);
    setTypeDrafts(draft.typeDrafts);
    setDraftLanguages(draft.languages);
    setCustomLanguageInput('');
    setFieldErrors({});
    setMode('summary');
  }, [profile]);

  const toggleGuideType = useCallback((code: GuideTypeCode) => {
    setFieldErrors((prev) => ({ ...prev, types: undefined }));
    if (selectedTypes.includes(code)) {
      setSelectedTypes((prev) => prev.filter((t) => t !== code));
      setTypeDrafts((prev) => {
        const next = { ...prev };
        delete next[code];
        return next;
      });
      return;
    }
    setSelectedTypes((prev) => [...prev, code]);
    setTypeDrafts((prev) => ({ ...prev, [code]: { geo: [], allUzbekistan: false } }));
  }, [selectedTypes]);

  const toggleLocalGeo = useCallback((geo: string) => {
    setFieldErrors((prev) => ({ ...prev, localGeo: undefined }));
    setTypeDrafts((prev) => {
      const draft = prev.local ?? { geo: [], allUzbekistan: false };
      const has = draft.geo.includes(geo);
      const nextGeo = has ? draft.geo.filter((g) => g !== geo) : [...draft.geo, geo];
      return { ...prev, local: { geo: nextGeo, allUzbekistan: false } };
    });
  }, []);

  const toggleMultiGeo = useCallback((code: 'route' | 'accompanying', geo: string) => {
    const errorKey = code === 'route' ? 'routeGeo' : 'accompanyingGeo';
    setFieldErrors((prev) => ({ ...prev, [errorKey]: undefined }));
    setTypeDrafts((prev) => {
      const draft = prev[code] ?? { geo: [], allUzbekistan: false };
      if (draft.allUzbekistan) return prev;
      const has = draft.geo.includes(geo);
      const nextGeo = has ? draft.geo.filter((g) => g !== geo) : [...draft.geo, geo];
      return { ...prev, [code]: { geo: nextGeo, allUzbekistan: false } };
    });
  }, []);

  const toggleAllUzbekistan = useCallback((code: 'route' | 'accompanying') => {
    const errorKey = code === 'route' ? 'routeGeo' : 'accompanyingGeo';
    setFieldErrors((prev) => ({ ...prev, [errorKey]: undefined }));
    setTypeDrafts((prev) => {
      const draft = prev[code] ?? { geo: [], allUzbekistan: false };
      if (draft.allUzbekistan) {
        return { ...prev, [code]: { geo: [], allUzbekistan: false } };
      }
      return { ...prev, [code]: { geo: [], allUzbekistan: true } };
    });
  }, []);

  const togglePresetLanguage = useCallback((lang: string) => {
    setFieldErrors((prev) => ({ ...prev, languages: undefined, customLanguage: undefined }));
    setDraftLanguages((prev) => {
      if (hasLanguage(prev, lang)) {
        return prev.filter((item) => normalizeLanguage(item) !== normalizeLanguage(lang));
      }
      return [...prev, lang];
    });
  }, []);

  const addCustomLanguage = useCallback(() => {
    const trimmed = customLanguageInput.trim();
    if (!trimmed) return;

    if (trimmed.length > 50) {
      setFieldErrors((prev) => ({ ...prev, customLanguage: t.profValLanguageTooLong }));
      return;
    }
    if (draftLanguages.length >= 20) {
      setFieldErrors((prev) => ({ ...prev, customLanguage: t.profValLanguageMax20 }));
      return;
    }
    if (hasLanguage(draftLanguages, trimmed)) {
      setFieldErrors((prev) => ({ ...prev, customLanguage: t.profValDuplicateLanguage }));
      return;
    }

    setFieldErrors((prev) => ({ ...prev, languages: undefined, customLanguage: undefined }));
    setDraftLanguages((prev) => [...prev, trimmed]);
    setCustomLanguageInput('');
  }, [customLanguageInput, draftLanguages]);

  const removeLanguage = useCallback((lang: string) => {
    setFieldErrors((prev) => ({ ...prev, languages: undefined }));
    setDraftLanguages((prev) => prev.filter((item) => item !== lang));
  }, []);

  const validateDraft = useCallback((): FieldErrors => {
    const errors: FieldErrors = {};
    if (selectedTypes.length === 0) {
      errors.types = t.profValNoType;
    }
    if (selectedTypes.includes('local')) {
      const local = typeDrafts.local;
      if (!local || local.geo.length === 0) {
        errors.localGeo = t.profValLocalGeo;
      }
    }
    if (selectedTypes.includes('route')) {
      const route = typeDrafts.route;
      if (!route || (!route.allUzbekistan && route.geo.length === 0)) {
        errors.routeGeo = t.profValRouteGeo;
      }
    }
    if (selectedTypes.includes('accompanying')) {
      const accompanying = typeDrafts.accompanying;
      if (!accompanying || (!accompanying.allUzbekistan && accompanying.geo.length === 0)) {
        errors.accompanyingGeo = t.profValAccompanyingGeo;
      }
    }
    if (draftLanguages.length === 0) {
      errors.languages = t.profValNoLanguage;
    }
    return errors;
  }, [draftLanguages, selectedTypes, typeDrafts]);

  const handleSave = useCallback(async () => {
    const errors = validateDraft();
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setSaving(true);
    try {
      const types = buildTypeInputs(selectedTypes, typeDrafts);
      const ok = await saveProfessionalProfile(types, draftLanguages);
      if (ok) {
        setMode('summary');
        setFieldErrors({});
      }
    } catch {
      /* context handles API failure feedback; keep draft in edit mode */
    } finally {
      setSaving(false);
    }
  }, [draftLanguages, saveProfessionalProfile, selectedTypes, typeDrafts, validateDraft]);

  const customLanguages = useMemo(
    () =>
      draftLanguages.filter(
        (lang) => !PRESET_TOUR_LANGUAGES.some((preset) => normalizeLanguage(preset) === normalizeLanguage(lang)),
      ),
    [draftLanguages],
  );

  if (mode === 'summary') {
    return (
      <div className="prof-profile-editor">
        <div className="section-title" style={{ padding: '12px 16px 0' }}>{t.settingsTypes}</div>
        <div className="prof-profile-summary" style={{ padding: '12px 16px' }}>
          {!configured ? (
            <>
              <p className="prof-summary-empty">{t.profProfileEmpty}</p>
              <button type="button" className="btn btn-primary btn-block" onClick={openEditor}>
                {t.profFillProfile}
              </button>
            </>
          ) : (
            <>
              {profile.types.map((type) => (
                <div key={type.type} className="prof-summary-type card">
                  <strong>{type.label}</strong>
                  <p className="text-muted">{formatGeography(type)}</p>
                </div>
              ))}
              {profile.languages.length > 0 && (
                <div className="prof-summary-languages">
                  <div className="form-label">{t.profTourLanguages}</div>
                  <p>{profile.languages.join(', ')}</p>
                </div>
              )}
              <button type="button" className="btn btn-secondary btn-block" onClick={openEditor}>
                {t.profEditProfile}
              </button>
            </>
          )}
        </div>
      </div>
    );
  }

  const localDraft = typeDrafts.local;
  const routeDraft = typeDrafts.route;
  const accompanyingDraft = typeDrafts.accompanying;

  return (
    <div className="prof-profile-editor">
      <div className="section-title" style={{ padding: '12px 16px 0' }}>{t.settingsTypes}</div>
      <div className="prof-profile-edit" style={{ padding: '12px 16px' }}>
        <fieldset className="prof-fieldset">
          <legend className="prof-fieldset-legend">{t.profGuideTypesLegend}</legend>
          <div className="prof-check-grid">
            {TYPE_ORDER.map((code) => (
              <label key={code} className="prof-check-label">
                <input
                  type="checkbox"
                  checked={selectedTypes.includes(code)}
                  onChange={() => toggleGuideType(code)}
                />
                <span>{GUIDE_TYPE_LABELS[code]}</span>
              </label>
            ))}
          </div>
          {fieldErrors.types && <p className="prof-validation-error">{fieldErrors.types}</p>}
        </fieldset>

        {selectedTypes.includes('local') && (
          <fieldset className="prof-fieldset">
            <legend className="prof-fieldset-legend">{t.profLocalGeoLegend}</legend>
            <div className="prof-check-grid">
              {GEOGRAPHY_OPTIONS.map((geo) => (
                <label key={geo} className="prof-check-label">
                  <input
                    type="checkbox"
                    checked={localDraft?.geo.includes(geo) ?? false}
                    onChange={() => toggleLocalGeo(geo)}
                  />
                  <span>{geo}</span>
                </label>
              ))}
            </div>
            {fieldErrors.localGeo && <p className="prof-validation-error">{fieldErrors.localGeo}</p>}
          </fieldset>
        )}

        {selectedTypes.includes('route') && (
          <fieldset className="prof-fieldset">
            <legend className="prof-fieldset-legend">{t.profRouteGeoLegend}</legend>
            <label className="prof-check-label prof-check-label-block">
              <input
                type="checkbox"
                checked={routeDraft?.allUzbekistan ?? false}
                onChange={() => toggleAllUzbekistan('route')}
              />
              <span>{t.profAllUzbekistan}</span>
            </label>
            {!routeDraft?.allUzbekistan && (
              <div className="prof-check-grid">
                {GEOGRAPHY_OPTIONS.map((geo) => (
                  <label key={geo} className="prof-check-label">
                    <input
                      type="checkbox"
                      checked={routeDraft?.geo.includes(geo) ?? false}
                      onChange={() => toggleMultiGeo('route', geo)}
                    />
                    <span>{geo}</span>
                  </label>
                ))}
              </div>
            )}
            {fieldErrors.routeGeo && <p className="prof-validation-error">{fieldErrors.routeGeo}</p>}
          </fieldset>
        )}

        {selectedTypes.includes('accompanying') && (
          <fieldset className="prof-fieldset">
            <legend className="prof-fieldset-legend">{t.profAccompanyingGeoLegend}</legend>
            <label className="prof-check-label prof-check-label-block">
              <input
                type="checkbox"
                checked={accompanyingDraft?.allUzbekistan ?? false}
                onChange={() => toggleAllUzbekistan('accompanying')}
              />
              <span>{t.profAllUzbekistan}</span>
            </label>
            {!accompanyingDraft?.allUzbekistan && (
              <div className="prof-check-grid">
                {GEOGRAPHY_OPTIONS.map((geo) => (
                  <label key={geo} className="prof-check-label">
                    <input
                      type="checkbox"
                      checked={accompanyingDraft?.geo.includes(geo) ?? false}
                      onChange={() => toggleMultiGeo('accompanying', geo)}
                    />
                    <span>{geo}</span>
                  </label>
                ))}
              </div>
            )}
            {fieldErrors.accompanyingGeo && (
              <p className="prof-validation-error">{fieldErrors.accompanyingGeo}</p>
            )}
          </fieldset>
        )}

        <fieldset className="prof-fieldset">
          <legend className="prof-fieldset-legend">{t.profTourLanguages}</legend>
          <div className="filter-row">
            {PRESET_TOUR_LANGUAGES.map((lang) => {
              const selected = hasLanguage(draftLanguages, lang);
              return (
                <button
                  key={lang}
                  type="button"
                  className={`chip${selected ? ' active' : ''}`}
                  aria-pressed={selected}
                  onClick={() => togglePresetLanguage(lang)}
                >
                  {lang}
                </button>
              );
            })}
            {customLanguages.map((lang) => (
              <button
                key={lang}
                type="button"
                className="chip active"
                aria-pressed={true}
                aria-label={t.profRemoveLanguage(lang)}
                onClick={() => removeLanguage(lang)}
              >
                {lang}
              </button>
            ))}
          </div>
          <div className="prof-language-custom-row">
            <label className="form-label" htmlFor="prof-custom-language">{t.profOtherLanguage}</label>
            <div className="form-row">
              <input
                id="prof-custom-language"
                className="form-input"
                value={customLanguageInput}
                onChange={(e) => {
                  setCustomLanguageInput(e.target.value);
                  setFieldErrors((prev) => ({ ...prev, customLanguage: undefined }));
                }}
              />
              <button type="button" className="btn btn-secondary" onClick={addCustomLanguage}>
                {t.profAddLanguage}
              </button>
            </div>
          </div>
          {fieldErrors.languages && <p className="prof-validation-error">{fieldErrors.languages}</p>}
          {fieldErrors.customLanguage && (
            <p className="prof-validation-error">{fieldErrors.customLanguage}</p>
          )}
        </fieldset>
      </div>

      <div className="sheet-footer prof-editor-footer">
        <div className="form-row">
          <button type="button" className="btn btn-secondary btn-block" onClick={cancelEdit} disabled={saving}>
            {t.cancel}
          </button>
          <button type="button" className="btn btn-primary btn-block" onClick={handleSave} disabled={saving}>
            {saving ? t.profSaving : t.save}
          </button>
        </div>
      </div>
    </div>
  );
}

export { buildTypeInputs, draftFromProfile, hasLanguage, isProfileConfigured };

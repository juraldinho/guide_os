import { useState } from 'react';
import { t } from '@/i18n/strings';
import { OfficialCompaniesSection } from './OfficialCompaniesSection';
import { PersonalPlacesSection } from './PersonalPlacesSection';

export function GuideShopPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <main className="main guideshop-page" aria-label={t.guideShop}>
      <div className="guideshop-search">
        <label className="form-label" htmlFor="guideshop-search">
          {t.guideShopSearchLabel}
        </label>
        <input
          id="guideshop-search"
          className="form-input"
          type="search"
          value={searchQuery}
          placeholder={t.guideShopSearchPlaceholder}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
      </div>

      <OfficialCompaniesSection searchQuery={searchQuery} />

      <PersonalPlacesSection
        searchQuery={searchQuery}
        createOpen={createOpen}
        onCreateOpenChange={setCreateOpen}
      />
    </main>
  );
}

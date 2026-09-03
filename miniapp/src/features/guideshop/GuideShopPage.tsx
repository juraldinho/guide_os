import { useState } from 'react';
import { t } from '@/i18n/strings';
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

      <section className="card guideshop-placeholder" aria-labelledby="guideshop-official-title">
        <h2 id="guideshop-official-title" className="guideshop-section-title">
          {t.guideShopOfficial}
        </h2>
        <p className="text-muted">{t.guideShopComingSoon}</p>
      </section>

      <PersonalPlacesSection
        searchQuery={searchQuery}
        createOpen={createOpen}
        onCreateOpenChange={setCreateOpen}
      />
    </main>
  );
}

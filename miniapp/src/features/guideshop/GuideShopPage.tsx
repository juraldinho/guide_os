import { t } from '@/i18n/strings';

export function GuideShopPage() {
  return (
    <main className="main guideshop-page" aria-label={t.guideShop}>
      <section className="card guideshop-placeholder" aria-labelledby="guideshop-official-title">
        <h2 id="guideshop-official-title" className="guideshop-section-title">
          {t.guideShopOfficial}
        </h2>
        <p className="text-muted">{t.guideShopComingSoon}</p>
      </section>

      <section className="card guideshop-placeholder" aria-labelledby="guideshop-personal-title">
        <h2 id="guideshop-personal-title" className="guideshop-section-title">
          {t.guideShopPersonal}
        </h2>
        <p className="text-muted">{t.guideShopComingSoon}</p>
      </section>
    </main>
  );
}

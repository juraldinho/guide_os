import { Chip } from '@/components/ui/Chip';
import { t } from '@/i18n/strings';
import { useCalendar } from '@/features/calendar/CalendarContext';

export function SettingsOverlay() {
  const {
    profile,
    themeMode,
    closeSettings,
    updateProfileName,
    copyTelegramId,
    toggleNotif,
    updateNotifTime,
    setThemeMode,
    openDemoStates,
  } = useCalendar();

  if (!profile) return null;

  return (
    <div
      className="overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) closeSettings();
      }}
    >
      <div className="sheet" style={{ maxHeight: '95vh' }}>
        <div className="sheet-header">
          <span className="sheet-title">{t.settings}</span>
          <button type="button" className="icon-btn" onClick={closeSettings} aria-label={t.close}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="sheet-body" style={{ padding: 0 }}>
          <div className="settings-list">
            <div className="section-title" style={{ padding: '12px 16px 0' }}>{t.settingsProfile}</div>
            <div style={{ padding: '12px 16px' }}>
              <label className="form-label" htmlFor="profile-name">{t.settingsDisplayName}</label>
              <input
                id="profile-name"
                className="form-input"
                value={profile.name}
                onChange={(e) => updateProfileName(e.target.value)}
              />
            </div>

            <div className="section-title" style={{ padding: '12px 16px 0' }}>{t.settingsTelegramId}</div>
            <div style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 8 }}>
              <code style={{ flex: 1, fontSize: 14 }}>{profile.telegramId}</code>
              <button type="button" className="btn btn-secondary" onClick={copyTelegramId}>
                {t.copyTelegramId}
              </button>
            </div>

            <div className="section-title" style={{ padding: '12px 16px 0' }}>{t.settingsTypes}</div>
            <div style={{ padding: '8px 16px 12px' }}>
              {profile.types.map((type) => (
                <div key={type.type} className="card" style={{ marginBottom: 8 }}>
                  <strong>{type.label}</strong>
                  <br />
                  <span className="text-muted">{type.geo.join(', ')}</span>
                </div>
              ))}
              <p className="text-muted" style={{ fontSize: 12 }}>{t.settingsTypesHint}</p>
            </div>

            <div className="section-title" style={{ padding: '12px 16px 0' }}>{t.settingsNotifications}</div>
            <div style={{ padding: '12px 16px' }}>
              <div className="toggle-row">
                <span>{t.settingsReminders}</span>
                <button
                  type="button"
                  className={`toggle${profile.notifications.enabled ? ' on' : ''}`}
                  onClick={toggleNotif}
                  aria-pressed={profile.notifications.enabled}
                />
              </div>
              <div className="form-group" style={{ marginTop: 8 }}>
                <label className="form-label" htmlFor="notif-time">{t.settingsReminderTime}</label>
                <input
                  id="notif-time"
                  type="time"
                  className="form-input"
                  value={profile.notifications.time}
                  onChange={(e) => updateNotifTime(e.target.value)}
                />
              </div>
            </div>

            <div className="section-title" style={{ padding: '12px 16px 0' }}>{t.settingsTheme}</div>
            <p className="demo-note">{t.settingsThemeNote}</p>
            <div className="filter-row" style={{ padding: '8px 16px 12px' }}>
              <Chip
                label={t.themeTelegram}
                active={themeMode === 'telegram'}
                onClick={() => setThemeMode('telegram')}
              />
              <Chip
                label={t.themeLight}
                active={themeMode === 'light'}
                onClick={() => setThemeMode('light')}
              />
              <Chip
                label={t.themeDark}
                active={themeMode === 'dark'}
                onClick={() => setThemeMode('dark')}
              />
            </div>

            <button type="button" className="settings-item" onClick={openDemoStates}>
              <span>{t.settingsDemoStates}</span>
              <span className="arrow">›</span>
            </button>
            <div className="settings-item" style={{ cursor: 'default' }}>
              <span>{t.settingsLanguage}</span>
              <span>{t.settingsLanguageValue}</span>
            </div>
            <div className="settings-item" style={{ cursor: 'default' }}>
              <span>{t.settingsAbout}</span>
              <span className="text-muted" style={{ fontSize: 12 }}>{t.settingsAboutValue}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

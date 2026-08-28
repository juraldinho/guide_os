export type ThemeMode = 'telegram' | 'light' | 'dark';

const THEME_KEY = 'guide_os_miniapp_theme';

export function applyThemeMode(mode: ThemeMode): void {
  const html = document.documentElement;
  if (mode === 'telegram') {
    html.removeAttribute('data-theme');
  } else {
    html.setAttribute('data-theme', mode);
  }
  try {
    sessionStorage.setItem(THEME_KEY, mode);
  } catch {
    /* ignore */
  }
}

export function loadStoredTheme(): ThemeMode {
  try {
    const saved = sessionStorage.getItem(THEME_KEY);
    if (saved === 'light' || saved === 'dark' || saved === 'telegram') {
      return saved;
    }
  } catch {
    /* ignore */
  }
  return 'telegram';
}

export function getSafeAreaInsets(): { top: string; bottom: string } {
  return {
    top: 'env(safe-area-inset-top, 0)',
    bottom: 'env(safe-area-inset-bottom, 0)',
  };
}

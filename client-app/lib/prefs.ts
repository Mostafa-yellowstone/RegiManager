import { kvGet, kvSet } from '@/lib/storage';

const LANGUAGE_KEY = 'client_app_language';
const THEME_KEY = 'client_app_theme';

export type AppLanguage = 'en' | 'es' | 'ar';
export type AppThemeMode = 'system' | 'light' | 'dark';

export async function getLanguage(): Promise<AppLanguage> {
  const value = await kvGet(LANGUAGE_KEY);
  if (value === 'es' || value === 'ar' || value === 'en') return value;
  return 'en';
}

export async function setLanguage(language: AppLanguage): Promise<void> {
  await kvSet(LANGUAGE_KEY, language);
}

export async function getThemeMode(): Promise<AppThemeMode> {
  const value = await kvGet(THEME_KEY);
  if (value === 'light' || value === 'dark' || value === 'system') return value;
  return 'system';
}

export async function setThemeMode(mode: AppThemeMode): Promise<void> {
  await kvSet(THEME_KEY, mode);
}

export const LANGUAGE_OPTIONS: { value: AppLanguage; label: string }[] = [
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Español' },
  { value: 'ar', label: 'العربية' },
];

export const THEME_OPTIONS: { value: AppThemeMode; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
];

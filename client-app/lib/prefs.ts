import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const LANGUAGE_KEY = 'client_app_language';
const THEME_KEY = 'client_app_theme';

export type AppLanguage = 'en' | 'es' | 'ar';
export type AppThemeMode = 'system' | 'light' | 'dark';

async function storageGet(key: string): Promise<string | null> {
  if (Platform.OS === 'web') {
    try {
      return globalThis.localStorage?.getItem(key) ?? null;
    } catch {
      return null;
    }
  }
  return SecureStore.getItemAsync(key);
}

async function storageSet(key: string, value: string): Promise<void> {
  if (Platform.OS === 'web') {
    globalThis.localStorage?.setItem(key, value);
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

export async function getLanguage(): Promise<AppLanguage> {
  const value = await storageGet(LANGUAGE_KEY);
  if (value === 'es' || value === 'ar' || value === 'en') return value;
  return 'en';
}

export async function setLanguage(language: AppLanguage): Promise<void> {
  await storageSet(LANGUAGE_KEY, language);
}

export async function getThemeMode(): Promise<AppThemeMode> {
  const value = await storageGet(THEME_KEY);
  if (value === 'light' || value === 'dark' || value === 'system') return value;
  return 'system';
}

export async function setThemeMode(mode: AppThemeMode): Promise<void> {
  await storageSet(THEME_KEY, mode);
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

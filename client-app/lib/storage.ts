import * as FileSystem from 'expo-file-system/legacy';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

/**
 * Durable key/value store for wallet session + onboarding flags.
 * Uses SecureStore when available, with a FileSystem backup so Expo Go
 * reloads still keep "logged in" / "seen onboarding" state.
 */
const BACKUP_FILE = `${FileSystem.documentDirectory || ''}wallet_kv_store.json`;

type StoreMap = Record<string, string>;

async function readBackup(): Promise<StoreMap> {
  try {
    if (!FileSystem.documentDirectory) return {};
    const info = await FileSystem.getInfoAsync(BACKUP_FILE);
    if (!info.exists) return {};
    const raw = await FileSystem.readAsStringAsync(BACKUP_FILE);
    return raw ? (JSON.parse(raw) as StoreMap) : {};
  } catch {
    return {};
  }
}

async function writeBackup(map: StoreMap): Promise<void> {
  try {
    if (!FileSystem.documentDirectory) return;
    await FileSystem.writeAsStringAsync(BACKUP_FILE, JSON.stringify(map));
  } catch {
    // ignore backup failures
  }
}

async function backupGet(key: string): Promise<string | null> {
  const map = await readBackup();
  return map[key] ?? null;
}

async function backupSet(key: string, value: string): Promise<void> {
  const map = await readBackup();
  map[key] = value;
  await writeBackup(map);
}

async function backupDelete(key: string): Promise<void> {
  const map = await readBackup();
  if (!(key in map)) return;
  delete map[key];
  await writeBackup(map);
}

export async function kvGet(key: string): Promise<string | null> {
  if (Platform.OS === 'web') {
    try {
      return globalThis.localStorage?.getItem(key) ?? null;
    } catch {
      return null;
    }
  }

  try {
    const secure = await SecureStore.getItemAsync(key);
    if (secure != null) {
      // Keep backup in sync for future SecureStore misses.
      await backupSet(key, secure);
      return secure;
    }
  } catch {
    // fall through to backup
  }

  return backupGet(key);
}

export async function kvSet(key: string, value: string): Promise<void> {
  if (Platform.OS === 'web') {
    try {
      globalThis.localStorage?.setItem(key, value);
    } catch {
      // ignore
    }
    return;
  }

  let secureOk = false;
  try {
    await SecureStore.setItemAsync(key, value);
    secureOk = true;
  } catch {
    secureOk = false;
  }
  // Always write backup so cold starts keep session/onboarding.
  await backupSet(key, value);
  if (!secureOk) {
    // Backup-only mode still works for Expo Go persistence.
  }
}

export async function kvDelete(key: string): Promise<void> {
  if (Platform.OS === 'web') {
    try {
      globalThis.localStorage?.removeItem(key);
    } catch {
      // ignore
    }
    return;
  }

  try {
    await SecureStore.deleteItemAsync(key);
  } catch {
    // ignore
  }
  await backupDelete(key);
}

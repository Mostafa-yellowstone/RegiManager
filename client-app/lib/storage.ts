import * as FileSystem from 'expo-file-system/legacy';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

/**
 * Secure key/value store for the wallet.
 * Secrets (tokens, credentials) stay in SecureStore only — never mirrored
 * to a plaintext FileSystem backup. Non-sensitive prefs may use a backup
 * so Expo Go reloads keep onboarding / UI preferences.
 */
const BACKUP_FILE = `${FileSystem.documentDirectory || ''}wallet_kv_store.json`;

/** Keys that must never be written to the plaintext backup file. */
const SECRET_KEYS = new Set([
  'client_app_token',
  'client_app_profile',
  'client_app_org',
  'client_app_saved_credentials',
]);

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
    // Strip any secrets that may have been written by older builds.
    for (const key of SECRET_KEYS) {
      delete map[key];
    }
    await FileSystem.writeAsStringAsync(BACKUP_FILE, JSON.stringify(map));
  } catch {
    // ignore backup failures
  }
}

async function backupGet(key: string): Promise<string | null> {
  if (SECRET_KEYS.has(key)) return null;
  const map = await readBackup();
  return map[key] ?? null;
}

async function backupSet(key: string, value: string): Promise<void> {
  if (SECRET_KEYS.has(key)) return;
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

/** One-time scrub of secrets left in older plaintext backups. */
export async function scrubSecretBackups(): Promise<void> {
  if (Platform.OS === 'web') return;
  try {
    const map = await readBackup();
    let dirty = false;
    for (const key of SECRET_KEYS) {
      if (key in map) {
        delete map[key];
        dirty = true;
      }
    }
    if (dirty) await writeBackup(map);
  } catch {
    // ignore
  }
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
    if (secure != null) return secure;
  } catch {
    // fall through
  }

  // Secrets never fall back to plaintext backup.
  if (SECRET_KEYS.has(key)) return null;
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

  try {
    await SecureStore.setItemAsync(key, value);
  } catch {
    // If SecureStore fails for a secret, do not write plaintext.
    if (SECRET_KEYS.has(key)) {
      throw new Error('Unable to securely store credentials on this device.');
    }
  }

  if (!SECRET_KEYS.has(key)) {
    await backupSet(key, value);
  } else {
    // Ensure leftover plaintext copies are removed.
    await backupDelete(key);
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

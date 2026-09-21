import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const memory = new Map<string, string>();

const SECURE_OPTIONS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

async function nativeGet(key: string): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(key, SECURE_OPTIONS);
  } catch {
    try {
      return await SecureStore.getItemAsync(key);
    } catch {
      return memory.get(key) ?? null;
    }
  }
}

async function nativeSet(key: string, value: string): Promise<void> {
  memory.set(key, value);
  try {
    await SecureStore.setItemAsync(key, value, SECURE_OPTIONS);
  } catch {
    try {
      await SecureStore.setItemAsync(key, value);
    } catch {
      // memory fallback for web / restricted environments
    }
  }
}

async function nativeDelete(key: string): Promise<void> {
  memory.delete(key);
  try {
    await SecureStore.deleteItemAsync(key, SECURE_OPTIONS);
  } catch {
    try {
      await SecureStore.deleteItemAsync(key);
    } catch {
      // ignore
    }
  }
}

export async function kvGet(key: string): Promise<string | null> {
  if (Platform.OS === 'web') return memory.get(key) ?? null;
  return nativeGet(key);
}

export async function kvSet(key: string, value: string): Promise<void> {
  if (Platform.OS === 'web') {
    memory.set(key, value);
    return;
  }
  await nativeSet(key, value);
}

export async function kvDelete(key: string): Promise<void> {
  if (Platform.OS === 'web') {
    memory.delete(key);
    return;
  }
  await nativeDelete(key);
}

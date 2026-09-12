import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const TOKEN_KEY = 'client_app_token';
const CLIENT_KEY = 'client_app_profile';
const ORG_KEY = 'client_app_org';

export const API_BASE_URL = (
  process.env.EXPO_PUBLIC_API_BASE_URL || 'https://www.regimanager.com'
).replace(/\/$/, '');

type Json = Record<string, unknown>;

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

async function storageDelete(key: string): Promise<void> {
  if (Platform.OS === 'web') {
    globalThis.localStorage?.removeItem(key);
    return;
  }
  await SecureStore.deleteItemAsync(key);
}

export async function getStoredToken(): Promise<string | null> {
  return storageGet(TOKEN_KEY);
}

export async function saveSession(token: string, client: Json, organization: Json): Promise<void> {
  await storageSet(TOKEN_KEY, token);
  await storageSet(CLIENT_KEY, JSON.stringify(client));
  await storageSet(ORG_KEY, JSON.stringify(organization));
}

export async function clearSession(): Promise<void> {
  await storageDelete(TOKEN_KEY);
  await storageDelete(CLIENT_KEY);
  await storageDelete(ORG_KEY);
}

export async function getStoredClient(): Promise<Json | null> {
  const raw = await storageGet(CLIENT_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function apiFetch<T = any>(
  path: string,
  options: RequestInit & { token?: string | null } = {},
): Promise<T> {
  const { token, headers, ...rest } = options;
  const authToken = token === undefined ? await getStoredToken() : token;
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(authToken ? { Authorization: `Token ${authToken}` } : {}),
      ...(headers || {}),
    },
  });
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    const detail =
      (data && (data.detail || data.error || data.message)) ||
      `Request failed (${res.status})`;
    throw new ApiError(res.status, String(detail));
  }
  return data as T;
}

export function login(payload: {
  portal_token?: string;
  organization_id?: number | string;
  phone?: string;
  email?: string;
  pin: string;
  device_label?: string;
}) {
  return apiFetch<{
    token: string;
    client: Json;
    organization: Json;
  }>('/api/client/auth/login/', {
    method: 'POST',
    body: JSON.stringify(payload),
    token: null,
  });
}

export function logout() {
  return apiFetch('/api/client/auth/logout/', { method: 'POST' });
}

export function fetchHome() {
  return apiFetch('/api/client/home/');
}

export function fetchPolicies() {
  return apiFetch('/api/client/policies/');
}

export function fetchPolicy(id: number | string) {
  return apiFetch(`/api/client/policies/${id}/`);
}

export function fetchSchedule(id: number | string) {
  return apiFetch(`/api/client/policies/${id}/schedule/`);
}

export function fetchIdCards() {
  return apiFetch('/api/client/id-cards/');
}

export function fetchDocuments() {
  return apiFetch('/api/client/documents/');
}

export function fetchPayments() {
  return apiFetch('/api/client/payments/');
}

export function fetchVehicles() {
  return apiFetch('/api/client/vehicles/');
}

export function fetchReceipts() {
  return apiFetch('/api/client/receipts/');
}

export function fetchUpcoming(days = 90) {
  return apiFetch(`/api/client/upcoming/?days=${days}`);
}

export function fetchAlerts() {
  return apiFetch('/api/client/alerts/');
}

export async function fetchDocumentBlob(kind: string, id: number | string): Promise<Blob> {
  const token = await getStoredToken();
  const res = await fetch(`${API_BASE_URL}/api/client/documents/${kind}/${id}/file/`, {
    headers: {
      ...(token ? { Authorization: `Token ${token}` } : {}),
    },
  });
  if (!res.ok) {
    throw new ApiError(res.status, 'Could not download document');
  }
  return res.blob();
}

import { kvDelete, kvGet, kvSet } from '@/lib/storage';

const TOKEN_KEY = 'client_app_token';
const CLIENT_KEY = 'client_app_profile';
const ORG_KEY = 'client_app_org';
const ONBOARDING_KEY = 'client_app_has_seen_onboarding';

export const API_BASE_URL = (
  process.env.EXPO_PUBLIC_API_BASE_URL || 'https://www.regimanager.com'
).replace(/\/$/, '');

/** Default request timeout — prevents hung UI on bad networks. */
const DEFAULT_TIMEOUT_MS = 25000;

type Json = Record<string, unknown>;

type UnauthorizedHandler = () => void | Promise<void>;
let unauthorizedHandler: UnauthorizedHandler | null = null;

/** AuthProvider registers this so expired sessions force logout everywhere. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  unauthorizedHandler = handler;
}

async function storageGet(key: string): Promise<string | null> {
  return kvGet(key);
}

async function storageSet(key: string, value: string): Promise<void> {
  await kvSet(key, value);
}

async function storageDelete(key: string): Promise<void> {
  await kvDelete(key);
}

export async function getStoredToken(): Promise<string | null> {
  return storageGet(TOKEN_KEY);
}

export async function getHasSeenOnboarding(): Promise<boolean> {
  const raw = await storageGet(ONBOARDING_KEY);
  return raw === 'true';
}

export async function setHasSeenOnboarding(seen: boolean): Promise<void> {
  if (seen) {
    await storageSet(ONBOARDING_KEY, 'true');
  } else {
    await storageDelete(ONBOARDING_KEY);
  }
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
    this.name = 'ApiError';
  }
}

function mergeAbortSignals(a?: AbortSignal | null, b?: AbortSignal | null): AbortSignal | undefined {
  if (!a && !b) return undefined;
  if (a && !b) return a;
  if (b && !a) return b;
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  a!.addEventListener('abort', onAbort);
  b!.addEventListener('abort', onAbort);
  if (a!.aborted || b!.aborted) controller.abort();
  return controller.signal;
}

async function handleUnauthorized(): Promise<void> {
  if (!unauthorizedHandler) return;
  try {
    await unauthorizedHandler();
  } catch {
    // never throw from auth recovery
  }
}

export async function apiFetch<T = any>(
  path: string,
  options: RequestInit & { token?: string | null; timeoutMs?: number } = {},
): Promise<T> {
  const { token, headers, timeoutMs = DEFAULT_TIMEOUT_MS, signal, ...rest } = options;
  const authToken = token === undefined ? await getStoredToken() : token;

  const timeoutController = new AbortController();
  const timer = setTimeout(() => timeoutController.abort(), timeoutMs);
  const combined = mergeAbortSignals(signal, timeoutController.signal);

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...rest,
      signal: combined,
      headers: {
        Accept: 'application/json',
        ...(rest.method && rest.method !== 'GET'
          ? { 'Content-Type': 'application/json' }
          : {}),
        ...(authToken ? { Authorization: `Token ${authToken}` } : {}),
        ...(headers || {}),
      },
    });
  } catch (err: any) {
    clearTimeout(timer);
    if (err?.name === 'AbortError') {
      if (signal?.aborted) throw err;
      throw new ApiError(408, 'Request timed out. Check your connection and try again.');
    }
    throw new ApiError(0, 'Network unavailable. Check your connection and try again.');
  } finally {
    clearTimeout(timer);
  }

  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    if (res.status === 401 && authToken) {
      await handleUnauthorized();
    }
    const detail =
      (data && (data.detail || data.error || data.message)) ||
      `Request failed (${res.status})`;
    throw new ApiError(res.status, String(detail));
  }
  return data as T;
}

/** Long-poll fetch with optional AbortSignal (chat realtime). */
export async function apiFetchWait<T = any>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  // Long-poll can legitimately take ~timeout seconds; don't use the short default.
  return apiFetch<T>(path, { signal, token: undefined, timeoutMs: 35000 });
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

export function fetchVehicle(id: number | string) {
  return apiFetch(`/api/client/vehicles/${id}/`);
}

export function fetchServices(opts?: { vehicleId?: number | string; limit?: number }) {
  const params = new URLSearchParams();
  if (opts?.vehicleId != null) params.set('vehicle_id', String(opts.vehicleId));
  if (opts?.limit != null) params.set('limit', String(opts.limit));
  const q = params.toString();
  return apiFetch(`/api/client/services/${q ? `?${q}` : ''}`);
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

export function fetchChatMessages(afterId = 0) {
  const q = afterId ? `?after_id=${afterId}` : '';
  return apiFetch(`/api/client/chat/messages/${q}`);
}

export function sendChatMessage(body: string) {
  return apiFetch('/api/client/chat/messages/', {
    method: 'POST',
    body: JSON.stringify({ body }),
  });
}

export function waitChatMessages(afterId = 0, timeout = 12, signal?: AbortSignal) {
  const q = `after_id=${afterId}&timeout=${Math.max(3, Math.min(timeout, 20))}`;
  return apiFetchWait(`/api/client/chat/wait/?${q}`, signal);
}

export async function fetchDocumentBlob(kind: string, id: number | string): Promise<Blob> {
  const token = await getStoredToken();
  const timeoutController = new AbortController();
  const timer = setTimeout(() => timeoutController.abort(), DEFAULT_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE_URL}/api/client/documents/${kind}/${id}/file/`, {
      headers: {
        ...(token ? { Authorization: `Token ${token}` } : {}),
      },
      signal: timeoutController.signal,
    });
    if (!res.ok) {
      if (res.status === 401 && token) await handleUnauthorized();
      throw new ApiError(res.status, 'Could not download document');
    }
    return res.blob();
  } catch (err: any) {
    if (err instanceof ApiError) throw err;
    if (err?.name === 'AbortError') {
      throw new ApiError(408, 'Download timed out. Try again.');
    }
    throw new ApiError(0, 'Network unavailable. Check your connection and try again.');
  } finally {
    clearTimeout(timer);
  }
}

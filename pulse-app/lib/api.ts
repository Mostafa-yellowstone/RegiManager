import { kvDelete, kvGet, kvSet } from '@/lib/storage';

export const API_BASE_URL = (
  process.env.EXPO_PUBLIC_API_BASE_URL || 'https://www.regimanager.com'
).replace(/\/$/, '');

const DEFAULT_TIMEOUT_MS = 25000;

const TOKEN_KEY = 'pulse_token';
const USER_KEY = 'pulse_user';
const ORGS_KEY = 'pulse_organizations';
const ORG_ID_KEY = 'pulse_selected_org_id';

export type PulseUser = {
  id: number;
  username: string;
  email: string;
  full_name: string;
};

export type PulseOrganization = {
  id: number;
  membership_id: number;
  name: string;
  city: string;
  state: string;
  role: string;
  permissions?: Record<string, boolean>;
};

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

type UnauthorizedHandler = () => void | Promise<void>;
let unauthorizedHandler: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  unauthorizedHandler = handler;
}

export async function getStoredToken() {
  return kvGet(TOKEN_KEY);
}

export async function getStoredUser(): Promise<PulseUser | null> {
  const raw = await kvGet(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as PulseUser;
  } catch {
    return null;
  }
}

export async function getStoredOrganizations(): Promise<PulseOrganization[]> {
  const raw = await kvGet(ORGS_KEY);
  if (!raw) return [];
  try {
    return JSON.parse(raw) as PulseOrganization[];
  } catch {
    return [];
  }
}

export async function getStoredOrgId(): Promise<number | null> {
  const raw = await kvGet(ORG_ID_KEY);
  if (!raw) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

export async function saveSession(opts: {
  token: string;
  user: PulseUser;
  organizations: PulseOrganization[];
  organizationId: number;
}) {
  await kvSet(TOKEN_KEY, opts.token);
  await kvSet(USER_KEY, JSON.stringify(opts.user));
  await kvSet(ORGS_KEY, JSON.stringify(opts.organizations));
  await kvSet(ORG_ID_KEY, String(opts.organizationId));
}

export async function setStoredOrgId(organizationId: number) {
  await kvSet(ORG_ID_KEY, String(organizationId));
}

export async function clearSession() {
  await kvDelete(TOKEN_KEY);
  await kvDelete(USER_KEY);
  await kvDelete(ORGS_KEY);
  await kvDelete(ORG_ID_KEY);
}

type ApiOptions = {
  method?: string;
  body?: unknown;
  orgId?: number | null;
  auth?: boolean;
  timeoutMs?: number;
};

export async function apiFetch<T = any>(path: string, options: ApiOptions = {}): Promise<T> {
  const { method = 'GET', body, orgId, auth = true, timeoutMs = DEFAULT_TIMEOUT_MS } = options;
  const headers: Record<string, string> = {
    Accept: 'application/json',
  };
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  if (auth) {
    const token = await getStoredToken();
    if (token) headers.Authorization = `Token ${token}`;
    const resolvedOrg =
      orgId ??
      (await getStoredOrgId()) ??
      undefined;
    if (resolvedOrg != null) headers['X-Organization-Id'] = String(resolvedOrg);
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    const text = await res.text();
    let data: any = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { detail: text };
    }

    if (res.status === 401 && auth) {
      await clearSession();
      if (unauthorizedHandler) await unauthorizedHandler();
      throw new ApiError(data?.detail || 'Session expired', 401);
    }

    if (!res.ok) {
      const detail =
        typeof data?.detail === 'string'
          ? data.detail
          : data?.detail
            ? JSON.stringify(data.detail)
            : `Request failed (${res.status})`;
      throw new ApiError(detail, res.status);
    }

    return data as T;
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      throw new ApiError('Request timed out', 408);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export async function loginCompanion(username: string, password: string) {
  return apiFetch<{
    token: string;
    token_type: string;
    user: PulseUser;
    organizations: PulseOrganization[];
    default_organization_id: number;
  }>('/api/auth/login/', {
    method: 'POST',
    body: { username, password },
    auth: false,
  });
}

export async function logoutCompanion() {
  try {
    await apiFetch('/api/auth/logout/', { method: 'POST' });
  } catch {
    // still clear local session
  }
  await clearSession();
}

export async function fetchOwnerOverview(params?: Record<string, string>) {
  const q = new URLSearchParams(params || {}).toString();
  return apiFetch(`/api/owner/overview/${q ? `?${q}` : ''}`);
}

export async function fetchOwnerFinanceSummary(params?: Record<string, string>) {
  const q = new URLSearchParams(params || {}).toString();
  return apiFetch(`/api/owner/finance/summary/${q ? `?${q}` : ''}`);
}

export async function fetchOwnerFinanceChart(months = 12) {
  return apiFetch(`/api/owner/finance/chart/?months=${months}`);
}

export async function fetchOwnerFinanceCashflow(params?: Record<string, string>) {
  const q = new URLSearchParams(params || {}).toString();
  return apiFetch(`/api/owner/finance/cashflow/${q ? `?${q}` : ''}`);
}

export async function fetchOwnerFinanceCompare(compareA: string, compareB: string) {
  return apiFetch(
    `/api/owner/finance/compare/?compare_a=${encodeURIComponent(compareA)}&compare_b=${encodeURIComponent(compareB)}&mode=month`,
  );
}

export async function fetchOwnerSpaces(params?: Record<string, string>) {
  const q = new URLSearchParams(params || {}).toString();
  return apiFetch(`/api/owner/spaces/${q ? `?${q}` : ''}`);
}

export async function fetchOwnerSpaceDetail(spaceId: string, params?: Record<string, string>) {
  const q = new URLSearchParams(params || {}).toString();
  return apiFetch(`/api/owner/spaces/${spaceId}/${q ? `?${q}` : ''}`);
}

export async function fetchOwnerFinanceRecords(opts?: {
  category?: 'dmv' | 'insurance';
  from_date?: string;
  to_date?: string;
  limit?: number;
}) {
  const params = new URLSearchParams();
  params.set('category', opts?.category || 'dmv');
  if (opts?.from_date) params.set('from_date', opts.from_date);
  if (opts?.to_date) params.set('to_date', opts.to_date);
  params.set('limit', String(opts?.limit ?? 40));
  return apiFetch(`/api/owner/finance/records/?${params.toString()}`);
}

export async function fetchOwnerProcesses() {
  return apiFetch('/api/owner/processes/');
}

export async function fetchOwnerAgents() {
  return apiFetch('/api/owner/agents/');
}

export async function fetchOwnerInsuranceTargets() {
  return apiFetch('/api/owner/insurance/targets/');
}

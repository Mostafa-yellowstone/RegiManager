import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import {
  clearSession,
  getStoredOrgId,
  getStoredOrganizations,
  getStoredToken,
  getStoredUser,
  loginCompanion,
  logoutCompanion,
  saveSession,
  setStoredOrgId,
  setUnauthorizedHandler,
  type PulseOrganization,
  type PulseUser,
} from '@/lib/api';

type AuthState = {
  ready: boolean;
  token: string | null;
  user: PulseUser | null;
  organizations: PulseOrganization[];
  selectedOrgId: number | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  selectOrganization: (orgId: number) => Promise<void>;
  selectedOrg: PulseOrganization | null;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<PulseUser | null>(null);
  const [organizations, setOrganizations] = useState<PulseOrganization[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<number | null>(null);

  const resetLocal = useCallback(() => {
    setToken(null);
    setUser(null);
    setOrganizations([]);
    setSelectedOrgId(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(async () => {
      resetLocal();
    });
    return () => setUnauthorizedHandler(null);
  }, [resetLocal]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [t, u, orgs, orgId] = await Promise.all([
        getStoredToken(),
        getStoredUser(),
        getStoredOrganizations(),
        getStoredOrgId(),
      ]);
      if (cancelled) return;
      setToken(t);
      setUser(u);
      setOrganizations(orgs);
      setSelectedOrgId(orgId ?? orgs[0]?.id ?? null);
      setReady(true);
      if (t) {
        void import('@/lib/notifications')
          .then((m) => m.syncDailySnapshotPreference())
          .catch(() => undefined);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const data = await loginCompanion(username.trim(), password);
    const orgId = data.default_organization_id || data.organizations[0]?.id;
    if (!orgId) throw new Error('No organization on this account.');
    await saveSession({
      token: data.token,
      user: data.user,
      organizations: data.organizations,
      organizationId: orgId,
    });
    setToken(data.token);
    setUser(data.user);
    setOrganizations(data.organizations);
    setSelectedOrgId(orgId);
    void import('@/lib/notifications')
      .then((m) => m.syncDailySnapshotPreference())
      .catch(() => undefined);
  }, []);

  const logout = useCallback(async () => {
    await logoutCompanion();
    resetLocal();
  }, [resetLocal]);

  const selectOrganization = useCallback(async (orgId: number) => {
    await setStoredOrgId(orgId);
    setSelectedOrgId(orgId);
  }, []);

  const selectedOrg = useMemo(
    () => organizations.find((o) => o.id === selectedOrgId) ?? null,
    [organizations, selectedOrgId],
  );

  const value = useMemo(
    () => ({
      ready,
      token,
      user,
      organizations,
      selectedOrgId,
      selectedOrg,
      login,
      logout,
      selectOrganization,
    }),
    [
      ready,
      token,
      user,
      organizations,
      selectedOrgId,
      selectedOrg,
      login,
      logout,
      selectOrganization,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

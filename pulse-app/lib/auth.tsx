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
import { useDateRangeStore } from '@/stores/dateRangeStore';
import { useSpaceStore } from '@/stores/spaceStore';

function ownerOrganizations(orgs: PulseOrganization[]): PulseOrganization[] {
  return (orgs || []).filter((o) => String(o.role || '').toLowerCase() === 'owner');
}

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
    useSpaceStore.getState().setSelectedSpaceId('all');
    useDateRangeStore.getState().setPreset('week');
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

      const owners = ownerOrganizations(orgs);
      if (t && owners.length === 0) {
        // Stale non-owner session from an older Pulse build.
        await clearSession();
        setReady(true);
        return;
      }

      const nextOrgId =
        (orgId && owners.some((o) => o.id === orgId) ? orgId : null) ?? owners[0]?.id ?? null;

      setToken(t && owners.length ? t : null);
      setUser(t && owners.length ? u : null);
      setOrganizations(owners);
      setSelectedOrgId(nextOrgId);
      setReady(true);
      if (t && owners.length) {
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
    const owners = ownerOrganizations(data.organizations);
    if (!owners.length) {
      throw new Error('Pulse is for organization owners only. Use an owner CRM account.');
    }
    const preferred = data.default_organization_id;
    const orgId = owners.some((o) => o.id === preferred) ? preferred : owners[0].id;
    await saveSession({
      token: data.token,
      user: data.user,
      organizations: owners,
      organizationId: orgId,
    });
    setToken(data.token);
    setUser(data.user);
    setOrganizations(owners);
    setSelectedOrgId(orgId);
    useSpaceStore.getState().setSelectedSpaceId('all');
    useDateRangeStore.getState().setPreset('week');
    void import('@/lib/notifications')
      .then((m) => m.syncDailySnapshotPreference())
      .catch(() => undefined);
  }, []);

  const logout = useCallback(async () => {
    await logoutCompanion();
    resetLocal();
  }, [resetLocal]);

  const selectOrganization = useCallback(
    async (orgId: number) => {
      if (!organizations.some((o) => o.id === orgId && String(o.role).toLowerCase() === 'owner')) {
        throw new Error('Only owner organizations can be selected in Pulse.');
      }
      await setStoredOrgId(orgId);
      setSelectedOrgId(orgId);
      useSpaceStore.getState().setSelectedSpaceId('all');
    },
    [organizations],
  );

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

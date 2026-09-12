import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import {
  ApiError,
  clearSession,
  getStoredClient,
  getStoredToken,
  login as apiLogin,
  logout as apiLogout,
  saveSession,
} from '@/lib/api';

type ClientProfile = Record<string, any> | null;

type AuthContextValue = {
  ready: boolean;
  token: string | null;
  client: ClientProfile;
  signIn: (input: {
    portal_token: string;
    phone?: string;
    email?: string;
    pin: string;
  }) => Promise<void>;
  signOut: () => Promise<void>;
  refreshClient: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [client, setClient] = useState<ClientProfile>(null);

  useEffect(() => {
    (async () => {
      const storedToken = await getStoredToken();
      const storedClient = await getStoredClient();
      setToken(storedToken);
      setClient(storedClient);
      setReady(true);
    })();
  }, []);

  const signIn = useCallback(async (input: {
    portal_token: string;
    phone?: string;
    email?: string;
    pin: string;
  }) => {
    const data = await apiLogin({
      ...input,
      device_label: 'Expo Wallet',
    });
    await saveSession(data.token, data.client, data.organization);
    setToken(data.token);
    setClient(data.client);
  }, []);

  const signOut = useCallback(async () => {
    try {
      if (token) await apiLogout();
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 401)) {
        // still clear local session
      }
    }
    await clearSession();
    setToken(null);
    setClient(null);
  }, [token]);

  const refreshClient = useCallback(async () => {
    const stored = await getStoredClient();
    setClient(stored);
  }, []);

  const value = useMemo(
    () => ({ ready, token, client, signIn, signOut, refreshClient }),
    [ready, token, client, signIn, signOut, refreshClient],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

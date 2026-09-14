import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import * as FileSystem from 'expo-file-system/legacy';

import {
  ApiError,
  clearSession,
  getHasSeenOnboarding,
  getStoredClient,
  getStoredToken,
  login as apiLogin,
  logout as apiLogout,
  saveSession,
  setHasSeenOnboarding,
  setUnauthorizedHandler,
} from '@/lib/api';
import { scrubSecretBackups } from '@/lib/storage';

type ClientProfile = Record<string, any> | null;

type AuthContextValue = {
  ready: boolean;
  token: string | null;
  client: ClientProfile;
  hasSeenOnboarding: boolean;
  signIn: (input: {
    portal_token: string;
    phone?: string;
    email?: string;
    pin: string;
  }) => Promise<void>;
  signOut: () => Promise<void>;
  refreshClient: () => Promise<void>;
  markOnboardingComplete: () => Promise<void>;
  resetOnboarding: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

async function clearDocumentCache(): Promise<void> {
  try {
    const dir = FileSystem.cacheDirectory;
    if (!dir) return;
    const entries = await FileSystem.readDirectoryAsync(dir);
    await Promise.all(
      entries
        .filter((name) => name.startsWith('wallet_') || name.startsWith('wallet_preview_'))
        .map((name) => FileSystem.deleteAsync(`${dir}${name}`, { idempotent: true }).catch(() => undefined)),
    );
  } catch {
    // ignore cache cleanup failures
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [client, setClient] = useState<ClientProfile>(null);
  const [hasSeenOnboarding, setHasSeenOnboardingState] = useState<boolean>(false);
  const signingOutRef = useRef(false);

  const forceLocalSignOut = useCallback(async () => {
    if (signingOutRef.current) return;
    signingOutRef.current = true;
    try {
      await clearSession();
      await clearDocumentCache();
      setToken(null);
      setClient(null);
    } finally {
      signingOutRef.current = false;
    }
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      void forceLocalSignOut();
    });
    return () => setUnauthorizedHandler(null);
  }, [forceLocalSignOut]);

  useEffect(() => {
    (async () => {
      await scrubSecretBackups();
      const storedToken = await getStoredToken();
      const storedClient = await getStoredClient();
      const seenOnboarding = await getHasSeenOnboarding();
      setToken(storedToken);
      setClient(storedClient);
      setHasSeenOnboardingState(seenOnboarding);
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
      device_label: 'RegiManager Wallet',
    });
    await saveSession(data.token, data.client, data.organization);
    await setHasSeenOnboarding(true);
    setHasSeenOnboardingState(true);
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
    await forceLocalSignOut();
  }, [token, forceLocalSignOut]);

  const refreshClient = useCallback(async () => {
    const stored = await getStoredClient();
    setClient(stored);
  }, []);

  const markOnboardingComplete = useCallback(async () => {
    await setHasSeenOnboarding(true);
    setHasSeenOnboardingState(true);
  }, []);

  const resetOnboarding = useCallback(async () => {
    await setHasSeenOnboarding(false);
    setHasSeenOnboardingState(false);
  }, []);

  const value = useMemo(
    () => ({
      ready,
      token,
      client,
      hasSeenOnboarding,
      signIn,
      signOut,
      refreshClient,
      markOnboardingComplete,
      resetOnboarding,
    }),
    [
      ready,
      token,
      client,
      hasSeenOnboarding,
      signIn,
      signOut,
      refreshClient,
      markOnboardingComplete,
      resetOnboarding,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

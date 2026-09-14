import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [client, setClient] = useState<ClientProfile>(null);
  const [hasSeenOnboarding, setHasSeenOnboardingState] = useState<boolean>(false);

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
    // Completing login implies onboarding is done — never show it again.
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
    // Keep onboarding + biometric credentials — only clear active session token.
    await clearSession();
    setToken(null);
    setClient(null);
  }, [token]);

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

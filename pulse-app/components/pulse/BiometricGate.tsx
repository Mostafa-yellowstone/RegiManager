import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { AppState, type AppStateStatus, Pressable, Text, View } from 'react-native';

import { useAuth } from '@/lib/auth';
import {
  authenticateWithBiometrics,
  getBiometricCapability,
  isBiometricLockEnabled,
} from '@/lib/biometrics';
import { Colors, Fonts } from '@/lib/theme';

const BACKGROUND_LOCK_MS = 30_000;

type Props = {
  children: ReactNode;
};

export function BiometricGate({ children }: Props) {
  const { token, ready } = useAuth();
  const [checking, setChecking] = useState(true);
  const [locked, setLocked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [label, setLabel] = useState('Biometrics');
  const backgroundAt = useRef<number | null>(null);

  const evaluateLock = useCallback(async () => {
    if (!token) {
      setLocked(false);
      setChecking(false);
      return;
    }
    const enabled = await isBiometricLockEnabled();
    const capability = await getBiometricCapability();
    setLabel(capability.label);
    if (enabled && capability.hardware && capability.enrolled) {
      setLocked(true);
    } else {
      setLocked(false);
    }
    setChecking(false);
  }, [token]);

  useEffect(() => {
    if (!ready) return;
    void evaluateLock();
  }, [ready, evaluateLock]);

  useEffect(() => {
    const onChange = (next: AppStateStatus) => {
      if (!token) return;
      if (next === 'background' || next === 'inactive') {
        backgroundAt.current = Date.now();
        return;
      }
      if (next === 'active' && backgroundAt.current != null) {
        const elapsed = Date.now() - backgroundAt.current;
        backgroundAt.current = null;
        if (elapsed >= BACKGROUND_LOCK_MS) {
          void (async () => {
            const enabled = await isBiometricLockEnabled();
            if (enabled) setLocked(true);
          })();
        }
      }
    };
    const sub = AppState.addEventListener('change', onChange);
    return () => sub.remove();
  }, [token]);

  async function unlock() {
    setBusy(true);
    setError('');
    const result = await authenticateWithBiometrics(`Unlock Pulse with ${label}`);
    setBusy(false);
    if (result.ok) {
      setLocked(false);
      return;
    }
    setError(result.message);
  }

  if (!ready || checking) {
    return (
      <View style={{ flex: 1, backgroundColor: Colors.navy, alignItems: 'center', justifyContent: 'center' }}>
        <Text style={{ fontFamily: Fonts.bold, color: Colors.teal }}>Pulse</Text>
      </View>
    );
  }

  if (!locked) return <>{children}</>;

  return (
    <View
      style={{
        flex: 1,
        backgroundColor: Colors.navy,
        paddingHorizontal: 24,
        justifyContent: 'center',
      }}
    >
      <Text
        style={{
          fontFamily: Fonts.extrabold,
          fontSize: 34,
          color: Colors.teal,
          letterSpacing: -0.6,
        }}
      >
        Pulse
      </Text>
      <Text
        style={{
          marginTop: 10,
          fontFamily: Fonts.medium,
          fontSize: 15,
          color: 'rgba(255,255,255,0.72)',
          lineHeight: 22,
        }}
      >
        Owner data is locked. Use {label.toLowerCase()} to open your dashboard.
      </Text>
      {error ? (
        <Text style={{ marginTop: 12, fontFamily: Fonts.medium, fontSize: 13, color: '#FDBA74' }}>
          {error}
        </Text>
      ) : null}
      <Pressable
        onPress={() => void unlock()}
        disabled={busy}
        style={{
          marginTop: 24,
          alignItems: 'center',
          borderRadius: 14,
          paddingVertical: 14,
          backgroundColor: Colors.teal,
          opacity: busy ? 0.7 : 1,
        }}
      >
        <Text style={{ fontFamily: Fonts.extrabold, fontSize: 15, color: Colors.white }}>
          {busy ? 'Checking…' : `Unlock with ${label}`}
        </Text>
      </Pressable>
    </View>
  );
}

import * as LocalAuthentication from 'expo-local-authentication';

import { kvDelete, kvGet, kvSet } from '@/lib/storage';

const BIOMETRIC_PREF_KEY = 'pulse_biometric_lock_enabled';

export type BiometricCapability = {
  hardware: boolean;
  enrolled: boolean;
  label: string;
};

export async function getBiometricCapability(): Promise<BiometricCapability> {
  try {
    const hardware = await LocalAuthentication.hasHardwareAsync();
    const enrolled = hardware ? await LocalAuthentication.isEnrolledAsync() : false;
    const types = hardware ? await LocalAuthentication.supportedAuthenticationTypesAsync() : [];
    const hasFace = types.includes(LocalAuthentication.AuthenticationType.FACIAL_RECOGNITION);
    const hasFinger = types.includes(LocalAuthentication.AuthenticationType.FINGERPRINT);
    let label = 'Biometrics';
    if (hasFace && hasFinger) label = 'Face ID or fingerprint';
    else if (hasFace) label = 'Face ID';
    else if (hasFinger) label = 'Fingerprint';
    return { hardware, enrolled, label };
  } catch {
    return { hardware: false, enrolled: false, label: 'Biometrics' };
  }
}

export async function isBiometricLockEnabled(): Promise<boolean> {
  return (await kvGet(BIOMETRIC_PREF_KEY)) === '1';
}

export async function setBiometricLockEnabled(enabled: boolean): Promise<void> {
  if (enabled) await kvSet(BIOMETRIC_PREF_KEY, '1');
  else await kvDelete(BIOMETRIC_PREF_KEY);
}

export async function authenticateWithBiometrics(promptMessage?: string): Promise<{
  ok: boolean;
  message: string;
}> {
  const capability = await getBiometricCapability();
  if (!capability.hardware) {
    return { ok: false, message: 'This device does not support biometrics.' };
  }
  if (!capability.enrolled) {
    return {
      ok: false,
      message: `Set up ${capability.label.toLowerCase()} in device settings first.`,
    };
  }

  try {
    const result = await LocalAuthentication.authenticateAsync({
      promptMessage: promptMessage || `Unlock Pulse with ${capability.label}`,
      cancelLabel: 'Cancel',
      disableDeviceFallback: false,
      fallbackLabel: 'Use passcode',
    });
    if (result.success) return { ok: true, message: 'Unlocked.' };
    return { ok: false, message: result.error || 'Authentication canceled.' };
  } catch (err: any) {
    return { ok: false, message: err?.message || 'Could not authenticate.' };
  }
}

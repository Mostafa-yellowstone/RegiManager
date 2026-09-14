import * as LocalAuthentication from 'expo-local-authentication';

import { kvDelete, kvGet, kvSet } from '@/lib/storage';

const CREDENTIALS_KEY = 'client_app_saved_credentials';
const BIOMETRIC_ENABLED_KEY = 'client_app_biometric_enabled';

export type SavedCredentials = {
  portal_token: string;
  phone?: string;
  email?: string;
  pin: string;
};

export async function getBiometricHardware(): Promise<{
  compatible: boolean;
  enrolled: boolean;
  label: string;
}> {
  try {
    const compatible = await LocalAuthentication.hasHardwareAsync();
    const enrolled = compatible ? await LocalAuthentication.isEnrolledAsync() : false;
    const types = compatible ? await LocalAuthentication.supportedAuthenticationTypesAsync() : [];
    const hasFace = types.includes(LocalAuthentication.AuthenticationType.FACIAL_RECOGNITION);
    const hasFinger = types.includes(LocalAuthentication.AuthenticationType.FINGERPRINT);
    const hasIris = types.includes(LocalAuthentication.AuthenticationType.IRIS);
    let label = 'Biometrics';
    if (hasFinger && !hasFace) label = 'Fingerprint';
    else if (hasFace && !hasFinger) label = 'Face ID';
    else if (hasFinger && hasFace) label = 'Fingerprint / Face ID';
    else if (hasIris) label = 'Iris';
    return { compatible, enrolled, label };
  } catch {
    return { compatible: false, enrolled: false, label: 'Biometrics' };
  }
}

export async function isBiometricLoginEnabled(): Promise<boolean> {
  const flag = await kvGet(BIOMETRIC_ENABLED_KEY);
  if (flag !== 'true') return false;
  const creds = await getSavedCredentials();
  return !!creds?.portal_token && !!creds?.pin;
}

export async function getSavedCredentials(): Promise<SavedCredentials | null> {
  const raw = await kvGet(CREDENTIALS_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as SavedCredentials;
    if (!parsed?.portal_token || !parsed?.pin) return null;
    return parsed;
  } catch {
    return null;
  }
}

export async function enableBiometricLogin(creds: SavedCredentials): Promise<void> {
  const hw = await getBiometricHardware();
  if (!hw.compatible || !hw.enrolled) {
    throw new Error(`${hw.label} is not set up on this device.`);
  }
  const ok = await LocalAuthentication.authenticateAsync({
    promptMessage: `Enable ${hw.label} sign-in`,
    cancelLabel: 'Cancel',
    disableDeviceFallback: false,
    fallbackLabel: 'Use device passcode',
  });
  if (!ok.success) {
    throw new Error('Biometric confirmation was cancelled.');
  }
  await kvSet(
    CREDENTIALS_KEY,
    JSON.stringify({
      portal_token: creds.portal_token.trim(),
      pin: creds.pin.trim(),
      ...(creds.email ? { email: creds.email.trim() } : {}),
      ...(creds.phone ? { phone: creds.phone.trim() } : {}),
    }),
  );
  await kvSet(BIOMETRIC_ENABLED_KEY, 'true');
}

export async function disableBiometricLogin(): Promise<void> {
  await kvDelete(CREDENTIALS_KEY);
  await kvDelete(BIOMETRIC_ENABLED_KEY);
}

/**
 * Prompt biometrics, then return the securely stored credentials
 * so the app can call the normal login API (credentials stay linked).
 */
export async function unlockCredentialsWithBiometrics(): Promise<SavedCredentials> {
  const enabled = await isBiometricLoginEnabled();
  if (!enabled) {
    throw new Error('Biometric sign-in is not enabled yet.');
  }
  const hw = await getBiometricHardware();
  const result = await LocalAuthentication.authenticateAsync({
    promptMessage: `Sign in with ${hw.label}`,
    cancelLabel: 'Cancel',
    disableDeviceFallback: false,
    fallbackLabel: 'Use device passcode',
  });
  if (!result.success) {
    throw new Error('Biometric unlock failed or was cancelled.');
  }
  const creds = await getSavedCredentials();
  if (!creds) {
    await disableBiometricLogin();
    throw new Error('Saved credentials missing. Sign in with PIN again.');
  }
  return creds;
}

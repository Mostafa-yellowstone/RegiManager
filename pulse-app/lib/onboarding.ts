import { kvDelete, kvGet, kvSet } from '@/lib/storage';

const ONBOARDING_KEY = 'pulse_onboarding_v1_done';

export async function hasCompletedOnboarding(): Promise<boolean> {
  const value = await kvGet(ONBOARDING_KEY);
  return value === '1';
}

export async function markOnboardingComplete(): Promise<void> {
  await kvSet(ONBOARDING_KEY, '1');
}

/** Dev/testing helper — not used in production UI. */
export async function resetOnboarding(): Promise<void> {
  await kvDelete(ONBOARDING_KEY);
}

import { kvDelete, kvGet, kvSet } from '@/lib/storage';

const ONBOARDING_KEY = 'pulse_onboarding_v1_done';

type Listener = (done: boolean) => void;
const listeners = new Set<Listener>();

/** In-memory latch so AuthGate updates before navigation completes. */
let memoryDone = false;

export function subscribeOnboarding(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export async function hasCompletedOnboarding(): Promise<boolean> {
  if (memoryDone) return true;
  const value = await kvGet(ONBOARDING_KEY);
  const done = value === '1';
  if (done) memoryDone = true;
  return done;
}

export async function markOnboardingComplete(): Promise<void> {
  memoryDone = true;
  await kvSet(ONBOARDING_KEY, '1');
  listeners.forEach((listener) => listener(true));
}

/** Dev/testing helper — not used in production UI. */
export async function resetOnboarding(): Promise<void> {
  memoryDone = false;
  await kvDelete(ONBOARDING_KEY);
  listeners.forEach((listener) => listener(false));
}

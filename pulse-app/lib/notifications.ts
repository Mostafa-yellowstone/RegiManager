import Constants from 'expo-constants';
import { Platform } from 'react-native';

import { apiFetch } from '@/lib/api';
import { kvDelete, kvGet, kvSet } from '@/lib/storage';

const PREF_KEY = 'pulse_daily_snapshot_enabled';
const SCHEDULE_ID_KEY = 'pulse_daily_snapshot_schedule_id';
/** Must match ACTIVITY_CHANNEL_ID in core/push_notifications.py. */
const ACTIVITY_CHANNEL_ID = 'pulse-activity';

/** Expo Go on Android cannot load expo-notifications (remote push removed in SDK 53+). */
function isExpoGo(): boolean {
  return Constants.appOwnership === 'expo';
}

type NotificationsModule = typeof import('expo-notifications');

let notificationsModule: NotificationsModule | null | undefined;
let handlerReady = false;

async function getNotifications(): Promise<NotificationsModule | null> {
  if (isExpoGo()) return null;
  if (notificationsModule !== undefined) return notificationsModule;
  try {
    notificationsModule = await import('expo-notifications');
    return notificationsModule;
  } catch {
    notificationsModule = null;
    return null;
  }
}

async function ensureHandler(Notifications: NotificationsModule) {
  if (handlerReady) return;
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
  handlerReady = true;
}

export async function isDailySnapshotEnabled(): Promise<boolean> {
  return (await kvGet(PREF_KEY)) === '1';
}

export async function setDailySnapshotEnabled(enabled: boolean): Promise<{ ok: boolean; message: string }> {
  if (enabled) {
    const result = await enableDailySnapshot();
    if (result.ok) {
      await kvSet(PREF_KEY, '1');
    }
    return result;
  }
  await kvSet(PREF_KEY, '0');
  await disableDailySnapshot();
  return { ok: true, message: 'Daily reminder turned off.' };
}

async function ensurePermissions(Notifications: NotificationsModule): Promise<boolean> {
  const current = await Notifications.getPermissionsAsync();
  if (
    current.granted ||
    current.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL
  ) {
    return true;
  }
  const asked = await Notifications.requestPermissionsAsync();
  return Boolean(
    asked.granted || asked.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL,
  );
}

async function ensureChannels(Notifications: NotificationsModule) {
  if (Platform.OS !== 'android') return;
  await Notifications.setNotificationChannelAsync(ACTIVITY_CHANNEL_ID, {
    name: 'Policies bound & DMV transactions',
    description: 'Instant alerts when a policy is bound or a DMV transaction is recorded.',
    importance: Notifications.AndroidImportance.HIGH,
    sound: 'default',
    vibrationPattern: [0, 200, 120, 200],
    lightColor: '#3DDC97',
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
  });
  await Notifications.setNotificationChannelAsync('pulse-daily', {
    name: 'Pulse daily snapshot',
    importance: Notifications.AndroidImportance.DEFAULT,
  });
}

function easProjectId(): string | undefined {
  return (
    (Constants.expoConfig?.extra as any)?.eas?.projectId ||
    (Constants as any).easConfig?.projectId ||
    undefined
  );
}

async function registerPushToken(Notifications: NotificationsModule): Promise<boolean> {
  try {
    await ensureChannels(Notifications);
    const projectId = easProjectId();
    const tokenData = await Notifications.getExpoPushTokenAsync(projectId ? { projectId } : undefined);
    const token = tokenData.data;
    if (!token) return false;
    await apiFetch('/api/push/register/', {
      method: 'POST',
      body: {
        token,
        platform: Platform.OS === 'ios' ? 'ios' : 'android',
      },
    });
    return true;
  } catch {
    return false;
  }
}

/**
 * Register this phone for instant policy-bound and DMV alerts. They are delivered by
 * the server, so they arrive in the notification center even when Pulse is closed.
 */
export async function registerActivityPush(): Promise<{ ok: boolean; message: string }> {
  try {
    const Notifications = await getNotifications();
    if (!Notifications) {
      return { ok: false, message: 'Phone alerts need the installed Pulse app (not Expo Go).' };
    }
    await ensureHandler(Notifications);
    if (!(await ensurePermissions(Notifications))) {
      return { ok: false, message: 'Notifications are turned off for Pulse in your phone settings.' };
    }
    const ok = await registerPushToken(Notifications);
    return ok
      ? { ok: true, message: 'Phone alerts are on for bound policies and DMV transactions.' }
      : { ok: false, message: 'Could not register this phone for alerts. Try again later.' };
  } catch {
    return { ok: false, message: 'Could not register this phone for alerts.' };
  }
}

export async function enableDailySnapshot(): Promise<{ ok: boolean; message: string }> {
  const Notifications = await getNotifications();
  if (!Notifications) {
    // Preference is still stored; scheduling needs a dev/production build.
    return {
      ok: true,
      message:
        'Preference saved. Local reminders need a development or production build (not Expo Go on Android).',
    };
  }

  await ensureHandler(Notifications);
  const allowed = await ensurePermissions(Notifications);
  if (!allowed) {
    return { ok: false, message: 'Notification permission was denied.' };
  }

  await disableDailySnapshot();
  await registerPushToken(Notifications);

  const id = await Notifications.scheduleNotificationAsync({
    content: {
      title: 'Pulse daily snapshot',
      body: "Yesterday's profit, expenses, and staff. Tap to open your Pulse brief.",
      data: { type: 'pulse_daily_snapshot' },
      ...(Platform.OS === 'android' ? { channelId: 'pulse-daily' } : {}),
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DAILY,
      hour: 18,
      minute: 0,
    },
  });
  await kvSet(SCHEDULE_ID_KEY, id);
  return { ok: true, message: 'Daily reminder set for 6:00 PM.' };
}

export async function disableDailySnapshot(): Promise<void> {
  const id = await kvGet(SCHEDULE_ID_KEY);
  if (!id) return;
  const Notifications = await getNotifications();
  if (Notifications) {
    try {
      await Notifications.cancelScheduledNotificationAsync(id);
    } catch {
      // ignore
    }
  }
  await kvDelete(SCHEDULE_ID_KEY);
}

/** Re-apply schedule after login when preference is on (no-op crash-safe in Expo Go). */
export async function syncDailySnapshotPreference(): Promise<void> {
  try {
    await registerActivityPush();
    if (await isDailySnapshotEnabled()) {
      await enableDailySnapshot();
    }
  } catch {
    // Never block auth/bootstrap on notification setup.
  }
}

export type NotificationTapType = 'pulse_daily_snapshot' | 'policy_bound' | 'dmv_transaction' | 'expense_alert';

const TAP_TYPES = new Set<string>(['pulse_daily_snapshot', 'policy_bound', 'dmv_transaction', 'expense_alert']);

/**
 * Route notification taps (warm and cold start). Safe no-op in Expo Go / missing module.
 * Returns an unsubscribe function.
 */
export async function registerNotificationTapHandler(
  onOpen: (type: NotificationTapType) => void,
): Promise<() => void> {
  const Notifications = await getNotifications();
  if (!Notifications) return () => undefined;

  try {
    await ensureHandler(Notifications);
  } catch {
    return () => undefined;
  }

  const route = (type: unknown) => {
    if (typeof type === 'string' && TAP_TYPES.has(type)) onOpen(type as NotificationTapType);
  };

  const sub = Notifications.addNotificationResponseReceivedListener((response) => {
    route(response?.notification?.request?.content?.data?.type);
  });

  try {
    const last = await Notifications.getLastNotificationResponseAsync();
    route(last?.notification?.request?.content?.data?.type);
  } catch {
    // ignore cold-start read failures
  }

  return () => {
    try {
      sub.remove();
    } catch {
      // ignore
    }
  };
}

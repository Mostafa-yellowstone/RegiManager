import Constants from 'expo-constants';
import { Platform } from 'react-native';

import { apiFetch } from '@/lib/api';
import { kvDelete, kvGet, kvSet } from '@/lib/storage';

const PREF_KEY = 'pulse_daily_snapshot_enabled';
const SCHEDULE_ID_KEY = 'pulse_daily_snapshot_schedule_id';

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
      shouldPlaySound: false,
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

async function registerPushToken(Notifications: NotificationsModule): Promise<void> {
  try {
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('pulse-daily', {
        name: 'Pulse daily snapshot',
        importance: Notifications.AndroidImportance.DEFAULT,
      });
    }
    const tokenData = await Notifications.getExpoPushTokenAsync();
    const token = tokenData.data;
    if (!token) return;
    await apiFetch('/api/push/register/', {
      method: 'POST',
      body: {
        token,
        platform: Platform.OS === 'ios' ? 'ios' : 'android',
      },
    });
  } catch {
    // Local schedule can still work without remote push registration.
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
    if (await isDailySnapshotEnabled()) {
      await enableDailySnapshot();
    }
  } catch {
    // Never block auth/bootstrap on notification setup.
  }
}

type SnapshotRouteHandler = () => void;

/**
 * Route notification taps to Pulse home. Safe no-op in Expo Go / missing module.
 * Returns an unsubscribe function.
 */
export async function registerSnapshotNotificationHandler(
  onOpenSnapshot: SnapshotRouteHandler,
): Promise<() => void> {
  const Notifications = await getNotifications();
  if (!Notifications) return () => undefined;

  try {
    await ensureHandler(Notifications);
  } catch {
    return () => undefined;
  }

  const sub = Notifications.addNotificationResponseReceivedListener((response) => {
    const type = response?.notification?.request?.content?.data?.type;
    if (type === 'pulse_daily_snapshot') {
      onOpenSnapshot();
    }
  });

  try {
    const last = await Notifications.getLastNotificationResponseAsync();
    const type = last?.notification?.request?.content?.data?.type;
    if (type === 'pulse_daily_snapshot') {
      onOpenSnapshot();
    }
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

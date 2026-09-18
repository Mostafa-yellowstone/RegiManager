import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, Switch, Text, View } from 'react-native';
import { useRouter } from 'expo-router';

import { useAuth } from '@/lib/auth';
import { crmHomeUrl, openCrmUrl } from '@/lib/crmLinks';
import { hapticSelection } from '@/lib/haptics';
import { isDailySnapshotEnabled, setDailySnapshotEnabled } from '@/lib/notifications';
import { Colors } from '@/lib/theme';

export default function SettingsScreen() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const [loading, setLoading] = useState(true);
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const on = await isDailySnapshotEnabled();
      if (!cancelled) {
        setEnabled(on);
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onToggle(next: boolean) {
    setBusy(true);
    setMessage('');
    try {
      const result = await setDailySnapshotEnabled(next);
      if (!result.ok) {
        setEnabled(false);
        setMessage(result.message || 'Could not enable notifications.');
        return;
      }
      setEnabled(next);
      setMessage(
        result.message ||
          (next
            ? 'Daily reminder enabled for 6:00 PM. Push token registered when available.'
            : 'Daily reminder turned off.'),
      );
    } catch (err: any) {
      setMessage(err?.message || 'Could not update notification preference.');
      setEnabled(!next);
    } finally {
      setBusy(false);
    }
  }

  async function onSignOut() {
    await hapticSelection();
    await logout();
    router.replace('/login');
  }

  return (
    <View className="flex-1 bg-cream p-4">
      <View
        className="rounded-2xl bg-white p-4"
        style={{ borderWidth: 1, borderColor: Colors.border }}
      >
        <Text className="text-title text-navy">Account</Text>
        {user?.full_name || user?.email ? (
          <Text className="mt-1 text-caption text-muted">
            {[user?.full_name, user?.email].filter(Boolean).join(' · ')}
          </Text>
        ) : null}
        <Text className="mt-1 text-caption text-muted">
          Owner account only. Pulse is view-only — use the CRM for edits.
        </Text>
        <Pressable
          onPress={() => {
            void hapticSelection();
            void openCrmUrl(crmHomeUrl());
          }}
          className="mt-3 items-center rounded-xl px-4 py-3"
          style={{ backgroundColor: Colors.navySoft }}
        >
          <Text className="text-body font-extrabold text-navy">Open RegiManager CRM</Text>
        </Pressable>
        <Pressable
          onPress={() => void onSignOut()}
          className="mt-3 items-center rounded-xl px-4 py-3"
          style={{ backgroundColor: Colors.tealSoft }}
          android_ripple={{ color: 'rgba(13,148,136,0.15)' }}
        >
          <Text className="text-body font-extrabold text-teal">Sign out</Text>
        </Pressable>
      </View>

      <View
        className="mt-4 rounded-2xl bg-white p-4"
        style={{ borderWidth: 1, borderColor: Colors.border }}
      >
        <Text className="text-title text-navy">Daily snapshot</Text>
        <Text className="mt-1 text-caption text-muted">
          6:00 PM reminder opens yesterday&apos;s brief on Pulse (profit, expenses, staff).
        </Text>
        <View className="mt-4 flex-row items-center justify-between">
          <Text className="text-body font-bold text-navy">Enable 6:00 PM reminder</Text>
          {loading ? (
            <ActivityIndicator color={Colors.teal} />
          ) : (
            <Switch
              value={enabled}
              onValueChange={(v) => void onToggle(v)}
              disabled={busy}
              trackColor={{ true: Colors.teal, false: Colors.border }}
            />
          )}
        </View>
        {message ? <Text className="mt-3 text-caption text-muted">{message}</Text> : null}
      </View>

      <View
        className="mt-4 rounded-2xl bg-white p-4"
        style={{ borderWidth: 1, borderColor: Colors.border }}
      >
        <Text className="text-caption text-muted">
          On Expo Go (Android), the reminder preference is saved but scheduling needs a development
          or production build. Server digests use `python manage.py send_pulse_daily_snapshot`.
        </Text>
      </View>
    </View>
  );
}

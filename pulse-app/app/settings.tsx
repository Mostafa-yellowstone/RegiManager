import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, Switch, Text, View } from 'react-native';
import { useRouter } from 'expo-router';

import { useAuth } from '@/lib/auth';
import { crmHomeUrl, openCrmUrl } from '@/lib/crmLinks';
import { hapticSelection } from '@/lib/haptics';
import { isDailySnapshotEnabled, setDailySnapshotEnabled } from '@/lib/notifications';
import { Colors, Fonts } from '@/lib/theme';

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
    <View style={{ flex: 1, backgroundColor: Colors.cream, padding: 16, gap: 16 }}>
      <View
        style={{
          borderRadius: 16,
          backgroundColor: Colors.white,
          padding: 16,
          borderWidth: 1,
          borderColor: Colors.border,
        }}
      >
        <Text style={{ fontFamily: Fonts.bold, fontSize: 20, color: Colors.navy }}>Account</Text>
        {user?.full_name ? (
          <Text
            style={{
              marginTop: 8,
              fontFamily: Fonts.extrabold,
              fontSize: 22,
              color: Colors.navy,
              letterSpacing: -0.3,
            }}
          >
            {user.full_name}
          </Text>
        ) : null}
        {user?.email ? (
          <Text style={{ marginTop: 4, fontFamily: Fonts.medium, fontSize: 13, color: Colors.muted }}>
            {user.email}
          </Text>
        ) : null}
        <Text style={{ marginTop: 8, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
          Owner account only. Pulse is read-only — edit in CRM.
        </Text>
        <Pressable
          onPress={() => {
            void hapticSelection();
            void openCrmUrl(crmHomeUrl());
          }}
          style={{
            marginTop: 14,
            alignItems: 'center',
            borderRadius: 12,
            paddingHorizontal: 16,
            paddingVertical: 12,
            backgroundColor: Colors.tealSoft,
            borderWidth: 1,
            borderColor: '#99F6E4',
          }}
        >
          <Text style={{ fontFamily: Fonts.extrabold, fontSize: 15, color: Colors.tealDeep }}>
            Open RegiManager CRM
          </Text>
        </Pressable>
        <Pressable
          onPress={() => void onSignOut()}
          style={{
            marginTop: 10,
            alignItems: 'center',
            borderRadius: 12,
            paddingHorizontal: 16,
            paddingVertical: 12,
            backgroundColor: Colors.white,
            borderWidth: 1,
            borderColor: Colors.border,
          }}
          android_ripple={{ color: 'rgba(13,148,136,0.12)' }}
        >
          <Text style={{ fontFamily: Fonts.extrabold, fontSize: 15, color: Colors.navy }}>Sign out</Text>
        </Pressable>
      </View>

      <View
        style={{
          borderRadius: 16,
          backgroundColor: Colors.white,
          padding: 16,
          borderWidth: 1,
          borderColor: Colors.border,
        }}
      >
        <Text style={{ fontFamily: Fonts.bold, fontSize: 20, color: Colors.navy }}>Daily snapshot</Text>
        <Text style={{ marginTop: 6, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
          6:00 PM reminder opens yesterday&apos;s brief on Pulse (profit, expenses, staff).
        </Text>
        <View
          style={{
            marginTop: 16,
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <Text style={{ flex: 1, fontFamily: Fonts.bold, fontSize: 15, color: Colors.navy }}>
            Enable 6:00 PM reminder
          </Text>
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
        {message ? (
          <Text style={{ marginTop: 12, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
            {message}
          </Text>
        ) : null}
      </View>
    </View>
  );
}

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, Switch, Text, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';

import { getExpenseWatch, updateExpenseWatch } from '@/data/repositories/leaderboardRepository';
import { useAuth } from '@/lib/auth';
import {
  authenticateWithBiometrics,
  getBiometricCapability,
  isBiometricLockEnabled,
  setBiometricLockEnabled,
} from '@/lib/biometrics';
import { crmHomeUrl, openCrmUrl } from '@/lib/crmLinks';
import { hapticSelection } from '@/lib/haptics';
import { isDailySnapshotEnabled, registerActivityPush, setDailySnapshotEnabled } from '@/lib/notifications';
import { Colors, Fonts } from '@/lib/theme';

export default function SettingsScreen() {
  const router = useRouter();
  const { user, logout, selectedOrg } = useAuth();
  const [loading, setLoading] = useState(true);
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [bioLoading, setBioLoading] = useState(true);
  const [bioEnabled, setBioEnabled] = useState(false);
  const [bioBusy, setBioBusy] = useState(false);
  const [bioMessage, setBioMessage] = useState('');
  const [bioLabel, setBioLabel] = useState('Biometrics');
  const [bioAvailable, setBioAvailable] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);
  const [pushMessage, setPushMessage] = useState('');
  const queryClient = useQueryClient();
  const watchQuery = useQuery({
    queryKey: ['pulse-expense-watch', selectedOrg?.id],
    queryFn: () => getExpenseWatch(),
    enabled: Boolean(selectedOrg?.id),
  });
  const [watchEnabled, setWatchEnabled] = useState(true);
  const [watchLimit, setWatchLimit] = useState('');
  const [watchPercent, setWatchPercent] = useState('');
  const [watchSaving, setWatchSaving] = useState(false);
  const [watchMessage, setWatchMessage] = useState('');
  const watchSettings = watchQuery.data?.settings;

  useEffect(() => {
    if (!watchSettings) return;
    setWatchEnabled(watchSettings.enabled);
    setWatchLimit(String(watchSettings.single_expense_limit));
    setWatchPercent(String(watchSettings.category_jump_percent));
  }, [watchSettings]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [on, bioOn, capability] = await Promise.all([
        isDailySnapshotEnabled(),
        isBiometricLockEnabled(),
        getBiometricCapability(),
      ]);
      if (cancelled) return;
      setEnabled(on);
      setBioEnabled(bioOn);
      setBioLabel(capability.label);
      setBioAvailable(capability.hardware && capability.enrolled);
      setLoading(false);
      setBioLoading(false);
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

  async function onSaveWatch() {
    await hapticSelection();
    const limit = Number(watchLimit.replace(/[$,\s]/g, ''));
    const percent = Number(watchPercent.replace(/[%\s]/g, ''));
    if (!Number.isFinite(limit) || limit < 0 || !Number.isFinite(percent) || percent < 0 || percent > 1000) {
      setWatchMessage('Enter a dollar amount of 0 or more and a percent between 0 and 1000.');
      return;
    }
    setWatchSaving(true);
    setWatchMessage('');
    try {
      const saved = await updateExpenseWatch({
        enabled: watchEnabled,
        single_expense_limit: limit,
        category_jump_percent: percent,
      });
      queryClient.setQueryData(['pulse-expense-watch', selectedOrg?.id], saved);
      setWatchMessage('Expense alerts saved.');
    } catch (err: any) {
      setWatchMessage(err?.message || 'Could not save expense alerts.');
    } finally {
      setWatchSaving(false);
    }
  }

  async function onRegisterAlerts() {
    await hapticSelection();
    setPushBusy(true);
    setPushMessage('');
    try {
      const result = await registerActivityPush();
      setPushMessage(result.message);
    } finally {
      setPushBusy(false);
    }
  }

  async function onToggleBiometrics(next: boolean) {
    setBioBusy(true);
    setBioMessage('');
    try {
      if (next) {
        const auth = await authenticateWithBiometrics(`Enable ${bioLabel} lock for Pulse`);
        if (!auth.ok) {
          setBioEnabled(false);
          setBioMessage(auth.message);
          return;
        }
        await setBiometricLockEnabled(true);
        setBioEnabled(true);
        setBioMessage(`${bioLabel} lock enabled. Pulse will ask after 30 seconds in the background.`);
        return;
      }
      await setBiometricLockEnabled(false);
      setBioEnabled(false);
      setBioMessage(`${bioLabel} lock turned off.`);
    } catch (err: any) {
      setBioMessage(err?.message || 'Could not update biometric preference.');
      setBioEnabled(!next);
    } finally {
      setBioBusy(false);
    }
  }

  async function onSignOut() {
    await hapticSelection();
    await logout();
    router.replace('/login');
  }

  return (
    <ScrollView
      keyboardShouldPersistTaps="handled"
      style={{ flex: 1, backgroundColor: Colors.cream }}
      contentContainerStyle={{ padding: 16, gap: 16, paddingBottom: 40 }}
    >
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
          Owner account only. Pulse is read-only. Edit in CRM.
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
            borderColor: Colors.border,
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
        <Text style={{ fontFamily: Fonts.bold, fontSize: 20, color: Colors.navy }}>Security</Text>
        <Text style={{ marginTop: 6, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
          Lock Pulse with {bioLabel.toLowerCase()} when you leave the app. Tokens stay in device secure
          storage.
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
            {bioLabel} lock
          </Text>
          {bioLoading ? (
            <ActivityIndicator color={Colors.teal} />
          ) : (
            <Switch
              value={bioEnabled}
              onValueChange={(v) => void onToggleBiometrics(v)}
              disabled={bioBusy || !bioAvailable}
              trackColor={{ true: Colors.teal, false: Colors.border }}
            />
          )}
        </View>
        {!bioAvailable ? (
          <Text style={{ marginTop: 10, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
            Set up Face ID or fingerprint in device settings to enable this lock.
          </Text>
        ) : null}
        {bioMessage ? (
          <Text style={{ marginTop: 12, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
            {bioMessage}
          </Text>
        ) : null}
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
        <Text style={{ fontFamily: Fonts.bold, fontSize: 20, color: Colors.navy }}>Expense alerts</Text>
        <Text style={{ marginTop: 6, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
          Get a phone alert for one big DMV or insurance expense, or when a category this month passes last
          month by your percent (once per category each month).
        </Text>
        {watchQuery.isLoading ? (
          <ActivityIndicator style={{ marginTop: 16 }} color={Colors.teal} />
        ) : (
          <>
            <View style={{ marginTop: 16, flexDirection: 'row', alignItems: 'center', gap: 12 }}>
              <Text style={{ flex: 1, fontFamily: Fonts.bold, fontSize: 15, color: Colors.navy }}>
                Expense alerts on
              </Text>
              <Switch
                value={watchEnabled}
                onValueChange={setWatchEnabled}
                trackColor={{ true: Colors.teal, false: Colors.border }}
              />
            </View>
            <View style={{ marginTop: 14, flexDirection: 'row', gap: 10 }}>
              <LabeledInput
                label="One expense over ($)"
                value={watchLimit}
                onChangeText={setWatchLimit}
                editable={watchEnabled}
              />
              <LabeledInput
                label="Category up (%)"
                value={watchPercent}
                onChangeText={setWatchPercent}
                editable={watchEnabled}
              />
            </View>
            <Text style={{ marginTop: 6, fontFamily: Fonts.medium, fontSize: 11, color: Colors.muted }}>
              Use 0 to turn off just that rule.
            </Text>
            <Pressable
              onPress={() => void onSaveWatch()}
              disabled={watchSaving}
              style={{
                marginTop: 14,
                alignItems: 'center',
                borderRadius: 12,
                paddingVertical: 12,
                backgroundColor: Colors.tealSoft,
                borderWidth: 1,
                borderColor: Colors.border,
              }}
            >
              {watchSaving ? (
                <ActivityIndicator color={Colors.teal} />
              ) : (
                <Text style={{ fontFamily: Fonts.extrabold, fontSize: 15, color: Colors.tealDeep }}>
                  Save expense alerts
                </Text>
              )}
            </Pressable>
          </>
        )}
        {watchMessage ? (
          <Text style={{ marginTop: 12, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
            {watchMessage}
          </Text>
        ) : null}
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
        <Text style={{ fontFamily: Fonts.bold, fontSize: 20, color: Colors.navy }}>Phone alerts</Text>
        <Text style={{ marginTop: 6, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
          Instant alerts for bound policies (commission and broker fee) and DMV transactions (office fee and
          DMV fees), even when Pulse is closed.
        </Text>
        <Pressable
          onPress={() => void onRegisterAlerts()}
          disabled={pushBusy}
          style={{
            marginTop: 14,
            alignItems: 'center',
            borderRadius: 12,
            paddingVertical: 12,
            backgroundColor: Colors.tealSoft,
            borderWidth: 1,
            borderColor: Colors.border,
          }}
        >
          {pushBusy ? (
            <ActivityIndicator color={Colors.teal} />
          ) : (
            <Text style={{ fontFamily: Fonts.extrabold, fontSize: 15, color: Colors.tealDeep }}>
              Turn on / re-check phone alerts
            </Text>
          )}
        </Pressable>
        {pushMessage ? (
          <Text style={{ marginTop: 12, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
            {pushMessage}
          </Text>
        ) : null}
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
    </ScrollView>
  );
}

function LabeledInput({
  label,
  value,
  onChangeText,
  editable,
}: {
  label: string;
  value: string;
  onChangeText: (text: string) => void;
  editable: boolean;
}) {
  return (
    <View style={{ flex: 1, gap: 6 }}>
      <Text style={{ fontFamily: Fonts.semibold, fontSize: 12, color: Colors.muted }}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        editable={editable}
        keyboardType="decimal-pad"
        placeholderTextColor={Colors.muted}
        style={{
          borderRadius: 12,
          borderWidth: 1,
          borderColor: Colors.border,
          backgroundColor: Colors.cream,
          paddingHorizontal: 12,
          paddingVertical: 10,
          fontFamily: Fonts.bold,
          fontSize: 16,
          color: editable ? Colors.navy : Colors.muted,
        }}
      />
    </View>
  );
}

import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { Colors, Radius } from '@/constants/theme';
import { useAuth } from '@/lib/auth';
import { API_BASE_URL } from '@/lib/api';
import {
  AppLanguage,
  AppThemeMode,
  LANGUAGE_OPTIONS,
  THEME_OPTIONS,
  getLanguage,
  getThemeMode,
  setLanguage,
  setThemeMode,
} from '@/lib/prefs';

export default function ProfileScreen() {
  const { client, signOut } = useAuth();
  const [busy, setBusy] = useState(false);
  const [language, setLanguageState] = useState<AppLanguage>('en');
  const [theme, setThemeState] = useState<AppThemeMode>('system');

  useEffect(() => {
    (async () => {
      setLanguageState(await getLanguage());
      setThemeState(await getThemeMode());
    })();
  }, []);

  const onLanguage = useCallback(async (value: AppLanguage) => {
    setLanguageState(value);
    await setLanguage(value);
  }, []);

  const onTheme = useCallback(async (value: AppThemeMode) => {
    setThemeState(value);
    await setThemeMode(value);
  }, []);

  async function onLogout() {
    setBusy(true);
    try {
      await signOut();
    } finally {
      setBusy(false);
    }
  }

  const initials = (client?.full_name || 'Client')
    .split(' ')
    .map((n: string) => n[0])
    .join('')
    .substring(0, 2)
    .toUpperCase();

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <View style={styles.card}>
        <View style={styles.avatarHeader}>
          <View style={styles.avatarBox}>
            <Text style={styles.avatarText}>{initials || 'CL'}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>{client?.full_name || 'Account Holder'}</Text>
            <View style={styles.verifiedBadge}>
              <Text style={styles.verifiedText}>VERIFIED CLIENT</Text>
            </View>
          </View>
        </View>

        <View style={styles.divider} />

        <InfoRow label="Phone" value={client?.phone_number || 'Not provided'} />
        <InfoRow label="Email" value={client?.email || 'Not provided'} />
        {client?.driver_license ? <InfoRow label="Driver license" value={client.driver_license} /> : null}
        {client?.address ? <InfoRow label="Address" value={client.address} /> : null}
      </View>

      <Text style={styles.sectionTitle}>APP PREFERENCES</Text>
      <View style={styles.card}>
        <Text style={styles.prefLabel}>Language</Text>
        <View style={styles.chipRow}>
          {LANGUAGE_OPTIONS.map((opt) => (
            <Pressable
              key={opt.value}
              style={[styles.chip, language === opt.value && styles.chipActive]}
              onPress={() => onLanguage(opt.value)}
            >
              <Text style={[styles.chipText, language === opt.value && styles.chipTextActive]}>
                {opt.label}
              </Text>
            </Pressable>
          ))}
        </View>

        <Text style={[styles.prefLabel, { marginTop: 16 }]}>Theme mode</Text>
        <View style={styles.chipRow}>
          {THEME_OPTIONS.map((opt) => (
            <Pressable
              key={opt.value}
              style={[styles.chip, theme === opt.value && styles.chipActive]}
              onPress={() => onTheme(opt.value)}
            >
              <Text style={[styles.chipText, theme === opt.value && styles.chipTextActive]}>
                {opt.label}
              </Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.hint}>
          Preferences are saved on this device. Full theme styling and translations will apply as the portal expands.
        </Text>
      </View>

      <Text style={styles.sectionTitle}>RECOMMENDED</Text>
      <View style={styles.card}>
        <Text style={styles.recTitle}>Keep your contact details current</Text>
        <Text style={styles.recBody}>
          Ask your agency to update phone/email so renewals and payment reminders reach you.
        </Text>
        <View style={styles.divider} />
        <Text style={styles.recTitle}>Store ID cards in Document Vault</Text>
        <Text style={styles.recBody}>
          Request your insurance ID card upload so it appears under ID Cards and Documents.
        </Text>
        <View style={styles.divider} />
        <Text style={styles.recTitle}>Review upcoming dues monthly</Text>
        <Text style={styles.recBody}>
          Use Account Center notifications for installment dates and policy expirations.
        </Text>
      </View>

      <View style={styles.serverCard}>
        <Text style={styles.serverTitle}>CONNECTED PORTAL</Text>
        <Text style={styles.api}>{API_BASE_URL}</Text>
      </View>

      <Pressable
        style={({ pressed }) => [styles.logout, pressed && styles.logoutPressed, busy && styles.disabled]}
        onPress={onLogout}
        disabled={busy}
      >
        {busy ? (
          <ActivityIndicator color={Colors.white} />
        ) : (
          <Text style={styles.logoutText}>Sign Out</Text>
        )}
      </Pressable>
    </ScrollView>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoLabel}>{label.toUpperCase()}</Text>
      <Text style={styles.infoValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.cream },
  content: { padding: 18, paddingBottom: 40 },
  card: {
    backgroundColor: Colors.white,
    borderRadius: 18,
    padding: 18,
    borderWidth: 1,
    borderColor: Colors.border,
    marginBottom: 14,
  },
  avatarHeader: { flexDirection: 'row', alignItems: 'center' },
  avatarBox: {
    width: 54,
    height: 54,
    borderRadius: 16,
    backgroundColor: Colors.navy,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 14,
  },
  avatarText: { color: Colors.white, fontSize: 18, fontWeight: '800' },
  name: { fontSize: 19, fontWeight: '800', color: Colors.navy },
  verifiedBadge: {
    backgroundColor: Colors.successLight,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    alignSelf: 'flex-start',
    marginTop: 4,
  },
  verifiedText: { color: Colors.success, fontSize: 10, fontWeight: '800', letterSpacing: 0.5 },
  divider: { height: 1, backgroundColor: Colors.borderSubtle, marginVertical: 14 },
  infoRow: { marginBottom: 12 },
  infoLabel: { fontSize: 10, fontWeight: '800', color: Colors.mutedLight, letterSpacing: 0.6 },
  infoValue: { fontSize: 14, fontWeight: '700', color: Colors.navy, marginTop: 2 },
  sectionTitle: {
    fontSize: 11,
    fontWeight: '800',
    color: Colors.muted,
    letterSpacing: 0.8,
    marginBottom: 10,
    marginTop: 4,
  },
  prefLabel: { fontSize: 13, fontWeight: '800', color: Colors.navy, marginBottom: 8 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 10,
    backgroundColor: Colors.cream,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  chipActive: { backgroundColor: Colors.navy, borderColor: Colors.navy },
  chipText: { color: Colors.navy, fontWeight: '700', fontSize: 12 },
  chipTextActive: { color: Colors.white },
  hint: { color: Colors.muted, fontSize: 12, marginTop: 12, lineHeight: 17 },
  recTitle: { fontSize: 14, fontWeight: '800', color: Colors.navy },
  recBody: { color: Colors.muted, fontSize: 13, marginTop: 4, lineHeight: 18 },
  serverCard: {
    backgroundColor: Colors.white,
    borderRadius: Radius.md,
    padding: 16,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  serverTitle: { fontSize: 10, fontWeight: '800', color: Colors.mutedLight, letterSpacing: 0.6 },
  api: { color: Colors.muted, fontSize: 13, fontWeight: '600', marginTop: 4 },
  logout: {
    marginTop: 18,
    backgroundColor: Colors.danger,
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
  },
  logoutPressed: { opacity: 0.9 },
  disabled: { opacity: 0.6 },
  logoutText: { color: Colors.white, fontWeight: '800', fontSize: 15 },
});

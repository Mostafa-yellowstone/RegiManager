import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { Colors } from '@/constants/theme';
import { useAuth } from '@/lib/auth';
import { API_BASE_URL } from '@/lib/api';

export default function ProfileScreen() {
  const { client, signOut } = useAuth();
  const [busy, setBusy] = useState(false);

  async function onLogout() {
    setBusy(true);
    try {
      await signOut();
    } finally {
      setBusy(false);
    }
  }

  // Generate initials for avatar badge
  const initials = (client?.full_name || 'Client')
    .split(' ')
    .map((n: string) => n[0])
    .join('')
    .substring(0, 2)
    .toUpperCase();

  return (
    <View style={styles.screen}>
      {/* Client Identity Card */}
      <View style={styles.card}>
        <View style={styles.avatarHeader}>
          <View style={styles.avatarBox}>
            <Text style={styles.avatarText}>{initials || 'CL'}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>{client?.full_name || 'Account Holder'}</Text>
            <View style={styles.verifiedBadge}>
              <Text style={styles.verifiedText}>✓ VERIFIED CLIENT</Text>
            </View>
          </View>
        </View>

        <View style={styles.divider} />

        {/* Profile Info Rows */}
        <View style={styles.infoRow}>
          <Text style={styles.infoIcon}>📱</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.infoLabel}>PHONE NUMBER</Text>
            <Text style={styles.infoValue}>{client?.phone_number || 'Not provided'}</Text>
          </View>
        </View>

        <View style={styles.infoRow}>
          <Text style={styles.infoIcon}>✉️</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.infoLabel}>EMAIL ADDRESS</Text>
            <Text style={styles.infoValue}>{client?.email || 'Not provided'}</Text>
          </View>
        </View>

        {client?.driver_license ? (
          <View style={styles.infoRow}>
            <Text style={styles.infoIcon}>🪪</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.infoLabel}>DRIVER LICENSE</Text>
              <Text style={styles.infoValue}>{client.driver_license}</Text>
            </View>
          </View>
        ) : null}
      </View>

      {/* System Server Connection Card */}
      <View style={styles.serverCard}>
        <Text style={styles.serverTitle}>CONNECTED PORTAL SERVER</Text>
        <Text style={styles.api}>{API_BASE_URL}</Text>
      </View>

      {/* Sign Out Action Button */}
      <Pressable
        style={({ pressed }) => [styles.logout, pressed && styles.logoutPressed, busy && styles.disabled]}
        onPress={onLogout}
        disabled={busy}
      >
        {busy ? (
          <ActivityIndicator color={Colors.white} />
        ) : (
          <Text style={styles.logoutText}>Sign Out of Wallet</Text>
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.cream, padding: 18 },
  card: {
    backgroundColor: Colors.white,
    borderRadius: 22,
    padding: 20,
    borderWidth: 1,
    borderColor: Colors.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.04,
    shadowRadius: 10,
    elevation: 2,
  },
  avatarHeader: { flexDirection: 'row', alignItems: 'center' },
  avatarBox: {
    width: 54,
    height: 54,
    borderRadius: 18,
    backgroundColor: Colors.primaryMid,
    alignItems: 'center',
    justify: 'center',
    marginRight: 14,
  },
  avatarText: { color: Colors.white, fontSize: 20, fontWeight: '800', letterSpacing: 0.5 },
  name: { fontSize: 20, fontWeight: '800', color: Colors.navy, letterSpacing: -0.3 },
  verifiedBadge: {
    backgroundColor: Colors.successLight,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    alignSelf: 'flex-start',
    marginTop: 4,
  },
  verifiedText: { color: Colors.success, fontSize: 10, fontWeight: '800', letterSpacing: 0.5 },
  divider: { height: 1, backgroundColor: Colors.borderSubtle, marginVertical: 18 },
  infoRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 14 },
  infoIcon: { fontSize: 18, marginRight: 12 },
  infoLabel: { fontSize: 10, fontWeight: '800', color: Colors.mutedLight, letterSpacing: 0.6 },
  infoValue: { fontSize: 14, fontWeight: '700', color: Colors.navy, marginTop: 2 },
  serverCard: {
    backgroundColor: Colors.white,
    borderRadius: 16,
    padding: 16,
    marginTop: 14,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  serverTitle: { fontSize: 10, fontWeight: '800', color: Colors.mutedLight, letterSpacing: 0.6 },
  api: { color: Colors.muted, fontSize: 13, fontWeight: '600', marginTop: 4 },
  logout: {
    marginTop: 22,
    backgroundColor: Colors.danger,
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
    shadowColor: Colors.danger,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 3,
  },
  logoutPressed: { opacity: 0.9, transform: [{ scale: 0.99 }] },
  disabled: { opacity: 0.6 },
  logoutText: { color: Colors.white, fontWeight: '800', fontSize: 15, letterSpacing: 0.2 },
});

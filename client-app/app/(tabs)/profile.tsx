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

  return (
    <View style={styles.screen}>
      <View style={styles.card}>
        <Text style={styles.name}>{client?.full_name || 'Client'}</Text>
        <Text style={styles.meta}>{client?.phone_number || 'No phone'}</Text>
        <Text style={styles.meta}>{client?.email || 'No email'}</Text>
        {client?.driver_license ? (
          <Text style={styles.meta}>DL: {client.driver_license}</Text>
        ) : null}
      </View>

      <Text style={styles.api}>API: {API_BASE_URL}</Text>

      <Pressable style={styles.logout} onPress={onLogout} disabled={busy}>
        {busy ? (
          <ActivityIndicator color={Colors.white} />
        ) : (
          <Text style={styles.logoutText}>Sign out</Text>
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.cream, padding: 20 },
  card: {
    backgroundColor: Colors.white,
    borderRadius: 16,
    padding: 20,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  name: { fontSize: 22, fontWeight: '800', color: Colors.navy },
  meta: { color: Colors.muted, marginTop: 6 },
  api: { color: Colors.muted, fontSize: 12, marginTop: 18 },
  logout: {
    marginTop: 24,
    backgroundColor: Colors.danger,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
  },
  logoutText: { color: Colors.white, fontWeight: '800', fontSize: 16 },
});

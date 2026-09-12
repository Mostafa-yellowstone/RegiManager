import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useFocusEffect } from 'expo-router';

import { Colors } from '@/constants/theme';
import { fetchVehicles } from '@/lib/api';

export default function VehiclesScreen() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const data = await fetchVehicles();
      setRows(data.results || []);
    } catch (err: any) {
      setError(err?.message || 'Could not load vehicles');
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      setLoading(true);
      load();
    }, [load]),
  );

  if (loading && !rows.length) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={Colors.primaryMid} size="large" />
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={Colors.primaryMid} />}
    >
      <Text style={styles.h1}>Vehicles</Text>
      <Text style={styles.sub}>Fleet units and vehicles listed on your policies</Text>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {!rows.length && !loading ? (
        <Text style={styles.empty}>No vehicles linked yet. Ask your agency to register one.</Text>
      ) : null}

      {rows.map((v) => (
        <View key={String(v.id)} style={styles.card}>
          <View style={styles.top}>
            <Text style={styles.title}>{v.label || 'Vehicle'}</Text>
            <View style={[styles.pill, v.source === 'policy' ? styles.pillPolicy : styles.pillFleet]}>
              <Text style={styles.pillText}>{v.source === 'policy' ? 'POLICY' : 'FLEET'}</Text>
            </View>
          </View>
          <Text style={styles.meta}>
            {v.vehicle_type_display || 'Vehicle'}
            {v.policy_number ? ` · Policy ${v.policy_number}` : ''}
          </Text>
          <View style={styles.grid}>
            <View style={styles.cell}>
              <Text style={styles.label}>PLATE</Text>
              <Text style={styles.value}>{v.plate_number || '—'}</Text>
            </View>
            <View style={styles.cell}>
              <Text style={styles.label}>VIN</Text>
              <Text style={styles.value}>{v.vin || '—'}</Text>
            </View>
          </View>
          {v.insurance_expiration_date ? (
            <Text style={styles.exp}>Expires {v.insurance_expiration_date}</Text>
          ) : null}
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#F1F5F9' },
  content: { padding: 16, paddingBottom: 40 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  h1: { fontSize: 22, fontWeight: '800', color: Colors.navy },
  sub: { color: Colors.muted, marginBottom: 14, marginTop: 2 },
  error: { color: Colors.danger, marginBottom: 10, fontWeight: '600' },
  empty: { color: Colors.muted, marginTop: 12 },
  card: {
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
    borderLeftWidth: 4,
    borderLeftColor: Colors.teal,
  },
  top: { flexDirection: 'row', justifyContent: 'space-between', gap: 8, alignItems: 'center' },
  title: { fontSize: 16, fontWeight: '800', color: Colors.navy, flex: 1 },
  pill: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 },
  pillFleet: { backgroundColor: Colors.tealSoft },
  pillPolicy: { backgroundColor: Colors.primarySubtle },
  pillText: { fontSize: 10, fontWeight: '800', color: Colors.navy },
  meta: { color: Colors.muted, marginTop: 4, fontSize: 12 },
  grid: { flexDirection: 'row', marginTop: 12, gap: 12 },
  cell: { flex: 1 },
  label: { fontSize: 10, fontWeight: '800', color: Colors.mutedLight, letterSpacing: 0.6 },
  value: { fontSize: 13, fontWeight: '700', color: Colors.navy, marginTop: 2 },
  exp: { marginTop: 10, color: Colors.warning, fontWeight: '700', fontSize: 12 },
});

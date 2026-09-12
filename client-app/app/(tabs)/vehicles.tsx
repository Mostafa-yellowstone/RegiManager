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

import { Colors, Radius } from '@/constants/theme';
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
      <Text style={styles.headerTitle}>Registered Vehicles</Text>
      <Text style={styles.headerSubtitle}>Units linked to your agency account</Text>

      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}

      {!rows.length && !loading ? (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyTitle}>No vehicles on file</Text>
          <Text style={styles.emptyText}>Ask your agency to register a vehicle on your client profile.</Text>
        </View>
      ) : null}

      {rows.map((v) => (
        <View key={v.id} style={styles.card}>
          <Text style={styles.title}>{v.label || 'Vehicle'}</Text>
          <Text style={styles.meta}>
            {v.vehicle_type_display || v.vehicle_type || 'Vehicle'}
            {v.body_type ? ` · ${v.body_type}` : ''}
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
            <Text style={styles.exp}>Insurance expires {v.insurance_expiration_date}</Text>
          ) : null}
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.cream },
  content: { padding: 18, paddingBottom: 40 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.cream },
  headerTitle: { fontSize: 22, fontWeight: '800', color: Colors.navy },
  headerSubtitle: { color: Colors.muted, marginBottom: 16, marginTop: 4, fontSize: 13 },
  errorBox: {
    backgroundColor: Colors.dangerLight,
    borderWidth: 1,
    borderColor: '#FCA5A5',
    borderRadius: Radius.md,
    padding: 12,
    marginBottom: 16,
  },
  errorText: { color: Colors.danger, fontSize: 13, fontWeight: '600' },
  emptyCard: {
    backgroundColor: Colors.white,
    borderRadius: Radius.lg,
    padding: 24,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  emptyTitle: { fontSize: 16, fontWeight: '800', color: Colors.navy },
  emptyText: { color: Colors.muted, marginTop: 6, fontSize: 13 },
  card: {
    backgroundColor: Colors.white,
    borderRadius: Radius.lg,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: Colors.border,
    borderLeftWidth: 4,
    borderLeftColor: Colors.teal,
  },
  title: { fontSize: 16, fontWeight: '800', color: Colors.navy },
  meta: { color: Colors.muted, marginTop: 4, fontSize: 12, fontWeight: '500' },
  grid: { flexDirection: 'row', marginTop: 14, gap: 12 },
  cell: { flex: 1 },
  label: { fontSize: 10, fontWeight: '800', color: Colors.mutedLight, letterSpacing: 0.6 },
  value: { fontSize: 13, fontWeight: '700', color: Colors.navy, marginTop: 2 },
  exp: { marginTop: 12, color: Colors.warning, fontWeight: '700', fontSize: 12 },
});

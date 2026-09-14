import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';

import { Colors, Radius, Shadows } from '@/constants/theme';
import { fetchServices } from '@/lib/api';

function statusColor(status?: string) {
  const s = (status || '').toLowerCase();
  if (s === 'completed') return Colors.success;
  if (s === 'pending') return Colors.warning;
  if (s === 'failed' || s === 'refund') return Colors.danger;
  return Colors.muted;
}

export default function ServicesScreen() {
  const router = useRouter();
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const data = await fetchServices({ limit: 80 });
      setRows(data.results || []);
    } catch (err: any) {
      setError(err?.message || 'Could not load services');
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
      <Text style={styles.h1}>Your Services</Text>
      <Text style={styles.sub}>Registrations, renewals, titles & other DMV work your agency handled</Text>
      {error ? <Text style={styles.error}>{error}</Text> : null}

      {!rows.length && !loading ? (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyTitle}>No services yet</Text>
          <Text style={styles.emptyText}>
            When your agency processes a registration, title, or plate service, it will show up here.
          </Text>
        </View>
      ) : null}

      {rows.map((s) => (
        <Pressable
          key={String(s.id)}
          style={styles.card}
          onPress={() => s.vehicle_id && router.push(`/vehicle/${s.vehicle_id}`)}
          disabled={!s.vehicle_id}
        >
          <View style={styles.top}>
            <Text style={styles.title}>{s.title || s.service_type_label || 'Service'}</Text>
            <Text style={[styles.status, { color: statusColor(s.status) }]}>
              {(s.status_display || s.status || '').toUpperCase()}
            </Text>
          </View>
          <Text style={styles.meta}>
            {s.transaction_date || '—'}
            {s.plate_number ? ` · Plate ${s.plate_number}` : ''}
            {s.vehicle_label ? ` · ${s.vehicle_label}` : ''}
          </Text>
          <View style={styles.footer}>
            <Text style={styles.receipt}>{s.receipt_number || `SR-${s.id}`}</Text>
            {s.amount ? <Text style={styles.amount}>${String(s.amount).replace(/^\$/, '')}</Text> : null}
          </View>
        </Pressable>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.cream },
  content: { padding: 16, paddingBottom: 40 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.cream },
  h1: { fontSize: 22, fontWeight: '800', color: Colors.navy },
  sub: { color: Colors.muted, marginBottom: 14, marginTop: 2, fontSize: 13 },
  error: { color: Colors.danger, marginBottom: 10, fontWeight: '600' },
  emptyCard: {
    backgroundColor: Colors.white,
    borderRadius: Radius.lg,
    padding: 24,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  emptyTitle: { fontWeight: '800', color: Colors.navy, fontSize: 16 },
  emptyText: { color: Colors.muted, marginTop: 6, fontSize: 13, lineHeight: 18 },
  card: {
    backgroundColor: Colors.white,
    borderRadius: Radius.lg,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadows.card,
  },
  top: { flexDirection: 'row', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start' },
  title: { flex: 1, fontWeight: '800', color: Colors.navy, fontSize: 15 },
  status: { fontWeight: '800', fontSize: 10 },
  meta: { color: Colors.muted, marginTop: 6, fontSize: 12 },
  footer: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 12, alignItems: 'center' },
  receipt: { color: Colors.mutedLight, fontWeight: '700', fontSize: 12 },
  amount: { color: Colors.navy, fontWeight: '800', fontSize: 14 },
});

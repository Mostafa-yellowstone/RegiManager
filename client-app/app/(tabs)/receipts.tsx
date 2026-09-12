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
import { fetchReceipts } from '@/lib/api';

function money(v?: string) {
  if (!v) return '—';
  return v.startsWith('$') ? v : `$${v}`;
}

export default function ReceiptsScreen() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const data = await fetchReceipts();
      setRows(data.results || []);
    } catch (err: any) {
      setError(err?.message || 'Could not load receipts');
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
      <Text style={styles.headerTitle}>Service Receipts</Text>
      <Text style={styles.headerSubtitle}>DMV and agency service payment history</Text>

      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}

      {!rows.length && !loading ? (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyTitle}>No receipts yet</Text>
          <Text style={styles.emptyText}>Completed service records will appear here.</Text>
        </View>
      ) : null}

      {rows.map((r) => (
        <View key={r.id} style={styles.card}>
          <View style={styles.top}>
            <Text style={styles.title}>{r.receipt_number}</Text>
            <Text style={styles.amount}>{money(r.service_fee)}</Text>
          </View>
          <Text style={styles.meta}>
            {r.transaction_date || '—'} · {r.service_type || r.transaction_type || 'Service'}
          </Text>
          <Text style={styles.meta}>
            {[r.plate_number && `Plate ${r.plate_number}`, r.status_display || r.status]
              .filter(Boolean)
              .join(' · ')}
          </Text>
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
  },
  top: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  title: { fontSize: 15, fontWeight: '800', color: Colors.navy },
  amount: { fontSize: 16, fontWeight: '800', color: Colors.navy },
  meta: { color: Colors.muted, marginTop: 4, fontSize: 12, fontWeight: '500' },
});

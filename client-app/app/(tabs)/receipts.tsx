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
      <Text style={styles.h1}>Receipts</Text>
      <Text style={styles.sub}>Service receipts and insurance payments</Text>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {!rows.length && !loading ? <Text style={styles.empty}>No receipts on file.</Text> : null}

      {rows.map((r) => {
        const insurance = r.kind === 'insurance_payment';
        return (
          <View key={String(r.id)} style={[styles.card, insurance && styles.cardIns]}>
            <View style={styles.top}>
              <Text style={styles.title}>{r.receipt_number}</Text>
              <Text style={styles.amount}>{money(r.amount || r.service_fee)}</Text>
            </View>
            <Text style={styles.meta}>
              {r.transaction_date || '—'} · {r.title || r.service_type || 'Receipt'}
            </Text>
            <Text style={styles.meta}>
              {[
                insurance ? 'Insurance payment' : 'Service receipt',
                r.company,
                r.policy_number && `Policy ${r.policy_number}`,
                r.plate_number && `Plate ${r.plate_number}`,
              ]
                .filter(Boolean)
                .join(' · ')}
            </Text>
          </View>
        );
      })}
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
  empty: { color: Colors.muted, marginTop: 20 },
  card: {
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
    borderLeftWidth: 4,
    borderLeftColor: Colors.warning,
  },
  cardIns: { borderLeftColor: Colors.primaryMid },
  top: { flexDirection: 'row', justifyContent: 'space-between', gap: 8 },
  title: { fontWeight: '800', color: Colors.navy, fontSize: 15, flex: 1 },
  amount: { fontWeight: '800', color: Colors.navy, fontSize: 15 },
  meta: { color: Colors.muted, marginTop: 4, fontSize: 12 },
});

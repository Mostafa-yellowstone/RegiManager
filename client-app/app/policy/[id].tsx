import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useLocalSearchParams, useFocusEffect } from 'expo-router';

import { Colors } from '@/constants/theme';
import { fetchPolicy } from '@/lib/api';

export default function PolicyDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!id) return;
    setError('');
    try {
      const policy = await fetchPolicy(id);
      setData(policy);
    } catch (err: any) {
      setError(err?.message || 'Could not load policy');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useFocusEffect(
    useCallback(() => {
      setLoading(true);
      load();
    }, [load]),
  );

  if (loading && !data) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={Colors.teal} size="large" />
      </View>
    );
  }

  const schedule = data?.schedule || {};
  const installments = schedule.installments || [];

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
    >
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {data ? (
        <>
          <Text style={styles.title}>{data.policy_number}</Text>
          <Text style={styles.meta}>
            {data.company || '—'} · {data.status_display || data.status}
          </Text>
          <Text style={styles.meta}>
            {data.start_date || '—'} → {data.end_date || '—'}
          </Text>

          <View style={styles.summary}>
            <Text style={styles.summaryLabel}>Payment schedule</Text>
            <Text style={styles.summaryValue}>
              {schedule.remaining ?? 0} remaining
              {schedule.remaining_amount ? ` · $${schedule.remaining_amount}` : ''}
            </Text>
            {schedule.next_due_date ? (
              <Text style={styles.meta}>
                Next due {schedule.next_due_date}
                {schedule.next_due_amount ? ` · $${schedule.next_due_amount}` : ''}
              </Text>
            ) : (
              <Text style={styles.meta}>No open installments</Text>
            )}
          </View>

          {installments.map((row: any) => (
            <View key={row.id} style={styles.row}>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>
                  {row.is_deposit ? 'Deposit' : `#${row.number}`}
                </Text>
                <Text style={styles.meta}>{row.due_date || '—'}</Text>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Text style={styles.amount}>${row.total_due}</Text>
                <Text
                  style={[
                    styles.badge,
                    row.is_paid ? styles.paid : styles.open,
                  ]}
                >
                  {row.is_paid ? 'Paid' : 'Due'}
                </Text>
              </View>
            </View>
          ))}
        </>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.cream },
  content: { padding: 16, paddingBottom: 40 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  error: { color: Colors.danger, marginBottom: 12 },
  title: { fontSize: 24, fontWeight: '800', color: Colors.navy },
  meta: { color: Colors.muted, marginTop: 4 },
  summary: {
    backgroundColor: Colors.navy,
    borderRadius: 16,
    padding: 16,
    marginTop: 18,
    marginBottom: 14,
  },
  summaryLabel: { color: '#94A3B8', fontWeight: '700', fontSize: 12 },
  summaryValue: { color: Colors.white, fontSize: 20, fontWeight: '800', marginTop: 6 },
  row: {
    backgroundColor: Colors.white,
    borderRadius: 12,
    padding: 14,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: Colors.border,
    flexDirection: 'row',
    alignItems: 'center',
  },
  rowTitle: { fontWeight: '800', color: Colors.text },
  amount: { fontWeight: '800', color: Colors.navy },
  badge: { marginTop: 4, fontSize: 12, fontWeight: '800' },
  paid: { color: Colors.success },
  open: { color: Colors.teal },
});

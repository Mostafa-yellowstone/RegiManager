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
import { Link, useFocusEffect } from 'expo-router';

import { Colors } from '@/constants/theme';
import { fetchPolicies } from '@/lib/api';

function money(v?: string | null) {
  if (!v) return '';
  return v.startsWith('$') ? v : `$${v}`;
}

export default function PoliciesScreen() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const data = await fetchPolicies();
      setRows(data.results || []);
    } catch (err: any) {
      setError(err?.message || 'Could not load policies');
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
      <Text style={styles.h1}>Your Policies</Text>
      <Text style={styles.sub}>{rows.length} coverage record{rows.length === 1 ? '' : 's'}</Text>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {!rows.length && !loading ? <Text style={styles.empty}>No policies on file.</Text> : null}

      {rows.map((p) => {
        const active = (p.status_display || p.status || '').toLowerCase().includes('active');
        return (
          <Link key={p.id} href={`/policy/${p.id}`} asChild>
            <Pressable style={styles.card}>
              <View style={styles.top}>
                <Text style={styles.number}>{p.policy_number}</Text>
                <View style={[styles.pill, { backgroundColor: active ? Colors.successLight : '#FEF3C7' }]}>
                  <Text style={[styles.pillText, { color: active ? Colors.success : Colors.warning }]}>
                    {(p.status_display || p.status || 'Policy').toUpperCase()}
                  </Text>
                </View>
              </View>
              <Text style={styles.company}>{p.company || 'Insurance carrier'}</Text>
              <View style={styles.metaRow}>
                <Text style={styles.meta}>
                  {p.next_due_date
                    ? `Next due ${p.next_due_date}${p.next_due_amount ? ` · ${money(p.next_due_amount)}` : ''}`
                    : 'No open installment'}
                </Text>
                {p.remaining_amount ? (
                  <Text style={styles.remain}>{money(p.remaining_amount)} left</Text>
                ) : null}
              </View>
            </Pressable>
          </Link>
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
    borderRadius: 16,
    padding: 16,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
    borderLeftWidth: 4,
    borderLeftColor: Colors.navy,
  },
  top: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  number: { fontSize: 17, fontWeight: '800', color: Colors.navy, flex: 1 },
  pill: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 },
  pillText: { fontSize: 10, fontWeight: '800' },
  company: { color: Colors.muted, marginTop: 6, fontWeight: '600' },
  metaRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 12, gap: 8 },
  meta: { color: Colors.textSecondary, fontSize: 12, flex: 1, fontWeight: '500' },
  remain: { color: Colors.navy, fontWeight: '800', fontSize: 12 },
});

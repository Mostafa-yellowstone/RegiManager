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
        <ActivityIndicator color={Colors.teal} size="large" />
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
    >
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {!rows.length ? <Text style={styles.empty}>No policies on file.</Text> : null}
      {rows.map((p) => (
        <Link key={p.id} href={`/policy/${p.id}`} asChild>
          <Pressable style={styles.card}>
            <Text style={styles.title}>{p.policy_number}</Text>
            <Text style={styles.meta}>
              {p.company || '—'} · {p.status_display || p.status}
            </Text>
            <Text style={styles.meta}>
              {p.start_date || '—'} → {p.end_date || '—'}
            </Text>
          </Pressable>
        </Link>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.cream },
  content: { padding: 16, paddingBottom: 40 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  error: { color: Colors.danger, marginBottom: 12 },
  empty: { color: Colors.muted, textAlign: 'center', marginTop: 40 },
  card: {
    backgroundColor: Colors.white,
    borderRadius: 14,
    padding: 16,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  title: { fontWeight: '800', fontSize: 17, color: Colors.navy },
  meta: { color: Colors.muted, marginTop: 4 },
});

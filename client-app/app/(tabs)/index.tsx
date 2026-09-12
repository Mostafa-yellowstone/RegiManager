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
import { fetchHome } from '@/lib/api';
import { useAuth } from '@/lib/auth';

export default function HomeScreen() {
  const { client } = useAuth();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError('');
    try {
      const home = await fetchHome();
      setData(home);
    } catch (err: any) {
      setError(err?.message || 'Could not load wallet');
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

  if (loading && !data) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={Colors.teal} size="large" />
      </View>
    );
  }

  const next = data?.next_payment;
  const totals = data?.totals || {};

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
    >
      <Text style={styles.greeting}>
        Hello{client?.first_name ? `, ${client.first_name}` : ''}
      </Text>
      <Text style={styles.sub}>Your documents and payment status in one place.</Text>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <View style={styles.heroCard}>
        <Text style={styles.heroLabel}>Next payment due</Text>
        {next ? (
          <>
            <Text style={styles.heroAmount}>
              {next.amount ? `$${next.amount}` : '—'}
            </Text>
            <Text style={styles.heroMeta}>
              {next.due_date} · {next.policy_number}
              {next.company ? ` · ${next.company}` : ''}
            </Text>
          </>
        ) : (
          <Text style={styles.heroAmount}>No open payments</Text>
        )}
      </View>

      <View style={styles.statsRow}>
        <View style={styles.stat}>
          <Text style={styles.statValue}>{totals.policies ?? 0}</Text>
          <Text style={styles.statLabel}>Policies</Text>
        </View>
        <View style={styles.stat}>
          <Text style={styles.statValue}>{totals.remaining_payments ?? 0}</Text>
          <Text style={styles.statLabel}>Remaining</Text>
        </View>
        <View style={styles.stat}>
          <Text style={styles.statValue}>{totals.id_cards ?? 0}</Text>
          <Text style={styles.statLabel}>ID cards</Text>
        </View>
      </View>

      <Text style={styles.section}>Quick links</Text>
      <View style={styles.links}>
        <Link href="/(tabs)/policies" asChild>
          <Pressable style={styles.linkBtn}>
            <Text style={styles.linkText}>Policies</Text>
          </Pressable>
        </Link>
        <Link href="/(tabs)/id-cards" asChild>
          <Pressable style={styles.linkBtn}>
            <Text style={styles.linkText}>ID Cards</Text>
          </Pressable>
        </Link>
        <Link href="/(tabs)/documents" asChild>
          <Pressable style={styles.linkBtn}>
            <Text style={styles.linkText}>Documents</Text>
          </Pressable>
        </Link>
      </View>

      <Text style={styles.section}>Policies</Text>
      {(data?.policies || []).map((p: any) => (
        <Link key={p.id} href={`/policy/${p.id}`} asChild>
          <Pressable style={styles.policyRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.policyTitle}>{p.policy_number}</Text>
              <Text style={styles.policyMeta}>
                {p.company || '—'} · {p.status_display || p.status}
              </Text>
            </View>
            <Text style={styles.chevron}>›</Text>
          </Pressable>
        </Link>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.cream },
  content: { padding: 20, paddingBottom: 40 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  greeting: { fontSize: 28, fontWeight: '800', color: Colors.navy },
  sub: { color: Colors.muted, marginTop: 4, marginBottom: 18 },
  error: { color: Colors.danger, marginBottom: 12 },
  heroCard: {
    backgroundColor: Colors.navy,
    borderRadius: 18,
    padding: 20,
    marginBottom: 16,
  },
  heroLabel: { color: '#94A3B8', fontWeight: '700', fontSize: 13 },
  heroAmount: { color: Colors.white, fontSize: 32, fontWeight: '800', marginTop: 6 },
  heroMeta: { color: '#CBD5E1', marginTop: 8 },
  statsRow: { flexDirection: 'row', gap: 10, marginBottom: 22 },
  stat: {
    flex: 1,
    backgroundColor: Colors.white,
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  statValue: { fontSize: 22, fontWeight: '800', color: Colors.navy },
  statLabel: { color: Colors.muted, marginTop: 4, fontSize: 12, fontWeight: '600' },
  section: {
    fontSize: 15,
    fontWeight: '800',
    color: Colors.navy,
    marginBottom: 10,
    marginTop: 6,
  },
  links: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 18 },
  linkBtn: {
    backgroundColor: Colors.tealSoft,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 999,
  },
  linkText: { color: Colors.teal, fontWeight: '800' },
  policyRow: {
    backgroundColor: Colors.white,
    borderRadius: 14,
    padding: 16,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
    flexDirection: 'row',
    alignItems: 'center',
  },
  policyTitle: { fontWeight: '800', color: Colors.text, fontSize: 16 },
  policyMeta: { color: Colors.muted, marginTop: 4 },
  chevron: { fontSize: 28, color: Colors.muted, marginLeft: 8 },
});

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
        <ActivityIndicator color={Colors.primaryMid} size="large" />
      </View>
    );
  }

  const next = data?.next_payment;
  const totals = data?.totals || {};

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={loading}
          onRefresh={load}
          tintColor={Colors.primaryMid}
        />
      }
    >
      {/* Header Greeting */}
      <View style={styles.headerRow}>
        <View>
          <Text style={styles.greeting}>
            Welcome{client?.first_name ? `, ${client.first_name}` : ''} 👋
          </Text>
          <Text style={styles.sub}>Insurance & DMV Account Dashboard</Text>
        </View>
      </View>

      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}

      {/* Hero Card - Next Payment */}
      <View style={styles.heroCard}>
        <View style={styles.heroHeader}>
          <Text style={styles.heroLabel}>NEXT PAYMENT DUE</Text>
          {next ? (
            <View style={styles.duePill}>
              <Text style={styles.duePillText}>UPCOMING</Text>
            </View>
          ) : (
            <View style={styles.paidPill}>
              <Text style={styles.paidPillText}>UP TO DATE</Text>
            </View>
          )}
        </View>

        {next ? (
          <>
            <Text style={styles.heroAmount}>
              {next.amount ? `$${next.amount}` : '—'}
            </Text>
            <View style={styles.heroDivider} />
            <Text style={styles.heroMeta}>
              📅 Due {next.due_date} · Policy #{next.policy_number}
              {next.company ? ` (${next.company})` : ''}
            </Text>
          </>
        ) : (
          <Text style={styles.heroAmount}>No Pending Payments</Text>
        )}
      </View>

      {/* Stats Counter Cards */}
      <View style={styles.statsRow}>
        <View style={styles.statCard}>
          <View style={[styles.statAccent, { backgroundColor: Colors.primaryMid }]} />
          <Text style={styles.statValue}>{totals.policies ?? 0}</Text>
          <Text style={styles.statLabel}>Policies</Text>
        </View>
        <View style={styles.statCard}>
          <View style={[styles.statAccent, { backgroundColor: Colors.warning }]} />
          <Text style={styles.statValue}>{totals.remaining_payments ?? 0}</Text>
          <Text style={styles.statLabel}>Open Payments</Text>
        </View>
        <View style={styles.statCard}>
          <View style={[styles.statAccent, { backgroundColor: Colors.teal }]} />
          <Text style={styles.statValue}>{totals.id_cards ?? 0}</Text>
          <Text style={styles.statLabel}>ID Cards</Text>
        </View>
      </View>

      {/* Quick Action Links */}
      <Text style={styles.sectionTitle}>QUICK ACTIONS</Text>
      <View style={styles.links}>
        <Link href="/(tabs)/policies" asChild>
          <Pressable style={({ pressed }) => [styles.linkBtn, pressed && styles.pressed]}>
            <Text style={styles.linkIcon}>📜</Text>
            <Text style={styles.linkText}>View Policies</Text>
          </Pressable>
        </Link>
        <Link href="/(tabs)/id-cards" asChild>
          <Pressable style={({ pressed }) => [styles.linkBtn, pressed && styles.pressed]}>
            <Text style={styles.linkIcon}>🎴</Text>
            <Text style={styles.linkText}>Digital IDs</Text>
          </Pressable>
        </Link>
        <Link href="/(tabs)/documents" asChild>
          <Pressable style={({ pressed }) => [styles.linkBtn, pressed && styles.pressed]}>
            <Text style={styles.linkIcon}>📂</Text>
            <Text style={styles.linkText}>Documents</Text>
          </Pressable>
        </Link>
      </View>

      {/* Active Policies List */}
      <View style={styles.sectionHeaderRow}>
        <Text style={styles.sectionTitle}>ACTIVE POLICIES</Text>
        <Link href="/(tabs)/policies" asChild>
          <Pressable>
            <Text style={styles.seeAllText}>See all ({data?.policies?.length || 0}) ›</Text>
          </Pressable>
        </Link>
      </View>

      {(data?.policies || []).map((p: any) => {
        const isActive = p.status === 'active' || p.status_display?.toLowerCase().includes('active');
        return (
          <Link key={p.id} href={`/policy/${p.id}`} asChild>
            <Pressable style={({ pressed }) => [styles.policyRow, pressed && styles.pressed]}>
              <View style={styles.policyIconBox}>
                <Text style={styles.policyBoxIcon}>🛡️</Text>
              </View>
              <View style={{ flex: 1 }}>
                <View style={styles.policyHeaderLine}>
                  <Text style={styles.policyTitle}>{p.policy_number}</Text>
                  <View
                    style={[
                      styles.statusBadge,
                      { backgroundColor: isActive ? Colors.successLight : Colors.warningLight },
                    ]}
                  >
                    <Text
                      style={[
                        styles.statusBadgeText,
                        { color: isActive ? Colors.success : Colors.warning },
                      ]}
                    >
                      {(p.status_display || p.status || 'Active').toUpperCase()}
                    </Text>
                  </View>
                </View>
                <Text style={styles.policyMeta}>
                  {p.company || 'Insurance Provider'}
                </Text>
              </View>
              <Text style={styles.chevron}>›</Text>
            </Pressable>
          </Link>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.cream },
  content: { padding: 18, paddingBottom: 40 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.cream },
  headerRow: { marginBottom: 18, marginTop: 4 },
  greeting: { fontSize: 26, fontWeight: '800', color: Colors.navy, letterSpacing: -0.4 },
  sub: { color: Colors.muted, marginTop: 3, fontSize: 14, fontWeight: '500' },
  errorBox: {
    backgroundColor: Colors.dangerLight,
    borderWidth: 1,
    borderColor: '#FCA5A5',
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
  },
  errorText: { color: Colors.danger, fontSize: 13, fontWeight: '600' },
  heroCard: {
    backgroundColor: Colors.navy,
    borderRadius: 20,
    padding: 22,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
    shadowColor: Colors.navy,
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.15,
    shadowRadius: 16,
    elevation: 5,
  },
  heroHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  heroLabel: { color: '#94A3B8', fontWeight: '800', fontSize: 11, letterSpacing: 0.8 },
  duePill: {
    backgroundColor: 'rgba(217, 119, 6, 0.2)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(217, 119, 6, 0.4)',
  },
  duePillText: { color: '#FBBF24', fontSize: 10, fontWeight: '800', letterSpacing: 0.5 },
  paidPill: {
    backgroundColor: 'rgba(5, 150, 105, 0.2)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(5, 150, 105, 0.4)',
  },
  paidPillText: { color: '#34D399', fontSize: 10, fontWeight: '800', letterSpacing: 0.5 },
  heroAmount: { color: Colors.white, fontSize: 34, fontWeight: '800', letterSpacing: -0.5 },
  heroDivider: { height: 1, backgroundColor: 'rgba(255, 255, 255, 0.12)', marginVertical: 14 },
  heroMeta: { color: '#CBD5E1', fontSize: 13, fontWeight: '500' },
  statsRow: { flexDirection: 'row', gap: 10, marginBottom: 22 },
  statCard: {
    flex: 1,
    backgroundColor: Colors.white,
    borderRadius: 16,
    padding: 14,
    borderWidth: 1,
    borderColor: Colors.border,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.03,
    shadowRadius: 6,
    elevation: 1,
  },
  statAccent: { position: 'absolute', top: 0, left: 0, right: 0, height: 3 },
  statValue: { fontSize: 24, fontWeight: '800', color: Colors.navy, marginTop: 4 },
  statLabel: { color: Colors.muted, marginTop: 2, fontSize: 11, fontWeight: '700' },
  sectionTitle: {
    fontSize: 12,
    fontWeight: '800',
    color: Colors.muted,
    marginBottom: 12,
    letterSpacing: 0.8,
  },
  sectionHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 6,
    marginBottom: 12,
  },
  seeAllText: { fontSize: 12, fontWeight: '700', color: Colors.primaryMid },
  links: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 22 },
  linkBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.white,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: Colors.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.03,
    shadowRadius: 4,
    elevation: 1,
  },
  linkIcon: { fontSize: 15, marginRight: 8 },
  linkText: { color: Colors.navy, fontWeight: '700', fontSize: 13 },
  policyRow: {
    backgroundColor: Colors.white,
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: Colors.border,
    flexDirection: 'row',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.03,
    shadowRadius: 6,
    elevation: 1,
  },
  pressed: { opacity: 0.9, transform: [{ scale: 0.995 }] },
  policyIconBox: {
    width: 42,
    height: 42,
    borderRadius: 12,
    backgroundColor: Colors.primarySubtle,
    alignItems: 'center',
    justify: 'center',
    marginRight: 12,
  },
  policyBoxIcon: { fontSize: 20 },
  policyHeaderLine: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginRight: 8 },
  policyTitle: { fontWeight: '800', color: Colors.navy, fontSize: 15 },
  statusBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 },
  statusBadgeText: { fontSize: 10, fontWeight: '800' },
  policyMeta: { color: Colors.muted, marginTop: 3, fontSize: 13, fontWeight: '500' },
  chevron: { fontSize: 22, color: Colors.mutedLight, fontWeight: '300' },
});

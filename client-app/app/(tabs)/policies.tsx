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
        <ActivityIndicator color={Colors.primaryMid} size="large" />
      </View>
    );
  }

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
      {/* Overview Header */}
      <View style={styles.headerBox}>
        <Text style={styles.headerTitle}>Active & Historical Coverage</Text>
        <Text style={styles.headerSubtitle}>
          {rows.length} policy record{rows.length === 1 ? '' : 's'} registered with agency
        </Text>
      </View>

      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}

      {!rows.length && !loading ? (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyIcon}>🛡️</Text>
          <Text style={styles.emptyTitle}>No Policies Found</Text>
          <Text style={styles.emptyText}>You do not have any registered insurance policies yet.</Text>
        </View>
      ) : null}

      {rows.map((p) => {
        const isActive = p.status === 'active' || p.status_display?.toLowerCase().includes('active');
        return (
          <Link key={p.id} href={`/policy/${p.id}`} asChild>
            <Pressable style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
              <View style={styles.cardHeader}>
                <View style={styles.policyNumberRow}>
                  <Text style={styles.policyBadgeIcon}>📋</Text>
                  <Text style={styles.title}>{p.policy_number}</Text>
                </View>
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

              <View style={styles.cardDivider} />

              <View style={styles.detailsRow}>
                <View style={styles.detailCol}>
                  <Text style={styles.detailLabel}>INSURANCE CARRIER</Text>
                  <Text style={styles.detailValue}>{p.company || 'Standard Coverage'}</Text>
                </View>
                <View style={styles.detailCol}>
                  <Text style={styles.detailLabel}>TERM DATES</Text>
                  <Text style={styles.detailValue}>
                    {p.start_date || 'N/A'} → {p.end_date || 'N/A'}
                  </Text>
                </View>
              </View>

              <View style={styles.cardFooter}>
                <Text style={styles.viewDetailsText}>Tap to view schedule & payments</Text>
                <Text style={styles.chevron}>›</Text>
              </View>
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
  headerBox: { marginBottom: 16, marginTop: 4 },
  headerTitle: { fontSize: 22, fontWeight: '800', color: Colors.navy, letterSpacing: -0.3 },
  headerSubtitle: { color: Colors.muted, fontSize: 13, fontWeight: '500', marginTop: 2 },
  errorBox: {
    backgroundColor: Colors.dangerLight,
    borderWidth: 1,
    borderColor: '#FCA5A5',
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
  },
  errorText: { color: Colors.danger, fontSize: 13, fontWeight: '600' },
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 50,
    backgroundColor: Colors.white,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyTitle: { fontSize: 18, fontWeight: '800', color: Colors.navy },
  emptyText: { color: Colors.muted, fontSize: 14, marginTop: 4, textAlign: 'center' },
  card: {
    backgroundColor: Colors.white,
    borderRadius: 18,
    padding: 18,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: Colors.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.04,
    shadowRadius: 10,
    elevation: 2,
  },
  pressed: { opacity: 0.92, transform: [{ scale: 0.995 }] },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  policyNumberRow: { flexDirection: 'row', alignItems: 'center' },
  policyBadgeIcon: { fontSize: 18, marginRight: 8 },
  title: { fontWeight: '800', fontSize: 17, color: Colors.navy, letterSpacing: -0.3 },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  statusBadgeText: { fontSize: 11, fontWeight: '800', letterSpacing: 0.4 },
  cardDivider: { height: 1, backgroundColor: Colors.borderSubtle, marginVertical: 14 },
  detailsRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 12 },
  detailCol: { flex: 1 },
  detailLabel: { fontSize: 10, fontWeight: '800', color: Colors.mutedLight, letterSpacing: 0.6, marginBottom: 4 },
  detailValue: { fontSize: 13, fontWeight: '700', color: Colors.text },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: Colors.borderSubtle,
  },
  viewDetailsText: { fontSize: 12, fontWeight: '700', color: Colors.primaryMid },
  chevron: { fontSize: 20, color: Colors.primaryMid, fontWeight: '700' },
});

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
        <ActivityIndicator color={Colors.primaryMid} size="large" />
      </View>
    );
  }

  const schedule = data?.schedule || {};
  const installments = schedule.installments || [];
  const isActive = data?.status === 'active' || data?.status_display?.toLowerCase().includes('active');

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
      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}

      {data ? (
        <>
          {/* Policy Overview Header Card */}
          <View style={styles.policyHeaderCard}>
            <View style={styles.policyTopRow}>
              <View>
                <Text style={styles.policyNumberLabel}>POLICY NUMBER</Text>
                <Text style={styles.title}>{data.policy_number}</Text>
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
                  {(data.status_display || data.status || 'Active').toUpperCase()}
                </Text>
              </View>
            </View>

            <View style={styles.divider} />

            <View style={styles.metaRow}>
              <View style={styles.metaCol}>
                <Text style={styles.metaLabel}>CARRIER</Text>
                <Text style={styles.metaValue}>{data.company || 'Standard Coverage'}</Text>
              </View>
              <View style={styles.metaCol}>
                <Text style={styles.metaLabel}>EFFECTIVE DATES</Text>
                <Text style={styles.metaValue}>
                  {data.start_date || '—'} → {data.end_date || '—'}
                </Text>
              </View>
            </View>
          </View>

          {/* Payment Schedule Summary Hero */}
          <View style={styles.summaryCard}>
            <View style={styles.summaryHeaderLine}>
              <Text style={styles.summaryLabel}>PAYMENT SCHEDULE</Text>
              <View style={styles.summaryBadge}>
                <Text style={styles.summaryBadgeText}>
                  {schedule.remaining ?? 0} REMAINING
                </Text>
              </View>
            </View>

            <Text style={styles.summaryValue}>
              {schedule.remaining_amount ? `$${schedule.remaining_amount}` : '$0.00'}
            </Text>
            <Text style={styles.summarySubtext}>Outstanding balance on schedule</Text>

            <View style={styles.summaryDivider} />

            {schedule.next_due_date ? (
              <View style={styles.nextDueRow}>
                <Text style={styles.nextDueLabel}>Next Due Date:</Text>
                <Text style={styles.nextDueValue}>
                  📅 {schedule.next_due_date}
                  {schedule.next_due_amount ? ` ($${schedule.next_due_amount})` : ''}
                </Text>
              </View>
            ) : (
              <Text style={styles.allPaidText}>✓ All scheduled payments complete</Text>
            )}
          </View>

          {/* Installments Section */}
          <Text style={styles.sectionTitle}>INSTALLMENT BREAKDOWN</Text>

          {installments.map((row: any) => (
            <View key={row.id} style={styles.row}>
              <View style={styles.rowIconBox}>
                <Text style={styles.rowEmoji}>{row.is_deposit ? '🏦' : '🗓️'}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>
                  {row.is_deposit ? 'Initial Deposit' : `Installment #${row.number}`}
                </Text>
                <Text style={styles.rowSub}>Due date: {row.due_date || '—'}</Text>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Text style={styles.amount}>${row.total_due}</Text>
                <View
                  style={[
                    styles.pillBadge,
                    { backgroundColor: row.is_paid ? Colors.successLight : Colors.primarySubtle },
                  ]}
                >
                  <Text
                    style={[
                      styles.pillBadgeText,
                      { color: row.is_paid ? Colors.success : Colors.primaryMid },
                    ]}
                  >
                    {row.is_paid ? 'PAID' : 'DUE'}
                  </Text>
                </View>
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
  content: { padding: 18, paddingBottom: 40 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.cream },
  errorBox: {
    backgroundColor: Colors.dangerLight,
    borderWidth: 1,
    borderColor: '#FCA5A5',
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
  },
  errorText: { color: Colors.danger, fontSize: 13, fontWeight: '600' },
  policyHeaderCard: {
    backgroundColor: Colors.white,
    borderRadius: 22,
    padding: 20,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: Colors.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.04,
    shadowRadius: 10,
    elevation: 2,
  },
  policyTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  policyNumberLabel: { fontSize: 10, fontWeight: '800', color: Colors.mutedLight, letterSpacing: 0.8 },
  title: { fontSize: 22, fontWeight: '800', color: Colors.navy, marginTop: 2, letterSpacing: -0.3 },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  statusBadgeText: { fontSize: 11, fontWeight: '800', letterSpacing: 0.4 },
  divider: { height: 1, backgroundColor: Colors.borderSubtle, marginVertical: 14 },
  metaRow: { flexDirection: 'row', justifyContent: 'space-between' },
  metaCol: { flex: 1 },
  metaLabel: { fontSize: 10, fontWeight: '800', color: Colors.mutedLight, letterSpacing: 0.6, marginBottom: 3 },
  metaValue: { fontSize: 13, fontWeight: '700', color: Colors.text },
  summaryCard: {
    backgroundColor: Colors.navy,
    borderRadius: 22,
    padding: 22,
    marginBottom: 22,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
    shadowColor: Colors.navy,
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.2,
    shadowRadius: 16,
    elevation: 4,
  },
  summaryHeaderLine: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  summaryLabel: { color: '#94A3B8', fontWeight: '800', fontSize: 11, letterSpacing: 0.8 },
  summaryBadge: {
    backgroundColor: 'rgba(59, 130, 246, 0.2)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: 'rgba(59, 130, 246, 0.4)',
  },
  summaryBadgeText: { color: '#93C5FD', fontSize: 10, fontWeight: '800', letterSpacing: 0.5 },
  summaryValue: { color: Colors.white, fontSize: 32, fontWeight: '800', marginTop: 10, letterSpacing: -0.5 },
  summarySubtext: { color: '#94A3B8', fontSize: 12, marginTop: 2, fontWeight: '500' },
  summaryDivider: { height: 1, backgroundColor: 'rgba(255, 255, 255, 0.12)', marginVertical: 14 },
  nextDueRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  nextDueLabel: { color: '#CBD5E1', fontSize: 13, fontWeight: '500' },
  nextDueValue: { color: Colors.white, fontSize: 13, fontWeight: '700' },
  allPaidText: { color: '#34D399', fontSize: 13, fontWeight: '700' },
  sectionTitle: { fontSize: 11, fontWeight: '800', color: Colors.muted, marginBottom: 12, letterSpacing: 0.8 },
  row: {
    backgroundColor: Colors.white,
    borderRadius: 16,
    padding: 16,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
    flexDirection: 'row',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.02,
    shadowRadius: 4,
    elevation: 1,
  },
  rowIconBox: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: Colors.cream,
    alignItems: 'center',
    justify: 'center',
    marginRight: 12,
  },
  rowEmoji: { fontSize: 18 },
  rowTitle: { fontWeight: '800', color: Colors.navy, fontSize: 14 },
  rowSub: { color: Colors.muted, fontSize: 12, marginTop: 2, fontWeight: '500' },
  amount: { fontWeight: '800', color: Colors.navy, fontSize: 16 },
  pillBadge: { marginTop: 4, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 },
  pillBadgeText: { fontSize: 10, fontWeight: '800', letterSpacing: 0.4 },
});

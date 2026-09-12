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
import { useLocalSearchParams, useFocusEffect } from 'expo-router';

import { Colors, Radius } from '@/constants/theme';
import { ApiError, fetchPolicy } from '@/lib/api';
import { openClientDocument } from '@/lib/openDocument';

function money(v?: string | null) {
  if (!v) return '—';
  return v.startsWith('$') ? v : `$${v}`;
}

export default function PolicyDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [openingId, setOpeningId] = useState<number | null>(null);

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

  async function openCard(doc: any) {
    setOpeningId(doc.id);
    try {
      await openClientDocument(doc.kind || 'insurance', doc.id, doc.title || 'ID Card');
    } catch (err: any) {
      setError(err instanceof ApiError ? err.message : err?.message || 'Could not open ID card');
    } finally {
      setOpeningId(null);
    }
  }

  if (loading && !data) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={Colors.primaryMid} size="large" />
      </View>
    );
  }

  const schedule = data?.schedule || {};
  const installments = schedule.installments || [];
  const payments = data?.payments || [];
  const idCards = data?.id_cards || [];
  const isActive = data?.status === 'active' || data?.status_display?.toLowerCase().includes('active');

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={Colors.primaryMid} />}
    >
      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}

      {data ? (
        <>
          <View style={styles.policyHeaderCard}>
            <View style={styles.policyTopRow}>
              <View style={{ flex: 1 }}>
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

          <View style={styles.summaryCard}>
            <Text style={styles.summaryLabel}>INSTALLMENT SUMMARY</Text>
            <View style={styles.summaryStats}>
              <View style={styles.summaryStat}>
                <Text style={styles.summaryStatValue}>{money(schedule.paid_amount)}</Text>
                <Text style={styles.summaryStatLabel}>Paid</Text>
              </View>
              <View style={styles.summaryStat}>
                <Text style={styles.summaryStatValue}>{money(schedule.remaining_amount)}</Text>
                <Text style={styles.summaryStatLabel}>Remaining</Text>
              </View>
              <View style={styles.summaryStat}>
                <Text style={styles.summaryStatValue}>{schedule.remaining ?? 0}</Text>
                <Text style={styles.summaryStatLabel}>Open</Text>
              </View>
            </View>
            <View style={styles.summaryDivider} />
            {schedule.next_due_date ? (
              <Text style={styles.nextDueValue}>
                Next due {schedule.next_due_date}
                {schedule.next_due_amount ? ` · ${money(schedule.next_due_amount)}` : ''}
              </Text>
            ) : (
              <Text style={styles.allPaidText}>All scheduled payments complete</Text>
            )}
          </View>

          <Text style={styles.sectionTitle}>INSTALLMENT BREAKDOWN</Text>
          {installments.map((row: any) => (
            <View key={row.id} style={styles.row}>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>
                  {row.is_deposit ? 'Deposit' : `Installment #${row.number}`}
                </Text>
                <Text style={styles.rowSub}>Due {row.due_date || '—'}</Text>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Text style={styles.amount}>{money(row.total_due)}</Text>
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

          <Text style={styles.sectionTitle}>PAYMENTS RECORDED</Text>
          {!payments.length ? (
            <View style={styles.emptySoft}>
              <Text style={styles.emptySoftText}>No agency payment transactions linked yet.</Text>
            </View>
          ) : (
            payments.map((p: any) => (
              <View key={p.id} style={styles.row}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle}>{money(p.amount)}</Text>
                  <Text style={styles.rowSub}>
                    {p.transaction_date || '—'} · {p.payment_type_display || p.payment_type}
                    {p.payment_method_display ? ` · ${p.payment_method_display}` : ''}
                  </Text>
                </View>
              </View>
            ))
          )}

          {idCards.length ? (
            <>
              <Text style={styles.sectionTitle}>INSURANCE ID CARDS</Text>
              {idCards.map((doc: any) => (
                <Pressable key={doc.id} style={styles.row} onPress={() => openCard(doc)}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle}>{doc.title || 'ID Card'}</Text>
                    <Text style={styles.rowSub}>{doc.document_type_display}</Text>
                  </View>
                  {openingId === doc.id ? (
                    <ActivityIndicator color={Colors.primaryMid} />
                  ) : (
                    <Text style={styles.openLink}>Open</Text>
                  )}
                </Pressable>
              ))}
            </>
          ) : null}
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
    borderRadius: Radius.md,
    padding: 12,
    marginBottom: 16,
  },
  errorText: { color: Colors.danger, fontSize: 13, fontWeight: '600' },
  policyHeaderCard: {
    backgroundColor: Colors.white,
    borderRadius: 18,
    padding: 18,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  policyTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  policyNumberLabel: { fontSize: 10, fontWeight: '800', color: Colors.mutedLight, letterSpacing: 0.8 },
  title: { fontSize: 22, fontWeight: '800', color: Colors.navy, marginTop: 2 },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  statusBadgeText: { fontSize: 11, fontWeight: '800', letterSpacing: 0.4 },
  divider: { height: 1, backgroundColor: Colors.borderSubtle, marginVertical: 14 },
  metaRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 10 },
  metaCol: { flex: 1 },
  metaLabel: { fontSize: 10, fontWeight: '800', color: Colors.mutedLight, letterSpacing: 0.6, marginBottom: 3 },
  metaValue: { fontSize: 13, fontWeight: '700', color: Colors.text },
  summaryCard: {
    backgroundColor: Colors.navy,
    borderRadius: 18,
    padding: 18,
    marginBottom: 18,
  },
  summaryLabel: { color: '#94A3B8', fontWeight: '800', fontSize: 11, letterSpacing: 0.8 },
  summaryStats: { flexDirection: 'row', marginTop: 14, gap: 10 },
  summaryStat: { flex: 1 },
  summaryStatValue: { color: Colors.white, fontSize: 18, fontWeight: '800' },
  summaryStatLabel: { color: '#94A3B8', fontSize: 11, marginTop: 2, fontWeight: '600' },
  summaryDivider: { height: 1, backgroundColor: 'rgba(255,255,255,0.12)', marginVertical: 14 },
  nextDueValue: { color: Colors.white, fontSize: 13, fontWeight: '700' },
  allPaidText: { color: '#34D399', fontSize: 13, fontWeight: '700' },
  sectionTitle: { fontSize: 11, fontWeight: '800', color: Colors.muted, marginBottom: 12, letterSpacing: 0.8, marginTop: 6 },
  row: {
    backgroundColor: Colors.white,
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
    flexDirection: 'row',
    alignItems: 'center',
  },
  rowTitle: { fontWeight: '800', color: Colors.navy, fontSize: 14 },
  rowSub: { color: Colors.muted, fontSize: 12, marginTop: 2, fontWeight: '500' },
  amount: { fontWeight: '800', color: Colors.navy, fontSize: 15 },
  pillBadge: { marginTop: 4, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 },
  pillBadgeText: { fontSize: 10, fontWeight: '800', letterSpacing: 0.4 },
  emptySoft: {
    backgroundColor: Colors.white,
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  emptySoftText: { color: Colors.muted, fontSize: 13 },
  openLink: { color: Colors.primaryMid, fontWeight: '800', fontSize: 12 },
});

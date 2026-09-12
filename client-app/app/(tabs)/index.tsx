import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Link, useFocusEffect, useRouter } from 'expo-router';

import { Colors, Radius } from '@/constants/theme';
import { fetchHome } from '@/lib/api';
import { useAuth } from '@/lib/auth';

function money(value?: string | null) {
  if (!value) return '—';
  return value.startsWith('$') ? value : `$${value}`;
}

const ACTIONS = [
  { href: '/(tabs)/policies', label: 'Policies', color: '#1D4ED8', soft: '#DBEAFE' },
  { href: '/(tabs)/id-cards', label: 'ID Cards', color: '#0F766E', soft: '#CCFBF1' },
  { href: '/(tabs)/documents', label: 'Documents', color: '#7C2D12', soft: '#FFEDD5' },
  { href: '/(tabs)/vehicles', label: 'Vehicles', color: '#4338CA', soft: '#E0E7FF' },
  { href: '/(tabs)/receipts', label: 'Receipts', color: '#B45309', soft: '#FEF3C7' },
  { href: '/(tabs)/chat', label: 'Messages', color: '#BE185D', soft: '#FCE7F3' },
] as const;

export default function HomeScreen() {
  const { client } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [alertsOpen, setAlertsOpen] = useState(false);

  const load = useCallback(async () => {
    setError('');
    try {
      setData(await fetchHome());
    } catch (err: any) {
      setError(err?.message || 'Could not load account');
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
  const upcoming = data?.upcoming || [];
  const alerts = data?.alerts || [];
  const alertCount = data?.alert_count ?? alerts.length;
  const chatUnread = data?.chat_unread || 0;
  const orgName = data?.organization_name || 'RegiManager';

  return (
    <>
      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={Colors.primaryMid} />}
      >
        <View style={styles.header}>
          <View style={{ flex: 1 }}>
            <Text style={styles.org}>{String(orgName).toUpperCase()}</Text>
            <Text style={styles.title}>
              {client?.first_name ? `Hello, ${client.first_name}` : 'Account Center'}
            </Text>
          </View>
          <View style={styles.headerActions}>
            <Pressable style={styles.iconBtn} onPress={() => router.push('/(tabs)/profile')}>
              <Text style={styles.iconBtnText}>👤</Text>
            </Pressable>
            <Pressable style={styles.iconBtn} onPress={() => router.push('/(tabs)/chat')}>
              <Text style={styles.iconBtnText}>💬</Text>
              {chatUnread > 0 ? (
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>{chatUnread > 9 ? '9+' : chatUnread}</Text>
                </View>
              ) : null}
            </Pressable>
            <Pressable style={styles.iconBtn} onPress={() => setAlertsOpen(true)}>
              <Text style={styles.iconBtnText}>🔔</Text>
              {alertCount > 0 ? (
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>{alertCount > 9 ? '9+' : alertCount}</Text>
                </View>
              ) : null}
            </Pressable>
          </View>
        </View>

        {error ? (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}

        <Pressable
          style={styles.hero}
          onPress={() => next?.policy_id && router.push(`/policy/${next.policy_id}`)}
        >
          <Text style={styles.heroLabel}>NEXT PAYMENT DUE</Text>
          <Text style={styles.heroAmount}>{next ? money(next.amount) : 'Up to date'}</Text>
          {next ? (
            <>
              <Text style={styles.heroMeta}>
                {next.due_date} · Policy #{next.policy_number}
                {next.company ? ` · ${next.company}` : ''}
              </Text>
              <View style={styles.heroStats}>
                <View style={styles.heroStat}>
                  <Text style={styles.heroStatValue}>{money(next.paid_amount)}</Text>
                  <Text style={styles.heroStatLabel}>Paid</Text>
                </View>
                <View style={styles.heroStat}>
                  <Text style={styles.heroStatValue}>{money(next.remaining_amount)}</Text>
                  <Text style={styles.heroStatLabel}>Remaining</Text>
                </View>
                <View style={styles.heroStat}>
                  <Text style={styles.heroStatValue}>{next.remaining_payments ?? 0}</Text>
                  <Text style={styles.heroStatLabel}>Payments left</Text>
                </View>
              </View>
              <Text style={styles.heroCta}>Tap for installment schedule →</Text>
            </>
          ) : (
            <Text style={styles.heroMeta}>No open installments on your policies</Text>
          )}
        </Pressable>

        <Text style={styles.section}>QUICK SERVICES</Text>
        <View style={styles.grid}>
          {ACTIONS.map((action) => (
            <Link key={action.href} href={action.href as any} asChild>
              <Pressable style={[styles.tile, { backgroundColor: action.soft, borderColor: action.color }]}>
                <View style={[styles.tileDot, { backgroundColor: action.color }]} />
                <Text style={[styles.tileLabel, { color: action.color }]}>{action.label}</Text>
              </Pressable>
            </Link>
          ))}
        </View>

        <Text style={styles.section}>UPCOMING</Text>
        {!upcoming.length ? (
          <View style={styles.softCard}>
            <Text style={styles.muted}>Nothing due in the next 90 days.</Text>
          </View>
        ) : (
          upcoming.slice(0, 4).map((item: any) => (
            <Pressable
              key={item.id}
              style={styles.row}
              onPress={() => item.policy_id && router.push(`/policy/${item.policy_id}`)}
            >
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>{item.title}</Text>
                <Text style={styles.muted}>{item.date}{item.subtitle ? ` · ${item.subtitle}` : ''}</Text>
              </View>
              {item.amount ? <Text style={styles.rowAmount}>{money(item.amount)}</Text> : null}
            </Pressable>
          ))
        )}

        <View style={styles.sectionRow}>
          <Text style={styles.section}>VEHICLES</Text>
          <Link href="/(tabs)/vehicles" asChild>
            <Pressable><Text style={styles.link}>See all</Text></Pressable>
          </Link>
        </View>
        {(data?.vehicles || []).slice(0, 3).map((v: any) => (
          <View key={String(v.id)} style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle}>{v.label}</Text>
              <Text style={styles.muted}>
                {[v.plate_number && `Plate ${v.plate_number}`, v.policy_number && `Policy ${v.policy_number}`, v.source === 'policy' ? 'On policy' : 'Fleet']
                  .filter(Boolean)
                  .join(' · ')}
              </Text>
            </View>
          </View>
        ))}
        {!data?.vehicles?.length ? (
          <View style={styles.softCard}><Text style={styles.muted}>No vehicles on file yet.</Text></View>
        ) : null}

        <View style={styles.sectionRow}>
          <Text style={styles.section}>RECEIPTS</Text>
          <Link href="/(tabs)/receipts" asChild>
            <Pressable><Text style={styles.link}>See all</Text></Pressable>
          </Link>
        </View>
        {(data?.recent_receipts || []).slice(0, 3).map((r: any) => (
          <View key={String(r.id)} style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle}>{r.receipt_number}</Text>
              <Text style={styles.muted}>
                {r.transaction_date || '—'} · {r.title || r.service_type || 'Receipt'}
              </Text>
            </View>
            <Text style={styles.rowAmount}>{money(r.amount || r.service_fee)}</Text>
          </View>
        ))}
        {!data?.recent_receipts?.length ? (
          <View style={styles.softCard}><Text style={styles.muted}>No receipts yet.</Text></View>
        ) : null}

        <View style={styles.sectionRow}>
          <Text style={styles.section}>POLICIES</Text>
          <Link href="/(tabs)/policies" asChild>
            <Pressable><Text style={styles.link}>See all</Text></Pressable>
          </Link>
        </View>
        {(data?.policies || []).slice(0, 4).map((p: any) => (
          <Link key={p.id} href={`/policy/${p.id}`} asChild>
            <Pressable style={styles.row}>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>{p.policy_number}</Text>
                <Text style={styles.muted}>
                  {p.company || 'Carrier'}
                  {p.next_due_amount ? ` · Next ${money(p.next_due_amount)}` : ''}
                  {p.next_due_date ? ` on ${p.next_due_date}` : ''}
                </Text>
              </View>
              <Text style={styles.chevron}>›</Text>
            </Pressable>
          </Link>
        ))}
      </ScrollView>

      <Modal visible={alertsOpen} transparent animationType="slide" onRequestClose={() => setAlertsOpen(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>Notifications</Text>
              <Pressable onPress={() => setAlertsOpen(false)}><Text style={styles.link}>Close</Text></Pressable>
            </View>
            <ScrollView>
              {!alerts.length ? (
                <Text style={styles.muted}>No alerts right now.</Text>
              ) : (
                alerts.map((a: any) => (
                  <Pressable
                    key={a.id}
                    style={styles.row}
                    onPress={() => {
                      setAlertsOpen(false);
                      if (a.policy_id) router.push(`/policy/${a.policy_id}`);
                    }}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={styles.rowTitle}>{a.title}</Text>
                      <Text style={styles.muted}>{a.date}{a.message ? ` · ${a.message}` : ''}</Text>
                    </View>
                  </Pressable>
                ))
              )}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#F1F5F9' },
  content: { padding: 16, paddingBottom: 40 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#F1F5F9' },
  header: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 16, gap: 10 },
  org: { color: Colors.primaryMid, fontSize: 11, fontWeight: '800', letterSpacing: 1 },
  title: { fontSize: 24, fontWeight: '800', color: Colors.navy, marginTop: 2 },
  headerActions: { flexDirection: 'row', gap: 8 },
  iconBtn: {
    width: 44, height: 44, borderRadius: 14, backgroundColor: '#fff',
    alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: Colors.border,
  },
  iconBtnText: { fontSize: 16 },
  badge: {
    position: 'absolute', top: -4, right: -4, minWidth: 18, height: 18, borderRadius: 9,
    backgroundColor: Colors.danger, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 4,
  },
  badgeText: { color: '#fff', fontSize: 10, fontWeight: '800' },
  errorBox: { backgroundColor: Colors.dangerLight, borderRadius: 12, padding: 12, marginBottom: 12 },
  errorText: { color: Colors.danger, fontWeight: '600', fontSize: 13 },
  hero: {
    backgroundColor: Colors.navy, borderRadius: 20, padding: 18, marginBottom: 18,
  },
  heroLabel: { color: '#94A3B8', fontWeight: '800', fontSize: 11, letterSpacing: 0.8 },
  heroAmount: { color: '#fff', fontSize: 30, fontWeight: '800', marginTop: 8 },
  heroMeta: { color: '#CBD5E1', marginTop: 8, fontSize: 13 },
  heroStats: { flexDirection: 'row', marginTop: 16, gap: 8 },
  heroStat: { flex: 1, backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: 12, padding: 10 },
  heroStatValue: { color: '#fff', fontWeight: '800', fontSize: 14 },
  heroStatLabel: { color: '#94A3B8', fontSize: 11, marginTop: 2, fontWeight: '600' },
  heroCta: { color: '#93C5FD', marginTop: 14, fontWeight: '700', fontSize: 12 },
  section: { fontSize: 11, fontWeight: '800', color: Colors.muted, letterSpacing: 0.8, marginBottom: 10, marginTop: 6 },
  sectionRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 6, marginBottom: 10 },
  link: { color: Colors.primaryMid, fontWeight: '700', fontSize: 13 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 14 },
  tile: {
    width: '31%', flexGrow: 1, minWidth: '30%', borderRadius: 16, paddingVertical: 16, paddingHorizontal: 12,
    borderWidth: 1.5, minHeight: 84, justifyContent: 'space-between',
  },
  tileDot: { width: 10, height: 10, borderRadius: 5, marginBottom: 10 },
  tileLabel: { fontWeight: '800', fontSize: 13 },
  row: {
    backgroundColor: '#fff', borderRadius: 14, padding: 14, marginBottom: 8,
    borderWidth: 1, borderColor: Colors.border, flexDirection: 'row', alignItems: 'center',
  },
  rowTitle: { fontWeight: '800', color: Colors.navy, fontSize: 14 },
  rowAmount: { fontWeight: '800', color: Colors.navy, marginLeft: 8 },
  muted: { color: Colors.muted, fontSize: 12, marginTop: 2 },
  softCard: { backgroundColor: '#fff', borderRadius: 14, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: Colors.border },
  chevron: { fontSize: 20, color: Colors.mutedLight },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(15,23,42,0.45)', justifyContent: 'flex-end' },
  modalSheet: { backgroundColor: '#fff', borderTopLeftRadius: 22, borderTopRightRadius: 22, maxHeight: '70%', padding: 16 },
  modalHead: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 12 },
  modalTitle: { fontSize: 18, fontWeight: '800', color: Colors.navy },
});

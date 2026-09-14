import { useCallback, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Dimensions,
  Modal,
  NativeScrollEvent,
  NativeSyntheticEvent,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Link, useFocusEffect, useRouter } from 'expo-router';

import { Colors, Radius, Shadows } from '@/constants/theme';
import { fetchHome } from '@/lib/api';
import { useAuth } from '@/lib/auth';

function money(value?: string | null) {
  if (!value) return '—';
  return value.startsWith('$') ? value : `$${value}`;
}

function statusColor(status?: string) {
  const s = (status || '').toLowerCase();
  if (s === 'completed') return Colors.success;
  if (s === 'pending') return Colors.warning;
  if (s === 'failed' || s === 'refund') return Colors.danger;
  return Colors.muted;
}

const WIDTH = Dimensions.get('window').width;
const POLICY_W = WIDTH - 48;

export default function HomeScreen() {
  const { client } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [policyPage, setPolicyPage] = useState(0);
  const policyScrollRef = useRef<ScrollView>(null);

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
  const alerts = data?.alerts || [];
  const alertCount = data?.alert_count ?? alerts.length;
  const chatUnread = data?.chat_unread || 0;
  const orgName = data?.organization_name || 'RegiManager';
  const agent = data?.linked_agent || {};
  const policies = data?.policies || [];
  const vehicles = (data?.vehicles || []).filter((v: any) => v.source !== 'policy').slice(0, 4);
  const services = data?.recent_services || [];
  const clientName = client?.full_name || client?.first_name || 'Client';

  function onPolicyScroll(e: NativeSyntheticEvent<NativeScrollEvent>) {
    setPolicyPage(Math.round(e.nativeEvent.contentOffset.x / (POLICY_W + 12)));
  }

  return (
    <>
      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={Colors.primaryMid} />}
      >
        <View style={styles.topBar}>
          <Pressable style={styles.avatarBtn} onPress={() => router.push('/(tabs)/profile')}>
            <Text style={styles.avatarText}>
              {String(clientName).trim().charAt(0).toUpperCase() || 'U'}
            </Text>
          </Pressable>
          <View style={{ flex: 1 }}>
            <Text style={styles.hello}>
              {client?.first_name ? `Hello, ${client.first_name}` : 'Account Center'}
            </Text>
            <Text style={styles.orgLine}>{String(orgName).toUpperCase()}</Text>
          </View>
          <Pressable style={styles.iconBtn} onPress={() => setAlertsOpen(true)}>
            <Text style={styles.bell}>🔔</Text>
            {alertCount > 0 ? (
              <View style={styles.badge}>
                <Text style={styles.badgeText}>{alertCount > 9 ? '9+' : alertCount}</Text>
              </View>
            ) : null}
          </Pressable>
        </View>

        {error ? (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}

        <View style={styles.linkedCard}>
          <View style={styles.linkedIcon}>
            <Text style={{ fontSize: 16 }}>🛡️</Text>
          </View>
          <Text style={styles.linkedText}>
            Linked Agent: {agent.name || orgName}
            {agent.organization_name && agent.name !== agent.organization_name
              ? ` — ${agent.organization_name}`
              : ''}
          </Text>
        </View>

        <Text style={styles.section}>ACTIVE POLICY</Text>
        {!policies.length ? (
          <View style={styles.softCard}>
            <Text style={styles.muted}>No active policies yet.</Text>
          </View>
        ) : (
          <>
            <ScrollView
              ref={policyScrollRef}
              horizontal
              showsHorizontalScrollIndicator={false}
              decelerationRate="fast"
              snapToInterval={POLICY_W + 12}
              contentContainerStyle={{ paddingRight: 16 }}
              onScroll={onPolicyScroll}
              scrollEventThrottle={16}
            >
              {policies.slice(0, 6).map((p: any) => (
                <Pressable
                  key={p.id}
                  style={[styles.policyCard, { width: POLICY_W }]}
                  onPress={() => router.push(`/policy/${p.id}`)}
                >
                  <View style={styles.policyTop}>
                    <Text style={styles.policyShield}>✦</Text>
                    <Text style={styles.policyChevron}>›››</Text>
                  </View>
                  <Text style={styles.policyKind}>
                    {p.insurance_type_display || p.status_display || 'Active Insurance'}
                  </Text>
                  <Text style={styles.policyVehicle}>
                    {p.vehicle_label ? `Vehicle: ${p.vehicle_label}` : p.company || 'Carrier'}
                  </Text>
                  <View style={styles.policyMeta}>
                    <Text style={styles.policyMetaLine}>Policyholder · {p.named_insured || clientName}</Text>
                    <Text style={styles.policyMetaLine}>Policy # · {p.policy_number}</Text>
                    <Text style={styles.policyMetaLine}>
                      Expires · {p.end_date || p.renewal_date || '—'}
                    </Text>
                    {p.next_due_amount ? (
                      <Text style={styles.policyMetaLine}>Next due · {money(p.next_due_amount)}</Text>
                    ) : null}
                  </View>
                </Pressable>
              ))}
            </ScrollView>
            <View style={styles.dots}>
              {policies.slice(0, 6).map((_: any, i: number) => (
                <View key={i} style={[styles.dot, i === policyPage && styles.dotActive]} />
              ))}
            </View>
          </>
        )}

        {next ? (
          <Pressable
            style={styles.payCard}
            onPress={() => next.policy_id && router.push(`/policy/${next.policy_id}`)}
          >
            <Text style={styles.payLabel}>NEXT PAYMENT DUE</Text>
            <Text style={styles.payDate}>{next.due_date}</Text>
            <Text style={styles.payAmount}>{money(next.amount)}</Text>
            <Text style={styles.payMeta}>
              Policy #{next.policy_number}
              {next.company ? ` · ${next.company}` : ''}
            </Text>
          </Pressable>
        ) : null}

        <Text style={styles.section}>YOUR AGENT</Text>
        <View style={styles.agentCard}>
          <View style={styles.agentRow}>
            <View style={styles.agentAvatar}>
              <Text style={styles.agentAvatarText}>
                {String(agent.name || 'A').charAt(0).toUpperCase()}
              </Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.agentName}>{agent.name || orgName}</Text>
              <Text style={styles.agentOrg}>{agent.organization_name || orgName}</Text>
            </View>
            {chatUnread > 0 ? (
              <View style={styles.unreadPill}>
                <Text style={styles.unreadText}>{chatUnread}</Text>
              </View>
            ) : null}
          </View>
          <Pressable style={styles.chatBtn} onPress={() => router.push('/(tabs)/chat')}>
            <Text style={styles.chatBtnText}>CHAT NOW</Text>
          </Pressable>
          <Text style={styles.chatHint}>Need assistance? Chat with your dedicated agent.</Text>
        </View>

        <View style={styles.sectionRow}>
          <Text style={styles.section}>DMV VEHICLES</Text>
          <Link href="/(tabs)/vehicles" asChild>
            <Pressable>
              <Text style={styles.link}>See all</Text>
            </Pressable>
          </Link>
        </View>
        {!vehicles.length ? (
          <View style={styles.softCard}>
            <Text style={styles.muted}>No fleet vehicles on file yet.</Text>
          </View>
        ) : (
          vehicles.map((v: any) => (
            <Pressable
              key={String(v.id)}
              style={styles.row}
              onPress={() => router.push(`/vehicle/${v.id}`)}
            >
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>{v.label}</Text>
                <Text style={styles.muted}>
                  Plate {v.plate_number || '—'}
                  {v.registration_expiration_date ? ` · Reg exp ${v.registration_expiration_date}` : ''}
                </Text>
                <View style={styles.docChips}>
                  <Text style={[styles.miniChip, v.has_registration && styles.miniChipOk]}>
                    {v.has_registration ? 'Reg ✓' : 'Reg —'}
                  </Text>
                  <Text style={[styles.miniChip, v.has_title && styles.miniChipOk]}>
                    {v.has_title ? 'Title ✓' : 'Title —'}
                  </Text>
                </View>
              </View>
              <Text style={styles.chevron}>›</Text>
            </Pressable>
          ))
        )}

        <View style={styles.sectionRow}>
          <Text style={styles.section}>LATEST SERVICES</Text>
          <Link href="/(tabs)/services" asChild>
            <Pressable>
              <Text style={styles.link}>See all</Text>
            </Pressable>
          </Link>
        </View>
        {!services.length ? (
          <View style={styles.softCard}>
            <Text style={styles.muted}>No DMV services requested yet.</Text>
          </View>
        ) : (
          services.slice(0, 4).map((s: any) => (
            <Pressable
              key={String(s.id)}
              style={styles.row}
              onPress={() => (s.vehicle_id ? router.push(`/vehicle/${s.vehicle_id}`) : router.push('/(tabs)/services'))}
            >
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>{s.title}</Text>
                <Text style={styles.muted}>
                  {s.transaction_date || '—'}
                  {s.plate_number ? ` · Plate ${s.plate_number}` : ''}
                </Text>
              </View>
              <Text style={[styles.status, { color: statusColor(s.status) }]}>
                {(s.status_display || s.status || '').toUpperCase()}
              </Text>
            </Pressable>
          ))
        )}

        <View style={styles.quickRow}>
          <Pressable style={styles.quickTile} onPress={() => router.push('/(tabs)/documents')}>
            <Text style={styles.quickTitle}>Documents</Text>
            <Text style={styles.quickSub}>Vault</Text>
          </Pressable>
          <Pressable style={styles.quickTile} onPress={() => router.push('/(tabs)/id-cards')}>
            <Text style={styles.quickTitle}>ID Cards</Text>
            <Text style={styles.quickSub}>License & IDs</Text>
          </Pressable>
          <Pressable style={styles.quickTile} onPress={() => router.push('/(tabs)/receipts')}>
            <Text style={styles.quickTitle}>Receipts</Text>
            <Text style={styles.quickSub}>Payments</Text>
          </Pressable>
        </View>
      </ScrollView>

      <Modal visible={alertsOpen} transparent animationType="slide" onRequestClose={() => setAlertsOpen(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>Notifications</Text>
              <Pressable onPress={() => setAlertsOpen(false)}>
                <Text style={styles.link}>Close</Text>
              </Pressable>
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
                      if (a.vehicle_id) router.push(`/vehicle/${a.vehicle_id}`);
                      else if (a.policy_id) router.push(`/policy/${a.policy_id}`);
                    }}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={styles.rowTitle}>{a.title}</Text>
                      <Text style={styles.muted}>
                        {a.date}
                        {a.message ? ` · ${a.message}` : ''}
                      </Text>
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
  screen: { flex: 1, backgroundColor: Colors.cream },
  content: { padding: 16, paddingBottom: 40 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.cream },
  topBar: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 },
  avatarBtn: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: Colors.navy,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: Colors.gold, fontWeight: '800', fontSize: 16 },
  hello: { fontSize: 18, fontWeight: '800', color: Colors.navy },
  orgLine: { color: Colors.muted, fontSize: 10, fontWeight: '800', letterSpacing: 0.8, marginTop: 2 },
  iconBtn: {
    width: 42,
    height: 42,
    borderRadius: 14,
    backgroundColor: Colors.white,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  bell: { fontSize: 16 },
  badge: {
    position: 'absolute',
    top: -4,
    right: -4,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: Colors.danger,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 4,
  },
  badgeText: { color: '#fff', fontSize: 10, fontWeight: '800' },
  errorBox: { backgroundColor: Colors.dangerLight, borderRadius: 12, padding: 12, marginBottom: 12 },
  errorText: { color: Colors.danger, fontWeight: '600', fontSize: 13 },
  linkedCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: Colors.white,
    borderRadius: Radius.lg,
    padding: 12,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadows.card,
  },
  linkedIcon: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: Colors.primarySubtle,
    alignItems: 'center',
    justifyContent: 'center',
  },
  linkedText: { flex: 1, fontWeight: '700', color: Colors.navy, fontSize: 13 },
  section: {
    fontSize: 11,
    fontWeight: '800',
    color: Colors.muted,
    letterSpacing: 0.8,
    marginBottom: 10,
    marginTop: 4,
  },
  sectionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 4,
    marginBottom: 10,
  },
  link: { color: Colors.primaryMid, fontWeight: '700', fontSize: 13 },
  policyCard: {
    backgroundColor: Colors.policyTeal,
    borderRadius: Radius.xl,
    padding: 16,
    marginRight: 12,
    minHeight: 180,
    ...Shadows.card,
  },
  policyTop: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  policyShield: { color: Colors.gold, fontSize: 18, fontWeight: '800' },
  policyChevron: { color: 'rgba(255,255,255,0.7)', fontWeight: '800', letterSpacing: 1 },
  policyKind: { color: '#fff', fontSize: 18, fontWeight: '800' },
  policyVehicle: { color: 'rgba(255,255,255,0.9)', marginTop: 4, fontWeight: '600', fontSize: 13 },
  policyMeta: { marginTop: 14, gap: 3 },
  policyMetaLine: { color: 'rgba(255,255,255,0.85)', fontSize: 12, fontWeight: '600' },
  dots: { flexDirection: 'row', justifyContent: 'center', gap: 6, marginVertical: 12 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: Colors.borderDark },
  dotActive: { backgroundColor: Colors.navy, width: 16 },
  payCard: {
    backgroundColor: Colors.white,
    borderRadius: Radius.lg,
    padding: 16,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadows.card,
  },
  payLabel: { color: Colors.muted, fontWeight: '800', fontSize: 11, letterSpacing: 0.6 },
  payDate: { color: Colors.navy, fontWeight: '800', fontSize: 16, marginTop: 6 },
  payAmount: { color: Colors.navy, fontWeight: '800', fontSize: 28, marginTop: 4 },
  payMeta: { color: Colors.muted, marginTop: 6, fontSize: 12 },
  agentCard: {
    backgroundColor: Colors.white,
    borderRadius: Radius.lg,
    padding: 14,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadows.card,
  },
  agentRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 },
  agentAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: Colors.navy,
    alignItems: 'center',
    justifyContent: 'center',
  },
  agentAvatarText: { color: Colors.gold, fontWeight: '800', fontSize: 16 },
  agentName: { fontWeight: '800', color: Colors.navy, fontSize: 15 },
  agentOrg: { color: Colors.muted, fontSize: 12, marginTop: 2 },
  unreadPill: {
    minWidth: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: Colors.chatOrange,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  unreadText: { color: '#fff', fontWeight: '800', fontSize: 11 },
  chatBtn: {
    backgroundColor: Colors.chatOrange,
    borderRadius: Radius.md,
    paddingVertical: 13,
    alignItems: 'center',
  },
  chatBtnText: { color: '#fff', fontWeight: '800', letterSpacing: 0.6 },
  chatHint: { textAlign: 'center', color: Colors.muted, fontSize: 11, marginTop: 8 },
  row: {
    backgroundColor: Colors.white,
    borderRadius: Radius.md,
    padding: 14,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: Colors.border,
    flexDirection: 'row',
    alignItems: 'center',
  },
  rowTitle: { fontWeight: '800', color: Colors.navy, fontSize: 14 },
  muted: { color: Colors.muted, fontSize: 12, marginTop: 2 },
  softCard: {
    backgroundColor: Colors.white,
    borderRadius: Radius.md,
    padding: 14,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  chevron: { fontSize: 20, color: Colors.mutedLight },
  docChips: { flexDirection: 'row', gap: 6, marginTop: 6 },
  miniChip: {
    fontSize: 10,
    fontWeight: '800',
    color: Colors.muted,
    backgroundColor: Colors.borderSubtle,
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    borderRadius: 6,
  },
  miniChipOk: { color: Colors.success, backgroundColor: Colors.successLight },
  status: { fontWeight: '800', fontSize: 10, marginLeft: 8 },
  quickRow: { flexDirection: 'row', gap: 8, marginTop: 12 },
  quickTile: {
    flex: 1,
    backgroundColor: Colors.white,
    borderRadius: Radius.md,
    padding: 12,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  quickTitle: { fontWeight: '800', color: Colors.navy, fontSize: 13 },
  quickSub: { color: Colors.muted, fontSize: 11, marginTop: 2 },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(15,23,42,0.45)', justifyContent: 'flex-end' },
  modalSheet: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    maxHeight: '70%',
    padding: 16,
  },
  modalHead: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 12 },
  modalTitle: { fontSize: 18, fontWeight: '800', color: Colors.navy },
});

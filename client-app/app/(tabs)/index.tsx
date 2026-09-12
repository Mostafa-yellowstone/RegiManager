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

import { Colors, Radius, Shadows } from '@/constants/theme';
import { fetchHome } from '@/lib/api';
import { useAuth } from '@/lib/auth';

function formatMoney(value?: string | null) {
  if (!value) return '—';
  return value.startsWith('$') ? value : `$${value}`;
}

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
      const home = await fetchHome();
      setData(home);
    } catch (err: any) {
      setError(err?.message || 'Could not load account center');
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
  const orgName = data?.organization_name || 'RegiManager';

  const quickActions = [
    { href: '/(tabs)/policies', label: 'Policies', subtitle: 'Coverage records', icon: 'P' },
    { href: '/(tabs)/id-cards', label: 'ID Cards', subtitle: 'Insurance cards', icon: 'ID' },
    { href: '/(tabs)/documents', label: 'Documents', subtitle: 'Secure vault', icon: 'DV' },
    { href: '/(tabs)/vehicles', label: 'Vehicles', subtitle: 'Registered units', icon: 'VH' },
    { href: '/(tabs)/receipts', label: 'Receipts', subtitle: 'Service history', icon: 'RC' },
    { href: '/(tabs)/profile', label: 'Profile', subtitle: 'Account & prefs', icon: 'PR' },
  ] as const;

  return (
    <>
      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl refreshing={loading} onRefresh={load} tintColor={Colors.primaryMid} />
        }
      >
        <View style={styles.headerBand}>
          <View style={{ flex: 1 }}>
            <Text style={styles.orgEyebrow}>{String(orgName).toUpperCase()}</Text>
            <Text style={styles.greeting}>
              {client?.first_name ? `${client.first_name}'s Account` : 'Client Account Center'}
            </Text>
            <Text style={styles.sub}>Official insurance & DMV client portal</Text>
          </View>
          <Pressable
            style={({ pressed }) => [styles.bellBtn, pressed && styles.pressed]}
            onPress={() => setAlertsOpen(true)}
            accessibilityLabel="Open notifications"
          >
            <Text style={styles.bellIcon}>🔔</Text>
            {alertCount > 0 ? (
              <View style={styles.bellBadge}>
                <Text style={styles.bellBadgeText}>{alertCount > 9 ? '9+' : alertCount}</Text>
              </View>
            ) : null}
          </Pressable>
        </View>

        {error ? (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}

        <View style={styles.heroCard}>
          <View style={styles.heroHeader}>
            <Text style={styles.heroLabel}>NEXT PAYMENT DUE</Text>
            <View style={next ? styles.duePill : styles.paidPill}>
              <Text style={next ? styles.duePillText : styles.paidPillText}>
                {next ? 'ACTION REQUIRED' : 'CURRENT'}
              </Text>
            </View>
          </View>
          {next ? (
            <>
              <Text style={styles.heroAmount}>{formatMoney(next.amount)}</Text>
              <Text style={styles.heroMeta}>
                Due {next.due_date} · Policy #{next.policy_number}
                {next.company ? ` · ${next.company}` : ''}
              </Text>
              {next.remaining_amount ? (
                <Text style={styles.heroRemain}>
                  Remaining on schedule: {formatMoney(next.remaining_amount)}
                  {next.remaining_payments != null ? ` · ${next.remaining_payments} open` : ''}
                </Text>
              ) : null}
              <Pressable
                style={styles.heroCta}
                onPress={() => router.push(`/policy/${next.policy_id}`)}
              >
                <Text style={styles.heroCtaText}>View installment schedule</Text>
              </Pressable>
            </>
          ) : (
            <Text style={styles.heroAmount}>No pending installments</Text>
          )}
        </View>

        <Text style={styles.sectionTitle}>OFFICIAL SERVICES</Text>
        <View style={styles.actionsGrid}>
          {quickActions.map((action) => (
            <Link key={action.href} href={action.href as any} asChild>
              <Pressable style={({ pressed }) => [styles.actionTile, pressed && styles.pressed]}>
                <View style={styles.actionIcon}>
                  <Text style={styles.actionIconText}>{action.icon}</Text>
                </View>
                <Text style={styles.actionLabel}>{action.label}</Text>
                <Text style={styles.actionSub}>{action.subtitle}</Text>
              </Pressable>
            </Link>
          ))}
        </View>

        <View style={styles.sectionHeaderRow}>
          <Text style={styles.sectionTitle}>UPCOMING</Text>
          <Text style={styles.seeAllText}>{upcoming.length} items</Text>
        </View>
        {!upcoming.length ? (
          <View style={styles.emptySoft}>
            <Text style={styles.emptySoftText}>No expirations or dues in the next 90 days.</Text>
          </View>
        ) : (
          upcoming.slice(0, 5).map((item: any) => (
            <Pressable
              key={item.id}
              style={({ pressed }) => [styles.listRow, pressed && styles.pressed]}
              onPress={() => {
                if (item.policy_id) router.push(`/policy/${item.policy_id}`);
                else if (item.vehicle_id) router.push('/(tabs)/vehicles');
              }}
            >
              <View style={styles.listAccent} />
              <View style={{ flex: 1 }}>
                <Text style={styles.listTitle}>{item.title}</Text>
                <Text style={styles.listMeta}>
                  {item.date}
                  {item.subtitle ? ` · ${item.subtitle}` : ''}
                </Text>
              </View>
              {item.amount ? <Text style={styles.listAmount}>{formatMoney(item.amount)}</Text> : null}
            </Pressable>
          ))
        )}

        <View style={styles.sectionHeaderRow}>
          <Text style={styles.sectionTitle}>VEHICLES</Text>
          <Link href="/(tabs)/vehicles" asChild>
            <Pressable>
              <Text style={styles.seeAllText}>See all ›</Text>
            </Pressable>
          </Link>
        </View>
        {(data?.vehicles || []).slice(0, 3).map((v: any) => (
          <View key={v.id} style={styles.listRow}>
            <View style={[styles.listAccent, { backgroundColor: Colors.teal }]} />
            <View style={{ flex: 1 }}>
              <Text style={styles.listTitle}>{v.label || 'Vehicle'}</Text>
              <Text style={styles.listMeta}>
                {[v.plate_number && `Plate ${v.plate_number}`, v.vin && `VIN ${v.vin}`]
                  .filter(Boolean)
                  .join(' · ') || 'No plate on file'}
              </Text>
            </View>
          </View>
        ))}
        {!data?.vehicles?.length ? (
          <View style={styles.emptySoft}>
            <Text style={styles.emptySoftText}>No vehicles linked to this account yet.</Text>
          </View>
        ) : null}

        <View style={styles.sectionHeaderRow}>
          <Text style={styles.sectionTitle}>RECENT RECEIPTS</Text>
          <Link href="/(tabs)/receipts" asChild>
            <Pressable>
              <Text style={styles.seeAllText}>See all ›</Text>
            </Pressable>
          </Link>
        </View>
        {(data?.recent_receipts || []).slice(0, 3).map((r: any) => (
          <View key={r.id} style={styles.listRow}>
            <View style={[styles.listAccent, { backgroundColor: Colors.warning }]} />
            <View style={{ flex: 1 }}>
              <Text style={styles.listTitle}>{r.receipt_number}</Text>
              <Text style={styles.listMeta}>
                {r.transaction_date || '—'} · {r.service_type || r.transaction_type || 'Service'}
              </Text>
            </View>
            <Text style={styles.listAmount}>{formatMoney(r.service_fee)}</Text>
          </View>
        ))}
        {!data?.recent_receipts?.length ? (
          <View style={styles.emptySoft}>
            <Text style={styles.emptySoftText}>No service receipts on file.</Text>
          </View>
        ) : null}

        <View style={styles.sectionHeaderRow}>
          <Text style={styles.sectionTitle}>ACTIVE POLICIES</Text>
          <Link href="/(tabs)/policies" asChild>
            <Pressable>
              <Text style={styles.seeAllText}>See all ›</Text>
            </Pressable>
          </Link>
        </View>
        {(data?.policies || []).slice(0, 4).map((p: any) => (
          <Link key={p.id} href={`/policy/${p.id}`} asChild>
            <Pressable style={({ pressed }) => [styles.policyRow, pressed && styles.pressed]}>
              <View style={{ flex: 1 }}>
                <Text style={styles.policyTitle}>{p.policy_number}</Text>
                <Text style={styles.policyMeta}>
                  {p.company || 'Carrier'}
                  {p.next_due_date ? ` · Next due ${p.next_due_date}` : ''}
                </Text>
              </View>
              <Text style={styles.chevron}>›</Text>
            </Pressable>
          </Link>
        ))}
      </ScrollView>

      <Modal visible={alertsOpen} animationType="slide" transparent onRequestClose={() => setAlertsOpen(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Notifications</Text>
              <Pressable onPress={() => setAlertsOpen(false)}>
                <Text style={styles.modalClose}>Close</Text>
              </Pressable>
            </View>
            <ScrollView contentContainerStyle={{ paddingBottom: 24 }}>
              {!alerts.length ? (
                <Text style={styles.emptySoftText}>No alerts right now. You’re up to date.</Text>
              ) : (
                alerts.map((alert: any) => (
                  <Pressable
                    key={alert.id}
                    style={styles.alertRow}
                    onPress={() => {
                      setAlertsOpen(false);
                      if (alert.policy_id) router.push(`/policy/${alert.policy_id}`);
                    }}
                  >
                    <View
                      style={[
                        styles.alertDot,
                        { backgroundColor: alert.level === 'warning' ? Colors.warning : Colors.primaryMid },
                      ]}
                    />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.listTitle}>{alert.title}</Text>
                      <Text style={styles.listMeta}>
                        {alert.date}
                        {alert.message ? ` · ${alert.message}` : ''}
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
  content: { padding: 18, paddingBottom: 48 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.cream },
  headerBand: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 18,
    marginTop: 2,
    gap: 12,
  },
  orgEyebrow: {
    color: Colors.primaryMid,
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 1.1,
    marginBottom: 4,
  },
  greeting: { fontSize: 24, fontWeight: '800', color: Colors.navy, letterSpacing: -0.4 },
  sub: { color: Colors.muted, marginTop: 4, fontSize: 13, fontWeight: '500' },
  bellBtn: {
    width: 46,
    height: 46,
    borderRadius: 14,
    backgroundColor: Colors.white,
    borderWidth: 1,
    borderColor: Colors.border,
    alignItems: 'center',
    justifyContent: 'center',
    ...Shadows.card,
  },
  bellIcon: { fontSize: 18 },
  bellBadge: {
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
    borderWidth: 2,
    borderColor: Colors.cream,
  },
  bellBadgeText: { color: Colors.white, fontSize: 10, fontWeight: '800' },
  errorBox: {
    backgroundColor: Colors.dangerLight,
    borderWidth: 1,
    borderColor: '#FCA5A5',
    borderRadius: Radius.md,
    padding: 12,
    marginBottom: 16,
  },
  errorText: { color: Colors.danger, fontSize: 13, fontWeight: '600' },
  heroCard: {
    backgroundColor: Colors.navy,
    borderRadius: Radius.xl,
    padding: 20,
    marginBottom: 22,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
  },
  heroHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  heroLabel: { color: '#94A3B8', fontWeight: '800', fontSize: 11, letterSpacing: 0.8 },
  duePill: {
    backgroundColor: 'rgba(217,119,6,0.2)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 8,
  },
  duePillText: { color: '#FBBF24', fontSize: 10, fontWeight: '800', letterSpacing: 0.4 },
  paidPill: {
    backgroundColor: 'rgba(5,150,105,0.2)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 8,
  },
  paidPillText: { color: '#34D399', fontSize: 10, fontWeight: '800', letterSpacing: 0.4 },
  heroAmount: { color: Colors.white, fontSize: 32, fontWeight: '800', marginTop: 10, letterSpacing: -0.5 },
  heroMeta: { color: '#CBD5E1', fontSize: 13, fontWeight: '500', marginTop: 8 },
  heroRemain: { color: '#94A3B8', fontSize: 12, marginTop: 6, fontWeight: '600' },
  heroCta: {
    marginTop: 14,
    alignSelf: 'flex-start',
    backgroundColor: Colors.primaryMid,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 10,
  },
  heroCtaText: { color: Colors.white, fontWeight: '800', fontSize: 12 },
  sectionTitle: {
    fontSize: 12,
    fontWeight: '800',
    color: Colors.muted,
    marginBottom: 12,
    letterSpacing: 0.9,
  },
  sectionHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 8,
    marginBottom: 12,
  },
  seeAllText: { fontSize: 12, fontWeight: '700', color: Colors.primaryMid },
  actionsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 22 },
  actionTile: {
    width: '31%',
    flexGrow: 1,
    minWidth: '30%',
    backgroundColor: Colors.white,
    borderRadius: Radius.md,
    padding: 14,
    borderWidth: 1,
    borderColor: Colors.border,
    borderLeftWidth: 3,
    borderLeftColor: Colors.navy,
    ...Shadows.card,
  },
  actionIcon: {
    width: 34,
    height: 34,
    borderRadius: 8,
    backgroundColor: Colors.navy,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 10,
  },
  actionIconText: { color: Colors.white, fontSize: 11, fontWeight: '800', letterSpacing: 0.4 },
  actionLabel: { color: Colors.navy, fontWeight: '800', fontSize: 13 },
  actionSub: { color: Colors.muted, fontSize: 11, marginTop: 2, fontWeight: '500' },
  listRow: {
    backgroundColor: Colors.white,
    borderRadius: Radius.md,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
    flexDirection: 'row',
    alignItems: 'center',
    overflow: 'hidden',
  },
  listAccent: { width: 4, alignSelf: 'stretch', backgroundColor: Colors.primaryMid, marginRight: 12, borderRadius: 2 },
  listTitle: { fontWeight: '800', color: Colors.navy, fontSize: 14 },
  listMeta: { color: Colors.muted, marginTop: 3, fontSize: 12, fontWeight: '500' },
  listAmount: { fontWeight: '800', color: Colors.navy, fontSize: 14, marginLeft: 8 },
  emptySoft: {
    backgroundColor: Colors.white,
    borderRadius: Radius.md,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  emptySoftText: { color: Colors.muted, fontSize: 13, fontWeight: '500' },
  policyRow: {
    backgroundColor: Colors.white,
    borderRadius: Radius.md,
    padding: 16,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
    flexDirection: 'row',
    alignItems: 'center',
  },
  policyTitle: { fontWeight: '800', color: Colors.navy, fontSize: 15 },
  policyMeta: { color: Colors.muted, marginTop: 3, fontSize: 12, fontWeight: '500' },
  chevron: { fontSize: 22, color: Colors.mutedLight, fontWeight: '300' },
  pressed: { opacity: 0.92 },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(11,25,44,0.45)', justifyContent: 'flex-end' },
  modalSheet: {
    backgroundColor: Colors.white,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    maxHeight: '72%',
    padding: 18,
  },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  modalTitle: { fontSize: 18, fontWeight: '800', color: Colors.navy },
  modalClose: { color: Colors.primaryMid, fontWeight: '700', fontSize: 14 },
  alertRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: Colors.borderSubtle,
  },
  alertDot: { width: 8, height: 8, borderRadius: 4, marginTop: 6, marginRight: 10 },
});

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
import { Link, useFocusEffect, useRouter } from 'expo-router';

import { Colors, Radius, Shadows } from '@/constants/theme';
import { fetchVehicles } from '@/lib/api';

export default function VehiclesScreen() {
  const router = useRouter();
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const data = await fetchVehicles();
      setRows(data.results || []);
    } catch (err: any) {
      setError(err?.message || 'Could not load vehicles');
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

  const fleet = rows.filter((v) => v.source !== 'policy');
  const policyOnly = rows.filter((v) => v.source === 'policy');

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={Colors.primaryMid} />}
    >
      <Text style={styles.h1}>DMV Vehicles</Text>
      <Text style={styles.sub}>Registrations, titles, plates & service history</Text>
      {error ? <Text style={styles.error}>{error}</Text> : null}

      <Link href="/(tabs)/services" asChild>
        <Pressable style={styles.servicesBanner}>
          <Text style={styles.servicesBannerTitle}>Latest services</Text>
          <Text style={styles.servicesBannerSub}>See registrations, renewals & titles you requested →</Text>
        </Pressable>
      </Link>

      {!rows.length && !loading ? (
        <Text style={styles.empty}>No vehicles linked yet. Ask your agency to register one.</Text>
      ) : null}

      {fleet.length ? <Text style={styles.section}>YOUR FLEET</Text> : null}
      {fleet.map((v) => (
        <Pressable
          key={String(v.id)}
          style={styles.card}
          onPress={() => router.push(`/vehicle/${v.id}`)}
        >
          <View style={styles.top}>
            <Text style={styles.title}>{v.label || 'Vehicle'}</Text>
            <View style={styles.pillFleet}>
              <Text style={styles.pillText}>DMV</Text>
            </View>
          </View>
          <Text style={styles.meta}>
            {v.vehicle_type_display || 'Vehicle'}
            {v.color ? ` · ${v.color}` : ''}
          </Text>
          <View style={styles.grid}>
            <View style={styles.cell}>
              <Text style={styles.label}>PLATE</Text>
              <Text style={styles.value}>{v.plate_number || '—'}</Text>
            </View>
            <View style={styles.cell}>
              <Text style={styles.label}>VIN</Text>
              <Text style={styles.value} numberOfLines={1}>
                {v.vin || '—'}
              </Text>
            </View>
          </View>
          <View style={styles.docRow}>
            <View style={[styles.docChip, v.has_registration ? styles.docOk : styles.docMissing]}>
              <Text style={styles.docChipText}>{v.has_registration ? 'Registration on file' : 'No registration'}</Text>
            </View>
            <View style={[styles.docChip, v.has_title ? styles.docOk : styles.docMissing]}>
              <Text style={styles.docChipText}>{v.has_title ? 'Title on file' : 'No title'}</Text>
            </View>
          </View>
          {v.registration_expiration_date ? (
            <Text style={styles.exp}>Reg expires {v.registration_expiration_date}</Text>
          ) : v.latest_service ? (
            <Text style={styles.serviceHint}>
              Latest: {v.latest_service.title} · {v.latest_service.status_display}
            </Text>
          ) : null}
          <Text style={styles.openHint}>Tap for registration, title & services →</Text>
        </Pressable>
      ))}

      {policyOnly.length ? <Text style={styles.section}>ON INSURANCE POLICIES</Text> : null}
      {policyOnly.map((v) => (
        <View key={String(v.id)} style={[styles.card, styles.cardMuted]}>
          <View style={styles.top}>
            <Text style={styles.title}>{v.label || 'Vehicle'}</Text>
            <View style={styles.pillPolicy}>
              <Text style={styles.pillText}>POLICY</Text>
            </View>
          </View>
          <Text style={styles.meta}>
            Policy {v.policy_number || '—'}
            {v.plate_number ? ` · Plate ${v.plate_number}` : ''}
          </Text>
          <Text style={styles.serviceHint}>DMV registration & title live on fleet vehicles.</Text>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.cream },
  content: { padding: 16, paddingBottom: 40 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.cream },
  h1: { fontSize: 22, fontWeight: '800', color: Colors.navy },
  sub: { color: Colors.muted, marginBottom: 14, marginTop: 2, fontSize: 13 },
  section: {
    fontSize: 11,
    fontWeight: '800',
    color: Colors.muted,
    letterSpacing: 0.8,
    marginBottom: 10,
    marginTop: 8,
  },
  error: { color: Colors.danger, marginBottom: 10, fontWeight: '600' },
  empty: { color: Colors.muted, marginTop: 12 },
  servicesBanner: {
    backgroundColor: Colors.navy,
    borderRadius: Radius.lg,
    padding: 14,
    marginBottom: 16,
    ...Shadows.card,
  },
  servicesBannerTitle: { color: Colors.gold, fontWeight: '800', fontSize: 13, letterSpacing: 0.4 },
  servicesBannerSub: { color: '#E2E8F0', marginTop: 4, fontSize: 13, fontWeight: '600' },
  card: {
    backgroundColor: Colors.white,
    borderRadius: Radius.lg,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
    borderLeftWidth: 4,
    borderLeftColor: Colors.policyTeal,
    ...Shadows.card,
  },
  cardMuted: { borderLeftColor: Colors.borderDark, opacity: 0.95 },
  top: { flexDirection: 'row', justifyContent: 'space-between', gap: 8, alignItems: 'center' },
  title: { fontSize: 16, fontWeight: '800', color: Colors.navy, flex: 1 },
  pillFleet: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8, backgroundColor: Colors.policyTealSoft },
  pillPolicy: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8, backgroundColor: Colors.primarySubtle },
  pillText: { fontSize: 10, fontWeight: '800', color: Colors.navy },
  meta: { color: Colors.muted, marginTop: 4, fontSize: 12 },
  grid: { flexDirection: 'row', marginTop: 12, gap: 12 },
  cell: { flex: 1 },
  label: { fontSize: 10, fontWeight: '800', color: Colors.mutedLight, letterSpacing: 0.6 },
  value: { fontSize: 13, fontWeight: '700', color: Colors.navy, marginTop: 2 },
  docRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 12 },
  docChip: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8 },
  docOk: { backgroundColor: Colors.successLight },
  docMissing: { backgroundColor: Colors.borderSubtle },
  docChipText: { fontSize: 11, fontWeight: '700', color: Colors.navy },
  exp: { marginTop: 10, color: Colors.warning, fontWeight: '700', fontSize: 12 },
  serviceHint: { marginTop: 8, color: Colors.muted, fontSize: 12, fontWeight: '600' },
  openHint: { marginTop: 10, color: Colors.primaryMid, fontWeight: '700', fontSize: 12 },
});

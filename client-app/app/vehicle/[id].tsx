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
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';

import { Colors, Radius, Shadows } from '@/constants/theme';
import { DocumentViewerModal } from '@/components/DocumentViewer';
import { fetchVehicle } from '@/lib/api';

function statusColor(status?: string) {
  const s = (status || '').toLowerCase();
  if (s === 'completed') return Colors.success;
  if (s === 'pending') return Colors.warning;
  if (s === 'failed' || s === 'refund') return Colors.danger;
  return Colors.muted;
}

type ViewerTarget = {
  kind: string;
  id: number | string;
  title: string;
  fileNameHint?: string | null;
} | null;

export default function VehicleDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [viewer, setViewer] = useState<ViewerTarget>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setError('');
    try {
      setData(await fetchVehicle(id));
    } catch (err: any) {
      setError(err?.message || 'Could not load vehicle');
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

  function openDoc(doc: any | null, fallbackLabel: string) {
    if (!doc?.id) {
      setError(`${fallbackLabel} is not uploaded yet. Ask your agency.`);
      return;
    }
    setError('');
    setViewer({
      kind: 'dmv',
      id: doc.id,
      title: doc.title || fallbackLabel,
      fileNameHint: doc.file_name || null,
    });
  }

  if (loading && !data) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={Colors.primaryMid} size="large" />
      </View>
    );
  }

  const services = data?.services || [];
  const documents = data?.documents || [];

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
          <View style={styles.hero}>
            <Text style={styles.heroEyebrow}>VEHICLE</Text>
            <Text style={styles.heroTitle}>{data.label || 'Vehicle'}</Text>
            <Text style={styles.heroMeta}>
              {[data.vehicle_type_display, data.color, data.plate_type_display].filter(Boolean).join(' · ') ||
                'DMV fleet unit'}
            </Text>
            <View style={styles.heroGrid}>
              <View style={styles.heroCell}>
                <Text style={styles.heroLabel}>PLATE</Text>
                <Text style={styles.heroValue}>{data.plate_number || '—'}</Text>
              </View>
              <View style={styles.heroCell}>
                <Text style={styles.heroLabel}>VIN</Text>
                <Text style={styles.heroValue} numberOfLines={1}>
                  {data.vin || '—'}
                </Text>
              </View>
            </View>
          </View>

          <View style={styles.card}>
            <Text style={styles.cardTitle}>Registration</Text>
            <View style={styles.rowBetween}>
              <Text style={styles.muted}>Effective</Text>
              <Text style={styles.bold}>{data.registration_effective_date || '—'}</Text>
            </View>
            <View style={styles.rowBetween}>
              <Text style={styles.muted}>Expires</Text>
              <Text style={[styles.bold, data.registration_expiration_date && { color: Colors.warning }]}>
                {data.registration_expiration_date || '—'}
              </Text>
            </View>
            <Pressable
              style={[styles.primaryBtn, !data.registration_document && styles.btnDisabled]}
              onPress={() => openDoc(data.registration_document, 'Registration')}
            >
              <Text style={styles.primaryBtnText}>
                {data.registration_document ? 'View Registration' : 'Registration not uploaded'}
              </Text>
            </Pressable>
          </View>

          <View style={styles.card}>
            <Text style={styles.cardTitle}>Certificate of Title</Text>
            <Text style={styles.mutedSmall}>
              {data.has_title
                ? 'Title document is on file with your agency.'
                : 'Ask your agency to upload the title certificate.'}
            </Text>
            <Pressable
              style={[styles.outlineBtn, !data.title_document && styles.btnDisabled]}
              onPress={() => openDoc(data.title_document, 'Title')}
            >
              <Text style={styles.outlineBtnText}>
                {data.title_document ? 'View Title' : 'Title not uploaded'}
              </Text>
            </Pressable>
          </View>

          <View style={styles.sectionRow}>
            <Text style={styles.section}>LATEST SERVICES</Text>
            <Pressable onPress={() => router.push('/(tabs)/services')}>
              <Text style={styles.link}>See all</Text>
            </Pressable>
          </View>
          {!services.length ? (
            <View style={styles.card}>
              <Text style={styles.muted}>No DMV services on this vehicle yet.</Text>
            </View>
          ) : (
            services.slice(0, 8).map((s: any) => (
              <View key={String(s.id)} style={styles.serviceRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.serviceTitle}>{s.title}</Text>
                  <Text style={styles.mutedSmall}>
                    {s.transaction_date || '—'}
                    {s.receipt_number ? ` · ${s.receipt_number}` : ''}
                  </Text>
                </View>
                <Text style={[styles.status, { color: statusColor(s.status) }]}>
                  {(s.status_display || s.status || '').toUpperCase()}
                </Text>
              </View>
            ))
          )}

          <Text style={styles.section}>ALL DOCUMENTS</Text>
          {!documents.length ? (
            <View style={styles.card}>
              <Text style={styles.muted}>No DMV files attached to this vehicle.</Text>
            </View>
          ) : (
            documents.map((doc: any) => (
              <Pressable
                key={String(doc.id)}
                style={styles.docRow}
                onPress={() => openDoc(doc, doc.title || 'Document')}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.serviceTitle}>{doc.title}</Text>
                  <Text style={styles.mutedSmall}>
                    {(doc.wallet_role || doc.document_type_display || '').toString().replace(/_/g, ' ')}
                    {doc.uploaded_at ? ` · ${String(doc.uploaded_at).slice(0, 10)}` : ''}
                  </Text>
                </View>
                <Text style={styles.link}>View</Text>
              </Pressable>
            ))
          )}
        </>
      ) : null}

      {viewer ? (
        <DocumentViewerModal
          visible
          kind={viewer.kind}
          id={viewer.id}
          title={viewer.title}
          fileNameHint={viewer.fileNameHint}
          onClose={() => setViewer(null)}
        />
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.cream },
  content: { padding: 16, paddingBottom: 40 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.cream },
  errorBox: {
    backgroundColor: Colors.dangerLight,
    borderRadius: Radius.md,
    padding: 12,
    marginBottom: 12,
  },
  errorText: { color: Colors.danger, fontWeight: '600', fontSize: 13 },
  hero: {
    backgroundColor: Colors.navy,
    borderRadius: Radius.xl,
    padding: 18,
    marginBottom: 14,
    ...Shadows.card,
  },
  heroEyebrow: { color: Colors.gold, fontWeight: '800', fontSize: 11, letterSpacing: 0.8 },
  heroTitle: { color: '#fff', fontSize: 22, fontWeight: '800', marginTop: 6 },
  heroMeta: { color: '#CBD5E1', marginTop: 6, fontSize: 13 },
  heroGrid: { flexDirection: 'row', gap: 10, marginTop: 16 },
  heroCell: { flex: 1, backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: Radius.md, padding: 10 },
  heroLabel: { color: '#94A3B8', fontSize: 10, fontWeight: '800', letterSpacing: 0.6 },
  heroValue: { color: '#fff', fontWeight: '800', marginTop: 4, fontSize: 13 },
  card: {
    backgroundColor: Colors.white,
    borderRadius: Radius.lg,
    padding: 14,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: Colors.border,
    ...Shadows.card,
  },
  cardTitle: { fontSize: 16, fontWeight: '800', color: Colors.navy, marginBottom: 10 },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  muted: { color: Colors.muted, fontSize: 13 },
  mutedSmall: { color: Colors.muted, fontSize: 12, marginBottom: 10 },
  bold: { color: Colors.navy, fontWeight: '800', fontSize: 13 },
  primaryBtn: {
    marginTop: 8,
    backgroundColor: Colors.navy,
    borderRadius: Radius.md,
    paddingVertical: 13,
    alignItems: 'center',
  },
  primaryBtnText: { color: '#fff', fontWeight: '800', fontSize: 14 },
  outlineBtn: {
    marginTop: 4,
    borderWidth: 1.5,
    borderColor: Colors.navy,
    borderRadius: Radius.md,
    paddingVertical: 12,
    alignItems: 'center',
    backgroundColor: Colors.white,
  },
  outlineBtnText: { color: Colors.navy, fontWeight: '800', fontSize: 14 },
  btnDisabled: { opacity: 0.55 },
  section: {
    fontSize: 11,
    fontWeight: '800',
    color: Colors.muted,
    letterSpacing: 0.8,
    marginBottom: 10,
    marginTop: 6,
  },
  sectionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 6,
    marginBottom: 10,
  },
  link: { color: Colors.primaryMid, fontWeight: '700', fontSize: 13 },
  serviceRow: {
    backgroundColor: Colors.white,
    borderRadius: Radius.md,
    padding: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: Colors.border,
    flexDirection: 'row',
    alignItems: 'center',
  },
  serviceTitle: { fontWeight: '800', color: Colors.navy, fontSize: 14 },
  status: { fontWeight: '800', fontSize: 10, marginLeft: 8 },
  docRow: {
    backgroundColor: Colors.white,
    borderRadius: Radius.md,
    padding: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: Colors.border,
    flexDirection: 'row',
    alignItems: 'center',
  },
});

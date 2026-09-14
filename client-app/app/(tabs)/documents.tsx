import { useCallback, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useFocusEffect } from 'expo-router';

import { Colors, Radius, Shadows } from '@/constants/theme';
import { ApiError, fetchDocuments } from '@/lib/api';
import { openClientDocument } from '@/lib/openDocument';

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'registration', label: 'Registration' },
  { key: 'title', label: 'Title' },
  { key: 'insurance', label: 'Insurance' },
  { key: 'other', label: 'Other' },
] as const;

export default function DocumentsScreen() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [openingId, setOpeningId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<(typeof FILTERS)[number]['key']>('all');

  const load = useCallback(async () => {
    setError('');
    try {
      const data = await fetchDocuments();
      setRows(data.results || []);
    } catch (err: any) {
      setError(err?.message || 'Could not load documents');
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

  const filtered = useMemo(() => {
    if (filter === 'all') return rows;
    if (filter === 'insurance') return rows.filter((d) => d.kind === 'insurance');
    if (filter === 'registration') {
      return rows.filter((d) => d.kind === 'dmv' && (d.wallet_role === 'registration' || d.document_type === 'registration' || d.document_type === 'mv82'));
    }
    if (filter === 'title') {
      return rows.filter((d) => d.kind === 'dmv' && (d.wallet_role === 'title' || d.document_type === 'title'));
    }
    return rows.filter((d) => {
      if (d.kind !== 'dmv') return false;
      const role = d.wallet_role || 'other';
      return role === 'other';
    });
  }, [rows, filter]);

  async function onOpen(doc: any) {
    const key = `${doc.kind}-${doc.id}`;
    setError('');
    setOpeningId(key);
    try {
      await openClientDocument(doc.kind, doc.id, doc.title || doc.document_type_display);
    } catch (err: any) {
      setError(err instanceof ApiError ? err.message : err?.message || 'Could not open file');
    } finally {
      setOpeningId(null);
    }
  }

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
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={Colors.primaryMid} />}
    >
      <View style={styles.headerBox}>
        <Text style={styles.headerTitle}>Document Vault</Text>
        <Text style={styles.headerSubtitle}>
          Registrations, titles, insurance files & more ({rows.length})
        </Text>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}>
        {FILTERS.map((f) => (
          <Pressable
            key={f.key}
            style={[styles.chip, filter === f.key && styles.chipActive]}
            onPress={() => setFilter(f.key)}
          >
            <Text style={[styles.chipText, filter === f.key && styles.chipTextActive]}>{f.label}</Text>
          </Pressable>
        ))}
      </ScrollView>

      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}

      {!filtered.length && !loading ? (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyTitle}>Nothing in this filter</Text>
          <Text style={styles.emptyText}>Ask your agency to upload registration or title documents.</Text>
        </View>
      ) : null}

      {filtered.map((doc) => {
        const key = `${doc.kind}-${doc.id}`;
        const busy = openingId === key;
        const isDmv = doc.kind === 'dmv';
        const role = isDmv ? doc.wallet_role || doc.document_type : 'insurance';
        return (
          <Pressable
            key={key}
            style={({ pressed }) => [styles.row, pressed && styles.pressedRow]}
            onPress={() => onOpen(doc)}
            disabled={!!openingId}
          >
            <View
              style={[
                styles.iconAvatar,
                {
                  backgroundColor:
                    role === 'title'
                      ? Colors.goldSoft
                      : role === 'registration'
                        ? Colors.policyTealSoft
                        : isDmv
                          ? '#FEF3C7'
                          : Colors.primarySubtle,
                },
              ]}
            >
              <Text style={styles.iconEmoji}>
                {role === 'title' ? '📜' : role === 'registration' ? '🪪' : isDmv ? '🚘' : '📄'}
              </Text>
            </View>

            <View style={{ flex: 1 }}>
              <View style={styles.kindBadgeRow}>
                <View style={styles.kindBadge}>
                  <Text style={styles.kindText}>
                    {isDmv
                      ? String(role || 'DMV').toUpperCase().replace(/_/g, ' ')
                      : 'INSURANCE'}
                  </Text>
                </View>
              </View>
              <Text style={styles.title}>{doc.title || doc.document_type_display}</Text>
              <Text style={styles.meta}>
                {doc.vehicle_label || doc.policy_number || doc.document_type_display || ''}
                {doc.plate_number ? ` · Plate ${doc.plate_number}` : ''}
              </Text>
            </View>

            <View style={styles.actionCol}>
              {busy ? (
                <ActivityIndicator color={Colors.primaryMid} size="small" />
              ) : (
                <View style={styles.openPill}>
                  <Text style={styles.openText}>View</Text>
                </View>
              )}
            </View>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.cream },
  content: { padding: 18, paddingBottom: 40 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.cream },
  headerBox: { marginBottom: 12, marginTop: 4 },
  headerTitle: { fontSize: 22, fontWeight: '800', color: Colors.navy, letterSpacing: -0.3 },
  headerSubtitle: { color: Colors.muted, fontSize: 13, fontWeight: '500', marginTop: 2 },
  filters: { gap: 8, marginBottom: 14 },
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: Radius.pill,
    backgroundColor: Colors.white,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  chipActive: { backgroundColor: Colors.navy, borderColor: Colors.navy },
  chipText: { fontWeight: '700', fontSize: 12, color: Colors.navy },
  chipTextActive: { color: '#fff' },
  errorBox: {
    backgroundColor: Colors.dangerLight,
    borderWidth: 1,
    borderColor: '#FCA5A5',
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
  },
  errorText: { color: Colors.danger, fontSize: 13, fontWeight: '600' },
  emptyCard: {
    backgroundColor: Colors.white,
    borderRadius: 20,
    padding: 32,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  emptyTitle: { fontSize: 18, fontWeight: '800', color: Colors.navy },
  emptyText: { color: Colors.muted, fontSize: 13, textAlign: 'center', marginTop: 4 },
  row: {
    backgroundColor: Colors.white,
    borderRadius: 18,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: Colors.border,
    flexDirection: 'row',
    alignItems: 'center',
    ...Shadows.card,
  },
  pressedRow: { opacity: 0.9, transform: [{ scale: 0.995 }] },
  iconAvatar: {
    width: 46,
    height: 46,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 14,
  },
  iconEmoji: { fontSize: 22 },
  kindBadgeRow: { flexDirection: 'row', marginBottom: 4 },
  kindBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: Colors.borderSubtle },
  kindText: { fontSize: 10, fontWeight: '800', letterSpacing: 0.6, color: Colors.navy },
  title: { fontWeight: '800', color: Colors.navy, fontSize: 15, letterSpacing: -0.2 },
  meta: { color: Colors.muted, marginTop: 3, fontSize: 12, fontWeight: '500' },
  actionCol: { marginLeft: 10 },
  openPill: {
    backgroundColor: Colors.primarySubtle,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 10,
  },
  openText: { color: Colors.navy, fontWeight: '800', fontSize: 12 },
});

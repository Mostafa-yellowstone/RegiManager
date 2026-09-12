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
import { useFocusEffect } from 'expo-router';

import { Colors } from '@/constants/theme';
import { ApiError, fetchDocuments } from '@/lib/api';
import { openClientDocument } from '@/lib/openDocument';

export default function DocumentsScreen() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [openingId, setOpeningId] = useState<string | null>(null);
  const [error, setError] = useState('');

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
      refreshControl={
        <RefreshControl
          refreshing={loading}
          onRefresh={load}
          tintColor={Colors.primaryMid}
        />
      }
    >
      {/* Intro Header */}
      <View style={styles.headerBox}>
        <Text style={styles.headerTitle}>Document Vault</Text>
        <Text style={styles.headerSubtitle}>
          {rows.length} verified document{rows.length === 1 ? '' : 's'} & certificates stored
        </Text>
      </View>

      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}

      {!rows.length && !loading ? (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyIcon}>📂</Text>
          <Text style={styles.emptyTitle}>No Documents Found</Text>
          <Text style={styles.emptyText}>Your agency has not uploaded any official policy or DMV documents yet.</Text>
        </View>
      ) : null}

      {rows.map((doc) => {
        const key = `${doc.kind}-${doc.id}`;
        const busy = openingId === key;
        const isDmv = doc.kind === 'dmv';
        return (
          <Pressable
            key={key}
            style={({ pressed }) => [styles.row, pressed && styles.pressedRow]}
            onPress={() => onOpen(doc)}
            disabled={!!openingId}
          >
            <View style={[styles.iconAvatar, { backgroundColor: isDmv ? '#FEF3C7' : Colors.primarySubtle }]}>
              <Text style={styles.iconEmoji}>{isDmv ? '🚘' : '📄'}</Text>
            </View>

            <View style={{ flex: 1 }}>
              <View style={styles.kindBadgeRow}>
                <View
                  style={[
                    styles.kindBadge,
                    { backgroundColor: isDmv ? 'rgba(217, 119, 6, 0.12)' : 'rgba(37, 99, 235, 0.12)' },
                  ]}
                >
                  <Text
                    style={[
                      styles.kindText,
                      { color: isDmv ? Colors.warning : Colors.primaryMid },
                    ]}
                  >
                    {isDmv ? 'DMV RECORD' : 'INSURANCE'}
                  </Text>
                </View>
              </View>

              <Text style={styles.title}>{doc.title || doc.document_type_display}</Text>
              <Text style={styles.meta}>
                {doc.document_type_display}
                {doc.policy_number ? ` · Policy ${doc.policy_number}` : ''}
              </Text>
            </View>

            <View style={styles.actionCol}>
              {busy ? (
                <ActivityIndicator color={Colors.primaryMid} size="small" />
              ) : (
                <View style={styles.openPill}>
                  <Text style={styles.openText}>View File</Text>
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
  emptyCard: {
    backgroundColor: Colors.white,
    borderRadius: 20,
    padding: 32,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  emptyIcon: { fontSize: 44, marginBottom: 12 },
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
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.03,
    shadowRadius: 8,
    elevation: 2,
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
  kindBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 },
  kindText: {
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.6,
  },
  title: { fontWeight: '800', color: Colors.navy, fontSize: 15, letterSpacing: -0.2 },
  meta: { color: Colors.muted, marginTop: 3, fontSize: 12, fontWeight: '500' },
  actionCol: { marginLeft: 10 },
  openPill: {
    backgroundColor: Colors.primarySubtle,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: 'rgba(37, 99, 235, 0.2)',
  },
  openText: { color: Colors.primaryMid, fontWeight: '800', fontSize: 12 },
});
